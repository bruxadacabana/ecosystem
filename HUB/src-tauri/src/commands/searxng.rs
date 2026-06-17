use crate::ecosystem;
use crate::AppError;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::Duration;

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

// ═════════════════════════════════════════════════════════════
//  SearXNG VENDORIZADO — 3ª alternativa de busca (gerenciado pelo HUB)
//
//  Processo Python (`searx.webapp`) que o HUB sobe SOB DEMANDA: só quando o
//  SearXNG remoto E o local estão fora. Sem systemd, multiplataforma. Watchdog
//  reinicia se cair; desliga quando remoto/local voltam. Ver TODO
//  "SearXNG vendorizado (Windows, sem Docker)".
// ═════════════════════════════════════════════════════════════

#[derive(Debug, Serialize, Deserialize)]
pub struct VendorStatus {
    pub running:   bool,   // processo rastreado e vivo
    pub reachable: bool,   // GET /healthz respondeu 200
    pub url:       String, // URL da instância vendorizada
}

/// Handle do processo vendorizado (global — compartilhado com o watchdog).
fn vendor_proc() -> &'static tokio::sync::Mutex<Option<tokio::process::Child>> {
    static P: OnceLock<tokio::sync::Mutex<Option<tokio::process::Child>>> = OnceLock::new();
    P.get_or_init(|| tokio::sync::Mutex::new(None))
}

/// Pasta do SearXNG vendorizado: `{AKASHA}/vendor/searxng`, derivada de
/// `akasha.exe_path` (o iniciar.bat/sh). None se não configurado.
fn vendor_dir() -> Option<PathBuf> {
    let eco = ecosystem::read_json();
    let exe = eco["akasha"]["exe_path"].as_str()?;
    let akasha = Path::new(exe).parent()?;
    Some(akasha.join("vendor").join("searxng"))
}

/// Interpretador do venv dedicado do vendor, por plataforma.
fn vendor_python(dir: &Path) -> PathBuf {
    if cfg!(windows) {
        dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        dir.join(".venv").join("bin").join("python")
    }
}

/// URL da instância vendorizada (`web_search_backend_vendor` ou o default 8889).
fn vendor_url() -> String {
    let eco = ecosystem::read_json();
    let raw = eco["akasha"]["web_search_backend_vendor"]
        .as_str()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or("http://127.0.0.1:8889");
    raw.trim_end_matches('/').to_string()
}

/// Decisão pura: o vendorizado deve rodar? Só quando remoto E local estão fora.
fn should_run_vendor(remote_up: bool, local_up: bool) -> bool {
    !(remote_up || local_up)
}

/// True se o vendorizado está instalado (venv criado pelo setup). Evita spam de
/// warning no watchdog em máquinas que não rodaram o setup do vendor.
fn vendor_available() -> bool {
    vendor_dir().map(|d| vendor_python(&d).exists()).unwrap_or(false)
}

/// True se o SearXNG remoto OU o local responde (cada um só é checado se configurado).
async fn remote_or_local_up() -> bool {
    let eco = ecosystem::read_json();
    let remote = eco["akasha"]["web_search_backend"].as_str().unwrap_or("").trim().to_string();
    let local  = eco["akasha"]["web_search_backend_fallback"].as_str().unwrap_or("").trim().to_string();
    if !remote.is_empty() && healthcheck(&remote).await {
        return true;
    }
    if !local.is_empty() && healthcheck(&local).await {
        return true;
    }
    false
}

/// True se há processo vendorizado rastreado e ainda vivo (limpa o handle se saiu).
async fn vendor_proc_alive() -> bool {
    let mut guard = vendor_proc().lock().await;
    if let Some(child) = guard.as_mut() {
        match child.try_wait() {
            Ok(Some(_)) => { *guard = None; false }  // já saiu
            Ok(None)    => true,
            Err(_)      => true,
        }
    } else {
        false
    }
}

/// Sobe o SearXNG vendorizado (no-op se já rastreado). Erro tipado em falha.
async fn start_vendor() -> Result<(), String> {
    let dir = vendor_dir().ok_or_else(|| "vendor dir não resolvido (akasha.exe_path ausente)".to_string())?;
    let py = vendor_python(&dir);
    if !py.exists() {
        return Err(format!(
            "venv do SearXNG vendorizado ausente: {} — rode o atualizar/setup",
            py.display()
        ));
    }
    let settings = dir.join("settings.yml");
    if !settings.exists() {
        return Err(format!("settings.yml ausente: {} — rode o atualizar/setup", settings.display()));
    }
    let mut guard = vendor_proc().lock().await;
    if guard.is_some() {
        return Ok(());
    }
    let mut cmd = tokio::process::Command::new(&py);
    cmd.arg("-m").arg("searx.webapp")
        .current_dir(&dir)
        .env("SEARXNG_SETTINGS_PATH", &settings);
    // Stub do `pwd` só no Windows (no Linux NÃO — shadowaria o módulo real).
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.env("PYTHONPATH", dir.join("_winshim"));
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let child = cmd.spawn().map_err(|e| format!("falha ao spawnar SearXNG vendorizado: {e}"))?;
    *guard = Some(child);
    log::info!("HUB: SearXNG vendorizado iniciado ({})", vendor_url());
    Ok(())
}

