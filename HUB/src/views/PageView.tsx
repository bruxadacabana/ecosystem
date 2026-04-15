/* ============================================================
   HUB — PageView
   Árvore de páginas à esquerda + conteúdo Editor.js à direita.
   ============================================================ */

import { useEffect, useMemo, useState } from 'react'
import { EditorRenderer } from '../lib/editorjs-renderer'
import * as cmd from '../lib/tauri'
import type { OgmaPage, OgmaProject } from '../types'

interface PageViewProps {
  dataPath: string
  project: OgmaProject
  onBack: () => void
}

// Nó da árvore de páginas
interface PageNode extends OgmaPage {
  children: PageNode[]
}

export function PageView({ dataPath, project, onBack }: PageViewProps) {
  const [pages, setPages]             = useState<OgmaPage[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [selectedPage, setSelectedPage] = useState<OgmaPage | null>(null)

  useEffect(() => {
    setLoading(true)
    setSelectedPage(null)
    cmd.listProjectPages(dataPath, project.id).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setPages(result.data)
      // Seleciona a primeira página automaticamente
      if (result.data.length > 0) {
        setSelectedPage(result.data[0])
      }
    })
  }, [dataPath, project.id])

  // Monta árvore a partir da lista plana
  const tree = useMemo(() => buildTree(pages), [pages])

  const accentColor = project.color ?? 'var(--accent)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Projetos</button>
        <span style={{ color: 'var(--rule)' }}>|</span>
        {project.icon && <span style={{ fontSize: 16 }}>{project.icon}</span>}
        <h1 style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 18,
          color: 'var(--ink)', fontWeight: 'normal',
        }}>
          {project.name}
        </h1>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.12em',
          textTransform: 'uppercase', color: accentColor,
          border: `1px solid ${accentColor}`, borderRadius: 2, padding: '1px 5px',
        }}>
          {project.project_type}
        </span>
      </div>

      {/* Corpo: sidebar + conteúdo */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Sidebar: árvore de páginas */}
        <aside style={{
          width: 220, flexShrink: 0,
          borderRight: '1px solid var(--rule)',
          overflowY: 'auto',
          padding: '12px 0',
        }}>
          {loading && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', padding: '8px 16px' }}>
              Carregando…
            </p>
          )}
          {error && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#8B3A2A', padding: '8px 16px' }}>
              {error}
            </p>
          )}
          {!loading && !error && pages.length === 0 && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', padding: '8px 16px' }}>
              Sem páginas.
            </p>
          )}
          {tree.map(node => (
            <PageTreeNode
              key={node.id}
              node={node}
              depth={0}
              selectedId={selectedPage?.id ?? null}
              accentColor={accentColor}
              onSelect={setSelectedPage}
            />
          ))}
        </aside>

        {/* Área de conteúdo */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '28px 32px 48px' }}>
          {!selectedPage && !loading && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
              Selecione uma página na lista.
            </p>
          )}

          {selectedPage && (
            <>
              <header style={{ marginBottom: 24 }}>
                <h2 style={{
                  fontFamily: 'var(--font-display)', fontStyle: 'italic', fontWeight: 'normal',
                  fontSize: 26, color: 'var(--ink)', lineHeight: 1.2,
                }}>
                  {selectedPage.icon && <span style={{ marginRight: 10, fontSize: 22 }}>{selectedPage.icon}</span>}
                  {selectedPage.title}
                </h2>
              </header>

              <EditorRenderer bodyJson={selectedPage.body_json} />
            </>
          )}
        </main>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  Nó da árvore
// ----------------------------------------------------------

interface PageTreeNodeProps {
  node: PageNode
  depth: number
  selectedId: number | null
  accentColor: string
  onSelect: (page: OgmaPage) => void
}

function PageTreeNode({ node, depth, selectedId, accentColor, onSelect }: PageTreeNodeProps) {
  const [expanded, setExpanded] = useState(true)
  const isSelected = node.id === selectedId
  const hasChildren = node.children.length > 0

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {/* Botão expandir/colapsar */}
        {hasChildren ? (
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              width: 16, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--ink-ghost)', fontSize: 8, flexShrink: 0,
              marginLeft: depth * 12 + 4,
            }}
          >
            {expanded ? '▾' : '▸'}
          </button>
        ) : (
          <span style={{ width: 16, marginLeft: depth * 12 + 4, flexShrink: 0 }} />
        )}

        {/* Linha de página */}
        <button
          onClick={() => onSelect(node)}
          style={{
            flex: 1, display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 12px 5px 4px', minWidth: 0,
            background: isSelected ? `color-mix(in srgb, ${accentColor} 12%, transparent)` : 'transparent',
            borderLeft: isSelected ? `2px solid ${accentColor}` : '2px solid transparent',
            border: 'none', borderRight: 'none', borderTop: 'none', borderBottom: 'none',
            cursor: 'pointer', textAlign: 'left',
            transition: 'background 120ms',
          }}
        >
          {node.icon && <span style={{ fontSize: 12, flexShrink: 0 }}>{node.icon}</span>}
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: isSelected ? 'var(--ink)' : 'var(--ink-ghost)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            transition: 'color 120ms',
          }}>
            {node.title}
          </span>
        </button>
      </div>

      {/* Filhos */}
      {hasChildren && expanded && node.children.map(child => (
        <PageTreeNode
          key={child.id}
          node={child}
          depth={depth + 1}
          selectedId={selectedId}
          accentColor={accentColor}
          onSelect={onSelect}
        />
      ))}
    </>
  )
}

// ----------------------------------------------------------
//  buildTree — lista plana → árvore
// ----------------------------------------------------------

function buildTree(pages: OgmaPage[]): PageNode[] {
  const map = new Map<number, PageNode>()
  const roots: PageNode[] = []

  for (const page of pages) {
    map.set(page.id, { ...page, children: [] })
  }

  for (const node of map.values()) {
    if (node.parent_id != null && map.has(node.parent_id)) {
      map.get(node.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  // Ordena por sort_order em cada nível
  const sortNodes = (nodes: PageNode[]) => {
    nodes.sort((a, b) => a.sort_order - b.sort_order)
    for (const n of nodes) sortNodes(n.children)
  }
  sortNodes(roots)

  return roots
}
