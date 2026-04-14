// ============================================================
//  HUB — Launcher de apps externos
//  Inicia apps do ecossistema e monitora se estão em execução.
// ============================================================

use std::collections::HashMap;
use std::process::Command;

use crate::AppError;

// ----------------------------------------------------------
//  Comandos IPC
// ----------------------------------------------------------

/// Inicia um app externo pelo caminho do executável.
#[tauri::command]
pub fn launch_app(exe_path: String) -> Result<(), AppError> {
    if exe_path.trim().is_empty() {
        return Err(AppError::InvalidPath(
            "Caminho do executável não configurado.".into(),
        ));
    }
    Command::new(&exe_path)
        .spawn()
        .map(|_| ())
        .map_err(|e| AppError::Io(format!("Não foi possível iniciar '{}': {}", exe_path, e)))
}

/// Verifica se um processo correspondente ao executável está em execução.
#[tauri::command]
pub fn is_app_running(exe_path: String) -> bool {
    if exe_path.trim().is_empty() {
        return false;
    }
    let name = process_name_from_path(&exe_path);
    check_running(&name)
}

/// Retorna o status de execução para todos os apps informados.
/// `exe_paths`: map `{ "app_name" → "caminho_executável" }`.
#[tauri::command]
pub fn get_all_app_statuses(exe_paths: HashMap<String, String>) -> HashMap<String, bool> {
    exe_paths
        .into_iter()
        .map(|(app, path)| {
            let running = if path.trim().is_empty() {
                false
            } else {
                let name = process_name_from_path(&path);
                check_running(&name)
            };
            (app, running)
        })
        .collect()
}

/// Verifica se um caminho aponta para um arquivo executável existente.
#[tauri::command]
pub fn validate_exe_path(path: String) -> bool {
    if path.trim().is_empty() {
        return false;
    }
    std::path::Path::new(&path).is_file()
}

/// Tenta descobrir automaticamente um executável testando uma lista de candidatos.
/// Cada candidato pode ser um nome simples (buscado no PATH) ou um caminho completo.
#[tauri::command]
pub fn discover_app_exe(candidates: Vec<String>) -> Option<String> {
    for candidate in &candidates {
        // Caminho absoluto/relativo que já existe como arquivo
        if std::path::Path::new(candidate.as_str()).is_file() {
            return Some(candidate.clone());
        }

        // Busca no PATH: `where` no Windows, `which` no Unix
        let finder = if cfg!(target_os = "windows") { "where" } else { "which" };
        if let Ok(output) = Command::new(finder).arg(candidate.as_str()).output() {
            if output.status.success() {
                let found = String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .next()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty());
                if let Some(path) = found {
                    return Some(path);
                }
            }
        }
    }
    None
}

// ----------------------------------------------------------
//  Helpers internos
// ----------------------------------------------------------

fn process_name_from_path(exe_path: &str) -> String {
    std::path::Path::new(exe_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(exe_path)
        .to_string()
}

fn check_running(process_name: &str) -> bool {
    #[cfg(target_os = "windows")]
    {
        check_running_windows(process_name)
    }
    #[cfg(not(target_os = "windows"))]
    {
        check_running_unix(process_name)
    }
}

#[cfg(target_os = "windows")]
fn check_running_windows(process_name: &str) -> bool {
    match Command::new("tasklist")
        .args([
            "/FI",
            &format!("IMAGENAME eq {}", process_name),
            "/NH",
            "/FO",
            "CSV",
        ])
        .output()
    {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout);
            text.to_lowercase()
                .contains(&process_name.to_lowercase())
        }
        Err(_) => false,
    }
}

#[cfg(not(target_os = "windows"))]
fn check_running_unix(process_name: &str) -> bool {
    Command::new("pgrep")
        .args(["-x", process_name])
        .output()
        .map(|out| out.status.success())
        .unwrap_or(false)
}
