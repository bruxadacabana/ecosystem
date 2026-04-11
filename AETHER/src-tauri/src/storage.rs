// ============================================================
//  AETHER — Camada de armazenamento em disco
//
//  Toda função retorna Result<T, AppError>.
//  Nenhum dado é transmitido para servidores externos.
//  O vault pertence inteiramente ao usuário.
// ============================================================

use std::fs;
use std::path::{Path, PathBuf};

use chrono::Utc;
use uuid::Uuid;

use crate::error::AppError;
use crate::types::{
    Annotation, AppData, Book, BookMeta, Character, ChapterMeta, ChapterStatus, Project,
    Relationship, Snapshot, SnapshotMeta, TimelineEvent, VaultConfig, WorldNote, WritingSession,
};

const APP_DATA_FILE: &str = "app.json";
const AETHER_DIR: &str = ".aether";
const VAULT_CONFIG_FILE: &str = "config.json";
const PROJECT_FILE: &str = "project.json";
const BOOK_FILE: &str = "book.json";

// ----------------------------------------------------------
//  Utilitários internos
// ----------------------------------------------------------

fn now_iso() -> String {
    Utc::now().to_rfc3339()
}

fn new_id() -> String {
    Uuid::new_v4().to_string()
}

fn read_json<T>(path: &Path) -> Result<T, AppError>
where
    T: serde::de::DeserializeOwned,
{
    let content = fs::read_to_string(path)?;
    let value: T = serde_json::from_str(&content)?;
    Ok(value)
}

fn write_json<T>(path: &Path, value: &T) -> Result<(), AppError>
where
    T: serde::Serialize,
{
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let content = serde_json::to_string_pretty(value)?;
    fs::write(path, content)?;
    Ok(())
}

// ----------------------------------------------------------
//  AppData (armazenado no diretório de dados do sistema)
//  Contém APENAS o caminho do vault — zero dados pessoais.
// ----------------------------------------------------------

pub fn load_app_data(app_data_dir: &Path) -> Result<AppData, AppError> {
    let path = app_data_dir.join(APP_DATA_FILE);
    if !path.exists() {
        return Ok(AppData::default());
    }
    read_json(&path)
}

pub fn save_app_data(app_data_dir: &Path, data: &AppData) -> Result<(), AppError> {
    let path = app_data_dir.join(APP_DATA_FILE);
    write_json(&path, data)
}

// ----------------------------------------------------------
//  VaultConfig ({vault}/.aether/config.json)
//  Preferências do usuário — portáveis com o vault.
// ----------------------------------------------------------

pub fn load_vault_config(vault_path: &Path) -> Result<VaultConfig, AppError> {
    let path = vault_path.join(AETHER_DIR).join(VAULT_CONFIG_FILE);
    if !path.exists() {
        return Ok(VaultConfig::default());
    }
    read_json(&path)
}

pub fn save_vault_config(vault_path: &Path, config: &VaultConfig) -> Result<(), AppError> {
    let path = vault_path.join(AETHER_DIR).join(VAULT_CONFIG_FILE);
    write_json(&path, config)
}

// ----------------------------------------------------------
//  Projetos ({vault}/{project_id}/project.json)
// ----------------------------------------------------------

pub fn project_dir(vault_path: &Path, project_id: &str) -> PathBuf {
    vault_path.join(project_id)
}

pub fn list_projects(vault_path: &Path) -> Result<Vec<Project>, AppError> {
    if !vault_path.exists() {
        return Err(AppError::VaultNotFound(
            vault_path.to_string_lossy().into_owned(),
        ));
    }

    let mut projects = Vec::new();

    for entry in fs::read_dir(vault_path)? {
        let entry = entry?;
        let path = entry.path();

        if !path.is_dir() {
            continue;
        }
        if entry.file_name() == AETHER_DIR {
            continue;
        }

        let project_json = path.join(PROJECT_FILE);
        if project_json.exists() {
            match read_json::<Project>(&project_json) {
                Ok(project) => projects.push(project),
                Err(e) => {
                    log::warn!(
                        "Ignorando pasta '{}': {}",
                        path.display(),
                        e
                    );
                }
            }
        }
    }

    // Mais recente primeiro
    projects.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(projects)
}

