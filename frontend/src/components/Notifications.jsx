import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { dt, notificationLabel } from '../lib/format'
import { Empty, Loading } from './States'
import Icon from './Icon'

// Lonceng notifikasi di topbar: jumlah belum dibaca, daftar, tandai dibaca.
export default function Notifications() {
  const nav = useNavigate()
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const boxRef = useRef(null)

  const loadCount = useCallback(() => {
    api('/api/notifications/unread-count')
      .then((d) => setUnread(d.unread_count || 0))
      .catch(() => {})
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    api('/api/notifications?per_page=15')
      .then((d) => { setData(d); setUnread(d.unread_count || 0); setError('') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Hitungan belum dibaca disegarkan berkala, terlepas panel terbuka atau tidak.
  useEffect(() => {
    loadCount()
    const t = setInterval(loadCount, 60000)
    return () => clearInterval(t)
  }, [loadCount])

  // Daftar dimuat saat panel dibuka.
  useEffect(() => {
    if (open) load()
  }, [open, load])

  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const openItem = async (n) => {
    setOpen(false)
    if (!n.is_read) {
      try {
        await api(`/api/notifications/${n.id}/read`, { method: 'PATCH' })
        setUnread((u) => Math.max(0, u - 1))
      } catch { /* biarkan; hitungan disegarkan saat panel dibuka lagi */ }
    }
    if (n.link) nav(n.link)
  }

  const readAll = async () => {
    try { await api('/api/notifications/read-all', { method: 'POST' }); load() } catch (e) { setError(e.message) }
  }

  const items = data?.items || []
  const hasUnread = items.some((n) => !n.is_read)

  return (
    <div className="notif" ref={boxRef}>
      <button className="ib" aria-label={t('Notifikasi')} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon name="bell" />
        {unread > 0 && <span className="badge">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="notif-menu" role="dialog" aria-label={t('Daftar notifikasi')}>
          <div className="notif-head">
            <b>{t('Notifikasi')}</b>
            {hasUnread && <button className="linkbtn" onClick={readAll}>{t('Tandai semua dibaca')}</button>}
          </div>
          {error && <div className="err" style={{ margin: 10 }}>{error}</div>}
          {loading && !data && <div style={{ padding: 12 }}><Loading /></div>}
          {data && items.length === 0 && <div style={{ padding: 12 }}><Empty text="Belum ada notifikasi." /></div>}
          {items.map((n) => (
            <button key={n.id} className={`notif-item ${n.is_read ? '' : 'unread'}`} onClick={() => openItem(n)}>
              <span className="notif-type">{t(notificationLabel(n.notification_type))}</span>
              <span className="notif-title">{n.title}</span>
              <span className="notif-msg">{n.message}</span>
              <time>{dt(n.created_at)}</time>
            </button>
          ))}
          <div className="notif-foot">
            <button className="linkbtn" onClick={() => { setOpen(false); nav('/automation') }}>{t('Buka Automation')}</button>
          </div>
        </div>
      )}
    </div>
  )
}
