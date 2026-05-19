use crate::ecosystem;
use crate::AppError;

const PORT: u16 = 8384;

// ── Config e API key ────────────────────────────────────────────

fn config_paths() -> Vec<std::path::PathBuf> {
    let mut v = vec![];
    if let Some(home) = dirs::home_dir() {
        v.push(home.join(".local/state/syncthing/config.xml"));
        v.push(home.join(".config/syncthing/config.xml"));
    }
    #[cfg(windows)]
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        v.push(std::path::PathBuf::from(local).join("Syncthing/config.xml"));
    }
    v
}

fn extract_apikey(xml: &str) -> Option<String> {
    let tag = "<apikey>";
    let start = xml.find(tag)? + tag.len();
    let end = xml[start..].find("</apikey>")?;
    Some(xml[start..start + end].trim().to_string())
}

fn read_api_key() -> Result<String, AppError> {
    for p in config_paths() {
        let Ok(xml) = std::fs::read_to_string(&p) else { continue };
        if let Some(key) = extract_apikey(&xml) {
            return Ok(key);
        }
    }
    Err(AppError::NotFound(
        "Syncthing config.xml não encontrado. Inicie o Syncthing ao menos uma vez.".into(),
    ))
}

// ── HTTP helpers ────────────────────────────────────────────────

fn st_client() -> Result<reqwest::Client, AppError> {
    // Syncthing usa HTTPS com certificado auto-assinado no localhost
    reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .map_err(|e| AppError::Io(e.to_string()))
}

async fn st_get(path: &str) -> Result<serde_json::Value, AppError> {
    let key = read_api_key()?;
    let url = format!("https://127.0.0.1:{PORT}{path}");
    st_client()?
        .get(&url)
        .header("X-API-Key", key)
        .send()
        .await
        .map_err(|e| AppError::Io(e.to_string()))?
        .json::<serde_json::Value>()
        .await
        .map_err(|e| AppError::Io(e.to_string()))
}

async fn st_post(path: &str) -> Result<(), AppError> {
    let key = read_api_key()?;
    let url = format!("https://127.0.0.1:{PORT}{path}");
    st_client()?
        .post(&url)
        .header("X-API-Key", key)
        .send()
        .await
        .map_err(|e| AppError::Io(e.to_string()))?;
    Ok(())
}

// ── Tipos de retorno ────────────────────────────────────────────

#[derive(serde::Serialize)]
pub struct SyncFolder {
    pub id:            String,
    pub label:         String,
    pub path:          String,
    pub paused:        bool,
    pub state:         String,
    pub need_bytes:    i64,
    pub in_sync_bytes: i64,
}

#[derive(serde::Serialize)]
pub struct SyncDevice {
    pub device_id: String,
    pub name:      String,
    pub connected: bool,
    pub last_seen: String,
}

#[derive(serde::Serialize)]
pub struct SyncStatus {
    pub running: bool,
    pub my_id:   String,
    pub folders: Vec<SyncFolder>,
    pub devices: Vec<SyncDevice>,
}

// ── Comandos Tauri ──────────────────────────────────────────────

