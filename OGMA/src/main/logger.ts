/**
 * OGMA Logger — Processo Main
 *
 * Grava logs em data/logs/YYYY-MM-DD.log
 * Formato: [HH:MM:SS.mmm] [LEVEL] [módulo] mensagem {meta?}
 *
 * Níveis: DEBUG < INFO < WARN < ERROR
 * Rotação: um arquivo por dia (nome = data ISO)
 * Retenção: apaga logs com mais de 30 dias automaticamente
 */

import fs from 'fs'
import path from 'path'
import { LOGS_DIR } from './paths'

// ── Tipos ────────────────────────────────────────────────────────────────────

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

interface LogEntry {
  ts:      string
  level:   LogLevel
  module:  string
  message: string
  meta?:   Record<string, unknown>
  ms?:     number   // duração em ms (para logs de performance)
}

// ── Configuração ─────────────────────────────────────────────────────────────

const LEVEL_RANK: Record<LogLevel, number> = {
  DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3,
}

let _minLevel: LogLevel = 'DEBUG'
let _currentFile: string | null = null
let _currentDate: string | null = null

// ── Helpers internos ─────────────────────────────────────────────────────────

function isoDate(): string {
  return new Date().toISOString().slice(0, 10)  // YYYY-MM-DD
}

function timestamp(): string {
  const now = new Date()
  return now.toTimeString().slice(0, 8) + '.' +
    String(now.getMilliseconds()).padStart(3, '0')
}

function getLogFile(): string {
  const today = isoDate()
  if (today !== _currentDate) {
    _currentDate = today
    _currentFile = path.join(LOGS_DIR, `${today}.log`)
    // Ao trocar de arquivo (novo dia), apagar logs antigos
    pruneOldLogs()
  }
  return _currentFile!
}

function pruneOldLogs(retentionDays = 30): void {
  try {
    const cutoff = Date.now() - retentionDays * 86_400_000
    const files = fs.readdirSync(LOGS_DIR)
    for (const f of files) {
      if (!f.endsWith('.log')) continue
      const full = path.join(LOGS_DIR, f)
      const stat = fs.statSync(full)
      if (stat.mtimeMs < cutoff) {
        fs.unlinkSync(full)
      }
    }
  } catch {
    // silencioso — não queremos que a limpeza quebre o app
  }
}

function formatLine(entry: LogEntry): string {
  const meta = entry.meta ? ' ' + JSON.stringify(entry.meta) : ''
  const perf = entry.ms !== undefined ? ` [${entry.ms}ms]` : ''
  return `[${entry.ts}] [${entry.level.padEnd(5)}] [${entry.module}]${perf} ${entry.message}${meta}\n`
}

function write(entry: LogEntry): void {
  if (LEVEL_RANK[entry.level] < LEVEL_RANK[_minLevel]) return

  const line = formatLine(entry)

  // Console (colorido em dev)
  const isDev = process.env.NODE_ENV === 'development' || !require('electron').app.isPackaged
  if (isDev) {
    const colors: Record<LogLevel, string> = {
      DEBUG: '\x1b[90m', INFO: '\x1b[36m', WARN: '\x1b[33m', ERROR: '\x1b[31m',
    }
    process.stdout.write(colors[entry.level] + line + '\x1b[0m')
  }

  // Arquivo
  try {
    fs.mkdirSync(LOGS_DIR, { recursive: true })
    fs.appendFileSync(getLogFile(), line, 'utf-8')
  } catch {
    // silencioso — não travar o app por falha de log
  }
}

// ── API pública ──────────────────────────────────────────────────────────────

export function setLevel(level: LogLevel): void {
  _minLevel = level
}

export function createLogger(module: string) {
  return {
    debug: (message: string, meta?: Record<string, unknown>) =>
      write({ ts: timestamp(), level: 'DEBUG', module, message, meta }),

    info: (message: string, meta?: Record<string, unknown>) =>
      write({ ts: timestamp(), level: 'INFO', module, message, meta }),

    warn: (message: string, meta?: Record<string, unknown>) =>
      write({ ts: timestamp(), level: 'WARN', module, message, meta }),

    error: (message: string, meta?: Record<string, unknown>) =>
      write({ ts: timestamp(), level: 'ERROR', module, message, meta }),

    /**
     * Mede o tempo de execução de uma função e loga como INFO.
     * Se ultrapassar `warnMs`, loga como WARN.
     *
     * Uso:
     *   const result = await log.perf('db.query', () => db.prepare(...).all())
     */
    perf: <T>(label: string, fn: () => T, warnMs = 200): T => {
      const start = performance.now()
      const result = fn()
      const ms = Math.round(performance.now() - start)
      const level: LogLevel = ms >= warnMs ? 'WARN' : 'DEBUG'
      write({ ts: timestamp(), level, module, message: label, ms })
      return result
    },

    /**
     * Versão assíncrona do perf.
     */
    perfAsync: async <T>(label: string, fn: () => Promise<T>, warnMs = 200): Promise<T> => {
      const start = performance.now()
      const result = await fn()
      const ms = Math.round(performance.now() - start)
      const level: LogLevel = ms >= warnMs ? 'WARN' : 'DEBUG'
      write({ ts: timestamp(), level, module, message: label, ms })
      return result
    },
  }
}

// ── Captura global de erros não tratados ─────────────────────────────────────

const rootLog = createLogger('process')

export function setupGlobalErrorHandlers(): void {
  process.on('uncaughtException', (err) => {
    rootLog.error('uncaughtException', {
      message: err.message,
      stack: err.stack?.slice(0, 800),
    })
  })

  process.on('unhandledRejection', (reason) => {
    rootLog.error('unhandledRejection', {
      reason: String(reason).slice(0, 400),
    })
  })
}

// ── IPC handler: renderer envia erros via ipcMain ────────────────────────────
// Registrado em ipc.ts junto com os outros handlers.
export const RENDERER_LOG_CHANNEL = 'log:renderer'
