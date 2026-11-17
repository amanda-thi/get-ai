"""Pengumpulan info perusahaan dari situs publik (URL diberikan admin).

Mengambil halaman utama + beberapa halaman kontak/tentang (maks `lead_fetch_max_pages`),
selalu menghormati robots.txt. Hanya kontak BISNIS publik yang diambil.
"""
from __future__ import annotations

import re

import httpx

from ..config import Settings
from ..utils.web import (
    contact_links,
    extract_description,
    extract_emails,
    extract_phones,
    extract_site_name,
    extract_title,
    fetch_html,
    normalize_url,
)
from .base import DiscoveryError, RawCompany, RawContact

_TITLE_NOISE = re.compile(
    r"\s*[\|\-–—:]\s*(home|beranda|official site|official website|situs resmi).*$", re.IGNORECASE
)


def guess_name(html: str, url: str) -> str:
    """Tebak nama perusahaan: og:site_name -> <title> (dibersihkan) -> domain."""
    name = extract_site_name(html)
    if name:
        return name.strip()
    title = extract_title(html)
    if title:
        cleaned = _TITLE_NOISE.sub("", title).strip(" -|–—:")
        if cleaned:
            return cleaned
    from ..utils.web import domain_of

    domain = domain_of(url)
    return domain.split(".")[0].replace("-", " ").title() if domain else url


def collect_from_url(url: str, settings: Settings, client: httpx.Client | None = None) -> RawCompany:
    """Kumpulkan info dari satu situs. DiscoveryError bila URL salah/tidak bisa diakses."""
    norm = normalize_url(url)
    if not norm:
        raise DiscoveryError(f"URL tidak valid: {url!r}")

    ua = settings.spse_user_agent
    owns = client is None
    client = client or httpx.Client(timeout=settings.http_timeout, follow_redirects=True)
    try:
        home = fetch_html(client, norm, ua)
        if home is None:
            raise DiscoveryError(
                f"Tidak bisa mengambil halaman publik {norm} "
                "(diblokir robots.txt, bukan HTML, atau tidak dapat diakses)."
            )

        name = guess_name(home, norm)
        description = extract_description(home)
        contacts: list[RawContact] = []
        seen_contacts: set[tuple[str, str]] = set()

        def add_contacts(html: str, page_url: str) -> None:
            for email in extract_emails(html):
                key = ("email", email)
                if key not in seen_contacts:
                    seen_contacts.add(key)
                    contacts.append(RawContact("email", email, page_url))
            for phone in extract_phones(html):
                key = ("phone", phone)
                if key not in seen_contacts:
                    seen_contacts.add(key)
                    contacts.append(RawContact("phone", phone, page_url))

        add_contacts(home, norm)

        pages = 1
        for link in contact_links(norm, home, limit=max(0, settings.lead_fetch_max_pages - 1)):
            if pages >= settings.lead_fetch_max_pages:
                break
            sub = fetch_html(client, link, ua)
            if sub is None:
                continue
            pages += 1
            if not description:
                description = extract_description(sub)
            add_contacts(sub, link)

        return RawCompany(
            name=name,
            website=norm,
            description=description,
            source_name="website",
            source_url=norm,
            contacts=contacts,
            raw_payload={"pages_fetched": pages},
        )
    finally:
        if owns:
            client.close()
