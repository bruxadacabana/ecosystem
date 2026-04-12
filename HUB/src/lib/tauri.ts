// ============================================================
//  HUB — Wrapper IPC
//  Normaliza invoke() para TauriResult<T>.
//  Padrão idêntico ao AETHER.
// ============================================================

import { invoke as tauriInvoke } from '@tauri-apps/api/core'
import type { AppError, TauriResult, EcosystemConfig } from '../types'

async function call<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<TauriResult<T>> {
  try {
    const data = await tauriInvoke<T>(command, args)
    return { ok: true, data }
  } catch (raw) {
    if (
      raw !== null &&
      typeof raw === 'object' &&
      'kind' in raw &&
      'message' in raw
    ) {
      return { ok: false, error: raw as AppError }
    }
    return {
      ok: false,
      error: {
        kind: 'Io',
        message: typeof raw === 'string' ? raw : 'Erro desconhecido.',
      },
    }
  }
}

// ----------------------------------------------------------
//  Config / Ecosystem
// ----------------------------------------------------------

export const readEcosystemConfig = (): Promise<TauriResult<Partial<EcosystemConfig>>> =>
  call<Partial<EcosystemConfig>>('read_ecosystem_config')

export const validatePath = (path: string): Promise<TauriResult<boolean>> =>
  call<boolean>('validate_path', { path })

export const saveEcosystemConfig = (
  updates: Partial<EcosystemConfig>,
): Promise<TauriResult<void>> =>
  call<void>('save_ecosystem_config', { updates })
