// ============================================================
//  LOGOS — Proxy central de LLM integrado ao HUB
//
//  Expõe um servidor HTTP em 127.0.0.1:7072 consumido pelos
//  apps Python do ecossistema. Serializa chamadas ao Ollama
//  numa fila de prioridades (P1 > P2 > P3) e monitora VRAM
//  da GPU (AMD/Linux via sysfs; fallback: uso relativo via Ollama /api/ps).
//
//  Rotas:
//    GET  /logos/status  → StatusResponse
//    POST /logos/chat    → proxy para Ollama /api/chat
//    POST /logos/silence → keep_alive: 0 em todos os modelos carregados
//
//  Otimizações de Ollama gerenciadas pelo LOGOS:
//    keep_alive: -1  → injetado automaticamente em todo request (modelo
//                      permanece carregado na VRAM entre chamadas)
//    Concorrência dinâmica via semáforo com 2 permits:
//      modelos leves (≤3B) → adquire 1 permit → até 2 rodam em paralelo
//      modelos pesados (>3B) → adquire 2 permits → exclusividade total
//      Requer OLLAMA_NUM_PARALLEL=2 no systemd para o Ollama aceitar 2
//      requests simultâneos.
// ============================================================

use axum::{
    extract::State,
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use reqwest::Client;
use serde::Serialize;
use std::sync::Arc;
use std::time::Duration;
use sysinfo::{ProcessesToUpdate, System};
use tokio::sync::{Mutex, Semaphore};

pub const LOGOS_PORT: u16 = 7072;

// Tempos máximos de espera na fila por prioridade
const P2_TIMEOUT: Duration = Duration::from_secs(60);
const P3_TIMEOUT: Duration = Duration::from_secs(30);

// P3 recebe 429 imediatamente se VRAM acima deste limiar
const VRAM_P3_BLOCK: f32 = 0.85;
// P3 recebe 429 se CPU ou RAM insuficiente — protege Windows e laptop durante indexação
const CPU_P3_BLOCK: f32 = 85.0;
const RAM_P3_BLOCK_MB: u64 = 1_536;
// Em bateria: threshold de CPU mais conservador para P2 (preservar energia)
const ON_BATTERY_P2_CPU_BLOCK: f32 = 60.0;

// ── Perfil de hardware ────────────────────────────────────────

/// Identifica em qual máquina o HUB está rodando.
/// Detectado em runtime via fingerprint de GPU — uma única vez no startup.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HardwareProfile {
    /// PC principal — AMD Ryzen 5 4600G + RX 6600 8 GB (ROCm/Linux)
    MainPc,
    /// Laptop Ideapad 330 — i7-8550U + NVIDIA MX150 2 GB (CUDA/Linux)
    Laptop,
    /// PC de trabalho — i5-3470 sem GPU discreta (CPU-only/Windows)
    WorkPc,
}

impl HardwareProfile {
    pub fn as_str(self) -> &'static str {
        match self {
            HardwareProfile::MainPc => "main_pc",
            HardwareProfile::Laptop => "laptop",
            HardwareProfile::WorkPc => "work_pc",
        }
    }

    pub fn display(self) -> &'static str {
        match self {
            HardwareProfile::MainPc => "PC Principal · RX 6600 (8 GB)",
            HardwareProfile::Laptop => "Laptop · MX150 (2 GB)",
            HardwareProfile::WorkPc => "PC de Trabalho · CPU-only",
        }
    }

    pub fn model_profile(self) -> ModelProfile {
        match self {
            HardwareProfile::MainPc => ModelProfile {
                llm_mnemosyne: "qwen2.5:7b",
                llm_kosmos:    "gemma2:2b",
                embed:         "bge-m3",
            },
            HardwareProfile::Laptop => ModelProfile {
                llm_mnemosyne: "gemma2:2b",
                llm_kosmos:    "smollm2:1.7b",
                embed:         "nomic-embed-text",
            },
            HardwareProfile::WorkPc => ModelProfile {
                llm_mnemosyne: "smollm2:1.7b",
                llm_kosmos:    "smollm2:1.7b",
                embed:         "all-minilm",
            },
        }
    }
}

/// Modelos recomendados para cada perfil de hardware.
/// Lidos pelos apps Python via `GET /logos/hardware` no startup.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct ModelProfile {
    pub llm_mnemosyne: &'static str,
    pub llm_kosmos:    &'static str,
    pub embed:         &'static str,
}

/// Detecta o perfil de hardware em runtime via fingerprint de GPU.
/// Chamada uma única vez no startup — bloqueante mas negligenciável.
///
/// Lógica em cascata:
///   1. Windows (compile-time)                          → WorkPc
///   2. Linux: `nvidia-smi` retorna "MX150"             → Laptop
///   3. Linux: AMD sysfs VRAM ≥ 4 GiB (RX 6600 = 8 GiB) → MainPc
///   4. Fallback                                         → WorkPc
pub fn detect_hardware_profile() -> HardwareProfile {
    #[cfg(target_os = "windows")]
    return HardwareProfile::WorkPc;

    #[cfg(target_os = "linux")]
    {
        // Etapa 1: NVIDIA MX150 → Laptop
        if let Ok(out) = std::process::Command::new("nvidia-smi")
            .args(["--query-gpu=name", "--format=csv,noheader"])
            .output()
        {
            if String::from_utf8_lossy(&out.stdout)
                .to_lowercase()
                .contains("mx150")
            {
                return HardwareProfile::Laptop;
            }
        }

        // Etapa 2: AMD sysfs — VRAM ≥ 4 GiB → MainPc
        for i in 0..8u8 {
            let path = format!("/sys/class/drm/card{i}/device/mem_info_vram_total");
            if let Ok(s) = std::fs::read_to_string(&path) {
                if let Ok(bytes) = s.trim().parse::<u64>() {
                    if bytes >= 4 * 1024 * 1024 * 1024 {
                        return HardwareProfile::MainPc;
                    }
                }
            }
        }

        // Etapa 3: Fallback
        return HardwareProfile::WorkPc;
    }

    #[allow(unreachable_code)]
    HardwareProfile::WorkPc
}

