// ============================================================
//  HUB — Launcher de apps externos
//  Inicia apps do ecossistema e monitora se estão em execução.
// ============================================================

use std::collections::HashMap;
use std::process::Command;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

use crate::AppError;

// ----------------------------------------------------------
//  Comandos IPC
// ----------------------------------------------------------

/// Liga ou desliga o backend de inferência (llama-server via LOGOS).
///
/// `enable = true`  → seta flag de inferência; o modelo é carregado lazily na
///                    primeira requisição real (não imediatamente).
/// `enable = false` → para llama-server e embed-server (libera VRAM/CPU).
///
/// Retorna `"enabled"` | `"already_running"` | `"stopped"` | `"already_stopped"`.
#[tauri::command]
pub async fn toggle_inference(
    state: tauri::State<'_, crate::logos::LogosState>,
    enable: bool,
) -> Result<String, AppError> {
    let responding = llama_server_responding().await;
    do_toggle_inference(state.inner(), enable, responding).await
}

/// Lógica testável de toggle_inference.
/// `server_responding` injeta o resultado do check HTTP para desacoplar de rede.
pub(crate) async fn do_toggle_inference(
    state: &crate::logos::LogosState,
    enable: bool,
    server_responding: bool,
) -> Result<String, AppError> {
    if enable {
        if server_responding {
            // Processo já rastreado pelo HUB → sincroniza flag e sinaliza já ativo.
            if state.llama_proc_active().await {
                state.set_inference_enabled(true);
                return Ok("already_running".into());
            }
            // Servidor órfão de sessão anterior: matar antes de habilitar.
            log::warn!("LOGOS toggle_inference: llama-server órfão detectado — matando");
            kill_orphaned_llama_server().await;
        }
        // Falha rápida: sem o binário é impossível carregar qualquer modelo.
        if !state.has_llama_server() {
            return Err(AppError::NotFound(
                "llama-server não encontrado. Instale o llama.cpp e certifique-se de que \
                 'llama-server' está no PATH, ou configure o caminho em ecosystem.json \
                 como logos.llama_server_path.".into(),
            ));
        }
        // Lazy loading: apenas habilita a flag; o modelo carrega na primeira requisição real.
        state.set_inference_enabled(true);
        log::info!("LOGOS: inferência habilitada — modelo será carregado na primeira requisição");
        Ok("enabled".into())
    } else {
        let stopped_akasha    = state.kill_akasha_proc().await;
        let stopped_mnemosyne = state.kill_mnemosyne_proc().await;
        let stopped_embed     = state.kill_embed_proc().await;
        state.set_inference_enabled(false);
        log::info!(
            "LOGOS: inferência desabilitada (akasha_killed={stopped_akasha} \
             mnemosyne_killed={stopped_mnemosyne} embed_killed={stopped_embed})"
        );
        Ok(if stopped_akasha || stopped_mnemosyne || stopped_embed { "stopped" } else { "already_stopped" }.into())
    }
}

/// Seleciona o primeiro modelo disponível da lista de nomes instalados.
pub(crate) fn select_model_to_load(names: &[String]) -> Option<String> {
    names.first().cloned()
}

/// Prefere modelos de chat/instrução; exclui embeddings e mmproj.
/// Reconhece modelos de embedding pelo nome (bge, e5, nomic-embed, etc.)
/// e modelos auxiliares (mmproj).
pub(crate) fn select_model_to_load_llm(names: &[String]) -> Option<String> {
    let skip_patterns = ["bge", "e5-", "nomic-embed", "all-minilm", "mmproj", "embed"];
    names.iter().find(|name| {
        let lower = name.to_lowercase();
        !skip_patterns.iter().any(|p| lower.contains(p))
    }).cloned()
}

