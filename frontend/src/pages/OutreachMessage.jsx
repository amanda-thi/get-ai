import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { Loading, ErrorBox, Empty } from '../components/States'
import { EMAIL_TYPES, LANGUAGES, dt, emailTypeLabel, languageLabel, messageChip } from '../lib/format'

const EVENT_LABEL = {
  created: 'Dibuat',
  edited: 'Diubah',
  approved: 'Disetujui',
  sent: 'Terkirim',
  failed: 'Gagal kirim',
  delivered: 'Diterima',
  replied: 'Dibalas',
  follow_up_scheduled: 'Tindak lanjut dijadwalkan',
  note: 'Catatan',
}

export default function OutreachMessage() {
  const { id } = useParams()
  const nav = useNavigate()
  const { t } = useI18n()
  const { profile } = useAuth()
  const isAdmin = profile?.role === 'admin'

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [actionError, setActionError] = useState('')
  const [form, setForm] = useState({ subject: '', body: '', language: 'id', email_type: 'company_intro', recipient_email: '' })

  const load = useCallback(() => {
    setLoading(true)
    api(`/api/outreach/messages/${id}`)
      .then((d) => {
        setData(d); setError('')
        const m = d.message
        setForm({ subject: m.subject, body: m.body, language: m.language, email_type: m.email_type, recipient_email: m.recipient_email || '' })
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => { load() }, [load])

  const run = async (key, fn) => {
    setBusy(key); setActionError('')
    try { await fn(); load() } catch (e) { setActionError(e.message) } finally { setBusy('') }
  }

  const save = () => run('save', () => api(`/api/outreach/messages/${id}`, { method: 'PATCH', body: JSON.stringify(form) }))
  const approve = () => run('approve', () => api(`/api/outreach/messages/${id}/approve`, { method: 'POST' }))
  const send = () => run('send', () => api(`/api/outreach/messages/${id}/send`, { method: 'POST' }))
  const setStatus = (status) => run('status', () => api(`/api/outreach/messages/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) }))

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!data) return <Empty text="Email tidak ditemukan." />

  const m = data.message
  const [cls, txt] = messageChip(m.status)
  const locked = m.status === 'sent'

  return (
    <div className="stack">
      <div>
        <Link to="/outreach" className="backlink">{t('‹ Kembali ke daftar email')}</Link>
        <h1 style={{ margin: '6px 0 2px' }}>{m.subject}</h1>
        <p className="sub">{t(emailTypeLabel(m.email_type))} · {t(languageLabel(m.language))} · {t('dibuat {tanggal}', { tanggal: dt(m.created_at) })}</p>
      </div>

      <div className="toolbar">
        <span className={`chip ${cls}`}>{t(txt)}</span>
        {m.recipient_email && <span className="sub">→ {m.recipient_email}</span>}
      </div>

      {actionError && <ErrorBox message={actionError} />}

      {m.status === 'failed' && m.error && <div className="err">{t('Pengiriman gagal: {pesan}', { pesan: m.error })}</div>}
      {m.status === 'sent' && (
        <div className="notice">{t('Terkirim {tanggal}', { tanggal: dt(m.sent_at) })} · {t('ID pesan')} {m.provider_message_id || '—'}</div>
      )}
      {m.status === 'approved' && (
        <div className="notice">{t('Disetujui {tanggal}. Siap dikirim oleh admin.', { tanggal: dt(m.approved_at) })}</div>
      )}

      <div className="card">
        <h2>{t('Isi email')}</h2>
        {locked && <div className="sub" style={{ marginBottom: 10 }}>{t('Email sudah terkirim dan tidak dapat diubah.')}</div>}
        <div className="formgrid" style={{ marginTop: 10 }}>
          <label className="field">{t('Jenis')}
            <select value={form.email_type} disabled={locked} onChange={(e) => setForm({ ...form, email_type: e.target.value })}>
              {EMAIL_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
            </select>
          </label>
          <label className="field">{t('Bahasa')}
            <select value={form.language} disabled={locked} onChange={(e) => setForm({ ...form, language: e.target.value })}>
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
            </select>
          </label>
          <label className="field">{t('Email tujuan')}
            <input value={form.recipient_email} disabled={locked} onChange={(e) => setForm({ ...form, recipient_email: e.target.value })} />
          </label>
          <label className="field">{t('Subjek')}
            <input value={form.subject} disabled={locked} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
          </label>
          <label className="field">{t('Isi')}
            <textarea className="textarea" style={{ minHeight: 220 }} value={form.body} disabled={locked} onChange={(e) => setForm({ ...form, body: e.target.value })} />
          </label>
        </div>
        {!locked && (
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="btn" onClick={save} disabled={busy === 'save'}>{busy === 'save' ? t('Menyimpan…') : t('Simpan perubahan')}</button>
            {m.status !== 'approved' && <button className="btn ghost" onClick={() => setStatus('saved_for_later')} disabled={busy === 'status'}>{t('Simpan untuk nanti')}</button>}
          </div>
        )}
      </div>

      <div className="card">
        <h2>{t('Persetujuan & pengiriman')}</h2>
        <div className="sub" style={{ marginBottom: 12 }}>
          {t('Email hanya dapat dikirim setelah disetujui admin (aturan ini juga ditegakkan oleh database).')}
        </div>
        <div className="toolbar">
          {isAdmin && m.status !== 'sent' && m.status !== 'approved' && (
            <button className="btn" onClick={approve} disabled={busy === 'approve'}>{busy === 'approve' ? t('Menyetujui…') : t('Setujui')}</button>
          )}
          {isAdmin && m.status === 'approved' && (
            <button className="btn" onClick={send} disabled={busy === 'send'}>{busy === 'send' ? t('Mengirim…') : t('Kirim email')}</button>
          )}
          {!isAdmin && <span className="sub">{t('Hanya admin yang dapat menyetujui & mengirim email.')}</span>}
          {isAdmin && m.status === 'sent' && <span className="sub">{t('Sudah terkirim.')}</span>}
        </div>
      </div>

      <div className="card">
        <h2>{t('Riwayat')}</h2>
        {data.logs?.length === 0 && <Empty text="Belum ada riwayat." />}
        <div className="timeline">
          {data.logs?.map((l, i) => (
            <div key={l.id} className={`tl ${i === 0 ? 'first' : ''}`}>
              <time>{dt(l.created_at)}</time>
              <div><b>{t(EVENT_LABEL[l.event_type] || l.event_type)}</b>{l.details && Object.keys(l.details).length > 0 && <span className="sub"> · {JSON.stringify(l.details)}</span>}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="toolbar">
        <button className="btn ghost" onClick={() => nav('/outreach')}>{t('Kembali')}</button>
      </div>
    </div>
  )
}