// ── Estado interno ────────────────────────────────────────────

struct Inner {
    ollama_url: String,
    /// Semáforo com 2 permits:
    ///   modelos leves  (≤3B): adquire 1 → permite 2 simultâneos
    ///   modelos pesados (>3B): adquire 2 → exclusividade (NUM_PARALLEL efetivo = 1)
    semaphore: Arc<Semaphore>,
    active_priority: Mutex<Option<u8>>,
    /// Classe do modelo em execução: "leve" | "pesado"
    active_model_class: Mutex<Option<String>>,
    /// App que está usando o LOGOS no momento ("kosmos", "mnemosyne", etc.)
    active_app: Mutex<Option<String>>,
    /// Perfil de workflow ativo — altera override de prioridade por app
    active_profile: Mutex<String>,
    /// Modo de hardware determinado em tempo de compilação: "normal" | "sobrevivencia"
    /// "sobrevivencia" é ativado automaticamente em builds Windows (CPU-only, RAM limitada).
    hardware_mode: String,
    /// Perfil de hardware detectado em runtime via fingerprint de GPU.
    hardware_profile: HardwareProfile,
    queue_counts: Mutex<[u32; 3]>,
    client: Client,
    /// Instância sysinfo — mantida entre polls para que CPU% seja calculado como delta.
    /// CRÍTICO: nunca criar nova instância a cada poll (retorna sempre 0%).
    sys: Mutex<System>,
    /// True se rodando em bateria (Linux: /sys/class/power_supply/*/status). Atualizado a cada 60s.
    on_battery: Mutex<bool>,
    /// Contagem de requests P3 preemptados por P1 desde o startup.
    preempted_count: Mutex<u32>,
    /// PID do processo Ollama detectado em runtime.
    /// None se o Ollama ainda não foi encontrado ou reiniciou.
    ollama_pid: Mutex<Option<u32>>,
}

/// Handle compartilhável do estado do LOGOS.
/// Clone é barato (Arc pointer copy).
#[derive(Clone)]
pub struct LogosState(Arc<Inner>);

impl LogosState {
    pub fn new(ollama_url: impl Into<String>) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(300))
            .build()
            .unwrap_or_default();
        let hardware_mode = if cfg!(target_os = "windows") {
            "sobrevivencia".to_string()
        } else {
            "normal".to_string()
        };
        let hardware_profile = detect_hardware_profile();
        // Inicialização prévia do sysinfo — primeira leitura é sempre 0%; a segunda é o delta real.
        let mut sys = System::new_all();
        sys.refresh_cpu_all();
        sys.refresh_memory();
        Self(Arc::new(Inner {
            ollama_url: ollama_url.into(),
            semaphore: Arc::new(Semaphore::new(2)),
            active_priority: Mutex::new(None),
            active_model_class: Mutex::new(None),
            active_app: Mutex::new(None),
            active_profile: Mutex::new("normal".to_string()),
            hardware_mode,
            hardware_profile,
            queue_counts: Mutex::new([0, 0, 0]),
            client,
            sys: Mutex::new(sys),
            on_battery: Mutex::new(is_on_battery()),
            preempted_count: Mutex::new(0),
            ollama_pid: Mutex::new(None),
        }))
    }
}

// ── Tipos de resposta ─────────────────────────────────────────

#[derive(Serialize, Clone)]
pub struct StatusResponse {
    pub active_priority: Option<u8>,
    /// Classe do modelo em execução: "leve" | "pesado" | null
    pub active_model_class: Option<String>,
    /// App que está usando o LOGOS ("kosmos", "mnemosyne", etc.)
    pub active_app: Option<String>,
    /// Perfil de workflow ativo: "normal" | "escrita" | "estudo" | "consumo"
    pub current_profile: String,
    /// Modo de hardware: "normal" (CachyOS/GPU) | "sobrevivencia" (Windows/CPU-only)
    pub hardware_mode: String,
    /// Perfil de hardware detectado: "main_pc" | "laptop" | "work_pc"
    pub hardware_profile: String,
    /// Nome legível do perfil: "PC Principal · RX 6600 (8 GB)" etc.
    pub hardware_profile_display: String,
    /// Contagem de requests aguardando por prioridade [P1, P2, P3]
    pub queue: [u32; 3],
    /// VRAM em uso (MB) reportada pelo Ollama /api/ps
    pub vram_used_mb: Option<u64>,
    /// Razão vram_used / vram_total; None se total desconhecido
    pub vram_pct: Option<f32>,
    pub ollama_url: String,
    /// Uso de CPU global (%) via sysinfo — delta entre dois polls consecutivos
    pub cpu_pct: f32,
    /// RAM livre em MB via sysinfo
    pub ram_free_mb: u64,
    /// RAM total em MB via sysinfo
    pub ram_total_mb: u64,
    /// True se rodando em bateria — P3 bloqueado, thresholds de P2 mais conservadores
    pub on_battery: bool,
    /// Requests P3 preemptados por P1 desde o startup
    pub preempted_count: u32,
}

#[derive(Serialize, Clone)]
pub struct OllamaModelInfo {
    pub name: String,
    pub size_vram_mb: u64,
}

#[derive(Serialize)]
pub struct HardwareResponse {
    pub profile:         &'static str,
    pub profile_display: &'static str,
    pub models:          ModelProfile,
}

// ── Router ────────────────────────────────────────────────────

