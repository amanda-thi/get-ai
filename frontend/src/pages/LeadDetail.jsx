import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { Loading, ErrorBox, Empty } from '../components/States'
import { LEAD_STATUSES, dt, emailTypeLabel, languageLabel, messageChip, statusChip } from '../lib/format'

const KV = ({ label, children }) => (
  <div className="kv">
    <span className="sub">{label}</span>
    <b>{children ?? '—'}</b>
  </div>
)

function AnalysisCard({ a }) {
  const { t } = useI18n()
  if (!a) return null
  return (
    <div className="card">
      <div className="toolbar" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>{t('Kualifikasi AI')}</h2>
        <span className="chip OK">{a.category}</span>
      </div>
      <div className="sub" style={{ marginBottom: 12 }}>
        {t('Model')} {a.model} · {t('prompt')} {a.prompt_version} · {dt(a.created_at)}
      </div>
      <div className="scoreline">
        <div className="sc" style={{ width: '100%' }}>
          <b>{a.lead_score}/100</b>
          <div className="pg"><i style={{ width: `${a.lead_score}%` }} /></div>
        </div>
      </div>
      <div className="kvlist">
        <KV label={t('Klasifikasi industri')}>{a.industry_classification}</KV>
        <KV label={t('Alasan skor')}>{a.reason}</KV>
        <KV label={t('Saran pendekatan')}>{a.suggested_approach}</KV>
      </div>
      {a.potential_products?.length > 0 && (
        <div className="block">
          <h3>{t('Produk/layanan yang mungkin dibutuhkan')}</h3>
          <div className="toolbar">
            {a.potential_products.map((p, i) => <span key={i} className="chip OK">{p}</span>)}
          </div>
        </div>
      )}
    </div>
  )
}

