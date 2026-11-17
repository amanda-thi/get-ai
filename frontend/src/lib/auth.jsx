import { createContext, useContext, useEffect, useState } from 'react'
import { supabase, configured } from './supabase'
import { api } from './api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(configured)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!configured) return
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!configured) return
    if (!session) { setProfile(null); setLoading(false); return }
    setLoading(true)
    api('/api/auth/me')
      .then((p) => { setProfile(p); setError('') })
      .catch((e) => { setProfile(null); setError(e.message) })
      .finally(() => setLoading(false))
  }, [session])

  const signIn = (email, password) => supabase.auth.signInWithPassword({ email, password })
  const signOut = () => supabase.auth.signOut()

  return <Ctx.Provider value={{ session, profile, loading, error, signIn, signOut }}>{children}</Ctx.Provider>
}
