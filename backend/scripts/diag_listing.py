import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import SupabaseClient
from app.routers.tenders import _LIST_TABLE, build_list_params, shape_tender

s = get_settings()
db = SupabaseClient(s.supabase_url, s.supabase_service_role_key, s.supabase_anon_key)


def run(label, **kw):
    params, filters = build_list_params(page=1, per_page=5, **kw)
    rows = db.select(_LIST_TABLE, params)
    total = db.count(_LIST_TABLE, filters, select="id")
    print(f"\n[{label}] total={total}  ditampilkan={len(rows)}")
    for r in rows:
        t = shape_tender(r)
        a = t.get("analysis") or {}
        print(f"   {t['package_name'][:52]:<52} | {a.get('priority') or '-':<6} skor={a.get('relevance_score')}")
    return rows


run("tanpa filter, sort announced_at desc", sort="announced_at", order="desc")
run("filter prioritas=MEDIUM (view column)", priority="MEDIUM")
run("sort relevance_score desc", sort="relevance_score", order="desc")
run("cari q=sampah", q="sampah")
run("cari q=limbah", q="limbah")

# detail
first = db.select("tenders", {"select": "id", "limit": "1", "order": "created_at.desc"})[0]["id"]
det = db.select("tenders", {
    "select": "id,package_name,tender_analysis(id,category,relevance_score,priority,is_current)",
    "id": f"eq.{first}", "limit": "1",
})
print(f"\n[detail] id={first} -> embed ok: {bool(det and det[0].get('tender_analysis'))}")
