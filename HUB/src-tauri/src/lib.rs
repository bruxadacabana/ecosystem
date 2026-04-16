// ============================================================
//  HUB — Entry point da biblioteca Tauri
// ============================================================

mod commands;
mod ecosystem;
mod error;

pub use error::AppError;

use tauri::Manager;

// ----------------------------------------------------------
//  Logging em arquivo
// ----------------------------------------------------------

fn resolve_logs_dir(app_data_dir: &std::path::Path) -> std::path::PathBuf {
    app_data_dir.join("logs")
}

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
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::config::read_ecosystem_config,
            commands::config::validate_path,
            commands::config::save_ecosystem_config,
            commands::config::apply_sync_root,
            commands::writing::list_writing_projects,
            commands::writing::list_books,
            commands::writing::read_chapter,
            commands::reading::list_articles,
            commands::reading::read_article,
            commands::reading::toggle_read,
            commands::projects::list_ogma_projects,
            commands::projects::list_project_pages,
            commands::launcher::launch_app,
            commands::launcher::is_app_running,
            commands::launcher::get_all_app_statuses,
            commands::launcher::validate_exe_path,
            commands::launcher::discover_app_exe,
            commands::launcher::auto_discover_all_exe_paths,
        ])
        .setup(|app| {
            let app_data_dir = app.path().app_data_dir().map_err(|e| {
                eprintln!("HUB: Não foi possível obter app_data_dir: {e}");
                e
            })?;

            // Inicializar logging
            let logs_dir = resolve_logs_dir(&app_data_dir);
            if let Err(e) = std::fs::create_dir_all(&logs_dir) {
                eprintln!("HUB: Não foi possível criar diretório de logs: {e}");
            } else {
                cleanup_old_logs(&logs_dir, 7);
            }

            let date = chrono::Local::now().format("%Y-%m-%d").to_string();
            let file_name = format!("hub-{date}");

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

            log::info!("HUB iniciado.");

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
