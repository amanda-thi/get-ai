import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { Empty, ErrorBox, Loading } from '../components/States'
import Pagination from '../components/Pagination'
import Modal, { ConfirmDialog } from '../components/Modal'
import Icon from '../components/Icon'
import {
  AUTOMATION_TYPES, JOB_STATUSES, SCHEDULE_TYPES, TRIGGER_TYPES, WEEKDAYS,
  automationTypeLabel, dt, duration, jobStatusChip, triggerLabel,
} from '../lib/format'

const PER_PAGE = 20

// Petunjuk parameter per tipe automation (dipakai di editor lanjutan).
const PARAM_HINTS = {
  tender_monitoring: 'analyze_limit (int), deadline_days (int)',
  company_discovery: 'queries (array), locations (array), industries (array), limit (int)',
  lead_qualification: 'limit (int)',
  outreach_draft_generation: 'limit (int), email_type, language, priorities (array), min_score (int)',
}

function buildQuery(filters, extra = {}) {
  const p = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => { if (v) p.set(k, v) })
  Object.entries(extra).forEach(([k, v]) => p.set(k, String(v)))
  return p.toString()
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

function Capabilities({ capabilities }) {
  const { t } = useI18n()
  if (!capabilities) return null
  const items = [
    ['AI (analisis & draft)', capabilities.ai],
    ['Pencarian lead (Tavily/Serper)', capabilities.lead_search],
    ['INAPROC (API key)', capabilities.inaproc],
    ['SMTP (kirim email)', capabilities.smtp],
  ]
  return (
    <div className="notice">
      <b>{t('Kesiapan integrasi:')}</b>{' '}
      {items.map(([label, ok], i) => (
        <span key={label}>
          {i > 0 && ' · '}
          <span className={`chip ${ok ? 'OK' : 'M'}`}>{t(label)}</span>
        </span>
      ))}
      <div className="sub" style={{ marginTop: 6 }}>
        {t('Fitur yang butuh kunci hanya aktif bila kuncinya diisi di')} <code>.env</code>{' '}
        {t('backend. Tanpa kunci, job akan ditandai gagal dengan pesan jelas — bukan dianggap sukses.')}
      </div>
    </div>
  )
}

// --- Ringkasan ---

