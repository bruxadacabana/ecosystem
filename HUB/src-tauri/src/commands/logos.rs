// ============================================================
//  HUB — commands/logos.rs
//  Tauri IPC commands para o frontend consultar e controlar o LOGOS.
// ============================================================

use std::time::Duration;
use tauri::Emitter;
use serde::{Deserialize, Serialize};
use crate::logos::{LogosState, ModelAssignment, OllamaModelEntry, OllamaModelInfo, OllamaStatus, PullProgress, RecommendedModel, StatusResponse};
use crate::ecosystem;

#[derive(Serialize, Clone)]
struct EmbedCompatWarning {
    old_model: String,
    new_model: String,
    old_dims:  u32,
    new_dims:  u32,
}

fn embed_dims(model: &str) -> Option<u32> {
    let m = model.to_lowercase();
    if m.contains("bge-m3")      { return Some(1024) }
    if m.contains("nomic-embed") { return Some(768)  }
    if m.contains("all-minilm")  { return Some(384)  }
    if m.contains("potion")      { return Some(256)  }
    None
}

/// Retorna o status atual do LOGOS: prioridade ativa, fila e VRAM.
#[tauri::command]
pub async fn logos_get_status(
    state: tauri::State<'_, LogosState>,
) -> Result<StatusResponse, String> {
    Ok(crate::logos::collect_status(&state).await)
}

/// Envia keep_alive: 0 para descarregar todos os modelos carregados no Ollama.
/// Retorna o número de modelos descarregados.
#[tauri::command]
pub async fn logos_silence(
    state: tauri::State<'_, LogosState>,
) -> Result<usize, String> {
    Ok(crate::logos::do_silence(&state).await)
}

/// Altera o perfil de workflow ativo.
/// Valores válidos: "normal" | "escrita" | "estudo" | "consumo".
#[tauri::command]
pub async fn logos_set_profile(
    state: tauri::State<'_, LogosState>,
    profile: String,
) -> Result<String, String> {
    Ok(crate::logos::do_set_profile(&state, profile).await)
}

/// Lista os modelos atualmente carregados na VRAM pelo Ollama.
#[tauri::command]
pub async fn logos_list_models(
    state: tauri::State<'_, LogosState>,
) -> Result<Vec<OllamaModelInfo>, String> {
    Ok(crate::logos::do_list_models(&state).await)
}

/// Força o descarregamento de um modelo específico (keep_alive: 0).
#[tauri::command]
pub async fn logos_unload_model(
    state: tauri::State<'_, LogosState>,
    model: String,
) -> Result<bool, String> {
    Ok(crate::logos::do_unload_model(&state, &model).await)
}

/// Lista todos os modelos instalados com status de carregamento (active/available).
/// Combina /api/ps (VRAM) e /api/tags (disco).
#[tauri::command]
pub async fn logos_list_all_models(
    state: tauri::State<'_, LogosState>,
) -> Result<Vec<OllamaModelEntry>, String> {
    Ok(crate::logos::do_list_all_models(&state).await)
}

/// Retorna as atribuições de modelo atuais com indicadores de compatibilidade de hardware.
#[tauri::command]
pub async fn logos_get_model_assignments(
    state: tauri::State<'_, LogosState>,
) -> Result<Vec<ModelAssignment>, String> {
    Ok(crate::logos::do_get_model_assignments(&state).await)
}

