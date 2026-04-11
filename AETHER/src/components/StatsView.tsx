/* ============================================================
   AETHER — StatsView (5.4)
   Painel de estatísticas do projeto:
   - Total de palavras e capítulos
   - Distribuição de status
   - Histórico de sessões de escrita (14 dias)
   - Streak de escrita diária
   - Meta de palavras do livro
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { Book, WritingSession } from '../types'

interface StatsViewProps {
  projectId: string
  onError: (msg: string) => void
}

interface AggStats {
  totalWords: number
  totalChapters: number
  draft: number
  revision: number
  final: number
  books: Book[]
}

export function StatsView({ projectId, onError }: StatsViewProps) {
  const [agg, setAgg] = useState<AggStats | null>(null)
  const [sessions, setSessions] = useState<WritingSession[]>([])
  const [streak, setStreak] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    load()
  }, [projectId])

  async function load() {
    setLoading(true)

    const [booksRes, sessionsRes, streakRes] = await Promise.all([
      cmd.listBooks(projectId),
      cmd.listSessions(projectId),
      cmd.getWritingStreak(projectId),
    ])

    if (!booksRes.ok) { onError(booksRes.error.message); setLoading(false); return }

    // Carregar livros completos para ter word_count dos capítulos
    const fullBooks: Book[] = []
    for (const meta of booksRes.data) {
      const r = await cmd.openBook(projectId, meta.id)
      if (r.ok) fullBooks.push(r.data)
    }

    let totalWords = 0
    let totalChapters = 0
    let draft = 0, revision = 0, final_ = 0
    for (const b of fullBooks) {
      for (const ch of b.chapters) {
        if (ch.trashed_at) continue
        totalWords += ch.word_count
        totalChapters++
        if (ch.status === 'draft') draft++
        else if (ch.status === 'revision') revision++
        else if (ch.status === 'final') final_++
      }
    }

    setAgg({ totalWords, totalChapters, draft, revision, final: final_, books: fullBooks })
    if (sessionsRes.ok) setSessions(sessionsRes.data)
    if (streakRes.ok) setStreak(streakRes.data)

    setLoading(false)
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--ink-ghost)', letterSpacing: '0.06em', animation: 'blink 1.2s ease infinite' }}>· · ·</p>
      </div>
    )
  }

  if (!agg) return null

  // Gráfico de barras dos últimos 14 dias
  const dailyData = buildDailyData(sessions, 14)
  const maxDay = Math.max(...dailyData.map((d) => d.words), 1)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px 60px', background: 'var(--paper)' }}>

      {/* Título */}
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--ink-ghost)', margin: '0 0 28px' }}>
        Estatísticas do Projeto
      </p>

      {/* Métricas principais */}
      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', marginBottom: '40px' }}>
        <StatCard value={formatWords(agg.totalWords)} label="palavras" />
        <StatCard value={String(agg.totalChapters)} label="capítulos" />
        <StatCard
          value={streak > 0 ? `${streak}` : '—'}
          label={streak === 1 ? 'dia seguido' : 'dias seguidos'}
          accent={streak > 0}
        />
        <StatCard value={String(sessions.filter((s) => s.ended_at).length)} label="sessões" />
      </div>

      {/* Distribuição de status */}
      {agg.totalChapters > 0 && (
        <div style={{ marginBottom: '40px' }}>
          <SectionHeader>Distribuição</SectionHeader>
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <StatusBar label="Rascunho" count={agg.draft} total={agg.totalChapters} color="var(--ink-ghost)" />
            <StatusBar label="Revisão" count={agg.revision} total={agg.totalChapters} color="var(--accent)" />
            <StatusBar label="Final" count={agg.final} total={agg.totalChapters} color="var(--accent-green)" />
          </div>
        </div>
      )}

      {/* Meta por livro */}
      {agg.books.some((b) => b.word_goal) && (
        <div style={{ marginBottom: '40px' }}>
          <SectionHeader>Metas por Livro</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {agg.books.filter((b) => b.word_goal).map((b) => {
              const bookWords = b.chapters.filter((c) => !c.trashed_at).reduce((s, c) => s + c.word_count, 0)
              const goal = b.word_goal!
              const pct = Math.min(100, (bookWords / goal) * 100)
              return (
                <div key={b.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '13px', color: 'var(--ink)' }}>{b.name}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: pct >= 100 ? 'var(--accent-green)' : 'var(--ink-ghost)' }}>
                      {formatWords(bookWords)}/{formatWords(goal)}
                    </span>
                  </div>
                  <div style={{ height: '5px', background: 'var(--rule)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: pct >= 100 ? 'var(--accent-green)' : 'var(--accent)', transition: 'width 0.5s ease' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Gráfico de escrita — 14 dias */}
      {dailyData.some((d) => d.words > 0) && (
        <div style={{ marginBottom: '40px' }}>
          <SectionHeader>Últimos 14 dias</SectionHeader>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '72px' }}>
            {dailyData.map((d) => (
              <div
                key={d.date}
                title={`${d.label}: ${d.words} palavras`}
                style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}
              >
                <div style={{
                  width: '100%',
                  height: `${Math.max(2, (d.words / maxDay) * 56)}px`,
                  background: d.isToday ? 'var(--accent)' : d.words > 0 ? 'var(--stamp)' : 'var(--rule)',
                  borderRadius: '2px 2px 0 0',
                  transition: 'height 0.3s ease',
                  minHeight: d.words > 0 ? '4px' : '2px',
                }} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '4px', marginTop: '4px' }}>
            {dailyData.map((d) => (
              <div key={d.date} style={{ flex: 1, textAlign: 'center' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '8px', color: d.isToday ? 'var(--accent)' : 'var(--ink-ghost)', letterSpacing: '0.04em' }}>
                  {d.dayLabel}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sessões recentes */}
      {sessions.filter((s) => s.ended_at).length > 0 && (
        <div>
          <SectionHeader>Sessões Recentes</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {sessions
              .filter((s) => s.ended_at)
              .slice(-10)
              .reverse()
              .map((s) => {
                const wordsWritten = Math.max(0, s.words_at_end - s.words_at_start)
                const durationSec = s.ended_at
                  ? Math.round((new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()) / 1000)
                  : 0
                return (
                  <div key={s.id} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '7px 0',
                    borderBottom: '1px solid var(--rule)',
                  }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ink-ghost)', letterSpacing: '0.04em', flexShrink: 0 }}>
                      {formatSessionDate(s.started_at)}
                    </span>
                    <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '12px', color: 'var(--ink-faint)', flex: 1 }}>
                      {formatDuration(durationSec)}
                    </span>
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                      color: wordsWritten > 0 ? 'var(--accent)' : 'var(--ink-ghost)',
                      letterSpacing: '0.04em',
                    }}>
                      {wordsWritten > 0 ? `+${wordsWritten}` : '—'}
                    </span>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {sessions.filter((s) => s.ended_at).length === 0 && (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ink-ghost)', letterSpacing: '0.06em', marginTop: '40px' }}>
          Nenhuma sessão de escrita registrada ainda.
        </p>
      )}
    </div>
  )
}

// ----------------------------------------------------------
//  Sub-componentes
// ----------------------------------------------------------

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--ink-ghost)', margin: '0 0 12px' }}>
      {children}
    </p>
  )
}

function StatCard({ value, label, accent = false }: { value: string; label: string; accent?: boolean }) {
  return (
    <div style={{
      background: 'var(--paper-dark)',
      border: '1px solid var(--rule)',
      borderRadius: 'var(--radius)',
      padding: '14px 20px',
      boxShadow: '3px 3px 0 var(--paper-darker)',
      minWidth: '90px',
    }}>
      <p style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: '28px',
        color: accent ? 'var(--accent)' : 'var(--ink)',
        margin: 0,
        lineHeight: 1,
      }}>{value}</p>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink-ghost)', margin: '4px 0 0' }}>{label}</p>
    </div>
  )
}

