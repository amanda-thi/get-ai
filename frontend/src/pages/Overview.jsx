import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { locale } from '../lib/format'
import { Loading, ErrorBox, Empty } from '../components/States'
import Icon from '../components/Icon'

const TZ = 'Asia/Jakarta'
const dt = (d, opt) => (d ? new Date(d).toLocaleString(locale(), { timeZone: TZ, ...opt }) : 'Belum pernah')
const PRIO = { HIGH: ['H', 'High'], MEDIUM: ['M', 'Medium'], LOW: ['L', 'Low'] }
const SRC = { ok: ['OK', 'Aktif'], untested: ['L', 'Belum diuji'], failed: ['H', 'Gagal'], blocked: ['M', 'Diblokir'], manual_only: ['M', 'Manual'] }
const RUN = {
  completed: ['OK', 'Selesai'], success: ['OK', 'Sukses'],
  partially_completed: ['M', 'Sebagian'], partial: ['M', 'Sebagian'],
  failed: ['H', 'Gagal'], cancelled: ['L', 'Dibatalkan'], running: ['L', 'Berjalan'],
}
const OUT = [['draft', 'Email draft'], ['approved', 'Disetujui'], ['sent', 'Terkirim'], ['failed', 'Gagal kirim']]

function greeting() {
  const h = Number(new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: TZ })) % 24
  return h < 11 ? 'Selamat pagi' : h < 15 ? 'Selamat siang' : h < 18 ? 'Selamat sore' : 'Selamat malam'
}

const Stat = ({ color, icon, label, value }) => {
  const { t } = useI18n()
  return (
    <div className="stat">
      <span className="sq" style={{ background: color }}><Icon name={icon} /></span>
      <div><small>{t(label)}</small><b>{value}</b></div>
    </div>
  )
}

export default function Overview() {
  const { t } = useI18n()
  const { profile } = useAuth()
  const nav = useNavigate()
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api('/api/dashboard/overview').then(setD).catch((e) => setError(e.message)) }, [])

  if (error) return <ErrorBox message={error} />
  if (!d) return <Loading />

  const max = Math.max(...d.weekly_tenders.map((w) => w.count), 0)
  const weekTotal = d.weekly_tenders.reduce((a, w) => a + w.count, 0)

  return (
    <div className="dgrid">
      <div className="card c4">
        <h2>{t(greeting())}, {profile?.full_name || t('Admin')}</h2>
        <div className="sub">{t('Tender dengan deadline terdekat')}</div>
        <div className="big">{t('{n} tender', { n: d.tenders_deadline_7d })}</div>
        <div className="sub" style={{ marginBottom: 14 }}>{t('berakhir dalam 7 hari')}</div>
        <button className="btn" onClick={() => nav('/tenders')}>{t('Lihat tender')}</button>
      </div>

      <div className="card c8">
        <h2>{t('Ringkasan')}</h2>
        <div className="sub">{t('Dihitung langsung dari database')}</div>
        <div className="stats">
          <Stat color="var(--primary)" icon="doc" label="Tender ditemukan" value={d.tenders_total} />
          <Stat color="var(--red)" icon="target" label="Prioritas tinggi" value={d.tenders_high_priority} />
          <Stat color="var(--teal)" icon="users" label="Calon pelanggan" value={d.companies_total} />
          <Stat color="var(--green)" icon="star" label="High potential" value={d.leads_high_potential} />
        </div>
      </div>

      <div className="card c5">
        <h2>{t('Tender baru per hari')}</h2>
        <div className="sub">{t('7 hari terakhir')}</div>
        <div className="chart">
          {d.weekly_tenders.map((w) => (
            <div key={w.date} className={`bar ${w.count > 0 && w.count === max ? 'hi' : ''}`} style={{ height: `${max ? (w.count / max) * 100 : 0}%` }}>
              <span>{w.count}</span>
            </div>
          ))}
        </div>
        <div className="days">{d.weekly_tenders.map((w) => <span key={w.date}>{t(dt(w.date + 'T12:00:00Z', { weekday: 'short' }))}</span>)}</div>
        {weekTotal === 0 && <p className="sub" style={{ marginTop: 10 }}>{t('Belum ada tender masuk minggu ini.')}</p>}
      </div>

      <div className="card c7">
        <h2>{t('Tender prioritas')}</h2>
        <div className="sub" style={{ marginBottom: 8 }}>{t('Skor relevansi dari AI, perlu diverifikasi admin')}</div>
        {d.top_tenders.length === 0 ? <Empty text="Belum ada tender yang dianalisis." /> : d.top_tenders.map((it, i) => {
          const [cls, txt] = PRIO[it.priority]
          return (
            <div key={i} className={`row ${i === 0 ? 'first' : ''}`}>
              <div className="t"><b>{it.tenders?.package_name}</b><span className="sub">{it.tenders?.agency || t('Tidak tersedia')}</span></div>
              <span className={`chip ${cls}`}>{t(txt)}</span>
              <div className="sc"><b>{it.relevance_score}/100</b><div className="pg"><i style={{ width: `${it.relevance_score}%` }} /></div></div>
            </div>
          )
        })}
      </div>

      {OUT.map(([k, label]) => (
        <div key={k} className="card c3 mini"><div className="sub">{t(label)}</div><b>{d.outreach[k]}</b></div>
      ))}

      <div className="card c6">
        <h2>{t('Status sumber tender')}</h2>
        <div className="sub" style={{ marginBottom: 8 }}>{t('Gagal akses dicatat, tidak dianggap berhasil')}</div>
        {d.sources.length === 0 ? <Empty text="Belum ada sumber." /> : d.sources.map((s, i) => {
          const [cls, txt] = SRC[s.health_status] || SRC.untested
          return (
            <div key={s.name} className={`row ${i === 0 ? 'first' : ''}`}>
              <div className="t"><b>{s.name}</b><span className="sub">{t('Cek terakhir:')} {t(dt(s.last_checked_at))}</span></div>
              <span className={`chip ${cls}`}>{t(txt)}</span>
            </div>
          )
        })}
      </div>

      <div className="card c6">
        <h2>{t('Aktivitas terbaru')}</h2>
        <div className="sub" style={{ marginBottom: 8 }}>{t('Dari log sistem')}</div>
        {d.recent_activity.length === 0 ? <Empty text="Belum ada aktivitas." /> : d.recent_activity.map((l, i) => (
          <div key={i} className={`log ${i === 0 ? 'first' : ''}`}><time>{t(dt(l.created_at, { dateStyle: 'short', timeStyle: 'short' }))}</time>[{l.level}] {l.component}: {l.message}</div>
        ))}
      </div>

      <div className="card c12">
        <h2>{t('Jadwal automation')}</h2>
        <div className="sub" style={{ marginBottom: 8 }}>{t('Dijadwalkan oleh scheduler Fase 4 (zona Asia/Jakarta). Ubah jadwal di halaman Automation.')}</div>
        {d.automation.length === 0 ? <Empty text="Belum ada jadwal." /> : d.automation.map((a, i) => {
          const [cls, txt] = a.last_status ? RUN[a.last_status] : ['L', 'Belum berjalan']
          return (
            <div key={a.job_type} className={`row ${i === 0 ? 'first' : ''}`}>
              <div className="t"><b>{a.job_type}</b><span className="sub">{a.cron_expression} ({a.timezone}) · {a.is_active ? t('aktif') : t('nonaktif')} · {t('berikutnya:')} {t(dt(a.next_run_at))} · {t('run terakhir:')} {t(dt(a.last_run_at))}</span></div>
              <span className={`chip ${cls}`}>{t(txt)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
