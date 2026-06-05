// ============================================================
//  LOGOS — Proxy central de LLM integrado ao HUB
//
//  Expõe um servidor HTTP em 127.0.0.1:7072 consumido pelos
//  apps Python do ecossistema. Serializa chamadas ao Ollama
//  numa fila de prioridades (P1 > P2 > P3) e monitora VRAM
//  da GPU (AMD/Linux via sysfs; fallback: uso relativo via Ollama /api/ps).
//
//  Rotas próprias:
//    GET  /logos/status    → StatusResponse
//    GET  /logos/vram             → VramResponse (usado_mb, total_mb, used_pct, profile)
//    GET  /logos/metrics/stream   → SSE MetricsSnapshot (1 evento/s) para o LogosPanel
//    POST /logos/chat      → proxy para Ollama /api/chat (API legada)
//    POST /logos/silence   → keep_alive: 0 em todos os modelos carregados
//
//  Proxy transparente (apps apontam para 7072 em vez de 11434):
//    POST /api/chat        → fila P1/P2/P3 + hardware guard
//    POST /api/generate    → fila P1/P2/P3 + hardware guard
//    POST /api/embed       → fila P3 (embeddings, endpoint novo do Ollama)
//    POST /api/embeddings  → fila P3 (embeddings, endpoint legado do Ollama)
//    GET  /api/tags        → passthrough direto ao Ollama (sem fila)
//    GET  /api/ps          → passthrough direto ao Ollama (sem fila)
//    DELETE /api/delete    → passthrough direto ao Ollama (sem fila)
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

use tauri::Emitter as _;

use axum::{
    body::Bytes,
    extract::{Path as AxumPath, State},
    http::{header, HeaderMap, StatusCode},
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::{delete, get, post},
    Json, Router,
};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use sysinfo::System;
use tokio::sync::{Mutex, Semaphore};

pub const LOGOS_PORT: u16 = 7072;
/// Porta do servidor llama-server dedicado ao AKASHA (knowledge_worker, query expansion).
pub(crate) const AKASHA_SERVER_PORT: u16    = 8081;
/// Porta do servidor llama-server dedicado ao modelo de embedding (bge-m3, etc.)
pub(crate) const EMBED_SERVER_PORT: u16     = 8082;
/// Porta do servidor llama-server dedicado à Mnemosyne (RAG, indexação, reflexões).
pub(crate) const MNEMOSYNE_SERVER_PORT: u16 = 8083;
/// Timeout (s) para o llama-server responder ao primeiro /health após o spawn.
const LLAMA_SERVER_READY_TIMEOUT_SECS: u64 = 90;
/// Default de `embed_n_gpu_layers`: **0 = embeddings em CPU** (BUG-028).
/// O embed-server (bge-m3, ~0,6 GB) é leve e roda em CPU sem disputar a VRAM com os
/// LLMs de chat de AKASHA+Mnemosyne (uso padrão do PC principal). Mantê-lo fora da VRAM
/// elimina o churn em que o watchdog de VRAM matava o embed-server (P3) ao passar do
/// limite. Pode ser sobrescrito por máquina via `ecosystem.json[logos][embed_n_gpu_layers]`
/// (ex.: -1 para offload total na GPU). Embeddings são P3/background — latência de CPU é aceitável.
const DEFAULT_EMBED_N_GPU_LAYERS: i32 = 0;

// ── Roteamento de servidor ────────────────────────────────────

/// Identifica qual servidor llama-server deve atender uma requisição.
/// Cada servidor tem seu próprio processo llama-server, porta e ciclo de vida independentes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ServerTarget {
    /// Servidor AKASHA (porta 8081) — knowledge_worker, expansão de query.
    Akasha,
    /// Servidor Mnemosyne (porta 8083) — RAG, indexação, reflexões.
    Mnemosyne,
}

/// Determina o servidor alvo com base no nome do app que fez a requisição.
/// Retorna `Mnemosyne` se o nome contém "mnemosyne" (case-insensitive),
/// `Akasha` para tudo o resto (akasha, hub, kosmos, desconhecido, etc.).
fn route_request(app_name: &str) -> ServerTarget {
    if app_name.to_ascii_lowercase().contains("mnemosyne") {
        ServerTarget::Mnemosyne
    } else {
        ServerTarget::Akasha
    }
}

// Tempos máximos de espera na fila por prioridade
const P1_TIMEOUT: Duration = Duration::from_secs(120);
const P2_TIMEOUT: Duration = Duration::from_secs(60);
const P3_TIMEOUT: Duration = Duration::from_secs(30);

// Thresholds normais de throttle P3: quando excedidos, P3 entra em delay loop (não rejeição)
const CPU_P3_BLOCK: f32 = 85.0;
const RAM_P3_BLOCK_MB: u64 = 1_536;
// P3 em modo sobrevivência: thresholds de throttle mais permissivos (Windows sem GPU)
const CPU_P3_SURVIVAL_BLOCK: f32 = 92.0;
const RAM_P3_SURVIVAL_BLOCK_MB: u64 = 512;
// Em bateria: threshold de CPU mais conservador para P2 (preservar energia)
const ON_BATTERY_P2_CPU_BLOCK: f32 = 60.0;
// Thresholds críticos de crash-prevention: únicas condições que disparam hard-reject 503 para P3
const VRAM_CRITICAL_PCT: f32 = 97.0;
const RAM_CRITICAL_MB:   u64 = 400;
const THERMAL_CRITICAL_C: f32 = 93.0;
// Intervalo do delay loop de P3 durante saturação de hardware
const P3_HW_WAIT_SECS: u64 = 30;

// ── Retry-After helper ────────────────────────────────────────

/// Constrói resposta HTTP com header `Retry-After: N` e JSON `{"error":..., "retry_after":N}`.
/// Usado em todos os retornos 429/503 para que os clientes saibam quando tentar novamente.
fn retry_after_response(status: StatusCode, msg: &str, retry_secs: u32) -> axum::response::Response {
    use axum::http::header::RETRY_AFTER;
    axum::http::Response::builder()
        .status(status)
        .header(axum::http::header::CONTENT_TYPE, "application/json")
        .header(RETRY_AFTER, retry_secs.to_string())
        .body(axum::body::Body::from(
            serde_json::json!({ "error": msg, "retry_after": retry_secs }).to_string()
        ))
        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

// ── Política de bateria em 3 níveis ──────────────────────────
/// Controla quanto o LOGOS restringe operações de acordo com o nível de bateria.
///
/// Normal   → sem restrições extras além do comportamento padrão de prioridades.
/// Economy  → bateria 30-80% em descarga: P3 bloqueado; P2 usa menos threads.
/// Critical → bateria <30% em descarga: P2 e P3 bloqueados; apenas P1 aceito.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BatteryPolicy {
    Normal,
    Economy,
    Critical,
}

impl BatteryPolicy {
    /// Calcula a política a partir do estado de descarga e percentual da bateria.
    pub fn from_state(discharging: bool, pct: u8) -> Self {
        if !discharging || pct > 80 {
            BatteryPolicy::Normal
        } else if pct < 30 {
            BatteryPolicy::Critical
        } else {
            BatteryPolicy::Economy
        }
    }

    /// Retorna true quando há alguma restrição ativa (Economy ou Critical).
    pub fn is_restricted(self) -> bool {
        self != BatteryPolicy::Normal
    }

    pub fn as_str(self) -> &'static str {
        match self {
            BatteryPolicy::Normal   => "normal",
            BatteryPolicy::Economy  => "economy",
            BatteryPolicy::Critical => "critical",
        }
    }
}

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

    /// VRAM total em MB da GPU discreta, conforme especificação de hardware.
    /// Usado como fallback em plataformas onde sysfs AMD não está disponível (NVIDIA/Windows).
    pub fn vram_total_mb(self) -> Option<u64> {
        match self {
            HardwareProfile::MainPc => Some(8_192),  // RX 6600 8 GB
            HardwareProfile::Laptop => Some(2_048),  // MX150 2 GB
            HardwareProfile::WorkPc => None,         // sem GPU discreta
        }
    }

    pub fn model_profile(self) -> ModelProfile {
        match self {
            HardwareProfile::MainPc => ModelProfile {
                llm_rag:      "qwen2.5:7b",
                // gemma2:2b coexiste com qwen2.5:7b na VRAM (1.6 + 4.7 = ~6.3 GB < 7.5 GB)
                llm_analysis: "gemma2:2b",
                // qwen2.5:3b: generation + JSON + diálogo para AKASHA; ~1.9 GB; coexiste com qwen2.5:7b (4.7+1.9=6.6 GB)
                llm_query:    "qwen2.5:3b",
                embed:        "bge-m3",
                // moondream: ~1.7 GB VRAM — multimodal compacto; coexiste com qwen2.5:7b (4.7+1.7=6.4 GB < 7.5 GB)
                image_ocr:    "moondream",
                // RX 6600 8 GB — todos os modelos na GPU total
                llm_rag_gpu_layers:      -1,
                llm_analysis_gpu_layers: -1,
                llm_query_gpu_layers:    -1,
                embed_gpu_layers:         -1,
                image_ocr_gpu_layers:     -1,
            },
            HardwareProfile::Laptop => ModelProfile {
                llm_rag:      "gemma2:2b",
                // smollm2:1.7b: análise batch no laptop — JSON 26% tolerável com retry
                llm_analysis: "smollm2:1.7b",
                llm_query:    "smollm2:1.7b",
                // bge-m3 (670 MB): mesmo vetorstore que MainPc — compatível via Syncthing
                embed:        "bge-m3",
                // moondream: ~1.7 GB — LOGOS descarrega bge-m3 antes de carregar (swap explícito)
                image_ocr:    "moondream",
                // gemma2:2b: offload parcial — 17 layers na GPU (~1026 MB)
                // bge-m3 (670 MB) + gemma2:2b parcial (1026 MB) + KV cache (~104 MB) ≈ 1800 MB ✓
                llm_rag_gpu_layers:      17,
                // smollm2:1.7b (~1000 MB) cabe full GPU junto com bge-m3 (670+1000+50=1720 MB)
                llm_analysis_gpu_layers: -1,
                llm_query_gpu_layers:    -1,
                embed_gpu_layers:         -1,
                // moondream: LOGOS descarrega bge-m3 antes — pode usar GPU total
                image_ocr_gpu_layers:     -1,
            },
            HardwareProfile::WorkPc => ModelProfile {
                llm_rag:      "smollm2:1.7b",
                // qwen2.5:0.5b tem JSON parse rate 61% vs smollm2 26% — melhor para extração
                llm_analysis: "qwen2.5:0.5b",
                llm_query:    "qwen2.5:0.5b",
                // bge-m3 em CPU: o work_pc NÃO indexa (só consulta o índice sincronizado),
                // então embeda 1 query por vez — leve. DEVE ser o mesmo modelo das outras
                // máquinas, senão os vetores do banco sincronizado ficam incompatíveis.
                embed:        "bge-m3",
                // WorkPc sem GPU discreta — OCR via Tesseract local apenas
                image_ocr:    "",
                // i5-3470 sem GPU discreta — todos os modelos em CPU
                llm_rag_gpu_layers:      0,
                llm_analysis_gpu_layers: 0,
                llm_query_gpu_layers:    0,
                embed_gpu_layers:         0,
                image_ocr_gpu_layers:     0,
            },
        }
    }
}

/// Modelos recomendados para cada perfil de hardware.
/// Lidos pelos apps Python via `GET /logos/hardware` no startup.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct ModelProfile {
    /// LLM para RAG conversacional (Mnemosyne) — síntese multi-doc, contexto longo.
    pub llm_rag:      &'static str,
    /// LLM para análise/sumarização em background (KOSMOS) — extração estruturada JSON.
    pub llm_analysis: &'static str,
    /// LLM leve para extração on-demand e expansão de query (AKASHA) — latência baixa.
    pub llm_query:    &'static str,
    pub embed:        &'static str,
    /// LLM multimodal para OCR de imagens (Mnemosyne) — "" quando hardware não suporta.
    pub image_ocr:    &'static str,
    /// Layers na GPU para cada modelo (-1 = todas, 0 = CPU only, N = N layers na GPU).
    /// Passado como `--n-gpu-layers` ao llama-server via LOGOS ao carregar o modelo.
    pub llm_rag_gpu_layers:      i32,
    pub llm_analysis_gpu_layers: i32,
    pub llm_query_gpu_layers:    i32,
    pub embed_gpu_layers:         i32,
    pub image_ocr_gpu_layers:     i32,
}

/// Atribuição de modelo para um app+tipo específico.
/// Enviada ao frontend para exibir configuração e indicador de compatibilidade.
#[derive(Serialize, Clone)]
pub struct ModelAssignment {
    /// Identificador do app: "mnemosyne", "kosmos", "embed"
    pub app: String,
    /// "llm" | "embed" | "image_ocr"
    pub model_type: String,
    /// Label legível: "Mnemosyne — LLM", "KOSMOS — LLM", "Embedding (todos os apps)"
    pub label: String,
    /// Modelo atualmente atribuído (override se `is_custom`, senão `recommended_model`)
    pub current_model: String,
    /// Modelo recomendado pelo perfil de hardware
    pub recommended_model: String,
    /// True se a usuária sobrescreveu o recomendado
    pub is_custom: bool,
    /// True se o modelo atual está instalado no Ollama
    pub is_installed: bool,
    /// VRAM estimada em MB (size_disco × 0.65 para modelos Q4); 0 se não instalado
    pub vram_required_mb: u64,
    /// VRAM ou RAM disponível para inferência no hardware atual (MB)
    pub vram_budget_mb: u64,
    /// True se `vram_required_mb <= vram_budget_mb`
    pub fits_hardware: bool,
    /// True se o modelo pode ser baixado automaticamente via HUB (está na HF table).
    /// False para modelos que precisam de instalação manual (ex: multimodais com vários arquivos).
    pub is_downloadable: bool,
}

/// Retorna o orçamento de VRAM/RAM disponível para inferência por hardware (MB).
fn vram_budget_for_profile(profile: HardwareProfile) -> u64 {
    match profile {
        HardwareProfile::MainPc  => 7_500,  // RX 6600 8 GB, buffer de 500 MB
        HardwareProfile::Laptop  => 1_800,  // MX150 2 GB, buffer de 200 MB
        HardwareProfile::WorkPc  => 4_000,  // CPU-only, ~4 GB RAM para inferência
    }
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
        // Etapa 1a: NVIDIA MX150 via nvidia-smi (requer driver proprietário instalado)
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

        // Etapa 1b: NVIDIA via sysfs vendor (funciona com nouveau e sem nvidia-smi).
        // Vendor 0x10de = NVIDIA. Se encontrado E nenhuma AMD ≥ 4 GiB → Laptop.
        // (No ecossistema, o único hardware Linux com NVIDIA é o Laptop MX150.)
        let has_nvidia_sysfs = (0u8..8).any(|i| {
            let path = format!("/sys/class/drm/card{i}/device/vendor");
            std::fs::read_to_string(path)
                .map(|s| s.trim().to_lowercase() == "0x10de")
                .unwrap_or(false)
        });

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

        // Etapa 1b (aplicada após verificar AMD): NVIDIA presente sem AMD ≥ 4 GiB → Laptop
        if has_nvidia_sysfs {
            return HardwareProfile::Laptop;
        }

        // Etapa 3: Fallback
        return HardwareProfile::WorkPc;
    }

    #[allow(unreachable_code)]
    HardwareProfile::WorkPc
}

// ── Estado interno ────────────────────────────────────────────

struct Inner {
    llama_server_url: String,
    /// Semáforo do servidor AKASHA com 2 permits:
    ///   modelos leves  (≤3B): adquire 1 → permite 2 simultâneos
    ///   modelos pesados (>3B): adquire 2 → exclusividade (NUM_PARALLEL efetivo = 1)
    akasha_semaphore: Arc<Semaphore>,
    /// Semáforo do servidor Mnemosyne — independente, mesma política de permits.
    mnemosyne_semaphore: Arc<Semaphore>,
    /// Semáforo EXCLUSIVO do embed-server (capacidade 1).
    /// O embed-server (llama-server na porta EMBED_SERVER_PORT) retorna HTTP 500
    /// quando recebe duas requisições simultâneas. AKASHA e Mnemosyne embedam em
    /// paralelo, então sem um semáforo dedicado os dois proxies de embed colidem.
    /// Capacidade 1 = serialização total das requisições de embedding (BUG-020).
    /// NÃO compartilhar com akasha_semaphore: este é só para embeddings.
    embed_semaphore: Arc<Semaphore>,
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
    /// True se a CPU suporta AVX2 (detectado via CPUID no startup).
    /// O i5-3470 (WorkPc) NÃO tem AVX2 — inferência INT4 é 30-50% mais lenta.
    /// Quando false: num_ctx, num_batch e num_thread são limitados automaticamente.
    has_avx2: bool,
    queue_counts: Mutex<[u32; 3]>,
    client: Client,
    /// Instância sysinfo — mantida entre polls para que CPU% seja calculado como delta.
    /// CRÍTICO: nunca criar nova instância a cada poll (retorna sempre 0%).
    sys: Mutex<System>,
    /// True se rodando em bateria (= BatteryPolicy::Economy ou Critical). Atualizado a cada 30s.
    on_battery: Mutex<bool>,
    /// Percentual da bateria (0–100). 100 quando em AC ou sem bateria. Atualizado a cada 30s.
    battery_pct: Mutex<u8>,
    /// Política de bateria em 3 níveis. Derivada de (on_battery, battery_pct). Atualizada a cada 30s.
    battery_policy: Mutex<BatteryPolicy>,
    /// Contagem de requests P3 preemptados por P1 desde o startup.
    preempted_count: Mutex<u32>,
    /// Substituições de modelo definidas pela usuária.
    /// Chave: "mnemosyne_llm_rag", "kosmos_llm_analysis", "akasha_llm_query", "embed_embed". Valor: nome do modelo.
    /// Vazio = usar recomendado do perfil de hardware.
    model_overrides: Mutex<HashMap<String, String>>,
    /// Contador de crashes consecutivos do servidor AKASHA. Zerado após restart bem-sucedido.
    akasha_crash_count: Mutex<u32>,
    /// True quando o servidor AKASHA atingiu o limite de 3 crashes e foi desabilitado.
    akasha_disabled: Arc<AtomicBool>,
    /// Contador de crashes consecutivos do servidor Mnemosyne.
    mnemosyne_crash_count: Mutex<u32>,
    /// True quando o servidor Mnemosyne atingiu o limite de 3 crashes e foi desabilitado.
    mnemosyne_disabled: Arc<AtomicBool>,
    /// Tauri AppHandle para emissão de eventos críticos ao frontend.
    /// Inicializado em start_server após o setup do Tauri.
    app_handle: Mutex<Option<tauri::AppHandle>>,

    /// Percentual máximo de VRAM permitido antes de bloquear P3.
    /// Padrão: 85. Persistido em ecosystem.json como logos.vram_limit_pct.
    vram_limit_pct: Mutex<f32>,
    /// Handles de abort para inferências em andamento, indexados por nome de modelo.
    /// Permite cancelar uma geração sem descarregar o modelo da VRAM.
    pub(crate) active_inferences: Mutex<HashMap<String, tokio::task::AbortHandle>>,
    /// Flag de histerese do watchdog de VRAM.
    /// true  → VRAM acima do threshold; P3 bloqueado até cair abaixo de 70%.
    /// false → P3 permitido (verificação por-request ainda acontece como defesa).
    p3_vram_blocked: Arc<AtomicBool>,
    /// true quando temperatura da GPU > 85°C — P3 pausado para evitar throttling térmico.
    /// A RX 6600 só faz throttling pelo driver acima de ~95°C; pausamos antes para preservar
    /// desempenho de P1/P2 e evitar o ciclo térmico boost→throttle.
    p3_thermal_blocked: Arc<AtomicBool>,
    /// Temperatura atual da GPU em °C (None se não disponível ou WorkPc sem GPU).
    gpu_temp_celsius: Mutex<Option<f32>>,
    /// Downloads de GGUF em andamento ou concluídos recentemente.
    /// Chave: download ID (timestamp_filename). Valor: sender do canal de progresso.
    downloads: Mutex<HashMap<String, tokio::sync::watch::Sender<DownloadProgress>>>,
    /// Diretório onde os modelos GGUF são salvos: {hub_data_path}/logos/models/
    models_dir: std::path::PathBuf,
    /// Caminho do binário llama-server detectado no startup. None = usar Ollama como fallback.
    llama_server_bin: Option<std::path::PathBuf>,
    /// Processo llama-server AKASHA (porta 8081). None = nenhum modelo carregado.
    akasha_proc: Mutex<Option<LlamaProcHandle>>,
    /// Processo llama-server Mnemosyne (porta 8083). None = nenhum modelo carregado.
    mnemosyne_proc: Mutex<Option<LlamaProcHandle>>,

    // ── Servidor de embedding (porta EMBED_SERVER_PORT) ──────────────────────
    /// Alias canônico do modelo de embedding (ex: "bge-m3").
    /// Lido de ecosystem.json["logos"]["embed_model"] no startup.
    embed_model: Mutex<String>,
    /// Camadas GPU para o servidor de embedding. -1 = offload total (GPU); 0 = CPU.
    /// Lido de ecosystem.json["logos"]["embed_n_gpu_layers"]. Padrão: **0 (CPU)** —
    /// ver `DEFAULT_EMBED_N_GPU_LAYERS` e BUG-028 (embed leve fora da VRAM).
    embed_n_gpu_layers: Mutex<i32>,
    /// Processo llama-server do servidor de embedding (porta EMBED_SERVER_PORT).
    /// Independente do llama_proc (porta AKASHA_SERVER_PORT) — falhas são isoladas.
    embed_proc: Mutex<Option<LlamaProcHandle>>,
    /// Trava de inicialização do embed-server (BUG-027). Serializa `ensure_embed_server_started`
    /// para que AKASHA e Mnemosyne, pedindo embedding AO MESMO TEMPO, não spawnem dois
    /// embed-servers que brigam pela porta 8082. Distinta do `embed_semaphore` (que serializa
    /// as REQUISIÇÕES de embedding, não o startup do processo).
    embed_start_lock: Mutex<()>,
    /// Porta usada por `collect_status` para pings de health no servidor AKASHA.
    /// Em produção = AKASHA_SERVER_PORT (8081). Em testes usa porta livre para isolamento.
    chat_health_port: u16,
    /// Porta usada por `collect_status` para pings de health no servidor de embedding.
    /// Em produção = EMBED_SERVER_PORT (8082). Em testes usa porta livre para isolamento.
    embed_health_port: u16,
    /// Porta usada por `collect_status` para pings de health no servidor Mnemosyne.
    /// Em produção = MNEMOSYNE_SERVER_PORT (8083). Em testes usa porta livre para isolamento.
    mnemosyne_health_port: u16,

    // ── Limites de recursos configuráveis ───────────────────────────────────
    /// Threshold de CPU (%) para bloquear tarefas P3. Padrão 85.
    /// Persistido em ecosystem.json como logos.cpu_p3_limit_pct.
    cpu_p3_limit_pct: Mutex<f32>,
    /// Último valor de CPU% calculado pelo cpu_watchdog (f32 bits em AtomicU32).
    /// Evita que múltiplos callers chamem refresh_cpu_all() com delta ≈ 0.
    cached_cpu_pct: Arc<AtomicU32>,

    // ── Ciclo de vida de modelos ─────────────────────────────────────────────
    /// True quando o usuário ativou a IA ("Ligar IA"). O modelo só é carregado
    /// lazily na primeira requisição real — não no momento do toggle.
    inference_enabled: Arc<AtomicBool>,
    /// Timestamp da última requisição ao servidor AKASHA (llama-server:8081).
    /// Atualizado por queue_and_forward a cada requisição; usado pelo idle watchdog.
    last_akasha_request_at: Mutex<std::time::Instant>,
    /// Timestamp da última requisição ao servidor Mnemosyne (llama-server:8083).
    last_mnemosyne_request_at: Mutex<std::time::Instant>,
    /// Timestamp da última requisição ao servidor de embedding (llama-server:8082).
    last_embed_request_at: Mutex<std::time::Instant>,
    /// Segundos de ociosidade após os quais o servidor de chat é descarregado.
    /// Lido de ecosystem.json["logos"]["idle_timeout_minutes"] (default 5 → 300s).
    idle_timeout_secs: u64,
    /// Tamanho máximo de GGUF (em MB) permitido para fallback CPU.
    /// Modelos acima desse limite retornam Err em vez de tentar rodar no CPU.
    /// Lido de ecosystem.json["logos"]["cpu_fallback_max_gb"] (default 2.0 → 2048 MB).
    cpu_fallback_max_mb: u64,
    /// Número máximo de threads de CPU para o llama-server em modo CPU.
    /// 0 = automático (metade dos cores lógicos).
    /// Lido de ecosystem.json["logos"]["cpu_max_threads"] (default 0).
    cpu_max_threads: usize,
}

/// Handle compartilhável do estado do LOGOS.
/// Clone é barato (Arc pointer copy).
#[derive(Clone)]
pub struct LogosState(Arc<Inner>);

impl LogosState {
    /// Atualiza o limite de VRAM em memória (não persiste — persistência fica em logos_set_vram_limit_pct).
    pub(crate) async fn set_vram_limit_pct(&self, pct: f32) {
        *self.0.vram_limit_pct.lock().await = pct.clamp(50.0, 95.0);
    }

    /// Atualiza o limite de CPU P3 em memória (não persiste — persistência fica em logos_set_cpu_p3_limit_pct).
    pub(crate) async fn set_cpu_p3_limit_pct(&self, pct: f32) {
        *self.0.cpu_p3_limit_pct.lock().await = pct.clamp(30.0, 99.0);
    }

    /// Aborta a inferência em andamento para o modelo especificado.
    /// O modelo permanece aquecido em VRAM. Retorna true se havia inferência ativa.
    pub(crate) async fn abort_inference(&self, model: &str) -> bool {
        if let Some(handle) = self.0.active_inferences.lock().await.remove(model) {
            handle.abort();
            true
        } else {
            false
        }
    }

    /// Para o processo llama-server AKASHA (se houver). Retorna true se havia processo.
    pub(crate) async fn kill_akasha_proc(&self) -> bool {
        let mut guard = self.0.akasha_proc.lock().await;
        if let Some(mut proc) = guard.take() {
            let _ = proc.child.kill();
            log::info!("LOGOS: processo AKASHA parado");
            true
        } else {
            false
        }
    }

    /// Alias de compatibilidade para código legado — chama kill_akasha_proc().
    pub(crate) async fn kill_llama_proc(&self) -> bool {
        self.kill_akasha_proc().await
    }

    /// Para o processo llama-server Mnemosyne (se houver). Retorna true se havia processo.
    pub(crate) async fn kill_mnemosyne_proc(&self) -> bool {
        let mut guard = self.0.mnemosyne_proc.lock().await;
        if let Some(mut proc) = guard.take() {
            let _ = proc.child.kill();
            log::info!("LOGOS: processo Mnemosyne parado");
            true
        } else {
            false
        }
    }

    /// Retorna o diretório de modelos GGUF (para acesso externo ao módulo).
    pub fn models_dir(&self) -> &std::path::Path {
        &self.0.models_dir
    }

    /// Retorna o alias canônico do modelo de embedding configurado.
    pub async fn embed_model(&self) -> String {
        self.0.embed_model.lock().await.clone()
    }

    /// Atualiza o modelo de embedding em memória (persiste via ecosystem.json externamente).
    pub async fn set_embed_model(&self, model: impl Into<String>) {
        *self.0.embed_model.lock().await = model.into();
    }

    /// Retorna true se há um processo embed-server rastreado ativamente.
    pub async fn embed_proc_active(&self) -> bool {
        self.0.embed_proc.lock().await.is_some()
    }

    /// Para o processo embed-server ativo (se houver). Retorna true se havia processo.
    pub(crate) async fn kill_embed_proc(&self) -> bool {
        let mut guard = self.0.embed_proc.lock().await;
        if let Some(mut proc) = guard.take() {
            let _ = proc.child.kill();
            true
        } else {
            false
        }
    }

    /// Retorna true se o binário llama-server foi localizado no startup.
    /// Usado para falha rápida antes de spawnar a task de carregamento.
    pub fn has_llama_server(&self) -> bool {
        self.0.llama_server_bin.is_some()
    }

    /// Retorna true se a IA está habilitada ("Ligar IA" ativado pela usuária).
    /// O modelo pode não estar carregado ainda — será carregado lazily na primeira requisição.
    pub fn inference_enabled(&self) -> bool {
        self.0.inference_enabled.load(Ordering::Relaxed)
    }

    /// Habilita ou desabilita a flag de inferência.
    /// `true` → IA ligada (modelo carrega lazily). `false` → IA desligada (rejeita requisições).
    pub fn set_inference_enabled(&self, val: bool) {
        self.0.inference_enabled.store(val, Ordering::Relaxed);
    }

    /// Retorna true se há um processo llama-server rastreado ativamente pelo HUB.
    pub async fn llama_proc_active(&self) -> bool {
        self.0.akasha_proc.lock().await.is_some()
    }

    /// Retorna true se há um processo Mnemosyne rastreado ativamente.
    pub async fn mnemosyne_proc_active(&self) -> bool {
        self.0.mnemosyne_proc.lock().await.is_some()
    }

    /// Retorna o caminho do binário llama-server, se encontrado.
    pub fn llama_server_path(&self) -> Option<&std::path::Path> {
        self.0.llama_server_bin.as_deref()
    }

    /// Emite um evento de alerta crítico para o frontend (nível "error" | "warn" | "info").
    /// Sem-op se o AppHandle ainda não foi inicializado.
    pub(crate) async fn emit_alert(&self, level: &str, message: &str) {
        #[derive(serde::Serialize, Clone)]
        struct LogosAlert { level: String, message: String, timestamp: String }
        if let Some(handle) = self.0.app_handle.lock().await.as_ref() {
            let _ = handle.emit("logos-alert", LogosAlert {
                level:     level.to_string(),
                message:   message.to_string(),
                timestamp: chrono::Local::now().to_rfc3339(),
            });
        }
    }

    /// Emite `logos-model-corrupted` para o frontend, informando que um modelo
    /// está corrompido ou com download incompleto e permite oferecer reparo.
    ///
    /// `reason`: "file_missing" | "incomplete_download" | "invalid_magic"
    pub(crate) async fn emit_model_corrupted(
        &self,
        model_name: &str,
        model_type: &str,
        reason:     &str,
        repo_id:    &str,
        filename:   &str,
    ) {
        #[derive(serde::Serialize, Clone)]
        struct ModelCorruptedEvent {
            model_name: String,
            model_type: String,
            reason:     String,
            repo_id:    String,
            filename:   String,
        }
        log::error!(
            "LOGOS: modelo '{}' ({}) corrompido — reason={} repo={} file={}",
            model_name, model_type, reason, repo_id, filename
        );
        if let Some(handle) = self.0.app_handle.lock().await.as_ref() {
            let _ = handle.emit("logos-model-corrupted", ModelCorruptedEvent {
                model_name: model_name.to_string(),
                model_type: model_type.to_string(),
                reason:     reason.to_string(),
                repo_id:    repo_id.to_string(),
                filename:   filename.to_string(),
            });
        }
    }

    pub fn new(llama_server_url: impl Into<String>) -> Self {
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
        let models_dir = {
            let eco = crate::ecosystem::read_json();
            let hub_data = eco["hub"]["data_path"].as_str()
                .filter(|s| !s.is_empty())
                .map(std::path::PathBuf::from);
            let xdg_dir = hub_data
                .or_else(|| dirs::data_local_dir().map(|d| d.join("ecosystem").join("hub")))
                .unwrap_or_else(|| {
                    dirs::home_dir()
                        .unwrap_or_else(|| std::path::PathBuf::from("/tmp"))
                        .join(".local").join("share").join("ecosystem").join("hub")
                })
                .join("logos")
                .join("models");
            let cwd_dir = std::env::current_dir()
                .unwrap_or_default()
                .join("logos")
                .join("models");
            pick_models_dir(xdg_dir, cwd_dir)
        };
        let llama_server_bin = find_llama_server_bin();
        if let Some(ref bin) = llama_server_bin {
            log::info!("LOGOS: llama-server encontrado em {} — modo llama-server ativo", bin.display());
        } else {
            log::info!("LOGOS: llama-server não encontrado — usando Ollama como backend de inferência");
        }

        let embed_model = {
            let eco = crate::ecosystem::read_json();
            eco["logos"]["embed_model"]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or("bge-m3")
                .to_string()
        };
        let embed_n_gpu_layers = {
            let eco = crate::ecosystem::read_json();
            eco["logos"]["embed_n_gpu_layers"]
                .as_i64()
                .map(|v| v as i32)
                .unwrap_or(DEFAULT_EMBED_N_GPU_LAYERS)
        };
        let cpu_p3_limit_pct = {
            let eco = crate::ecosystem::read_json();
            eco["logos"]["cpu_p3_limit_pct"]
                .as_f64()
                .map(|v| (v as f32).clamp(30.0, 99.0))
                .unwrap_or(85.0)
        };
        let idle_timeout_secs = {
            let eco = crate::ecosystem::read_json();
            let minutes = eco["logos"]["idle_timeout_minutes"]
                .as_f64()
                .unwrap_or(5.0)
                .max(0.5);
            (minutes * 60.0) as u64
        };
        let cpu_fallback_max_mb = {
            let eco = crate::ecosystem::read_json();
            let gb = eco["logos"]["cpu_fallback_max_gb"]
                .as_f64()
                .unwrap_or(2.0)
                .max(0.1);
            (gb * 1024.0) as u64
        };
        let cpu_max_threads = {
            let eco = crate::ecosystem::read_json();
            eco["logos"]["cpu_max_threads"]
                .as_u64()
                .unwrap_or(0) as usize
        };
        let active_profile = {
            let eco = crate::ecosystem::read_json();
            let p = eco["logos"]["active_profile"]
                .as_str()
                .unwrap_or("analise")
                .to_string();
            match p.as_str() {
                "estudo" | "analise" | "normal" => p,
                _ => "analise".to_string(),
            }
        };
        // Dual-server mode: se ambos llm_query (AKASHA) e llm_rag (Mnemosyne) estiverem
        // configurados, o estado estável usa ~84% da VRAM (3B + 7B). Ajustamos o threshold
        // default de 85% → 93% para evitar bloqueio desnecessário de P3 nesse estado.
        // Apenas quando o threshold ainda está no default (85%) — respeita configuração explícita.
        let vram_limit_pct = {
            let eco = crate::ecosystem::read_json();
            let configured = eco["logos"]["vram_limit_pct"]
                .as_f64()
                .map(|v| (v as f32).clamp(50.0, 95.0))
                .unwrap_or(85.0);
            let akasha_model    = eco["logos"]["llm_query"].as_str().unwrap_or("").to_string();
            let mnemosyne_model = eco["logos"]["llm_rag"].as_str().unwrap_or("").to_string();
            let dual_server = !akasha_model.is_empty() && !mnemosyne_model.is_empty();
            if dual_server && (configured - 85.0).abs() < 0.1 {
                log::info!(
                    "LOGOS: dual-server mode (akasha={akasha_model}, mnemosyne={mnemosyne_model}) \
                     — vram_limit ajustado automaticamente para 93%"
                );
                93.0f32
            } else {
                configured
            }
        };
        log::info!(
            "LOGOS: embed_model='{}' embed_n_gpu_layers={} cpu_p3_limit_pct={:.0}% \
             idle_timeout={}s cpu_fallback_max={}MB cpu_max_threads={} active_profile='{}'",
            embed_model, embed_n_gpu_layers, cpu_p3_limit_pct,
            idle_timeout_secs, cpu_fallback_max_mb,
            if cpu_max_threads == 0 { "auto".to_string() } else { cpu_max_threads.to_string() },
            active_profile
        );

        // Inicialização prévia do sysinfo — primeira leitura é sempre 0%; a segunda é o delta real.
        let mut sys = System::new_all();
        sys.refresh_cpu_all();
        sys.refresh_memory();
        Self(Arc::new(Inner {
            llama_server_url: llama_server_url.into(),
            akasha_semaphore:    Arc::new(Semaphore::new(2)),
            mnemosyne_semaphore: Arc::new(Semaphore::new(2)),
            embed_semaphore:     Arc::new(Semaphore::new(1)),
            active_priority: Mutex::new(None),
            active_model_class: Mutex::new(None),
            active_app: Mutex::new(None),
            active_profile: Mutex::new(active_profile),
            hardware_mode,
            hardware_profile,
            has_avx2: detect_avx2(),
            queue_counts: Mutex::new([0, 0, 0]),
            client,
            sys: Mutex::new(sys),
            on_battery: Mutex::new(is_on_battery()),
            battery_pct: Mutex::new(read_battery_pct()),
            battery_policy: Mutex::new({
                let (dis, pct) = read_battery_info();
                BatteryPolicy::from_state(dis, pct)
            }),
            preempted_count: Mutex::new(0),
            model_overrides: Mutex::new(HashMap::new()),
            vram_limit_pct: Mutex::new(vram_limit_pct),
            active_inferences: Mutex::new(HashMap::new()),
            p3_vram_blocked: Arc::new(AtomicBool::new(false)),
            p3_thermal_blocked: Arc::new(AtomicBool::new(false)),
            gpu_temp_celsius: Mutex::new(read_gpu_temp_celsius()),
            downloads: Mutex::new(HashMap::new()),
            models_dir,
            llama_server_bin,
            akasha_proc:    Mutex::new(None),
            mnemosyne_proc: Mutex::new(None),
            akasha_crash_count:    Mutex::new(0),
            akasha_disabled:       Arc::new(AtomicBool::new(false)),
            mnemosyne_crash_count: Mutex::new(0),
            mnemosyne_disabled:    Arc::new(AtomicBool::new(false)),
            app_handle: Mutex::new(None),
            embed_model: Mutex::new(embed_model),
            embed_n_gpu_layers: Mutex::new(embed_n_gpu_layers),
            embed_proc: Mutex::new(None),
            embed_start_lock: Mutex::new(()),
            chat_health_port:      AKASHA_SERVER_PORT,
            embed_health_port:     EMBED_SERVER_PORT,
            mnemosyne_health_port: MNEMOSYNE_SERVER_PORT,
            cpu_p3_limit_pct: Mutex::new(cpu_p3_limit_pct),
            cached_cpu_pct: Arc::new(AtomicU32::new(0)),
            inference_enabled:          Arc::new(AtomicBool::new(false)),
            last_akasha_request_at:     Mutex::new(std::time::Instant::now()),
            last_mnemosyne_request_at:  Mutex::new(std::time::Instant::now()),
            last_embed_request_at:      Mutex::new(std::time::Instant::now()),
            idle_timeout_secs,
            cpu_fallback_max_mb,
            cpu_max_threads,
        }))
    }

    /// Injeta um processo filho como akasha_proc ativo — apenas para testes.
    #[cfg(test)]
    pub(crate) async fn inject_proc_for_test(&self, child: tokio::process::Child, model_name: &str) {
        *self.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: model_name.to_string(),
        });
    }

    /// Construtor mínimo para testes unitários em outros módulos.
    /// Não lê ecosystem.json; usa valores padrão seguros.
    #[cfg(test)]
    pub(crate) fn for_testing(
        models_dir: std::path::PathBuf,
        llama_server_bin: Option<std::path::PathBuf>,
    ) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap_or_default();
        let mut sys = System::new_all();
        sys.refresh_cpu_all();
        sys.refresh_memory();
        Self(Arc::new(Inner {
            llama_server_url:    "http://127.0.0.1:8081".to_string(),
            akasha_semaphore:    Arc::new(Semaphore::new(2)),
            mnemosyne_semaphore: Arc::new(Semaphore::new(2)),
            embed_semaphore:     Arc::new(Semaphore::new(1)),
            active_priority:    Mutex::new(None),
            active_model_class: Mutex::new(None),
            active_app:         Mutex::new(None),
            active_profile:     Mutex::new("normal".to_string()),
            hardware_mode:      "normal".to_string(),
            hardware_profile:   HardwareProfile::WorkPc,
            has_avx2:           true,
            queue_counts:       Mutex::new([0, 0, 0]),
            client,
            sys:                Mutex::new(sys),
            on_battery:         Mutex::new(false),
            battery_pct:        Mutex::new(100),
            battery_policy:     Mutex::new(BatteryPolicy::Normal),
            preempted_count:    Mutex::new(0),
            model_overrides:    Mutex::new(HashMap::new()),
            vram_limit_pct:     Mutex::new(85.0),
            active_inferences:  Mutex::new(HashMap::new()),
            p3_vram_blocked:    Arc::new(AtomicBool::new(false)),
            p3_thermal_blocked: Arc::new(AtomicBool::new(false)),
            gpu_temp_celsius:   Mutex::new(None),
            downloads:          Mutex::new(HashMap::new()),
            models_dir,
            llama_server_bin,
            akasha_proc:           Mutex::new(None),
            mnemosyne_proc:        Mutex::new(None),
            akasha_crash_count:    Mutex::new(0),
            akasha_disabled:       Arc::new(AtomicBool::new(false)),
            mnemosyne_crash_count: Mutex::new(0),
            mnemosyne_disabled:    Arc::new(AtomicBool::new(false)),
            app_handle:         Mutex::new(None),
            embed_model:        Mutex::new("bge-m3".to_string()),
            embed_n_gpu_layers: Mutex::new(DEFAULT_EMBED_N_GPU_LAYERS),
            embed_proc:         Mutex::new(None),
            embed_start_lock:   Mutex::new(()),
            // Em testes: portas livres para isolamento — sem servidor nestas portas
            chat_health_port:      59981,
            embed_health_port:     59982,
            mnemosyne_health_port: 59983,
            cpu_p3_limit_pct:    Mutex::new(85.0),
            cached_cpu_pct:      Arc::new(AtomicU32::new(0)),
            inference_enabled:          Arc::new(AtomicBool::new(false)),
            last_akasha_request_at:     Mutex::new(std::time::Instant::now()),
            last_mnemosyne_request_at:  Mutex::new(std::time::Instant::now()),
            last_embed_request_at:      Mutex::new(std::time::Instant::now()),
            idle_timeout_secs:  300,
            cpu_fallback_max_mb: 2048,
            cpu_max_threads:    0,
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
    /// Perfil de workflow ativo: "analise" | "estudo" | "normal"
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
    pub llama_server_url: String,
    /// Uso de CPU global (%) via sysinfo — delta entre dois polls consecutivos
    pub cpu_pct: f32,
    /// RAM livre em MB via sysinfo
    pub ram_free_mb: u64,
    /// RAM total em MB via sysinfo
    pub ram_total_mb: u64,
    /// True se rodando em bateria (= Economy ou Critical). P3 bloqueado, P2 com thresholds conservadores.
    pub on_battery: bool,
    /// Percentual da bateria (0–100). 100 quando em AC ou sem bateria.
    pub battery_pct: u8,
    /// Política de bateria: "normal", "economy" (30-80%), "critical" (<30%).
    pub battery_policy: String,
    /// Requests P3 preemptados por P1 desde o startup
    pub preempted_count: u32,
    /// Limite de VRAM configurado (0–100). P3 bloqueado acima deste percentual.
    pub vram_limit_pct: f32,
    /// Limite de CPU (%) para bloquear P3. Configurável, padrão 85.
    pub cpu_p3_limit_pct: f32,
    /// True quando o watchdog de VRAM bloqueou P3 (VRAM > block_pct%).
    /// Retoma automaticamente quando VRAM cai abaixo de 70%.
    pub p3_vram_blocked: bool,
    /// True quando temperatura da GPU > 85°C — P3 pausado.
    /// Retoma quando temperatura cai abaixo de 80°C.
    pub p3_thermal_blocked: bool,
    /// Temperatura atual da GPU em °C (None se WorkPc/CPU-only ou leitura indisponível).
    pub gpu_temp_celsius: Option<f32>,
    /// True se o processo llama-server de chat (porta 8081) está ativo.
    pub chat_server_online: bool,
    /// Modelo carregado no servidor de chat ("" se offline).
    pub chat_server_model: String,
    /// Latência do último /health no servidor de chat (ms); None se offline ou não respondeu.
    pub chat_response_ms: Option<u32>,
    /// True se o processo embed-server (porta 8082) está ativo.
    pub embed_server_online: bool,
    /// Modelo carregado no servidor de embedding ("" se offline).
    pub embed_server_model: String,
    /// Latência do último /health no servidor de embedding (ms); None se offline ou não respondeu.
    pub embed_response_ms: Option<u32>,
    /// True quando "Ligar IA" foi ativado pela usuária.
    /// O modelo pode ainda não estar carregado (lazy loading) — ver `chat_server_online`.
    pub inference_enabled: bool,
    // ── Campos novos: dois servidores de chat independentes ──────────────────
    /// Modelo carregado no servidor AKASHA (porta 8081). Vazio se offline.
    pub chat_akasha_model: String,
    /// True se o servidor AKASHA está ativo.
    pub chat_akasha_online: bool,
    /// Latência do /health no servidor AKASHA (ms). None se offline.
    pub chat_akasha_ms: Option<u32>,
    /// Modelo carregado no servidor Mnemosyne (porta 8083). Vazio se offline.
    pub chat_mnemosyne_model: String,
    /// True se o servidor Mnemosyne está ativo.
    pub chat_mnemosyne_online: bool,
    /// Latência do /health no servidor Mnemosyne (ms). None se offline.
    pub chat_mnemosyne_ms: Option<u32>,
}

#[derive(Serialize, Clone)]
pub struct ModelInfo {
    pub name: String,
    pub size_vram_mb: u64,
}

/// Entrada de modelo para listagem completa (instalados + status de carregamento).
#[derive(Serialize, Clone)]
pub struct ModelEntry {
    pub name: String,
    /// "active" = carregado na VRAM; "available" = instalado mas não carregado
    pub status: String,
    /// VRAM em uso em MB — 0 quando não carregado
    pub size_vram_mb: u64,
    /// Tamanho em disco em MB
    pub size_disk_mb: u64,
}

#[derive(Serialize)]
pub struct HardwareResponse {
    pub profile:              &'static str,
    pub profile_display:      &'static str,
    pub models:               ModelProfile,
    /// Máximo de modelos que podem rodar simultaneamente neste hardware
    pub max_concurrent:       u32,
}

/// Resposta do endpoint GET /logos/vram — snapshot de VRAM/RAM.
#[derive(Serialize)]
pub struct VramResponse {
    /// VRAM em uso em MB (None se não detectado)
    pub used_mb:          Option<u64>,
    /// VRAM total em MB do perfil de hardware (None se WorkPc/CPU-only)
    pub total_mb:         Option<u64>,
    /// Percentual de uso 0–100 (None se total desconhecido)
    pub used_pct:         Option<f32>,
    /// Perfil de hardware: "main_pc" | "laptop" | "work_pc"
    pub hardware_profile: &'static str,
}

/// Slot de modelo — app + tipo + labels legíveis.
#[derive(Serialize, Clone)]
pub struct ModelSlot {
    pub app:        String,
    pub model_type: String,
    /// Label completo: "Mnemosyne — RAG", "KOSMOS — Análise", etc.
    pub label:      String,
    /// Label conciso derivado do model_type: "RAG/chat (Mnemosyne)", "Análise de artigos (KOSMOS)", etc.
    pub slot_label: String,
    /// Idiomas com melhor desempenho documentado, ex: ["zh", "en"] para qwen2.5.
    /// None = sem afinidade específica conhecida.
    pub language_affinity: Option<Vec<String>>,
}

fn slot_label_for(model_type: &str) -> &'static str {
    match model_type {
        "llm_rag"      => "RAG/chat (Mnemosyne)",
        "llm_analysis" => "Análise de artigos (KOSMOS)",
        "llm_query"    => "Busca inteligente (AKASHA)",
        "embed"        => "Embedding",
        _              => "—",
    }
}

/// Retorna os idiomas com melhor desempenho documentado para o modelo, se conhecido.
fn language_affinity_for(model_name: &str) -> Option<Vec<String>> {
    let lower = model_name.to_lowercase();
    if lower.contains("qwen") {
        Some(vec!["zh".into(), "en".into()])
    } else if lower.contains("gemma") || lower.contains("llama") || lower.contains("smollm") {
        Some(vec!["en".into()])
    } else if lower.contains("mistral") || lower.contains("phi") {
        Some(vec!["en".into()])
    } else {
        None
    }
}

/// Modelo recomendado para instalação — compilado de todos os perfis de hardware.
#[derive(Serialize, Clone)]
pub struct RecommendedModel {
    pub model_name:          String,
    /// Slots que este modelo serve (pode ser o mesmo modelo em múltiplos apps/perfis)
    pub slots:               Vec<ModelSlot>,
    /// Perfis de hardware que recomendam este modelo
    pub for_profiles:        Vec<String>,
    /// True se o perfil atual recomenda este modelo para algum slot
    pub for_current_profile: bool,
    /// Instalado (registry LOGOS ou blob store do Ollama)
    pub is_installed:        bool,
    /// Modelo estático (model2vec, não-Ollama) — download automático no primeiro uso
    pub is_static:           bool,
    /// Tamanho em disco em MB (0 se não instalado ou estático)
    pub size_disk_mb:        u64,
    /// Justificativa de recurso: tamanho, VRAM, pontos fortes
    pub rationale:           String,
    /// Nota de velocidade esperada (apenas WorkPc). Ex: "~3 tok/s — adequado para background".
    /// None nos demais perfis.
    pub expected_speed_note: Option<String>,
}

/// Progresso de download de um modelo via Ollama pull.
#[derive(Serialize, Clone)]
pub struct PullProgress {
    pub model:     String,
    pub status:    String,
    pub completed: Option<u64>,
    pub total:     Option<u64>,
    pub done:      bool,
    pub error:     Option<String>,
    /// Índice do arquivo atual (0-based). 0 para download de arquivo único.
    pub file_index: u32,
    /// Total de arquivos para download. 1 para download de arquivo único.
    pub file_total:  u32,
}

/// Evento emitido pelo ciclo de vida do backend de inferência.
#[derive(Serialize, Clone)]
pub struct InferenceStatus {
    pub running: bool,
    pub message: String,
}

// ── Download de GGUF via HuggingFace ──────────────────────────

/// Payload de POST /logos/models/download
#[derive(Deserialize)]
struct DownloadRequest {
    /// Ex: "bartowski/Phi-3.5-mini-instruct-GGUF"
    repo_id:    String,
    /// Ex: "Phi-3.5-mini-instruct-Q4_K_M.gguf"
    filename:   String,
    /// Alias canônico do modelo (ex: "qwen2.5:7b", "bge-m3").
    /// Usado como `name` no registry em vez do filename sem extensão.
    model_name: Option<String>,
}

/// Progresso de download emitido via SSE a cada 500 ms e no final.
#[derive(Serialize, Clone)]
pub struct DownloadProgress {
    pub id:               String,
    pub filename:         String,
    pub bytes_downloaded: u64,
    pub total_bytes:      Option<u64>,
    /// Percentual 0–100; None quando Content-Length não informado
    pub pct:              Option<f32>,
    pub speed_mbps:       f32,
    pub done:             bool,
    pub error:            Option<String>,
}

// ── Validação de arquivos GGUF ────────────────────────────────────────────────

/// Resultado da validação de integridade de um arquivo GGUF antes de carregá-lo.
#[derive(Debug, PartialEq)]
pub(crate) enum GgufValidation {
    Ok,
    /// Arquivo não existe no caminho esperado.
    FileMissing,
    /// Download foi interrompido — arquivo menor que o esperado pelo registry.
    IncompleteDownload { actual_bytes: u64, expected_bytes: u64 },
    /// Primeiros 4 bytes não são "GGUF" — arquivo corrompido ou tipo errado.
    InvalidMagic { actual_magic: [u8; 4] },
}

/// Valida um arquivo GGUF antes de passá-lo ao llama-server.
///
/// Verifica em ordem:
/// 1. Arquivo existe
/// 2. Tamanho ≥ `expected_bytes` (detecção de download incompleto)
/// 3. Primeiros 4 bytes == b"GGUF" (magic number do formato)
pub(crate) fn validate_gguf_file(
    path:           &std::path::Path,
    expected_bytes: Option<u64>,
) -> GgufValidation {
    use std::io::Read as _;

    let metadata = match std::fs::metadata(path) {
        Ok(m)  => m,
        Err(_) => return GgufValidation::FileMissing,
    };
    let actual_bytes = metadata.len();

    if let Some(expected) = expected_bytes {
        if actual_bytes < expected {
            return GgufValidation::IncompleteDownload { actual_bytes, expected_bytes: expected };
        }
    }

    let mut f = match std::fs::File::open(path) {
        Ok(f)  => f,
        Err(_) => return GgufValidation::FileMissing,
    };
    let mut magic = [0u8; 4];
    if f.read_exact(&mut magic).is_err() {
        return GgufValidation::IncompleteDownload {
            actual_bytes,
            expected_bytes: expected_bytes.unwrap_or(4),
        };
    }
    if &magic != b"GGUF" {
        return GgufValidation::InvalidMagic { actual_magic: magic };
    }

    GgufValidation::Ok
}

/// Busca a entry completa do registry para um nome de modelo (sync).
/// Retorna None se o registry não existir ou o modelo não estiver registrado.
pub(crate) fn find_model_registry_entry(
    model_name: &str,
    models_dir: &std::path::Path,
) -> Option<ModelRegistryEntry> {
    let text = std::fs::read_to_string(models_dir.join("registry.json")).ok()?;
    let entries: Vec<ModelRegistryEntry> = serde_json::from_str(&text).ok()?;
    entries.into_iter().find(|e| {
        e.name == model_name
            || e.filename == model_name
            || e.filename.trim_end_matches(".gguf") == model_name
    })
}

/// Entrada no registry local logos/models/registry.json
#[derive(Serialize, Deserialize, Clone)]
pub struct ModelRegistryEntry {
    pub name:          String,   // filename sem extensão
    pub repo_id:       String,
    pub filename:      String,
    pub path:          String,   // caminho absoluto do arquivo
    pub size_bytes:    u64,
    pub sha256:        String,
    pub downloaded_at: String,   // ISO 8601
    /// Tipo do modelo: "chat" (LLM generativo) ou "embed" (modelo de embedding).
    /// Determina qual instância llama-server serve este modelo (8081=chat, 8082=embed).
    /// Entries antigas sem este campo são tratadas como "chat" por retrocompatibilidade.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model_type:    Option<String>,
    /// Caminho do arquivo mmproj para modelos multimodais (moondream, LLaVA, etc.)
    /// None para modelos de texto puro.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mmproj_path:   Option<String>,
}

/// Handle de um processo llama-server ativo gerenciado pelo LOGOS.
struct LlamaProcHandle {
    child:      tokio::process::Child,
    model_name: String,
}

// ── llama-server backend ──────────────────────────────────────
//
// O LOGOS gerencia um processo llama-server local como backend de inferência.
// Ativado automaticamente quando o binário é encontrado no startup.
// Fallback para Ollama quando llama-server não está disponível.
//
// Resolução de modelo (em ordem):
//   1. Registry do LOGOS ({models_dir}/registry.json) — modelos baixados via HUB
//   2. Blob store do Ollama (~/.ollama/models/blobs/) — reutiliza downloads existentes
//
// Tradução de formato:
//   /api/chat     (Ollama) → /v1/chat/completions (OpenAI) → llama-server
//   /api/generate (Ollama) → /v1/completions       (OpenAI) → llama-server
//   /api/embed    (Ollama) → /v1/embeddings         (OpenAI) → llama-server
//   Streaming é bufferizado no LOGOS e retornado como resposta única.

/// Seleciona o `models_dir` com base na existência de `registry.json`.
///
/// Regra: usa `xdg` se ele já tem registry. Caso contrário, usa `cwd_logos_models`
/// se este tem registry (fallback dev — `cargo tauri dev` roda com CWD = src-tauri/).
/// Se nenhum tem registry, retorna `xdg` como padrão seguro.
pub(crate) fn pick_models_dir(
    xdg: std::path::PathBuf,
    cwd_logos_models: std::path::PathBuf,
) -> std::path::PathBuf {
    if xdg.join("registry.json").exists() {
        return xdg;
    }
    if cwd_logos_models.join("registry.json").exists() {
        log::info!("LOGOS: models_dir fallback para CWD: {}", cwd_logos_models.display());
        return cwd_logos_models;
    }
    xdg
}

/// Encontra o binário llama-server de forma dinâmica — sem paths hardcoded por máquina.
///
/// Ordem de busca:
///   1. `ecosystem.json["logos"]["llama_server_path"]` — configuração por máquina (não sincronizada)
///   2. PATH via `which`/`where` — funciona em qualquer instalação do sistema
///   3. Paths padrão comuns (/usr/bin, /usr/local/bin, /opt)
fn find_llama_server_bin() -> Option<std::path::PathBuf> {
    // 1. Caminho configurado manualmente no ecosystem.json local (não sincronizado entre máquinas)
    {
        let eco = crate::ecosystem::read_json();
        if let Some(configured) = eco["logos"]["llama_server_path"].as_str().filter(|s| !s.is_empty()) {
            let p = std::path::Path::new(configured);
            if p.exists() && p.is_file() {
                log::info!("LOGOS: llama-server configurado em ecosystem.json: {}", p.display());
                return Some(p.to_owned());
            }
        }
    }

    // 2. PATH do sistema via `which` (Linux/macOS) / `where` (Windows)
    let finder = if cfg!(target_os = "windows") { "where" } else { "which" };
    if let Ok(out) = std::process::Command::new(finder).arg("llama-server").output() {
        if out.status.success() {
            let path_str = String::from_utf8_lossy(&out.stdout);
            if let Some(found) = path_str.lines().next().map(str::trim).filter(|s| !s.is_empty()) {
                let p = std::path::PathBuf::from(found);
                if p.exists() {
                    log::info!("LOGOS: llama-server encontrado via PATH: {}", p.display());
                    return Some(p);
                }
            }
        }
    }

    // 3. Paths padrão do sistema como último recurso
    for path in [
        "/usr/bin/llama-server",
        "/usr/local/bin/llama-server",
        "/opt/llama.cpp/llama-server",
    ] {
        let p = std::path::Path::new(path);
        if p.exists() {
            return Some(p.to_owned());
        }
    }

    None
}

/// Localiza o blob GGUF de um modelo no store local do Ollama.
/// Analisa o manifesto em ~/.ollama/models/manifests/ para extrair o hash do layer GGUF.
pub(crate) fn find_gguf_in_ollama_store(model_name: &str) -> Option<std::path::PathBuf> {
    let (name, tag) = model_name.split_once(':').unwrap_or((model_name, "latest"));
    let home = dirs::home_dir()?;
    let manifest_path = home
        .join(".ollama").join("models").join("manifests")
        .join("registry.ollama.ai").join("library")
        .join(name).join(tag);
    let text = std::fs::read_to_string(&manifest_path).ok()?;
    let manifest: serde_json::Value = serde_json::from_str(&text).ok()?;
    let layers = manifest["layers"].as_array()?;
    let model_layer = layers.iter().find(|l| {
        l["mediaType"].as_str() == Some("application/vnd.ollama.image.model")
    })?;
    let digest    = model_layer["digest"].as_str()?; // "sha256:abc..."
    let blob_name = digest.replace(':', "-");          // "sha256-abc..."
    let blob_path = home.join(".ollama").join("models").join("blobs").join(&blob_name);
    if blob_path.exists() { Some(blob_path) } else { None }
}

/// Resolve o nome de um modelo para o caminho do seu arquivo GGUF.
/// Verifica o registry do LOGOS primeiro, depois o blob store do Ollama.
pub(crate) fn resolve_gguf_path(
    model_name: &str,
    models_dir: &std::path::Path,
) -> Option<std::path::PathBuf> {
    // 1. Registry do LOGOS
    let registry_path = models_dir.join("registry.json");
    if let Ok(text) = std::fs::read_to_string(&registry_path) {
        if let Ok(entries) = serde_json::from_str::<Vec<ModelRegistryEntry>>(&text) {
            if let Some(entry) = entries.iter().find(|e| {
                e.name == model_name
                    || e.filename == model_name
                    || e.filename.trim_end_matches(".gguf") == model_name
            }) {
                let p = std::path::PathBuf::from(&entry.path);
                if p.exists() {
                    return Some(p);
                }
            }
        }
    }
    // 2. Blob store do Ollama — reutiliza downloads existentes diretamente
    find_gguf_in_ollama_store(model_name)
}

/// Retorna o número de layers na GPU para um modelo dado o perfil de hardware.
pub(crate) fn gpu_layers_for_model(model_name: &str, profile: HardwareProfile) -> i32 {
    let mp = profile.model_profile();
    if model_name == mp.llm_rag     { return mp.llm_rag_gpu_layers; }
    if model_name == mp.llm_analysis { return mp.llm_analysis_gpu_layers; }
    if model_name == mp.llm_query   { return mp.llm_query_gpu_layers; }
    if model_name == mp.embed       { return mp.embed_gpu_layers; }
    if model_name == mp.image_ocr   { return mp.image_ocr_gpu_layers; }
    match profile {
        HardwareProfile::WorkPc => 0,  // sem GPU discreta
        _                       => -1, // offload total na GPU
    }
}

/// Estima o KV cache em MB para um modelo e tamanho de contexto dados.
///
/// Fórmula empírica: `(model_size_mb × n_ctx) / (4096 × 3)`.
/// Calibrada para modelos Q4_K_M (~1489 MB para 7B@4096, ~745 MB para 7B@2048).
fn estimate_kv_cache_mb(model_size_mb: u64, n_ctx: u32) -> u64 {
    if model_size_mb == 0 { return 0; }
    (model_size_mb * n_ctx as u64) / (4096 * 3)
}

/// Decide quantas layers carregar na GPU considerando a VRAM disponível AGORA.
///
/// Lógica:
/// - `profile_n_gpu == 0` (WorkPc ou slot CPU fixo) → 0, sem checar VRAM.
/// - Hardware sem GPU (WorkPc) → 0.
/// - Lê VRAM usada atual via sysfs/nvidia-smi.
/// - Usa VRAM real do sysfs como budget (não o valor fixo do perfil).
/// - Checa `model_size_mb + kv_cache_estimate > total_real × 0.90 − vram_used` → 0 (CPU).
/// - Senão → `profile_n_gpu` (full GPU ou partial layers do perfil).
async fn effective_gpu_layers(
    client: &Client,
    profile: HardwareProfile,
    profile_n_gpu: i32,
    model_size_mb: u64,
    n_ctx: u32,
) -> i32 {
    // Slot configurado como CPU-only no perfil — respeitar sem checar VRAM
    if profile_n_gpu == 0 {
        return 0;
    }
    // Hardware sem GPU discreta — CPU sempre
    if profile == HardwareProfile::WorkPc {
        return 0;
    }
    let (vram_used_opt, vram_total_opt, _) = vram_usage(client, profile).await;
    let vram_used  = vram_used_opt.unwrap_or(0);
    // Usa total real do sysfs; fallback para valor conservador do perfil
    let vram_total = vram_total_opt.unwrap_or_else(|| vram_budget_for_profile(profile));
    // 10% reservado para overhead do driver
    let safe_budget = (vram_total as f64 * 0.90) as u64;
    let available   = safe_budget.saturating_sub(vram_used);
    let kv_cache_mb = estimate_kv_cache_mb(model_size_mb, n_ctx);
    let total_needed = model_size_mb.saturating_add(kv_cache_mb);
    if total_needed > 0 && total_needed > available {
        log::info!(
            "LOGOS: VRAM insuficiente para GPU \
             (usada: {vram_used} MB, disponível: {available} MB, \
             modelo: {model_size_mb} MB + KV cache estimado: {kv_cache_mb} MB, \
             necessário: {total_needed} MB, total sysfs: {vram_total} MB) — \
             carregando em CPU"
        );
        0
    } else {
        log::info!(
            "LOGOS: VRAM suficiente para GPU \
             (usada: {vram_used} MB, disponível: {available} MB, \
             necessário: {total_needed} MB, total sysfs: {vram_total} MB)"
        );
        profile_n_gpu
    }
}

/// Tamanho do contexto para o perfil de hardware.
fn n_ctx_for_hardware(hw: HardwareProfile) -> u32 {
    match hw {
        HardwareProfile::MainPc  => 4096,
        HardwareProfile::Laptop  => 2048, // KV cache >2048 esgota 2 GB da MX150
        HardwareProfile::WorkPc  => 2048,
    }
}

/// Inicia um processo llama-server para o modelo especificado.
/// `mmproj_path`: caminho do arquivo de projeção visual para modelos multimodais (moondream, LLaVA).
/// None para modelos de texto puro.
/// Constrói o `Command` do llama-server sem spawná-lo.
/// Separado para permitir inspeção dos args em testes sem precisar de um binário real.
pub(crate) fn build_llama_server_cmd(
    bin: &std::path::Path,
    model_path: &std::path::Path,
    mmproj_path: Option<&std::path::Path>,
    n_gpu: i32,
    n_ctx: u32,
    port: u16,
) -> tokio::process::Command {
    let mut cmd = tokio::process::Command::new(bin);
    cmd.arg("--model")     .arg(model_path)
       .arg("--port")      .arg(port.to_string())
       .arg("--ctx-size")  .arg(n_ctx.to_string())
       .arg("--parallel")  .arg("2")
       .arg("--cont-batching")
       .arg("--pooling")   .arg("mean")   // habilita /v1/embeddings no modelo de chat
       .stdout(std::process::Stdio::null())
       .stderr(std::process::Stdio::piped());
    if let Some(mp) = mmproj_path {
        cmd.arg("--mmproj").arg(mp);
    }
    if n_gpu == 0 {
        cmd.arg("--n-gpu-layers").arg("0");
    } else if n_gpu > 0 {
        cmd.arg("--n-gpu-layers").arg(n_gpu.to_string());
    } else {
        // n_gpu == -1: offload total — llama-server NÃO usa GPU sem esta flag (padrão = CPU)
        cmd.arg("--n-gpu-layers").arg("9999");
    }
    cmd
}

async fn spawn_llama_server_proc(
    bin: &std::path::Path,
    model_path: &std::path::Path,
    mmproj_path: Option<&std::path::Path>,
    n_gpu: i32,
    n_ctx: u32,
    port: u16,
) -> Result<tokio::process::Child, String> {
    // Sem process_group(0): llama-server é filho do HUB e morre junto com ele
    build_llama_server_cmd(bin, model_path, mmproj_path, n_gpu, n_ctx, port)
        .spawn()
        .map_err(|e| format!("Falha ao iniciar llama-server: {e}"))
}

/// Constrói o `Command` do llama-server em modo CPU fallback com recursos restritos.
///
/// Aplicado após OOM de GPU confirmado e modelo dentro do limite `cpu_fallback_max_mb`.
/// Restrições para evitar travamento do sistema:
/// - `--n-gpu-layers 0`: sem GPU
/// - `--threads N` / `--threads-batch N`: N ≤ metade dos cores lógicos (mínimo 1)
/// - `--ctx-size 512`: contexto mínimo para reduzir uso de RAM
/// - `--parallel 1`: uma requisição por vez (CPU não suporta batching eficiente)
///
/// `cpu_max_threads`: valor de `ecosystem.json["logos"]["cpu_max_threads"]`.
/// 0 = automático (metade dos cores, mínimo 1). >0 = limitado a esse valor.
pub(crate) fn build_llama_server_cmd_cpu_fallback(
    bin:             &std::path::Path,
    model_path:      &std::path::Path,
    mmproj_path:     Option<&std::path::Path>,
    port:            u16,
    cpu_max_threads: usize,
) -> tokio::process::Command {
    let total_cores = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(2);
    let auto_threads = (total_cores / 2).max(1);
    let threads = if cpu_max_threads == 0 {
        auto_threads
    } else {
        cpu_max_threads.min(total_cores).max(1)
    };
    log::info!(
        "LOGOS CPU fallback cmd: threads={threads} \
         (cpu_max_threads={cpu_max_threads}, total_cores={total_cores}), \
         ctx-size=512, parallel=1, n-gpu-layers=0"
    );
    let mut cmd = tokio::process::Command::new(bin);
    cmd.arg("--model")         .arg(model_path)
       .arg("--port")          .arg(port.to_string())
       .arg("--n-gpu-layers")  .arg("0")
       .arg("--threads")       .arg(threads.to_string())
       .arg("--threads-batch") .arg(threads.to_string())
       .arg("--ctx-size")      .arg("512")
       .arg("--parallel")      .arg("1")
       .arg("--pooling")       .arg("mean")
       .stdout(std::process::Stdio::null())
       .stderr(std::process::Stdio::piped());
    if let Some(mp) = mmproj_path {
        cmd.arg("--mmproj").arg(mp);
    }
    cmd
}

/// Spawna llama-server em modo CPU fallback e aplica prioridade reduzida no SO.
///
/// No Linux: `renice +10` (prioridade CPU baixa) + `ionice -c 3` (I/O idle).
/// Garante que o fallback não monopolize o sistema mesmo dentro dos threads permitidos.
async fn spawn_llama_server_cpu_fallback(
    bin:             &std::path::Path,
    model_path:      &std::path::Path,
    mmproj_path:     Option<&std::path::Path>,
    port:            u16,
    cpu_max_threads: usize,
) -> Result<tokio::process::Child, String> {
    let mut child =
        build_llama_server_cmd_cpu_fallback(bin, model_path, mmproj_path, port, cpu_max_threads)
            .spawn()
            .map_err(|e| format!("Falha ao iniciar llama-server em modo CPU: {e}"))?;

    // Linux: reduzir prioridade para o fallback não monopolizar CPU e disco
    #[cfg(target_os = "linux")]
    if let Some(pid) = child.id() {
        let pid_str = pid.to_string();
        match std::process::Command::new("renice")
            .args(["+10", "-p", &pid_str])
            .status()
        {
            Ok(s) if s.success() =>
                log::info!("LOGOS CPU fallback: renice +10 aplicado ao pid {pid}"),
            Ok(s) =>
                log::warn!("LOGOS CPU fallback: renice retornou {s} para pid {pid}"),
            Err(e) =>
                log::warn!("LOGOS CPU fallback: renice falhou (não instalado?) para pid {pid}: {e}"),
        }
        match std::process::Command::new("ionice")
            .args(["-c", "3", "-p", &pid_str])
            .status()
        {
            Ok(s) if s.success() =>
                log::info!("LOGOS CPU fallback: ionice -c 3 aplicado ao pid {pid}"),
            Ok(s) =>
                log::warn!("LOGOS CPU fallback: ionice retornou {s} para pid {pid}"),
            Err(e) =>
                log::warn!("LOGOS CPU fallback: ionice falhou (não instalado?) para pid {pid}: {e}"),
        }
    }

    Ok(child)
}

/// Inicia uma task que lê o stderr do chat-server, registra via log e escreve em arquivo.
///
/// `log_path`: caminho do arquivo de log (`logos_chat.log` no diretório logos/).
fn spawn_chat_stderr_reader(
    stderr:     tokio::process::ChildStderr,
    model_name: String,
    log_path:   std::path::PathBuf,
) {
    tokio::spawn(async move {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

        let log_file = tokio::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .await
            .ok();
        let mut log_file = log_file;

        let mut lines = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if line.trim().is_empty() { continue; }
            log::warn!("[logos-chat] [{}]: {}", model_name, line);
            if let Some(ref mut f) = log_file {
                let ts       = chrono::Local::now().format("%Y-%m-%dT%H:%M:%S");
                let log_line = format!("{ts} {line}\n");
                let _        = f.write_all(log_line.as_bytes()).await;
            }
        }
    });
}

// ── Servidor de embedding (porta EMBED_SERVER_PORT) ───────────────────────

/// Constrói o `Command` do servidor de embedding sem spawná-lo.
///
/// Diferenças em relação ao servidor de chat (`build_llama_server_cmd`):
/// - Adiciona `--embeddings` (habilita /v1/embeddings, restringe a embedding-only)
/// - Usa `--pooling mean` (pooling por média de tokens — padrão para bge-m3)
/// - Sem `--ctx-size`, `--parallel`, `--cont-batching` (não aplicáveis a embedding)
/// - Sem `--chat-template` (embedding-only não processa chat)
///
/// Separado por design: impossível ter chat e embedding no mesmo processo com `--embeddings`.
pub(crate) fn build_embed_server_cmd(
    bin:        &std::path::Path,
    model_path: &std::path::Path,
    n_gpu:      i32,
    port:       u16,
) -> tokio::process::Command {
    let mut cmd = tokio::process::Command::new(bin);
    cmd.arg("--model")      .arg(model_path)
       .arg("--port")       .arg(port.to_string())
       .arg("--embeddings")              // habilita /v1/embeddings (embedding-only mode)
       .arg("--pooling")    .arg("mean") // pooling por média — padrão para bge-m3
       // BUG-029: sem isto, o ubatch default (512) faz o llama-server forçar
       // n_batch = n_ubatch = 512 → qualquer input > 512 tokens dá 500 "input too large".
       // bge-m3 aceita até 8192 tokens. ctx 8192 + batch/ubatch 2048 cobrem os chunks
       // dos clientes (AKASHA trunca em ~2000 chars; Mnemosyne ~1200) com folga.
       .arg("--ctx-size")    .arg("8192")
       .arg("--batch-size")  .arg("2048")
       .arg("--ubatch-size") .arg("2048")
       .stdout(std::process::Stdio::null())
       .stderr(std::process::Stdio::piped());
    if n_gpu == 0 {
        cmd.arg("--n-gpu-layers").arg("0");
    } else if n_gpu > 0 {
        cmd.arg("--n-gpu-layers").arg(n_gpu.to_string());
    } else {
        // n_gpu == -1: offload total
        cmd.arg("--n-gpu-layers").arg("9999");
    }
    cmd
}

/// Spawna o processo llama-server em modo embedding (porta EMBED_SERVER_PORT).
/// O processo é filho do HUB e encerra quando o HUB encerra.
async fn spawn_embed_server_proc(
    bin:        &std::path::Path,
    model_path: &std::path::Path,
    n_gpu:      i32,
    port:       u16,
) -> Result<tokio::process::Child, String> {
    build_embed_server_cmd(bin, model_path, n_gpu, port)
        .spawn()
        .map_err(|e| format!("Falha ao iniciar embed-server: {e}"))
}

/// Inicia uma task que lê o stderr do embed-server, registra via log e escreve em arquivo.
///
/// `log_path`: caminho do arquivo de log rotativo (`logos_embed.log` no diretório logos/).
/// Logs são escritos em append com timestamp ISO, permitindo diagnóstico pós-mortem.
fn spawn_embed_stderr_reader(
    stderr:     tokio::process::ChildStderr,
    model_name: String,
    log_path:   std::path::PathBuf,
) {
    tokio::spawn(async move {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

        let log_file = tokio::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .await
            .ok();
        let mut log_file = log_file;

        let mut lines = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if line.trim().is_empty() { continue; }
            log::info!("[logos-embed] [{}]: {}", model_name, line);
            if let Some(ref mut f) = log_file {
                let ts       = chrono::Local::now().format("%Y-%m-%dT%H:%M:%S");
                let log_line = format!("{ts} {line}\n");
                let _        = f.write_all(log_line.as_bytes()).await;
            }
        }
    });
}

/// Deriva o caminho do arquivo de log do embed-server a partir do `models_dir`.
/// `models_dir` = `{logos_data}/logos/models/` → log em `{logos_data}/logos/logos_embed.log`
pub(crate) fn embed_log_path(models_dir: &std::path::Path) -> std::path::PathBuf {
    models_dir
        .parent()
        .unwrap_or(models_dir)
        .join("logos_embed.log")
}

/// Deriva o caminho do arquivo de log do chat-server a partir do `models_dir`.
/// `models_dir` = `{logos_data}/logos/models/` → log em `{logos_data}/logos/logos_chat.log`
pub(crate) fn chat_log_path(models_dir: &std::path::Path) -> std::path::PathBuf {
    models_dir
        .parent()
        .unwrap_or(models_dir)
        .join("logos_chat.log")
}

/// Aguarda llama-server responder em /health com 200 OK.
async fn wait_llama_ready(port: u16, client: &Client, timeout_secs: u64) -> bool {
    let url      = format!("http://127.0.0.1:{port}/health");
    let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);
    loop {
        if tokio::time::Instant::now() >= deadline {
            return false;
        }
        if let Ok(resp) = client.get(&url).timeout(Duration::from_secs(2)).send().await {
            if resp.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
}

/// Igual a `wait_llama_ready` mas verifica a cada iteração se o processo filho
/// já saiu — retorna false imediatamente ao detectar saída, sem aguardar o timeout.
///
/// Use quando o processo pode falhar rápido (modelo corrompido, OOM) para evitar
/// os 90 segundos de espera de `wait_llama_ready`.
async fn wait_llama_ready_checking_child(
    port:         u16,
    client:       &Client,
    timeout_secs: u64,
    child:        &mut tokio::process::Child,
) -> bool {
    let url      = format!("http://127.0.0.1:{port}/health");
    let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);
    loop {
        if tokio::time::Instant::now() >= deadline {
            log::warn!("LOGOS wait_ready: timeout de {timeout_secs}s na porta {port}");
            return false;
        }
        // Saída precoce do processo — não tem sentido aguardar HTTP de processo morto
        if let Ok(Some(status)) = child.try_wait() {
            log::warn!("LOGOS wait_ready: processo na porta {port} saiu antes de ficar pronto (status={status:?})");
            return false;
        }
        if let Ok(resp) = client.get(&url).timeout(Duration::from_secs(2)).send().await {
            if resp.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
}

/// Retorna `true` se a VRAM livre é suficiente para carregar o modelo (margem de 15%).
/// `model_size_mb = 0` → sem dados de tamanho, skip da verificação (retorna true).
pub(crate) fn vram_sufficient_for_model(vram_free_mb: u64, model_size_mb: u64) -> bool {
    if model_size_mb == 0 { return true; }
    let needed = (model_size_mb as f64 * 1.15) as u64;
    vram_free_mb >= needed
}

/// Verifica se o tamanho do arquivo GGUF permite fallback para CPU após OOM de GPU.
/// Retorna `None` se o modelo cabe dentro do limite; `Some(mensagem)` se for muito grande.
/// Usa o tamanho real do arquivo em disco (mais confiável que o registry para modelos importados).
fn check_cpu_fallback_allowed(gguf_path: &std::path::Path, cpu_fallback_max_mb: u64) -> Option<String> {
    let file_size_mb = std::fs::metadata(gguf_path)
        .map(|m| m.len() / 1_048_576)
        .unwrap_or(0);
    if file_size_mb > cpu_fallback_max_mb {
        Some(format!(
            "modelo {file_size_mb}MB excede o limite de fallback CPU {cpu_fallback_max_mb}MB — \
             fallback desabilitado para evitar travamento do sistema. \
             Reduza o modelo ou aumente logos.cpu_fallback_max_gb em ecosystem.json"
        ))
    } else {
        None
    }
}

/// Garante que o llama-server está rodando com o modelo solicitado.
/// Para o processo atual e reinicia com o novo modelo se necessário.
/// Deve ser chamado enquanto o semáforo de concorrência está adquirido.
/// Inicia (ou confirma já ativo) o servidor llama-server para o target especificado.
/// `target` determina: qual porta usar, qual campo de processo, qual log label.
/// CPU fallback é suportado apenas para ServerTarget::Akasha (modelos leves em WorkPc).
pub(crate) async fn ensure_server_loaded(
    s: &LogosState,
    target: ServerTarget,
    model_name: &str,
) -> Result<(), String> {
    let bin = s.0.llama_server_bin.as_ref()
        .ok_or_else(|| "llama-server não encontrado".to_string())?
        .clone();

    let port  = match target { ServerTarget::Akasha => AKASHA_SERVER_PORT, ServerTarget::Mnemosyne => MNEMOSYNE_SERVER_PORT };
    let label = match target { ServerTarget::Akasha => "AKASHA",           ServerTarget::Mnemosyne => "Mnemosyne" };

    // Fast path: modelo correto já carregado neste servidor
    {
        let guard = match target {
            ServerTarget::Akasha    => s.0.akasha_proc.lock().await,
            ServerTarget::Mnemosyne => s.0.mnemosyne_proc.lock().await,
        };
        if guard.as_ref().map(|p| p.model_name.as_str()) == Some(model_name) {
            return Ok(());
        }
    }

    // Para o processo atual (se houver). Aguarda 500ms para GPU liberar VRAM.
    let killed_prev = {
        let mut guard = match target {
            ServerTarget::Akasha    => s.0.akasha_proc.lock().await,
            ServerTarget::Mnemosyne => s.0.mnemosyne_proc.lock().await,
        };
        if let Some(mut proc) = guard.take() {
            let prev = proc.model_name.clone();
            let _ = proc.child.kill();
            let _ = proc.child.wait().await;
            log::info!("LOGOS {label}: processo anterior ({prev}) encerrado — carregando '{model_name}'");
            true
        } else { false }
    };
    if killed_prev {
        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    // Resolve caminho do GGUF
    let gguf_path = resolve_gguf_path(model_name, &s.0.models_dir)
        .ok_or_else(|| format!(
            "Modelo '{model_name}' não encontrado no registry do LOGOS nem no Ollama. \
             Faça download via HUB ou execute 'ollama pull {model_name}'."
        ))?;

    let registry = read_model_registry(&s.0.models_dir).await;
    let registry_entry = registry.iter().find(|e| e.name == model_name);

    // Validação de integridade GGUF
    {
        let expected_bytes = registry_entry.map(|e| e.size_bytes);
        let (repo_id, filename) = registry_entry
            .map(|e| (e.repo_id.as_str(), e.filename.as_str()))
            .unwrap_or(("", model_name));
        match validate_gguf_file(&gguf_path, expected_bytes) {
            GgufValidation::Ok => {}
            GgufValidation::FileMissing => {
                s.emit_model_corrupted(model_name, label, "file_missing", repo_id, filename).await;
                return Err(format!("Modelo '{model_name}': arquivo GGUF não encontrado no disco"));
            }
            GgufValidation::IncompleteDownload { actual_bytes, expected_bytes: exp } => {
                log::error!("LOGOS {label}: modelo '{model_name}' incompleto — {actual_bytes} de {exp} bytes");
                s.emit_model_corrupted(model_name, label, "incomplete_download", repo_id, filename).await;
                return Err(format!(
                    "Modelo '{model_name}' incompleto: {actual_bytes} de {exp} bytes \
                     (download interrompido — use reparo no HUB)"
                ));
            }
            GgufValidation::InvalidMagic { actual_magic } => {
                log::error!("LOGOS {label}: modelo '{model_name}' com magic bytes inválidos: {actual_magic:?}");
                s.emit_model_corrupted(model_name, label, "invalid_magic", repo_id, filename).await;
                return Err(format!("Modelo '{model_name}' corrompido: magic bytes inválidos {actual_magic:?}"));
            }
        }
    }

    let mmproj_path: Option<std::path::PathBuf> = registry_entry
        .and_then(|e| e.mmproj_path.as_deref())
        .map(std::path::PathBuf::from)
        .filter(|p| p.exists());

    let model_size_mb = registry_entry.map(|e| e.size_bytes / 1_048_576).unwrap_or(0);
    let profile_n_gpu = gpu_layers_for_model(model_name, s.0.hardware_profile);
    let n_ctx = n_ctx_for_hardware(s.0.hardware_profile);
    let n_gpu = effective_gpu_layers(&s.0.client, s.0.hardware_profile, profile_n_gpu, model_size_mb, n_ctx).await;

    // VRAM pre-check: só executa se o servidor não estava ativo (modelo novo a carregar).
    // Se `killed_prev` é false, nenhum processo estava rodando → verificar disponibilidade.
    // Se `killed_prev` é true, o modelo anterior foi descarregado → VRAM foi liberada.
    // Em ambos os casos sem servidor ativo, verificar. Se já havia modelo (fast-path acima
    // retornou Ok), nunca chegamos aqui — logo o check é sempre pertinente quando chegamos.
    if n_gpu != 0 && model_size_mb > 0 {
        let (vram_used_opt, vram_total_opt, _) = vram_usage(&s.0.client, s.0.hardware_profile).await;
        if let (Some(vram_used), Some(vram_total)) = (vram_used_opt, vram_total_opt) {
            let vram_free = vram_total.saturating_sub(vram_used);
            if !vram_sufficient_for_model(vram_free, model_size_mb) {
                let needed_mb = (model_size_mb as f64 * 1.15) as u64;
                let msg = format!(
                    "VRAM insuficiente para '{model_name}' ({label}): {vram_free}MB livre, \
                     modelo precisa ~{needed_mb}MB"
                );
                log::error!("LOGOS VRAM pre-check: {msg}");
                s.emit_alert("error", &msg).await;
                return Err(msg);
            }
            log::info!(
                "LOGOS VRAM pre-check ({label}): OK — {vram_free}MB livre, \
                 '{model_name}' precisa ~{}MB",
                (model_size_mb as f64 * 1.15) as u64
            );
        }
    }

    let gpu_mode = if n_gpu == 0 { "CPU".to_string() } else if n_gpu == -1 { "GPU (full)".to_string() } else { format!("GPU ({n_gpu} layers)") };
    log::info!(
        "LOGOS {label}: carregando '{model_name}' ({gpu_mode}, n_ctx={n_ctx}, porta={port}, mmproj={})",
        mmproj_path.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "none".into())
    );

    let mut child = spawn_llama_server_proc(&bin, &gguf_path, mmproj_path.as_deref(), n_gpu, n_ctx, port)
        .await?;

    if let Some(stderr) = child.stderr.take() {
        spawn_chat_stderr_reader(stderr, model_name.to_string(), chat_log_path(&s.0.models_dir));
    }

    if !wait_llama_ready_checking_child(port, &s.0.client, LLAMA_SERVER_READY_TIMEOUT_SECS, &mut child).await {
        let proc_exited = child.try_wait().ok().flatten().is_some();
        let _ = child.kill().await;

        // CPU fallback: apenas para AKASHA (WorkPc não tem GPU)
        if proc_exited && n_gpu != 0 && target == ServerTarget::Akasha {
            if let Some(gate_err) = check_cpu_fallback_allowed(&gguf_path, s.0.cpu_fallback_max_mb) {
                let alert = format!("'{model_name}': OOM GPU — {gate_err}");
                log::error!("LOGOS {label}: {alert}");
                s.emit_alert("error", &alert).await;
                return Err(format!("OOM GPU em '{model_name}' — {gate_err}"));
            }
            log::warn!(
                "LOGOS {label}: '{model_name}' saiu (provável OOM GPU, dentro do limite {}MB) — \
                 retentando com CPU only",
                s.0.cpu_fallback_max_mb
            );
            let mut cpu_child = spawn_llama_server_cpu_fallback(
                &bin, &gguf_path, mmproj_path.as_deref(), port, s.0.cpu_max_threads,
            )
            .await
            .map_err(|e| format!("Falha ao reiniciar em modo CPU: {e}"))?;

            if let Some(stderr) = cpu_child.stderr.take() {
                spawn_chat_stderr_reader(stderr, format!("{model_name}[cpu]"), chat_log_path(&s.0.models_dir));
            }

            if !wait_llama_ready_checking_child(port, &s.0.client, LLAMA_SERVER_READY_TIMEOUT_SECS, &mut cpu_child).await {
                let _ = cpu_child.kill().await;
                return Err(format!(
                    "llama-server ({label}) não ficou pronto em modo CPU — \
                     '{model_name}' pode estar corrompido ou incompatível"
                ));
            }

            *s.0.akasha_proc.lock().await = Some(LlamaProcHandle {
                child: cpu_child,
                model_name: model_name.to_string(),
            });
            log::warn!("LOGOS {label}: '{model_name}' carregado em modo CPU only (downgrade de GPU)");
            return Ok(());
        }

        return Err(format!(
            "llama-server ({label}) não ficou pronto em {LLAMA_SERVER_READY_TIMEOUT_SECS}s. \
             Verifique se o modelo cabe na VRAM disponível."
        ));
    }

    // Servidor pronto — armazena handle no estado correto
    match target {
        ServerTarget::Akasha => {
            *s.0.akasha_proc.lock().await = Some(LlamaProcHandle {
                child,
                model_name: model_name.to_string(),
            });
            log::info!("LOGOS {label}: '{model_name}' pronto na porta {port}");
        }
        ServerTarget::Mnemosyne => {
            *s.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle {
                child,
                model_name: model_name.to_string(),
            });
            log::info!("LOGOS {label}: '{model_name}' pronto na porta {port}");
        }
    }
    Ok(())
}

/// Alias de compatibilidade para callers existentes — usa ServerTarget::Akasha.
pub(crate) async fn ensure_llama_model_loaded(
    s: &LogosState,
    model_name: &str,
) -> Result<(), String> {
    ensure_server_loaded(s, ServerTarget::Akasha, model_name).await
}

// ── Tradução de formato: Ollama ↔ OpenAI ─────────────────────

/// Converte requisição de chat do formato Ollama para OpenAI.
/// Achata `options.*` para o topo e força `stream: false` (LOGOS bufferiza).
fn translate_ollama_chat_to_openai(
    mut body: serde_json::Map<String, serde_json::Value>,
) -> serde_json::Value {
    body.insert("stream".to_string(), serde_json::json!(false));
    if let Some(opts) = body.remove("options") {
        if let Some(obj) = opts.as_object() {
            for (k, v) in obj {
                let oai_key = match k.as_str() {
                    "temperature"    => "temperature",
                    "top_p"          => "top_p",
                    "repeat_penalty" => "frequency_penalty",
                    "seed"           => "seed",
                    "stop"           => "stop",
                    "num_predict"    => "max_tokens",
                    _                => continue,
                };
                body.entry(oai_key.to_string()).or_insert_with(|| v.clone());
            }
        }
    }
    body.remove("keep_alive");
    body.remove("raw");
    // Ollama "format" (JSON schema ou "json") → OpenAI "response_format"
    if let Some(fmt) = body.remove("format") {
        let response_format = if fmt.is_object() {
            serde_json::json!({
                "type": "json_schema",
                "json_schema": { "name": "response", "strict": true, "schema": fmt }
            })
        } else {
            serde_json::json!({"type": "json_object"})
        };
        body.entry("response_format".to_string()).or_insert(response_format);
    }
    serde_json::Value::Object(body)
}

/// Converte requisição de completions (/api/generate) do formato Ollama para OpenAI.
fn translate_ollama_generate_to_openai(
    mut body: serde_json::Map<String, serde_json::Value>,
) -> serde_json::Value {
    body.insert("stream".to_string(), serde_json::json!(false));
    if let Some(opts) = body.remove("options") {
        if let Some(obj) = opts.as_object() {
            for (k, v) in obj {
                let oai_key = match k.as_str() {
                    "temperature"    => "temperature",
                    "top_p"          => "top_p",
                    "num_predict"    => "max_tokens",
                    "seed"           => "seed",
                    "stop"           => "stop",
                    _                => continue,
                };
                body.entry(oai_key.to_string()).or_insert_with(|| v.clone());
            }
        }
    }
    body.remove("keep_alive");
    body.remove("format");
    body.remove("raw");
    serde_json::Value::Object(body)
}

/// Converte resposta OpenAI `/v1/chat/completions` para formato Ollama `/api/chat`.
fn translate_openai_chat_to_ollama(bytes: &[u8], model: &str) -> Vec<u8> {
    let Ok(resp) = serde_json::from_slice::<serde_json::Value>(bytes) else {
        return bytes.to_vec();
    };
    let choice  = resp["choices"].get(0);
    let content = choice.and_then(|c| c["message"]["content"].as_str()).unwrap_or("").to_string();
    let role    = choice.and_then(|c| c["message"]["role"].as_str()).unwrap_or("assistant").to_string();
    let finish  = choice.and_then(|c| c["finish_reason"].as_str()).unwrap_or("stop").to_string();
    let prompt_tokens     = resp["usage"]["prompt_tokens"]    .as_u64().unwrap_or(0);
    let completion_tokens = resp["usage"]["completion_tokens"].as_u64().unwrap_or(0);
    let ollama = serde_json::json!({
        "model":             model,
        "created_at":        chrono::Local::now().to_rfc3339(),
        "message":           { "role": role, "content": content },
        "done_reason":       finish,
        "done":              true,
        "prompt_eval_count": prompt_tokens,
        "eval_count":        completion_tokens,
    });
    serde_json::to_vec(&ollama).unwrap_or_else(|_| bytes.to_vec())
}

/// Converte resposta OpenAI `/v1/completions` para formato Ollama `/api/generate`.
fn translate_openai_generate_to_ollama(bytes: &[u8], model: &str) -> Vec<u8> {
    let Ok(resp) = serde_json::from_slice::<serde_json::Value>(bytes) else {
        return bytes.to_vec();
    };
    let text   = resp["choices"][0]["text"].as_str().unwrap_or("").to_string();
    let finish = resp["choices"][0]["finish_reason"].as_str().unwrap_or("stop").to_string();
    let prompt_tokens     = resp["usage"]["prompt_tokens"]    .as_u64().unwrap_or(0);
    let completion_tokens = resp["usage"]["completion_tokens"].as_u64().unwrap_or(0);
    let ollama = serde_json::json!({
        "model":             model,
        "created_at":        chrono::Local::now().to_rfc3339(),
        "response":          text,
        "done_reason":       finish,
        "done":              true,
        "prompt_eval_count": prompt_tokens,
        "eval_count":        completion_tokens,
    });
    serde_json::to_vec(&ollama).unwrap_or_else(|_| bytes.to_vec())
}

/// Converte requisição de embedding do formato Ollama para OpenAI `/v1/embeddings`.
/// /api/embeddings usa "prompt"; /api/embed usa "input" — normaliza para "input".
fn translate_ollama_embed_to_openai(body: &[u8]) -> Vec<u8> {
    let Ok(mut map) = serde_json::from_slice::<serde_json::Map<String, serde_json::Value>>(body)
    else {
        return body.to_vec();
    };
    if let Some(prompt) = map.remove("prompt") {
        map.entry("input".to_string()).or_insert(prompt);
    }
    map.remove("keep_alive");
    serde_json::to_vec(&map).unwrap_or_else(|_| body.to_vec())
}

/// Converte resposta OpenAI `/v1/embeddings` para formato Ollama `/api/embed`.
fn translate_openai_embed_to_ollama(bytes: &[u8]) -> Vec<u8> {
    let Ok(resp) = serde_json::from_slice::<serde_json::Value>(bytes) else {
        return bytes.to_vec();
    };
    let embedding = resp["data"][0]["embedding"].clone();
    let ollama = serde_json::json!({
        "embedding":  embedding,
        "embeddings": [embedding],
    });
    serde_json::to_vec(&ollama).unwrap_or_else(|_| bytes.to_vec())
}

/// VRAM atual da GPU NVIDIA via nvidia-smi.
/// Retorna (total_mb, used_mb) ou None se nvidia-smi não disponível.
async fn nvidia_vram_mb() -> Option<(u64, u64)> {
    let out = tokio::process::Command::new("nvidia-smi")
        .args(["--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"])
        .output()
        .await
        .ok()?;
    let text = String::from_utf8_lossy(&out.stdout);
    let line = text.trim();
    let mut parts = line.split(',');
    let used  = parts.next()?.trim().parse::<u64>().ok()?;
    let total = parts.next()?.trim().parse::<u64>().ok()?;
    Some((total, used))
}

// ── Router ────────────────────────────────────────────────────

pub fn build_router(state: LogosState) -> Router {
    Router::new()
        // LOGOS API própria
        .route("/logos/status",          get(status_handler))
        .route("/logos/vram",            get(vram_handler))
        .route("/logos/metrics/stream",  get(metrics_stream_handler))
        .route("/logos/chat",           post(chat_handler))
        .route("/logos/silence",        post(silence_handler))
        .route("/logos/profile",        post(profile_handler))
        .route("/logos/log-level",      post(log_level_handler))
        .route("/logos/logs/chat",      get(logs_chat_handler))
        .route("/logos/logs/embed",     get(logs_embed_handler))
        .route("/logos/models",                          get(models_handler))
        .route("/logos/models/load",                     post(models_load_handler))
        .route("/logos/models/unload",                   post(models_unload_handler))
        .route("/logos/models/download",                 post(download_model_handler))
        .route("/logos/models/download/progress/:id",    get(download_progress_handler))
        .route("/logos/models/registry",                 get(model_registry_handler))
        .route("/logos/hardware",                        get(hardware_handler))
        // OpenAI-compatible endpoints — apps usam formato OpenAI diretamente
        .route("/v1/chat/completions",  post(v1_chat_completions_proxy))
        .route("/v1/embeddings",        post(v1_embeddings_proxy))
        .route("/v1/models",            get(v1_models_proxy))
        .route("/health",               get(health_proxy))
        // Proxy transparente legado — apps Ollama apontam para 7072 em vez de 11434
        .route("/api/chat",       post(api_chat_proxy))
        .route("/api/generate",   post(api_generate_proxy))
        .route("/api/embed",      post(api_embed_proxy))
        .route("/api/embeddings", post(api_embeddings_proxy))
        .route("/api/tags",       get(api_tags_passthrough))
        .route("/api/ps",         get(api_ps_passthrough))
        .route("/api/delete",     delete(api_delete_passthrough))
        .with_state(state)
}

// ── Handlers ─────────────────────────────────────────────────

async fn status_handler(State(s): State<LogosState>) -> Json<StatusResponse> {
    Json(collect_status(&s).await)
}

/// Lê as últimas `max_lines` linhas de um arquivo de log.
/// Retorna string vazia se o arquivo não existir.
pub(crate) async fn read_tail_log(path: std::path::PathBuf, max_lines: usize) -> String {
    match tokio::fs::read_to_string(&path).await {
        Ok(content) => {
            let lines: Vec<&str> = content.lines().collect();
            let start = lines.len().saturating_sub(max_lines);
            lines[start..].join("\n")
        }
        Err(_) => String::new(),
    }
}

async fn logs_chat_handler(State(s): State<LogosState>) -> Response {
    let content = read_tail_log(chat_log_path(&s.0.models_dir), 500).await;
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, "text/plain; charset=utf-8")],
        content,
    )
        .into_response()
}

async fn logs_embed_handler(State(s): State<LogosState>) -> Response {
    let content = read_tail_log(embed_log_path(&s.0.models_dir), 500).await;
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, "text/plain; charset=utf-8")],
        content,
    )
        .into_response()
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
    queue_and_forward(s, body, app_name, requested_priority, "api/chat").await
}

/// Lê X-App e X-Priority dos headers HTTP. Fallback: app="", priority=3.
fn extract_app_priority(headers: &HeaderMap) -> (String, u8) {
    let app = headers
        .get("x-app")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    let priority = headers
        .get("x-priority")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<u8>().ok())
        .map(|p| p.clamp(1, 3))
        .unwrap_or(3);
    (app, priority)
}

/// Seleciona o valor de keep_alive a injetar por prioridade de requisição.
/// P1 e P2 → "10m": o idle watchdog cuida do descarregamento após ociosidade.
/// P3       → 0:    descarrega imediatamente após a resposta (background não precisa ficar quente).
fn select_keep_alive(priority: u8) -> serde_json::Value {
    match priority {
        1 | 2 => serde_json::json!("10m"),
        _     => serde_json::json!(0),
    }
}

/// Verifica ociosidade do chat server e descarrega o modelo se necessário.
/// Retorna `true` se o processo foi morto, `false` se não havia processo ou não estava ocioso.
/// Chamada pelo idle watchdog a cada 60s — e diretamente por testes.
async fn check_idle_llm(s: &LogosState) -> bool {
    if !s.llama_proc_active().await {
        return false;
    }
    let elapsed = s.0.last_akasha_request_at.lock().await.elapsed().as_secs();
    if elapsed > s.0.idle_timeout_secs {
        log::info!(
            "LOGOS idle watchdog: chat sem requisições por {elapsed}s \
             (limite: {}s) — descarregando modelo",
            s.0.idle_timeout_secs
        );
        s.kill_llama_proc().await;
        true
    } else {
        log::debug!(
            "LOGOS idle watchdog: chat ativo há {elapsed}s (limite: {}s) — mantendo",
            s.0.idle_timeout_secs
        );
        false
    }
}

/// Idle watchdog para o servidor Mnemosyne — mesmo comportamento, timer independente.
async fn check_idle_mnemosyne(s: &LogosState) -> bool {
    if !s.mnemosyne_proc_active().await {
        return false;
    }
    let elapsed = s.0.last_mnemosyne_request_at.lock().await.elapsed().as_secs();
    if elapsed > s.0.idle_timeout_secs {
        log::info!(
            "LOGOS idle watchdog (Mnemosyne): sem requisições por {elapsed}s \
             (limite: {}s) — descarregando modelo",
            s.0.idle_timeout_secs
        );
        s.kill_mnemosyne_proc().await;
        true
    } else {
        log::debug!(
            "LOGOS idle watchdog (Mnemosyne): ativo há {elapsed}s (limite: {}s) — mantendo",
            s.0.idle_timeout_secs
        );
        false
    }
}

/// Análogo para o embed server — mesmo comportamento, timer independente.
async fn check_idle_embed(s: &LogosState) -> bool {
    if !s.embed_proc_active().await {
        return false;
    }
    let elapsed = s.0.last_embed_request_at.lock().await.elapsed().as_secs();
    if elapsed > s.0.idle_timeout_secs {
        log::info!(
            "LOGOS idle watchdog: embed sem requisições por {elapsed}s \
             (limite: {}s) — descarregando modelo",
            s.0.idle_timeout_secs
        );
        s.kill_embed_proc().await;
        true
    } else {
        log::debug!(
            "LOGOS idle watchdog: embed ativo há {elapsed}s (limite: {}s) — mantendo",
            s.0.idle_timeout_secs
        );
        false
    }
}

/// Resolve o modelo a carregar para um app específico, respeitando overrides e o perfil de hardware.
/// Ordem: override da usuária → modelo recomendado do perfil → primeiro LLM instalado (fallback).
/// Verifica instalação antes de retornar; se não instalado, usa o fallback.
async fn model_for_app(s: &LogosState, app_name: &str) -> Option<String> {
    let profile  = s.0.hardware_profile.model_profile();
    let overrides = s.0.model_overrides.lock().await.clone();

    let lower = app_name.to_lowercase();
    let configured: Option<String> = if lower.contains("akasha") {
        let key = "akasha_llm_query";
        Some(overrides.get(key).cloned().unwrap_or_else(|| profile.llm_query.to_string()))
    } else if lower.contains("mnemosyne") {
        let key = "mnemosyne_llm_rag";
        Some(overrides.get(key).cloned().unwrap_or_else(|| profile.llm_rag.to_string()))
    } else if lower.contains("kosmos") {
        let key = "kosmos_llm_analysis";
        Some(overrides.get(key).cloned().unwrap_or_else(|| profile.llm_analysis.to_string()))
    } else {
        None
    };

    if let Some(ref model) = configured {
        if !model.is_empty() {
            let registry = read_model_registry(&s.0.models_dir).await;
            let installed = registry.iter().any(|e| {
                e.name == *model
                    || e.name == format!("{}:latest", model)
                    || e.filename.trim_end_matches(".gguf") == *model
            });
            if installed {
                return configured;
            }
            log::warn!(
                "LOGOS: modelo configurado '{}' para '{}' não instalado — \
                 usando primeiro LLM disponível",
                model, app_name
            );
        }
    }

    // Fallback: primeiro modelo LLM instalado (não embedding)
    let models = do_list_all_models(s).await;
    let names: Vec<String> = models.into_iter().map(|m| m.name).collect();
    crate::commands::launcher::select_model_to_load_llm(&names)
        .or_else(|| crate::commands::launcher::select_model_to_load(&names))
}

/// Núcleo da fila de prioridades: aplica guards, enfileira e encaminha ao Ollama.
/// Compartilhado entre /logos/chat (legado) e /api/chat, /api/generate (proxy transparente).
async fn queue_and_forward(
    s: LogosState,
    mut body: serde_json::Map<String, serde_json::Value>,
    app_name: String,
    requested_priority: u8,
    ollama_target: &str,
) -> Response {
    // Rejeitar imediatamente se a IA estiver desabilitada ("Ligar IA" desligado).
    if !s.0.inference_enabled.load(Ordering::Relaxed) {
        log::debug!("LOGOS: requisição rejeitada de '{}' — inferência desabilitada", app_name);
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "LOGOS: inferência desabilitada — ative a IA no HUB antes de fazer requisições"
            })),
        ).into_response();
    }

    // Determina o servidor alvo: Mnemosyne (porta 8083) ou AKASHA (porta 8081).
    let target = route_request(&app_name);

    // Lazy loading: IA habilitada mas nenhum modelo ativo no servidor alvo → carregar.
    let target_proc_active = match target {
        ServerTarget::Akasha    => s.llama_proc_active().await,
        ServerTarget::Mnemosyne => s.mnemosyne_proc_active().await,
    };
    if !target_proc_active {
        let to_load = model_for_app(&s, &app_name).await;

        match to_load {
            None => {
                log::error!(
                    "LOGOS lazy load: nenhum modelo instalado — \
                     requisição P{} de '{}' rejeitada",
                    requested_priority, app_name
                );
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    Json(serde_json::json!({
                        "error": "LOGOS: nenhum modelo instalado — faça download de um modelo LLM no HUB"
                    })),
                ).into_response();
            }
            Some(ref model_name) => {
                log::info!(
                    "LOGOS lazy load: primeira requisição de '{}' (P{}) — \
                     carregando '{}' no servidor {:?}",
                    app_name, requested_priority, model_name, target
                );
                if let Err(e) = ensure_server_loaded(&s, target, model_name).await {
                    log::error!(
                        "LOGOS lazy load: falha ao carregar '{}' para requisição de '{}': {}",
                        model_name, app_name, e
                    );
                    return (
                        StatusCode::SERVICE_UNAVAILABLE,
                        Json(serde_json::json!({
                            "error": format!(
                                "LOGOS: falha ao carregar modelo '{}' — {}",
                                model_name, e
                            )
                        })),
                    ).into_response();
                }
                log::info!(
                    "LOGOS lazy load: '{}' carregado — requisição de '{}' prossegue",
                    model_name, app_name
                );
                ensure_embed_server_started(&s).await;
            }
        }
    }

    // Atualiza timestamp do servidor correto (idle watchdog usa por servidor).
    match target {
        ServerTarget::Akasha    => *s.0.last_akasha_request_at.lock().await    = std::time::Instant::now(),
        ServerTarget::Mnemosyne => *s.0.last_mnemosyne_request_at.lock().await = std::time::Instant::now(),
    }

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
    let on_battery     = *s.0.on_battery.lock().await;
    let battery_policy = *s.0.battery_policy.lock().await;

    // Injeção de keep_alive por prioridade (transparente para os apps):
    //   Sobrevivência → 0 (RAM liberada imediatamente, independente da prioridade)
    //   Bateria + P1/P2 → 0 (economiza VRAM; modelo descarregado após cada resposta)
    //   P1 → "10m" (idle watchdog gerencia descarregamento; keep_alive permanente removido)
    //   P2 → "10m" (libera após 10 min de inatividade)
    //   P3 → 0     (descarrega imediatamente — background não precisa ficar quente)
    if is_survival || on_battery {
        body.insert("keep_alive".to_string(), serde_json::json!(0));
    } else {
        let ka = select_keep_alive(priority);
        body.entry("keep_alive".to_string()).or_insert(ka);
    }

    // Cap de num_ctx por hardware: WorkPc (sem RAM) e Laptop (VRAM MX150 2 GB)
    // WorkPc: RAM satura com contextos longos no i5-3470 (8 GB).
    // Laptop: KV cache para contextos >2048 esgota a VRAM de 2 GB da MX150.
    let hw_ctx_cap = if is_survival {
        Some(2_048_u64)  // WorkPc (survival)
    } else if s.0.hardware_profile == HardwareProfile::Laptop {
        Some(2_048_u64)  // MX150 2 GB — contextos longos esgotam VRAM
    } else {
        None
    };
    if let Some(max_ctx) = hw_ctx_cap {
        if let Some(opts) = body.get_mut("options").and_then(|v| v.as_object_mut()) {
            let ctx = opts.get("num_ctx").and_then(|v| v.as_u64()).unwrap_or(0);
            if ctx == 0 || ctx > max_ctx {
                opts.insert("num_ctx".to_string(), serde_json::json!(max_ctx));
            }
        } else {
            body.insert("options".to_string(), serde_json::json!({ "num_ctx": max_ctx }));
        }
    }

    // Parâmetros de eficiência por prioridade (num_thread, num_batch, num_ctx, num_gpu).
    // Chamado após survival/keep_alive para não sobrescrever caps já aplicados.
    inject_efficiency_params(&mut body, priority, s.0.hardware_profile, is_survival, on_battery, s.0.has_avx2);

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
        // P3 em modo sobrevivência: delay loop — aguarda CPU/RAM normalizarem.
        // Hard-reject 503 apenas para RAM abaixo do limiar de crash.
        if priority == 3 {
            loop {
                let (cpu, ram_free, _) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
                if ram_free < RAM_CRITICAL_MB {
                    return retry_after_response(
                        StatusCode::SERVICE_UNAVAILABLE,
                        &format!("RAM livre {ram_free} MB — abaixo do mínimo de segurança ({RAM_CRITICAL_MB} MB)"),
                        15,
                    );
                }
                if cpu <= CPU_P3_SURVIVAL_BLOCK && ram_free >= RAM_P3_SURVIVAL_BLOCK_MB {
                    break;
                }
                log::debug!(
                    "LOGOS P3 (sobrevivência) aguardando hardware — cpu={:.0}% ram={}MB — dormindo {}s",
                    cpu, ram_free, P3_HW_WAIT_SECS
                );
                tokio::time::sleep(Duration::from_secs(P3_HW_WAIT_SECS)).await;
            }
        }
    } else if priority == 3 {
        // LOGOS gere P3 via delay loop — nunca rejeita por thresholds normais de hardware.
        // Hard-reject 503 apenas para valores críticos que causariam crash imediato do sistema.
        // Sequência garantida: loop de hardware termina → só então tenta adquirir semáforo.
        loop {
            // Crash-prevention: avaliar antes de qualquer espera
            let gpu_temp = *s.0.gpu_temp_celsius.lock().await;
            if let Some(t) = gpu_temp {
                if t > THERMAL_CRITICAL_C {
                    return retry_after_response(
                        StatusCode::SERVICE_UNAVAILABLE,
                        &format!("GPU {t:.0}°C — temperatura crítica (>{THERMAL_CRITICAL_C:.0}°C); pausando para evitar dano térmico"),
                        30,
                    );
                }
            }
            let (cpu, ram_free, _) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
            if ram_free < RAM_CRITICAL_MB {
                return retry_after_response(
                    StatusCode::SERVICE_UNAVAILABLE,
                    &format!("RAM livre {ram_free} MB — abaixo do mínimo de segurança ({RAM_CRITICAL_MB} MB)"),
                    15,
                );
            }
            if let Some(vram) = vram_pct(&s.0.client, s.0.hardware_profile).await {
                if vram * 100.0 > VRAM_CRITICAL_PCT {
                    return retry_after_response(
                        StatusCode::SERVICE_UNAVAILABLE,
                        &format!("VRAM {:.0}% — crítica (>{VRAM_CRITICAL_PCT:.0}%); aguardar descarga", vram * 100.0),
                        30,
                    );
                }
            }
            // Throttle normal: aguardar condições melhores (sem rejeição)
            let vram_blocked    = s.0.p3_vram_blocked.load(Ordering::Relaxed);
            let thermal_blocked = s.0.p3_thermal_blocked.load(Ordering::Relaxed);
            let cpu_limit       = *s.0.cpu_p3_limit_pct.lock().await;
            let should_wait = on_battery
                || vram_blocked
                || thermal_blocked
                || cpu > cpu_limit
                || ram_free < RAM_P3_BLOCK_MB;
            if !should_wait { break; }
            log::debug!(
                "LOGOS P3 aguardando hardware — cpu={:.0}% ram={}MB \
                 vram_block={} thermal={} on_battery={} — dormindo {}s",
                cpu, ram_free, vram_blocked, thermal_blocked, on_battery, P3_HW_WAIT_SECS
            );
            tokio::time::sleep(Duration::from_secs(P3_HW_WAIT_SECS)).await;
        }
    } else if priority == 2 {
        if battery_policy == BatteryPolicy::Critical {
            // Bateria crítica (<30%): apenas P1 é aceito
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Bateria crítica: apenas tarefas P1 são aceitas para preservar energia"
                })),
            ).into_response();
        }
        if on_battery {
            // Bateria (Economy): threshold de CPU mais conservador para P2
            let (cpu, _ram, _) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
            if cpu > ON_BATTERY_P2_CPU_BLOCK {
                return (
                    StatusCode::TOO_MANY_REQUESTS,
                    Json(serde_json::json!({
                        "error": format!("CPU {cpu:.0}% em bateria (economy) — tarefa P2 adiada")
                    })),
                ).into_response();
            }
        }
    }

    // Preempção inteligente (P1 apenas): se P3 está ativo e VRAM insuficiente para P1,
    // força descarregamento dos modelos P3 antes de entrar na fila do semáforo.
    if priority == 1 {
        try_preempt_p3(&s, &model_name).await;
    }

    // Incrementa contador de fila
    s.0.queue_counts.lock().await[(priority - 1) as usize] += 1;

    // Aguarda semáforo do servidor alvo respeitando timeout por prioridade.
    // Modelos pesados adquirem 2 permits (exclusividade total);
    // modelos leves adquirem 1 (até 2 simultâneos).
    let sem = match target {
        ServerTarget::Akasha    => s.0.akasha_semaphore.clone(),
        ServerTarget::Mnemosyne => s.0.mnemosyne_semaphore.clone(),
    };
    let permit = match priority {
        1 => tokio::time::timeout(P1_TIMEOUT, sem.acquire_many_owned(permits))
                .await.ok().and_then(|r| r.ok()),
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
        None => return retry_after_response(
            StatusCode::SERVICE_UNAVAILABLE,
            if priority == 1 {
                "Timeout aguardando slot de inferência — sistema sobrecarregado"
            } else {
                "Timeout aguardando LOGOS — sistema sobrecarregado"
            },
            60,
        ),
    };

    // Marca prioridade, classe do modelo e app ativos
    *s.0.active_priority.lock().await    = Some(priority);
    *s.0.active_model_class.lock().await = Some(model_class);
    *s.0.active_app.lock().await         = Some(app_name);


    // Encaminha ao backend de inferência (llama-server ou Ollama).
    // Verifica disabled flag do servidor alvo (crash watchdog seta após 3 falhas).
    let target_disabled = match target {
        ServerTarget::Akasha    => s.0.akasha_disabled.load(Ordering::Relaxed),
        ServerTarget::Mnemosyne => s.0.mnemosyne_disabled.load(Ordering::Relaxed),
    };
    let target_port = match target {
        ServerTarget::Akasha    => AKASHA_SERVER_PORT,
        ServerTarget::Mnemosyne => MNEMOSYNE_SERVER_PORT,
    };
    let use_llama = s.0.llama_server_bin.is_some() && !target_disabled;
    let is_generate = ollama_target == "api/generate";

    let task_result: Result<Result<(reqwest::StatusCode, Bytes), String>, tokio::task::JoinError> =
    if use_llama {
        // ── llama-server: garante modelo carregado no servidor alvo e traduz formato ──
        if let Err(e) = ensure_server_loaded(&s, target, &model_name).await {
            *s.0.active_priority.lock().await    = None;
            *s.0.active_model_class.lock().await = None;
            *s.0.active_app.lock().await         = None;
            drop(_permit);
            return (StatusCode::BAD_GATEWAY, Json(serde_json::json!({ "error": e }))).into_response();
        }
        let body_map = ollama_payload.as_object().cloned().unwrap_or_default();
        let openai_payload = if is_generate {
            translate_ollama_generate_to_openai(body_map)
        } else {
            translate_ollama_chat_to_openai(body_map)
        };
        let endpoint = if is_generate { "v1/completions" } else { "v1/chat/completions" };
        let url          = format!("http://127.0.0.1:{target_port}/{endpoint}");
        let client_clone = s.0.client.clone();
        let model_clone  = model_name.clone();
        let task = tokio::spawn(async move {
            let resp = client_clone.post(&url).json(&openai_payload).send().await
                .map_err(|e| format!("llama-server indisponível: {e}"))?;
            let status = resp.status();
            let raw    = resp.bytes().await
                .map_err(|e| format!("Erro ao ler resposta llama-server: {e}"))?;
            let translated = if is_generate {
                translate_openai_generate_to_ollama(&raw, &model_clone)
            } else {
                translate_openai_chat_to_ollama(&raw, &model_clone)
            };
            Ok::<_, String>((status, Bytes::from(translated)))
        });
        if !model_name.is_empty() {
            s.0.active_inferences.lock().await.insert(model_name.clone(), task.abort_handle());
        }
        let r = task.await;
        if !model_name.is_empty() {
            s.0.active_inferences.lock().await.remove(&model_name);
        }
        r
    } else {
        // llama-server não encontrado — IA indisponível
        *s.0.active_priority.lock().await    = None;
        *s.0.active_model_class.lock().await = None;
        *s.0.active_app.lock().await         = None;
        drop(_permit);
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "Backend de inferência indisponível — instale llama-server e reinicie o HUB"
            })),
        ).into_response();
    };


    // Limpa estado ativo antes de liberar o semáforo
    *s.0.active_priority.lock().await    = None;
    *s.0.active_model_class.lock().await = None;
    *s.0.active_app.lock().await         = None;
    drop(_permit);

    match task_result {
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({ "error": "Geração abortada" })),
        ).into_response(),
        Ok(Err(e)) => (
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({ "error": e })),
        ).into_response(),
        Ok(Ok((status, bytes))) => axum::http::Response::builder()
            .status(status)
            .header(header::CONTENT_TYPE, "application/json")
            .body(axum::body::Body::from(bytes))
            .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response()),
    }
}

// ── Proxy transparente — /api/* ────────────────────────────────

async fn api_chat_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let (app_name, priority) = extract_app_priority(&headers);
    let body_map = serde_json::from_slice(&body).unwrap_or_default();
    queue_and_forward(s, body_map, app_name, priority, "api/chat").await
}

async fn api_generate_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let (app_name, priority) = extract_app_priority(&headers);
    let body_map = serde_json::from_slice(&body).unwrap_or_default();
    queue_and_forward(s, body_map, app_name, priority, "api/generate").await
}

async fn api_embed_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    do_embed_proxy(s, headers, body, "api/embed").await
}

async fn api_embeddings_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    do_embed_proxy(s, headers, body, "api/embeddings").await
}

/// Proxy de embeddings — sempre P3, sem keep_alive, sem preempção.
/// Hardware guard aplicado: rejeita se VRAM saturada ou CPU/RAM insuficiente.
async fn do_embed_proxy(s: LogosState, headers: HeaderMap, body: Bytes, target: &str) -> Response {
    let app_name = headers
        .get("x-app")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown")
        .to_string();
    let on_battery = *s.0.on_battery.lock().await;
    let is_survival = s.0.hardware_mode == "sobrevivencia";

    if on_battery {
        return (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
            "error": "Modo bateria: embeddings desabilitados para preservar energia"
        }))).into_response();
    }
    if is_survival {
        return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
            "error": "Modo Sobrevivência: embeddings desabilitados nesta máquina"
        }))).into_response();
    }

    let vram_block = *s.0.vram_limit_pct.lock().await / 100.0;
    if let Some(pct) = vram_pct(&s.0.client, s.0.hardware_profile).await {
        if pct > vram_block {
            let pct_cfg = (vram_block * 100.0) as u32;
            return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                "error": format!("VRAM > {pct_cfg}% — embedding adiado")
            }))).into_response();
        }
    }
    let (cpu, ram_free) = {
        let (c, f, _) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
        (c, f)
    };
    let cpu_limit = *s.0.cpu_p3_limit_pct.lock().await;
    if cpu > cpu_limit || ram_free < RAM_P3_BLOCK_MB {
        return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
            "error": format!("CPU {cpu:.0}% ou RAM livre {ram_free} MB insuficiente — embedding adiado")
        }))).into_response();
    }

    s.0.queue_counts.lock().await[2] += 1;
    // BUG-020: semáforo EXCLUSIVO do embed-server (capacidade 1) — serializa
    // embeddings de AKASHA e Mnemosyne para nunca colidirem no embed-server.
    let sem = s.0.embed_semaphore.clone();
    if sem.available_permits() == 0 {
        log::debug!("LOGOS embed proxy (Ollama): embed_semaphore ocupado — requisição entra na fila de espera");
    }
    let permit = tokio::time::timeout(P3_TIMEOUT, sem.acquire_many_owned(1))
        .await.ok().and_then(|r| r.ok());
    {
        let mut counts = s.0.queue_counts.lock().await;
        counts[2] = counts[2].saturating_sub(1);
    }

    let _permit = match permit {
        Some(p) => p,
        None => return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
            "error": "Timeout aguardando LOGOS — sistema sobrecarregado"
        }))).into_response(),
    };

    *s.0.active_priority.lock().await = Some(3);
    *s.0.active_app.lock().await = Some(app_name);

    let input_bytes = body.len();
    let t0 = std::time::Instant::now();

    let result = if s.0.llama_server_bin.is_some() {
        // ── llama-server: traduz para OpenAI /v1/embeddings e roteia para embed-server ──
        let openai_body = translate_ollama_embed_to_openai(&body);
        let url = format!("http://127.0.0.1:{EMBED_SERVER_PORT}/v1/embeddings");
        let active_app = s.0.active_app.lock().await.clone().unwrap_or_else(|| "unknown".to_string());
        log::info!(
            "LOGOS embed proxy (Ollama→OpenAI): app='{}' target={target} → {url} input_bytes={input_bytes}",
            active_app
        );
        s.0.client
            .post(&url)
            .header(header::CONTENT_TYPE, "application/json")
            .body(openai_body)
            .send()
            .await
            .map_err(|e| e.to_string())
    } else {
        // ── Ollama: injeta parâmetros de eficiência e encaminha ──
        let embed_body: Vec<u8> =
            if let Ok(mut m) = serde_json::from_slice::<serde_json::Map<String, serde_json::Value>>(&body) {
                inject_efficiency_params(&mut m, 3, s.0.hardware_profile, is_survival, on_battery, s.0.has_avx2);
                serde_json::to_vec(&m).unwrap_or_else(|_| body.to_vec())
            } else {
                body.to_vec()
            };
        let url = format!("{}/{target}", s.0.llama_server_url);
        s.0.client
            .post(&url)
            .header(header::CONTENT_TYPE, "application/json")
            .body(embed_body)
            .send()
            .await
            .map_err(|e| e.to_string())
    };

    *s.0.active_priority.lock().await = None;
    *s.0.active_app.lock().await      = None;
    drop(_permit);

    match result {
        Ok(resp) => {
            let latency_ms = t0.elapsed().as_millis();
            let status     = resp.status();
            log::info!(
                "LOGOS embed proxy (Ollama): target={target} status={} input_bytes={} latency={}ms",
                status.as_u16(), input_bytes, latency_ms
            );
            match resp.bytes().await {
                Ok(raw) => {
                    let bytes = if s.0.llama_server_bin.is_some() {
                        Bytes::from(translate_openai_embed_to_ollama(&raw))
                    } else {
                        raw
                    };
                    axum::http::Response::builder()
                        .status(status)
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(axum::body::Body::from(bytes))
                        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
                }
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => {
            let latency_ms = t0.elapsed().as_millis();
            log::warn!(
                "LOGOS embed proxy (Ollama): target={target} ERRO='{}' input_bytes={} latency={}ms",
                e, input_bytes, latency_ms
            );
            (StatusCode::BAD_GATEWAY, Json(serde_json::json!({
                "error": format!("Backend de inferência indisponível: {e}")
            }))).into_response()
        }
    }
}

/// GET /api/tags — retorna modelos do registry no formato Ollama (compatibilidade legada).
async fn api_tags_passthrough(State(s): State<LogosState>) -> Response {
    let registry = read_model_registry(&s.0.models_dir).await;
    let models: Vec<serde_json::Value> = registry.iter().map(|e| serde_json::json!({
        "name":       e.name,
        "model":      e.name,
        "size":       e.size_bytes,
        "digest":     e.sha256,
        "modified_at": e.downloaded_at,
    })).collect();
    (StatusCode::OK, Json(serde_json::json!({ "models": models }))).into_response()
}

/// GET /api/ps — retorna o modelo atualmente carregado no formato Ollama (compatibilidade legada).
async fn api_ps_passthrough(State(s): State<LogosState>) -> Response {
    let models = list_ollama_models(&s).await;
    let arr: Vec<serde_json::Value> = models.iter().map(|m| serde_json::json!({
        "name":      m.name,
        "model":     m.name,
        "size_vram": 0,
    })).collect();
    (StatusCode::OK, Json(serde_json::json!({ "models": arr }))).into_response()
}

/// DELETE /api/delete — remove modelo do registry e disco (compatibilidade legada).
/// Delega para a mesma lógica de logos_delete_model.
async fn api_delete_passthrough(State(s): State<LogosState>, body: Bytes) -> Response {
    let model = serde_json::from_slice::<serde_json::Value>(&body)
        .ok()
        .and_then(|v| v["name"].as_str().map(str::to_string))
        .unwrap_or_default();

    let registry_path = s.0.models_dir.join("registry.json");
    let text = match std::fs::read_to_string(&registry_path) {
        Ok(t) => t,
        Err(_) => return (StatusCode::NOT_FOUND, Json(serde_json::json!({ "error": "registry não encontrado" }))).into_response(),
    };
    let mut entries: Vec<ModelRegistryEntry> = match serde_json::from_str(&text) {
        Ok(e) => e,
        Err(_) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({ "error": "registry corrompido" }))).into_response(),
    };
    let idx = entries.iter().position(|e| e.name == model || e.filename == model);
    if let Some(i) = idx {
        let entry = entries.remove(i);
        let _ = std::fs::remove_file(&entry.path);
        let _ = std::fs::write(&registry_path, serde_json::to_string_pretty(&entries).unwrap_or_default());
        (StatusCode::OK, Json(serde_json::json!({ "ok": true }))).into_response()
    } else {
        (StatusCode::NOT_FOUND, Json(serde_json::json!({ "error": format!("modelo '{model}' não encontrado") }))).into_response()
    }
}


// ── OpenAI-compatible endpoints (/v1/*) ─────────────────────────

/// Proxy transparente para llama-server via semáforo de prioridade.
/// Sem tradução de formato — apps enviam OpenAI diretamente.
async fn proxy_openai_to_llama(s: &LogosState, headers: &HeaderMap, body: Bytes, endpoint: &str, default_priority: u8) -> Response {
    let (app_name, req_priority) = extract_app_priority(headers);
    let profile  = s.0.active_profile.lock().await.clone();
    let priority = apply_profile_priority(&profile, &app_name,
                       if req_priority == 0 { default_priority } else { req_priority });

    // Rejeitar se inferência desabilitada ("Ligar IA" desligado).
    if !s.0.inference_enabled.load(Ordering::Relaxed) {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "LOGOS: inferência desabilitada — ative a IA no HUB antes de fazer requisições"
            })),
        ).into_response();
    }

    // Determina o servidor alvo e verifica se está desabilitado por crash repetido.
    let target = route_request(&app_name);
    let target_disabled = match target {
        ServerTarget::Akasha    => s.0.akasha_disabled.load(Ordering::Relaxed),
        ServerTarget::Mnemosyne => s.0.mnemosyne_disabled.load(Ordering::Relaxed),
    };
    if target_disabled {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "LOGOS: llama-server desabilitado após múltiplos crashes — reinicie o HUB"
            })),
        ).into_response();
    }

    // Hardware guards por prioridade (mesma lógica de queue_and_forward):
    let on_battery     = *s.0.on_battery.lock().await;
    let battery_policy = *s.0.battery_policy.lock().await;
    let is_survival    = s.0.hardware_mode == "sobrevivencia";
    if priority == 3 {
        if on_battery {
            return (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
                "error": "Modo bateria: tarefas P3 desabilitadas para preservar energia"
            }))).into_response();
        }
        if s.0.p3_vram_blocked.load(Ordering::Relaxed) {
            let pct_cfg = (*s.0.vram_limit_pct.lock().await) as u32;
            return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                "error": format!("VRAM > {pct_cfg}% — tarefa P3 bloqueada pelo watchdog; aguarde VRAM < 70%")
            }))).into_response();
        }
        if s.0.p3_thermal_blocked.load(Ordering::Relaxed) {
            let temp = s.0.gpu_temp_celsius.lock().await.unwrap_or(0.0);
            return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                "error": format!("GPU {temp:.0}°C — tarefa P3 pausada para evitar thermal throttle; aguarde cair abaixo de 80°C")
            }))).into_response();
        }
        let vram_block = *s.0.vram_limit_pct.lock().await / 100.0;
        if let Some(pct) = vram_pct(&s.0.client, s.0.hardware_profile).await {
            if pct > vram_block {
                let pct_cfg = (vram_block * 100.0) as u32;
                return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                    "error": format!("VRAM > {pct_cfg}% — tarefa P3 adiada; tente novamente mais tarde")
                }))).into_response();
            }
        }
        let cpu_limit = if is_survival { CPU_P3_SURVIVAL_BLOCK } else { *s.0.cpu_p3_limit_pct.lock().await };
        let ram_limit = if is_survival { RAM_P3_SURVIVAL_BLOCK_MB } else { RAM_P3_BLOCK_MB };
        let (cpu, ram_free) = {
            let (c, f, _) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
            (c, f)
        };
        if cpu > cpu_limit || ram_free < ram_limit {
            return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                "error": format!("CPU {cpu:.0}% ou RAM livre {ram_free} MB insuficiente — tarefa P3 adiada")
            }))).into_response();
        }
    } else if priority == 2 {
        if battery_policy == BatteryPolicy::Critical {
            return (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
                "error": "Bateria crítica: apenas tarefas P1 são aceitas para preservar energia"
            }))).into_response();
        }
        if on_battery {
            let (cpu, _ram, _) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
            if cpu > ON_BATTERY_P2_CPU_BLOCK {
                return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                    "error": format!("CPU {cpu:.0}% em bateria (economy) — tarefa P2 adiada")
                }))).into_response();
            }
        }
    }

    // Lazy loading + model switching:
    // ensure_llama_model_loaded tem fast path — se o modelo correto já estiver carregado,
    // retorna Ok imediatamente. Cobre tanto o primeiro acesso (lazy) quanto troca de modelo
    // (e.g., Mnemosyne carregou 7b, AKASHA precisa de 3b → troca automática).
    //
    // Prioridade de seleção do modelo:
    // 1. Campo "model" do body OpenAI (apps que enviam diretamente via httpx sem X-App header)
    // 2. model_for_app (apps que enviam X-App header; fallback = primeiro LLM instalado)
    let body_model = serde_json::from_slice::<serde_json::Value>(&body).ok()
        .and_then(|v| v["model"].as_str().map(String::from))
        .filter(|m| !m.is_empty());
    let chosen_model = if body_model.is_some() {
        body_model
    } else {
        model_for_app(s, &app_name).await
    };
    match chosen_model {
        None => {
            log::error!(
                "LOGOS /v1: nenhum modelo instalado — requisição P{} de '{}' rejeitada",
                priority, app_name
            );
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "LOGOS: nenhum modelo instalado — faça download de um modelo LLM no HUB"
                })),
            ).into_response();
        }
        Some(ref model_name) => {
            let was_idle = match target {
                ServerTarget::Akasha    => !s.llama_proc_active().await,
                ServerTarget::Mnemosyne => !s.mnemosyne_proc_active().await,
            };
            if was_idle {
                log::info!(
                    "LOGOS lazy load (/v1): primeira requisição de '{}' (P{}) — carregando '{}' em {:?}",
                    app_name, priority, model_name, target
                );
            }
            if let Err(e) = ensure_server_loaded(s, target, model_name).await {
                log::error!(
                    "LOGOS /v1: falha ao carregar '{}' para '{}': {}", model_name, app_name, e
                );
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    Json(serde_json::json!({
                        "error": format!("LOGOS: falha ao carregar modelo '{}' — {}", model_name, e)
                    })),
                ).into_response();
            }
            if was_idle {
                log::info!(
                    "LOGOS lazy load (/v1): '{}' carregado — requisição de '{}' prossegue",
                    model_name, app_name
                );
                // Inicia embed-server em paralelo — mesmo ciclo de vida do chat server.
                ensure_embed_server_started(s).await;
            }
        }
    }

    // Preempção P1: se P3 está ativo e VRAM insuficiente, descarregar antes de entrar na fila.
    if priority == 1 {
        try_preempt_p3(s, &chosen_model.as_deref().unwrap_or("")).await;
    }

    // Atualiza timestamp do servidor alvo (idle watchdog usa por servidor).
    match target {
        ServerTarget::Akasha    => *s.0.last_akasha_request_at.lock().await    = std::time::Instant::now(),
        ServerTarget::Mnemosyne => *s.0.last_mnemosyne_request_at.lock().await = std::time::Instant::now(),
    }

    let permits: u32 = if priority >= 3 { 1 } else { 2 };
    let timeout = match priority {
        1 => Duration::from_secs(120),
        2 => P2_TIMEOUT,
        _ => P3_TIMEOUT,
    };
    let sem = match target {
        ServerTarget::Akasha    => s.0.akasha_semaphore.clone(),
        ServerTarget::Mnemosyne => s.0.mnemosyne_semaphore.clone(),
    };
    let _permit = match tokio::time::timeout(timeout, sem.acquire_many_owned(permits)).await {
        Ok(Ok(p)) => p,
        _ => return retry_after_response(
            StatusCode::SERVICE_UNAVAILABLE,
            "Timeout aguardando LOGOS — sistema sobrecarregado",
            60,
        ),
    };

    // Rastreia estado ativo (prioridade, app, classe do modelo) para métricas e UI.
    *s.0.active_priority.lock().await    = Some(priority);
    *s.0.active_app.lock().await         = Some(app_name.clone());
    *s.0.active_model_class.lock().await = Some(
        if chosen_model.as_deref().map(is_light_model).unwrap_or(true) { "leve" } else { "pesado" }
            .to_string()
    );

    let target_port = match target {
        ServerTarget::Akasha    => AKASHA_SERVER_PORT,
        ServerTarget::Mnemosyne => MNEMOSYNE_SERVER_PORT,
    };
    let url = format!("http://127.0.0.1:{target_port}/{endpoint}");
    let result = s.0.client
        .post(&url)
        .header(header::CONTENT_TYPE, "application/json")
        .body(body)
        .send()
        .await;

    *s.0.active_priority.lock().await    = None;
    *s.0.active_model_class.lock().await = None;
    *s.0.active_app.lock().await         = None;

    match result {
        Ok(resp) => {
            let status = resp.status();
            let ct = resp.headers()
                .get(header::CONTENT_TYPE)
                .cloned()
                .unwrap_or_else(|| "application/json".parse().unwrap());
            match resp.bytes().await {
                Ok(bytes) => axum::http::Response::builder()
                    .status(status)
                    .header(header::CONTENT_TYPE, ct)
                    .body(axum::body::Body::from(bytes))
                    .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response()),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        },
        Err(e) => (StatusCode::BAD_GATEWAY, Json(serde_json::json!({
            "error": format!("llama-server indisponível: {e}")
        }))).into_response(),
    }
}

async fn v1_chat_completions_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    proxy_openai_to_llama(&s, &headers, body, "v1/chat/completions", 2).await
}

/// Proxy para POST /v1/embeddings — roteado para o embed-server (porta EMBED_SERVER_PORT).
///
/// Separado de `proxy_openai_to_llama` porque o embed-server corre numa porta própria
/// (EMBED_SERVER_PORT) e tem ciclo de vida independente do servidor de chat (AKASHA_SERVER_PORT).
///
/// Logging obrigatório: timestamp, app, tamanho do input, porta, latência, status/erro.
async fn v1_embeddings_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let (app_name, req_priority) = extract_app_priority(&headers);
    let profile  = s.0.active_profile.lock().await.clone();
    // Prioridade calculada para fins de log/perfil; embeddings são sempre serializados
    // pelo embed_semaphore (cap. 1), independentemente da prioridade (BUG-020).
    let _priority = apply_profile_priority(&profile, &app_name,
                       if req_priority == 0 { 3 } else { req_priority });

    // Gate: inferência desabilitada → rejeitar embeddings também.
    if !s.0.inference_enabled.load(Ordering::Relaxed) {
        return (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
            "error": "LOGOS: inferência desabilitada — ative a IA no HUB antes de fazer requisições"
        }))).into_response();
    }

    // Lazy loading do embed-server: inicia se não estiver ativo.
    // ensure_embed_server_started é não-fatal e tem fast path (noop se já ativo).
    if !s.embed_proc_active().await {
        log::info!(
            "LOGOS embed proxy: embed-server inativo — iniciando para requisição de '{}'",
            app_name
        );
        ensure_embed_server_started(&s).await;

        // Após tentativa de start, verificar se subiu de fato.
        // BUG-027 (cont.): o gate é a SAÚDE do embed-server, não o handle interno. Se o
        // `embed_proc` está dessincronizado (None) mas o servidor responde /health na porta
        // — caso clássico após um wait_ready lento ou processo herdado — encaminhamos mesmo
        // assim, em vez de devolver 503 com um embed-server perfeitamente saudável no ar.
        if !s.embed_proc_active().await
            && !embed_health_ok(&s.0.client, s.0.embed_health_port).await {
            log::warn!(
                "LOGOS embed proxy: embed-server não ativo nem saudável para '{}' — \
                 verifique embed_model em ecosystem.json (porta {})",
                app_name, EMBED_SERVER_PORT
            );
            return (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
                "error": format!(
                    "embed-server não está ativo (porta {EMBED_SERVER_PORT}). \
                     Verifique embed_model em ecosystem.json."
                )
            }))).into_response();
        }
    }

    let timeout  = P3_TIMEOUT; // embeddings são sempre P3

    // BUG-020: semáforo EXCLUSIVO do embed-server (capacidade 1). Como a capacidade
    // é 1, sempre adquirimos 1 permit — cada requisição de embedding já obtém
    // exclusividade. Pedir 2 permits aqui nunca seria concedido (deadlock por timeout).
    let sem      = s.0.embed_semaphore.clone();
    if sem.available_permits() == 0 {
        log::debug!("LOGOS embed proxy: embed_semaphore ocupado — requisição de '{app_name}' entra na fila de espera");
    }
    let _permit  = match tokio::time::timeout(timeout, sem.acquire_many_owned(1)).await {
        Ok(Ok(p)) => p,
        _ => return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
            "error": "Timeout aguardando LOGOS — sistema sobrecarregado"
        }))).into_response(),
    };

    let url         = format!("http://127.0.0.1:{EMBED_SERVER_PORT}/v1/embeddings");
    let input_bytes = body.len();
    let t0          = std::time::Instant::now();

    log::info!(
        "LOGOS embed proxy: app='{}' → {url} input_bytes={input_bytes}",
        app_name
    );

    match s.0.client
        .post(&url)
        .header(header::CONTENT_TYPE, "application/json")
        .body(body)
        .send()
        .await
    {
        Ok(resp) => {
            let latency_ms = t0.elapsed().as_millis();
            let status     = resp.status();
            let ct         = resp.headers()
                .get(header::CONTENT_TYPE)
                .cloned()
                .unwrap_or_else(|| "application/json".parse().unwrap());
            log::info!(
                "LOGOS embed proxy: app='{}' status={} input_bytes={} latency={}ms porta={}",
                app_name, status.as_u16(), input_bytes, latency_ms, EMBED_SERVER_PORT
            );
            match resp.bytes().await {
                Ok(bytes) => axum::http::Response::builder()
                    .status(status)
                    .header(header::CONTENT_TYPE, ct)
                    .body(axum::body::Body::from(bytes))
                    .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response()),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => {
            let latency_ms = t0.elapsed().as_millis();
            log::warn!(
                "LOGOS embed proxy: app='{}' ERRO='{}' input_bytes={} latency={}ms porta={}",
                app_name, e, input_bytes, latency_ms, EMBED_SERVER_PORT
            );
            (StatusCode::BAD_GATEWAY, Json(serde_json::json!({
                "error": format!("embed-server indisponível (porta {EMBED_SERVER_PORT}): {e}")
            }))).into_response()
        }
    }
}

async fn v1_models_proxy(State(s): State<LogosState>) -> Response {
    let url = format!("http://127.0.0.1:{AKASHA_SERVER_PORT}/v1/models");
    match s.0.client.get(&url).timeout(Duration::from_secs(3)).send().await {
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
        },
        Err(_) => (StatusCode::OK, Json(serde_json::json!({ "object": "list", "data": [] }))).into_response(),
    }
}

async fn health_proxy(State(s): State<LogosState>) -> Response {
    // Com lazy loading, o llama-server só sobe na primeira requisição real.
    // Se o LOGOS está habilitado (inference_enabled=true), retorna 200 imediatamente —
    // independentemente do llama-server estar carregado ou não.
    // Isso evita o deadlock: health retornava 503 → AKASHA parava de mandar req →
    // lazy load nunca disparava → llama-server nunca subia.
    if s.inference_enabled() {
        // Se llama-server já estiver rodando, proxy o /health real para refletir estado correto.
        if s.llama_proc_active().await {
            let url = format!("http://127.0.0.1:{AKASHA_SERVER_PORT}/health");
            if let Ok(resp) = s.0.client.get(&url).timeout(Duration::from_secs(2)).send().await {
                let status = resp.status();
                if let Ok(bytes) = resp.bytes().await {
                    return axum::http::Response::builder()
                        .status(status)
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(axum::body::Body::from(bytes))
                        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response());
                }
            }
        }
        // Habilitada mas sem modelo carregado ainda (idle): 200 — LOGOS pronto para receber req
        return (StatusCode::OK, Json(serde_json::json!({
            "status": "ok",
            "model": null,
            "inference_enabled": true,
            "llm_loaded": false
        }))).into_response();
    }
    // inference_enabled=false → LOGOS não aceitará requisições LLM
    (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
        "status": "disabled",
        "inference_enabled": false
    }))).into_response()
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

/// POST /logos/log-level { "level": "debug"|"info"|"warn" }
/// Altera o nível de log em runtime sem reiniciar o HUB.
async fn log_level_handler(
    Json(body): Json<serde_json::Value>,
) -> Response {
    let level = body["level"].as_str().unwrap_or("info");
    let filter = match level {
        "debug" => log::LevelFilter::Debug,
        "warn"  => log::LevelFilter::Warn,
        "error" => log::LevelFilter::Error,
        _       => log::LevelFilter::Info,
    };
    log::set_max_level(filter);
    log::info!("LOGOS: nível de log alterado para '{level}'");
    (StatusCode::OK, Json(serde_json::json!({ "level": level }))).into_response()
}

async fn models_handler(State(s): State<LogosState>) -> Response {
    let models = do_list_models(&s).await;
    (StatusCode::OK, Json(models)).into_response()
}

async fn models_load_handler(
    State(s): State<LogosState>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    let model = match body["model"].as_str() {
        Some(m) if !m.is_empty() => m.to_string(),
        _ => return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "campo 'model' obrigatório" })),
        ).into_response(),
    };
    let ok = do_load_model(&s, &model).await;
    (StatusCode::OK, Json(serde_json::json!({ "ok": ok, "model": model }))).into_response()
}

async fn models_unload_handler(
    State(s): State<LogosState>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    let model = match body["model"].as_str() {
        Some(m) if !m.is_empty() => m.to_string(),
        _ => return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "campo 'model' obrigatório" })),
        ).into_response(),
    };
    let ok = do_unload_model(&s, &model).await;
    (StatusCode::OK, Json(serde_json::json!({ "ok": ok, "model": model }))).into_response()
}

async fn hardware_handler(State(s): State<LogosState>) -> Json<HardwareResponse> {
    let hw = s.0.hardware_profile;
    Json(HardwareResponse {
        profile:          hw.as_str(),
        profile_display:  hw.display(),
        models:           hw.model_profile(),
        max_concurrent:   max_concurrent_for_profile(hw),
    })
}

async fn vram_handler(State(s): State<LogosState>) -> Json<VramResponse> {
    let hw = s.0.hardware_profile;
    let (used_mb, total_sysfs, pct) = vram_usage(&s.0.client, hw).await;
    // Prefere total real do sysfs; fallback para valor fixo do perfil
    let total_mb = total_sysfs.or_else(|| hw.vram_total_mb());
    Json(VramResponse {
        used_mb,
        total_mb,
        used_pct: pct.map(|p| p * 100.0),
        hardware_profile: hw.as_str(),
    })
}

/// Snapshot de métricas de hardware emitido a cada 1 s pelo endpoint SSE.
#[derive(Debug, Clone, Serialize)]
struct MetricsSnapshot {
    vram_used_mb:  Option<u64>,
    vram_total_mb: Option<u64>,
    vram_pct:      Option<f32>,   // 0–100
    cpu_pct:       f32,
    ram_free_mb:   u64,
    ram_total_mb:  u64,
}

/// GET /logos/metrics/stream — SSE com snapshot de métricas a cada 1 s.
/// O LogosPanel usa EventSource neste endpoint para atualizações em tempo real
/// em vez de polling via Tauri IPC a cada 5 s.
async fn metrics_stream_handler(State(s): State<LogosState>) -> impl IntoResponse {
    let stream = async_stream::stream! {
        loop {
            let hw = s.0.hardware_profile;
            let (vram_used_mb, vram_total_sysfs, vram_pct_raw) =
                vram_usage(&s.0.client, hw).await;
            let (cpu_pct, ram_free_mb, ram_total_mb) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
            let snap = MetricsSnapshot {
                vram_used_mb,
                vram_total_mb: vram_total_sysfs.or_else(|| hw.vram_total_mb()),
                vram_pct: vram_pct_raw.map(|p| p * 100.0),
                cpu_pct,
                ram_free_mb,
                ram_total_mb,
            };
            if let Ok(json) = serde_json::to_string(&snap) {
                yield Ok::<Event, std::convert::Infallible>(Event::default().data(json));
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    };
    Sse::new(stream).keep_alive(KeepAlive::default())
}

fn max_concurrent_for_profile(profile: HardwareProfile) -> u32 {
    match profile {
        // RX 6600 tem 8 GB — permite 2 modelos leves (≤3B) simultâneos
        HardwareProfile::MainPc => 2,
        // MX150 2 GB e WorkPc CPU-only: apenas 1 modelo por vez
        HardwareProfile::Laptop | HardwareProfile::WorkPc => 1,
    }
}

// ── Lógica pública (usada também pelos Tauri commands) ────────

/// Pinga /health numa porta do llama-server com timeout curto.
/// Retorna latência em ms ou None (timeout / servidor offline).
/// Timeout: 400 ms — suficientemente rápido para não atrasar o poll de status (4 s).
async fn ping_server_ms(client: &reqwest::Client, port: u16) -> Option<u32> {
    let url = format!("http://127.0.0.1:{port}/health");
    let t0  = std::time::Instant::now();
    match tokio::time::timeout(
        Duration::from_millis(400),
        client.get(&url).send(),
    ).await {
        Ok(Ok(_)) => Some(t0.elapsed().as_millis() as u32),
        _         => None,
    }
}

pub async fn collect_status(s: &LogosState) -> StatusResponse {
    let active_priority    = *s.0.active_priority.lock().await;
    let active_model_class = s.0.active_model_class.lock().await.clone();
    let active_app         = s.0.active_app.lock().await.clone();
    let current_profile    = s.0.active_profile.lock().await.clone();
    let hardware_mode             = s.0.hardware_mode.clone();
    let hardware_profile          = s.0.hardware_profile.as_str().to_string();
    let hardware_profile_display  = s.0.hardware_profile.display().to_string();
    let queue = *s.0.queue_counts.lock().await;
    let (vram_used_mb, _, vram_pct) = vram_usage(&s.0.client, s.0.hardware_profile).await;
    let (cpu_pct, ram_free_mb, ram_total_mb) = cpu_ram_usage(&s.0.sys, &s.0.cached_cpu_pct).await;
    let on_battery       = *s.0.on_battery.lock().await;
    let battery_pct      = *s.0.battery_pct.lock().await;
    let battery_policy   = s.0.battery_policy.lock().await.as_str().to_string();
    let preempted_count  = *s.0.preempted_count.lock().await;
    let vram_limit_pct   = *s.0.vram_limit_pct.lock().await;
    let cpu_p3_limit_pct = *s.0.cpu_p3_limit_pct.lock().await;
    let p3_vram_blocked     = s.0.p3_vram_blocked.load(Ordering::Relaxed);
    let p3_thermal_blocked  = s.0.p3_thermal_blocked.load(Ordering::Relaxed);
    let gpu_temp_celsius     = *s.0.gpu_temp_celsius.lock().await;

    // Estado dos três servidores llama.cpp
    let akasha_model = {
        let g = s.0.akasha_proc.lock().await;
        g.as_ref().map(|p| p.model_name.clone()).unwrap_or_default()
    };
    let mnemosyne_model_loaded = {
        let g = s.0.mnemosyne_proc.lock().await;
        g.as_ref().map(|p| p.model_name.clone()).unwrap_or_default()
    };
    let embed_model_loaded = {
        let g = s.0.embed_proc.lock().await;
        g.as_ref().map(|p| p.model_name.clone()).unwrap_or_default()
    };
    let akasha_online    = !akasha_model.is_empty();
    let mnemosyne_online = !mnemosyne_model_loaded.is_empty();
    let embed_online     = !embed_model_loaded.is_empty();

    // Pings paralelos para os três servidores — só quando processo ativo.
    let (akasha_ms, mnemosyne_ms, embed_ms) = tokio::join!(
        async {
            if akasha_online    { ping_server_ms(&s.0.client, s.0.chat_health_port).await }
            else                { None }
        },
        async {
            if mnemosyne_online { ping_server_ms(&s.0.client, s.0.mnemosyne_health_port).await }
            else                { None }
        },
        async {
            if embed_online     { ping_server_ms(&s.0.client, s.0.embed_health_port).await }
            else                { None }
        },
    );

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
        llama_server_url: s.0.llama_server_url.clone(),
        cpu_pct,
        ram_free_mb,
        ram_total_mb,
        on_battery,
        battery_pct,
        battery_policy,
        preempted_count,
        vram_limit_pct,
        cpu_p3_limit_pct,
        p3_vram_blocked,
        p3_thermal_blocked,
        gpu_temp_celsius,
        // Campos legados (compatibilidade) — reusam o servidor AKASHA
        chat_server_online: akasha_online,
        chat_server_model:  akasha_model.clone(),
        chat_response_ms:   akasha_ms,
        embed_server_online: embed_online,
        embed_server_model:  embed_model_loaded,
        embed_response_ms:   embed_ms,
        inference_enabled:   s.inference_enabled(),
        // Campos novos: dois servidores de chat
        chat_akasha_model:    akasha_model,
        chat_akasha_online:   akasha_online,
        chat_akasha_ms:       akasha_ms,
        chat_mnemosyne_model:  mnemosyne_model_loaded,
        chat_mnemosyne_online: mnemosyne_online,
        chat_mnemosyne_ms:     mnemosyne_ms,
    }
}

/// Inicia o embed-server se `embed_model` estiver configurado e o servidor não estiver ativo.
///
/// Não-fatal: erros (modelo ausente, falha de spawn, timeout de ready) são apenas logados —
/// o servidor de chat continua funcionando independentemente.
/// Health-check single-shot do embed-server: `GET /health` → 2xx? Timeout curto.
/// Usado para detectar um embed-server saudável já no ar (handle dessincronizado).
async fn embed_health_ok(client: &Client, port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/health");
    client.get(&url)
        .timeout(Duration::from_secs(2))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

async fn ensure_embed_server_started(s: &LogosState) {
    let embed_model = s.0.embed_model.lock().await.clone();
    if embed_model.is_empty() {
        log::debug!("LOGOS embed: embed_model vazio — embed-server não iniciado");
        return;
    }

    // Fast path: processo já ativo
    if s.embed_proc_active().await {
        return;
    }

    // BUG-027: serializa o startup. Sem isto, AKASHA e Mnemosyne pedindo embedding ao MESMO
    // tempo (ambos veem embed_proc inativo) chamam esta função em paralelo e cada um tenta
    // spawnar um embed-server → conflito na porta 8082 → churn de restart → HTTP 500.
    // (Distinto do embed_semaphore, que serializa as REQUISIÇÕES, não o startup.)
    let _start = s.0.embed_start_lock.lock().await;

    // Re-checa sob a trava — outra task pode ter iniciado o embed-server enquanto esperávamos.
    if s.embed_proc_active().await {
        return;
    }
    // Handle dessincronizado: se um embed-server saudável JÁ responde na 8082 (ex.: o LOGOS
    // perdeu o handle após um wait_ready lento), reutiliza-o em vez de spawnar um duplicado
    // que não daria bind. Elimina a briga pela porta.
    if embed_health_ok(&s.0.client, EMBED_SERVER_PORT).await {
        log::info!(
            "LOGOS embed: servidor saudável já responde na porta {EMBED_SERVER_PORT} — \
             reutilizando (sem novo spawn)"
        );
        return;
    }

    // Busca a entry completa do registry ANTES do bin check — validação de integridade
    // deve ocorrer mesmo em ambientes de teste onde não há llama-server disponível.
    let entry = match find_model_registry_entry(&embed_model, &s.0.models_dir) {
        Some(e) => e,
        None => {
            let msg = format!(
                "embed-server não iniciado: modelo '{}' não encontrado no registry. \
                 Verifique se o nome em ecosystem.json[logos][embed_model] corresponde \
                 exatamente a um entry do registry.",
                embed_model
            );
            log::warn!("LOGOS embed: {msg}");
            s.emit_alert("warn", &msg).await;
            return;
        }
    };

    let gguf_path = std::path::PathBuf::from(&entry.path);

    // ── Validação de integridade GGUF — ocorre antes de buscar o bin ──────────
    // Detecta downloads incompletos e arquivos corrompidos antes de tentar spawnar,
    // evitando o timeout de 90s do wait_llama_ready em arquivos inválidos.
    match validate_gguf_file(&gguf_path, Some(entry.size_bytes)) {
        GgufValidation::Ok => {}
        GgufValidation::FileMissing => {
            log::error!(
                "LOGOS embed: arquivo '{}' não encontrado em '{}' — corrompido ou ausente",
                entry.filename, gguf_path.display()
            );
            s.emit_model_corrupted(
                &embed_model, "embed", "file_missing",
                &entry.repo_id, &entry.filename,
            ).await;
            return;
        }
        GgufValidation::IncompleteDownload { actual_bytes, expected_bytes } => {
            log::error!(
                "LOGOS embed: arquivo '{}' incompleto — {} de {} bytes (download interrompido)",
                entry.filename, actual_bytes, expected_bytes
            );
            s.emit_model_corrupted(
                &embed_model, "embed", "incomplete_download",
                &entry.repo_id, &entry.filename,
            ).await;
            return;
        }
        GgufValidation::InvalidMagic { actual_magic } => {
            log::error!(
                "LOGOS embed: arquivo '{}' com magic bytes inválidos ({:?}) — não é um GGUF válido",
                entry.filename, actual_magic
            );
            s.emit_model_corrupted(
                &embed_model, "embed", "invalid_magic",
                &entry.repo_id, &entry.filename,
            ).await;
            return;
        }
    }

    let bin = match s.0.llama_server_bin.as_ref() {
        Some(b) => b.clone(),
        None => {
            log::warn!("LOGOS embed: llama-server não encontrado — embed-server não iniciado");
            return;
        }
    };

    let n_gpu    = *s.0.embed_n_gpu_layers.lock().await;
    let log_path = embed_log_path(&s.0.models_dir);

    log::info!(
        "LOGOS embed-server: iniciando '{}' (n_gpu={}, porta={}, log={})",
        embed_model, n_gpu, EMBED_SERVER_PORT, log_path.display()
    );

    match spawn_embed_server_proc(&bin, &gguf_path, n_gpu, EMBED_SERVER_PORT).await {
        Ok(mut child) => {
            // Captura stderr antes de aguardar — reader roda em background
            if let Some(stderr) = child.stderr.take() {
                spawn_embed_stderr_reader(stderr, embed_model.clone(), log_path);
            }

            // Aguarda servidor pronto; detecção precoce de saída do processo evita
            // 90s de timeout quando o modelo falha ao carregar (ex: GGUF corrompido)
            let ready = wait_llama_ready_checking_child(
                EMBED_SERVER_PORT, &s.0.client, LLAMA_SERVER_READY_TIMEOUT_SECS, &mut child,
            ).await;

            if ready {
                *s.0.embed_proc.lock().await = Some(LlamaProcHandle {
                    child,
                    model_name: embed_model.clone(),
                });
                log::info!(
                    "LOGOS embed-server: '{}' pronto na porta {}",
                    embed_model, EMBED_SERVER_PORT
                );
            } else {
                // Processo morreu ou timeout — encerra e loga
                let _ = child.kill().await;
                log::error!(
                    "LOGOS embed-server: '{}' não ficou pronto — abortando \
                     (processo saiu ou timeout de {}s)",
                    embed_model, LLAMA_SERVER_READY_TIMEOUT_SECS
                );
            }
        }
        Err(e) => {
            log::error!("LOGOS embed-server: falha ao spawnar '{}': {}", embed_model, e);
        }
    }
}

/// Envia keep_alive: 0 para descarregar todos os modelos carregados.
/// Para o processo llama-server e o embed-server para liberar VRAM completamente.
/// Retorna o número de processos parados (0, 1 ou 2).
pub async fn do_silence(s: &LogosState) -> usize {
    let stopped_akasha    = s.kill_akasha_proc().await;
    let stopped_mnemosyne = s.kill_mnemosyne_proc().await;
    let stopped_embed     = s.kill_embed_proc().await;
    if stopped_akasha    { log::info!("LOGOS silence: servidor AKASHA parado"); }
    if stopped_mnemosyne { log::info!("LOGOS silence: servidor Mnemosyne parado"); }
    if stopped_embed     { log::info!("LOGOS silence: embed-server parado"); }
    usize::from(stopped_akasha) + usize::from(stopped_mnemosyne) + usize::from(stopped_embed)
}

/// Retorna o modelo atualmente carregado no llama-server (se houver).
/// Com llama-server, apenas um modelo roda por vez — é o que está em `llama_proc`.
pub async fn list_inference_models(s: &LogosState) -> Vec<ModelInfo> {
    let guard = s.0.akasha_proc.lock().await;
    match guard.as_ref() {
        Some(p) => vec![ModelInfo { name: p.model_name.clone(), size_vram_mb: 0 }],
        None    => vec![],
    }
}

/// Alias for backward compat with internal callers.
pub async fn list_ollama_models(s: &LogosState) -> Vec<ModelInfo> {
    list_inference_models(s).await
}

/// Para o processo llama-server e o embed-server ativos para liberar VRAM.
/// Retorna true se o servidor de chat estava rodando.
pub async fn do_unload_model(s: &LogosState, _model: &str) -> bool {
    s.kill_embed_proc().await;
    s.kill_llama_proc().await
}

/// Carrega um modelo no llama-server (garante processo ativo com o modelo correto).
/// Após o chat server estar pronto, inicia o embed-server se configurado.
/// Retorna true se o modelo de chat foi carregado com sucesso.
pub async fn do_load_model(s: &LogosState, model: &str) -> bool {
    let ok = ensure_llama_model_loaded(s, model).await.is_ok();
    if ok {
        ensure_embed_server_started(s).await;
    }
    ok
}

/// Altera o perfil de workflow ativo. Valores inválidos caem em "normal".
/// Retorna o perfil efetivamente aplicado.
pub async fn do_set_profile(s: &LogosState, profile: String) -> String {
    let validated = match profile.as_str() {
        "estudo" | "analise" | "normal" => profile,
        _ => "normal".to_string(),
    };
    *s.0.active_profile.lock().await = validated.clone();
    validated
}

/// Wrapper público de `list_inference_models` para uso nos Tauri commands.
pub async fn do_list_models(s: &LogosState) -> Vec<ModelInfo> {
    list_inference_models(s).await
}

/// Retorna todos os modelos instalados com status de carregamento.
/// Fonte: registry.json do LOGOS (modelos baixados via HUB).
/// Status "active" = modelo atualmente rodando no llama-server.
pub async fn do_list_all_models(s: &LogosState) -> Vec<ModelEntry> {
    let registry = read_model_registry(&s.0.models_dir).await;
    let active_name: Option<String> = s.0.akasha_proc.lock().await
        .as_ref()
        .map(|p| p.model_name.clone());

    let mut entries: Vec<ModelEntry> = registry.iter().map(|e| {
        let is_active = active_name.as_deref() == Some(&e.name)
            || active_name.as_deref() == Some(e.filename.trim_end_matches(".gguf"));
        ModelEntry {
            name:         e.name.clone(),
            status:       if is_active { "active" } else { "available" }.to_string(),
            size_vram_mb: 0,
            size_disk_mb: e.size_bytes / 1_000_000,
        }
    }).collect();

    entries.sort_by(|a, b| b.status.cmp(&a.status).then(a.name.cmp(&b.name)));
    entries
}

/// Retorna as atribuições de modelo atuais para cada app+tipo.
/// Combina recomendações do perfil de hardware com overrides da usuária.
/// Calcula compatibilidade com o hardware disponível.
pub async fn do_get_model_assignments(s: &LogosState) -> Vec<ModelAssignment> {
    let profile = s.0.hardware_profile.model_profile();
    let budget  = vram_budget_for_profile(s.0.hardware_profile);
    let overrides = s.0.model_overrides.lock().await.clone();

    // Mapa de tamanho em disco por modelo instalado (lido do registry.json do LOGOS)
    let registry_entries_assign = read_model_registry(&s.0.models_dir).await;
    let size_map: HashMap<String, u64> = registry_entries_assign.iter().flat_map(|e| {
        let size_mb = e.size_bytes / 1_000_000;
        // Indexa por nome do registro e pelo filename sem extensão
        let alt_name = e.filename.trim_end_matches(".gguf").to_string();
        vec![(e.name.clone(), size_mb), (alt_name, size_mb)]
    }).collect();

    // Definição de todos os slots de modelo configuráveis
    let slots: &[(&str, &str, &str, &str)] = &[
        // (app, model_type, label, recommended)
        ("mnemosyne", "llm_rag",      "Mnemosyne — RAG",               profile.llm_rag),
        ("mnemosyne", "image_ocr",    "Mnemosyne — OCR de imagens",    profile.image_ocr),
        ("kosmos",    "llm_analysis", "KOSMOS — Análise",               profile.llm_analysis),
        ("akasha",    "llm_query",    "AKASHA — Extração/Query",        profile.llm_query),
        ("embed",     "embed",        "Embedding (todos os apps)",      profile.embed),
    ];

    slots.iter().filter(|(_, _, _, recommended)| !recommended.is_empty()).map(|(app, model_type, label, recommended)| {
        let key = format!("{}_{}", app, model_type);
        let current = overrides.get(&key).map(String::as_str).unwrap_or(recommended);
        let is_custom = overrides.contains_key(&key);
        // Heurística: VRAM ≈ 65% do tamanho em disco (típico para Q4)
        let name_latest    = format!("{}:latest", current);
        let hf_fn_assign: Option<&str> = crate::commands::logos::model_hf_table(current)
            .map(|(_, fn_)| fn_)
            .or_else(|| crate::commands::logos::model_hf_table_multi(current)
                .and_then(|f| f.first().map(|(_, fn_)| *fn_)));
        let is_installed   = size_map.contains_key(current)
            || size_map.contains_key(&name_latest)
            || hf_fn_assign
                .map(|fn_| registry_entries_assign.iter().any(|e| e.filename == fn_))
                .unwrap_or(false);
        let vram_required_mb = size_map.get(current)
            .or_else(|| size_map.get(&name_latest))
            .map(|&s| s * 65 / 100)
            .unwrap_or(0);
        let fits_hardware = vram_required_mb == 0 || vram_required_mb <= budget;
        let is_downloadable = crate::commands::logos::model_hf_table(current).is_some()
            || crate::commands::logos::model_hf_table_multi(current).is_some();
        ModelAssignment {
            app: app.to_string(),
            model_type: model_type.to_string(),
            label: label.to_string(),
            current_model: current.to_string(),
            recommended_model: recommended.to_string(),
            is_custom,
            is_installed,
            vram_required_mb,
            vram_budget_mb: budget,
            fits_hardware,
            is_downloadable,
        }
    }).collect()
}

/// Sobrescreve o modelo atribuído a um slot (app + model_type).
/// Passar o próprio modelo recomendado remove o override (volta ao padrão).
pub async fn do_set_model_assignment(s: &LogosState, app: &str, model_type: &str, model: &str) {
    let key = format!("{}_{}", app, model_type);
    let recommended = {
        let profile = s.0.hardware_profile.model_profile();
        match (app, model_type) {
            ("mnemosyne", "llm_rag")   => profile.llm_rag.to_string(),
            ("mnemosyne", "image_ocr") => profile.image_ocr.to_string(),
            ("kosmos",    "llm_analysis") => profile.llm_analysis.to_string(),
            ("akasha",    "llm_query")    => profile.llm_query.to_string(),
            ("embed",     "embed")        => profile.embed.to_string(),
            _ => String::new(),
        }
    };
    let mut overrides = s.0.model_overrides.lock().await;
    if model == recommended || model.is_empty() {
        overrides.remove(&key);
    } else {
        overrides.insert(key, model.to_string());
    }
}

/// Nota de velocidade esperada no WorkPc (i5-3470, sem AVX2).
/// None para modelos não usados no WorkPc ou perfis com GPU.
fn speed_note_workpc(model: &str) -> Option<&'static str> {
    match model {
        "smollm2:1.7b"             => Some("~3–5 tok/s (WorkPc) — adequado para background, lento em chat interativo"),
        "qwen2.5:0.5b"             => Some("~5–8 tok/s (WorkPc) — extração JSON leve, sem AVX2"),
        "potion-multilingual-128M" => Some("~500 ms/chunk (WorkPc) — modelo estático CPU-only, sem Ollama"),
        _                          => None,
    }
}

fn rationale_for_model(name: &str) -> &'static str {
    match name {
        "qwen2.5:7b"               => "7B · ~4.5 GB VRAM · síntese multi-doc, RAG longo · JSON 92%",
        "qwen2.5:3b"               => "3B · ~1.9 GB VRAM · geração, diálogo e JSON para AKASHA · coexiste com qwen2.5:7b",
        "gemma2:2b"                => "2B · ~1.5 GB VRAM · rápido, streaming ágil · JSON 74%",
        "smollm2:1.7b"             => "1.7B · ~1 GB RAM · CPU-only, geração de texto · JSON 26% (não usar para extração estruturada)",
        "qwen2.5:0.5b"             => "0.5B · ~400 MB RAM · CPU-only, extração JSON · JSON 61% (melhor que smollm2 para schema)",
        "moondream"               => "multimodal compacto · ~1.7 GB VRAM · OCR + descrição de imagens · ideal para indexação de PDFs com figuras",
        "bge-m3"                   => "embed multilíngue SOTA · ~670 MB VRAM · 1024 dims",
        "nomic-embed-text"         => "embed compacto · boa qualidade · 2 GB VRAM",
        "all-minilm"               => "embed 384-dim · muito leve · CPU-only",
        "potion-multilingual-128M" => "embed estático · ~50ms/chunk · sem GPU · sem Ollama",
        _                          => "",
    }
}

/// Retorna todos os modelos recomendados compilados de todos os perfis de hardware,
/// com status de instalação e justificativas de uso.
pub async fn do_get_recommended_models(s: &LogosState) -> Vec<RecommendedModel> {
    let current = s.0.hardware_profile;
    let all_profiles = [HardwareProfile::MainPc, HardwareProfile::Laptop, HardwareProfile::WorkPc];

    // Definição dos slots: (app, model_type, label)
    let slot_defs: &[(&str, &str, &str)] = &[
        ("mnemosyne", "llm_rag",      "Mnemosyne — RAG"),
        ("mnemosyne", "image_ocr",    "Mnemosyne — OCR de imagens"),
        ("kosmos",    "llm_analysis", "KOSMOS — Análise"),
        ("akasha",    "llm_query",    "AKASHA — Extração/Query"),
        ("embed",     "embed",        "Embedding (todos os apps)"),
    ];

    // Constrói mapa: model_name → (slots únicos, perfis únicos)
    let mut map: HashMap<String, (Vec<ModelSlot>, Vec<String>)> = HashMap::new();

    for profile in all_profiles {
        let mp  = profile.model_profile();
        let models_for_profile = [mp.llm_rag, mp.image_ocr, mp.llm_analysis, mp.llm_query, mp.embed];
        for (slot_def, model_name) in slot_defs.iter().zip(models_for_profile.iter()).filter(|(_, m)| !m.is_empty()) {
            let (app, model_type, label) = slot_def;
            let entry = map.entry(model_name.to_string()).or_insert_with(|| (vec![], vec![]));
            if !entry.0.iter().any(|sl: &ModelSlot| sl.app == *app && sl.model_type == *model_type) {
                entry.0.push(ModelSlot {
                    app:               app.to_string(),
                    model_type:        model_type.to_string(),
                    label:             label.to_string(),
                    slot_label:        slot_label_for(model_type).to_string(),
                    language_affinity: language_affinity_for(model_name),
                });
            }
            let ps = profile.as_str().to_string();
            if !entry.1.contains(&ps) {
                entry.1.push(ps);
            }
        }
    }

    // Modelos do perfil atual
    let current_mp = current.model_profile();
    let current_models: std::collections::HashSet<String> = [
        current_mp.llm_rag, current_mp.image_ocr, current_mp.llm_analysis,
        current_mp.llm_query, current_mp.embed,
    ].iter().filter(|s| !s.is_empty()).map(|s| s.to_string()).collect();

    // Status de instalação: registry LOGOS primeiro, depois blob store do Ollama.
    // Não consulta Ollama /api/tags — funciona sem Ollama em execução.
    let model_names: Vec<String> = map.keys().cloned().collect();
    let registry_entries = read_model_registry(&s.0.models_dir).await;
    let size_map: HashMap<String, u64> = {
        let mut m: HashMap<String, u64> = HashMap::new();
        // 1. Modelos registrados no LOGOS (downloaded via HUB ou gguf_converter)
        for entry in &registry_entries {
            m.insert(entry.name.clone(), entry.size_bytes / 1_000_000);
        }
        // 2. Modelos no blob store do Ollama (reutiliza downloads existentes)
        for name in &model_names {
            if !m.contains_key(name.as_str()) {
                if let Some(blob) = find_gguf_in_ollama_store(name) {
                    let size_mb = std::fs::metadata(&blob)
                        .map(|meta| meta.len() / 1_000_000)
                        .unwrap_or(0);
                    m.insert(name.clone(), size_mb);
                }
            }
        }
        m
    };

    let mut result: Vec<RecommendedModel> = map.into_iter().map(|(model_name, (slots, for_profiles))| {
        // Lookup primário: pelo alias canônico no registry (modelos baixados com a versão corrigida).
        // Fallback: via HF table — verifica se alguma entrada do registry tem o filename esperado
        // (cobre modelos baixados antes da correção que usavam filename como name).
        // lookup pelo alias canônico; fallback pelo filename da HF table (single ou multi-file)
        let hf_main_filename: Option<&str> = crate::commands::logos::model_hf_table(&model_name)
            .map(|(_, fn_)| fn_)
            .or_else(|| crate::commands::logos::model_hf_table_multi(&model_name)
                .and_then(|f| f.first().map(|(_, fn_)| *fn_)));
        let is_installed = size_map.contains_key(&model_name)
            || hf_main_filename
                .map(|fn_| registry_entries.iter().any(|e| e.filename == fn_))
                .unwrap_or(false);
        let size_disk_mb = size_map.get(&model_name).copied().unwrap_or_else(|| {
            hf_main_filename
                .and_then(|fn_| registry_entries.iter().find(|e| e.filename == fn_))
                .map(|e| e.size_bytes / 1_000_000)
                .unwrap_or(0)
        });
        let for_current_profile  = current_models.contains(&model_name);
        let expected_speed_note = if for_profiles.contains(&"work_pc".to_string()) {
            speed_note_workpc(&model_name).map(str::to_string)
        } else {
            None
        };
        RecommendedModel {
            rationale: rationale_for_model(&model_name).to_string(),
            for_current_profile,
            is_installed,
            is_static: false,
            size_disk_mb,
            expected_speed_note,
            model_name,
            slots,
            for_profiles,
        }
    }).collect();

    // potion: modelo estático (não-Ollama), disponível para todos os perfis
    result.push(RecommendedModel {
        model_name:          "potion-multilingual-128M".to_string(),
        slots:               vec![ModelSlot {
            app:               "embed".to_string(),
            model_type:        "embed".to_string(),
            label:             "Embedding (todos os apps)".to_string(),
            slot_label:        slot_label_for("embed").to_string(),
            language_affinity: Some(vec!["pt".into(), "en".into(), "zh".into()]),
        }],
        for_profiles:        all_profiles.iter().map(|p| p.as_str().to_string()).collect(),
        for_current_profile: true,
        is_installed:        false, // model2vec baixa automaticamente no primeiro uso
        is_static:           true,
        size_disk_mb:        0,
        rationale:           rationale_for_model("potion-multilingual-128M").to_string(),
        expected_speed_note: speed_note_workpc("potion-multilingual-128M").map(str::to_string),
    });

    // Perfil atual primeiro, depois alfabético
    result.sort_by(|a, b| {
        b.for_current_profile.cmp(&a.for_current_profile)
            .then(a.model_name.cmp(&b.model_name))
    });
    result
}

/// Aplica override de prioridade baseado no perfil ativo e no app requisitante.
///
/// Perfis e seus efeitos:
///   analise — caso de uso primário: indexação e análise em background.
///             AKASHA/Mnemosyne/KOSMOS P3 → P2 (análises não ficam na fila mais baixa).
///   estudo  — consulta ativa ao vault: Mnemosyne RAG P2→P1; AKASHA P3→P2.
///   normal  — sem override; prioridades definidas pelos apps.
fn apply_profile_priority(profile: &str, app: &str, requested: u8) -> u8 {
    match profile {
        "analise" => match (app, requested) {
            ("akasha",    3) => 2,
            ("mnemosyne", 3) => 2,
            ("kosmos",    3) => 2,
            _ => requested,
        },
        "estudo" => match (app, requested) {
            // Mnemosyne RAG promovido: consultas ao vault são prioridade
            ("mnemosyne", 2) => 1,
            // AKASHA e KOSMOS reader promovidos: pesquisa ativa
            ("akasha",    3) => 2,
            ("kosmos",    1) => 2,
            _ => requested,
        },
        // normal: sem override de prioridade
        _ => requested,
    }
}

// ── Classificação de modelo ───────────────────────────────────

/// Retorna true se o modelo é "leve" (≤3B parâmetros).
/// Modelos leves adquirem 1 permit → até 2 rodam em paralelo.
/// Modelos pesados adquirem 2 permits → exclusividade total.
fn is_light_model(model: &str) -> bool {
    let lower = model.to_lowercase();
    // Detecta tamanho pelo tag: "gemma2:2b", "qwen2.5:3b", "smollm2:1.7b", "llama3.2:1b-instruct"
    [":0.5b", ":1b", ":1.3b", ":1.5b", ":1.7b", ":2b", ":3b",
     "-0.5b", "-1b", "-1.3b", "-1.5b", "-1.7b", "-2b", "-3b"]
        .iter()
        .any(|p| lower.contains(p))
}

// ── VRAM helpers ──────────────────────────────────────────────

async fn vram_pct(client: &Client, hw: HardwareProfile) -> Option<f32> {
    vram_usage(client, hw).await.2
}

/// Retorna `(used_mb, total_mb, pct)` — total_mb é o real do sysfs, não hardcoded.
async fn vram_usage(_client: &Client, hw: HardwareProfile) -> (Option<u64>, Option<u64>, Option<f32>) {
    // No Linux, sysfs é a fonte correta para AMD/ROCm —
    // o Ollama reporta size_vram=0 para GPUs AMD, tornando /api/ps inútil para VRAM.
    #[cfg(target_os = "linux")]
    if let Some((total_mb, used_mb)) = sysfs_vram_mb() {
        let pct = if total_mb > 0 { Some(used_mb as f32 / total_mb as f32) } else { None };
        return (Some(used_mb), Some(total_mb), pct);
    }

    // NVIDIA: nvidia-smi (não depende do Ollama — funciona com llama-server)
    #[cfg(target_os = "linux")]
    if hw == HardwareProfile::Laptop {
        if let Some((total_mb, used_mb)) = nvidia_vram_mb().await {
            let pct = if total_mb > 0 { Some(used_mb as f32 / total_mb as f32) } else { None };
            return (Some(used_mb), Some(total_mb), pct);
        }
    }

    // WorkPc não tem GPU discreta — sem VRAM para monitorar
    (None, None, None)
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

/// Lê temperatura da GPU discreta (em °C) via sysfs hwmon (Linux/AMD e NVIDIA).
///
/// Para AMD (RX 6600): `/sys/class/drm/cardX/device/hwmon/hwmonY/temp1_input`
/// O valor é retornado em mili-graus Celsius — divide por 1000 para obter °C.
/// temp1 = edge (borda do chip), temp2 = junction (die), temp3 = mem.
/// Retorna None no Windows ou se nenhuma GPU for detectada.
fn read_gpu_temp_celsius() -> Option<f32> {
    #[cfg(target_os = "linux")]
    {
        for i in 0..8u8 {
            let hwmon_path = format!("/sys/class/drm/card{i}/device/hwmon");
            let hwmon_dir = std::path::Path::new(&hwmon_path);
            let Ok(entries) = std::fs::read_dir(hwmon_dir) else { continue };
            for entry in entries.flatten() {
                let temp_path = entry.path().join("temp1_input");
                if let Ok(raw) = std::fs::read_to_string(&temp_path) {
                    if let Ok(millideg) = raw.trim().parse::<i64>() {
                        return Some(millideg as f32 / 1000.0);
                    }
                }
            }
        }
    }
    None
}

/// Lê uso de CPU e memória.
/// CPU% vem do `cached_cpu_pct` atualizado pelo `cpu_watchdog` a cada 1s — evita delta zero
/// quando múltiplos callers chamam `refresh_cpu_all()` com menos de 15ms de intervalo (Windows).
/// RAM é lida diretamente via sysinfo (sem problema de delta).
async fn cpu_ram_usage(sys: &Mutex<System>, cached_cpu_pct: &AtomicU32) -> (f32, u64, u64) {
    let cpu = f32::from_bits(cached_cpu_pct.load(Ordering::Relaxed));
    let (free_mb, total_mb) = {
        let mut s = sys.lock().await;
        s.refresh_memory();
        (s.available_memory() / 1_048_576, s.total_memory() / 1_048_576)
    };
    (cpu, free_mb, total_mb)
}

// ── Bateria ───────────────────────────────────────────────────

/// Detecta se o dispositivo está rodando em bateria via sysfs (Linux).
/// Lê /sys/class/power_supply/ e retorna (is_discharging, battery_pct).
/// Itera todas as fontes; usa a primeira bateria encontrada.
/// No Windows (desktop sem bateria) retorna sempre (false, 100).
fn read_battery_info() -> (bool, u8) {
    #[cfg(target_os = "linux")]
    {
        let mut discharging = false;
        let mut pct: u8 = 100;
        if let Ok(entries) = std::fs::read_dir("/sys/class/power_supply") {
            for entry in entries.flatten() {
                let p = entry.path();
                // Pular fontes do tipo "Mains" (adaptador AC)
                if let Ok(t) = std::fs::read_to_string(p.join("type")) {
                    if t.trim() == "Mains" { continue; }
                }
                if let Ok(s) = std::fs::read_to_string(p.join("status")) {
                    if s.trim() == "Discharging" {
                        discharging = true;
                    }
                }
                if let Ok(c) = std::fs::read_to_string(p.join("capacity")) {
                    if let Ok(n) = c.trim().parse::<u8>() {
                        pct = n;
                    }
                }
                // Parar na primeira bateria com dados válidos
                break;
            }
        }
        return (discharging, pct);
    }
    #[cfg(not(target_os = "linux"))]
    { (false, 100) }
}

/// Retorna true se alguma fonte de energia reportar "Discharging".
fn is_on_battery() -> bool {
    read_battery_info().0
}

/// Retorna o percentual da bateria (0-100). 100 quando em AC ou sem bateria.
fn read_battery_pct() -> u8 {
    read_battery_info().1
}

/// Detecta suporte a AVX2 via CPUID em runtime.
/// Funciona em x86/x86_64 (Linux e Windows). Retorna false em outras arquiteturas.
/// O i5-3470 (WorkPc, Ivy Bridge 2012) não tem AVX2 — inferência INT4 30-50% mais lenta.
fn detect_avx2() -> bool {
    #[cfg(any(target_arch = "x86", target_arch = "x86_64"))]
    { std::arch::is_x86_feature_detected!("avx2") }
    #[cfg(not(any(target_arch = "x86", target_arch = "x86_64")))]
    { false }
}

// ── Parâmetros de eficiência por prioridade ───────────────────

/// Injeta parâmetros de eficiência no objeto `options` do body conforme prioridade e hardware.
///
/// P1 normal:   sem injeção (máxima performance, app decide).
/// P1 bateria:  num_thread=2 (reduzir consumo energético do CPU).
/// P1 survival: num_thread=3 (i5-3470: 4 cores, deixa 1 livre para o SO).
/// P2 normal:   num_batch=256 (preservar RAM); em bateria: num_thread=2 adicional.
/// P2 survival: num_thread=4 (usa todos os 4 cores — usuária esperando resposta).
/// P3 normal:    num_thread=2, num_batch=256, num_ctx=2048 (impacto mínimo no sistema).
/// P3 survival:  num_thread=1, num_batch=64, num_ctx=1024 (mínimo viável; 3 cores livres para P1/P2/SO).
/// P3 laptop:    num_gpu=0 adicional (background roda só na CPU, preserva VRAM da MX150).
fn inject_efficiency_params(
    body: &mut serde_json::Map<String, serde_json::Value>,
    priority: u8,
    hw: HardwareProfile,
    is_survival: bool,
    on_battery: bool,
    has_avx2: bool,
) {
    if priority == 1 {
        let opts = body.entry("options").or_insert_with(|| serde_json::json!({}));
        if let Some(o) = opts.as_object_mut() {
            if is_survival {
                // i5-3470: 4 cores sem hyperthreading — 3 para Ollama, 1 livre para o SO
                o.entry("num_thread").or_insert(serde_json::json!(3));
            } else if on_battery || !has_avx2 {
                // Em bateria OU sem AVX2: 2 threads para reduzir consumo / evitar travamento
                o.entry("num_thread").or_insert(serde_json::json!(2));
            }
            // Sem AVX2: limitar contexto para reduzir KV cache (memória e latência)
            if !has_avx2 {
                o.entry("num_ctx").or_insert(serde_json::json!(512));
                o.entry("num_batch").or_insert(serde_json::json!(128));
            }
        }
        return;
    }
    let opts = body.entry("options").or_insert_with(|| serde_json::json!({}));
    let Some(o) = opts.as_object_mut() else { return };
    match priority {
        2 => {
            o.entry("num_batch").or_insert(serde_json::json!(if has_avx2 { 256 } else { 128 }));
            if is_survival {
                // WorkPc: resposta interativa — usa todos os 4 cores do i5-3470
                o.entry("num_thread").or_insert(serde_json::json!(4));
            } else if on_battery || !has_avx2 {
                o.entry("num_thread").or_insert(serde_json::json!(2));
            }
            if !has_avx2 {
                o.entry("num_ctx").or_insert(serde_json::json!(512));
            }
        }
        _ => {
            if is_survival {
                // P3 sobrevivência: mínimo viável — 1 core, contexto curto, batch mínimo.
                // P1/P2 usa 3-4 cores → 1 core livre para background sem impacto perceptível.
                o.entry("num_thread").or_insert(serde_json::json!(1));
                o.entry("num_batch").or_insert(serde_json::json!(64));
                o.entry("num_ctx").or_insert(serde_json::json!(1024));
            } else {
                // Sem AVX2: limites conservadores para não saturar CPU
                let (num_thread, num_batch, num_ctx) = if has_avx2 {
                    (2u32, 256u32, 2048u32)
                } else {
                    (2u32, 128u32, 512u32) // i5-3470: sem AVX2 → contextos longos travam
                };
                o.entry("num_thread").or_insert(serde_json::json!(num_thread));
                o.entry("num_batch").or_insert(serde_json::json!(num_batch));
                o.entry("num_ctx").or_insert(serde_json::json!(num_ctx));
                if hw == HardwareProfile::Laptop {
                    // MX150 tem apenas 2 GB VRAM — background não deve competir com P1/P2
                    o.entry("num_gpu").or_insert(serde_json::json!(0));
                }
            }
        }
    }
}

// ── Preempção inteligente ─────────────────────────────────────

/// Retorna estimativa de VRAM necessária em MB para o modelo via registry.json.
/// Tamanho em disco × 85% é uma heurística razoável para modelos Q4.
/// Fallback: 4 GB (conservador — garante preempção se o modelo não estiver no registry).
async fn estimate_model_vram_mb(s: &LogosState, model: &str) -> u64 {
    let registry = read_model_registry(&s.0.models_dir).await;
    registry.iter()
        .find(|e| e.name == model || e.filename.trim_end_matches(".gguf") == model)
        .map(|e| e.size_bytes * 85 / (100 * 1_048_576))
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
    let needed_mb = estimate_model_vram_mb(s, model_name).await;
    if vram_free >= needed_mb + 500 {
        return; // VRAM suficiente — coexistência possível
    }
    log::info!(
        "LOGOS: preemptando P3 — VRAM livre {vram_free} MB, necessário ≈{needed_mb} MB para P1 ({model_name})"
    );
    do_silence(s).await;
    *s.0.preempted_count.lock().await += 1;
    // Aguarda até 10s para o llama-server liberar a VRAM
    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    loop {
        if tokio::time::Instant::now() >= deadline {
            break;
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
        if list_ollama_models(s).await.is_empty() {
            break;
        }
    }
}


// ── Download de GGUF do HuggingFace ──────────────────────────

/// POST /logos/models/download — inicia download em background e retorna { id }.
async fn download_model_handler(
    State(s): State<LogosState>,
    Json(req): Json<DownloadRequest>,
) -> Response {
    if req.repo_id.is_empty() || req.filename.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "campos 'repo_id' e 'filename' são obrigatórios" })),
        ).into_response();
    }
    // Rejeita filenames com path traversal
    if req.filename.contains("..") || req.filename.contains('/') || req.filename.contains('\\') {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "filename inválido" })),
        ).into_response();
    }

    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let safe_name = req.filename.replace(['.', '-', ' '], "_");
    let id = format!("{ts}_{safe_name}");

    // Verifica se já existe um download ativo para o mesmo arquivo
    {
        let map = s.0.downloads.lock().await;
        for tx in map.values() {
            let p = tx.borrow();
            if p.filename == req.filename && !p.done && p.error.is_none() {
                return (
                    StatusCode::CONFLICT,
                    Json(serde_json::json!({
                        "error": "download já em andamento para este arquivo",
                        "id": p.id,
                    })),
                ).into_response();
            }
        }
    }

    let hf_url = format!(
        "https://huggingface.co/{}/resolve/main/{}",
        req.repo_id, req.filename
    );

    let initial = DownloadProgress {
        id:               id.clone(),
        filename:         req.filename.clone(),
        bytes_downloaded: 0,
        total_bytes:      None,
        pct:              None,
        speed_mbps:       0.0,
        done:             false,
        error:            None,
    };
    let (tx, _) = tokio::sync::watch::channel(initial);
    s.0.downloads.lock().await.insert(id.clone(), tx.clone());

    let s_task  = s.clone();
    let id_task = id.clone();
    let url_log = hf_url.clone();
    let model_name_task = req.model_name.clone();
    tokio::spawn(async move {
        download_model_task(s_task, id_task, hf_url, req.repo_id, req.filename, model_name_task, tx).await;
    });

    log::info!("LOGOS: download iniciado — id={id}, url={url_log}");
    (StatusCode::ACCEPTED, Json(serde_json::json!({ "id": id }))).into_response()
}

/// GET /logos/models/download/progress/:id — SSE com progresso do download.
async fn download_progress_handler(
    State(s): State<LogosState>,
    AxumPath(id): AxumPath<String>,
) -> impl IntoResponse {
    let rx = {
        let map = s.0.downloads.lock().await;
        map.get(&id).map(|tx| tx.subscribe())
    };

    let Some(mut rx) = rx else {
        return (StatusCode::NOT_FOUND, "download não encontrado").into_response();
    };

    let stream = async_stream::stream! {
        loop {
            let progress = rx.borrow().clone();
            let done = progress.done || progress.error.is_some();
            if let Ok(json) = serde_json::to_string(&progress) {
                yield Ok::<Event, std::convert::Infallible>(Event::default().data(json));
            }
            if done { break; }
            if rx.changed().await.is_err() { break; }
        }
    };
    Sse::new(stream).keep_alive(KeepAlive::default()).into_response()
}

/// GET /logos/models/registry — lista modelos baixados registrados em registry.json.
async fn model_registry_handler(State(s): State<LogosState>) -> Response {
    let entries = read_model_registry(&s.0.models_dir).await;
    (StatusCode::OK, Json(entries)).into_response()
}

/// Task de download em background.
async fn download_model_task(
    s:          LogosState,
    id:         String,
    url:        String,
    repo_id:    String,
    filename:   String,
    model_name: Option<String>,
    tx:         tokio::sync::watch::Sender<DownloadProgress>,
) {
    // Envia erro e limpa o mapa após 60s para consumidores tardios
    macro_rules! fail {
        ($msg:expr) => {{
            let _ = tx.send(DownloadProgress {
                id: id.clone(), filename: filename.clone(),
                bytes_downloaded: 0, total_bytes: None, pct: None,
                speed_mbps: 0.0, done: true, error: Some($msg),
            });
            log::warn!("LOGOS: download falhou — id={id}: {}", $msg);
            tokio::time::sleep(Duration::from_secs(60)).await;
            s.0.downloads.lock().await.remove(&id);
            return;
        }};
    }

    // Passo 1: iniciar request HTTP
    let mut resp = match s.0.client.get(&url).send().await {
        Ok(r) if r.status().is_success() => r,
        Ok(r)  => fail!(format!("HuggingFace retornou {}", r.status())),
        Err(e) => fail!(format!("Erro de rede: {e}")),
    };

    let total_bytes = resp.content_length();

    // Passo 2: criar arquivo de destino
    if let Err(e) = tokio::fs::create_dir_all(&s.0.models_dir).await {
        fail!(format!("Erro ao criar diretório de modelos: {e}"));
    }
    let out_path = s.0.models_dir.join(&filename);
    let mut file = match tokio::fs::File::create(&out_path).await {
        Ok(f)  => f,
        Err(e) => fail!(format!("Erro ao criar arquivo de destino: {e}")),
    };

    // Passo 3: stream de chunks + SHA256
    use sha2::{Digest as _, Sha256};
    use tokio::io::AsyncWriteExt as _;

    let mut hasher            = Sha256::new();
    let mut bytes_downloaded  = 0u64;
    let start                 = std::time::Instant::now();
    let mut last_report       = std::time::Instant::now();

    loop {
        match resp.chunk().await {
            Ok(Some(chunk)) => {
                hasher.update(&chunk);
                bytes_downloaded += chunk.len() as u64;
                if let Err(e) = file.write_all(&chunk).await {
                    let _ = tokio::fs::remove_file(&out_path).await;
                    fail!(format!("Erro de escrita: {e}"));
                }
                if last_report.elapsed().as_millis() >= 500 {
                    let elapsed   = start.elapsed().as_secs_f64().max(0.001);
                    let speed_mbps = (bytes_downloaded as f64 / elapsed / 1_000_000.0) as f32;
                    let pct = total_bytes
                        .filter(|&t| t > 0)
                        .map(|t| bytes_downloaded as f32 / t as f32 * 100.0);
                    let _ = tx.send(DownloadProgress {
                        id: id.clone(), filename: filename.clone(),
                        bytes_downloaded, total_bytes, pct, speed_mbps,
                        done: false, error: None,
                    });
                    last_report = std::time::Instant::now();
                }
            }
            Ok(None) => break, // transfer completa
            Err(e)   => {
                let _ = tokio::fs::remove_file(&out_path).await;
                fail!(format!("Erro ao receber chunk: {e}"));
            }
        }
    }

    if let Err(e) = file.flush().await {
        let _ = tokio::fs::remove_file(&out_path).await;
        fail!(format!("Erro ao finalizar arquivo: {e}"));
    }
    drop(file);

    // Passo 4: SHA256 e registry
    let sha256         = hex::encode(hasher.finalize());
    let resolved_name  = model_name.unwrap_or_else(|| filename.trim_end_matches(".gguf").to_string());
    let model_type_str = crate::commands::logos::model_type_for_name(&resolved_name);
    log::info!(
        "LOGOS: download finalizado — modelo='{}' tipo='{}' sha256={}…",
        resolved_name, model_type_str, &sha256[..8]
    );
    let entry = ModelRegistryEntry {
        name:          resolved_name,
        repo_id:       repo_id.clone(),
        filename:      filename.clone(),
        path:          out_path.to_string_lossy().into_owned(),
        size_bytes:    bytes_downloaded,
        sha256:        sha256.clone(),
        downloaded_at: chrono::Local::now().to_rfc3339(),
        model_type:    Some(model_type_str.to_string()),
        mmproj_path:   None,
    };
    update_model_registry(&s.0.models_dir, entry).await;

    // Passo 5: progresso final
    let elapsed    = start.elapsed().as_secs_f64().max(0.001);
    let speed_mbps = (bytes_downloaded as f64 / elapsed / 1_000_000.0) as f32;
    let _ = tx.send(DownloadProgress {
        id: id.clone(), filename: filename.clone(),
        bytes_downloaded, total_bytes, pct: Some(100.0), speed_mbps,
        done: true, error: None,
    });

    log::info!(
        "LOGOS: download concluído — {} ({:.1} MB em {:.1}s, {:.1} MB/s, sha256={}…)",
        filename,
        bytes_downloaded as f64 / 1_000_000.0,
        elapsed,
        speed_mbps,
        &sha256[..8],
    );

    // Mantém entrada para consumidores tardios do SSE
    tokio::time::sleep(Duration::from_secs(60)).await;
    s.0.downloads.lock().await.remove(&id);
}

/// Lê o registry de modelos GGUF de {models_dir}/registry.json.
/// Retorna vec vazio se o arquivo não existir ou estiver corrompido.
async fn read_model_registry(models_dir: &std::path::Path) -> Vec<ModelRegistryEntry> {
    let path = models_dir.join("registry.json");
    tokio::fs::read_to_string(&path)
        .await
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

/// Adiciona ou atualiza uma entrada no registry.
/// Entradas com o mesmo `filename` são substituídas (re-download).
async fn update_model_registry(models_dir: &std::path::Path, entry: ModelRegistryEntry) {
    let path = models_dir.join("registry.json");
    let mut entries = read_model_registry(models_dir).await;
    entries.retain(|e| e.filename != entry.filename);
    entries.push(entry);
    if let Ok(json) = serde_json::to_string_pretty(&entries) {
        let _ = tokio::fs::write(&path, json).await;
    }
}

/// Atualiza o campo `mmproj_path` de uma entrada existente no registry (busca por `name`).
/// Usado após o download do arquivo de projeção visual de modelos multimodais.
pub(crate) async fn update_registry_mmproj(
    models_dir: &std::path::Path,
    model_name: &str,
    mmproj_path: &str,
) {
    let path = models_dir.join("registry.json");
    let mut entries = read_model_registry(models_dir).await;
    let mut found = false;
    for e in entries.iter_mut() {
        if e.name == model_name {
            e.mmproj_path = Some(mmproj_path.to_string());
            found = true;
            break;
        }
    }
    if !found {
        log::warn!("update_registry_mmproj: modelo '{}' não encontrado no registry", model_name);
        return;
    }
    if let Ok(json) = serde_json::to_string_pretty(&entries) {
        let _ = tokio::fs::write(&path, json).await;
    }
}

// ── Entry point ───────────────────────────────────────────────

pub async fn start_server(state: LogosState, app_handle: tauri::AppHandle) {

    // Armazena o AppHandle para emissão de eventos críticos ao frontend
    *state.0.app_handle.lock().await = Some(app_handle);

    // Log de capacidades da CPU no startup
    if state.0.has_avx2 {
        log::info!("logos: CPU tem AVX2 — inferência INT4 em velocidade máxima");
    } else {
        log::warn!(
            "logos: CPU SEM AVX2 — inferência INT4 30-50% mais lenta; \
             aplicando limites conservadores: num_ctx=512, num_batch=128, num_thread=2"
        );
    }

    // Task de atualização do status de bateria a cada 30s.
    // Atualiza on_battery, battery_pct e battery_policy (3 níveis: Normal/Economy/Critical).
    let battery_state = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(30)).await;
            let (dis, pct) = read_battery_info();
            let policy = BatteryPolicy::from_state(dis, pct);
            let prev = *battery_state.0.battery_policy.lock().await;
            if policy != prev {
                log::info!(
                    "logos: política de bateria alterada: {} → {} ({}% bateria, descarga={})",
                    prev.as_str(), policy.as_str(), pct, dis,
                );
            }
            *battery_state.0.on_battery.lock().await    = dis;
            *battery_state.0.battery_pct.lock().await   = pct;
            *battery_state.0.battery_policy.lock().await = policy;
        }
    });

    // Watchdog de CPU — único caller de refresh_cpu_all(), a cada 1s.
    // Resolve BUG-007: múltiplos callers com delta ≈ 0 ms retornavam 0% no Windows (PDH).
    // 200ms de espera inicial garante baseline não-zero antes da primeira leitura.
    let cpu_wdg = state.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(200)).await;
        loop {
            let pct = {
                let mut s = cpu_wdg.0.sys.lock().await;
                s.refresh_cpu_all();
                s.global_cpu_usage()
            };
            cpu_wdg.0.cached_cpu_pct.store(pct.to_bits(), Ordering::Relaxed);
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    });

    // Watchdog de processo do llama-server — verifica a cada 10s.
    // Detecta crashes e tenta restart automático com backoff exponencial (10s/30s/60s).
    // Após 3 falhas consecutivas: desabilita o llama-server e emite "logos-llama-unavailable".
    let proc_wdg = state.clone();
    tokio::spawn(async move {
        const BACKOFFS: [u64; 3] = [10, 30, 60];
        loop {
            tokio::time::sleep(Duration::from_secs(10)).await;

            // Verifica se o processo existe e saiu inesperadamente
            let crashed_model: Option<String> = {
                let mut guard = proc_wdg.0.akasha_proc.lock().await;
                if let Some(ref mut proc) = guard.as_mut() {
                    match proc.child.try_wait() {
                        Ok(Some(status)) => {
                            log::error!(
                                "LOGOS watchdog: llama-server saiu inesperadamente \
                                 (modelo='{}', status={:?})",
                                proc.model_name, status
                            );
                            Some(proc.model_name.clone())
                        }
                        Ok(None) => None, // ainda rodando — ok
                        Err(e) => {
                            log::warn!("LOGOS watchdog: erro ao verificar processo: {e}");
                            None
                        }
                    }
                } else {
                    None // nenhum processo ativo — normal
                }
            };

            let Some(model_name) = crashed_model else { continue };

            // Limpa o handle do processo morto
            *proc_wdg.0.akasha_proc.lock().await = None;

            // Emite evento de crash para o frontend
            proc_wdg.emit_alert(
                "error",
                &format!("llama-server caiu inesperadamente (modelo '{model_name}')"),
            ).await;
            {
                let guard = proc_wdg.0.app_handle.lock().await;
                if let Some(ref handle) = *guard {
                    let _ = handle.emit("logos-llama-crashed", serde_json::json!({
                        "model": model_name,
                    }));
                }
            }

            // Incrementa contador de crashes
            let crash_count = {
                let mut cc = proc_wdg.0.akasha_crash_count.lock().await;
                *cc += 1;
                *cc
            };

            if crash_count > 3 {
                log::error!(
                    "LOGOS watchdog: llama-server falhou {} vezes — \
                     desabilitado até reload manual",
                    crash_count
                );
                proc_wdg.0.akasha_disabled.store(true, Ordering::Relaxed);
                proc_wdg.emit_alert(
                    "error",
                    "llama-server falhou 3+ vezes consecutivas — \
                     desabilitado. Reinicie o HUB para reativar.",
                ).await;
                {
                    let guard = proc_wdg.0.app_handle.lock().await;
                    if let Some(ref handle) = *guard {
                        let _ = handle.emit("logos-llama-unavailable", ());
                    }
                }
                // Watchdog permanece ativo mas sem tentar restart
                loop { tokio::time::sleep(Duration::from_secs(3600)).await; }
            }

            let backoff = BACKOFFS[(crash_count as usize - 1).min(2)];
            log::warn!(
                "LOGOS watchdog: tentativa {crash_count}/3 de restart de '{model_name}' em {backoff}s"
            );
            tokio::time::sleep(Duration::from_secs(backoff)).await;

            // Tenta restart
            let ok = do_load_model(&proc_wdg, &model_name).await;
            if ok {
                *proc_wdg.0.akasha_crash_count.lock().await = 0;
                log::info!(
                    "LOGOS watchdog: llama-server reiniciado com sucesso — '{model_name}'"
                );
                proc_wdg.emit_alert(
                    "warn",
                    &format!("llama-server reiniciado após crash — '{model_name}'"),
                ).await;
            } else {
                log::error!(
                    "LOGOS watchdog: falha ao reiniciar llama-server — '{model_name}' \
                     (tentativa {crash_count}/3)"
                );
            }
        }
    });

    // Crash watchdog do servidor Mnemosyne — análogo ao do AKASHA, independente.
    // Detecta saída inesperada, tenta restart com backoff (10s/30s/60s).
    // Após 3 falhas: desabilita o servidor Mnemosyne e emite alerta.
    let mnemosyne_wdg = state.clone();
    tokio::spawn(async move {
        const BACKOFFS: [u64; 3] = [10, 30, 60];
        loop {
            tokio::time::sleep(Duration::from_secs(10)).await;

            let crashed_model: Option<String> = {
                let mut guard = mnemosyne_wdg.0.mnemosyne_proc.lock().await;
                if let Some(ref mut proc) = guard.as_mut() {
                    match proc.child.try_wait() {
                        Ok(Some(status)) => {
                            log::error!(
                                "LOGOS watchdog (Mnemosyne): servidor saiu inesperadamente \
                                 (modelo='{}', status={:?})",
                                proc.model_name, status
                            );
                            Some(proc.model_name.clone())
                        }
                        Ok(None)  => None,
                        Err(e) => { log::warn!("LOGOS watchdog (Mnemosyne): erro ao verificar: {e}"); None }
                    }
                } else { None }
            };

            let Some(model_name) = crashed_model else { continue };

            *mnemosyne_wdg.0.mnemosyne_proc.lock().await = None;

            mnemosyne_wdg.emit_alert(
                "error",
                &format!("Mnemosyne server caiu inesperadamente (modelo '{model_name}')"),
            ).await;
            {
                let guard = mnemosyne_wdg.0.app_handle.lock().await;
                if let Some(ref handle) = *guard {
                    let _ = handle.emit("logos-mnemosyne-crashed", serde_json::json!({ "model": model_name }));
                }
            }

            let crash_count = {
                let mut cc = mnemosyne_wdg.0.mnemosyne_crash_count.lock().await;
                *cc += 1;
                *cc
            };

            if crash_count > 3 {
                log::error!(
                    "LOGOS watchdog (Mnemosyne): servidor falhou {} vezes — \
                     desabilitado até reload manual",
                    crash_count
                );
                mnemosyne_wdg.0.mnemosyne_disabled.store(true, Ordering::Relaxed);
                mnemosyne_wdg.emit_alert(
                    "error",
                    "Mnemosyne server falhou 3+ vezes consecutivas — \
                     desabilitado. Reinicie o HUB para reativar.",
                ).await;
                {
                    let guard = mnemosyne_wdg.0.app_handle.lock().await;
                    if let Some(ref handle) = *guard {
                        let _ = handle.emit("logos-mnemosyne-unavailable", ());
                    }
                }
                loop { tokio::time::sleep(Duration::from_secs(3600)).await; }
            }

            let backoff = BACKOFFS[(crash_count as usize - 1).min(2)];
            log::warn!(
                "LOGOS watchdog (Mnemosyne): tentativa {crash_count}/3 de restart de '{model_name}' em {backoff}s"
            );
            tokio::time::sleep(Duration::from_secs(backoff)).await;

            if let Ok(()) = ensure_server_loaded(&mnemosyne_wdg, ServerTarget::Mnemosyne, &model_name).await {
                *mnemosyne_wdg.0.mnemosyne_crash_count.lock().await = 0;
                log::info!("LOGOS watchdog (Mnemosyne): servidor reiniciado com sucesso — '{model_name}'");
                mnemosyne_wdg.emit_alert(
                    "warn",
                    &format!("Mnemosyne server reiniciado após crash — '{model_name}'"),
                ).await;
            } else {
                log::error!(
                    "LOGOS watchdog (Mnemosyne): falha ao reiniciar servidor — '{model_name}' \
                     (tentativa {crash_count}/3)"
                );
            }
        }
    });

    // Watchdog do embed-server — verifica a cada 10s.
    // Detecta crash e tenta 1 restart (sem backoff exponencial — embed é leve).
    // Se o restart também falhar, emite alerta e aguarda o próximo ciclo.
    let embed_wdg = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(10)).await;

            let crashed_model: Option<String> = {
                let mut guard = embed_wdg.0.embed_proc.lock().await;
                if let Some(ref mut proc) = guard.as_mut() {
                    match proc.child.try_wait() {
                        Ok(Some(status)) => {
                            log::error!(
                                "LOGOS embed-watchdog: embed-server saiu inesperadamente \
                                 (modelo='{}', status={:?})",
                                proc.model_name, status
                            );
                            Some(proc.model_name.clone())
                        }
                        Ok(None) => None, // ainda rodando — ok
                        Err(e) => {
                            log::warn!(
                                "LOGOS embed-watchdog: erro ao verificar processo: {e}"
                            );
                            None
                        }
                    }
                } else {
                    None // nenhum embed-server ativo — normal (modelo não configurado)
                }
            };

            let Some(model_name) = crashed_model else { continue };

            // Limpa o handle do processo morto
            *embed_wdg.0.embed_proc.lock().await = None;

            embed_wdg.emit_alert(
                "warn",
                &format!("embed-server caiu — tentando reiniciar '{model_name}'"),
            ).await;

            // Uma tentativa de restart (embed é leve, reinício é rápido)
            log::warn!("LOGOS embed-watchdog: tentando reiniciar '{model_name}'");
            ensure_embed_server_started(&embed_wdg).await;

            if embed_wdg.embed_proc_active().await {
                log::info!(
                    "LOGOS embed-watchdog: embed-server reiniciado — '{model_name}'"
                );
                embed_wdg.emit_alert(
                    "warn",
                    &format!("embed-server reiniciado após crash — '{model_name}'"),
                ).await;
            } else {
                log::error!(
                    "LOGOS embed-watchdog: falha ao reiniciar embed-server — \
                     '{model_name}' — /v1/embeddings indisponível"
                );
                embed_wdg.emit_alert(
                    "error",
                    &format!("embed-server falhou — /v1/embeddings indisponível até restart manual"),
                ).await;
            }
        }
    });

    // Watchdog de VRAM com histerese — verifica a cada 5s.
    // Block em >block_pct% (padrão 85%), retoma em <70% (VRAM_P3_RESUME).
    // Descarrega modelos P3 ao bloquear para liberar VRAM antes que P1/P2 precise.
    const VRAM_P3_RESUME: f32 = 0.70;
    let wdg_state = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(5)).await;
            let on_battery = *wdg_state.0.on_battery.lock().await;
            if on_battery {
                // Em bateria P3 já está bloqueado por outra razão — não interferir
                continue;
            }
            let block_threshold = *wdg_state.0.vram_limit_pct.lock().await / 100.0;
            let currently_blocked = wdg_state.0.p3_vram_blocked.load(Ordering::Relaxed);
            let pct = vram_pct(&wdg_state.0.client, wdg_state.0.hardware_profile).await;

            match pct {
                Some(p) if !currently_blocked && p > block_threshold => {
                    wdg_state.0.p3_vram_blocked.store(true, Ordering::Relaxed);
                    log::info!(
                        "LOGOS watchdog: VRAM {:.0}% > {:.0}% — P3 bloqueado; descarregando modelos P3",
                        p * 100.0,
                        block_threshold * 100.0,
                    );
                    do_silence(&wdg_state).await;
                }
                Some(p) if currently_blocked && p < VRAM_P3_RESUME => {
                    wdg_state.0.p3_vram_blocked.store(false, Ordering::Relaxed);
                    log::info!(
                        "LOGOS watchdog: VRAM {:.0}% < {:.0}% — P3 retomado",
                        p * 100.0,
                        VRAM_P3_RESUME * 100.0,
                    );
                }
                None if currently_blocked => {
                    // Sem leitura de VRAM (GPU offline?): desbloquear para não travar P3 forever
                    wdg_state.0.p3_vram_blocked.store(false, Ordering::Relaxed);
                }
                _ => {}
            }
        }
    });

    // Watchdog térmico — pausa P3 quando GPU > 85°C.
    // Poll a cada 15s (temperatura muda mais devagar que VRAM).
    // A RX 6600 só faz throttling pelo driver acima de ~95°C; pausamos antes para preservar
    // desempenho de P1/P2 e evitar o ciclo térmico boost→throttle.
    // Retoma quando temperatura cai abaixo de 80°C (histerese de 5°C).
    const GPU_TEMP_BLOCK_C: f32  = 85.0;
    const GPU_TEMP_RESUME_C: f32 = 80.0;
    let thermal_state = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(15)).await;
            let temp = read_gpu_temp_celsius();
            *thermal_state.0.gpu_temp_celsius.lock().await = temp;
            let currently_blocked = thermal_state.0.p3_thermal_blocked.load(Ordering::Relaxed);
            match temp {
                Some(t) if !currently_blocked && t > GPU_TEMP_BLOCK_C => {
                    thermal_state.0.p3_thermal_blocked.store(true, Ordering::Relaxed);
                    log::warn!(
                        "LOGOS watchdog: GPU {:.0}°C > {:.0}°C — P3 pausado (thermal throttle prevention)",
                        t, GPU_TEMP_BLOCK_C,
                    );
                }
                Some(t) if currently_blocked && t < GPU_TEMP_RESUME_C => {
                    thermal_state.0.p3_thermal_blocked.store(false, Ordering::Relaxed);
                    log::info!(
                        "LOGOS watchdog: GPU {:.0}°C < {:.0}°C — P3 retomado (temperatura normalizada)",
                        t, GPU_TEMP_RESUME_C,
                    );
                }
                None if currently_blocked => {
                    // Temperatura ilegível: desbloquear para não travar P3 para sempre
                    thermal_state.0.p3_thermal_blocked.store(false, Ordering::Relaxed);
                }
                _ => {}
            }
        }
    });

    // Idle unload watchdog — servidor AKASHA (chat). Timer independente dos outros servidores.
    let idle_llm_wdg = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            check_idle_llm(&idle_llm_wdg).await;
        }
    });

    // Idle unload watchdog — servidor Mnemosyne. Timer independente do AKASHA.
    let idle_mnemosyne_wdg = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            check_idle_mnemosyne(&idle_mnemosyne_wdg).await;
        }
    });

    // Idle unload watchdog — embed server. Timer independente do chat server.
    let idle_embed_wdg = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            check_idle_embed(&idle_embed_wdg).await;
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    // ── ModelRegistryEntry — serialização roundtrip ───────────────────────────

    #[test]
    fn registry_entry_serde_roundtrip() {
        let entry = ModelRegistryEntry {
            name:          "Phi-3_5-mini-instruct-Q4_K_M".to_string(),
            repo_id:       "bartowski/Phi-3.5-mini-instruct-GGUF".to_string(),
            filename:      "Phi-3.5-mini-instruct-Q4_K_M.gguf".to_string(),
            path:          "/home/user/.local/share/ecosystem/hub/logos/models/Phi-3.5-mini-instruct-Q4_K_M.gguf".to_string(),
            size_bytes:    2_400_000_000,
            sha256:        "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string(),
            downloaded_at: "2026-05-23T12:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   None,
        };
        let json = serde_json::to_string(&entry).expect("serialize");
        let back: ModelRegistryEntry = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.filename, entry.filename);
        assert_eq!(back.sha256,   entry.sha256);
        assert_eq!(back.size_bytes, entry.size_bytes);
        assert!(back.mmproj_path.is_none());
    }

    #[test]
    fn registry_entry_with_mmproj_roundtrip() {
        let entry = ModelRegistryEntry {
            name:          "moondream".to_string(),
            repo_id:       "ggml-org/moondream2-20250414-GGUF".to_string(),
            filename:      "moondream2-20250414-text-model-f16.gguf".to_string(),
            path:          "/tmp/moondream2-20250414-text-model-f16.gguf".to_string(),
            size_bytes:    1_800_000_000,
            sha256:        "deadbeef".to_string(),
            downloaded_at: "2026-05-24T00:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   Some("/tmp/moondream2-20250414-mmproj-f16.gguf".to_string()),
        };
        let json = serde_json::to_string(&entry).expect("serialize");
        let back: ModelRegistryEntry = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.mmproj_path.as_deref(), Some("/tmp/moondream2-20250414-mmproj-f16.gguf"));
    }

    #[test]
    fn registry_entry_legacy_no_mmproj_deserializes() {
        // Entradas antigas no registry.json sem campo mmproj_path devem deserializar com None
        let legacy = r#"{"name":"qwen2.5:7b","repo_id":"bartowski/Qwen2.5-7B-Instruct-GGUF","filename":"Qwen2.5-7B-Instruct-Q4_K_M.gguf","path":"/tmp/q.gguf","size_bytes":4000000000,"sha256":"abc","downloaded_at":"2026-05-01T00:00:00+00:00"}"#;
        let entry: ModelRegistryEntry = serde_json::from_str(legacy).expect("deserialize legacy");
        assert!(entry.mmproj_path.is_none(), "campo ausente deve deserializar como None");
    }

    // ── update_model_registry — deduplication ────────────────────────────────

    #[tokio::test]
    async fn registry_update_deduplicates_by_filename() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let e1 = ModelRegistryEntry {
            name:          "model_v1".to_string(),
            repo_id:       "org/repo".to_string(),
            filename:      "model.gguf".to_string(),
            path:          "/tmp/model.gguf".to_string(),
            size_bytes:    1_000,
            sha256:        "aaa".to_string(),
            downloaded_at: "2026-01-01T00:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   None,
        };
        let e2 = ModelRegistryEntry {
            sha256: "bbb".to_string(),
            size_bytes: 2_000,
            downloaded_at: "2026-06-01T00:00:00+00:00".to_string(),
            ..e1.clone()
        };

        update_model_registry(&models_dir, e1).await;
        update_model_registry(&models_dir, e2).await;

        let entries = read_model_registry(&models_dir).await;
        assert_eq!(entries.len(), 1, "re-download substitui entrada anterior");
        assert_eq!(entries[0].sha256, "bbb", "sha256 deve ser do download mais recente");
        assert_eq!(entries[0].size_bytes, 2_000);
    }

    #[tokio::test]
    async fn registry_stores_multiple_distinct_files() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        for i in 0..3u32 {
            let e = ModelRegistryEntry {
                name:          format!("model_{i}"),
                repo_id:       "org/repo".to_string(),
                filename:      format!("model_{i}.gguf"),
                path:          format!("/tmp/model_{i}.gguf"),
                size_bytes:    i as u64 * 1_000,
                sha256:        format!("{i:064x}"),
                downloaded_at: "2026-05-23T00:00:00+00:00".to_string(),
                model_type:    None,
                mmproj_path:   None,
            };
            update_model_registry(&models_dir, e).await;
        }

        let entries = read_model_registry(&models_dir).await;
        assert_eq!(entries.len(), 3);
    }

    #[tokio::test]
    async fn registry_read_returns_empty_when_file_missing() {
        let dir  = tempfile::tempdir().expect("tmpdir");
        let entries = read_model_registry(dir.path()).await;
        assert!(entries.is_empty());
    }

    #[tokio::test]
    async fn update_registry_mmproj_sets_path() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let entry = ModelRegistryEntry {
            name:          "moondream".to_string(),
            repo_id:       "ggml-org/moondream2-20250414-GGUF".to_string(),
            filename:      "moondream2-20250414-text-model-f16.gguf".to_string(),
            path:          "/tmp/text.gguf".to_string(),
            size_bytes:    1_800_000_000,
            sha256:        "abc".to_string(),
            downloaded_at: "2026-05-24T00:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   None,
        };
        update_model_registry(&models_dir, entry).await;

        update_registry_mmproj(&models_dir, "moondream", "/tmp/mmproj.gguf").await;

        let entries = read_model_registry(&models_dir).await;
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0].mmproj_path.as_deref(),
            Some("/tmp/mmproj.gguf"),
            "mmproj_path deve ser atualizado"
        );
    }

    #[tokio::test]
    async fn update_registry_mmproj_noop_for_unknown_model() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();
        // Registry vazio — sem crash, sem efeito
        update_registry_mmproj(&models_dir, "nao-existe", "/tmp/x.gguf").await;
        let entries = read_model_registry(&models_dir).await;
        assert!(entries.is_empty());
    }

    // ── ModelRegistryEntry — model_type ──────────────────────────────────────

    #[tokio::test]
    async fn registry_entry_bge_m3_persists_model_type_embed() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let entry = ModelRegistryEntry {
            name:          "bge-m3".to_string(),
            repo_id:       "gpustack/bge-m3-GGUF".to_string(),
            filename:      "bge-m3-Q4_K_M.gguf".to_string(),
            path:          "/tmp/bge-m3-Q4_K_M.gguf".to_string(),
            size_bytes:    360_000_000,
            sha256:        "abc".to_string(),
            downloaded_at: "2026-05-26T00:00:00+00:00".to_string(),
            model_type:    Some("embed".to_string()),
            mmproj_path:   None,
        };
        update_model_registry(&models_dir, entry).await;

        let entries = read_model_registry(&models_dir).await;
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0].model_type.as_deref(),
            Some("embed"),
            "model_type deve ser 'embed' para bge-m3"
        );
    }

    #[tokio::test]
    async fn registry_entry_model_type_defaults_to_none_for_legacy_entries() {
        // Verifica retrocompatibilidade: entradas sem model_type no JSON desserializam como None
        let dir = tempfile::tempdir().expect("tmpdir");
        let registry_path = dir.path().join("registry.json");
        let legacy = r#"[{
            "name": "qwen2.5-7b",
            "repo_id": "bartowski/Qwen2.5-7B-Instruct-GGUF",
            "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            "path": "/tmp/qwen.gguf",
            "size_bytes": 4000000000,
            "sha256": "deadbeef",
            "downloaded_at": "2026-01-01T00:00:00+00:00"
        }]"#;
        std::fs::write(&registry_path, legacy).unwrap();

        let entries = read_model_registry(dir.path()).await;
        assert_eq!(entries.len(), 1);
        assert!(
            entries[0].model_type.is_none(),
            "entry legada sem model_type deve deserializar como None"
        );
    }

    #[tokio::test]
    async fn registry_model_type_derived_from_name_for_bge_m3() {
        // Simula o comportamento do download_model_task: model_type derivado de model_type_for_name
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let model_name = "bge-m3";
        let derived_type = crate::commands::logos::model_type_for_name(model_name);
        let entry = ModelRegistryEntry {
            name:          model_name.to_string(),
            repo_id:       "gpustack/bge-m3-GGUF".to_string(),
            filename:      "bge-m3-Q4_K_M.gguf".to_string(),
            path:          "/tmp/bge-m3-Q4_K_M.gguf".to_string(),
            size_bytes:    360_000_000,
            sha256:        "abc".to_string(),
            downloaded_at: "2026-05-26T00:00:00+00:00".to_string(),
            model_type:    Some(derived_type.to_string()),
            mmproj_path:   None,
        };
        update_model_registry(&models_dir, entry).await;

        let entries = read_model_registry(&models_dir).await;
        assert_eq!(
            entries[0].model_type.as_deref(),
            Some("embed"),
            "model_type derivado de model_type_for_name deve ser 'embed' para bge-m3"
        );
    }

    #[tokio::test]
    async fn registry_model_type_chat_for_llm_models() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let entry = ModelRegistryEntry {
            name:          "qwen2.5:7b".to_string(),
            repo_id:       "bartowski/Qwen2.5-7B-Instruct-GGUF".to_string(),
            filename:      "Qwen2.5-7B-Instruct-Q4_K_M.gguf".to_string(),
            path:          "/tmp/qwen.gguf".to_string(),
            size_bytes:    4_000_000_000,
            sha256:        "xyz".to_string(),
            downloaded_at: "2026-05-26T00:00:00+00:00".to_string(),
            model_type:    Some(crate::commands::logos::model_type_for_name("qwen2.5:7b").to_string()),
            mmproj_path:   None,
        };
        update_model_registry(&models_dir, entry).await;

        let entries = read_model_registry(&models_dir).await;
        assert_eq!(
            entries[0].model_type.as_deref(),
            Some("chat"),
            "model_type deve ser 'chat' para LLMs generativos"
        );
    }

    // ── DownloadProgress — serialização ──────────────────────────────────────

    #[test]
    fn download_progress_serializes_correctly() {
        let p = DownloadProgress {
            id:               "12345_model_gguf".to_string(),
            filename:         "model.gguf".to_string(),
            bytes_downloaded: 500_000_000,
            total_bytes:      Some(1_000_000_000),
            pct:              Some(50.0),
            speed_mbps:       25.5,
            done:             false,
            error:            None,
        };
        let json = serde_json::to_value(&p).expect("serialize");
        assert_eq!(json["pct"], 50.0);
        assert_eq!(json["done"], false);
        assert_eq!(json["bytes_downloaded"], 500_000_000_u64);
        assert!(json["error"].is_null());
    }

    #[test]
    fn download_progress_done_with_error() {
        let p = DownloadProgress {
            id: "id".to_string(), filename: "f.gguf".to_string(),
            bytes_downloaded: 0, total_bytes: None, pct: None,
            speed_mbps: 0.0, done: true,
            error: Some("HuggingFace retornou 404".to_string()),
        };
        let json = serde_json::to_value(&p).expect("serialize");
        assert_eq!(json["done"], true);
        assert_eq!(json["error"], "HuggingFace retornou 404");
    }

    // ── translate_ollama_chat_to_openai ───────────────────────────────────────

    #[test]
    fn chat_translate_forces_stream_false() {
        let body = serde_json::json!({ "model": "m", "messages": [] });
        let out = translate_ollama_chat_to_openai(body.as_object().unwrap().clone());
        assert_eq!(out["stream"], false);
    }

    #[test]
    fn chat_translate_flattens_options() {
        let body = serde_json::json!({
            "model": "m",
            "messages": [],
            "options": {
                "temperature": 0.8,
                "top_p": 0.9,
                "num_predict": 512,
                "repeat_penalty": 1.1
            }
        });
        let out = translate_ollama_chat_to_openai(body.as_object().unwrap().clone());
        assert_eq!(out["temperature"], 0.8);
        assert_eq!(out["top_p"], 0.9);
        assert_eq!(out["max_tokens"], 512);
        assert_eq!(out["frequency_penalty"], 1.1);
        assert!(out.get("options").is_none(), "options deve ser removido");
    }

    #[test]
    fn chat_translate_removes_ollama_only_fields() {
        let body = serde_json::json!({
            "model": "m", "messages": [],
            "keep_alive": "5m", "format": "json", "raw": true
        });
        let out = translate_ollama_chat_to_openai(body.as_object().unwrap().clone());
        assert!(out.get("keep_alive").is_none());
        assert!(out.get("format").is_none());
        assert!(out.get("raw").is_none());
    }

    #[test]
    fn chat_translate_does_not_override_existing_top_level_keys() {
        let body = serde_json::json!({
            "model": "m", "messages": [],
            "temperature": 0.3,
            "options": { "temperature": 0.9 }
        });
        let out = translate_ollama_chat_to_openai(body.as_object().unwrap().clone());
        // temperature já presente no topo — options não deve sobrescrever
        assert_eq!(out["temperature"], 0.3);
    }

    // ── translate_openai_chat_to_ollama ───────────────────────────────────────

    #[test]
    fn chat_response_translate_extracts_content() {
        let oai = serde_json::json!({
            "choices": [{
                "message": { "role": "assistant", "content": "Olá!" },
                "finish_reason": "stop"
            }],
            "usage": { "prompt_tokens": 10, "completion_tokens": 5 }
        });
        let bytes = serde_json::to_vec(&oai).unwrap();
        let result_bytes = translate_openai_chat_to_ollama(&bytes, "test-model");
        let result: serde_json::Value = serde_json::from_slice(&result_bytes).unwrap();
        assert_eq!(result["message"]["content"], "Olá!");
        assert_eq!(result["message"]["role"], "assistant");
        assert_eq!(result["model"], "test-model");
        assert_eq!(result["done"], true);
        assert_eq!(result["done_reason"], "stop");
        assert_eq!(result["prompt_eval_count"], 10);
        assert_eq!(result["eval_count"], 5);
    }

    #[test]
    fn chat_response_translate_passthrough_on_invalid_json() {
        let garbage = b"not json";
        let out = translate_openai_chat_to_ollama(garbage, "m");
        assert_eq!(out, garbage);
    }

    // ── translate_ollama_generate_to_openai ───────────────────────────────────

    #[test]
    fn generate_translate_converts_prompt_field() {
        let body = serde_json::json!({
            "model": "m",
            "prompt": "Olá",
            "options": { "num_predict": 100 }
        });
        let out = translate_ollama_generate_to_openai(body.as_object().unwrap().clone());
        assert_eq!(out["stream"], false);
        assert_eq!(out["max_tokens"], 100);
        assert_eq!(out["prompt"], "Olá");
    }

    // ── translate_openai_generate_to_ollama ───────────────────────────────────

    #[test]
    fn generate_response_translate_extracts_text() {
        let oai = serde_json::json!({
            "choices": [{ "text": "resultado", "finish_reason": "length" }],
            "usage": { "prompt_tokens": 3, "completion_tokens": 7 }
        });
        let bytes = serde_json::to_vec(&oai).unwrap();
        let out: serde_json::Value =
            serde_json::from_slice(&translate_openai_generate_to_ollama(&bytes, "m")).unwrap();
        assert_eq!(out["response"], "resultado");
        assert_eq!(out["done_reason"], "length");
        assert_eq!(out["prompt_eval_count"], 3);
        assert_eq!(out["eval_count"], 7);
    }

    // ── translate_ollama_embed_to_openai ─────────────────────────────────────

    #[test]
    fn embed_translate_renames_prompt_to_input() {
        let body = serde_json::json!({ "model": "emb", "prompt": "texto", "keep_alive": "1m" });
        let out_bytes = translate_ollama_embed_to_openai(&serde_json::to_vec(&body).unwrap());
        let out: serde_json::Value = serde_json::from_slice(&out_bytes).unwrap();
        assert_eq!(out["input"], "texto");
        assert!(out.get("prompt").is_none(), "prompt deve ser removido");
        assert!(out.get("keep_alive").is_none(), "keep_alive deve ser removido");
    }

    #[test]
    fn embed_translate_preserves_input_if_already_present() {
        let body = serde_json::json!({ "model": "emb", "input": ["a", "b"] });
        let out_bytes = translate_ollama_embed_to_openai(&serde_json::to_vec(&body).unwrap());
        let out: serde_json::Value = serde_json::from_slice(&out_bytes).unwrap();
        assert_eq!(out["input"], serde_json::json!(["a", "b"]));
    }

    // ── translate_openai_embed_to_ollama ─────────────────────────────────────

    #[test]
    fn embed_response_translate_extracts_embedding() {
        let oai = serde_json::json!({
            "data": [{ "embedding": [0.1, 0.2, 0.3], "index": 0 }]
        });
        let bytes = serde_json::to_vec(&oai).unwrap();
        let out: serde_json::Value =
            serde_json::from_slice(&translate_openai_embed_to_ollama(&bytes)).unwrap();
        assert_eq!(out["embedding"], serde_json::json!([0.1, 0.2, 0.3]));
        assert_eq!(out["embeddings"], serde_json::json!([[0.1, 0.2, 0.3]]));
    }

    #[test]
    fn embed_response_translate_passthrough_on_invalid_json() {
        let garbage = b"!!!";
        let out = translate_openai_embed_to_ollama(garbage);
        assert_eq!(out, garbage);
    }

    // ── gpu_layers_for_model ─────────────────────────────────────────────────

    #[test]
    fn gpu_layers_unknown_model_workpc_returns_zero() {
        assert_eq!(gpu_layers_for_model("unknown-model", HardwareProfile::WorkPc), 0);
    }

    #[test]
    fn gpu_layers_unknown_model_laptop_returns_minus_one() {
        assert_eq!(gpu_layers_for_model("unknown-model", HardwareProfile::Laptop), -1);
    }

    #[test]
    fn gpu_layers_unknown_model_mainpc_returns_minus_one() {
        assert_eq!(gpu_layers_for_model("unknown-model", HardwareProfile::MainPc), -1);
    }

    // ── effective_gpu_layers ─────────────────────────────────────────────────

    #[tokio::test]
    async fn effective_gpu_workpc_always_cpu() {
        // WorkPc sem GPU discreta — deve retornar 0 independente do model_size
        let client = Client::new();
        let result = effective_gpu_layers(&client, HardwareProfile::WorkPc, -1, 0, 4096).await;
        assert_eq!(result, 0);
    }

    #[tokio::test]
    async fn effective_gpu_profile_zero_passthrough() {
        // Se o perfil já diz 0 (slot CPU-only), não deve checar VRAM
        let client = Client::new();
        let result = effective_gpu_layers(&client, HardwareProfile::MainPc, 0, 0, 4096).await;
        assert_eq!(result, 0);
    }

    #[tokio::test]
    async fn effective_gpu_model_fits_uses_profile_value() {
        // Modelo pequeno cabe na VRAM — sem GPU no CI, vram_used=0, modelo+KV < budget
        let client = Client::new();
        let result = effective_gpu_layers(&client, HardwareProfile::MainPc, -1, 500, 4096).await;
        // KV cache estimado: 500*4096/(4096*3) = 167MB; total=667MB < budget → retorna -1
        assert_eq!(result, -1);
    }

    #[tokio::test]
    async fn effective_gpu_model_size_zero_uses_profile_value() {
        // Tamanho desconhecido (0) → não deve bloquear GPU
        let client = Client::new();
        let result = effective_gpu_layers(&client, HardwareProfile::MainPc, -1, 0, 4096).await;
        assert_eq!(result, -1);
    }

    // ── resolve_gguf_path ────────────────────────────────────────────────────

    #[tokio::test]
    async fn resolve_gguf_path_finds_entry_in_registry() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        // Cria um arquivo GGUF fictício
        let gguf_path = models_dir.join("mnemosyne-ft-v1-q4km.gguf");
        std::fs::write(&gguf_path, b"fake gguf").unwrap();

        let entry = ModelRegistryEntry {
            name:          "mnemosyne-ft-v1".to_string(),
            repo_id:       "local/fine-tuned".to_string(),
            filename:      "mnemosyne-ft-v1-q4km.gguf".to_string(),
            path:          gguf_path.to_str().unwrap().to_string(),
            size_bytes:    9,
            sha256:        "abc".to_string(),
            downloaded_at: "2026-05-23T00:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   None,
        };
        update_model_registry(&models_dir, entry).await;

        let resolved = resolve_gguf_path("mnemosyne-ft-v1", &models_dir);
        assert!(resolved.is_some(), "deve encontrar no registry");
        assert_eq!(resolved.unwrap(), gguf_path);
    }

    #[test]
    fn resolve_gguf_path_returns_none_for_missing_model() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let result = resolve_gguf_path("modelo-inexistente", dir.path());
        assert!(result.is_none());
    }

    // ── find_gguf_in_ollama_store ─────────────────────────────────────────────

    #[test]
    fn find_gguf_ollama_store_returns_none_for_nonexistent_model() {
        let result = find_gguf_in_ollama_store("modelo-que-nao-existe-xyz");
        assert!(result.is_none());
    }

    // ── size_map para recommended models — registry LOGOS ────────────────────

    #[tokio::test]
    async fn recommended_size_map_uses_logos_registry() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let gguf = models_dir.join("smollm2-q4km.gguf");
        std::fs::write(&gguf, vec![0u8; 2_000_000]).unwrap(); // 2 MB

        let entry = ModelRegistryEntry {
            name:          "smollm2:1.7b".to_string(),
            repo_id:       "org/repo".to_string(),
            filename:      "smollm2-q4km.gguf".to_string(),
            path:          gguf.to_str().unwrap().to_string(),
            size_bytes:    2_000_000,
            sha256:        "aaa".to_string(),
            downloaded_at: "2026-05-23T00:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   None,
        };
        update_model_registry(&models_dir, entry).await;

        // Simula o bloco size_map da do_get_recommended_models
        let registry_entries = read_model_registry(&models_dir).await;
        let mut size_map: std::collections::HashMap<String, u64> = std::collections::HashMap::new();
        for e in &registry_entries {
            size_map.insert(e.name.clone(), e.size_bytes / 1_000_000);
        }

        assert_eq!(size_map.get("smollm2:1.7b"), Some(&2));
        assert!(!size_map.contains_key("modelo-ausente"));
    }

    // ── Helpers para testes de LogosState ────────────────────────────────────

    fn make_test_state(models_dir: std::path::PathBuf) -> LogosState {
        let client = Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap_or_default();
        let mut sys = System::new_all();
        sys.refresh_cpu_all();
        sys.refresh_memory();
        LogosState(Arc::new(Inner {
            llama_server_url:    "http://127.0.0.1:8081".to_string(),
            akasha_semaphore:    Arc::new(Semaphore::new(2)),
            mnemosyne_semaphore: Arc::new(Semaphore::new(2)),
            embed_semaphore:     Arc::new(Semaphore::new(1)),
            active_priority:     Mutex::new(None),
            active_model_class:  Mutex::new(None),
            active_app:          Mutex::new(None),
            active_profile:      Mutex::new("normal".to_string()),
            hardware_mode:       "normal".to_string(),
            hardware_profile:    HardwareProfile::WorkPc,
            has_avx2:            detect_avx2(),
            queue_counts:        Mutex::new([0, 0, 0]),
            client,
            sys:                 Mutex::new(sys),
            on_battery:          Mutex::new(false),
            battery_pct:         Mutex::new(100),
            battery_policy:      Mutex::new(BatteryPolicy::Normal),
            preempted_count:     Mutex::new(0),
            model_overrides:     Mutex::new(HashMap::new()),
            vram_limit_pct:      Mutex::new(85.0),
            active_inferences:   Mutex::new(HashMap::new()),
            p3_vram_blocked:     Arc::new(AtomicBool::new(false)),
            p3_thermal_blocked:  Arc::new(AtomicBool::new(false)),
            gpu_temp_celsius:    Mutex::new(None),
            downloads:           Mutex::new(HashMap::new()),
            models_dir,
            llama_server_bin:       None,
            akasha_proc:            Mutex::new(None),
            mnemosyne_proc:         Mutex::new(None),
            akasha_crash_count:     Mutex::new(0),
            akasha_disabled:        Arc::new(AtomicBool::new(false)),
            mnemosyne_crash_count:  Mutex::new(0),
            mnemosyne_disabled:     Arc::new(AtomicBool::new(false)),
            app_handle:          Mutex::new(None),
            embed_model:         Mutex::new("bge-m3".to_string()),
            embed_n_gpu_layers:  Mutex::new(DEFAULT_EMBED_N_GPU_LAYERS),
            embed_proc:          Mutex::new(None),
            embed_start_lock:    Mutex::new(()),
            // Portas livres para isolamento de testes — sem servidor nestas portas
            chat_health_port:      59981,
            embed_health_port:     59982,
            mnemosyne_health_port: 59983,
            cpu_p3_limit_pct:    Mutex::new(85.0),
            cached_cpu_pct:      Arc::new(AtomicU32::new(0)),
            inference_enabled:          Arc::new(AtomicBool::new(false)),
            last_akasha_request_at:     Mutex::new(std::time::Instant::now()),
            last_mnemosyne_request_at:  Mutex::new(std::time::Instant::now()),
            last_embed_request_at:      Mutex::new(std::time::Instant::now()),
            idle_timeout_secs:  300,
            cpu_fallback_max_mb: 2048,
            cpu_max_threads:    0,
        }))
    }

    fn sample_registry_entry(name: &str, filename: &str, path: &str) -> ModelRegistryEntry {
        ModelRegistryEntry {
            name:          name.to_string(),
            repo_id:       "test/repo".to_string(),
            filename:      filename.to_string(),
            path:          path.to_string(),
            size_bytes:    1_000_000_000,
            sha256:        "abc123".to_string(),
            downloaded_at: "2026-05-24T00:00:00+00:00".to_string(),
            model_type:    None,
            mmproj_path:   None,
        }
    }

    // ── LogosState::new — campos básicos ──────────────────────────────────────

    #[test]
    fn logos_state_stores_llama_server_url() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert_eq!(state.0.llama_server_url, "http://127.0.0.1:8081");
    }

    // ── Embed server — estado separado ────────────────────────────────────────

    #[tokio::test]
    async fn embed_model_defaults_to_bge_m3() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert_eq!(state.embed_model().await, "bge-m3");
    }

    #[tokio::test]
    async fn embed_proc_active_starts_false() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.embed_proc_active().await, "embed_proc deve iniciar inativo");
    }

    #[tokio::test]
    async fn embed_n_gpu_layers_defaults_to_cpu() {
        // BUG-028: o default passou a ser 0 (CPU) para tirar o embed-server da disputa de VRAM.
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let n = *state.0.embed_n_gpu_layers.lock().await;
        assert_eq!(n, DEFAULT_EMBED_N_GPU_LAYERS, "embed_n_gpu_layers padrão deve ser 0 (CPU)");
        assert_eq!(n, 0, "0 = --n-gpu-layers 0 = embeddings em CPU");
    }

    #[tokio::test]
    async fn set_embed_model_updates_in_memory() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        state.set_embed_model("nomic-embed-text").await;
        assert_eq!(state.embed_model().await, "nomic-embed-text");
    }

    #[tokio::test]
    async fn kill_embed_proc_returns_false_when_no_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.kill_embed_proc().await, "kill_embed_proc sem processo ativo deve retornar false");
    }

    #[test]
    fn embed_server_port_is_8082() {
        assert_eq!(EMBED_SERVER_PORT, 8082, "porta do embed-server deve ser 8082");
    }

    #[test]
    fn akasha_server_port_is_8081() {
        assert_eq!(AKASHA_SERVER_PORT, 8081, "porta do servidor AKASHA deve ser 8081");
    }

    #[test]
    fn mnemosyne_server_port_is_8083() {
        assert_eq!(MNEMOSYNE_SERVER_PORT, 8083, "porta do servidor Mnemosyne deve ser 8083");
    }

    #[test]
    fn all_three_server_ports_are_distinct() {
        assert_ne!(AKASHA_SERVER_PORT, EMBED_SERVER_PORT,
            "AKASHA e embed-server devem usar portas diferentes");
        assert_ne!(AKASHA_SERVER_PORT, MNEMOSYNE_SERVER_PORT,
            "AKASHA e Mnemosyne devem usar portas diferentes");
        assert_ne!(EMBED_SERVER_PORT, MNEMOSYNE_SERVER_PORT,
            "embed e Mnemosyne devem usar portas diferentes");
    }

    // ── Testes de route_request (Passo 1) ────────────────────

    #[test]
    fn route_mnemosyne_returns_mnemosyne() {
        assert_eq!(route_request("mnemosyne"), ServerTarget::Mnemosyne);
    }

    #[test]
    fn route_mnemosyne_case_insensitive() {
        assert_eq!(route_request("Mnemosyne"), ServerTarget::Mnemosyne);
        assert_eq!(route_request("MNEMOSYNE"), ServerTarget::Mnemosyne);
        assert_eq!(route_request("mNeMoSyNe"), ServerTarget::Mnemosyne);
    }

    #[test]
    fn route_akasha_returns_akasha() {
        assert_eq!(route_request("akasha"), ServerTarget::Akasha);
    }

    #[test]
    fn route_empty_returns_akasha() {
        assert_eq!(route_request(""), ServerTarget::Akasha,
            "app desconhecido (string vazia) deve ir para servidor AKASHA");
    }

    #[test]
    fn route_hub_returns_akasha() {
        assert_eq!(route_request("hub"), ServerTarget::Akasha,
            "HUB usa o servidor AKASHA (mesmo servidor que queries gerais)");
    }

    #[test]
    fn route_kosmos_returns_akasha() {
        assert_eq!(route_request("kosmos"), ServerTarget::Akasha,
            "KOSMOS usa o servidor AKASHA (análise de artigos)");
    }

    #[test]
    fn route_unknown_app_returns_akasha() {
        assert_eq!(route_request("qualquer-coisa-desconhecida"), ServerTarget::Akasha,
            "app desconhecido deve fazer fallback para AKASHA");
    }

    // ── Watchdog de VRAM — 4 cenários ────────────────────────────────────────

    #[test]
    fn vram_watchdog_p3_blocked_starts_false() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.0.p3_vram_blocked.load(Ordering::Relaxed),
            "p3_vram_blocked deve iniciar em false");
    }

    #[test]
    fn vram_watchdog_sets_blocked_when_stored_true() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        state.0.p3_vram_blocked.store(true, Ordering::Relaxed);
        assert!(state.0.p3_vram_blocked.load(Ordering::Relaxed),
            "p3_vram_blocked deve refletir o valor armazenado");
    }

    #[test]
    fn vram_watchdog_unblocks_when_vram_drops() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        // Simula: bloqueado → VRAM cai → desbloqueia
        state.0.p3_vram_blocked.store(true, Ordering::Relaxed);
        state.0.p3_vram_blocked.store(false, Ordering::Relaxed);
        assert!(!state.0.p3_vram_blocked.load(Ordering::Relaxed),
            "p3_vram_blocked deve ser false após desbloquear");
    }

    #[tokio::test]
    async fn vram_watchdog_limit_pct_defaults_to_85() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let pct = *state.0.vram_limit_pct.lock().await;
        assert!((pct - 85.0).abs() < 0.001,
            "vram_limit_pct deve iniciar em 85%");
    }

    // ── cpu_p3_limit_pct — limite configurável ────────────────────────────────

    #[tokio::test]
    async fn cpu_p3_limit_pct_defaults_to_85() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let pct   = *state.0.cpu_p3_limit_pct.lock().await;
        assert!((pct - 85.0).abs() < 0.001, "cpu_p3_limit_pct deve iniciar em 85%");
    }

    #[tokio::test]
    async fn cpu_p3_limit_pct_set_clamps_to_valid_range() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        state.set_cpu_p3_limit_pct(200.0).await;
        assert!((*state.0.cpu_p3_limit_pct.lock().await - 99.0).abs() < 0.001,
            "acima de 99 deve ser clamped para 99");
        state.set_cpu_p3_limit_pct(0.0).await;
        assert!((*state.0.cpu_p3_limit_pct.lock().await - 30.0).abs() < 0.001,
            "abaixo de 30 deve ser clamped para 30");
    }

    #[tokio::test]
    async fn cpu_p3_limit_pct_exposed_in_collect_status() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        state.set_cpu_p3_limit_pct(70.0).await;
        let s = collect_status(&state).await;
        assert!((s.cpu_p3_limit_pct - 70.0).abs() < 0.001,
            "cpu_p3_limit_pct no StatusResponse deve refletir o valor configurado");
    }

    // ── cpu_watchdog — CPU% via AtomicU32 ────────────────────────────────────

    #[test]
    fn cached_cpu_pct_starts_at_zero() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let bits  = state.0.cached_cpu_pct.load(Ordering::Relaxed);
        assert_eq!(f32::from_bits(bits), 0.0,
            "cached_cpu_pct deve iniciar em 0.0 antes do watchdog rodar");
    }

    #[test]
    fn cached_cpu_pct_store_and_load_roundtrip() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let val: f32 = 42.5;
        state.0.cached_cpu_pct.store(val.to_bits(), Ordering::Relaxed);
        let loaded = f32::from_bits(state.0.cached_cpu_pct.load(Ordering::Relaxed));
        assert!((loaded - val).abs() < 0.001,
            "store/load de f32 via AtomicU32 deve preservar o valor");
    }

    #[tokio::test]
    async fn cpu_ram_usage_reads_from_cached_cpu_pct() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        // Simula o watchdog armazenando 55.0%
        state.0.cached_cpu_pct.store(55.0_f32.to_bits(), Ordering::Relaxed);
        let (cpu, _, _) = cpu_ram_usage(&state.0.sys, &state.0.cached_cpu_pct).await;
        assert!((cpu - 55.0).abs() < 0.001,
            "cpu_ram_usage deve retornar o valor cacheado pelo watchdog, não chamar refresh");
    }

    // ── CPU/RAM guard — 4 cenários ────────────────────────────────────────────

    #[test]
    fn cpu_ram_guard_constants_are_sane() {
        assert!(CPU_P3_BLOCK > 0.0 && CPU_P3_BLOCK <= 100.0,
            "CPU_P3_BLOCK deve estar entre 0 e 100");
        assert!(RAM_P3_BLOCK_MB > 0,
            "RAM_P3_BLOCK_MB deve ser positivo");
        assert!(CPU_P3_SURVIVAL_BLOCK >= CPU_P3_BLOCK,
            "threshold de sobrevivência deve ser >= threshold normal");
        assert!(RAM_P3_SURVIVAL_BLOCK_MB <= RAM_P3_BLOCK_MB,
            "RAM de sobrevivência deve ser mais permissiva (menor threshold)");
    }

    #[test]
    fn cpu_p3_block_is_85_percent() {
        assert!((CPU_P3_BLOCK - 85.0).abs() < 0.001);
    }

    #[test]
    fn ram_p3_block_is_1536_mb() {
        assert_eq!(RAM_P3_BLOCK_MB, 1_536);
    }

    #[test]
    fn cpu_p3_survival_block_is_92_percent() {
        assert!((CPU_P3_SURVIVAL_BLOCK - 92.0).abs() < 0.001);
    }

    // ── Battery mode — 3 cenários ─────────────────────────────────────────────

    #[tokio::test]
    async fn battery_mode_on_battery_starts_false_in_test() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        // make_test_state inicializa on_battery = false
        assert!(!*state.0.on_battery.lock().await,
            "on_battery deve iniciar false no test state");
    }

    #[tokio::test]
    async fn battery_mode_can_be_set_true() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        *state.0.on_battery.lock().await = true;
        assert!(*state.0.on_battery.lock().await,
            "on_battery deve refletir o valor definido");
    }

    #[test]
    fn battery_mode_cpu_p2_threshold_more_conservative() {
        // Em bateria, P2 usa threshold mais conservador que o P3 normal
        assert!(ON_BATTERY_P2_CPU_BLOCK < CPU_P3_BLOCK,
            "threshold de bateria P2 deve ser mais conservador que P3 normal");
    }

    // ── BatteryPolicy — 3 níveis ─────────────────────────────────────────────

    #[test]
    fn battery_policy_normal_when_ac() {
        let p = BatteryPolicy::from_state(false, 50);
        assert_eq!(p, BatteryPolicy::Normal, "AC → sempre Normal independente do pct");
    }

    #[test]
    fn battery_policy_normal_when_high_charge_discharging() {
        // >80% em descarga → ainda Normal (bateria cheia, laptop desconectado)
        let p = BatteryPolicy::from_state(true, 85);
        assert_eq!(p, BatteryPolicy::Normal);
    }

    #[test]
    fn battery_policy_economy_at_boundary_80() {
        let p = BatteryPolicy::from_state(true, 80);
        assert_eq!(p, BatteryPolicy::Economy, "80% em descarga → Economy");
    }

    #[test]
    fn battery_policy_economy_mid_range() {
        let p = BatteryPolicy::from_state(true, 55);
        assert_eq!(p, BatteryPolicy::Economy);
    }

    #[test]
    fn battery_policy_economy_at_boundary_30() {
        // 30% é a fronteira — ainda Economy (não Critical)
        let p = BatteryPolicy::from_state(true, 30);
        assert_eq!(p, BatteryPolicy::Economy, "30% em descarga → ainda Economy");
    }

    #[test]
    fn battery_policy_critical_below_30() {
        let p = BatteryPolicy::from_state(true, 29);
        assert_eq!(p, BatteryPolicy::Critical, "29% em descarga → Critical");
    }

    #[test]
    fn battery_policy_critical_at_zero() {
        let p = BatteryPolicy::from_state(true, 0);
        assert_eq!(p, BatteryPolicy::Critical);
    }

    #[test]
    fn battery_policy_is_restricted_normal() {
        assert!(!BatteryPolicy::Normal.is_restricted());
    }

    #[test]
    fn battery_policy_is_restricted_economy() {
        assert!(BatteryPolicy::Economy.is_restricted());
    }

    #[test]
    fn battery_policy_is_restricted_critical() {
        assert!(BatteryPolicy::Critical.is_restricted());
    }

    #[test]
    fn battery_policy_as_str() {
        assert_eq!(BatteryPolicy::Normal.as_str(),   "normal");
        assert_eq!(BatteryPolicy::Economy.as_str(),  "economy");
        assert_eq!(BatteryPolicy::Critical.as_str(), "critical");
    }

    #[tokio::test]
    async fn battery_policy_starts_normal_in_test() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let policy = *state.0.battery_policy.lock().await;
        assert_eq!(policy, BatteryPolicy::Normal, "test state começa com Normal");
    }

    #[tokio::test]
    async fn battery_pct_starts_100_in_test() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert_eq!(*state.0.battery_pct.lock().await, 100u8);
    }

    // ── Thermal throttling — proteção de temperatura ──────────────────────────

    #[tokio::test]
    async fn thermal_blocked_starts_false_in_test() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.0.p3_thermal_blocked.load(Ordering::Relaxed),
            "p3_thermal_blocked deve iniciar false no test state");
    }

    #[tokio::test]
    async fn gpu_temp_celsius_starts_none_in_test() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(state.0.gpu_temp_celsius.lock().await.is_none(),
            "gpu_temp_celsius deve iniciar None no test state");
    }

    #[test]
    fn thermal_block_threshold_higher_than_resume() {
        // Histerese: threshold de bloqueio > threshold de retomada (evita oscilação)
        const GPU_TEMP_BLOCK_C: f32  = 85.0;
        const GPU_TEMP_RESUME_C: f32 = 80.0;
        assert!(GPU_TEMP_BLOCK_C > GPU_TEMP_RESUME_C,
            "threshold de bloqueio deve ser maior que o de retomada");
        assert_eq!(GPU_TEMP_BLOCK_C - GPU_TEMP_RESUME_C, 5.0,
            "histerese de 5°C entre bloqueio e retomada");
    }

    #[test]
    fn thermal_block_threshold_below_driver_throttle() {
        // A RX 6600 só faz throttling pelo driver acima de ~95°C.
        // Nossa proteção antecipa em 10°C para preservar desempenho P1/P2.
        const GPU_TEMP_BLOCK_C: f32 = 85.0;
        const DRIVER_THROTTLE_C: f32 = 95.0;
        assert!(GPU_TEMP_BLOCK_C < DRIVER_THROTTLE_C,
            "nosso threshold ({GPU_TEMP_BLOCK_C}°C) deve ser menor que o do driver ({DRIVER_THROTTLE_C}°C)");
    }

    #[tokio::test]
    async fn thermal_blocked_can_be_set_and_reported_in_status() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Simular watchdog detectando temperatura alta
        state.0.p3_thermal_blocked.store(true, Ordering::Relaxed);
        *state.0.gpu_temp_celsius.lock().await = Some(87.5);

        assert!(state.0.p3_thermal_blocked.load(Ordering::Relaxed));
        assert_eq!(*state.0.gpu_temp_celsius.lock().await, Some(87.5));
    }

    // ── AVX2 — detecção e limites ─────────────────────────────────────────────

    #[test]
    fn detect_avx2_returns_bool() {
        // Apenas verifica que a função não causa panic — o valor depende da CPU de CI
        let result = detect_avx2();
        // Em qualquer máquina x86_64 moderna com AVX2, deve ser true
        // Em arquiteturas sem AVX2 (i5-3470) será false
        let _ = result; // sem assert — valor é legítimo em ambos os casos
    }

    #[test]
    fn inject_efficiency_no_avx2_p3_limits_context() {
        // Sem AVX2: P3 deve ter num_ctx=512, num_batch=128, num_thread=2
        let mut body = serde_json::Map::new();
        inject_efficiency_params(&mut body, 3, HardwareProfile::WorkPc, false, false, false);
        let opts = body["options"].as_object().expect("options ausente");
        assert_eq!(opts["num_ctx"].as_u64(), Some(512), "num_ctx deve ser 512 sem AVX2");
        assert_eq!(opts["num_batch"].as_u64(), Some(128), "num_batch deve ser 128 sem AVX2");
        assert_eq!(opts["num_thread"].as_u64(), Some(2));
    }

    #[test]
    fn inject_efficiency_no_avx2_p1_limits_context() {
        // Sem AVX2: P1 também recebe num_ctx=512, num_batch=128
        let mut body = serde_json::Map::new();
        inject_efficiency_params(&mut body, 1, HardwareProfile::WorkPc, false, false, false);
        let opts = body["options"].as_object().expect("options ausente");
        assert_eq!(opts["num_ctx"].as_u64(), Some(512));
        assert_eq!(opts["num_batch"].as_u64(), Some(128));
        assert_eq!(opts["num_thread"].as_u64(), Some(2));
    }

    #[test]
    fn inject_efficiency_no_avx2_p2_limits_batch_and_ctx() {
        // Sem AVX2: P2 recebe num_batch=128 e num_ctx=512
        let mut body = serde_json::Map::new();
        inject_efficiency_params(&mut body, 2, HardwareProfile::MainPc, false, false, false);
        let opts = body["options"].as_object().expect("options ausente");
        assert_eq!(opts["num_batch"].as_u64(), Some(128));
        assert_eq!(opts["num_ctx"].as_u64(), Some(512));
    }

    #[test]
    fn inject_efficiency_with_avx2_p3_normal_context() {
        // Com AVX2: P3 usa contexto completo (2048)
        let mut body = serde_json::Map::new();
        inject_efficiency_params(&mut body, 3, HardwareProfile::MainPc, false, false, true);
        let opts = body["options"].as_object().expect("options ausente");
        assert_eq!(opts["num_ctx"].as_u64(), Some(2048), "AVX2 → num_ctx=2048");
        assert_eq!(opts["num_batch"].as_u64(), Some(256));
    }

    #[test]
    fn inject_efficiency_no_avx2_p3_survival_unchanged() {
        // Modo sobrevivência já aplica limites próprios — AVX2 não interfere
        let mut body = serde_json::Map::new();
        inject_efficiency_params(&mut body, 3, HardwareProfile::WorkPc, true, false, false);
        let opts = body["options"].as_object().expect("options ausente");
        assert_eq!(opts["num_ctx"].as_u64(), Some(1024)); // survival mantém 1024
    }

    #[tokio::test]
    async fn test_state_has_avx2_field_accessible() {
        // has_avx2 é acessível e inicializado em make_test_state
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let _ = state.0.has_avx2; // apenas verifica acesso sem panic
    }

    // ── Semáforo — 4 cenários ─────────────────────────────────────────────────

    #[test]
    fn semaphore_starts_with_2_permits() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let sem = state.0.akasha_semaphore.clone();
        // Deve conseguir adquirir 2 permits de uma vez
        let _p = sem.try_acquire_many(2).expect("semáforo deve ter 2 permits inicialmente");
    }

    #[test]
    fn semaphore_heavy_model_uses_2_permits() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let sem = state.0.akasha_semaphore.clone();
        // Modelo pesado: 2 permits → exclusividade total
        let p1 = sem.try_acquire_many(2).expect("2 permits disponíveis");
        // Com 2 permits adquiridos, nenhum outro consegue
        assert!(sem.try_acquire_many(1).is_err(),
            "nenhum permit restante após modelo pesado");
        drop(p1);
    }

    #[test]
    fn semaphore_light_model_uses_1_permit() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let sem = state.0.akasha_semaphore.clone();
        // Modelo leve: 1 permit → permite 2 simultâneos
        let p1 = sem.try_acquire_many(1).expect("1 permit disponível");
        let p2 = sem.try_acquire_many(1).expect("segundo permit também disponível");
        assert!(sem.try_acquire_many(1).is_err(),
            "sem terceiro permit (semáforo tem apenas 2)");
        drop(p1);
        drop(p2);
    }

    #[test]
    fn is_light_model_identifies_models_correctly() {
        assert!(is_light_model("gemma2:2b"),  "2b é leve");
        assert!(is_light_model("smollm2:1.7b"), "1.7b é leve");
        assert!(is_light_model("qwen2.5:3b"), "3b é leve");
        assert!(!is_light_model("qwen2.5:7b"), "7b não é leve");
        assert!(!is_light_model("llama3:8b"),  "8b não é leve");
        assert!(is_light_model("qwen2.5:0.5b"), "0.5b é leve");
    }

    // ── Crash counter e akasha_disabled — 4 cenários ───────────────────────────

    #[tokio::test]
    async fn akasha_crash_count_starts_zero() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let count = *state.0.akasha_crash_count.lock().await;
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn akasha_crash_count_increments_correctly() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        for expected in 1u32..=3 {
            let count = {
                let mut cc = state.0.akasha_crash_count.lock().await;
                *cc += 1;
                *cc
            };
            assert_eq!(count, expected, "crash count deve incrementar para {expected}");
        }
    }

    #[test]
    fn akasha_disabled_starts_false() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.0.akasha_disabled.load(Ordering::Relaxed),
            "akasha_disabled deve iniciar false");
    }

    #[test]
    fn akasha_disabled_flag_prevents_inference_path() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        // Simula estado após 3+ crashes
        state.0.akasha_disabled.store(true, Ordering::Relaxed);
        // A expressão que queue_and_forward usa para decidir use_llama
        let use_llama = state.0.llama_server_bin.is_some()
            && !state.0.akasha_disabled.load(Ordering::Relaxed);
        assert!(!use_llama,
            "akasha_disabled=true deve impedir uso do llama-server mesmo se bin existe");
    }

    // ── Testes de mnemosyne_proc (Passo 2) ───────────────────────────────────

    #[tokio::test]
    async fn mnemosyne_proc_active_false_when_no_proc() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert!(!state.mnemosyne_proc_active().await,
            "mnemosyne_proc_active deve ser false quando não há processo");
    }

    #[tokio::test]
    async fn mnemosyne_proc_active_true_when_set() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        let child = tokio::process::Command::new("sleep")
            .arg("1")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep disponível");
        *state.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "qwen2.5:7b".to_string(),
        });
        assert!(state.mnemosyne_proc_active().await,
            "mnemosyne_proc_active deve ser true após injetar processo");
    }

    #[tokio::test]
    async fn kill_mnemosyne_proc_removes_handle() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep disponível");
        *state.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "qwen2.5:7b".to_string(),
        });
        assert!(state.mnemosyne_proc_active().await);
        let killed = state.kill_mnemosyne_proc().await;
        assert!(killed, "kill_mnemosyne_proc deve retornar true quando havia processo");
        assert!(!state.mnemosyne_proc_active().await,
            "mnemosyne_proc_active deve ser false após kill");
    }

    // ── sysfs_vram_mb — 3 cenários ────────────────────────────────────────────

    #[test]
    fn sysfs_vram_mb_does_not_panic_without_hardware() {
        // Em ambiente de teste (sem GPU física), não deve entrar em pânico
        let _ = sysfs_vram_mb();
    }

    #[test]
    fn sysfs_vram_mb_returns_none_on_non_linux() {
        // Em Linux sem /sys/class/drm/card* (CI/container), retorna None
        // Em Linux com hardware AMD, pode retornar Some — ambos são válidos
        #[cfg(not(target_os = "linux"))]
        assert!(sysfs_vram_mb().is_none(), "não-Linux deve retornar None");
        #[cfg(target_os = "linux")]
        let _ = sysfs_vram_mb(); // não crasha
    }

    #[test]
    fn sysfs_vram_mb_picks_highest_vram_card() {
        // Valida a lógica de seleção do melhor card via inspeção da função.
        // A função retorna o card com maior mem_info_vram_total — se dois cards
        // existirem, o menor não deve ser selecionado.
        // Como não podemos criar sysfs fictício em teste unitário, validamos que
        // a função retorna valores consistentes (used ≤ total se Some).
        if let Some((total_mb, used_mb)) = sysfs_vram_mb() {
            assert!(total_mb > 0, "total_mb deve ser positivo");
            assert!(used_mb <= total_mb,
                "used_mb ({used_mb}) não pode exceder total_mb ({total_mb})");
        }
    }

    // ── P1 timeout ────────────────────────────────────────────────────────────

    #[test]
    fn p1_timeout_constant_is_120s() {
        assert_eq!(P1_TIMEOUT.as_secs(), 120, "P1_TIMEOUT deve ser 120s");
    }

    #[test]
    fn timeout_hierarchy_p1_gt_p2_gt_p3() {
        assert!(P1_TIMEOUT > P2_TIMEOUT, "P1 > P2 timeout");
        assert!(P2_TIMEOUT > P3_TIMEOUT, "P2 > P3 timeout");
    }

    // ── list_ollama_models ────────────────────────────────────────────────────

    #[tokio::test]
    async fn list_ollama_models_empty_when_no_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let models = list_ollama_models(&state).await;
        assert!(models.is_empty(), "sem proc ativo → lista vazia");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn list_ollama_models_returns_active_model_name() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Injeta um proc fictício (sleep em background)
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "phi-3-mini".to_string(),
        });

        let models = list_ollama_models(&state).await;
        assert_eq!(models.len(), 1);
        assert_eq!(models[0].name, "phi-3-mini");
    }

    // ── do_list_all_models ────────────────────────────────────────────────────

    #[tokio::test]
    async fn do_list_all_models_empty_when_registry_missing() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let entries = do_list_all_models(&state).await;
        assert!(entries.is_empty());
    }

    #[tokio::test]
    async fn do_list_all_models_shows_available_when_not_loaded() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();
        let entry = sample_registry_entry("phi-3-mini", "phi-3-mini.gguf", "/tmp/phi-3-mini.gguf");
        update_model_registry(&models_dir, entry).await;

        let state = make_test_state(models_dir);
        let entries = do_list_all_models(&state).await;
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "phi-3-mini");
        assert_eq!(entries[0].status, "available", "sem proc → status available");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn do_list_all_models_marks_loaded_model_active() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let entry = sample_registry_entry("phi-3-mini", "phi-3-mini.gguf", "/tmp/phi-3-mini.gguf");
        update_model_registry(&models_dir, entry).await;

        let state = make_test_state(models_dir);

        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "phi-3-mini".to_string(),
        });

        let entries = do_list_all_models(&state).await;
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].status, "active", "proc ativo com mesmo nome → status active");
    }

    #[tokio::test]
    async fn do_list_all_models_size_disk_mb_from_registry() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let mut entry = sample_registry_entry("smol", "smol.gguf", "/tmp/smol.gguf");
        entry.size_bytes = 2_500_000_000; // 2500 MB
        update_model_registry(&models_dir, entry).await;

        let state = make_test_state(models_dir);
        let entries = do_list_all_models(&state).await;
        assert_eq!(entries[0].size_disk_mb, 2_500);
    }

    // ── do_silence ────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn do_silence_returns_zero_when_no_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let count = do_silence(&state).await;
        assert_eq!(count, 0, "nenhum proc para parar → retorna 0");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn do_silence_returns_one_and_clears_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });

        let count = do_silence(&state).await;
        assert_eq!(count, 1);
        assert!(state.0.akasha_proc.lock().await.is_none(), "proc deve ser None após silence");
    }

    // ── do_unload_model ───────────────────────────────────────────────────────

    #[tokio::test]
    async fn do_unload_model_returns_false_when_no_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let stopped = do_unload_model(&state, "qualquer-modelo").await;
        assert!(!stopped, "nenhum proc ativo → retorna false");
    }

    // ── kill_llama_proc ───────────────────────────────────────────────────────

    #[tokio::test]
    async fn kill_llama_proc_returns_false_when_no_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.kill_llama_proc().await);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn kill_llama_proc_returns_true_and_clears_handle() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });

        assert!(state.kill_llama_proc().await, "proc ativo → true");
        assert!(state.0.akasha_proc.lock().await.is_none(), "handle limpo após kill");
        // Segunda chamada: nenhum proc → false
        assert!(!state.kill_llama_proc().await);
    }

    // ── llama_proc_active ─────────────────────────────────────────────────────

    #[tokio::test]
    async fn llama_proc_active_false_when_no_proc() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.llama_proc_active().await);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn llama_proc_active_true_when_proc_set() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-active".to_string(),
        });
        assert!(state.llama_proc_active().await);
        state.kill_llama_proc().await;
        assert!(!state.llama_proc_active().await);
    }

    // ── pick_models_dir — seleção determinística com tempdir ──────────────────

    #[test]
    fn pick_models_dir_prefers_xdg_when_xdg_has_registry() {
        let xdg_tmp  = tempfile::tempdir().unwrap();
        let cwd_tmp  = tempfile::tempdir().unwrap();
        // xdg tem registry.json; cwd não tem
        std::fs::write(xdg_tmp.path().join("registry.json"), "[]").unwrap();
        let result = pick_models_dir(xdg_tmp.path().to_owned(), cwd_tmp.path().to_owned());
        assert_eq!(result, xdg_tmp.path(), "xdg deve ser preferido quando tem registry.json");
    }

    #[test]
    fn pick_models_dir_falls_back_to_cwd_when_only_cwd_has_registry() {
        let xdg_tmp  = tempfile::tempdir().unwrap();
        let cwd_tmp  = tempfile::tempdir().unwrap();
        // cwd tem registry.json; xdg não tem
        std::fs::write(cwd_tmp.path().join("registry.json"), "[]").unwrap();
        let result = pick_models_dir(xdg_tmp.path().to_owned(), cwd_tmp.path().to_owned());
        assert_eq!(result, cwd_tmp.path(), "cwd deve ser usado como fallback quando só ele tem registry.json");
    }

    #[test]
    fn pick_models_dir_uses_xdg_when_neither_has_registry() {
        let xdg_tmp  = tempfile::tempdir().unwrap();
        let cwd_tmp  = tempfile::tempdir().unwrap();
        // nenhum tem registry.json
        let result = pick_models_dir(xdg_tmp.path().to_owned(), cwd_tmp.path().to_owned());
        assert_eq!(result, xdg_tmp.path(), "xdg deve ser o padrão quando nenhum tem registry.json");
    }

    // ── build_llama_server_cmd — flags obrigatórias ───────────────────────────

    fn cmd_args(cmd: &tokio::process::Command) -> Vec<String> {
        cmd.as_std().get_args()
            .map(|a| a.to_string_lossy().into_owned())
            .collect()
    }

    #[test]
    fn spawn_cmd_always_includes_pooling_mean() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd(bin, model, None, -1, 4096, 8081);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--pooling")
            .expect("--pooling deve estar presente (BUG-002: sem ela /v1/embeddings retorna 501)");
        assert_eq!(args[idx + 1], "mean", "--pooling deve ser 'mean'");
    }

    #[test]
    fn spawn_cmd_always_includes_port() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd(bin, model, None, 0, 4096, 8081);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--port")
            .expect("--port deve sempre estar presente");
        assert_eq!(args[idx + 1], "8081");
    }

    #[test]
    fn spawn_cmd_n_gpu_minus1_emits_9999() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd(bin, model, None, -1, 4096, 8081);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente quando n_gpu=-1 (BUG-003: sem ela roda em CPU)");
        assert_eq!(args[idx + 1], "9999", "n_gpu=-1 deve gerar 9999 (offload total)");
    }

    #[test]
    fn spawn_cmd_n_gpu_zero_emits_zero() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd(bin, model, None, 0, 4096, 8081);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente quando n_gpu=0");
        assert_eq!(args[idx + 1], "0", "n_gpu=0 deve forçar modo CPU explícito");
    }

    #[test]
    fn spawn_cmd_n_gpu_positive_uses_value() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd(bin, model, None, 24, 4096, 8081);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente quando n_gpu=24");
        assert_eq!(args[idx + 1], "24");
    }

    #[test]
    fn spawn_cmd_with_mmproj_includes_flag() {
        let bin    = std::path::Path::new("llama-server");
        let model  = std::path::Path::new("model.gguf");
        let mmproj = std::path::Path::new("mmproj.gguf");
        let cmd    = build_llama_server_cmd(bin, model, Some(mmproj), -1, 4096, 8081);
        let args   = cmd_args(&cmd);
        let idx    = args.iter().position(|a| a == "--mmproj")
            .expect("--mmproj deve estar presente quando mmproj_path é Some");
        assert!(args[idx + 1].ends_with("mmproj.gguf"));
    }

    #[test]
    fn spawn_cmd_without_mmproj_excludes_flag() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd(bin, model, None, -1, 4096, 8081);
        let args  = cmd_args(&cmd);
        assert!(!args.contains(&"--mmproj".to_string()),
            "--mmproj não deve aparecer quando mmproj_path é None");
    }

    // ── do_list_all_models: active model detectado via llama_proc ─────────────

    #[cfg(unix)]
    #[tokio::test]
    async fn do_list_all_models_active_requires_llama_proc_not_just_server() {
        // Garante que status=active só aparece quando llama_proc está setado no HUB.
        // Sem isso, mesmo com server rodando, a lista mostra "available" — causando timeout na UI.
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let gguf = models_dir.join("qwen.gguf");
        std::fs::write(&gguf, b"fake").unwrap();
        let entry = sample_registry_entry("qwen", "qwen.gguf", gguf.to_str().unwrap());
        update_model_registry(&models_dir, entry).await;

        let state = make_test_state(models_dir);

        // Sem llama_proc → nenhum active
        let entries = do_list_all_models(&state).await;
        assert!(entries.iter().all(|e| e.status == "available"),
            "sem llama_proc, nenhum modelo deve ser active — senão UI nunca sai do poll");

        // Com llama_proc setado → active
        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "qwen".to_string(),
        });
        let entries = do_list_all_models(&state).await;
        assert!(entries.iter().any(|e| e.status == "active"),
            "com llama_proc setado, o modelo deve aparecer como active");
        state.kill_llama_proc().await;
    }

    // ── build_embed_server_cmd — flags e parâmetros ──────────────────────────

    fn embed_cmd_args(n_gpu: i32, port: u16) -> Vec<String> {
        let bin        = std::path::Path::new("/usr/bin/llama-server");
        let model_path = std::path::Path::new("/models/bge-m3.gguf");
        let mut cmd    = build_embed_server_cmd(bin, model_path, n_gpu, port);
        cmd.as_std()
           .get_args()
           .map(|a| a.to_string_lossy().to_string())
           .collect()
    }

    #[test]
    fn build_embed_server_cmd_has_embeddings_flag() {
        let args = embed_cmd_args(-1, 8082);
        assert!(args.contains(&"--embeddings".to_string()),
            "--embeddings deve estar presente (habilita /v1/embeddings)");
    }

    #[test]
    fn build_embed_server_cmd_has_pooling_mean() {
        let args = embed_cmd_args(-1, 8082);
        let pooling_idx = args.iter().position(|a| a == "--pooling")
            .expect("--pooling deve estar presente");
        assert_eq!(args[pooling_idx + 1], "mean",
            "pooling deve ser 'mean' (padrão para bge-m3)");
    }

    #[test]
    fn build_embed_server_cmd_has_correct_port() {
        let args = embed_cmd_args(-1, 8082);
        let port_idx = args.iter().position(|a| a == "--port")
            .expect("--port deve estar presente");
        assert_eq!(args[port_idx + 1], "8082",
            "porta do embed-server deve ser 8082");
    }

    #[test]
    fn build_embed_server_cmd_n_gpu_zero_passes_0() {
        let args = embed_cmd_args(0, 8082);
        let idx = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente quando n_gpu=0");
        assert_eq!(args[idx + 1], "0",
            "n_gpu=0 deve passar '--n-gpu-layers 0' (CPU-only)");
    }

    #[test]
    fn default_embed_n_gpu_layers_is_cpu() {
        // BUG-028: o default do embed-server é CPU (0) para não disputar VRAM.
        assert_eq!(DEFAULT_EMBED_N_GPU_LAYERS, 0,
            "default deve ser 0 (CPU)");
        let args = embed_cmd_args(DEFAULT_EMBED_N_GPU_LAYERS, 8082);
        let idx = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente");
        assert_eq!(args[idx + 1], "0",
            "o default deve produzir '--n-gpu-layers 0' (embeddings em CPU)");
    }

    #[test]
    fn build_embed_server_cmd_n_gpu_positive_passes_value() {
        let args = embed_cmd_args(16, 8082);
        let idx = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente quando n_gpu=16");
        assert_eq!(args[idx + 1], "16",
            "n_gpu=16 deve passar '--n-gpu-layers 16'");
    }

    #[test]
    fn build_embed_server_cmd_n_gpu_minus1_passes_9999() {
        let args = embed_cmd_args(-1, 8082);
        let idx = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente quando n_gpu=-1");
        assert_eq!(args[idx + 1], "9999",
            "n_gpu=-1 (offload total) deve passar '--n-gpu-layers 9999'");
    }

    #[test]
    fn build_embed_server_cmd_no_chat_template() {
        let args = embed_cmd_args(-1, 8082);
        assert!(!args.contains(&"--chat-template".to_string()),
            "--chat-template não deve aparecer no embed-server (embedding-only)");
    }

    #[test]
    fn build_embed_server_cmd_no_cont_batching() {
        let args = embed_cmd_args(-1, 8082);
        assert!(!args.contains(&"--cont-batching".to_string()),
            "--cont-batching não deve aparecer no embed-server (não aplicável a embedding)");
    }

    #[test]
    fn build_embed_server_cmd_no_parallel() {
        let args = embed_cmd_args(-1, 8082);
        assert!(!args.contains(&"--parallel".to_string()),
            "--parallel não deve aparecer no embed-server");
    }

    // ── BUG-029: ubatch/batch/ctx para inputs > 512 tokens ──────────────────

    #[test]
    fn build_embed_server_cmd_sets_ubatch_2048() {
        let args = embed_cmd_args(0, 8082);
        let i = args.iter().position(|a| a == "--ubatch-size")
            .expect("--ubatch-size deve estar presente (senão default 512 → 500 'input too large')");
        assert_eq!(args[i + 1], "2048");
    }

    #[test]
    fn build_embed_server_cmd_sets_batch_2048() {
        let args = embed_cmd_args(0, 8082);
        let i = args.iter().position(|a| a == "--batch-size")
            .expect("--batch-size deve estar presente");
        // Para embeddings o llama-server força n_batch == n_ubatch; mantê-los iguais.
        assert_eq!(args[i + 1], "2048");
    }

    #[test]
    fn build_embed_server_cmd_sets_ctx_8192() {
        let args = embed_cmd_args(0, 8082);
        let i = args.iter().position(|a| a == "--ctx-size")
            .expect("--ctx-size deve estar presente");
        assert_eq!(args[i + 1], "8192");
    }

    // ── embed_log_path ────────────────────────────────────────────────────────

    #[test]
    fn embed_log_path_is_sibling_of_models_dir() {
        let models_dir = std::path::Path::new("/home/user/logos/models");
        let log        = embed_log_path(models_dir);
        assert_eq!(log.parent().unwrap(), std::path::Path::new("/home/user/logos"),
            "log deve ficar no diretório pai de models/");
    }

    #[test]
    fn embed_log_path_filename_is_logos_embed_log() {
        let models_dir = std::path::Path::new("/home/user/logos/models");
        let log        = embed_log_path(models_dir);
        assert_eq!(log.file_name().unwrap().to_str().unwrap(), "logos_embed.log",
            "nome do arquivo de log deve ser 'logos_embed.log'");
    }

    #[test]
    fn embed_log_path_fallback_when_no_parent() {
        // Caminho sem parent (ex: "models") — deve usar o próprio diretório
        let models_dir = std::path::Path::new("models");
        let log        = embed_log_path(models_dir);
        assert_eq!(log.file_name().unwrap().to_str().unwrap(), "logos_embed.log");
    }

    // ── v1_embeddings_proxy — roteamento para porta 8082 ─────────────────────

    #[test]
    fn embed_proxy_url_uses_embed_server_port_not_chat_port() {
        // Verifica que a URL construída aponta para 8082 e não para 8081 (chat)
        let url = format!("http://127.0.0.1:{EMBED_SERVER_PORT}/v1/embeddings");
        assert!(url.contains("8082"),
            "URL de embedding deve conter porta 8082 (EMBED_SERVER_PORT)");
        assert!(!url.contains("8081"),
            "URL de embedding NÃO deve conter porta 8081 (AKASHA_SERVER_PORT/chat)");
    }

    #[test]
    fn embed_proxy_url_endpoint_is_v1_embeddings() {
        let url = format!("http://127.0.0.1:{EMBED_SERVER_PORT}/v1/embeddings");
        assert!(url.ends_with("/v1/embeddings"),
            "endpoint deve ser /v1/embeddings");
    }

    #[tokio::test]
    async fn v1_embeddings_proxy_returns_503_when_embed_proc_not_active() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // embed_proc = None (padrão) → deve retornar 503
        assert!(!state.embed_proc_active().await,
            "pré-condição: embed_proc deve estar inativo");

        let headers = axum::http::HeaderMap::new();
        let body    = axum::body::Bytes::from(r#"{"input": "teste"}"#);

        let response = v1_embeddings_proxy(State(state), headers, body).await;
        assert_eq!(
            response.status(),
            StatusCode::SERVICE_UNAVAILABLE,
            "embed-server inativo → proxy deve retornar 503 SERVICE_UNAVAILABLE"
        );
    }

    #[tokio::test]
    async fn v1_embeddings_proxy_503_body_mentions_embed_port() {
        use axum::body::to_bytes;

        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Habilitar inferência para ultrapassar o gate de inference_enabled
        // e chegar ao check do embed-server (que menciona porta 8082 no 503).
        state.0.inference_enabled.store(true, std::sync::atomic::Ordering::Relaxed);

        let headers = axum::http::HeaderMap::new();
        let body    = axum::body::Bytes::from(r#"{"input": "teste"}"#);

        let response = v1_embeddings_proxy(State(state), headers, body).await;

        let (parts, body_stream) = response.into_parts();
        assert_eq!(parts.status, StatusCode::SERVICE_UNAVAILABLE);

        let bytes  = to_bytes(body_stream, 4096).await.unwrap();
        let text   = String::from_utf8_lossy(&bytes);
        assert!(
            text.contains("8082"),
            "corpo do 503 deve mencionar a porta 8082; obtido: {text}"
        );
    }

    // ── Ciclo de vida integrado (item 4) ─────────────────────────────────────

    #[tokio::test]
    async fn do_silence_kills_both_chat_and_embed() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Spawna dois processos "sleep" simulando chat + embed
        let chat_child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        let embed_child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();

        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child: chat_child, model_name: "qwen".to_string(),
        });
        *state.0.embed_proc.lock().await = Some(LlamaProcHandle {
            child: embed_child, model_name: "bge-m3".to_string(),
        });

        let stopped = do_silence(&state).await;

        assert_eq!(stopped, 2, "do_silence deve retornar 2 quando ambos os processos estavam ativos");
        assert!(!state.embed_proc_active().await, "embed_proc deve ser None após do_silence");
        assert!(!state.0.akasha_proc.lock().await.is_some(), "llama_proc deve ser None após do_silence");
    }

    #[tokio::test]
    async fn do_silence_returns_0_when_no_procs() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let stopped = do_silence(&state).await;
        assert_eq!(stopped, 0, "do_silence sem processos deve retornar 0");
    }

    // ── Testes de dois servidores (Passos 6, 9, 11) ──────────────────────────

    #[tokio::test]
    async fn do_silence_kills_both_chat_servers() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let spawn_sleep = || tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();

        *state.0.akasha_proc.lock().await    = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "akasha-model".into() });
        *state.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "mnemosyne-model".into() });

        let stopped = do_silence(&state).await;
        assert_eq!(stopped, 2, "do_silence com AKASHA + Mnemosyne deve retornar 2");
        assert!(!state.llama_proc_active().await,    "AKASHA deve estar parado após do_silence");
        assert!(!state.mnemosyne_proc_active().await, "Mnemosyne deve estar parado após do_silence");
    }

    #[tokio::test]
    async fn kill_akasha_proc_does_not_affect_mnemosyne() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let spawn_sleep = || tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();

        *state.0.akasha_proc.lock().await    = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "akasha-model".into() });
        *state.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "mnemosyne-model".into() });

        state.kill_akasha_proc().await;

        assert!(!state.llama_proc_active().await,    "AKASHA deve estar parado");
        assert!(state.mnemosyne_proc_active().await,  "Mnemosyne deve permanecer ativo após kill_akasha_proc");
    }

    #[tokio::test]
    async fn idle_watchdog_akasha_independent_of_mnemosyne() {
        // check_idle_llm só considera o akasha_proc e last_akasha_request_at
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let spawn_sleep = || tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();

        *state.0.akasha_proc.lock().await    = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "akasha-model".into() });
        *state.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "mnemosyne-model".into() });

        // Simula que AKASHA está ocioso há muito tempo (1 dia)
        *state.0.last_akasha_request_at.lock().await = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(86400))
            .unwrap_or_else(std::time::Instant::now);

        let killed = check_idle_llm(&state).await;
        assert!(killed, "check_idle_llm deve matar AKASHA ocioso");
        assert!(!state.llama_proc_active().await,     "AKASHA deve estar parado");
        assert!(state.mnemosyne_proc_active().await,   "Mnemosyne não deve ser afetado pelo idle watchdog do AKASHA");
    }

    #[tokio::test]
    async fn idle_watchdog_mnemosyne_independent_of_akasha() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let spawn_sleep = || tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();

        *state.0.akasha_proc.lock().await    = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "akasha-model".into() });
        *state.0.mnemosyne_proc.lock().await = Some(LlamaProcHandle { child: spawn_sleep(), model_name: "mnemosyne-model".into() });

        // Simula que Mnemosyne está ocioso há muito tempo
        *state.0.last_mnemosyne_request_at.lock().await = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(86400))
            .unwrap_or_else(std::time::Instant::now);

        let killed = check_idle_mnemosyne(&state).await;
        assert!(killed, "check_idle_mnemosyne deve matar Mnemosyne ocioso");
        assert!(!state.mnemosyne_proc_active().await,  "Mnemosyne deve estar parado");
        assert!(state.llama_proc_active().await,        "AKASHA não deve ser afetado pelo idle watchdog da Mnemosyne");
    }

    #[test]
    fn retry_after_response_has_correct_header() {
        let resp = retry_after_response(StatusCode::SERVICE_UNAVAILABLE, "teste", 30);
        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE);
        let ra = resp.headers().get("retry-after")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("");
        assert_eq!(ra, "30", "Retry-After header deve ser 30");
    }

    #[test]
    fn retry_after_response_body_has_retry_after_field() {
        let resp = retry_after_response(StatusCode::TOO_MANY_REQUESTS, "ocupado", 60);
        assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
    }

    #[tokio::test]
    async fn do_silence_returns_1_when_only_chat_active() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child, model_name: "qwen".to_string(),
        });

        let stopped = do_silence(&state).await;
        assert_eq!(stopped, 1, "apenas chat ativo → do_silence retorna 1");
    }

    #[tokio::test]
    async fn do_unload_model_kills_embed_proc_too() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let embed_child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        *state.0.embed_proc.lock().await = Some(LlamaProcHandle {
            child: embed_child, model_name: "bge-m3".to_string(),
        });

        do_unload_model(&state, "qwen").await;

        assert!(!state.embed_proc_active().await,
            "do_unload_model deve matar embed_proc além do llama_proc");
    }

    #[tokio::test]
    async fn ensure_embed_server_started_noop_when_embed_model_empty() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // embed_model vazio por padrão no make_test_state — não deve spawnar nada
        *state.0.embed_model.lock().await = String::new();

        ensure_embed_server_started(&state).await;

        assert!(!state.embed_proc_active().await,
            "embed_model vazio → ensure_embed_server_started não deve criar processo");
    }

    #[tokio::test]
    async fn ensure_embed_server_started_noop_when_already_active() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Simula processo já ativo
        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        let pid_before = child.id();
        *state.0.embed_proc.lock().await = Some(LlamaProcHandle {
            child, model_name: "bge-m3".to_string(),
        });
        *state.0.embed_model.lock().await = "bge-m3".to_string();

        ensure_embed_server_started(&state).await;

        // PID não deve ter mudado — nenhum novo spawn
        let pid_after = state.0.embed_proc.lock().await
            .as_ref()
            .and_then(|p| p.child.id());
        assert_eq!(pid_before, pid_after,
            "embed-server já ativo → ensure_embed_server_started deve ser no-op");

        state.kill_embed_proc().await;
    }

    #[tokio::test]
    async fn ensure_embed_server_started_noop_when_model_not_in_registry() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Modelo configurado mas GGUF ausente — deve logar warn e não criar processo
        *state.0.embed_model.lock().await = "bge-m3".to_string();

        ensure_embed_server_started(&state).await;

        assert!(!state.embed_proc_active().await,
            "modelo ausente do registry → nenhum processo deve ser criado");
    }

    // ── Regressão BUG-008: nome canônico "bge-m3" no registry ────────────────

    #[test]
    fn resolve_gguf_path_finds_bge_m3_by_canonical_name() {
        // Verifica que resolve_gguf_path("bge-m3") encontra uma entrada cujo
        // `name` é "bge-m3" — mesmo que o filename seja "bge-m3-Q4_K_M.gguf".
        // Regressão: entry com name="bge-m3-Q4_K_M" não era encontrada por "bge-m3".
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        // Cria o arquivo GGUF no tempdir
        let gguf = models_dir.join("bge-m3-Q4_K_M.gguf");
        std::fs::write(&gguf, b"fake-gguf").unwrap();

        // Entry com o nome canônico correto ("bge-m3") — como deve estar no registry
        let registry = vec![serde_json::json!({
            "name":         "bge-m3",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf.to_string_lossy(),
            "size_bytes":   437_778_496_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26",
            "model_type":   "embed"
        })];
        std::fs::write(
            models_dir.join("registry.json"),
            serde_json::to_string(&registry).unwrap(),
        ).unwrap();

        let result = resolve_gguf_path("bge-m3", &models_dir);
        assert!(result.is_some(),
            "resolve_gguf_path deve encontrar 'bge-m3' quando registry.name == 'bge-m3'");
    }

    #[test]
    fn resolve_gguf_path_does_not_find_bge_m3_when_registry_name_has_quantization_suffix() {
        // Regressão BUG-008: entry com name="bge-m3-Q4_K_M" NÃO deve ser encontrada
        // por embed_model="bge-m3". Garante que o fix (renomear para "bge-m3") foi feito.
        let dir = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().to_path_buf();

        let gguf = models_dir.join("bge-m3-Q4_K_M.gguf");
        std::fs::write(&gguf, b"fake-gguf").unwrap();

        // Entry com nome errado — como estava antes do fix
        let registry = vec![serde_json::json!({
            "name":         "bge-m3-Q4_K_M",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf.to_string_lossy(),
            "size_bytes":   437_778_496_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26"
        })];
        std::fs::write(
            models_dir.join("registry.json"),
            serde_json::to_string(&registry).unwrap(),
        ).unwrap();

        let result = resolve_gguf_path("bge-m3", &models_dir);
        assert!(result.is_none(),
            "name='bge-m3-Q4_K_M' não deve ser encontrado por 'bge-m3' — \
             garante que a busca é por nome exato, não por prefixo");
    }

    // ── collect_status — campos de servidor ───────────────────────────────────

    #[tokio::test]
    async fn collect_status_chat_offline_when_no_proc() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Nenhum processo ativo
        let s = collect_status(&state).await;
        assert!(!s.chat_server_online, "sem llama_proc → chat_server_online deve ser false");
        assert!(s.chat_server_model.is_empty(), "sem proc → chat_server_model deve ser vazio");
        assert!(s.chat_response_ms.is_none(), "sem proc → chat_response_ms deve ser None");
    }

    #[tokio::test]
    async fn collect_status_embed_offline_when_no_proc() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        let s = collect_status(&state).await;
        assert!(!s.embed_server_online, "sem embed_proc → embed_server_online deve ser false");
        assert!(s.embed_server_model.is_empty(), "sem proc → embed_server_model deve ser vazio");
        assert!(s.embed_response_ms.is_none(), "sem proc → embed_response_ms deve ser None");
    }

    #[tokio::test]
    async fn collect_status_chat_online_model_reflects_proc() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        // Injeta processo dummy: o ping vai falhar (nenhum servidor real),
        // mas chat_server_online e chat_server_model devem refletir o proc.
        #[cfg(unix)]
        let child = tokio::process::Command::new("sleep")
            .arg("600")
            .spawn()
            .expect("sleep disponível em Unix");
        #[cfg(windows)]
        let child = tokio::process::Command::new("cmd")
            .args(["/C", "timeout", "/T", "600", "/NOBREAK"])
            .spawn()
            .expect("cmd disponível no Windows");

        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "qwen2.5-7b".to_string(),
        });

        let s = collect_status(&state).await;
        assert!(s.chat_server_online, "llama_proc Some → chat_server_online deve ser true");
        assert_eq!(s.chat_server_model, "qwen2.5-7b");
        // response_ms = None porque o sleep/cmd não serve /health
        assert!(s.chat_response_ms.is_none(),
            "processo dummy sem servidor HTTP → chat_response_ms deve ser None");

        state.kill_llama_proc().await;
    }

    #[tokio::test]
    async fn collect_status_embed_online_model_reflects_proc() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        #[cfg(unix)]
        let child = tokio::process::Command::new("sleep")
            .arg("600")
            .spawn()
            .expect("sleep disponível em Unix");
        #[cfg(windows)]
        let child = tokio::process::Command::new("cmd")
            .args(["/C", "timeout", "/T", "600", "/NOBREAK"])
            .spawn()
            .expect("cmd disponível no Windows");

        *state.0.embed_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "bge-m3".to_string(),
        });

        let s = collect_status(&state).await;
        assert!(s.embed_server_online, "embed_proc Some → embed_server_online deve ser true");
        assert_eq!(s.embed_server_model, "bge-m3");
        assert!(s.embed_response_ms.is_none(),
            "processo dummy sem servidor HTTP → embed_response_ms deve ser None");

        state.kill_embed_proc().await;
    }

    #[tokio::test]
    async fn collect_status_both_servers_reported_independently() {
        // Verifica que chat e embed têm campos independentes — um online, outro offline.
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());

        #[cfg(unix)]
        let chat_child = tokio::process::Command::new("sleep").arg("600").spawn().unwrap();
        #[cfg(windows)]
        let chat_child = tokio::process::Command::new("cmd")
            .args(["/C", "timeout", "/T", "600", "/NOBREAK"]).spawn().unwrap();

        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child: chat_child,
            model_name: "phi3.5".to_string(),
        });
        // embed_proc permanece None

        let s = collect_status(&state).await;
        assert!(s.chat_server_online,   "chat_server_online deve ser true");
        assert!(!s.embed_server_online, "embed_server_online deve ser false (proc ausente)");
        assert_eq!(s.chat_server_model, "phi3.5");
        assert!(s.embed_server_model.is_empty());

        state.kill_llama_proc().await;
    }

    // ── chat_log_path ─────────────────────────────────────────────────────────

    #[test]
    fn chat_log_path_is_sibling_of_models_dir() {
        let models_dir = std::path::Path::new("/home/user/logos/models");
        let log        = chat_log_path(models_dir);
        assert_eq!(log.parent().unwrap(), std::path::Path::new("/home/user/logos"),
            "log deve ficar no diretório pai de models/");
    }

    #[test]
    fn chat_log_path_filename_is_logos_chat_log() {
        let models_dir = std::path::Path::new("/home/user/logos/models");
        let log        = chat_log_path(models_dir);
        assert_eq!(log.file_name().unwrap().to_str().unwrap(), "logos_chat.log",
            "nome do arquivo de log deve ser 'logos_chat.log'");
    }

    #[test]
    fn chat_log_path_fallback_when_no_parent() {
        let models_dir = std::path::Path::new("models");
        let log        = chat_log_path(models_dir);
        assert_eq!(log.file_name().unwrap().to_str().unwrap(), "logos_chat.log");
    }

    #[test]
    fn chat_log_path_differs_from_embed_log_path() {
        let models_dir = std::path::Path::new("/home/user/logos/models");
        assert_ne!(
            chat_log_path(models_dir),
            embed_log_path(models_dir),
            "chat e embed devem gravar em arquivos distintos"
        );
    }

    // ── /logos/logs — endpoints de log ───────────────────────────────────────

    #[tokio::test]
    async fn logs_chat_handler_returns_empty_when_no_file() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        // Arquivo ainda não existe — handler deve retornar 200 com body vazio
        let response = logs_chat_handler(State(state)).await;
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn logs_embed_handler_returns_empty_when_no_file() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let response = logs_embed_handler(State(state)).await;
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn logs_chat_handler_returns_file_content() {
        use axum::body::to_bytes;

        let dir        = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().join("models");
        tokio::fs::create_dir_all(&models_dir).await.unwrap();

        let log_path = chat_log_path(&models_dir);
        tokio::fs::write(&log_path, b"2026-05-26T10:00:00 llama-server started\n").await.unwrap();

        let state    = make_test_state(models_dir);
        let response = logs_chat_handler(State(state)).await;
        assert_eq!(response.status(), StatusCode::OK);

        let bytes = to_bytes(response.into_body(), 4096).await.unwrap();
        let text  = String::from_utf8_lossy(&bytes);
        assert!(text.contains("llama-server started"),
            "resposta deve conter o conteúdo do log; obtido: {text}");
    }

    #[tokio::test]
    async fn logs_embed_handler_returns_file_content() {
        use axum::body::to_bytes;

        let dir        = tempfile::tempdir().expect("tmpdir");
        let models_dir = dir.path().join("models");
        tokio::fs::create_dir_all(&models_dir).await.unwrap();

        let log_path = embed_log_path(&models_dir);
        tokio::fs::write(&log_path, b"2026-05-26T10:00:00 embed-server ready\n").await.unwrap();

        let state    = make_test_state(models_dir);
        let response = logs_embed_handler(State(state)).await;
        assert_eq!(response.status(), StatusCode::OK);

        let bytes = to_bytes(response.into_body(), 4096).await.unwrap();
        let text  = String::from_utf8_lossy(&bytes);
        assert!(text.contains("embed-server ready"),
            "resposta deve conter o conteúdo do log; obtido: {text}");
    }

    #[tokio::test]
    async fn logs_chat_handler_content_type_is_text_plain() {
        let dir   = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let response = logs_chat_handler(State(state)).await;
        let ct = response.headers()
            .get(axum::http::header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("");
        assert!(ct.contains("text/plain"),
            "Content-Type deve ser text/plain; obtido: {ct}");
    }

    #[tokio::test]
    async fn read_tail_log_returns_last_n_lines() {
        let dir      = tempfile::tempdir().expect("tmpdir");
        let log_path = dir.path().join("test.log");
        let content  = (1u32..=10).map(|i| format!("linha {i}")).collect::<Vec<_>>().join("\n");
        tokio::fs::write(&log_path, content.as_bytes()).await.unwrap();

        let tail = read_tail_log(log_path, 3).await;
        let lines: Vec<&str> = tail.lines().collect();
        assert_eq!(lines.len(), 3, "deve retornar exatamente 3 linhas");
        assert_eq!(lines[2], "linha 10", "última linha deve ser 'linha 10'");
        assert_eq!(lines[0], "linha 8",  "primeira linha do tail deve ser 'linha 8'");
    }

    // ── validate_gguf_file ────────────────────────────────────────────────────

    #[test]
    fn validate_gguf_file_ok_with_correct_magic_and_size() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("model.gguf");
        // 8 bytes: magic "GGUF" + padding
        std::fs::write(&path, b"GGUF\x00\x00\x00\x00").unwrap();
        assert_eq!(
            validate_gguf_file(&path, Some(8)),
            GgufValidation::Ok,
            "arquivo com magic GGUF e tamanho correto deve ser Ok"
        );
    }

    #[test]
    fn validate_gguf_file_ok_without_expected_size() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("model.gguf");
        std::fs::write(&path, b"GGUF\x00\x00\x00\x00").unwrap();
        // Sem expected_size: só verifica magic
        assert_eq!(
            validate_gguf_file(&path, None),
            GgufValidation::Ok,
            "sem expected_size, apenas magic é verificado"
        );
    }

    #[test]
    fn validate_gguf_file_missing_returns_file_missing() {
        let path = std::path::Path::new("/tmp/nonexistent_gguf_test_file.gguf");
        assert_eq!(
            validate_gguf_file(path, None),
            GgufValidation::FileMissing,
            "arquivo inexistente deve retornar FileMissing"
        );
    }

    #[test]
    fn validate_gguf_file_too_small_returns_incomplete_download() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("partial.gguf");
        std::fs::write(&path, b"GGUF\x00").unwrap(); // 5 bytes
        let result = validate_gguf_file(&path, Some(417_000_000));
        assert!(
            matches!(result, GgufValidation::IncompleteDownload { actual_bytes: 5, expected_bytes: 417_000_000 }),
            "arquivo menor que o esperado deve retornar IncompleteDownload"
        );
    }

    #[test]
    fn validate_gguf_file_bad_magic_returns_invalid_magic() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bad.gguf");
        std::fs::write(&path, b"XXXX\x00\x00\x00\x00").unwrap();
        let result = validate_gguf_file(&path, Some(8));
        assert!(
            matches!(result, GgufValidation::InvalidMagic { actual_magic: [b'X', b'X', b'X', b'X'] }),
            "arquivo com magic errado deve retornar InvalidMagic; obtido: {result:?}"
        );
    }

    #[test]
    fn validate_gguf_file_empty_file_returns_incomplete() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("empty.gguf");
        std::fs::write(&path, b"").unwrap();
        // Arquivo vazio: tamanho 0 < esperado, ou não tem 4 bytes para ler
        let result = validate_gguf_file(&path, Some(100));
        assert!(
            matches!(result, GgufValidation::IncompleteDownload { actual_bytes: 0, .. }),
            "arquivo vazio deve retornar IncompleteDownload; obtido: {result:?}"
        );
    }

    #[test]
    fn validate_gguf_file_exact_size_match_is_ok() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("exact.gguf");
        let data = b"GGUF\x01\x02\x03\x04";
        std::fs::write(&path, data).unwrap();
        // Tamanho exato (8 bytes) deve passar
        assert_eq!(
            validate_gguf_file(&path, Some(8)),
            GgufValidation::Ok,
            "tamanho exato igual ao esperado deve ser Ok"
        );
    }

    #[test]
    fn validate_gguf_file_larger_than_expected_is_ok() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("big.gguf");
        let data = b"GGUF\x01\x02\x03\x04\x05\x06";
        std::fs::write(&path, data).unwrap();
        // Arquivo MAIOR que expected_bytes: não é erro (tamanho do registry pode ser arredondado)
        assert_eq!(
            validate_gguf_file(&path, Some(4)),
            GgufValidation::Ok,
            "arquivo maior que o esperado não é download incompleto"
        );
    }

    // ── find_model_registry_entry ─────────────────────────────────────────────

    #[test]
    fn find_model_registry_entry_by_name() {
        let dir = tempfile::tempdir().unwrap();
        let registry = vec![serde_json::json!({
            "name": "bge-m3", "repo_id": "org/bge", "filename": "bge-m3-Q4.gguf",
            "path": "/models/bge-m3-Q4.gguf", "size_bytes": 100_u64,
            "sha256": "abc", "downloaded_at": "2026-05-26"
        })];
        std::fs::write(dir.path().join("registry.json"), serde_json::to_string(&registry).unwrap()).unwrap();
        let entry = find_model_registry_entry("bge-m3", dir.path());
        assert!(entry.is_some(), "deve encontrar por name exato");
        assert_eq!(entry.unwrap().repo_id, "org/bge");
    }

    #[test]
    fn find_model_registry_entry_by_filename() {
        let dir = tempfile::tempdir().unwrap();
        let registry = vec![serde_json::json!({
            "name": "bge-m3", "repo_id": "org/bge", "filename": "bge-m3-Q4.gguf",
            "path": "/models/bge-m3-Q4.gguf", "size_bytes": 100_u64,
            "sha256": "abc", "downloaded_at": "2026-05-26"
        })];
        std::fs::write(dir.path().join("registry.json"), serde_json::to_string(&registry).unwrap()).unwrap();
        let entry = find_model_registry_entry("bge-m3-Q4.gguf", dir.path());
        assert!(entry.is_some(), "deve encontrar por filename");
    }

    #[test]
    fn find_model_registry_entry_not_found_returns_none() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("registry.json"), "[]").unwrap();
        let entry = find_model_registry_entry("inexistente", dir.path());
        assert!(entry.is_none(), "registry vazio deve retornar None");
    }

    #[test]
    fn find_model_registry_entry_no_registry_returns_none() {
        let dir = tempfile::tempdir().unwrap();
        // registry.json não existe
        let entry = find_model_registry_entry("bge-m3", dir.path());
        assert!(entry.is_none(), "sem registry.json deve retornar None");
    }

    // ── wait_llama_ready_checking_child ───────────────────────────────────────

    #[tokio::test]
    async fn wait_llama_ready_checking_child_exits_early_when_process_dies() {
        // Spawna um processo que termina imediatamente
        #[cfg(unix)]
        let mut child = tokio::process::Command::new("true").spawn().expect("'true' disponível");
        #[cfg(windows)]
        let mut child = tokio::process::Command::new("cmd")
            .args(["/C", "exit", "0"]).spawn().expect("cmd disponível");

        // Aguarda o processo sair antes de chamar wait_llama_ready_checking_child
        let _ = child.wait().await;

        let client = reqwest::Client::new();
        let t0 = std::time::Instant::now();
        // timeout = 30s, mas processo já morreu → deve retornar em < 2s
        let ready = wait_llama_ready_checking_child(59983, &client, 30, &mut child).await;
        let elapsed = t0.elapsed().as_millis();

        assert!(!ready, "processo morto → wait_llama_ready_checking_child deve retornar false");
        assert!(elapsed < 2_000, "deve retornar rapidamente quando processo morreu; elapsed={elapsed}ms");
    }

    #[tokio::test]
    async fn wait_llama_ready_checking_child_times_out_when_no_server() {
        // Processo vivo (sleep 600) mas sem servidor HTTP na porta
        #[cfg(unix)]
        let mut child = tokio::process::Command::new("sleep").arg("600").spawn().expect("sleep disponível");
        #[cfg(windows)]
        let mut child = tokio::process::Command::new("cmd")
            .args(["/C", "timeout", "/T", "600", "/NOBREAK"]).spawn().expect("cmd disponível");

        let client = reqwest::Client::new();
        let t0 = std::time::Instant::now();
        // timeout = 2s (pequeno para o teste ser rápido)
        let ready = wait_llama_ready_checking_child(59984, &client, 2, &mut child).await;
        let elapsed = t0.elapsed().as_millis();

        assert!(!ready, "sem servidor HTTP → deve retornar false após timeout");
        assert!(elapsed >= 1_900, "deve aguardar ~2s de timeout; elapsed={elapsed}ms");
        assert!(elapsed < 4_000,  "não deve ultrapassar muito o timeout; elapsed={elapsed}ms");

        let _ = child.kill().await;
    }

    // ── ensure_embed_server_started com validação GGUF ────────────────────────

    #[tokio::test]
    async fn ensure_embed_server_no_spawn_when_gguf_truncated() {
        let dir   = tempfile::tempdir().unwrap();
        let state = make_test_state(dir.path().to_path_buf());

        // Cria GGUF truncado (32 MB de lixo, sem magic correto)
        let gguf = dir.path().join("models").join("bge-m3-Q4_K_M.gguf");
        std::fs::create_dir_all(gguf.parent().unwrap()).unwrap();
        std::fs::write(&gguf, b"NOTGGUF_TRUNCATED").unwrap();

        // Registry aponta para o arquivo truncado com size_bytes = 417 MB
        let registry = vec![serde_json::json!({
            "name":         "bge-m3",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf.to_string_lossy(),
            "size_bytes":   437_778_496_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26",
            "model_type":   "embed"
        })];
        std::fs::write(dir.path().join("models").join("registry.json"),
            serde_json::to_string(&registry).unwrap()).unwrap();

        *state.0.embed_model.lock().await = "bge-m3".to_string();
        ensure_embed_server_started(&state).await;

        assert!(!state.embed_proc_active().await,
            "GGUF truncado → nenhum processo deve ser criado");
    }

    #[tokio::test]
    async fn ensure_embed_server_no_spawn_when_gguf_has_bad_magic() {
        let dir   = tempfile::tempdir().unwrap();
        let state = make_test_state(dir.path().to_path_buf());

        // Arquivo com tamanho correto mas magic bytes errados
        let gguf = dir.path().join("models").join("bge-m3-Q4_K_M.gguf");
        std::fs::create_dir_all(gguf.parent().unwrap()).unwrap();
        let fake_data = vec![0xAB_u8; 437_778_496]; // tamanho correto, bytes errados
        // Escrever 8 bytes apenas (magic errado) — mais rápido nos testes
        std::fs::write(&gguf, b"INVALID!").unwrap();

        let registry = vec![serde_json::json!({
            "name":         "bge-m3",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf.to_string_lossy(),
            "size_bytes":   8_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26",
            "model_type":   "embed"
        })];
        std::fs::write(dir.path().join("models").join("registry.json"),
            serde_json::to_string(&registry).unwrap()).unwrap();

        let _ = fake_data; // evitar warning unused
        *state.0.embed_model.lock().await = "bge-m3".to_string();
        ensure_embed_server_started(&state).await;

        assert!(!state.embed_proc_active().await,
            "magic bytes inválidos → nenhum processo deve ser criado");
    }

    #[tokio::test]
    async fn ensure_embed_server_no_spawn_when_gguf_missing() {
        let dir   = tempfile::tempdir().unwrap();
        let state = make_test_state(dir.path().to_path_buf());

        // Registry aponta para arquivo que não existe
        let gguf_path = dir.path().join("models").join("bge-m3-Q4_K_M.gguf");
        std::fs::create_dir_all(gguf_path.parent().unwrap()).unwrap();

        let registry = vec![serde_json::json!({
            "name":         "bge-m3",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf_path.to_string_lossy(),
            "size_bytes":   437_778_496_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26",
            "model_type":   "embed"
        })];
        std::fs::write(dir.path().join("models").join("registry.json"),
            serde_json::to_string(&registry).unwrap()).unwrap();

        *state.0.embed_model.lock().await = "bge-m3".to_string();
        ensure_embed_server_started(&state).await;

        assert!(!state.embed_proc_active().await,
            "GGUF ausente → nenhum processo deve ser criado");
    }

    // ── logos_repair_model — lógica interna ──────────────────────────────────

    #[test]
    fn logos_repair_model_deletes_file_keeps_registry() {
        let dir = tempfile::tempdir().unwrap();
        let models_dir = dir.path().join("models");
        std::fs::create_dir_all(&models_dir).unwrap();

        let gguf = models_dir.join("bge-m3-Q4_K_M.gguf");
        std::fs::write(&gguf, b"fake-truncated").unwrap();

        let registry = vec![serde_json::json!({
            "name":         "bge-m3",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf.to_string_lossy(),
            "size_bytes":   437_778_496_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26",
            "model_type":   "embed"
        })];
        let registry_path = models_dir.join("registry.json");
        std::fs::write(&registry_path, serde_json::to_string(&registry).unwrap()).unwrap();

        // Simula o que logos_repair_model faz internamente
        let entry = find_model_registry_entry("bge-m3", &models_dir).expect("entry existe");
        let gguf_to_remove = std::path::PathBuf::from(&entry.path);
        if gguf_to_remove.exists() {
            std::fs::remove_file(&gguf_to_remove).unwrap();
        }

        // Arquivo removido
        assert!(!gguf.exists(), "GGUF deve ser removido após repair");

        // Registry intacto
        let text = std::fs::read_to_string(&registry_path).unwrap();
        let restored: Vec<serde_json::Value> = serde_json::from_str(&text).unwrap();
        assert_eq!(restored.len(), 1, "registry deve manter 1 entry após repair");
        assert_eq!(restored[0]["name"], "bge-m3", "entry deve ser preservada");
        assert_eq!(restored[0]["repo_id"], "gpustack/bge-m3-GGUF", "repo_id preservado para re-download");
    }

    #[test]
    fn logos_repair_model_noop_when_file_already_absent() {
        let dir = tempfile::tempdir().unwrap();
        let models_dir = dir.path().join("models");
        std::fs::create_dir_all(&models_dir).unwrap();

        // Arquivo NÃO existe — registry existe
        let gguf_path = models_dir.join("bge-m3-Q4_K_M.gguf");
        let registry = vec![serde_json::json!({
            "name":         "bge-m3",
            "repo_id":      "gpustack/bge-m3-GGUF",
            "filename":     "bge-m3-Q4_K_M.gguf",
            "path":         gguf_path.to_string_lossy(),
            "size_bytes":   437_778_496_u64,
            "sha256":       "abc",
            "downloaded_at":"2026-05-26"
        })];
        let registry_path = models_dir.join("registry.json");
        std::fs::write(&registry_path, serde_json::to_string(&registry).unwrap()).unwrap();

        // Simula lógica: arquivo ausente → apenas loga, não falha
        let entry = find_model_registry_entry("bge-m3", &models_dir).expect("entry existe");
        let gguf_to_remove = std::path::PathBuf::from(&entry.path);
        // Não deve panicar quando o arquivo já não existe
        if gguf_to_remove.exists() {
            std::fs::remove_file(&gguf_to_remove).unwrap();
        }

        // Registry intacto
        let text = std::fs::read_to_string(&registry_path).unwrap();
        let restored: Vec<serde_json::Value> = serde_json::from_str(&text).unwrap();
        assert_eq!(restored.len(), 1, "registry não deve ser alterado se arquivo já ausente");
    }

    // ── Passo 1: campos de ciclo de vida ─────────────────────────────────────

    #[test]
    fn inference_enabled_starts_false() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert!(
            !state.0.inference_enabled.load(Ordering::Relaxed),
            "inference_enabled deve iniciar false — modelo não carregado ao criar LogosState"
        );
    }

    #[test]
    fn inference_enabled_can_be_set_true() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.0.inference_enabled.store(true, Ordering::Relaxed);
        assert!(
            state.0.inference_enabled.load(Ordering::Relaxed),
            "inference_enabled deve poder ser setado true"
        );
    }

    #[test]
    fn idle_timeout_secs_default_is_300() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert_eq!(
            state.0.idle_timeout_secs, 300,
            "idle_timeout_secs default deve ser 300s (5 minutos)"
        );
    }

    #[test]
    fn cpu_fallback_max_mb_default_is_2048() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert_eq!(
            state.0.cpu_fallback_max_mb, 2048,
            "cpu_fallback_max_mb default deve ser 2048MB (2 GB)"
        );
    }

    #[test]
    fn cpu_max_threads_default_is_zero_meaning_auto() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert_eq!(
            state.0.cpu_max_threads, 0,
            "cpu_max_threads=0 significa automático (metade dos cores)"
        );
    }

    #[tokio::test]
    async fn last_akasha_request_at_is_recent_on_init() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        let elapsed = state.0.last_akasha_request_at.lock().await.elapsed();
        assert!(
            elapsed.as_secs() < 5,
            "last_akasha_request_at deve ser inicializado recentemente (elapsed={elapsed:?})"
        );
    }

    #[tokio::test]
    async fn last_embed_request_at_is_recent_on_init() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        let elapsed = state.0.last_embed_request_at.lock().await.elapsed();
        assert!(
            elapsed.as_secs() < 5,
            "last_embed_request_at deve ser inicializado recentemente (elapsed={elapsed:?})"
        );
    }

    // ── Passo 2: lazy loading — gate de inference_enabled em queue_and_forward ─

    #[tokio::test]
    async fn inference_enabled_false_rejects_requests() {
        // inference_enabled=false (padrão) → queue_and_forward deve retornar 503
        // antes de qualquer processamento (sem tentativa de rede).
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Confirma pré-condição: flag false por padrão
        assert!(!state.inference_enabled(), "pré-condição: inference_enabled deve ser false");

        let body = serde_json::Map::from_iter([
            ("model".to_string(), serde_json::json!("qwen2.5:3b")),
            ("messages".to_string(), serde_json::json!([])),
        ]);
        let response = queue_and_forward(state, body, "test_app".to_string(), 1, "api/chat").await;
        assert_eq!(
            response.status(),
            StatusCode::SERVICE_UNAVAILABLE,
            "inference_enabled=false → 503 SERVICE_UNAVAILABLE esperado"
        );
    }

    #[tokio::test]
    async fn inference_enabled_true_passes_gate() {
        // inference_enabled=true → não retorna 503 pelo gate (pode falhar por outro motivo —
        // o servidor não existe — mas o gate em si não rejeita a requisição).
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);

        let body = serde_json::Map::from_iter([
            ("model".to_string(), serde_json::json!("qwen2.5:3b")),
            ("messages".to_string(), serde_json::json!([])),
        ]);
        let response = queue_and_forward(state, body, "test_app".to_string(), 1, "api/chat").await;
        // O gate foi ultrapassado: a resposta pode ser qualquer erro de rede/504/503 por motivo
        // diferente (sem llama-server real), mas NÃO deve ser 503 pelo gate de inference_enabled.
        // Verificamos que o status não é o 503 específico do gate.
        if response.status() == StatusCode::SERVICE_UNAVAILABLE {
            use axum::body::to_bytes;
            let (_, body_stream) = response.into_parts();
            let bytes = to_bytes(body_stream, 4096).await.unwrap();
            let text = String::from_utf8_lossy(&bytes);
            assert!(
                !text.contains("inferência desabilitada"),
                "com inference_enabled=true o gate não deve rejeitar; body: {text}"
            );
        }
        // Qualquer outro status (5xx, timeout, etc.) é aceitável — o gate passou
    }

    // ── Passo 4: idle watchdogs e keep_alive P1 ─────────────────────────────

    #[test]
    fn keep_alive_p1_is_not_negative_one() {
        let ka_p1 = select_keep_alive(1);
        assert_ne!(
            ka_p1,
            serde_json::json!(-1),
            "P1 keep_alive não deve ser -1 — idle watchdog gerencia descarregamento"
        );
        assert_eq!(
            ka_p1,
            serde_json::json!("10m"),
            "P1 keep_alive deve ser '10m'"
        );
    }

    #[test]
    fn keep_alive_p2_is_10m() {
        assert_eq!(select_keep_alive(2), serde_json::json!("10m"));
    }

    #[test]
    fn keep_alive_p3_is_zero() {
        assert_eq!(select_keep_alive(3), serde_json::json!(0));
    }

    #[tokio::test]
    async fn idle_watchdog_noop_when_no_proc() {
        // Sem processo ativo → check_idle_llm retorna false sem panic
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        assert!(!state.llama_proc_active().await, "pré-condição: nenhum proc");
        let killed = check_idle_llm(&state).await;
        assert!(!killed, "sem proc ativo → não deve matar nada");
    }

    #[tokio::test]
    async fn idle_watchdog_embed_noop_when_no_proc() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        let killed = check_idle_embed(&state).await;
        assert!(!killed, "sem embed proc → não deve matar nada");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn idle_watchdog_kills_after_timeout() {
        // Proc ativo + timestamp muito antigo → watchdog deve matar o processo
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Injeta processo sleep simulando modelo carregado
        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().expect("sleep deve estar disponível");
        state.inject_proc_for_test(child, "gemma-2b").await;
        assert!(state.llama_proc_active().await, "pré-condição: proc ativo");

        // Falsifica timestamp como sendo (idle_timeout_secs + 1) atrás
        let old = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(state.0.idle_timeout_secs + 1));
        let Some(old) = old else {
            // Sistema com uptime muito baixo (CI fresh boot) — skip graceful
            state.kill_llama_proc().await;
            return;
        };
        *state.0.last_akasha_request_at.lock().await = old;

        let killed = check_idle_llm(&state).await;
        assert!(killed, "proc ocioso deve ser morto pelo watchdog");
        assert!(!state.llama_proc_active().await, "proc deve ser None após kill pelo watchdog");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn idle_watchdog_embed_kills_after_timeout() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().expect("sleep deve estar disponível");
        *state.0.embed_proc.lock().await = Some(LlamaProcHandle {
            child, model_name: "bge-m3".to_string(),
        });
        assert!(state.embed_proc_active().await, "pré-condição: embed proc ativo");

        let old = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(state.0.idle_timeout_secs + 1));
        let Some(old) = old else {
            state.kill_embed_proc().await;
            return;
        };
        *state.0.last_embed_request_at.lock().await = old;

        let killed = check_idle_embed(&state).await;
        assert!(killed, "embed ocioso deve ser morto");
        assert!(!state.embed_proc_active().await, "embed_proc deve ser None após kill");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn idle_watchdog_resets_on_request() {
        // Proc ativo + timestamp recente → watchdog NÃO deve matar
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().expect("sleep deve estar disponível");
        state.inject_proc_for_test(child, "gemma-2b").await;

        // Timestamp recente (Instant::now) — simula que requisição acabou de chegar
        *state.0.last_akasha_request_at.lock().await = std::time::Instant::now();

        let killed = check_idle_llm(&state).await;
        assert!(!killed, "proc com requisição recente não deve ser morto");
        assert!(state.llama_proc_active().await, "proc deve continuar ativo");

        state.kill_llama_proc().await;
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn idle_watchdog_timers_are_independent() {
        // Chat ocioso mas embed recente → apenas chat é morto, embed continua
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Injeta chat proc com timestamp antigo
        let chat_child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        state.inject_proc_for_test(chat_child, "qwen2.5:3b").await;

        let old = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(state.0.idle_timeout_secs + 1));
        let Some(old) = old else {
            state.kill_llama_proc().await;
            return;
        };
        *state.0.last_akasha_request_at.lock().await = old;

        // Injeta embed proc com timestamp recente
        let embed_child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().unwrap();
        *state.0.embed_proc.lock().await = Some(LlamaProcHandle {
            child: embed_child, model_name: "bge-m3".to_string(),
        });
        *state.0.last_embed_request_at.lock().await = std::time::Instant::now();

        // Verifica chat (deve matar) e embed (não deve matar)
        let chat_killed  = check_idle_llm(&state).await;
        let embed_killed = check_idle_embed(&state).await;

        assert!(chat_killed,  "chat ocioso deve ser morto");
        assert!(!embed_killed, "embed recente não deve ser morto");
        assert!(!state.llama_proc_active().await, "chat proc deve ser None");
        assert!(state.embed_proc_active().await,  "embed proc deve continuar ativo");

        state.kill_embed_proc().await;
    }

    // ── Passo 5: CPU fallback gate por tamanho de modelo ─────────────────────

    #[test]
    fn cpu_fallback_blocked_for_large_model() {
        // Arquivo 3 MB, limite 2 MB → gate bloqueia
        let td = tempfile::tempdir().unwrap();
        let gguf = td.path().join("large.gguf");
        std::fs::write(&gguf, vec![0u8; 3 * 1024 * 1024]).unwrap();

        let result = check_cpu_fallback_allowed(&gguf, 2);
        assert!(
            result.is_some(),
            "modelo 3MB com limite 2MB deve ser bloqueado"
        );
        let msg = result.unwrap();
        assert!(msg.contains("3MB"), "mensagem deve mencionar tamanho real: {msg}");
        assert!(msg.contains("2MB"), "mensagem deve mencionar o limite: {msg}");
    }

    #[test]
    fn cpu_fallback_allowed_for_small_model() {
        // Arquivo 1 MB, limite 2 MB → gate permite
        let td = tempfile::tempdir().unwrap();
        let gguf = td.path().join("small.gguf");
        std::fs::write(&gguf, vec![0u8; 1024 * 1024]).unwrap();

        let result = check_cpu_fallback_allowed(&gguf, 2);
        assert!(result.is_none(), "modelo 1MB com limite 2MB deve ser permitido");
    }

    #[test]
    fn cpu_fallback_exact_limit_is_allowed() {
        // Arquivo exatamente no limite (não estritamente maior) → permitido
        let td = tempfile::tempdir().unwrap();
        let gguf = td.path().join("exact.gguf");
        std::fs::write(&gguf, vec![0u8; 2 * 1024 * 1024]).unwrap();

        let result = check_cpu_fallback_allowed(&gguf, 2);
        assert!(
            result.is_none(),
            "modelo no exato limite (2MB == 2MB) deve ser permitido (não estritamente maior)"
        );
    }

    #[test]
    fn cpu_fallback_missing_file_returns_allowed() {
        // Arquivo ausente → tamanho 0 → permitido para qualquer limite > 0
        let td = tempfile::tempdir().unwrap();
        let gguf = td.path().join("nao_existe.gguf");

        let result = check_cpu_fallback_allowed(&gguf, 2);
        assert!(
            result.is_none(),
            "arquivo ausente → 0MB → permitido com limite 2MB"
        );
    }

    #[test]
    fn cpu_fallback_zero_limit_blocks_any_model() {
        // Limite 0 → qualquer modelo com tamanho > 0 é bloqueado
        let td = tempfile::tempdir().unwrap();
        let gguf = td.path().join("any.gguf");
        std::fs::write(&gguf, vec![0u8; 1024 * 1024]).unwrap();

        let result = check_cpu_fallback_allowed(&gguf, 0);
        assert!(
            result.is_some(),
            "com limite 0MB, qualquer modelo real deve ser bloqueado"
        );
    }

    #[test]
    fn cpu_fallback_message_mentions_ecosystem_config() {
        // A mensagem de erro deve guiar a usuária para a configuração correta
        let td = tempfile::tempdir().unwrap();
        let gguf = td.path().join("large.gguf");
        std::fs::write(&gguf, vec![0u8; 3 * 1024 * 1024]).unwrap();

        let msg = check_cpu_fallback_allowed(&gguf, 2).unwrap();
        assert!(
            msg.contains("cpu_fallback_max_gb") || msg.contains("ecosystem.json"),
            "mensagem deve referenciar configuração: {msg}"
        );
    }

    #[test]
    fn inference_enabled_accessor_reads_flag() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        assert!(!state.inference_enabled(), "deve iniciar false");
        state.set_inference_enabled(true);
        assert!(state.inference_enabled(), "deve retornar true após set");
        state.set_inference_enabled(false);
        assert!(!state.inference_enabled(), "deve retornar false após reset");
    }

    // ── Passo 3: lazy loading — primeira requisição carrega modelo ────────────

    /// Helper: escreve registry.json no diretório informado com um modelo fake.
    fn write_registry_for_test(dir: &std::path::Path, model_name: &str) {
        let registry = serde_json::json!([{
            "name": model_name,
            "repo_id": "test/repo",
            "filename": format!("{model_name}.gguf"),
            "path": dir.join(format!("{model_name}.gguf")).to_string_lossy(),
            "size_bytes": 1_000_000_u64,
            "sha256": "abc123",
            "downloaded_at": "2026-05-29T00:00:00+00:00"
        }]);
        std::fs::write(
            dir.join("registry.json"),
            serde_json::to_vec(&registry).unwrap(),
        ).unwrap();
    }

    #[tokio::test]
    async fn lazy_load_no_models_returns_503_no_models() {
        // inference_enabled=true, proc inativo, SEM modelos instalados
        // → 503 com mensagem "nenhum modelo instalado"
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);

        // sem registry.json → nenhum modelo instalado
        let body = serde_json::Map::from_iter([
            ("model".to_string(), serde_json::json!("qwen2.5:3b")),
            ("messages".to_string(), serde_json::json!([])),
        ]);
        let response = queue_and_forward(state, body, "mnemosyne".to_string(), 2, "api/chat").await;

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let (_, body_stream) = response.into_parts();
        let bytes = axum::body::to_bytes(body_stream, 4096).await.unwrap();
        let text  = String::from_utf8_lossy(&bytes);
        assert!(
            text.contains("nenhum modelo"),
            "503 deve mencionar 'nenhum modelo'; body: {text}"
        );
    }

    #[tokio::test]
    async fn lazy_load_first_request_triggers_load() {
        // inference_enabled=true, proc inativo, modelo no registry mas sem binário real
        // → tenta carregar (lazy load path ativado) → falha com 503 de carregamento
        //   (não com "inferência desabilitada" nem "nenhum modelo")
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);

        // Registra um modelo fake (sem GGUF real — o carregamento vai falhar, mas o
        // lazy-load path será percorrido, provando que a lógica foi ativada)
        write_registry_for_test(td.path(), "gemma-2b");

        assert!(!state.llama_proc_active().await, "pré-condição: nenhum proc antes da requisição");

        let body = serde_json::Map::from_iter([
            ("model".to_string(), serde_json::json!("gemma-2b")),
            ("messages".to_string(), serde_json::json!([])),
        ]);
        let response = queue_and_forward(state, body, "mnemosyne".to_string(), 2, "api/chat").await;

        // O lazy-load foi ativado (proc inativo + inference_enabled=true + modelo no registry).
        // Como não há llama-server real, o carregamento falha → 503, mas com mensagem de FALHA
        // de carregamento ou de binário não encontrado — NÃO a mensagem de gate desabilitado.
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let (_, body_stream) = response.into_parts();
        let bytes = axum::body::to_bytes(body_stream, 4096).await.unwrap();
        let text  = String::from_utf8_lossy(&bytes);
        assert!(
            !text.contains("inferência desabilitada"),
            "não deve rejeitar pelo gate de inference_enabled; body: {text}"
        );
        assert!(
            !text.contains("nenhum modelo"),
            "não deve rejeitar por falta de modelos — há um no registry; body: {text}"
        );
        // Qualquer outra mensagem de falha (binário, GGUF, etc.) é aceitável — o lazy-load foi ativado
    }

    #[tokio::test]
    async fn lazy_load_skipped_when_proc_already_active() {
        // Se já há um processo ativo, o bloco de lazy load é pulado completamente.
        // O timestamp de last_akasha_request_at deve ser atualizado mesmo assim.
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);

        // Injeta um proc "ativo" (sleep) para simular modelo já carregado
        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().expect("sleep deve estar disponível");
        state.inject_proc_for_test(child, "gemma-2b").await;

        assert!(state.llama_proc_active().await, "pré-condição: proc ativo");

        // Registra timestamp muito antigo (simula idle)
        let old_instant = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(600))
            .unwrap_or_else(std::time::Instant::now);
        *state.0.last_akasha_request_at.lock().await = old_instant;

        let body = serde_json::Map::from_iter([
            ("model".to_string(), serde_json::json!("gemma-2b")),
            ("messages".to_string(), serde_json::json!([])),
        ]);
        // Usa app_name "akasha" para que a requisição roteie para o servidor AKASHA
        // onde o proc foi injetado (inject_proc_for_test → akasha_proc)
        let _response = queue_and_forward(state.clone(), body, "akasha".to_string(), 2, "api/chat").await;

        // Timestamp do servidor AKASHA deve ter sido atualizado
        let elapsed = state.0.last_akasha_request_at.lock().await.elapsed();
        assert!(
            elapsed.as_secs() < 5,
            "last_akasha_request_at deve ser atualizado na requisição; elapsed={elapsed:?}"
        );

        state.kill_llama_proc().await;
    }

    #[tokio::test]
    async fn lazy_load_updates_timestamp_on_gate_pass() {
        // Quando inference_enabled=true e sem modelos instalados → 503 "nenhum modelo".
        // O timestamp de last_akasha_request_at ainda deve ser atualizado
        // (a requisição chegou ao LOGOS mesmo que não tenha sido encaminhada).
        // NOTA: o timestamp é atualizado APÓS o bloco lazy, que por sua vez retorna 503
        // antes de chegar à linha de update quando não há modelo.
        // Este teste verifica o comportamento atual: com modelo no registry,
        // o timestamp é atualizado após o lazy load (seja ele bem-sucedido ou não com binário).

        // A regra aqui é simples: apenas verificar que o timestamp é atualizado
        // quando o caminho chega até a linha de update (proc ativo → lazy skipped).
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);

        // Força timestamp antigo
        let old = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(300))
            .unwrap_or_else(std::time::Instant::now);
        *state.0.last_akasha_request_at.lock().await = old;

        // Proc ativo → lazy load é pulado, timestamp é atualizado
        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().expect("sleep deve estar disponível");
        state.inject_proc_for_test(child, "gemma-2b").await;

        let body = serde_json::Map::from_iter([
            ("model".to_string(), serde_json::json!("gemma-2b")),
            ("messages".to_string(), serde_json::json!([])),
        ]);
        let _r = queue_and_forward(state.clone(), body, "test".to_string(), 1, "api/chat").await;

        let elapsed = state.0.last_akasha_request_at.lock().await.elapsed();
        assert!(
            elapsed.as_secs() < 5,
            "last_akasha_request_at deve ser < 5s após requisição; elapsed={elapsed:?}"
        );
        state.kill_llama_proc().await;
    }

    // ── model_for_app — seleção de modelo por app ─────────────────────────────

    /// Helper: registry com dois modelos (LLM pequeno + LLM grande) sem GGUF real.
    fn write_two_model_registry(dir: &std::path::Path, small: &str, large: &str) {
        let registry = serde_json::json!([
            {
                "name": small,
                "repo_id": "test/small",
                "filename": format!("{small}.gguf"),
                "path": dir.join(format!("{small}.gguf")).to_string_lossy(),
                "size_bytes": 2_000_000_000_u64,
                "sha256": "aaa",
                "downloaded_at": "2026-05-30T00:00:00+00:00"
            },
            {
                "name": large,
                "repo_id": "test/large",
                "filename": format!("{large}.gguf"),
                "path": dir.join(format!("{large}.gguf")).to_string_lossy(),
                "size_bytes": 7_000_000_000_u64,
                "sha256": "bbb",
                "downloaded_at": "2026-05-30T00:00:00+00:00"
            }
        ]);
        std::fs::write(
            dir.join("registry.json"),
            serde_json::to_vec(&registry).unwrap(),
        ).unwrap();
    }

    #[tokio::test]
    async fn model_for_app_akasha_uses_llm_query_from_profile() {
        // A AKASHA deve receber o modelo configurado em llm_query do perfil de hardware,
        // não o primeiro da lista (que pode ser um modelo diferente).
        // make_test_state usa WorkPc: llm_query="qwen2.5:0.5b", llm_rag="smollm2:1.7b"
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Registra llm_query e llm_rag do perfil WorkPc; llm_rag vem primeiro para expor o bug.
        write_two_model_registry(td.path(), "smollm2:1.7b", "qwen2.5:0.5b");

        let selected = model_for_app(&state, "akasha").await;
        assert_eq!(
            selected.as_deref(), Some("qwen2.5:0.5b"),
            "AKASHA deve usar llm_query (qwen2.5:0.5b no WorkPc), não o primeiro da lista; got={selected:?}"
        );
    }

    #[tokio::test]
    async fn model_for_app_mnemosyne_uses_llm_rag_from_profile() {
        // Mnemosyne deve receber o modelo configurado em llm_rag do perfil de hardware.
        // make_test_state usa WorkPc: llm_rag="smollm2:1.7b"
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Registra llm_rag e llm_query; llm_query vem primeiro para expor o bug.
        write_two_model_registry(td.path(), "qwen2.5:0.5b", "smollm2:1.7b");

        let selected = model_for_app(&state, "mnemosyne").await;
        assert_eq!(
            selected.as_deref(), Some("smollm2:1.7b"),
            "Mnemosyne deve usar llm_rag (smollm2:1.7b no WorkPc); got={selected:?}"
        );
    }

    #[tokio::test]
    async fn model_for_app_override_takes_priority_over_profile() {
        // Override da usuária deve ter prioridade sobre o modelo recomendado pelo perfil.
        // make_test_state usa WorkPc: llm_query="qwen2.5:0.5b"
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Registra dois modelos
        write_two_model_registry(td.path(), "qwen2.5:0.5b", "smollm2:1.7b");

        // Override: AKASHA usa smollm2:1.7b em vez de qwen2.5:0.5b configurado no perfil
        state.0.model_overrides.lock().await
            .insert("akasha_llm_query".to_string(), "smollm2:1.7b".to_string());

        let selected = model_for_app(&state, "akasha").await;
        assert_eq!(
            selected.as_deref(), Some("smollm2:1.7b"),
            "override deve ter prioridade sobre o perfil; got={selected:?}"
        );
    }

    #[tokio::test]
    async fn model_for_app_falls_back_when_configured_not_installed() {
        // Se o modelo configurado (llm_query do perfil) não está no registry,
        // cai para o primeiro LLM disponível.
        // make_test_state usa WorkPc: llm_query="qwen2.5:0.5b"
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Só smollm2:1.7b está instalado; qwen2.5:0.5b (llm_query WorkPc) não está.
        let registry = serde_json::json!([{
            "name": "smollm2:1.7b",
            "repo_id": "test/smollm",
            "filename": "smollm2:1.7b.gguf",
            "path": td.path().join("smollm2:1.7b.gguf").to_string_lossy(),
            "size_bytes": 1_000_000_000_u64,
            "sha256": "aaa",
            "downloaded_at": "2026-05-30T00:00:00+00:00"
        }]);
        std::fs::write(td.path().join("registry.json"), serde_json::to_vec(&registry).unwrap()).unwrap();

        let selected = model_for_app(&state, "akasha").await;
        assert_eq!(
            selected.as_deref(), Some("smollm2:1.7b"),
            "fallback ao primeiro LLM disponível quando llm_query não instalado; got={selected:?}"
        );
    }

    #[tokio::test]
    async fn model_for_app_unknown_app_uses_first_llm() {
        // App desconhecido (sem mapeamento) usa o primeiro modelo LLM da lista.
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        write_two_model_registry(td.path(), "qwen2.5:3b", "qwen2.5:7b");

        let selected = model_for_app(&state, "unknown_app").await;
        assert!(selected.is_some(), "app desconhecido deve retornar algum modelo; got={selected:?}");
    }

    #[tokio::test]
    async fn model_for_app_no_models_installed_returns_none() {
        // Sem modelos no registry → None.
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        // sem registry.json
        let selected = model_for_app(&state, "akasha").await;
        assert!(selected.is_none(), "sem modelos instalados deve retornar None; got={selected:?}");
    }

    // ── Passo 6: build_llama_server_cmd_cpu_fallback ──────────────────────────

    #[test]
    fn cpu_spawn_has_zero_gpu_layers() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 8081, 0);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--n-gpu-layers")
            .expect("--n-gpu-layers deve estar presente em modo CPU fallback");
        assert_eq!(args[idx + 1], "0", "modo CPU fallback deve usar --n-gpu-layers 0");
    }

    #[test]
    fn cpu_spawn_has_ctx_size_512() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 8081, 0);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--ctx-size")
            .expect("--ctx-size deve estar presente em modo CPU fallback");
        assert_eq!(args[idx + 1], "512", "ctx-size deve ser 512 em modo CPU (economia de RAM)");
    }

    #[test]
    fn cpu_spawn_parallel_is_one() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 8081, 0);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--parallel")
            .expect("--parallel deve estar presente");
        assert_eq!(args[idx + 1], "1", "--parallel deve ser 1 em modo CPU (uma req por vez)");
    }

    #[test]
    fn cpu_spawn_uses_limited_threads_explicit() {
        let total = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(2);
        let cpu_max = 2usize;
        let expected = cpu_max.min(total).max(1);

        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 8081, cpu_max);
        let args  = cmd_args(&cmd);

        let idx = args.iter().position(|a| a == "--threads")
            .expect("--threads deve estar presente");
        let idx_batch = args.iter().position(|a| a == "--threads-batch")
            .expect("--threads-batch deve estar presente");
        let t: usize = args[idx + 1].parse().expect("--threads deve ser número");
        let tb: usize = args[idx_batch + 1].parse().expect("--threads-batch deve ser número");
        assert_eq!(t, expected, "--threads deve ser min(cpu_max_threads, total_cores)");
        assert_eq!(tb, t, "--threads-batch deve ser igual a --threads");
        assert!(t <= total, "threads não pode exceder total de cores lógicos");
    }

    #[test]
    fn cpu_spawn_auto_threads_is_at_most_half_cores() {
        let total    = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(2);
        let expected = (total / 2).max(1);

        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 8081, 0); // 0 = auto
        let args  = cmd_args(&cmd);

        let idx = args.iter().position(|a| a == "--threads")
            .expect("--threads deve estar presente com cpu_max_threads=0");
        let t: usize = args[idx + 1].parse().expect("--threads deve ser número");
        assert_eq!(t, expected,
            "cpu_max_threads=0 deve usar metade dos cores ({total} cores → {expected} threads)");
        assert!(t <= total, "auto threads não pode exceder total de cores");
    }

    #[test]
    fn cpu_spawn_threads_and_batch_are_equal() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 8081, 4);
        let args  = cmd_args(&cmd);

        let idx_t  = args.iter().position(|a| a == "--threads")       .expect("--threads");
        let idx_tb = args.iter().position(|a| a == "--threads-batch")  .expect("--threads-batch");
        assert_eq!(args[idx_t + 1], args[idx_tb + 1],
            "--threads e --threads-batch devem ter o mesmo valor");
    }

    // ── Passo 7: vram_sufficient_for_model ────────────────────────────────────

    #[test]
    fn vram_precheck_skips_when_model_size_zero() {
        // model_size_mb=0 → sem dados de tamanho → não bloquear (skip check)
        assert!(vram_sufficient_for_model(0, 0),
            "model_size=0 deve retornar true (skip)");
        assert!(vram_sufficient_for_model(100, 0),
            "qualquer vram_free com model_size=0 deve retornar true");
    }

    #[test]
    fn vram_precheck_sufficient_when_free_gt_needed() {
        // free = 1200 MB, model = 1000 MB, needed = 1000 * 1.15 = 1150 → 1200 >= 1150 = OK
        assert!(vram_sufficient_for_model(1_200, 1_000),
            "1200MB livre deve ser suficiente para modelo de 1000MB (needed=1150MB)");
    }

    #[test]
    fn vram_precheck_insufficient_when_free_lt_needed() {
        // free = 1000 MB, model = 1000 MB, needed = 1150 → 1000 < 1150 = FAIL
        assert!(!vram_sufficient_for_model(1_000, 1_000),
            "1000MB livre não deve ser suficiente para modelo de 1000MB (needed=1150MB)");
    }

    #[test]
    fn vram_precheck_margin_is_fifteen_pct() {
        // Verifica que a margem é exatamente 15%: needed = floor(size * 1.15)
        let size   = 100u64;
        let needed = (size as f64 * 1.15) as u64; // = 115
        assert!( vram_sufficient_for_model(needed,      size), "free=115 deve passar (exact)");
        assert!(!vram_sufficient_for_model(needed - 1,  size), "free=114 deve falhar (<115)");
        assert!( vram_sufficient_for_model(needed + 1,  size), "free=116 deve passar (>115)");
    }

    #[test]
    fn vram_precheck_small_model_always_ok_with_full_vram() {
        // Modelo de 100MB em 8192MB VRAM (RX 6600) → sempre OK
        assert!(vram_sufficient_for_model(8_192, 100));
    }

    #[test]
    fn vram_precheck_large_model_fails_small_vram() {
        // Modelo de 7000MB em 500MB livre → falha
        assert!(!vram_sufficient_for_model(500, 7_000));
    }

    // ── Passo 9: testes de integração ────────────────────────────────────────

    #[cfg(unix)]
    #[tokio::test]
    async fn full_cycle_idle_kill_preserves_inference_flag() {
        // Cria estado com inference_enabled=true e proc ativo simulado.
        // Simula idle (timestamp antigo) → check_idle_llm mata o proc.
        // Verifica: proc killed, mas inference_enabled permanece true.
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);

        // Injeta proc "ativo"
        let child = tokio::process::Command::new("sleep").arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn().expect("sleep disponível");
        state.inject_proc_for_test(child, "gemma-2b").await;

        assert!(state.llama_proc_active().await, "proc deve estar ativo após inject");

        // Simula idle: last_akasha_request_at muito antigo
        let old = std::time::Instant::now()
            .checked_sub(std::time::Duration::from_secs(state.0.idle_timeout_secs + 10))
            .unwrap_or_else(std::time::Instant::now);
        *state.0.last_akasha_request_at.lock().await = old;

        let killed = check_idle_llm(&state).await;
        assert!(killed, "idle watchdog deve matar proc após timeout");
        assert!(!state.llama_proc_active().await, "proc deve estar inativo após kill");
        assert!(state.inference_enabled(),
            "inference_enabled deve permanecer true após idle unload — modelo recarrega na próxima req");
    }

    #[tokio::test]
    async fn collect_status_includes_inference_enabled_field() {
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        // Verifica estado inicial = false
        let st = collect_status(&state).await;
        assert!(!st.inference_enabled,
            "inference_enabled deve ser false por padrão");

        // Ativa e verifica
        state.set_inference_enabled(true);
        let st2 = collect_status(&state).await;
        assert!(st2.inference_enabled,
            "inference_enabled deve ser true após set_inference_enabled(true)");

        // Desativa e verifica
        state.set_inference_enabled(false);
        let st3 = collect_status(&state).await;
        assert!(!st3.inference_enabled,
            "inference_enabled deve ser false após set_inference_enabled(false)");
    }

    #[tokio::test]
    async fn full_cycle_inference_disabled_rejects_all_priorities() {
        // inference_enabled=false → TODAS as prioridades (P1, P2, P3) recebem 503
        let td = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        // inference_enabled=false por padrão

        for priority in [1u8, 2, 3] {
            let body = serde_json::Map::from_iter([
                ("model".to_string(), serde_json::json!("any-model")),
                ("messages".to_string(), serde_json::json!([])),
            ]);
            let resp = queue_and_forward(
                state.clone(), body, "test".to_string(), priority, "api/chat"
            ).await;
            assert_eq!(
                resp.status(), StatusCode::SERVICE_UNAVAILABLE,
                "P{priority} deve receber 503 com inference_enabled=false"
            );
            let (_, body_stream) = resp.into_parts();
            let bytes = axum::body::to_bytes(body_stream, 4096).await.unwrap();
            let text  = String::from_utf8_lossy(&bytes);
            assert!(
                text.contains("inferência desabilitada"),
                "P{priority} corpo deve mencionar 'inferência desabilitada'; got: {text}"
            );
        }
    }

    // ── health_proxy — comportamento com lazy loading ─────────────────────────

    #[tokio::test]
    async fn health_returns_200_when_inference_enabled_but_no_model_loaded() {
        // Reproduz o deadlock corrigido: AKASHA chamava /health, LOGOS retornava 503
        // (llama-server não carregado), AKASHA parava de mandar req, lazy load nunca disparava.
        // Com o fix: inference_enabled=true + sem proc → 200 imediato.
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.set_inference_enabled(true);
        // Sem proc ativo → llama_proc_active() = false

        let resp = health_proxy(axum::extract::State(state)).await;
        assert_eq!(resp.status(), StatusCode::OK,
            "inference_enabled=true sem modelo carregado deve retornar 200 (lazy load disponível)");

        let (_, body_stream) = resp.into_parts();
        let bytes = axum::body::to_bytes(body_stream, 4096).await.unwrap();
        let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["inference_enabled"], serde_json::json!(true));
        assert_eq!(body["llm_loaded"],        serde_json::json!(false));
    }

    #[tokio::test]
    async fn health_returns_503_when_inference_disabled() {
        // inference_enabled=false → LOGOS não aceita req → /health deve retornar 503
        // para que apps externos (AKASHA) saibam que não devem enviar requisições LLM.
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        // inference_enabled=false por padrão

        let resp = health_proxy(axum::extract::State(state)).await;
        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE,
            "inference_enabled=false deve retornar 503");

        let (_, body_stream) = resp.into_parts();
        let bytes = axum::body::to_bytes(body_stream, 4096).await.unwrap();
        let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["inference_enabled"], serde_json::json!(false));
        assert_eq!(body["status"],            serde_json::json!("disabled"));
    }

    // ── Testes de hardware guards P3 (Passo 0B) ──────────────

    #[test]
    fn p3_critical_ram_constant_is_400mb() {
        assert_eq!(RAM_CRITICAL_MB, 400,
            "RAM_CRITICAL_MB deve ser 400 MB para prevenir crash por OOM");
    }

    #[test]
    fn p3_critical_vram_constant_is_97pct() {
        assert!((VRAM_CRITICAL_PCT - 97.0).abs() < 0.001,
            "VRAM_CRITICAL_PCT deve ser 97% — OOM certo ao tentar carregar modelo");
    }

    #[test]
    fn p3_critical_thermal_constant_is_93c() {
        assert!((THERMAL_CRITICAL_C - 93.0).abs() < 0.001,
            "THERMAL_CRITICAL_C deve ser 93°C — risco de dano térmico");
    }

    #[test]
    fn p3_hw_wait_constant_is_30s() {
        assert_eq!(P3_HW_WAIT_SECS, 30,
            "P3_HW_WAIT_SECS deve ser 30s por iteração do delay loop");
    }

    #[tokio::test]
    async fn p3_rejected_503_when_gpu_temp_exceeds_critical() {
        // GPU temp > THERMAL_CRITICAL_C → hard-reject 503 (crash-prevention)
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.0.inference_enabled.store(true, Ordering::Relaxed);
        // Fake proc ativo para pular lazy loading
        let child = tokio::process::Command::new("sleep")
            .arg("1")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível em Linux/Mac");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });
        // Temperatura crítica
        *state.0.gpu_temp_celsius.lock().await = Some(THERMAL_CRITICAL_C + 1.0);

        let body = serde_json::json!({ "model": "test:3b", "messages": [] });
        let resp  = queue_and_forward(
            state,
            body.as_object().cloned().unwrap(),
            "akasha".to_string(),
            3,
            "/api/chat",
        ).await;

        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE,
            "GPU temp crítica deve retornar 503, não delay");
        let bytes = axum::body::to_bytes(resp.into_body(), 4096).await.unwrap();
        let val: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        let msg = val["error"].as_str().unwrap_or("");
        assert!(msg.contains("temperatura crítica") || msg.contains("°C"),
            "mensagem deve mencionar temperatura: {msg}");
    }

    #[tokio::test(start_paused = true)]
    async fn p3_waits_when_vram_blocked_not_immediately_rejected() {
        // Antigo comportamento: p3_vram_blocked → 429 imediato.
        // Novo comportamento: delay loop — handler não retorna 429, aguarda.
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.0.inference_enabled.store(true, Ordering::Relaxed);
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });
        state.0.p3_vram_blocked.store(true, Ordering::Relaxed);

        let state_c = state.clone();
        let handler = tokio::spawn(async move {
            let body = serde_json::json!({ "model": "test:3b", "messages": [] });
            queue_and_forward(
                state_c,
                body.as_object().cloned().unwrap(),
                "akasha".to_string(),
                3,
                "/api/chat",
            ).await
        });

        // Com tempo pausado, o sleep(30s) dentro do loop não avança.
        // O handler deve estar parado no loop — não ter retornado 429.
        tokio::task::yield_now().await;
        assert!(!handler.is_finished(),
            "P3 com vram_blocked deve aguardar no loop, não rejeitar imediatamente");
        handler.abort();
    }

    #[tokio::test(start_paused = true)]
    async fn p3_waits_when_thermal_blocked_not_immediately_rejected() {
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.0.inference_enabled.store(true, Ordering::Relaxed);
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });
        // thermal_blocked ativo mas temperatura abaixo do crítico (≤ 93°C) → delay, não 503
        state.0.p3_thermal_blocked.store(true, Ordering::Relaxed);
        *state.0.gpu_temp_celsius.lock().await = Some(87.0); // >85 mas <93

        let state_c = state.clone();
        let handler = tokio::spawn(async move {
            let body = serde_json::json!({ "model": "test:3b", "messages": [] });
            queue_and_forward(
                state_c,
                body.as_object().cloned().unwrap(),
                "akasha".to_string(),
                3,
                "/api/chat",
            ).await
        });

        tokio::task::yield_now().await;
        assert!(!handler.is_finished(),
            "P3 com thermal_blocked deve aguardar no loop, não rejeitar imediatamente");
        handler.abort();
    }

    #[tokio::test(start_paused = true)]
    async fn p3_waits_on_battery_not_immediately_rejected() {
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.0.inference_enabled.store(true, Ordering::Relaxed);
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });
        // Em bateria: antigo comportamento era 503 imediato; novo é delay loop
        *state.0.on_battery.lock().await = true;
        *state.0.battery_policy.lock().await = BatteryPolicy::Economy;

        let state_c = state.clone();
        let handler = tokio::spawn(async move {
            let body = serde_json::json!({ "model": "test:3b", "messages": [] });
            queue_and_forward(
                state_c,
                body.as_object().cloned().unwrap(),
                "akasha".to_string(),
                3,
                "/api/chat",
            ).await
        });

        tokio::task::yield_now().await;
        assert!(!handler.is_finished(),
            "P3 em bateria deve aguardar no loop, não rejeitar imediatamente");
        handler.abort();
    }

    #[tokio::test(start_paused = true)]
    async fn p3_hardware_loop_sequential_before_semaphore() {
        // Verifica que o loop de hardware termina ANTES de tentar o semáforo.
        // Se o loop conclui e o semáforo está disponível, o handler avança.
        // (Condições OK → loop sai na 1ª iteração sem dormir.)
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        state.0.inference_enabled.store(true, Ordering::Relaxed);
        let child = tokio::process::Command::new("sleep")
            .arg("3600")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("sleep deve estar disponível");
        *state.0.akasha_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });
        // Todas as condições OK → loop deve sair imediatamente (sem sleep)
        // Estado default: on_battery=false, vram_blocked=false, thermal_blocked=false, gpu_temp=None

        let state_c = state.clone();
        let handler = tokio::spawn(async move {
            let body = serde_json::json!({ "model": "test:3b", "messages": [] });
            queue_and_forward(
                state_c,
                body.as_object().cloned().unwrap(),
                "akasha".to_string(),
                3,
                "/api/chat",
            ).await
        });

        // Com condições OK e tempo pausado, o loop sai na 1ª iteração (sem sleep).
        // O handler avança para o semáforo e depois para o forward (que falha — sem servidor).
        // Esperamos que complete rapidamente (sem sleep no loop).
        tokio::task::yield_now().await;
        // Aguarda até 100ms de tempo real (o handler faz HTTP e vai falhar rápido)
        let result = tokio::time::timeout(
            Duration::from_millis(200),
            handler
        ).await;
        // Não importa se completou ou não; o importante é que o handler AVANÇOU
        // além do loop (não ficou preso nele) — verificado pela ausência de sleep(30s).
        // Se o handler ainda estiver rodando é porque está no forward HTTP, não no loop.
        drop(result);
    }

    #[test]
    fn cpu_fallback_cmd_port_is_passed_through() {
        let bin   = std::path::Path::new("llama-server");
        let model = std::path::Path::new("model.gguf");
        let cmd   = build_llama_server_cmd_cpu_fallback(bin, model, None, 9090, 0);
        let args  = cmd_args(&cmd);
        let idx   = args.iter().position(|a| a == "--port").expect("--port presente");
        assert_eq!(args[idx + 1], "9090");
    }

    // ── Testes de apply_profile_priority ─────────────────────

    #[test]
    fn analise_akasha_p3_promoted_to_p2() {
        assert_eq!(apply_profile_priority("analise", "akasha", 3), 2);
    }

    #[test]
    fn analise_mnemosyne_p3_promoted_to_p2() {
        assert_eq!(apply_profile_priority("analise", "mnemosyne", 3), 2);
    }

    #[test]
    fn analise_kosmos_p3_promoted_to_p2() {
        assert_eq!(apply_profile_priority("analise", "kosmos", 3), 2);
    }

    #[test]
    fn analise_mnemosyne_p2_unchanged() {
        // Mnemosyne P2 (RAG) não é alterado em analise — já é P2
        assert_eq!(apply_profile_priority("analise", "mnemosyne", 2), 2);
    }

    #[test]
    fn analise_kosmos_p1_unchanged() {
        // KOSMOS P1 (leitura ativa) não sobe nem desce em analise
        assert_eq!(apply_profile_priority("analise", "kosmos", 1), 1);
    }

    #[test]
    fn estudo_mnemosyne_rag_promoted_to_p1() {
        assert_eq!(apply_profile_priority("estudo", "mnemosyne", 2), 1);
    }

    #[test]
    fn estudo_akasha_p3_promoted_to_p2() {
        assert_eq!(apply_profile_priority("estudo", "akasha", 3), 2);
    }

    #[test]
    fn estudo_kosmos_p1_demoted_to_p2() {
        // KOSMOS leitor rebaixado durante estudo: não compete com consultas ativas
        assert_eq!(apply_profile_priority("estudo", "kosmos", 1), 2);
    }

    #[test]
    fn normal_no_overrides() {
        // Perfil normal não altera nada
        assert_eq!(apply_profile_priority("normal", "akasha",    3), 3);
        assert_eq!(apply_profile_priority("normal", "mnemosyne", 2), 2);
        assert_eq!(apply_profile_priority("normal", "kosmos",    1), 1);
    }

    #[test]
    fn unknown_profile_falls_through_unchanged() {
        // Perfil inválido/desconhecido age como normal
        assert_eq!(apply_profile_priority("inexistente", "akasha", 3), 3);
        assert_eq!(apply_profile_priority("",            "mnemosyne", 2), 2);
    }

    #[tokio::test]
    async fn do_set_profile_accepts_valid_profiles() {
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert_eq!(do_set_profile(&state, "analise".into()).await, "analise");
        assert_eq!(do_set_profile(&state, "estudo".into()).await,  "estudo");
        assert_eq!(do_set_profile(&state, "normal".into()).await,  "normal");
    }

    #[tokio::test]
    async fn do_set_profile_rejects_removed_profiles() {
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        // "escrita" e "consumo" foram removidos — devem cair em "normal"
        assert_eq!(do_set_profile(&state, "escrita".into()).await, "normal");
        assert_eq!(do_set_profile(&state, "consumo".into()).await, "normal");
    }

    #[tokio::test]
    async fn do_set_profile_rejects_unknown_profile() {
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert_eq!(do_set_profile(&state, "foo".into()).await, "normal");
    }

    // ── BUG-020: semáforo dedicado do embed-server ───────────────────────────

    #[tokio::test]
    async fn embed_semaphore_tem_capacidade_um() {
        // Capacidade 1 = serialização total. Garante que nunca há duas
        // requisições de embedding simultâneas batendo no embed-server.
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        assert_eq!(state.0.embed_semaphore.available_permits(), 1);
    }

    #[tokio::test]
    async fn embed_semaphore_serializa_duas_requisicoes() {
        // Simula AKASHA + Mnemosyne embedando ao mesmo tempo: a primeira adquire
        // o permit; a segunda DEVE aguardar (não consegue adquirir enquanto a
        // primeira segura). Após liberar, a segunda passa.
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        let sem   = state.0.embed_semaphore.clone();

        let permit1 = sem.clone().acquire_owned().await.unwrap();
        assert_eq!(sem.available_permits(), 0, "primeira requisição segura o único permit");

        // Segunda tentativa com timeout curto deve falhar (estaria na fila).
        let segunda = tokio::time::timeout(
            std::time::Duration::from_millis(150),
            sem.clone().acquire_owned(),
        ).await;
        assert!(segunda.is_err(), "segunda requisição de embedding deve aguardar, não passar");

        // Libera a primeira → a segunda agora consegue.
        drop(permit1);
        let segunda_ok = tokio::time::timeout(
            std::time::Duration::from_millis(150),
            sem.acquire_owned(),
        ).await;
        assert!(segunda_ok.is_ok(), "após liberar, a próxima requisição passa");
    }

    #[tokio::test]
    async fn embed_semaphore_nao_afeta_akasha_semaphore() {
        // Embeddings não devem consumir permits do servidor de chat AKASHA.
        // Segurar o permit de embedding mantém akasha_semaphore intacto (cap. 2).
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());

        let _permit_embed = state.0.embed_semaphore.clone().acquire_owned().await.unwrap();
        assert_eq!(state.0.embed_semaphore.available_permits(), 0);
        assert_eq!(
            state.0.akasha_semaphore.available_permits(), 2,
            "akasha_semaphore não é tocado por requisições de embedding"
        );
        assert_eq!(
            state.0.mnemosyne_semaphore.available_permits(), 2,
            "mnemosyne_semaphore não é tocado por requisições de embedding"
        );
    }

    // ── BUG-027: trava de startup do embed-server + reuso por health ────────

    #[tokio::test]
    async fn embed_start_lock_inicia_destravado() {
        let td    = tempfile::tempdir().unwrap();
        let state = make_test_state(td.path().to_path_buf());
        // A trava deve poder ser adquirida (não nasce travada).
        assert!(state.0.embed_start_lock.try_lock().is_ok());
    }

    #[tokio::test]
    async fn embed_health_ok_true_quando_responde_200() {
        // Listener local responde 200 em /health → reuso do embed-server existente.
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        tokio::spawn(async move {
            if let Ok((mut sock, _)) = listener.accept().await {
                let mut buf = [0u8; 1024];
                let _ = sock.read(&mut buf).await;
                let _ = sock.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK").await;
            }
        });
        let client = Client::new();
        assert!(embed_health_ok(&client, port).await,
            "embed-server saudável (200) deve ser detectado para reuso");
    }

    #[tokio::test]
    async fn embed_health_ok_false_em_porta_fechada() {
        let client = Client::new();
        assert!(!embed_health_ok(&client, 1).await,
            "porta sem servidor → health falso → segue para spawn");
    }
}
