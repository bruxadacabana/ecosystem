// ============================================================
//  AETHER — Entry point da biblioteca Tauri
// ============================================================

mod commands;
mod ecosystem;
mod error;
mod storage;
mod types;

pub use error::AppError;
pub use types::*;

use std::{path::PathBuf, sync::Mutex};
use tauri::Manager;

// ----------------------------------------------------------
//  Estado global gerenciado pelo Tauri
//  (injetado via .manage() e acessível em todos os commands)
// ----------------------------------------------------------

pub struct AppState {
    /// Caminho do vault atualmente aberto.
    /// None = vault ainda não selecionado (primeiro uso).
    pub vault_path: Mutex<Option<PathBuf>>,
}

// ----------------------------------------------------------
//  Logging em arquivo
// ----------------------------------------------------------

/// Devolve o diretório de logs para esta sessão:
///   {vault}/.aether/logs/   (se vault configurado)
///   {app_data_dir}/logs/    (fallback)
fn resolve_logs_dir(vault: Option<&PathBuf>, app_data_dir: &std::path::Path) -> PathBuf {
    vault
        .map(|v| v.join(".aether").join("logs"))
        .unwrap_or_else(|| app_data_dir.join("logs"))
}

/// Remove arquivos de log com mais de `keep_days` dias.
fn cleanup_old_logs(logs_dir: &std::path::Path, keep_days: u64) {
    let Ok(entries) = std::fs::read_dir(logs_dir) else { return };
    let threshold = std::time::SystemTime::now()
        .checked_sub(std::time::Duration::from_secs(keep_days * 86_400))
        .unwrap_or(std::time::UNIX_EPOCH);

    for entry in entries.flatten() {
        if let Ok(meta) = entry.metadata() {
            if let Ok(modified) = meta.modified() {
                if modified < threshold {
                    let _ = std::fs::remove_file(entry.path());
                }
            }
        }
    }
}

// ----------------------------------------------------------
//  Run
// ----------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            vault_path: Mutex::new(None),
        })
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            // Vault + Projetos
            commands::project::get_vault_path,
            commands::project::set_vault_path,
            commands::project::list_projects,
            commands::project::create_project,
            commands::project::open_project,
            commands::project::delete_project,
            commands::project::update_project,
            // Livros
            commands::book::list_books,
            commands::book::create_book,
            commands::book::open_book,
            commands::book::update_book,
            commands::book::delete_book,
            commands::book::reorder_books,
            // Capítulos
            commands::chapter::create_chapter,
            commands::chapter::read_chapter,
            commands::chapter::save_chapter,
            commands::chapter::delete_chapter,
            commands::chapter::reorder_chapters,
            commands::chapter::update_chapter_title,
            commands::chapter::update_chapter_status,
            commands::chapter::update_chapter_synopsis,
            // Lixeira
            commands::chapter::trash_chapter,
            commands::chapter::restore_chapter,
            commands::chapter::list_trash,
            commands::chapter::list_books_for_trash,
            // Scratchpad
            commands::chapter::read_scratchpad,
            commands::chapter::save_scratchpad,
            // Vínculos (4.6)
            commands::chapter::update_chapter_links,
            // Metas de palavras (5.1)
            commands::chapter::set_chapter_word_goal,
            commands::chapter::set_book_word_goal,
            // Sessões (5.2) e Streak (5.3)
            commands::stats::start_session,
            commands::stats::end_session,
            commands::stats::list_sessions,
            commands::stats::get_writing_streak,
            // Snapshots (5.5)
            commands::chapter::list_snapshots,
            commands::chapter::create_snapshot,
            commands::chapter::load_snapshot_content,
            commands::chapter::restore_snapshot,
            commands::chapter::delete_snapshot,
            // Anotações inline (5.6)
            commands::chapter::list_annotations,
            commands::chapter::create_annotation,
            commands::chapter::update_annotation,
            commands::chapter::delete_annotation,
            // Personagens (4.1)
            commands::character::list_characters,
            commands::character::create_character,
            commands::character::load_character,
            commands::character::save_character,
            commands::character::delete_character,
            // Relacionamentos (4.2)
            commands::character::list_relationships,
            commands::character::add_relationship,
            commands::character::update_relationship,
            commands::character::delete_relationship,
            // Worldbuilding (4.3)
            commands::world::list_world_notes,
            commands::world::create_world_note,
            commands::world::load_world_note,
            commands::world::save_world_note,
            commands::world::delete_world_note,
            // Timeline (4.4)
            commands::world::load_timeline,
            commands::world::create_timeline_event,
            commands::world::save_timeline_event,
            commands::world::reorder_timeline,
            commands::world::delete_timeline_event,
            // Imagens (4.5)
            commands::world::attach_image,
            commands::world::load_image,
            commands::world::remove_image,
        ])
        .setup(|app| {
            // Carregar vault salvo sem expor dados além do necessário
            let app_data_dir = app.path().app_data_dir().map_err(|e| {
                eprintln!("AETHER: Não foi possível obter app_data_dir: {e}");
                e
            })?;

            let mut loaded_vault: Option<PathBuf> = None;

            match storage::load_app_data(&app_data_dir) {
                Ok(app_data) => {
                    if let Some(vault_path) = app_data.vault_path {
                        loaded_vault = Some(vault_path.clone());
                        match app.state::<AppState>().vault_path.lock() {
                            Ok(mut guard) => {
                                *guard = Some(vault_path);
                            }
                            Err(e) => {
                                eprintln!("AETHER: Mutex envenenado ao inicializar vault: {e}");
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("AETHER: Não foi possível carregar app_data: {e}");
                }
            }

            // Inicializar logging em arquivo
            let logs_dir = resolve_logs_dir(loaded_vault.as_ref(), &app_data_dir);
            if let Err(e) = std::fs::create_dir_all(&logs_dir) {
                eprintln!("AETHER: Não foi possível criar diretório de logs: {e}");
            } else {
                cleanup_old_logs(&logs_dir, 7);
            }

            let date = chrono::Local::now().format("%Y-%m-%d").to_string();
            let file_name = format!("aether-{date}");

            let log_level = if cfg!(debug_assertions) {
                log::LevelFilter::Debug
            } else {
                log::LevelFilter::Info
            };

            let mut log_targets = vec![
                tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Folder {
                        path: logs_dir,
                        file_name: Some(file_name),
                    },
                ),
            ];

            if cfg!(debug_assertions) {
                log_targets.push(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Stdout,
                ));
            }

            app.handle().plugin(
                tauri_plugin_log::Builder::default()
                    .targets(log_targets)
                    .level(log_level)
                    .build(),
            )?;

            // Registrar vault_path no ecosystem compartilhado (falha silenciosa)
            if let Some(ref vault) = loaded_vault {
                ecosystem::write_section(
                    "aether",
                    serde_json::json!({ "vault_path": vault.to_string_lossy() }),
                )
                .unwrap_or_else(|e| eprintln!("AETHER: ecosystem write falhou: {e}"));
            }

            log::info!("AETHER iniciado. Vault: {:?}", loaded_vault);

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
