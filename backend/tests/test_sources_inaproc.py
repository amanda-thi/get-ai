"""Uji adapter INAPROC API Gateway (resmi) dengan `httpx.MockTransport`.

Belum ada kredensial nyata, jadi perilaku diuji terhadap skema respons yang
terdokumentasi di https://data.inaproc.id/docs. Tanpa key adapter HARUS menolak
dengan jelas (tidak berpura-pura berhasil).
"""
from datetime import date

import httpx
import pytest

from app.config import Settings
from app.sources.base import SourceError
from app.sources.inaproc_api import InaprocApiAdapter

ITEM = {
    "id": 998877,
    "nama_paket": "Pengadaan Mesin Shredder Sampah",
    "satuan_kerja": "Dinas Lingkungan Hidup Provinsi",
    "jenis_pengadaan": "Barang",
    "metode_pengadaan": "Tender",
    "pagu": "Rp. 500.000.000,00",
    "status": "AKTIF",
    "tanggal_dibuat": "2026-11-10 08:30:00",
}
ITEM_OTHER = {**ITEM, "id": 998878, "nama_paket": "Pengadaan Alat Tulis"}


def make_adapter(handler, key=""):
    s = Settings(inaproc_api_key=key)
    src = {"id": "src-i", "base_url": "https://data.inaproc.id", "adapter_type": "inaproc", "config": {}}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return InaprocApiAdapter(src, s, client=client)


def test_discover_without_key_raises_clear_error():
    adapter = make_adapter(lambda r: httpx.Response(200, json={}), key="")
    with pytest.raises(SourceError) as e:
        adapter.discover([], {})
    assert "INAPROC_API_KEY" in str(e.value)


def test_health_check_without_key_is_manual_only():
    adapter = make_adapter(lambda r: httpx.Response(200, json={}), key="")
    res = adapter.health_check()
    assert not res.ok and res.status == "manual_only"


def test_discover_maps_and_filters_with_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"success": True, "data": [ITEM, ITEM_OTHER], "meta": {"cursor": None, "has_more": False, "limit": 100}},
        )

    adapter = make_adapter(handler, key="secret-token")
    found = adapter.discover(["Mesin shredder"], {})
    assert len(found) == 1
    t = found[0]
    assert t.external_id == "998877"
    assert t.package_name == "Pengadaan Mesin Shredder Sampah"
    assert t.agency == "Dinas Lingkungan Hidup Provinsi"
    assert t.budget_ceiling == 500000000.0
    assert t.announced_at == date(2026, 11, 10)
    assert t.matched_keywords == ["Mesin shredder"]
    assert seen["auth"] == "Bearer secret-token"


def test_discover_paginates_until_has_more_false():
    pages = [
        {"success": True, "data": [ITEM], "meta": {"cursor": "c2", "has_more": True, "limit": 1}},
        {"success": True, "data": [ITEM_OTHER], "meta": {"cursor": None, "has_more": False, "limit": 1}},
    ]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        page = pages[min(calls["n"], len(pages) - 1)]
        calls["n"] += 1
        return httpx.Response(200, json=page)

    adapter = make_adapter(handler, key="k")
    found = adapter.discover([], {"limit": 1, "max_rows": 10})
    assert {t.external_id for t in found} == {"998877", "998878"}
    assert calls["n"] == 2


def test_discover_401_raises_source_error():
    adapter = make_adapter(lambda r: httpx.Response(401, json={"error": "unauthorized"}), key="bad")
    with pytest.raises(SourceError) as e:
        adapter.discover([], {})
    assert "401" in str(e.value)
