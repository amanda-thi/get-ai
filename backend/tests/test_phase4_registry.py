"""Uji modul registry Fase 4: konversi jadwal -> cron -> trigger APScheduler.

Fokus pada kebenaran hari (crontab standar 0=Minggu vs APScheduler 0=Senin) dan
timezone Asia/Jakarta, karena kesalahan di sini membuat jadwal bergeser satu hari.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.automation import registry

TZ = ZoneInfo("Asia/Jakarta")
MONDAY = datetime(2026, 11, 16, 0, 0, tzinfo=TZ)  # 16 Nov 2026 = Senin


def test_cron_weekly_monday_is_standard_crontab():
    # schedule_config memakai 0=Senin; cron standar memakai 1=Senin.
    assert registry.cron_from_schedule("weekly", {"day_of_week": 0, "hour": 8, "minute": 0}) == "0 8 * * 1"


def test_cron_weekly_sunday_maps_to_zero():
    assert registry.cron_from_schedule("weekly", {"day_of_week": 6, "hour": 9, "minute": 30}) == "30 9 * * 0"


def test_cron_daily_monthly_custom():
    assert registry.cron_from_schedule("daily", {"hour": 6, "minute": 30}) == "30 6 * * *"
    assert registry.cron_from_schedule("monthly", {"day": 1, "hour": 9, "minute": 0}) == "0 9 1 * *"
    assert registry.cron_from_schedule("custom", {"cron": "15 7 * * 5"}) == "15 7 * * 5"


def test_trigger_weekly_monday_fires_monday():
    trig = registry.build_trigger("weekly", {"day_of_week": 0, "hour": 8, "minute": 0}, TZ)
    nxt = trig.get_next_fire_time(None, MONDAY)
    assert nxt.weekday() == 0 and nxt.hour == 8 and nxt.minute == 0


def test_trigger_weekly_tuesday_fires_tuesday():
    trig = registry.build_trigger("weekly", {"day_of_week": 1, "hour": 9, "minute": 0}, TZ)
    nxt = trig.get_next_fire_time(None, MONDAY)
    assert nxt.weekday() == 1 and nxt.hour == 9


def test_trigger_custom_converts_standard_dow():
    # crontab standar '1' = Senin -> harus tetap Senin di APScheduler.
    trig = registry.build_trigger("custom", {"cron": "0 8 * * 1"}, TZ)
    nxt = trig.get_next_fire_time(None, MONDAY)
    assert nxt.weekday() == 0


def test_trigger_custom_sunday_name():
    trig = registry.build_trigger("custom", {"cron": "0 8 * * sun"}, TZ)
    nxt = trig.get_next_fire_time(None, MONDAY)
    assert nxt.weekday() == 6


def test_trigger_custom_dow_range_and_list():
    trig = registry.build_trigger("custom", {"cron": "0 8 * * mon-fri"}, TZ)
    nxt = trig.get_next_fire_time(None, MONDAY)
    assert nxt.weekday() == 0  # Senin
    trig2 = registry.build_trigger("custom", {"cron": "0 8 * * 1,3"}, TZ)
    nxt2 = trig2.get_next_fire_time(None, MONDAY)
    assert nxt2.weekday() == 0  # Senin lebih dulu dari Rabu


def test_next_run_at_timezone_jakarta():
    nxt = registry.next_run_at(
        "weekly", {"day_of_week": 1, "hour": 9, "minute": 0}, "Asia/Jakarta", base=MONDAY
    )
    assert nxt.weekday() == 1 and nxt.hour == 9
    assert nxt.utcoffset().total_seconds() == 7 * 3600  # WIB +07:00


def test_describe_schedule_indonesian():
    assert registry.describe_schedule("weekly", {"day_of_week": 0, "hour": 8, "minute": 0}) == \
        "Setiap Senin pukul 08:00 (Asia/Jakarta)"
    assert registry.describe_schedule("daily", {"hour": 6, "minute": 5}) == \
        "Setiap hari pukul 06:05 (Asia/Jakarta)"
    assert "Tanggal 1" in registry.describe_schedule("monthly", {"day": 1, "hour": 9, "minute": 0})
    assert "kustom" in registry.describe_schedule("custom", {"cron": "0 8 * * 1"})


def test_invalid_schedules_raise_schedule_error():
    with pytest.raises(registry.ScheduleError):
        registry.cron_from_schedule("weekly", {"day_of_week": 9})
    with pytest.raises(registry.ScheduleError):
        registry.cron_from_schedule("daily", {"hour": 99})
    with pytest.raises(registry.ScheduleError):
        registry.cron_from_schedule("custom", {"cron": "not a cron"})
    with pytest.raises(registry.ScheduleError):
        registry.cron_from_schedule("hourly", {})


def test_get_tz_rejects_unknown():
    with pytest.raises(registry.ScheduleError):
        registry.get_tz("Not/AZone")


def test_automation_types_metadata():
    assert set(registry.AUTOMATION_TYPES) == {
        "tender_monitoring",
        "company_discovery",
        "lead_qualification",
        "outreach_draft_generation",
    }
    assert registry.AUTOMATION_TYPES["lead_qualification"]["requires"] == ("ai",)
    assert registry.AUTOMATION_TYPES["company_discovery"]["requires"] == ("lead_search",)
