/**
 * OGMA — Scheduler de lembretes
 * Verifica a cada 60 s se há lembretes vencidos e dispara notificações Electron.
 */

import { Notification } from 'electron'
import { dbAll, dbRun } from './database'
import { createLogger } from './logger'

const log = createLogger('scheduler')

export const EVENT_TYPE_LABELS: Record<string, string> = {
  prova:     'Prova',
  trabalho:  'Trabalho',
  seminario: 'Seminário',
  defesa:    'Defesa',
  prazo:     'Prazo',
  reuniao:   'Reunião',
  outro:     'Lembrete',
}

export function startReminderScheduler(): void {
  log.info('Scheduler iniciado')
  checkAndFire()
  setInterval(checkAndFire, 60_000)
}

async function checkAndFire(): Promise<void> {
  try {
    const now = new Date().toISOString().slice(0, 16) // YYYY-MM-DDTHH:MM
    const due = await dbAll(
      `SELECT r.*, ce.event_type, ce.start_dt AS event_start
       FROM reminders r
       LEFT JOIN calendar_events ce ON ce.id = r.linked_event_id
       WHERE r.trigger_at <= ? AND r.is_dismissed = 0`,
      now
    )

    for (const r of due) {
      try {
        const label = EVENT_TYPE_LABELS[r.event_type ?? ''] ?? 'Lembrete'
        const body  = r.event_start
          ? `${label} em ${formatDt(r.event_start)}`
          : 'OGMA · Lembrete'

        const notif = new Notification({ title: `◎ ${r.title}`, body })
        notif.show()
      } catch (e) {
        log.warn('Falha ao disparar notificação', { id: r.id, error: String(e) })
      }
      await dbRun(`UPDATE reminders SET is_dismissed = 1 WHERE id = ?`, r.id)
    }

    if (due.length > 0) log.info(`Disparou ${due.length} lembrete(s)`)
  } catch (e) {
    log.error('Erro no scheduler', { error: String(e) })
  }
}

function formatDt(iso: string): string {
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}