function OverviewTab({ data, isAdmin, onRun, onOpenJob }) {
  const { t } = useI18n()
  if (!data) return <Loading />
  const totals = data.totals || {}
  const stats = [
    ['var(--primary)', 'doc', 'Total job', totals.total ?? 0],
    ['var(--primary2)', 'clock', 'Berjalan', totals.running ?? 0],
    ['var(--green)', 'check', 'Selesai', totals.completed ?? 0],
    ['#e0a800', 'alert', 'Selesai sebagian', totals.partial ?? 0],
    ['var(--red)', 'alert', 'Gagal', totals.failed ?? 0],
    ['#9aa7b2', 'x', 'Dibatalkan', totals.cancelled ?? 0],
    ['var(--teal)', 'clock', 'Menunggu', totals.pending ?? 0],
    ['var(--primary)', 'clock', 'Rata-rata durasi', duration(data.avg_duration_seconds)],
  ]
  return (
    <>
      <div className="card">
        <h2>{t('Ringkasan eksekusi')}</h2>
        <div className="sub">{t('Dihitung dari riwayat job automation (300 terbaru).')}</div>
        <div className="stats">{stats.map(([c, i, l, v]) => <Stat key={l} color={c} icon={i} label={l} value={v} />)}</div>
      </div>

      <div className="card">
        <h2>{t('Jadwal berikutnya')}</h2>
        <div className="sub" style={{ marginBottom: 8 }}>{t('Waktu dalam zona Asia/Jakarta.')}</div>
        {(data.upcoming || []).length === 0 && <Empty text="Belum ada jadwal aktif." />}
        {(data.upcoming || []).map((u, i) => (
          <div key={u.id} className={`row ${i === 0 ? 'first' : ''}`}>
            <div className="t">
              <b>{u.automation_name}</b>
              <span className="sub">{u.schedule_description} · {t('berikutnya')} {dt(u.next_run_at)}</span>
            </div>
            {isAdmin && (
              <button className="btn ghost" onClick={() => onRun(u.id)}>{t('Jalankan')}</button>
            )}
          </div>
        ))}
      </div>

      <div className="card">
        <h2>{t('Job terakhir')}</h2>
        <div className="sub" style={{ marginBottom: 8 }}>{t('Klik baris untuk melihat detail & log.')}</div>
        {(data.recent_jobs || []).length === 0 && <Empty text="Belum ada job dijalankan." />}
        {(data.recent_jobs || []).length > 0 && (
          <div className="tblwrap">
            <table className="tbl">
              <thead>
                <tr><th>{t('Status')}</th><th>{t('Tipe')}</th><th>{t('Pemicu')}</th><th>{t('Hasil')}</th><th>{t('Durasi')}</th><th>{t('Waktu')}</th></tr>
              </thead>
              <tbody>
                {data.recent_jobs.map((j) => {
                  const [cls, txt] = jobStatusChip(j.status)
                  return (
                    <tr key={j.id} className="clickable" onClick={() => onOpenJob(j.id)}>
                      <td><span className={`chip ${cls}`}>{t(txt)}</span></td>
                      <td>{t(automationTypeLabel(j.job_type))}</td>
                      <td>{t(triggerLabel(j.trigger_type))}</td>
                      <td>{j.total_processed || 0} {t('diproses')} / {j.failed_count || 0} {t('gagal')}</td>
                      <td>{duration(j.duration_seconds)}</td>
                      <td>{dt(j.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

// --- Konfigurasi ---

function ConfigsTab({ configs, capabilities, isAdmin, onEdit, onToggle, onRun, busyId }) {
  const { t } = useI18n()
  if (!configs) return <Loading />
  return (
    <>
      <Capabilities capabilities={capabilities} />
      {configs.length === 0 && <div className="card"><Empty text="Belum ada konfigurasi automation. Jalankan migrasi Fase 4 (010)." /></div>}
      {configs.map((c) => {
        const [cls, txt] = c.last_status ? jobStatusChip(c.last_status) : ['L', 'Belum berjalan']
        const busy = busyId === c.id
        return (
          <div key={c.id} className="card">
            <div className="toolbar" style={{ justifyContent: 'space-between' }}>
              <div>
                <h2 style={{ margin: 0 }}>{c.automation_name}</h2>
                <div className="sub">{t(automationTypeLabel(c.automation_type))}</div>
              </div>
              <span className={`chip ${c.is_enabled ? 'OK' : 'L'}`}>{c.is_enabled ? t('aktif') : t('nonaktif')}</span>
            </div>

            <div className="kvlist two" style={{ marginTop: 12 }}>
              <div className="kv"><small className="sub">{t('Jadwal')}</small><b>{c.schedule_description}</b></div>
              <div className="kv"><small className="sub">{t('Jalannya berikutnya')}</small><b>{dt(c.next_run_at)}</b></div>
              <div className="kv"><small className="sub">{t('Jalan terakhir')}</small><b>{dt(c.last_run_at)}</b></div>
              <div className="kv">
                <small className="sub">{t('Status terakhir')}</small>
                <span><span className={`chip ${cls}`}>{t(txt)}</span></span>
              </div>
              <div className="kv"><small className="sub">{t('Retry / timeout')}</small><b>{c.retry_max_attempts}× ({t('jeda')} {c.retry_backoff_seconds}s) · {c.timeout_seconds}s</b></div>
            </div>

            {!c.requirements_ready && (
              <div className="notice warn" style={{ marginTop: 12 }}>
                {t('Butuh:')} {(c.requires || []).join(', ')}. {t('Kunci/konfigurasi terkait belum lengkap di backend — job akan gagal dengan pesan jelas sampai dilengkapi.')}
              </div>
            )}

            {isAdmin && (
              <div className="toolbar" style={{ marginTop: 14 }}>
                <button className="btn" disabled={busy} onClick={() => onRun(c.id)}>{t('Jalankan sekarang')}</button>
                <button className="btn ghost" disabled={busy} onClick={() => onEdit(c)}>{t('Ubah jadwal')}</button>
                <button className="btn ghost" disabled={busy} onClick={() => onToggle(c)}>
                  {c.is_enabled ? t('Nonaktifkan') : t('Aktifkan')}
                </button>
              </div>
            )}
          </div>
        )
      })}
    </>
  )
}

// --- Riwayat job ---

function JobsTab({ data, loading, error, filters, setFilters, page, setPage, onOpen }) {
  const { t } = useI18n()
  const items = data?.items || []
  const set = (patch) => { setFilters((f) => ({ ...f, ...patch })); setPage(1) }
  return (
    <div className="card">
      <h2>{t('Riwayat job')}</h2>
      <form className="toolbar filters" onSubmit={(e) => e.preventDefault()}>
        <select value={filters.job_type} onChange={(e) => set({ job_type: e.target.value })}>
          <option value="">{t('Semua tipe')}</option>
          {AUTOMATION_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
        </select>
        <select value={filters.status} onChange={(e) => set({ status: e.target.value })}>
          <option value="">{t('Semua status')}</option>
          {JOB_STATUSES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
        </select>
        <select value={filters.trigger_type} onChange={(e) => set({ trigger_type: e.target.value })}>
          <option value="">{t('Semua pemicu')}</option>
          {TRIGGER_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
        </select>
        <label className="field" style={{ gap: 2 }}>{t('Dari')}
          <input type="date" value={filters.date_from} onChange={(e) => set({ date_from: e.target.value })} />
        </label>
        <label className="field" style={{ gap: 2 }}>{t('Sampai')}
          <input type="date" value={filters.date_to} onChange={(e) => set({ date_to: e.target.value })} />
        </label>
        <button className="btn ghost" type="button" onClick={() => { setFilters({ job_type: '', status: '', trigger_type: '', date_from: '', date_to: '' }); setPage(1) }}>{t('Reset')}</button>
      </form>

      {error && <ErrorBox message={error} />}
      {loading && !data && <Loading />}
      {data && items.length === 0 && <Empty text="Belum ada job sesuai filter." />}

      {items.length > 0 && (
        <div className="tblwrap">
          <table className="tbl">
            <thead>
              <tr><th>{t('Status')}</th><th>{t('Tipe')}</th><th>{t('Pemicu')}</th><th>{t('Percobaan')}</th><th>{t('Hasil')}</th><th>{t('Durasi')}</th><th>{t('Dibuat')}</th></tr>
            </thead>
            <tbody>
              {items.map((j) => {
                const [cls, txt] = jobStatusChip(j.status)
                return (
                  <tr key={j.id} className="clickable" onClick={() => onOpen(j.id)}>
                    <td><span className={`chip ${cls}`}>{t(txt)}</span></td>
                    <td>{t(automationTypeLabel(j.job_type))}</td>
                    <td>{t(triggerLabel(j.trigger_type))}</td>
                    <td>{j.attempt}/{j.max_attempts}</td>
                    <td>{j.total_processed || 0} {t('diproses')} / {j.failed_count || 0} {t('gagal')}</td>
                    <td>{duration(j.duration_seconds)}</td>
                    <td>{dt(j.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />}
    </div>
  )
}

// --- Detail job ---

function JobDetailModal({ jobId, isAdmin, onClose, onChanged }) {
  const { t } = useI18n()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(() => {
    api(`/api/automation/jobs/${jobId}`).then((d) => { setData(d); setError('') }).catch((e) => setError(e.message))
  }, [jobId])
  useEffect(() => { load() }, [load])

  const act = async (kind) => {
    setBusy(kind); setError('')
    try {
      if (kind === 'retry') await api(`/api/automation/jobs/${jobId}/retry`, { method: 'POST' })
      if (kind === 'cancel') await api(`/api/automation/jobs/${jobId}/cancel`, { method: 'POST' })
      setConfirm(null)
      onChanged()
      load()
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const job = data?.job
  const [cls, txt] = job ? jobStatusChip(job.status) : ['L', '—']
  const canRetry = job && ['failed', 'partially_completed', 'cancelled'].includes(job.status)
  const canCancel = job && ['pending', 'queued', 'running'].includes(job.status)

  return (
    <Modal title="Detail job" onClose={onClose} wide
      footer={<button className="btn ghost" onClick={onClose}>{t('Tutup')}</button>}>
      {error && <ErrorBox message={error} />}
      {!job && !error && <Loading />}
      {job && (
        <>
          <div className="kvlist two">
            <div className="kv"><small className="sub">{t('Tipe')}</small><b>{t(automationTypeLabel(job.job_type))}</b></div>
            <div className="kv"><small className="sub">{t('Status')}</small><span><span className={`chip ${cls}`}>{t(txt)}</span></span></div>
            <div className="kv"><small className="sub">{t('Pemicu')}</small><b>{t(triggerLabel(job.trigger_type))}</b></div>
            <div className="kv"><small className="sub">{t('Percobaan')}</small><b>{job.attempt}/{job.max_attempts}</b></div>
            <div className="kv"><small className="sub">{t('Mulai')}</small><b>{dt(job.started_at)}</b></div>
            <div className="kv"><small className="sub">{t('Selesai')}</small><b>{dt(job.completed_at)}</b></div>
            <div className="kv"><small className="sub">{t('Durasi')}</small><b>{duration(job.duration_seconds)}</b></div>
            <div className="kv"><small className="sub">{t('Diproses / sukses / gagal')}</small><b>{job.total_processed || 0} / {job.success_count || 0} / {job.failed_count || 0}</b></div>
          </div>

          <div className="block">
            <h3>{t('Progres')}</h3>
            <div className="pg"><i style={{ width: `${job.progress || 0}%` }} /></div>
            <small className="sub">{job.progress || 0}%</small>
          </div>

          {job.error_message && (
            <div className="notice warn" style={{ marginTop: 12 }}><b>{t('Pesan:')}</b> {job.error_message}</div>
          )}

          {(data.retries || []).length > 0 && (
            <div className="block">
              <h3>{t('Percobaan lanjutan')}</h3>
              {(data.retries || []).map((r) => {
                const [rc, rt] = jobStatusChip(r.status)
                return (
                  <div key={r.id} className="row">
                    <div className="t"><b>{t('Percobaan')} {r.attempt}</b><span className="sub">{dt(r.created_at)}</span></div>
                    <span className={`chip ${rc}`}>{t(rt)}</span>
                  </div>
                )
              })}
            </div>
          )}

          <div className="block">
            <h3>{t('Log')}</h3>
            {(data.logs || []).length === 0 && <Empty text="Belum ada log." />}
            {(data.logs || []).length > 0 && (
              <div className="timeline">
                {(data.logs || []).map((l, i) => (
                  <div key={l.id || i} className={`tl ${i === 0 ? 'first' : ''}`}>
                    <time>{dt(l.created_at, { dateStyle: 'short', timeStyle: 'medium' })}</time>
                    <span className={`chip ${l.log_level === 'error' ? 'H' : l.log_level === 'warning' ? 'M' : 'L'}`}>{l.log_level}</span>
                    <span style={{ flex: 1 }}>{l.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {isAdmin && (canRetry || canCancel) && (
            <div className="toolbar" style={{ marginTop: 16 }}>
              {canRetry && <button className="btn" disabled={!!busy} onClick={() => setConfirm('retry')}>{t('Jalankan ulang')}</button>}
              {canCancel && <button className="btn danger" disabled={!!busy} onClick={() => setConfirm('cancel')}>{t('Batalkan')}</button>}
            </div>
          )}

          {confirm === 'retry' && (
            <ConfirmDialog
              title="Jalankan ulang job?"
              message="Job baru akan dibuat untuk automation ini. Pastikan tidak ada job lain yang sedang berjalan."
              confirmLabel="Jalankan ulang"
              busy={busy === 'retry'}
              onConfirm={() => act('retry')}
              onClose={() => setConfirm(null)}
            />
          )}
          {confirm === 'cancel' && (
            <ConfirmDialog
              title="Batalkan job?"
              message={job.status === 'running'
                ? 'Job sedang berjalan. Pembatalan bersifat kooperatif: job berhenti pada titik pemeriksaan berikutnya.'
                : 'Job yang masih dalam antrean akan langsung dibatalkan.'}
              confirmLabel="Batalkan job"
              danger
              busy={busy === 'cancel'}
              onConfirm={() => act('cancel')}
              onClose={() => setConfirm(null)}
            />
          )}
        </>
      )}
    </Modal>
  )
}

// --- Editor jadwal ---

function initForm(config) {
  const sc = config.schedule_config || {}
  return {
    automation_name: config.automation_name || '',
    description: config.description || '',
    schedule_type: config.schedule_type || 'weekly',
    timezone: config.timezone || 'Asia/Jakarta',
    day_of_week: String(sc.day_of_week ?? 0),
    day: String(sc.day ?? 1),
    hour: String(sc.hour ?? 8),
    minute: String(sc.minute ?? 0),
    cron: sc.cron || '0 8 * * 1',
    retry_max_attempts: String(config.retry_max_attempts ?? 2),
    retry_backoff_seconds: String(config.retry_backoff_seconds ?? 60),
    timeout_seconds: String(config.timeout_seconds ?? 900),
    paramsText: JSON.stringify(config.params || {}, null, 2),
  }
}

function ScheduleEditor({ config, onClose, onSaved }) {
  const { t } = useI18n()
  const [form, setForm] = useState(() => initForm(config))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  const save = async () => {
    let params
    try {
      params = form.paramsText.trim() ? JSON.parse(form.paramsText) : {}
    } catch {
      setError(t('Parameter harus berupa JSON yang valid.'))
      return
    }
    const schedule_config =
      form.schedule_type === 'daily' ? { hour: Number(form.hour), minute: Number(form.minute) }
        : form.schedule_type === 'weekly' ? { day_of_week: Number(form.day_of_week), hour: Number(form.hour), minute: Number(form.minute) }
          : form.schedule_type === 'monthly' ? { day: Number(form.day), hour: Number(form.hour), minute: Number(form.minute) }
            : { cron: form.cron.trim() }

    const body = {
      automation_name: form.automation_name.trim(),
      description: form.description.trim(),
      schedule_type: form.schedule_type,
      schedule_config,
      timezone: form.timezone,
      params,
      retry_max_attempts: Number(form.retry_max_attempts),
      retry_backoff_seconds: Number(form.retry_backoff_seconds),
      timeout_seconds: Number(form.timeout_seconds),
    }
    if (!body.automation_name) { setError(t('Nama automation wajib diisi.')); return }

    setBusy(true); setError('')
    try {
      await api(`/api/automation/configs/${config.id}`, { method: 'PATCH', body: JSON.stringify(body) })
      onSaved()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const timeFields = (
    <>
      <label className="field">{t('Jam')}
        <input type="number" min="0" max="23" value={form.hour} onChange={(e) => set({ hour: e.target.value })} />
      </label>
      <label className="field">{t('Menit')}
        <input type="number" min="0" max="59" value={form.minute} onChange={(e) => set({ minute: e.target.value })} />
      </label>
    </>
  )

  return (
    <Modal title={t('Ubah jadwal — {name}', { name: config.automation_name })} onClose={onClose} wide
      footer={(
        <>
          <button className="btn ghost" onClick={onClose} disabled={busy}>{t('Batal')}</button>
          <button className="btn" onClick={save} disabled={busy}>{busy ? t('Menyimpan…') : t('Simpan')}</button>
        </>
      )}>
      {error && <ErrorBox message={error} />}
      <div className="formgrid">
        <label className="field">{t('Nama automation')}
          <input value={form.automation_name} onChange={(e) => set({ automation_name: e.target.value })} />
        </label>
        <label className="field">{t('Jenis jadwal')}
          <select value={form.schedule_type} onChange={(e) => set({ schedule_type: e.target.value })}>
            {SCHEDULE_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
          </select>
        </label>
        <label className="field">{t('Zona waktu')}
          <input value={form.timezone} onChange={(e) => set({ timezone: e.target.value })} />
        </label>

        {form.schedule_type === 'weekly' && (
          <label className="field">{t('Hari')}
            <select value={form.day_of_week} onChange={(e) => set({ day_of_week: e.target.value })}>
              {WEEKDAYS.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
            </select>
          </label>
        )}
        {form.schedule_type === 'monthly' && (
          <label className="field">{t('Tanggal (1–28)')}
            <input type="number" min="1" max="28" value={form.day} onChange={(e) => set({ day: e.target.value })} />
          </label>
        )}
        {form.schedule_type !== 'custom' && timeFields}
        {form.schedule_type === 'custom' && (
          <label className="field">{t('Cron (standar, 5 bagian)')}
            <input value={form.cron} onChange={(e) => set({ cron: e.target.value })} placeholder="0 8 * * 1" />
          </label>
        )}

        <label className="field">{t('Maks. percobaan ulang')}
          <input type="number" min="0" max="10" value={form.retry_max_attempts} onChange={(e) => set({ retry_max_attempts: e.target.value })} />
        </label>
        <label className="field">{t('Jeda awal retry (detik)')}
          <input type="number" min="5" max="86400" value={form.retry_backoff_seconds} onChange={(e) => set({ retry_backoff_seconds: e.target.value })} />
        </label>
        <label className="field">{t('Batas waktu job (detik)')}
          <input type="number" min="30" max="86400" value={form.timeout_seconds} onChange={(e) => set({ timeout_seconds: e.target.value })} />
        </label>
      </div>

      <div className="block">
        <h3>{t('Parameter')}</h3>
        <p className="sub">{t('Kunci yang dikenali:')} {PARAM_HINTS[config.automation_type] || '—'}</p>
        <textarea className="textarea" value={form.paramsText} onChange={(e) => set({ paramsText: e.target.value })} spellCheck={false} />
      </div>
    </Modal>
  )
}

// --- Halaman ---

export default function Automation() {
  const { t } = useI18n()
  const { profile } = useAuth()
  const isAdmin = profile?.role === 'admin'
  const [params, setParams] = useSearchParams()

  const [tab, setTab] = useState(params.get('tab') || 'overview')
  const [overview, setOverview] = useState(null)
  const [configs, setConfigs] = useState(null)
  const [capabilities, setCapabilities] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [flash, setFlash] = useState('')
  const [busyId, setBusyId] = useState('')
  const [confirm, setConfirm] = useState(null)
  const [editing, setEditing] = useState(null)
  const [openJob, setOpenJob] = useState(params.get('job') || '')
  const [jobsData, setJobsData] = useState(null)
  const [jobsLoading, setJobsLoading] = useState(false)
  const [jobsError, setJobsError] = useState('')
  const [filters, setFilters] = useState({ job_type: '', status: '', trigger_type: '', date_from: '', date_to: '' })
  const [page, setPage] = useState(1)

  const say = (msg) => { setFlash(msg); setTimeout(() => setFlash(''), 4000) }

  const loadOverview = useCallback(() => {
    api('/api/automation/overview').then(setOverview).catch((e) => setLoadError(e.message))
  }, [])
  const loadConfigs = useCallback(() => {
    api('/api/automation/configs')
      .then((d) => { setConfigs(d.items || []); setCapabilities(d.capabilities || null) })
      .catch((e) => setLoadError(e.message))
  }, [])

  const jobsQuery = useMemo(() => buildQuery(filters, { page, per_page: PER_PAGE }), [filters, page])
  const loadJobs = useCallback(() => {
    setJobsLoading(true)
    api(`/api/automation/jobs?${jobsQuery}`)
      .then((d) => { setJobsData(d); setJobsError('') })
      .catch((e) => setJobsError(e.message))
      .finally(() => setJobsLoading(false))
  }, [jobsQuery])

  useEffect(() => { loadOverview(); loadConfigs() }, [loadOverview, loadConfigs])
  useEffect(() => { if (tab === 'jobs') loadJobs() }, [tab, loadJobs])

  // Sinkronkan tab/job ke URL agar bisa ditautkan dari notifikasi.
  useEffect(() => {
    const next = new URLSearchParams()
    if (tab !== 'overview') next.set('tab', tab)
    if (openJob) next.set('job', openJob)
    if (next.toString() !== params.toString()) setParams(next, { replace: true })
  }, [tab, openJob, params, setParams])

  const refreshAll = () => { loadOverview(); loadConfigs(); if (tab === 'jobs') loadJobs() }

  const runNow = async (configId) => {
    setBusyId(configId)
    try {
      await api('/api/automation/jobs/run', { method: 'POST', body: JSON.stringify({ config_id: configId }) })
      say('Job dijalankan di latar belakang. Lihat tab Riwayat job untuk statusnya.')
      refreshAll()
    } catch (e) { setLoadError(e.message) } finally { setBusyId('') }
  }

  const toggle = async (c) => {
    setBusyId(c.id)
    try {
      await api(`/api/automation/configs/${c.id}/${c.is_enabled ? 'disable' : 'enable'}`, { method: 'POST' })
      say(c.is_enabled ? 'Automation dinonaktifkan.' : 'Automation diaktifkan.')
      loadConfigs()
    } catch (e) { setLoadError(e.message) } finally { setBusyId('') }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t('Automation')}</h1>
          <p className="sub">{t('Jadwal otomatis untuk pemantauan tender, penemuan perusahaan, kualifikasi lead, dan pembuatan draft outreach. Email tidak pernah dikirim otomatis.')}</p>
        </div>
      </div>

      {flash && <div className="notice">{t(flash)}</div>}
      {loadError && <ErrorBox message={loadError} />}

      <div className="tabs">
        {[['overview', 'Ringkasan'], ['configs', 'Konfigurasi'], ['jobs', 'Riwayat job']].map(([v, label]) => (
          <button key={v} className={`tab ${tab === v ? 'on' : ''}`} onClick={() => setTab(v)}>{t(label)}</button>
        ))}
      </div>

      {tab === 'overview' && (
        <OverviewTab data={overview} isAdmin={isAdmin} onRun={(id) => setConfirm({ kind: 'run', configId: id, name: (configs || []).find((c) => c.id === id)?.automation_name || '' })} onOpenJob={setOpenJob} />
      )}
      {tab === 'configs' && (
        <ConfigsTab
          configs={configs}
          capabilities={capabilities}
          isAdmin={isAdmin}
          busyId={busyId}
          onRun={(id) => setConfirm({ kind: 'run', configId: id, name: (configs || []).find((c) => c.id === id)?.automation_name || '' })}
          onEdit={(c) => setEditing(c)}
          onToggle={(c) => (c.is_enabled ? setConfirm({ kind: 'toggle', config: c }) : toggle(c))}
        />
      )}
      {tab === 'jobs' && (
        <JobsTab
          data={jobsData} loading={jobsLoading} error={jobsError}
          filters={filters} setFilters={setFilters} page={page} setPage={setPage}
          onOpen={setOpenJob}
        />
      )}

      {confirm?.kind === 'run' && (
        <ConfirmDialog
          title="Jalankan automation sekarang?"
          message={t('Job "{name}" akan dijalankan di latar belakang. Bila sudah ada job aktif untuk automation ini, permintaan akan ditolak (tidak ada duplikasi).', { name: confirm.name })}
          confirmLabel="Jalankan"
          busy={!!busyId}
          onConfirm={async () => { await runNow(confirm.configId); setConfirm(null) }}
          onClose={() => setConfirm(null)}
        />
      )}
      {confirm?.kind === 'toggle' && (
        <ConfirmDialog
          title="Nonaktifkan automation?"
          message={t('"{name}" tidak akan berjalan sesuai jadwal sampai diaktifkan kembali.', { name: confirm.config.automation_name })}
          confirmLabel="Nonaktifkan"
          danger
          busy={!!busyId}
          onConfirm={async () => { await toggle(confirm.config); setConfirm(null) }}
          onClose={() => setConfirm(null)}
        />
      )}

      {editing && (
        <ScheduleEditor
          config={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); say('Jadwal disimpan.'); loadConfigs() }}
        />
      )}
      {openJob && (
        <JobDetailModal
          jobId={openJob}
          isAdmin={isAdmin}
          onClose={() => setOpenJob('')}
          onChanged={() => { refreshAll(); say('Job baru dibuat.') }}
        />
      )}
    </div>
  )
}
