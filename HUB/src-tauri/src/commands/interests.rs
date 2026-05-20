// ============================================================
//  HUB — commands/interests.rs
//  Leitura e edição do perfil de interesses em interests.json.
//  Schema: { "topics": [...], "updated_at": ISO8601 }
//  Cada tópico: { name, weight, sources, pinned, excluded }
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TopicEntry {
    pub name:     String,
    pub weight:   f64,
    pub sources:  Vec<String>,
    pub pinned:   bool,
    pub excluded: bool,
}

fn interests_path() -> Option<PathBuf> {
    let eco = ecosystem::read_json();
    let sr = eco["sync_root"].as_str()?;
    Some(PathBuf::from(sr).join("interests.json"))
}

fn read_interests_raw() -> Value {
    interests_path()
        .and_then(|p| std::fs::read_to_string(&p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({ "topics": [] }))
}

fn write_interests_raw(data: Value) -> Result<(), AppError> {
    let path = interests_path().ok_or_else(|| {
        AppError::MissingConfig("sync_root não configurado".into())
    })?;
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let s = serde_json::to_string_pretty(&data)?;
    std::fs::write(&path, s)?;
    Ok(())
}

/// Retorna todos os tópicos (inclusive excluídos — UI decide o que mostrar).
#[tauri::command]
pub fn interests_get() -> Result<Vec<TopicEntry>, AppError> {
    let data = read_interests_raw();
    let topics = data["topics"].as_array().cloned().unwrap_or_default();
    let result = topics
        .into_iter()
        .filter_map(|t| {
            let name = t["name"].as_str()?.to_string();
            Some(TopicEntry {
                name,
                weight:   t["weight"].as_f64().unwrap_or(0.0),
                sources:  t["sources"].as_array()
                    .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
                    .unwrap_or_default(),
                pinned:   t["pinned"].as_bool().unwrap_or(false),
                excluded: t["excluded"].as_bool().unwrap_or(false),
            })
        })
        .collect();
    Ok(result)
}

/// Atualiza weight, pinned e/ou excluded de um tópico existente.
/// Campos None não são alterados.
#[tauri::command]
pub fn interests_set_topic(
    name:     String,
    weight:   Option<f64>,
    pinned:   Option<bool>,
    excluded: Option<bool>,
) -> Result<(), AppError> {
    let mut data = read_interests_raw();
    let topics = data["topics"].as_array_mut().ok_or_else(|| {
        AppError::InvalidPath("interests.json malformado".into())
    })?;

    let entry = topics.iter_mut().find(|t| t["name"].as_str() == Some(&name));
    if let Some(t) = entry {
        if let Some(w) = weight  { t["weight"]   = json!(w); }
        if let Some(p) = pinned  { t["pinned"]   = json!(p); }
        if let Some(e) = excluded { t["excluded"] = json!(e); }
    }

    data["updated_at"] = json!(Utc::now().to_rfc3339());
    write_interests_raw(data)
}

/// Adiciona um tópico manual. Ignora se já existe.
#[tauri::command]
pub fn interests_add_manual(name: String, weight: f64) -> Result<(), AppError> {
    let mut data = read_interests_raw();
    let topics = data["topics"]
        .as_array_mut()
        .ok_or_else(|| AppError::InvalidPath("interests.json malformado".into()))?;

    let already = topics.iter().any(|t| t["name"].as_str() == Some(&name));
    if !already {
        topics.push(json!({
            "name":     name,
            "weight":   weight,
            "sources":  ["manual"],
            "pinned":   true,
            "excluded": false,
        }));
        // ordena por peso desc
        topics.sort_by(|a, b| {
            let wa = a["weight"].as_f64().unwrap_or(0.0);
            let wb = b["weight"].as_f64().unwrap_or(0.0);
            wb.partial_cmp(&wa).unwrap_or(std::cmp::Ordering::Equal)
        });
    }

    data["updated_at"] = json!(Utc::now().to_rfc3339());
    write_interests_raw(data)
}

/// Tenta acionar re-exportação de interesses via AKASHA e Mnemosyne.
/// Falha silenciosa se os apps estiverem offline.
#[tauri::command]
pub async fn interests_refresh() -> Result<(), AppError> {
    let eco = ecosystem::read_json();

    let akasha_base = eco["akasha"]["base_url"]
        .as_str()
        .unwrap_or("http://localhost:7071")
        .to_string();
    let mnemosyne_base = eco["mnemosyne"]["base_url"]
        .as_str()
        .unwrap_or("http://localhost:7070")
        .to_string();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| AppError::Io(e.to_string()))?;

    // POST /interests/refresh se o endpoint existir — ignora erro se não existir
    let _ = client
        .post(format!("{akasha_base}/interests/refresh"))
        .send()
        .await;
    let _ = client
        .post(format!("{mnemosyne_base}/interests/refresh"))
        .send()
        .await;

    Ok(())
}
