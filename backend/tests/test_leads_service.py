"""Uji layanan Company Leads: dedupe, penyimpanan, discovery (mock DB)."""
import pytest

from app.config import Settings
from app.discovery.base import RawCompany, RawContact
from app.services import leads
from tests.fakes import RecordingDB

EXISTING = {
    "id": "c1",
    "name": "PT Acme Lingkungan",
    "normalized_name": "pt acme lingkungan",
    "website": "https://acme.co.id",
}


def test_normalize_company_name():
    assert leads.normalize_company_name("PT Acme, Lingkungan!") == "pt acme lingkungan"
    assert leads.normalize_company_name(None) == ""


def test_save_company_new_inserts_company_lead_and_contacts():
    db = RecordingDB()
    raw = RawCompany(
        name="PT Baru Jaya",
        website="barujaya.co.id",
        industry="Daur Ulang",
        source_name="manual",
        source_url="https://barujaya.co.id",
        contacts=[RawContact("email", "info@barujaya.co.id", "https://barujaya.co.id")],
    )
    res = leads.save_company(db, raw)
    assert res["created"] is True
    assert db.inserted_in("companies")[0]["rows"][0]["normalized_name"] == "pt baru jaya"
    assert db.inserted_in("companies")[0]["rows"][0]["website"] == "https://barujaya.co.id"
    assert db.inserted_in("company_leads")[0]["rows"][0]["status"] == "new"
    assert db.inserted_in("company_contacts")[0]["upsert"] is True


def test_save_company_detects_duplicate():
    db = RecordingDB(tables={"companies": [EXISTING]})
    raw = RawCompany(name="PT Acme Lingkungan", website="https://acme.co.id", source_name="manual", source_url="x")
    res = leads.save_company(db, raw)
    assert res["created"] is False
    assert res["duplicate_of"] == "c1"
    assert not db.inserted_in("companies")


def test_discover_items_creates_and_counts():
    db = RecordingDB()
    out = leads.discover(
        db, Settings(),
        items=[{"name": "PT Satu", "website": "satu.co.id", "emails": ["a@satu.co.id"]}],
    )
    assert out["created"] == 1 and out["duplicates"] == 0
    assert out["results"][0]["contacts_added"] == 1


def test_discover_urls_uses_collector(monkeypatch):
    db = RecordingDB()
    raw = RawCompany(name="PT Web", website="web.co.id", source_name="website", source_url="https://web.co.id")
    monkeypatch.setattr(leads, "collect_from_url", lambda url, settings, client=None: raw)
    out = leads.discover(db, Settings(), urls=["web.co.id"])
    assert out["created"] == 1
    assert db.inserted_in("companies")[0]["rows"][0]["name"] == "PT Web"


def test_discover_url_error_is_recorded(monkeypatch):
    from app.discovery.base import DiscoveryError

    db = RecordingDB()

    def boom(url, settings, client=None):
        raise DiscoveryError("diblokir robots.txt")

    monkeypatch.setattr(leads, "collect_from_url", boom)
    out = leads.discover(db, Settings(), urls=["terlarang.co.id"])
    assert out["created"] == 0 and out["failed"] == 1
    assert "robots" in out["errors"][0]["error"]


def test_discover_search_without_key_records_error():
    db = RecordingDB()
    out = leads.discover(db, Settings(lead_search_api_key=""), query="pengelola sampah")
    assert out["created"] == 0
    assert any("LEAD_SEARCH_API_KEY" in e["error"] for e in out["errors"])


def test_add_contact_validates_type():
    db = RecordingDB()
    with pytest.raises(ValueError):
        leads.add_contact(db, "c1", "fax", "123", "")
    assert leads.add_contact(db, "c1", "email", "x@y.co.id", "")["value"] == "x@y.co.id"
