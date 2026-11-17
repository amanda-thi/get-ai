"""Uji utilitas web: normalisasi URL, ekstraksi kontak publik, robots.txt."""
import httpx

from app.utils.web import (
    canonical_website,
    contact_links,
    domain_of,
    extract_emails,
    extract_phones,
    extract_title,
    fetch_html,
    normalize_url,
    robots_allows,
)

HTML = """
<html><head>
  <title>PT Acme Lingkungan - Home</title>
  <meta name="description" content="Pengelolaan sampah dan daur ulang plastik.">
  <meta property="og:site_name" content="PT Acme Lingkungan">
</head><body>
  <a href="mailto:info@acme.co.id">Email kami</a>
  <p>Hubungi sales@acme.co.id atau noreply@acme.co.id</p>
  <a href="tel:+62 21 5550 1234">Telepon</a>
  <p>WA: 0812-3456-7890</p>
  <a href="/kontak">Kontak</a>
  <a href="https://lain.co.id/kontak">Eksternal</a>
  <a href="/produk">Produk</a>
</body></html>
"""


def test_normalize_url_and_domain():
    assert normalize_url("acme.co.id") == "https://acme.co.id"
    assert normalize_url("https://www.acme.co.id/") == "https://www.acme.co.id"
    assert normalize_url("https://acme.co.id/kontak") == "https://acme.co.id/kontak"
    assert normalize_url("bukan url") is None
    assert normalize_url("") is None
    assert domain_of("https://www.acme.co.id/x") == "acme.co.id"
    assert canonical_website("acme.co.id/kontak") == "https://acme.co.id"


def test_extract_emails_filters_junk_and_dedupes():
    emails = extract_emails(HTML)
    assert "info@acme.co.id" in emails
    assert "sales@acme.co.id" in emails
    assert "noreply@acme.co.id" not in emails
    assert emails.count("info@acme.co.id") == 1


def test_extract_phones_normalizes_indonesian():
    phones = extract_phones(HTML)
    assert "+622155501234" in phones
    assert "+6281234567890" in phones


def test_extract_title_and_contact_links():
    assert extract_title(HTML) == "PT Acme Lingkungan - Home"
    links = contact_links("https://acme.co.id", HTML)
    assert "https://acme.co.id/kontak" in links
    assert all("lain.co.id" not in x for x in links)  # hanya domain sama
    assert all("produk" not in x for x in links)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_robots_allows_respects_disallow():
    def handler(request):
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")

    c = _client(handler)
    assert robots_allows(c, "https://acme.co.id/") is True
    assert robots_allows(c, "https://acme.co.id/private/x") is False


def test_robots_missing_is_allowed():
    c = _client(lambda r: httpx.Response(404))
    assert robots_allows(c, "https://acme.co.id/") is True


def test_fetch_html_blocked_by_robots_returns_none():
    def handler(request):
        if str(request.url).endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    assert fetch_html(_client(handler), "https://acme.co.id/") is None
