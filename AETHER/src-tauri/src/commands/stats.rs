// ============================================================
//  AETHER — Commands Tauri: Estatísticas & Sessões
//  Sessões de escrita com timer (5.2)
//  Streak diário (5.3)
//  Toda função retorna Result<T, AppError> — sem .unwrap().
// ============================================================

use tauri::State;

use crate::{
    commands::project::require_vault,
    error::AppError,
    storage,
    types::WritingSession,
    AppState,
};

// ----------------------------------------------------------
//  Sessões (5.2)
// ----------------------------------------------------------

/// Inicia uma nova sessão de escrita.
/// Chamado quando o editor carrega um capítulo.
#[tauri::command]
pub fn start_session(
    state: State<'_, AppState>,
    project_id: String,
    book_id: String,
    chapter_id: String,
    words_at_start: usize,
    goal_minutes: Option<u32>,
) -> Result<WritingSession, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::start_session(
        &vault,
        &project_id,
        &book_id,
        &chapter_id,
        words_at_start,
        goal_minutes,
    );
    if let Ok(ref s) = result {
        log::info!(
            "Sessão iniciada: {} (cap: {}, palavras: {})",
            s.id, chapter_id, words_at_start
        );
    }
    result
}

/// Encerra uma sessão de escrita com a contagem final de palavras.
/// Chamado quando o usuário troca de capítulo ou fecha o editor.
#[tauri::command]
pub fn end_session(
    state: State<'_, AppState>,
    session_id: String,
    words_at_end: usize,
) -> Result<WritingSession, AppError> {
    let vault = require_vault(&state)?;
    let result = storage::end_session(&vault, &session_id, words_at_end);
    if let Ok(ref s) = result {
        let words_written = s.words_at_end.saturating_sub(s.words_at_start);
        log::info!(
            "Sessão encerrada: {} (+{} palavras)",
            session_id, words_written
        );
    }
    result
}

/// Lista todas as sessões, opcionalmente filtradas por projeto.
#[tauri::command]
pub fn list_sessions(
    state: State<'_, AppState>,
    project_id: Option<String>,
) -> Result<Vec<WritingSession>, AppError> {
    let vault = require_vault(&state)?;
    let sessions = storage::load_sessions(&vault)?;
    if let Some(pid) = project_id {
        Ok(sessions.into_iter().filter(|s| s.project_id == pid).collect())
    } else {
        Ok(sessions)
    }
}

// ----------------------------------------------------------
//  Streak (5.3) — derivado das sessões
// ----------------------------------------------------------

/// Retorna o streak de escrita em dias consecutivos para um projeto.
/// Um "dia de escrita" = pelo menos uma sessão encerrada com
/// words_at_end > words_at_start naquele dia (hora local).
#[tauri::command]
pub fn get_writing_streak(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<u32, AppError> {
    let vault = require_vault(&state)?;
    let sessions = storage::load_sessions(&vault)?;

    // Coletar datas únicas em que houve escrita para este projeto
    let mut writing_dates: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    for s in &sessions {
        if s.project_id != project_id {
            continue;
        }
        if s.words_at_end <= s.words_at_start {
            continue;
        }
        // ended_at em formato ISO 8601 — pegar apenas os 10 primeiros chars (YYYY-MM-DD)
        if let Some(ended) = &s.ended_at {
            if ended.len() >= 10 {
                writing_dates.insert(ended[..10].to_owned());
            }
        }
    }

    if writing_dates.is_empty() {
        return Ok(0);
    }

    // Hoje em UTC (o campo ended_at usa UTC/RFC3339)
    let today = chrono::Utc::now().format("%Y-%m-%d").to_string();

    // Contar streak: iterar de hoje para trás
    let mut streak = 0u32;
    let mut check_date = today.clone();

    loop {
        if writing_dates.contains(&check_date) {
            streak += 1;
        } else {
            // Se hoje ainda não escreveu, não quebra o streak — verifica ontem
            if check_date == today && streak == 0 {
                // Avançar para ontem antes de desistir
                if let Some(prev) = prev_date(&check_date) {
                    check_date = prev;
                    if writing_dates.contains(&check_date) {
                        streak += 1;
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            } else {
                break;
            }
        }
        if let Some(prev) = prev_date(&check_date) {
            check_date = prev;
        } else {
            break;
        }
    }

    Ok(streak)
}

/// Retorna a data do dia anterior no formato YYYY-MM-DD.
fn prev_date(date: &str) -> Option<String> {
    use chrono::NaiveDate;
    let d = NaiveDate::parse_from_str(date, "%Y-%m-%d").ok()?;
    let prev = d.pred_opt()?;
    Some(prev.format("%Y-%m-%d").to_string())
}
