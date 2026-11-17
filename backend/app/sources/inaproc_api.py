"""Adapter INAPROC API Gateway (resmi) — https://data.inaproc.id/docs

Endpoint RUP terdokumentasi:
    GET {base}/api/v1/rup/rencana/penyedia?limit&cursor&start_date&end_date
Auth: Authorization: Bearer <JWT>  atau  X-API-Key: <key>

PENTING: akses API ini butuh token terdaftar (role Data Integrator, surat permohonan
instansi). Tanpa `INAPROC_API_KEY` adapter mengembalikan SourceError yang jelas dan
TIDAK berpura-pura berhasil. Belum diuji live karena belum ada kredensial.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..utils.text import JAKARTA, match_keywords, parse_id_datetime, parse_rupiah, strip_html
from .base import HealthResult, RawTender, SourceAdapter, SourceError


class InaprocApiAdapter(SourceAdapter):
    adapter_type = "inaproc"

    def _headers(self) -> dict:
        key = self.settings.inaproc_api_key
        return {
            "Authorization": f"Bearer {key}",
            "X-API-Key": key,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict) -> dict:
        if not self.settings.inaproc_configured:
            raise SourceError(
                "INAPROC_API_KEY belum diisi. API Gateway INAPROC butuh token terdaftar "
                "(lihat PHASE2_PLAN.md bagian 2.1)."
            )
        base = (self.settings.inaproc_api_base or self.base_url).rstrip("/")
        url = f"{base}{path}"
        try:
            r = self.client.get(url, params=params, headers=self._headers())
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"INAPROC tidak terjangkau: {e}") from e
        if r.status_code in (401, 403):
            raise SourceError(f"INAPROC menolak akses ({r.status_code}) — token tidak valid/berhak")
        if r.status_code != 200:
            raise SourceError(f"INAPROC error {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"Respons INAPROC bukan JSON: {e}") from e

    def _map(self, item: dict) -> RawTender:
        rid = item.get("id")
        return RawTender(
            external_id=str(rid) if rid is not None else None,
            package_name=strip_html(item.get("nama_paket")) or "(tanpa nama)",
            source_url=f"{(self.settings.inaproc_api_base or self.base_url).rstrip('/')}/api/v1/rup/rencana/penyedia",
            agency=strip_html(item.get("satuan_kerja")) or None,
            procurement_type=strip_html(item.get("jenis_pengadaan")) or None,
            description=strip_html(item.get("metode_pengadaan")) or None,
            budget_ceiling=parse_rupiah(item.get("pagu")) if isinstance(item.get("pagu"), str) else item.get("pagu"),
            status=strip_html(item.get("status")) or None,
            announced_at=parse_id_datetime(item.get("tanggal_dibuat")).date()
            if parse_id_datetime(item.get("tanggal_dibuat"))
            else None,
            raw_payload=item,
        )

    def discover(self, keywords: list[str], options: dict | None = None) -> list[RawTender]:
        options = options or {}
        limit = int(options.get("limit") or 100)
        max_rows = int(options.get("max_rows") or self.settings.collect_max_rows)
        params: dict = {"limit": min(limit, 100)}
        if options.get("start_date"):
            params["start_date"] = options["start_date"]
        if options.get("end_date"):
            params["end_date"] = options["end_date"]

        found: list[RawTender] = []
        cursor = None
        while len(found) < max_rows:
            if cursor:
                params["cursor"] = cursor
            payload = self._get("/api/v1/rup/rencana/penyedia", params)
            items = payload.get("data") or []
            if not items:
                break
            for item in items:
                tender = self._map(item)
                text = " ".join(
                    filter(None, [tender.package_name, tender.agency, tender.procurement_type])
                )
                hits = match_keywords(text, keywords) if keywords else []
                if keywords and not hits:
                    continue
                tender.matched_keywords = hits
                found.append(tender)
                if len(found) >= max_rows:
                    break
            meta = payload.get("meta") or {}
            cursor = meta.get("cursor")
            if not meta.get("has_more") or not cursor:
                break
        return found

    def health_check(self) -> HealthResult:
        if not self.settings.inaproc_configured:
            return HealthResult(
                False,
                "manual_only",
                "Butuh INAPROC_API_KEY (pendaftaran Data Integrator). Lihat PHASE2_PLAN.md.",
            )
        try:
            self._get("/api/v1/rup/rencana/penyedia", {"limit": 1})
            return HealthResult(True, "ok", f"API OK ({datetime.now(timezone.utc).isoformat()})")
        except SourceError as e:
            return HealthResult(False, "failed", str(e))
