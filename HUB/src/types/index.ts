// ============================================================
//  HUB — Tipos compartilhados
// ============================================================

// ----------------------------------------------------------
//  IPC Result (padrão do ecossistema)
// ----------------------------------------------------------

export interface AppError {
  kind: string
  message: string
}

export type TauriResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: AppError }

// ----------------------------------------------------------
//  Ecosystem
// ----------------------------------------------------------

export interface EcosystemConfig {
  aether:    { vault_path: string }
  kosmos:    { data_path: string; archive_path: string }
  ogma:      { data_path: string }
  mnemosyne: { index_paths: string[] }
  hub:       { data_path: string }
}

// ----------------------------------------------------------
//  HUB Navigation
// ----------------------------------------------------------

export type HubView = 'home' | 'writing' | 'reading' | 'projects' | 'questions'

export interface ModuleCard {
  id: HubView
  label: string
  description: string
  seed: number          // CosmosLayer seed
  configKey: keyof EcosystemConfig
  configField: string   // campo que deve estar preenchido para habilitar o card
}
