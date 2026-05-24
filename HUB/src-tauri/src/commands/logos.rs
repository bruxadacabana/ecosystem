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

/// Inicia o download de um modelo via LOGOS (HuggingFace).
///
/// Localiza o modelo na lista de recomendados (por nome ou filename) e
/// usa o endpoint /logos/models/download do LOGOS proxy. Emite eventos
/// "logos-pull-progress" com PullProgress durante o download via SSE.
#[tauri::command]
pub async fn logos_pull_model(
    app: tauri::AppHandle,
    state: tauri::State<'_, LogosState>,
    model: String,
) -> Result<(), String> {
    let logos_base = "http://127.0.0.1:7072";

    // Encontra repo_id + filename nos modelos recomendados ou no registry
    let (repo_id, filename) = find_model_hf_info(&state, &model).await
        .ok_or_else(|| format!(
            "Modelo '{model}' não encontrado na lista de recomendados. \
             Use o HUB para baixar modelos suportados."
        ))?;

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(7200))
        .build()
        .unwrap_or_default();

    // Inicia o download
    let start_resp = client
        .post(format!("{logos_base}/logos/models/download"))
        .json(&serde_json::json!({ "repo_id": repo_id, "filename": filename }))
        .send()
        .await
        .map_err(|e| format!("LOGOS indisponível: {e}"))?;

    let status = start_resp.status();
    if !status.is_success() && status.as_u16() != 409 {
        let code = status.as_u16();
        let body = start_resp.text().await.unwrap_or_default();
        return Err(format!("LOGOS retornou {code}: {body}"));
    }

    let body_json: serde_json::Value = start_resp.json().await
        .map_err(|e| format!("Resposta inválida do LOGOS: {e}"))?;
    let id = body_json["id"].as_str()
        .ok_or_else(|| "LOGOS não retornou id de download".to_string())?
        .to_string();

    // Acompanha progresso via SSE
    let mut sse = client
        .get(format!("{logos_base}/logos/models/download/progress/{id}"))
        .send()
        .await
        .map_err(|e| format!("Erro ao acompanhar progresso: {e}"))?;

    let model_str = model.clone();
    let mut buf   = String::new();

    loop {
        let chunk = sse.chunk().await.map_err(|e| format!("Erro ao ler SSE: {e}"))?;
        let Some(bytes) = chunk else { break };
        buf.push_str(&String::from_utf8_lossy(&bytes));

        while let Some(pos) = buf.find('\n') {
            let line = buf[..pos].trim().to_string();
            buf.drain(..=pos);
            if !line.starts_with("data: ") { continue; }
            let data = &line[6..];
            if let Ok(progress) = serde_json::from_str::<serde_json::Value>(data) {
                let done       = progress["done"].as_bool().unwrap_or(false);
                let has_error  = progress["error"].is_string();
                let error_msg  = progress["error"].as_str().map(str::to_string);
                let completed  = progress["bytes_downloaded"].as_u64();
                let total      = progress["total_bytes"].as_u64();
                let status_str = if done { "success" } else { "downloading" };
                let _ = app.emit("logos-pull-progress", PullProgress {
                    model:     model_str.clone(),
                    status:    status_str.into(),
                    completed,
                    total,
                    done,
                    error:     error_msg.clone(),
                });
                if done || has_error {
                    return match error_msg {
                        Some(e) => Err(e),
                        None    => Ok(()),
                    };
                }
            }
        }
    }

    let _ = app.emit("logos-pull-progress", PullProgress {
        model: model_str, status: "success".into(),
        completed: None, total: None, done: true, error: None,
    });
    Ok(())
}