/// Testa se o llama-server (através do LOGOS) está respondendo (timeout 500 ms).
async fn llama_server_responding() -> bool {
    reqwest::Client::new()
        .get("http://127.0.0.1:7072/health")
        .timeout(std::time::Duration::from_millis(500))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

/// Mata qualquer processo llama-server órfão (de sessão anterior do HUB).
async fn kill_orphaned_llama_server() {
    #[cfg(unix)]
    {
        let port = crate::logos::AKASHA_SERVER_PORT.to_string();
        // fuser -k <port>/tcp encerra processos escutando na porta (Linux)
        let ok = tokio::process::Command::new("fuser")
            .args(["-k", &format!("{port}/tcp")])
            .status()
            .await
            .map(|s| s.success())
            .unwrap_or(false);
        if !ok {
            // Fallback: pkill por nome do binário
            let _ = tokio::process::Command::new("pkill")
                .args(["-f", "llama-server"])
                .status()
                .await;
        }
    }
    #[cfg(windows)]
    {
        use crate::logos::AKASHA_SERVER_PORT;
        // netstat para encontrar PID escutando na porta, depois taskkill
        if let Ok(out) = tokio::process::Command::new("netstat")
            .args(["-ano"])
            .output()
            .await
        {
            let text = String::from_utf8_lossy(&out.stdout);
            let port_str = format!(":{AKASHA_SERVER_PORT}");
            for line in text.lines() {
                if line.contains(&port_str) && line.contains("LISTENING") {
                    if let Some(pid) = line.split_whitespace().last() {
                        let _ = tokio::process::Command::new("taskkill")
                            .args(["/PID", pid, "/F"])
                            .status()
                            .await;
                    }
                }
            }
        }
    }
    // Aguarda o processo liberar a porta
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;
}

/// Inicia um app externo pelo caminho do executável.
/// No Windows, scripts `.sh` são automaticamente envolvidos com `bash`.
#[tauri::command]
pub fn launch_app(exe_path: String) -> Result<(), AppError> {
    if exe_path.trim().is_empty() {
        return Err(AppError::InvalidPath(
            "Caminho do executável não configurado.".into(),
        ));
    }

    let mut cmd = build_launch_command(&exe_path);
    cmd.spawn()
        .map(|_| ())
        .map_err(|e| AppError::Io(format!("Não foi possível iniciar '{}': {}", exe_path, e)))
}

/// Inicia um app externo com argumentos adicionais de linha de comando.
/// Usado para passar flags como `--open-insights` ao lançar a Mnemosyne.
#[tauri::command]
pub fn launch_app_with_args(exe_path: String, args: Vec<String>) -> Result<(), AppError> {
    if exe_path.trim().is_empty() {
        return Err(AppError::InvalidPath(
            "Caminho do executável não configurado.".into(),
        ));
    }

    let mut cmd = build_launch_command(&exe_path);
    cmd.args(&args);
    cmd.spawn()
        .map(|_| ())
        .map_err(|e| AppError::Io(format!("Não foi possível iniciar '{}': {}", exe_path, e)))
}

/// Constrói o Command correto dependendo do tipo de script e plataforma.
/// - Windows + .sh → `bash <path>`
/// - Windows + .bat/.cmd → `cmd /C <path>`  (deixa o cmd resolver o ambiente)
/// - Unix ou binário nativo → executa diretamente
fn build_launch_command(exe_path: &str) -> Command {
    #[cfg(target_os = "windows")]
    {
        let lower = exe_path.to_lowercase();
        if lower.ends_with(".sh") {
            let mut cmd = Command::new("bash");
            cmd.arg(exe_path);
            return cmd;
        }
        if lower.ends_with(".bat") || lower.ends_with(".cmd") {
            let mut cmd = Command::new("cmd");
            cmd.args(["/C", exe_path]);
            return cmd;
        }
    }
    Command::new(exe_path)
}

/// Verifica se um processo correspondente ao executável está em execução.
#[tauri::command]
pub fn is_app_running(exe_path: String) -> bool {
    if exe_path.trim().is_empty() {
        return false;
    }
    check_running(&exe_path)
}

/// Retorna o status de execução para todos os apps informados.
/// `exe_paths`: map `{ "app_name" → "caminho_executável" }`.
///
/// No Windows, apps lançados via .bat não aparecem no tasklist pelo nome do script.
/// Para esses casos fazemos UMA única chamada WMIC que retorna todos os cmdlines,
/// depois buscamos o nome do diretório pai (`\Hermes\`, `\KOSMOS\`, …) em Rust —
/// sem filtro WQL (evita escaping e self-matching do processo WMIC).
#[tauri::command]
pub fn get_all_app_statuses(exe_paths: HashMap<String, String>) -> HashMap<String, bool> {
    #[cfg(target_os = "windows")]
    {
        // Separar .bat/.sh (detectados por cmdline) de binários nativos (detectados por tasklist)
        let mut script_apps: Vec<(String, String)> = Vec::new(); // (app, dir_name)
        let mut exe_apps: Vec<(String, String)>    = Vec::new(); // (app, exe_path)

        for (app, path) in &exe_paths {
            if path.trim().is_empty() {
                continue;
            }
            let lower = path.to_lowercase();
            if lower.ends_with(".bat") || lower.ends_with(".sh") {
                let dir_name = std::path::Path::new(path)
                    .parent()
                    .and_then(|p| p.file_name())
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .to_string();
                if !dir_name.is_empty() {
                    script_apps.push((app.clone(), dir_name));
                }
            } else {
                exe_apps.push((app.clone(), path.clone()));
            }
        }

        // Uma única chamada WMIC para todos os scripts — resultado filtrado em Rust
        let all_cmdlines_lower: String = if !script_apps.is_empty() {
            Command::new("wmic")
                .args(["process", "get", "CommandLine", "/format:list"])
                .creation_flags(CREATE_NO_WINDOW)
                .output()
                .map(|out| String::from_utf8_lossy(&out.stdout).to_lowercase())
                .unwrap_or_default()
        } else {
            String::new()
        };

        let mut result: HashMap<String, bool> = HashMap::new();

        for (app, dir_name) in script_apps {
            // Busca \DirName\ (case-insensitive) — o cmdline do WMIC em si não contém \Hermes\ etc.
            let needle = format!("\\{}\\", dir_name.to_lowercase());
            result.insert(app, all_cmdlines_lower.contains(&needle));
        }

        for (app, path) in exe_apps {
            result.insert(app, check_running(&path));
        }

        // Garantir que todos os apps estejam no resultado
        for app in exe_paths.keys() {
            result.entry(app.clone()).or_insert(false);
        }

        result
    }
    #[cfg(not(target_os = "windows"))]
    {
        exe_paths
            .into_iter()
            .map(|(app, path)| {
                let running = if path.trim().is_empty() { false } else { check_running(&path) };
                (app, running)
            })
            .collect()
    }
}

/// Verifica se um caminho aponta para um arquivo executável existente.
#[tauri::command]
pub fn validate_exe_path(path: String) -> bool {
    if path.trim().is_empty() {
        return false;
    }
    std::path::Path::new(&path).is_file()
}

/// Tenta descobrir automaticamente um executável testando uma lista de candidatos.
/// Cada candidato pode ser um nome simples (buscado no PATH) ou um caminho completo.
#[tauri::command]
pub fn discover_app_exe(candidates: Vec<String>) -> Option<String> {
    for candidate in &candidates {
        // Caminho absoluto/relativo que já existe como arquivo
        if std::path::Path::new(candidate.as_str()).is_file() {
            return Some(candidate.clone());
        }

        // Busca no PATH: `where` no Windows, `which` no Unix
        let finder = if cfg!(target_os = "windows") { "where" } else { "which" };
        #[allow(unused_mut)]
        let mut finder_cmd = Command::new(finder);
        finder_cmd.arg(candidate.as_str());
        #[cfg(target_os = "windows")]
        finder_cmd.creation_flags(CREATE_NO_WINDOW);
        if let Ok(output) = finder_cmd.output() {
            if output.status.success() {
                let found = String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .next()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty());
                if let Some(path) = found {
                    return Some(path);
                }
            }
        }
    }
    None
}

