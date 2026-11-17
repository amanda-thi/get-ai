"""Uji lead discovery: pengumpulan dari situs & pencarian (mock, tanpa jaringan nyata)."""
import httpx
import pytest

from app.config import Settings
from app.discovery.base import DiscoveryError
from app.discovery.search import search_companies
from app.discovery.website import collect_from_url, guess_name

HOME = """
<html><head>
  <title>PT Acme Lingkungan - Home</title>
  <meta name="description" content="Pengelolaan sampah dan daur ulang plastik.">
</head><body>
  <a href="mailto:info@acme.co.id">Email</a>
  <p>sales@acme.co.id</p>
  <a href="/kontak">Kontak</a>
</body></html>
"""

KONTAK = """
<html><head><title>Kontak</title></head><body>
  <p>Telepon: 0812-3456-7890</p>
  <a href="mailto:partnership@acme.co.id">Partnership</a>
</body></html>
"""


def site_client():
    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if url.rstrip("/") == "https://acme.co.id":
            return httpx.Response(200, text=HOME, headers={"content-type": "text/html"})
        if "kontak" in url:
            return httpx.Response(200, text=KONTAK, headers={"content-type": "text/html"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_guess_name_prefers_site_name_then_title():
    assert guess_name("<title>X - Home</title>", "https://a.co.id") == "X"
    assert guess_name("<title>PT Foo</title>", "https://a.co.id") == "PT Foo"
    assert guess_name("<html></html>", "https://my-company.co.id") == "My Company"


def test_collect_from_url_gathers_name_description_and_contacts():
    company = collect_from_url("acme.co.id", Settings(), client=site_client())
    assert company.name == "PT Acme Lingkungan"
    assert company.website == "https://acme.co.id"
    assert "daur ulang" in (company.description or "")
    values = {(c.contact_type, c.value) for c in company.contacts}
    assert ("email", "info@acme.co.id") in values
    assert ("email", "sales@acme.co.id") in values
    assert ("email", "partnership@acme.co.id") in values
    assert ("phone", "+6281234567890") in values
    # kontak wajib punya halaman sumber
    assert all(c.source_url for c in company.contacts)


def test_collect_from_url_invalid_raises():
    with pytest.raises(DiscoveryError):
        collect_from_url("bukan url", Settings(), client=site_client())


def test_search_requires_key():
    with pytest.raises(DiscoveryError) as e:
        search_companies("pengelola sampah", settings=Settings(lead_search_api_key=""))
    assert "LEAD_SEARCH_API_KEY" in str(e.value)


def test_search_returns_companies():
    def handler(request):
        assert request.headers.get("X-API-KEY") == "secret"
        return httpx.Response(
            200,
            json={
                "organic": [
                    {"title": "PT Daur Ulang Jaya", "link": "https://daurulang.co.id", "snippet": "Pengelola sampah"},
                    {"title": "", "link": "https://tanpa-nama.co.id"},
                ]
            },
        )

    s = Settings(lead_search_provider="serper", lead_search_api_key="secret")
    out = search_companies("pengelola sampah", industry="Limbah", limit=5, settings=s,
                           client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(out) == 1
    assert out[0].name == "PT Daur Ulang Jaya"
    assert out[0].website == "https://daurulang.co.id"
    assert out[0].industry == "Limbah"
    assert out[0].source_name == "search:serper"


def test_search_rejects_unknown_provider():
    s = Settings(lead_search_provider="bing", lead_search_api_key="x")
    with pytest.raises(DiscoveryError):
        search_companies("x", settings=s)


def test_search_tavily_returns_companies():
    def handler(request):
        assert request.headers.get("Authorization") == "Bearer tvly-secret"
        assert request.url.path.endswith("/search")
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "PT Olah Sampah Nusantara", "url": "https://olahsampah.co.id", "content": "Daur ulang plastik"},
                    {"title": "Tanpa URL", "url": ""},
                ]
            },
        )

    s = Settings(lead_search_provider="tavily", lead_search_api_key="tvly-secret",
                 lead_search_base_url="https://api.tavily.com")
    out = search_companies("pengelola sampah", location="Bandung", limit=5, settings=s,
                           client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(out) == 1
    assert out[0].name == "PT Olah Sampah Nusantara"
    assert out[0].website == "https://olahsampah.co.id"
    assert out[0].source_name == "search:tavily"


def test_search_tavily_rejects_bad_key():
    def handler(request):
        return httpx.Response(401, json={"detail": {"error": "Unauthorized"}})

    s = Settings(lead_search_provider="tavily", lead_search_api_key="bad",
                 lead_search_base_url="https://api.tavily.com")
    with pytest.raises(DiscoveryError) as e:
        search_companies("x", settings=s,
                         client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert "LEAD_SEARCH_API_KEY" in str(e.value)
