from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `.env` di folder backend (bila ada) lalu `.env` di root repo (lokasi yang
    # didokumentasikan & dipakai docker-compose). File yang tidak ada dilewati.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"
    rate_limit: str = "120/minute"
    timezone: str = "Asia/Jakarta"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # --- Fase 2: AI ---
    ai_provider: str = "groq"  # groq | openai
    groq_api_key: str = ""
    openai_api_key: str = ""
    ai_model: str = ""  # kosong = pakai default per provider
    ai_timeout: float = 60.0

    # --- Fase 2: sumber tender ---
    spse_base_url: str = "https://spse.inaproc.id"
    # Halaman HTML SPSE menolak (403) User-Agent non-browser; endpoint JSON tidak.
    # Karena halaman ini publik (robots.txt: Allow: /) dan tanpa CAPTCHA/login,
    # kita pakai UA browser standar agar halaman detail/jadwal dapat dibaca.
    spse_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    http_timeout: float = 30.0
    collect_max_rows: int = 2000  # batas aman baris per sumber per koleksi
    analyze_max_batch: int = 25  # batas aman analisis AI per panggilan

    # INAPROC API Gateway resmi (butuh token terdaftar; lihat PHASE2_PLAN.md)
    inaproc_api_base: str = "https://data.inaproc.id"
    inaproc_api_key: str = ""

    # --- Fase 3: AI Marketing & Business Outreach ---
    # Profil perusahaan (satu-satunya sumber fakta untuk AI). Kosong = config/company_profile.yaml.
    company_profile_path: str = ""
    lead_analysis_max_batch: int = 25  # batas lead dianalisis AI per panggilan
    lead_fetch_max_pages: int = 4  # halaman publik per situs saat pengumpulan info
    outreach_max_batch: int = 20  # batas email digenerate per panggilan

    # SMTP (kredensial HANYA di backend). Kosong = pengiriman dinonaktifkan, draft tetap jalan.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True  # STARTTLS pada port 587; false untuk relay internal
    smtp_timeout: float = 30.0

    # Discovery berbasis kata kunci butuh API pencarian. Kosong = fitur nonaktif
    # dengan pesan jelas; tambah manual & pengumpulan dari situs tetap berfungsi.
    lead_search_provider: str = "serper"  # serper | tavily | none
    lead_search_api_key: str = ""
    lead_search_base_url: str = "https://google.serper.dev"  # tavily: https://api.tavily.com

    # --- Fase 4: Automation & Intelligent Scheduling ---
    # Scheduler dinyalakan saat startup. Matikan (SCHEDULER_ENABLED=false) untuk
    # proses yang bukan web (mis. migrasi/test) atau saat menjalankan banyak worker
    # tanpa lock DB. Lock job tetap dijaga unique index di database.
    scheduler_enabled: bool = True
    automation_max_workers: int = 4  # ukuran thread pool scheduler
    automation_default_timeout: int = 900  # detik; batas kooperatif per job
    automation_misfire_grace: int = 3600  # detik; job terjadwal yang terlewat masih dijalankan
    # Notifikasi email ke admin (butuh SMTP). Default nonaktif: notifikasi internal saja.
    automation_notify_email: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def ai_key(self) -> str:
        return self.openai_api_key if self.ai_provider == "openai" else self.groq_api_key

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_key)

    @property
    def ai_model_name(self) -> str:
        if self.ai_model:
            return self.ai_model
        return "gpt-4o-mini" if self.ai_provider == "openai" else "openai/gpt-oss-120b"

    @property
    def inaproc_configured(self) -> bool:
        return bool(self.inaproc_api_key)

    @property
    def company_profile_file(self) -> Path:
        """Lokasi profil perusahaan. Default relatif ke root repo (bukan cwd)."""
        if self.company_profile_path:
            return Path(self.company_profile_path)
        return Path(__file__).resolve().parents[2] / "config" / "company_profile.yaml"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def lead_search_configured(self) -> bool:
        provider = (self.lead_search_provider or "").strip().lower()
        return bool(self.lead_search_api_key and provider not in ("", "none"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
