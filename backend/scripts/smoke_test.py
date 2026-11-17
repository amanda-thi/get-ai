"""Smoke test Fase 2 - verifikasi nyata: SPSE Nasional -> Supabase -> analisis AI.

Menjalankan lapisan service langsung (tanpa HTTP/JWT), jadi cukup mengisi `.env`.
Tidak menghapus data apa pun; hanya menambah/memperbarui tender & analisis.

Contoh pemakaian:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\smoke_test.py
    .\\.venv\\Scripts\\python.exe scripts\\smoke_test.py --years 2026 --max-rows 1500
    .\\.venv\\Scripts\\python.exe scripts\\smoke_test.py --dry-run        (tidak menulis ke DB)
    .\\.venv\\Scripts\\python.exe scripts\\smoke_test.py --skip-analyze

Exit code 0 = semua langkah yang dijalankan berhasil; >0 = ada yang gagal/dilewati
karena konfigurasi belum lengkap (lihat pesan).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))


def load_env() -> list[str]:
    """Muat .env dari root repo lalu backend (tanpa menimpa env yang sudah ada)."""
    loaded: list[str] = []
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv ikut pydantic-settings
        return loaded
    for path in (REPO_DIR / ".env", BACKEND_DIR / ".env"):
        if path.exists():
            load_dotenv(path, override=False)
            loaded.append(str(path))
    return loaded


def hr(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke test Fase 2 (SPSE -> DB -> AI).")
    p.add_argument("--years", type=int, nargs="+", default=None, help="tahun anggaran (default: tahun ini & depan)")
    p.add_argument("--max-rows", type=int, default=None, help="batas baris per sumber (default: COLLECT_MAX_ROWS)")
    p.add_argument("--enrich", type=int, default=3, help="jumlah tender yang detailnya diambil (default 3)")
    p.add_argument("--analyze", type=int, default=5, help="jumlah tender dianalisis AI (default 5)")
    p.add_argument("--keywords", default="", help="override keyword, dipisah koma (default: keyword aktif dari DB)")
    p.add_argument("--dry-run", action="store_true", help="ambil dari SPSE & tampilkan hasil tanpa menulis ke DB")
    p.add_argument("--skip-collect", action="store_true", help="lewati langkah koleksi")
    p.add_argument("--skip-analyze", action="store_true", help="lewati langkah analisis AI")
    return p.parse_args()


def main() -> int:  # noqa: C901 - alur linear dengan banyak cabang pesan
    args = parse_args()

    loaded = load_env()
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    hr("1. Konfigurasi")
    print(f"  .env dimuat dari   : {', '.join(loaded) if loaded else '(tidak ada file .env, hanya env OS)'}")
    print(f"  Supabase siap      : {'YA' if settings.db_configured else 'TIDAK'}")
    print(f"  AI siap            : {'YA' if settings.ai_configured else 'TIDAK'} "
          f"(provider={settings.ai_provider}, model={settings.ai_model_name})")
    print(f"  INAPROC API siap   : {'YA' if settings.inaproc_configured else 'TIDAK'}")

    if not settings.db_configured:
        hr("BERHENTI: Supabase belum diisi")
        print("  Isi SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY di .env, lalu ulangi.")
        return 2

    from app.db import SupabaseClient, SupabaseError

    db = SupabaseClient(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_anon_key)

    hr("2. Koneksi & skema database")
    try:
        sources = db.select(
            "tender_sources",
            {"select": "id,name,adapter_type,base_url,is_active,health_status", "order": "name.asc"},
        )
        # cek kolom Fase 2 ada (gagal di sini = migrasi belum lengkap)
        db.select("tenders", {"select": "id,dedupe_hash,matched_keywords", "limit": "1"})
        db.select("tender_analysis", {"select": "id,relevance_score,priority,is_current", "limit": "1"})
    except SupabaseError as e:
        msg = str(e)
        if "42501" in msg or "permission denied" in msg:
            hr("BERHENTI: kunci OK, tapi tabel belum diberi izin (GRANT)")
            print("  Supabase menolak akses ke tabel public. Jalankan migrasi ini di")
            print("  Supabase SQL Editor, lalu ulangi smoke test:")
            print("      supabase/migrations/005_phase2_grants.sql")
            return 4
        hr("BERHENTI: database tidak bisa diakses")
        print(f"  {msg}")
        return 3

    print(f"  Sumber terdaftar   : {len(sources)}")
    for s in sources:
        print(f"    - {s.get('name'):<18} [{s.get('adapter_type')}] aktif={s.get('is_active')} "
              f"status={s.get('health_status')}")
    spse = [s for s in sources if s.get("adapter_type") == "spse" and s.get("is_active")]
    if not spse:
        hr("BERHENTI: sumber SPSE belum ada")
        print("  Jalankan migrasi supabase/migrations/004_phase2_sources.sql di SQL Editor Supabase.")
        return 3

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not keywords:
        try:
            keywords = [r["keyword"] for r in db.select(
                "tender_keywords", {"select": "keyword", "is_active": "eq.true", "order": "keyword.asc"}
            ) if r.get("keyword")]
        except SupabaseError:
            keywords = []
    print(f"  Keyword dipakai    : {len(keywords)}")
    if keywords:
        print(f"    contoh: {', '.join(keywords[:8])}{' ...' if len(keywords) > 8 else ''}")

    years = args.years or [datetime.now().year, datetime.now().year + 1]
    max_rows = args.max_rows or settings.collect_max_rows
    options = {"years": years, "max_rows": max_rows, "enrich_limit": args.enrich}

    # ---- 3. Koleksi ----
    if args.skip_collect:
        print("\n[3] Koleksi: DILEWATI (--skip-collect)")
    elif not keywords:
        print("\n[3] Koleksi: DILEWATI - tidak ada keyword aktif.")
        print("    Jalankan 002_seed_config.sql ATAU pakai --keywords \"sampah,limbah,TPST\".")
    elif args.dry_run:
        hr("3. Koleksi (DRY-RUN, tidak menulis DB)")
        from app.sources.registry import build_adapter

        total = 0
        for src in spse:
            adapter = build_adapter(src, settings)
            try:
                with adapter:
                    found = adapter.discover(keywords, options)
            except Exception as e:  # noqa: BLE001
                print(f"  {src.get('name')}: GAGAL - {e}")
                continue
            total += len(found)
            print(f"  {src.get('name')}: {len(found)} tender cocok keyword (tahun {years})")
            for t in found[:5]:
                print(f"    - [{t.external_id}] {t.package_name[:70]}")
        print(f"  Total cocok        : {total}")
    else:
        hr("3. Koleksi + simpan (SPSE -> Supabase)")
        from app.services import collection

        result = collection.collect_all(db, settings, source_ids=[s["id"] for s in spse], options=options)
        for r in result["sources"]:
            print(f"  {r['name']:<18} status={r['status']:<11} cocok={r['found']:<5} disimpan={r['upserted']}"
                  + (f" error={r['error']}" if r.get("error") else ""))
        print(f"  Total disimpan     : {result['upserted_total']}")
        try:
            total_tenders = db.count("tenders")
            print(f"  Tender di DB       : {total_tenders}")
        except SupabaseError as e:
            print(f"  (gagal hitung total tender: {e})")

    # ---- 4. Analisis AI ----
    if args.skip_analyze or args.dry_run:
        print("\n[4] Analisis AI: DILEWATI")
    elif not settings.ai_configured:
        hr("4. Analisis AI: DILEWATI - kunci AI belum diisi")
        print("  Isi GROQ_API_KEY (gratis di https://console.groq.com) lalu ulangi.")
    else:
        hr("4. Analisis AI (tender yang belum dianalisis)")
        from app.services import analysis

        res = analysis.analyze_pending(db, settings, limit=args.analyze)
        print(f"  Dianalisis         : {res['analyzed']}")
        print(f"  Gagal              : {res['failed']}")
        for r in res["results"]:
            if r["status"] == "ok":
                print(f"    - {r['tender_id']}  {r['priority']:<6} skor={r['relevance_score']}")
            else:
                print(f"    - {r['tender_id']}  ERROR: {r.get('error')}")

    hr("SELESAI")
    print("  Kalau langkah 3 & 4 berhasil: buka frontend -> halaman Tender Monitoring")
    print("  untuk melihat hasilnya (cari/filter/export).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
