import json

import httpx
import pytest

from app.db import SupabaseClient, SupabaseError, is_conflict_error, is_missing_table_error


def make(handler):
    c = SupabaseClient("https://x.supabase.co", "svc", "anon")
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def test_count_parses_content_range():
    c = make(lambda r: httpx.Response(206, json=[], headers={"content-range": "0-0/42"}))
    assert c.count("tenders") == 42


def test_count_empty_table():
    c = make(lambda r: httpx.Response(200, json=[], headers={"content-range": "*/0"}))
    assert c.count("tenders") == 0


def test_get_user_invalid_token_returns_none():
    c = make(lambda r: httpx.Response(401, json={}))
    assert c.get_user("bad") is None


def test_user_token_not_replaced_by_service_key():
    seen = {}

    def h(r):
        seen["auth"] = r.headers["authorization"]
        return httpx.Response(200, json={"id": "u"})

    make(h).get_user("usertoken")
    assert seen["auth"] == "Bearer usertoken"


def test_insert_posts_json_and_prefers_representation():
    seen = {}

    def h(r):
        seen["method"] = r.method
        seen["prefer"] = r.headers.get("prefer")
        seen["body"] = r.content.decode()
        return httpx.Response(201, json=[{"id": "1"}])

    rows = make(h).insert("tenders", {"package_name": "X"})
    assert rows == [{"id": "1"}]
    assert seen["method"] == "POST"
    assert "return=representation" in seen["prefer"]
    assert json.loads(seen["body"]) == [{"package_name": "X"}]


def test_upsert_sets_merge_duplicates_and_on_conflict():
    seen = {}

    def h(r):
        seen["url"] = str(r.url)
        seen["prefer"] = r.headers.get("prefer")
        return httpx.Response(201, json=[{"id": "1"}])

    make(h).insert("tenders", {"package_name": "X"}, upsert=True, on_conflict="dedupe_hash")
    assert "on_conflict=dedupe_hash" in seen["url"]
    assert "resolution=merge-duplicates" in seen["prefer"]


def test_update_patches_with_filters():
    seen = {}

    def h(r):
        seen["method"] = r.method
        seen["url"] = str(r.url)
        seen["body"] = r.content.decode()
        return httpx.Response(200, json=[{"id": "1"}])

    make(h).update("tender_analysis", {"tender_id": "eq.abc"}, {"is_current": False})
    assert seen["method"] == "PATCH"
    assert "tender_id=eq.abc" in seen["url"]
    assert json.loads(seen["body"]) == {"is_current": False}


def test_insert_raises_on_conflict():
    import pytest

    from app.db import SupabaseError

    c = make(lambda r: httpx.Response(409, text="duplicate key"))
    with pytest.raises(SupabaseError):
        c.insert("tenders", {"package_name": "X"})


def test_is_conflict_error_detects_409_and_23505():
    assert is_conflict_error(SupabaseError("GET /x gagal (409): duplicate key"))
    assert is_conflict_error(SupabaseError("kode 23505"))
    assert not is_conflict_error(SupabaseError("gagal (500)"))


def test_is_missing_table_error_detects_pgrst205_and_42p01():
    # Migrasi belum dijalankan: PostgREST PGRST205 / Postgres 42P01 / pesan schema cache.
    assert is_missing_table_error(SupabaseError('{"code":"PGRST205"}'))
    assert is_missing_table_error(SupabaseError("ERROR: 42P01 relation does not exist"))
    assert is_missing_table_error(SupabaseError("Could not find the table in the schema cache"))
    assert not is_missing_table_error(SupabaseError("permission denied (42501)"))