pub fn create_project(
    vault_path: &Path,
    name: &str,
    project_type: crate::types::ProjectType,
    description: Option<String>,
    subtitle: Option<String>,
    genre: Option<String>,
    target_audience: Option<String>,
    language: Option<String>,
    tags: Option<Vec<String>>,
    has_magic_system: Option<bool>,
    tech_level: Option<String>,
    inspirations: Option<String>,
) -> Result<Project, AppError> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O nome do projeto não pode ser vazio.".into(),
        ));
    }

    let id = new_id();
    let now = now_iso();
    let dir = project_dir(vault_path, &id);

    if dir.exists() {
        return Err(AppError::AlreadyExists(id.clone()));
    }

    fs::create_dir_all(&dir)?;

    // Livro único: criar livro automaticamente com mesmo nome do projeto
    let default_book_id = match project_type {
        crate::types::ProjectType::Single => {
            let book = Book {
                id: new_id(),
                project_id: id.clone(),
                name: trimmed.to_owned(),
                order: 0,
                chapters: Vec::new(),
                series_name: None,
                word_goal: None,
            };
            let book_dir = dir.join(&book.id);
            fs::create_dir_all(&book_dir)?;
            write_json(&book_dir.join(BOOK_FILE), &book)?;
            Some(book.id)
        }
        crate::types::ProjectType::Series | crate::types::ProjectType::Fanfiction => None,
    };

    let project = Project {
        id: id.clone(),
        name: trimmed.to_owned(),
        description,
        project_type,
        default_book_id,
        created_at: now.clone(),
        updated_at: now,
        subtitle,
        genre,
        target_audience,
        language,
        tags: tags.unwrap_or_default(),
        has_magic_system: has_magic_system.unwrap_or(false),
        tech_level,
        inspirations,
    };

    write_json(&dir.join(PROJECT_FILE), &project)?;
    Ok(project)
}

pub fn load_project(vault_path: &Path, project_id: &str) -> Result<Project, AppError> {
    let path = project_dir(vault_path, project_id).join(PROJECT_FILE);
    if !path.exists() {
        return Err(AppError::ProjectNotFound(project_id.to_owned()));
    }
    read_json(&path)
}

pub fn save_project(vault_path: &Path, project: &Project) -> Result<(), AppError> {
    let path = project_dir(vault_path, &project.id).join(PROJECT_FILE);
    write_json(&path, project)
}

pub fn delete_project(vault_path: &Path, project_id: &str) -> Result<(), AppError> {
    let dir = project_dir(vault_path, project_id);
    if !dir.exists() {
        return Err(AppError::ProjectNotFound(project_id.to_owned()));
    }
    fs::remove_dir_all(&dir)?;
    Ok(())
}

// ----------------------------------------------------------
//  Livros ({vault}/{project_id}/{book_id}/book.json)
// ----------------------------------------------------------

pub fn book_dir(vault_path: &Path, project_id: &str, book_id: &str) -> PathBuf {
    project_dir(vault_path, project_id).join(book_id)
}

pub fn list_books(vault_path: &Path, project_id: &str) -> Result<Vec<BookMeta>, AppError> {
    let proj_dir = project_dir(vault_path, project_id);
    if !proj_dir.exists() {
        return Err(AppError::ProjectNotFound(project_id.to_owned()));
    }

    let mut books = Vec::new();

    for entry in fs::read_dir(&proj_dir)? {
        let entry = entry?;
        let path = entry.path();

        if !path.is_dir() {
            continue;
        }

        let book_json = path.join(BOOK_FILE);
        if book_json.exists() {
            match read_json::<Book>(&book_json) {
                Ok(book) => books.push(BookMeta::from(&book)),
                Err(e) => {
                    log::warn!(
                        "Ignorando pasta de livro '{}': {}",
                        path.display(),
                        e
                    );
                }
            }
        }
    }

    books.sort_by_key(|b| b.order);
    Ok(books)
}

pub fn create_book(
    vault_path: &Path,
    project_id: &str,
    name: &str,
    series_name: Option<String>,
) -> Result<BookMeta, AppError> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O nome do livro não pode ser vazio.".into(),
        ));
    }

    let existing = list_books(vault_path, project_id)?;
    let next_order = existing.len();

    let id = new_id();
    let dir = book_dir(vault_path, project_id, &id);

    let book = Book {
        id: id.clone(),
        project_id: project_id.to_owned(),
        name: trimmed.to_owned(),
        order: next_order,
        chapters: Vec::new(),
        series_name,
        word_goal: None,
    };

    fs::create_dir_all(&dir)?;
    write_json(&dir.join(BOOK_FILE), &book)?;

    // Atualizar updated_at do projeto
    touch_project(vault_path, project_id)?;

    Ok(BookMeta::from(&book))
}

