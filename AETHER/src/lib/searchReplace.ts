// ============================================================
//  AETHER — Extensão TipTap: Localizar e Substituir
//  Plugin ProseMirror que decora ocorrências do termo buscado.
//  O estado (matches, current) vive no plugin; React lê via
//  searchKey.getState(editor.state) após cada dispatch.
// ============================================================

import { Extension } from '@tiptap/core'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node } from '@tiptap/pm/model'
import { Fragment } from '@tiptap/pm/model'

export interface SearchMatch {
  from: number
  to: number
}

export interface SearchPluginState {
  term: string
  caseSensitive: boolean
  matches: SearchMatch[]
  current: number
}

export const searchKey = new PluginKey<SearchPluginState>('searchReplace')

export function findMatches(
  doc: Node,
  term: string,
  caseSensitive: boolean,
): SearchMatch[] {
  if (!term) return []
  const results: SearchMatch[] = []
  const needle = caseSensitive ? term : term.toLowerCase()

  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return
    const hay = caseSensitive ? node.text : node.text.toLowerCase()
    let i = 0
    while (true) {
      const idx = hay.indexOf(needle, i)
      if (idx === -1) break
      results.push({ from: pos + idx, to: pos + idx + term.length })
      i = idx + 1
    }
  })

  return results
}

export const SearchReplace = Extension.create({
  name: 'searchReplace',

  addProseMirrorPlugins() {
    return [
      new Plugin<SearchPluginState>({
        key: searchKey,
        state: {
          init(): SearchPluginState {
            return { term: '', caseSensitive: false, matches: [], current: -1 }
          },
          apply(tr, prev): SearchPluginState {
            const meta = tr.getMeta(searchKey) as SearchPluginState | undefined
            if (meta !== undefined) return meta
            if (tr.docChanged && prev.term) {
              const matches = findMatches(tr.doc, prev.term, prev.caseSensitive)
              const current =
                matches.length > 0
                  ? Math.min(Math.max(prev.current, 0), matches.length - 1)
                  : -1
              return { ...prev, matches, current }
            }
            return prev
          },
        },
        props: {
          decorations(state) {
            const s = searchKey.getState(state)
            if (!s || !s.term || s.matches.length === 0) return DecorationSet.empty
            const decos = s.matches.map((m, i) =>
              Decoration.inline(m.from, m.to, {
                class:
                  i === s.current
                    ? 'search-highlight search-highlight-current'
                    : 'search-highlight',
              })
            )
            return DecorationSet.create(state.doc, decos)
          },
        },
      }),
    ]
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addCommands(): any {
    return {
      setSearchTerm:
        (term: string, caseSensitive = false) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ tr, dispatch, state }: any) => {
          const matches = findMatches(state.doc, term, caseSensitive)
          const current = matches.length > 0 ? 0 : -1
          const newState: SearchPluginState = { term, caseSensitive, matches, current }
          tr.setMeta(searchKey, newState)
          if (dispatch) dispatch(tr)
          return true
        },

      goToMatch:
        (index: number) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ tr, dispatch, state }: any) => {
          const s = searchKey.getState(state) as SearchPluginState | undefined
          if (!s || s.matches.length === 0) return false
          const i = ((index % s.matches.length) + s.matches.length) % s.matches.length
          const match = s.matches[i]
          const newState: SearchPluginState = { ...s, current: i }
          tr.setMeta(searchKey, newState)
          const sel = TextSelection.create(tr.doc, match.from, match.to)
          tr.setSelection(sel).scrollIntoView()
          if (dispatch) dispatch(tr)
          return true
        },

      replaceCurrentMatch:
        (replacement: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ tr, dispatch, state }: any) => {
          const s = searchKey.getState(state) as SearchPluginState | undefined
          if (!s || s.current === -1 || s.matches.length === 0) return false
          const match = s.matches[s.current]
          const content = replacement
            ? Fragment.from(state.schema.text(replacement))
            : Fragment.empty
          tr.replaceWith(match.from, match.to, content)
          if (dispatch) dispatch(tr)
          return true
        },

      replaceAllMatches:
        (replacement: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ tr, dispatch, state }: any) => {
          const s = searchKey.getState(state) as SearchPluginState | undefined
          if (!s || s.matches.length === 0) return false
          // Do último para o primeiro para preservar offsets
          const sorted = [...s.matches].sort((a, b) => b.from - a.from)
          for (const match of sorted) {
            const content = replacement
              ? Fragment.from(state.schema.text(replacement))
              : Fragment.empty
            tr.replaceWith(match.from, match.to, content)
          }
          if (dispatch) dispatch(tr)
          return true
        },

      clearSearch:
        () =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ tr, dispatch }: any) => {
          const empty: SearchPluginState = {
            term: '',
            caseSensitive: false,
            matches: [],
            current: -1,
          }
          tr.setMeta(searchKey, empty)
          if (dispatch) dispatch(tr)
          return true
        },
    }
  },
})
