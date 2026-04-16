/* ============================================================
   HUB — EditorJS Renderer
   Renderiza body_json do OGMA (formato Editor.js) como React.
   Blocos suportados: paragraph, header, list, checklist,
   quote, code, table, delimiter, columns.
   ============================================================ */

import React from 'react'

// ----------------------------------------------------------
//  Tipos internos
// ----------------------------------------------------------

interface Block {
  type: string
  data: Record<string, unknown>
}

interface EditorOutput {
  blocks: Block[]
}

// ----------------------------------------------------------
//  Componente principal
// ----------------------------------------------------------

interface EditorRendererProps {
  bodyJson: string | null
}

export function EditorRenderer({ bodyJson }: EditorRendererProps) {
  if (!bodyJson) {
    return (
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', fontStyle: 'italic' }}>
        Página sem conteúdo.
      </p>
    )
  }

  let output: EditorOutput
  try {
    output = JSON.parse(bodyJson) as EditorOutput
  } catch {
    return (
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>
        Erro ao ler conteúdo da página.
      </p>
    )
  }

  if (!output.blocks || output.blocks.length === 0) {
    return (
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', fontStyle: 'italic' }}>
        Página sem conteúdo.
      </p>
    )
  }

  return (
    <div className="ej-body">
      {output.blocks.map((block, i) => (
        <BlockRenderer key={i} block={block} />
      ))}
      <EditorStyles />
    </div>
  )
}

// ----------------------------------------------------------
//  Renderizador por tipo de bloco
// ----------------------------------------------------------

function BlockRenderer({ block }: { block: Block }) {
  switch (block.type) {
    case 'paragraph':
      return <ParagraphBlock data={block.data} />
    case 'header':
      return <HeaderBlock data={block.data} />
    case 'list':
      return <ListBlock data={block.data} />
    case 'checklist':
      return <ChecklistBlock data={block.data} />
    case 'quote':
      return <QuoteBlock data={block.data} />
    case 'code':
      return <CodeBlock data={block.data} />
    case 'table':
      return <TableBlock data={block.data} />
    case 'delimiter':
      return <hr className="ej-delimiter" />
    case 'columns':
      return <ColumnsBlock data={block.data} />
    default:
      return null
  }
}

// ----------------------------------------------------------
//  Blocos individuais
// ----------------------------------------------------------

function ParagraphBlock({ data }: { data: Record<string, unknown> }) {
  const text = String(data.text ?? '')
  if (!text) return null
  return (
    <p
      className="ej-paragraph"
      dangerouslySetInnerHTML={{ __html: text }}
    />
  )
}

function HeaderBlock({ data }: { data: Record<string, unknown> }) {
  const text  = String(data.text ?? '')
  const level = Number(data.level ?? 2)
  const Tag   = `h${Math.min(Math.max(level, 1), 6)}` as React.ElementType
  return (
    <Tag
      className={`ej-header ej-header-${level}`}
      dangerouslySetInnerHTML={{ __html: text }}
    />
  )
}

function ListBlock({ data }: { data: Record<string, unknown> }) {
  const style = String(data.style ?? 'unordered')
  const items = Array.isArray(data.items) ? (data.items as unknown[]) : []

  const renderItem = (item: unknown, i: number): React.ReactNode => {
    if (typeof item === 'string') {
      return <li key={i} dangerouslySetInnerHTML={{ __html: item }} />
    }
    if (item && typeof item === 'object') {
      const obj = item as Record<string, unknown>
      const content = String(obj.content ?? '')
      const nested  = Array.isArray(obj.items) ? (obj.items as unknown[]) : []
      return (
        <li key={i}>
          <span dangerouslySetInnerHTML={{ __html: content }} />
          {nested.length > 0 && (
            style === 'ordered'
              ? <ol className="ej-list ej-list-ol">{nested.map(renderItem)}</ol>
              : <ul className="ej-list ej-list-ul">{nested.map(renderItem)}</ul>
          )}
        </li>
      )
    }
    return null
  }

  if (style === 'ordered') {
    return <ol className="ej-list ej-list-ol">{items.map(renderItem)}</ol>
  }
  return <ul className="ej-list ej-list-ul">{items.map(renderItem)}</ul>
}

function ChecklistBlock({ data }: { data: Record<string, unknown> }) {
  const items = Array.isArray(data.items)
    ? (data.items as Array<{ text: string; checked: boolean }>)
    : []
  return (
    <ul className="ej-checklist">
      {items.map((item, i) => (
        <li key={i} className={`ej-checklist-item${item.checked ? ' ej-checklist-item--done' : ''}`}>
          <span className="ej-checklist-box">{item.checked ? '✓' : ''}</span>
          <span dangerouslySetInnerHTML={{ __html: item.text ?? '' }} />
        </li>
      ))}
    </ul>
  )
}

