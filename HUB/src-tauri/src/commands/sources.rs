// ============================================================
//  HUB — commands/sources.rs
//  Gestão unificada de fontes (domínios) do ecossistema.
//  Lê AKASHA (crawl_sites) e KOSMOS (feeds) diretamente do SQLite.
//  Estado library/feed persiste em ecosystem.json["sources"].
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize, Default)]
pub struct DomainEntry {
    /// Hostname canônico — ex: "example.com"
    pub domain: String,
    /// Label mais legível (nome do feed KOSMOS ou label do site AKASHA)
    pub label: String,
    /// True se o HUB marcou este domínio para indexação deep pelo AKASHA
    pub library: bool,
    /// True se o HUB marcou este domínio para monitoramento de feeds pelo KOSMOS
    pub feed: bool,
    /// base_url do site no AKASHA (None se não estiver na biblioteca)
    pub akasha_url: Option<String>,
    /// Nomes dos feeds KOSMOS para este domínio (vazio se não houver)
    pub kosmos_feeds: Vec<String>,
}

/// Extrai o hostname de uma URL sem scheme, porta ou path.
fn extract_host(url: &str) -> String {
    let s = url
        .trim_start_matches("https://")
        .trim_start_matches("http://");
    let host = s.split('/').next().unwrap_or(s);
    host.split(':').next().unwrap_or(host).to_lowercase()
}

fn akasha_db_path() -> Option<PathBuf> {
    let eco = ecosystem::read_json();
    let data = eco["akasha"]["data_path"].as_str()?;
    let p = PathBuf::from(data).join("akasha.db");
    p.exists().then_some(p)
}

fn kosmos_db_path() -> Option<PathBuf> {
    let eco = ecosystem::read_json();
    // kosmos.db fica em data_path; archive_path = data_path/archive (legado)
    if let Some(dp) = eco["kosmos"]["data_path"].as_str() {
        let p = PathBuf::from(dp).join("kosmos.db");
        if p.exists() {
            return Some(p);
        }
    }
    // Fallback: derivar de archive_path (parent)
    if let Some(ap) = eco["kosmos"]["archive_path"].as_str() {
        let p = PathBuf::from(ap).parent()?.join("kosmos.db");
        if p.exists() {
            return Some(p);
        }
    }
    None
}

/// Lê todos os domínios conhecidos pelo ecossistema:
/// - AKASHA: tabela `crawl_sites` WHERE deleted=0
/// - KOSMOS:  tabela `feeds`      WHERE active=1
/// Mescla com estado atual de ecosystem.json["sources"].
#[tauri::command]
pub fn sources_get_domains() -> Result<Vec<DomainEntry>, AppError> {
    let eco = ecosystem::read_json();
    let sources = eco["sources"].as_object().cloned().unwrap_or_default();

    let mut map: HashMap<String, DomainEntry> = HashMap::new();

    // ── AKASHA: crawl_sites ─────────────────────────────────────────
    if let Some(db) = akasha_db_path() {
        let conn = Connection::open(&db)
            .map_err(|e| AppError::Io(format!("akasha.db: {e}")))?;
        let mut stmt = conn
            .prepare(
                "SELECT base_url, label FROM crawl_sites \
                 WHERE deleted = 0 ORDER BY label ASC",
            )
            .map_err(|e| AppError::Io(e.to_string()))?;

        stmt.query_map(params![], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
            ))
        })
        .map_err(|e| AppError::Io(e.to_string()))?
        .filter_map(|r| r.ok())
        .for_each(|(base_url, label)| {
            let host = extract_host(&base_url);
            let entry = map.entry(host.clone()).or_insert_with(|| DomainEntry {
                domain: host.clone(),
                ..Default::default()
            });
            if entry.label.is_empty() {
                entry.label = label;
            }
            entry.akasha_url = Some(base_url);
        });
    }

    // ── KOSMOS: feeds ───────────────────────────────────────────────
    if let Some(db) = kosmos_db_path() {
        let conn = Connection::open(&db)
            .map_err(|e| AppError::Io(format!("kosmos.db: {e}")))?;
        let mut stmt = conn
            .prepare(
                "SELECT url, name FROM feeds WHERE active = 1 ORDER BY name ASC",
            )
            .map_err(|e| AppError::Io(e.to_string()))?;

        stmt.query_map(params![], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
            ))
        })
        .map_err(|e| AppError::Io(e.to_string()))?
        .filter_map(|r| r.ok())
        .for_each(|(url, name)| {
            let host = extract_host(&url);
            let entry = map.entry(host.clone()).or_insert_with(|| DomainEntry {
                domain: host.clone(),
                ..Default::default()
            });
            if entry.label.is_empty() {
                entry.label = name.clone();
            }
            entry.kosmos_feeds.push(name);
        });
    }

    // ── Aplica estado de ecosystem.json["sources"] ──────────────────
    for (host, entry) in map.iter_mut() {
        if let Some(state) = sources.get(host) {
            entry.library = state["library"].as_bool().unwrap_or(false);
            entry.feed    = state["feed"].as_bool().unwrap_or(false);
        }
    }

    let mut result: Vec<DomainEntry> = map.into_values().collect();
    result.sort_by(|a, b| a.domain.cmp(&b.domain));
    Ok(result)
}

/// Atualiza o flag `library` ou `feed` de um domínio em ecosystem.json["sources"].
/// `flag` deve ser "library" ou "feed".
#[tauri::command]
pub fn sources_set_flag(
    domain: String,
    flag: String,
    enabled: bool,
) -> Result<(), AppError> {
    if flag != "library" && flag != "feed" {
        return Err(AppError::InvalidPath(
            format!("flag inválida: {flag} (esperado: library | feed)"),
        ));
    }

    let eco = ecosystem::read_json();
    let mut sources = eco["sources"]
        .as_object()
        .cloned()
        .unwrap_or_default();

    let entry = sources
        .entry(domain)
        .or_insert_with(|| json!({ "library": false, "feed": false }));

    if let Some(obj) = entry.as_object_mut() {
        obj.insert(flag, json!(enabled));
    }

    ecosystem::write_section("sources", serde_json::Value::Object(sources))
}
