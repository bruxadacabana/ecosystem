/**
 * OGMA EditorFrame
 * Segue o padrão do StudyFlow: dynamic import do Editor.js direto no renderer,
 * montado em uma div via ref. Sem iframe, sem bundle separado, sem build step.
 */
import React, { useRef, useEffect, useCallback, useState } from 'react'
import { createLogger } from '../../utils/logger'
import { AlchemyLoader } from '../UI/AlchemyLoader'
import './EditorFrame.css'

const log = createLogger('EditorFrame')

// ── ColumnsBlock ───────────────────────────────────────────────────────────────
// Block customizado: dois painéis lado a lado com contenteditable independente.

class ColumnsBlock {
  private _wrapper: HTMLDivElement | null = null
  private data: { left: string; right: string }
  private readonly readOnly: boolean

  static get toolbox() {
    return { title: 'Colunas', icon: '⊞' }
  }
  static get isReadOnlySupported() { return true }
  static get sanitize() {
    return { left: { b: true, i: true, u: true, br: true }, right: { b: true, i: true, u: true, br: true } }
  }

  constructor({ data, readOnly }: any) {
    this.data     = { left: data?.left ?? '', right: data?.right ?? '' }
    this.readOnly = readOnly ?? false
  }

  render() {
    const wrapper = document.createElement('div')
    wrapper.className = 'columns-block'

    const makeCol = (content: string, side: 'left' | 'right') => {
      const col = document.createElement('div')
      col.className = 'columns-block__col'
      col.dataset.col = side
      col.dataset.placeholder = side === 'left' ? 'Coluna esquerda…' : 'Coluna direita…'
      col.contentEditable = String(!this.readOnly)
      col.innerHTML = content

      if (!this.readOnly) {
        col.addEventListener('keydown', (e: KeyboardEvent) => {
          // Impede que o Editor.js intercepte teclas dentro das colunas
          e.stopPropagation()

          // Tab → muda de coluna
          if (e.key === 'Tab') {
            e.preventDefault()
            const otherSide = side === 'left' ? 'right' : 'left'
            const other = wrapper.querySelector<HTMLElement>(`[data-col="${otherSide}"]`)
            other?.focus()
          }
        })

        // Impede que paste acione o handler global do Editor.js
        col.addEventListener('paste', (e) => e.stopPropagation())
      }
      return col
    }

    wrapper.appendChild(makeCol(this.data.left, 'left'))
    wrapper.appendChild(makeCol(this.data.right, 'right'))
    this._wrapper = wrapper
    return wrapper
  }

  save() {
    if (!this._wrapper) return this.data
    return {
      left:  this._wrapper.querySelector<HTMLElement>('[data-col="left"]')?.innerHTML  ?? '',
      right: this._wrapper.querySelector<HTMLElement>('[data-col="right"]')?.innerHTML ?? '',
    }
  }
}

interface Props {
  content:   string | null
  dark:      boolean
  readOnly?: boolean
  onSave:    (content: string) => void
  onReady?:  () => void
}

