/**
 * OGMA Logger — Processo Renderer (React)
 *
 * Erros e eventos importantes são enviados ao processo main via IPC,
 * que os grava no arquivo de log em data/logs/.
 *
 * Em desenvolvimento também imprime no console do DevTools.
 */

type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

interface RendererLogEntry {
  level:   LogLevel
  module:  string
  message: string
  meta?:   Record<string, unknown>
  ms?:     number
}

const isDev = import.meta.env.DEV

function send(entry: RendererLogEntry): void {
  // Console do DevTools em dev
  if (isDev) {
    const styles: Record<LogLevel, string> = {
      DEBUG: 'color: #888',
      INFO:  'color: #2196F3',
      WARN:  'color: #FF9800; font-weight: bold',
      ERROR: 'color: #F44336; font-weight: bold',
    }
    const perf = entry.ms !== undefined ? ` [${entry.ms}ms]` : ''
    console.log(
      `%c[${entry.level}] [${entry.module}]${perf} ${entry.message}`,
      styles[entry.level],
      entry.meta ?? '',
    )
  }

  // Enviar ao main apenas WARN e ERROR (evitar flood de DEBUG/INFO via IPC)
  if (entry.level === 'WARN' || entry.level === 'ERROR') {
    try {
      ;(window as any).db?.log?.renderer(entry)
    } catch {
      // silencioso
    }
  }
}

export function createLogger(module: string) {
  return {
    debug: (message: string, meta?: Record<string, unknown>) =>
      send({ level: 'DEBUG', module, message, meta }),

    info: (message: string, meta?: Record<string, unknown>) =>
      send({ level: 'INFO', module, message, meta }),

    warn: (message: string, meta?: Record<string, unknown>) =>
      send({ level: 'WARN', module, message, meta }),

    error: (message: string, meta?: Record<string, unknown>) =>
      send({ level: 'ERROR', module, message, meta }),

    /**
     * Mede o tempo de execução de uma função síncrona.
     * Loga como WARN se ultrapassar warnMs (padrão: 100ms no renderer).
     */
    perf: <T>(label: string, fn: () => T, warnMs = 100): T => {
      const start = performance.now()
      const result = fn()
      const ms = Math.round(performance.now() - start)
      send({ level: ms >= warnMs ? 'WARN' : 'DEBUG', module, message: label, ms })
      return result
    },
  }
}

/**
 * Captura erros globais do React e do window.
 * Chamar uma vez em main.tsx.
 */
export function setupRendererErrorHandlers(): void {
  // Erros JS não capturados
  window.addEventListener('error', (e) => {
    send({
      level: 'ERROR',
      module: 'window',
      message: e.message,
      meta: {
        filename: e.filename,
        line: e.lineno,
        col: e.colno,
        stack: e.error?.stack?.slice(0, 600),
      },
    })
  })

  // Promises não tratadas
  window.addEventListener('unhandledrejection', (e) => {
    send({
      level: 'ERROR',
      module: 'window',
      message: 'unhandledRejection',
      meta: { reason: String(e.reason).slice(0, 400) },
    })
  })
}
