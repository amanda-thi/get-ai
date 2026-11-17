"""Orkestrasi Company Leads (Fase 3): discovery -> dedupe -> simpan + kontak.

Data mentah perusahaan disimpan di `companies`; status CRM di `company_leads`
(satu baris per perusahaan); kontak bisnis publik di `company_contacts`.
Tidak ada data dummy: input yang gagal dicatat apa adanya.
"""
from __future__ import annotations

from ..config import Settings
from ..db import SupabaseClient, SupabaseError
from ..discovery.base import DiscoveryError, RawCompany, RawContact
from ..discovery.search import search_companies
from ..discovery.website import collect_from_url
from ..utils.text import normalize_text
from ..utils.web import canonical_website, domain_of, normalize_url
from .collection import log_event

_CONTACT_TYPES = ("email", "phone")


def normalize_company_name(name: str | None) -> str:
    """Kunci dedupe nama perusahaan (huruf kecil, tanpa tanda baca)."""
    return normalize_text(name)


def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def find_company(db: SupabaseClient, name: str, website: str | None) -> dict | None:
    """Cari perusahaan yang sudah ada (nama ternormalisasi + situs/domain sama)."""
    norm = normalize_company_name(name)
    site = canonical_website(website) or (website or "")
    if norm:
        rows = db.select(
            "companies",
            {"select": "*", "normalized_name": f"eq.{norm}", "limit": "10"},
        )
        for r in rows:
            if (r.get("website") or "") == site:
                return r
    if site:
        rows = db.select("companies", {"select": "*", "website": f"eq.{site}", "limit": "1"})
        if rows:
            return rows[0]
    return None


def _save_contacts(db: SupabaseClient, company_id: str, contacts: list[RawContact]) -> int:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for c in contacts:
        ctype = (c.contact_type or "").strip().lower()
        value = _clean(c.value)
        if ctype not in _CONTACT_TYPES or not value:
            continue
        key = (ctype, value)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "company_id": company_id,
                "contact_type": ctype,
                "value": value,
                "source_url": _clean(c.source_url) or "manual",
            }
        )
    if not rows:
        return 0
    db.insert(
        "company_contacts",
        rows,
        upsert=True,
        on_conflict="company_id,contact_type,value",
        returning=False,
    )
    return len(rows)


def _ensure_lead(db: SupabaseClient, company_id: str) -> None:
    """Pastikan ada satu baris `company_leads` (status awal 'new')."""
    try:
        db.insert("company_leads", {"company_id": company_id, "status": "new"}, returning=False)
    except SupabaseError as e:  # sudah ada (unique company_id) -> abaikan
        if "409" not in str(e) and "duplicate" not in str(e).lower():
            raise


def save_company(db: SupabaseClient, raw: RawCompany, *, user_id: str | None = None) -> dict:
    """Simpan perusahaan + kontak. Deteksi duplikat lebih dulu (tidak membuat baris ganda)."""
    website = canonical_website(raw.website) or _clean(raw.website)
    existing = find_company(db, raw.name, website)
    if existing:
        return {"company": existing, "created": False, "duplicate_of": existing["id"], "contacts_added": 0}

    row = {
        "name": (raw.name or "").strip()[:300] or "Tanpa nama",
        "normalized_name": normalize_company_name(raw.name),
        "industry": _clean(raw.industry),
        "description": _clean(raw.description),
        "address": _clean(raw.address),
        "city": _clean(raw.city),
        "province": _clean(raw.province),
        "website": website,
        "source_name": _clean(raw.source_name) or "manual",
        "source_url": _clean(raw.source_url) or website or "manual",
    }
    try:
        created = db.insert("companies", row)
    except SupabaseError as e:
        if "409" in str(e) or "duplicate" in str(e).lower():
            existing = find_company(db, raw.name, website)
            if existing:
                return {"company": existing, "created": False, "duplicate_of": existing["id"], "contacts_added": 0}
        raise
    company = created[0] if created else row
    _ensure_lead(db, company["id"])
    contacts_added = _save_contacts(db, company["id"], raw.contacts)
    return {"company": company, "created": True, "duplicate_of": None, "contacts_added": contacts_added}


