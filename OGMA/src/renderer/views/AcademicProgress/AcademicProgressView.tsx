import React, { useMemo } from 'react'
import { ViewRendererProps } from '../ProjectDashboard/ViewRenderer'
import { disciplineColor, disciplineColorAlpha } from '../../utils/colorUtils'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'

export const AcademicProgressView: React.FC<ViewRendererProps> = ({
  project, pages, properties, dark, onPageOpen, onNewPage,
}) => {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const color  = project.color ?? '#8B7355'

  // Encontrar propriedades relevantes
  const statusProp    = properties.find(p => p.prop_key === 'status')
  const trimestreProp = properties.find(p => p.prop_key === 'trimestre')
  const cicloProp     = properties.find(p => p.prop_key === 'ciclo')
  // ciclo para autodidata, trimestre para projetos acadêmicos convencionais
  const groupProp     = trimestreProp ?? cicloProp
  const groupLabel    = cicloProp && !trimestreProp ? 'Ciclo' : 'Trimestre'
  const notaProp      = properties.find(p => p.prop_key === 'nota')
  const creditosProp  = properties.find(p => p.prop_key === 'creditos')
  const codigoProp    = properties.find(p => p.prop_key === 'codigo')

  const getPV = (page: typeof pages[0], propId: number | undefined) => {
    if (!propId) return undefined
    return page.prop_values?.find(v => v.property_id === propId)
  }

  // Agregar por ciclo/trimestre
  const byTrimester = useMemo(() => {
    const map: Record<string, typeof pages> = {}
    const unsorted: typeof pages = []

    pages.forEach(page => {
      const pv  = groupProp ? getPV(page, groupProp.id) : undefined
      const tri = pv?.value_text ?? ''
      if (tri) {
        if (!map[tri]) map[tri] = []
        map[tri].push(page)
      } else {
        unsorted.push(page)
      }
    })

    const sortedKeys = Object.keys(map).sort()
    const result: { trimester: string; pages: typeof pages }[] = sortedKeys.map(k => ({
      trimester: k,
      pages: map[k],
    }))
    if (unsorted.length > 0) {
      result.push({ trimester: '—', pages: unsorted })
    }
    return result
  }, [pages, trimestreProp])

  // Estatísticas globais
  const stats = useMemo(() => {
    let total = pages.length
    let cursando = 0, concluida = 0, pendente = 0, trancada = 0
    let totalCredits = 0, earnedCredits = 0
    let totalNota = 0, countNota = 0

    pages.forEach(page => {
      const statusVal  = statusProp   ? getPV(page, statusProp.id)?.value_text   : undefined
      const creditVal  = creditosProp ? getPV(page, creditosProp.id)?.value_num  : undefined
      const notaVal    = notaProp     ? getPV(page, notaProp.id)?.value_num       : undefined

      if (statusVal === 'Cursando')  cursando++
      if (statusVal === 'Concluída') concluida++
      if (statusVal === 'Pendente')  pendente++
      if (statusVal === 'Trancada')  trancada++

      if (creditVal) {
        totalCredits += creditVal
        if (statusVal === 'Concluída') earnedCredits += creditVal
      }
      if (notaVal != null) { totalNota += notaVal; countNota++ }
    })

    const gpa = countNota > 0 ? (totalNota / countNota).toFixed(1) : null
    const progress = total > 0 ? Math.round((concluida / total) * 100) : 0

    return { total, cursando, concluida, pendente, trancada, totalCredits, earnedCredits, gpa, progress }
  }, [pages, statusProp, creditosProp, notaProp])

  const getStatus = (page: typeof pages[0]) => {
    if (!statusProp) return null
    return getPV(page, statusProp.id)?.value_text ?? null
  }
  const getNota = (page: typeof pages[0]) => {
    if (!notaProp) return null
    return getPV(page, notaProp.id)?.value_num ?? null
  }
  const getCreditos = (page: typeof pages[0]) => {
    if (!creditosProp) return null
    return getPV(page, creditosProp.id)?.value_num ?? null
  }
  const getCodigo = (page: typeof pages[0]) => {
    if (!codigoProp) return null
    return getPV(page, codigoProp.id)?.value_text ?? null
  }

  const statusColors: Record<string, string> = {
    'Cursando':  accent,
    'Concluída': dark ? '#6A9060' : '#4A6741',
    'Pendente':  ink2,
    'Trancada':  dark ? '#C45A40' : '#8B3A2A',
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 40px' }}>

      {/* ── Resumo global ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
        gap: 10, marginBottom: 24,
      }}>
        {[
          { label: 'Total',      value: stats.total,         sub: 'disciplinas' },
          { label: 'Cursando',   value: stats.cursando,      sub: 'em andamento', col: accent },
          { label: 'Concluídas', value: stats.concluida,     sub: 'finalizadas', col: dark ? '#6A9060' : '#4A6741' },
          { label: 'Créditos',   value: stats.earnedCredits, sub: `de ${stats.totalCredits}` },
          ...(stats.gpa ? [{ label: 'Média', value: stats.gpa, sub: 'nota global', col: accent }] : []),
        ].map(s => (
          <div key={s.label} style={{
            background: cardBg, border: `1px solid ${border}`,
            borderRadius: 2, boxShadow: `2px 2px 0 ${border}`,
            padding: '12px 14px',
          }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: 28, fontStyle: 'italic',
              color: s.col ?? ink, lineHeight: 1, marginBottom: 4,
            }}>{s.value}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
              letterSpacing: '0.1em', color: ink }}>{s.label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
              color: ink2, marginTop: 1 }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* ── Barra de progresso global ── */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.1em' }}>
            PROGRESSO GERAL
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
            {stats.progress}%
          </span>
        </div>
        <div style={{ height: 6, background: border, borderRadius: 3 }}>
          <div style={{
            height: '100%', width: `${stats.progress}%`,
            background: `linear-gradient(to right, ${color}, ${accent})`,
            borderRadius: 3, transition: 'width 500ms ease-out',
          }} />
        </div>
      </div>

      {/* ── Semestres ── */}
      {byTrimester.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
          gap: 12, padding: 40, color: ink2, fontStyle: 'italic', position: 'relative',
          minHeight: 200 }}>
          <CosmosLayer width={560} height={200} seed="academic_empty" density="low" dark={dark}
            style={{ opacity: dark ? 0.22 : 0.1 }} />
          <span style={{ fontSize: 32, opacity: 0.4 }}>◎</span>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: ink }}>
            Nenhuma disciplina ainda
          </span>
          <button className="btn btn-sm" onClick={onNewPage}
            style={{ borderColor: color, color }}>
            + Adicionar disciplina
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {byTrimester.map(({ trimester, pages: triPages }) => {
            const done    = triPages.filter(p => getStatus(p) === 'Concluída').length
            const pct     = triPages.length > 0 ? Math.round((done / triPages.length) * 100) : 0
            const triNota = triPages
              .map(p => getNota(p))
              .filter((n): n is number => n !== null)
            const triAvg  = triNota.length > 0
              ? (triNota.reduce((a, b) => a + b, 0) / triNota.length).toFixed(1)
              : null

            return (
              <div key={trimester}>
                {/* Cabeçalho do trimestre */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
                }}>
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em',
                    color: color, fontWeight: 'bold',
                  }}>
                    {trimester === '—' ? `SEM ${groupLabel.toUpperCase()}` : trimester}
                  </div>
                  <div style={{ flex: 1, height: 1, background: border }} />
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                    {done}/{triPages.length}
                    {triAvg && <> · média {triAvg}</>}
                  </div>
                </div>

                {/* Barra do trimestre */}
                <div style={{ height: 3, background: border, borderRadius: 2, marginBottom: 10 }}>
                  <div style={{
                    height: '100%', width: `${pct}%`,
                    background: color, borderRadius: 2,
                  }} />
                </div>

                {/* Grade de disciplinas */}
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: 8,
                }}>
                  {triPages.map(page => {
                    const status   = getStatus(page)
                    const nota     = getNota(page)
                    const creditos = getCreditos(page)
                    const codigo   = getCodigo(page)
                    const stColor  = status ? (statusColors[status] ?? ink2) : ink2
                    const dColor   = disciplineColor(page.title, dark)
                    const dColorBg = disciplineColorAlpha(page.title, dark, 0.08)

                    return (
                      <button key={page.id}
                        onClick={() => onPageOpen(page)}
                        style={{
                          background: cardBg, border: `1px solid ${border}`,
                          borderLeft: `3px solid ${stColor}`,
                          borderRadius: 2, boxShadow: `2px 2px 0 ${border}`,
                          padding: '10px 12px', cursor: 'pointer', textAlign: 'left',
                          transition: 'transform 80ms',
                        }}
                        onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-1px)')}
                        onMouseLeave={e => (e.currentTarget.style.transform = 'none')}
                      >
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 5 }}>
                          {/* Ícone com cor automática da disciplina */}
                          <span style={{
                            fontSize: 14, flexShrink: 0, lineHeight: 1,
                            width: 26, height: 26, display: 'flex',
                            alignItems: 'center', justifyContent: 'center',
                            borderRadius: 2, background: dColorBg,
                            border: `1px solid ${dColor}33`,
                          }}>
                            {page.icon ?? '◦'}
                          </span>
                          <div style={{ flex: 1, overflow: 'hidden' }}>
                            {codigo && (
                              <div style={{
                                fontFamily: 'var(--font-mono)', fontSize: 8,
                                letterSpacing: '0.12em', color: dColor,
                                marginBottom: 2,
                              }}>
                                {codigo}
                              </div>
                            )}
                            <span style={{
                              fontFamily: 'var(--font-display)', fontSize: 13, fontStyle: 'italic',
                              color: ink, lineHeight: 1.3,
                              display: '-webkit-box', WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical', overflow: 'hidden',
                            }}>
                              {page.title}
                            </span>
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          {status && (
                            <span style={{
                              fontFamily: 'var(--font-mono)', fontSize: 9,
                              letterSpacing: '0.08em', color: stColor,
                              border: `1px solid ${stColor}`,
                              borderRadius: 1, padding: '1px 5px',
                            }}>
                              {status}
                            </span>
                          )}
                          <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
                            {nota != null && (
                              <span style={{
                                fontFamily: 'var(--font-mono)', fontSize: 10,
                                color: nota >= 6 ? (dark ? '#6A9060' : '#4A6741') : (dark ? '#C45A40' : '#8B3A2A'),
                                fontWeight: 'bold',
                              }}>
                                {nota}
                              </span>
                            )}
                            {creditos != null && (
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                                {creditos}cr
                              </span>
                            )}
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