/// Estado completo do Syncthing: se está rodando, pastas e dispositivos.
#[tauri::command]
pub async fn syncthing_status() -> Result<SyncStatus, AppError> {
    let system = match st_get("/rest/system/status").await {
        Err(_) => {
            return Ok(SyncStatus {
                running: false,
                my_id:   String::new(),
                folders: vec![],
                devices: vec![],
            })
        }
        Ok(v) => v,
    };
    let my_id = system["myID"].as_str().unwrap_or("").to_string();

    // Pastas
    let config_folders = st_get("/rest/config/folders").await.unwrap_or_default();
    let folder_arr = config_folders.as_array().cloned().unwrap_or_default();
    let mut folders = vec![];
    for f in &folder_arr {
        let id     = f["id"].as_str().unwrap_or("").to_string();
        let label  = f["label"].as_str().filter(|s| !s.is_empty()).unwrap_or(&id).to_string();
        let path   = f["path"].as_str().unwrap_or("").to_string();
        let paused = f["paused"].as_bool().unwrap_or(false);

        let db = st_get(&format!("/rest/db/status?folder={id}"))
            .await
            .unwrap_or_default();
        let state         = db["state"].as_str().unwrap_or("unknown").to_string();
        let need_bytes    = db["needBytes"].as_i64().unwrap_or(0);
        let in_sync_bytes = db["inSyncBytes"].as_i64().unwrap_or(0);

        folders.push(SyncFolder { id, label, path, paused, state, need_bytes, in_sync_bytes });
    }

    // Dispositivos
    let connections_resp = st_get("/rest/system/connections").await.unwrap_or_default();
    let conns = connections_resp["connections"]
        .as_object()
        .cloned()
        .unwrap_or_default();

    let config_devs = st_get("/rest/config/devices").await.unwrap_or_default();
    let dev_arr = config_devs.as_array().cloned().unwrap_or_default();
    let mut devices = vec![];
    for d in &dev_arr {
        let device_id = d["deviceID"].as_str().unwrap_or("").to_string();
        if device_id.is_empty() || device_id == my_id {
            continue;
        }
        let short_id = if device_id.len() >= 7 { &device_id[..7] } else { &device_id };
        let name      = d["name"].as_str().filter(|s| !s.is_empty()).unwrap_or(short_id).to_string();
        let connected = conns
            .get(&device_id)
            .and_then(|c| c["connected"].as_bool())
            .unwrap_or(false);
        let last_seen = d["lastSeen"].as_str().unwrap_or("").to_string();
        devices.push(SyncDevice { device_id, name, connected, last_seen });
    }

    Ok(SyncStatus { running: true, my_id, folders, devices })
}

/// Inicia o processo syncthing em background.
#[tauri::command]
pub fn syncthing_start() -> Result<(), AppError> {
    std::process::Command::new("syncthing")
        .arg("serve")
        .arg("--no-browser")
        .spawn()
        .map_err(|e| AppError::Io(format!("Falha ao iniciar Syncthing: {e}")))?;
    Ok(())
}

/// Encerra o Syncthing via REST API.
#[tauri::command]
pub async fn syncthing_shutdown() -> Result<(), AppError> {
    st_post("/rest/system/shutdown").await
}

/// Pausa todas as pastas configuradas no Syncthing.
/// Chamado automaticamente quando apps com banco de dados estão em uso.
#[tauri::command]
pub async fn syncthing_pause_all() -> Result<(), AppError> {
    let config_folders = st_get("/rest/config/folders").await?;
    for f in config_folders.as_array().unwrap_or(&vec![]) {
        if let Some(id) = f["id"].as_str() {
            let _ = st_post(&format!("/rest/db/pause?folder={id}")).await;
        }
    }
    Ok(())
}

/// Retoma todas as pastas pausadas.
#[tauri::command]
pub async fn syncthing_resume_all() -> Result<(), AppError> {
    let config_folders = st_get("/rest/config/folders").await?;
    for f in config_folders.as_array().unwrap_or(&vec![]) {
        if let Some(id) = f["id"].as_str() {
            let _ = st_post(&format!("/rest/db/resume?folder={id}")).await;
        }
    }
    Ok(())
}

/// Força re-scan de uma pasta específica.
#[tauri::command]
pub async fn syncthing_rescan(folder_id: String) -> Result<(), AppError> {
    st_post(&format!("/rest/db/scan?folder={folder_id}")).await
}

/// Retorna o estado de pausa manual (persiste em ecosystem.json).
#[tauri::command]
pub fn syncthing_get_paused() -> bool {
    ecosystem::read_json()["hub"]["syncthing_paused"]
        .as_bool()
        .unwrap_or(false)
}

/// Salva o estado de pausa manual em ecosystem.json.
#[tauri::command]
pub fn syncthing_set_paused(paused: bool) -> Result<(), AppError> {
    ecosystem::write_section("hub", serde_json::json!({ "syncthing_paused": paused }))
}
