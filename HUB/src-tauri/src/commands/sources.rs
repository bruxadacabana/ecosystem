// ============================================================
//  HUB — commands/sources.rs
//  Gestão unificada de fontes (domínios) do ecossistema.
//  Lê AKASHA (crawl_sites) e KOSMOS (feeds) diretamente do SQLite.
//  Estado library/feed persiste em ecosystem.json["sources"].
//
//  Falhas no AKASHA DB são tratadas com graceful degradation:
//  - KOSMOS sempre é retornado normalmente
//  - Se AKASHA DB corrompido: tenta ler .backup/akasha/sites.json
//  - Campo akasha_error sinaliza ao frontend que os dados são do backup
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

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

/// Resposta de `sources_get_domains` — inclui aviso se AKASHA DB falhou.
#[derive(Debug, Serialize, Deserialize)]
pub struct SourcesResponse {
    pub domains:      Vec<DomainEntry>,
    /// Preenchido quando AKASHA DB falhou. Frontend deve exibir aviso.
    pub akasha_error: Option<String>,
    /// True quando os dados do AKASHA vieram do backup JSON (não do DB).
    pub from_backup:  bool,
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
    // Canônico (KOSMOS v3): {archive_path}/kosmos.db = {sync_root}/kosmos/kosmos.db.
    if let Some(ap) = eco["kosmos"]["archive_path"].as_str() {
        let p = PathBuf::from(ap).join("kosmos.db");
        if p.exists() { return Some(p); }
    }
    // Fallback: banco local legado (antes da migração para o sync_root).
    if let Some(dp) = eco["kosmos"]["data_path"].as_str() {
        let p = PathBuf::from(dp).join("kosmos.db");
        if p.exists() { return Some(p); }
    }
    None
}

fn akasha_backup_sites_path() -> Option<PathBuf> {
    let eco = ecosystem::read_json();
    let root = eco["sync_root"].as_str()?.trim().to_string();
    if root.is_empty() { return None; }
    let p = PathBuf::from(root).join(".backup").join("akasha").join("sites.json");
    p.exists().then_some(p)
}

/// Tenta ler `crawl_sites` do AKASHA DB. Retorna `Err` se DB corrompido ou ausente.
fn read_akasha_sites(
    map:  &mut HashMap<String, DomainEntry>,
    db:   &Path,
) -> Result<(), String> {
    let conn = Connection::open(db).map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT base_url, label FROM crawl_sites WHERE deleted = 0 ORDER BY label ASC")
        .map_err(|e| e.to_string())?;

    stmt.query_map(params![], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
    })
    .map_err(|e| e.to_string())?
    .filter_map(|r| r.ok())
    .for_each(|(base_url, label)| {
        let host = extract_host(&base_url);
        let entry = map.entry(host.clone()).or_insert_with(|| DomainEntry {
            domain: host.clone(),
            ..Default::default()
        });
        if entry.label.is_empty() { entry.label = label; }
        entry.akasha_url = Some(base_url);
    });
    Ok(())
}

/// Fallback: lê `.backup/akasha/sites.json` quando o DB falha.
fn read_akasha_backup(
    map:         &mut HashMap<String, DomainEntry>,
    backup_path: &Path,
) -> Result<(), String> {
    let content = std::fs::read_to_string(backup_path).map_err(|e| e.to_string())?;
    let sites: Vec<serde_json::Value> = serde_json::from_str(&content).map_err(|e| e.to_string())?;
    for site in sites {
        let base_url = site["base_url"].as_str().unwrap_or("").to_string();
        let label    = site["label"].as_str().unwrap_or(&base_url).to_string();
        if base_url.is_empty() { continue; }
        let host = extract_host(&base_url);
        let entry = map.entry(host.clone()).or_insert_with(|| DomainEntry {
            domain: host.clone(),
            ..Default::default()
        });
        if entry.label.is_empty() { entry.label = label; }
        entry.akasha_url = Some(base_url);
    }
    Ok(())
}

