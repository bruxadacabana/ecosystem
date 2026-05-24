// ============================================================
//  HUB — commands/config.rs
//  Leitura, validação e escrita do ecosystem.json.
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use serde::{Deserialize, Serialize};
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

/// Lê as últimas `n` linhas do log de um app (ex: "mnemosyne").
///
/// O log fica em `{sync_root}/{app}/{app}.log`.
/// Retorna lista de strings vazia se o arquivo não existir.
#[tauri::command]
pub fn read_app_log(app: String, n: u32) -> Result<Vec<String>, AppError> {
    use std::io::{BufRead, BufReader};

    let eco = ecosystem::read_json();
    let sync_root = eco["sync_root"].as_str().unwrap_or("").to_string();
    if sync_root.is_empty() {
        return Ok(vec![]);
    }

    let log_path = std::path::Path::new(&sync_root)
        .join(&app)
        .join(format!("{app}.log"));

    if !log_path.exists() {
        return Ok(vec![]);
    }

    let file = std::fs::File::open(&log_path)?;
    let reader = BufReader::new(file);
    // filter_map para tolerar linhas com encoding inválido sem interromper a leitura
    let all: Vec<String> = reader.lines().filter_map(|l| l.ok()).collect();
    let n = n as usize;
    if all.len() > n {
        Ok(all[all.len() - n..].to_vec())
    } else {
        Ok(all)
    }
}

// ─── ServiceCredentials ──────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct ServiceCredentials {
    pub unpaywall_email:        String,
    pub qbt_host:               String,
    pub qbt_port:               u16,
    pub qbt_user:               String,
    pub qbt_password:           String,
    pub syncthing_gui_user:     String,
    pub syncthing_gui_password: String,
}

/// Núcleo testável de `get_service_credentials` — recebe `eco` diretamente.
pub(crate) fn get_service_credentials_inner(eco: &Value) -> ServiceCredentials {
    let akasha = &eco["akasha"];
    let hub    = &eco["hub"];
    ServiceCredentials {
        unpaywall_email:        akasha["unpaywall_email"].as_str().unwrap_or("").to_string(),
        qbt_host:               akasha["qbt_host"].as_str().unwrap_or("localhost").to_string(),
        qbt_port:               akasha["qbt_port"].as_u64().unwrap_or(8080) as u16,
        qbt_user:               akasha["qbt_user"].as_str().unwrap_or("").to_string(),
        qbt_password:           akasha["qbt_password"].as_str().unwrap_or("").to_string(),
        syncthing_gui_user:     hub["syncthing_gui_user"].as_str().unwrap_or("").to_string(),
        syncthing_gui_password: hub["syncthing_gui_password"].as_str().unwrap_or("").to_string(),
    }
}

/// Lê credenciais de serviços externos do ecosystem.json.
#[tauri::command]
pub fn get_service_credentials() -> Result<ServiceCredentials, AppError> {
    Ok(get_service_credentials_inner(&ecosystem::read_json()))
}

/// Salva credenciais de serviços externos no ecosystem.json.
#[tauri::command]
pub fn save_service_credentials(creds: ServiceCredentials) -> Result<(), AppError> {
    ecosystem::write_section("akasha", serde_json::json!({
        "unpaywall_email": creds.unpaywall_email,
        "qbt_host":        creds.qbt_host,
        "qbt_port":        creds.qbt_port,
        "qbt_user":        creds.qbt_user,
        "qbt_password":    creds.qbt_password,
    }))?;
    ecosystem::write_section("hub", serde_json::json!({
        "syncthing_gui_user":     creds.syncthing_gui_user,
        "syncthing_gui_password": creds.syncthing_gui_password,
    }))
}

// ─── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_get_service_credentials_reads_all_fields() {
        let eco = json!({
            "akasha": {
                "unpaywall_email": "test@example.com",
                "qbt_host": "192.168.1.1",
                "qbt_port": 9090,
                "qbt_user": "admin",
                "qbt_password": "secret",
            },
            "hub": {
                "syncthing_gui_user": "sync_user",
                "syncthing_gui_password": "sync_pass",
            }
        });
        let creds = get_service_credentials_inner(&eco);
        assert_eq!(creds.unpaywall_email, "test@example.com");
        assert_eq!(creds.qbt_host, "192.168.1.1");
        assert_eq!(creds.qbt_port, 9090);
        assert_eq!(creds.qbt_user, "admin");
        assert_eq!(creds.qbt_password, "secret");
        assert_eq!(creds.syncthing_gui_user, "sync_user");
        assert_eq!(creds.syncthing_gui_password, "sync_pass");
    }

    #[test]
    fn test_get_service_credentials_defaults() {
        let eco = json!({});
        let creds = get_service_credentials_inner(&eco);
        assert_eq!(creds.unpaywall_email, "");
        assert_eq!(creds.qbt_host, "localhost");
        assert_eq!(creds.qbt_port, 8080);
        assert_eq!(creds.qbt_user, "");
        assert_eq!(creds.qbt_password, "");
        assert_eq!(creds.syncthing_gui_user, "");
        assert_eq!(creds.syncthing_gui_password, "");
    }

    #[test]
    fn test_service_credentials_serializes() {
        let creds = ServiceCredentials {
            unpaywall_email:        "a@b.com".into(),
            qbt_host:               "localhost".into(),
            qbt_port:               8080,
            qbt_user:               "u".into(),
            qbt_password:           "p".into(),
            syncthing_gui_user:     "s".into(),
            syncthing_gui_password: "q".into(),
        };
        let json_str = serde_json::to_string(&creds).unwrap();
        assert!(json_str.contains("unpaywall_email"));
        assert!(json_str.contains("qbt_port"));
        assert!(json_str.contains("syncthing_gui_user"));
    }
}

/// Alterna entre modo compacto (~640×440) e expandido (~1280×800).
#[tauri::command]
pub fn set_window_compact(
    window: tauri::WebviewWindow,
    compact: bool,
) -> Result<(), AppError> {
    let size = if compact {
        tauri::LogicalSize::new(640_f64, 440_f64)
    } else {
        tauri::LogicalSize::new(1280_f64, 800_f64)
    };
    window.set_size(size).map_err(|e| AppError::Io(e.to_string()))
}
