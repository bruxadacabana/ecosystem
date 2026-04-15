// ============================================================
//  HUB — Módulo Projetos
//  Lê projetos e páginas do banco SQLite do OGMA (read-only).
// ============================================================

use std::path::PathBuf;

use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};

use crate::AppError;

// ----------------------------------------------------------
//  Tipos públicos
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct OgmaProject {
    pub id:           i64,
    pub name:         String,
    pub description:  Option<String>,
    pub icon:         Option<String>,
    pub color:        Option<String>,
    pub project_type: String,
    pub subcategory:  Option<String>,
    pub status:       String,
    pub date_start:   Option<String>,
    pub date_end:     Option<String>,
    pub sort_order:   i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct OgmaPage {
    pub id:         i64,
    pub title:      String,
    pub icon:       Option<String>,
    pub parent_id:  Option<i64>,
    pub sort_order: i64,
    pub body_json:  Option<String>,
}

// ----------------------------------------------------------
//  Comandos IPC
// ----------------------------------------------------------

/// Lista os projetos não-arquivados do OGMA.
/// `data_path` = caminho para o diretório de dados do OGMA (contém ogma.db).
#[tauri::command]
pub fn list_ogma_projects(data_path: String) -> Result<Vec<OgmaProject>, AppError> {
    let conn = open_db(&data_path)?;

    let mut stmt = conn
        .prepare(
            "SELECT id, name, description, icon, color, project_type,
                    subcategory, status, date_start, date_end, sort_order
             FROM   projects
             WHERE  status != 'archived'
             ORDER  BY sort_order, name",
        )
        .map_err(|e| AppError::Json(format!("Erro ao preparar query de projetos: {e}")))?;

    let rows = stmt
        .query_map([], |row| {
            Ok(OgmaProject {
                id:           row.get(0)?,
                name:         row.get(1)?,
                description:  row.get(2)?,
                icon:         row.get(3)?,
                color:        row.get(4)?,
                project_type: row.get::<_, Option<String>>(5)?.unwrap_or_else(|| "custom".into()),
                subcategory:  row.get(6)?,
                status:       row.get::<_, Option<String>>(7)?.unwrap_or_else(|| "active".into()),
                date_start:   row.get(8)?,
                date_end:     row.get(9)?,
                sort_order:   row.get::<_, Option<i64>>(10)?.unwrap_or(0),
            })
        })
        .map_err(|e| AppError::Json(format!("Erro ao executar query de projetos: {e}")))?;

    let projects: Result<Vec<_>, _> = rows.collect();
    projects.map_err(|e| AppError::Json(format!("Erro ao ler linha de projeto: {e}")))
}

/// Lista as páginas não-deletadas de um projeto.
/// Retorna a árvore completa (incluindo subpáginas) — o frontend monta a hierarquia.
#[tauri::command]
pub fn list_project_pages(data_path: String, project_id: i64) -> Result<Vec<OgmaPage>, AppError> {
    let conn = open_db(&data_path)?;

    let mut stmt = conn
        .prepare(
            "SELECT id, title, icon, parent_id, sort_order, body_json
             FROM   pages
             WHERE  project_id = ?1
               AND  is_deleted = 0
             ORDER  BY sort_order, title",
        )
        .map_err(|e| AppError::Json(format!("Erro ao preparar query de páginas: {e}")))?;

    let rows = stmt
        .query_map([project_id], |row| {
            Ok(OgmaPage {
                id:         row.get(0)?,
                title:      row.get::<_, Option<String>>(1)?.unwrap_or_else(|| "Sem título".into()),
                icon:       row.get(2)?,
                parent_id:  row.get(3)?,
                sort_order: row.get::<_, Option<i64>>(4)?.unwrap_or(0),
                body_json:  row.get(5)?,
            })
        })
        .map_err(|e| AppError::Json(format!("Erro ao executar query de páginas: {e}")))?;

    let pages: Result<Vec<_>, _> = rows.collect();
    pages.map_err(|e| AppError::Json(format!("Erro ao ler linha de página: {e}")))
}

// ----------------------------------------------------------
//  Helpers internos
// ----------------------------------------------------------

fn open_db(data_path: &str) -> Result<Connection, AppError> {
    let db_path = PathBuf::from(data_path).join("ogma.db");
    if !db_path.exists() {
        return Err(AppError::NotFound(format!(
            "Banco de dados OGMA não encontrado em: {}",
            db_path.display()
        )));
    }
    // Abre em modo somente-leitura para não interferir com o OGMA em execução
    Connection::open_with_flags(&db_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|e| AppError::Io(format!("Não foi possível abrir ogma.db: {e}")))
}
