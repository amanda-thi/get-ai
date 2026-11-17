"""Router Reports: ringkasan lintas modul (tender, leads, outreach, automation)
beserta ekspor Excel (.xlsx) dan PDF.

Semua angka dihitung dari database, tanpa data dummy. PostgREST tidak mendukung
GROUP BY, jadi baris diambil (dibatasi `_MAX_ROWS` per bagian) lalu diagregasi di
Python — pola yang sama dipakai ekspor tender (Fase 2).

Bagian yang tabelnya belum ada (mis. migrasi 010 belum dijalankan) ditandai
`available: false` beserta pesan galatnya, tanpa menjatuhkan seluruh laporan.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..db import SupabaseClient, SupabaseError
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Batas baris yang diambil per bagian untuk agregasi (sejalan dengan _EXPORT_MAX tender).
_MAX_ROWS = 5000
_CHUNK = 1000

PRIORITIES = ("HIGH", "MEDIUM", "LOW")
LEAD_STATUSES = (
    "new", "qualified", "contacted", "responded",
    "negotiation", "won", "lost", "do_not_contact",
)
MESSAGE_STATUSES = ("draft", "saved_for_later", "approved", "sent", "failed")
EMAIL_TYPES = (
    "company_intro", "product_intro", "partnership_proposal",
    "service_offering", "follow_up",
)
JOB_STATUSES = (
    "pending", "queued", "running", "completed",
    "partially_completed", "failed", "cancelled",
)

TENDER_SELECT = (
    "id,package_name,agency,location,procurement_type,hps,budget_ceiling,bid_deadline,"
    "status,source_id,first_seen_at,announced_at,analysis_id,analysis_priority,"
    "analysis_category,analysis_relevance_score,analysis_deadline_flag"
)
LEAD_SELECT = (
    "id,name,industry,city,province,source_name,lead_status,created_at,analysis_id,"
    "analysis_lead_score,analysis_category"
)
MESSAGE_SELECT = "id,status,email_type,language,campaign_id,recipient_email,created_at,sent_at"
JOB_SELECT = (
    "id,job_type,job_name,status,trigger_type,started_at,completed_at,created_at,"
    "total_processed,success_count,failed_count,attempt,max_attempts,error_message"
)


# --- util ---

def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _fetch(
    db: SupabaseClient,
    table: str,
    select: str,
    *,
    order: str | None = None,
    cap: int = _MAX_ROWS,
) -> list[dict]:
    """Ambil baris dengan paginasi sampai `cap` (PostgREST membatasi per request)."""
    rows: list[dict] = []
    offset = 0
    while len(rows) < cap:
        params: dict = {"select": select, "limit": str(_CHUNK), "offset": str(offset)}
        if order:
            params["order"] = order
        batch = db.select(table, params)
        rows.extend(batch)
        if len(batch) < _CHUNK:
            break
        offset += _CHUNK
    return rows[:cap]


def _counts(rows: list[dict], field: str, keys=(), blank: str = "Belum diketahui") -> dict:
    out = {k: 0 for k in keys}
    for r in rows:
        k = r.get(field)
        if k is None or k == "":
            k = blank
        out[k] = out.get(k, 0) + 1
    return out


def _trend(rows: list[dict], field: str, days: int, tz: ZoneInfo) -> list[dict]:
    """Jumlah baris per hari (zona lokal), `days` hari terakhir termasuk hari ini."""
    now = datetime.now(tz)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {(start + timedelta(days=i)).date(): 0 for i in range(days)}
    for r in rows:
        d = _parse(r.get(field))
        if d is None:
            continue
        day = d.astimezone(tz).date()
        if day in counts:
            counts[day] += 1
    return [{"date": d.isoformat(), "count": c} for d, c in counts.items()]


def _avg(values: list[int]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _job_duration(job: dict) -> int | None:
    start, end = _parse(job.get("started_at")), _parse(job.get("completed_at"))
    if start and end:
        return max(0, int((end - start).total_seconds()))
    return None


def _deadline_within(value, now: datetime, days: int) -> bool:
    d = _parse(value)
    return bool(d and now <= d <= now + timedelta(days=days))


# --- bagian ---

def _tenders_section(db: SupabaseClient, days: int, tz: ZoneInfo):
    rows = _fetch(db, "tenders_with_analysis", TENDER_SELECT, order="first_seen_at.desc")
    sources = {s["id"]: s.get("name") for s in _fetch(db, "tender_sources", "id,name", cap=1000)}
    analyzed = [r for r in rows if r.get("analysis_id")]
    now = datetime.now(timezone.utc)

    source_counts = _counts(rows, "source_id")
    by_source = [
        {"source": sources.get(sid) or "Tanpa sumber", "count": n}
        for sid, n in sorted(source_counts.items(), key=lambda x: (-x[1], str(x[0])))
    ]
    top = sorted(analyzed, key=lambda r: r.get("analysis_relevance_score") or 0, reverse=True)[:10]

    data = {
        "available": True,
        "total": len(rows),
        "analyzed": len(analyzed),
        "unanalyzed": len(rows) - len(analyzed),
        "high_priority": sum(1 for r in analyzed if r.get("analysis_priority") == "HIGH"),
        "deadline_7d": sum(1 for r in rows if _deadline_within(r.get("bid_deadline"), now, 7)),
        "by_priority": _counts(rows, "analysis_priority", PRIORITIES, blank="Belum dianalisis"),
        "by_category": _counts(analyzed, "analysis_category"),
        "by_status": _counts(rows, "status"),
        "by_source": by_source,
        "trend": _trend(rows, "first_seen_at", days, tz),
        "top": [
            {
                "id": r.get("id"),
                "package_name": r.get("package_name"),
                "agency": r.get("agency"),
                "priority": r.get("analysis_priority"),
                "relevance_score": r.get("analysis_relevance_score"),
                "bid_deadline": r.get("bid_deadline"),
            }
            for r in top
        ],
    }
    return data, rows


def _leads_section(db: SupabaseClient, days: int, tz: ZoneInfo):
    rows = _fetch(db, "leads_with_analysis", LEAD_SELECT, order="created_at.desc")
    analyzed = [r for r in rows if r.get("analysis_id")]
    total = len(rows)
    won = sum(1 for r in rows if r.get("lead_status") == "won")
    contacted = sum(1 for r in rows if r.get("lead_status") in ("contacted", "responded", "negotiation", "won"))
    top = sorted(analyzed, key=lambda r: r.get("analysis_lead_score") or 0, reverse=True)[:10]

    data = {
        "available": True,
        "total": total,
        "analyzed": len(analyzed),
        "high_potential": sum(1 for r in analyzed if r.get("analysis_category") == "HIGH"),
        "won": won,
        "contacted": contacted,
        "conversion_rate": round(won / total * 100, 1) if total else 0,
        "by_status": _counts(rows, "lead_status", LEAD_STATUSES),
        "by_priority": _counts(rows, "analysis_category", PRIORITIES, blank="Belum dianalisis"),
        "by_industry": _counts(rows, "industry"),
        "by_source": _counts(rows, "source_name"),
        "trend": _trend(rows, "created_at", days, tz),
        "top": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "industry": r.get("industry"),
                "city": r.get("city"),
                "lead_status": r.get("lead_status"),
                "score": r.get("analysis_lead_score"),
                "category": r.get("analysis_category"),
            }
            for r in top
        ],
    }
    return data, rows


def _outreach_section(db: SupabaseClient, days: int, tz: ZoneInfo):
    rows = _fetch(db, "outreach_messages", MESSAGE_SELECT, order="created_at.desc")
    campaigns = {c["id"]: c.get("name") for c in _fetch(db, "outreach_campaigns", "id,name", cap=1000)}
    by_status = _counts(rows, "status", MESSAGE_STATUSES)
    sent, failed = by_status.get("sent", 0), by_status.get("failed", 0)
    finished = sent + failed

    campaign_counts = _counts(rows, "campaign_id")
    by_campaign = [
        {"campaign": campaigns.get(cid) or "Tanpa kampanye", "count": n}
        for cid, n in sorted(campaign_counts.items(), key=lambda x: (-x[1], str(x[0])))
    ]

    data = {
        "available": True,
        "total": len(rows),
        "pending_approval": by_status.get("draft", 0) + by_status.get("saved_for_later", 0),
        "sent": sent,
        "failed": failed,
        "send_success_rate": round(sent / finished * 100, 1) if finished else 0,
        "by_status": by_status,
        "by_email_type": _counts(rows, "email_type", EMAIL_TYPES),
        "by_language": _counts(rows, "language"),
        "by_campaign": by_campaign,
        "trend": _trend(rows, "created_at", days, tz),
    }
    return data, rows


def _automation_section(db: SupabaseClient, days: int, tz: ZoneInfo):
    jobs = _fetch(db, "automation_jobs", JOB_SELECT, order="created_at.desc")
    configs = _fetch(
        db, "automation_configs",
        "id,automation_name,automation_type,is_enabled,last_status,last_run_at,next_run_at,"
        "cron_expression,timezone",
        order="automation_name.asc", cap=1000,
    )
    names = {c.get("automation_type"): c.get("automation_name") for c in configs}
    by_status = _counts(jobs, "status", JOB_STATUSES)
    finished = by_status.get("completed", 0) + by_status.get("partially_completed", 0) + by_status.get("failed", 0)
    durations = [_job_duration(j) for j in jobs]

    by_type: list[dict] = []
    for jtype in sorted({j.get("job_type") for j in jobs if j.get("job_type")}):
        group = [j for j in jobs if j.get("job_type") == jtype]
        st = _counts(group, "status", JOB_STATUSES)
        fin = st.get("completed", 0) + st.get("partially_completed", 0) + st.get("failed", 0)
        by_type.append({
            "type": jtype,
            "name": names.get(jtype) or jtype,
            "total": len(group),
            "completed": st.get("completed", 0),
            "partially_completed": st.get("partially_completed", 0),
            "failed": st.get("failed", 0),
            "cancelled": st.get("cancelled", 0),
            "running": st.get("running", 0),
            "success_rate": round(st.get("completed", 0) / fin * 100, 1) if fin else 0,
            "avg_duration_seconds": _avg([_job_duration(j) for j in group]),
        })

    failures = [
        {
            "id": j.get("id"),
            "job_name": j.get("job_name") or names.get(j.get("job_type")) or j.get("job_type"),
            "job_type": j.get("job_type"),
            "error_message": j.get("error_message"),
            "created_at": j.get("created_at"),
        }
        for j in jobs if j.get("status") == "failed"
    ][:5]

    data = {
        "available": True,
        "total_jobs": len(jobs),
        "success_rate": round(by_status.get("completed", 0) / finished * 100, 1) if finished else 0,
        "avg_duration_seconds": _avg(durations),
        "by_status": by_status,
        "by_type": by_type,
        "recent_failures": failures,
        "trend": _trend(jobs, "created_at", days, tz),
        "configs": [
            {
                "id": c.get("id"),
                "automation_name": c.get("automation_name"),
                "automation_type": c.get("automation_type"),
                "is_enabled": c.get("is_enabled"),
                "last_status": c.get("last_status"),
                "last_run_at": c.get("last_run_at"),
                "next_run_at": c.get("next_run_at"),
                "cron_expression": c.get("cron_expression"),
                "timezone": c.get("timezone"),
            }
            for c in configs
        ],
    }
    return data, jobs


_LOADERS = (
    ("tenders", _tenders_section),
    ("leads", _leads_section),
    ("outreach", _outreach_section),
    ("automation", _automation_section),
)


def _gather(db: SupabaseClient, days: int, tz: ZoneInfo) -> tuple[dict, dict]:
    sections: dict = {}
    raw: dict = {}
    for key, fn in _LOADERS:
        try:
            data, rows = fn(db, days, tz)
        except SupabaseError as e:
            data, rows = {"available": False, "error": str(e)}, []
        sections[key] = data
        raw[key] = rows
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period_days": days,
        **sections,
    }
    return report, raw


# --- endpoint ---

@router.get("/summary")
def summary(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Ringkasan lintas modul untuk periode `days` hari terakhir."""
    tz = ZoneInfo(get_settings().timezone)
    report, _ = _gather(db, days, tz)
    return report


