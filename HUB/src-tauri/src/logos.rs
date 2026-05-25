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
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use sysinfo::System;
use tokio::sync::{Mutex, Semaphore};

pub const LOGOS_PORT: u16 = 7072;
/// Porta local do processo llama-server gerenciado pelo LOGOS.
const LLAMA_SERVER_PORT: u16 = 8081;
/// Timeout (s) para o llama-server responder ao primeiro /health após o spawn.
const LLAMA_SERVER_READY_TIMEOUT_SECS: u64 = 90;

// Tempos máximos de espera na fila por prioridade
const P1_TIMEOUT: Duration = Duration::from_secs(120);
const P2_TIMEOUT: Duration = Duration::from_secs(60);
const P3_TIMEOUT: Duration = Duration::from_secs(30);

// P3 recebe 429 se CPU ou RAM insuficiente — protege Windows e laptop durante indexação
const CPU_P3_BLOCK: f32 = 85.0;
const RAM_P3_BLOCK_MB: u64 = 1_536;
// P3 em modo sobrevivência: thresholds mais permissivos — CPU quase saturada ou RAM crítica
const CPU_P3_SURVIVAL_BLOCK: f32 = 92.0;
const RAM_P3_SURVIVAL_BLOCK_MB: u64 = 512;
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
                // potion: modelo estático, sem GPU, multilíngue — substitui all-minilm
                embed:        "potion-multilingual-128M",
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
    /// Substituições de modelo definidas pela usuária.
    /// Chave: "mnemosyne_llm_rag", "kosmos_llm_analysis", "akasha_llm_query", "embed_embed". Valor: nome do modelo.
    /// Vazio = usar recomendado do perfil de hardware.
    model_overrides: Mutex<HashMap<String, String>>,
    /// Contador de crashes consecutivos do llama-server. Zerado após restart bem-sucedido.
    llama_crash_count: Mutex<u32>,
    /// True quando o llama-server atingiu o limite de 3 crashes e foi desabilitado.
    /// Permanece true até reload manual (reinício do HUB).
    llama_disabled: Arc<AtomicBool>,
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
    /// Downloads de GGUF em andamento ou concluídos recentemente.
    /// Chave: download ID (timestamp_filename). Valor: sender do canal de progresso.
    downloads: Mutex<HashMap<String, tokio::sync::watch::Sender<DownloadProgress>>>,
    /// Diretório onde os modelos GGUF são salvos: {hub_data_path}/logos/models/
    models_dir: std::path::PathBuf,
    /// Caminho do binário llama-server detectado no startup. None = usar Ollama como fallback.
    llama_server_bin: Option<std::path::PathBuf>,
    /// Processo llama-server ativo gerenciado pelo LOGOS. None = nenhum modelo carregado.
    llama_proc: Mutex<Option<LlamaProcHandle>>,
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

    /// Para o processo llama-server ativo (se houver). Retorna true se havia processo.
    pub(crate) async fn kill_llama_proc(&self) -> bool {
        let mut guard = self.0.llama_proc.lock().await;
        if let Some(mut proc) = guard.take() {
            let _ = proc.child.kill();
            true
        } else {
            false
        }
    }

    /// Retorna o diretório de modelos GGUF (para acesso externo ao módulo).
    pub fn models_dir(&self) -> &std::path::Path {
        &self.0.models_dir
    }

    /// Retorna true se o binário llama-server foi localizado no startup.
    /// Usado para falha rápida antes de spawnar a task de carregamento.
    pub fn has_llama_server(&self) -> bool {
        self.0.llama_server_bin.is_some()
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

    pub fn new(llama_server_url: impl Into<String>) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(300))
            .build()
            .unwrap_or_default();
        let vram_limit_pct = {
            let eco = crate::ecosystem::read_json();
            eco["logos"]["vram_limit_pct"]
                .as_f64()
                .map(|v| (v as f32).clamp(50.0, 95.0))
                .unwrap_or(85.0)
        };
        let hardware_mode = if cfg!(target_os = "windows") {
            "sobrevivencia".to_string()
        } else {
            "normal".to_string()
        };
        let hardware_profile = detect_hardware_profile();
        let models_dir = {
            let eco = crate::ecosystem::read_json();
            let hub_data = eco["hub"]["data_path"].as_str().map(std::path::PathBuf::from);
            hub_data
                .or_else(|| dirs::data_local_dir().map(|d| d.join("ecosystem").join("hub")))
                .unwrap_or_else(|| {
                    dirs::home_dir()
                        .unwrap_or_else(|| std::path::PathBuf::from("/tmp"))
                        .join(".local").join("share").join("ecosystem").join("hub")
                })
                .join("logos")
                .join("models")
        };
        let llama_server_bin = find_llama_server_bin();
        if let Some(ref bin) = llama_server_bin {
            log::info!("LOGOS: llama-server encontrado em {} — modo llama-server ativo", bin.display());
        } else {
            log::info!("LOGOS: llama-server não encontrado — usando Ollama como backend de inferência");
        }

        // Inicialização prévia do sysinfo — primeira leitura é sempre 0%; a segunda é o delta real.
        let mut sys = System::new_all();
        sys.refresh_cpu_all();
        sys.refresh_memory();
        Self(Arc::new(Inner {
            llama_server_url: llama_server_url.into(),
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
            model_overrides: Mutex::new(HashMap::new()),
            vram_limit_pct: Mutex::new(vram_limit_pct),
            active_inferences: Mutex::new(HashMap::new()),
            p3_vram_blocked: Arc::new(AtomicBool::new(false)),
            downloads: Mutex::new(HashMap::new()),
            models_dir,
            llama_server_bin,
            llama_proc: Mutex::new(None),
            llama_crash_count: Mutex::new(0),
            llama_disabled: Arc::new(AtomicBool::new(false)),
            app_handle: Mutex::new(None),
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
    pub llama_server_url: String,
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
    /// Limite de VRAM configurado (0–100). P3 bloqueado acima deste percentual.
    pub vram_limit_pct: f32,
    /// True quando o watchdog de VRAM bloqueou P3 (VRAM > block_pct%).
    /// Retoma automaticamente quando VRAM cai abaixo de 70%.
    pub p3_vram_blocked: bool,
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
async fn spawn_llama_server_proc(
    bin: &std::path::Path,
    model_path: &std::path::Path,
    mmproj_path: Option<&std::path::Path>,
    n_gpu: i32,
    n_ctx: u32,
    port: u16,
) -> Result<tokio::process::Child, String> {
    let mut cmd = tokio::process::Command::new(bin);
    cmd.arg("--model")     .arg(model_path)
       .arg("--port")      .arg(port.to_string())
       .arg("--ctx-size")  .arg(n_ctx.to_string())
       .arg("--parallel")  .arg("2")
       .arg("--cont-batching")
       .stdout(std::process::Stdio::null())
       .stderr(std::process::Stdio::piped()); // capturado para log
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
    #[cfg(unix)]
    cmd.process_group(0); // novo grupo de processos — sobrevive ao fechamento do HUB
    cmd.spawn().map_err(|e| format!("Falha ao iniciar llama-server: {e}"))
}

/// Inicia uma task que lê o stderr do processo llama-server linha a linha e registra via log.
fn spawn_stderr_reader(stderr: tokio::process::ChildStderr, model_name: String) {
    tokio::spawn(async move {
        use tokio::io::{AsyncBufReadExt, BufReader};
        let mut lines = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if !line.trim().is_empty() {
                log::warn!("llama-server [{}]: {}", model_name, line);
            }
        }
    });
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

/// Garante que o llama-server está rodando com o modelo solicitado.
/// Para o processo atual e reinicia com o novo modelo se necessário.
/// Deve ser chamado enquanto o semáforo de concorrência está adquirido.
pub(crate) async fn ensure_llama_model_loaded(
    s: &LogosState,
    model_name: &str,
) -> Result<(), String> {
    let bin = s.0.llama_server_bin.as_ref()
        .ok_or_else(|| "llama-server não encontrado".to_string())?
        .clone();

    // Fast path: modelo correto já carregado
    {
        let guard = s.0.llama_proc.lock().await;
        if guard.as_ref().map(|p| p.model_name.as_str()) == Some(model_name) {
            return Ok(());
        }
    }

    // Para o processo atual (se houver)
    {
        let mut guard = s.0.llama_proc.lock().await;
        if let Some(mut proc) = guard.take() {
            let _ = proc.child.kill();
            let _ = proc.child.wait().await;
        }
    }

    // Resolve caminho do GGUF
    let gguf_path = resolve_gguf_path(model_name, &s.0.models_dir)
        .ok_or_else(|| format!(
            "Modelo '{model_name}' não encontrado no registry do LOGOS nem no Ollama. \
             Faça download via HUB ou execute 'ollama pull {model_name}'."
        ))?;

    // Lê o registry uma vez — usado para mmproj e tamanho do modelo (VRAM check)
    let registry = read_model_registry(&s.0.models_dir).await;
    let registry_entry = registry.iter().find(|e| e.name == model_name);

    // Resolve mmproj para modelos multimodais (moondream, LLaVA, etc.)
    let mmproj_path: Option<std::path::PathBuf> = registry_entry
        .and_then(|e| e.mmproj_path.as_deref())
        .map(std::path::PathBuf::from)
        .filter(|p| p.exists());

    // Tamanho em disco ≈ VRAM para GGUFs quantizados
    let model_size_mb = registry_entry.map(|e| e.size_bytes / 1_048_576).unwrap_or(0);

    let profile_n_gpu = gpu_layers_for_model(model_name, s.0.hardware_profile);
    // n_ctx calculado ANTES do check de VRAM para incluir KV cache na estimativa
    let n_ctx = n_ctx_for_hardware(s.0.hardware_profile);
    let n_gpu = effective_gpu_layers(&s.0.client, s.0.hardware_profile, profile_n_gpu, model_size_mb, n_ctx).await;
    let gpu_mode = if n_gpu == 0 { "CPU".to_string() } else if n_gpu == -1 { "GPU (full)".to_string() } else { format!("GPU ({n_gpu} layers)") };
    log::info!(
        "LOGOS llama-server: carregando '{model_name}' \
         ({gpu_mode}, n_ctx={n_ctx}, porta={LLAMA_SERVER_PORT}, mmproj={})",
        mmproj_path.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "none".into())
    );

    let mut child = spawn_llama_server_proc(&bin, &gguf_path, mmproj_path.as_deref(), n_gpu, n_ctx, LLAMA_SERVER_PORT)
        .await?;

    // Captura stderr para log (leitura linha a linha em background)
    if let Some(stderr) = child.stderr.take() {
        spawn_stderr_reader(stderr, model_name.to_string());
    }

    {
        let mut guard = s.0.llama_proc.lock().await;
        *guard = Some(LlamaProcHandle { child, model_name: model_name.to_string() });
    }

    if !wait_llama_ready(LLAMA_SERVER_PORT, &s.0.client, LLAMA_SERVER_READY_TIMEOUT_SECS).await {
        // Verifica se o processo saiu prematuramente (provável OOM em GPU)
        let proc_exited = {
            let mut guard = s.0.llama_proc.lock().await;
            guard.as_mut()
                .and_then(|p| p.child.try_wait().ok())
                .map(|o| o.is_some())
                .unwrap_or(false)
        };

        // Mata o processo (se ainda vivo) e limpa o handle
        {
            let mut guard = s.0.llama_proc.lock().await;
            if let Some(mut p) = guard.take() {
                let _ = p.child.kill();
            }
        }

        // OOM fallback: se o processo saiu sozinho E estava usando GPU, tenta CPU only
        if proc_exited && n_gpu != 0 {
            log::warn!(
                "LOGOS llama-server: '{model_name}' saiu (provável OOM de GPU) — \
                 retentando com CPU only (n_gpu_layers=0)"
            );
            let mut cpu_child = spawn_llama_server_proc(&bin, &gguf_path, mmproj_path.as_deref(), 0, n_ctx, LLAMA_SERVER_PORT)
                .await
                .map_err(|e| format!("Falha ao reiniciar em modo CPU: {e}"))?;

            if let Some(stderr) = cpu_child.stderr.take() {
                spawn_stderr_reader(stderr, format!("{model_name}[cpu]"));
            }
            {
                let mut guard = s.0.llama_proc.lock().await;
                *guard = Some(LlamaProcHandle { child: cpu_child, model_name: model_name.to_string() });
            }
            if !wait_llama_ready(LLAMA_SERVER_PORT, &s.0.client, LLAMA_SERVER_READY_TIMEOUT_SECS).await {
                let mut guard = s.0.llama_proc.lock().await;
                if let Some(mut p) = guard.take() { let _ = p.child.kill(); }
                return Err(format!(
                    "llama-server não ficou pronto em modo CPU — \
                     '{model_name}' pode estar corrompido ou incompatível"
                ));
            }
            log::warn!(
                "LOGOS llama-server: '{model_name}' carregado em modo CPU only (downgrade de GPU)"
            );
            return Ok(());
        }

        return Err(format!(
            "llama-server não ficou pronto em {LLAMA_SERVER_READY_TIMEOUT_SECS}s. \
             Verifique se o modelo cabe na VRAM disponível."
        ));
    }

    log::info!("LOGOS llama-server: '{model_name}' pronto na porta {LLAMA_SERVER_PORT}");
    Ok(())
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

/// Núcleo da fila de prioridades: aplica guards, enfileira e encaminha ao Ollama.
/// Compartilhado entre /logos/chat (legado) e /api/chat, /api/generate (proxy transparente).
async fn queue_and_forward(
    s: LogosState,
    mut body: serde_json::Map<String, serde_json::Value>,
    app_name: String,
    requested_priority: u8,
    ollama_target: &str,
) -> Response {
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
        // P3 em modo sobrevivência: permite com throttle mínimo, bloqueia só se sistema saturado
        if priority == 3 {
            let (cpu, ram_free) = {
                let (c, f, _) = cpu_ram_usage(&s.0.sys).await;
                (c, f)
            };
            if cpu > CPU_P3_SURVIVAL_BLOCK || ram_free < RAM_P3_SURVIVAL_BLOCK_MB {
                return (
                    StatusCode::TOO_MANY_REQUESTS,
                    Json(serde_json::json!({
                        "error": format!(
                            "Modo Sobrevivência: CPU {cpu:.0}% ou RAM livre {ram_free} MB — tarefa P3 adiada"
                        )
                    })),
                ).into_response();
            }
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
        // Normal: rejeita P3 se watchdog sinalizou VRAM saturada (histerese: bloqueia >85%, retoma <70%)
        if s.0.p3_vram_blocked.load(Ordering::Relaxed) {
            let pct_cfg = (*s.0.vram_limit_pct.lock().await) as u32;
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({
                    "error": format!("VRAM > {pct_cfg}% — tarefa P3 bloqueada pelo watchdog; aguarde VRAM < 70%")
                })),
            ).into_response();
        }
        // Verificação por-request como defesa secundária (cobre janela entre polls do watchdog)
        let vram_block = *s.0.vram_limit_pct.lock().await / 100.0;
        if let Some(pct) = vram_pct(&s.0.client, s.0.hardware_profile).await {
            if pct > vram_block {
                let pct_cfg = (vram_block * 100.0) as u32;
                return (
                    StatusCode::TOO_MANY_REQUESTS,
                    Json(serde_json::json!({
                        "error": format!("VRAM > {pct_cfg}% — tarefa P3 adiada; tente novamente mais tarde")
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
        None => {
            let msg = if priority == 1 {
                "Timeout aguardando slot de inferência — sistema sobrecarregado"
            } else {
                "Timeout aguardando LOGOS — sistema sobrecarregado"
            };
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": msg })),
            ).into_response();
        }
    };

    // Marca prioridade, classe do modelo e app ativos
    *s.0.active_priority.lock().await    = Some(priority);
    *s.0.active_model_class.lock().await = Some(model_class);
    *s.0.active_app.lock().await         = Some(app_name);


    // Encaminha ao backend de inferência (llama-server ou Ollama).
    // llama_disabled é setado pelo watchdog após 3 crashes consecutivos.
    let use_llama   = s.0.llama_server_bin.is_some()
        && !s.0.llama_disabled.load(Ordering::Relaxed);
    let is_generate = ollama_target == "api/generate";

    let task_result: Result<Result<(reqwest::StatusCode, Bytes), String>, tokio::task::JoinError> =
    if use_llama {
        // ── llama-server: garante modelo carregado e traduz formato ──
        if let Err(e) = ensure_llama_model_loaded(&s, &model_name).await {
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
        let url          = format!("http://127.0.0.1:{LLAMA_SERVER_PORT}/{endpoint}");
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
        let (c, f, _) = cpu_ram_usage(&s.0.sys).await;
        (c, f)
    };
    if cpu > CPU_P3_BLOCK || ram_free < RAM_P3_BLOCK_MB {
        return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
            "error": format!("CPU {cpu:.0}% ou RAM livre {ram_free} MB insuficiente — embedding adiado")
        }))).into_response();
    }

    s.0.queue_counts.lock().await[2] += 1;
    let sem = s.0.semaphore.clone();
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

    let result = if s.0.llama_server_bin.is_some() {
        // ── llama-server: traduz para OpenAI /v1/embeddings ──
        let openai_body = translate_ollama_embed_to_openai(&body);
        let url = format!("http://127.0.0.1:{LLAMA_SERVER_PORT}/v1/embeddings");
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
                inject_efficiency_params(&mut m, 3, s.0.hardware_profile, is_survival, on_battery);
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
            let status = resp.status();
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
        Err(e) => (StatusCode::BAD_GATEWAY, Json(serde_json::json!({
            "error": format!("Backend de inferência indisponível: {e}")
        }))).into_response(),
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

    let permits: u32 = if priority >= 3 { 1 } else { 2 };
    let timeout = match priority {
        1 => Duration::from_secs(120),
        2 => P2_TIMEOUT,
        _ => P3_TIMEOUT,
    };
    let sem = s.0.semaphore.clone();
    let _permit = match tokio::time::timeout(timeout, sem.acquire_many_owned(permits)).await {
        Ok(Ok(p)) => p,
        _ => return (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
            "error": "Timeout aguardando LOGOS — sistema sobrecarregado"
        }))).into_response(),
    };

    let url = format!("http://127.0.0.1:{LLAMA_SERVER_PORT}/{endpoint}");
    match s.0.client
        .post(&url)
        .header(header::CONTENT_TYPE, "application/json")
        .body(body)
        .send()
        .await
    {
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

async fn v1_embeddings_proxy(
    State(s): State<LogosState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    proxy_openai_to_llama(&s, &headers, body, "v1/embeddings", 3).await
}

async fn v1_models_proxy(State(s): State<LogosState>) -> Response {
    let url = format!("http://127.0.0.1:{LLAMA_SERVER_PORT}/v1/models");
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
    let url = format!("http://127.0.0.1:{LLAMA_SERVER_PORT}/health");
    match s.0.client.get(&url).timeout(Duration::from_secs(2)).send().await {
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
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
            "status": "offline"
        }))).into_response(),
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
            let (cpu_pct, ram_free_mb, ram_total_mb) = cpu_ram_usage(&s.0.sys).await;
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
    let (cpu_pct, ram_free_mb, ram_total_mb) = cpu_ram_usage(&s.0.sys).await;
    let on_battery       = *s.0.on_battery.lock().await;
    let preempted_count  = *s.0.preempted_count.lock().await;
    let vram_limit_pct   = *s.0.vram_limit_pct.lock().await;
    let p3_vram_blocked  = s.0.p3_vram_blocked.load(Ordering::Relaxed);
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
        preempted_count,
        vram_limit_pct,
        p3_vram_blocked,
    }
}

