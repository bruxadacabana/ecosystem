// ============================================================
//  AETHER — Commands Tauri: Projetos
//  Gerenciar vault path + CRUD de projetos.
//  Toda função retorna Result<T, AppError> — sem .unwrap().
// ============================================================

use std::path::PathBuf;

use tauri::{AppHandle, Manager, State};

use crate::{
    error::AppError,
    storage,
    types::{AppData, Project, ProjectType},
    AppState,
};

// ----------------------------------------------------------
//  Helpers internos
// ----------------------------------------------------------

/// Extrai o vault_path do estado ou retorna VaultNotConfigured.
pub(super) fn require_vault(state: &AppState) -> Result<PathBuf, AppError> {
    let guard = state
        .vault_path
        .lock()
        .map_err(|e| AppError::Io(format!("Mutex envenenado: {e}")))?;

    guard
        .clone()
        .ok_or(AppError::VaultNotConfigured)
}

// ----------------------------------------------------------
//  Vault
// ----------------------------------------------------------

/// Retorna o caminho do vault atualmente configurado.
/// Retorna None se o vault ainda não foi selecionado.
#[tauri::command]
pub fn get_vault_path(state: State<'_, AppState>) -> Result<Option<String>, AppError> {
    let guard = state
        .vault_path
        .lock()
        .map_err(|e| AppError::Io(format!("Mutex envenenado: {e}")))?;

    Ok(guard.as_ref().map(|p| p.to_string_lossy().into_owned()))
}

/// Define o vault path, persiste no AppData do sistema e valida
/// que a pasta existe (ou a cria se não existir).
#[tauri::command]
pub fn set_vault_path(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
) -> Result<(), AppError> {
    if path.trim().is_empty() {
        return Err(AppError::InvalidPath("Caminho não pode ser vazio.".into()));
    }

    let vault_path = PathBuf::from(&path);

    // Cria a pasta do vault se não existir
    if !vault_path.exists() {
        std::fs::create_dir_all(&vault_path)?;
    } else if !vault_path.is_dir() {
        return Err(AppError::InvalidPath(format!(
            "'{path}' existe mas não é uma pasta."
        )));
    }

    // Persiste no AppData
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| AppError::Io(e.to_string()))?;

    let app_data = AppData {
        vault_path: Some(vault_path.clone()),
    };
    storage::save_app_data(&app_data_dir, &app_data)?;

    // Atualiza estado em memória
    let mut guard = state
        .vault_path
        .lock()
        .map_err(|e| AppError::Io(format!("Mutex envenenado: {e}")))?;
    *guard = Some(vault_path.clone());

    log::info!("Vault configurado: {}", vault_path.display());
    Ok(())
}

// ----------------------------------------------------------
//  Projetos
// ----------------------------------------------------------

/// Lista todos os projetos no vault, ordenados do mais recente.
#[tauri::command]
pub fn list_projects(state: State<'_, AppState>) -> Result<Vec<Project>, AppError> {
    let vault = require_vault(&state)?;
    storage::list_projects(&vault)
}

/// Cria um novo projeto no vault.
/// project_type: "single" | "series"
/// Para "single", um livro é criado automaticamente com o mesmo nome.
/// Todos os campos de metadados são opcionais exceto name e project_type.
#[tauri::command]
pub fn create_project(
    state: State<'_, AppState>,
    name: String,
    project_type: ProjectType,
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
    let vault = require_vault(&state)?;
    let result = storage::create_project(
        &vault,
        &name,
        project_type,
        description,
        subtitle,
        genre,
        target_audience,
        language,
        tags,
        has_magic_system,
        tech_level,
        inspirations,
    );
    match &result {
        Ok(p) => log::info!("Projeto criado: '{}' ({})", p.name, p.id),
        Err(e) => log::error!("Erro ao criar projeto '{}': {}", name, e),
    }
    result
}

/// Carrega um projeto pelo ID.
#[tauri::command]
pub fn open_project(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<Project, AppError> {
    let vault = require_vault(&state)?;
    storage::load_project(&vault, &project_id)
}

/// Deleta um projeto e todo seu conteúdo do disco.
/// Operação irreversível — o frontend deve confirmar com o usuário.
#[tauri::command]
pub fn delete_project(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<(), AppError> {
    let vault = require_vault(&state)?;
    let result = storage::delete_project(&vault, &project_id);
    match &result {
        Ok(()) => log::info!("Projeto deletado: {project_id}"),
        Err(e) => log::error!("Erro ao deletar projeto {project_id}: {e}"),
    }
    result
}

/// Atualiza nome e/ou descrição de um projeto existente.
#[tauri::command]
pub fn update_project(
    state: State<'_, AppState>,
    project_id: String,
    name: Option<String>,
    description: Option<String>,
) -> Result<Project, AppError> {
    let vault = require_vault(&state)?;
    let mut project = storage::load_project(&vault, &project_id)?;

    if let Some(n) = name {
        let trimmed = n.trim().to_owned();
        if trimmed.is_empty() {
            return Err(AppError::InvalidName(
                "O nome do projeto não pode ser vazio.".into(),
            ));
        }
        project.name = trimmed;
    }

    if let Some(d) = description {
        let trimmed = d.trim().to_owned();
        project.description = if trimmed.is_empty() { None } else { Some(trimmed) };
    }

    storage::save_project(&vault, &project)?;
    Ok(project)
}
