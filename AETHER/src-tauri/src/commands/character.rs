// ============================================================
//  AETHER — Commands Tauri: Personagens & Relacionamentos
//  Fichas de personagem com campos customizáveis (4.1)
//  Relacionamentos entre personagens (4.2)
//  Toda função retorna Result<T, AppError> — sem .unwrap().
// ============================================================

use tauri::State;

use crate::{
    commands::project::require_vault,
    error::AppError,
    storage,
    types::{Character, CustomField, Relationship},
    AppState,
};

// ----------------------------------------------------------
//  Personagens (4.1)
// ----------------------------------------------------------

/// Lista todos os personagens do projeto.
#[tauri::command]
pub fn list_characters(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Vec<Character>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_characters(&vault, &project_id)
}

/// Cria um novo personagem com o nome fornecido.
#[tauri::command]
pub fn create_character(
    state: State<'_, AppState>,
    project_id: String,
    name: String,
) -> Result<Character, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::create_character(&vault, &project_id, &name);
    match &result {
        Ok(c) => log::info!("Personagem criado: '{}' ({})", c.name, c.id),
        Err(e) => log::error!("Erro ao criar personagem '{}': {}", name, e),
    }
    result
}

/// Carrega uma ficha de personagem completa.
#[tauri::command]
pub fn load_character(
    state: State<'_, AppState>,
    project_id: String,
    character_id: String,
) -> Result<Character, AppError> {
    let vault = require_vault(&state)?;
    storage::load_character(&vault, &project_id, &character_id)
}

/// Salva alterações em uma ficha de personagem.
/// Substitui o objeto completo — o frontend envia o estado atualizado.
#[tauri::command]
pub fn save_character(
    state: State<'_, AppState>,
    project_id: String,
    character_id: String,
    name: String,
    role: Option<String>,
    description: Option<String>,
    fields: Vec<CustomField>,
    image_path: Option<String>,
    chapter_ids: Vec<String>,
) -> Result<Character, AppError> {
    let vault = require_vault(&state)?;
    let existing = storage::load_character(&vault, &project_id, &character_id)?;
    let updated = Character {
        id: existing.id,
        project_id: existing.project_id,
        name,
        role,
        description,
        fields,
        image_path,
        chapter_ids,
        created_at: existing.created_at,
        updated_at: String::new(), // será preenchido por save_character
    };
    let result = storage::save_character(&vault, &project_id, updated);
    if let Err(ref e) = result {
        log::error!("Erro ao salvar personagem {character_id}: {e}");
    }
    result
}

/// Exclui permanentemente um personagem.
#[tauri::command]
pub fn delete_character(
    state: State<'_, AppState>,
    project_id: String,
    character_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::delete_character(&vault, &project_id, &character_id);
    match &result {
        Ok(_) => log::info!("Personagem excluído: {}", character_id),
        Err(e) => log::error!("Erro ao excluir personagem {}: {}", character_id, e),
    }
    result
}

// ----------------------------------------------------------
//  Relacionamentos (4.2)
// ----------------------------------------------------------

/// Lista todos os relacionamentos do projeto.
#[tauri::command]
pub fn list_relationships(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Vec<Relationship>, AppError> {
    let vault = require_vault(&state)?;
    storage::load_relationships(&vault, &project_id)
}

/// Adiciona um relacionamento entre dois personagens.
#[tauri::command]
pub fn add_relationship(
    state: State<'_, AppState>,
    project_id: String,
    from_id: String,
    to_id: String,
    kind: String,
    note: Option<String>,
) -> Result<Relationship, AppError> {
    let vault = require_vault(&state)?;
    let mut rels = storage::load_relationships(&vault, &project_id)?;

    let id = uuid::Uuid::new_v4().to_string();
    let rel = Relationship {
        id: id.clone(),
        from_id,
        to_id,
        kind,
        note,
    };
    rels.push(rel.clone());
    storage::save_relationships(&vault, &project_id, &rels)?;
    log::info!("Relacionamento criado: {}", id);
    Ok(rel)
}

/// Atualiza kind/note de um relacionamento existente.
#[tauri::command]
pub fn update_relationship(
    state: State<'_, AppState>,
    project_id: String,
    relationship_id: String,
    kind: String,
    note: Option<String>,
) -> Result<Relationship, AppError> {
    let vault = require_vault(&state)?;
    let mut rels = storage::load_relationships(&vault, &project_id)?;

    let rel = rels
        .iter_mut()
        .find(|r| r.id == relationship_id)
        .ok_or_else(|| AppError::NotFound(format!("Relacionamento '{relationship_id}' não encontrado.")))?;

    rel.kind = kind;
    rel.note = note;
    let updated = rel.clone();

    storage::save_relationships(&vault, &project_id, &rels)?;
    Ok(updated)
}

/// Remove um relacionamento.
#[tauri::command]
pub fn delete_relationship(
    state: State<'_, AppState>,
    project_id: String,
    relationship_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let mut rels = storage::load_relationships(&vault, &project_id)?;
    let before = rels.len();
    rels.retain(|r| r.id != relationship_id);
    if rels.len() == before {
        return Err(AppError::NotFound(format!("Relacionamento '{relationship_id}' não encontrado.")));
    }
    storage::save_relationships(&vault, &project_id, &rels)?;
    log::info!("Relacionamento removido: {}", relationship_id);
    Ok(())
}
