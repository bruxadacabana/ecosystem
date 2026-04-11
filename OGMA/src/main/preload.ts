import { contextBridge, ipcRenderer } from 'electron'
import type { AppSettings } from './settings'

const api = (channel: string, data?: any) => ipcRenderer.invoke(channel, data)

contextBridge.exposeInMainWorld('db', {
  workspace: {
    get:    ()       => api('workspace:get'),
    update: (d: any) => api('workspace:update', d),
    updateSettings: (d: any) => api('workspace:updateSettings', d),
  },
  projects: {
    list:          ()            => api('projects:list'),
    create:        (d: any)      => api('projects:create', d),
    update:        (d: any)      => api('projects:update', d),
    delete:        (id: number)  => api('projects:delete', { id }),
    getProperties: (id: number)  => api('projects:getProperties', { id }),
    getViews:      (id: number)  => api('projects:getViews', { id }),
  },
  dashboard: {
    stats: () => api('dashboard:stats'),
  },
  calendar: {
    pagesForMonth: (year: number, month: number) => api('calendar:pagesForMonth', { year, month }),
  },
  pages: {
    list:         (project_id: number) => api('pages:list',         { project_id }),
    get:          (id: number)         => api('pages:get',          { id }),
    create:       (d: any)             => api('pages:create',       d),
    update:       (d: any)             => api('pages:update',       d),
    delete:       (id: number)         => api('pages:delete',       { id }),
    reorder:      (items: any[])       => api('pages:reorder',      items),
    setPropValue: (d: any)             => api('pages:setPropValue', d),
    search:      (query: string, limit?: number) => api('pages:search',      { query, limit: limit ?? 20 }),
    reindexAll:  ()                              => api('pages:reindexAll',  {}),
    listRecent:  (limit?: number)                => api('pages:listRecent',  { limit: limit ?? 8 }),
    listUpcoming:(days?: number)                 => api('pages:listUpcoming',{ days:  days  ?? 14 }),
  },
  properties: {
    create:         (d: any)                                    => api('properties:create',         d),
    update:         (d: any)                                    => api('properties:update',         d),
    delete:         (id: number)                                => api('properties:delete',         { id }),
    reorder:        (items: any[])                              => api('properties:reorder',        items),
    getOptions:     (id: number)                                => api('properties:getOptions',     { id }),
    createOption:   (d: any)                                    => api('properties:createOption',   d),
    updateOption:   (d: any)                                    => api('properties:updateOption',   d),
    deleteOption:   (id: number)                                => api('properties:deleteOption',   { id }),
    reorderOptions: (items: any[])                              => api('properties:reorderOptions', items),
  },
  views: {
    create:     (d: any)       => api('views:create',     d),
    update:     (d: any)       => api('views:update',     d),
    delete:     (id: number)   => api('views:delete',     { id }),
    setDefault: (id: number)   => api('views:setDefault', { id }),
  },
  tags: {
    list:        ()                                   => api('tags:list',        {}),
    create:      (name: string, color?: string)        => api('tags:create',      { name, color }),
    delete:      (id: number)                          => api('tags:delete',      { id }),
    listForPage: (page_id: number)                     => api('tags:listForPage', { page_id }),
    assign:      (page_id: number, tag_id: number)     => api('tags:assign',      { page_id, tag_id }),
    remove:      (page_id: number, tag_id: number)     => api('tags:remove',      { page_id, tag_id }),
  },
  prerequisites: {
    list:           (page_id: number)                            => api('prerequisites:list',           { page_id }),
    listDependents: (page_id: number)                            => api('prerequisites:listDependents', { page_id }),
    add:            (page_id: number, prerequisite_id: number)   => api('prerequisites:add',            { page_id, prerequisite_id }),
    remove:         (page_id: number, prerequisite_id: number)   => api('prerequisites:remove',         { page_id, prerequisite_id }),
  },
  backlinks: {
    list:        (page_id: number)                              => api('backlinks:list',        { page_id }),
    listOutgoing:(page_id: number)                              => api('backlinks:listOutgoing',{ page_id }),
    add:         (source_page_id: number, target_page_id: number) => api('backlinks:add',      { source_page_id, target_page_id }),
    remove:      (source_page_id: number, target_page_id: number) => api('backlinks:remove',   { source_page_id, target_page_id }),
  },
  readings: {
    list:   ()       => api('readings:list',   {}),
    create: (d: any) => api('readings:create', d),
    update: (d: any) => api('readings:update', d),
    delete: (id: number) => api('readings:delete', { id }),
  },
  readingSessions: {
    list:   (reading_id: number) => api('reading_sessions:list',   { reading_id }),
    create: (d: any)             => api('reading_sessions:create', d),
    delete: (id: number)         => api('reading_sessions:delete', { id }),
  },
  readingNotes: {
    list:   (reading_id: number) => api('reading_notes:list',   { reading_id }),
    create: (d: any)             => api('reading_notes:create', d),
    delete: (id: number)         => api('reading_notes:delete', { id }),
  },
  readingQuotes: {
    list:   (reading_id: number) => api('reading_quotes:list',   { reading_id }),
    create: (d: any)             => api('reading_quotes:create', d),
    delete: (id: number)         => api('reading_quotes:delete', { id }),
  },
  readingLinks: {
    list:           (reading_id: number)                  => api('reading_links:list',           { reading_id }),
    add:            (reading_id: number, page_id: number) => api('reading_links:add',            { reading_id, page_id }),
    remove:         (reading_id: number, page_id: number) => api('reading_links:remove',         { reading_id, page_id }),
    listForProject: (project_id: number)                  => api('reading_links:listForProject', { project_id }),
  },
  readingGoals: {
    get:      (workspace_id: number, year: number)                    => api('reading:goals:get',      { workspace_id, year }),
    set:      (workspace_id: number, year: number, target: number)    => api('reading:goals:set',      { workspace_id, year, target }),
    progress: (workspace_id: number, year: number)                    => api('reading:goals:progress', { workspace_id, year }),
  },
  resources: {
    list:      ()                                           => api('resources:list',   {}),
    create:    (d: any)                                     => api('resources:create', d),
    update:    (d: any)                                     => api('resources:update', d),
    delete:    (id: number)                                 => api('resources:delete', { id }),
    fetchMeta:  (type: string, query: string, url?: string) => ipcRenderer.invoke('resources:fetchMeta',  { type, query, url }),
    searchMeta: (type: string, query: string)              => ipcRenderer.invoke('resources:searchMeta', { type, query }),
  },
  resourcePages: {
    listForResource: (resource_id: number)               => api('resource_pages:listForResource', { resource_id }),
    listForPage:     (page_id: number)                   => api('resource_pages:listForPage',     { page_id }),
    add:             (resource_id: number, page_id: number) => api('resource_pages:add',          { resource_id, page_id }),
    remove:          (resource_id: number, page_id: number) => api('resource_pages:remove',       { resource_id, page_id }),
  },
  config: {
    get:    (key: string)                => api('config:get',    { key }),
    set:    (key: string, value: string) => api('config:set',    { key, value }),
    getAll: ()                           => api('config:getAll'),
  },
  log: {
    renderer: (entry: any) => api('log:renderer', entry),
  },
  uploads: {
    saveImage: (d: any) => api('uploads:saveImage', d),
  },
  sync: {
    now: () => api('db:sync'),
  },
  events: {
    listForMonth:   (year: number, month: number) => api('events:listForMonth',   { year, month }),
    listForPage:    (page_id: number)              => api('events:listForPage',    { page_id }),
    listForProject: (project_id: number)           => api('events:listForProject', { project_id }),
    listUpcoming:   (days?: number)                => api('events:listUpcoming',   { days: days ?? 14 }),
    create:         (d: any)                       => api('events:create',         d),
    update:         (d: any)                       => api('events:update',         d),
    delete:         (id: number)                   => api('events:delete',         { id }),
  },
  reminders: {
    list:           (include_dismissed?: boolean)                 => api('reminders:list',           { include_dismissed: include_dismissed ?? false }),
    listForProject: (project_id: number, include_dismissed?: boolean) => api('reminders:listForProject', { project_id, include_dismissed: include_dismissed ?? false }),
    create:         (d: any)                                      => api('reminders:create',         d),
    dismiss:        (id: number)                                  => api('reminders:dismiss',        { id }),
    delete:         (id: number)                                  => api('reminders:delete',         { id }),
  },
  dashboardExtra: {
    projectsProgress: () => api('dashboard:projectsProgress'),
    randomQuote:      () => api('dashboard:randomQuote'),
  },
  analytics: {
    global:     () => api('analytics:global'),
    todayFocus: () => api('analytics:todayFocus'),
    project:    (project_id: number) => api('analytics:project', { project_id }),
  },
  planner: {
    listTasks:     (project_id: number)               => api('planner:listTasks',     { project_id }),
    createTask:    (d: any)                           => api('planner:createTask',    d),
    updateTask:    (d: any)                           => api('planner:updateTask',    d),
    deleteTask:    (id: number)                       => api('planner:deleteTask',    { id }),
    listBlocks:    (task_id: number)                  => api('planner:listBlocks',    { task_id }),
    logBlock:      (id: number, logged_hours: number) => api('planner:logBlock',      { id, logged_hours }),
    updateBlock:   (d: any)                           => api('planner:updateBlock',   d),
    schedule:      (project_id: number)               => api('planner:schedule',      { project_id }),
    rescheduleAll: ()                                 => api('planner:rescheduleAll', {}),
    todayBlocks:   (dateStr?: string)                 => api('planner:todayBlocks',   dateStr),
    listAllTasks:  (opts?: { include_completed?: boolean }) => api('planner:listAllTasks', opts ?? {}),
  },
  time: {
    list:   (d: { project_id: number }) => api('time:list',   d),
    create: (d: any)                    => api('time:create', d),
    delete: (d: { id: number })         => api('time:delete', d),
    todayBlocks:      (dateStr?: string) => api('planner:todayBlocks', dateStr),
    logBlock:         (block_id: number, hours: number) => api('planner:logBlock', { block_id, hours }),
    logWork:          (data: any) => api('planner:logWork', data), // <--- O NOVO CALCULADOR
    listBlocks:       (task_id: number) => api('planner:listBlocks', { task_id }),
  },
})


contextBridge.exposeInMainWorld('appSettings', {
  getAll: ():                                          Promise<AppSettings>    => ipcRenderer.invoke('appSettings:getAll'),
  get:    <K extends keyof AppSettings>(key: K):       Promise<AppSettings[K]> => ipcRenderer.invoke('appSettings:get', { key }),
  set:    <K extends keyof AppSettings>(key: K, value: AppSettings[K]): Promise<void> =>
    ipcRenderer.invoke('appSettings:set', { key, value }),
})

contextBridge.exposeInMainWorld('electron', {
  ipcRenderer: {
    on: (channel: string, listener: (...args: any[]) => void) => {
      const subscription = (_event: any, ...args: any[]) => listener(...args)
      ipcRenderer.on(channel, subscription)
      // Retorna a função de limpeza para o React usar no useEffect
      return () => {
        ipcRenderer.removeListener(channel, subscription)
      }
    }
  }
})