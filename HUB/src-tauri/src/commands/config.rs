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
