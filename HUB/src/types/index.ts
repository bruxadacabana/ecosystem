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
  aether:    { vault_path: string; exe_path?: string }
  kosmos:    { data_path: string; archive_path: string; exe_path?: string }
  ogma:      { data_path: string; exe_path?: string }
  mnemosyne: { index_paths: string[]; exe_path?: string }
  hermes:    { exe_path?: string }
  akasha:    { base_url?: string; exe_path?: string }
  hub:       { data_path: string }
}

export type AppName = 'aether' | 'ogma' | 'kosmos' | 'mnemosyne' | 'hermes' | 'akasha'

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
//  KOSMOS — Leituras
// ----------------------------------------------------------

export interface ArticleMeta {
  path: string      // caminho absoluto do .md
  title: string
  source: string    // label do feed (pasta pai)
  date: string
  author: string
  url: string
  is_read: boolean
}

export interface ArticleContent {
  meta: ArticleMeta
  body: string      // corpo Markdown sem o bloco frontmatter
}

// ----------------------------------------------------------
//  OGMA — Projetos
// ----------------------------------------------------------

export interface OgmaProject {
  id:           number
  name:         string
  description:  string | null
  icon:         string | null
  color:        string | null
  project_type: string
  subcategory:  string | null
  status:       string
  date_start:   string | null
  date_end:     string | null
  sort_order:   number
}

export interface OgmaPage {
  id:         number
  title:      string
  icon:       string | null
  parent_id:  number | null
  sort_order: number
  body_json:  string | null
}

// ----------------------------------------------------------
//  LOGOS — Status do proxy LLM
// ----------------------------------------------------------

export interface LogosStatus {
  active_priority: number | null
  queue: [number, number, number]
  vram_used_mb: number | null
  vram_pct: number | null
  ollama_url: string
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