/// Descobre automaticamente os scripts de inicialização de todos os apps,
/// procurando na pasta raiz do ecossistema (pasta-mãe do diretório HUB/).
/// Retorna um map `{ "app_key" → "caminho_do_script" }` para os apps encontrados.
#[tauri::command]
pub fn auto_discover_all_exe_paths() -> HashMap<String, String> {
    let mut result = HashMap::new();
    let Some(root) = find_ecosystem_root() else {
        return result;
    };

    // Scripts em ordem de prioridade: .sh primeiro no Unix, .bat primeiro no Windows
    #[cfg(target_os = "windows")]
    let scripts: &[&str] = &["iniciar.bat", "iniciar.sh"];
    #[cfg(not(target_os = "windows"))]
    let scripts: &[&str] = &["iniciar.sh", "iniciar.bat"];

    let apps: &[(&str, &str)] = &[
        ("aether",    "AETHER"),
        ("ogma",      "OGMA"),
        ("kosmos",    "KOSMOS"),
        ("mnemosyne", "Mnemosyne"),
        ("hermes",    "Hermes"),
        ("akasha",    "AKASHA"),
    ];

    for (key, subdir) in apps {
        for script in scripts {
            let candidate = root.join(subdir).join(script);
            if candidate.is_file() {
                result.insert(
                    key.to_string(),
                    candidate.to_string_lossy().into_owned(),
                );
                break;
            }
        }
    }

    result
}

