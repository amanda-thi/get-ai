import { useEffect, useState } from 'react'
import { api, apiDownload } from '../lib/api'
import { Loading, ErrorBox, Empty } from '../components/States'
import { useI18n } from '../lib/i18n'
import {
  TZ, dt, dateOnly, priorityChip, statusChip, messageChip,
  emailTypeLabel, jobStatusChip, duration, locale,
} from '../lib/format'

const PERIODS = [
  [7, '7 hari terakhir'],
  [30, '30 hari terakhir'],
  [90, '90 hari terakhir'],
]

// Ubah galat backend menjadi pesan yang bisa ditindaklanjuti.
function sectionError(section) {
  const e = section?.error || ''
  if (/PGRST205|42P01|schema cache/i.test(e)) {
    return 'Tabel untuk bagian ini belum ada. Jalankan migrasi terbaru di Supabase SQL Editor, lalu muat ulang halaman.'
  }
  return e || 'Data tidak tersedia.'
}

// Objek {kunci: jumlah} -> daftar terurut menurun.
const entries = (obj, limit = 6) =>
  Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).slice(0, limit)

function Breakdown({ items, label = (k) => k }) {
  const { t } = useI18n()
  if (!items.length) return <Empty text="Belum ada data." />
  const max = Math.max(0, ...items.map(([, v]) => v))
  return (
    <div>
      {items.map(([k, v], i) => (
        <div key={k} className={`row ${i === 0 ? 'first' : ''}`}>
          <div className="t"><b>{t(label(k))}</b></div>
          <div className="sc"><b>{v}</b><div className="pg"><i style={{ width: `${max ? (v / max) * 100 : 0}%` }} /></div></div>
        </div>
      ))}
    </div>
  )
}

function Trend({ title, points }) {
  const { t } = useI18n()
  const pts = (points || []).slice(-30)
  const max = Math.max(0, ...pts.map((p) => p.count))
  const total = (points || []).reduce((a, p) => a + p.count, 0)
  return (
    <div className="card c6">
      <h2>{t(title)}</h2>
      <div className="sub">{t('30 hari terakhir ditampilkan · total {total}', { total })}</div>
      <div className="chart">
        {pts.map((p) => (
          <div key={p.date} className={`bar ${max && p.count === max ? 'hi' : ''}`} style={{ height: `${max ? (p.count / max) * 100 : 0}%` }}>
            {p.count > 0 && <span>{p.count}</span>}
          </div>
        ))}
      </div>
      <div className="days">
        {pts.map((p) => (
          <span key={p.date}>{new Date(p.date + 'T12:00:00Z').toLocaleDateString(locale(), { timeZone: TZ, day: 'numeric' })}</span>
        ))}
      </div>
    </div>
  )
}

function Unavailable({ title, section }) {
  const { t } = useI18n()
  return (
    <div className="card c6">
      <h2>{t(title)}</h2>
      <div className="notice warn" style={{ marginTop: 12 }}>{t(sectionError(section))}</div>
    </div>
  )
}

