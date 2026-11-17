import { useEffect } from 'react'
import { useI18n } from '../lib/i18n'
import Icon from './Icon'

// Modal sederhana: tutup lewat tombol, klik latar, atau tombol Esc.
export default function Modal({ title, onClose, children, footer, wide }) {
  const { t } = useI18n()
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{t(title)}</h2>
          <button className="ib" onClick={onClose} aria-label={t('Tutup')}><Icon name="x" /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

// Dialog konfirmasi untuk aksi yang perlu persetujuan (jalankan/batalkan/nonaktifkan).
export function ConfirmDialog({ title, message, confirmLabel = 'Ya, lanjutkan', danger, busy, onConfirm, onClose }) {
  const { t } = useI18n()
  return (
    <Modal
      title={title}
      onClose={busy ? () => {} : onClose}
      footer={(
        <>
          <button className="btn ghost" onClick={onClose} disabled={busy}>{t('Batal')}</button>
          <button className={`btn ${danger ? 'danger' : ''}`} onClick={onConfirm} disabled={busy}>
            {busy ? t('Memproses…') : t(confirmLabel)}
          </button>
        </>
      )}
    >
      <p style={{ margin: 0 }}>{t(message)}</p>
    </Modal>
  )
}
