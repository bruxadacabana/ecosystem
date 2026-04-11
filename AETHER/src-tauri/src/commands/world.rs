// ============================================================
//  AETHER — Commands Tauri: Worldbuilding & Timeline & Imagens
//  Notas de worldbuilding por categoria (4.3)
//  Linha do tempo de eventos (4.4)
//  Anexar imagens a personagens e locais (4.5)
//  Toda função retorna Result<T, AppError> — sem .unwrap().
// ============================================================

use std::path::PathBuf;
use tauri::State;

use crate::{
    commands::project::require_vault,
    error::AppError,
    storage,
    types::{CustomField, TimelineEvent, WorldCategory, WorldNote},
    AppState,
};

// ----------------------------------------------------------
//  Worldbuilding (4.3)
// ----------------------------------------------------------

/// Lista todas as notas de worldbuilding do projeto.
#[tauri::command]
pub fn list_world_notes(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Vec<WorldNote>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_world_notes(&vault, &project_id)
}

/// Cria uma nova nota de worldbuilding.
#[tauri::command]
pub fn create_world_note(
    state: State<'_, AppState>,
    project_id: String,
    name: String,
    category: WorldCategory,
) -> Result<WorldNote, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::create_world_note(&vault, &project_id, &name, category);
    match &result {
        Ok(n) => log::info!("Nota criada: '{}' ({})", n.name, n.id),
        Err(e) => log::error!("Erro ao criar nota '{}': {}", name, e),
    }
    result
}

/// Carrega uma nota de worldbuilding completa.
#[tauri::command]
pub fn load_world_note(
    state: State<'_, AppState>,
    project_id: String,
    note_id: String,
) -> Result<WorldNote, AppError> {
    let vault = require_vault(&state)?;
    storage::load_world_note(&vault, &project_id, &note_id)
}

/// Salva alterações em uma nota de worldbuilding.
#[tauri::command]
pub fn save_world_note(
    state: State<'_, AppState>,
    project_id: String,
    note_id: String,
    name: String,
    category: WorldCategory,
    description: Option<String>,
    fields: Vec<CustomField>,
    image_path: Option<String>,
    chapter_ids: Vec<String>,
) -> Result<WorldNote, AppError> {
    let vault = require_vault(&state)?;
    let existing = storage::load_world_note(&vault, &project_id, &note_id)?;
    let updated = WorldNote {
        id: existing.id,
        project_id: existing.project_id,
        name,
        category,
        description,
        fields,
        image_path,
        chapter_ids,
        created_at: existing.created_at,
        updated_at: String::new(), // será preenchido por save_world_note
    };
    let result = storage::save_world_note(&vault, &project_id, updated);
    if let Err(ref e) = result {
        log::error!("Erro ao salvar nota {note_id}: {e}");
    }
    result
}

/// Exclui permanentemente uma nota de worldbuilding.
#[tauri::command]
pub fn delete_world_note(
    state: State<'_, AppState>,
    project_id: String,
    note_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::delete_world_note(&vault, &project_id, &note_id);
    match &result {
        Ok(_) => log::info!("Nota excluída: {}", note_id),
        Err(e) => log::error!("Erro ao excluir nota {}: {}", note_id, e),
    }
    result
}

// ----------------------------------------------------------
//  Linha do tempo (4.4)
// ----------------------------------------------------------

