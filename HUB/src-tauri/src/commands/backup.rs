// ============================================================
//  HUB — commands/backup.rs
//  Backup e restauração de dados chave do ecossistema.
//
//  Dados críticos exportados automaticamente em .backup/:
//    .backup/akasha/sites.json         ← crawl_sites (WHERE deleted=0)
//    .backup/akasha/blocked_domains.json  ← userdata JSON
//    .backup/akasha/watch_later.json      ← userdata JSON
//    .backup/kosmos/sources.json       ← feeds table
//    .backup/ecosystem.json            ← cópia do ecosystem.json
//
//  Chamado: ao fechar app, a cada 60 min (junto ao git_scheduled_commit),
//  e manualmente via SyncView.
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

// ─── Structs de retorno ──────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct BackupReport {
    pub backed_up: Vec<String>,
    pub failed:    Vec<String>,
    pub timestamp: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RestoreReport {
    pub app:       String,
    pub restored:  Vec<String>,
    pub not_found: Vec<String>,
    pub errors:    Vec<String>,
    pub timestamp: String,
}

// ─── Helpers de path ─────────────────────────────────────────────────────────

fn sync_root() -> Option<PathBuf> {
    let eco = ecosystem::read_json();
    let root = eco["sync_root"].as_str()?.trim().to_string();
    if root.is_empty() { return None; }
    let p = PathBuf::from(root);
    p.is_dir().then_some(p)
}

fn backup_dir(sync_root: &Path) -> PathBuf {
    sync_root.join(".backup")
}

fn akasha_db_path(eco: &Value) -> Option<PathBuf> {
    let data = eco["akasha"]["data_path"].as_str()?;
    let p = PathBuf::from(data).join("akasha.db");
    p.exists().then_some(p)
}

fn akasha_userdata_path(eco: &Value) -> Option<PathBuf> {
    let data = eco["akasha"]["data_path"].as_str()?;
    let p = PathBuf::from(data).join("userdata");
    p.is_dir().then_some(p)
}

fn kosmos_db_path(eco: &Value) -> Option<PathBuf> {
    if let Some(dp) = eco["kosmos"]["data_path"].as_str() {
        let p = PathBuf::from(dp).join("kosmos.db");
        if p.exists() { return Some(p); }
    }
    if let Some(ap) = eco["kosmos"]["archive_path"].as_str() {
        let p = PathBuf::from(ap).parent()?.join("kosmos.db");
        if p.exists() { return Some(p); }
    }
    None
}

fn ecosystem_json_path() -> Option<PathBuf> {
    dirs::data_dir().map(|b| b.join("ecosystem").join("ecosystem.json"))
}

/// Escreve `content` em `dest` de forma atômica (via arquivo .tmp).
fn atomic_write(dest: &Path, content: &[u8]) -> Result<(), String> {
    let tmp = dest.with_extension("tmp");
    std::fs::write(&tmp, content).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, dest).map_err(|e| e.to_string())
}

// ─── backup_key_data ────────────────────────────────────────────────────────

/// Exporta os dados chave do ecossistema para `.backup/`.
///
/// Falhas individuais são registradas em `report.failed` — a função nunca
/// retorna `Err` por causa de uma fonte indisponível.
#[tauri::command]
pub fn backup_key_data() -> Result<BackupReport, AppError> {
    let eco = ecosystem::read_json();
    let root = sync_root().ok_or_else(|| {
        AppError::MissingConfig("sync_root não configurado".into())
    })?;
    let bdir = backup_dir(&root);
    std::fs::create_dir_all(bdir.join("akasha"))
        .map_err(|e| AppError::Io(e.to_string()))?;
    std::fs::create_dir_all(bdir.join("kosmos"))
        .map_err(|e| AppError::Io(e.to_string()))?;

    let mut backed_up: Vec<String> = Vec::new();
    let mut failed:    Vec<String> = Vec::new();
    let timestamp = Utc::now().to_rfc3339();

    // ── 1. AKASHA crawl_sites ────────────────────────────────────────────────
    match backup_akasha_sites(&eco, &bdir) {
        Ok(path) => backed_up.push(path),
        Err(e)   => failed.push(format!("akasha/sites.json: {e}")),
    }

    // ── 2. AKASHA userdata JSONs ─────────────────────────────────────────────
    for filename in &["blocked_domains.json", "watch_later.json", "lenses.json", "favorites.json"] {
        match backup_akasha_userdata_file(&eco, &bdir, filename) {
            Ok(path) => backed_up.push(path),
            Err(e)   => failed.push(format!("akasha/{filename}: {e}")),
        }
    }

    // ── 3. KOSMOS feeds ──────────────────────────────────────────────────────
    match backup_kosmos_feeds(&eco, &bdir) {
        Ok(path) => backed_up.push(path),
        Err(e)   => failed.push(format!("kosmos/sources.json: {e}")),
    }

    // ── 4. ecosystem.json ────────────────────────────────────────────────────
    match backup_ecosystem_json(&bdir) {
        Ok(path) => backed_up.push(path),
        Err(e)   => failed.push(format!("ecosystem.json: {e}")),
    }

    Ok(BackupReport { backed_up, failed, timestamp })
}

