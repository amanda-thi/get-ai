"""Uji adapter SPSE Nasional memakai `httpx.MockTransport` (fixture berbentuk data nyata).

Tidak ada panggilan jaringan: struktur HTML/JSON dibuat menyerupai respons asli
spse.inaproc.id yang sudah diverifikasi manual (lihat PHASE2_PLAN.md bagian 2.3).
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.config import Settings
from app.sources.base import SourceError
from app.sources.spse_nasional import (
    SpseNasionalAdapter,
    derive_schedule_dates,
    parse_detail_fields,
    parse_list_row,
    parse_schedule,
)

TZ = ZoneInfo("Asia/Jakarta")

BOOTSTRAP_HTML = """
<html><body><div id="app" data-authenticityToken="deadbeef0123456789"></div>
<script>var authenticityToken = 'deadbeef0123456789';</script></body></html>
"""

# 15 kolom sesuai DataTables SPSE (array), nama paket mengandung badge HTML.
LIST_ROW = [
    "10182597000",
    "Pengadaan Mesin Pencacah Sampah <span class='badge badge-success'>Tender</span>",
    "Dinas Lingkungan Hidup Kota Bandung",
    "Sedang Berjalan",
    "204,8 Jt",
    "Kualifikasi Kecil",
    "Barang",
    "Harga Terendah",
    "Barang - TA 2026",
    "1",
    "Nilai Kontrak belum dibuat",
    "",
    "",
    "",
    "",
]
OTHER_ROW = [
    "10182597001",
    "Pengadaan Alat Tulis Kantor",
    "Sekretariat Daerah",
    "Selesai",
    "12,5 Jt",
    "Kualifikasi Kecil",
    "Barang",
    "Harga Terendah",
    "Barang - TA 2026",
    "1",
    "Rp. 12.500.000,00",
    "",
    "",
    "",
    "",
]

DETAIL_HTML = """
<table><tbody>
<tr><td>Kode Tender</td><td>10182597000</td></tr>
<tr><td>Nama Tender</td><td>Pengadaan Mesin Pencacah Sampah Kapasitas 5 Ton</td></tr>
<tr><td>Kode RUP</td><td>45678901</td></tr>
<tr><td>Uraian Singkat Pekerjaan</td><td>Pengadaan mesin pencacah sampah organik &amp; anorganik</td></tr>
<tr><td>Tanggal Pembuatan</td><td>14 November 2026</td></tr>
<tr><td>Tahap Tender Saat Ini</td><td>Pemasukan Dokumen Penawaran</td></tr>
<tr><td>K/L/PD/Instansi Lainnya</td><td>Pemerintah Kota Bandung</td></tr>
<tr><td>Satuan Kerja</td><td>Dinas Lingkungan Hidup</td></tr>
<tr><td>Jenis Pengadaan</td><td>Barang</td></tr>
<tr><td>Metode Pengadaan</td><td>Tender</td></tr>
<tr><td>Tahun Anggaran</td><td>2026</td></tr>
<tr><td>Nilai Pagu Paket</td><td>Rp. 250.000.000,00</td></tr>
<tr><td>Nilai HPS Paket</td><td>Rp. 204.800.000,00</td></tr>
<tr><td>Lokasi Pekerjaan</td><td>Kota Bandung</td></tr>
<tr><td>Syarat Kualifikasi</td><td>Kualifikasi Kecil - Pengadaan Barang</td></tr>
</tbody></table>
"""

SCHEDULE_HTML = """
<table><thead><tr><th>No</th><th>Tahapan</th><th>Mulai</th><th>Selesai</th><th>Perubahan</th></tr></thead>
<tbody>
<tr><td>1</td><td>Pengumuman</td><td>14 November 2026 09:00</td><td>14 November 2026 12:00</td><td>-</td></tr>
<tr><td>2</td><td>Pemasukan Dokumen Penawaran</td><td>15 November 2026 08:00</td><td>21 November 2026 16:00</td><td>-</td></tr>
</tbody></table>
"""


def make_adapter(handler, **settings_kwargs):
    s = Settings(**settings_kwargs)
    src = {"id": "src-1", "base_url": "https://spse.inaproc.id", "adapter_type": "spse", "config": {}}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SpseNasionalAdapter(src, s, client=client)


def route_handler(rows, *, list_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/nasional/lelang":
            return httpx.Response(200, text=BOOTSTRAP_HTML)
        if request.method == "POST" and path == "/nasional/dt/lelang":
            if list_status != 200:
                return httpx.Response(list_status, text="blocked")
            return httpx.Response(200, json={"draw": 1, "recordsTotal": len(rows), "data": rows})
        if path.endswith("/pengumumanlelang"):
            return httpx.Response(200, text=DETAIL_HTML)
        if path.endswith("/jadwal"):
            return httpx.Response(200, text=SCHEDULE_HTML)
        return httpx.Response(404)

    return handler


def test_parse_list_row_normalizes_fields():
    p = parse_list_row(LIST_ROW)
    assert p["external_id"] == "10182597000"
    assert p["package_name"] == "Pengadaan Mesin Pencacah Sampah Tender"
    assert p["agency"] == "Dinas Lingkungan Hidup Kota Bandung"
    assert p["hps"] == 204800000.0
    assert p["procurement_type"] == "Barang"
    assert p["budget_year"] == 2026
    assert p["contract_value"] is None


def test_discover_filters_by_keyword_and_parses_rows():
    adapter = make_adapter(route_handler([LIST_ROW, OTHER_ROW]))
    found = adapter.discover(["Mesin pencacah sampah"], {"years": [2026]})
    assert len(found) == 1
    t = found[0]
    assert t.external_id == "10182597000"
    assert t.source_url == "https://spse.inaproc.id/nasional/lelang/10182597000/pengumumanlelang"
    assert t.matched_keywords == ["Mesin pencacah sampah"]
    assert t.hps == 204800000.0
    assert t.raw_payload["year"] == 2026


def test_discover_without_keywords_returns_all():
    adapter = make_adapter(route_handler([LIST_ROW, OTHER_ROW]))
    found = adapter.discover([], {"years": [2026]})
    assert {t.external_id for t in found} == {"10182597000", "10182597001"}


def test_health_check_ok():
    adapter = make_adapter(route_handler([LIST_ROW]))
    res = adapter.health_check()
    assert res.ok and res.status == "ok"


def test_health_check_blocked_on_403():
    adapter = make_adapter(route_handler([], list_status=403), collect_max_rows=1)
    res = adapter.health_check()
    assert not res.ok and res.status == "blocked"


def test_bootstrap_missing_token_reports_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>no token here</html>")

    adapter = make_adapter(handler)
    res = adapter.health_check()
    assert not res.ok and "token" in res.message.lower()
    with pytest.raises(SourceError):
        adapter._bootstrap()


def test_parse_detail_fields_label_pairs():
    fields = parse_detail_fields(DETAIL_HTML)
    assert fields["external_id"] == "10182597000"
    assert fields["package_name"] == "Pengadaan Mesin Pencacah Sampah Kapasitas 5 Ton"
    assert fields["description"] == "Pengadaan mesin pencacah sampah organik & anorganik"
    assert fields["location"] == "Kota Bandung"
    assert fields["budget_ceiling_raw"] == "Rp. 250.000.000,00"


def test_parse_schedule_and_derive_dates():
    stages = parse_schedule(SCHEDULE_HTML)
    assert [s["stage"] for s in stages] == ["Pengumuman", "Pemasukan Dokumen Penawaran"]
    dates = derive_schedule_dates(stages)
    assert dates["registration_start"] == datetime(2026, 11, 14, 9, 0, tzinfo=TZ)
    assert dates["registration_end"] == datetime(2026, 11, 21, 16, 0, tzinfo=TZ)
    assert dates["bid_deadline"] == datetime(2026, 11, 21, 16, 0, tzinfo=TZ)


def test_enrich_merges_detail_and_schedule():
    adapter = make_adapter(route_handler([LIST_ROW]))
    found = adapter.discover([], {"years": [2026], "enrich_limit": 1})
    t = found[0]
    assert t.package_name == "Pengadaan Mesin Pencacah Sampah Kapasitas 5 Ton"
    assert t.budget_ceiling == 250000000.0
    assert t.hps == 204800000.0
    assert t.announced_at == date(2026, 11, 14)
    assert t.registration_end == datetime(2026, 11, 21, 16, 0, tzinfo=TZ)
    assert t.location == "Kota Bandung"
    assert "detail" in t.raw_payload and "schedule" in t.raw_payload
