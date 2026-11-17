import { useCallback, useEffect, useRef, useState } from 'react'
import { useI18n } from '../lib/i18n'

/**
 * Combobox dengan pencarian (hasil diambil dari server saat mengetik).
 *
 * Dipakai untuk memilih perusahaan tujuan saat membuat email, agar tetap mudah
 * dipakai walau jumlah perusahaan banyak — tidak perlu menggulir daftar panjang.
 *
 * Props:
 * - value: id yang terpilih (string, '' bila kosong)
 * - onChange: (id, item|null) => void
 * - fetchItems: (query: string) => Promise<Array<{id, label, sub?}>>
 * - placeholder, initialLabel (label untuk `value` yang sudah terpilih), emptyText
 */
export default function SearchSelect({
  value,
  onChange,
  fetchItems,
  placeholder = 'Cari…',
  initialLabel = '',
  emptyText = 'Tidak ada hasil.',
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(initialLabel)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hi, setHi] = useState(0)

  const boxRef = useRef(null)
  const timer = useRef(null)
  const labelRef = useRef(initialLabel)
  const openRef = useRef(false)

  useEffect(() => { labelRef.current = initialLabel; if (initialLabel) setText(initialLabel) }, [initialLabel])
  useEffect(() => { openRef.current = open }, [open])
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const runFetch = useCallback(async (q) => {
    setLoading(true); setError('')
    try {
      setItems((await fetchItems(q)) || [])
      setHi(0)
    } catch (e) {
      setError(e.message || 'Gagal memuat daftar.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [fetchItems])

  const openMenu = () => {
    setOpen(true)
    if (!items.length && !loading) runFetch('')
  }

  const onInput = (v) => {
    setText(v)
    setOpen(true)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => runFetch(v.trim()), 250)
  }

  const pick = (item) => {
    labelRef.current = item.label
    setText(item.label)
    setOpen(false)
    onChange(item.id, item)
  }

  const clear = () => {
    labelRef.current = ''
    setText('')
    setItems([])
    onChange('', null)
  }

  const restore = () => { setText(labelRef.current || '') }

  useEffect(() => {
    const onDoc = (e) => {
      if (!openRef.current) return
      if (boxRef.current && !boxRef.current.contains(e.target)) {
        setOpen(false)
        setText(labelRef.current || '')
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const onKey = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) openMenu()
      else setHi((i) => Math.min(i + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHi((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && items[hi]) { e.preventDefault(); pick(items[hi]) }
    } else if (e.key === 'Escape') {
      setOpen(false); restore()
    }
  }

  return (
    <div className="ss" ref={boxRef}>
      <div className="ss-inputwrap">
        <input
          className="ss-input"
          value={text}
          placeholder={t(placeholder)}
          onChange={(e) => onInput(e.target.value)}
          onFocus={openMenu}
          onKeyDown={onKey}
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
        />
        {(value || text) && (
          <button type="button" className="ss-clear" onClick={clear} aria-label={t('Hapus pilihan')} title={t('Hapus pilihan')}>×</button>
        )}
      </div>
      {open && (
        <div className="ss-menu" role="listbox">
          {loading && <div className="ss-note">{t('Memuat…')}</div>}
          {error && <div className="ss-note ss-note-err">{t(error)}</div>}
          {!loading && !error && items.length === 0 && <div className="ss-note">{t(emptyText)}</div>}
          {!loading && !error && items.map((it, i) => (
            <div
              key={it.id}
              role="option"
              aria-selected={it.id === value}
              className={`ss-opt ${i === hi ? 'hi' : ''} ${it.id === value ? 'on' : ''}`}
              onMouseEnter={() => setHi(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(it)}
            >
              <span className="ss-opt-label">{it.label}</span>
              {it.sub ? <span className="ss-opt-sub">{it.sub}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
