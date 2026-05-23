// ============================================================
//  HUB — Cliente de inferência (LOGOS proxy)
//  Chama LOGOS (localhost:7072) via fetch.
//  CSP desabilitado em tauri.conf.json (csp: null).
// ============================================================

const BASE = 'http://localhost:7072'

// ----------------------------------------------------------
//  Tipos
// ----------------------------------------------------------

// ----------------------------------------------------------
//  listModels — GET /v1/models
// ----------------------------------------------------------

export async function listModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/v1/models`)
  if (!res.ok) {
    throw new Error(`Servidor de inferência retornou ${res.status}`)
  }
  const data = (await res.json()) as { data?: { id: string }[] }
  return (data.data ?? []).map(m => m.id).sort()
}