/// Remove um modelo do registry do LOGOS e apaga o arquivo GGUF do disco.
/// O modelo não deve estar carregado na VRAM — descarregue antes de remover.
#[tauri::command]
pub async fn logos_delete_model(
    state: tauri::State<'_, LogosState>,
    model: String,
) -> Result<(), String> {
    use std::path::PathBuf;

    let registry_path = state.models_dir().join("registry.json");
    let text = std::fs::read_to_string(&registry_path)
        .map_err(|e| format!("Falha ao ler registry.json: {e}"))?;
    let mut entries: Vec<crate::logos::ModelRegistryEntry> = serde_json::from_str(&text)
        .map_err(|e| format!("registry.json corrompido: {e}"))?;

    let idx = entries.iter().position(|e| {
        e.name == model || e.filename == model || e.filename.trim_end_matches(".gguf") == model
    }).ok_or_else(|| format!("Modelo '{model}' não encontrado no registry do LOGOS"))?;

    let entry = entries.remove(idx);
    let gguf  = PathBuf::from(&entry.path);
    if gguf.exists() {
        std::fs::remove_file(&gguf)
            .map_err(|e| format!("Falha ao remover arquivo GGUF: {e}"))?;
    }

    let tmp = registry_path.with_extension("tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(&entries).unwrap_or_default())
        .map_err(|e| format!("Falha ao escrever registry.json: {e}"))?;
    std::fs::rename(&tmp, &registry_path)
        .map_err(|e| format!("Falha ao atualizar registry.json: {e}"))?;

    log::info!("LOGOS: modelo '{}' removido do registry e disco", model);
    Ok(())
}

/// Mapeia nome de modelo para (repo_id, filename) no HuggingFace.
/// Consulta primeiro o registry LOGOS (modelos já baixados), depois a lista de recomendados.
async fn find_model_hf_info(
    state: &tauri::State<'_, LogosState>,
    model: &str,
) -> Option<(String, String)> {
    // 1. Registry local (modelo já baixado via HUB)
    let registry_path = state.models_dir().join("registry.json");
    if let Ok(text) = std::fs::read_to_string(&registry_path) {
        if let Ok(entries) = serde_json::from_str::<Vec<crate::logos::ModelRegistryEntry>>(&text) {
            if let Some(e) = entries.iter().find(|e| {
                e.name == model || e.filename == model || e.name.contains(model)
            }) {
                return Some((e.repo_id.clone(), e.filename.clone()));
            }
        }
    }
    // 2. Mapeamento estático: nome de modelo → (repo_id, filename no HuggingFace)
    let hf = model_hf_table(model)?;
    Some((hf.0.to_string(), hf.1.to_string()))
}

/// Tabela estática de mapeamento: nome/alias do modelo → (repo_id, filename GGUF).
fn model_hf_table(model: &str) -> Option<(&'static str, &'static str)> {
    let m = model.to_lowercase();
    let m = m.trim_end_matches(":latest");
    match m {
        "smollm2:1.7b" | "smollm2-1.7b" | "smollm2_1.7b" =>
            Some(("HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF", "SmolLM2-1.7B-Instruct-Q4_K_M.gguf")),
        "gemma2:2b" | "gemma2-2b" | "gemma-2-2b" =>
            Some(("bartowski/gemma-2-2b-it-GGUF", "gemma-2-2b-it-Q4_K_M.gguf")),
        "llama3.2:3b" | "llama3.2-3b" | "llama-3.2-3b" =>
            Some(("bartowski/Llama-3.2-3B-Instruct-GGUF", "Llama-3.2-3B-Instruct-Q4_K_M.gguf")),
        "command-r:7b" | "command-r-7b" =>
            Some(("bartowski/c4ai-command-r7b-12-2024-GGUF", "c4ai-command-r7b-12-2024-Q4_K_M.gguf")),
        "nomic-embed-text" =>
            Some(("nomic-ai/nomic-embed-text-v1.5-GGUF", "nomic-embed-text-v1.5.Q4_K_M.gguf")),
        _ => None,
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

/// Verifica se o backend de inferência (llama-server via LOGOS) está respondendo.
/// Emite logos-inference-status { running: bool }.
#[tauri::command]
pub async fn logos_start_inference(
    app: tauri::AppHandle,
    _state: tauri::State<'_, LogosState>,
) -> Result<(), String> {
    let running = inference_check("http://127.0.0.1:7072/health").await;
    let _ = app.emit("logos-inference-status", OllamaStatus {
        running,
        message: if running {
            "LOGOS ativo.".into()
        } else {
            "LOGOS não está respondendo — verifique se o HUB está em execução.".into()
        },
    });
    Ok(())
}

/// Para o llama-server para liberar VRAM.
/// Emite logos-inference-status { running: false } após o encerramento.
#[tauri::command]
pub async fn logos_stop_inference(
    app: tauri::AppHandle,
    state: tauri::State<'_, LogosState>,
) -> Result<(), String> {
    state.kill_llama_proc().await;
    wait_inference_down(&app).await;
    Ok(())
}

/// Verifica se o LOGOS (llama-server) está respondendo via /health (timeout 500 ms).
async fn inference_check(url: &str) -> bool {
    reqwest::Client::new()
        .get(url)
        .timeout(Duration::from_millis(500))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

/// Polling até 5 s: aguarda o llama-server parar, depois emite evento de status.
async fn wait_inference_down(app: &tauri::AppHandle) {
    for _ in 0..10 {
        tokio::time::sleep(Duration::from_millis(500)).await;
        if !inference_check("http://127.0.0.1:7072/health").await {
            break;
        }
    }
    let _ = app.emit("logos-inference-status", OllamaStatus {
        running: false,
        message: "Backend de inferência encerrado.".into(),
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
