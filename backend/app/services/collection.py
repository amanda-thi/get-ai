"""Orkestrasi koleksi tender: adapter -> keyword -> dedupe -> upsert -> kesehatan sumber + log.

Tidak ada data dummy: bila sumber tidak bisa diakses, status kesehatan sumber
diperbarui dan kejadian dicatat di `system_logs`, bukan menghasilkan data palsu.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import Settings
from ..db import SupabaseClient, SupabaseError
from ..sources.base import RawTender, SourceError
from ..sources.registry import build_adapter
from ..utils.text import dedupe_hash, iso

log = logging.getLogger(__name__)

UPSERT_BATCH = 200  # simpan per batch agar payload PostgREST tetap wajar


def active_keywords(db: SupabaseClient) -> list[str]:
    rows = db.select(
        "tender_keywords",
        {"select": "keyword", "is_active": "eq.true", "order": "keyword.asc"},
    )
    return [r["keyword"] for r in rows if r.get("keyword")]


def log_event(db: SupabaseClient, level: str, component: str, message: str, details: dict | None = None) -> None:
    """Tulis ke system_logs; kegagalan log tidak boleh menggagalkan koleksi."""
    try:
        db.insert(
            "system_logs",
            {"level": level, "component": component, "message": message, "details": details or {}},
            returning=False,
        )
    except SupabaseError as e:  # pragma: no cover - jalur error I/O
        log.warning("gagal menulis system_logs: %s", e)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _update_health(db: SupabaseClient, source_id: str, status: str, error: str | None) -> None:
    now = _now_iso()
    values = {"health_status": status, "last_checked_at": now, "last_error": error}
    if status == "ok":
        values["last_success_at"] = now
    try:
        db.update("tender_sources", {"id": f"eq.{source_id}"}, values, returning=False)
    except SupabaseError as e:  # pragma: no cover - jalur error I/O
        log.warning("gagal memperbarui kesehatan sumber %s: %s", source_id, e)


def tender_row(source_id: str, t: RawTender, seen_at: str) -> dict:
    """Baris `tenders` untuk upsert. `first_seen_at` TIDAK disertakan agar tidak tertimpa."""
    return {
        "source_id": source_id,
        "external_id": t.external_id,
        "dedupe_hash": dedupe_hash(source_id, t.external_id, t.package_name, t.agency),
        "package_name": t.package_name,
        "agency": t.agency,
        "location": t.location,
        "procurement_type": t.procurement_type,
        "description": t.description,
        "technical_specs": t.technical_specs,
        "budget_ceiling": t.budget_ceiling,
        "hps": t.hps,
        "announced_at": iso(t.announced_at),
        "registration_start": iso(t.registration_start),
        "registration_end": iso(t.registration_end),
        "bid_deadline": iso(t.bid_deadline),
        "participant_requirements": t.participant_requirements,
        "status": t.status,
        "source_url": t.source_url,
        "raw_payload": t.raw_payload,
        "matched_keywords": t.matched_keywords,
        "last_seen_at": seen_at,
    }


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def collect_source(
    db: SupabaseClient,
    source: dict,
    keywords: list[str],
    settings: Settings,
    options: dict | None = None,
) -> dict:
    """Kumpulkan satu sumber. Selalu mengembalikan ringkasan; tidak melempar ke pemanggil."""
    options = dict(options or {})
    sid = source["id"]
    name = source.get("name") or sid
    try:
        adapter = build_adapter(source, settings)
    except SourceError as e:
        _update_health(db, sid, "manual_only", str(e))
        log_event(
            db, "warning", "collection", f"Sumber '{name}' dilewati: {e}",
            {"source_id": sid, "adapter_type": source.get("adapter_type")},
        )
        return {"source_id": sid, "name": name, "status": "manual_only", "found": 0, "upserted": 0, "error": str(e)}

    try:
        with adapter:
            found = adapter.discover(keywords, options)
    except SourceError as e:
        status = "blocked" if ("403" in str(e) or "menolak" in str(e)) else "failed"
        _update_health(db, sid, status, str(e))
        log_event(db, "error", "collection", f"Gagal mengambil dari '{name}': {e}", {"source_id": sid})
        return {"source_id": sid, "name": name, "status": status, "found": 0, "upserted": 0, "error": str(e)}

    seen = _now_iso()
    rows = [tender_row(sid, t, seen) for t in found if t.package_name and t.source_url]
    upserted = 0
    try:
        for chunk in _chunks(rows, UPSERT_BATCH):
            db.insert("tenders", chunk, upsert=True, on_conflict="dedupe_hash", returning=False)
            upserted += len(chunk)
    except SupabaseError as e:
        _update_health(db, sid, "failed", f"Gagal simpan: {e}")
        log_event(db, "error", "collection", f"Gagal menyimpan tender '{name}': {e}", {"source_id": sid})
        return {"source_id": sid, "name": name, "status": "failed", "found": len(found), "upserted": upserted, "error": str(e)}

    _update_health(db, sid, "ok", None)
    log_event(
        db, "info", "collection",
        f"'{name}': {len(found)} cocok keyword, {upserted} disimpan/diperbarui",
        {"source_id": sid, "matched": len(found), "upserted": upserted},
    )
    return {"source_id": sid, "name": name, "status": "ok", "found": len(found), "upserted": upserted, "error": None}


def collect_all(
    db: SupabaseClient,
    settings: Settings,
    *,
    source_ids: list[str] | None = None,
    keywords: list[str] | None = None,
    options: dict | None = None,
) -> dict:
    """Kumpulkan dari semua (atau sebagian) sumber aktif."""
    if keywords is None:
        keywords = active_keywords(db)
    params = {
        "select": "id,name,adapter_type,base_url,config,is_active",
        "is_active": "eq.true",
        "order": "name.asc",
    }
    if source_ids:
        params["id"] = f"in.({','.join(source_ids)})"
    sources = db.select("tender_sources", params)
    results = [collect_source(db, s, keywords, settings, options) for s in sources]
    return {
        "keywords_used": len(keywords),
        "sources_total": len(sources),
        "sources_ok": sum(1 for r in results if r["status"] == "ok"),
        "upserted_total": sum(r["upserted"] for r in results),
        "sources": results,
    }