pub fn build_router(state: LogosState) -> Router {
    Router::new()
        .route("/logos/status",  get(status_handler))
        .route("/logos/chat",    post(chat_handler))
        .route("/logos/silence", post(silence_handler))
        .route("/logos/profile", post(profile_handler))
        .route("/logos/models",   get(models_handler))
        .route("/logos/hardware", get(hardware_handler))
        .with_state(state)
}

// ── Handlers ─────────────────────────────────────────────────

async fn status_handler(State(s): State<LogosState>) -> Json<StatusResponse> {
    Json(collect_status(&s).await)
}

async fn chat_handler(
    State(s): State<LogosState>,
    Json(mut body): Json<serde_json::Map<String, serde_json::Value>>,
) -> Response {
    let requested_priority = body
        .remove("priority")
        .and_then(|v| v.as_u64())
        .map(|p| p.clamp(1, 3) as u8)
        .unwrap_or(3);
    // Lê app antes de remover (rastreamento + override de perfil)
    let app_name = body
        .remove("app")
        .and_then(|v| v.as_str().map(String::from))
        .unwrap_or_default();

    // Aplica override de prioridade baseado no perfil ativo
    let profile = s.0.active_profile.lock().await.clone();
    let priority = apply_profile_priority(&profile, &app_name, requested_priority);
    let is_survival = s.0.hardware_mode == "sobrevivencia";

    // Determina classe do modelo e número de permits necessários.
    // Survival: força 2 permits mesmo em modelos leves → serial (sem paralelo no trabalho).
    let model_name = body.get("model")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let light = is_light_model(&model_name);
    let permits = if !is_survival && light { 1u32 } else { 2u32 };
    let model_class = if light { "leve" } else { "pesado" }.to_string();
    let on_battery = *s.0.on_battery.lock().await;

    // Injeção de keep_alive por prioridade (transparente para os apps):
    //   Sobrevivência → 0 (RAM liberada imediatamente, independente da prioridade)
    //   Bateria + P1/P2 → 0 (economiza VRAM; modelo descarregado após cada resposta)
    //   P1 → -1 (modelo permanece na VRAM indefinidamente — sessão ativa)
    //   P2 → "10m" (libera após 10 min de inatividade)
    //   P3 → "0"  (descarrega imediatamente após resposta — background, não precisa ficar quente)
    if is_survival || on_battery {
        body.insert("keep_alive".to_string(), serde_json::json!(0));
    } else {
        let ka = match priority {
            1 => serde_json::json!(-1),
            2 => serde_json::json!("10m"),
            _ => serde_json::json!(0),
        };
        body.entry("keep_alive".to_string()).or_insert(ka);
    }

    // Sobrevivência: cap de num_ctx em 2048 (contextos maiores saturam RAM no Windows)
    if is_survival {
        const MAX_CTX: u64 = 2048;
        if let Some(opts) = body.get_mut("options").and_then(|v| v.as_object_mut()) {
            let ctx = opts.get("num_ctx").and_then(|v| v.as_u64()).unwrap_or(0);
            if ctx == 0 || ctx > MAX_CTX {
                opts.insert("num_ctx".to_string(), serde_json::json!(MAX_CTX));
            }
        } else {
            body.insert("options".to_string(), serde_json::json!({ "num_ctx": MAX_CTX }));
        }
    }

    // Parâmetros de eficiência por prioridade (num_thread, num_batch, num_ctx, num_gpu).
    // Chamado após survival/keep_alive para não sobrescrever caps já aplicados.
    inject_efficiency_params(&mut body, priority, s.0.hardware_profile, is_survival, on_battery);

    let ollama_payload = serde_json::Value::Object(body);

    // Rejeições antecipadas — antes de entrar na fila/semáforo
    if is_survival {
        // Modelos pesados bloqueados: sem VRAM, sem RAM suficiente
        if !light {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({
                    "error": "Modo Sobrevivência: apenas modelos ≤3B são aceitos nesta máquina"
                })),
            ).into_response();
        }
        // P3 bloqueado: sem análise em background no computador de trabalho
        if priority == 3 {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({
                    "error": "Modo Sobrevivência: tarefas P3 desabilitadas para preservar recursos"
                })),
            ).into_response();
        }
    } else if priority == 3 {
        // Em bateria: P3 bloqueado completamente (preservar energia)
        if on_battery {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Modo bateria: tarefas P3 desabilitadas para preservar energia"
                })),
            ).into_response();
        }
        // Normal: rejeita P3 se VRAM saturada
        if let Some(pct) = vram_pct(&s.0.client, &s.0.ollama_url).await {
            if pct > VRAM_P3_BLOCK {
                return (
                    StatusCode::TOO_MANY_REQUESTS,
                    Json(serde_json::json!({
                        "error": "VRAM > 85% — tarefa P3 adiada; tente novamente mais tarde"
                    })),
                ).into_response();
            }
        }
        // CPU/RAM check — protege Windows (sem GPU) e laptop durante indexação pesada
        let (cpu, ram_free) = {
            let (c, f, _) = cpu_ram_usage(&s.0.sys).await;
            (c, f)
        };
        if cpu > CPU_P3_BLOCK || ram_free < RAM_P3_BLOCK_MB {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({
                    "error": format!(
                        "CPU {cpu:.0}% ou RAM livre {ram_free} MB insuficiente — tarefa P3 adiada"
                    )
                })),
            ).into_response();
        }
    } else if priority == 2 && on_battery {
        // Em bateria: threshold de CPU mais conservador para P2
        let (cpu, _ram, _) = cpu_ram_usage(&s.0.sys).await;
        if cpu > ON_BATTERY_P2_CPU_BLOCK {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({
                    "error": format!("CPU {cpu:.0}% em bateria — tarefa P2 adiada")
                })),
            ).into_response();
        }
    }

    // Preempção inteligente (P1 apenas): se P3 está ativo e VRAM insuficiente para P1,
    // força descarregamento dos modelos P3 antes de entrar na fila do semáforo.
    if priority == 1 {
        try_preempt_p3(&s, &model_name).await;
    }

    // Incrementa contador de fila
    s.0.queue_counts.lock().await[(priority - 1) as usize] += 1;

    // Aguarda semáforo respeitando timeout por prioridade.
    // Modelos pesados adquirem 2 permits (exclusividade total);
    // modelos leves adquirem 1 (até 2 simultâneos se OLLAMA_NUM_PARALLEL=2).
    let sem = s.0.semaphore.clone();
    let permit = match priority {
        1 => sem.acquire_many_owned(permits).await.ok(),
        2 => tokio::time::timeout(P2_TIMEOUT, sem.acquire_many_owned(permits))
                .await.ok().and_then(|r| r.ok()),
        _ => tokio::time::timeout(P3_TIMEOUT, sem.acquire_many_owned(permits))
                .await.ok().and_then(|r| r.ok()),
    };

    // Decrementa contador de fila
    let idx = (priority - 1) as usize;
    let mut counts = s.0.queue_counts.lock().await;
    counts[idx] = counts[idx].saturating_sub(1);
    drop(counts);

    let _permit = match permit {
        Some(p) => p,
        None => {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({
                    "error": "Timeout aguardando LOGOS — sistema sobrecarregado"
                })),
            ).into_response();
        }
    };

    // Marca prioridade, classe do modelo e app ativos
    *s.0.active_priority.lock().await    = Some(priority);
    *s.0.active_model_class.lock().await = Some(model_class);
    *s.0.active_app.lock().await         = Some(app_name);

    // Boost de prioridade do Ollama para P1: restaura para normal enquanto responde
    if priority == 1 {
        if let Some(pid) = get_or_find_ollama_pid(&s).await {
            set_ollama_priority(pid, true).await;
        }
    }

    // Encaminha ao Ollama
    let url = format!("{}/api/chat", s.0.ollama_url);
    let result = s.0.client.post(&url).json(&ollama_payload).send().await;

    // Restaura prioridade de background do Ollama após P1
    if priority == 1 {
        if let Some(pid) = *s.0.ollama_pid.lock().await {
            set_ollama_priority(pid, false).await;
        }
    }

    // Limpa estado ativo antes de liberar o semáforo
    *s.0.active_priority.lock().await    = None;
    *s.0.active_model_class.lock().await = None;
    *s.0.active_app.lock().await         = None;
    drop(_permit);

    match result {
        Ok(resp) => {
            let status = resp.status();
            match resp.bytes().await {
                Ok(bytes) => axum::http::Response::builder()
                    .status(status)
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(axum::body::Body::from(bytes))
                    .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response()),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({ "error": format!("Ollama indisponível: {e}") })),
        ).into_response(),
    }
}

