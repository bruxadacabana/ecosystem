// ============================================================
//  HUB — Cliente Ollama
//  Chama localhost:11434 diretamente via fetch (sem Rust).
//  CSP desabilitado em tauri.conf.json (csp: null).
// ============================================================

const BASE = 'http://localhost:11434'

// ----------------------------------------------------------
//  Tipos
// ----------------------------------------------------------

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

