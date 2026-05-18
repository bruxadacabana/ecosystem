// ============================================================
//  HUB — commands/git.rs
//  Operações git offline na sync_root do ecossistema.
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use std::path::Path;
use std::process::Command;

const GITIGNORE_ENTRIES: &[&str] = &["*.db-wal", "*.db-shm"];
const STIGNORE_ENTRIES: &[&str]  = &["*.db-wal", "*.db-shm", "*.tmp"];

/// Inicializa o repositório git offline na sync_root do ecossistema.
///
/// Se `.git/` não existir:
///   - executa `git init`
///   - cria `.gitignore` com `*.db-wal` e `*.db-shm`
///   - cria `.stignore` (Syncthing) com `*.db-wal`, `*.db-shm` e `*.tmp`
///   - faz commit inicial "init: ecosystem sync root"
///
/// Se `.git/` já existir, garante apenas que os arquivos de ignore
/// contenham as entradas obrigatórias (acrescenta ao final se faltar).
#[tauri::command]
pub fn git_init_sync_root() -> Result<(), AppError> {
    let eco = ecosystem::read_json();
    let sync_root = eco["sync_root"]
        .as_str()
        .unwrap_or("")
        .trim()
        .to_string();

    if sync_root.is_empty() {
        return Err(AppError::MissingConfig("sync_root não configurado.".into()));
    }

    let root = Path::new(&sync_root);
    if !root.is_dir() {
        return Err(AppError::InvalidPath(format!(
            "sync_root não existe como diretório: {sync_root}"
        )));
    }

    let is_new = !root.join(".git").exists();

    if is_new {
        run_git(root, &["init"])?;
    }

    // Garante entradas de ignore em ambos os arquivos
    ensure_file_entries(root, ".gitignore", GITIGNORE_ENTRIES)?;
    ensure_file_entries(root, ".stignore",  STIGNORE_ENTRIES)?;

    if is_new {
        // Stage os arquivos de ignore e cria commit inicial
        run_git(root, &["add", ".gitignore", ".stignore"])?;
        run_git(root, &[
            "-c", "user.name=HUB",
            "-c", "user.email=hub@ecosystem",
            "commit", "--allow-empty",
            "-m", "init: ecosystem sync root",
        ])?;
    }

    Ok(())
}

// ------------------------------------------------------------------
//  Auxiliares internos
// ------------------------------------------------------------------

/// Executa `git -C <root> <args…>` e retorna erro se o processo falhar.
pub(crate) fn run_git(root: &Path, args: &[&str]) -> Result<std::process::Output, AppError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|e| AppError::Io(format!("git não encontrado ou inacessível: {e}")))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::Io(format!("git: {}", stderr.trim())));
    }
    Ok(output)
}

/// Garante que um arquivo contenha todas as entradas da lista.
/// Cria o arquivo se não existir; acrescenta ao final as entradas ausentes.
fn ensure_file_entries(root: &Path, filename: &str, required: &[&str]) -> Result<(), AppError> {
    let path = root.join(filename);
    let existing = if path.exists() {
        std::fs::read_to_string(&path)?
    } else {
        String::new()
    };

    let mut content = existing.clone();
    let mut changed = !path.exists();

    for entry in required {
        if !content.lines().any(|l| l.trim() == *entry) {
            if !content.is_empty() && !content.ends_with('\n') {
                content.push('\n');
            }
            content.push_str(entry);
            content.push('\n');
            changed = true;
        }
    }

    if changed {
        std::fs::write(&path, &content)?;
    }
    Ok(())
}
