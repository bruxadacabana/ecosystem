// ============================================================
//  AETHER — AppError
//  Enum central de erros. Toda função que pode falhar retorna
//  Result<T, AppError>. Nunca usar .unwrap() / .expect() fora
//  de testes.
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

    #[error("Vault não configurado")]
    VaultNotConfigured,

    #[error("Vault não encontrado: {0}")]
    VaultNotFound(String),

    #[error("Projeto não encontrado: {0}")]
    ProjectNotFound(String),

    #[error("Livro não encontrado: {0}")]
    BookNotFound(String),

    #[error("Capítulo não encontrado: {0}")]
    ChapterNotFound(String),

    #[error("Caminho inválido: {0}")]
    InvalidPath(String),

    #[error("Nome inválido: {0}")]
    InvalidName(String),

    #[error("Já existe: {0}")]
    AlreadyExists(String),

    #[error("Não encontrado: {0}")]
    NotFound(String),
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
