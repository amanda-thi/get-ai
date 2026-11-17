"""Handler 4 automation Fase 4 — memanggil layanan Phase 2/3 yang sudah ada.

Setiap handler menerima `JobContext` dan mengembalikan dict ringkasan:
    {"total": int, "success": int, "failed": int, "message": str, ...}
Runner menentukan status job dari dict ini. **Tidak ada data palsu**: bila dependensi
eksternal (kunci AI / kunci pencarian) belum ada, handler melempar `JobError` dengan
pesan jelas sehingga job ditandai gagal — bukan "sukses" palsu.

Automation outreach HANYA membuat draft; tidak pernah mengirim email.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..services import analysis as analysis_service
from ..services import collection
from ..services import lead_analysis as lead_analysis_service
from ..services import leads as leads_service
from ..services import outreach as outreach_service
from ..utils.text import iso
from .errors import JobError

_DRAFT_STATUSES = ("draft", "saved_for_later", "approved", "sent")


def _params(ctx) -> dict:
    return ctx.config.get("params") or {}


# --- A. Automatic Tender Monitoring ---

def _notify_upcoming_deadlines(ctx, days: int) -> int:
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=max(1, days))
    rows = ctx.db.select(
        "tenders",
        {
            "select": "id,package_name,agency,bid_deadline",
            "and": f"(bid_deadline.gte.{iso(now)},bid_deadline.lte.{iso(until)})",
            "order": "bid_deadline.asc",
            "limit": "100",
        },
    )
    if rows:
        ctx.notify(
            "tender_deadline",
            f"{len(rows)} tender deadline ≤ {days} hari",
            f"Contoh: {rows[0].get('package_name') or '-'} ({rows[0].get('agency') or '-'}).",
            link="/tenders",
            dedupe_key=f"tender_deadline:{ctx.job['id']}",
        )
    return len(rows)


def tender_monitoring(ctx) -> dict:
    db, settings = ctx.db, ctx.settings
    params = _params(ctx)
    analyze_limit = int(params.get("analyze_limit") or settings.analyze_max_batch)
    deadline_days = int(params.get("deadline_days") or 7)

    ctx.check()
    ctx.log("info", "Mengumpulkan tender dari sumber aktif.")
    collected = collection.collect_all(db, settings)
    sources = collected.get("sources") or []
    sources_total = int(collected.get("sources_total") or 0)
    sources_ok = int(collected.get("sources_ok") or 0)
    failed_sources = sum(1 for r in sources if r.get("status") in ("failed", "blocked"))
    upserted = int(collected.get("upserted_total") or 0)
    ctx.progress(35, total=upserted, success=upserted, failed=failed_sources)
    ctx.check()

    analyzed = analyze_failed = 0
    if upserted and settings.ai_configured:
        ctx.log("info", f"Menganalisis hingga {analyze_limit} tender baru dengan AI.")
        res = analysis_service.analyze_pending(db, settings, limit=analyze_limit)
        analyzed = int(res.get("analyzed") or 0)
        analyze_failed = int(res.get("failed") or 0)
    elif upserted:
        ctx.log("warning", "Kunci AI belum diisi: analisis relevansi dilewati (tender tetap tersimpan).")
    ctx.progress(75, total=upserted, success=upserted, failed=failed_sources + analyze_failed)
    ctx.check()

    deadline_upcoming = _notify_upcoming_deadlines(ctx, deadline_days)

    if upserted:
        ctx.notify(
            "tender_new",
            f"{upserted} tender baru/diperbarui",
            f"Tender Monitoring: {upserted} tender dari {sources_ok}/{sources_total} sumber aktif.",
            link="/tenders",
            dedupe_key=f"tender_new:{ctx.job['id']}",
        )

    message = (
        f"{upserted} tender disimpan/diperbarui, {analyzed} dianalisis AI "
        f"({analyze_failed} gagal analisis), {deadline_upcoming} deadline mendekat, "
        f"{failed_sources} sumber gagal dari {sources_total}."
    )
    return {
        "total": upserted,
        "success": upserted,
        "failed": failed_sources + analyze_failed,
        "analyzed": analyzed,
        "deadline_upcoming": deadline_upcoming,
        "message": message,
    }


# --- B. Automatic Company Discovery ---

def company_discovery(ctx) -> dict:
    db, settings = ctx.db, ctx.settings
    if not settings.lead_search_configured:
        raise JobError(
            "Kunci pencarian belum diisi (LEAD_SEARCH_API_KEY). "
            "Isi di .env, atau tambah perusahaan manual dari halaman Company Leads."
        )
    params = _params(ctx)
    queries = [str(q).strip() for q in (params.get("queries") or []) if str(q).strip()]
    if not queries:
        queries = collection.active_keywords(db)[:3]
    if not queries:
        raise JobError("Belum ada kata kunci pencarian. Isi parameter 'queries' pada konfigurasi automation.")

    locations = [str(x).strip() for x in (params.get("locations") or []) if str(x).strip()] or [None]
    industries = [str(x).strip() for x in (params.get("industries") or []) if str(x).strip()] or [None]
    limit = int(params.get("limit") or 10)

    combos = [(q, loc, ind) for q in queries for loc in locations for ind in industries][:10]
    found = created = duplicates = failed = 0
    for i, (q, loc, ind) in enumerate(combos):
        ctx.check()
        try:
            res = leads_service.discover(db, settings, query=q, industry=ind, location=loc, limit=limit)
        except Exception as e:  # kegagalan satu pencarian tidak menghentikan sisanya
            failed += 1
            ctx.log("warning", f"Pencarian '{q}' gagal: {e}")
            continue
        found += int(res.get("found") or 0)
        created += int(res.get("created") or 0)
        duplicates += int(res.get("duplicates") or 0)
        failed += int(res.get("failed") or 0)
        ctx.progress(int(90 * (i + 1) / len(combos)), total=found, success=created, failed=failed)

    if created:
        ctx.notify(
            "lead_new",
            f"{created} perusahaan baru ditemukan",
            f"Company Discovery: {created} baru, {duplicates} duplikat dari {len(combos)} pencarian.",
            link="/leads",
            dedupe_key=f"lead_new:{ctx.job['id']}",
        )

    message = (
        f"{created} perusahaan baru, {duplicates} duplikat, {failed} gagal, "
        f"dari {len(combos)} pencarian."
    )
    return {"total": found, "success": created, "failed": failed, "duplicates": duplicates, "message": message}


# --- C. Automatic Lead Qualification ---

def lead_qualification(ctx) -> dict:
    db, settings = ctx.db, ctx.settings
    if not settings.ai_configured:
        raise JobError("Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    params = _params(ctx)
    limit = min(int(params.get("limit") or 20), settings.lead_analysis_max_batch)
    ctx.check()
    ctx.log("info", f"Kualifikasi AI hingga {limit} lead yang belum dianalisis.")
    res = lead_analysis_service.analyze_pending(db, settings, limit=limit)
    analyzed = int(res.get("analyzed") or 0)
    failed = int(res.get("failed") or 0)
    ctx.progress(90, total=analyzed + failed, success=analyzed, failed=failed)

    high = [r for r in res.get("results", []) if r.get("status") == "ok" and r.get("category") == "HIGH"]
    if high:
        ctx.notify(
            "lead_high_priority",
            f"{len(high)} lead prioritas tinggi",
            "Lead baru berkualifikasi HIGH. Tinjau di halaman Company Leads.",
            link="/leads",
            dedupe_key=f"lead_high:{ctx.job['id']}",
        )

    message = f"{analyzed} lead dikualifikasi AI, {failed} gagal ({len(high)} prioritas tinggi)."
    return {"total": analyzed + failed, "success": analyzed, "failed": failed, "high": len(high), "message": message}


# --- D. Automatic Outreach Draft Generation (draft saja, tanpa kirim) ---

def _find_email(db, company_id: str) -> str | None:
    rows = db.select(
        "company_contacts",
        {"select": "value", "company_id": f"eq.{company_id}", "contact_type": "eq.email", "limit": "1"},
    )
    value = (rows[0].get("value") if rows else None) or ""
    return value.strip() or None


def _has_draft(db, lead_id: str, email_type: str, language: str) -> bool:
    rows = db.select(
        "outreach_messages",
        {
            "select": "id",
            "lead_id": f"eq.{lead_id}",
            "email_type": f"eq.{email_type}",
            "language": f"eq.{language}",
            "status": f"in.({','.join(_DRAFT_STATUSES)})",
            "limit": "1",
        },
    )
    return bool(rows)


def outreach_draft_generation(ctx) -> dict:
    db, settings = ctx.db, ctx.settings
    if not settings.ai_configured:
        raise JobError("Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    params = _params(ctx)
    limit = min(int(params.get("limit") or 20), settings.outreach_max_batch)
    email_type = params.get("email_type") or "company_intro"
    language = params.get("language") or "id"
    priorities = params.get("priorities") or ["HIGH", "MEDIUM"]
    min_score = int(params.get("min_score") or 0)

    ctx.check()
    candidates = db.select(
        "leads_with_analysis",
        {
            "select": "id,name,lead_id,lead_status,analysis_category,analysis_lead_score",
            "lead_status": "eq.qualified",
            "analysis_category": f"in.({','.join(priorities)})",
            "order": "analysis_lead_score.desc.nullslast",
            "limit": str(max(limit * 3, limit)),
        },
    )
    ctx.log("info", f"{len(candidates)} kandidat lead qualified berprioritas {','.join(priorities)}.")

    created = skipped_no_email = skipped_duplicate = failed = 0
    processed = 0
    for i, row in enumerate(candidates):
        ctx.check()
        if processed >= limit:
            break
        lead_id = row.get("lead_id")
        company_id = row.get("id")
        if not lead_id or not company_id:
            continue
        score = row.get("analysis_lead_score") or 0
        if min_score and int(score) < min_score:
            continue
        processed += 1
        if _has_draft(db, lead_id, email_type, language):
            skipped_duplicate += 1
            continue
        recipient = _find_email(db, company_id)
        if not recipient:
            skipped_no_email += 1
            ctx.log("info", f"Dilewati (tanpa email bisnis valid): {row.get('name')}")
            continue
        try:
            outreach_service.generate_draft(
                db, settings,
                {
                    "lead_id": lead_id,
                    "email_type": email_type,
                    "language": language,
                    "recipient_email": recipient,
                },
            )
            created += 1
        except Exception as e:  # satu kegagalan tidak menghentikan sisanya
            failed += 1
            ctx.log("warning", f"Gagal membuat draft untuk {row.get('name')}: {e}")
        ctx.progress(int(90 * (i + 1) / max(1, len(candidates))), total=processed, success=created, failed=failed)

    if created:
        ctx.notify(
            "outreach_draft_ready",
            f"{created} draft email siap diperiksa",
            f"Outreach Draft Generation: {created} draft baru ({email_type}/{language}). "
            "Kirim hanya setelah disetujui admin.",
            link="/outreach",
            dedupe_key=f"outreach_draft:{ctx.job['id']}",
        )

    message = (
        f"{created} draft dibuat, {skipped_duplicate} dilewati (sudah ada draft), "
        f"{skipped_no_email} dilewati (tanpa email), {failed} gagal. Tidak ada email yang dikirim."
    )
    return {
        "total": processed,
        "success": created,
        "failed": failed,
        "skipped_duplicate": skipped_duplicate,
        "skipped_no_email": skipped_no_email,
        "message": message,
    }


HANDLERS = {
    "tender_monitoring": tender_monitoring,
    "company_discovery": company_discovery,
    "lead_qualification": lead_qualification,
    "outreach_draft_generation": outreach_draft_generation,
}

__all__ = ["HANDLERS", "tender_monitoring", "company_discovery", "lead_qualification", "outreach_draft_generation"]
