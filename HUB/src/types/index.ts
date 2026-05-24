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
  mnemosyne: { watched_dir?: string; vault_dir?: string; chroma_dir?: string; extra_dirs?: string[]; index_paths?: string[]; exe_path?: string; pending_insights?: number; incoming_insights?: InsightQueueItem[]; bg_processing?: { indexing?: boolean; files_pending?: number; current_file?: string | null }; personality_prompt?: string; cmd_reset_memory?: boolean }
  hermes:    { exe_path?: string }
  akasha:    { base_url?: string; exe_path?: string; incoming_insights?: InsightQueueItem[]; bg_processing?: { knowledge_extraction?: number; worker_active?: boolean }; personality_prompt?: string; interest_seeds?: string[] }
  hub:       { data_path: string }
  logos?:    { vram_limit_pct?: number; cpu_threads?: number; flash_attention?: boolean }
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
  llama_server_url:   string
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
  /** Limite de VRAM (%) para bloquear P3 — configurável, padrão 85 */
  vram_limit_pct:     number
  /** True quando o watchdog de VRAM bloqueou P3 (VRAM > limit%). Retoma automaticamente em <70%. */
  p3_vram_blocked:    boolean
}

export interface ModelInfo {
  name:         string
  size_vram_mb: number
}

export interface ModelEntry {
  name:          string
  /** "active" = carregado na VRAM; "available" = instalado mas não carregado */
  status:        'active' | 'available'
  /** VRAM em uso em MB; 0 se não carregado */
  size_vram_mb:  number
  /** Tamanho em disco em MB */
  size_disk_mb:  number
}

// backward-compat aliases
export type OllamaModelInfo  = ModelInfo
export type OllamaModelEntry = ModelEntry

export interface ModelSlot {
  app:        string
  model_type: string
  /** Label completo: "Mnemosyne — RAG", "KOSMOS — Análise", etc. */
  label:      string
  /** Label conciso do tipo funcional: "RAG/chat (Mnemosyne)", "Análise de artigos (KOSMOS)", etc. */
  slot_label: string
  /** Idiomas com melhor desempenho documentado, ex: ["zh","en"] para qwen2.5. Null = sem afinidade conhecida. */
  language_affinity: string[] | null
}

export interface RecommendedModel {
  model_name:          string
  slots:               ModelSlot[]
  for_profiles:        string[]
  for_current_profile: boolean
  is_installed:        boolean
  /** Modelo estático (model2vec) — não requer Ollama */
  is_static:           boolean
  size_disk_mb:        number
  rationale:           string
  /** Velocidade esperada no WorkPc. null nos demais perfis. */
  expected_speed_note: string | null
}

export interface PullProgress {
  model:     string
  status:    string
  completed: number | null
  total:     number | null
  done:      boolean
  error:     string | null
  /** Índice do arquivo atual (0-based). 0 para download de arquivo único. */
  file_index?: number
  /** Total de arquivos para download. 1 para download de arquivo único. */
  file_total?:  number
}

export interface EmbedCompatWarning {
  old_model: string
  new_model: string
  old_dims:  number
  new_dims:  number
}

export interface ModelAssignment {
  /** "mnemosyne" | "kosmos" | "akasha" | "embed" */
  app:               string
  /** "llm_rag" | "llm_analysis" | "llm_query" | "embed" | "image_ocr" */
  model_type:        string
  /** Label legível para a UI */
  label:             string
  current_model:     string
  recommended_model: string
  /** True se a usuária sobrescreveu o recomendado */
  is_custom:         boolean
  /** True se o modelo atual está instalado no Ollama */
  is_installed:      boolean
  /** VRAM estimada em MB (0 se modelo não instalado) */
  vram_required_mb:  number
  /** VRAM/RAM disponível no hardware atual em MB */
  vram_budget_mb:    number
  fits_hardware:     boolean
  /** True se o modelo pode ser baixado automaticamente via HUB */
  is_downloadable:   boolean
}

// ----------------------------------------------------------
//  HUB Navigation
// ----------------------------------------------------------

// ----------------------------------------------------------
//  Git — status e log da sync_root
// ----------------------------------------------------------

export interface GitFileStatus {
  /** Caminho relativo ao sync_root */
  path: string
  /** Código porcelain de 2 chars: "M ", " M", "??", "A ", "D ", etc. */
  status: string
}

export interface GitLogEntry {
  hash:    string
  date:    string
  message: string
  author:  string
}

export interface GitIncomingInfo {
  count:   number
  entries: GitLogEntry[]
}

// ----------------------------------------------------------
//  Memória pessoal
// ----------------------------------------------------------

export interface MemoryEntry {
  id:         number
  created_at: string
  type:       string
  content:    string
  tags:       string[]
  feedback:   string | null
  category?:  string
}

export interface CommEntry {
  id:              number
  source_app:      string
  content:         string
  importance:      number | null
  tags:            string[]
  sent_at:         string
  feedback:        string | null
  feedback_at:     string | null
  feedback_reason: string | null
}

// Item numa fila de insight entre AKASHA e Mnemosyne
export interface InsightQueueItem {
  // Mnemosyne → AKASHA (notify_akasha_insight)
  content?:          string
  // AKASHA → Mnemosyne (notify_mnemosyne_insight)
  summary?:          string
  akasha_thought?:   string
  topics?:           string[]
  sources?:          { url?: string; title?: string }[]
  // comum
  received_at:       string
  tags?:             string[]
}

// ----------------------------------------------------------
//  Fontes — domínios do ecossistema
// ----------------------------------------------------------

export interface DomainEntry {
  domain:       string
  label:        string
  library:      boolean
  feed:         boolean
  akasha_url:   string | null
  kosmos_feeds: string[]
}

// ----------------------------------------------------------
//  Interesses — perfil de tópicos compartilhado
// ----------------------------------------------------------

export interface TopicEntry {
  name:     string
  weight:   number
  sources:  string[]
  pinned:   boolean
  excluded: boolean
}

// ----------------------------------------------------------
//  HUB Navigation
// ----------------------------------------------------------

// ----------------------------------------------------------
//  Fine-tuning
// ----------------------------------------------------------

export interface FinetuneState {
  corpus_chunks_at_last_train: number
  last_cycle_at:               string    // ISO-8601 UTC ou ""
  current_model:               string
  prev_model:                  string
  current_step:                string    // "" = parado; "erro: ..." = falha
  examples_generated:          number
  last_train_loss:             number    // -1 se não disponível
  running:                     boolean
}

export type HubView = 'home' | 'writing' | 'reading' | 'projects'

export type HubSection = 'home' | 'logos' | 'atividade' | 'monitoramento' | 'git' | 'sync' | 'fontes' | 'interesses' | 'comunicacoes' | 'config'

export interface ModuleCard {
  id: HubView
  label: string
  description: string
  seed: number          // CosmosLayer seed
  configKey: keyof EcosystemConfig
  configField: string   // campo que deve estar preenchido para habilitar o card
}
