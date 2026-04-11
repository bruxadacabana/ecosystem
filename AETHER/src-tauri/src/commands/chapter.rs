// ============================================================
//  AETHER — Commands Tauri: Capítulos
//  CRUD de capítulos dentro de um livro.
//  Conteúdo em .md puro; metadados em book.json.
//  Toda função retorna Result<T, AppError> — sem .unwrap().
// ============================================================

use tauri::State;

use crate::{
    commands::project::require_vault,
    error::AppError,
    storage,
    types::{Annotation, BookMeta, ChapterMeta, ChapterStatus, SnapshotMeta},
    AppState,
};

/// Cria um novo capítulo vazio no livro.
#[tauri::command]
pub fn create_chapter(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    title: String,
) -> Result<ChapterMeta, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::create_chapter(&vault, &project_id, &book_id, &title);
    match &result {
        Ok(ch) => log::info!("Capítulo criado: '{}' ({})", ch.title, ch.id),
        Err(e) => log::error!("Erro ao criar capítulo '{}': {}", title, e),
    }
    result
}

/// Lê o conteúdo de texto de um capítulo (Markdown puro).
#[tauri::command]
pub fn read_chapter(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<String, AppError> {
    let vault = require_vault(&state)?;
    storage::read_chapter(&vault, &project_id, &book_id, &chapter_id)
}

/// Salva o conteúdo de um capítulo e atualiza word_count no book.json.
#[tauri::command]
pub fn save_chapter(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    content: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::save_chapter(&vault, &project_id, &book_id, &chapter_id, &content);
    if let Err(ref e) = result {
        log::error!("Erro ao salvar capítulo {chapter_id}: {e}");
    }
    result
}

/// Deleta um capítulo (arquivo .md + remove de book.json).
/// Operação irreversível — o frontend deve confirmar com o usuário.
#[tauri::command]
pub fn delete_chapter(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::delete_chapter(&vault, &project_id, &book_id, &chapter_id);
    match &result {
        Ok(()) => log::info!("Capítulo deletado: {chapter_id}"),
        Err(e) => log::error!("Erro ao deletar capítulo {chapter_id}: {e}"),
    }
    result
}

/// Reordena capítulos dentro de um livro.
/// `ordered_ids`: lista de chapter_ids na nova ordem desejada.
#[tauri::command]
pub fn reorder_chapters(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    ordered_ids: Vec<String>,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    storage::reorder_chapters(&vault, &project_id, &book_id, &ordered_ids)
}

/// Atualiza o título de um capítulo.
#[tauri::command]
pub fn update_chapter_title(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    title: String,
) -> Result<ChapterMeta, AppError> {
    let trimmed = title.trim().to_owned();
    if trimmed.is_empty() {
        return Err(AppError::InvalidName(
            "O título do capítulo não pode ser vazio.".into(),
        ));
    }

    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| AppError::ChapterNotFound(chapter_id.clone()))?;

    meta.title = trimmed;
    let updated = meta.clone();

    storage::save_book(&vault, &book)?;
    Ok(updated)
}

/// Atualiza o status de um capítulo (Draft / Revision / Final).
#[tauri::command]
pub fn update_chapter_status(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    status: ChapterStatus,
) -> Result<ChapterMeta, AppError> {
    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| AppError::ChapterNotFound(chapter_id.clone()))?;

    meta.status = status;
    let updated = meta.clone();

    storage::save_book(&vault, &book)?;
    Ok(updated)
}

/// Atualiza a sinopse de um capítulo.
#[tauri::command]
pub fn update_chapter_synopsis(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    synopsis: Option<String>,
) -> Result<ChapterMeta, AppError> {
    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| AppError::ChapterNotFound(chapter_id.clone()))?;

    meta.synopsis = synopsis.and_then(|s| {
        let t = s.trim().to_owned();
        if t.is_empty() { None } else { Some(t) }
    });
    let updated = meta.clone();

    storage::save_book(&vault, &book)?;
    Ok(updated)
}

// ----------------------------------------------------------
//  Lixeira
// ----------------------------------------------------------

/// Move um capítulo para a lixeira (soft delete — recuperável).
#[tauri::command]
pub fn trash_chapter(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::trash_chapter(&vault, &project_id, &book_id, &chapter_id);
    match &result {
        Ok(ch) => log::info!("Capítulo movido para lixeira: '{}' ({})", ch.title, ch.id),
        Err(e) => log::error!("Erro ao mover capítulo para lixeira {chapter_id}: {e}"),
    }
    result.map(|_| ())
}

/// Restaura um capítulo da lixeira para o fim da lista ativa.
#[tauri::command]
pub fn restore_chapter(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<ChapterMeta, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::restore_chapter(&vault, &project_id, &book_id, &chapter_id);
    match &result {
        Ok(ch) => log::info!("Capítulo restaurado: '{}' ({})", ch.title, ch.id),
        Err(e) => log::error!("Erro ao restaurar capítulo {chapter_id}: {e}"),
    }
    result
}

/// Lista todos os capítulos na lixeira de um livro.
#[tauri::command]
pub fn list_trash(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
) -> Result<Vec<ChapterMeta>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_trash(&vault, &project_id, &book_id)
}

/// Lista livros do projeto para uso na TrashView.
#[tauri::command]
pub fn list_books_for_trash(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Vec<BookMeta>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_books(&vault, &project_id)
}

// ----------------------------------------------------------
//  Scratchpad
// ----------------------------------------------------------

