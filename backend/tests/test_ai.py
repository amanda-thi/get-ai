"""Uji klien AI, validasi output, dan layanan analisis (semua dengan mock, tanpa panggilan jaringan)."""
import json

import httpx
import pytest

from app.ai.client import AIClient, AIError
from app.ai.service import analyze as ai_analyze
from app.ai.validate import AIValidationError, derive_priority, validate_analysis
from app.config import Settings

GOOD = {
    "category": "Recycling Equipment",
    "relevance_score": 82,
    "priority": "HIGH",
    "score_reason": "Butuh mesin pencacah sampah plastik.",
    "equipment_needs": "Shredder, conveyor",
    "cooperation_opportunity": "Penyediaan alat",
    "key_requirements": "Kualifikasi kecil",
    "deadline_flag": "Deadline dekat",
}


def chat_response(content: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def make_ai(handler, **kwargs):
    s = Settings(groq_api_key="test-key", **kwargs)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AIClient(s, client=client)


# --- validasi ---

def test_validate_analysis_ok():
    out = validate_analysis(GOOD)
    assert out["relevance_score"] == 82 and out["priority"] == "HIGH"
    assert out["category"] == "Recycling Equipment"


def test_validate_derives_priority_when_missing():
    out = validate_analysis({"relevance_score": 55, "score_reason": "cukup"})
    assert out["priority"] == "MEDIUM" and out["category"] == "Other"


def test_validate_clamps_score_and_rejects_bad_score():
    assert validate_analysis({"relevance_score": 150, "score_reason": "x"})["relevance_score"] == 100
    with pytest.raises(AIValidationError):
        validate_analysis({"relevance_score": "bukan angka", "score_reason": "x"})


def test_validate_requires_reason_and_object():
    with pytest.raises(AIValidationError):
        validate_analysis({"relevance_score": 50})
    with pytest.raises(AIValidationError):
        validate_analysis(["not", "a", "dict"])


def test_derive_priority_thresholds():
    assert derive_priority(70) == "HIGH"
    assert derive_priority(69) == "MEDIUM"
    assert derive_priority(40) == "MEDIUM"
    assert derive_priority(39) == "LOW"


# --- klien ---

def test_client_without_key_raises():
    ai = AIClient(Settings(groq_api_key=""))
    with pytest.raises(AIError) as e:
        ai.complete_json("sys", "user")
    assert "belum diisi" in str(e.value)


def test_client_parses_json_content():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return chat_response(json.dumps(GOOD))

    out = make_ai(handler).complete_json("sys", "user")
    assert out["relevance_score"] == 82
    assert "api.groq.com" in seen["url"] and seen["auth"] == "Bearer test-key"


def test_client_openai_base_url():
    s = Settings(ai_provider="openai", openai_api_key="x")
    assert AIClient(s).base_url == "https://api.openai.com/v1"


def test_client_rejects_401():
    ai = make_ai(lambda r: httpx.Response(401, json={}))
    with pytest.raises(AIError) as e:
        ai.complete_json("sys", "user")
    assert "401" in str(e.value)


def test_client_bad_json_content():
    ai = make_ai(lambda r: chat_response("bukan json"))
    with pytest.raises(AIError):
        ai.complete_json("sys", "user")


# --- layanan ---

def test_service_analyze_returns_validated_result():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: chat_response(json.dumps(GOOD))))
    s = Settings(groq_api_key="test-key")
    out = ai_analyze({"package_name": "Pengadaan Shredder", "agency": "DLH"}, s, client=client)
    assert out["priority"] == "HIGH"
    assert out["model"] == s.ai_model_name
    assert out["prompt_version"] == "tender-v1"
    assert out["raw_ai_output"]["relevance_score"] == 82
