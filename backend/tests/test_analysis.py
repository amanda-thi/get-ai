"""Uji penyimpanan & orkestrasi analisis AI (mock, tanpa jaringan/DB nyata)."""
import json

import httpx
import pytest

from app.config import Settings
from app.services import analysis
from tests.fakes import RecordingDB

GOOD = {
    "category": "Recycling Equipment",
    "relevance_score": 80,
    "priority": "HIGH",
    "score_reason": "Sesuai lini produk daur ulang.",
    "equipment_needs": "Shredder",
    "cooperation_opportunity": "Penyediaan alat",
    "key_requirements": "Kualifikasi kecil",
    "deadline_flag": "Deadline dekat",
}

TENDER = {
    "id": "tid-1",
    "package_name": "Pengadaan Mesin Shredder",
    "agency": "DLH",
    "created_at": "2026-11-10T00:00:00Z",
}


def ai_client(payload=GOOD, status=200):
    body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


def test_store_analysis_deactivates_old_then_inserts_current():
    db = RecordingDB()
    result = {**GOOD, "model": "llama", "prompt_version": "tender-v1", "raw_ai_output": GOOD}
    analysis.store_analysis(db, "tid-1", result)

    upd = db.updates_in("tender_analysis")[0]
    assert upd["filters"] == {"tender_id": "eq.tid-1", "is_current": "eq.true"}
    assert upd["values"] == {"is_current": False}

    row = db.inserted_in("tender_analysis")[0]["rows"][0]
    assert row["tender_id"] == "tid-1" and row["is_current"] is True
    assert row["relevance_score"] == 80 and row["priority"] == "HIGH"
    assert row["model"] == "llama"


def test_analyze_tender_stores_and_logs():
    db = RecordingDB(tables={"tenders": [TENDER]})
    res = analysis.analyze_tender(db, "tid-1", Settings(groq_api_key="k"), client=ai_client())
    assert res["priority"] == "HIGH"
    assert db.inserted_in("tender_analysis")
    assert db.inserted_in("system_logs")[-1]["rows"][0]["component"] == "analysis"


def test_analyze_tender_missing_raises_lookup_error():
    db = RecordingDB(tables={"tenders": []})
    with pytest.raises(LookupError):
        analysis.analyze_tender(db, "nope", Settings(groq_api_key="k"), client=ai_client())


def test_pending_tenders_excludes_already_analyzed():
    db = RecordingDB(
        tables={
            "tenders": [{"id": "a", "created_at": "2026-11-10T00:00:00Z"}, {"id": "b", "created_at": "2026-11-09T00:00:00Z"}],
            "tender_analysis": [{"tender_id": "a"}],
        }
    )
    assert [t["id"] for t in analysis.pending_tenders(db, 10)] == ["b"]


def test_analyze_pending_processes_and_counts():
    db = RecordingDB(tables={"tenders": [TENDER], "tender_analysis": []})
    out = analysis.analyze_pending(db, Settings(groq_api_key="k"), limit=5, client=ai_client())
    assert out["analyzed"] == 1 and out["failed"] == 0
    assert out["results"][0]["priority"] == "HIGH"


def test_analyze_pending_stops_on_missing_key():
    db = RecordingDB(tables={"tenders": [TENDER], "tender_analysis": []})
    out = analysis.analyze_pending(db, Settings(groq_api_key=""), limit=5)
    assert out["analyzed"] == 0 and out["failed"] == 1
    assert "belum diisi" in out["results"][0]["error"]
