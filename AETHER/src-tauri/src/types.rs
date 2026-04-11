// ============================================================
//  AETHER — Tipos de dados
//
//  Hierarquia de armazenamento (modelo Obsidian):
//
//  AppData do sistema  →  app.json  (apenas caminho do vault)
//  {vault}/.aether/    →  config.json (preferências do usuário)
//  {vault}/{proj}/     →  project.json
//  {vault}/{proj}/{book}/  →  book.json  (inclui Vec<ChapterMeta>)
//  {vault}/{proj}/{book}/{chapter}.md  →  conteúdo puro
// ============================================================

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ----------------------------------------------------------
//  AppData — armazenado em AppData do sistema
//  Contém APENAS o caminho do vault. Nada mais.
//  Zero dados do usuário aqui.
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Default)]
pub struct AppData {
    pub vault_path: Option<PathBuf>,
}

// ----------------------------------------------------------
//  Tema
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "snake_case")]
pub enum Theme {
    #[default]
    Day,
    Dark,
}

// ----------------------------------------------------------
//  VaultConfig — armazenado em {vault}/.aether/config.json
//  Preferências do usuário: portáveis junto com o vault.
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct VaultConfig {
    pub theme: Theme,
    pub font_size: u8,
    pub line_height: f32,
    pub column_width: u16,
}

impl Default for VaultConfig {
    fn default() -> Self {
        VaultConfig {
            theme: Theme::Day,
            font_size: 16,
            line_height: 1.75,
            column_width: 680,
        }
    }
}

// ----------------------------------------------------------
//  Status de capítulo
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "snake_case")]
pub enum ChapterStatus {
    #[default]
    Draft,
    Revision,
    Final,
}

// ----------------------------------------------------------
//  ChapterMeta — armazenado dentro de book.json
//  O conteúdo em si fica em {chapter_id}.md
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ChapterMeta {
    pub id: String,
    pub title: String,
    pub order: usize,
    pub status: ChapterStatus,
    pub synopsis: Option<String>,
    /// Cache de contagem de palavras — recalculado ao salvar
    pub word_count: usize,
    /// Quando preenchido, indica que o capítulo está na lixeira.
    /// ISO 8601 da data em que foi movido para a lixeira.
    /// None = capítulo ativo; Some(_) = capítulo na lixeira.
    #[serde(default)]
    pub trashed_at: Option<String>,
    /// IDs de personagens vinculados a este capítulo (4.6)
    #[serde(default)]
    pub character_ids: Vec<String>,
    /// IDs de notas de worldbuilding vinculadas a este capítulo (4.6)
    #[serde(default)]
    pub note_ids: Vec<String>,
    /// Meta de palavras para este capítulo (5.1)
    #[serde(default)]
    pub word_goal: Option<usize>,
}

// ----------------------------------------------------------
//  Book — armazenado em {vault}/{proj}/{book_id}/book.json
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Book {
    pub id: String,
    pub project_id: String,
    pub name: String,
    pub order: usize,
    pub chapters: Vec<ChapterMeta>,
    /// Usado em projetos Fanfiction para agrupar livros numa saga.
    /// None = fanfic avulsa (standalone). Ignorado em Single/Series.
    #[serde(default)]
    pub series_name: Option<String>,
    /// Meta de palavras total para este livro (5.1)
    #[serde(default)]
    pub word_goal: Option<usize>,
}

/// Versão compacta para listagens (sem a lista de capítulos)
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BookMeta {
    pub id: String,
    pub name: String,
    pub order: usize,
    #[serde(default)]
    pub series_name: Option<String>,
}

impl From<&Book> for BookMeta {
    fn from(book: &Book) -> Self {
        BookMeta {
            id: book.id.clone(),
            name: book.name.clone(),
            order: book.order,
            series_name: book.series_name.clone(),
        }
    }
}

// ----------------------------------------------------------
//  Tipo de projeto
//  Single:      um livro único — binder mostra só capítulos.
//  Series:      múltiplos livros — Livros > Capítulos.
//  Fanfiction:  como Series, mas os livros podem ser agrupados
//               por série dentro do fandom (series_name em Book).
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "snake_case")]
pub enum ProjectType {
    #[default]
    Single,
    Series,
    Fanfiction,
}

// ----------------------------------------------------------
//  Project — armazenado em {vault}/{proj_id}/project.json
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Project {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub project_type: ProjectType,
    /// Para single: Some com o id do livro criado automaticamente.
    /// Para series: None (usuário cria livros manualmente).
    pub default_book_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,

    // Metadados opcionais — todos com #[serde(default)] para
    // retrocompatibilidade com project.json criados antes de 1.10.
    #[serde(default)]
    pub subtitle: Option<String>,
    #[serde(default)]
    pub genre: Option<String>,
    #[serde(default)]
    pub target_audience: Option<String>,
    #[serde(default)]
    pub language: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub has_magic_system: bool,
    #[serde(default)]
    pub tech_level: Option<String>,
    #[serde(default)]
    pub inspirations: Option<String>,
}