/// Sobrescreve o modelo de um slot específico (app + model_type).
/// Passar o modelo recomendado remove o override (restaura padrão).
/// Se o slot for "embed" e as dimensões do novo modelo diferirem do atual,
/// emite `logos-embed-compat-warning` antes de aplicar a troca.
#[tauri::command]
pub async fn logos_set_model_assignment(
    app_handle: tauri::AppHandle,
    state: tauri::State<'_, LogosState>,
    app: String,
    model_type: String,
    model: String,
) -> Result<(), String> {
    if model_type == "embed" {
        let assignments = crate::logos::do_get_model_assignments(&state).await;
        if let Some(current) = assignments.iter().find(|a| a.app == "embed" && a.model_type == "embed") {
            let old = &current.current_model;
            if old != &model {
                if let (Some(old_dims), Some(new_dims)) = (embed_dims(old), embed_dims(&model)) {
                    if old_dims != new_dims {
                        let _ = app_handle.emit("logos-embed-compat-warning", EmbedCompatWarning {
                            old_model: old.clone(),
                            new_model: model.clone(),
                            old_dims,
                            new_dims,
                        });
                    }
                }
            }
        }
    }
    crate::logos::do_set_model_assignment(&state, &app, &model_type, &model).await;
    Ok(())
}

/// Retorna todos os modelos recomendados compilados de todos os perfis de hardware,
/// com status de instalação e justificativas.
#[tauri::command]
pub async fn logos_get_recommended_models(
    state: tauri::State<'_, LogosState>,
) -> Result<Vec<RecommendedModel>, String> {
    Ok(crate::logos::do_get_recommended_models(&state).await)
}

/// Inicia o download de um modelo via Ollama pull.
/// Emite eventos "logos-pull-progress" com PullProgress durante o download.
#[tauri::command]
pub async fn logos_pull_model(
    app: tauri::AppHandle,
    state: tauri::State<'_, LogosState>,
    model: String,
) -> Result<(), String> {
    let ollama_url = crate::logos::collect_status(&state).await.ollama_url;

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3600))
        .build()
        .unwrap_or_default();

    let resp = client
        .post(format!("{ollama_url}/api/pull"))
        .json(&serde_json::json!({ "model": model, "stream": true }))
        .send()
        .await
        .map_err(|e| format!("Ollama indisponível: {e}"))?;

    if !resp.status().is_success() {
        let code = resp.status().as_u16();
        return Err(format!("Ollama retornou {code}"));
    }

    let mut resp = resp;
    let mut buf  = String::new();
    let model_str = model.clone();

    loop {
        let chunk = resp.chunk().await.map_err(|e| format!("Erro ao ler stream: {e}"))?;
        let Some(bytes) = chunk else { break };
        buf.push_str(&String::from_utf8_lossy(&bytes));

        while let Some(pos) = buf.find('\n') {
            let line = buf[..pos].trim().to_string();
            buf.drain(..=pos);
            if line.is_empty() { continue; }
            if let Ok(obj) = serde_json::from_str::<serde_json::Value>(&line) {
                let status_str = obj["status"].as_str().unwrap_or("").to_string();
                let done       = status_str == "success";
                let _ = app.emit("logos-pull-progress", PullProgress {
                    model:     model_str.clone(),
                    status:    status_str,
                    completed: obj["completed"].as_u64(),
                    total:     obj["total"].as_u64(),
                    done,
                    error:     None,
                });
                if done { return Ok(()); }
            }
        }
    }

    let _ = app.emit("logos-pull-progress", PullProgress {
        model: model_str, status: "success".to_string(),
        completed: None, total: None, done: true, error: None,
    });
    Ok(())
}

/// Remove um modelo do disco via DELETE /api/delete do Ollama.
/// O modelo não deve estar ativo na VRAM — descarregue antes de remover.
#[tauri::command]
pub async fn logos_delete_model(
    state: tauri::State<'_, LogosState>,
    model: String,
) -> Result<(), String> {
    let ollama_url = crate::logos::collect_status(&state).await.ollama_url;
    let client = reqwest::Client::new();
    let resp = client
        .delete(format!("{ollama_url}/api/delete"))
        .json(&serde_json::json!({ "name": model }))
        .send()
        .await
        .map_err(|e| format!("Ollama indisponível: {e}"))?;
    if resp.status().is_success() {
        Ok(())
    } else {
        let code = resp.status().as_u16();
        let body = resp.text().await.unwrap_or_default();
        Err(format!("Erro {code}: {body}"))
    }
}