function StatusBar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <div style={{ flex: '1 1 120px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.12em', color }}>{label}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ink-ghost)' }}>{count}</span>
      </div>
      <div style={{ height: '4px', background: 'var(--rule)', borderRadius: '2px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  Helpers
// ----------------------------------------------------------

function formatWords(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  return `${h}h${m % 60 > 0 ? ` ${m % 60}min` : ''}`
}

function formatSessionDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

interface DayData {
  date: string
  label: string
  dayLabel: string
  words: number
  isToday: boolean
}

function buildDailyData(sessions: WritingSession[], days: number): DayData[] {
  // Calcular palavras por dia a partir das sessões encerradas
  const byDate: Record<string, number> = {}
  for (const s of sessions) {
    if (!s.ended_at) continue
    const written = Math.max(0, s.words_at_end - s.words_at_start)
    if (written === 0) continue
    const date = s.ended_at.slice(0, 10)
    byDate[date] = (byDate[date] ?? 0) + written
  }

  const result: DayData[] = []
  const today = new Date()

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(today.getDate() - i)
    const date = d.toISOString().slice(0, 10)
    const dayNames = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S']
    result.push({
      date,
      label: d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }),
      dayLabel: dayNames[d.getDay()],
      words: byDate[date] ?? 0,
      isToday: i === 0,
    })
  }

  return result
}
