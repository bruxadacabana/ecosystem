// ── Primitivas neverthrow ─────────────────────────────────────────────────────
export { ok, err, Result, ResultAsync } from 'neverthrow'
import { ok, err, Result, ResultAsync } from 'neverthrow'

// ── Códigos de erro tipados ────────────────────────────────────────────────────

export type ErrorCode =
  | 'DB_CONSTRAINT'   // Violação de unicidade ou chave estrangeira
  | 'DB_WRITE'        // Falha ao gravar (lock, readonly, disco cheio)
  | 'DB_READ'         // Falha ao ler
  | 'NOT_FOUND'       // Registo não encontrado
  | 'VALIDATION'      // Input inválido
  | 'IPC_ERROR'       // Falha na comunicação renderer↔main
  | 'UNKNOWN'         // Erro não classificado

// ── AppError ──────────────────────────────────────────────────────────────────

export interface AppError {
  readonly code:     ErrorCode
  readonly message:  string
  readonly context?: string   // ex.: 'createProject', 'loadPages'
}

// ── Helpers ───────────────────────────────────────────────────────────────────

export function makeError(
  code:     ErrorCode,
  message:  string,
  context?: string,
): AppError {
  return { code, message, context }
}

/** Extrai a mensagem de qualquer valor capturado num catch */
export function extractMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return 'Erro desconhecido'
}

/** Mensagem amigável por código de erro */
export function friendlyMessage(code: ErrorCode): string {
  const map: Record<ErrorCode, string> = {
    DB_CONSTRAINT: 'Conflito de dados: registo duplicado ou referência inválida.',
    DB_WRITE:      'Falha ao gravar na base de dados.',
    DB_READ:       'Falha ao ler da base de dados.',
    NOT_FOUND:     'Registo não encontrado.',
    VALIDATION:    'Dados inválidos.',
    IPC_ERROR:     'Erro de comunicação interna.',
    UNKNOWN:       'Erro inesperado.',
  }
  return map[code]
}

// ── Wrappers para chamadas IPC ────────────────────────────────────────────────

/**
 * Envolve uma chamada IPC assíncrona num ResultAsync<T, AppError>.
 *
 * Uso:
 *   const result = await fromIpc<Project>(() => db().projects.create(input), 'createProject')
 *   if (result.isErr()) { ... result.error ... }
 *   else { ... result.value ... }
 */
export function fromIpc<T>(
  call:    () => Promise<{ ok: boolean; data?: T; error?: string; errorCode?: ErrorCode }>,
  context: string,
): ResultAsync<T, AppError> {
  return ResultAsync.fromPromise(
    call().then(res => {
      if (res?.ok && res.data !== undefined) return res.data
      const code: ErrorCode = res?.errorCode ?? 'UNKNOWN'
      throw makeError(code, res?.error ?? 'Erro desconhecido', context)
    }),
    (e): AppError => {
      // já é um AppError se vier do .then() acima
      if (e && typeof e === 'object' && 'code' in e && 'message' in e) {
        return e as AppError
      }
      return makeError('IPC_ERROR', extractMessage(e), context)
    },
  )
}