fn backup_akasha_sites(eco: &Value, bdir: &Path) -> Result<String, String> {
    let db_path = akasha_db_path(eco).ok_or("akasha.db não encontrado")?;
    let conn = Connection::open_with_flags(
        &db_path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    ).map_err(|e| e.to_string())?;

    let mut stmt = conn.prepare(
        "SELECT base_url, label, crawl_depth, crawl_interval_days \
         FROM crawl_sites WHERE deleted = 0 ORDER BY label ASC"
    ).map_err(|e| e.to_string())?;

    let sites: Vec<Value> = stmt.query_map(params![], |row| {
        Ok(json!({
            "base_url":            row.get::<_, String>(0)?,
            "label":               row.get::<_, String>(1)?,
            "crawl_depth":         row.get::<_, i64>(2)?,
            "crawl_interval_days": row.get::<_, i64>(3)?,
        }))
    }).map_err(|e| e.to_string())?
    .filter_map(|r| r.ok())
    .collect();

    let dest = bdir.join("akasha").join("sites.json");
    let content = serde_json::to_vec_pretty(&sites).map_err(|e| e.to_string())?;
    atomic_write(&dest, &content)?;
    Ok(dest.display().to_string())
}

fn backup_akasha_userdata_file(eco: &Value, bdir: &Path, filename: &str) -> Result<String, String> {
    let userdata = akasha_userdata_path(eco).ok_or("akasha/userdata não encontrado")?;
    let src = userdata.join(filename);
    if !src.exists() {
        return Err(format!("{filename} não existe em userdata"));
    }
    let content = std::fs::read(&src).map_err(|e| e.to_string())?;
    let dest = bdir.join("akasha").join(filename);
    atomic_write(&dest, &content)?;
    Ok(dest.display().to_string())
}

fn backup_kosmos_feeds(eco: &Value, bdir: &Path) -> Result<String, String> {
    let db_path = kosmos_db_path(eco).ok_or("kosmos.db não encontrado")?;
    let conn = Connection::open_with_flags(
        &db_path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    ).map_err(|e| e.to_string())?;

    let mut stmt = conn.prepare(
        "SELECT url, name, feed_type, active FROM feeds ORDER BY name ASC"
    ).map_err(|e| e.to_string())?;

    let feeds: Vec<Value> = stmt.query_map(params![], |row| {
        Ok(json!({
            "url":       row.get::<_, String>(0)?,
            "name":      row.get::<_, String>(1)?,
            "feed_type": row.get::<_, String>(2)?,
            "active":    row.get::<_, bool>(3)?,
        }))
    }).map_err(|e| e.to_string())?
    .filter_map(|r| r.ok())
    .collect();

    let dest = bdir.join("kosmos").join("sources.json");
    let content = serde_json::to_vec_pretty(&feeds).map_err(|e| e.to_string())?;
    atomic_write(&dest, &content)?;
    Ok(dest.display().to_string())
}