// ----------------------------------------------------------
//  Testes
// ----------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_select_model_to_load_returns_first() {
        let names = vec!["gemma-2b".to_string(), "llama-3b".to_string()];
        assert_eq!(select_model_to_load(&names), Some("gemma-2b".to_string()));
    }

    #[test]
    fn test_select_model_to_load_empty_returns_none() {
        assert_eq!(select_model_to_load(&[]), None);
    }

    #[test]
    fn test_select_model_to_load_single_element() {
        let names = vec!["only-model".to_string()];
        assert_eq!(select_model_to_load(&names), Some("only-model".to_string()));
    }

    #[test]
    fn test_select_model_to_load_llm_skips_bge() {
        let names = vec![
            "bge-m3-Q4_K_M".to_string(),
            "gemma-2-2b-it-Q4_K_M".to_string(),
            "Qwen2.5-7B-Instruct-Q4_K_M".to_string(),
        ];
        assert_eq!(
            select_model_to_load_llm(&names),
            Some("gemma-2-2b-it-Q4_K_M".to_string())
        );
    }

    #[test]
    fn test_select_model_to_load_llm_skips_mmproj() {
        let names = vec![
            "moondream2-mmproj-f16-20250414".to_string(),
            "moondream".to_string(),
        ];
        assert_eq!(
            select_model_to_load_llm(&names),
            Some("moondream".to_string())
        );
    }

    #[test]
    fn test_select_model_to_load_llm_skips_embed() {
        let names = vec![
            "nomic-embed-text".to_string(),
            "e5-large".to_string(),
            "all-minilm".to_string(),
            "qwen2.5:3b".to_string(),
        ];
        assert_eq!(
            select_model_to_load_llm(&names),
            Some("qwen2.5:3b".to_string())
        );
    }

    #[test]
    fn test_select_model_to_load_llm_empty_returns_none() {
        assert_eq!(select_model_to_load_llm(&[]), None);
    }

    #[test]
    fn test_select_model_to_load_llm_all_embeddings_returns_none() {
        let names = vec!["bge-m3".to_string(), "nomic-embed".to_string()];
        assert_eq!(select_model_to_load_llm(&names), None);
    }

    // ── do_toggle_inference ───────────────────────────────────────────────────

