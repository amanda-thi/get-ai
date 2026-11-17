export const TZ = 'Asia/Jakarta'

// Bahasa aktif untuk format tanggal & durasi. Diatur oleh <I18nProvider>
// (lib/i18n.jsx) saat render, sehingga pemanggil dt()/dateOnly()/duration()
// tidak perlu diubah.
let CURRENT_LANG = 'id'

export function setFormatLang(lang) {
  CURRENT_LANG = lang === 'ko' ? 'ko' : 'id'
}

export function locale() {
  return CURRENT_LANG === 'ko' ? 'ko-KR' : 'id-ID'
}

export function rupiah(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n)
}

export function dt(v, opts = { dateStyle: 'short', timeStyle: 'short' }) {
  return v ? new Date(v).toLocaleString(locale(), { timeZone: TZ, ...opts }) : '—'
}

export function dateOnly(v) {
  return v ? new Date(v).toLocaleDateString(locale(), { timeZone: TZ }) : '—'
}

export const PRIORITY = {
  HIGH: ['H', 'High'],
  MEDIUM: ['M', 'Medium'],
  LOW: ['L', 'Low'],
}

export function priorityChip(p) {
  return PRIORITY[p] || ['L', 'Belum dianalisis']
}

export const CATEGORIES = [
  'Waste Management',
  'Recycling Equipment',
  'Industrial Machinery',
  'Environmental Facilities',
  'Water Treatment',
  'Other',
]

// --- Fase 3: Company Leads & Marketing Outreach ---

// Status CRM di DB dipetakan ke label yang diminta spesifikasi.
// (negotiation -> "Interested", won -> "Converted", lost -> "Not Interested")
export const LEAD_STATUSES = [
  ['new', 'New'],
  ['qualified', 'Qualified'],
  ['contacted', 'Contacted'],
  ['responded', 'Responded'],
  ['negotiation', 'Interested'],
  ['won', 'Converted'],
  ['lost', 'Not Interested'],
  ['do_not_contact', 'Do Not Contact'],
]

const LEAD_STATUS_CHIP = {
  new: 'L',
  qualified: 'OK',
  contacted: 'M',
  responded: 'OK',
  negotiation: 'M',
  won: 'OK',
  lost: 'L',
  do_not_contact: 'H',
}

export function statusChip(status) {
  const label = LEAD_STATUSES.find(([v]) => v === status)?.[1]
  return [LEAD_STATUS_CHIP[status] || 'L', label || status || '—']
}

export const EMAIL_TYPES = [
  ['company_intro', 'Perkenalan perusahaan'],
  ['product_intro', 'Perkenalan produk'],
  ['partnership_proposal', 'Proposal kerja sama'],
  ['service_offering', 'Penawaran layanan'],
  ['follow_up', 'Tindak lanjut'],
]

export const LANGUAGES = [
  ['id', 'Bahasa Indonesia'],
  ['en', 'English'],
  ['ko', '한국어'],
]

const MESSAGE_STATUS_CHIP = {
  draft: 'L',
  saved_for_later: 'M',
  approved: 'OK',
  sent: 'OK',
  failed: 'H',
}

const MESSAGE_STATUS_LABEL = {
  draft: 'Draft',
  saved_for_later: 'Disimpan',
  approved: 'Disetujui',
  sent: 'Terkirim',
  failed: 'Gagal kirim',
}

export function messageChip(status) {
  return [MESSAGE_STATUS_CHIP[status] || 'L', MESSAGE_STATUS_LABEL[status] || status || '—']
}

export function emailTypeLabel(value) {
  return EMAIL_TYPES.find(([v]) => v === value)?.[1] || value || '—'
}

export function languageLabel(value) {
  return LANGUAGES.find(([v]) => v === value)?.[1] || value || '—'
}

// --- Fase 4: Automation & Notifikasi ---

// Status job automation (spesifikasi Fase 4).
export const JOB_STATUSES = [
  ['pending', 'Menunggu'],
  ['queued', 'Dalam antrean'],
  ['running', 'Berjalan'],
  ['completed', 'Selesai'],
  ['partially_completed', 'Selesai sebagian'],
  ['failed', 'Gagal'],
  ['cancelled', 'Dibatalkan'],
]

const JOB_STATUS_CHIP = {
  pending: 'L',
  queued: 'M',
  running: 'M',
  completed: 'OK',
  partially_completed: 'M',
  failed: 'H',
  cancelled: 'L',
}

export function jobStatusChip(status) {
  const label = JOB_STATUSES.find(([v]) => v === status)?.[1]
  return [JOB_STATUS_CHIP[status] || 'L', label || status || '—']
}

export const JOB_STATUS_LABEL = Object.fromEntries(JOB_STATUSES)

// Pemicu job: terjadwal, manual (Run Now), atau percobaan ulang otomatis.
export const TRIGGER_TYPES = [
  ['scheduled', 'Terjadwal'],
  ['manual', 'Manual'],
  ['retry', 'Percobaan ulang'],
]

export function triggerLabel(value) {
  return TRIGGER_TYPES.find(([v]) => v === value)?.[1] || value || '—'
}

// Tipe automation Fase 4.
export const AUTOMATION_TYPES = [
  ['tender_monitoring', 'Pemantauan Tender'],
  ['company_discovery', 'Penemuan Perusahaan'],
  ['lead_qualification', 'Kualifikasi Lead'],
  ['outreach_draft_generation', 'Pembuatan Draft Outreach'],
]

export function automationTypeLabel(value) {
  return AUTOMATION_TYPES.find(([v]) => v === value)?.[1] || value || '—'
}

// Hari untuk jadwal mingguan. Konvensi backend: 0 = Senin.
export const WEEKDAYS = [
  ['0', 'Senin'], ['1', 'Selasa'], ['2', 'Rabu'], ['3', 'Kamis'],
  ['4', 'Jumat'], ['5', 'Sabtu'], ['6', 'Minggu'],
]

export const SCHEDULE_TYPES = [
  ['daily', 'Setiap hari'],
  ['weekly', 'Mingguan'],
  ['monthly', 'Bulanan'],
  ['custom', 'Kustom (cron)'],
]

// Durasi job dalam bentuk yang mudah dibaca.
export function duration(seconds) {
  if (seconds === null || seconds === undefined || seconds === '') return '—'
  const s = Math.max(0, Math.round(Number(seconds)))
  if (!Number.isFinite(s)) return '—'
  const u = CURRENT_LANG === 'ko'
    ? { sec: '초', min: '분', hour: '시간', sep: ' ' }
    : { sec: 'dtk', min: 'mnt', hour: 'jam', sep: ' ' }
  if (s < 60) return `${s}${u.sep}${u.sec}`
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m < 60) return r ? `${m}${u.sep}${u.min}${u.sep}${r}${u.sep}${u.sec}` : `${m}${u.sep}${u.min}`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm ? `${h}${u.sep}${u.hour}${u.sep}${rm}${u.sep}${u.min}` : `${h}${u.sep}${u.hour}`
}

// Label ramah untuk tipe notifikasi (Fase 4).
const NOTIFICATION_LABEL = {
  automation_completed: 'Automation selesai',
  automation_partial: 'Automation selesai sebagian',
  automation_failed: 'Automation gagal',
  job_failed_final: 'Job gagal (final)',
  tender_new: 'Tender baru',
  tender_deadline: 'Deadline tender',
  lead_new: 'Lead baru',
  lead_high_priority: 'Lead prioritas tinggi',
  outreach_draft_ready: 'Draft outreach siap',
}

export function notificationLabel(value) {
  return NOTIFICATION_LABEL[value] || value || 'Notifikasi'
}
