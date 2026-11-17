"""Limiter slowapi bersama (dipakai main.py dan endpoint yang butuh batas khusus)."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings

# Default limit dari setting; endpoint tertentu dapat menambah batas lebih ketat.
limiter = Limiter(key_func=get_remote_address, default_limits=[get_settings().rate_limit])

__all__ = ["limiter"]