#[tokio::test]
    async fn toggle_disable_no_proc_returns_already_stopped() {
        let dir = tempfile::tempdir().unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), None);
        let result = do_toggle_inference(&state, false, false).await.unwrap();
        assert_eq!(result, "already_stopped");
    }

    #[tokio::test]
    async fn toggle_enable_no_llama_server_returns_not_found() {
        // has_llama_server() = false → NotFound independente de server_responding
        let dir = tempfile::tempdir().unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), None);
        let err = do_toggle_inference(&state, true, false).await.unwrap_err();
        assert!(matches!(err, crate::AppError::NotFound(_)), "esperado NotFound, obteve: {err:?}");
    }

    #[tokio::test]
    async fn toggle_enable_no_models_still_returns_enabled() {
        // Lazy loading: toggle_inference(true) com binário presente mas sem modelos
        // deve retornar "enabled" — a verificação de modelos acontece na primeira requisição.
        let dir = tempfile::tempdir().unwrap();
        let bin = dir.path().join("llama-server");
        std::fs::write(&bin, b"").unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), Some(bin));
        // sem registry.json → modelos ausentes, mas não mais um erro no toggle
        let result = do_toggle_inference(&state, true, false).await.unwrap();
        assert_eq!(result, "enabled", "sem modelos instalados ainda retorna 'enabled' (lazy load)");
    }

    #[tokio::test]
    async fn toggle_enable_returns_enabled_and_sets_flag() {
        // toggle_inference(true) → retorna "enabled" e seta inference_enabled=true.
        // Não deve spawnar nenhum processo (lazy loading).
        let dir = tempfile::tempdir().unwrap();
        let bin = dir.path().join("llama-server");
        std::fs::write(&bin, b"").unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), Some(bin));
        let result = do_toggle_inference(&state, true, false).await.unwrap();
        assert_eq!(result, "enabled");
        assert!(state.inference_enabled(), "inference_enabled deve ser true após toggle(true)");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn toggle_disable_with_active_proc_returns_stopped() {
        let dir = tempfile::tempdir().unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), None);

        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível em Unix");
        state.inject_proc_for_test(child, "stub").await;

        let result = do_toggle_inference(&state, false, false).await.unwrap();
        assert_eq!(result, "stopped");
        assert!(!state.llama_proc_active().await, "proc deve ser None após kill");
    }

    #[tokio::test]
    async fn toggle_enable_orphan_server_returns_enabled() {
        // Cenário: server_responding=true mas llama_proc_active=false (órfão de sessão anterior).
        // A função deve: chamar kill_orphaned_llama_server + setar flag + retornar "enabled".
        let dir = tempfile::tempdir().unwrap();
        let bin = dir.path().join("llama-server");
        std::fs::write(&bin, b"").unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), Some(bin));
        // server_responding=true + proc_active=false → orphan path → habilita lazy e retorna "enabled"
        let result = do_toggle_inference(&state, true, true).await.unwrap();
        assert_eq!(result, "enabled", "após matar órfão deve habilitar lazy loading");
        assert!(state.inference_enabled(), "flag deve ser true após toggle(true) com órfão");
    }

    #[tokio::test]
    async fn lazy_load_toggle_does_not_spawn_llama() {
        // toggle_inference(true) não deve spawnar processo — apenas seta flag.
        let dir = tempfile::tempdir().unwrap();
        let bin = dir.path().join("llama-server");
        std::fs::write(&bin, b"").unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), Some(bin));

        // Pré-condição: nenhum processo ativo
        assert!(!state.llama_proc_active().await, "pré-condição: nenhum proc antes do toggle");
        assert!(!state.inference_enabled(), "pré-condição: flag false antes do toggle");

        let result = do_toggle_inference(&state, true, false).await.unwrap();
        assert_eq!(result, "enabled");

        // Flag setada, mas nenhum processo foi spawned (lazy loading)
        assert!(state.inference_enabled(), "flag deve ser true após toggle(true)");
        assert!(!state.llama_proc_active().await, "nenhum proc deve ter sido spawned — lazy loading");
    }

    #[tokio::test]
    async fn toggle_disable_sets_inference_enabled_false() {
        // toggle_inference(false) deve: matar processos + setar inference_enabled=false.
        let dir = tempfile::tempdir().unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), None);

        // Simula IA ligada
        state.set_inference_enabled(true);
        assert!(state.inference_enabled(), "pré-condição: flag true");

        let result = do_toggle_inference(&state, false, false).await.unwrap();
        assert_eq!(result, "already_stopped"); // nenhum proc ativo

        // Flag deve ser false após toggle(false), independente de haver proc ou não
        assert!(!state.inference_enabled(), "inference_enabled deve ser false após toggle(false)");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn toggle_enable_server_responding_proc_active_returns_already_running() {
        let dir = tempfile::tempdir().unwrap();
        let state = crate::logos::LogosState::for_testing(dir.path().to_path_buf(), None);

        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível em Unix");
        state.inject_proc_for_test(child, "stub").await;

        // server_responding=true e proc_active=true → already_running (sem kill, sem spawn)
        let result = do_toggle_inference(&state, true, true).await.unwrap();
        assert_eq!(result, "already_running");

        state.kill_llama_proc().await;
    }
}

