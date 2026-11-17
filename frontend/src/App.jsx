import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { I18nProvider } from './lib/i18n'
import { configured } from './lib/supabase'
import Layout from './components/Layout'
import { Loading, ErrorBox } from './components/States'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Tenders from './pages/Tenders'
import TenderDetail from './pages/TenderDetail'
import Leads from './pages/Leads'
import LeadDetail from './pages/LeadDetail'
import Outreach from './pages/Outreach'
import OutreachMessage from './pages/OutreachMessage'
import Automation from './pages/Automation'
import Reports from './pages/Reports'

function Gate() {
  const { session, profile, loading } = useAuth()
  if (loading) return <div className="p-8"><Loading /></div>
  if (!session || !profile) return <Login />
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="tenders" element={<Tenders />} />
        <Route path="tenders/:id" element={<TenderDetail />} />
        <Route path="leads" element={<Leads />} />
        <Route path="leads/:id" element={<LeadDetail />} />
        <Route path="outreach" element={<Outreach />} />
        <Route path="outreach/:id" element={<OutreachMessage />} />
        <Route path="reports" element={<Reports />} />
        <Route path="automation" element={<Automation />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  if (!configured)
    return <div className="p-8"><ErrorBox message="VITE_SUPABASE_URL dan VITE_SUPABASE_ANON_KEY belum diisi (lihat .env.example)." /></div>
  return <BrowserRouter><I18nProvider><AuthProvider><Gate /></AuthProvider></I18nProvider></BrowserRouter>
}
