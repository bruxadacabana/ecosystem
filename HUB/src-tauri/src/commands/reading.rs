// ============================================================
//  HUB — Módulo Leituras
//  Lê artigos do archive do KOSMOS e mantém estado de leitura.
// ============================================================

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::AppError;

const READ_STATE_FILE: &str = "hub_read_state.json";

// ----------------------------------------------------------
//  Tipos públicos
// ----------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ArticleMeta {
    pub path: String,    // caminho absoluto do .md
    pub title: String,
    pub source: String,  // label do feed (pasta pai)
    pub date: String,
    pub author: String,
    pub url: String,
    pub is_read: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ArticleContent {
    pub meta: ArticleMeta,
    pub body: String,  // corpo Markdown sem o bloco frontmatter
}

// ----------------------------------------------------------
//  Comandos IPC
// ----------------------------------------------------------

/// Lista todos os artigos `.md` no archive do KOSMOS.
/// Ordena por data descendente.
#[tauri::command]
pub fn list_articles(archive_path: String) -> Result<Vec<ArticleMeta>, AppError> {
    let root = PathBuf::from(&archive_path);
    if !root.is_dir() {
        return Err(AppError::InvalidPath(format!(
            "archive_path não é um diretório: {}",
            archive_path
        )));
    }

    let read_state = load_read_state(&root)?;
    let mut articles = Vec::new();

    collect_articles(&root, &read_state, &mut articles)?;

    // Mais recente primeiro
    articles.sort_by(|a, b| b.date.cmp(&a.date));
    Ok(articles)
}

/// Lê um artigo `.md` completo: retorna metadata e corpo sem frontmatter.
#[tauri::command]
pub fn read_article(archive_path: String, path: String) -> Result<ArticleContent, AppError> {
    let file_path = PathBuf::from(&path);
    let raw = std::fs::read_to_string(&file_path)
        .map_err(|e| AppError::Io(format!("Não foi possível ler '{}': {}", path, e)))?;

    let (fm, body) = split_frontmatter(&raw);
    let parsed = parse_frontmatter(fm);

    // source: pasta pai como label legível
    let source_slug = file_path
        .parent()
        .and_then(|p| p.file_name())
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();
    let source = if parsed.source.is_empty() {
        source_slug.replace('_', " ")
    } else {
        parsed.source
    };

    let title = if parsed.title.is_empty() {
        file_path
            .file_stem()
            .and_then(|n| n.to_str())
            .unwrap_or("Sem título")
            .replace('_', " ")
    } else {
        parsed.title
    };

    let root = PathBuf::from(&archive_path);
    let read_state = load_read_state(&root)?;
    let is_read = read_state.contains(&path);

    Ok(ArticleContent {
        meta: ArticleMeta {
            path,
            title,
            source,
            date: parsed.date,
            author: parsed.author,
            url: parsed.url,
            is_read,
        },
        body: body.trim_start().to_string(),
    })
}

/// Alterna o estado "lido" de um artigo. Retorna o novo estado.
#[tauri::command]
pub fn toggle_read(archive_path: String, article_path: String) -> Result<bool, AppError> {
    let root = PathBuf::from(&archive_path);
    let mut state = load_read_state(&root)?;

    let new_state = if state.contains(&article_path) {
        state.remove(&article_path);
        false
    } else {
        state.insert(article_path);
        true
    };

    save_read_state(&root, &state)?;
    Ok(new_state)
}

// ----------------------------------------------------------
//  Helpers internos
// ----------------------------------------------------------

fn load_read_state(archive_root: &Path) -> Result<HashSet<String>, AppError> {
    let path = archive_root.join(READ_STATE_FILE);
    if !path.exists() {
        return Ok(HashSet::new());
    }
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| AppError::Io(format!("Não foi possível ler hub_read_state.json: {e}")))?;
    let vec: Vec<String> = serde_json::from_str(&raw)
        .map_err(|e| AppError::Json(format!("hub_read_state.json malformado: {e}")))?;
    Ok(vec.into_iter().collect())
}