/// Alias — project.json serve tanto para metadados quanto para
/// listagem. Mantemos o tipo único para simplificar.
pub type ProjectMeta = Project;

// ----------------------------------------------------------
//  Campo customizável — usado em Character e WorldNote
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CustomField {
    pub label: String,
    pub value: String,
}

// ----------------------------------------------------------
//  Character — armazenado em {project_id}/characters/{id}.json
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Character {
    pub id: String,
    pub project_id: String,
    pub name: String,
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub fields: Vec<CustomField>,
    /// Caminho relativo à raiz do vault (ex: "{proj}/images/char_{id}_foto.png")
    #[serde(default)]
    pub image_path: Option<String>,
    /// IDs de capítulos vinculados a este personagem (4.6)
    #[serde(default)]
    pub chapter_ids: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

// ----------------------------------------------------------
//  Relationship — armazenado em {project_id}/characters/relationships.json
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Relationship {
    pub id: String,
    pub from_id: String,
    pub to_id: String,
    pub kind: String,
    #[serde(default)]
    pub note: Option<String>,
}

// ----------------------------------------------------------
//  WorldNote — armazenado em {project_id}/worldbuilding/{id}.json
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone, Default, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum WorldCategory {
    #[default]
    Location,
    Faction,
    Object,
    Concept,
    Other,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct WorldNote {
    pub id: String,
    pub project_id: String,
    pub name: String,
    pub category: WorldCategory,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub fields: Vec<CustomField>,
    /// Caminho relativo à raiz do vault
    #[serde(default)]
    pub image_path: Option<String>,
    /// IDs de capítulos vinculados a esta nota (4.6)
    #[serde(default)]
    pub chapter_ids: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

// ----------------------------------------------------------
//  Snapshot de capítulo (5.5)
//  Armazenado em {project}/{book}/snapshots/{id}.json
//  Cada arquivo contém metadados + conteúdo completo
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Snapshot {
    pub id: String,
    pub chapter_id: String,
    pub created_at: String,
    #[serde(default)]
    pub label: Option<String>,
    pub word_count: usize,
    /// Conteúdo Markdown completo no momento do snapshot
    pub content: String,
}

/// Versão sem conteúdo para listagens
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SnapshotMeta {
    pub id: String,
    pub chapter_id: String,
    pub created_at: String,
    #[serde(default)]
    pub label: Option<String>,
    pub word_count: usize,
}

impl From<&Snapshot> for SnapshotMeta {
    fn from(s: &Snapshot) -> Self {
        SnapshotMeta {
            id: s.id.clone(),
            chapter_id: s.chapter_id.clone(),
            created_at: s.created_at.clone(),
            label: s.label.clone(),
            word_count: s.word_count,
        }
    }
}

// ----------------------------------------------------------
//  Anotação inline (5.6)
//  Armazenada em {project}/{book}/{chapter_id}.annotations.json
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Annotation {
    pub id: String,
    pub chapter_id: String,
    pub text: String,
    /// Trecho de texto citado — usado para localizar no editor
    pub quote: String,
    pub created_at: String,
    #[serde(default)]
    pub resolved: bool,
}

// ----------------------------------------------------------
//  WritingSession — armazenado em {vault}/.aether/sessions.json
//  Registra sessões de escrita para streak e estatísticas (5.2/5.3/5.4)
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct WritingSession {
    pub id: String,
    pub project_id: String,
    pub book_id: String,
    pub chapter_id: String,
    /// ISO 8601 — início da sessão
    pub started_at: String,
    /// ISO 8601 — fim da sessão; None = sessão ainda ativa
    #[serde(default)]
    pub ended_at: Option<String>,
    /// Contagem de palavras quando a sessão começou
    pub words_at_start: usize,
    /// Contagem de palavras quando a sessão terminou
    #[serde(default)]
    pub words_at_end: usize,
    /// Meta de duração em minutos (opcional)
    #[serde(default)]
    pub goal_minutes: Option<u32>,
}

// ----------------------------------------------------------
//  TimelineEvent — armazenado em {project_id}/timeline.json
//  O arquivo contém Vec<TimelineEvent> ordenado por `order`.
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TimelineEvent {
    pub id: String,
    pub project_id: String,
    pub title: String,
    #[serde(default)]
    pub description: Option<String>,
    /// Rótulo de data livre (ex: "Ano 1024", "Capítulo 3", "Antes da guerra")
    pub date_label: String,
    pub order: usize,
    #[serde(default)]
    pub character_ids: Vec<String>,
    #[serde(default)]
    pub note_ids: Vec<String>,
    #[serde(default)]
    pub chapter_ids: Vec<String>,
}