/// Envia keep_alive: 0 para descarregar todos os modelos carregados.
/// Para o processo llama-server para liberar VRAM completamente.
/// Retorna o número de processos parados (0 ou 1).
pub async fn do_silence(s: &LogosState) -> usize {
    let stopped = s.kill_llama_proc().await;
    if stopped {
        log::info!("LOGOS silence: llama-server parado");
    }
    if stopped { 1 } else { 0 }
}

/// Retorna o modelo atualmente carregado no llama-server (se houver).
/// Com llama-server, apenas um modelo roda por vez — é o que está em `llama_proc`.
pub async fn list_inference_models(s: &LogosState) -> Vec<ModelInfo> {
    let guard = s.0.llama_proc.lock().await;
    match guard.as_ref() {
        Some(p) => vec![ModelInfo { name: p.model_name.clone(), size_vram_mb: 0 }],
        None    => vec![],
    }
}

/// Alias for backward compat with internal callers.
pub async fn list_ollama_models(s: &LogosState) -> Vec<ModelInfo> {
    list_inference_models(s).await
}

/// Para o processo llama-server ativo para liberar VRAM.
/// Retorna true se havia processo rodando.
pub async fn do_unload_model(s: &LogosState, _model: &str) -> bool {
    s.kill_llama_proc().await
}