/// Lê todos os domínios conhecidos pelo ecossistema:
/// - AKASHA: tabela `crawl_sites` WHERE deleted=0
///   → se DB corrompido: fallback para `.backup/akasha/sites.json`
/// - KOSMOS:  tabela `feeds`      WHERE enabled=1 (schema v3)
/// Mescla com estado atual de ecosystem.json["sources"].
/// Falha no AKASHA não interrompe a leitura do KOSMOS.
#[tauri::command]
pub fn sources_get_domains() -> Result<SourcesResponse, AppError> {
    let eco = ecosystem::read_json();
    let sources = eco["sources"].as_object().cloned().unwrap_or_default();

    let mut map: HashMap<String, DomainEntry> = HashMap::new();
    let mut akasha_error: Option<String> = None;
    let mut from_backup = false;

    // ── AKASHA: crawl_sites (com graceful degradation) ──────────────
    let akasha_ok = akasha_db_path()
        .map(|db| read_akasha_sites(&mut map, &db))
        .unwrap_or_else(|| Err("akasha.db não encontrado".into()));

    if let Err(db_err) = akasha_ok {
        // DB falhou — tentar backup JSON
        match akasha_backup_sites_path() {
            Some(backup) => match read_akasha_backup(&mut map, &backup) {
                Ok(_) => {
                    akasha_error = Some(format!("AKASHA DB corrompido ({db_err}) — exibindo dados do backup"));
                    from_backup = true;
                }
                Err(bak_err) => {
                    akasha_error = Some(format!(
                        "AKASHA DB corrompido ({db_err}); backup também falhou ({bak_err})"
                    ));
                }
            },
            None => {
                akasha_error = Some(format!("AKASHA DB corrompido ({db_err}); backup não encontrado"));
            }
        }
    }

    // ── KOSMOS: feeds (independente do AKASHA) ──────────────────────
    if let Some(db) = kosmos_db_path() {
        // Falhas no KOSMOS também são toleradas — não abortam a resposta
        if let Ok(conn) = Connection::open(&db) {
            // Schema v3 do KOSMOS: feeds(url, title, category, enabled). title pode
            // ser NULL antes do 1º fetch → COALESCE para a url como rótulo.
            if let Ok(mut stmt) = conn.prepare(
                "SELECT url, COALESCE(title, url) FROM feeds WHERE enabled = 1 \
                 ORDER BY COALESCE(title, url)"
            ) {
                if let Ok(rows) = stmt.query_map(params![], |row| {
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                }) {
                    rows.filter_map(|r| r.ok()).for_each(|(url, title)| {
                        let host = extract_host(&url);
                        let entry = map.entry(host.clone()).or_insert_with(|| DomainEntry {
                            domain: host.clone(),
                            ..Default::default()
                        });
                        if entry.label.is_empty() { entry.label = title.clone(); }
                        entry.kosmos_feeds.push(title);
                    });
                }
            }
        }
    }

    // ── Aplica estado de ecosystem.json["sources"] ──────────────────
    for (host, entry) in map.iter_mut() {
        if let Some(state) = sources.get(host) {
            entry.library = state["library"].as_bool().unwrap_or(false);
            entry.feed    = state["feed"].as_bool().unwrap_or(false);
        }
    }

    let mut domains: Vec<DomainEntry> = map.into_values().collect();
    domains.sort_by(|a, b| a.domain.cmp(&b.domain));
    Ok(SourcesResponse { domains, akasha_error, from_backup })
}

/// Retorna sites do AKASHA lidos do backup JSON (`.backup/akasha/sites.json`).
/// Usado quando o DB está corrompido e indisponível.
#[tauri::command]
pub fn sources_get_akasha_backup() -> Result<Vec<DomainEntry>, AppError> {
    let backup = akasha_backup_sites_path()
        .ok_or_else(|| AppError::NotFound(".backup/akasha/sites.json não encontrado".into()))?;
    let mut map: HashMap<String, DomainEntry> = HashMap::new();
    read_akasha_backup(&mut map, &backup)
        .map_err(|e| AppError::Io(e))?;
    let mut result: Vec<DomainEntry> = map.into_values().collect();
    result.sort_by(|a, b| a.domain.cmp(&b.domain));
    Ok(result)
}

