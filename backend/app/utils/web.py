"""Pengumpulan info dari web publik: robots.txt, ambil halaman, ekstrak kontak.

Prinsip (Fase 3): hanya halaman PUBLIK, hormati `robots.txt`, tidak melewati
login/CAPTCHA/paywall. Hanya kontak BISNIS publik (email/telepon) yang diambil.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .text import strip_html

# UA jelas dengan identitas agar pemilik situs bisa menghubungi bila perlu.
DEFAULT_UA = "GreenEcoAI/1.0 (+https://greenecoteknologi.com; business-contact)"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?62|0)[\s.\-]?\d{2,3}[\s.\-]?\d{3,4}[\s.\-]?\d{3,5}")
_TEL_RE = re.compile(r"""href=["']tel:([^"']+)["']""", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r"""<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)["']""", re.IGNORECASE
)
_META_DESC_RE2 = re.compile(
    r"""<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["']""", re.IGNORECASE
)
_OG_SITE_RE = re.compile(
    r"""<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']*)["']""", re.IGNORECASE
)
_LINK_RE = re.compile(r"""<a\b[^>]*href=["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.IGNORECASE | re.DOTALL)

# Alamat yang jelas bukan kontak bisnis.
_EMAIL_DOMAIN_BLOCK = ("example.com", "sentry.io", "wixpress.com", "domain.com", "email.com", "yourdomain.com")
_EMAIL_LOCAL_BLOCK = ("noreply", "no-reply", "donotreply", "postmaster", "abuse", "webmaster", "privacy")

# Halaman yang biasanya memuat kontak/deskripsi perusahaan.
_CONTACT_HINTS = (
    "kontak", "contact", "hubungi", "tentang", "about", "perusahaan", "company",
    "profil", "profile", "about-us", "contact-us",
)


def normalize_url(url: str | None) -> str | None:
    """Rapikan URL: tambah https:// bila tanpa skema; None bila tidak valid."""
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    if not re.match(r"^https?://", s, re.IGNORECASE):
        s = "https://" + s.lstrip("/")
    parsed = urlparse(s)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}".rstrip("/") or f"{parsed.scheme}://{parsed.netloc}"


def domain_of(url: str | None) -> str:
    """Domain tanpa `www.` (untuk dedupe & perbandingan situs)."""
    if not url:
        return ""
    netloc = urlparse(url if re.match(r"^https?://", str(url)) else f"https://{url}").netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def canonical_website(url: str | None) -> str:
    d = domain_of(url)
    return f"https://{d}" if d else ""


def robots_allows(client: httpx.Client, url: str, user_agent: str = DEFAULT_UA) -> bool:
    """True bila robots.txt situs mengizinkan pengambilan `url`.

    Bila robots.txt tidak ada (404) -> diizinkan. Bila tidak terjangkau -> diizinkan
    (perilaku standar), tetapi 401/403 dianggap melarang semua.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = client.get(robots_url, headers={"User-Agent": user_agent})
    except httpx.HTTPError:
        return True
    if r.status_code in (401, 403):
        return False
    if r.status_code != 200 or not r.text:
        return True
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(user_agent, url)


def fetch_html(client: httpx.Client, url: str, user_agent: str = DEFAULT_UA) -> str | None:
    """Ambil halaman HTML. None bila gagal/bukan HTML/robots melarang."""
    if not robots_allows(client, url, user_agent):
        return None
    try:
        r = client.get(url, headers={"User-Agent": user_agent})
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype.lower() and ctype:
        return None
    return r.text


def extract_emails(html: str) -> list[str]:
    """Email bisnis publik dari halaman (termasuk `mailto:`), tanpa duplikat."""
    # Dipindai dari HTML mentah agar `mailto:` pada atribut ikut terbaca.
    text = html or ""
    seen: dict[str, None] = {}
    for raw in _EMAIL_RE.findall(text):
        email = raw.strip().strip(".").lower()
        local, _, domain = email.partition("@")
        if not domain or domain in _EMAIL_DOMAIN_BLOCK:
            continue
        if any(local.startswith(bad) for bad in _EMAIL_LOCAL_BLOCK):
            continue
        if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js)$", domain):
            continue
        seen.setdefault(email, None)
    return list(seen)


def extract_phones(html: str) -> list[str]:
    """Nomor telepon bisnis publik (Indonesia), dinormalkan ke format +62."""
    text = strip_html(html or "")
    found: list[str] = []
    for raw in [*_TEL_RE.findall(html or ""), *_PHONE_RE.findall(text)]:
        digits = re.sub(r"[^\d+]", "", raw)
        digits = re.sub(r"^\+?62", "62", digits)
        if digits.startswith("0"):
            digits = "62" + digits[1:]
        if not digits.startswith("62") or not (9 <= len(digits) <= 15):
            continue
        normalized = "+" + digits
        if normalized not in found:
            found.append(normalized)
    return found


def extract_title(html: str) -> str | None:
    m = _TITLE_RE.search(html or "")
    if not m:
        return None
    title = strip_html(m.group(1))
    return title or None


def extract_description(html: str) -> str | None:
    for rx in (_META_DESC_RE, _META_DESC_RE2):
        m = rx.search(html or "")
        if m:
            desc = strip_html(m.group(1))
            if desc:
                return desc
    return None


def extract_site_name(html: str) -> str | None:
    m = _OG_SITE_RE.search(html or "")
    if m:
        name = strip_html(m.group(1))
        if name:
            return name
    return None


def contact_links(base_url: str, html: str, limit: int = 4) -> list[str]:
    """Tautan internal (domain sama) yang mengarah ke halaman kontak/tentang."""
    base_domain = domain_of(base_url)
    seen: dict[str, None] = {}
    for href, label in _LINK_RE.findall(html or ""):
        absolute = urljoin(base_url, href.strip())
        if domain_of(absolute) != base_domain:
            continue
        path = urlparse(absolute).path.lower()
        if path in ("", "/"):
            continue
        hay = f"{path} {strip_html(label).lower()}"
        if any(h in hay for h in _CONTACT_HINTS):
            seen.setdefault(absolute.split("?")[0].split("#")[0], None)
    return list(seen)[:limit]