pub fn load_book(vault_path: &Path, project_id: &str, book_id: &str) -> Result<Book, AppError> {
    let path = book_dir(vault_path, project_id, book_id).join(BOOK_FILE);
    if !path.exists() {
        return Err(AppError::BookNotFound(book_id.to_owned()));
    }
    read_json(&path)
}

pub fn save_book(vault_path: &Path, book: &Book) -> Result<(), AppError> {
    let path = book_dir(vault_path, &book.project_id, &book.id).join(BOOK_FILE);
    write_json(&path, book)
}

pub fn delete_book(vault_path: &Path, project_id: &str, book_id: &str) -> Result<(), AppError> {
    let dir = book_dir(vault_path, project_id, book_id);
    if !dir.exists() {
        return Err(AppError::BookNotFound(book_id.to_owned()));
    }
    fs::remove_dir_all(&dir)?;
    touch_project(vault_path, project_id)?;
    Ok(())
}

// ----------------------------------------------------------
//  Capítulos ({vault}/{proj}/{book}/{chapter_id}.md)
//  Metadados ficam em book.json. Conteúdo em .md puro.
// ----------------------------------------------------------

pub fn chapter_path(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> PathBuf {
    book_dir(vault_path, project_id, book_id).join(format!("{}.md", chapter_id))
}

pub fn create_chapter(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    title: &str,
) -> Result<ChapterMeta, AppError> {
    let trimmed = title.trim();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O título do capítulo não pode ser vazio.".into(),
        ));
    }

    let mut book = load_book(vault_path, project_id, book_id)?;
    // Ordem baseada nos capítulos ativos (não na lixeira)
    let next_order = book.chapters.iter().filter(|c| c.trashed_at.is_none()).count();
    let id = new_id();

    let meta = ChapterMeta {
        id: id.clone(),
        title: trimmed.to_owned(),
        order: next_order,
        status: ChapterStatus::default(),
        synopsis: None,
        word_count: 0,
        trashed_at: None,
        character_ids: vec![],
        note_ids: vec![],
        word_goal: None,
    };

    // Criar arquivo .md vazio
    let md_path = chapter_path(vault_path, project_id, book_id, &id);
    fs::write(&md_path, "")?;

    book.chapters.push(meta.clone());
    save_book(vault_path, &book)?;
    touch_project(vault_path, project_id)?;

    Ok(meta)
}