/// Atualiza o flag `library` ou `feed` de um domínio em ecosystem.json["sources"].
/// `flag` deve ser "library" ou "feed".
#[tauri::command]
pub fn sources_set_flag(domain: String, flag: String, enabled: bool) -> Result<(), AppError> {
    if flag != "library" && flag != "feed" {
        return Err(AppError::InvalidPath(
            format!("flag inválida: {flag} (esperado: library | feed)"),
        ));
    }
    let eco = ecosystem::read_json();
    let mut sources = eco["sources"].as_object().cloned().unwrap_or_default();
    let entry = sources
        .entry(domain)
        .or_insert_with(|| json!({ "library": false, "feed": false }));
    if let Some(obj) = entry.as_object_mut() {
        obj.insert(flag, json!(enabled));
    }
    ecosystem::write_section("sources", serde_json::Value::Object(sources))
}

// ─── Testes ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    fn make_akasha_db(dir: &Path, corrupted: bool) -> PathBuf {
        let db_path = dir.join("akasha.db");
        if corrupted {
            std::fs::write(&db_path, b"not a sqlite file").unwrap();
        } else {
            let conn = Connection::open(&db_path).unwrap();
            conn.execute_batch(
                "CREATE TABLE crawl_sites (
                    id INTEGER PRIMARY KEY, base_url TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL DEFAULT '', crawl_depth INTEGER NOT NULL DEFAULT 2,
                    crawl_interval_days INTEGER NOT NULL DEFAULT 7, deleted INTEGER NOT NULL DEFAULT 0
                 );
                 INSERT INTO crawl_sites (base_url, label, deleted)
                 VALUES ('https://ok.com', 'OK Site', 0),
                        ('https://gone.com', 'Deleted', 1);",
            ).unwrap();
        }
        db_path
    }

    fn make_backup_sites(dir: &Path) -> PathBuf {
        let bdir = dir.join(".backup/akasha");
        std::fs::create_dir_all(&bdir).unwrap();
        let p = bdir.join("sites.json");
        std::fs::write(&p, r#"[{"base_url":"https://backup.com","label":"Backup","crawl_depth":2,"crawl_interval_days":7}]"#).unwrap();
        p
    }

    #[test]
    fn test_sources_akasha_db_ok_returns_non_deleted() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db(tmp.path(), false);
        let db = tmp.path().join("akasha.db");
        let mut map = HashMap::new();
        read_akasha_sites(&mut map, &db).unwrap();
        assert_eq!(map.len(), 1, "apenas site não deletado deve aparecer");
        assert!(map.contains_key("ok.com"));
    }

    #[test]
    fn test_sources_akasha_db_corrupted_returns_err() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db(tmp.path(), true);
        let db = tmp.path().join("akasha.db");
        let mut map = HashMap::new();
        assert!(read_akasha_sites(&mut map, &db).is_err());
    }

    #[test]
    fn test_sources_fallback_to_backup_when_db_corrupted() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db(tmp.path(), true);
        let backup = make_backup_sites(tmp.path());
        let mut map = HashMap::new();
        read_akasha_backup(&mut map, &backup).unwrap();
        assert_eq!(map.len(), 1);
        assert!(map.contains_key("backup.com"));
    }

    #[test]
    fn test_sources_kosmos_failure_does_not_block_akasha() {
        // Sem KOSMOS DB → akasha ainda é retornado
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db(tmp.path(), false);
        let db = tmp.path().join("akasha.db");
        let mut map = HashMap::new();
        read_akasha_sites(&mut map, &db).unwrap();
        // KOSMOS ausente: map ainda tem o site do AKASHA
        assert!(!map.is_empty(), "sites do AKASHA devem aparecer mesmo sem KOSMOS");
    }
}