fn save_read_state(archive_root: &Path, state: &HashSet<String>) -> Result<(), AppError> {
    let path = archive_root.join(READ_STATE_FILE);
    let mut sorted: Vec<&String> = state.iter().collect();
    sorted.sort();
    let json = serde_json::to_string_pretty(&sorted)
        .map_err(|e| AppError::Json(format!("Erro ao serializar read_state: {e}")))?;
    std::fs::write(&path, json)
        .map_err(|e| AppError::Io(format!("Não foi possível salvar hub_read_state.json: {e}")))?;
    Ok(())
}

fn collect_articles(
    dir: &Path,
    read_state: &HashSet<String>,
    out: &mut Vec<ArticleMeta>,
) -> Result<(), AppError> {
    let entries = std::fs::read_dir(dir)
        .map_err(|e| AppError::Io(format!("Não foi possível ler diretório: {e}")))?;

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_articles(&path, read_state, out)?;
        } else if path.extension().and_then(|e| e.to_str()) == Some("md") {
            if let Some(meta) = read_meta(&path, read_state) {
                out.push(meta);
            }
        }
    }
    Ok(())
}

fn read_meta(path: &Path, read_state: &HashSet<String>) -> Option<ArticleMeta> {
    let raw = std::fs::read_to_string(path).ok()?;
    let (fm, _) = split_frontmatter(&raw);
    let parsed = parse_frontmatter(fm);

    let source_slug = path
        .parent()
        .and_then(|p| p.file_name())
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();
    let source = if parsed.source.is_empty() {
        source_slug.replace('_', " ")
    } else {
        parsed.source
    };

    let abs_path = path.to_string_lossy().into_owned();
    let is_read = read_state.contains(&abs_path);

    let title = if parsed.title.is_empty() {
        path.file_stem()
            .and_then(|n| n.to_str())
            .unwrap_or("Sem título")
            .replace('_', " ")
    } else {
        parsed.title
    };

    Some(ArticleMeta {
        path: abs_path,
        title,
        source,
        date: parsed.date,
        author: parsed.author,
        url: parsed.url,
        is_read,
    })
}

// ----------------------------------------------------------
//  Parsing de frontmatter YAML simples
// ----------------------------------------------------------

#[derive(Default)]
struct FrontmatterFields {
    title: String,
    source: String,
    date: String,
    author: String,
    url: String,
}

/// Separa o bloco frontmatter do corpo Markdown.
/// Retorna `(frontmatter_str, body_str)`.
fn split_frontmatter(raw: &str) -> (&str, &str) {
    // Strip BOM se presente
    let raw = raw.trim_start_matches('\u{feff}');
    if !raw.starts_with("---") {
        return ("", raw);
    }
    let after_open = &raw[3..];
    // Encontra o `---` de fechamento após uma nova linha
    if let Some(pos) = after_open.find("\n---") {
        let fm_end = 3 + pos;
        let body_start = fm_end + 4; // pula `\n---`
        (&raw[3..fm_end], &raw[body_start..])
    } else {
        ("", raw)
    }
}

/// Parseia linhas `chave: valor` do frontmatter YAML simples.
/// `split_once(':')` divide apenas no primeiro `:`, portanto URLs ficam intactas.
fn parse_frontmatter(fm: &str) -> FrontmatterFields {
    let mut fields = FrontmatterFields::default();
    for line in fm.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if let Some((raw_key, _)) = line.split_once(':') {
            let key = raw_key.trim().to_lowercase();
            // splitn(2, ':') divide apenas no primeiro `:`, deixando URLs intactas
            let val = line
                .splitn(2, ':')
                .nth(1)
                .unwrap_or("")
                .trim()
                .trim_matches('"')
                .to_string();
            match key.as_str() {
                "title"  => fields.title  = val,
                "source" => fields.source = val,
                "date"   => fields.date   = val,
                "author" => fields.author = val,
                "url"    => fields.url    = val,
                _        => {}
            }
        }
    }
    fields
}
