// ============================================================
//  HUB — Launcher de apps externos
//  Inicia apps do ecossistema e monitora se estão em execução.
// ============================================================

use std::collections::HashMap;
use std::process::Command;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

use crate::AppError;

// ----------------------------------------------------------
//  Comandos IPC
// ----------------------------------------------------------

/// Inicia um app externo pelo caminho do executável.
/// No Windows, scripts `.sh` são automaticamente envolvidos com `bash`.
#[tauri::command]
pub fn launch_app(exe_path: String) -> Result<(), AppError> {
    if exe_path.trim().is_empty() {
        return Err(AppError::InvalidPath(
            "Caminho do executável não configurado.".into(),
        ));
    }

    let mut cmd = build_launch_command(&exe_path);
    cmd.spawn()
        .map(|_| ())
        .map_err(|e| AppError::Io(format!("Não foi possível iniciar '{}': {}", exe_path, e)))
}

/// Constrói o Command correto dependendo do tipo de script e plataforma.
/// - Windows + .sh → `bash <path>`
/// - Windows + .bat/.cmd → `cmd /C <path>`  (deixa o cmd resolver o ambiente)
/// - Unix ou binário nativo → executa diretamente
fn build_launch_command(exe_path: &str) -> Command {
    #[cfg(target_os = "windows")]
    {
        let lower = exe_path.to_lowercase();
        if lower.ends_with(".sh") {
            let mut cmd = Command::new("bash");
            cmd.arg(exe_path);
            return cmd;
        }
        if lower.ends_with(".bat") || lower.ends_with(".cmd") {
            let mut cmd = Command::new("cmd");
            cmd.args(["/C", exe_path]);
            return cmd;
        }
    }
    Command::new(exe_path)
}

/// Verifica se um processo correspondente ao executável está em execução.
#[tauri::command]
pub fn is_app_running(exe_path: String) -> bool {
    if exe_path.trim().is_empty() {
        return false;
    }
    check_running(&exe_path)
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
                check_running(&path)
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
        #[allow(unused_mut)]
        let mut finder_cmd = Command::new(finder);
        finder_cmd.arg(candidate.as_str());
        #[cfg(target_os = "windows")]
        finder_cmd.creation_flags(CREATE_NO_WINDOW);
        if let Ok(output) = finder_cmd.output() {
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

/// Descobre automaticamente os scripts de inicialização de todos os apps,
/// procurando na pasta raiz do ecossistema (pasta-mãe do diretório HUB/).
/// Retorna um map `{ "app_key" → "caminho_do_script" }` para os apps encontrados.
#[tauri::command]
pub fn auto_discover_all_exe_paths() -> HashMap<String, String> {
    let mut result = HashMap::new();
    let Some(root) = find_ecosystem_root() else {
        return result;
    };

    // Scripts em ordem de prioridade: .sh primeiro no Unix, .bat primeiro no Windows
    #[cfg(target_os = "windows")]
    let scripts: &[&str] = &["iniciar.bat", "iniciar.sh"];
    #[cfg(not(target_os = "windows"))]
    let scripts: &[&str] = &["iniciar.sh", "iniciar.bat"];

    let apps: &[(&str, &str)] = &[
        ("aether",    "AETHER"),
        ("ogma",      "OGMA"),
        ("kosmos",    "KOSMOS"),
        ("mnemosyne", "Mnemosyne"),
        ("hermes",    "Hermes"),
        ("akasha",    "AKASHA"),
    ];

    for (key, subdir) in apps {
        for script in scripts {
            let candidate = root.join(subdir).join(script);
            if candidate.is_file() {
                result.insert(
                    key.to_string(),
                    candidate.to_string_lossy().into_owned(),
                );
                break;
            }
        }
    }

    result
}

// ----------------------------------------------------------
//  Helpers — descoberta do root do ecossistema
// ----------------------------------------------------------

/// Sobe pelo path do executável atual até encontrar um componente chamado "HUB",
/// depois retorna o pai desse diretório (a pasta raiz do ecossistema).
fn find_ecosystem_root() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut current = exe.as_path();

    while let Some(parent) = current.parent() {
        let is_hub = parent
            .file_name()
            .and_then(|n| n.to_str())
            .map(|n| n.eq_ignore_ascii_case("hub"))
            .unwrap_or(false);

        if is_hub {
            if let Some(root) = parent.parent() {
                if is_ecosystem_root(root) {
                    return Some(root.to_path_buf());
                }
            }
        }
        current = parent;
    }
    None
}

/// Verifica se um diretório é a raiz do ecossistema
/// confirmando a presença de ao menos 2 dos apps conhecidos.
fn is_ecosystem_root(path: &std::path::Path) -> bool {
    ["AETHER", "OGMA", "KOSMOS", "Mnemosyne", "Hermes"]
        .iter()
        .filter(|app| path.join(app).is_dir())
        .count() >= 2
}

// ----------------------------------------------------------
//  Helpers internos
// ----------------------------------------------------------

fn check_running(exe_path: &str) -> bool {
    #[cfg(target_os = "windows")]
    {
        let lower = exe_path.to_lowercase();
        if lower.ends_with(".bat") || lower.ends_with(".sh") {
            // .bat não aparece no tasklist — o processo real é python.exe, cargo.exe, etc.
            // Usa WMIC para buscar o nome do diretório pai (ex: "Hermes") na cmdline dos processos.
            let dir_name = std::path::Path::new(exe_path)
                .parent()
                .and_then(|p| p.file_name())
                .and_then(|n| n.to_str())
                .unwrap_or("");
            if !dir_name.is_empty() {
                return check_running_windows_cmdline(dir_name);
            }
            return false;
        }
        // Binário nativo: busca pelo nome do arquivo no tasklist
        let process_name = std::path::Path::new(exe_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(exe_path)
            .to_string();
        check_running_windows(&process_name)
    }
    #[cfg(not(target_os = "windows"))]
    {
        // No Linux/macOS, busca o exe_path completo na linha de comando do processo
        // (pgrep -f) — funciona tanto para scripts (bash iniciar.sh) quanto para
        // binários instalados, inclusive em modo dev (cargo tauri dev).
        check_running_unix(exe_path)
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
        .creation_flags(CREATE_NO_WINDOW)
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

/// Busca processos cuja linha de comando contém `dir_name` (ex: "Hermes", "KOSMOS").
/// Usado para detectar apps iniciados via .bat (python, cargo, node não aparecem pelo
/// nome do .bat no tasklist).
#[cfg(target_os = "windows")]
fn check_running_windows_cmdline(dir_name: &str) -> bool {
    let filter = format!("commandline like '%{}%'", dir_name);
    match Command::new("wmic")
        .args(["process", "where", &filter, "get", "ProcessId"])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout);
            // WMIC retorna só o cabeçalho "ProcessId" quando não há resultados;
            // quando há, adiciona linhas com o PID numérico.
            text.lines()
                .any(|l| l.trim().parse::<u32>().is_ok())
        }
        Err(_) => false,
    }
}

#[cfg(not(target_os = "windows"))]
fn check_running_unix(exe_path: &str) -> bool {
    Command::new("pgrep")
        .args(["-f", exe_path])
        .output()
        .map(|out| out.status.success())
        .unwrap_or(false)
}
