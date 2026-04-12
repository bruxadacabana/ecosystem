// ============================================================
//  HUB — AppError
//  Toda função falível retorna Result<T, AppError>.
// ============================================================

use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Error, Serialize)]
#[serde(tag = "kind", content = "message")]
pub enum AppError {
    #[error("Erro de I/O: {0}")]
    Io(String),

    #[error("Erro ao parsear JSON: {0}")]
    Json(String),

    #[error("Caminho inválido: {0}")]
    InvalidPath(String),

    #[error("Não encontrado: {0}")]
    NotFound(String),

    #[error("Configuração ausente: {0}")]
    MissingConfig(String),
}

impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        AppError::Io(e.to_string())
    }
}

impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::Json(e.to_string())
    }
}