pub fn read_chapter(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<String, AppError> {
    let path = chapter_path(vault_path, project_id, book_id, chapter_id);
    if !path.exists() {
        return Err(AppError::ChapterNotFound(chapter_id.to_owned()));
    }
    Ok(fs::read_to_string(&path)?)
}

pub fn save_chapter(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    content: &str,
) -> Result<(), AppError> {
    let path = chapter_path(vault_path, project_id, book_id, chapter_id);
    if !path.exists() {
        return Err(AppError::ChapterNotFound(chapter_id.to_owned()));
    }

    fs::write(&path, content)?;

    // Atualizar word_count no book.json
    let word_count = count_words(content);
    let mut book = load_book(vault_path, project_id, book_id)?;
    if let Some(meta) = book.chapters.iter_mut().find(|c| c.id == chapter_id) {
        meta.word_count = word_count;
    }
    save_book(vault_path, &book)?;
    touch_project(vault_path, project_id)?;

    Ok(())
}

pub fn delete_chapter(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<(), AppError> {
    let path = chapter_path(vault_path, project_id, book_id, chapter_id);
    if !path.exists() {
        return Err(AppError::ChapterNotFound(chapter_id.to_owned()));
    }

    fs::remove_file(&path)?;

    let mut book = load_book(vault_path, project_id, book_id)?;
    book.chapters.retain(|c| c.id != chapter_id);
    // Renormalizar order
    for (i, chapter) in book.chapters.iter_mut().enumerate() {
        chapter.order = i;
    }
    save_book(vault_path, &book)?;
    touch_project(vault_path, project_id)?;

    Ok(())
}

pub fn reorder_chapters(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    ordered_ids: &[String],
) -> Result<(), AppError> {
    let mut book = load_book(vault_path, project_id, book_id)?;

    for (new_order, chapter_id) in ordered_ids.iter().enumerate() {
        if let Some(meta) = book.chapters.iter_mut().find(|c| &c.id == chapter_id) {
            meta.order = new_order;
        } else {
            return Err(AppError::ChapterNotFound(chapter_id.clone()));
        }
    }

    book.chapters.sort_by_key(|c| c.order);
    save_book(vault_path, &book)?;
    Ok(())
}

// ----------------------------------------------------------
//  Lixeira — soft delete de capítulos
// ----------------------------------------------------------

/// Move um capítulo para a lixeira (soft delete).
/// O arquivo .md e o capítulo em book.json são preservados;
/// apenas `trashed_at` é preenchido com a data/hora atual.
pub fn trash_chapter(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<ChapterMeta, AppError> {
    let mut book = load_book(vault_path, project_id, book_id)?;

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| AppError::ChapterNotFound(chapter_id.to_owned()))?;

    if meta.trashed_at.is_some() {
        // Já está na lixeira — retorna sem alterar
        return Ok(meta.clone());
    }

    meta.trashed_at = Some(now_iso());
    let updated = meta.clone();

    save_book(vault_path, &book)?;
    touch_project(vault_path, project_id)?;
    Ok(updated)
}

/// Restaura um capítulo da lixeira para a posição final dos capítulos ativos.
pub fn restore_chapter(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<ChapterMeta, AppError> {
    let mut book = load_book(vault_path, project_id, book_id)?;

    // Calcular a próxima ordem entre os capítulos ativos
    let active_count = book.chapters.iter().filter(|c| c.trashed_at.is_none()).count();

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| AppError::ChapterNotFound(chapter_id.to_owned()))?;

    meta.trashed_at = None;
    meta.order = active_count; // Vai para o fim da lista ativa
    let updated = meta.clone();

    save_book(vault_path, &book)?;
    touch_project(vault_path, project_id)?;
    Ok(updated)
}

/// Lista os capítulos na lixeira de um livro.
pub fn list_trash(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
) -> Result<Vec<ChapterMeta>, AppError> {
    let book = load_book(vault_path, project_id, book_id)?;
    let mut trashed: Vec<ChapterMeta> = book
        .chapters
        .into_iter()
        .filter(|c| c.trashed_at.is_some())
        .collect();
    // Mais recentes primeiro
    trashed.sort_by(|a, b| {
        b.trashed_at.as_deref().unwrap_or("").cmp(a.trashed_at.as_deref().unwrap_or(""))
    });
    Ok(trashed)
}

// ----------------------------------------------------------
//  Scratchpad ({chapter_id}.scratch.md no mesmo diretório)
// ----------------------------------------------------------

fn scratchpad_path(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> PathBuf {
    book_dir(vault_path, project_id, book_id).join(format!("{}.scratch.md", chapter_id))
}

/// Lê o scratchpad de um capítulo. Retorna string vazia se não existir.
pub fn read_scratchpad(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<String, AppError> {
    let path = scratchpad_path(vault_path, project_id, book_id, chapter_id);
    if !path.exists() {
        return Ok(String::new());
    }
    Ok(fs::read_to_string(&path)?)
}

/// Salva o scratchpad de um capítulo.
pub fn save_scratchpad(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    content: &str,
) -> Result<(), AppError> {
    let path = scratchpad_path(vault_path, project_id, book_id, chapter_id);
    // Garante que o diretório existe (segurança)
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&path, content)?;
    Ok(())
}

// ----------------------------------------------------------
//  Personagens ({project_id}/characters/{char_id}.json)
// ----------------------------------------------------------

pub fn characters_dir(vault_path: &Path, project_id: &str) -> PathBuf {
    project_dir(vault_path, project_id).join("characters")
}

fn relationships_path(vault_path: &Path, project_id: &str) -> PathBuf {
    characters_dir(vault_path, project_id).join("relationships.json")
}

pub fn list_characters(
    vault_path: &Path,
    project_id: &str,
) -> Result<Vec<Character>, AppError> {
    let dir = characters_dir(vault_path, project_id);
    if !dir.exists() {
        return Ok(vec![]);
    }
    let mut characters: Vec<Character> = Vec::new();
    for entry in fs::read_dir(&dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("json")
            && path.file_stem().and_then(|s| s.to_str()) != Some("relationships")
        {
            match read_json::<Character>(&path) {
                Ok(c) => characters.push(c),
                Err(e) => log::warn!("Falha ao ler personagem {:?}: {}", path, e),
            }
        }
    }
    characters.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    Ok(characters)
}

pub fn create_character(
    vault_path: &Path,
    project_id: &str,
    name: &str,
) -> Result<Character, AppError> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O nome do personagem não pode ser vazio.".into(),
        ));
    }
    let dir = characters_dir(vault_path, project_id);
    fs::create_dir_all(&dir)?;

    let id = new_id();
    let now = now_iso();
    let character = Character {
        id: id.clone(),
        project_id: project_id.to_owned(),
        name: trimmed.to_owned(),
        role: None,
        description: None,
        fields: vec![],
        image_path: None,
        chapter_ids: vec![],
        created_at: now.clone(),
        updated_at: now,
    };

    write_json(&dir.join(format!("{}.json", id)), &character)?;
    touch_project(vault_path, project_id)?;
    Ok(character)
}

