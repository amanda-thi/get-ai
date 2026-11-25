import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, apiDownload } from '../lib/api'
import { Loading, ErrorBox, Empty } from '../components/States'
import Pagination from '../components/Pagination'
import { CATEGORIES, dateOnly, dt, priorityChip, rupiah } from '../lib/format'
import { useI18n } from '../lib/i18n'

const EMPTY = { q: '', priority: '', category: '', source_id: '', status: '', sort: 'announced_at', order: 'desc' }
const PER_PAGE = 5

function buildParams(filters, extra = {}) {
  const p = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => { if (v) p.set(k, v) })
  Object.entries(extra).forEach(([k, v]) => p.set(k, String(v)))
  return p.toString()
}

export default function Tenders() {
  const { t } = useI18n()
  const nav = useNavigate()
  const [filters, setFilters] = useState(EMPTY)
  const [qInput, setQInput] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sources, setSources] = useState([])
  const [exporting, setExporting] = useState(false)

  const [showCollect, setShowCollect] = useState(false)
  const [collect, setCollect] = useState({ years: String(new Date().getFullYear()), max_rows: 200, enrich_limit: 0, keywords: '', source_ids: [] })
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState(null)
  const [runError, setRunError] = useState('')

  const query = useMemo(() => buildParams(filters, { page, per_page: PER_PAGE }), [filters, page])

  const load = useCallback(() => {
    setLoading(true)
    api(`/api/tenders?${query}`)
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [query])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    api('/api/sources').then((d) => setSources(d.sources || [])).catch(() => {})
  }, [])

  const set = (patch) => { setFilters((f) => ({ ...f, ...patch })); setPage(1) }

  const runCollect = async () => {
    setRunning(true); setRunResult(null); setRunError('')
    try {
      const body = {
        years: collect.years.split(',').map((s) => s.trim()).filter(Boolean).map(Number),
        max_rows: Number(collect.max_rows) || undefined,
        enrich_limit: Number(collect.enrich_limit) || 0,
        keywords: collect.keywords.split(',').map((s) => s.trim()).filter(Boolean),
        source_ids: collect.source_ids.length ? collect.source_ids : undefined,
      }
      setRunResult(await api('/api/tenders/collect', { method: 'POST', body: JSON.stringify(body) }))
      load()
    } catch (e) { setRunError(e.message) } finally { setRunning(false) }
  }

  const doExport = async () => {
    setExporting(true); setError('')
    try { await apiDownload(`/api/tenders/export?${buildParams(filters)}`, 'tenders.xlsx') }
    catch (e) { setError(e.message) } finally { setExporting(false) }
  }

  const items = data?.items || []

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t('Tender Monitoring')}</h1>
          <p className="sub">{t('Hasil pemantauan sumber resmi, dianalisis AI untuk skor relevansi.')}</p>
        </div>
        <div className="toolbar">
          <button className="btn ghost" onClick={() => setShowCollect((v) => !v)}>{t('Cari sekarang')}</button>
          <button className="btn" onClick={doExport} disabled={exporting}>{exporting ? t('Menyiapkan…') : t('Export Excel')}</button>
        </div>
      </div>

      {showCollect && (
        <div className="card">
          <h2>{t('Pencarian manual')}</h2>
          <div className="formgrid">
            <label className="field">{t('Tahun anggaran (pisahkan koma)')}
              <input value={collect.years} onChange={(e) => setCollect({ ...collect, years: e.target.value })} placeholder="2026, 2027" />
            </label>
            <label className="field">{t('Batas baris per tahun')}
              <input type="number" min="1" value={collect.max_rows} onChange={(e) => setCollect({ ...collect, max_rows: e.target.value })} />
            </label>
            <label className="field">{t('Ambil detail/jadwal (0 = tidak, N = N teratas)')}
              <input type="number" min="0" value={collect.enrich_limit} onChange={(e) => setCollect({ ...collect, enrich_limit: e.target.value })} />
            </label>
            <label className="field">{t('Keyword (opsional, pisahkan koma)')}
              <input value={collect.keywords} onChange={(e) => setCollect({ ...collect, keywords: e.target.value })} placeholder={t('kosong = pakai keyword aktif di DB')} />
            </label>
            <label className="field">{t('Sumber (opsional)')}
              <select
                multiple size={Math.min(4, Math.max(1, sources.length))}
                value={collect.source_ids}
                onChange={(e) => setCollect({ ...collect, source_ids: Array.from(e.target.selectedOptions, (o) => o.value) })}
              >
                {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          </div>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="btn" onClick={runCollect} disabled={running}>{running ? t('Menjalankan…') : t('Jalankan pencarian')}</button>
            {running && <span className="sub">{t('Mengambil dari sumber bisa memakan waktu beberapa detik…')}</span>}
          </div>
          {runError && <div className="err" style={{ marginTop: 12 }}>{runError}</div>}
          {runResult && (
            <div className="runresult">
              <b>{t('{ok}/{total} sumber OK · {saved} tender disimpan/diperbarui', { ok: runResult.sources_ok, total: runResult.sources_total, saved: runResult.upserted_total })}</b>
              <div className="sub">{t('Keyword dipakai: {keywords}', { keywords: runResult.keywords_used })}</div>
              <ul>
                {runResult.sources.map((s) => (
                  <li key={s.source_id}>
                    <span className={`chip ${s.status === 'ok' ? 'OK' : s.status === 'blocked' ? 'M' : 'H'}`}>{s.status}</span>{' '}
                    {t('{name}: {found} cocok', { name: s.name, found: s.found })}{s.error ? ` — ${s.error}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <form className="toolbar filters" onSubmit={(e) => { e.preventDefault(); set({ q: qInput }) }}>
          <input className="search" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={t('Cari nama paket / instansi…')} />
          <select value={filters.priority} onChange={(e) => set({ priority: e.target.value })}>
            <option value="">{t('Semua prioritas')}</option>
            <option value="HIGH">{t('High')}</option>
            <option value="MEDIUM">{t('Medium')}</option>
            <option value="LOW">{t('Low')}</option>
          </select>
          <select value={filters.category} onChange={(e) => set({ category: e.target.value })}>
            <option value="">{t('Semua kategori')}</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{t(c)}</option>)}
          </select>
          <select value={filters.source_id} onChange={(e) => set({ source_id: e.target.value })}>
            <option value="">{t('Semua sumber')}</option>
            {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select value={`${filters.sort}:${filters.order}`} onChange={(e) => {
            const [sort, order] = e.target.value.split(':')
            set({ sort, order })
          }}>
            <option value="announced_at:desc">{t('Terbaru diumumkan')}</option>
            <option value="bid_deadline:asc">{t('Deadline terdekat')}</option>
            <option value="relevance_score:desc">{t('Skor relevansi tertinggi')}</option>
            <option value="hps:desc">{t('HPS terbesar')}</option>
            <option value="first_seen_at:desc">{t('Baru ditemukan')}</option>
          </select>
          <button className="btn" type="submit">{t('Cari')}</button>
          <button className="btn ghost" type="button" onClick={() => { setQInput(''); setFilters(EMPTY); setPage(1) }}>{t('Reset')}</button>
        </form>

        {error && <ErrorBox message={error} />}
        {loading && !data && <Loading />}

        {data && items.length === 0 && <Empty text="Belum ada tender yang cocok. Jalankan pencarian manual di atas." />}

        {items.length > 0 && (
          <div className="tblwrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t('Paket')}</th>
                  <th>{t('Instansi')}</th>
                  <th className="num">{t('HPS')}</th>
                  <th>{t('Deadline')}</th>
                  <th>{t('Prioritas')}</th>
                  <th className="num">{t('Skor')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const [cls, txt] = priorityChip(item.analysis?.priority)
                  return (
                    <tr key={item.id} onClick={() => nav(`/tenders/${item.id}`)} className="clickable">
                      <td>
                        <b>{item.package_name}</b>
                        {item.location && <span className="sub"> · {item.location}</span>}
                      </td>
                      <td>{item.agency || '—'}</td>
                      <td className="num">{rupiah(item.hps)}</td>
                      <td>{dateOnly(item.bid_deadline)}</td>
                      <td><span className={`chip ${cls}`}>{t(txt)}</span></td>
                      <td className="num">{item.analysis?.relevance_score ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {data && <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />}
        {data && data.total > 0 && (
          <p className="sub" style={{ marginTop: 8 }}>{t('Terakhir dimuat {waktu}', { waktu: dt(new Date().toISOString()) })}</p>
        )}
      </div>
    </div>
  )
}
