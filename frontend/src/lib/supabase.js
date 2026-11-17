import { createClient } from '@supabase/supabase-js'

// Hanya anon key. Service role key tidak pernah ada di frontend.
const url = import.meta.env.VITE_SUPABASE_URL
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY

export const configured = Boolean(url && anon)
export const supabase = configured ? createClient(url, anon) : null