pub fn load_character(
    vault_path: &Path,
    project_id: &str,
    character_id: &str,
) -> Result<Character, AppError> {
    let path = characters_dir(vault_path, project_id).join(format!("{}.json", character_id));
    if !path.exists() {
        return Err(AppError::NotFound(format!("Personagem '{character_id}' não encontrado.")));
    }
    read_json(&path)
}

pub fn save_character(
    vault_path: &Path,
    project_id: &str,
    mut character: Character,
) -> Result<Character, AppError> {
    let dir = characters_dir(vault_path, project_id);
    fs::create_dir_all(&dir)?;
    character.updated_at = now_iso();
    write_json(&dir.join(format!("{}.json", character.id)), &character)?;
    touch_project(vault_path, project_id)?;
    Ok(character)
}

pub fn delete_character(
    vault_path: &Path,
    project_id: &str,
    character_id: &str,
) -> Result<(), AppError> {
    let path = characters_dir(vault_path, project_id).join(format!("{}.json", character_id));
    if !path.exists() {
        return Err(AppError::NotFound(format!("Personagem '{character_id}' não encontrado.")));
    }
    fs::remove_file(&path)?;
    touch_project(vault_path, project_id)?;
    Ok(())
}

// ----------------------------------------------------------
//  Relacionamentos ({project_id}/characters/relationships.json)
// ----------------------------------------------------------

pub fn load_relationships(
    vault_path: &Path,
    project_id: &str,
) -> Result<Vec<Relationship>, AppError> {
    let path = relationships_path(vault_path, project_id);
    if !path.exists() {
        return Ok(vec![]);
    }
    read_json(&path)
}

pub fn save_relationships(
    vault_path: &Path,
    project_id: &str,
    relationships: &[Relationship],
) -> Result<(), AppError> {
    let dir = characters_dir(vault_path, project_id);
    fs::create_dir_all(&dir)?;
    let rels_vec: Vec<Relationship> = relationships.to_vec();
    write_json(&relationships_path(vault_path, project_id), &rels_vec)?;
    Ok(())
}

// ----------------------------------------------------------
//  Worldbuilding ({project_id}/worldbuilding/{note_id}.json)
// ----------------------------------------------------------

pub fn worldbuilding_dir(vault_path: &Path, project_id: &str) -> PathBuf {
    project_dir(vault_path, project_id).join("worldbuilding")
}

pub fn list_world_notes(
    vault_path: &Path,
    project_id: &str,
) -> Result<Vec<WorldNote>, AppError> {
    let dir = worldbuilding_dir(vault_path, project_id);
    if !dir.exists() {
        return Ok(vec![]);
    }
    let mut notes: Vec<WorldNote> = Vec::new();
    for entry in fs::read_dir(&dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("json") {
            match read_json::<WorldNote>(&path) {
                Ok(n) => notes.push(n),
                Err(e) => log::warn!("Falha ao ler nota {:?}: {}", path, e),
            }
        }
    }
    notes.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    Ok(notes)
}

