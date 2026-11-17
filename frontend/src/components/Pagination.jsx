import { useI18n } from '../lib/i18n'

export default function Pagination({ page, pages, total, perPage, onPage }) {
  const { t } = useI18n()
  if (!total) return null
  const from = (page - 1) * perPage + 1
  const to = Math.min(page * perPage, total)
  const canPrev = page > 1
  const canNext = page < pages
  return (
    <div className="pager">
      <span className="sub">
        {t('Menampilkan {from}–{to} dari {total}', { from, to, total })}
      </span>
      <div className="pager-btns">
        <button className="btn ghost" disabled={!canPrev} onClick={() => onPage(page - 1)}>‹ {t('Sebelumnya')}</button>
        <span className="sub">{t('Halaman {page} / {pages}', { page, pages: pages || 1 })}</span>
        <button className="btn ghost" disabled={!canNext} onClick={() => onPage(page + 1)}>{t('Berikutnya')} ›</button>
      </div>
    </div>
  )
}
