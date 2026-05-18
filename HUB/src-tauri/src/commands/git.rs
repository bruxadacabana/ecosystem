// ============================================================
//  HUB — commands/git.rs
//  Operações git offline na sync_root do ecossistema.
// ============================================================

use crate::ecosystem;
use crate::error::AppError;
use serde::Serialize;
use std::path::Path;
use std::process::Command;

// ------------------------------------------------------------------
//  Tipos retornados para o frontend
// ------------------------------------------------------------------

#[derive(Debug, Serialize)]
pub struct GitFileStatus {
    /// Caminho relativo ao sync_root
    pub path: String,
    /// Código porcelain de 2 chars: "M ", " M", "??", "A ", "D ", etc.
    pub status: String,
}

#[derive(Debug, Serialize)]
pub struct GitLogEntry {
    pub hash:    String,
    pub date:    String,
    pub message: String,
    pub author:  String,
}

// ------------------------------------------------------------------
//  Comandos Tauri
// ------------------------------------------------------------------

/// Retorna o status do repositório (arquivos modificados/não-rastreados).
/// Usa `git status --porcelain=v1`.
#[tauri::command]
pub fn git_status() -> Result<Vec<GitFileStatus>, AppError> {
    let root = sync_root_path()?;
    let out = run_git(&root, &["status", "--porcelain=v1"])?;
    let text = String::from_utf8_lossy(&out.stdout);

    let mut entries = Vec::new();
    for line in text.lines() {
        if line.len() < 3 {
            continue;
        }
        let status = &line[..2];
        let rest   = line[3..].trim();
        // Renomes: "old -> new" — pega só o destino
        let path = if rest.contains(" -> ") {
            rest.split(" -> ").last().unwrap_or(rest).to_string()
        } else {
            rest.to_string()
        };
        entries.push(GitFileStatus {
            path,
            status: status.to_string(),
        });
    }
    Ok(entries)
}

/// Cria um commit com `git add -A` + `git commit`.
/// Se `message` for None, usa mensagem automática com timestamp.
/// Retorna o hash curto do commit criado.
#[tauri::command]
pub fn git_commit(message: Option<String>) -> Result<String, AppError> {
    let root = sync_root_path()?;

    let msg = message.unwrap_or_else(|| {
        let now = chrono::Local::now().format("%Y-%m-%d %H:%M").to_string();
        format!("auto: snapshot — {now}")
    });

    run_git(&root, &["add", "-A"])?;

    let commit_result = run_git(&root, &[
        "-c", "user.name=HUB",
        "-c", "user.email=hub@ecosystem",
        "commit", "-m", &msg,
    ]);

    match commit_result {
        Err(AppError::Io(ref s)) if s.contains("nothing to commit") => {
            return Err(AppError::NotFound("Nada para commitar.".into()));
        }
        other => { other?; }
    }

    let hash_out = run_git(&root, &["rev-parse", "--short", "HEAD"])?;
    Ok(String::from_utf8_lossy(&hash_out.stdout).trim().to_string())
}

/// Retorna os últimos `n` commits do log.
#[tauri::command]
pub fn git_log(n: u32) -> Result<Vec<GitLogEntry>, AppError> {
    let root  = sync_root_path()?;
    let n_str = n.to_string();
    let out   = run_git(&root, &[
        "log",
        &format!("-{n_str}"),
        "--format=%h\x1f%ad\x1f%s\x1f%an",
        "--date=format:%Y-%m-%d %H:%M",
    ])?;
    let text = String::from_utf8_lossy(&out.stdout);

    let entries = text
        .lines()
        .filter(|l| !l.trim().is_empty())
        .filter_map(|line| {
            let parts: Vec<&str> = line.splitn(4, '\x1f').collect();
            if parts.len() < 4 { return None; }
            Some(GitLogEntry {
                hash:    parts[0].trim().to_string(),
                date:    parts[1].trim().to_string(),
                message: parts[2].trim().to_string(),
                author:  parts[3].trim().to_string(),
            })
        })
        .collect();
    Ok(entries)
}

/// Retorna o diff de um arquivo específico ou de todo o repositório vs HEAD.
/// Para novos arquivos (staged only), tenta `--cached` se o diff vs HEAD estiver vazio.
#[tauri::command]
pub fn git_diff(path: Option<String>) -> Result<String, AppError> {
    let root = sync_root_path()?;

    let diff = match &path {
        Some(p) => {
            let text = run_git(&root, &["diff", "HEAD", "--", p.as_str()])
                .ok()
                .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
                .unwrap_or_default();
            if text.trim().is_empty() {
                // arquivo pode ser staged-only (A ); tenta --cached
                run_git(&root, &["diff", "--cached", "--", p.as_str()])
                    .ok()
                    .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
                    .unwrap_or_default()
            } else {
                text
            }
        }
        None => {
            let out = run_git(&root, &["diff", "HEAD"])?;
            String::from_utf8_lossy(&out.stdout).to_string()
        }
    };
    Ok(diff)
}

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

/// Lê sync_root do ecosystem.json e retorna como PathBuf validado.
fn sync_root_path() -> Result<std::path::PathBuf, AppError> {
    let eco = ecosystem::read_json();
    let s = eco["sync_root"].as_str().unwrap_or("").trim().to_string();
    if s.is_empty() {
        return Err(AppError::MissingConfig("sync_root não configurado.".into()));
    }
    let p = std::path::PathBuf::from(&s);
    if !p.is_dir() {
        return Err(AppError::InvalidPath(format!("sync_root não existe: {s}")));
    }
    Ok(p)
}

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
