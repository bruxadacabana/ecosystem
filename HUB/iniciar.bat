@echo off
cd /d "%~dp0"

:: CARGO_INCREMENTAL=0: desabilita o cache incremental por funcao do Cargo.
:: Necessario porque o cache incremental usa hard links entre %TEMP% (C:) e
:: target\debug\incremental (D:) -- hard links nao funcionam entre drives no
:: NTFS, causando recompilacao completa toda vez que o cache e invalidado.
:: O cache normal de dependencias (.rlib, objetos) continua funcionando --
:: crates nao modificados nao sao recompilados.
set CARGO_INCREMENTAL=0

cargo tauri dev
