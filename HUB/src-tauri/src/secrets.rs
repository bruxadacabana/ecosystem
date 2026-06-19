//  secrets — criptografia leve de segredos do ecosystem.json (abordagem B).
//
//  AES-256-GCM com chave local em `{data_dir}/ecosystem/.secret.key` (mesma pasta do
//  ecosystem.json). Valor cifrado:
//
//      "enc:" + base64( nonce[12] || ciphertext || tag[16] )
//
//  Formato IDÊNTICO ao `ecosystem_secrets.py` (Python) — interop provada por vetor de
//  teste conhecido (ver testes no fim). `decrypt()` é no-op se não começar com "enc:".
//
//  Threat model: local/offline/sem conta → a chave fica na mesma máquina. Protege contra
//  exposição casual (backup, screenshare, cópia), não contra acesso total à máquina.

use std::path::PathBuf;

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Key, Nonce};
use base64::{engine::general_purpose::STANDARD as B64, Engine};

use crate::error::AppError;

const ENC_PREFIX: &str = "enc:";
const NONCE_LEN: usize = 12;
const SECRET_PATTERNS: [&str; 4] = ["password", "api_key", "token", "secret"];

/// True se o NOME da chave indica um segredo (mesmo detector do editor de config / Python).
pub fn looks_secret(key: &str) -> bool {
    let k = key.to_lowercase();
    SECRET_PATTERNS.iter().any(|p| k.contains(p))
}

pub fn is_encrypted(value: &str) -> bool {
    value.starts_with(ENC_PREFIX)
}

/// `{data_dir}/ecosystem/.secret.key` — override por env `ECOSYSTEM_SECRET_KEY_FILE` (testes).
fn key_path() -> Result<PathBuf, AppError> {
    if let Ok(p) = std::env::var("ECOSYSTEM_SECRET_KEY_FILE") {
        return Ok(PathBuf::from(p));
    }
    dirs::data_dir()
        .map(|base| base.join("ecosystem").join(".secret.key"))
        .ok_or_else(|| AppError::Other("não foi possível resolver data_dir para a chave".into()))
}

/// Carrega a chave AES-256 (32 bytes) do arquivo; cria uma aleatória se ausente.
pub fn load_or_create_key() -> Result<[u8; 32], AppError> {
    let p = key_path()?;
    if p.exists() {
        let txt = std::fs::read_to_string(&p)
            .map_err(|e| AppError::Other(format!("lendo .secret.key: {e}")))?;
        let raw = B64
            .decode(txt.trim())
            .map_err(|e| AppError::Other(format!(".secret.key inválida (base64): {e}")))?;
        let arr: [u8; 32] = raw
            .as_slice()
            .try_into()
            .map_err(|_| AppError::Other(".secret.key não tem 32 bytes".into()))?;
        return Ok(arr);
    }
    if let Some(parent) = p.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| AppError::Other(format!("criando pasta da chave: {e}")))?;
    }
    let mut key = [0u8; 32];
    rand::RngCore::fill_bytes(&mut rand::thread_rng(), &mut key);
    std::fs::write(&p, B64.encode(key))
        .map_err(|e| AppError::Other(format!("gravando .secret.key: {e}")))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o600));
    }
    log::info!("secrets: chave criada em {}", p.display());
    Ok(key)
}

// ── Núcleo cripto (key/nonce explícitos — usado por encrypt/decrypt e testes) ──

fn encrypt_with(key: &[u8; 32], nonce: &[u8; NONCE_LEN], plaintext: &str) -> Result<String, AppError> {
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let ct = cipher
        .encrypt(Nonce::from_slice(nonce), plaintext.as_bytes())
        .map_err(|e| AppError::Other(format!("falha ao cifrar: {e}")))?;
    let mut blob = Vec::with_capacity(NONCE_LEN + ct.len());
    blob.extend_from_slice(nonce);
    blob.extend_from_slice(&ct);
    Ok(format!("{ENC_PREFIX}{}", B64.encode(blob)))
}

