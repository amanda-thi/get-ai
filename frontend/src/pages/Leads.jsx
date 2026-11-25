import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Loading, ErrorBox, Empty } from '../components/States'
import Pagination from '../components/Pagination'
import { LEAD_STATUSES, dt, statusChip } from '../lib/format'

const EMPTY = { q: '', status: '', category: '', industry: '', province: '', sort: 'created_at', order: 'desc' }
const PER_PAGE = 5

function buildParams(filters, extra = {}) {
  const p = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => { if (v) p.set(k, v) })
  Object.entries(extra).forEach(([k, v]) => p.set(k, String(v)))
  return p.toString()
}

// Impor massal: satu perusahaan per baris, dipisah tanda "|":
// Nama | Website | Industri | Kota | email1;email2 | telepon1;telepon2
function parseImport(text) {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, website, industry, city, emails, phones] = line.split('|').map((s) => (s || '').trim())
      return {
        name,
        website: website || undefined,
        industry: industry || undefined,
        city: city || undefined,
        emails: emails ? emails.split(';').map((s) => s.trim()).filter(Boolean) : [],
        phones: phones ? phones.split(';').map((s) => s.trim()).filter(Boolean) : [],
      }
    })
    .filter((it) => it.name)
}

const splitList = (s) => s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean)