fn backup_ecosystem_json(bdir: &Path) -> Result<String, String> {
    let src = ecosystem_json_path().ok_or("ecosystem.json não encontrado")?;
    if !src.exists() {
        return Err("ecosystem.json não existe".into());
    }
    let content = std::fs::read(&src).map_err(|e| e.to_string())?;
    let dest = bdir.join("ecosystem.json");
    atomic_write(&dest, &content)?;
    Ok(dest.display().to_string())
}

// ─── restore_from_backup ────────────────────────────────────────────────────

/// Restaura dados de um app a partir dos backups em `.backup/`.
///
/// `app`: `"akasha"` | `"kosmos"` | `"ecosystem"`
#[tauri::command]
pub fn restore_from_backup(app: String) -> Result<RestoreReport, AppError> {
    let root = sync_root().ok_or_else(|| {
        AppError::MissingConfig("sync_root não configurado".into())
    })?;
    let bdir = backup_dir(&root);
    let eco = ecosystem::read_json();
    let timestamp = Utc::now().to_rfc3339();

    let mut restored:  Vec<String> = Vec::new();
    let mut not_found: Vec<String> = Vec::new();
    let mut errors:    Vec<String> = Vec::new();

    match app.as_str() {
        "akasha" => restore_akasha(&eco, &bdir, &mut restored, &mut not_found, &mut errors),
        "kosmos" => restore_kosmos(&eco, &bdir, &mut restored, &mut not_found, &mut errors),
        "ecosystem" => restore_ecosystem_json_backup(&bdir, &mut restored, &mut not_found, &mut errors),
        other => errors.push(format!("app desconhecido: {other}")),
    }

    Ok(RestoreReport { app, restored, not_found, errors, timestamp })
}

fn restore_akasha(
    eco:       &Value,
    bdir:      &Path,
    restored:  &mut Vec<String>,
    not_found: &mut Vec<String>,
    errors:    &mut Vec<String>,
) {
    // 1. Restaurar crawl_sites a partir de sites.json
    let sites_backup = bdir.join("akasha").join("sites.json");
    if !sites_backup.exists() {
        not_found.push("akasha/sites.json".into());
    } else {
        match restore_akasha_sites(eco, &sites_backup) {
            Ok(n)  => restored.push(format!("crawl_sites: {n} sites restaurados")),
            Err(e) => errors.push(format!("crawl_sites: {e}")),
        }
    }

    // 2. Restaurar userdata JSONs
    if let Some(userdata) = akasha_userdata_path(eco) {
        for filename in &["blocked_domains.json", "watch_later.json", "lenses.json", "favorites.json"] {
            let src = bdir.join("akasha").join(filename);
            if !src.exists() {
                not_found.push(format!("akasha/{filename}"));
                continue;
            }
            let dest = userdata.join(filename);
            match std::fs::copy(&src, &dest) {
                Ok(_)  => restored.push(format!("userdata/{filename}")),
                Err(e) => errors.push(format!("userdata/{filename}: {e}")),
            }
        }
    } else {
        errors.push("akasha/userdata não encontrado — não foi possível restaurar JSONs".into());
    }
}

fn restore_akasha_sites(eco: &Value, backup_path: &Path) -> Result<usize, String> {
    let db_path = akasha_db_path(eco).ok_or("akasha.db não encontrado")?;

    let content = std::fs::read_to_string(backup_path).map_err(|e| e.to_string())?;
    let sites: Vec<Value> = serde_json::from_str(&content).map_err(|e| e.to_string())?;

    let conn = Connection::open(&db_path).map_err(|e| e.to_string())?;

    // Usar INSERT OR IGNORE para não sobrescrever entradas existentes
    let mut count = 0usize;
    for site in &sites {
        let base_url           = site["base_url"].as_str().unwrap_or("");
        let label              = site["label"].as_str().unwrap_or(base_url);
        let crawl_depth        = site["crawl_depth"].as_i64().unwrap_or(2);
        let crawl_interval     = site["crawl_interval_days"].as_i64().unwrap_or(7);

        if base_url.is_empty() { continue; }

        conn.execute(
            "INSERT OR IGNORE INTO crawl_sites \
             (base_url, label, crawl_depth, crawl_interval_days, deleted, status, created_at) \
             VALUES (?1, ?2, ?3, ?4, 0, 'idle', datetime('now'))",
            params![base_url, label, crawl_depth, crawl_interval],
        ).map_err(|e| e.to_string())?;
        count += 1;
    }

    Ok(count)
}

