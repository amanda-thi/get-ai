import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.registry import build_adapter

s = get_settings()
src = {"id": "x", "name": "SPSE", "adapter_type": "spse", "base_url": s.spse_base_url, "config": {}}
a = build_adapter(src, s)
a._bootstrap()

payload = a._post_datatable(2026, 0, 5)
ids = [r[0] for r in (payload.get("data") or [])]
eid = ids[-1]
print("=== 403 body (id", eid, ") ===")
r = a.client.get(a._detail_url(eid), headers={"Referer": f"{a.base_url}/nasional/lelang"})
print("status", r.status_code)
txt = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S)
txt = re.sub(r"<[^>]+>", " ", txt)
print(re.sub(r"\s+", " ", txt)[:1200])

print("\n=== link detail di halaman daftar ===")
r2 = a.client.get(f"{a.base_url}/nasional/lelang")
links = sorted(set(re.findall(r"/nasional/lelang/[0-9A-Za-z\-]+/[a-z]+", r2.text)))
print("status", r2.status_code, "jumlah link unik:", len(links))
for l in links[:10]:
    print("  ", l)
