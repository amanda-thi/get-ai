from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..db import SupabaseClient, SupabaseError
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

MESSAGE_STATUSES = ("draft", "saved_for_later", "approved", "sent", "failed")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def automation_overview(db: SupabaseClient) -> list[dict]:
    """Jadwal automation untuk dashboard.

    Utamakan tabel Fase 4 `automation_configs`; jatuh ke `automation_schedules`
    (Fase 1) bila migrasi 010 belum dijalankan.
    """
    try:
        rows = db.select(
            "automation_configs",
            {
                "select": "automation_name,automation_type,cron_expression,timezone,is_enabled,"
                          "last_run_at,last_status,next_run_at",
                "order": "automation_name.asc",
            },
        )
        return [
            {
                "job_type": r.get("automation_name") or r.get("automation_type"),
                "automation_type": r.get("automation_type"),
                "cron_expression": r.get("cron_expression"),
                "timezone": r.get("timezone"),
                "is_active": r.get("is_enabled"),
                "last_run_at": r.get("last_run_at"),
                "last_status": r.get("last_status"),
                "next_run_at": r.get("next_run_at"),
            }
            for r in rows
        ]
    except SupabaseError:
        return db.select(
            "automation_schedules",
            {"select": "job_type,cron_expression,timezone,is_active,last_run_at,last_status,next_run_at"},
        )


def weekly_tenders(db: SupabaseClient, tz: ZoneInfo, now: datetime | None = None) -> list[dict]:
    """Jumlah tender baru (first_seen_at) per hari, 7 hari terakhir, zona waktu lokal."""
    now = (now or datetime.now(tz)).astimezone(tz)
    start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.select(
        "tenders",
        {"select": "first_seen_at", "first_seen_at": f"gte.{_iso(start)}", "limit": "5000"},
    )
    counts = {(start + timedelta(days=i)).date(): 0 for i in range(7)}
    for r in rows:
        d = datetime.fromisoformat(r["first_seen_at"].replace("Z", "+00:00")).astimezone(tz).date()
        if d in counts:
            counts[d] += 1
    return [{"date": d.isoformat(), "count": c} for d, c in counts.items()]


@router.get("/overview")
def overview(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    """Semua angka dihitung langsung dari DB. Kosong = 0, tidak ada data dummy."""
    tz = ZoneInfo(get_settings().timezone)
    now = datetime.now(timezone.utc)
    window = f"(bid_deadline.gte.{_iso(now)},bid_deadline.lte.{_iso(now + timedelta(days=7))})"
    try:
        return {
            "tenders_total": db.count("tenders"),
            "tenders_high_priority": db.count("tender_analysis", {"priority": "eq.HIGH", "is_current": "eq.true"}),
            "tenders_deadline_7d": db.count("tenders", {"and": window}),
            "companies_total": db.count("companies"),
            "leads_high_potential": db.count("lead_analysis", {"category": "eq.HIGH", "is_current": "eq.true"}),
            "outreach": {s: db.count("outreach_messages", {"status": f"eq.{s}"}) for s in MESSAGE_STATUSES},
            "weekly_tenders": weekly_tenders(db, tz),
            "top_tenders": db.select(
                "tender_analysis",
                {
                    "select": "relevance_score,priority,tenders(package_name,agency,bid_deadline)",
                    "is_current": "eq.true",
                    "order": "relevance_score.desc",
                    "limit": "5",
                },
            ),
            "sources": db.select(
                "tender_sources",
                {"select": "name,health_status,last_checked_at", "order": "name.asc"},
            ),
            "automation": automation_overview(db),
            "recent_activity": db.select(
                "system_logs",
                {"select": "level,component,message,created_at", "order": "created_at.desc", "limit": "10"},
            ),
        }
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