/// Lê o scratchpad de um capítulo. Retorna string vazia se não existir.
#[tauri::command]
pub fn read_scratchpad(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<String, AppError> {
    let vault = require_vault(&state)?;
    storage::read_scratchpad(&vault, &project_id, &book_id, &chapter_id)
}

/// Salva o scratchpad de um capítulo.
#[tauri::command]
pub fn save_scratchpad(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    content: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    storage::save_scratchpad(&vault, &project_id, &book_id, &chapter_id, &content)
}

// ----------------------------------------------------------
//  Vínculos capítulo ↔ personagens/notas (4.6)
// ----------------------------------------------------------

/// Atualiza os vínculos de um capítulo com personagens e notas de worldbuilding.
#[tauri::command]
pub fn update_chapter_links(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    character_ids: Vec<String>,
    note_ids: Vec<String>,
) -> Result<ChapterMeta, AppError> {
    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| crate::error::AppError::ChapterNotFound(chapter_id.clone()))?;

    meta.character_ids = character_ids;
    meta.note_ids = note_ids;
    let updated = meta.clone();

    storage::save_book(&vault, &book)?;
    storage::touch_project_pub(&vault, &project_id)?;
    Ok(updated)
}

// ----------------------------------------------------------
//  Metas de palavras (5.1)
// ----------------------------------------------------------

/// Define ou remove a meta de palavras de um capítulo.
/// `goal: None` remove a meta existente.
#[tauri::command]
pub fn set_chapter_word_goal(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    goal: Option<usize>,
) -> Result<ChapterMeta, AppError> {
    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;

    let meta = book
        .chapters
        .iter_mut()
        .find(|c| c.id == chapter_id)
        .ok_or_else(|| AppError::ChapterNotFound(chapter_id.clone()))?;

    meta.word_goal = goal;
    let updated = meta.clone();

    storage::save_book(&vault, &book)?;
    Ok(updated)
}

/// Define ou remove a meta de palavras de um livro.
/// `goal: None` remove a meta existente.
#[tauri::command]
pub fn set_book_word_goal(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    goal: Option<usize>,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let mut book = storage::load_book(&vault, &project_id, &book_id)?;
    book.word_goal = goal;
    storage::save_book(&vault, &book)?;
    log::info!("Meta de palavras do livro {book_id} definida para {goal:?}");
    Ok(())
}

// ----------------------------------------------------------
//  Snapshots de capítulo (5.5)
// ----------------------------------------------------------

/// Lista snapshots de um capítulo, ordenados por data (mais recente primeiro).
#[tauri::command]
pub fn list_snapshots(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<Vec<SnapshotMeta>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_snapshots(&vault, &project_id, &book_id, &chapter_id)
}

/// Cria um snapshot manual do capítulo com o conteúdo atual.
#[tauri::command]
pub fn create_snapshot(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    label: Option<String>,
) -> Result<SnapshotMeta, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::create_snapshot(&vault, &project_id, &book_id, &chapter_id, label);
    match &result {
        Ok(s) => log::info!("Snapshot criado: {} (cap: {})", s.id, chapter_id),
        Err(e) => log::error!("Erro ao criar snapshot: {e}"),
    }
    result
}

/// Retorna o conteúdo Markdown de um snapshot.
#[tauri::command]
pub fn load_snapshot_content(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    snapshot_id: String,
) -> Result<String, AppError> {
    let vault = require_vault(&state)?;
    storage::load_snapshot_content(&vault, &project_id, &book_id, &snapshot_id)
}

/// Restaura um snapshot, substituindo o conteúdo atual do capítulo.
#[tauri::command]
pub fn restore_snapshot(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    snapshot_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::restore_snapshot(&vault, &project_id, &book_id, &chapter_id, &snapshot_id);
    match &result {
        Ok(()) => log::info!("Snapshot {snapshot_id} restaurado para capítulo {chapter_id}"),
        Err(e) => log::error!("Erro ao restaurar snapshot: {e}"),
    }
    result
}

/// Deleta um snapshot permanentemente.
#[tauri::command]
pub fn delete_snapshot(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    snapshot_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    storage::delete_snapshot(&vault, &project_id, &book_id, &snapshot_id)
}

// ----------------------------------------------------------
//  Anotações inline (5.6)
// ----------------------------------------------------------

/// Lista todas as anotações de um capítulo.
#[tauri::command]
pub fn list_annotations(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
) -> Result<Vec<Annotation>, AppError> {
    let vault = require_vault(&state)?;
    storage::load_annotations(&vault, &project_id, &book_id, &chapter_id)
}

/// Cria uma nova anotação com o trecho citado.
#[tauri::command]
pub fn create_annotation(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    text: String,
    quote: String,
) -> Result<Annotation, AppError> {
    let vault = require_vault(&state)?;
    storage::create_annotation(&vault, &project_id, &book_id, &chapter_id, &text, &quote)
}

/// Atualiza o texto e/ou status de resolução de uma anotação.
#[tauri::command]
pub fn update_annotation(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    annotation_id: String,
    text: String,
    resolved: bool,
) -> Result<Annotation, AppError> {
    let vault = require_vault(&state)?;
    storage::update_annotation(
        &vault, &project_id, &book_id, &chapter_id, &annotation_id, &text, resolved,
    )
}

/// Remove uma anotação permanentemente.
#[tauri::command]
pub fn delete_annotation(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    annotation_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    storage::delete_annotation(&vault, &project_id, &book_id, &chapter_id, &annotation_id)
}
