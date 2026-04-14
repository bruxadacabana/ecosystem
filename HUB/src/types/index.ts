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
//  AETHER — Escrita
// ----------------------------------------------------------

export type ProjectType = 'single' | 'series' | 'fanfiction'
export type ChapterStatus = 'draft' | 'revision' | 'final'

export interface Project {
  id: string
  name: string
  description: string | null
  project_type: ProjectType
  default_book_id: string | null
  created_at: string
  updated_at: string
  subtitle: string | null
  genre: string | null
  tags: string[]
}

export interface ChapterMeta {
  id: string
  title: string
  order: number
  status: ChapterStatus
  synopsis: string | null
  word_count: number
  trashed_at: string | null
  word_goal: number | null
}

export interface Book {
  id: string
  project_id: string
  name: string
  order: number
  chapters: ChapterMeta[]
  series_name: string | null
  word_goal: number | null
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
