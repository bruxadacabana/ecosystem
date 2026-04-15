// ============================================================
//  HUB — Cliente Ollama
//  Chama localhost:11434 diretamente via fetch (sem Rust).
//  CSP desabilitado em tauri.conf.json (csp: null).
// ============================================================

const BASE = 'http://localhost:11434'

// ----------------------------------------------------------
//  Tipos
// ----------------------------------------------------------

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

// ----------------------------------------------------------
//  listModels — GET /api/tags
// ----------------------------------------------------------

export async function listModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/tags`)
  if (!res.ok) {
    throw new Error(`Ollama retornou ${res.status}`)
  }
  const data = (await res.json()) as { models?: { name: string }[] }
  return (data.models ?? []).map(m => m.name).sort()
}

// ----------------------------------------------------------
//  streamChat — POST /api/chat (NDJSON streaming)
// ----------------------------------------------------------

export async function* streamChat(
  model: string,
  messages: ChatMessage[],
): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, stream: true }),
  })

  if (!res.ok) {
    throw new Error(`Ollama retornou ${res.status}`)
  }
  if (!res.body) {
    throw new Error('Resposta sem body')
  }

  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let   buffer  = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Processa linhas completas do buffer NDJSON
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? '' // última linha pode estar incompleta

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const obj = JSON.parse(trimmed) as {
          message?: { content?: string }
          done?: boolean
        }
        const token = obj.message?.content
        if (token) yield token
        if (obj.done) return
      } catch {
        // linha malformada — ignora silenciosamente
      }
    }
  }
}
