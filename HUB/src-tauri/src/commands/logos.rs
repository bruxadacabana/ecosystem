// ============================================================
//  HUB — commands/logos.rs
//  Tauri IPC commands para o frontend consultar e controlar o LOGOS.
// ============================================================

use crate::logos::{LogosState, ModelAssignment, OllamaModelEntry, OllamaModelInfo, StatusResponse};

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