export default function Leads() {
  const nav = useNavigate()
  const { t } = useI18n()
  const [filters, setFilters] = useState(EMPTY)
  const [qInput, setQInput] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showDiscover, setShowDiscover] = useState(false)
  const [mode, setMode] = useState('manual')
  const [manual, setManual] = useState({ name: '', website: '', industry: '', city: '', province: '', description: '', emails: '', phones: '' })
  const [urls, setUrls] = useState('')
  const [importText, setImportText] = useState('')
  const [search, setSearch] = useState({ query: '', industry: '', location: '', limit: '10' })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [runError, setRunError] = useState('')

  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)
  const [analyzeError, setAnalyzeError] = useState('')

  const query = useMemo(() => buildParams(filters, { page, per_page: PER_PAGE }), [filters, page])

  const load = useCallback(() => {
    setLoading(true)
    api(`/api/leads?${query}`)
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [query])

  useEffect(() => { load() }, [load])

  const set = (patch) => { setFilters((f) => ({ ...f, ...patch })); setPage(1) }

  const runDiscover = async (body, ok) => {
    setBusy(true); setResult(null); setRunError('')
    try {
      const res = await api('/api/leads/discover', { method: 'POST', body: JSON.stringify(body) })
      setResult(res)
      if (ok) ok()
      load()
    } catch (e) { setRunError(e.message) } finally { setBusy(false) }
  }

  const submitManual = () => {
    if (!manual.name.trim()) { setRunError(t('Nama perusahaan wajib diisi.')); return }
    runDiscover({ items: [{ ...manual, emails: splitList(manual.emails), phones: splitList(manual.phones) }] },
      () => setManual({ name: '', website: '', industry: '', city: '', province: '', description: '', emails: '', phones: '' }))
  }

  const submitUrls = () => {
    const list = urls.split('\n').map((s) => s.trim()).filter(Boolean)
    if (!list.length) { setRunError(t('Masukkan minimal satu URL.')); return }
    runDiscover({ urls: list }, () => setUrls(''))
  }

  const submitImport = () => {
    const items = parseImport(importText)
    if (!items.length) { setRunError(t('Tidak ada baris valid untuk diimpor.')); return }
    runDiscover({ items }, () => setImportText(''))
  }

  const submitSearch = () => {
    if (!search.query.trim()) { setRunError(t('Kata kunci pencarian wajib diisi.')); return }
    runDiscover({
      query: search.query,
      industry: search.industry || undefined,
      location: search.location || undefined,
      limit: Number(search.limit) || 10,
    })
  }

  const runAnalyzePending = async () => {
    setAnalyzing(true); setAnalyzeResult(null); setAnalyzeError('')
    try {
      const res = await api('/api/leads/analyze-pending', { method: 'POST', body: JSON.stringify({ limit: 10 }) })
      setAnalyzeResult(res)
      load()
    } catch (e) { setAnalyzeError(e.message) } finally { setAnalyzing(false) }
  }

  const items = data?.items || []

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t('Company Leads')}</h1>
          <p className="sub">{t('Temukan calon pelanggan, kumpulkan info publik, dan nilai kecocokannya dengan AI.')}</p>
        </div>
        <div className="toolbar">
          <button className="btn ghost" onClick={runAnalyzePending} disabled={analyzing}>
            {analyzing ? t('Menganalisis…') : t('Kualifikasi massal (AI)')}
          </button>
          <button className="btn" onClick={() => setShowDiscover((v) => !v)}>{t('Tambah / cari perusahaan')}</button>
        </div>
      </div>

      {showDiscover && (
        <div className="card">
          <div className="tabs">
            {[['manual', 'Tambah manual'], ['url', 'Dari situs web'], ['import', 'Impor daftar'], ['search', 'Pencarian']].map(([v, label]) => (
              <button key={v} className={`tab ${mode === v ? 'on' : ''}`} onClick={() => { setMode(v); setRunError(''); setResult(null) }}>{t(label)}</button>
            ))}
          </div>

          {mode === 'manual' && (
            <div className="formgrid">
              <label className="field">{t('Nama perusahaan *')}<input value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} /></label>
              <label className="field">{t('Website')}<input value={manual.website} onChange={(e) => setManual({ ...manual, website: e.target.value })} placeholder="acme.co.id" /></label>
              <label className="field">{t('Industri')}<input value={manual.industry} onChange={(e) => setManual({ ...manual, industry: e.target.value })} placeholder={t('Pengelolaan sampah')} /></label>
              <label className="field">{t('Kota')}<input value={manual.city} onChange={(e) => setManual({ ...manual, city: e.target.value })} /></label>
              <label className="field">{t('Provinsi')}<input value={manual.province} onChange={(e) => setManual({ ...manual, province: e.target.value })} /></label>
              <label className="field">{t('Email (pisahkan koma)')}<input value={manual.emails} onChange={(e) => setManual({ ...manual, emails: e.target.value })} placeholder="info@acme.co.id" /></label>
              <label className="field">{t('Telepon (pisahkan koma)')}<input value={manual.phones} onChange={(e) => setManual({ ...manual, phones: e.target.value })} /></label>
              <label className="field">{t('Deskripsi')}<textarea className="textarea" value={manual.description} onChange={(e) => setManual({ ...manual, description: e.target.value })} /></label>
            </div>
          )}

          {mode === 'url' && (
            <div>
              <div className="sub" style={{ marginBottom: 8 }}>
                {t('Sistem membuka halaman publik (termasuk halaman kontak/tentang) dan mengambil email/telepon bisnis yang tertera. Menghormati robots.txt; tidak melewati login/CAPTCHA.')}
              </div>
              <textarea className="textarea" value={urls} onChange={(e) => setUrls(e.target.value)} placeholder={'acme.co.id\nhttps://perusahaan-lain.co.id'} />
            </div>
          )}

          {mode === 'import' && (
            <div>
              <div className="sub" style={{ marginBottom: 8 }}>
                {t('Satu perusahaan per baris, dipisah tanda')} <b>|</b>{t(': Nama | Website | Industri | Kota | email1;email2 | telepon1;telepon2')}
              </div>
              <textarea className="textarea" value={importText} onChange={(e) => setImportText(e.target.value)} placeholder="PT Contoh Jaya | contoh.co.id | Daur ulang | Bandung | info@contoh.co.id" />
            </div>
          )}

          {mode === 'search' && (
            <div>
              <div className="formgrid">
                <label className="field">{t('Kata kunci *')}<input value={search.query} onChange={(e) => setSearch({ ...search, query: e.target.value })} placeholder={t('pengelola sampah')} /></label>
                <label className="field">{t('Industri')}<input value={search.industry} onChange={(e) => setSearch({ ...search, industry: e.target.value })} /></label>
                <label className="field">{t('Lokasi')}<input value={search.location} onChange={(e) => setSearch({ ...search, location: e.target.value })} placeholder="Surabaya" /></label>
                <label className="field">{t('Jumlah hasil')}<input type="number" min="1" max="20" value={search.limit} onChange={(e) => setSearch({ ...search, limit: e.target.value })} /></label>
              </div>
            </div>
          )}

          <div className="toolbar" style={{ marginTop: 12 }}>
            {mode === 'manual' && <button className="btn" onClick={submitManual} disabled={busy}>{t('Simpan perusahaan')}</button>}
            {mode === 'url' && <button className="btn" onClick={submitUrls} disabled={busy}>{busy ? t('Mengambil…') : t('Kumpulkan dari situs')}</button>}
            {mode === 'import' && <button className="btn" onClick={submitImport} disabled={busy}>{t('Impor daftar')}</button>}
            {mode === 'search' && <button className="btn" onClick={submitSearch} disabled={busy}>{busy ? t('Mencari…') : t('Cari perusahaan')}</button>}
            {busy && <span className="sub">{t('Memproses…')}</span>}
          </div>

          {runError && <div className="err" style={{ marginTop: 12 }}>{runError}</div>}
          {result && (
            <div className="runresult">
              <b>{t('{n} perusahaan baru · {d} duplikat · {f} gagal', { n: result.created, d: result.duplicates, f: result.failed })}</b>
              <div className="sub">{t('Ditemukan {n} kandidat.', { n: result.found })}</div>
              {result.errors?.length > 0 && (
                <ul>{result.errors.map((e, i) => <li key={i}><span className="chip H">{t('gagal')}</span> {e.input}: {e.error}</li>)}</ul>
              )}
            </div>
          )}
        </div>
      )}

      {(analyzeResult || analyzeError) && (
        <div className="card">
          {analyzeError ? (
            <ErrorBox message={t('Kualifikasi massal gagal: {msg}', { msg: analyzeError })} />
          ) : (
            <>
              <b>{t('Kualifikasi massal: {ok} berhasil · {fail} gagal', { ok: analyzeResult.analyzed, fail: analyzeResult.failed })}</b>
              {analyzeResult.analyzed === 0 && analyzeResult.failed === 0 && (
                <div className="sub" style={{ marginTop: 6 }}>
                  {data?.total === 0
                    ? t('Belum ada perusahaan untuk dikualifikasi. Tambahkan perusahaan dulu lewat tombol “Tambah / cari perusahaan”.')
                    : t('Semua perusahaan sudah punya hasil kualifikasi terkini.')}
                </div>
              )}
              {analyzeResult.results?.filter((r) => r.status === 'error').map((r, i) => (
                <div key={i} className="sub">{t('Gagal: {msg}', { msg: r.error })}</div>
              ))}
            </>
          )}
        </div>
      )}

      <div className="card">
        <form className="toolbar filters" onSubmit={(e) => { e.preventDefault(); set({ q: qInput }) }}>
          <input className="search" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={t('Cari nama / deskripsi / website…')} />
          <select value={filters.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="">{t('Semua status')}</option>
            {LEAD_STATUSES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
          </select>
          <select value={filters.category} onChange={(e) => set({ category: e.target.value })}>
            <option value="">{t('Semua kategori')}</option>
            <option value="HIGH">{t('High')}</option>
            <option value="MEDIUM">{t('Medium')}</option>
            <option value="LOW">{t('Low')}</option>
          </select>
          <input value={filters.industry} onChange={(e) => set({ industry: e.target.value })} placeholder={t('Industri')} />
          <input value={filters.province} onChange={(e) => set({ province: e.target.value })} placeholder={t('Provinsi')} />
          <select value={`${filters.sort}:${filters.order}`} onChange={(e) => { const [sort, order] = e.target.value.split(':'); set({ sort, order }) }}>
            <option value="created_at:desc">{t('Terbaru ditambahkan')}</option>
            <option value="lead_score:desc">{t('Skor tertinggi')}</option>
            <option value="name:asc">{t('Nama A–Z')}</option>
          </select>
          <button className="btn" type="submit">{t('Cari')}</button>
          <button className="btn ghost" type="button" onClick={() => { setQInput(''); setFilters(EMPTY); setPage(1) }}>{t('Reset')}</button>
        </form>

        {error && <ErrorBox message={error} />}
        {loading && !data && <Loading />}
        {data && items.length === 0 && <Empty text="Belum ada perusahaan. Tambahkan manual atau kumpulkan dari situs web." />}

        {items.length > 0 && (
          <div className="tblwrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t('Perusahaan')}</th>
                  <th>{t('Industri')}</th>
                  <th>{t('Lokasi')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Kategori')}</th>
                  <th className="num">{t('Skor')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => {
                  const [cls, txt] = statusChip(c.lead?.status)
                  return (
                    <tr key={c.id} onClick={() => nav(`/leads/${c.id}`)} className="clickable">
                      <td>
                        <b>{c.name}</b>
                        {c.website && <span className="sub"> · {c.website.replace(/^https?:\/\//, '')}</span>}
                      </td>
                      <td>{c.industry || '—'}</td>
                      <td>{[c.city, c.province].filter(Boolean).join(', ') || '—'}</td>
                      <td><span className={`chip ${cls}`}>{t(txt)}</span></td>
                      <td>{c.analysis?.category ? <span className="chip OK">{c.analysis.category}</span> : <span className="sub">{t('belum dianalisis')}</span>}</td>
                      <td className="num">{c.analysis?.lead_score ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {data && <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />}
        {data && data.total > 0 && <p className="sub" style={{ marginTop: 8 }}>{t('Terakhir dimuat {waktu}', { waktu: dt(new Date().toISOString()) })}</p>}
      </div>
    </div>
  )
}