function QuoteBlock({ data }: { data: Record<string, unknown> }) {
  const text    = String(data.text ?? '')
  const caption = String(data.caption ?? '')
  return (
    <blockquote className="ej-quote">
      <p dangerouslySetInnerHTML={{ __html: text }} />
      {caption && <cite dangerouslySetInnerHTML={{ __html: caption }} />}
    </blockquote>
  )
}

function CodeBlock({ data }: { data: Record<string, unknown> }) {
  return (
    <pre className="ej-code">
      <code>{String(data.code ?? '')}</code>
    </pre>
  )
}

function TableBlock({ data }: { data: Record<string, unknown> }) {
  const withHeadings = Boolean(data.withHeadings)
  const content = Array.isArray(data.content)
    ? (data.content as string[][])
    : []
  if (content.length === 0) return null

  const [head, ...body] = content

  return (
    <div className="ej-table-wrapper">
      <table className="ej-table">
        {withHeadings && head && (
          <thead>
            <tr>{head.map((cell, i) => (
              <th key={i} dangerouslySetInnerHTML={{ __html: cell }} />
            ))}</tr>
          </thead>
        )}
        <tbody>
          {(withHeadings ? body : content).map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci} dangerouslySetInnerHTML={{ __html: cell }} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ColumnsBlock({ data }: { data: Record<string, unknown> }) {
  const left  = String(data.left ?? '')
  const right = String(data.right ?? '')
  return (
    <div className="ej-columns">
      <div className="ej-column" dangerouslySetInnerHTML={{ __html: left }} />
      <div className="ej-column" dangerouslySetInnerHTML={{ __html: right }} />
    </div>
  )
}

// ----------------------------------------------------------
//  Estilos inline (scoped)
// ----------------------------------------------------------

function EditorStyles() {
  return (
    <style>{`
      .ej-body { color: var(--ink); }

      .ej-paragraph {
        font-size: 14px; line-height: 1.75; margin-bottom: 0.9em;
      }
      .ej-paragraph b, .ej-paragraph strong { font-weight: 600; }
      .ej-paragraph i, .ej-paragraph em { font-style: italic; }
      .ej-paragraph u { text-decoration: underline; }
      .ej-paragraph a { color: var(--accent); }
      .ej-paragraph mark { background: color-mix(in srgb, var(--accent) 30%, transparent); }
      .ej-paragraph code {
        font-family: var(--font-mono); font-size: 12px;
        background: var(--paper-dark); padding: 1px 4px; border-radius: 2px;
      }

      .ej-header { font-family: var(--font-display); font-style: italic; font-weight: normal;
                   color: var(--ink); margin: 1.4em 0 0.4em; line-height: 1.2; }
      .ej-header-1 { font-size: 24px; }
      .ej-header-2 { font-size: 19px; }
      .ej-header-3 { font-size: 15px; }

      .ej-list { padding-left: 1.5em; margin-bottom: 0.9em; }
      .ej-list li { font-size: 14px; line-height: 1.7; margin-bottom: 2px; }
      .ej-list-ul { list-style-type: disc; }
      .ej-list-ol { list-style-type: decimal; }

      .ej-checklist { list-style: none; padding: 0; margin-bottom: 0.9em; }
      .ej-checklist-item {
        display: flex; align-items: baseline; gap: 8px;
        font-size: 14px; line-height: 1.7; margin-bottom: 2px;
      }
      .ej-checklist-item--done { opacity: 0.5; text-decoration: line-through; }
      .ej-checklist-box {
        width: 14px; height: 14px; border: 1px solid var(--rule); border-radius: 2px;
        display: flex; align-items: center; justify-content: center;
        font-size: 10px; flex-shrink: 0; color: var(--accent);
      }

      .ej-quote {
        border-left: 3px solid var(--rule); margin: 1em 0;
        padding: 0.5em 1em; font-style: italic; color: var(--ink-ghost);
      }
      .ej-quote p { margin: 0 0 4px; font-size: 14px; line-height: 1.6; }
      .ej-quote cite { font-size: 11px; font-style: normal; }

      .ej-code {
        background: var(--paper-dark); border-radius: 2px;
        padding: 12px 14px; margin-bottom: 0.9em; overflow-x: auto;
      }
      .ej-code code { font-family: var(--font-mono); font-size: 12px; }

      .ej-table-wrapper { overflow-x: auto; margin-bottom: 0.9em; }
      .ej-table { border-collapse: collapse; width: 100%; font-size: 13px; }
      .ej-table th, .ej-table td {
        border: 1px solid var(--rule); padding: 6px 10px; text-align: left;
      }
      .ej-table th { font-family: var(--font-mono); font-size: 10px;
                      letter-spacing: 0.1em; text-transform: uppercase; }

      .ej-delimiter { border: none; border-top: 1px solid var(--rule); margin: 1.5em 0; }

      .ej-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 0.9em; }
      .ej-column { font-size: 14px; line-height: 1.7; }
    `}</style>
  )
}
