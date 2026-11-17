import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Loading, ErrorBox, Empty } from '../components/States'
import Pagination from '../components/Pagination'
import SearchSelect from '../components/SearchSelect'
import { EMAIL_TYPES, LANGUAGES, dt, emailTypeLabel, languageLabel, messageChip } from '../lib/format'
import { useI18n } from '../lib/i18n'

const EMPTY = { q: '', status: '', email_type: '', language: '' }
const PER_PAGE = 20

function buildParams(filters, extra = {}) {
  const p = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => { if (v) p.set(k, v) })
  Object.entries(extra).forEach(([k, v]) => p.set(k, String(v)))
  return p.toString()
}

function MessagesTab({ leads, templates, onOpen, initialLeadId }) {
  const { t } = useI18n()
  const [filters, setFilters] = useState(EMPTY)
  const [qInput, setQInput] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showGen, setShowGen] = useState(true)
  const [gen, setGen] = useState({ lead_id: initialLeadId || '', email_type: 'company_intro', language: 'id', template_id: '', recipient_email: '', instructions: '' })
  const [busy, setBusy] = useState(false)
  const [genError, setGenError] = useState('')

  const query = useMemo(() => buildParams(filters, { page, per_page: PER_PAGE }), [filters, page])
  const load = useCallback(() => {
    setLoading(true)
    api(`/api/outreach/messages?${query}`)
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [query])
  useEffect(() => { load() }, [load])

  const set = (patch) => { setFilters((f) => ({ ...f, ...patch })); setPage(1) }

  // Opsi perusahaan untuk combobox: dicari ke server saat mengetik, jadi tetap
  // nyaman walau jumlah perusahaan banyak (bukan daftar gulir panjang).
  const fetchLeadOptions = useCallback(async (q) => {
    const params = new URLSearchParams({ per_page: '20', sort: 'created_at', order: 'desc' })
    if (q) params.set('q', q)
    const d = await api(`/api/leads?${params.toString()}`)
    return (d.items || [])
      .map((l) => ({
        id: l.lead?.id,
        label: l.name,
        sub: [l.city, l.province].filter(Boolean).join(', ') || l.industry || l.website || '',
      }))
      .filter((it) => it.id)
  }, [])

  const selectedLeadName = useMemo(
    () => leads.find((l) => l.lead?.id === gen.lead_id)?.name || '',
    [leads, gen.lead_id],
  )

  const generate = async () => {
    if (!gen.lead_id) { setGenError(t('Pilih perusahaan tujuan.')); return }
    setBusy(true); setGenError('')
    try {
      const body = { ...gen, lead_id: gen.lead_id, limit: undefined }
      Object.keys(body).forEach((k) => { if (body[k] === '') delete body[k] })
      const msg = await api('/api/outreach/generate', { method: 'POST', body: JSON.stringify(body) })
      load()
      onOpen(msg.id)
    } catch (e) { setGenError(e.message) } finally { setBusy(false) }
  }

  const items = data?.items || []
  const tplOptions = templates.filter((t) => t.email_type === gen.email_type && t.language === gen.language && t.is_active)

  return (
    <>
      {showGen && (
        <div className="card">
          <div className="toolbar" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}>{t('Buat email dengan AI')}</h2>
            <button className="linkbtn" onClick={() => setShowGen(false)}>{t('Tutup')}</button>
          </div>
          <div className="sub" style={{ marginBottom: 12 }}>
            {t('AI menulis draft berdasarkan profil perusahaan (')}<code>config/company_profile.yaml</code>{t(') dan data lead. Draft tidak terkirim otomatis — perlu persetujuan admin.')}
          </div>
          <div className="formgrid">
            <div className="field">{t('Perusahaan tujuan *')}
              <SearchSelect
                value={gen.lead_id}
                initialLabel={selectedLeadName}
                onChange={(id) => setGen({ ...gen, lead_id: id })}
                fetchItems={fetchLeadOptions}
                placeholder="Ketik nama perusahaan…"
                emptyText="Perusahaan tidak ditemukan."
              />
            </div>
            <label className="field">{t('Jenis email')}
              <select value={gen.email_type} onChange={(e) => setGen({ ...gen, email_type: e.target.value, template_id: '' })}>
                {EMAIL_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
              </select>
            </label>
            <label className="field">{t('Bahasa')}
              <select value={gen.language} onChange={(e) => setGen({ ...gen, language: e.target.value, template_id: '' })}>
                {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
              </select>
            </label>
            <label className="field">{t('Template (opsional)')}
              <select value={gen.template_id} onChange={(e) => setGen({ ...gen, template_id: e.target.value })}>
                <option value="">{t('— tanpa template —')}</option>
                {tplOptions.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
            <label className="field">{t('Email tujuan (opsional)')}
              <input value={gen.recipient_email} onChange={(e) => setGen({ ...gen, recipient_email: e.target.value })} placeholder={t('otomatis dari kontak lead')} />
            </label>
            <label className="field">{t('Instruksi tambahan (opsional)')}
              <textarea className="textarea" value={gen.instructions} onChange={(e) => setGen({ ...gen, instructions: e.target.value })} />
            </label>
          </div>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="btn" onClick={generate} disabled={busy}>{busy ? t('Menulis…') : t('Buat draft')}</button>
          </div>
          {genError && <div className="err" style={{ marginTop: 12 }}>{genError}</div>}
        </div>
      )}

      <div className="card">
        <div className="toolbar" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>{t('Pesan outreach')}</h2>
          {!showGen && <button className="btn ghost" onClick={() => setShowGen(true)}>{t('Buat email')}</button>}
        </div>
        <form className="toolbar filters" onSubmit={(e) => { e.preventDefault(); set({ q: qInput }) }}>
          <input className="search" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={t('Cari subjek / isi / email…')} />
          <select value={filters.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="">{t('Semua status')}</option>
            <option value="draft">{t('Draft')}</option>
            <option value="saved_for_later">{t('Disimpan')}</option>
            <option value="approved">{t('Disetujui')}</option>
            <option value="sent">{t('Terkirim')}</option>
            <option value="failed">{t('Gagal kirim')}</option>
          </select>
          <select value={filters.email_type} onChange={(e) => set({ email_type: e.target.value })}>
            <option value="">{t('Semua jenis')}</option>
            {EMAIL_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
          </select>
          <select value={filters.language} onChange={(e) => set({ language: e.target.value })}>
            <option value="">{t('Semua bahasa')}</option>
            {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
          </select>
          <button className="btn" type="submit">{t('Cari')}</button>
          <button className="btn ghost" type="button" onClick={() => { setQInput(''); setFilters(EMPTY); setPage(1) }}>{t('Reset')}</button>
        </form>

        {error && <ErrorBox message={error} />}
        {loading && !data && <Loading />}
        {data && items.length === 0 && <Empty text="Belum ada email. Buat draft baru di atas." />}

        {items.length > 0 && (
          <div className="tblwrap">
            <table className="tbl">
              <thead>
                <tr><th>{t('Perusahaan')}</th><th>{t('Jenis')}</th><th>{t('Bahasa')}</th><th>{t('Subjek')}</th><th>{t('Status')}</th><th>{t('Dibuat')}</th></tr>
              </thead>
              <tbody>
                {items.map((m) => {
                  const [cls, txt] = messageChip(m.status)
                  return (
                    <tr key={m.id} className="clickable" onClick={() => onOpen(m.id)}>
                      <td><b>{m.company_name || m.recipient_email || '—'}</b></td>
                      <td>{t(emailTypeLabel(m.email_type))}</td>
                      <td>{t(languageLabel(m.language))}</td>
                      <td>{m.subject}</td>
                      <td><span className={`chip ${cls}`}>{t(txt)}</span></td>
                      <td>{dt(m.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {data && <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />}
      </div>
    </>
  )
}

function TemplatesTab({ templates, reload, isAdmin }) {
  const { t } = useI18n()
  const [form, setForm] = useState({ name: '', email_type: 'company_intro', language: 'id', subject: '', body: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const create = async () => {
    if (!form.name.trim() || !form.subject.trim() || !form.body.trim()) { setError(t('Nama, subjek, dan isi wajib diisi.')); return }
    setBusy(true); setError('')
    try {
      await api('/api/outreach/templates', { method: 'POST', body: JSON.stringify({ ...form, is_active: true }) })
      setForm({ name: '', email_type: 'company_intro', language: 'id', subject: '', body: '' })
      reload()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const remove = async (id) => { try { await api(`/api/outreach/templates/${id}`, { method: 'DELETE' }); reload() } catch (e) { setError(e.message) } }
  const toggle = async (t) => { try { await api(`/api/outreach/templates/${t.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !t.is_active }) }); reload() } catch (e) { setError(e.message) } }

  return (
    <>
      {isAdmin && (
        <div className="card">
          <h2>{t('Template baru')}</h2>
          <div className="formgrid" style={{ marginTop: 10 }}>
            <label className="field">{t('Nama *')}<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="field">{t('Jenis')}
              <select value={form.email_type} onChange={(e) => setForm({ ...form, email_type: e.target.value })}>
                {EMAIL_TYPES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
              </select>
            </label>
            <label className="field">{t('Bahasa')}
              <select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
                {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
              </select>
            </label>
            <label className="field">{t('Subjek *')}<input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></label>
            <label className="field">{t('Isi *')}<textarea className="textarea" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></label>
          </div>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="btn" onClick={create} disabled={busy}>{busy ? t('Menyimpan…') : t('Simpan template')}</button>
          </div>
          {error && <div className="err" style={{ marginTop: 12 }}>{error}</div>}
        </div>
      )}

      <div className="card">
        <h2>{t('Daftar template')}</h2>
        <div className="sub" style={{ marginBottom: 10 }}>{t('Template menjadi kerangka opsional saat AI menulis email.')}</div>
        {templates.length === 0 && <Empty text="Belum ada template." />}
        {templates.map((tpl) => (
          <div key={tpl.id} className="row">
            <div className="t">
              <b>{tpl.name}</b>
              <span className="sub">{t(emailTypeLabel(tpl.email_type))} · {t(languageLabel(tpl.language))} · {tpl.subject}</span>
            </div>
            <span className={`chip ${tpl.is_active ? 'OK' : 'L'}`}>{tpl.is_active ? t('aktif') : t('nonaktif')}</span>
            {isAdmin && <button className="linkbtn" onClick={() => toggle(tpl)}>{tpl.is_active ? t('Nonaktifkan') : t('Aktifkan')}</button>}
            {isAdmin && <button className="linkbtn" onClick={() => remove(tpl.id)}>{t('Hapus')}</button>}
          </div>
        ))}
      </div>
    </>
  )
}

function CampaignsTab({ campaigns, reload, isAdmin }) {
  const { t } = useI18n()
  const [form, setForm] = useState({ name: '', description: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const create = async () => {
    if (!form.name.trim()) { setError(t('Nama kampanye wajib diisi.')); return }
    setBusy(true); setError('')
    try {
      await api('/api/outreach/campaigns', { method: 'POST', body: JSON.stringify({ ...form, status: 'active' }) })
      setForm({ name: '', description: '' })
      reload()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const setStatus = async (c, status) => { try { await api(`/api/outreach/campaigns/${c.id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); reload() } catch (e) { setError(e.message) } }

  return (
    <>
      {isAdmin && (
        <div className="card">
          <h2>{t('Kampanye baru')}</h2>
          <div className="formgrid" style={{ marginTop: 10 }}>
            <label className="field">{t('Nama *')}<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="field">{t('Deskripsi')}<textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          </div>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="btn" onClick={create} disabled={busy}>{busy ? t('Menyimpan…') : t('Simpan kampanye')}</button>
          </div>
          {error && <div className="err" style={{ marginTop: 12 }}>{error}</div>}
        </div>
      )}

      <div className="card">
        <h2>{t('Daftar kampanye')}</h2>
        {campaigns.length === 0 && <Empty text="Belum ada kampanye." />}
        {campaigns.map((c) => (
          <div key={c.id} className="row">
            <div className="t"><b>{c.name}</b><span className="sub">{c.description || '—'}</span></div>
            <span className={`chip ${c.status === 'active' ? 'OK' : 'L'}`}>{c.status}</span>
            {isAdmin && c.status !== 'completed' && <button className="linkbtn" onClick={() => setStatus(c, c.status === 'active' ? 'paused' : 'active')}>{c.status === 'active' ? t('Jeda') : t('Lanjutkan')}</button>}
            {isAdmin && c.status !== 'completed' && <button className="linkbtn" onClick={() => setStatus(c, 'completed')}>{t('Selesaikan')}</button>}
          </div>
        ))}
      </div>
    </>
  )
}

export default function Outreach() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const { profile } = useAuth()
  const { t } = useI18n()
  const isAdmin = profile?.role === 'admin'

  const [tab, setTab] = useState('messages')
  const [config, setConfig] = useState(null)
  const [templates, setTemplates] = useState([])
  const [campaigns, setCampaigns] = useState([])
  const [leads, setLeads] = useState([])
  const [loadError, setLoadError] = useState('')

  const loadTemplates = useCallback(() => api('/api/outreach/templates').then((d) => setTemplates(d.items || [])).catch((e) => setLoadError(e.message)), [])
  const loadCampaigns = useCallback(() => api('/api/outreach/campaigns').then((d) => setCampaigns(d.items || [])).catch((e) => setLoadError(e.message)), [])

  useEffect(() => {
    api('/api/outreach/config').then(setConfig).catch((e) => setLoadError(e.message))
    api('/api/leads?per_page=100&sort=created_at&order=desc').then((d) => setLeads(d.items || [])).catch(() => {})
    loadTemplates(); loadCampaigns()
  }, [loadTemplates, loadCampaigns])

  // Pratinjau lead dari halaman detail (mis. /outreach?lead_id=...)
  const preselect = params.get('lead_id')

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t('Marketing Outreach')}</h1>
          <p className="sub">{t('Tulis email penawaran dengan AI, kelola template & kampanye, lalu kirim setelah disetujui admin.')}</p>
        </div>
      </div>

      {config && !config.smtp_configured && (
        <div className="notice warn">
          {t('SMTP belum dikonfigurasi — email bisa dibuat & disimpan sebagai draft, tetapi')}{' '}
          <b>{t('belum bisa dikirim')}</b>{t('. Isi variabel ')}
          <code>SMTP_*</code>{t(' di backend untuk mengaktifkan pengiriman.')}
        </div>
      )}
      {config && !config.ai_configured && (
        <div className="notice warn">
          {t('Kunci AI belum diisi (')}<code>GROQ_API_KEY</code>{' / '}<code>OPENAI_API_KEY</code>{t(') — pembuatan email otomatis belum aktif.')}
        </div>
      )}
      {loadError && <ErrorBox message={loadError} />}

      <div className="tabs">
        {[['messages', 'Pesan'], ['templates', 'Template'], ['campaigns', 'Kampanye']].map(([v, label]) => (
          <button key={v} className={`tab ${tab === v ? 'on' : ''}`} onClick={() => setTab(v)}>{t(label)}</button>
        ))}
      </div>

      {tab === 'messages' && (
        <MessagesTab
          leads={leads}
          templates={templates}
          initialLeadId={preselect || ''}
          onOpen={(id) => nav(`/outreach/${id}`)}
        />
      )}
      {tab === 'templates' && <TemplatesTab templates={templates} reload={loadTemplates} isAdmin={isAdmin} />}
      {tab === 'campaigns' && <CampaignsTab campaigns={campaigns} reload={loadCampaigns} isAdmin={isAdmin} />}
    </div>
  )
}
