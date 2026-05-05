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
  mnemosyne: { watched_dir?: string; vault_dir?: string; chroma_dir?: string; extra_dirs?: string[]; index_paths?: string[]; exe_path?: string }
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
  active_priority:    number | null
  /** "leve" | "pesado" | null */
  active_model_class: string | null
  /** App que está usando o LOGOS no momento ("kosmos", "mnemosyne", etc.) */
  active_app:         string | null
  /** Perfil de workflow ativo: "normal" | "escrita" | "estudo" | "consumo" */
  current_profile:    string
  /** Modo de hardware: "normal" (CachyOS/GPU) | "sobrevivencia" (Windows/CPU-only) */
  hardware_mode:      string
  /** Perfil de hardware detectado: "main_pc" | "laptop" | "work_pc" */
  hardware_profile:         string
  /** Nome legível: "PC Principal · RX 6600 (8 GB)" etc. */
  hardware_profile_display: string
  queue:              [number, number, number]
  vram_used_mb:       number | null
  vram_pct:           number | null
  ollama_url:         string
  /** Uso de CPU global (0–100) via sysinfo — delta entre polls consecutivos */
  cpu_pct:            number
  /** RAM livre em MB via sysinfo */
  ram_free_mb:        number
  /** RAM total em MB via sysinfo */
  ram_total_mb:       number
  /** True se rodando em bateria — P3 bloqueado, thresholds de P2 mais conservadores */
  on_battery:         boolean
  /** Requests P3 preemptados por P1 desde o startup */
  preempted_count:    number
}

export interface OllamaModelInfo {
  name:         string
  size_vram_mb: number
}

// ----------------------------------------------------------
//  HUB Navigation
// ----------------------------------------------------------

export type HubView = 'home' | 'writing' | 'reading' | 'projects' | 'questions'

export type HubSection = 'home' | 'logos' | 'atividade' | 'config'

export interface ModuleCard {
  id: HubView
  label: string
  description: string
  seed: number          // CosmosLayer seed
  configKey: keyof EcosystemConfig
  configField: string   // campo que deve estar preenchido para habilitar o card
}
