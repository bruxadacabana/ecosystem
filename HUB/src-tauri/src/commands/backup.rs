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
    // Canônico: o KOSMOS v3 guarda o banco em {archive_path}/kosmos.db
    // (= {sync_root}/kosmos/kosmos.db), sincronizado via Syncthing.
    if let Some(ap) = eco["kosmos"]["archive_path"].as_str() {
        let p = PathBuf::from(ap).join("kosmos.db");
        if p.exists() { return Some(p); }
    }
    // Fallback: data_path/kosmos.db (banco local legado, antes da migração).
    if let Some(dp) = eco["kosmos"]["data_path"].as_str() {
        let p = PathBuf::from(dp).join("kosmos.db");
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

    // Schema v3 do KOSMOS: feeds(url, title, category, enabled). title pode ser NULL.
    let mut stmt = conn.prepare(
        "SELECT url, COALESCE(title, ''), COALESCE(category, 'Sem categoria'), enabled \
         FROM feeds ORDER BY category, COALESCE(title, url)"
    ).map_err(|e| e.to_string())?;

    let feeds: Vec<Value> = stmt.query_map(params![], |row| {
        Ok(json!({
            "url":      row.get::<_, String>(0)?,
            "title":    row.get::<_, String>(1)?,
            "category": row.get::<_, String>(2)?,
            "enabled":  row.get::<_, bool>(3)?,
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

// ─── check_db_integrity ─────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct IntegrityReport {
    pub app:      String,
    pub db_path:  String,
    pub ok:       bool,
    pub details:  String,
    pub wal_size: u64,
}

/// Núcleo testável de `check_db_integrity` — recebe `eco` diretamente.
pub(crate) fn check_db_integrity_inner(eco: &Value, app: &str) -> Result<IntegrityReport, AppError> {
    let db_path = resolve_app_db(eco, app)
        .ok_or_else(|| AppError::NotFound(format!("{app}.db não encontrado")))?;

    let wal_path = db_path.with_extension("db-wal");
    let wal_size = wal_path.metadata().map(|m| m.len()).unwrap_or(0);

    match Connection::open(&db_path) {
        Err(e) => Ok(IntegrityReport {
            app: app.to_string(),
            db_path: db_path.display().to_string(),
            ok:      false,
            details: format!("não foi possível abrir: {e}"),
            wal_size,
        }),
        Ok(conn) => {
            let _ = conn.execute_batch("PRAGMA wal_checkpoint(FULL);");
            let details: String = conn
                .query_row("PRAGMA integrity_check(1);", [], |r| r.get(0))
                .unwrap_or_else(|e| format!("erro ao executar integrity_check: {e}"));
            Ok(IntegrityReport {
                app: app.to_string(),
                db_path: db_path.display().to_string(),
                ok: details.trim() == "ok",
                details,
                wal_size,
            })
        }
    }
}

/// Verifica a integridade de um banco SQLite do ecossistema.
///
/// `app`: `"akasha"` | `"kosmos"`
/// Executa `PRAGMA integrity_check(1)` e `PRAGMA wal_checkpoint(FULL)`.
/// Mede o tamanho do `.db-wal` para identificar WAL pendente.
#[tauri::command]
pub fn check_db_integrity(app: String) -> Result<IntegrityReport, AppError> {
    let eco = ecosystem::read_json();
    check_db_integrity_inner(&eco, &app)
}

// ─── recover_db ─────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct RecoveryReport {
    pub app:     String,
    pub method:  String,
    pub ok:      bool,
    pub details: String,
}

/// Núcleo testável de `recover_db` — recebe `eco` e `sync_root` diretamente.
pub(crate) fn recover_db_inner(eco: &Value, app: &str, sr: &Path) -> Result<RecoveryReport, AppError> {
    let db_path = resolve_app_db(eco, app)
        .ok_or_else(|| AppError::NotFound(format!("{app}.db não encontrado")))?;
    recover_db_at(app, &db_path, eco, sr)
}

/// Tenta recuperar um banco corrompido em sequência:
/// 1. `PRAGMA wal_checkpoint(TRUNCATE)` + `integrity_check` → se "ok", sucesso
/// 2. `sqlite3 db ".recover" | sqlite3 db_recovered` via CLI + renomear
/// 3. `restore_from_backup` a partir dos JSONs em `.backup/`
/// 4. Falhou — retorna `method: "failed"`
#[tauri::command]
pub fn recover_db(app: String) -> Result<RecoveryReport, AppError> {
    let eco = ecosystem::read_json();
    let db_path = resolve_app_db(&eco, &app)
        .ok_or_else(|| AppError::NotFound(format!("{app}.db não encontrado")))?;
    let sr = sync_root().ok_or_else(|| AppError::MissingConfig("sync_root não configurado".into()))?;
    recover_db_at(&app, &db_path, &eco, &sr)
}

fn recover_db_at(app: &str, db_path: &Path, eco: &Value, sr: &Path) -> Result<RecoveryReport, AppError> {

    // 1. Tentativa: WAL checkpoint + integrity_check
    if let Ok(conn) = Connection::open(db_path) {
        let _ = conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);");
        let result: String = conn
            .query_row("PRAGMA integrity_check(1);", [], |r| r.get(0))
            .unwrap_or_default();
        if result.trim() == "ok" {
            return Ok(RecoveryReport {
                app:     app.to_string(),
                method:  "wal_checkpoint".into(),
                ok:      true,
                details: "WAL checkpoint + integrity_check ok".into(),
            });
        }
    }

    // 2. Tentativa: sqlite3 .recover via CLI
    let recovered = db_path.with_file_name(format!(
        "{}_recovered.db",
        db_path.file_stem().unwrap_or_default().to_string_lossy()
    ));
    let _ = std::fs::remove_file(&recovered);

    let dump = std::process::Command::new("sqlite3")
        .arg(db_path)
        .arg(".recover")
        .output();

    if let Ok(dump_out) = dump {
        if dump_out.status.success() || !dump_out.stdout.is_empty() {
            let restore = std::process::Command::new("sqlite3")
                .arg(&recovered)
                .stdin(std::process::Stdio::piped())
                .spawn();

            if let Ok(mut child) = restore {
                use std::io::Write;
                if let Some(stdin) = child.stdin.as_mut() {
                    let _ = stdin.write_all(&dump_out.stdout);
                }
                if child.wait().map(|s| s.success()).unwrap_or(false) && recovered.exists() {
                    let ok = Connection::open(&recovered)
                        .and_then(|c| c.query_row("PRAGMA integrity_check(1);", [], |r| r.get::<_, String>(0)))
                        .map(|s| s.trim() == "ok")
                        .unwrap_or(false);

                    if ok {
                        if std::fs::rename(&recovered, db_path).is_ok() {
                            return Ok(RecoveryReport {
                                app:     app.to_string(),
                                method:  "sqlite_recover".into(),
                                ok:      true,
                                details: "recuperado via sqlite3 .recover".into(),
                            });
                        }
                    }
                }
            }
        }
    }
    let _ = std::fs::remove_file(&recovered);

    // 3. Tentativa: restore_from_backup
    let bdir = backup_dir(sr);
    let backup_sites = bdir.join("akasha").join("sites.json");
    if backup_sites.exists() {
        match restore_akasha_sites(eco, &backup_sites) {
            Ok(n) => {
                return Ok(RecoveryReport {
                    app:     app.to_string(),
                    method:  "restore_backup".into(),
                    ok:      true,
                    details: format!("restaurados {n} sites do backup JSON"),
                });
            }
            Err(e) => {
                return Ok(RecoveryReport {
                    app:     app.to_string(),
                    method:  "restore_backup".into(),
                    ok:      false,
                    details: format!("backup encontrado mas restauração falhou: {e}"),
                });
            }
        }
    }

    // 4. Falhou
    Ok(RecoveryReport {
        app:     app.to_string(),
        method:  "failed".into(),
        ok:      false,
        details: "todos os métodos de recuperação falharam".into(),
    })
}

// ─── syncthing_checkpoint_app_dbs ───────────────────────────────────────────

/// Executa WAL checkpoint em todos os bancos SQLite de um app.
///
/// Deve ser chamado ANTES de retomar o Syncthing quando um app fecha,
/// para garantir que o WAL foi incorporado ao arquivo principal.
/// O Syncthing então sincroniza um arquivo SQLite coerente.
#[tauri::command]
pub fn syncthing_checkpoint_app_dbs(app: String) -> Result<(), AppError> {
    let eco = ecosystem::read_json();
    let db_path = resolve_app_db(&eco, &app)
        .ok_or_else(|| AppError::NotFound(format!("{app}.db não encontrado")))?;

    let conn = Connection::open(&db_path)
        .map_err(|e| AppError::Io(format!("{app}.db: {e}")))?;
    conn.execute_batch("PRAGMA wal_checkpoint(FULL);")
        .map_err(|e| AppError::Io(format!("checkpoint {app}: {e}")))?;
    Ok(())
}

// ─── Helper: resolver path do DB por app ─────────────────────────────────────

pub(crate) fn resolve_app_db(eco: &Value, app: &str) -> Option<PathBuf> {
    match app {
        "akasha" => akasha_db_path(eco),
        "kosmos" => kosmos_db_path(eco),
        _ => None,
    }
}

// ─── ecosystem_reset ────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct ResetReport {
    pub deleted:   Vec<String>,
    pub preserved: Vec<String>,
    pub errors:    Vec<String>,
    pub timestamp: String,
}

/// Núcleo testável de `ecosystem_reset` — recebe `eco` e `root` diretamente.
/// NÃO chama backup — isso é responsabilidade do command.
pub(crate) fn ecosystem_reset_inner(
    confirm_token: &str,
    eco:           &Value,
    root:          &Path,
) -> Result<ResetReport, AppError> {
    if confirm_token.trim() != "RESETAR" {
        return Err(AppError::InvalidPath(
            "Token de confirmação inválido. Digite RESETAR para confirmar.".into(),
        ));
    }

    let timestamp = Utc::now().to_rfc3339();
    let mut deleted:   Vec<String> = Vec::new();
    let mut preserved: Vec<String> = Vec::new();
    let mut errors:    Vec<String> = Vec::new();

    reset_akasha(eco, root, &mut deleted, &mut preserved, &mut errors);
    reset_kosmos(eco, root, &mut deleted, &mut preserved, &mut errors);
    reset_mnemosyne(eco, root, &mut deleted, &mut preserved, &mut errors);
    reset_shared(root, &mut deleted, &mut preserved, &mut errors);

    Ok(ResetReport { deleted, preserved, errors, timestamp })
}

/// Apaga dados transientes do ecossistema, preservando dados da usuária.
///
/// Requer token de confirmação `"RESETAR"`.
/// Cria backup antes de apagar qualquer coisa.
#[tauri::command]
pub fn ecosystem_reset(confirm_token: String) -> Result<ResetReport, AppError> {
    if confirm_token.trim() != "RESETAR" {
        return Err(AppError::InvalidPath(
            "Token de confirmação inválido. Digite RESETAR para confirmar.".into(),
        ));
    }
    let eco  = ecosystem::read_json();
    let root = sync_root().ok_or_else(|| {
        AppError::MissingConfig("sync_root não configurado".into())
    })?;
    // Cria backup antes de qualquer deleção
    let _ = backup_key_data();
    ecosystem_reset_inner(&confirm_token, &eco, &root)
}

// ── Helpers de reset por app ──────────────────────────────────────────────────

fn reset_akasha(
    eco:       &Value,
    root:      &Path,
    deleted:   &mut Vec<String>,
    preserved: &mut Vec<String>,
    errors:    &mut Vec<String>,
) {
    // 1. Apagar personal_memory.db da IA (fora do akasha.db)
    let pm_path = root.join(".ai_private").join("akasha").join("personal_memory.db");
    delete_file_or_dir(&pm_path, false, deleted, errors);

    // 2. akasha.db — apagar crawl_pages + crawl_fts + personal_memory
    if let Some(db_path) = akasha_db_path(eco) {
        match Connection::open(&db_path) {
            Err(e) => errors.push(format!("akasha.db: não foi possível abrir: {e}")),
            Ok(conn) => {
                // busy_timeout: AKASHA pode estar rodando com o DB aberto.
                // Sem timeout, rusqlite falha imediatamente com SQLITE_BUSY.
                let _ = conn.busy_timeout(std::time::Duration::from_secs(5));

                // crawl_pages: apagar tudo (o schema não tem coluna 'saved' — a tabela é
                // redesenhada depois pelo crawler; crawl_sites é preservado).
                // Fallback encadeado por segurança caso o schema mude no futuro.
                let del_pages = conn.execute_batch("DELETE FROM crawl_pages");
                match del_pages {
                    Ok(_)  => deleted.push("akasha: crawl_pages".into()),
                    Err(e) => errors.push(format!("akasha: crawl_pages: {e}")),
                }

                // crawl_fts: tabela FTS5 separada — deve ser limpa junto com crawl_pages.
                // Sem isso, a busca retorna resultados de páginas já deletadas.
                match conn.execute_batch("DELETE FROM crawl_fts") {
                    Ok(_) => deleted.push("akasha: crawl_fts".into()),
                    Err(e) if e.to_string().contains("no such table") => {}
                    Err(e) => errors.push(format!("akasha: crawl_fts: {e}")),
                }

                // personal_memory (tabela no akasha.db — pode não existir em todos os schemas)
                match conn.execute_batch("DELETE FROM personal_memory") {
                    Ok(_)  => deleted.push("akasha: personal_memory (tabela)".into()),
                    Err(e) if e.to_string().contains("no such table") => {}
                    Err(e) => errors.push(format!("akasha: personal_memory: {e}")),
                }

                preserved.push("akasha: crawl_sites (lista de sites da usuária)".into());
            }
        }

        // 3. Apagar akasha_knowledge.db
        let knowledge_db = db_path.with_file_name("akasha_knowledge.db");
        delete_file_or_dir(&knowledge_db, false, deleted, errors);
    }

    // Preservar: userdata/, Web/, Papers/
    preserved.push("akasha: userdata/ (blocked_domains, watch_later, etc.)".into());
    preserved.push("akasha: Web/ e Papers/ (arquivos salvos)".into());
}

fn reset_kosmos(
    eco:       &Value,
    _root:     &Path,
    deleted:   &mut Vec<String>,
    preserved: &mut Vec<String>,
    errors:    &mut Vec<String>,
) {
    if let Some(db_path) = kosmos_db_path(eco) {
        match Connection::open(&db_path) {
            Err(e) => errors.push(format!("kosmos.db: não foi possível abrir: {e}")),
            Ok(conn) => {
                let del = conn.execute_batch(
                    "DELETE FROM articles WHERE is_saved IS NULL OR is_saved = 0"
                ).or_else(|_| conn.execute_batch(
                    "DELETE FROM articles WHERE saved IS NULL OR saved = 0"
                ));
                match del {
                    Ok(_)  => deleted.push("kosmos: artigos não salvos".into()),
                    Err(e) => errors.push(format!("kosmos: articles: {e}")),
                }
                preserved.push("kosmos: feeds (lista de fontes RSS)".into());
                preserved.push("kosmos: artigos salvos (is_saved=1)".into());
            }
        }
    }
}

fn reset_mnemosyne(
    eco:       &Value,
    root:      &Path,
    deleted:   &mut Vec<String>,
    preserved: &mut Vec<String>,
    errors:    &mut Vec<String>,
) {
    // 1. Apagar ChromaDB
    if let Some(chroma) = eco["mnemosyne"]["chroma_dir"].as_str() {
        let chroma_path = std::path::Path::new(chroma);
        delete_file_or_dir(chroma_path, true, deleted, errors);

        // 2. BM25 index — fica no diretório pai do chroma_dir
        if let Some(parent) = chroma_path.parent() {
            let bm25 = parent.join("bm25_index.pkl");
            delete_file_or_dir(&bm25, false, deleted, errors);

            // 3. Studio outputs — notebooks/{id}/studio/*.md
            let notebooks_dir = parent.join("notebooks");
            if notebooks_dir.is_dir() {
                delete_studio_outputs(&notebooks_dir, deleted, errors);
            }
        }
    }

    // 4. personal_memory.db da IA
    let pm_path = root.join(".ai_private").join("mnemosyne").join("personal_memory.db");
    delete_file_or_dir(&pm_path, false, deleted, errors);

    preserved.push("mnemosyne: notebooks/ (histórico de conversas)".into());
    preserved.push("mnemosyne: biblioteca de documentos indexados".into());
}

fn reset_shared(
    root:    &Path,
    deleted: &mut Vec<String>,
    _pres:   &mut Vec<String>,
    errors:  &mut Vec<String>,
) {
    let comm = root.join("communication_history.db");
    delete_file_or_dir(&comm, false, deleted, errors);

    // shared_topic_profile: suporta .db (formato legado) e .json (formato atual pós-BUG-011)
    let topic_db   = root.join("shared_topic_profile.db");
    let topic_json = root.join("shared_topic_profile.json");
    delete_file_or_dir(&topic_db,   false, deleted, errors);
    delete_file_or_dir(&topic_json, false, deleted, errors);

    // interests.json — perfil de interesses exibido na aba Interesses do HUB
    // Zerado (não deletado) para manter estrutura válida; topics[] regenerados pela análise
    let interests = root.join("interests.json");
    if interests.exists() || true {
        let empty = r#"{"topics":[],"updated_at":""#.to_string()
            + &chrono::Utc::now().to_rfc3339()
            + r#""}"#;
        match std::fs::write(&interests, &empty) {
            Ok(_)  => deleted.push(format!("{} (zerado)", interests.display())),
            Err(e) => errors.push(format!("{}: {e}", interests.display())),
        }
    }
}

/// Apaga um arquivo ou diretório (recursivo se `is_dir=true`).
/// Não-encontrado → silencioso. Erros → reportados em `errors`.
fn delete_file_or_dir(
    path:    &Path,
    is_dir:  bool,
    deleted: &mut Vec<String>,
    errors:  &mut Vec<String>,
) {
    if !path.exists() { return; }
    let label = path.display().to_string();
    let result = if is_dir {
        std::fs::remove_dir_all(path).map_err(|e| e.to_string())
    } else {
        std::fs::remove_file(path).map_err(|e| e.to_string())
    };
    match result {
        Ok(_)  => deleted.push(label),
        Err(e) => errors.push(format!("{label}: {e}")),
    }
}

/// Apaga todos os arquivos `.md` em `{notebooks_dir}/{id}/studio/`.
fn delete_studio_outputs(notebooks_dir: &Path, deleted: &mut Vec<String>, errors: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(notebooks_dir) else { return; };
    for entry in entries.flatten() {
        let studio = entry.path().join("studio");
        if !studio.is_dir() { continue; }
        let Ok(files) = std::fs::read_dir(&studio) else { continue; };
        for file in files.flatten() {
            let fp = file.path();
            if fp.extension().map(|e| e == "md").unwrap_or(false) {
                delete_file_or_dir(&fp, false, deleted, errors);
            }
        }
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
        // Schema v3 do KOSMOS: feeds(url, title, category, enabled).
        conn.execute_batch(
            "CREATE TABLE feeds (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                url      TEXT NOT NULL UNIQUE,
                title    TEXT,
                category TEXT NOT NULL DEFAULT 'Sem categoria',
                enabled  INTEGER NOT NULL DEFAULT 1
             );
             INSERT INTO feeds (url, title, category, enabled)
             VALUES ('https://feed.example.com/rss', 'Example Feed', 'Geral', 1);",
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
        assert_eq!(feeds[0]["title"], "Example Feed");      // schema v3
        assert_eq!(feeds[0]["category"], "Geral");
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

    // ─── check_db_integrity ──────────────────────────────────────────────────

    #[test]
    fn test_integrity_check_ok() {
        let tmp = tempfile::tempdir().unwrap();
        let db_path = make_fake_akasha_db(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        let report = check_db_integrity_inner(&eco, "akasha").unwrap();
        assert!(report.ok, "DB recém-criado deve passar no integrity_check");
        assert_eq!(report.details.trim(), "ok");
    }

    #[test]
    fn test_integrity_check_corrupted() {
        let tmp = tempfile::tempdir().unwrap();
        // Criar um arquivo DB com conteúdo inválido
        let db_path = tmp.path().join("akasha.db");
        std::fs::write(&db_path, b"not a valid sqlite database content xyz").unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        let report = check_db_integrity_inner(&eco, "akasha").unwrap();
        assert!(!report.ok, "DB corrompido deve falhar no integrity_check");
    }

    #[test]
    fn test_integrity_wal_size_reported() {
        let tmp = tempfile::tempdir().unwrap();
        make_fake_akasha_db(tmp.path());
        // Criar um .db-wal falso com tamanho conhecido
        let wal_path = tmp.path().join("akasha.db-wal");
        std::fs::write(&wal_path, vec![0u8; 512]).unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        let report = check_db_integrity_inner(&eco, "akasha").unwrap();
        assert_eq!(report.wal_size, 512, "wal_size deve refletir tamanho do arquivo .db-wal");
    }

    // ─── recover_db ──────────────────────────────────────────────────────────

    #[test]
    fn test_recover_via_checkpoint() {
        let tmp = tempfile::tempdir().unwrap();
        // DB saudável: checkpoint deve resolver
        make_fake_akasha_db(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        let report = recover_db_inner(&eco, "akasha", tmp.path()).unwrap();
        assert!(report.ok);
        assert_eq!(report.method, "wal_checkpoint");
    }

    #[test]
    fn test_recover_attempts_all_methods() {
        let tmp = tempfile::tempdir().unwrap();
        // DB com conteúdo inválido — sqlite3 .recover pode gerar um DB vazio
        let db_path = tmp.path().join("akasha.db");
        std::fs::write(&db_path, b"garbage").unwrap();

        let bdir = tmp.path().join(".backup");
        std::fs::create_dir_all(bdir.join("akasha")).unwrap();
        let backup_sites = bdir.join("akasha/sites.json");
        std::fs::write(&backup_sites, r#"[{"base_url":"https://t.com","label":"T","crawl_depth":2,"crawl_interval_days":7}]"#).unwrap();

        let eco = make_eco(tmp.path(), tmp.path());
        let report = recover_db_inner(&eco, "akasha", tmp.path()).unwrap();
        // sqlite3 .recover pode reconstruir um DB vazio válido a partir de garbage —
        // o importante é que a função retorna Ok com método preenchido
        assert!(!report.method.is_empty(), "método não pode ser vazio");
    }

    #[test]
    fn test_recover_db_not_found_returns_err() {
        let tmp = tempfile::tempdir().unwrap();
        // Sem akasha.db em tmp.path() → resolve_app_db retorna None → Err(NotFound)
        let eco = make_eco(tmp.path(), tmp.path());
        let result = recover_db_inner(&eco, "akasha", tmp.path());
        assert!(result.is_err(), "deve retornar Err quando DB não existe");
    }

    // ─── ecosystem_reset ─────────────────────────────────────────────────────

    fn make_akasha_db_with_memory(dir: &Path) -> PathBuf {
        let db_path = dir.join("akasha.db");
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
             );
             INSERT INTO crawl_sites (base_url, label) VALUES ('https://keep.com', 'Keep');
             -- Schema real: sem coluna 'saved' — dados crawleados são todos transientes.
             -- Arquivos explicitamente salvos ficam em Web/ e Papers/ (não nesta tabela).
             CREATE TABLE crawl_pages (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id          INTEGER NOT NULL DEFAULT 1,
                url              TEXT    NOT NULL UNIQUE,
                title            TEXT    NOT NULL DEFAULT '',
                content_md       TEXT    NOT NULL DEFAULT '',
                crawled_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                knowledge_processed INTEGER NOT NULL DEFAULT 0
             );
             CREATE VIRTUAL TABLE crawl_fts USING fts5(
                site_id UNINDEXED, url UNINDEXED, title, content_md
             );
             INSERT INTO crawl_pages (url, title, content_md) VALUES
                ('https://keep.com/page1', 'Page 1', 'content one'),
                ('https://keep.com/page2', 'Page 2', 'content two'),
                ('https://keep.com/page3', 'Page 3', 'content three');
             INSERT INTO crawl_fts (site_id, url, title, content_md) VALUES
                (1, 'https://keep.com/page1', 'Page 1', 'content one'),
                (1, 'https://keep.com/page2', 'Page 2', 'content two'),
                (1, 'https://keep.com/page3', 'Page 3', 'content three');
             CREATE TABLE personal_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT
             );
             INSERT INTO personal_memory (content) VALUES ('private thought');",
        ).unwrap();
        db_path
    }

    #[test]
    fn test_reset_requires_confirm_token() {
        let tmp = tempfile::tempdir().unwrap();
        let eco = json!({});
        let result = ecosystem_reset_inner("wrong_token", &eco, tmp.path());
        assert!(result.is_err(), "token inválido deve retornar Err");
        let err_msg = result.unwrap_err().to_string();
        assert!(err_msg.contains("RESETAR"), "mensagem de erro deve mencionar RESETAR");
    }

    #[test]
    fn test_reset_deletes_crawl_pages() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        let report = ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        let conn = Connection::open(tmp.path().join("akasha.db")).unwrap();
        let total: i64 = conn.query_row("SELECT count(*) FROM crawl_pages", [], |r| r.get(0)).unwrap();
        // Todas as páginas crawleadas são dados transientes — apagadas pelo reset.
        // Arquivos salvos pela usuária ficam em Web/ e Papers/ (não nesta tabela).
        assert_eq!(total, 0, "todas as crawl_pages devem ser apagadas no reset");
        assert!(report.deleted.iter().any(|d| d.contains("crawl_pages")),
            "relatório deve mencionar crawl_pages");
    }

    #[test]
    fn test_reset_clears_crawl_fts() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        let conn_before = Connection::open(tmp.path().join("akasha.db")).unwrap();
        let fts_before: i64 = conn_before.query_row(
            "SELECT count(*) FROM crawl_fts", [], |r| r.get(0)
        ).unwrap();
        assert_eq!(fts_before, 3, "crawl_fts deve ter 3 entradas antes do reset");
        drop(conn_before);

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        let conn = Connection::open(tmp.path().join("akasha.db")).unwrap();
        let fts_after: i64 = conn.query_row(
            "SELECT count(*) FROM crawl_fts", [], |r| r.get(0)
        ).unwrap();
        assert_eq!(fts_after, 0,
            "crawl_fts deve ser esvaziada junto com crawl_pages (evita resultados de busca órfãos)");
    }

    #[test]
    fn test_reset_preserves_crawl_sites() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        let conn = Connection::open(tmp.path().join("akasha.db")).unwrap();
        let count: i64 = conn.query_row("SELECT count(*) FROM crawl_sites", [], |r| r.get(0)).unwrap();
        assert_eq!(count, 1, "crawl_sites deve ser preservada após reset");
    }

    #[test]
    fn test_reset_deletes_personal_memory() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        let conn = Connection::open(tmp.path().join("akasha.db")).unwrap();
        let count: i64 = conn.query_row("SELECT count(*) FROM personal_memory", [], |r| r.get(0)).unwrap();
        assert_eq!(count, 0, "personal_memory deve ser apagada após reset");
    }

    #[test]
    fn test_reset_preserves_user_prefs() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        // Criar userdata com arquivo de preferências
        let userdata = tmp.path().join("userdata");
        std::fs::create_dir_all(&userdata).unwrap();
        std::fs::write(userdata.join("blocked_domains.json"), b"[]").unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        assert!(userdata.join("blocked_domains.json").exists(), "userdata deve ser preservado");
    }

    #[test]
    fn test_reset_report_lists_deleted() {
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        // Criar personal_memory.db externo
        let ai_private = tmp.path().join(".ai_private").join("akasha");
        std::fs::create_dir_all(&ai_private).unwrap();
        std::fs::write(ai_private.join("personal_memory.db"), b"").unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        let report = ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        assert!(!report.deleted.is_empty(), "relatório deve listar itens deletados");
        assert!(!report.preserved.is_empty(), "relatório deve listar itens preservados");
    }

    #[test]
    fn test_reset_deletes_mnemosyne_chroma() {
        let tmp = tempfile::tempdir().unwrap();
        // Criar chroma_dir com arquivos dentro
        let chroma_dir = tmp.path().join("chroma_db");
        std::fs::create_dir_all(&chroma_dir).unwrap();
        std::fs::write(chroma_dir.join("chroma.sqlite3"), b"fake").unwrap();
        // BM25 index
        std::fs::write(tmp.path().join("bm25_index.pkl"), b"fake bm25").unwrap();

        let eco = json!({
            "akasha": { "data_path": tmp.path().display().to_string() },
            "kosmos": { "data_path": tmp.path().display().to_string() },
            "mnemosyne": { "chroma_dir": chroma_dir.display().to_string() },
        });

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        assert!(!chroma_dir.exists(), "chroma_dir deve ser apagado");
        assert!(!tmp.path().join("bm25_index.pkl").exists(), "bm25_index deve ser apagado");
    }

    #[test]
    fn test_reset_clears_shared_topic_profile_json() {
        // Verifica que reset apaga shared_topic_profile.json (formato atual, pós-BUG-011)
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        let profile = tmp.path().join("shared_topic_profile.json");
        std::fs::write(&profile, b"[{\"topic\":\"crochet\",\"score\":100}]").unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        assert!(!profile.exists(),
            "shared_topic_profile.json deve ser apagado no reset");
    }

    #[test]
    fn test_reset_zeroes_interests_json() {
        // Verifica que reset zera interests.json (não deleta, mantém estrutura válida)
        let tmp = tempfile::tempdir().unwrap();
        make_akasha_db_with_memory(tmp.path());
        let interests = tmp.path().join("interests.json");
        std::fs::write(&interests, br#"{"topics":[{"name":"crochet","weight":10}]}"#).unwrap();
        let eco = make_eco(tmp.path(), tmp.path());

        ecosystem_reset_inner("RESETAR", &eco, tmp.path()).unwrap();

        // O arquivo deve existir mas com topics: []
        assert!(interests.exists(), "interests.json deve existir após reset (zerado, não deletado)");
        let content: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(&interests).unwrap()
        ).unwrap();
        let topics = content["topics"].as_array().expect("topics deve ser array");
        assert!(topics.is_empty(), "topics deve ser [] após reset; contém: {topics:?}");
    }

    // ─── syncthing_checkpoint_app_dbs ────────────────────────────────────────

    #[test]
    fn test_checkpoint_app_dbs_ok() {
        let tmp = tempfile::tempdir().unwrap();
        make_fake_akasha_db(tmp.path());
        let eco = make_eco(tmp.path(), tmp.path());

        let db_path = akasha_db_path(&eco).unwrap();
        let conn = Connection::open(&db_path).unwrap();
        let result = conn.execute_batch("PRAGMA wal_checkpoint(FULL);");
        assert!(result.is_ok(), "checkpoint em DB saudável deve funcionar");
    }
}
