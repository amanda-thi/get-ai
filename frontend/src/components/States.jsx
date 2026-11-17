import { useI18n } from '../lib/i18n'

// Teks default diterjemahkan otomatis: pemanggil tetap mengirim teks sumber
// Bahasa Indonesia, lalu Empty/Loading menerjemahkannya sesuai bahasa aktif.
export const Loading = ({ text }) => {
  const { t } = useI18n()
  return <p className="sub">{t(text ?? 'Memuat…')}</p>
}

export const ErrorBox = ({ message }) => <div role="alert" className="err">{message}</div>

export const Empty = ({ text }) => {
  const { t } = useI18n()
  return <p className="empty">{t(text ?? 'Tidak ada data.')}</p>
}
