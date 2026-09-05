const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'
const USER = import.meta.env.VITE_USER_ID ?? 'demo-user'

const headers = (extra = {}) => ({ 'X-User-ID': USER, ...extra })

async function json(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: headers({ 'Content-Type': 'application/json', ...(options.headers || {}) })
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.error?.message || body?.detail || `${res.status} ${res.statusText}`)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  options: () => json('/settings/options'),
  getSettings: () => json('/settings'),
  saveSettings: (body) => json('/settings', { method: 'PUT', body: JSON.stringify(body) }),

  conversations: () => json('/conversations?limit=100'),
  conversation: (id) => json(`/conversations/${id}`),
  deleteConversation: (id) => json(`/conversations/${id}`, { method: 'DELETE' }),
  runs: (id) => json(`/conversations/${id}/runs`),

  files: () => json('/files'),
  deleteFile: (id) => json(`/files/${id}`, { method: 'DELETE' }),
  reingest: (id) => json(`/files/${id}/reingest`, { method: 'POST' }),
  search: (body) => json('/search', { method: 'POST', body: JSON.stringify(body) }),
  health: () => json('/health'),

  upload: async (file, conversationId) => {
    const form = new FormData()
    form.append('file', file)
    if (conversationId) form.append('conversation_id', conversationId)
    const res = await fetch(`${BASE}/files`, { method: 'POST', headers: headers(), body: form })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.detail || body?.error?.message || 'Upload failed')
    }
    return res.json()
  }
}

/**
 * Reads the SSE stream. We use fetch + a reader rather than EventSource because
 * EventSource cannot send a POST body or custom headers.
 */
export async function streamChat(body, { onEvent, signal }) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
    body: JSON.stringify(body),
    signal
  })
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Stream failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue                      // heartbeat comment
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') return
      try {
        onEvent(JSON.parse(payload))
      } catch {
        // A truncated frame is not fatal; the next read completes it.
      }
    }
  }
}

export const USER_ID = USER
