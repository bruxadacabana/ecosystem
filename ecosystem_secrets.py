"""
ecosystem_secrets — criptografia leve de segredos do ecosystem.json (abordagem B).

AES-256-GCM com uma chave local em `{data_dir}/ecosystem/.secret.key` (a MESMA pasta
do ecosystem.json). Valor cifrado:

    "enc:" + base64( nonce[12] || ciphertext || tag[16] )

`decrypt(v)` é **no-op** se `v` não começar com `enc:` (adoção fácil: pode envolver
qualquer leitura de config). Formato **idêntico** ao `HUB/src-tauri/src/secrets.rs`
(interop Python↔Rust provada por vetor de teste conhecido).

Threat model: o ecossistema é local/offline/sem conta → a chave fica na mesma máquina.
Protege contra exposição **casual** (backup, screenshare, cópia), não contra alguém com
acesso total à máquina. Ver TODO "Criptografar senhas e chaves no ecosystem.json".
"""
from __future__ import annotations

import base64
import logging
import os
import secrets as _secrets
from pathlib import Path

log = logging.getLogger("ecosystem.secrets")

_ENC_PREFIX = "enc:"
_NONCE_LEN = 12
_SECRET_PATTERNS = ("password", "api_key", "token", "secret")


def looks_secret(key: str) -> bool:
    """True se o NOME da chave indica um segredo (mesmo detector do editor de config)."""
    k = (key or "").lower()
    return any(p in k for p in _SECRET_PATTERNS)


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def _key_path() -> Path:
    """`{data_dir}/ecosystem/.secret.key` — mesma pasta do ecosystem.json (e do Rust).

    Override por `ECOSYSTEM_SECRET_KEY_FILE` (usado em testes).
    """
    override = os.environ.get("ECOSYSTEM_SECRET_KEY_FILE")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows (dirs::data_dir() = %APPDATA% Roaming)
        root = Path(appdata) / "ecosystem"
    else:        # Linux: $XDG_DATA_HOME ou ~/.local/share
        xdg = os.environ.get("XDG_DATA_HOME")
        root = (Path(xdg) if xdg else Path.home() / ".local" / "share") / "ecosystem"
    return root / ".secret.key"


def load_or_create_key() -> bytes:
    """Carrega a chave AES-256 (32 bytes) do arquivo; cria uma aleatória se ausente."""
    p = _key_path()
    if p.exists():
        return base64.b64decode(p.read_text(encoding="utf-8").strip())
    p.parent.mkdir(parents=True, exist_ok=True)
    key = _secrets.token_bytes(32)
    p.write_text(base64.b64encode(key).decode("ascii"), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass  # Windows ignora chmod POSIX; ACL padrão de %APPDATA% já é por-usuário
    log.info("ecosystem_secrets: chave criada em %s", p)
    return key


# ── Núcleo cripto (com chave/nonce explícitos — usado por encrypt/decrypt e testes) ──

def _encrypt_with(key: bytes, nonce: bytes, plaintext: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _ENC_PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def _decrypt_with(key: bytes, value: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(value[len(_ENC_PREFIX):])
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


# ── API pública ──────────────────────────────────────────────────────────────

def encrypt(plaintext: str) -> str:
    """Cifra uma string → `enc:...`. String vazia retorna vazia (nada a cifrar)."""
    if not plaintext:
        return plaintext
    return _encrypt_with(load_or_create_key(), _secrets.token_bytes(_NONCE_LEN), plaintext)


def decrypt(value):
    """Descriptografa um valor `enc:...`. No-op para qualquer outro valor (texto puro,
    None, não-str). Levanta em caso de cifra adulterada/chave errada (caller decide)."""
    if not is_encrypted(value):
        return value
    return _decrypt_with(load_or_create_key(), value)


# ── Helpers de wiring (graceful: nunca quebram o caller; logam em caso de erro) ──

def dec_or_keep(value):
    """Descriptografa; em caso de erro loga e devolve o valor original (degradação)."""
    try:
        return decrypt(value)
    except Exception as e:
        log.warning("ecosystem_secrets: falha ao decifrar (mantendo original): %s", e)
        return value


def enc_if_plaintext(value):
    """Cifra se for str não-vazia em texto puro; já-cifrado/vazio/não-str passa direto."""
    if not isinstance(value, str) or not value or is_encrypted(value):
        return value
    try:
        return encrypt(value)
    except Exception as e:
        log.warning("ecosystem_secrets: falha ao cifrar (mantendo texto puro): %s", e)
        return value
