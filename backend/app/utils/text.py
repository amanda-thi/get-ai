"""Utilitas teks: bersihkan HTML, normalisasi, cocokkan keyword, parse angka/tanggal Indonesia, hash dedupe."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NONWORD_RE = re.compile(r"[^a-z0-9 ]+")

_ID_MONTHS = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "agt": 8, "ags": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12,
}

_DATE_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:[\s,]+(\d{1,2})[:.](\d{2}))?", re.IGNORECASE
)


def strip_html(value: str | None) -> str:
    """Buang tag HTML & entitas, rapikan spasi."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize_text(value: str | None) -> str:
    """Huruf kecil, buang tanda baca, rapikan spasi — untuk pencocokan & dedupe."""
    if not value:
        return ""
    return _WS_RE.sub(" ", _NONWORD_RE.sub(" ", strip_html(value).lower())).strip()


def match_keywords(text: str | None, keywords: list[str]) -> list[str]:
    """Kembalikan keyword (asli) yang muncul sebagai substring pada teks ternormalisasi."""
    hay = normalize_text(text)
    if not hay:
        return []
    hits: list[str] = []
    for kw in keywords:
        needle = normalize_text(kw)
        if needle and needle in hay:
            hits.append(kw)
    return hits


# Terpanjang lebih dulu supaya "jt" tidak salah cocok sebagai "t" (triliun).
_SUFFIXES = [
    ("triliun", 1e12),
    ("miliar", 1e9),
    ("juta", 1e6),
    ("ribu", 1e3),
    ("jt", 1e6),
    ("rb", 1e3),
    ("t", 1e12),
    ("m", 1e9),
    ("k", 1e3),
]


def parse_rupiah(value: str | None) -> float | None:
    """Parse nilai rupiah Indonesia. 'Rp. 3.175.070.597,00' -> 3175070597.0 ; '204,8 Jt' -> 204800000.0."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if re.search(r"belum dibuat|belum ada|tidak ada|n/a", s, re.IGNORECASE):
        return None

    mult = 1.0
    stripped = s.rstrip()
    low = stripped.lower()
    # Suffix hanya berlaku bila di akhir & didahului angka/spasi (mis. "204,8 Jt").
    for suffix, factor in _SUFFIXES:
        if not low.endswith(suffix):
            continue
        prefix = low[: len(low) - len(suffix)]
        if prefix and prefix[-1].isalpha():
            continue
        mult = factor
        s = stripped[: len(stripped) - len(suffix)]
        break

    s = re.sub(r"(?i)rp\.?", "", s)
    s = s.replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None

    has_comma = "," in s
    has_dot = "." in s
    if has_comma:
        # koma = desimal, titik = pemisah ribuan
        s = s.replace(".", "").replace(",", ".")
    elif has_dot:
        # titik = pemisah ribuan (konteks Indonesia)
        s = s.replace(".", "")
    try:
        return float(s) * mult
    except ValueError:
        return None


def parse_id_datetime(value: str | None) -> datetime | None:
    """Parse '14 November 2026 19:00' / '14 Nov 2026' / ISO '2026-11-10 08:30:00' -> datetime WIB."""
    if not value:
        return None
    m = _DATE_RE.search(value)
    if m:
        day, month_name, year, hour, minute = m.groups()
        month = _ID_MONTHS.get(month_name.lower())
        if not month:
            return None
        try:
            return datetime(
                int(year), month, int(day), int(hour or 0), int(minute or 0), tzinfo=JAKARTA
            )
        except ValueError:
            return None
    # Fallback ISO 8601 (mis. API INAPROC: '2026-11-10 08:30:00' atau '2026-11-10T08:30:00Z').
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=JAKARTA)
    return dt.astimezone(JAKARTA)


def parse_id_date(value: str | None) -> date | None:
    dt = parse_id_datetime(value)
    return dt.date() if dt else None


def dedupe_hash(source_id: str, external_id: str | None, package_name: str, agency: str | None) -> str:
    """Hash idempoten per sumber: utamakan external_id, fallback nama+instansi ternormalisasi."""
    if external_id:
        key = f"{source_id}:{external_id.strip()}"
    else:
        key = f"{source_id}:{normalize_text(package_name)}:{normalize_text(agency)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def content_key(package_name: str, agency: str | None) -> str:
    """Kunci konten lintas-sumber (untuk deteksi duplikat antar sumber)."""
    return f"{normalize_text(package_name)}|{normalize_text(agency)}"


def iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat()
