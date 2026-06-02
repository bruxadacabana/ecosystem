use crate::ecosystem;
use crate::AppError;
use serde::{Deserialize, Serialize};

// ── Tipos ────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct SearxngStatus {
    pub active:    bool,   // systemctl is-active searxng
    pub reachable: bool,   // GET /healthz respondeu 200
    pub url:       String, // web_search_backend atual
}

// ── Helpers internos ─────────────────────────────────────────

fn get_url() -> String {
    let eco = ecosystem::read_json();
    eco["akasha"]["web_search_backend"]
        .as_str()
        .unwrap_or("http://localhost:8888")
        .to_string()
}

/// Verifica se o serviço searxng está ativo via `systemctl is-active`.
/// Funciona sem sudo. Retorna false em plataformas sem systemctl.
fn service_is_active() -> bool {
    std::process::Command::new("systemctl")
        .args(["is-active", "--quiet", "searxng"])
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Executa `systemctl <action> searxng` e mapeia o resultado.
fn systemctl(action: &str) -> Result<(), AppError> {
    let status = std::process::Command::new("systemctl")
        .args([action, "searxng"])
        .status()
        .map_err(|e| AppError::Io(format!("Falha ao executar systemctl {action}: {e}")))?;

    if status.success() {
        Ok(())
    } else {
        let code = status.code().unwrap_or(-1);
        Err(AppError::Io(format!(
            "systemctl {action} searxng falhou (código {code}). \
             Pode ser necessário permissão de administrador — \
             tente: sudo systemctl {action} searxng"
        )))
    }
}

// ── Comandos Tauri ───────────────────────────────────────────

/// Status completo do SearXNG: serviço ativo, URL configurada e healthcheck.
#[tauri::command]
pub async fn searxng_status() -> Result<SearxngStatus, AppError> {
    let active = service_is_active();
    let url    = get_url();

    let reachable = if active {
        let health = format!("{}/healthz", url.trim_end_matches('/'));
        reqwest::Client::new()
            .get(&health)
            .timeout(std::time::Duration::from_secs(3))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    } else {
        false
    };

    Ok(SearxngStatus { active, reachable, url })
}

/// Inicia o serviço searxng via systemctl.
#[tauri::command]
pub fn searxng_start() -> Result<(), AppError> {
    systemctl("start")
}

/// Para o serviço searxng via systemctl.
#[tauri::command]
pub fn searxng_stop() -> Result<(), AppError> {
    systemctl("stop")
}

/// Lê a URL atual do SearXNG em ecosystem.json.
#[tauri::command]
pub fn searxng_get_url() -> Result<String, AppError> {
    Ok(get_url())
}

/// Salva a URL do SearXNG em ecosystem.json["akasha"]["web_search_backend"].
#[tauri::command]
pub fn searxng_set_url(url: String) -> Result<(), AppError> {
    ecosystem::write_section("akasha", serde_json::json!({ "web_search_backend": url }))
}

// ── Testes ───────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_url_fallback() {
        // Sem ecosystem.json configurado, deve retornar o default.
        // Este teste verifica que a função não pânica.
        let url = get_url();
        assert!(!url.is_empty());
        assert!(url.starts_with("http"));
    }

    #[test]
    fn test_searxng_status_serializes() {
        let s = SearxngStatus {
            active:    true,
            reachable: false,
            url:       "http://localhost:8888".into(),
        };
        let json = serde_json::to_string(&s).unwrap();
        assert!(json.contains("active"));
        assert!(json.contains("reachable"));
        assert!(json.contains("localhost:8888"));
    }

    #[test]
    fn test_systemctl_invalid_action_error() {
        // Ação inválida deve retornar erro (systemctl retorna exit != 0).
        let result = systemctl("status-invalido-xyzzy");
        assert!(result.is_err());
    }
}