export default function LeadDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const { profile } = useAuth()
  const { t } = useI18n()
  const isAdmin = profile?.role === 'admin'

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [actionError, setActionError] = useState('')

  const [statusForm, setStatusForm] = useState({ status: '', notes: '' })
  const [contactForm, setContactForm] = useState({ contact_type: 'email', value: '', source_url: '' })

  const load = useCallback(() => {
    setLoading(true)
    api(`/api/leads/${id}`)
      .then((d) => {
        setData(d); setError('')
        setStatusForm({ status: d.lead?.status || 'new', notes: d.lead?.notes || '' })
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => { load() }, [load])

  const run = async (key, fn) => {
    setBusy(key); setActionError('')
    try { await fn(); load() } catch (e) { setActionError(e.message) } finally { setBusy('') }
  }

  const saveStatus = () => run('status', () => api(`/api/leads/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: statusForm.status, notes: statusForm.notes }),
  }))

  const addContact = () => {
    if (!contactForm.value.trim()) { setActionError(t('Isi nilai kontak.')); return }
    run('contact', async () => {
      await api(`/api/leads/${id}/contacts`, { method: 'POST', body: JSON.stringify(contactForm) })
      setContactForm({ contact_type: 'email', value: '', source_url: '' })
    })
  }

  const deleteContact = (contactId) => run('del-' + contactId, () => api(`/api/leads/contacts/${contactId}`, { method: 'DELETE' }))

  const qualify = () => run('qualify', () => api(`/api/leads/${id}/qualify`, { method: 'POST' }))

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!data) return <Empty text="Perusahaan tidak ditemukan." />

  const c = data.company
  const lead = data.lead
  const [cls, txt] = statusChip(lead?.status)

  return (
    <div className="stack">
      <div>
        <Link to="/leads" className="backlink">‹ {t('Kembali ke daftar perusahaan')}</Link>
        <h1 style={{ margin: '6px 0 2px' }}>{c.name}</h1>
        <p className="sub">
          {c.website ? <a href={c.website} target="_blank" rel="noreferrer">{c.website}</a> : t('Website tidak tersedia')}
          {c.source_name ? ` · ${t('sumber')}: ${c.source_name}` : ''}
        </p>
      </div>

      <div className="toolbar">
        <span className={`chip ${cls}`}>{t(txt)}</span>
        <button className="btn" onClick={qualify} disabled={busy === 'qualify'}>
          {busy === 'qualify' ? t('Menganalisis…') : data.analysis ? t('Kualifikasi ulang (AI)') : t('Kualifikasi dengan AI')}
        </button>
        <button className="btn ghost" onClick={() => nav(`/outreach?lead_id=${lead?.id || ''}`)} disabled={!lead}>
          {t('Buat email outreach')}
        </button>
        {c.source_url && c.source_url !== 'manual' && <a className="btn ghost" href={c.source_url} target="_blank" rel="noreferrer">{t('Buka sumber')} ↗</a>}
      </div>
      {actionError && <ErrorBox message={actionError} />}

      <div className="card">
        <h2>{t('Data perusahaan')}</h2>
        <div className="sub" style={{ marginBottom: 12 }}>{t('Data mentah dari sumber publik, tidak diubah AI.')}</div>
        <div className="kvlist two">
          <KV label={t('Industri')}>{c.industry}</KV>
          <KV label={t('Kota')}>{c.city}</KV>
          <KV label={t('Provinsi')}>{c.province}</KV>
          <KV label={t('Alamat')}>{c.address}</KV>
          <KV label={t('Ditambahkan')}>{dt(c.created_at)}</KV>
        </div>
        {c.description && <div className="block"><h3>{t('Deskripsi')}</h3><p>{c.description}</p></div>}
      </div>

      <div className="card">
        <h2>{t('Status & catatan')}</h2>
        <div className="formgrid" style={{ marginTop: 10 }}>
          <label className="field">{t('Status')}
            <select value={statusForm.status} onChange={(e) => setStatusForm({ ...statusForm, status: e.target.value })}>
              {LEAD_STATUSES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
            </select>
          </label>
          <label className="field">{t('Catatan')}
            <textarea className="textarea" value={statusForm.notes} onChange={(e) => setStatusForm({ ...statusForm, notes: e.target.value })} />
          </label>
        </div>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button className="btn" onClick={saveStatus} disabled={busy === 'status'}>{busy === 'status' ? t('Menyimpan…') : t('Simpan')}</button>
        </div>
      </div>

      <div className="card">
        <h2>{t('Kontak bisnis publik')}</h2>
        <div className="sub" style={{ marginBottom: 10 }}>{t('Hanya kontak yang dipublikasikan perusahaan (wajib ada sumber).')}</div>
        {data.contacts.length === 0 && <Empty text="Belum ada kontak." />}
        {data.contacts.map((k) => (
          <div key={k.id} className="row">
            <span className={`chip ${k.contact_type === 'email' ? 'OK' : 'M'}`}>{k.contact_type}</span>
            <div className="t"><b>{k.value}</b><span className="sub">{t('sumber')}: {k.source_url}</span></div>
            <button className="linkbtn" onClick={() => deleteContact(k.id)} disabled={busy === 'del-' + k.id}>{t('Hapus')}</button>
          </div>
        ))}
        <div className="formgrid" style={{ marginTop: 12 }}>
          <label className="field">{t('Jenis')}
            <select value={contactForm.contact_type} onChange={(e) => setContactForm({ ...contactForm, contact_type: e.target.value })}>
              <option value="email">{t('Email')}</option>
              <option value="phone">{t('Telepon')}</option>
            </select>
          </label>
          <label className="field">{t('Nilai')}<input value={contactForm.value} onChange={(e) => setContactForm({ ...contactForm, value: e.target.value })} placeholder="info@acme.co.id" /></label>
          <label className="field">{t('Sumber (URL)')}<input value={contactForm.source_url} onChange={(e) => setContactForm({ ...contactForm, source_url: e.target.value })} placeholder="https://acme.co.id/kontak" /></label>
        </div>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button className="btn ghost" onClick={addContact} disabled={busy === 'contact'}>{t('Tambah kontak')}</button>
        </div>
      </div>

      {data.analysis ? <AnalysisCard a={data.analysis} /> : (
        <div className="card">
          <h2>{t('Kualifikasi AI')}</h2>
          <Empty text="Belum ada kualifikasi. Klik “Kualifikasi dengan AI” (butuh kunci AI di backend)." />
        </div>
      )}

      {data.analysis_history?.length > 1 && (
        <div className="card">
          <h2>{t('Riwayat kualifikasi')}</h2>
          {data.analysis_history.map((h) => (
            <div key={h.id} className="row">
              <div className="t"><b>{h.lead_score}/100 · {h.category}</b><span className="sub">{dt(h.created_at)} · {h.model}</span></div>
              {h.is_current && <span className="chip OK">{t('terkini')}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h2>{t('Email outreach')}</h2>
        {data.messages?.length === 0 && <Empty text="Belum ada email untuk perusahaan ini." />}
        {data.messages?.map((m) => {
          const [mcls, mtxt] = messageChip(m.status)
          return (
            <div key={m.id} className="row">
              <div className="t">
                <b>{m.subject}</b>
                <span className="sub">{t(emailTypeLabel(m.email_type))} · {t(languageLabel(m.language))} · {dt(m.created_at)}</span>
              </div>
              <span className={`chip ${mcls}`}>{t(mtxt)}</span>
              <button className="linkbtn" onClick={() => nav(`/outreach/${m.id}`)}>{t('Buka')}</button>
            </div>
          )
        })}
      </div>

      {isAdmin && (
        <details className="card">
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{t('Zona admin')}</summary>
          <div className="sub" style={{ margin: '10px 0' }}>{t('Menghapus perusahaan juga menghapus lead, kontak, dan riwayat kualifikasinya.')}</div>
          <button className="btn ghost" onClick={() => run('delete', async () => {
            await api(`/api/leads/${id}`, { method: 'DELETE' })
            nav('/leads')
          })} disabled={busy === 'delete'}>{t('Hapus perusahaan')}</button>
        </details>
      )}
    </div>
  )
}
