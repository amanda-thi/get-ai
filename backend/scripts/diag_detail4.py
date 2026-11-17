import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.registry import build_adapter

s = get_settings()
src = {"id": "x", "name": "SPSE", "adapter_type": "spse", "base_url": s.spse_base_url, "config": {}}
a = build_adapter(src, s)
a._bootstrap()
payload = a._post_datatable(2026, 0, 1)
eid = payload["data"][0][0]
print("id uji:", eid)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
browser_headers = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"{a.base_url}/nasional/lelang",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}

variants = [
    ("UA sekarang", f"{a.base_url}/nasional/lelang/{eid}/pengumumanlelang", {"Referer": f"{a.base_url}/nasional/lelang"}),
    ("UA browser", f"{a.base_url}/nasional/lelang/{eid}/pengumumanlelang", browser_headers),
    ("UA browser + tahun", f"{a.base_url}/nasional/lelang/{eid}/pengumumanlelang?tahun=2026", browser_headers),
    ("tanpa /pengumumanlelang", f"{a.base_url}/nasional/lelang/{eid}", browser_headers),
]
for label, url, headers in variants:
    r = a.client.get(url, headers=headers)
    print(f"  {label:<24} -> {r.status_code} len={len(r.text)}  {url}")
