"""Uji layanan koleksi: dedupe/upsert, kesehatan sumber, dan penanganan kegagalan."""
from app.config import Settings
from app.services import collection
from app.sources.base import RawTender, SourceError
from tests.fakes import RecordingDB

SETTINGS = Settings()


class FakeAdapter:
    def __init__(self, tenders=None, error: Exception | None = None):
        self.tenders = tenders or []
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def discover(self, keywords, options=None):
        if self.error:
            raise self.error
        return self.tenders


def raw(external_id="1", name="Pengadaan Mesin Pencacah Sampah", agency="DLH Kota X"):
    return RawTender(
        external_id=external_id,
        package_name=name,
        source_url=f"https://spse.inaproc.id/nasional/lelang/{external_id}/pengumumanlelang",
        agency=agency,
        hps=100000000.0,
        matched_keywords=["Mesin pencacah sampah"],
    )


SOURCE = {"id": "src-1", "name": "SPSE Nasional", "adapter_type": "spse", "base_url": "https://spse.inaproc.id", "config": {}}


def test_collect_source_upserts_and_marks_ok(monkeypatch):
    db = RecordingDB()
    monkeypatch.setattr(collection, "build_adapter", lambda s, st, client=None: FakeAdapter([raw()]))

    res = collection.collect_source(db, SOURCE, ["Mesin pencacah sampah"], SETTINGS)
    assert res["status"] == "ok" and res["upserted"] == 1

    inserts = db.inserted_in("tenders")
    assert inserts and inserts[0]["upsert"] and inserts[0]["on_conflict"] == "dedupe_hash"
    row = inserts[0]["rows"][0]
    assert row["package_name"] == "Pengadaan Mesin Pencacah Sampah"
    assert row["dedupe_hash"] and "first_seen_at" not in row  # jangan timpa first_seen_at

    health = db.updates_in("tender_sources")
    assert health and health[-1]["values"]["health_status"] == "ok"
    assert db.inserted_in("system_logs")  # tercatat


def test_collect_source_records_failure(monkeypatch):
    db = RecordingDB()
    monkeypatch.setattr(collection, "build_adapter", lambda s, st, client=None: FakeAdapter(error=SourceError("SPSE datatable gagal (500)")))

    res = collection.collect_source(db, SOURCE, [], SETTINGS)
    assert res["status"] == "failed" and res["upserted"] == 0
    assert db.inserted_in("tenders") == []
    assert db.updates_in("tender_sources")[-1]["values"]["health_status"] == "failed"
    assert db.inserted_in("system_logs")[-1]["rows"][0]["level"] == "error"


def test_collect_source_marks_blocked_on_403(monkeypatch):
    db = RecordingDB()
    monkeypatch.setattr(collection, "build_adapter", lambda s, st, client=None: FakeAdapter(error=SourceError("SPSE datatable gagal (403)")))
    res = collection.collect_source(db, SOURCE, [], SETTINGS)
    assert res["status"] == "blocked"


def test_unsupported_adapter_type_is_manual_only():
    db = RecordingDB()
    src = {"id": "s", "name": "SIRUP", "adapter_type": "sirup", "base_url": "https://sirup.inaproc.id", "config": {}}
    res = collection.collect_source(db, src, [], SETTINGS)  # memakai registry asli
    assert res["status"] == "manual_only" and "SIRUP" in res["error"]
    assert db.updates_in("tender_sources")[-1]["values"]["health_status"] == "manual_only"


def test_collect_all_uses_active_keywords_and_sources(monkeypatch):
    db = RecordingDB(sources=[SOURCE], keywords=["Mesin shredder"])
    monkeypatch.setattr(collection, "build_adapter", lambda s, st, client=None: FakeAdapter([raw()]))
    out = collection.collect_all(db, SETTINGS)
    assert out["keywords_used"] == 1 and out["sources_total"] == 1 and out["sources_ok"] == 1


def test_active_keywords_filters_empty():
    db = RecordingDB(keywords=["a", "", "b"])
    assert collection.active_keywords(db) == ["a", "b"]
