// ============================================================
//  HUB — commands/logos.rs
//  Tauri IPC commands para o frontend consultar e controlar o LOGOS.
// ============================================================

use std::time::Duration;
use tauri::Emitter;
use crate::logos::{LogosState, ModelAssignment, OllamaModelEntry, OllamaModelInfo, OllamaStatus, PullProgress, RecommendedModel, StatusResponse};

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
#[tauri::command]
pub async fn logos_set_model_assignment(
    state: tauri::State<'_, LogosState>,
    app: String,
    model_type: String,
    model: String,
) -> Result<(), String> {
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
