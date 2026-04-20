// ============================================================
//  HUB — commands/config.rs
//  Leitura, validação e escrita do ecosystem.json.
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use serde_json::Value;
use std::path::Path;

/// Lê o ecosystem.json e retorna o objeto completo.
/// Retorna objeto vazio se o arquivo não existir.
#[tauri::command]
pub fn read_ecosystem_config() -> Result<Value, AppError> {
    let path = ecosystem::ecosystem_path().ok_or_else(|| {
        AppError::MissingConfig("Não foi possível determinar o diretório de dados.".into())
    })?;

    if !path.exists() {
        return Ok(serde_json::json!({}));
    }

    let content = std::fs::read_to_string(&path)?;
    let value: Value = serde_json::from_str(&content)?;
    Ok(value)
}

/// Verifica se um caminho existe e é um diretório.
#[tauri::command]
pub fn validate_path(path: String) -> bool {
    if path.trim().is_empty() {
        return false;
    }
    Path::new(&path).is_dir()
}

/// Aplica um diretório raiz de sincronização ao ecossistema:
/// cria as subpastas necessárias e escreve os caminhos derivados
/// no ecosystem.json para todos os apps.
#[tauri::command]
pub fn apply_sync_root(sync_root: String) -> Result<(), AppError> {
    use serde_json::json;
    use std::path::Path;

    let root = Path::new(&sync_root);

    let dirs = [
        root.join("aether"),
        root.join("aether").join(".config"),
        root.join("kosmos"),
        root.join("kosmos").join(".config"),
        root.join("mnemosyne").join("docs"),
        root.join("mnemosyne").join("chroma_db"),
        root.join("mnemosyne").join(".config"),
        root.join("hermes"),
        root.join("hermes").join(".config"),
        root.join("akasha"),
        root.join("akasha").join(".config"),
        root.join("ogma"),
        root.join("ogma").join(".config"),
    ];

    for dir in &dirs {
        std::fs::create_dir_all(dir)?;
    }

    // Escreve sync_root como campo top-level
    ecosystem::write_section("sync_root", json!(sync_root))?;

    // Escreve caminhos derivados por app (merge — preserva exe_path e outros campos)
    ecosystem::write_section("aether", json!({
        "vault_path":  root.join("aether").to_string_lossy().as_ref(),
        "config_path": root.join("aether").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_section("kosmos", json!({
        "archive_path": root.join("kosmos").to_string_lossy().as_ref(),
        "config_path":  root.join("kosmos").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_section("mnemosyne", json!({
        "watched_dir": root.join("mnemosyne").join("docs").to_string_lossy().as_ref(),
        "chroma_dir":  root.join("mnemosyne").join("chroma_db").to_string_lossy().as_ref(),
        "config_path": root.join("mnemosyne").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_section("hermes", json!({
        "output_dir":  root.join("hermes").to_string_lossy().as_ref(),
        "config_path": root.join("hermes").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_section("akasha", json!({
        "archive_path": root.join("akasha").to_string_lossy().as_ref(),
        "data_path":    root.join("akasha").to_string_lossy().as_ref(),
        "config_path":  root.join("akasha").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_section("ogma", json!({
        "data_path":   root.join("ogma").to_string_lossy().as_ref(),
        "config_path": root.join("ogma").join(".config").to_string_lossy().as_ref(),
    }))?;

    Ok(())
}

/// Atualiza seções do ecosystem.json com os valores fornecidos.
/// `updates` é um objeto onde cada chave é um app e o valor é a seção.
/// Exemplo: `{ "aether": { "vault_path": "/..." }, "kosmos": { ... } }`
#[tauri::command]
pub fn save_ecosystem_config(updates: Value) -> Result<(), AppError> {
    let obj = updates.as_object().ok_or_else(|| {
        AppError::InvalidPath("O payload de configuração deve ser um objeto JSON.".into())
    })?;

    for (app, section) in obj {
        ecosystem::write_section(app, section.clone())?;
    }

    Ok(())
}