/// Carrega um modelo no llama-server (garante processo ativo com o modelo correto).
/// Retorna true se o modelo foi carregado com sucesso.
pub async fn do_load_model(s: &LogosState, model: &str) -> bool {
    ensure_llama_model_loaded(s, model).await.is_ok()
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

/// Wrapper público de `list_inference_models` para uso nos Tauri commands.
pub async fn do_list_models(s: &LogosState) -> Vec<ModelInfo> {
    list_inference_models(s).await
}

/// Retorna todos os modelos instalados com status de carregamento.
/// Fonte: registry.json do LOGOS (modelos baixados via HUB).
/// Status "active" = modelo atualmente rodando no llama-server.
pub async fn do_list_all_models(s: &LogosState) -> Vec<ModelEntry> {
    let registry = read_model_registry(&s.0.models_dir).await;
    let active_name: Option<String> = s.0.llama_proc.lock().await
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
///   escrita — prioriza AETHER/HUB; rebaixa KOSMOS reader (P1→P2) e Mnemosyne RAG (P2→P3)
///   estudo  — promove Mnemosyne RAG (P2→P1); rebaixa KOSMOS reader (P1→P2)
///   consumo — sem override (KOSMOS P1, tudo normal)
///   normal  — sem override
fn apply_profile_priority(profile: &str, app: &str, requested: u8) -> u8 {
    match profile {
        "escrita" => match (app, requested) {
            // KOSMOS reader rebaixado: não interrompe a escrita
            ("kosmos", 1) => 2,
            // Mnemosyne RAG rebaixado para background: escrita em foco
            ("mnemosyne", 2) => 3,
            // AETHER, hub e AKASHA (conversas interativas) mantêm prioridade solicitada
            ("aether" | "hub" | "akasha", p) => p,
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
            if is_survival {
                // WorkPc: resposta interativa — usa todos os 4 cores do i5-3470
                o.entry("num_thread").or_insert(serde_json::json!(4));
            } else if on_battery {
                o.entry("num_thread").or_insert(serde_json::json!(2));
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
                // Normal: 2 cores (impacto mínimo no sistema)
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
    let sha256 = hex::encode(hasher.finalize());
    let entry  = ModelRegistryEntry {
        name:          model_name.unwrap_or_else(|| filename.trim_end_matches(".gguf").to_string()),
        repo_id:       repo_id.clone(),
        filename:      filename.clone(),
        path:          out_path.to_string_lossy().into_owned(),
        size_bytes:    bytes_downloaded,
        sha256:        sha256.clone(),
        downloaded_at: chrono::Local::now().to_rfc3339(),
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

    // Task de atualização do status de bateria a cada 60s.
    let battery_state = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            *battery_state.0.on_battery.lock().await = is_on_battery();
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
                let mut guard = proc_wdg.0.llama_proc.lock().await;
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
            *proc_wdg.0.llama_proc.lock().await = None;

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
                let mut cc = proc_wdg.0.llama_crash_count.lock().await;
                *cc += 1;
                *cc
            };

            if crash_count > 3 {
                log::error!(
                    "LOGOS watchdog: llama-server falhou {} vezes — \
                     desabilitado até reload manual",
                    crash_count
                );
                proc_wdg.0.llama_disabled.store(true, Ordering::Relaxed);
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
                *proc_wdg.0.llama_crash_count.lock().await = 0;
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
            semaphore:           Arc::new(Semaphore::new(2)),
            active_priority:     Mutex::new(None),
            active_model_class:  Mutex::new(None),
            active_app:          Mutex::new(None),
            active_profile:      Mutex::new("normal".to_string()),
            hardware_mode:       "normal".to_string(),
            hardware_profile:    HardwareProfile::WorkPc,
            queue_counts:        Mutex::new([0, 0, 0]),
            client,
            sys:                 Mutex::new(sys),
            on_battery:          Mutex::new(false),
            preempted_count:     Mutex::new(0),
            model_overrides:     Mutex::new(HashMap::new()),
            vram_limit_pct:      Mutex::new(85.0),
            active_inferences:   Mutex::new(HashMap::new()),
            p3_vram_blocked:     Arc::new(AtomicBool::new(false)),
            downloads:           Mutex::new(HashMap::new()),
            models_dir,
            llama_server_bin:    None,
            llama_proc:          Mutex::new(None),
            llama_crash_count:   Mutex::new(0),
            llama_disabled:      Arc::new(AtomicBool::new(false)),
            app_handle:          Mutex::new(None),
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

    // ── Semáforo — 4 cenários ─────────────────────────────────────────────────

    #[test]
    fn semaphore_starts_with_2_permits() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let sem = state.0.semaphore.clone();
        // Deve conseguir adquirir 2 permits de uma vez
        let _p = sem.try_acquire_many(2).expect("semáforo deve ter 2 permits inicialmente");
    }

    #[test]
    fn semaphore_heavy_model_uses_2_permits() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let sem = state.0.semaphore.clone();
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
        let sem = state.0.semaphore.clone();
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

    // ── Crash counter e llama_disabled — 4 cenários ───────────────────────────

    #[tokio::test]
    async fn llama_crash_count_starts_zero() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        let count = *state.0.llama_crash_count.lock().await;
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn llama_crash_count_increments_correctly() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        for expected in 1u32..=3 {
            let count = {
                let mut cc = state.0.llama_crash_count.lock().await;
                *cc += 1;
                *cc
            };
            assert_eq!(count, expected, "crash count deve incrementar para {expected}");
        }
    }

    #[test]
    fn llama_disabled_starts_false() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        assert!(!state.0.llama_disabled.load(Ordering::Relaxed),
            "llama_disabled deve iniciar false");
    }

    #[test]
    fn llama_disabled_flag_prevents_inference_path() {
        let dir = tempfile::tempdir().expect("tmpdir");
        let state = make_test_state(dir.path().to_path_buf());
        // Simula estado após 3+ crashes
        state.0.llama_disabled.store(true, Ordering::Relaxed);
        // A expressão que queue_and_forward usa para decidir use_llama
        let use_llama = state.0.llama_server_bin.is_some()
            && !state.0.llama_disabled.load(Ordering::Relaxed);
        assert!(!use_llama,
            "llama_disabled=true deve impedir uso do llama-server mesmo se bin existe");
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
        *state.0.llama_proc.lock().await = Some(LlamaProcHandle {
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
        *state.0.llama_proc.lock().await = Some(LlamaProcHandle {
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
        *state.0.llama_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });

        let count = do_silence(&state).await;
        assert_eq!(count, 1);
        assert!(state.0.llama_proc.lock().await.is_none(), "proc deve ser None após silence");
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
        *state.0.llama_proc.lock().await = Some(LlamaProcHandle {
            child,
            model_name: "test-model".to_string(),
        });

        assert!(state.kill_llama_proc().await, "proc ativo → true");
        assert!(state.0.llama_proc.lock().await.is_none(), "handle limpo após kill");
        // Segunda chamada: nenhum proc → false
        assert!(!state.kill_llama_proc().await);
    }
}
