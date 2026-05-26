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

/// Núcleo testável de `apply_sync_root` — recebe o path do ecosystem.json explicitamente.
/// Permite testes com tempdir sem tocar no arquivo real do sistema.
pub(crate) fn apply_sync_root_inner(
    root: &Path,
    eco_path: &std::path::PathBuf,
) -> Result<(), AppError> {
    use serde_json::json;

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

    let root_str = root.to_string_lossy();

    ecosystem::write_to_file(eco_path, "sync_root", json!(root_str.as_ref()))?;
    ecosystem::write_to_file(eco_path, "aether", json!({
        "vault_path":  root.join("aether").to_string_lossy().as_ref(),
        "config_path": root.join("aether").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_to_file(eco_path, "kosmos", json!({
        "archive_path": root.join("kosmos").to_string_lossy().as_ref(),
        "config_path":  root.join("kosmos").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_to_file(eco_path, "mnemosyne", json!({
        "watched_dir": root.join("mnemosyne").join("docs").to_string_lossy().as_ref(),
        "chroma_dir":  root.join("mnemosyne").join("chroma_db").to_string_lossy().as_ref(),
        "config_path": root.join("mnemosyne").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_to_file(eco_path, "hermes", json!({
        "output_dir":  root.join("hermes").to_string_lossy().as_ref(),
        "config_path": root.join("hermes").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_to_file(eco_path, "akasha", json!({
        "archive_path": root.join("akasha").to_string_lossy().as_ref(),
        "data_path":    root.join("akasha").to_string_lossy().as_ref(),
        "config_path":  root.join("akasha").join(".config").to_string_lossy().as_ref(),
    }))?;
    ecosystem::write_to_file(eco_path, "ogma", json!({
        "data_path":   root.join("ogma").to_string_lossy().as_ref(),
        "config_path": root.join("ogma").join(".config").to_string_lossy().as_ref(),
    }))?;

    // ── Seção logos — inicializa defaults sem sobrescrever config existente ──
    // Lê o estado atual e só escreve os campos ausentes, preservando embed_model
    // e embed_port que a usuária pode ter configurado manualmente.
    {
        let cur: Value = if eco_path.exists() {
            std::fs::read_to_string(eco_path)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
                .unwrap_or(json!({}))
        } else {
            json!({})
        };
        let mut defaults = serde_json::Map::new();
        if !cur["logos"]["embed_model"].is_string() {
            defaults.insert("embed_model".into(), json!("bge-m3"));
        }
        if cur["logos"]["embed_port"].as_u64().is_none() {
            defaults.insert("embed_port".into(), json!(8082_u64));
        }
        if !defaults.is_empty() {
            ecosystem::write_to_file(eco_path, "logos", Value::Object(defaults))?;
        }
    }

    Ok(())
}

/// Aplica um diretório raiz de sincronização ao ecossistema:
/// cria as subpastas necessárias e escreve os caminhos derivados
/// no ecosystem.json para todos os apps.
#[tauri::command]
pub fn apply_sync_root(sync_root: String) -> Result<(), AppError> {
    let eco_path = ecosystem::ecosystem_path().ok_or_else(|| {
        AppError::Io("Não foi possível determinar o diretório de dados do sistema.".into())
    })?;
    apply_sync_root_inner(Path::new(&sync_root), &eco_path)
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

    // ── apply_sync_root ────────────────────────────────────────────────────────

    fn run_inner(sync_tmp: &tempfile::TempDir, eco_tmp: &tempfile::TempDir) -> Result<(), AppError> {
        let eco_path = eco_tmp.path().join("ecosystem.json");
        apply_sync_root_inner(sync_tmp.path(), &eco_path)
    }

    fn read_eco(eco_tmp: &tempfile::TempDir) -> serde_json::Value {
        let eco_path = eco_tmp.path().join("ecosystem.json");
        let text = std::fs::read_to_string(&eco_path).unwrap_or_default();
        serde_json::from_str(&text).unwrap_or(json!({}))
    }

    #[test]
    fn apply_sync_root_creates_all_subdirs() {
        let sync_tmp = tempfile::tempdir().unwrap();
        let eco_tmp  = tempfile::tempdir().unwrap();
        run_inner(&sync_tmp, &eco_tmp).unwrap();

        let expected = [
            vec!["aether"],
            vec!["aether", ".config"],
            vec!["kosmos"],
            vec!["kosmos", ".config"],
            vec!["mnemosyne", "docs"],
            vec!["mnemosyne", "chroma_db"],
            vec!["mnemosyne", ".config"],
            vec!["hermes"],
            vec!["hermes", ".config"],
            vec!["akasha"],
            vec!["akasha", ".config"],
            vec!["ogma"],
            vec!["ogma", ".config"],
        ];
        for parts in &expected {
            let mut path = sync_tmp.path().to_path_buf();
            for p in parts { path = path.join(p); }
            assert!(path.is_dir(), "subdiretório ausente: {:?}", path);
        }
    }

    #[test]
    fn apply_sync_root_writes_correct_paths_for_all_apps() {
        let sync_tmp = tempfile::tempdir().unwrap();
        let eco_tmp  = tempfile::tempdir().unwrap();
        run_inner(&sync_tmp, &eco_tmp).unwrap();

        let eco = read_eco(&eco_tmp);
        let root = sync_tmp.path().to_string_lossy();

        assert_eq!(eco["aether"]["vault_path"].as_str().unwrap(),
            sync_tmp.path().join("aether").to_string_lossy().as_ref());
        assert_eq!(eco["kosmos"]["archive_path"].as_str().unwrap(),
            sync_tmp.path().join("kosmos").to_string_lossy().as_ref());
        assert_eq!(eco["mnemosyne"]["watched_dir"].as_str().unwrap(),
            sync_tmp.path().join("mnemosyne").join("docs").to_string_lossy().as_ref());
        assert_eq!(eco["mnemosyne"]["chroma_dir"].as_str().unwrap(),
            sync_tmp.path().join("mnemosyne").join("chroma_db").to_string_lossy().as_ref());
        assert_eq!(eco["hermes"]["output_dir"].as_str().unwrap(),
            sync_tmp.path().join("hermes").to_string_lossy().as_ref());
        assert_eq!(eco["akasha"]["data_path"].as_str().unwrap(),
            sync_tmp.path().join("akasha").to_string_lossy().as_ref());
        assert_eq!(eco["ogma"]["data_path"].as_str().unwrap(),
            sync_tmp.path().join("ogma").to_string_lossy().as_ref());
        assert_eq!(eco["sync_root"].as_str().unwrap(), root.as_ref());
    }

    #[test]
    fn apply_sync_root_preserves_existing_fields() {
        let sync_tmp = tempfile::tempdir().unwrap();
        let eco_tmp  = tempfile::tempdir().unwrap();
        let eco_path = eco_tmp.path().join("ecosystem.json");

        // Pré-escreve campos existentes que não devem ser removidos
        let pre = json!({
            "aether": { "exe_path": "/usr/bin/aether", "some_flag": true },
            "hub":    { "port": 7072 }
        });
        std::fs::write(&eco_path, serde_json::to_string_pretty(&pre).unwrap()).unwrap();

        apply_sync_root_inner(sync_tmp.path(), &eco_path).unwrap();

        let eco = read_eco(&eco_tmp);
        // Campos antigos preservados
        assert_eq!(eco["aether"]["exe_path"].as_str().unwrap(), "/usr/bin/aether",
            "exe_path deve ser preservado — apply_sync_root não deve sobrescrever campos existentes");
        assert_eq!(eco["aether"]["some_flag"].as_bool().unwrap(), true);
        assert_eq!(eco["hub"]["port"].as_u64().unwrap(), 7072,
            "seção hub não deve ser tocada por apply_sync_root");
        // Novo campo também presente
        assert!(eco["aether"]["vault_path"].as_str().is_some(),
            "vault_path deve ter sido adicionado");
    }

    #[test]
    fn apply_sync_root_fails_on_invalid_path() {
        let eco_tmp = tempfile::tempdir().unwrap();
        let eco_path = eco_tmp.path().join("ecosystem.json");

        // Cria um arquivo onde apply_sync_root esperaria um diretório
        // — create_dir_all falha quando um componente do path é um arquivo existente
        let blocker = eco_tmp.path().join("blocker");
        std::fs::write(&blocker, b"not a dir").unwrap();
        // sync_root aponta para dentro do "arquivo", que não é um dir
        let invalid_root = blocker.join("subpath");

        let result = apply_sync_root_inner(&invalid_root, &eco_path);
        assert!(result.is_err(), "deve falhar quando o path não pode ser criado");
    }

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

    // ── LogosEmbedConfig ──────────────────────────────────────────────────────

    #[test]
    fn logos_embed_config_reads_configured_values() {
        let eco = json!({
            "logos": {
                "embed_model": "custom-embed.gguf",
                "embed_port":  9000
            }
        });
        let cfg = get_logos_embed_config_inner(&eco);
        assert_eq!(cfg.embed_model, "custom-embed.gguf");
        assert_eq!(cfg.embed_port, 9000);
    }

    #[test]
    fn logos_embed_config_defaults_when_logos_section_absent() {
        let eco = json!({});
        let cfg = get_logos_embed_config_inner(&eco);
        assert_eq!(cfg.embed_model, "bge-m3",
            "embed_model padrão deve ser 'bge-m3'");
        assert_eq!(cfg.embed_port, 8082,
            "embed_port padrão deve ser 8082");
    }

    #[test]
    fn logos_embed_config_defaults_when_embed_model_empty_string() {
        let eco = json!({ "logos": { "embed_model": "", "embed_port": 8082 } });
        let cfg = get_logos_embed_config_inner(&eco);
        assert_eq!(cfg.embed_model, "bge-m3",
            "embed_model vazio deve cair no default 'bge-m3'");
    }

    #[test]
    fn logos_embed_config_serializes() {
        let cfg = LogosEmbedConfig { embed_model: "bge-m3".into(), embed_port: 8082 };
        let s   = serde_json::to_string(&cfg).unwrap();
        assert!(s.contains("embed_model"), "deve serializar embed_model");
        assert!(s.contains("embed_port"),  "deve serializar embed_port");
        assert!(s.contains("8082"),        "porta deve estar no JSON");
    }

    // ── apply_sync_root: logos defaults ─────────────────────────────────────

    #[test]
    fn apply_sync_root_writes_logos_embed_defaults_when_absent() {
        let sync_tmp = tempfile::tempdir().unwrap();
        let eco_tmp  = tempfile::tempdir().unwrap();
        run_inner(&sync_tmp, &eco_tmp).unwrap();

        let eco = read_eco(&eco_tmp);
        assert_eq!(eco["logos"]["embed_model"].as_str().unwrap(), "bge-m3",
            "logos.embed_model deve ser inicializado com 'bge-m3'");
        assert_eq!(eco["logos"]["embed_port"].as_u64().unwrap(), 8082,
            "logos.embed_port deve ser inicializado com 8082");
    }

    #[test]
    fn apply_sync_root_preserves_existing_logos_embed_config() {
        let sync_tmp = tempfile::tempdir().unwrap();
        let eco_tmp  = tempfile::tempdir().unwrap();
        let eco_path = eco_tmp.path().join("ecosystem.json");

        // Pré-escreve config customizada de logos
        let pre = json!({
            "logos": {
                "embed_model": "custom-embed.gguf",
                "embed_port":  9000
            }
        });
        std::fs::write(&eco_path, serde_json::to_string_pretty(&pre).unwrap()).unwrap();

        apply_sync_root_inner(sync_tmp.path(), &eco_path).unwrap();

        let eco = read_eco(&eco_tmp);
        assert_eq!(eco["logos"]["embed_model"].as_str().unwrap(), "custom-embed.gguf",
            "apply_sync_root NÃO deve sobrescrever embed_model já configurado");
        assert_eq!(eco["logos"]["embed_port"].as_u64().unwrap(), 9000,
            "apply_sync_root NÃO deve sobrescrever embed_port já configurado");
    }

    #[test]
    fn apply_sync_root_writes_only_missing_logos_fields() {
        let sync_tmp = tempfile::tempdir().unwrap();
        let eco_tmp  = tempfile::tempdir().unwrap();
        let eco_path = eco_tmp.path().join("ecosystem.json");

        // embed_model configurado, embed_port ausente
        let pre = json!({ "logos": { "embed_model": "my-embed.gguf" } });
        std::fs::write(&eco_path, serde_json::to_string_pretty(&pre).unwrap()).unwrap();

        apply_sync_root_inner(sync_tmp.path(), &eco_path).unwrap();

        let eco = read_eco(&eco_tmp);
        assert_eq!(eco["logos"]["embed_model"].as_str().unwrap(), "my-embed.gguf",
            "embed_model existente deve ser preservado");
        assert_eq!(eco["logos"]["embed_port"].as_u64().unwrap(), 8082,
            "embed_port ausente deve receber valor padrão 8082");
    }
}

// ─── LogosEmbedConfig ─────────────────────────────────────────────────────────

/// Configuração do servidor de embedding do LOGOS.
/// `embed_model`: nome do GGUF de embedding (ex: "bge-m3"). Padrão: "bge-m3".
/// `embed_port`: porta do embed-server. Padrão: 8082 (= EMBED_SERVER_PORT).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogosEmbedConfig {
    pub embed_model: String,
    pub embed_port:  u16,
}

/// Núcleo testável — lê `logos.embed_model` e `logos.embed_port` do ecosystem.json.
pub(crate) fn get_logos_embed_config_inner(eco: &Value) -> LogosEmbedConfig {
    let logos = &eco["logos"];
    LogosEmbedConfig {
        embed_model: logos["embed_model"]
            .as_str()
            .filter(|s| !s.is_empty())
            .unwrap_or("bge-m3")
            .to_string(),
        embed_port: logos["embed_port"].as_u64().unwrap_or(8082) as u16,
    }
}

/// Lê a configuração do servidor de embedding do LOGOS a partir do ecosystem.json.
#[tauri::command]
pub fn get_logos_embed_config() -> Result<LogosEmbedConfig, AppError> {
    Ok(get_logos_embed_config_inner(&ecosystem::read_json()))
}

/// Salva a configuração do servidor de embedding do LOGOS no ecosystem.json.
/// Usa merge de campos — não toca em outros campos da seção `logos`.
#[tauri::command]
pub fn save_logos_embed_config(config: LogosEmbedConfig) -> Result<(), AppError> {
    ecosystem::write_section("logos", serde_json::json!({
        "embed_model": config.embed_model,
        "embed_port":  config.embed_port,
    }))
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
