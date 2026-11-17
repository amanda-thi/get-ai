import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.registry import build_adapter

s = get_settings()
src = {"id": "x", "name": "SPSE", "adapter_type": "spse", "base_url": s.spse_base_url, "config": {}}
a = build_adapter(src, s)

a._bootstrap()
print("token:", (a._token or "")[:14], "...")
print("cookies setelah bootstrap:", dict(a.client.cookies))

payload = a._post_datatable(2026, 0, 5)
ids = [r[0] for r in (payload.get("data") or [])]
print("ids:", ids)
print("cookies setelah datatable:", dict(a.client.cookies))

for eid in ids[:3]:
    url = a._detail_url(eid)
    for label, headers in [
        ("referer", {"Referer": f"{a.base_url}/nasional/lelang"}),
        ("referer+xrw", {"Referer": f"{a.base_url}/nasional/lelang", "X-Requested-With": "XMLHttpRequest"}),
        ("plain", {}),
    ]:
        r = a.client.get(url, headers=headers)
        print(f"  {eid} [{label}] -> {r.status_code} len={len(r.text)}")
        if r.status_code != 200:
            print("     ", r.text[:160].replace("\n", " "))
