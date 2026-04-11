// ============================================================
//  AETHER — Tipos TypeScript
//  Espelham exatamente os tipos Rust em src-tauri/src/types.rs
//  e o enum AppError em src-tauri/src/error.rs.
//  Nunca usar `any`. strict: true obrigatório.
// ============================================================

// ----------------------------------------------------------
//  Erros — espelha AppError (error.rs)
//  Serde serializa como { kind: "...", message: "..." }
// ----------------------------------------------------------

export type AppErrorKind =
  | 'Io'
  | 'Json'
  | 'VaultNotConfigured'
  | 'VaultNotFound'
  | 'ProjectNotFound'
  | 'BookNotFound'
  | 'ChapterNotFound'
  | 'InvalidPath'
  | 'InvalidName'
  | 'AlreadyExists'
  | 'NotFound'

export interface AppError {
  kind: AppErrorKind
  message: string
}

// ----------------------------------------------------------
//  Result<T> — wrapper para respostas dos commands Tauri
//  Tauri lança exceção em caso de Err no Rust;
//  o wrapper em tauri.ts captura e normaliza para este tipo.
// ----------------------------------------------------------

export type TauriResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: AppError }

// ----------------------------------------------------------
//  Tema — espelha enum Theme (types.rs)
// ----------------------------------------------------------

export type Theme = 'day' | 'dark'

// ----------------------------------------------------------
//  Status de capítulo — espelha enum ChapterStatus (types.rs)
//  Serde usa snake_case.
// ----------------------------------------------------------

export type ChapterStatus = 'draft' | 'revision' | 'final'

// ----------------------------------------------------------
//  VaultConfig — espelha struct VaultConfig (types.rs)
// ----------------------------------------------------------

export interface VaultConfig {
  theme: Theme
  font_size: number
  line_height: number
  column_width: number
}

// ----------------------------------------------------------
//  Tipo de projeto — espelha enum ProjectType (types.rs)
// ----------------------------------------------------------

export type ProjectType = 'single' | 'series' | 'fanfiction'

// ----------------------------------------------------------
//  Project (= ProjectMeta) — espelha struct Project (types.rs)
// ----------------------------------------------------------

export interface Project {
  id: string
  name: string
  description: string | null
  project_type: ProjectType
  /** Para single: ID do livro único criado automaticamente. */
  default_book_id: string | null
  created_at: string
  updated_at: string
  // Metadados opcionais (adicionados em 1.10)
  subtitle: string | null
  genre: string | null
  target_audience: string | null
  language: string | null
  tags: string[]
  has_magic_system: boolean
  tech_level: string | null
  inspirations: string | null
}

// ----------------------------------------------------------
//  BookMeta — espelha struct BookMeta (types.rs)
// ----------------------------------------------------------

export interface BookMeta {
  id: string
  name: string
  order: number
  series_name: string | null
}

// ----------------------------------------------------------
//  ChapterMeta — espelha struct ChapterMeta (types.rs)
// ----------------------------------------------------------

export interface ChapterMeta {
  id: string
  title: string
  order: number
  status: ChapterStatus
  synopsis: string | null
  word_count: number
  /** ISO 8601 — preenchido quando o capítulo está na lixeira; null = capítulo ativo */
  trashed_at: string | null
  /** IDs de personagens vinculados a este capítulo (4.6) */
  character_ids: string[]
  /** IDs de notas de worldbuilding vinculadas (4.6) */
  note_ids: string[]
  /** Meta de palavras para este capítulo (5.1) */
  word_goal: number | null
}

// ----------------------------------------------------------
//  Fase 4 — Personagens, Worldbuilding, Timeline
// ----------------------------------------------------------

export interface CustomField {
  label: string
  value: string
}

export interface Character {
  id: string
  project_id: string
  name: string
  role: string | null
  description: string | null
  fields: CustomField[]
  image_path: string | null
  chapter_ids: string[]
  created_at: string
  updated_at: string
}

export interface Relationship {
  id: string
  from_id: string
  to_id: string
  kind: string
  note: string | null
}

export type WorldCategory = 'location' | 'faction' | 'object' | 'concept' | 'other'

export interface WorldNote {
  id: string
  project_id: string
  name: string
  category: WorldCategory
  description: string | null
  fields: CustomField[]
  image_path: string | null
  chapter_ids: string[]
  created_at: string
  updated_at: string
}

export interface TimelineEvent {
  id: string
  project_id: string
  title: string
  description: string | null
  date_label: string
  order: number
  character_ids: string[]
  note_ids: string[]
  chapter_ids: string[]
}

// ----------------------------------------------------------
//  Fase 5 — Sessões, Snapshots, Anotações
// ----------------------------------------------------------

export interface WritingSession {
  id: string
  project_id: string
  book_id: string
  chapter_id: string
  started_at: string
  ended_at: string | null
  words_at_start: number
  words_at_end: number
  goal_minutes: number | null
}

export interface SnapshotMeta {
  id: string
  chapter_id: string
  created_at: string
  label: string | null
  word_count: number
}

export interface Annotation {
  id: string
  chapter_id: string
  text: string
  /** Trecho do texto ao qual a anotação se refere */
  quote: string
  created_at: string
  resolved: boolean
}

// ----------------------------------------------------------
//  Book — espelha struct Book (types.rs)
//  Versão completa com lista de capítulos.
// ----------------------------------------------------------

export interface Book {
  id: string
  project_id: string
  name: string
  order: number
  chapters: ChapterMeta[]
  series_name: string | null
  /** Meta de palavras total para este livro (5.1) */
  word_goal: number | null
}
