// ── App Settings (data/settings.json) ─────────────────────────────────────────

export interface StoredLocation {
  city:         string
  admin1:       string
  country:      string
  country_code: string
  latitude:     number
  longitude:    number
  hemisphere:   'north' | 'south'
  timezone:     string
}

export interface AppSettings {
  theme?:           'dark' | 'day'
  location?:        StoredLocation | null
  dashboard_order?: string[]
  widget_sizes?:    Record<string, string>
  hidden_widgets?:  string[]
  sync_remote?:     string
  sync_enabled?:    boolean
  ui_font_size?:    'small' | 'normal' | 'large'
}

/** Definições globais para o bridge do Electron */
declare global {
  interface Window {
    db: any; // Pode tipar isto melhor no futuro para remover o 'any'
    appSettings: {
      getAll: () => Promise<AppSettings>
      get: <K extends keyof AppSettings>(key: K) => Promise<AppSettings[K]>
      set: <K extends keyof AppSettings>(key: K, v: AppSettings[K]) => Promise<void>
    }
    electron: {
      ipcRenderer: {
        on: (channel: string, func: (...args: any[]) => void) => () => void
      }
    }
  }
}

// ── Projeto ───────────────────────────────────────────────────────────────────

export type ProjectType =
  | 'academic' | 'writing' | 'research'
  | 'software' | 'health'  | 'hobby' | 'idea' | 'custom'

export type ProjectStatus = 'active' | 'paused' | 'completed' | 'archived'

export interface Project {
  id:           number
  workspace_id: number
  name:         string
  description:  string | null
  icon:         string | null
  color:        string | null
  project_type: ProjectType
  subcategory:  string | null
  semester:     string | null
  institution:  string | null
  status:       ProjectStatus
  date_start:   string | null
  date_end:     string | null
  sort_order:        number
  aether_project_id: string | null
  created_at:        string
  updated_at:        string
}

export interface ProjectCreateInput {
  workspace_id:  number
  name:          string
  description?:  string
  icon?:         string
  color?:        string
  project_type:  ProjectType
  subcategory?:  string
  institution?:  string
  status?:       ProjectStatus
  date_start?:   string
  date_end?:     string
  sort_order?:   number
}

// ── Propriedades de Projeto ───────────────────────────────────────────────────

export type PropType =
  | 'text' | 'number' | 'select' | 'multi_select'
  | 'date' | 'checkbox' | 'url' | 'color'

export interface ProjectProperty {
  id:          number
  project_id:  number
  name:        string
  prop_key:    string
  prop_type:   PropType
  is_required: number
  is_built_in: number
  sort_order:  number
  created_at:  string
}

export interface PropOption {
  id:          number
  property_id: number
  label:       string
  color:       string | null
  sort_order:  number
}

export interface PagePropValue {
  id:          number
  page_id:     number
  property_id: number
  prop_key:    string
  prop_type:   PropType
  prop_name:   string
  value_text:  string | null
  value_num:   number | null
  value_bool:  number | null
  value_date:  string | null
  value_date2: string | null
  value_json:  string | null
}

// ── Views de Projeto ──────────────────────────────────────────────────────────

export type ViewType = 'table' | 'kanban' | 'list' | 'calendar' | 'gallery' | 'timeline' | 'progress'

export interface ProjectView {
  id:                   number
  project_id:           number
  name:                 string
  view_type:            ViewType
  group_by_property_id: number | null
  date_property_id:     number | null
  visible_props_json:   string | null
  filter_json:          string | null
  sort_json:            string | null
  include_subpages:     number
  is_default:           number
  sort_order:           number
}

// ── Página ────────────────────────────────────────────────────────────────────

export interface Page {
  id:          number
  project_id:  number | null
  parent_id:   number | null
  title:       string
  icon:        string | null
  cover:       string | null
  cover_color: string | null
  body_json:   string | null
  sort_order:  number
  is_deleted:  number
  created_at:  string
  updated_at:  string
  prop_values?: PagePropValue[]
}

// ── Workspace ─────────────────────────────────────────────────────────────────

export interface Workspace {
  id:           number
  name:         string
  icon:         string
  accent_color: string
}

// ── Subcategorias por tipo ────────────────────────────────────────────────────

export const SUBCATEGORIES: Record<ProjectType, string[]> = {
  academic: ['Faculdade', 'Idiomas', 'Concurso Público', 'Curso Livre', 'Autodidata', 'Livre'],
  writing:  ['Roteiro', 'Worldbuilding', 'Escrita Ficcional', 'Outro'],
  research: ['Científica', 'Jornalística', 'Pessoal', 'Outro'],
  software: ['Aplicativo Desktop', 'Web', 'Mobile', 'Biblioteca', 'Outro'],
  health:   ['Fitness', 'Nutrição', 'Saúde Mental', 'Geral'],
  hobby:    ['Arte', 'Música', 'Leitura', 'Jogos', 'Esportes', 'Culinária', 'Artesanato', 'Outro'],
  idea:     ['Projeto Futuro', 'Negócio', 'Pesquisa', 'Criativo', 'Outro'],
  custom:   [],
}

export const PROJECT_TYPE_LABELS: Record<ProjectType, string> = {
  academic: 'Acadêmico',
  writing:  'Escrita',
  research: 'Pesquisa',
  software: 'Dev de Software',
  health:   'Saúde e Hábitos',
  hobby:    'Hobby',
  idea:     'Ideia Futura',
  custom:   'Personalizado',
}

export const PROJECT_TYPE_ICONS: Record<ProjectType, string> = {
  academic: '🎓',
  writing:  '✍️',
  research: '🔍',
  software: '💻',
  health:   '🌿',
  hobby:    '🎨',
  idea:     '💡',
  custom:   '✦',
}

export const PROJECT_TYPE_DESCRIPTIONS: Record<ProjectType, string> = {
  academic: 'Grades curriculares, disciplinas, semestres e prazos acadêmicos.',
  writing:  'Roteiros, worldbuilding, escrita ficcional e projetos criativos.',
  research: 'Pesquisas científicas, jornalísticas ou pessoais.',
  software: 'Desenvolvimento de aplicativos, APIs, bibliotecas e sistemas.',
  health:   'Rastreamento de hábitos, metas de saúde e rotinas.',
  hobby:    'Atividades de lazer, passatempos e interesses pessoais.',
  idea:     'Ideias e projetos futuros para explorar eventualmente.',
  custom:   'Estrutura totalmente personalizada para qualquer propósito.',
}

export const PROJECT_COLORS = [
  '#8B7355', // sépia
  '#8B3A2A', // vermelho desbotado
  '#4A6741', // verde musgo
  '#7A5C2E', // marrom
  '#2C5F8A', // azul
  '#6B4F72', // roxo
  '#5C8A6B', // verde água
  '#8A6B2C', // dourado
]

// ── API Response ──────────────────────────────────────────────────────────────

export type { ErrorCode, AppError } from './errors'

export interface ApiResponse<T = unknown> {
  ok:         boolean
  data?:      T
  error?:     string
  errorCode?: import('./errors').ErrorCode
}
