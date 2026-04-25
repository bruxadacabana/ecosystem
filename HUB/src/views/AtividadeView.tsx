/* ============================================================
   HUB — AtividadeView
   Feed de atividade cross-app — placeholder.
   ============================================================ */

export function AtividadeView() {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 14,
        padding: 40,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: 40,
          color: 'var(--ink-ghost)',
          opacity: 0.3,
          userSelect: 'none',
        }}
      >
        ≋
      </span>
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--ink-ghost)',
          letterSpacing: '0.04em',
          textAlign: 'center',
          maxWidth: 340,
          lineHeight: 1.7,
          margin: 0,
        }}
      >
        Feed de atividade em desenvolvimento.
        <br />
        Mostrará eventos recentes de todos os apps — artigos baixados,
        indexações, transcrições, sessões de escrita.
      </p>
    </div>
  )
}