/// Cancela a geração em andamento para um modelo específico sem descarregá-lo da VRAM.
/// Retorna true se havia uma inferência ativa para esse modelo.
#[tauri::command]
pub async fn logos_abort_model_inference(
    state: tauri::State<'_, LogosState>,
    model: String,
) -> Result<bool, String> {
    Ok(state.abort_inference(&model).await)
}

/// Define o percentual máximo de VRAM permitido antes de bloquear tarefas P3.
/// Persiste em ecosystem.json como logos.vram_limit_pct. Faixa válida: 50–95.
#[tauri::command]
pub async fn logos_set_vram_limit_pct(
    state: tauri::State<'_, LogosState>,
    pct: f32,
) -> Result<(), String> {
    let clamped = pct.clamp(50.0, 95.0);
    state.set_vram_limit_pct(clamped).await;
    crate::ecosystem::write_section("logos", serde_json::json!({ "vram_limit_pct": clamped }))
        .map_err(|e| format!("Erro ao salvar vram_limit_pct: {e}"))
}

/// Inicia o servidor Ollama com variáveis de ambiente corretas para o hardware.
///
/// Comportamento:
/// - Se já estiver respondendo: emite logos-ollama-status { running: true } e retorna.
/// - Linux: tenta `systemctl start ollama.service` primeiro; se falhar, fallback para
///   subprocesso direto com env vars do perfil.
/// - Windows: spawn direto via build_ollama_serve_command().
/// - Após o spawn, faz polling a cada 500 ms por até 30 s e emite
///   logos-ollama-status { running: true/false } quando o Ollama responder (ou timeout).
/// - Guarda o handle do subprocesso no LogosState para uso no stop.
#[tauri::command]
pub async fn logos_start_ollama(
    app: tauri::AppHandle,
    state: tauri::State<'_, LogosState>,
) -> Result<(), String> {
    let ollama_url = crate::logos::collect_status(&state).await.ollama_url;

    if ollama_check(&ollama_url).await {
        let _ = app.emit("logos-ollama-status", OllamaStatus {
            running: true,
            message: "Ollama já está em execução.".into(),
        });
        return Ok(());
    }

    // Linux: tentar systemctl antes do spawn direto
    #[cfg(not(target_os = "windows"))]
    {
        let systemctl_ok = tokio::process::Command::new("systemctl")
            .args(["start", "ollama.service"])
            .output()
            .await
            .map(|out| out.status.success())
            .unwrap_or(false);
        if systemctl_ok {
            // systemctl gerencia o processo — não há handle de filho para guardar
            return poll_ollama_ready(app, &ollama_url).await;
        }
    }

    // Spawn direto (Windows sempre; Linux como fallback)
    let mut cmd = crate::commands::launcher::build_ollama_serve_command();
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }

    match cmd.spawn() {
        Ok(child) => {
            state.store_ollama_child(child).await;
            poll_ollama_ready(app, &ollama_url).await
        }
        Err(e) => {
            let msg = format!("Falha ao iniciar Ollama: {e}");
            let _ = app.emit("logos-ollama-status", OllamaStatus {
                running: false,
                message: msg.clone(),
            });
            Err(msg)
        }
    }
}