pub fn create_world_note(
    vault_path: &Path,
    project_id: &str,
    name: &str,
    category: crate::types::WorldCategory,
) -> Result<WorldNote, AppError> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O nome da nota não pode ser vazio.".into(),
        ));
    }
    let dir = worldbuilding_dir(vault_path, project_id);
    fs::create_dir_all(&dir)?;

    let id = new_id();
    let now = now_iso();
    let note = WorldNote {
        id: id.clone(),
        project_id: project_id.to_owned(),
        name: trimmed.to_owned(),
        category,
        description: None,
        fields: vec![],
        image_path: None,
        chapter_ids: vec![],
        created_at: now.clone(),
        updated_at: now,
    };

    write_json(&dir.join(format!("{}.json", id)), &note)?;
    touch_project(vault_path, project_id)?;
    Ok(note)
}

pub fn load_world_note(
    vault_path: &Path,
    project_id: &str,
    note_id: &str,
) -> Result<WorldNote, AppError> {
    let path = worldbuilding_dir(vault_path, project_id).join(format!("{}.json", note_id));
    if !path.exists() {
        return Err(AppError::NotFound(format!("Nota '{note_id}' não encontrada.")));
    }
    read_json(&path)
}

pub fn save_world_note(
    vault_path: &Path,
    project_id: &str,
    mut note: WorldNote,
) -> Result<WorldNote, AppError> {
    let dir = worldbuilding_dir(vault_path, project_id);
    fs::create_dir_all(&dir)?;
    note.updated_at = now_iso();
    write_json(&dir.join(format!("{}.json", note.id)), &note)?;
    touch_project(vault_path, project_id)?;
    Ok(note)
}

pub fn delete_world_note(
    vault_path: &Path,
    project_id: &str,
    note_id: &str,
) -> Result<(), AppError> {
    let path = worldbuilding_dir(vault_path, project_id).join(format!("{}.json", note_id));
    if !path.exists() {
        return Err(AppError::NotFound(format!("Nota '{note_id}' não encontrada.")));
    }
    fs::remove_file(&path)?;
    touch_project(vault_path, project_id)?;
    Ok(())
}

// ----------------------------------------------------------
//  Linha do tempo ({project_id}/timeline.json)
//  Armazena Vec<TimelineEvent> completo.
// ----------------------------------------------------------

fn timeline_path(vault_path: &Path, project_id: &str) -> PathBuf {
    project_dir(vault_path, project_id).join("timeline.json")
}

pub fn load_timeline(
    vault_path: &Path,
    project_id: &str,
) -> Result<Vec<TimelineEvent>, AppError> {
    let path = timeline_path(vault_path, project_id);
    if !path.exists() {
        return Ok(vec![]);
    }
    read_json(&path)
}

pub fn save_timeline(
    vault_path: &Path,
    project_id: &str,
    events: &[TimelineEvent],
) -> Result<(), AppError> {
    let events_vec: Vec<TimelineEvent> = events.to_vec();
    write_json(&timeline_path(vault_path, project_id), &events_vec)
}

// ----------------------------------------------------------
//  Imagens ({project_id}/images/)
// ----------------------------------------------------------

pub fn images_dir(vault_path: &Path, project_id: &str) -> PathBuf {
    project_dir(vault_path, project_id).join("images")
}

/// Copia um arquivo de imagem para o diretório de imagens do projeto.
/// Retorna o caminho relativo ao vault (ex: "{project_id}/images/char_{id}_foto.png").
pub fn attach_image(
    vault_path: &Path,
    project_id: &str,
    entity_prefix: &str,
    source_path: &Path,
) -> Result<String, AppError> {
    let dir = images_dir(vault_path, project_id);
    fs::create_dir_all(&dir)?;

    let original_name = source_path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| AppError::InvalidPath("Caminho de imagem inválido.".into()))?;

    let file_name = format!("{}_{}", entity_prefix, original_name);
    let dest = dir.join(&file_name);
    fs::copy(source_path, &dest)?;

    // Retornar caminho relativo ao vault
    Ok(format!("{}/images/{}", project_id, file_name))
}

/// Lê uma imagem e retorna como base64.
pub fn load_image_base64(
    vault_path: &Path,
    relative_path: &str,
) -> Result<String, AppError> {
    let path = vault_path.join(relative_path);
    if !path.exists() {
        return Err(AppError::NotFound(format!("Imagem '{relative_path}' não encontrada.")));
    }
    let bytes = fs::read(&path)?;
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("png")
        .to_lowercase();
    let mime = match ext.as_str() {
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        _ => "image/png",
    };
    let b64 = base64_encode(&bytes);
    Ok(format!("data:{};base64,{}", mime, b64))
}

