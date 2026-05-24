// ============================================================
//  HUB — Entry point da biblioteca Tauri
// ============================================================

mod commands;
mod ecosystem;
mod error;
mod logos;

pub use error::AppError;

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

// ----------------------------------------------------------
//  Logging em arquivo
// ----------------------------------------------------------

fn resolve_logs_dir(app_data_dir: &std::path::Path) -> std::path::PathBuf {
    app_data_dir.join("logs")
}

/// Move logs com mais de `archive_after_days` dias para `logs_dir/archive/`.
/// Remove arquivos do archive com mais de 30 dias.
fn cleanup_old_logs(logs_dir: &std::path::Path, archive_after_days: u64) {
    let now = std::time::SystemTime::now();
    let archive_threshold = now
        .checked_sub(std::time::Duration::from_secs(archive_after_days * 86_400))
        .unwrap_or(std::time::UNIX_EPOCH);
    let delete_threshold = now
        .checked_sub(std::time::Duration::from_secs(30 * 86_400))
        .unwrap_or(std::time::UNIX_EPOCH);

    let archive_dir = logs_dir.join("archive");
    let _ = std::fs::create_dir_all(&archive_dir);

    // Move logs antigos para archive/
    if let Ok(entries) = std::fs::read_dir(logs_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_file() { continue; }
            if let Ok(meta) = entry.metadata() {
                if let Ok(modified) = meta.modified() {
                    if modified < archive_threshold {
                        if let Some(name) = path.file_name() {
                            let dest = archive_dir.join(name);
                            let _ = std::fs::rename(&path, &dest);
                        }
                    }
                }
            }
        }
    }

    // Remove arquivos do archive com mais de 30 dias
    if let Ok(entries) = std::fs::read_dir(&archive_dir) {
        for entry in entries.flatten() {
            if let Ok(meta) = entry.metadata() {
                if let Ok(modified) = meta.modified() {
                    if modified < delete_threshold {
                        let _ = std::fs::remove_file(entry.path());
                    }
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
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            commands::backup::backup_key_data,
            commands::backup::restore_from_backup,
            commands::backup::check_db_integrity,
            commands::backup::recover_db,
            commands::backup::syncthing_checkpoint_app_dbs,
            commands::backup::ecosystem_reset,
            commands::config::get_service_credentials,
            commands::config::save_service_credentials,
            commands::git::git_init_sync_root,
            commands::git::git_status,
            commands::git::git_commit,
            commands::git::git_log,
            commands::git::git_diff,
            commands::git::git_commit_for_app,
            commands::git::git_scheduled_commit,
            commands::git::git_check_incoming,
            commands::git::git_get_paused,
            commands::git::git_set_paused,
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
            commands::launcher::toggle_inference,
            commands::launcher::launch_app,
            commands::launcher::launch_app_with_args,
            commands::launcher::is_app_running,
            commands::launcher::get_all_app_statuses,
            commands::launcher::validate_exe_path,
            commands::launcher::discover_app_exe,
            commands::launcher::auto_discover_all_exe_paths,
            commands::logos::logos_get_status,
            commands::logos::logos_silence,
            commands::logos::logos_set_profile,
            commands::logos::logos_list_models,
            commands::logos::logos_unload_model,
            commands::logos::logos_list_all_models,
            commands::logos::logos_get_model_assignments,
            commands::logos::logos_set_model_assignment,
            commands::logos::logos_get_recommended_models,
            commands::logos::logos_pull_model,
            commands::logos::logos_start_inference,
            commands::logos::logos_stop_inference,
            commands::logos::logos_set_vram_limit_pct,
            commands::logos::logos_abort_model_inference,
            commands::logos::logos_delete_model,
            commands::logos::logos_get_finetune_state,
            commands::logos::logos_trigger_finetune,
            commands::memory::memory_get_entries,
            commands::memory::memory_delete_entry,
            commands::memory::kosmos_get_analysis_stats,
            commands::memory::comm_history_get,
            commands::config::set_window_compact,
            commands::config::read_app_log,
            commands::notify::send_notification,
            commands::syncthing::syncthing_status,
            commands::syncthing::syncthing_start,
            commands::syncthing::syncthing_shutdown,
            commands::syncthing::syncthing_pause_all,
            commands::syncthing::syncthing_resume_all,
            commands::syncthing::syncthing_rescan,
            commands::syncthing::syncthing_get_paused,
            commands::syncthing::syncthing_set_paused,
            commands::syncthing::syncthing_pause_folder,
            commands::syncthing::syncthing_resume_folder,
            commands::syncthing::syncthing_get_log,
            commands::syncthing::syncthing_get_events,
            commands::syncthing::syncthing_get_credentials,
            commands::syncthing::syncthing_set_credentials,
            commands::sources::sources_get_domains,
            commands::sources::sources_set_flag,
            commands::sources::sources_get_akasha_backup,
            commands::interests::interests_get,
            commands::interests::interests_set_topic,
            commands::interests::interests_add_manual,
            commands::interests::interests_refresh,
        ])
        .setup(|app| {
            // Inicializar LOGOS antes do logging para ter o estado pronto
            let llama_server_url = {
                let eco = ecosystem::read_json();
                eco["logos"]["llama_server_url"]
                    .as_str()
                    .unwrap_or("http://localhost:8081")
                    .to_string()
            };
            let logos_state = logos::LogosState::new(llama_server_url);
            app.manage(logos_state.clone());
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                logos::start_server(logos_state, app_handle).await;
            });

            // System tray — clique esquerdo mostra/oculta; direito abre menu
            let show_item    = MenuItem::with_id(app, "show",    "Abrir HUB",       true, None::<&str>)?;
            let silence_item = MenuItem::with_id(app, "silence", "Silenciar LOGOS", true, None::<&str>)?;
            let sep          = PredefinedMenuItem::separator(app)?;
            let quit_item    = MenuItem::with_id(app, "quit",    "Fechar HUB",      true, None::<&str>)?;
            let tray_menu    = Menu::with_items(app, &[&show_item, &silence_item, &sep, &quit_item])?;

            if let Some(icon) = app.default_window_icon().cloned() {
                let _ = TrayIconBuilder::new()
                    .icon(icon)
                    .tooltip("HUB — Central do Ecossistema")
                    .menu(&tray_menu)
                    .show_menu_on_left_click(false)
                    .on_menu_event(|app, event| match event.id().as_ref() {
                        "show" => {
                            if let Some(win) = app.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        }
                        "silence" => {
                            tauri::async_runtime::spawn(async {
                                let _ = reqwest::Client::new()
                                    .post("http://127.0.0.1:7072/logos/silence")
                                    .send()
                                    .await;
                            });
                        }
                        "quit" => {
                            // Commit do HUB + salva HEAD antes de sair
                            let eco = ecosystem::read_json();
                            if let Some(sr) = eco["sync_root"].as_str() {
                                let root = std::path::Path::new(sr);
                                if root.is_dir() {
                                    let _ = commands::git::git_commit_hub_close(root);
                                    let _ = commands::git::save_git_head(root);
                                }
                            }
                            app.exit(0);
                        }
                        _ => {}
                    })
                    .on_tray_icon_event(|tray, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            let app = tray.app_handle();
                            if let Some(win) = app.get_webview_window("main") {
                                if win.is_visible().unwrap_or(false) {
                                    let _ = win.hide();
                                } else {
                                    let _ = win.show();
                                    let _ = win.set_focus();
                                }
                            }
                        }
                    })
                    .build(app);
            }

            // Fechar janela → ocultar na bandeja (não encerra o processo)
            if let Some(win) = app.get_webview_window("main") {
                let win_clone = win.clone();
                win.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = win_clone.hide();
                    }
                });
            }

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