fn decrypt_with(key: &[u8; 32], value: &str) -> Result<String, AppError> {
    let raw = B64
        .decode(&value[ENC_PREFIX.len()..])
        .map_err(|e| AppError::Other(format!("base64 inválido: {e}")))?;
    if raw.len() < NONCE_LEN {
        return Err(AppError::Other("cifra curta demais".into()));
    }
    let (nonce, ct) = raw.split_at(NONCE_LEN);
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let pt = cipher
        .decrypt(Nonce::from_slice(nonce), ct)
        .map_err(|e| AppError::Other(format!("falha ao decifrar (chave errada/adulterado?): {e}")))?;
    String::from_utf8(pt).map_err(|e| AppError::Other(format!("utf-8 inválido: {e}")))
}

// ── API pública ───────────────────────────────────────────────────────────────

/// Cifra uma string → `enc:...`. String vazia retorna vazia (nada a cifrar).
pub fn encrypt(plaintext: &str) -> Result<String, AppError> {
    if plaintext.is_empty() {
        return Ok(String::new());
    }
    let key = load_or_create_key()?;
    let mut nonce = [0u8; NONCE_LEN];
    rand::RngCore::fill_bytes(&mut rand::thread_rng(), &mut nonce);
    encrypt_with(&key, &nonce, plaintext)
}

/// Descriptografa um valor `enc:...`. No-op para qualquer outro valor (texto puro).
pub fn decrypt(value: &str) -> Result<String, AppError> {
    if !is_encrypted(value) {
        return Ok(value.to_string());
    }
    let key = load_or_create_key()?;
    decrypt_with(&key, value)
}

// ── Helpers de wiring (graceful: nunca quebram o caller; logam em caso de erro) ──

/// Descriptografa, mas em caso de erro loga e devolve o valor original (degradação).
pub fn dec_or_keep(value: &str) -> String {
    match decrypt(value) {
        Ok(v) => v,
        Err(e) => {
            log::warn!("secrets: falha ao decifrar valor (mantendo original): {e}");
            value.to_string()
        }
    }
}

/// Cifra se for texto puro não-vazio; já-cifrado ou vazio passa direto. Loga erro.
pub fn enc_if_plaintext(value: &str) -> String {
    if value.is_empty() || is_encrypted(value) {
        return value.to_string();
    }
    match encrypt(value) {
        Ok(v) => v,
        Err(e) => {
            log::warn!("secrets: falha ao cifrar valor (mantendo texto puro): {e}");
            value.to_string()
        }
    }
}

/// Percorre uma árvore JSON descriptografando TODO string `enc:...` (usado na leitura
/// que alimenta o editor de config — mostra plaintext).
pub fn decrypt_tree(v: &mut serde_json::Value) {
    match v {
        serde_json::Value::String(s) => {
            if is_encrypted(s) {
                *s = dec_or_keep(s);
            }
        }
        serde_json::Value::Object(map) => map.values_mut().for_each(decrypt_tree),
        serde_json::Value::Array(arr) => arr.iter_mut().for_each(decrypt_tree),
        _ => {}
    }
}

/// Em um objeto-seção, cifra valores cujo NOME de chave é "secret" e estão em texto puro.
pub fn encrypt_secret_fields(section: &mut serde_json::Value) {
    if let serde_json::Value::Object(map) = section {
        for (k, val) in map.iter_mut() {
            if looks_secret(k) {
                if let serde_json::Value::String(s) = val {
                    *s = enc_if_plaintext(s);
                }
            }
        }
    }
}