/// Verifica se o Ollama está respondendo (timeout 500 ms).
async fn ollama_check(url: &str) -> bool {
    reqwest::Client::new()
        .get(format!("{url}/api/tags"))
        .timeout(Duration::from_millis(500))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

/// Polling pós-spawn: tenta 60 × 500 ms = 30 s.
/// Emite logos-ollama-status ao primeiro sucesso ou após timeout.
async fn poll_ollama_ready(app: tauri::AppHandle, url: &str) -> Result<(), String> {
    for _ in 0..60 {
        tokio::time::sleep(Duration::from_millis(500)).await;
        if ollama_check(url).await {
            let _ = app.emit("logos-ollama-status", OllamaStatus {
                running: true,
                message: "Ollama pronto.".into(),
            });
            return Ok(());
        }
    }
    let _ = app.emit("logos-ollama-status", OllamaStatus {
        running: false,
        message: "Timeout aguardando Ollama (30 s).".into(),
    });
    Err("Timeout aguardando Ollama (30 s).".into())
}

/// Para o servidor Ollama.
///
/// Prioridade de parada:
/// 1. Se o LOGOS iniciou o processo (handle disponível): `child.kill()` — mais limpo.
/// 2. Windows: verifica se "Ollama app.exe" está na bandeja do sistema via tasklist.
///    Se sim, retorna erro explicativo (o app reinstanciaria o servidor imediatamente).
///    Se não, executa `taskkill /F /IM ollama.exe /T`.
/// 3. Linux: tenta `systemctl stop ollama.service`; fallback para `pkill -f "ollama serve"`.
///
/// Emite `logos-ollama-status { running: false }` após confirmar que o Ollama parou (até 5 s).
#[tauri::command]
pub async fn logos_stop_ollama(
    app: tauri::AppHandle,
    state: tauri::State<'_, LogosState>,
) -> Result<(), String> {
    let ollama_url = crate::logos::collect_status(&state).await.ollama_url;

    // Prioridade 1: matar o child que o LOGOS iniciou
    if state.kill_ollama_child().await {
        wait_ollama_down(&app, &ollama_url).await;
        return Ok(());
    }

    // Prioridade 2/3: SO-específico
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;

        // Detectar se "Ollama app.exe" (bandeja do sistema) está rodando
        let tasklist = std::process::Command::new("tasklist")
            .args(["/FI", "IMAGENAME eq ollama app.exe", "/NH", "/FO", "CSV"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).to_lowercase())
            .unwrap_or_default();
        if tasklist.contains("ollama app.exe") {
            return Err(
                "O app do Ollama está na bandeja do sistema e reiniciaria o servidor automaticamente. \
                 Feche-o antes de parar.".to_string()
            );
        }

        std::process::Command::new("taskkill")
            .args(["/F", "/IM", "ollama.exe", "/T"])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("taskkill falhou: {e}"))?;
    }
    #[cfg(not(target_os = "windows"))]
    {
        let systemctl_ok = tokio::process::Command::new("systemctl")
            .args(["stop", "ollama.service"])
            .output()
            .await
            .map(|out| out.status.success())
            .unwrap_or(false);
        if !systemctl_ok {
            tokio::process::Command::new("pkill")
                .args(["-f", "ollama serve"])
                .spawn()
                .map_err(|e| format!("pkill falhou: {e}"))?;
        }
    }

    wait_ollama_down(&app, &ollama_url).await;
    Ok(())
}

/// Polling até 5 s: aguarda o servidor de inferência parar de responder antes de emitir o evento final.
async fn wait_ollama_down(app: &tauri::AppHandle, ollama_url: &str) {
    let check_url = if ollama_url.contains("7072") {
        // LOGOS proxy — checar diretamente o llama-server na 8080
        "http://localhost:8080/health".to_string()
    } else {
        format!("{ollama_url}/health")
    };
    for _ in 0..10 {
        tokio::time::sleep(Duration::from_millis(500)).await;
        let still_up = reqwest::Client::new()
            .get(&check_url)
            .timeout(Duration::from_millis(400))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false);
        if !still_up {
            break;
        }
    }
    let _ = app.emit("logos-ollama-status", OllamaStatus {
        running: false,
        message: "Ollama encerrado.".into(),
    });
}

// ============================================================
//  Fine-tuning
// ============================================================

/// Estado do ciclo de fine-tuning — espelha logos/finetune_scheduler.py:FinetuneState.
#[derive(Serialize, Deserialize, Clone, Default)]
pub struct FinetuneState {
    pub corpus_chunks_at_last_train: i64,
    pub last_cycle_at:               String,
    pub current_model:               String,
    pub prev_model:                  String,
    pub current_step:                String,
    pub examples_generated:          i64,
    pub last_train_loss:             f64,
    pub running:                     bool,
}

