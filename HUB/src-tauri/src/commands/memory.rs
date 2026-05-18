// ============================================================
//  HUB — Leitura da memória pessoal de AKASHA e Mnemosyne
//  Lê personal_memory.db via rusqlite (sem HTTP — app pode estar fechada).
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub id:         i64,
    pub created_at: String,
    #[serde(rename = "type")]
    pub entry_type: String,
    pub content:    String,
    pub tags:       Vec<String>,
    pub feedback:   Option<String>,
}

/// Resolve o caminho de personal_memory.db para `app` ("akasha" ou "mnemosyne").
/// Prioriza {sync_root}/.ai_private/{app}/personal_memory.db; fallback para home.
fn pm_db_path(app: &str) -> Option<PathBuf> {
    let eco = ecosystem::read_json();

    // Caminho preferido: ai_private_dir
    if let Some(sr) = eco["sync_root"].as_str() {
        let p = PathBuf::from(sr)
            .join(".ai_private")
            .join(app)
            .join("personal_memory.db");
        if p.exists() {
            return Some(p);
        }
    }

    // Fallback: diretório home da plataforma
    let home = dirs::home_dir()?;
    let fallback = match app {
        "akasha" => home
            .join(".local")
            .join("share")
            .join("akasha")
            .join("personal_memory.db"),
        "mnemosyne" => {
            // Tenta app_data_dir padrão do Tauri (Linux: ~/.local/share/mnemosyne)
            home.join(".local")
                .join("share")
                .join("mnemosyne")
                .join("personal_memory.db")
        }
        _ => return None,
    };

    fallback.exists().then_some(fallback)
}

/// Retorna as N entradas mais recentes da memória pessoal de `app`.
#[tauri::command]
pub fn memory_get_entries(app: String, n: u32) -> Result<Vec<MemoryEntry>, AppError> {
    let path = pm_db_path(&app).ok_or_else(|| AppError::NotFound(
        format!("personal_memory.db de {app} não encontrado"),
    ))?;

    let conn = Connection::open(&path).map_err(|e| AppError::Io(
        format!("Erro ao abrir {}: {e}", path.display()),
    ))?;

    let mut stmt = conn
        .prepare(
            "SELECT id, created_at, type, content, tags, feedback \
             FROM personal_memory ORDER BY id DESC LIMIT ?1",
        )
        .map_err(|e| AppError::Io(e.to_string()))?;

    let entries = stmt
        .query_map(params![n], |row| {
            let tags_json: String = row.get(4)?;
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                tags_json,
                row.get::<_, Option<String>>(5)?,
            ))
        })
        .map_err(|e| AppError::Io(e.to_string()))?
        .filter_map(|r| r.ok())
        .map(|(id, created_at, entry_type, content, tags_json, feedback)| {
            let tags: Vec<String> =
                serde_json::from_str(&tags_json).unwrap_or_default();
            MemoryEntry { id, created_at, entry_type, content, tags, feedback }
        })
        .collect();

    Ok(entries)
}

/// Retorna estatísticas de análise de artigos do KOSMOS lidas diretamente do SQLite.
/// Funciona mesmo com o KOSMOS fechado.
#[tauri::command]
pub fn kosmos_get_analysis_stats() -> Result<serde_json::Value, AppError> {
    let eco = ecosystem::read_json();

    // Deriva o caminho do DB a partir de archive_path configurado no ecosystem.json
    let db_path: PathBuf = if let Some(archive) = eco["kosmos"]["archive_path"].as_str() {
        let p = PathBuf::from(archive)
            .parent()
            .map(|d| d.join("kosmos.db"))
            .unwrap_or_default();
        if p.exists() {
            p
        } else {
            return Ok(serde_json::json!({ "available": false }));
        }
    } else {
        return Ok(serde_json::json!({ "available": false }));
    };

    let conn = Connection::open(&db_path)
        .map_err(|e| AppError::Io(format!("Erro ao abrir kosmos.db: {e}")))?;

    let total: i64 = conn
        .query_row("SELECT COUNT(*) FROM articles", [], |r| r.get(0))
        .unwrap_or(0);
    let pending: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM articles WHERE ai_tags IS NULL",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let analyzed: i64 = total - pending;

    Ok(serde_json::json!({
        "available": true,
        "total":     total,
        "pending":   pending,
        "analyzed":  analyzed,
    }))
}

/// Apaga uma entrada específica de memória por ID.
#[tauri::command]
pub fn memory_delete_entry(app: String, entry_id: i64) -> Result<(), AppError> {
    let path = pm_db_path(&app).ok_or_else(|| AppError::NotFound(
        format!("personal_memory.db de {app} não encontrado"),
    ))?;

    let conn = Connection::open(&path).map_err(|e| AppError::Io(
        format!("Erro ao abrir {}: {e}", path.display()),
    ))?;

    conn.execute(
        "DELETE FROM personal_memory WHERE id = ?1",
        params![entry_id],
    )
    .map_err(|e| AppError::Io(e.to_string()))?;

    Ok(())
}
