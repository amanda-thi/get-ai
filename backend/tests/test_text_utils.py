from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.utils.text import (
    content_key,
    dedupe_hash,
    iso,
    match_keywords,
    normalize_text,
    parse_id_date,
    parse_id_datetime,
    parse_rupiah,
    strip_html,
)


def test_strip_html_removes_badges_and_entities():
    raw = "PENGADAAN SAMPAH <span class='badge badge-warning'>Tender Ulang</span>&nbsp;&amp; lagi"
    assert strip_html(raw) == "PENGADAAN SAMPAH Tender Ulang & lagi"


def test_normalize_text_strips_punctuation():
    assert normalize_text("Pisau Crusher, Tipe-X (2026)!") == "pisau crusher tipe x 2026"


def test_match_keywords_english_and_indonesian():
    text = "Pengadaan Mesin Pencacah Sampah dan Plastic Recycling Machine"
    hits = match_keywords(text, ["Mesin pencacah sampah", "Recycling Machine", "Crusher Machine"])
    assert hits == ["Mesin pencacah sampah", "Recycling Machine"]


def test_match_keywords_empty_text():
    assert match_keywords(None, ["x"]) == []


def test_parse_rupiah_full_value():
    assert parse_rupiah("Rp. 3.175.070.597,00") == 3175070597.0
    assert parse_rupiah("Rp 200.400.000,00") == 200400000.0


def test_parse_rupiah_abbreviations():
    assert parse_rupiah("204,8 Jt") == 204800000.0
    assert parse_rupiah("36,9 M") == 36900000000.0
    assert parse_rupiah("1,5 T") == 1500000000000.0


def test_parse_rupiah_missing_values():
    assert parse_rupiah(None) is None
    assert parse_rupiah("Nilai Kontrak belum dibuat") is None
    assert parse_rupiah("") is None


def test_parse_id_datetime_with_time():
    tz = ZoneInfo("Asia/Jakarta")
    dt = parse_id_datetime("14 November 2026 19:00")
    assert dt == datetime(2026, 11, 14, 19, 0, tzinfo=tz)


def test_parse_id_date_short_month():
    assert parse_id_date("21 Nov 2026") == date(2026, 11, 21)


def test_parse_id_datetime_invalid():
    assert parse_id_datetime("bukan tanggal") is None


def test_parse_id_datetime_iso_fallback():
    tz = ZoneInfo("Asia/Jakarta")
    assert parse_id_datetime("2026-11-10 08:30:00") == datetime(2026, 11, 10, 8, 30, tzinfo=tz)
    assert parse_id_datetime("2026-11-10T01:30:00Z") == datetime(2026, 11, 10, 8, 30, tzinfo=tz)


def test_dedupe_hash_stable_and_source_scoped():
    a = dedupe_hash("src-1", "10182597000", "Nama", "Instansi")
    b = dedupe_hash("src-1", "10182597000", "Nama lain", "Instansi lain")
    c = dedupe_hash("src-2", "10182597000", "Nama", "Instansi")
    assert a == b  # external_id menang
    assert a != c  # beda sumber -> beda hash


def test_dedupe_hash_fallback_without_external_id():
    a = dedupe_hash("src-1", None, "Nama Paket", "Dinas X")
    b = dedupe_hash("src-1", None, "  nama   paket ", "dinas x")
    assert a == b


def test_content_key_ignores_punctuation_and_case():
    assert content_key("TPST Kota, 2026", "Dinas LH") == content_key("tpst kota 2026", "dinas lh")


def test_iso_serializes_date_and_datetime():
    assert iso(date(2026, 11, 16)) == "2026-11-16"
    assert iso(datetime(2026, 11, 16, 8, 0, tzinfo=ZoneInfo("Asia/Jakarta"))).startswith("2026-11-16T08:00")