async fn silence_handler(State(s): State<LogosState>) -> Response {
    let unloaded = do_silence(&s).await;
    (StatusCode::OK, Json(serde_json::json!({ "unloaded": unloaded }))).into_response()
}

async fn profile_handler(
    State(s): State<LogosState>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    let requested = body["profile"].as_str().unwrap_or("normal").to_string();
    let profile = do_set_profile(&s, requested).await;
    (StatusCode::OK, Json(serde_json::json!({ "profile": profile }))).into_response()
}

async fn models_handler(State(s): State<LogosState>) -> Response {
    let models = do_list_models(&s).await;
    (StatusCode::OK, Json(models)).into_response()
}

async fn hardware_handler(State(s): State<LogosState>) -> Json<HardwareResponse> {
    let hw = s.0.hardware_profile;
    Json(HardwareResponse {
        profile:         hw.as_str(),
        profile_display: hw.display(),
        models:          hw.model_profile(),
    })
}

// ── Lógica pública (usada também pelos Tauri commands) ────────

pub async fn collect_status(s: &LogosState) -> StatusResponse {
    let active_priority    = *s.0.active_priority.lock().await;
    let active_model_class = s.0.active_model_class.lock().await.clone();
    let active_app         = s.0.active_app.lock().await.clone();
    let current_profile    = s.0.active_profile.lock().await.clone();
    let hardware_mode             = s.0.hardware_mode.clone();
    let hardware_profile          = s.0.hardware_profile.as_str().to_string();
    let hardware_profile_display  = s.0.hardware_profile.display().to_string();
    let queue = *s.0.queue_counts.lock().await;
    let (vram_used_mb, vram_pct) = vram_usage(&s.0.client, &s.0.ollama_url).await;
    let (cpu_pct, ram_free_mb, ram_total_mb) = cpu_ram_usage(&s.0.sys).await;
    let on_battery     = *s.0.on_battery.lock().await;
    let preempted_count = *s.0.preempted_count.lock().await;
    StatusResponse {
        active_priority,
        active_model_class,
        active_app,
        current_profile,
        hardware_mode,
        hardware_profile,
        hardware_profile_display,
        queue,
        vram_used_mb,
        vram_pct,
        ollama_url: s.0.ollama_url.clone(),
        cpu_pct,
        ram_free_mb,
        ram_total_mb,
        on_battery,
        preempted_count,
    }
}

/// Envia keep_alive: 0 para descarregar todos os modelos carregados.
/// Retorna o número de modelos descarregados.
pub async fn do_silence(s: &LogosState) -> usize {
    let ps_url = format!("{}/api/ps", s.0.ollama_url);
    let Ok(resp) = s.0.client.get(&ps_url).timeout(Duration::from_secs(5)).send().await else {
        return 0;
    };
    let json = resp.json::<serde_json::Value>().await.unwrap_or_default();
    let models = json["models"].as_array().cloned().unwrap_or_default();
    let count = models.len();
    for model in &models {
        if let Some(name) = model["name"].as_str() {
            let _ = s.0.client
                .post(format!("{}/api/generate", s.0.ollama_url))
                .json(&serde_json::json!({ "model": name, "keep_alive": 0 }))
                .timeout(Duration::from_secs(10))
                .send()
                .await;
        }
    }
    count
}

