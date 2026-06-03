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

/// Healthcheck HTTP: `GET {url}/healthz`, true se status 2xx.
///
/// INDEPENDENTE do systemd local (BUG-026): o SearXNG pode ser uma instância
/// **remota** (ex.: Docker no servidor T410), caso em que não há serviço systemd
/// local — mas a URL continua perfeitamente acessível pela rede. Nunca gatear este
/// check por `service_is_active()`.
async fn healthcheck(url: &str) -> bool {
    let u = url.trim();
    if u.is_empty() {
        return false;
    }
    let health = format!("{}/healthz", u.trim_end_matches('/'));
    reqwest::Client::new()
        .get(&health)
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

/// Status completo do SearXNG: serviço local ativo (informativo), URL e healthcheck.
#[tauri::command]
pub async fn searxng_status() -> Result<SearxngStatus, AppError> {
    let url    = get_url();
    let active = service_is_active();
    // `reachable` é independente de `active`: a instância pode ser remota.
    let reachable = healthcheck(&url).await;
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

    // ── BUG-026: healthcheck independente do systemd local ──────────────

    #[tokio::test]
    async fn healthcheck_empty_url_is_false() {
        assert!(!healthcheck("").await);
        assert!(!healthcheck("   ").await);
    }

    #[tokio::test]
    async fn healthcheck_unreachable_is_false() {
        // Porta 1: nada escutando → conexão recusada → false (rápido).
        assert!(!healthcheck("http://127.0.0.1:1").await);
    }

    #[tokio::test]
    async fn healthcheck_200_is_true() {
        // Sobe um listener mínimo que responde 200 em qualquer rota (inclui /healthz).
        // Prova que `reachable` funciona com instância REMOTA, sem systemd local.
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            if let Ok((mut sock, _)) = listener.accept().await {
                let mut buf = [0u8; 1024];
                let _ = sock.read(&mut buf).await;
                let _ = sock
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                    .await;
            }
        });
        let url = format!("http://{addr}");
        assert!(healthcheck(&url).await, "200 em /healthz deve resultar em reachable=true");
    }

    #[tokio::test]
    async fn healthcheck_trailing_slash_ok() {
        // URL com barra final não deve gerar // nem quebrar o check.
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            if let Ok((mut sock, _)) = listener.accept().await {
                let mut buf = [0u8; 1024];
                let _ = sock.read(&mut buf).await;
                let _ = sock
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                    .await;
            }
        });
        let url = format!("http://{addr}/");  // barra final
        assert!(healthcheck(&url).await);
    }
}
