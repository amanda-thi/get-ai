import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { ErrorBox } from '../components/States'

export default function Login() {
  const { signIn, error: profileError } = useAuth()
  const { t, lang, setLang, langs } = useI18n()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError('')
    const { error } = await signIn(email, password)
    if (error) setError(error.message)
    setBusy(false)
  }

  return (
    <div className="auth">
      <form onSubmit={submit} className="authcard">
        <div className="flex items-center gap-3">
          <img className="logo" src="/logo.png" alt={t('Logo PT Green Eco Teknologi')} width="64" />
          <div>
            <h1 className="m-0 text-lg font-semibold" style={{ color: 'var(--ptext)' }}>Green Eco Teknologi</h1>
            <p className="sub m-0">{t('Business Automation')}</p>
          </div>
        </div>
        {(error || profileError) && <ErrorBox message={error || profileError} />}
        <label className="field">{t('Email')}
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">{t('Password')}
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button className="btn" disabled={busy}>{busy ? t('Masuk…') : t('Masuk')}</button>
        <div style={{ marginTop: 12, textAlign: 'center' }}>
          <select
            className="lang"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            aria-label={t('Ganti bahasa')}
            title={t('Ganti bahasa')}
          >
            {langs.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
      </form>
    </div>
  )
}