/// Retorna lista de modelos atualmente carregados na memória pelo Ollama.
pub async fn list_ollama_models(client: &Client, ollama_url: &str) -> Vec<OllamaModelInfo> {
    let Ok(resp) = client
        .get(format!("{}/api/ps", ollama_url))
        .timeout(Duration::from_secs(5))
        .send()
        .await
    else {
        return vec![];
    };
    let Ok(json) = resp.json::<serde_json::Value>().await else {
        return vec![];
    };
    json["models"]
        .as_array()
        .unwrap_or(&vec![])
        .iter()
        .filter_map(|m| {
            let name = m["name"].as_str()?.to_string();
            let size_vram_mb = m["size_vram"].as_u64().unwrap_or(0) / 1_000_000;
            Some(OllamaModelInfo { name, size_vram_mb })
        })
        .collect()
}

/// Envia keep_alive: 0 para descarregar um modelo específico da VRAM.
/// Retorna true se o request chegou ao Ollama (independente de o modelo estar carregado).
pub async fn do_unload_model(s: &LogosState, model: &str) -> bool {
    s.0.client
        .post(format!("{}/api/generate", s.0.ollama_url))
        .json(&serde_json::json!({ "model": model, "keep_alive": 0 }))
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .is_ok()
}

/// Altera o perfil de workflow ativo. Valores inválidos caem em "normal".
/// Retorna o perfil efetivamente aplicado.
pub async fn do_set_profile(s: &LogosState, profile: String) -> String {
    let validated = match profile.as_str() {
        "escrita" | "estudo" | "consumo" | "normal" => profile,
        _ => "normal".to_string(),
    };
    *s.0.active_profile.lock().await = validated.clone();
    validated
}

/// Wrapper público de `list_ollama_models` para uso nos Tauri commands.
pub async fn do_list_models(s: &LogosState) -> Vec<OllamaModelInfo> {
    list_ollama_models(&s.0.client, &s.0.ollama_url).await
}

/// Aplica override de prioridade baseado no perfil ativo e no app requisitante.
///
/// Perfis e seus efeitos:
///   escrita — prioriza AETHER/HUB; rebaixa KOSMOS reader (P1→P2) e Mnemosyne RAG (P2→P3)
///   estudo  — promove Mnemosyne RAG (P2→P1); rebaixa KOSMOS reader (P1→P2)
///   consumo — sem override (KOSMOS P1, tudo normal)
///   normal  — sem override
fn apply_profile_priority(profile: &str, app: &str, requested: u8) -> u8 {
    match profile {
        "escrita" => match (app, requested) {
            // AETHER e HUB (chat interativo) mantêm prioridade máxima
            ("aether" | "hub", p) => p,
            // KOSMOS reader rebaixado: não interrompe a escrita
            ("kosmos", 1) => 2,
            // Mnemosyne RAG rebaixado para background: escrita em foco
            ("mnemosyne", 2) => 3,
            _ => requested,
        },
        "estudo" => match (app, requested) {
            // Mnemosyne RAG promovido: consultas ao vault são prioridade
            ("mnemosyne", 2) => 1,
            // KOSMOS reader rebaixado: não compete com o estudo ativo
            ("kosmos", 1) => 2,
            _ => requested,
        },
        // consumo e normal: sem override de prioridade
        _ => requested,
    }
}

// ── Classificação de modelo ───────────────────────────────────

/// Retorna true se o modelo é "leve" (≤3B parâmetros).
/// Modelos leves adquirem 1 permit → até 2 rodam em paralelo.
/// Modelos pesados adquirem 2 permits → exclusividade total.
fn is_light_model(model: &str) -> bool {
    let lower = model.to_lowercase();
    // Detecta tamanho pelo tag: "gemma2:2b", "qwen2.5:3b", "llama3.2:1b-instruct"
    [":0.5b", ":1b", ":1.5b", ":2b", ":3b",
     "-0.5b", "-1b", "-1.5b", "-2b", "-3b"]
        .iter()
        .any(|p| lower.contains(p))
}

// ── VRAM helpers ──────────────────────────────────────────────

async fn vram_pct(client: &Client, ollama_url: &str) -> Option<f32> {
    vram_usage(client, ollama_url).await.1
}

async fn vram_usage(client: &Client, ollama_url: &str) -> (Option<u64>, Option<f32>) {
    // No Linux, sysfs é a fonte correta para AMD/ROCm —
    // o Ollama reporta size_vram=0 para GPUs AMD, tornando /api/ps inútil para VRAM.
    #[cfg(target_os = "linux")]
    if let Some((total_mb, used_mb)) = sysfs_vram_mb() {
        let pct = if total_mb > 0 { Some(used_mb as f32 / total_mb as f32) } else { None };
        return (Some(used_mb), pct);
    }

    // Fallback: Ollama /api/ps (NVIDIA ou plataformas sem sysfs AMD)
    let Ok(resp) = client
        .get(format!("{}/api/ps", ollama_url))
        .timeout(Duration::from_secs(3))
        .send()
        .await
    else {
        return (None, None);
    };
    let Ok(json) = resp.json::<serde_json::Value>().await else {
        return (None, None);
    };
    let used_bytes: u64 = json["models"]
        .as_array()
        .unwrap_or(&vec![])
        .iter()
        .filter_map(|m| m["size_vram"].as_u64())
        .sum();
    let used_mb = used_bytes / 1_000_000;
    let total_mb = sysfs_vram_mb().map(|(t, _)| t);
    let pct = total_mb.filter(|&t| t > 0).map(|t| used_mb as f32 / t as f32);
    (Some(used_mb), pct)
}