def _raw_from_item(item: dict) -> RawCompany:
    """Bangun RawCompany dari input manual/impor."""
    name = _clean(item.get("name")) or "Tanpa nama"
    website = normalize_url(item.get("website")) or _clean(item.get("website"))
    source_url = _clean(item.get("source_url")) or website or "manual"
    source_name = _clean(item.get("source_name")) or "manual"
    contacts: list[RawContact] = []
    for email in item.get("emails") or []:
        if _clean(email):
            contacts.append(RawContact("email", str(email).strip(), source_url))
    for phone in item.get("phones") or []:
        if _clean(phone):
            contacts.append(RawContact("phone", str(phone).strip(), source_url))
    return RawCompany(
        name=name,
        website=website,
        industry=_clean(item.get("industry")),
        description=_clean(item.get("description")),
        address=_clean(item.get("address")),
        city=_clean(item.get("city")),
        province=_clean(item.get("province")),
        source_name=source_name,
        source_url=source_url,
        contacts=contacts,
    )


def discover(
    db: SupabaseClient,
    settings: Settings,
    *,
    items: list[dict] | None = None,
    urls: list[str] | None = None,
    query: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    limit: int = 10,
    user_id: str | None = None,
    client=None,
) -> dict:
    """Kumpulkan calon perusahaan dari beberapa cara, lalu simpan dengan dedupe.

    Cara: `items` (manual/impor), `urls` (situs publik), `query` (API pencarian, butuh kunci).
    """
    raw_companies: list[RawCompany] = []
    errors: list[dict] = []

    for item in items or []:
        if not isinstance(item, dict):
            continue
        raw_companies.append(_raw_from_item(item))

    for url in urls or []:
        if not _clean(url):
            continue
        try:
            raw_companies.append(collect_from_url(str(url).strip(), settings, client=client))
        except DiscoveryError as e:
            errors.append({"input": url, "error": str(e)})

    if query and str(query).strip():
        try:
            raw_companies.extend(
                search_companies(
                    str(query).strip(),
                    industry=industry,
                    location=location,
                    limit=limit,
                    settings=settings,
                    client=client,
                )
            )
        except DiscoveryError as e:
            errors.append({"input": f"search:{query}", "error": str(e)})

    created = 0
    duplicates = 0
    results: list[dict] = []
    for raw in raw_companies:
        try:
            res = save_company(db, raw, user_id=user_id)
        except SupabaseError as e:
            errors.append({"input": raw.name, "error": str(e)})
            continue
        if res["created"]:
            created += 1
        else:
            duplicates += 1
        results.append(
            {
                "company_id": res["company"]["id"],
                "name": res["company"]["name"],
                "website": res["company"].get("website"),
                "created": res["created"],
                "duplicate_of": res["duplicate_of"],
                "contacts_added": res["contacts_added"],
            }
        )

    if raw_companies:
        log_event(
            db, "info", "leads",
            f"Discovery: {created} baru, {duplicates} duplikat, {len(errors)} gagal",
            {"created": created, "duplicates": duplicates, "errors": len(errors)},
        )
    return {
        "found": len(raw_companies),
        "created": created,
        "duplicates": duplicates,
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


def add_contact(
    db: SupabaseClient, company_id: str, contact_type: str, value: str, source_url: str
) -> dict:
    ctype = (contact_type or "").strip().lower()
    if ctype not in _CONTACT_TYPES:
        raise ValueError("contact_type harus 'email' atau 'phone'")
    val = _clean(value)
    if not val:
        raise ValueError("value kontak wajib diisi")
    rows = db.insert(
        "company_contacts",
        {"company_id": company_id, "contact_type": ctype, "value": val, "source_url": _clean(source_url) or "manual"},
        upsert=True,
        on_conflict="company_id,contact_type,value",
    )
    return rows[0] if rows else {}


def domain_matches(company: dict, url: str | None) -> bool:
    """True bila `url` berada di domain yang sama dengan situs perusahaan."""
    d1 = domain_of(company.get("website"))
    d2 = domain_of(url)
    return bool(d1 and d2 and d1 == d2)
