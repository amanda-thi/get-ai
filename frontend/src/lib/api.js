import { supabase } from './supabase'

export async function api(path, options = {}) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request gagal (${res.status})`)
  }
  return res.json()
}

// Unduh berkas (mis. export Excel) dengan token sesi. Memicu unduhan di browser.
export async function apiDownload(path, fallbackName = 'download') {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Unduhan gagal (${res.status})`)
  }
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') || ''
  const m = cd.match(/filename="?([^"]+)"?/)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = m ? m[1] : fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
