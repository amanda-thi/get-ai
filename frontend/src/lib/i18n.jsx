import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import ko from '../i18n/ko'
import { setFormatLang } from './format'

// Dua bahasa: Indonesia (sumber) & Korea (terjemahan).
export const LANGS = [
  ['id', 'Indonesia'],
  ['ko', '한국어'],
]

const STORAGE_KEY = 'greeneco.lang'
const I18nContext = createContext(null)

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'ko' ? 'ko' : 'id'
  } catch {
    return 'id'
  }
}

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(readStored)

  // Selaraskan format tanggal & durasi (lib/format.js) dengan bahasa aktif.
  // Dilakukan saat render agar anak-anak sudah memakai locale yang benar.
  setFormatLang(lang)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, lang)
    } catch {
      // localStorage bisa diblokir (mode privat) — abaikan, bahasa tetap jalan di sesi ini.
    }
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo(
    () => ({
      lang,
      setLang,
      langs: LANGS,
      // t(teks) mengembalikan terjemahan Korea bila bahasa = ko, jika tidak teks asli.
      // Kunci yang belum ada di kamus otomatis jatuh ke teks sumber (aman).
      t: (text, vars) => {
        const src = text == null ? '' : String(text)
        let out = lang === 'ko' ? (ko[src] ?? src) : src
        if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v))
        return out
      },
    }),
    [lang],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n harus dipakai di dalam <I18nProvider>')
  return ctx
}
