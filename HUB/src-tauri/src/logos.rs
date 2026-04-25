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
use tokio::sync::{Mutex, Semaphore};

pub const LOGOS_PORT: u16 = 7072;

// Tempos máximos de espera na fila por prioridade
const P2_TIMEOUT: Duration = Duration::from_secs(60);
const P3_TIMEOUT: Duration = Duration::from_secs(30);

// P3 recebe 429 imediatamente se VRAM acima deste limiar
const VRAM_P3_BLOCK: f32 = 0.85;

// ── Estado interno ────────────────────────────────────────────

struct Inner {
    ollama_url: String,
    semaphore: Arc<Semaphore>,
    active_priority: Mutex<Option<u8>>,
    queue_counts: Mutex<[u32; 3]>,
    client: Client,
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
        Self(Arc::new(Inner {
            ollama_url: ollama_url.into(),
            semaphore: Arc::new(Semaphore::new(1)),
            active_priority: Mutex::new(None),
            queue_counts: Mutex::new([0, 0, 0]),
            client,
        }))
    }
}

// ── Tipos de resposta ─────────────────────────────────────────

#[derive(Serialize, Clone)]
pub struct StatusResponse {
    pub active_priority: Option<u8>,
    /// Contagem de requests aguardando por prioridade [P1, P2, P3]
    pub queue: [u32; 3],
    /// VRAM em uso (MB) reportada pelo Ollama /api/ps
    pub vram_used_mb: Option<u64>,
    /// Razão vram_used / vram_total; None se total desconhecido
    pub vram_pct: Option<f32>,
    pub ollama_url: String,
}

// ── Router ────────────────────────────────────────────────────

pub fn build_router(state: LogosState) -> Router {
    Router::new()
        .route("/logos/status",  get(status_handler))
        .route("/logos/chat",    post(chat_handler))
        .route("/logos/silence", post(silence_handler))
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
    let priority = body
        .remove("priority")
        .and_then(|v| v.as_u64())
        .map(|p| p.clamp(1, 3) as u8)
        .unwrap_or(3);
    // Remove campos LOGOS-específicos; o restante vai ao Ollama
    body.remove("app");
    let ollama_payload = serde_json::Value::Object(body);

    // P3: rejeitar imediatamente se VRAM saturada
    if priority == 3 {
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
    }

    // Incrementa contador de fila
    s.0.queue_counts.lock().await[(priority - 1) as usize] += 1;

    // Aguarda semáforo respeitando timeout por prioridade
    let sem = s.0.semaphore.clone();
    let permit = match priority {
        1 => sem.acquire_owned().await.ok(),
        2 => tokio::time::timeout(P2_TIMEOUT, sem.acquire_owned())
                .await.ok().and_then(|r| r.ok()),
        _ => tokio::time::timeout(P3_TIMEOUT, sem.acquire_owned())
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

    // Marca prioridade ativa
    *s.0.active_priority.lock().await = Some(priority);

    // Encaminha ao Ollama
    let url = format!("{}/api/chat", s.0.ollama_url);
    let result = s.0.client.post(&url).json(&ollama_payload).send().await;

    // Limpa prioridade ativa antes de liberar o semáforo
    *s.0.active_priority.lock().await = None;
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

// ── Lógica pública (usada também pelos Tauri commands) ────────

pub async fn collect_status(s: &LogosState) -> StatusResponse {
    let active_priority = *s.0.active_priority.lock().await;
    let queue = *s.0.queue_counts.lock().await;
    let (vram_used_mb, vram_pct) = vram_usage(&s.0.client, &s.0.ollama_url).await;
    StatusResponse {
        active_priority,
        queue,
        vram_used_mb,
        vram_pct,
        ollama_url: s.0.ollama_url.clone(),
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

// ── VRAM helpers ──────────────────────────────────────────────

async fn vram_pct(client: &Client, ollama_url: &str) -> Option<f32> {
    vram_usage(client, ollama_url).await.1
}

async fn vram_usage(client: &Client, ollama_url: &str) -> (Option<u64>, Option<f32>) {
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
    let total_mb = total_vram_mb();
    let pct = total_mb.filter(|&t| t > 0).map(|t| used_mb as f32 / t as f32);
    (Some(used_mb), pct)
}

/// Lê a memória VRAM total da GPU via sysfs (Linux/AMD).
/// Itera todos os cards e retorna o maior valor — garante que a GPU discreta
/// (RX 6600, card1+) seja usada em vez da integrada (card0, Vega/UMA ~2-3 GB).
fn total_vram_mb() -> Option<u64> {
    #[cfg(target_os = "linux")]
    {
        let mut max_mb: Option<u64> = None;
        for i in 0..8u8 {
            let path = format!("/sys/class/drm/card{i}/device/mem_info_vram_total");
            if let Ok(s) = std::fs::read_to_string(&path) {
                if let Ok(bytes) = s.trim().parse::<u64>() {
                    let mb = bytes / 1_048_576;
                    max_mb = Some(max_mb.map_or(mb, |prev| prev.max(mb)));
                }
            }
        }
        return max_mb;
    }
    #[allow(unreachable_code)]
    None
}

// ── Entry point ───────────────────────────────────────────────

pub async fn start_server(state: LogosState) {
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
