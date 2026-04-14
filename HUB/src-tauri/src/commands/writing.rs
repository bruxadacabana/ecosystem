// ============================================================
//  HUB — commands/writing.rs
//  Leitura read-only do vault AETHER.
//  Hierarquia: {vault}/{project_id}/project.json
//              {vault}/{project_id}/{book_id}/book.json
//              {vault}/{project_id}/{book_id}/{chapter_id}.md
// ============================================================

use crate::error::AppError;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ----------------------------------------------------------
//  Tipos espelhados do AETHER (subconjunto necessário)
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "snake_case")]
pub enum ProjectType {
    #[default]
    Single,
    Series,
    Fanfiction,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "snake_case")]
pub enum ChapterStatus {
    #[default]
    Draft,
    Revision,
    Final,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ChapterMeta {
    pub id: String,
    pub title: String,
    pub order: usize,
    pub status: ChapterStatus,
    pub synopsis: Option<String>,
    pub word_count: usize,
    #[serde(default)]
    pub trashed_at: Option<String>,
    #[serde(default)]
    pub word_goal: Option<usize>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Book {
    pub id: String,
    pub project_id: String,
    pub name: String,
    pub order: usize,
    pub chapters: Vec<ChapterMeta>,
    #[serde(default)]
    pub series_name: Option<String>,
    #[serde(default)]
    pub word_goal: Option<usize>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Project {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub project_type: ProjectType,
    pub default_book_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    #[serde(default)]
    pub subtitle: Option<String>,
    #[serde(default)]
    pub genre: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
}

// ----------------------------------------------------------
//  Commands
// ----------------------------------------------------------

/// Lista todos os projetos do vault AETHER.
/// Lê `{vault}/{uuid}/project.json` para cada subpasta que tenha esse arquivo.
#[tauri::command]
pub fn list_writing_projects(vault_path: String) -> Result<Vec<Project>, AppError> {
    let vault = PathBuf::from(&vault_path);
    if !vault.is_dir() {
        return Err(AppError::InvalidPath(format!(
            "Vault não encontrado: {vault_path}"
        )));
    }

    let mut projects: Vec<Project> = Vec::new();

    let entries = std::fs::read_dir(&vault)?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        // Ignorar pastas ocultas (.aether, .git, etc.)
        if path
            .file_name()
            .and_then(|n| n.to_str())
            .map(|n| n.starts_with('.'))
            .unwrap_or(false)
        {
            continue;
        }

        let project_file = path.join("project.json");
        if !project_file.exists() {
            continue;
        }

        match read_json::<Project>(&project_file) {
            Ok(p) => projects.push(p),
            Err(e) => {
                log::warn!("HUB: Ignorando project.json inválido em {:?}: {e}", path);
            }
        }
    }

    // Ordenar por nome
    projects.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));

    Ok(projects)
}

/// Lista todos os livros de um projeto.
/// Lê `{vault}/{project_id}/{uuid}/book.json` para cada subpasta.
#[tauri::command]
pub fn list_books(vault_path: String, project_id: String) -> Result<Vec<Book>, AppError> {
    let proj_dir = PathBuf::from(&vault_path).join(&project_id);
    if !proj_dir.is_dir() {
        return Err(AppError::NotFound(format!(
            "Projeto não encontrado: {project_id}"
        )));
    }

    let mut books: Vec<Book> = Vec::new();

    let entries = std::fs::read_dir(&proj_dir)?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        if path
            .file_name()
            .and_then(|n| n.to_str())
            .map(|n| n.starts_with('.'))
            .unwrap_or(false)
        {
            continue;
        }

        let book_file = path.join("book.json");
        if !book_file.exists() {
            continue;
        }

        match read_json::<Book>(&book_file) {
            Ok(mut b) => {
                // Filtrar capítulos na lixeira
                b.chapters.retain(|c| c.trashed_at.is_none());
                b.chapters.sort_by_key(|c| c.order);
                books.push(b);
            }
            Err(e) => {
                log::warn!("HUB: Ignorando book.json inválido em {:?}: {e}", path);
            }
        }
    }

    books.sort_by_key(|b| b.order);
    Ok(books)
}

/// Lê o conteúdo Markdown de um capítulo.
#[tauri::command]
pub fn read_chapter(
    vault_path: String,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<String, AppError> {
    let chapter_file = PathBuf::from(&vault_path)
        .join(&project_id)
        .join(&book_id)
        .join(format!("{chapter_id}.md"));

    if !chapter_file.exists() {
        return Err(AppError::NotFound(format!(
            "Capítulo não encontrado: {chapter_id}"
        )));
    }

    let content = std::fs::read_to_string(&chapter_file)?;
    Ok(content)
}

// ----------------------------------------------------------
//  Helpers
// ----------------------------------------------------------

fn read_json<T: for<'de> Deserialize<'de>>(path: &std::path::Path) -> Result<T, AppError> {
    let content = std::fs::read_to_string(path)?;
    let value = serde_json::from_str(&content)?;
    Ok(value)
}
