// ============================================================
//  ecosystem — integração com o ecosystem.json compartilhado
// ============================================================
//
//  Caminho: ~/.local/share/ecosystem/ecosystem.json (Linux)
//           %APPDATA%\ecosystem\ecosystem.json (Windows)
//
//  Apenas write_section() é exposto. A leitura é feita por outros
//  apps; o AETHER só precisa escrever sua própria seção.

use crate::error::AppError;
use serde_json::{json, Value};
use std::path::PathBuf;

/// Retorna o caminho canônico do ecosystem.json.
/// Retorna None apenas se o diretório de dados do sistema não puder ser
/// determinado (situação extremamente rara).
pub fn ecosystem_path() -> Option<PathBuf> {
    dirs::data_dir().map(|base| base.join("ecosystem").join("ecosystem.json"))
}

/// Lê o ecosystem.json atual. Retorna `{}` se ausente ou inválido.
fn read_ecosystem(path: &std::path::Path) -> Value {
    if !path.exists() {
        return json!({});
    }
    std::fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}))
}

/// Atualiza apenas a seção `app` do ecosystem.json, preservando as demais.
/// Escrita atômica: grava em arquivo temporário e renomeia.
///
/// Falha silenciosa é aceitável no call site — use `unwrap_or_else(|e| eprintln!(...))`.
pub fn write_section(app: &str, section: Value) -> Result<(), AppError> {
    let path = ecosystem_path().ok_or_else(|| {
        AppError::Io("Não foi possível determinar o diretório de dados do sistema.".to_string())
    })?;

    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }

    let mut data = read_ecosystem(&path);

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
    std::fs::rename(&tmp_path, &path)?;

    Ok(())
}