// ----------------------------------------------------------
//  Helpers — descoberta do root do ecossistema
// ----------------------------------------------------------

/// Sobe pelo path do executável atual até encontrar um componente chamado "HUB",
/// depois retorna o pai desse diretório (a pasta raiz do ecossistema).
fn find_ecosystem_root() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut current = exe.as_path();

    while let Some(parent) = current.parent() {
        let is_hub = parent
            .file_name()
            .and_then(|n| n.to_str())
            .map(|n| n.eq_ignore_ascii_case("hub"))
            .unwrap_or(false);

        if is_hub {
            if let Some(root) = parent.parent() {
                if is_ecosystem_root(root) {
                    return Some(root.to_path_buf());
                }
            }
        }
        current = parent;
    }
    None
}

/// Verifica se um diretório é a raiz do ecossistema
/// confirmando a presença de ao menos 2 dos apps conhecidos.
fn is_ecosystem_root(path: &std::path::Path) -> bool {
    ["AETHER", "OGMA", "KOSMOS", "Mnemosyne", "Hermes"]
        .iter()
        .filter(|app| path.join(app).is_dir())
        .count() >= 2
}

// ----------------------------------------------------------
//  Helpers internos
// ----------------------------------------------------------

fn check_running(exe_path: &str) -> bool {
    #[cfg(target_os = "windows")]
    {
        let lower = exe_path.to_lowercase();
        if lower.ends_with(".bat") || lower.ends_with(".sh") {
            // .bat não aparece no tasklist — o processo real é python.exe, cargo.exe, etc.
            // Usa WMIC para buscar o nome do diretório pai (ex: "Hermes") na cmdline dos processos.
            let dir_name = std::path::Path::new(exe_path)
                .parent()
                .and_then(|p| p.file_name())
                .and_then(|n| n.to_str())
                .unwrap_or("");
            if !dir_name.is_empty() {
                return check_running_windows_cmdline(dir_name);
            }
            return false;
        }
        // Binário nativo: busca pelo nome do arquivo no tasklist
        let process_name = std::path::Path::new(exe_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(exe_path)
            .to_string();
        check_running_windows(&process_name)
    }
    #[cfg(not(target_os = "windows"))]
    {
        // No Linux/macOS, busca o exe_path completo na linha de comando do processo
        // (pgrep -f) — funciona tanto para scripts (bash iniciar.sh) quanto para
        // binários instalados, inclusive em modo dev (cargo tauri dev).
        check_running_unix(exe_path)
    }
}

#[cfg(target_os = "windows")]
fn check_running_windows(process_name: &str) -> bool {
    match Command::new("tasklist")
        .args([
            "/FI",
            &format!("IMAGENAME eq {}", process_name),
            "/NH",
            "/FO",
            "CSV",
        ])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout);
            text.to_lowercase()
                .contains(&process_name.to_lowercase())
        }
        Err(_) => false,
    }
}

/// Busca processos cuja linha de comando contém `\dir_name\`.
/// Obtém todos os cmdlines sem filtro WQL (evita escaping e auto-match do WMIC),
/// depois busca `\DirName\` em Rust (case-insensitive).
#[cfg(target_os = "windows")]
fn check_running_windows_cmdline(dir_name: &str) -> bool {
    let needle = format!("\\{}\\", dir_name.to_lowercase());
    match Command::new("wmic")
        .args(["process", "get", "CommandLine", "/format:list"])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
            text.contains(&needle)
        }
        Err(_) => false,
    }
}

#[cfg(not(target_os = "windows"))]
fn check_running_unix(exe_path: &str) -> bool {
    Command::new("pgrep")
        .args(["-f", exe_path])
        .output()
        .map(|out| out.status.success())
        .unwrap_or(false)
}
