"""Adapter SPSE Nasional (spse.inaproc.id) — portal pengadaan publik LKPP.

Diuji langsung 16 Nov 2026:
  * daftar : POST /nasional/dt/lelang?tahun=YYYY (DataTables server-side)
  * detail : GET  /nasional/lelang/<id>/pengumumanlelang
  * jadwal : GET  /nasional/lelang/<id>/jadwal

Halaman-halaman ini PUBLIK (robots.txt: Allow: /). Yang dibutuhkan hanya cookie sesi
dan `authenticityToken` yang memang dirender di halaman — bukan CAPTCHA, bukan login.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from ..utils.text import (
    JAKARTA,
    match_keywords,
    parse_id_date,
    parse_id_datetime,
    parse_rupiah,
    strip_html,
)
from .base import HealthResult, RawTender, SourceAdapter, SourceError

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"authenticityToken\s*[:=]\s*['\"]([A-Za-z0-9_-]{8,})['\"]", re.IGNORECASE)
_COOKIE_TOKEN_RE = re.compile(r"___AT=([A-Za-z0-9_-]+)")
_TR_RE = re.compile(r"(?s)<tr[^>]*>(.*?)</tr>")
_CELL_RE = re.compile(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>")
_YEAR_RE = re.compile(r"TA\s*(\d{4})", re.IGNORECASE)

# label di halaman detail -> kunci internal
_DETAIL_LABELS = {
    "Kode Tender": "external_id",
    "Nama Tender": "package_name",
    "Kode RUP": "rup_code",
    "Nama Paket": "rup_package",
    "Sumber Dana": "funding_source",
    "Uraian Singkat Pekerjaan": "description",
    "Tanggal Pembuatan": "announced_raw",
    "Tahap Tender Saat Ini": "status",
    "K/L/PD/Instansi Lainnya": "agency",
    "Satuan Kerja": "satker",
    "Jenis Pengadaan": "procurement_type",
    "Metode Pengadaan": "method",
    "Tahun Anggaran": "budget_years",
    "Nilai Pagu Paket": "budget_ceiling_raw",
    "Nilai HPS Paket": "hps_raw",
    "Jenis Kontrak": "contract_type",
    "Lokasi Pekerjaan": "location",
    "Syarat Kualifikasi": "participant_requirements",
}

# tahap -> peran tanggal
_STAGE_ROLE = {
    "pengumuman": "announce",
    "kirim persyaratan kualifikasi": "submit",
    "pemasukan dokumen penawaran": "submit",
    "upload dokumen penawaran": "submit",
    "upload dokumen": "submit",
    "penawaran": "submit",
}


def parse_list_row(row: list) -> dict:
    """Petakan satu baris DataTables SPSE (array) menjadi dict ternormalisasi."""
    get = lambda i: row[i] if i < len(row) else None  # noqa: E731
    category_year = strip_html(get(8))
    year_match = _YEAR_RE.search(category_year or "")
    return {
        "external_id": str(get(0)).strip() if get(0) is not None else None,
        "package_name": strip_html(get(1)),
        "agency": strip_html(get(2)) or None,
        "status": strip_html(get(3)) or None,
        "hps": parse_rupiah(get(4)),
        "method": strip_html(get(5)) or None,
        "procurement_type": strip_html(get(6)) or None,
        "evaluation": strip_html(get(7)) or None,
        "category_year": category_year or None,
        "budget_year": int(year_match.group(1)) if year_match else None,
        "contract_value": parse_rupiah(get(10)),
    }


def parse_detail_fields(html: str) -> dict[str, str]:
    """Ambil pasangan label->nilai dari tabel halaman detail."""
    fields: dict[str, str] = {}
    for tr in _TR_RE.finditer(html or ""):
        cells = [strip_html(c) for c in _CELL_RE.findall(tr.group(1))]
        for i in range(0, len(cells) - 1, 2):
            label, value = cells[i], cells[i + 1]
            if label in _DETAIL_LABELS and value:
                fields.setdefault(_DETAIL_LABELS[label], value)
    return fields


def parse_schedule(html: str) -> list[dict]:
    """Ambil tahapan jadwal: [{no, stage, start_raw, end_raw, changed}]."""
    stages: list[dict] = []
    for tr in _TR_RE.finditer(html or ""):
        cells = [strip_html(c) for c in _CELL_RE.findall(tr.group(1))]
        if len(cells) >= 4 and cells[0].isdigit():
            stages.append(
                {
                    "no": cells[0],
                    "stage": cells[1],
                    "start_raw": cells[2],
                    "end_raw": cells[3],
                    "changed": cells[4] if len(cells) > 4 else None,
                }
            )
    return stages


def derive_schedule_dates(stages: list[dict]) -> dict:
    """Turunkan registration_start/end & bid_deadline dari tahapan jadwal."""
    out: dict = {"registration_start": None, "registration_end": None, "bid_deadline": None}
    for stage in stages:
        name = (stage.get("stage") or "").lower()
        start = parse_id_datetime(stage.get("start_raw"))
        end = parse_id_datetime(stage.get("end_raw"))
        if out["registration_start"] is None and "pengumuman" in name and start:
            out["registration_start"] = start
        for needle, role in _STAGE_ROLE.items():
            if needle in name:
                if role == "submit" and end:
                    out["registration_end"] = end
                    out["bid_deadline"] = end
                break
    return out


class SpseNasionalAdapter(SourceAdapter):
    adapter_type = "spse"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._token: str | None = None

    # --- sesi publik (cookie + authenticity token) ---
    def _bootstrap(self) -> None:
        url = f"{self.base_url}/nasional/lelang"
        try:
            r = self.client.get(url)
        except Exception as e:  # noqa: BLE001 - jadikan SourceError seragam
            raise SourceError(f"SPSE tidak terjangkau: {e}") from e
        if r.status_code >= 500:
            raise SourceError(f"SPSE error {r.status_code}")
        html = r.text
        token = None
        m = _TOKEN_RE.search(html)
        if m:
            token = m.group(1)
        if not token:
            m = _COOKIE_TOKEN_RE.search(r.headers.get("set-cookie", ""))
            if m:
                token = m.group(1)
        if not token:
            raise SourceError("authenticity token tidak ditemukan (struktur halaman berubah?)")
        self._token = token

    def _post_datatable(self, year: int, start: int, length: int) -> dict:
        if not self._token:
            self._bootstrap()
        url = f"{self.base_url}/nasional/dt/lelang?tahun={year}"
        data = {
            "authenticityToken": self._token or "",
            "draw": "1",
            "start": str(start),
            "length": str(length),
            "search[value]": "",
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}/nasional/lelang",
            "Origin": self.base_url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            r = self.client.post(url, data=data, headers=headers)
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"SPSE tidak terjangkau: {e}") from e
        if r.status_code == 403:
            # sesi/token kedaluwarsa -> bootstrap ulang sekali
            self._token = None
            self._bootstrap()
            data["authenticityToken"] = self._token or ""
            r = self.client.post(url, data=data, headers=headers)
        if r.status_code != 200:
            raise SourceError(f"SPSE datatable gagal ({r.status_code})")
        try:
            return r.json()
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"Respons SPSE bukan JSON: {e}") from e

    def fetch_year(self, year: int, max_rows: int) -> list[dict]:
        """Ambil semua baris untuk satu tahun anggaran (dengan paginasi), dibatasi max_rows."""
        rows: list[dict] = []
        page = 1000
        start = 0
        while len(rows) < max_rows:
            payload = self._post_datatable(year, start, page)
            data = payload.get("data") or []
            if not data:
                break
            rows.extend(data)
            if len(data) < page:
                break
            start += page
        return rows[:max_rows]

    # --- detail & jadwal ---
    def _detail_url(self, external_id: str) -> str:
        return f"{self.base_url}/nasional/lelang/{external_id}/pengumumanlelang"

    def _schedule_url(self, external_id: str) -> str:
        return f"{self.base_url}/nasional/lelang/{external_id}/jadwal"

    def _get_html(self, url: str) -> str:
        headers = {"Referer": f"{self.base_url}/nasional/lelang"}
        try:
            r = self.client.get(url, headers=headers)
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"SPSE tidak terjangkau: {e}") from e
        if r.status_code == 403:
            self._token = None
            self._bootstrap()
            r = self.client.get(url, headers=headers)
        if r.status_code != 200:
            raise SourceError(f"SPSE halaman gagal ({r.status_code}) untuk {url}")
        return r.text

    def fetch_detail(self, external_id: str) -> dict:
        return parse_detail_fields(self._get_html(self._detail_url(external_id)))

    def fetch_schedule(self, external_id: str) -> list[dict]:
        return parse_schedule(self._get_html(self._schedule_url(external_id)))

    def enrich(self, tender: RawTender) -> RawTender:
        if not tender.external_id:
            return tender
        fields = self.fetch_detail(tender.external_id)
        if fields.get("package_name"):
            tender.package_name = fields["package_name"]
        tender.description = fields.get("description") or tender.description
        tender.agency = fields.get("agency") or tender.agency
        tender.location = fields.get("location") or tender.location
        tender.procurement_type = fields.get("procurement_type") or tender.procurement_type
        tender.participant_requirements = fields.get("participant_requirements")
        tender.status = fields.get("status") or tender.status
        tender.budget_ceiling = parse_rupiah(fields.get("budget_ceiling_raw"))
        tender.hps = parse_rupiah(fields.get("hps_raw")) or tender.hps
        tender.announced_at = parse_id_date(fields.get("announced_raw")) or tender.announced_at
        tender.technical_specs = fields.get("method")
        tender.raw_payload = {**tender.raw_payload, "detail": fields}
        try:
            stages = self.fetch_schedule(tender.external_id)
        except SourceError:
            stages = []
        if stages:
            dates = derive_schedule_dates(stages)
            tender.registration_start = dates["registration_start"] or tender.registration_start
            tender.registration_end = dates["registration_end"] or tender.registration_end
            tender.bid_deadline = dates["bid_deadline"] or tender.bid_deadline
            tender.raw_payload["schedule"] = stages
        return tender

    # --- API utama ---
    def discover(self, keywords: list[str], options: dict | None = None) -> list[RawTender]:
        options = options or {}
        years = options.get("years")
        if not years:
            current = datetime.now(JAKARTA).year
            years = [current, current + 1]
        max_rows = int(options.get("max_rows") or self.settings.collect_max_rows)
        enrich_limit = int(options.get("enrich_limit", 0) or 0)

        found: list[RawTender] = []
        seen_ids: set[str] = set()
        for year in years:
            for raw_row in self.fetch_year(int(year), max_rows):
                parsed = parse_list_row(raw_row)
                if not parsed["external_id"] or parsed["external_id"] in seen_ids:
                    continue
                text = " ".join(
                    filter(
                        None,
                        [
                            parsed["package_name"],
                            parsed["agency"],
                            parsed["category_year"],
                            parsed["procurement_type"],
                        ],
                    )
                )
                hits = match_keywords(text, keywords) if keywords else []
                if keywords and not hits:
                    continue
                seen_ids.add(parsed["external_id"])
                found.append(
                    RawTender(
                        external_id=parsed["external_id"],
                        package_name=parsed["package_name"] or "(tanpa nama)",
                        source_url=self._detail_url(parsed["external_id"]),
                        agency=parsed["agency"],
                        procurement_type=parsed["procurement_type"],
                        hps=parsed["hps"],
                        status=parsed["status"],
                        matched_keywords=hits,
                        raw_payload={"list_row": raw_row, "year": year, **parsed},
                    )
                )
        if enrich_limit > 0:
            for tender in found[:enrich_limit]:
                try:
                    self.enrich(tender)
                except SourceError as e:
                    # Detail satu paket gagal tidak boleh menggagalkan seluruh koleksi;
                    # data dari daftar tetap dipakai apa adanya.
                    log.warning("enrich gagal untuk %s: %s", tender.external_id, e)
                    tender.raw_payload["enrich_error"] = str(e)
        return found

    def health_check(self) -> HealthResult:
        try:
            self._bootstrap()
            payload = self._post_datatable(datetime.now(JAKARTA).year, 0, 1)
            if payload.get("data") is not None:
                return HealthResult(True, "ok", f"datatable OK (draw={payload.get('draw')})")
            return HealthResult(False, "failed", "respons tanpa 'data'")
        except SourceError as e:
            return HealthResult(False, "blocked" if "403" in str(e) else "failed", str(e))
