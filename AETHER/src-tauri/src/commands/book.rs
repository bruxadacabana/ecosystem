// ============================================================
//  AETHER — Commands Tauri: Livros
//  CRUD de livros dentro de um projeto.
//  Toda função retorna Result<T, AppError> — sem .unwrap().
// ============================================================

use tauri::State;

use crate::{
    commands::project::require_vault,
    error::AppError,
    storage,
    types::{Book, BookMeta},
    AppState,
};

/// Lista todos os livros de um projeto, ordenados por `order`.
#[tauri::command]
pub fn list_books(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Vec<BookMeta>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_books(&vault, &project_id)
}

/// Cria um novo livro no projeto.
/// series_name: usado em projetos Fanfiction para agrupar livros numa saga.
#[tauri::command]
pub fn create_book(
    state: State<'_, AppState>,
    project_id: String,
    name: String,
    series_name: Option<String>,
) -> Result<BookMeta, AppError> {
    let vault = require_vault(&state)?;
    let series = series_name.and_then(|s| {
        let t = s.trim().to_owned();
        if t.is_empty() { None } else { Some(t) }
    });
    storage::create_book(&vault, &project_id, &name, series)
}

/// Carrega um livro completo com apenas os capítulos ativos (não na lixeira).
#[tauri::command]
pub fn open_book(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
) -> Result<Book, AppError> {
    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;
    // Filtrar capítulos na lixeira — a lixeira é gerenciada via list_trash
    book.chapters.retain(|c| c.trashed_at.is_none());
    Ok(book)
}

/// Atualiza o nome e/ou series_name de um livro.
#[tauri::command]
pub fn update_book(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    name: String,
    series_name: Option<String>,
) -> Result<BookMeta, AppError> {
    let trimmed = name.trim().to_owned();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O nome do livro não pode ser vazio.".into(),
        ));
    }

    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;
    book.name = trimmed;
    // series_name: None = não alterar; Some("") = limpar; Some("x") = definir
    if let Some(s) = series_name {
        let t = s.trim().to_owned();
        book.series_name = if t.is_empty() { None } else { Some(t) };
    }
    storage::save_book(&vault, &book)?;
    Ok(BookMeta::from(&book))
}

/// Deleta um livro e todos os seus capítulos.
/// Operação irreversível — o frontend deve confirmar com o usuário.
#[tauri::command]
pub fn delete_book(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    storage::delete_book(&vault, &project_id, &book_id)
}

/// Reordena livros dentro de um projeto.
/// `ordered_ids`: lista de book_ids na nova ordem desejada.
#[tauri::command]
pub fn reorder_books(
    state: State<'_, AppState>,
    project_id: String,
    ordered_ids: Vec<String>,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let existing = storage::list_books(&vault, &project_id)?;

    // Valida que todos os IDs fornecidos existem
    for id in &ordered_ids {
        if !existing.iter().any(|b| &b.id == id) {
            return Err(AppError::BookNotFound(id.clone()));
        }
    }

    // Atualiza order em cada book.json
    for (new_order, book_id) in ordered_ids.iter().enumerate() {
        let mut book = storage::load_book(&vault, &project_id, book_id)?;
        book.order = new_order;
        storage::save_book(&vault, &book)?;
    }

    Ok(())
}
