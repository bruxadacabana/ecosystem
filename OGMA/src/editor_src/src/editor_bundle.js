/**
 * OGMA Editor Bundle
 * Importa e configura o Editor.js com todos os plugins.
 * Compilado por esbuild → editor.bundle.js
 */

// ── Imports dinâmicos (necessário para Editor.js funcionar no bundle) ─────────

let EditorJS, Header, List, Checklist, Quote, Code, Table, ImageTool, InlineCode, Delimiter, ToggleBlock

async function loadModules() {
  // Editor.js requer dynamic import para funcionar corretamente em bundles
  const [
    ejsMod, headerMod, listMod, checkMod, quoteMod,
    codeMod, tableMod, imageMod, inlineMod, delimMod, toggleMod
  ] = await Promise.all([
    import('@editorjs/editorjs'),
    import('@editorjs/header'),
    import('@editorjs/list'),
    import('@editorjs/checklist'),
    import('@editorjs/quote'),
    import('@editorjs/code'),
    import('@editorjs/table'),
    import('@editorjs/image'),
    import('@editorjs/inline-code'),
    import('@editorjs/delimiter'),
    import('editorjs-toggle-block').catch(() => null),
  ])

  EditorJS    = ejsMod.default
  Header      = headerMod.default
  List        = listMod.default
  Checklist   = checkMod.default
  Quote       = quoteMod.default
  Code        = codeMod.default
  Table       = tableMod.default
  ImageTool   = imageMod.default
  InlineCode  = inlineMod.default
  Delimiter   = delimMod.default
  ToggleBlock = toggleMod?.default ?? null
}

// ── Estado do editor ──────────────────────────────────────────────────────────

let editor    = null
let saveTimer = null
let isDark    = false

// ── Comunicação com o React (parent frame) ────────────────────────────────────

function sendToParent(type, payload = {}) {
  window.parent.postMessage({ source: 'ogma-editor', type, ...payload }, '*')
}

// Receber mensagens do React
window.addEventListener('message', async (e) => {
  if (!e.data || e.data.source !== 'ogma-app') return
  const { type, data } = e.data

  switch (type) {
    case 'init':
      isDark = data?.dark ?? false
      await initEditor(data?.content ?? null)
      break
    case 'load':
      if (editor) {
        try {
          await editor.render(data?.content ?? { blocks: [] })
        } catch {}
      }
      break
    case 'save':
      await doSave()
      break
    case 'set-theme':
      isDark = data?.dark ?? false
      applyTheme()
      break
    case 'focus':
      editor?.focus?.()
      break
  }
})

// ── Inicializar editor ────────────────────────────────────────────────────────

async function initEditor(initialContent) {
  await loadModules()

  const tools = {
    header: {
      class: Header,
      config: { levels: [1, 2, 3], defaultLevel: 2 },
      shortcut: 'CMD+SHIFT+H',
    },
    list: {
      class: List,
      inlineToolbar: true,
      config: { defaultStyle: 'unordered' },
    },
    checklist: {
      class: Checklist,
      inlineToolbar: true,
    },
    quote: {
      class: Quote,
      inlineToolbar: true,
      config: { quotePlaceholder: 'Escreva uma citação...', captionPlaceholder: 'Autor' },
    },
    code: { class: Code },
    table: {
      class: Table,
      inlineToolbar: true,
      config: { rows: 2, cols: 3, withHeadings: true },
    },
    image: {
      class: ImageTool,
      config: {
        // Upload via postMessage — o React recebe e salva em data/uploads/
        uploader: {
          uploadByFile: async (file) => {
            return new Promise((resolve) => {
              const reader = new FileReader()
              reader.onload = (e) => {
                sendToParent('upload-image', { data: e.target.result, name: file.name })
                // Aguardar resposta do parent
                const handler = (evt) => {
                  if (evt.data?.source === 'ogma-app' && evt.data?.type === 'upload-image-result') {
                    window.removeEventListener('message', handler)
                    resolve({ success: 1, file: { url: evt.data.url } })
                  }
                }
                window.addEventListener('message', handler)
              }
              reader.readAsDataURL(file)
            })
          },
          uploadByUrl: async (url) => ({ success: 1, file: { url } }),
        },
      },
    },
    inlineCode: { class: InlineCode },
    delimiter: { class: Delimiter },
    ...(ToggleBlock ? { toggle: { class: ToggleBlock } } : {}),
  }

  editor = new EditorJS({
    holder:      'editor-container',
    tools,
    data:        initialContent ?? { blocks: [] },
    placeholder: 'Escreva algo ou pressione "/" para inserir um bloco...',
    autofocus:   true,
    inlineToolbar: ['bold', 'italic', 'underline', 'inlineCode', 'link'],

    onChange: () => {
      // Debounce de 2 segundos
      clearTimeout(saveTimer)
      saveTimer = setTimeout(doSave, 2000)
    },

    onReady: () => {
      applyTheme()
      sendToParent('ready')
    },
  })
}

// ── Salvar conteúdo ───────────────────────────────────────────────────────────

async function doSave() {
  if (!editor) return
  try {
    const content = await editor.save()
    sendToParent('save', { content })
  } catch (e) {
    sendToParent('error', { message: e.message })
  }
}

// ── Tema ──────────────────────────────────────────────────────────────────────

function applyTheme() {
  document.documentElement.classList.toggle('dark', isDark)
}

// ── Expor API global (usada pelo HTML inline) ─────────────────────────────────

window.OgmaEditor = { initEditor, doSave, applyTheme }
