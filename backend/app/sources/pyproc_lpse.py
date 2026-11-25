"""Adapter tender berbasis `pyproc` (SPSE/LPSE/Inaproc publik).

Menggantikan scraping manual SPSE dengan library pyproc (`Lpse`) yang menangani
sesi/authenticity token, endpoint DataTables, dan parsing detail/jadwal LPSE.
Mendukung host SPSE/LPSE apa pun di bawah `spse.inaproc.id/{host}` (mis. `nasional`
atau LPSE instansi tertentu).

Konfigurasi sumber (`tender_sources.config`):
  - host / scope / instansi: kode host LPSE (default: diturunkan dari base_url, fallback "nasional")

Opsi discover:
  - years: daftar tahun anggaran
  - max_rows: batas baris per tahun
  - enrich_limit: jumlah tender teratas yang diperkaya detail+jadwal
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..utils.text import JAKARTA, match_keywords, parse_id_date, parse_id_datetime
from .base import HealthResult, RawTender, SourceAdapter, SourceError
from .spse_nasional import parse_list_row

log = logging.getLogger(__name__)


def _get(obj: dict, *keys: str, default=None):
    for k in keys:
        if obj.get(k) not in (None, ""):
            return obj[k]
    return default


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return "; ".join(parts) if parts else None
    s = str(value).strip()
    return s or None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:  # noqa: BLE001
            return None
    # fallback parse string angka/rupiah sederhana
    try:
        from ..utils.text import parse_rupiah

        return parse_rupiah(value)
    except Exception:  # noqa: BLE001
        return None


def derive_host(source: dict) -> str:
    config = source.get("config") or {}
    host = config.get("host") or config.get("scope") or config.get("instansi")
    if host:
        return str(host).strip().strip("/")
    base = (source.get("base_url") or "").rstrip("/")
    # contoh: https://spse.inaproc.id/nasional -> nasional
    marker = "spse.inaproc.id/"
    if marker in base:
        tail = base.split(marker, 1)[1].strip("/")
        if tail:
            return tail.split("/")[0]
    # contoh base tanpa path (spse.inaproc.id) -> nasional
    if base.endswith("spse.inaproc.id"):
        return "nasional"
    return "nasional"


def _detail_url(host: str, external_id: str) -> str:
    return f"https://spse.inaproc.id/{host}/lelang/{external_id}/pengumumanlelang"


def _schedule_dates(stages: list[dict]) -> dict:
    out = {"registration_start": None, "registration_end": None, "bid_deadline": None}
    for stage in stages or []:
        name = str(_get(stage, "tahap", "tahapan", "stage", default="") or "").lower()
        start = parse_id_datetime(_get(stage, "mulai", "start", "start_raw"))
        end = parse_id_datetime(_get(stage, "sampai", "selesai", "end", "end_raw"))
        if out["registration_start"] is None and "pengumuman" in name and start:
            out["registration_start"] = start
        if end and any(k in name for k in ("penawaran", "upload", "pemasukan", "dokumen", "kirim persyaratan")):
            out["registration_end"] = end
            out["bid_deadline"] = end
    return out


class PyprocLpseAdapter(SourceAdapter):
    adapter_type = "pyproc"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = derive_host(self.source)
        self._lpse = None

    @property
    def lpse(self):
        if self._lpse is None:
            try:
                from pyproc import Lpse  # type: ignore
            except Exception as e:  # noqa: BLE001
                raise SourceError(
                    "Dependensi pyproc belum terpasang. Jalankan: pip install pyproc"
                ) from e
            try:
                self._lpse = Lpse(self.host, timeout=int(self.settings.http_timeout), verify=False)
            except Exception as e:  # noqa: BLE001
                raise SourceError(f"Gagal menginisialisasi pyproc Lpse('{self.host}'): {e}") from e
        return self._lpse

    def close(self) -> None:
        try:
            if self._lpse is not None:
                # pyproc Lpse menutup session di __del__/session.close
                try:
                    self._lpse.session.close()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self._lpse = None
            super().close()

    def _fetch_year_rows(self, year: int, max_rows: int) -> list:
        rows: list = []
        page = 1000
        start = 0
        while len(rows) < max_rows:
            try:
                payload = self.lpse.get_paket_tender(start=start, length=page, tahun=year)
            except Exception as e:  # noqa: BLE001
                raise SourceError(f"pyproc gagal mengambil data ({self.host}, {year}): {e}") from e
            data = payload.get("data") if isinstance(payload, dict) else (payload or [])
            if not data:
                break
            rows.extend(data)
            if len(data) < page:
                break
            start += page
            # hentikan bila sudah mencapai total yang dilaporkan
            try:
                total = int(payload.get("recordsFiltered") or payload.get("recordsTotal") or 0)
                if total and start >= total:
                    break
            except Exception:  # noqa: BLE001
                pass
        return rows[:max_rows]

    def _map_detail(self, tender: RawTender, info: dict) -> RawTender:
        if not info:
            return tender
        tender.package_name = _as_text(_get(info, "nama_tender", "nama_paket")) or tender.package_name
        tender.description = _as_text(_get(info, "uraian_singkat_pekerjaan")) or tender.description
        tender.agency = _as_text(_get(info, "k/l/pd/instansi_lainnya", "k/l/pd", "instansi", "satuan_kerja")) or tender.agency
        tender.location = _as_text(_get(info, "lokasi_pekerjaan")) or tender.location
        tender.procurement_type = _as_text(_get(info, "jenis_pengadaan")) or tender.procurement_type
        tender.status = _as_text(_get(info, "tahap_tender_saat_ini", "status")) or tender.status
        tender.budget_ceiling = _as_float(_get(info, "nilai_pagu_paket")) or tender.budget_ceiling
        tender.hps = _as_float(_get(info, "nilai_hps_paket")) or tender.hps
        tender.announced_at = parse_id_date(_get(info, "tanggal_pembuatan")) or tender.announced_at
        tender.technical_specs = _as_text(_get(info, "metode_pengadaan")) or tender.technical_specs
        tender.participant_requirements = _as_text(_get(info, "syarat_kualifikasi")) or tender.participant_requirements
        return tender

    def enrich(self, tender: RawTender) -> RawTender:
        if not tender.external_id:
            return tender
        try:
            detil = self.lpse.detil_paket_tender(tender.external_id)
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"pyproc gagal membuka detail tender {tender.external_id}: {e}") from e

        info = {}
        stages: list[dict] = []
        try:
            pengumuman = detil.get_pengumuman() or {}
            info = pengumuman if isinstance(pengumuman, dict) else {}
        except Exception as e:  # noqa: BLE001
            tender.raw_payload["enrich_error_pengumuman"] = str(e)
        try:
            jadwal = detil.get_jadwal() or []
            stages = jadwal if isinstance(jadwal, list) else []
        except Exception as e:  # noqa: BLE001
            tender.raw_payload["enrich_error_jadwal"] = str(e)

        self._map_detail(tender, info)
        if stages:
            dates = _schedule_dates(stages)
            tender.registration_start = dates["registration_start"] or tender.registration_start
            tender.registration_end = dates["registration_end"] or tender.registration_end
            tender.bid_deadline = dates["bid_deadline"] or tender.bid_deadline
            tender.raw_payload["schedule"] = stages
        if info:
            tender.raw_payload["detail"] = info
        return tender

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
            for raw_row in self._fetch_year_rows(int(year), max_rows):
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
                        source_url=_detail_url(self.host, parsed["external_id"]),
                        agency=parsed["agency"],
                        procurement_type=parsed["procurement_type"],
                        hps=parsed["hps"],
                        status=parsed["status"],
                        matched_keywords=hits,
                        raw_payload={"list_row": raw_row, "year": int(year), **parsed, "host": self.host},
                    )
                )
        if enrich_limit > 0:
            for tender in found[:enrich_limit]:
                try:
                    self.enrich(tender)
                except SourceError as e:
                    log.warning("enrich gagal untuk %s: %s", tender.external_id, e)
                    tender.raw_payload["enrich_error"] = str(e)
        return found

    def health_check(self) -> HealthResult:
        try:
            _ = self.lpse  # init + auth lazily on first call
            # coba ambil 1 baris tahun berjalan
            year = datetime.now(JAKARTA).year
            payload = self.lpse.get_paket_tender(start=0, length=1, tahun=year)
            if isinstance(payload, dict) and payload.get("data") is not None:
                total = payload.get("recordsTotal")
                return HealthResult(True, "ok", f"pyproc/Lpse('{self.host}') OK (recordsTotal={total})")
            return HealthResult(False, "failed", "Respons pyproc tanpa 'data'")
        except SourceError as e:
            msg = str(e)
            status = "blocked" if ("403" in msg or "menolak" in msg.lower()) else "failed"
            return HealthResult(False, status, msg)
        except Exception as e:  # noqa: BLE001
            return HealthResult(False, "failed", f"pyproc health check gagal: {e}")