/// Lê total e uso de VRAM da GPU discreta via sysfs (Linux/AMD).
/// Itera card0..card7, identifica a GPU discreta pelo maior mem_info_vram_total
/// e retorna (total_mb, used_mb) desse card.
fn sysfs_vram_mb() -> Option<(u64, u64)> {
    #[cfg(target_os = "linux")]
    {
        let mut best: Option<(u64, u64)> = None; // (total_mb, used_mb)
        for i in 0..8u8 {
            let t_path = format!("/sys/class/drm/card{i}/device/mem_info_vram_total");
            let u_path = format!("/sys/class/drm/card{i}/device/mem_info_vram_used");
            let Ok(t_str) = std::fs::read_to_string(&t_path) else { continue };
            let Ok(u_str) = std::fs::read_to_string(&u_path) else { continue };
            let Ok(t_bytes) = t_str.trim().parse::<u64>() else { continue };
            let Ok(u_bytes) = u_str.trim().parse::<u64>() else { continue };
            let t_mb = t_bytes / 1_048_576;
            let u_mb = u_bytes / 1_048_576;
            best = Some(match best {
                None => (t_mb, u_mb),
                Some((prev_t, _)) if t_mb > prev_t => (t_mb, u_mb),
                Some(prev) => prev,
            });
        }
        return best;
    }
    #[allow(unreachable_code)]
    None
}

/// Lê uso de CPU e memória via sysinfo.
/// Mantém a instância System entre chamadas — CPU% é calculado como delta entre dois polls.
/// Retorna (cpu_pct: f32, ram_free_mb: u64, ram_total_mb: u64).
async fn cpu_ram_usage(sys: &Mutex<System>) -> (f32, u64, u64) {
    let mut s = sys.lock().await;
    s.refresh_cpu_all();
    s.refresh_memory();
    let cpu = s.global_cpu_usage();
    let free_mb  = s.available_memory() / 1_048_576;
    let total_mb = s.total_memory()     / 1_048_576;
    (cpu, free_mb, total_mb)
}

// ── Bateria ───────────────────────────────────────────────────

/// Detecta se o dispositivo está rodando em bateria via sysfs (Linux).
/// Lê /sys/class/power_supply/*/status; retorna true se alguma fonte reportar "Discharging".
/// No Windows retorna sempre false (work_pc é desktop sem bateria).
fn is_on_battery() -> bool {
    #[cfg(target_os = "linux")]
    if let Ok(entries) = std::fs::read_dir("/sys/class/power_supply") {
        for entry in entries.flatten() {
            if let Ok(s) = std::fs::read_to_string(entry.path().join("status")) {
                if s.trim() == "Discharging" {
                    return true;
                }
            }
        }
    }
    false
}

// ── Parâmetros de eficiência por prioridade ───────────────────

/// Injeta parâmetros de eficiência no objeto `options` do body conforme prioridade e hardware.
///
/// P1 normal: sem injeção (máxima performance, app decide).
/// P1 bateria: num_thread=2 (reduzir consumo energético do CPU).
/// P1 survival: num_thread=3 (i5-3470: 4 cores, deixa 1 livre para o SO).
/// P2: num_batch=256 (preservar RAM); em bateria: num_thread=2 adicional.
/// P3: num_thread=2, num_batch=256, num_ctx=2048 (impacto mínimo no sistema).
/// P3 laptop (MX150 2 GB): num_gpu=0 adicional (background roda só na CPU, preserva VRAM).
fn inject_efficiency_params(
    body: &mut serde_json::Map<String, serde_json::Value>,
    priority: u8,
    hw: HardwareProfile,
    is_survival: bool,
    on_battery: bool,
) {
    if priority == 1 {
        let opts = body.entry("options").or_insert_with(|| serde_json::json!({}));
        if let Some(o) = opts.as_object_mut() {
            if is_survival {
                // i5-3470: 4 cores sem hyperthreading — 3 para Ollama, 1 livre para o SO
                o.entry("num_thread").or_insert(serde_json::json!(3));
            } else if on_battery {
                // Em bateria: 2 threads para reduzir consumo energético
                o.entry("num_thread").or_insert(serde_json::json!(2));
            }
        }
        return;
    }
    let opts = body.entry("options").or_insert_with(|| serde_json::json!({}));
    let Some(o) = opts.as_object_mut() else { return };
    match priority {
        2 => {
            o.entry("num_batch").or_insert(serde_json::json!(256));
            if on_battery {
                o.entry("num_thread").or_insert(serde_json::json!(2));
            }
        }
        _ => {
            o.entry("num_thread").or_insert(serde_json::json!(2));
            o.entry("num_batch").or_insert(serde_json::json!(256));
            o.entry("num_ctx").or_insert(serde_json::json!(2048));
            if hw == HardwareProfile::Laptop {
                // MX150 tem apenas 2 GB VRAM — background não deve competir com P1/P2
                o.entry("num_gpu").or_insert(serde_json::json!(0));
            }
        }
    }
}

// ── Preempção inteligente ─────────────────────────────────────

/// Retorna estimativa de VRAM necessária em MB para o modelo, via /api/tags.
/// /api/tags reporta tamanho em disco (bytes); VRAM ≈ 85% para modelos Q4.
/// Fallback: 4 GB (conservador — garante que preemptamos se não conseguirmos estimar).
async fn estimate_model_vram_mb(client: &Client, ollama_url: &str, model: &str) -> u64 {
    let Ok(resp) = client
        .get(format!("{ollama_url}/api/tags"))
        .timeout(Duration::from_secs(3))
        .send()
        .await
    else {
        return 4_096;
    };
    let Ok(json) = resp.json::<serde_json::Value>().await else {
        return 4_096;
    };
    json["models"]
        .as_array()
        .and_then(|arr| {
            arr.iter()
                .find(|m| m["name"].as_str() == Some(model))
                .and_then(|m| m["size"].as_u64())
                .map(|bytes| bytes * 85 / (100 * 1_048_576))
        })
        .unwrap_or(4_096)
}

