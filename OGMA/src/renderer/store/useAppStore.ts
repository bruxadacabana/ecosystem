import { create } from 'zustand'
import { Project, Page, Workspace, ProjectProperty, ProjectView } from '../types'
import { AppError, Result, ok, err, fromIpc, makeError, extractMessage } from '../types/errors'
import { createLogger } from '../utils/logger'

const log = createLogger('store')

// ── Toast ─────────────────────────────────────────────────────────────────────

export interface Toast {
  id:      string
  kind:    'error' | 'success' | 'warning' | 'info'
  title:   string
  detail?: string
  ttl?:    number
}

let _toastSeq = 0
function nextId() { return `t${Date.now()}_${_toastSeq++}` }

// ── Estado ────────────────────────────────────────────────────────────────────

interface AppState {
  // ── Dados ─────────────────────────────────────────────────────────────────
  workspace:          Workspace | null
  projects:           Project[]
  activeProjectId:    number | null
  activeProject:      Project | null
  pages:              Page[]
  projectProperties:  ProjectProperty[]
  projectViews:       ProjectView[]
  activeViewId:       number | null

  // ── UI ────────────────────────────────────────────────────────────────────
  dark:        boolean
  accentColor: string
  loading:     boolean
  toasts:      Toast[]
  // ── Actions UI ────────────────────────────────────────────────────────────
  setDark:        (dark: boolean) => void
  setAccentColor: (color: string) => void
  setLoading:     (v: boolean) => void
  setActiveView:  (id: number | null) => void
  pushToast:      (toast: Omit<Toast, 'id'>) => void
  dismissToast:   (id: string) => void

  // ── Loads (void — erros surfaced via toast) ───────────────────────────────
  loadWorkspace:  () => Promise<void>
  loadProjects:   () => Promise<void>
  selectProject:  (id: number | null) => void
  loadPages:      (projectId: number) => Promise<void>
  loadProperties: (projectId: number) => Promise<void>
  loadViews:      (projectId: number) => Promise<void>

  // ── Mutações — Result<T, AppError> para feedback inline nos componentes ───
  createProject: (input: Omit<Project, 'id' | 'created_at' | 'updated_at'>) => Promise<Result<Project, AppError>>
  updateProject: (data: Partial<Project> & { id: number })                   => Promise<Result<Project, AppError>>
  deleteProject: (id: number)                                                 => Promise<Result<void, AppError>>
  updatePage:    (data: Partial<Page>    & { id: number })                   => Promise<Result<Page, AppError>>
}

const db = () => (window as any).db

// ── Helper: toast de erro + log ───────────────────────────────────────────────

function toastError(
  pushToast: AppState['pushToast'],
  title: string,
  error: AppError,
) {
  log.error(error.context ?? 'store', { error: error.message, code: error.code })
  pushToast({ kind: 'error', title, detail: error.message })
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useAppStore = create<AppState>((set, get) => ({
  workspace:         null,
  projects:          [],
  activeProjectId:   null,
  activeProject:     null,
  pages:             [],
  projectProperties: [],
  projectViews:      [],
  activeViewId:      null,
  dark:              false,
  accentColor:       '#b8860b',
  loading:           false,
  toasts:            [],

  // ── UI ────────────────────────────────────────────────────────────────────

  setDark:        (dark)  => set({ dark }),
  setAccentColor: (color) => set({ accentColor: color }),
  setLoading:     (v)     => set({ loading: v }),
  setActiveView:  (id)    => set({ activeViewId: id }),

  pushToast: (toast) =>
    set(s => ({ toasts: [...s.toasts, { ...toast, id: nextId() }] })),

  dismissToast: (id) =>
    set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),

  // ── Loads ─────────────────────────────────────────────────────────────────

  loadWorkspace: async () => {
    const result = await fromIpc<Workspace>(() => db().workspace.get(), 'loadWorkspace')
    result.match(
      workspace => set({ workspace }),
      error     => toastError(get().pushToast, 'Workspace indisponível', error),
    )
  },

  loadProjects: async () => {
    const result = await fromIpc<Project[]>(() => db().projects.list(), 'loadProjects')
    result.match(
      projects => set({ projects }),
      error    => toastError(get().pushToast, 'Erro ao carregar projetos', error),
    )
  },

  selectProject: (id) => {
    const project = id ? get().projects.find(p => p.id === id) ?? null : null
    set({
      activeProjectId:   id,
      activeProject:     project,
      pages:             [],
      projectProperties: [],
      projectViews:      [],
      activeViewId:      null,
    })
    if (id) {
      get().loadPages(id)
      get().loadProperties(id)
      get().loadViews(id)
    }
  },

  loadPages: async (projectId) => {
    const result = await fromIpc<Page[]>(() => db().pages.list(projectId), 'loadPages')
    result.match(
      pages => set({ pages }),
      error => toastError(get().pushToast, 'Erro ao carregar páginas', error),
    )
  },

  loadProperties: async (projectId) => {
    const result = await fromIpc<ProjectProperty[]>(
      () => db().projects.getProperties(projectId), 'loadProperties',
    )
    result.match(
      projectProperties => set({ projectProperties }),
      error             => toastError(get().pushToast, 'Erro ao carregar propriedades', error),
    )
  },

  loadViews: async (projectId) => {
    const result = await fromIpc<ProjectView[]>(
      () => db().projects.getViews(projectId), 'loadViews',
    )
    result.match(
      views => {
        const defaultView = views.find(v => v.is_default) ?? views[0] ?? null
        set({ projectViews: views, activeViewId: defaultView?.id ?? null })
      },
      error => toastError(get().pushToast, 'Erro ao carregar vistas', error),
    )
  },

  // ── Mutações ──────────────────────────────────────────────────────────────

  createProject: async (input) => {
    const result = await fromIpc<Project>(() => db().projects.create(input), 'createProject')
    if (result.isOk()) {
      set(s => ({ projects: [...s.projects, result.value] }))
      log.info('createProject', { id: result.value.id, name: result.value.name })
    }
    return result
  },

  updateProject: async (data) => {
    const result = await fromIpc<Project>(() => db().projects.update(data), 'updateProject')
    if (result.isOk()) {
      set(s => ({
        projects:      s.projects.map(p => p.id === data.id ? result.value : p),
        activeProject: s.activeProjectId === data.id ? result.value : s.activeProject,
      }))
    }
    return result
  },

  deleteProject: async (id) => {
    const result = await fromIpc<unknown>(() => db().projects.delete(id), 'deleteProject')
    if (result.isOk()) {
      set(s => ({
        projects:        s.projects.filter(p => p.id !== id),
        activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
        activeProject:   s.activeProjectId === id ? null : s.activeProject,
      }))
      return ok(undefined)
    }
    return err(result.error)
  },

  updatePage: async (data) => {
    const result = await fromIpc<Page>(() => db().pages.update(data), 'updatePage')
    if (result.isOk()) {
      set(s => ({ pages: s.pages.map(p => p.id === data.id ? result.value : p) }))
    }
    return result
  },
}))
