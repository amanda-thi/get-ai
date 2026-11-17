import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.registry import build_adapter
from app.sources.spse_nasional import parse_list_row
from app.utils.text import match_keywords

s = get_settings()
src = {"id": "x", "name": "SPSE", "adapter_type": "spse", "base_url": s.spse_base_url, "config": {}}

a = build_adapter(src, s)
try:
    with a:
        rows = a.fetch_year(2026, 200)
except Exception as e:  # noqa: BLE001
    print("FETCH ERROR:", type(e).__name__, e)
    raise SystemExit(1)

print("raw rows 2026:", len(rows))
if not rows:
    print("=> SPSE mengembalikan 0 baris (masalah akses/struktur), bukan soal keyword.")
    raise SystemExit(0)

parsed = [parse_list_row(r) for r in rows]
print("contoh paket:")
for p in parsed[:6]:
    print(f"   [{p['external_id']}] {(p['package_name'] or '')[:72]}")

kws = ["sampah", "limbah", "tpst", "persampahan", "pengolahan", "daur ulang", "ipal", "incinerator"]
hits = 0
for p in parsed:
    text = " ".join(filter(None, [p["package_name"], p["agency"], p["category_year"], p["procurement_type"]]))
    h = match_keywords(text, kws)
    if h:
        hits += 1
        print(f"   MATCH {h}  {(p['package_name'] or '')[:60]}")
print("matches dgn keyword Indonesia:", hits)