# --- ekspor ---

def _safe(value) -> str:
    """Teks aman untuk font standar PDF (Helvetica, Latin-1)."""
    return str(value if value is not None else "").encode("latin-1", "replace").decode("latin-1")


def _pdf_text(value) -> str:
    """Teks untuk Paragraph reportlab: aman Latin-1 sekaligus escape markup."""
    return _safe(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xlsx_bytes(report: dict, raw: dict) -> bytes:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover - hanya bila dependensi hilang
        raise HTTPException(503, "openpyxl belum terpasang di backend") from e

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ringkasan"

    t, l, o, a = report["tenders"], report["leads"], report["outreach"], report["automation"]

    def add(label="", value=""):
        ws.append([label, value])

    add("Laporan", "Green Eco AI")
    add("Dibuat", report["generated_at"])
    add("Periode (hari)", report["period_days"])
    add()
    add("TENDER")
    if t.get("available"):
        add("Total tender", t.get("total"))
        add("Sudah dianalisis", t.get("analyzed"))
        add("Belum dianalisis", t.get("unanalyzed"))
        add("Prioritas tinggi", t.get("high_priority"))
        add("Deadline <= 7 hari", t.get("deadline_7d"))
        for k, v in (t.get("by_priority") or {}).items():
            add(f"  Prioritas {k}", v)
        for k, v in (t.get("by_status") or {}).items():
            add(f"  Status {k}", v)
        for row in t.get("by_source") or []:
            add(f"  Sumber {row['source']}", row["count"])
    else:
        add("Tidak tersedia", t.get("error"))
    add()
    add("LEADS")
    if l.get("available"):
        add("Total perusahaan", l.get("total"))
        add("High potential", l.get("high_potential"))
        add("Sudah dikontak", l.get("contacted"))
        add("Converted (won)", l.get("won"))
        add("Tingkat konversi (%)", l.get("conversion_rate"))
        for k, v in (l.get("by_status") or {}).items():
            add(f"  Status {k}", v)
        for k, v in (l.get("by_priority") or {}).items():
            add(f"  Prioritas {k}", v)
    else:
        add("Tidak tersedia", l.get("error"))
    add()
    add("OUTREACH")
    if o.get("available"):
        add("Total pesan", o.get("total"))
        add("Menunggu persetujuan", o.get("pending_approval"))
        add("Terkirim", o.get("sent"))
        add("Gagal kirim", o.get("failed"))
        add("Tingkat keberhasilan kirim (%)", o.get("send_success_rate"))
        for k, v in (o.get("by_status") or {}).items():
            add(f"  Status {k}", v)
        for k, v in (o.get("by_email_type") or {}).items():
            add(f"  Tipe {k}", v)
    else:
        add("Tidak tersedia", o.get("error"))
    add()
    add("AUTOMATION")
    if a.get("available"):
        add("Total job", a.get("total_jobs"))
        add("Tingkat sukses (%)", a.get("success_rate"))
        add("Durasi rata-rata (dtk)", a.get("avg_duration_seconds"))
        for k, v in (a.get("by_status") or {}).items():
            add(f"  Status {k}", v)
        for row in a.get("by_type") or []:
            add(f"  {row['name']} - total", row["total"])
            add(f"  {row['name']} - sukses", row["completed"])
            add(f"  {row['name']} - gagal", row["failed"])
    else:
        add("Tidak tersedia", a.get("error"))

    sh = wb.create_sheet("Tender")
    sh.append(["ID", "Nama Paket", "Instansi", "Lokasi", "Jenis", "HPS", "Pagu",
               "Deadline", "Status", "Prioritas", "Skor", "Kategori", "Sumber"])
    for r in raw.get("tenders", []):
        sh.append([
            r.get("id"), r.get("package_name"), r.get("agency"), r.get("location"),
            r.get("procurement_type"), r.get("hps"), r.get("budget_ceiling"),
            r.get("bid_deadline"), r.get("status"), r.get("analysis_priority"),
            r.get("analysis_relevance_score"), r.get("analysis_category"), r.get("source_id"),
        ])

    sh = wb.create_sheet("Leads")
    sh.append(["ID", "Nama", "Industri", "Kota", "Provinsi", "Sumber", "Status",
               "Prioritas", "Skor"])
    for r in raw.get("leads", []):
        sh.append([
            r.get("id"), r.get("name"), r.get("industry"), r.get("city"), r.get("province"),
            r.get("source_name"), r.get("lead_status"), r.get("analysis_category"),
            r.get("analysis_lead_score"),
        ])

    sh = wb.create_sheet("Outreach")
    sh.append(["ID", "Status", "Tipe Email", "Bahasa", "Kampanye", "Penerima", "Dibuat", "Terkirim"])
    for r in raw.get("outreach", []):
        sh.append([
            r.get("id"), r.get("status"), r.get("email_type"), r.get("language"),
            r.get("campaign_id"), r.get("recipient_email"), r.get("created_at"), r.get("sent_at"),
        ])

    sh = wb.create_sheet("Automation")
    sh.append(["ID", "Automation", "Tipe", "Pemicu", "Status", "Diproses", "Sukses",
               "Gagal", "Percobaan", "Durasi (dtk)", "Mulai", "Selesai", "Error"])
    for r in raw.get("automation", []):
        sh.append([
            r.get("id"), r.get("job_name"), r.get("job_type"), r.get("trigger_type"),
            r.get("status"), r.get("total_processed"), r.get("success_count"),
            r.get("failed_count"), f"{r.get('attempt')}/{r.get('max_attempts')}",
            _job_duration(r), r.get("started_at"), r.get("completed_at"), r.get("error_message"),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf_bytes(report: dict) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:  # pragma: no cover - hanya bila dependensi hilang
        raise HTTPException(503, "reportlab belum terpasang di backend") from e

    t, l, o, a = report["tenders"], report["leads"], report["outreach"], report["automation"]
    styles = getSampleStyleSheet()
    story: list = []

    def heading(title):
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(_pdf_text(title), styles["Heading2"]))

    def table(header, rows):
        data = [[_safe(c) for c in header]] + [[_safe(c) for c in row] for row in rows]
        tb = Table(data, hAlign="LEFT", repeatRows=1)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#134a72")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e3e9ee")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f8")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tb)

    story.append(Paragraph("Laporan Green Eco AI", styles["Title"]))
    story.append(Paragraph(
        _pdf_text(f"Dibuat: {report['generated_at']} · Periode: {report['period_days']} hari terakhir"),
        styles["Normal"],
    ))

    heading("Ringkasan Tender")
    if t.get("available"):
        table(["Metrik", "Nilai"], [
            ["Total tender", t.get("total")],
            ["Sudah dianalisis", t.get("analyzed")],
            ["Belum dianalisis", t.get("unanalyzed")],
            ["Prioritas tinggi", t.get("high_priority")],
            ["Deadline <= 7 hari", t.get("deadline_7d")],
        ])
        table(["Prioritas", "Jumlah"], list((t.get("by_priority") or {}).items()))
        if t.get("by_source"):
            table(["Sumber", "Jumlah"], [(r["source"], r["count"]) for r in t["by_source"]])
    else:
        story.append(Paragraph(_pdf_text(f"Tidak tersedia: {t.get('error')}"), styles["Normal"]))

    heading("Ringkasan Leads")
    if l.get("available"):
        table(["Metrik", "Nilai"], [
            ["Total perusahaan", l.get("total")],
            ["High potential", l.get("high_potential")],
            ["Sudah dikontak", l.get("contacted")],
            ["Converted (won)", l.get("won")],
            ["Tingkat konversi (%)", l.get("conversion_rate")],
        ])
        table(["Status CRM", "Jumlah"], list((l.get("by_status") or {}).items()))
    else:
        story.append(Paragraph(_pdf_text(f"Tidak tersedia: {l.get('error')}"), styles["Normal"]))

    heading("Ringkasan Outreach")
    if o.get("available"):
        table(["Metrik", "Nilai"], [
            ["Total pesan", o.get("total")],
            ["Menunggu persetujuan", o.get("pending_approval")],
            ["Terkirim", o.get("sent")],
            ["Gagal kirim", o.get("failed")],
            ["Keberhasilan kirim (%)", o.get("send_success_rate")],
        ])
        table(["Status", "Jumlah"], list((o.get("by_status") or {}).items()))
    else:
        story.append(Paragraph(_pdf_text(f"Tidak tersedia: {o.get('error')}"), styles["Normal"]))

    heading("Kinerja Automation")
    if a.get("available"):
        table(["Metrik", "Nilai"], [
            ["Total job", a.get("total_jobs")],
            ["Tingkat sukses (%)", a.get("success_rate")],
            ["Durasi rata-rata (dtk)", a.get("avg_duration_seconds")],
        ])
        if a.get("by_type"):
            table(["Automation", "Total", "Selesai", "Sebagian", "Gagal", "Sukses (%)"], [
                [r["name"], r["total"], r["completed"], r["partially_completed"], r["failed"], r["success_rate"]]
                for r in a["by_type"]
            ])
        if a.get("recent_failures"):
            table(["Job gagal", "Pesan galat", "Waktu"], [
                [r["job_name"], r["error_message"] or "-", r["created_at"] or "-"]
                for r in a["recent_failures"]
            ])
    else:
        story.append(Paragraph(_pdf_text(f"Tidak tersedia: {a.get('error')}"), styles["Normal"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title="Laporan Green Eco AI",
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    doc.build(story)
    return buf.getvalue()


def _stamp() -> str:
    return datetime.now(ZoneInfo(get_settings().timezone)).strftime("%Y%m%d-%H%M")


@router.get("/export.xlsx")
def export_xlsx(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Unduh laporan sebagai Excel (satu sheet ringkasan + detail per modul)."""
    tz = ZoneInfo(get_settings().timezone)
    report, raw = _gather(db, days, tz)
    content = _xlsx_bytes(report, raw)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="laporan-green-eco-{_stamp()}.xlsx"'},
    )


@router.get("/export.pdf")
def export_pdf(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Unduh laporan sebagai PDF."""
    tz = ZoneInfo(get_settings().timezone)
    report, _ = _gather(db, days, tz)
    content = _pdf_bytes(report)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="laporan-green-eco-{_stamp()}.pdf"'},
    )