/// Migração idempotente: cifra segredos em texto puro existentes no ecosystem.json.
/// Chamada no startup do HUB. Já-cifrados são ignorados.
pub fn migrate_plaintext_secrets() {
    let eco = crate::ecosystem::read_json();
    let serde_json::Value::Object(sections) = eco else { return };
    for (name, mut section) in sections {
        if !section.is_object() {
            continue;
        }
        let before = section.clone();
        encrypt_secret_fields(&mut section);
        if section != before {
            if let Err(e) = crate::ecosystem::write_section(&name, section) {
                log::warn!("secrets: migração falhou na seção '{name}': {e}");
            } else {
                log::info!("secrets: segredos da seção '{name}' migrados para cifrado");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Serializa os testes que mexem em ECOSYSTEM_SECRET_KEY_FILE (env é global ao processo).
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    // Vetor conhecido — IDÊNTICO ao teste Python (prova de interop):
    //   key = bytes 00..1f, nonce = bytes 00..0b, plaintext = "segredo-teste"
    fn vec_key() -> [u8; 32] {
        let mut k = [0u8; 32];
        for (i, b) in k.iter_mut().enumerate() {
            *b = i as u8;
        }
        k
    }
    const VALUE: &str = "enc:AAECAwQFBgcICQoLNGexaaCBrTb5JOT/1KV0wXdXiJ3Qp/F9rAjJIoI=";

    #[test]
    fn known_vector_encrypt_matches_python() {
        let mut nonce = [0u8; NONCE_LEN];
        for (i, b) in nonce.iter_mut().enumerate() {
            *b = i as u8;
        }
        assert_eq!(encrypt_with(&vec_key(), &nonce, "segredo-teste").unwrap(), VALUE);
    }

    #[test]
    fn known_vector_decrypt_matches_python() {
        assert_eq!(decrypt_with(&vec_key(), VALUE).unwrap(), "segredo-teste");
    }

    #[test]
    fn roundtrip_with_keyfile() {
        let _g = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        let kp = dir.path().join(".secret.key");
        std::env::set_var("ECOSYSTEM_SECRET_KEY_FILE", &kp);
        let enc = encrypt("minha-senha!@#").unwrap();
        assert!(enc.starts_with("enc:"));
        assert_ne!(enc, "minha-senha!@#");
        assert_eq!(decrypt(&enc).unwrap(), "minha-senha!@#");
        assert!(kp.exists());
        std::env::remove_var("ECOSYSTEM_SECRET_KEY_FILE");
    }

    #[test]
    fn decrypt_is_noop_on_plaintext() {
        assert_eq!(decrypt("texto puro").unwrap(), "texto puro");
        assert_eq!(decrypt("").unwrap(), "");
    }

    #[test]
    fn encrypt_empty_stays_empty() {
        assert_eq!(encrypt("").unwrap(), "");
    }

    #[test]
    fn looks_secret_detects() {
        assert!(looks_secret("syncthing_gui_password"));
        assert!(looks_secret("marginalia_api_key"));
        assert!(looks_secret("algum_token"));
        assert!(!looks_secret("web_search_backend"));
        assert!(!looks_secret("vault_path"));
    }

    #[test]
    fn enc_if_plaintext_is_idempotent() {
        let _g = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("ECOSYSTEM_SECRET_KEY_FILE", dir.path().join(".k"));
        let once = enc_if_plaintext("senha");
        assert!(once.starts_with("enc:"));
        let twice = enc_if_plaintext(&once); // já cifrado → não re-cifra
        assert_eq!(once, twice);
        assert_eq!(dec_or_keep(&twice), "senha");
        assert_eq!(enc_if_plaintext(""), ""); // vazio passa direto
        std::env::remove_var("ECOSYSTEM_SECRET_KEY_FILE");
    }

    #[test]
    fn encrypt_secret_fields_only_secrets() {
        let _g = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("ECOSYSTEM_SECRET_KEY_FILE", dir.path().join(".k"));
        let mut section = serde_json::json!({
            "syncthing_gui_password": "p@ss",
            "syncthing_gui_user": "alice",     // não-secret → intacto
            "web_search_backend": "http://x",  // não-secret → intacto
        });
        encrypt_secret_fields(&mut section);
        assert!(section["syncthing_gui_password"].as_str().unwrap().starts_with("enc:"));
        assert_eq!(section["syncthing_gui_user"], "alice");
        assert_eq!(section["web_search_backend"], "http://x");
        std::env::remove_var("ECOSYSTEM_SECRET_KEY_FILE");
    }

    #[test]
    fn decrypt_tree_walks_nested() {
        let _g = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("ECOSYSTEM_SECRET_KEY_FILE", dir.path().join(".k"));
        let enc = encrypt("segredo").unwrap();
        let mut tree = serde_json::json!({
            "hub": { "syncthing_gui_password": enc, "user": "bob" },
            "plain": "abc",
        });
        decrypt_tree(&mut tree);
        assert_eq!(tree["hub"]["syncthing_gui_password"], "segredo");
        assert_eq!(tree["hub"]["user"], "bob");
        assert_eq!(tree["plain"], "abc");
        std::env::remove_var("ECOSYSTEM_SECRET_KEY_FILE");
    }
}