/// Lê {sync_root}/logos/finetune_state.json e retorna o estado atual.
/// Retorna estado vazio se o arquivo não existir ou sync_root não estiver configurado.
#[tauri::command]
pub fn logos_get_finetune_state() -> FinetuneState {
    let eco = ecosystem::read_json();
    let sync_root = eco["sync_root"].as_str().unwrap_or("").trim().to_string();
    if sync_root.is_empty() {
        return FinetuneState::default();
    }
    let path = std::path::PathBuf::from(&sync_root)
        .join("logos")
        .join("finetune_state.json");
    if !path.exists() {
        return FinetuneState::default();
    }
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str::<FinetuneState>(&s).ok())
        .unwrap_or_default()
}

/// Localiza o binário `uv` em locais canônicos (espelha iniciar.sh).
fn find_uv() -> Option<std::path::PathBuf> {
    // Verifica PATH primeiro via which
    if let Ok(p) = which::which("uv") {
        return Some(p);
    }
    // Locais canônicos sem PATH (mesmo que iniciar.sh)
    let home = dirs::home_dir()?;
    for candidate in &[
        home.join(".local").join("bin").join("uv"),
        home.join(".cargo").join("bin").join("uv"),
        std::path::PathBuf::from("/usr/local/bin/uv"),
    ] {
        if candidate.exists() {
            return Some(candidate.clone());
        }
    }
    None
}

/// Localiza o diretório raiz do ecossistema (onde logos/finetune_scheduler.py existe).
/// Tenta: pai do executável, diretório atual, e subidas até encontrar o script.
fn find_ecosystem_root() -> Option<std::path::PathBuf> {
    let marker = std::path::Path::new("logos").join("finetune_scheduler.py");
    // 1. Tentar partir do executável e subir
    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent()?;
        for _ in 0..6 {
            if dir.join(&marker).exists() {
                return Some(dir.to_path_buf());
            }
            dir = dir.parent()?;
        }
    }
    // 2. Diretório de trabalho atual
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join(&marker).exists() {
            return Some(cwd);
        }
    }
    None
}

/// Dispara o ciclo de fine-tuning em background via `uv run python logos/finetune_scheduler.py --trigger`.
///
/// Retorna true se o processo foi iniciado com sucesso.
/// Retorna false se já houver um ciclo em andamento (lock file existe) ou se o
/// uv/ecosistema não forem encontrados.
#[tauri::command]
pub fn logos_trigger_finetune() -> Result<bool, crate::AppError> {
    // Verificar lock file antes de spawnar processo
    let eco = ecosystem::read_json();
    let sync_root = eco["sync_root"].as_str().unwrap_or("").trim().to_string();
    if !sync_root.is_empty() {
        let lock = std::path::PathBuf::from(&sync_root)
            .join("logos")
            .join("finetune.lock");
        if lock.exists() {
            return Ok(false);  // já em andamento
        }
    }

    let ecosystem_root = find_ecosystem_root().ok_or_else(|| {
        crate::AppError::NotFound("logos/finetune_scheduler.py não encontrado. Certifique-se de que o HUB está sendo executado a partir do diretório do ecossistema.".into())
    })?;

    let uv = find_uv().ok_or_else(|| {
        crate::AppError::NotFound("uv não encontrado. Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh".into())
    })?;

    // Spawna processo detached — não aguarda conclusão
    let mut cmd = std::process::Command::new(&uv);
    cmd.args(["run", "--python", "3.13", "python", "logos/finetune_scheduler.py", "--trigger"])
        .current_dir(&ecosystem_root)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // process_group(0) cria novo grupo de processo → sobrevive ao HUB
        cmd.process_group(0);
    }

    cmd.spawn()
        .map(|_| true)
        .map_err(|e| crate::AppError::Io(e.to_string()))
}
