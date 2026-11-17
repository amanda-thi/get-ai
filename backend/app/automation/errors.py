"""Galat khusus automation (dipisah agar runner & handler tidak saling mengimpor)."""
from __future__ import annotations


class JobError(Exception):
    """Kegagalan yang sudah dijelaskan (mis. kunci API belum diisi)."""


class JobCancelled(Exception):
    """Job dihentikan atas permintaan admin (kooperatif)."""


class JobTimeout(Exception):
    """Job melewati `timeout_seconds` (kooperatif)."""


__all__ = ["JobError", "JobCancelled", "JobTimeout"]
