"""Klien AI (Groq & OpenAI, keduanya OpenAI-compatible) via httpx. Tidak menyimpan DB."""
from __future__ import annotations

import json

import httpx

from ..config import Settings


class AIError(Exception):
    """Gagal memanggil atau mengurai respons AI."""


class AIClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=settings.ai_timeout)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "AIClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def base_url(self) -> str:
        return "https://api.openai.com/v1" if self.settings.ai_provider == "openai" else "https://api.groq.com/openai/v1"

    def complete_json(self, system: str, user: str, *, temperature: float = 0.1) -> dict:
        """Panggil chat completions dan kembalikan objek JSON. AIError bila gagal/tak terparse."""
        if not self.settings.ai_configured:
            raise AIError(
                f"Kunci AI belum diisi (provider={self.settings.ai_provider}). "
                "Isi GROQ_API_KEY atau OPENAI_API_KEY di .env backend."
            )
        payload = {
            "model": self.settings.ai_model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            r = self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.ai_key}", "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.HTTPError as e:
            raise AIError(f"AI tidak terjangkau: {e}") from e
        if r.status_code in (401, 403):
            raise AIError(f"AI menolak akses ({r.status_code}) — periksa API key")
        if r.status_code != 200:
            raise AIError(f"AI error {r.status_code}: {r.text[:200]}")
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise AIError(f"Struktur respons AI tak terduga: {e}") from e
        try:
            return json.loads(content)
        except (TypeError, ValueError) as e:
            raise AIError(f"Output AI bukan JSON valid: {e}") from e