/// Para o SearXNG vendorizado se estiver rodando. True se havia processo.
async fn stop_vendor() -> bool {
    let mut guard = vendor_proc().lock().await;
    if let Some(mut child) = guard.take() {
        let _ = child.kill().await;
        log::info!("HUB: SearXNG vendorizado parado");
        true
    } else {
        false
    }
}

/// Watchdog (iniciado no setup do HUB): a cada 30s decide se o vendorizado deve
/// rodar. Sobe quando remoto+local caem; desliga quando um volta; reinicia se
/// vivo mas sem resposta. Nunca usa o próprio vendor na decisão (evita flapping).
pub async fn vendor_watchdog() {
    loop {
        tokio::time::sleep(Duration::from_secs(30)).await;

        let up = remote_or_local_up().await;
        if !should_run_vendor(up, false) {
            // remoto/local atendem → vendorizado é desnecessário
            if vendor_proc_alive().await {
                stop_vendor().await;
                log::info!("HUB: remoto/local disponível — SearXNG vendorizado desligado");
            }
            continue;
        }

        // remoto E local fora → garantir vendorizado vivo e saudável
        let alive = vendor_proc_alive().await;
        if !alive {
            if !vendor_available() {
                // Sem o setup do vendor não há o que subir — silencioso (debug).
                log::debug!("HUB: SearXNG vendorizado não instalado (rode o atualizar/setup) — pulando");
            } else {
                match start_vendor().await {
                    Ok(())  => log::info!("HUB: remoto/local fora — subindo SearXNG vendorizado"),
                    Err(e)  => log::warn!("HUB: não foi possível subir o SearXNG vendorizado: {e}"),
                }
            }
        } else if !healthcheck(&vendor_url()).await {
            log::warn!("HUB: SearXNG vendorizado vivo mas sem resposta — reiniciando");
            stop_vendor().await;
            let _ = start_vendor().await;
        }
    }
}

// ── Comandos Tauri — vendorizado ─────────────────────────────

/// Status do SearXNG vendorizado: processo vivo, healthcheck e URL.
#[tauri::command]
pub async fn searxng_vendor_status() -> Result<VendorStatus, AppError> {
    let url = vendor_url();
    let running = vendor_proc_alive().await;
    let reachable = healthcheck(&url).await;
    Ok(VendorStatus { running, reachable, url })
}

/// Sobe o SearXNG vendorizado manualmente (override do watchdog).
#[tauri::command]
pub async fn searxng_vendor_start() -> Result<(), AppError> {
    start_vendor().await.map_err(AppError::Io)
}

/// Para o SearXNG vendorizado manualmente.
#[tauri::command]
pub async fn searxng_vendor_stop() -> Result<(), AppError> {
    stop_vendor().await;
    Ok(())
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

    // ── SearXNG vendorizado ──────────────────────────────────────────

    #[test]
    fn should_run_vendor_only_when_both_down() {
        assert!(should_run_vendor(false, false), "remoto+local fora → roda o vendor");
        assert!(!should_run_vendor(true, false), "remoto up → não roda");
        assert!(!should_run_vendor(false, true), "local up → não roda");
        assert!(!should_run_vendor(true, true), "ambos up → não roda");
    }

    #[test]
    fn vendor_python_path_per_platform() {
        let dir = Path::new("/x/vendor/searxng");
        let py = vendor_python(dir);
        let s = py.to_string_lossy();
        assert!(s.contains(".venv"));
        if cfg!(windows) {
            assert!(s.ends_with("python.exe") && s.contains("Scripts"));
        } else {
            assert!(s.ends_with("python") && s.contains("bin"));
        }
    }

    #[test]
    fn vendor_url_has_default_port() {
        // Sem override, cai no default 8889 (sem barra final).
        let url = vendor_url();
        assert!(url.starts_with("http"));
        assert!(!url.ends_with('/'));
    }

    #[test]
    fn vendor_status_serializes() {
        let s = VendorStatus { running: true, reachable: false, url: "http://127.0.0.1:8889".into() };
        let json = serde_json::to_string(&s).unwrap();
        assert!(json.contains("running") && json.contains("reachable") && json.contains("8889"));
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