export default function Reports() {
  const { t } = useI18n()
  const [days, setDays] = useState(30)
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(null)
  const [exportError, setExportError] = useState('')

  useEffect(() => {
    let alive = true
    setD(null)
    setError('')
    api(`/api/reports/summary?days=${days}`)
      .then((r) => { if (alive) setD(r) })
      .catch((e) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [days])

  async function download(kind) {
    setBusy(kind)
    setExportError('')
    try {
      await apiDownload(`/api/reports/export.${kind}?days=${days}`, `laporan-green-eco.${kind}`)
    } catch (e) {
      setExportError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const head = (
    <div className="page-head">
      <div>
        <h1>{t('Reports')}</h1>
        <p className="sub">{t('Ringkasan lintas modul, dihitung langsung dari database')}</p>
      </div>
      <div className="toolbar">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label={t('Periode laporan')}>
          {PERIODS.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
        </select>
        <button className="btn ghost" onClick={() => download('xlsx')} disabled={!!busy}>
          {busy === 'xlsx' ? t('Menyiapkan…') : t('Ekspor Excel')}
        </button>
        <button className="btn" onClick={() => download('pdf')} disabled={!!busy}>
          {busy === 'pdf' ? t('Menyiapkan…') : t('Ekspor PDF')}
        </button>
      </div>
    </div>
  )

  if (error) return <div className="stack">{head}<ErrorBox message={error} /></div>
  if (!d) return <div className="stack">{head}<Loading text="Menghitung laporan…" /></div>

  const { tenders: tn, leads: l, outreach: o, automation: a } = d

  return (
    <div className="stack">
      {head}
      {exportError && <ErrorBox message={exportError} />}
      <div className="notice">
        {t('Angka dihitung dari maksimum 5.000 baris terbaru per modul. Bagian yang tabelnya belum ada ditandai terpisah, tidak dianggap nol.')}
      </div>

      <div className="dgrid">
        {/* --- Ringkasan tender --- */}
        {tn.available === false ? <Unavailable title="Ringkasan Tender" section={tn} /> : (
          <div className="card c6">
            <h2>{t('Ringkasan Tender')}</h2>
            <div className="sub">{t('Prioritas AI, sumber, dan deadline')}</div>
            <div className="metrics">
              <div className="metric"><small>{t('Total tender')}</small><b>{tn.total}</b></div>
              <div className="metric"><small>{t('Prioritas tinggi')}</small><b>{tn.high_priority}</b></div>
              <div className="metric"><small>{t('Sudah dianalisis')}</small><b>{tn.analyzed}</b></div>
              <div className="metric"><small>{t('Deadline ≤ 7 hari')}</small><b>{tn.deadline_7d}</b></div>
            </div>
            <div className="sect">
              <h3>{t('Per prioritas')}</h3>
              <Breakdown items={entries(tn.by_priority)} label={(k) => priorityChip(k)[1]} />
            </div>
            <div className="sect">
              <h3>{t('Per sumber')}</h3>
              <Breakdown items={(tn.by_source || []).slice(0, 6).map((r) => [r.source, r.count])} />
            </div>
            <div className="sect">
              <h3>{t('Top tender (skor AI)')}</h3>
              {tn.top.length === 0 ? <Empty text="Belum ada tender teranalisis." /> : tn.top.slice(0, 5).map((x, i) => {
                const [cls, txt] = priorityChip(x.priority)
                return (
                  <div key={x.id} className={`row ${i === 0 ? 'first' : ''}`}>
                    <div className="t">
                      <b>{x.package_name}</b>
                      <span className="sub">{x.agency || t('Instansi tidak tersedia')} · {t('deadline')} {dateOnly(x.bid_deadline)}</span>
                    </div>
                    <span className={`chip ${cls}`}>{t(txt)}</span>
                    <div className="sc"><b>{x.relevance_score ?? '—'}/100</b><div className="pg"><i style={{ width: `${x.relevance_score || 0}%` }} /></div></div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* --- Ringkasan leads --- */}
        {l.available === false ? <Unavailable title="Ringkasan Leads" section={l} /> : (
          <div className="card c6">
            <h2>{t('Ringkasan Leads')}</h2>
            <div className="sub">{t('Status CRM, potensi, dan konversi')}</div>
            <div className="metrics">
              <div className="metric"><small>{t('Total perusahaan')}</small><b>{l.total}</b></div>
              <div className="metric"><small>{t('High potential')}</small><b>{l.high_potential}</b></div>
              <div className="metric"><small>{t('Sudah dikontak')}</small><b>{l.contacted}</b></div>
              <div className="metric"><small>{t('Tingkat konversi')}</small><b>{l.conversion_rate}%</b></div>
            </div>
            <div className="sect">
              <h3>{t('Per status CRM')}</h3>
              <Breakdown items={entries(l.by_status, 8)} label={(k) => statusChip(k)[1]} />
            </div>
            <div className="sect">
              <h3>{t('Top leads (skor AI)')}</h3>
              {l.top.length === 0 ? <Empty text="Belum ada lead teranalisis." /> : l.top.slice(0, 5).map((x, i) => {
                const [cls, txt] = statusChip(x.lead_status)
                return (
                  <div key={x.id} className={`row ${i === 0 ? 'first' : ''}`}>
                    <div className="t">
                      <b>{x.name}</b>
                      <span className="sub">{x.industry || t('Industri tidak tersedia')}{x.city ? ` · ${x.city}` : ''}</span>
                    </div>
                    <span className={`chip ${cls}`}>{t(txt)}</span>
                    <div className="sc"><b>{x.score ?? '—'}/100</b><div className="pg"><i style={{ width: `${x.score || 0}%` }} /></div></div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* --- Ringkasan outreach --- */}
        {o.available === false ? <Unavailable title="Ringkasan Outreach" section={o} /> : (
          <div className="card c6">
            <h2>{t('Ringkasan Outreach')}</h2>
            <div className="sub">{t('Draft, persetujuan, dan pengiriman')}</div>
            <div className="metrics">
              <div className="metric"><small>{t('Total pesan')}</small><b>{o.total}</b></div>
              <div className="metric"><small>{t('Menunggu persetujuan')}</small><b>{o.pending_approval}</b></div>
              <div className="metric"><small>{t('Terkirim')}</small><b>{o.sent}</b></div>
              <div className="metric"><small>{t('Gagal kirim')}</small><b>{o.failed}</b></div>
            </div>
            <div className="sect">
              <h3>{t('Per status')}</h3>
              <Breakdown items={entries(o.by_status)} label={(k) => messageChip(k)[1]} />
            </div>
            <div className="sect">
              <h3>{t('Per tipe email')}</h3>
              <Breakdown items={entries(o.by_email_type)} label={emailTypeLabel} />
            </div>
            <div className="sect">
              <h3>{t('Per kampanye')}</h3>
              <Breakdown items={(o.by_campaign || []).slice(0, 6).map((r) => [r.campaign, r.count])} />
            </div>
          </div>
        )}

        {/* --- Kinerja automation --- */}
        {a.available === false ? <Unavailable title="Kinerja Automation" section={a} /> : (
          <div className="card c6">
            <h2>{t('Kinerja Automation')}</h2>
            <div className="sub">{t('Dari riwayat job Fase 4')}</div>
            <div className="metrics">
              <div className="metric"><small>{t('Total job')}</small><b>{a.total_jobs}</b></div>
              <div className="metric"><small>{t('Tingkat sukses')}</small><b>{a.success_rate}%</b></div>
              <div className="metric"><small>{t('Durasi rata-rata')}</small><b>{duration(a.avg_duration_seconds)}</b></div>
              <div className="metric"><small>{t('Job gagal')}</small><b>{a.by_status?.failed ?? 0}</b></div>
            </div>
            <div className="sect">
              <h3>{t('Per automation')}</h3>
              {a.by_type.length === 0 ? <Empty text="Belum ada job dijalankan." /> : (
                <div className="tblwrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>{t('Automation')}</th>
                        <th className="num">{t('Total')}</th>
                        <th className="num">{t('Sukses')}</th>
                        <th className="num">{t('Sebagian')}</th>
                        <th className="num">{t('Gagal')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {a.by_type.map((r) => (
                        <tr key={r.type}>
                          <td>{r.name}</td>
                          <td className="num">{r.total}</td>
                          <td className="num">{r.completed}</td>
                          <td className="num">{r.partially_completed}</td>
                          <td className="num">{r.failed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {a.recent_failures.length > 0 && (
              <div className="sect">
                <h3>{t('Kegagalan terbaru')}</h3>
                {a.recent_failures.map((f, i) => (
                  <div key={f.id} className={`row ${i === 0 ? 'first' : ''}`}>
                    <div className="t"><b>{f.job_name}</b><span className="sub">{f.error_message || t('Tanpa pesan galat')} · {dt(f.created_at)}</span></div>
                    <span className="chip H">{t('Gagal')}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="sect">
              <h3>{t('Jadwal automation')}</h3>
              {a.configs.length === 0 ? <Empty text="Belum ada konfigurasi automation." /> : a.configs.map((c, i) => {
                const [cls, txt] = c.last_status ? jobStatusChip(c.last_status) : ['L', 'Belum berjalan']
                return (
                  <div key={c.id} className={`row ${i === 0 ? 'first' : ''}`}>
                    <div className="t">
                      <b>{c.automation_name}</b>
                      <span className="sub">{c.cron_expression} ({c.timezone}) · {c.is_enabled ? t('aktif') : t('nonaktif')} · {t('berikutnya')}: {dt(c.next_run_at)}</span>
                    </div>
                    <span className={`chip ${cls}`}>{t(txt)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* --- Tren --- */}
        {tn.available !== false && <Trend title="Tren tender baru" points={tn.trend} />}
        {l.available !== false && <Trend title="Tren leads baru" points={l.trend} />}
        {o.available !== false && <Trend title="Tren pesan outreach" points={o.trend} />}
        {a.available !== false && <Trend title="Tren job automation" points={a.trend} />}
      </div>
    </div>
  )
}
