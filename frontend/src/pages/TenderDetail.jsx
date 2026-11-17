import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Loading, ErrorBox, Empty } from '../components/States'
import { dateOnly, dt, priorityChip, rupiah } from '../lib/format'

const KV = ({ label, children }) => (
  <div className="kv">
    <span className="sub">{label}</span>
    <b>{children ?? '—'}</b>
  </div>
)

function AnalysisCard({ a }) {
  const { t } = useI18n()
  if (!a) return null
  const [cls, txt] = priorityChip(a.priority)
  return (
    <div className="card">
      <div className="toolbar" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>{t('Analisis AI')}</h2>
        <span className={`chip ${cls}`}>{t(txt)}</span>
      </div>
      <div className="sub" style={{ marginBottom: 12 }}>
        {t('Model')} {a.model} · {t('prompt')} {a.prompt_version} · {dt(a.created_at)}
        {a.verified_at ? ` · ${t('diverifikasi {waktu}', { waktu: dt(a.verified_at) })}` : ` · ${t('belum diverifikasi admin')}`}
      </div>
      <div className="scoreline">
        <div className="sc" style={{ width: '100%' }}>
          <b>{a.relevance_score}/100</b>
          <div className="pg"><i style={{ width: `${a.relevance_score}%` }} /></div>
        </div>
        {a.category && <span className="chip OK">{t(a.category)}</span>}
      </div>
      <div className="kvlist">
        <KV label={t('Alasan skor')}>{a.score_reason}</KV>
        <KV label={t('Kebutuhan peralatan')}>{a.equipment_needs}</KV>
        <KV label={t('Peluang kerja sama')}>{a.cooperation_opportunity}</KV>
        <KV label={t('Syarat penting')}>{a.key_requirements}</KV>
        <KV label={t('Catatan tenggat')}>{a.deadline_flag}</KV>
      </div>
    </div>
  )
}

export default function TenderDetail() {
  const { id } = useParams()
  const { t } = useI18n()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    api(`/api/tenders/${id}`)
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => { load() }, [load])

  const runAnalyze = async () => {
    setAnalyzing(true); setAnalyzeError('')
    try { await api(`/api/tenders/${id}/analyze`, { method: 'POST' }); load() }
    catch (e) { setAnalyzeError(e.message) } finally { setAnalyzing(false) }
  }

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!data) return <Empty text="Tender tidak ditemukan." />

  const tender = data.tender
  const a = data.analysis

  return (
    <div className="stack">
      <div>
        <Link to="/tenders" className="backlink">‹ {t('Kembali ke daftar tender')}</Link>
        <h1 style={{ margin: '6px 0 2px' }}>{tender.package_name}</h1>
        <p className="sub">{tender.agency || t('Instansi tidak tersedia')}{tender.external_id ? ` · ${t('Kode')} ${tender.external_id}` : ''}</p>
      </div>

      <div className="toolbar">
        <button className="btn" onClick={runAnalyze} disabled={analyzing}>
          {analyzing ? t('Menganalisis…') : a ? t('Analisis ulang dengan AI') : t('Analisis dengan AI')}
        </button>
        {tender.source_url && <a className="btn ghost" href={tender.source_url} target="_blank" rel="noreferrer">{t('Buka di sumber resmi ↗')}</a>}
      </div>
      {analyzeError && <ErrorBox message={analyzeError} />}

      <div className="card">
        <h2>{t('Data tender')}</h2>
        <div className="sub" style={{ marginBottom: 12 }}>{t('Data mentah dari sumber, tidak diubah AI.')}</div>
        <div className="kvlist two">
          <KV label={t('Instansi')}>{tender.agency}</KV>
          <KV label={t('Lokasi')}>{tender.location}</KV>
          <KV label={t('Jenis pengadaan')}>{tender.procurement_type}</KV>
          <KV label={t('Status / tahap')}>{tender.status}</KV>
          <KV label={t('Nilai HPS')}>{rupiah(tender.hps)}</KV>
          <KV label={t('Pagu')}>{rupiah(tender.budget_ceiling)}</KV>
          <KV label={t('Deadline penawaran')}>{tender.bid_deadline ? dt(tender.bid_deadline) : '—'}</KV>
          <KV label={t('Diumumkan')}>{dateOnly(tender.announced_at)}</KV>
          <KV label={t('Mulai pendaftaran')}>{tender.registration_start ? dt(tender.registration_start) : '—'}</KV>
          <KV label={t('Akhir pendaftaran')}>{tender.registration_end ? dt(tender.registration_end) : '—'}</KV>
          <KV label={t('Keyword cocok')}>{(tender.matched_keywords || []).join(', ') || '—'}</KV>
          <KV label={t('Pertama terlihat')}>{dt(tender.first_seen_at)}</KV>
        </div>
        {tender.description && <div className="block"><h3>{t('Uraian')}</h3><p>{tender.description}</p></div>}
        {tender.technical_specs && <div className="block"><h3>{t('Spesifikasi / metode')}</h3><p>{tender.technical_specs}</p></div>}
        {tender.participant_requirements && <div className="block"><h3>{t('Syarat kualifikasi')}</h3><p>{tender.participant_requirements}</p></div>}
      </div>

      {a ? <AnalysisCard a={a} /> : (
        <div className="card">
          <h2>{t('Analisis AI')}</h2>
          <Empty text="Belum ada analisis. Klik “Analisis dengan AI” (butuh kunci AI di backend)." />
        </div>
      )}

      {data.analysis_history?.length > 1 && (
        <div className="card">
          <h2>{t('Riwayat analisis')}</h2>
          <div className="sub" style={{ marginBottom: 8 }}>{t('Analisis lama tetap tersimpan.')}</div>
          {data.analysis_history.map((h) => {
            const [cls, txt] = priorityChip(h.priority)
            return (
              <div key={h.id} className="row">
                <div className="t"><b>{h.relevance_score}/100 · {t(h.category || 'Other')}</b><span className="sub">{dt(h.created_at)} · {h.model}</span></div>
                <span className={`chip ${cls}`}>{t(txt)}</span>
                {h.is_current && <span className="chip OK">{t('terkini')}</span>}
              </div>
            )
          })}
        </div>
      )}

      <details className="card">
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{t('Data mentah sumber (raw)')}</summary>
        <pre className="raw">{JSON.stringify(tender.raw_payload || {}, null, 2)}</pre>
      </details>
    </div>
  )
}