/// Remove um arquivo de imagem do disco.
pub fn remove_image(
    vault_path: &Path,
    relative_path: &str,
) -> Result<(), AppError> {
    let path = vault_path.join(relative_path);
    if path.exists() {
        fs::remove_file(&path)?;
    }
    Ok(())
}

/// Codificação Base64 simples sem dependência externa.
fn base64_encode(data: &[u8]) -> String {
    const CHARS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = chunk.get(1).copied().unwrap_or(0) as u32;
        let b2 = chunk.get(2).copied().unwrap_or(0) as u32;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(CHARS[((n >> 18) & 0x3f) as usize] as char);
        out.push(CHARS[((n >> 12) & 0x3f) as usize] as char);
        out.push(if chunk.len() > 1 { CHARS[((n >> 6) & 0x3f) as usize] as char } else { '=' });
        out.push(if chunk.len() > 2 { CHARS[(n & 0x3f) as usize] as char } else { '=' });
    }
    out
}

// ----------------------------------------------------------
//  Utilitários internos
// ----------------------------------------------------------

pub fn touch_project_pub(vault_path: &Path, project_id: &str) -> Result<(), AppError> {
    touch_project(vault_path, project_id)
}

fn touch_project(vault_path: &Path, project_id: &str) -> Result<(), AppError> {
    let path = project_dir(vault_path, project_id).join(PROJECT_FILE);
    if !path.exists() {
        return Err(AppError::ProjectNotFound(project_id.to_owned()));
    }
    let mut project: Project = read_json(&path)?;
    project.updated_at = now_iso();
    write_json(&path, &project)
}

fn count_words(text: &str) -> usize {
    text.split_whitespace().count()
}

// ----------------------------------------------------------
//  Sessões de escrita (5.2/5.3/5.4)
//  Armazenadas em {vault}/.aether/sessions.json
// ----------------------------------------------------------

fn sessions_path(vault_path: &Path) -> PathBuf {
    vault_path.join(AETHER_DIR).join("sessions.json")
}

pub fn load_sessions(vault_path: &Path) -> Result<Vec<WritingSession>, AppError> {
    let path = sessions_path(vault_path);
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_json(&path)
}

pub fn save_sessions(vault_path: &Path, sessions: &[WritingSession]) -> Result<(), AppError> {
    let vec: Vec<WritingSession> = sessions.to_vec();
    write_json(&sessions_path(vault_path), &vec)
}

/// Cria uma nova sessão e persiste na lista.
pub fn start_session(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    words_at_start: usize,
    goal_minutes: Option<u32>,
) -> Result<WritingSession, AppError> {
    let session = WritingSession {
        id: new_id(),
        project_id: project_id.to_owned(),
        book_id: book_id.to_owned(),
        chapter_id: chapter_id.to_owned(),
        started_at: now_iso(),
        ended_at: None,
        words_at_start,
        words_at_end: 0,
        goal_minutes,
    };
    let mut sessions = load_sessions(vault_path)?;
    sessions.push(session.clone());
    save_sessions(vault_path, &sessions)?;
    Ok(session)
}

/// Encerra uma sessão existente com a contagem final de palavras.
pub fn end_session(
    vault_path: &Path,
    session_id: &str,
    words_at_end: usize,
) -> Result<WritingSession, AppError> {
    let mut sessions = load_sessions(vault_path)?;
    let session = sessions
        .iter_mut()
        .find(|s| s.id == session_id)
        .ok_or_else(|| AppError::NotFound(format!("Sessão não encontrada: {session_id}")))?;
    session.ended_at = Some(now_iso());
    session.words_at_end = words_at_end;
    let result = session.clone();
    save_sessions(vault_path, &sessions)?;
    Ok(result)
}

// ----------------------------------------------------------
//  Snapshots de capítulo (5.5)
//  {project}/{book}/snapshots/{id}.json
// ----------------------------------------------------------

fn snapshots_dir(vault_path: &Path, project_id: &str, book_id: &str) -> PathBuf {
    book_dir(vault_path, project_id, book_id).join("snapshots")
}