export const EditorFrame: React.FC<Props> = ({
  content, dark, readOnly = false, onSave, onReady,
}) => {
  const holderRef     = useRef<HTMLDivElement>(null)
  const editorRef     = useRef<any>(null)
  const saveTimerRef  = useRef<any>(null)
  const [loading, setLoading] = useState(true)
  const onSaveRef  = useRef(onSave)
  const onReadyRef = useRef(onReady)

  // Manter refs atualizados sem recriar o editor
  useEffect(() => { onSaveRef.current  = onSave  }, [onSave])
  useEffect(() => { onReadyRef.current = onReady }, [onReady])

  // Aplicar tema dark/light ao holder
  useEffect(() => {
    if (holderRef.current) {
      holderRef.current.classList.toggle('editor-dark', dark)
    }
  }, [dark])

  // Inicializar editor
  useEffect(() => {
    if (!holderRef.current) return

    let destroyed = false

    const init = async () => {
      // Destruir instância anterior se existir
      if (editorRef.current?.destroy) {
        await editorRef.current.destroy()
        editorRef.current = null
      }

      // Dynamic imports — exatamente como o StudyFlow faz
      const [
        { default: EditorJS },
        { default: Header },
        { default: List },
        { default: Checklist },
        { default: Quote },
        { default: Code },
        { default: Table },
        { default: InlineCode },
        { default: Delimiter },
        { default: Marker },
      ] = await Promise.all([
        import('@editorjs/editorjs'),
        import('@editorjs/header'),
        import('@editorjs/list'),
        import('@editorjs/checklist'),
        import('@editorjs/quote'),
        import('@editorjs/code'),
        import('@editorjs/table'),
        import('@editorjs/inline-code'),
        import('@editorjs/delimiter'),
        import('@editorjs/marker'),
      ])

      // Toggle — opcional, não quebra se não existir
      let ToggleBlock: any = null
      try {
        const mod = await import('editorjs-toggle-block')
        ToggleBlock = mod.default
      } catch {}

      if (destroyed) return

      // Parsear conteúdo
      let data: any = {}
      if (content) {
        try { data = JSON.parse(content) } catch {}
      }

      const tools: any = {
        header:     { class: Header,       config: { levels: [1, 2, 3], defaultLevel: 2 } },
        list:       { class: List,         inlineToolbar: true },
        checklist:  { class: Checklist,    inlineToolbar: true },
        quote:      { class: Quote,        inlineToolbar: true, config: { quotePlaceholder: 'Escreva uma citação...', captionPlaceholder: 'Autor' } },
        code:       { class: Code },
        table:      { class: Table,        inlineToolbar: true, config: { rows: 2, cols: 3, withHeadings: true } },
        inlineCode: { class: InlineCode },
        delimiter:  { class: Delimiter },
        marker:     { class: Marker },
        columns:    { class: ColumnsBlock },
      }

      if (ToggleBlock) {
        tools.toggle = { class: ToggleBlock }
      }

      editorRef.current = new EditorJS({
        holder:        holderRef.current!,
        data,
        placeholder:   'Escreva algo ou pressione "/" para inserir um bloco...',
        readOnly,
        tools,
        inlineToolbar: ['bold', 'italic', 'marker', 'inlineCode', 'link'],

        onChange: async () => {
          clearTimeout(saveTimerRef.current)
          saveTimerRef.current = setTimeout(async () => {
            if (!editorRef.current) return
            try {
              const output = await editorRef.current.save()
              onSaveRef.current(JSON.stringify(output))
            } catch (e: any) {
              log.error('save failed', { error: e.message })
            }
          }, 1500)
        },

        onReady: async () => {
          // Activar drag-and-drop para reordenar blocos
          try {
            const { default: DragDrop } = await import('editorjs-drag-drop')
            new DragDrop(editorRef.current, '2px dashed #C4B9A8')
          } catch (e) {
            log.warn('drag-drop plugin não disponível', {})
          }
          setLoading(false)
          onReadyRef.current?.()
          log.debug('editor pronto')
        },
      })
    }

    init().catch(e => {
      log.error('init failed', { error: e.message })
      setLoading(false)
    })

    return () => {
      destroyed = true
      clearTimeout(saveTimerRef.current)
      if (editorRef.current?.destroy) {
        editorRef.current.destroy()
        editorRef.current = null
      }
    }
  // Só reinicia quando muda a página (content muda de forma estrutural)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])  // Monta uma vez — troca de conteúdo é feita abaixo via render()

  // Carregar novo conteúdo ao trocar de página sem recriar o editor
  const prevContentRef = useRef(content)
  useEffect(() => {
    if (prevContentRef.current === content) return
    prevContentRef.current = content

    if (!editorRef.current) return
    setLoading(true)
    let data: any = {}
    if (content) { try { data = JSON.parse(content) } catch {} }
    editorRef.current.render(data).then(() => setLoading(false)).catch(() => setLoading(false))
  }, [content])

  return (
    <div className="editor-frame-wrapper">
      {loading && (
        <div className="editor-loading">
          <AlchemyLoader symbol="☿" size="md" />
        </div>
      )}
      <div
        ref={holderRef}
        className={`editor-holder${dark ? ' editor-dark' : ''}${loading ? ' editor-holder--hidden' : ''}`}
      />
    </div>
  )
}