/// Carrega todos os eventos da linha do tempo.
#[tauri::command]
pub fn load_timeline(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Vec<TimelineEvent>, AppError> {
    let vault = require_vault(&state)?;
    storage::load_timeline(&vault, &project_id)
}

/// Cria um novo evento na linha do tempo.
#[tauri::command]
pub fn create_timeline_event(
    state: State<'_, AppState>,
    project_id: String,
    title: String,
    date_label: String,
) -> Result<TimelineEvent, AppError> {
    let vault = require_vault(&state)?;
    let mut events = storage::load_timeline(&vault, &project_id)?;

    let id = uuid::Uuid::new_v4().to_string();
    let order = events.len();
    let event = TimelineEvent {
        id: id.clone(),
        project_id: project_id.clone(),
        title,
        description: None,
        date_label,
        order,
        character_ids: vec![],
        note_ids: vec![],
        chapter_ids: vec![],
    };
    events.push(event.clone());
    storage::save_timeline(&vault, &project_id, &events)?;
    log::info!("Evento criado na timeline: {}", id);
    Ok(event)
}

/// Salva alterações em um evento da linha do tempo.
/// Recebe o evento completo atualizado.
#[tauri::command]
pub fn save_timeline_event(
    state: State<'_, AppState>,
    project_id: String,
    event_id: String,
    title: String,
    date_label: String,
    description: Option<String>,
    character_ids: Vec<String>,
    note_ids: Vec<String>,
    chapter_ids: Vec<String>,
) -> Result<TimelineEvent, AppError> {
    let vault = require_vault(&state)?;
    let mut events = storage::load_timeline(&vault, &project_id)?;

    let event = events
        .iter_mut()
        .find(|e| e.id == event_id)
        .ok_or_else(|| AppError::NotFound(format!("Evento '{event_id}' não encontrado.")))?;

    event.title = title;
    event.date_label = date_label;
    event.description = description;
    event.character_ids = character_ids;
    event.note_ids = note_ids;
    event.chapter_ids = chapter_ids;
    let updated = event.clone();

    storage::save_timeline(&vault, &project_id, &events)?;
    Ok(updated)
}

/// Reordena os eventos da timeline pelo novo vetor de IDs ordenados.
#[tauri::command]
pub fn reorder_timeline(
    state: State<'_, AppState>,
    project_id: String,
    ordered_ids: Vec<String>,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let mut events = storage::load_timeline(&vault, &project_id)?;

    for (new_order, id) in ordered_ids.iter().enumerate() {
        if let Some(e) = events.iter_mut().find(|e| &e.id == id) {
            e.order = new_order;
        } else {
            return Err(AppError::NotFound(format!("Evento '{id}' não encontrado.")));
        }
    }
    events.sort_by_key(|e| e.order);
    storage::save_timeline(&vault, &project_id, &events)
}

/// Remove um evento da timeline.
#[tauri::command]
pub fn delete_timeline_event(
    state: State<'_, AppState>,
    project_id: String,
    event_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let mut events = storage::load_timeline(&vault, &project_id)?;
    let before = events.len();
    events.retain(|e| e.id != event_id);
    if events.len() == before {
        return Err(AppError::NotFound(format!("Evento '{event_id}' não encontrado.")));
    }
    // Renormalizar order
    for (i, e) in events.iter_mut().enumerate() {
        e.order = i;
    }
    storage::save_timeline(&vault, &project_id, &events)?;
    log::info!("Evento excluído da timeline: {}", event_id);
    Ok(())
}

// ----------------------------------------------------------
//  Imagens (4.5)
// ----------------------------------------------------------

/// Copia um arquivo de imagem para o diretório de imagens do projeto.
/// `entity_prefix` é uma string identificadora (ex: "char_abc", "note_xyz").
/// Retorna o caminho relativo ao vault.
#[tauri::command]
pub fn attach_image(
    state: State<'_, AppState>,
    project_id: String,
    entity_prefix: String,
    source_path: String,
) -> Result<String, AppError> {
    let vault = require_vault(&state)?;
    let src = PathBuf::from(&source_path);
    if !src.exists() {
        return Err(AppError::NotFound(format!("Arquivo '{source_path}' não encontrado.")));
    }
    let result = storage::attach_image(&vault, &project_id, &entity_prefix, &src);
    if let Err(ref e) = result {
        log::error!("Erro ao anexar imagem: {e}");
    }
    result
}

/// Lê uma imagem e retorna como data URL base64 para exibição no frontend.
#[tauri::command]
pub fn load_image(
    state: State<'_, AppState>,
    relative_path: String,
) -> Result<String, AppError> {
    let vault = require_vault(&state)?;
    storage::load_image_base64(&vault, &relative_path)
}

/// Remove um arquivo de imagem do disco.
#[tauri::command]
pub fn remove_image(
    state: State<'_, AppState>,
    relative_path: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::remove_image(&vault, &relative_path);
    if let Err(ref e) = result {
        log::error!("Erro ao remover imagem: {e}");
    }
    result
}