fn restore_kosmos(
    _eco:      &Value,
    _bdir:     &Path,
    _restored: &mut Vec<String>,
    not_found: &mut Vec<String>,
    _errors:   &mut Vec<String>,
) {
    // KOSMOS feeds são gerenciados pelo próprio app (não há migration automática segura).
    // O backup existe para consulta manual; a restauração programática não é suportada.
    not_found.push(
        "kosmos: restauração automática de feeds não suportada — use o backup JSON manualmente".into()
    );
}

fn restore_ecosystem_json_backup(
    bdir:      &Path,
    restored:  &mut Vec<String>,
    not_found: &mut Vec<String>,
    errors:    &mut Vec<String>,
) {
    let src = bdir.join("ecosystem.json");
    if !src.exists() {
        not_found.push("ecosystem.json".into());
        return;
    }
    let dest = match ecosystem_json_path() {
        Some(p) => p,
        None => { errors.push("não foi possível resolver ecosystem_json_path".into()); return; }
    };
    match std::fs::copy(&src, &dest) {
        Ok(_)  => restored.push("ecosystem.json".into()),
        Err(e) => errors.push(format!("ecosystem.json: {e}")),
    }
}

// ─── Testes ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn make_fake_akasha_db(dir: &Path) -> PathBuf {
        let db_path = dir.join("akasha.db");
        let conn = Connection::open(&db_path).unwrap();
        conn.execute_batch(
            "CREATE TABLE crawl_sites (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                base_url           TEXT NOT NULL UNIQUE,
                label              TEXT NOT NULL DEFAULT '',
                crawl_depth        INTEGER NOT NULL DEFAULT 2,
                subdomains_json    TEXT NOT NULL DEFAULT '[]',
                page_count         INTEGER NOT NULL DEFAULT 0,
                last_crawled_at    TEXT,
                status             TEXT NOT NULL DEFAULT 'idle',
                created_at         TEXT NOT NULL DEFAULT (datetime('now')),
                crawl_interval_days INTEGER NOT NULL DEFAULT 7,
                deleted            INTEGER NOT NULL DEFAULT 0,
                crawl_fail_count   INTEGER NOT NULL DEFAULT 0,
                crawl_frequency    TEXT NOT NULL DEFAULT 'weekly',
                next_crawl_at      INTEGER NOT NULL DEFAULT 0,
                content_hash       TEXT NOT NULL DEFAULT ''
             );
             INSERT INTO crawl_sites (base_url, label, crawl_depth, crawl_interval_days, deleted)
             VALUES ('https://example.com', 'Example', 2, 7, 0),
                    ('https://deleted.com', 'Deleted', 2, 7, 1);",
        ).unwrap();
        db_path
    }

    fn make_fake_kosmos_db(dir: &Path) -> PathBuf {
        let db_path = dir.join("kosmos.db");
        let conn = Connection::open(&db_path).unwrap();
        conn.execute_batch(
            "CREATE TABLE feeds (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                url       TEXT NOT NULL UNIQUE,
                name      TEXT NOT NULL DEFAULT '',
                feed_type TEXT NOT NULL DEFAULT 'rss',
                active    INTEGER NOT NULL DEFAULT 1
             );
             INSERT INTO feeds (url, name, feed_type, active)
             VALUES ('https://feed.example.com/rss', 'Example Feed', 'rss', 1);",
        ).unwrap();
        db_path
    }

    fn make_eco(akasha_data: &Path, kosmos_data: &Path) -> Value {
        json!({
            "akasha": { "data_path": akasha_data.display().to_string() },
            "kosmos": { "data_path": kosmos_data.display().to_string() },
        })
    }

    // ─── backup_akasha_sites ─────────────────────────────────────────────────

    #[test]
    fn test_backup_akasha_sites_from_db() {
        let tmp = tempfile::tempdir().unwrap();
        make_fake_akasha_db(tmp.path());
        let bdir = tmp.path().join(".backup");
        std::fs::create_dir_all(bdir.join("akasha")).unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        backup_akasha_sites(&eco, &bdir).unwrap();

        let content = std::fs::read_to_string(bdir.join("akasha/sites.json")).unwrap();
        let sites: Vec<Value> = serde_json::from_str(&content).unwrap();
        // deleted=1 deve ser excluído
        assert_eq!(sites.len(), 1, "só sites não deletados devem aparecer");
        assert_eq!(sites[0]["base_url"], "https://example.com");
    }

    #[test]
    fn test_backup_akasha_sites_db_not_found() {
        let tmp = tempfile::tempdir().unwrap();
        let bdir = tmp.path().join(".backup");
        let eco = json!({ "akasha": { "data_path": tmp.path().display().to_string() } });
        // akasha.db não existe neste dir
        let result = backup_akasha_sites(&eco, &bdir);
        assert!(result.is_err());
    }

    // ─── backup_kosmos_feeds ─────────────────────────────────────────────────

    #[test]
    fn test_backup_kosmos_feeds_from_db() {
        let tmp = tempfile::tempdir().unwrap();
        make_fake_kosmos_db(tmp.path());
        let bdir = tmp.path().join(".backup");
        std::fs::create_dir_all(bdir.join("kosmos")).unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        backup_kosmos_feeds(&eco, &bdir).unwrap();

        let content = std::fs::read_to_string(bdir.join("kosmos/sources.json")).unwrap();
        let feeds: Vec<Value> = serde_json::from_str(&content).unwrap();
        assert_eq!(feeds.len(), 1);
        assert_eq!(feeds[0]["url"], "https://feed.example.com/rss");
    }

    // ─── atomic_write ────────────────────────────────────────────────────────

    #[test]
    fn test_backup_atomic_write_leaves_no_tmp_file() {
        let tmp = tempfile::tempdir().unwrap();
        let dest = tmp.path().join("out.json");
        atomic_write(&dest, b"{}").unwrap();
        let tmps: Vec<_> = std::fs::read_dir(tmp.path()).unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map(|x| x == "tmp").unwrap_or(false))
            .collect();
        assert!(tmps.is_empty(), "arquivo .tmp não deve sobrar após escrita atômica");
    }

    // ─── restore_akasha_sites ────────────────────────────────────────────────

    #[test]
    fn test_restore_from_backup_akasha() {
        let tmp = tempfile::tempdir().unwrap();
        // DB vazio (sem sites)
        let db_path = tmp.path().join("akasha.db");
        let conn = Connection::open(&db_path).unwrap();
        conn.execute_batch(
            "CREATE TABLE crawl_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_url TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                crawl_depth INTEGER NOT NULL DEFAULT 2,
                subdomains_json TEXT NOT NULL DEFAULT '[]',
                page_count INTEGER NOT NULL DEFAULT 0,
                last_crawled_at TEXT,
                status TEXT NOT NULL DEFAULT 'idle',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                crawl_interval_days INTEGER NOT NULL DEFAULT 7,
                deleted INTEGER NOT NULL DEFAULT 0,
                crawl_fail_count INTEGER NOT NULL DEFAULT 0,
                crawl_frequency TEXT NOT NULL DEFAULT 'weekly',
                next_crawl_at INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT ''
             );",
        ).unwrap();
        drop(conn);

        // Criar backup com 2 sites
        let backup = tmp.path().join("sites_backup.json");
        let sites = json!([
            {"base_url": "https://a.com", "label": "A", "crawl_depth": 2, "crawl_interval_days": 7},
            {"base_url": "https://b.com", "label": "B", "crawl_depth": 3, "crawl_interval_days": 14},
        ]);
        std::fs::write(&backup, sites.to_string()).unwrap();

        let eco = json!({ "akasha": { "data_path": tmp.path().display().to_string() } });
        let n = restore_akasha_sites(&eco, &backup).unwrap();
        assert_eq!(n, 2);

        // Verificar que os sites foram inseridos
        let conn = Connection::open(&db_path).unwrap();
        let count: i64 = conn.query_row("SELECT count(*) FROM crawl_sites", [], |r| r.get(0)).unwrap();
        assert_eq!(count, 2);
    }
}
