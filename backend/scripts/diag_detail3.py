import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.registry import build_adapter

s = get_settings()
src = {"id": "x", "name": "SPSE", "adapter_type": "spse", "base_url": s.spse_base_url, "config": {}}
a = build_adapter(src, s)
a._bootstrap()
payload = a._post_datatable(2026, 0, 2)
print("keys payload:", list(payload.keys()))
print("keys row[0]:", payload["data"][0] if isinstance(payload["data"][0], dict) else type(payload["data"][0]))
print(json.dumps(payload, ensure_ascii=False)[:2500])
