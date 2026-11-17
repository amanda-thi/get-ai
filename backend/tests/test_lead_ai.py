"""Uji profil perusahaan, validasi kualifikasi lead, dan pembuatan email outreach (mock)."""
import json

import httpx
import pytest

from app.ai.client import AIError
from app.ai.lead_service import qualify
from app.ai.lead_validate import validate_lead_analysis
from app.ai.outreach_service import generate_email, validate_email
from app.ai.validate import AIValidationError
from app.config import Settings
from app.services.company_profile import is_usable, load_profile, profile_summary

GOOD_LEAD = {
    "lead_score": 78,
    "category": "HIGH",
    "industry_classification": "Pengelolaan Sampah",
    "potential_products": ["Mesin pencacah sampah", "Suku cadang dan komponen mesin", "Mesin pencacah sampah"],
    "reason": "Perusahaan bergerak di pengelolaan sampah kota.",
    "suggested_approach": "Tawarkan mesin pencacah & suku cadang.",
}

GOOD_EMAIL = {"subject": "Kerja sama pengelolaan sampah", "body": "Halo,\n\nKami PT Green Eco Teknologi..."}


def ai_client(payload, status=200):
    body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


# --- profil ---

def test_profile_loads_and_summarizes():
    p = load_profile()
    assert is_usable(p)
    assert p.get("company_name") == "PT Green Eco Teknologi"
    summary = profile_summary(p)
    assert "PT Green Eco Teknologi" in summary
    assert "Mesin" in summary or "mesin" in summary
    assert "JANGAN membuat klaim" in summary


def test_profile_missing_file_is_empty():
    p = load_profile(Settings(company_profile_path="tidak/ada.yaml"))
    assert p == {} and not is_usable(p)


# --- validasi lead ---

def test_validate_lead_ok_and_dedupes_products():
    out = validate_lead_analysis(GOOD_LEAD)
    assert out["lead_score"] == 78 and out["category"] == "HIGH"
    assert out["potential_products"].count("Mesin pencacah sampah") == 1


def test_validate_lead_clamps_and_forces_category_from_score():
    out = validate_lead_analysis({"lead_score": 150, "category": "LOW", "reason": "x"})
    assert out["lead_score"] == 100 and out["category"] == "HIGH"


def test_validate_lead_rejects_bad_input():
    with pytest.raises(AIValidationError):
        validate_lead_analysis({"lead_score": "x", "reason": "y"})
    with pytest.raises(AIValidationError):
        validate_lead_analysis({"lead_score": 50})
    with pytest.raises(AIValidationError):
        validate_lead_analysis(["nope"])


# --- layanan ---

def test_qualify_returns_validated_result():
    s = Settings(groq_api_key="test-key")
    out = qualify({"name": "PT Acme", "industry": "Sampah"}, [], s, client=ai_client(GOOD_LEAD))
    assert out["category"] == "HIGH" and out["lead_score"] == 78
    assert out["prompt_version"] == "lead-v1"
    assert out["model"] == s.ai_model_name
    assert out["raw_ai_output"]["lead_score"] == 78


def test_qualify_without_key_raises():
    with pytest.raises(AIError):
        qualify({"name": "PT Acme"}, [], Settings(groq_api_key=""))


# --- email outreach ---

def test_validate_email_requires_subject_and_body():
    assert validate_email(GOOD_EMAIL)["subject"].startswith("Kerja")
    with pytest.raises(AIError):
        validate_email({"subject": "", "body": "x"})


def test_generate_email_ok():
    s = Settings(groq_api_key="test-key")
    out = generate_email(
        {"name": "PT Acme", "industry": "Sampah"},
        [{"contact_type": "email", "value": "info@acme.co.id"}],
        "company_intro",
        "id",
        s,
        client=ai_client(GOOD_EMAIL),
    )
    assert out["subject"] and out["body"]
    assert out["prompt_version"] == "outreach-v1"
