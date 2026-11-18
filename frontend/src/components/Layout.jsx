import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import Icon from './Icon'
import Notifications from './Notifications'

const nav = [
  ['/', 'Dashboard', 'home'],
  ['/tenders', 'Tender Monitoring', 'doc'],
  ['/leads', 'Company Leads', 'users'],
  ['/outreach', 'Marketing Outreach', 'mail'],
  ['/reports', 'Reports', 'chart'],
  ['/automation', 'Automation Settings', 'set'],
]

export default function Layout() {
  const { profile, signOut } = useAuth()
  const { t, lang, setLang, langs } = useI18n()
  const [open, setOpen] = useState(false)
  const initial = (profile?.full_name || profile?.email || '?')[0].toUpperCase()
  return (
    <div className="app">
      <aside className={`side ${open ? 'open' : ''}`}>
        <div className="brand">
          <img className="logo" src="/logo.png" alt={t('Logo PT Green Eco Teknologi')} width="44" />
          Green Eco Teknologi
        </div>
        <nav onClick={() => setOpen(false)}>
          {nav.map(([to, label, icon], i) => (
            <div key={to}>
              {i === 1 && <div className="grp">{t('Modul')}</div>}
              <NavLink to={to} end={to === '/'} className={({ isActive }) => `navlink ${isActive ? 'on' : ''}`}>
                <Icon name={icon} />{t(label)}
              </NavLink>
            </div>
          ))}
        </nav>
      </aside>
      <div className="main">
        <div className="top">
          <button className="ib menu" aria-label={t('Buka menu')} onClick={() => setOpen(!open)}><Icon name="menu" /></button>
          <span className="sp" />
          <select
            className="lang"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            aria-label={t('Ganti bahasa')}
            title={t('Ganti bahasa')}
          >
            {langs.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <Notifications />
          <div className="who">{profile?.full_name || profile?.email}<small>{profile?.role}</small></div>
          <div className="av" title={profile?.email}>{initial}</div>
          <button className="btn" onClick={signOut}>{t('Keluar')}</button>
        </div>
        <Outlet />
      </div>
    </div>
  )
}
