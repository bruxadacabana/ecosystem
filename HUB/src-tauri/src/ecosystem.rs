// ============================================================
//  ecosystem — integração com o ecosystem.json compartilhado
// ============================================================
//
//  Caminho base (compartilhado, sincronizado entre máquinas):
//    ~/.local/share/ecosystem/ecosystem.json  (Linux)
//    %APPDATA%\ecosystem\ecosystem.json       (Windows)
//
//  Caminho local (paths absolutos por máquina, NÃO sincronizado):
//    ~/.local/share/ecosystem/ecosystem.local.json  (Linux)
//    %APPDATA%\ecosystem\ecosystem.local.json       (Windows)
//
//  Na leitura, os dois são mesclados: ecosystem.local.json tem precedência.
//  Apenas write_section() é exposto. A leitura é feita por outros
//  apps; o AETHER só precisa escrever sua própria seção.

use crate::error::AppError;
use fs2::FileExt;
use serde_json::{json, Map, Value};
use std::path::PathBuf;

/// Retorna o caminho do ecosystem.json compartilhado (sincronizado via Proton Drive / Syncthing).
pub fn ecosystem_path() -> Option<PathBuf> {
    dirs::data_dir().map(|base| base.join("ecosystem").join("ecosystem.json"))
}

/// Retorna o caminho do ecosystem.local.json — paths específicos desta máquina, nunca sincronizado.
pub fn ecosystem_local_path() -> Option<PathBuf> {
    dirs::data_dir().map(|base| base.join("ecosystem").join("ecosystem.local.json"))
}

/// Lê o ecosystem.json mesclado com ecosystem.local.json.
/// ecosystem.local.json tem precedência: qualquer chave presente nele sobrescreve a do base.
/// Deep merge em objetos aninhados (ex: seção "mnemosyne" é mesclada campo a campo).
pub fn read_json() -> Value {
    let base = ecosystem_path()
        .map(|p| read_file(&p))
        .unwrap_or_else(|| json!({}));
    let local = ecosystem_local_path()
        .map(|p| read_file(&p))
        .unwrap_or_else(|| json!({}));
    merge_json(base, local)
}

/// Lê um único arquivo JSON. Retorna `{}` se ausente ou inválido.
fn read_file(path: &std::path::Path) -> Value {
    if !path.exists() {
        return json!({});
    }
    std::fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}))
}

/// Deep merge: valores de `overlay` têm precedência sobre `base`.
/// Objetos são mesclados recursivamente; outros tipos: overlay substitui base.
fn merge_json(base: Value, overlay: Value) -> Value {
    match (base, overlay) {
        (Value::Object(mut base_map), Value::Object(overlay_map)) => {
            for (k, v) in overlay_map {
                let merged = match base_map.remove(&k) {
                    Some(base_val) => merge_json(base_val, v),
                    None => v,
                };
                base_map.insert(k, merged);
            }
            Value::Object(base_map)
        }
        // Se overlay não é objeto (ou base não é objeto), overlay vence inteiro
        (_, overlay) => overlay,
    }
}

/// Atualiza apenas a seção `app` do ecosystem.json compartilhado, preservando as demais.
/// Dados de registro (base_url, exe_path) vão no arquivo compartilhado — são iguais em todas
/// as máquinas. Paths absolutos devem ser escritos com write_local_section().
/// Lock exclusivo via `.ecosystem.lock` + escrita atômica (tmp → rename).
pub fn write_section(app: &str, section: Value) -> Result<(), AppError> {
    let path = ecosystem_path().ok_or_else(|| {
        AppError::Io("Não foi possível determinar o diretório de dados do sistema.".to_string())
    })?;
    write_to_file(&path, app, section)
}

/// Atualiza a seção `app` do ecosystem.local.json — para paths absolutos por máquina.
pub fn write_local_section(app: &str, section: Value) -> Result<(), AppError> {
    let path = ecosystem_local_path().ok_or_else(|| {
        AppError::Io("Não foi possível determinar o diretório de dados do sistema.".to_string())
    })?;
    write_to_file(&path, app, section)
}

fn write_to_file(path: &PathBuf, app: &str, section: Value) -> Result<(), AppError> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }

    // Lock exclusivo — mesmo mecanismo usado pelo Python (filelock cria o mesmo arquivo)
    let lock_path = path.with_file_name(".ecosystem.lock");
    let lock_file = std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .open(&lock_path)?;
    lock_file.lock_exclusive()?;

    let mut data = read_file(path);

    // Merge: atualiza apenas os campos fornecidos na seção
    if let Some(obj) = data.get_mut(app) {
        if let (Some(obj_map), Some(section_map)) = (obj.as_object_mut(), section.as_object()) {
            for (k, v) in section_map {
                obj_map.insert(k.clone(), v.clone());
            }
        } else {
            data[app] = section;
        }
    } else {
        data[app] = section;
    }

    let serialized = serde_json::to_string_pretty(&data)?;

    // Escrita atômica: tmp → rename
    let tmp_path = path.with_extension("json.tmp");
    std::fs::write(&tmp_path, serialized)?;
    std::fs::rename(&tmp_path, path)?;

    // Lock liberado automaticamente quando lock_file sai de escopo
    Ok(())
}
