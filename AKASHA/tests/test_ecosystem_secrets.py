"""
Testes do ecosystem_secrets (criptografia de segredos do ecosystem.json — abordagem B).

Inclui o VETOR CONHECIDO (key+nonce fixos → cifra esperada) que o `secrets.rs` do HUB
também valida — é a prova de interop Python↔Rust sem rodar os dois juntos.
"""
from __future__ import annotations

import config  # noqa: F401 — coloca a raiz do ecossistema no sys.path

import ecosystem_secrets as es

# Vetor conhecido (idêntico no teste Rust):
#   key = bytes 00..1f, nonce = bytes 00..0b, plaintext = "segredo-teste"
KEY = bytes(range(32))
VALUE = "enc:AAECAwQFBgcICQoLNGexaaCBrTb5JOT/1KV0wXdXiJ3Qp/F9rAjJIoI="


def test_known_vector_encrypt_matches():
    assert es._encrypt_with(KEY, bytes(range(12)), "segredo-teste") == VALUE


def test_known_vector_decrypt_matches():
    assert es._decrypt_with(KEY, VALUE) == "segredo-teste"


def test_roundtrip_with_keyfile(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOSYSTEM_SECRET_KEY_FILE", str(tmp_path / ".secret.key"))
    enc = es.encrypt("minha-senha!@#")
    assert enc.startswith("enc:")
    assert enc != "minha-senha!@#"
    assert es.decrypt(enc) == "minha-senha!@#"
    assert (tmp_path / ".secret.key").exists()


def test_decrypt_is_noop_on_non_encrypted():
    assert es.decrypt("texto puro") == "texto puro"
    assert es.decrypt("") == ""
    assert es.decrypt(None) is None


def test_encrypt_empty_stays_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOSYSTEM_SECRET_KEY_FILE", str(tmp_path / ".k"))
    assert es.encrypt("") == ""


def test_looks_secret():
    assert es.looks_secret("syncthing_gui_password")
    assert es.looks_secret("marginalia_api_key")
    assert es.looks_secret("chave_api_dados_token")
    assert not es.looks_secret("web_search_backend")
    assert not es.looks_secret("vault_path")


def test_is_encrypted():
    assert es.is_encrypted(VALUE)
    assert not es.is_encrypted("plain")
    assert not es.is_encrypted(None)


def test_roundtrip_persists_key(tmp_path, monkeypatch):
    """Segunda chamada reusa a mesma chave (decifra o que a primeira cifrou)."""
    monkeypatch.setenv("ECOSYSTEM_SECRET_KEY_FILE", str(tmp_path / ".secret.key"))
    enc = es.encrypt("abc")
    # nova "sessão" lógica: mesma chave em disco
    assert es.decrypt(enc) == "abc"


def test_enc_if_plaintext_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOSYSTEM_SECRET_KEY_FILE", str(tmp_path / ".k"))
    once = es.enc_if_plaintext("senha")
    assert once.startswith("enc:")
    assert es.enc_if_plaintext(once) == once   # já cifrado → não re-cifra
    assert es.enc_if_plaintext("") == ""       # vazio passa direto
    assert es.enc_if_plaintext(None) is None   # não-str passa direto
    assert es.dec_or_keep(once) == "senha"


def test_dec_or_keep_graceful_on_garbage():
    # valor 'enc:' inválido → não levanta; devolve o original (degradação + log)
    assert es.dec_or_keep("enc:!!!notbase64!!!") == "enc:!!!notbase64!!!"
    assert es.dec_or_keep("texto puro") == "texto puro"
