"""Metadata & konversi jadwal untuk automation Fase 4.

Sumber kebenaran jadwal ada di DB (`automation_configs.schedule_type` +
`schedule_config`). Modul ini murni (tanpa I/O) agar mudah diuji:

* `cron_from_schedule` -> ekspresi crontab **standar** (0=Minggu, 1=Senin) untuk
  ditampilkan/disimpan sebagai `cron_expression`.
* `build_trigger` -> `CronTrigger` APScheduler (APScheduler memakai 0=Senin, jadi
  hari dikonversi eksplisit agar tidak bergeser).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

SCHEDULE_TYPES = ("daily", "weekly", "monthly", "custom")

DAY_NAMES_ID = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")

# Jenis automation yang didukung beserta dependensi eksternalnya (untuk ditampilkan
# jujur di UI bila kunci belum diisi).
AUTOMATION_TYPES: dict[str, dict] = {
    "tender_monitoring": {
        "name": "Tender Monitoring",
        "description": "Cari tender baru + analisis AI + peringatan deadline.",
        "requires": (),
        "icon": "doc",
    },
    "company_discovery": {
        "name": "Company Discovery",
        "description": "Cari calon pelanggan baru dari sumber publik.",
        "requires": ("lead_search",),
        "icon": "users",
    },
    "lead_qualification": {
        "name": "Lead Qualification",
        "description": "Kualifikasi AI untuk lead yang belum dianalisis.",
        "requires": ("ai",),
        "icon": "star",
    },
    "outreach_draft_generation": {
        "name": "Outreach Draft Generation",
        "description": "Buat draft email penawaran (tanpa mengirim).",
        "requires": ("ai",),
        "icon": "mail",
    },
}

_STD_DOW_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


class ScheduleError(ValueError):
    """Jadwal tidak valid (dipakai router untuk membalas 400)."""


def _int(value, field: str, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ScheduleError(f"{field} harus berupa angka") from None
    if not lo <= n <= hi:
        raise ScheduleError(f"{field} harus antara {lo} dan {hi}")
    return n


def _std_to_aps(dow: int) -> int:
    """Konversi hari crontab standar (0=Minggu) -> APScheduler (0=Senin)."""
    return (dow + 6) % 7


def _dow_number(token: str) -> int:
    token = str(token).strip().lower()
    if token in _STD_DOW_NAMES:
        return _std_to_aps(_STD_DOW_NAMES[token])
    return _std_to_aps(_int(token, "day_of_week", 0, 7) % 7)


def _convert_dow_field(field: str) -> str:
    """Ubah field day-of-week crontab standar menjadi konvensi APScheduler."""
    out: list[str] = []
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = ""
        if "/" in part:
            part, s = part.split("/", 1)
            step = f"/{s}"
        if part in ("*", "?"):
            out.append(f"*{step}")
        elif "-" in part:
            a, b = part.split("-", 1)
            out.append(f"{_dow_number(a)}-{_dow_number(b)}{step}")
        else:
            out.append(f"{_dow_number(part)}{step}")
    return ",".join(out) or "*"


def _schedule_parts(schedule_type: str, schedule_config: dict) -> dict:
    cfg = schedule_config or {}
    if schedule_type not in SCHEDULE_TYPES:
        raise ScheduleError(f"schedule_type tidak valid. Pilihan: {', '.join(SCHEDULE_TYPES)}")
    if schedule_type == "daily":
        return {"minute": _int(cfg.get("minute", 0), "minute", 0, 59),
                "hour": _int(cfg.get("hour", 8), "hour", 0, 23)}
    if schedule_type == "weekly":
        return {"minute": _int(cfg.get("minute", 0), "minute", 0, 59),
                "hour": _int(cfg.get("hour", 8), "hour", 0, 23),
                "day_of_week": _int(cfg.get("day_of_week", 0), "day_of_week", 0, 6)}
    if schedule_type == "monthly":
        return {"minute": _int(cfg.get("minute", 0), "minute", 0, 59),
                "hour": _int(cfg.get("hour", 8), "hour", 0, 23),
                "day": _int(cfg.get("day", 1), "day", 1, 31)}
    # custom
    cron = str(cfg.get("cron", "")).strip()
    if len(cron.split()) != 5:
        raise ScheduleError("cron kustom harus 5 field, mis. '0 8 * * 1'")
    return {"cron": cron}


def cron_from_schedule(schedule_type: str, schedule_config: dict) -> str:
    """Ekspresi crontab standar (0=Minggu) dari konfigurasi jadwal."""
    parts = _schedule_parts(schedule_type, schedule_config)
    if "cron" in parts:
        return parts["cron"]
    minute, hour = parts["minute"], parts["hour"]
    if schedule_type == "daily":
        return f"{minute} {hour} * * *"
    if schedule_type == "weekly":
        std_dow = (parts["day_of_week"] + 1) % 7  # APScheduler 0=Senin -> crontab 1=Senin
        return f"{minute} {hour} * * {std_dow}"
    return f"{minute} {hour} {parts['day']} * *"


def build_trigger(schedule_type: str, schedule_config: dict, tz: ZoneInfo) -> CronTrigger:
    """Buat `CronTrigger` APScheduler dari konfigurasi jadwal."""
    parts = _schedule_parts(schedule_type, schedule_config)
    if "cron" in parts:
        minute, hour, day, month, dow = parts["cron"].split()
        return CronTrigger(
            minute=minute, hour=hour, day=day, month=month,
            day_of_week=_convert_dow_field(dow), timezone=tz,
        )
    if schedule_type == "daily":
        return CronTrigger(minute=parts["minute"], hour=parts["hour"], timezone=tz)
    if schedule_type == "weekly":
        return CronTrigger(minute=parts["minute"], hour=parts["hour"],
                           day_of_week=parts["day_of_week"], timezone=tz)
    return CronTrigger(minute=parts["minute"], hour=parts["hour"],
                       day=parts["day"], timezone=tz)


def get_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Asia/Jakarta")
    except Exception as e:  # pragma: no cover - nama zona rusak
        raise ScheduleError(f"timezone tidak dikenal: {name}") from e


def next_run_at(schedule_type: str, schedule_config: dict, timezone: str,
                base: datetime | None = None) -> datetime | None:
    """Waktu eksekusi berikutnya (timezone-aware) atau None bila tidak ada."""
    tz = get_tz(timezone)
    trigger = build_trigger(schedule_type, schedule_config, tz)
    now = base or datetime.now(tz)
    return trigger.get_next_fire_time(None, now)


def describe_schedule(schedule_type: str, schedule_config: dict, timezone: str = "Asia/Jakarta") -> str:
    """Deskripsi jadwal dalam bahasa Indonesia (untuk UI/log)."""
    try:
        parts = _schedule_parts(schedule_type, schedule_config)
    except ScheduleError:
        return "Jadwal tidak valid"
    tz = timezone or "Asia/Jakarta"
    if "cron" in parts:
        return f"Jadwal kustom: {parts['cron']} ({tz})"
    hhmm = f"{parts['hour']:02d}:{parts['minute']:02d}"
    if schedule_type == "daily":
        return f"Setiap hari pukul {hhmm} ({tz})"
    if schedule_type == "weekly":
        return f"Setiap {DAY_NAMES_ID[parts['day_of_week']]} pukul {hhmm} ({tz})"
    return f"Tanggal {parts['day']} setiap bulan pukul {hhmm} ({tz})"


__all__ = [
    "AUTOMATION_TYPES",
    "SCHEDULE_TYPES",
    "DAY_NAMES_ID",
    "ScheduleError",
    "build_trigger",
    "cron_from_schedule",
    "describe_schedule",
    "get_tz",
    "next_run_at",
]