pub fn list_snapshots(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<Vec<SnapshotMeta>, AppError> {
    let dir = snapshots_dir(vault_path, project_id, book_id);
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut metas: Vec<SnapshotMeta> = Vec::new();
    for entry in fs::read_dir(&dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let snap: Snapshot = match read_json(&path) {
            Ok(s) => s,
            Err(_) => continue,
        };
        if snap.chapter_id == chapter_id {
            metas.push(SnapshotMeta::from(&snap));
        }
    }
    // Ordenar por data decrescente
    metas.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    Ok(metas)
}

pub fn create_snapshot(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    label: Option<String>,
) -> Result<SnapshotMeta, AppError> {
    // Ler conteúdo atual do capítulo
    let content = read_chapter(vault_path, project_id, book_id, chapter_id)
        .unwrap_or_default();
    let word_count = count_words(&content);

    let snap = Snapshot {
        id: new_id(),
        chapter_id: chapter_id.to_owned(),
        created_at: now_iso(),
        label,
        word_count,
        content,
    };

    let dir = snapshots_dir(vault_path, project_id, book_id);
    fs::create_dir_all(&dir)?;
    write_json(&dir.join(format!("{}.json", snap.id)), &snap)?;

    Ok(SnapshotMeta::from(&snap))
}

pub fn load_snapshot_content(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    snapshot_id: &str,
) -> Result<String, AppError> {
    let path = snapshots_dir(vault_path, project_id, book_id).join(format!("{snapshot_id}.json"));
    if !path.exists() {
        return Err(AppError::NotFound(format!("Snapshot não encontrado: {snapshot_id}")));
    }
    let snap: Snapshot = read_json(&path)?;
    Ok(snap.content)
}

pub fn restore_snapshot(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    snapshot_id: &str,
) -> Result<(), AppError> {
    let content = load_snapshot_content(vault_path, project_id, book_id, snapshot_id)?;
    save_chapter(vault_path, project_id, book_id, chapter_id, &content)
}

pub fn delete_snapshot(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    snapshot_id: &str,
) -> Result<(), AppError> {
    let path = snapshots_dir(vault_path, project_id, book_id).join(format!("{snapshot_id}.json"));
    if path.exists() {
        fs::remove_file(&path)?;
    }
    Ok(())
}

// ----------------------------------------------------------
//  Anotações inline (5.6)
//  {project}/{book}/{chapter_id}.annotations.json
// ----------------------------------------------------------

fn annotations_path(vault_path: &Path, project_id: &str, book_id: &str, chapter_id: &str) -> PathBuf {
    book_dir(vault_path, project_id, book_id).join(format!("{chapter_id}.annotations.json"))
}

pub fn load_annotations(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
) -> Result<Vec<Annotation>, AppError> {
    let path = annotations_path(vault_path, project_id, book_id, chapter_id);
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_json(&path)
}

fn save_annotations(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    annotations: &[Annotation],
) -> Result<(), AppError> {
    let vec: Vec<Annotation> = annotations.to_vec();
    write_json(
        &annotations_path(vault_path, project_id, book_id, chapter_id),
        &vec,
    )
}

pub fn create_annotation(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    text: &str,
    quote: &str,
) -> Result<Annotation, AppError> {
    let mut annotations = load_annotations(vault_path, project_id, book_id, chapter_id)?;
    let ann = Annotation {
        id: new_id(),
        chapter_id: chapter_id.to_owned(),
        text: text.to_owned(),
        quote: quote.to_owned(),
        created_at: now_iso(),
        resolved: false,
    };
    annotations.push(ann.clone());
    save_annotations(vault_path, project_id, book_id, chapter_id, &annotations)?;
    Ok(ann)
}

pub fn update_annotation(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    annotation_id: &str,
    text: &str,
    resolved: bool,
) -> Result<Annotation, AppError> {
    let mut annotations = load_annotations(vault_path, project_id, book_id, chapter_id)?;
    let ann = annotations
        .iter_mut()
        .find(|a| a.id == annotation_id)
        .ok_or_else(|| AppError::NotFound(format!("Anotação não encontrada: {annotation_id}")))?;
    ann.text = text.to_owned();
    ann.resolved = resolved;
    let updated = ann.clone();
    save_annotations(vault_path, project_id, book_id, chapter_id, &annotations)?;
    Ok(updated)
}

pub fn delete_annotation(
    vault_path: &Path,
    project_id: &str,
    book_id: &str,
    chapter_id: &str,
    annotation_id: &str,
) -> Result<(), AppError> {
    let mut annotations = load_annotations(vault_path, project_id, book_id, chapter_id)?;
    annotations.retain(|a| a.id != annotation_id);
    save_annotations(vault_path, project_id, book_id, chapter_id, &annotations)
}