/// Preempção inteligente: se P3 está ativo E a VRAM livre não comporta o modelo P1,
/// força descarregamento dos modelos via do_silence() e aguarda até 10s para VRAM liberar.
/// Chamado antes do P1 entrar na fila do semáforo — garante VRAM livre quando P1 executa.
async fn try_preempt_p3(s: &LogosState, model_name: &str) {
    if *s.0.active_priority.lock().await != Some(3) {
        return;
    }
    let Some((vram_total, vram_used)) = sysfs_vram_mb() else { return };
    let vram_free = vram_total.saturating_sub(vram_used);
    let needed_mb = estimate_model_vram_mb(&s.0.client, &s.0.ollama_url, model_name).await;
    if vram_free >= needed_mb + 500 {
        return; // VRAM suficiente — coexistência possível
    }
    log::info!(
        "LOGOS: preemptando P3 — VRAM livre {vram_free} MB, necessário ≈{needed_mb} MB para P1 ({model_name})"
    );
    do_silence(s).await;
    *s.0.preempted_count.lock().await += 1;
    // Aguarda até 10s para os modelos serem descarregados do /api/ps
    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    loop {
        if tokio::time::Instant::now() >= deadline {
            break;
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
        if list_ollama_models(&s.0.client, &s.0.ollama_url).await.is_empty() {
            break;
        }
    }
}

// ── Prioridade de processo do Ollama ────────────────────────

/// Encontra o PID do processo Ollama varrendo a tabela de processos do SO.
/// Executa de forma síncrona — deve ser chamado via spawn_blocking.
fn find_ollama_pid_sync() -> Option<u32> {
    let mut sys = System::new();
    sys.refresh_processes(ProcessesToUpdate::All, false);
    sys.processes().iter().find_map(|(pid, proc)| {
        let name = proc.name().to_string_lossy().to_lowercase();
        // Corresponde a "ollama", "ollama.exe" — exclui "ollama_llm" (worker interno)
        if name.starts_with("ollama") && !name.contains("_llm") {
            Some(pid.as_u32())
        } else {
            None
        }
    })
}

/// Ajusta a prioridade de processo do Ollama via comandos de SO.
///
/// `p1_active = true`  → normal priority (nice=0 / NORMAL)
///   Usado quando P1 (chat interativo) está ativo — Ollama recebe sua cota justa de CPU.
/// `p1_active = false` → abaixo do normal (nice=10 / BELOW_NORMAL)
///   Usado em background — P3 cede CPU para apps ativos sem polling ativo do LOGOS.
///
/// Nota: elevar acima do normal (nice < 0) requer root no Linux; usamos
/// apenas 0 ↔ 10 para operar sem privilégios.
async fn set_ollama_priority(pid: u32, p1_active: bool) {
    #[cfg(target_os = "linux")]
    {
        let nice_val = if p1_active { "0" } else { "10" };
        let _ = tokio::process::Command::new("renice")
            .args(["-n", nice_val, "-p", &pid.to_string()])
            .output()
            .await;
    }
    #[cfg(target_os = "windows")]
    {
        // NORMAL_PRIORITY_CLASS = 0x20, BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        let class = if p1_active { "Normal" } else { "BelowNormal" };
        let script = format!(
            "$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{ $p.PriorityClass = '{class}' }}"
        );
        let _ = tokio::process::Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", &script])
            .output()
            .await;
    }
}

/// Retorna o PID do Ollama guardado, ou tenta descobri-lo agora.
/// Atualiza o cache se encontrado.
async fn get_or_find_ollama_pid(s: &LogosState) -> Option<u32> {
    {
        if let Some(pid) = *s.0.ollama_pid.lock().await {
            return Some(pid);
        }
    }
    let pid = tokio::task::spawn_blocking(find_ollama_pid_sync)
        .await
        .ok()
        .flatten();
    if let Some(p) = pid {
        *s.0.ollama_pid.lock().await = Some(p);
    }
    pid
}

// ── cgroup para Ollama via systemd ───────────────────────────

/// Escreve drop-in de cgroup para o serviço Ollama em ~/.config/systemd/user/ollama.service.d/
/// Limita CPU e RAM do Ollama para que o sistema permaneça responsivo durante inferência P3.
/// Aplica apenas em máquinas com GPU discreta (MainPc e Laptop).
#[allow(unused_variables)]
fn configure_cgroup(profile: HardwareProfile) {
    #[cfg(target_os = "linux")]
    {
        use std::io::Write as _;
        let (cpu_weight, cpu_quota, mem_max) = match profile {
            HardwareProfile::MainPc => (20u32, "80%", "10G"),
            HardwareProfile::Laptop => (20u32, "60%", "6G"),
            HardwareProfile::WorkPc => return, // CPU-only sem cgroup — sem GPU para proteger
        };
        let Some(home) = dirs::home_dir() else { return };
        let drop_in = home.join(".config/systemd/user/ollama.service.d");
        if std::fs::create_dir_all(&drop_in).is_err() {
            return;
        }
        let conf = drop_in.join("logos-limits.conf");
        let Ok(mut f) = std::fs::OpenOptions::new()
            .write(true).create(true).truncate(true)
            .open(&conf)
        else {
            return;
        };
        let _ = writeln!(f, "[Service]");
        let _ = writeln!(f, "CPUWeight={cpu_weight}");
        let _ = writeln!(f, "CPUQuota={cpu_quota}");
        let _ = writeln!(f, "MemoryMax={mem_max}");
        let _ = writeln!(f, "IOSchedulingClass=idle");
        log::info!(
            "LOGOS: cgroup escrito em {} — rode `systemctl --user daemon-reload && systemctl --user restart ollama` para aplicar",
            conf.display()
        );
    }
}

// ── Ollama env vars por perfil de hardware ────────────────────

/// Retorna as variáveis de ambiente recomendadas para o Ollama
/// conforme o perfil de hardware detectado.
///
/// | Variável                   | high (RX 6600) | medium (MX150) | low (i5-3470) |
/// |---------------------------|----------------|----------------|---------------|
/// | OLLAMA_MAX_LOADED_MODELS   | 2              | 1              | 1             |
/// | OLLAMA_GPU_OVERHEAD (bytes)| 524 288 000    | 209 715 200    | 0             |
/// | OLLAMA_FLASH_ATTENTION     | 1              | 1              | 0 (sem GPU)   |
/// | OLLAMA_NUM_PARALLEL        | 2              | 1              | 1             |
fn ollama_env_for_profile(profile: HardwareProfile) -> Vec<(&'static str, String)> {
    match profile {
        HardwareProfile::MainPc => vec![
            ("OLLAMA_MAX_LOADED_MODELS", "2".into()),
            ("OLLAMA_GPU_OVERHEAD",      "524288000".into()),
            ("OLLAMA_FLASH_ATTENTION",   "1".into()),
            ("OLLAMA_NUM_PARALLEL",      "2".into()),
        ],
        HardwareProfile::Laptop => vec![
            ("OLLAMA_MAX_LOADED_MODELS", "1".into()),
            ("OLLAMA_GPU_OVERHEAD",      "209715200".into()),
            ("OLLAMA_FLASH_ATTENTION",   "1".into()),
            ("OLLAMA_NUM_PARALLEL",      "1".into()),
        ],
        HardwareProfile::WorkPc => vec![
            ("OLLAMA_MAX_LOADED_MODELS", "1".into()),
            ("OLLAMA_GPU_OVERHEAD",      "0".into()),
            ("OLLAMA_FLASH_ATTENTION",   "0".into()),
            ("OLLAMA_NUM_PARALLEL",      "1".into()),
        ],
    }
}

/// Persiste as variáveis de ambiente do Ollama em arquivo de configuração e registra no log.
///
/// Linux: escreve em `~/.config/ollama/ollama_env` (compatível com systemd EnvironmentFile).
/// Windows: não escreve arquivo (sem systemd); apenas loga as variáveis recomendadas.
///
/// Para aplicar no Linux após escrita:
///   systemctl --user daemon-reload && systemctl --user restart ollama
pub fn configure_ollama_env(profile: HardwareProfile) {
    let vars = ollama_env_for_profile(profile);
    log::info!(
        "LOGOS: perfil {} — variáveis Ollama recomendadas: {}",
        profile.display(),
        vars.iter()
            .map(|(k, v)| format!("{k}={v}"))
            .collect::<Vec<_>>()
            .join(", ")
    );

    #[cfg(target_os = "linux")]
    {
        use std::io::Write;
        let Some(config_dir) = dirs::config_dir() else { return };
        let ollama_dir = config_dir.join("ollama");
        if std::fs::create_dir_all(&ollama_dir).is_err() { return }
        let env_path = ollama_dir.join("ollama_env");
        let Ok(mut f) = std::fs::OpenOptions::new()
            .write(true).create(true).truncate(true)
            .open(&env_path)
        else { return };
        for (k, v) in &vars {
            let _ = writeln!(f, "{k}={v}");
        }
        log::info!(
            "LOGOS: variáveis escritas em {} — rode `systemctl --user restart ollama` para aplicar",
            env_path.display()
        );
    }
}

// ── Entry point ───────────────────────────────────────────────

pub async fn start_server(state: LogosState) {
    // Configura variáveis de ambiente do Ollama conforme o perfil de hardware detectado.
    // No Linux, escreve ~/.config/ollama/ollama_env; sempre loga as variáveis recomendadas.
    configure_ollama_env(state.0.hardware_profile);

    // Escreve drop-in de cgroup para o serviço Ollama (Linux/systemd, perfis high/medium).
    configure_cgroup(state.0.hardware_profile);

    // Task de descoberta do PID do Ollama + prioridade inicial de background.
    // Aguarda 3s para dar tempo do Ollama inicializar caso tenha sido lançado junto com o HUB.
    // Tenta novamente a cada 5 minutos para cobrir reinicios do Ollama.
    let pid_state = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(3)).await;
            if let Some(pid) = tokio::task::spawn_blocking(find_ollama_pid_sync)
                .await
                .ok()
                .flatten()
            {
                let already_known = *pid_state.0.ollama_pid.lock().await == Some(pid);
                *pid_state.0.ollama_pid.lock().await = Some(pid);
                if !already_known {
                    set_ollama_priority(pid, false).await;
                    log::info!(
                        "LOGOS: Ollama PID={pid} detectado — prioridade de background aplicada (nice=10)"
                    );
                }
            }
            tokio::time::sleep(Duration::from_secs(297)).await; // ~5 min total
        }
    });

    // Task de atualização do status de bateria a cada 60s.
    let battery_state = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            *battery_state.0.on_battery.lock().await = is_on_battery();
        }
    });

    let addr = format!("127.0.0.1:{LOGOS_PORT}");
    let listener = match tokio::net::TcpListener::bind(&addr).await {
        Ok(l) => l,
        Err(e) => {
            log::error!("LOGOS: não foi possível iniciar em {addr}: {e}");
            return;
        }
    };
    log::info!("LOGOS iniciado em http://{addr}");
    if let Err(e) = axum::serve(listener, build_router(state)).await {
        log::error!("LOGOS: servidor encerrado inesperadamente: {e}");
    }
}
