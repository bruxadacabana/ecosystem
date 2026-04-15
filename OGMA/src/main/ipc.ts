import { ipcMain } from 'electron'
import https from 'https'
import http from 'http'
import { dbGet, dbAll, dbRun, getClient } from './database'
import { createLogger, RENDERER_LOG_CHANNEL } from './logger'
import { getSetting, setSetting, getAllSettings, AppSettings } from './settings'

const log   = createLogger('ipc')
const dbLog = createLogger('db')

// ── Classificação de erros ─────────────────────────────────────────────────────

type ErrorCode = 'DB_CONSTRAINT' | 'DB_WRITE' | 'DB_READ' | 'NOT_FOUND' | 'VALIDATION' | 'UNKNOWN'

function classifyError(err: Error): ErrorCode {
  const msg = (err.message ?? '').toLowerCase()
  if (msg.includes('unique') || msg.includes('constraint') || msg.includes('foreign key')) {
    return 'DB_CONSTRAINT'
  }
  if (msg.includes('no such') || msg.includes('not found')) return 'NOT_FOUND'
  if (msg.includes('readonly') || msg.includes('locked') || msg.includes('disk full')) {
    return 'DB_WRITE'
  }
  if (msg.includes('failed to fetch') || msg.includes('no rows')) return 'DB_READ'
  return 'UNKNOWN'
}

// ── Wrapper IPC ────────────────────────────────────────────────────────────────

const api = (channel: string, handler: (data: any) => Promise<any> | any) => {
  ipcMain.handle(channel, async (_event, data) => {
    try {
      return { ok: true, data: await handler(data) }
    } catch (err: any) {
      const errorCode = classifyError(err)
      log.error(`handler:${channel}`, { error: err.message, errorCode, data })
      return { ok: false, error: err.message, errorCode }
    }
  })
}

// ── Seed interno: propriedades e views padrão por tipo de projeto ──────────────

async function seedProjectProperties(projectId: number, projectType: string, subcategory?: string): Promise<Map<string, number>> {
  const propIds = new Map<string, number>()
  let order = 0

  const addProp = async (name: string, key: string, type: string, options?: [string, string | null][]) => {
    const r = await dbRun(
      `INSERT INTO project_properties (project_id, name, prop_key, prop_type, is_built_in, sort_order)
       VALUES (?, ?, ?, ?, 1, ?)`,
      projectId, name, key, type, order++
    )
    const propId = r.lastInsertRowid
    propIds.set(key, propId)
    if (options) {
      for (let i = 0; i < options.length; i++) {
        await dbRun(
          `INSERT INTO prop_options (property_id, label, color, sort_order) VALUES (?, ?, ?, ?)`,
          propId, options[i][0], options[i][1] ?? null, i
        )
      }
    }
  }

  const year = new Date().getFullYear()

  const schemas: Record<string, () => Promise<void>> = {
    academic: async () => {
      await addProp('Status', 'status', 'select', [
        ['Pendente', '#8B7355'], ['Cursando', '#b8860b'],
        ['Concluída', '#4A6741'], ['Trancada', '#8B3A2A'],
      ])
      if (subcategory === 'Autodidata') {
        await addProp('Ciclo', 'ciclo', 'select', [
          ['Ciclo 1', null], ['Ciclo 2', null], ['Ciclo 3', null],
          ['Ciclo 4', null], ['Ciclo 5', null],
        ])
      } else {
        await addProp('Trimestre', 'trimestre', 'select', [
          [`${year - 1}.1`, null], [`${year - 1}.2`, null], [`${year - 1}.3`, null], [`${year - 1}.4`, null],
          [`${year}.1`,     null], [`${year}.2`,     null], [`${year}.3`,     null], [`${year}.4`,     null],
          [`${year + 1}.1`, null], [`${year + 1}.2`, null], [`${year + 1}.3`, null], [`${year + 1}.4`, null],
        ])
      }
      await addProp('Área', 'area', 'multi_select', [
        ['Humanas', '#7A5C2E'], ['Exatas', '#2C5F8A'], ['Biológicas', '#4A6741'],
        ['Computação', '#4A3A7A'], ['Linguagens', '#6A4A2E'], ['Artes', '#8A2A5A'],
      ])
      await addProp('Nota',          'nota',         'number')
      await addProp('Créditos',      'creditos',     'number')
      await addProp('Carga Horária', 'carga_horaria','number')
      await addProp('Professor',     'professor',    'text')
      await addProp('Instituição',   'instituicao',  'text')
      await addProp('Código',        'codigo',       'text')
      await addProp('Data Início',   'data_inicio',  'date')
      await addProp('Data Fim',      'data_fim',     'date')
    },
    software: async () => {
      await addProp('Status', 'status', 'select', [
        ['Backlog', '#8B7355'], ['A Fazer', '#7A5C2E'],
        ['Em Andamento', '#b8860b'], ['Em Revisão', '#2C5F8A'],
        ['Concluído', '#4A6741'],
      ])
      await addProp('Prioridade', 'prioridade', 'select', [
        ['Baixa', '#4A6741'], ['Média', '#7A5C2E'],
        ['Alta', '#b8860b'], ['Urgente', '#8B3A2A'],
      ])
      await addProp('Tags',        'tags',        'multi_select')
      await addProp('Sprint',      'sprint',      'select')
      await addProp('Data Limite', 'data_limite', 'date')
      await addProp('Estimativa',  'estimativa',  'number')
    },
    health: async () => {
      await addProp('Status', 'status', 'select', [
        ['Não Iniciado', '#8B7355'], ['Em Andamento', '#b8860b'],
        ['Concluído', '#4A6741'], ['Abandonado', '#8B3A2A'],
      ])
      await addProp('Frequência', 'frequencia', 'select', [
        ['Diário', null], ['Semanal', null], ['Mensal', null], ['Pontual', null],
      ])
      await addProp('Data Início', 'data_inicio', 'date')
      await addProp('Meta',        'meta',        'text')
      await addProp('Progresso',   'progresso',   'number')
      await addProp('Tags',        'tags',        'multi_select')
    },
    writing: async () => {
      await addProp('Status', 'status', 'select', [
        ['Ideia', '#8B7355'], ['Em Progresso', '#b8860b'],
        ['Pausado', '#7A5C2E'], ['Concluído', '#4A6741'], ['Publicado', '#2C5F8A'],
      ])
      await addProp('Tags',        'tags',        'multi_select')
      await addProp('Data Limite', 'data_limite', 'date')
      await addProp('Prioridade', 'prioridade', 'select', [
        ['Baixa', '#4A6741'], ['Média', '#7A5C2E'], ['Alta', '#b8860b'],
      ])
    },
    research: async () => {
      await addProp('Status', 'status', 'select', [
        ['A Pesquisar', '#8B7355'], ['Em Andamento', '#b8860b'],
        ['Rascunho', '#7A5C2E'], ['Revisão', '#2C5F8A'], ['Concluído', '#4A6741'],
      ])
      await addProp('Fonte', 'fonte', 'text')
      await addProp('Data',  'data',  'date')
      await addProp('Tags',  'tags',  'multi_select')
      await addProp('Área',  'area',  'multi_select')
    },
    hobby: async () => {
      await addProp('Status', 'status', 'select', [
        ['Quero Aprender', '#8B7355'], ['Em Andamento', '#b8860b'],
        ['Pausado', '#7A5C2E'], ['Concluído', '#4A6741'],
      ])
      await addProp('Tags',        'tags',        'multi_select')
      await addProp('Data Início', 'data_inicio', 'date')
      await addProp('Notas',       'notas',       'text')
    },
    idea: async () => {
      await addProp('Status', 'status', 'select', [
        ['Bruta', '#8B7355'], ['Refinando', '#b8860b'],
        ['Viável', '#4A6741'], ['Arquivada', '#6B4F72'],
      ])
      await addProp('Urgência', 'urgencia', 'select', [
        ['Baixa', '#4A6741'], ['Média', '#7A5C2E'], ['Alta', '#b8860b'],
      ])
      await addProp('Tags',         'tags',         'multi_select')
      await addProp('Data Captura', 'data_captura', 'date')
      await addProp('Notas',        'notas',        'text')
    },
    custom: async () => {
      await addProp('Status', 'status', 'select', [
        ['A Fazer', '#8B7355'], ['Em Andamento', '#b8860b'], ['Concluído', '#4A6741'],
      ])
      await addProp('Tags', 'tags', 'multi_select')
      await addProp('Data', 'data', 'date')
    },
  }

  await (schemas[projectType] ?? schemas.custom)()
  return propIds
}

async function seedProjectViews(
  projectId: number,
  projectType: string,
  propIds: Map<string, number>,
  subcategory?: string,
): Promise<void> {
  type ViewDef = [string, string, string | null, string | null]

  const academicGroupProp = subcategory === 'Autodidata' ? 'ciclo' : 'trimestre'

  const viewConfigs: Record<string, ViewDef[]> = {
    academic: [
      ['Progresso',  'progress', academicGroupProp, null      ],
      ['Tabela',     'table',    null,        null      ],
      ['Kanban',     'kanban',   'status',    null      ],
      ['Calendário', 'calendar', null,        'data_fim'],
    ],
    software: [
      ['Kanban',     'kanban',   'status', null         ],
      ['Tabela',     'table',    null,     null         ],
      ['Calendário', 'calendar', null,     'data_limite'],
    ],
    health: [
      ['Lista',      'list',     null,     null         ],
      ['Calendário', 'calendar', null,     'data_inicio'],
      ['Tabela',     'table',    null,     null         ],
    ],
    writing: [
      ['Kanban', 'kanban', 'status', null],
      ['Tabela', 'table',  null,     null],
    ],
    research: [
      ['Tabela', 'table', null, null],
      ['Lista',  'list',  null, null],
    ],
    hobby: [
      ['Lista',  'list',  null, null],
      ['Tabela', 'table', null, null],
    ],
    idea: [
      ['Lista',  'list',   null,     null],
      ['Kanban', 'kanban', 'status', null],
      ['Tabela', 'table',  null,     null],
    ],
    custom: [
      ['Tabela', 'table',  null,     null],
      ['Kanban', 'kanban', 'status', null],
    ],
  }

  const configs: ViewDef[] = viewConfigs[projectType] ?? viewConfigs.custom

  for (let i = 0; i < configs.length; i++) {
    const [name, type, groupByKey, dateKey] = configs[i]
    const groupByPropId = groupByKey ? (propIds.get(groupByKey) ?? null) : null
    const datePropId    = dateKey    ? (propIds.get(dateKey)    ?? null) : null
    const isDefault     = i === 0 ? 1 : 0
    await dbRun(
      `INSERT INTO project_views
        (project_id, name, view_type, group_by_property_id, date_property_id, is_default, sort_order)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      projectId, name, type, groupByPropId, datePropId, isDefault, i
    )
  }
}

// ── FTS5: extração de texto do body_json do Editor.js ────────────────────────

function extractBodyText(bodyJson: string | null | undefined): string {
  if (!bodyJson) return ''
  try {
    const data = JSON.parse(bodyJson)
    return (data.blocks ?? []).map((b: any) => {
      const d = b.data ?? {}
      if (typeof d.text === 'string')   return d.text.replace(/<[^>]*>/g, ' ')
      if (Array.isArray(d.items))       return d.items.map((it: any) =>
        typeof it === 'string' ? it : (it.content ?? '')
      ).join(' ')
      if (typeof d.caption === 'string') return d.caption
      return ''
    }).filter(Boolean).join(' ')
  } catch { return '' }
}

async function ftsUpsert(pageId: number, projectId: number, title: string, body: string) {
  await dbRun(`DELETE FROM search_index WHERE entity_type = 'page' AND entity_id = ?`, pageId)
  await dbRun(
    `INSERT INTO search_index (entity_type, entity_id, project_id, title, body) VALUES ('page', ?, ?, ?, ?)`,
    pageId, projectId, title, body
  )
}

// ── Helpers de fetch para metadados ───────────────────────────────────────────

function fetchJson(url: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http
    const req = lib.get(url, { headers: { 'User-Agent': 'OGMA/1.0 (metadata-fetcher)' } }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        fetchJson(res.headers.location).then(resolve).catch(reject)
        return
      }
      let data = ''
      res.on('data', (c: any) => { data += c })
      res.on('end', () => {
        try { resolve(JSON.parse(data)) } catch { reject(new Error('JSON inválido')) }
      })
    })
    req.on('error', reject)
    req.setTimeout(8000, () => { req.destroy(); reject(new Error('Timeout')) })
  })
}

function fetchHtml(url: string, depth = 0): Promise<string> {
  return new Promise((resolve, reject) => {
    if (depth > 3) { reject(new Error('Too many redirects')); return }
    const lib = url.startsWith('https') ? https : http
    const req = lib.get(url, { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; OGMA/1.0)' } }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        fetchHtml(res.headers.location, depth + 1).then(resolve).catch(reject)
        return
      }
      let data = ''
      res.on('data', (c: any) => { data += c })
      res.on('end', () => resolve(data))
    })
    req.on('error', reject)
    req.setTimeout(8000, () => { req.destroy(); reject(new Error('Timeout')) })
  })
}

function parseOgTags(html: string): Record<string, string> {
  const m: Record<string, string> = {}
  const og = /<meta[^>]+property=["']og:([^"']+)["'][^>]+content=["']([^"']*)["'][^>]*>/gi
  let r
  while ((r = og.exec(html)) !== null) m[r[1]] = r[2]
  const tw = /<meta[^>]+name=["']twitter:([^"']+)["'][^>]+content=["']([^"']*)["'][^>]*>/gi
  while ((r = tw.exec(html)) !== null) if (!m[r[1]]) m[r[1]] = r[2]
  const titleM = html.match(/<title[^>]*>([^<]+)<\/title>/i)
  if (titleM) m['page_title'] = titleM[1].trim()
  const descM = html.match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)["']/i)
  if (descM && !m['description']) m['description'] = descM[1]
  return m
}

async function fetchMetadata(type: string, query: string, url?: string): Promise<Record<string, any>> {
  try {
    if (type === 'livro') {
      const isISBN = /^[\d -]{9,17}$/.test(query)
      const encoded = encodeURIComponent(query.replace(/[-\s]/g, ''))
      if (isISBN) {
        const data = await fetchJson(`https://openlibrary.org/isbn/${encoded}.json`)
        if (data?.title) {
          return {
            title:     data.title,
            publisher: data.publishers?.join(', '),
            year:      data.publish_date ? parseInt(data.publish_date) || undefined : undefined,
            pages:     data.number_of_pages,
            isbn:      encoded,
          }
        }
      }
      const olFields = 'key,title,author_name,first_publish_year,number_of_pages_median,isbn,publisher,language,cover_i'
      const data = await fetchJson(`https://openlibrary.org/search.json?title=${encodeURIComponent(query)}&limit=1&fields=${olFields}`)
      const doc = data?.docs?.[0]
      if (!doc) return {}
      return {
        title:       doc.title,
        author:      doc.author_name?.join(', ') ?? null,
        year:        doc.first_publish_year ?? null,
        pages:       doc.number_of_pages_median ?? null,
        isbn:        doc.isbn?.[0] ?? null,
        publisher:   doc.publisher?.[0] ?? null,
        language:    doc.language?.[0] ?? null,
        cover_url:   doc.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg` : null,
        cover_url_m: doc.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg` : null,
      }
    }

    if (type === 'artigo') {
      const isDOI = /^10\.\d{4,}\//.test(query)
      if (isDOI) {
        const data = await fetchJson(`https://api.crossref.org/works/${encodeURIComponent(query)}`)
        const w = data?.message
        if (w) return {
          title:   w.title?.[0],
          authors: w.author?.map((a: any) => `${a.given ?? ''} ${a.family ?? ''}`.trim()).join(', '),
          journal: w['container-title']?.[0],
          year:    w.published?.['date-parts']?.[0]?.[0],
          doi:     w.DOI,
          volume:  w.volume,
          issue:   w.issue,
        }
      }
      const data = await fetchJson(`https://api.crossref.org/works?query=${encodeURIComponent(query)}&rows=1`)
      const w = data?.message?.items?.[0]
      if (!w) return {}
      return {
        title:   w.title?.[0],
        authors: w.author?.map((a: any) => `${a.given ?? ''} ${a.family ?? ''}`.trim()).join(', '),
        journal: w['container-title']?.[0],
        year:    w.published?.['date-parts']?.[0]?.[0],
        doi:     w.DOI,
        volume:  w.volume,
        issue:   w.issue,
      }
    }

    if (type === 'video' && url) {
      if (url.includes('youtube.com') || url.includes('youtu.be')) {
        const data = await fetchJson(`https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`)
        return { title: data.title, channel: data.author_name, thumbnail_url: data.thumbnail_url, platform: 'YouTube' }
      }
    }

    if (url) {
      const html = await fetchHtml(url)
      const tags = parseOgTags(html)
      let domain = ''
      try { domain = new URL(url).hostname } catch {}
      return {
        title:       tags.title || tags.page_title,
        description: tags.description || tags['description'],
        thumbnail:   tags.image,
        domain,
      }
    }
  } catch (e: any) {
    log.warn('fetchMetadata error', e?.message)
  }
  return {}
}

// ── Planejador: funções auxiliares ────────────────────────────────────────────

async function getDailyCapacity(): Promise<number> {
  const row = await dbGet(`SELECT value FROM settings WHERE key = 'planner_daily_hours'`)
  return row ? parseFloat(row.value) || 4 : 4
}

async function getSkipWeekends(): Promise<boolean> {
  const row = await dbGet(`SELECT value FROM settings WHERE key = 'planner_skip_weekends'`)
  return row?.value === '1'
}

async function getDailyCapacityPerDay(): Promise<Record<number, number> | null> {
  const row = await dbGet(`SELECT value FROM settings WHERE key = 'planner_daily_hours_per_day'`)
  if (!row?.value) return null
  try { return JSON.parse(row.value) } catch { return null }
}

// 1. O NOVO ALGORITMO GLOBAL
async function scheduleGlobalTasks(): Promise<void> {
  const dailyCap     = await getDailyCapacity()
  const perDayMap    = await getDailyCapacityPerDay()
  const skipWeekends = await getSkipWeekends()
  const today        = new Date().toISOString().slice(0, 10)

  // Inclui tarefas 'overdue' — tarefas atrasadas têm urgência máxima (0) na ordenação
  const tasks = await dbAll(`
    SELECT pt.*,
      COALESCE((
        SELECT SUM(wb.logged_hours) FROM work_blocks wb
        WHERE wb.task_id = pt.id AND wb.status = 'done'
      ), 0) AS done_hours
    FROM planned_tasks pt
    WHERE pt.status IN ('pending','in_progress','overdue')
    ORDER BY
      CASE
        WHEN pt.due_date < date('now')                 THEN 0
        WHEN COALESCE(pt.priority,'medium') = 'urgent' THEN 1
        WHEN COALESCE(pt.priority,'medium') = 'high'   THEN 2
        WHEN COALESCE(pt.priority,'medium') = 'medium' THEN 3
        ELSE 4
      END ASC,
      pt.due_date ASC
  `)

  if (tasks.length === 0) return

  const c = await getClient()

  // Limpa o horizonte: deleta todos os blocos agendados no futuro para recalcular
  await c.execute({
    sql:  `DELETE FROM work_blocks WHERE date >= ? AND status = 'scheduled'`,
    args: [today],
  })

  const loadMap = new Map<string, number>()
  const inserts: { sql: string; args: any[] }[] = []

  for (const task of tasks) {
    const remaining = Math.max(0, task.estimated_hours - task.done_hours)
    if (remaining <= 0) continue

    const due   = task.due_date.slice(0, 10)
    const dates: string[] = []
    let cur = new Date(today + 'T12:00:00')
    const dueDate = new Date(due + 'T12:00:00')

    while (cur <= dueDate) {
      const dow = cur.getDay() // 0=Sun, 6=Sat
      // Com mapa por dia: inclui o dia apenas se capacidade > 0
      // Sem mapa: aplica regra de skipWeekends
      const dayOk = perDayMap !== null
        ? ((perDayMap[dow] ?? dailyCap) > 0)
        : (!skipWeekends || (dow !== 0 && dow !== 6))
      if (dayOk) dates.push(cur.toISOString().slice(0, 10))
      cur = new Date(cur.getTime() + 86400000)
    }

    if (dates.length === 0) {
      // Tarefa atrasada: distribuir a partir de hoje (horizonte de 30 dias)
      let d = new Date(today + 'T12:00:00')
      const horizon = new Date(d.getTime() + 30 * 86400000)
      while (d <= horizon) {
        const dow = d.getDay()
        const dayOk = perDayMap !== null
          ? ((perDayMap[dow] ?? dailyCap) > 0)
          : (!skipWeekends || (dow !== 0 && dow !== 6))
        if (dayOk) dates.push(d.toISOString().slice(0, 10))
        d = new Date(d.getTime() + 86400000)
      }
      if (dates.length === 0) dates.push(today) // fallback absoluto
    }

    let hoursLeft = remaining
    for (const date of dates) {
      if (hoursLeft <= 0) break
      const dow       = new Date(date + 'T12:00:00').getDay()
      const cap       = perDayMap !== null ? (perDayMap[dow] ?? dailyCap) : dailyCap
      const load      = loadMap.get(date) ?? 0
      const available = Math.max(0, cap - load)
      if (available <= 0) continue

      const h = Math.min(hoursLeft, available)
      inserts.push({
        sql:  `INSERT INTO work_blocks (task_id, date, planned_hours, logged_hours, status) VALUES (?, ?, ?, 0, 'scheduled')`,
        args: [task.id, date, Math.round(h * 100) / 100],
      })
      loadMap.set(date, load + h)
      hoursLeft -= h
    }

    if (hoursLeft > 0.01) {
      const lastDate = dates[dates.length - 1]
      inserts.push({
        sql:  `INSERT INTO work_blocks (task_id, date, planned_hours, logged_hours, status) VALUES (?, ?, ?, 0, 'scheduled')`,
        args: [task.id, lastDate, Math.round(hoursLeft * 100) / 100],
      })
      loadMap.set(lastDate, (loadMap.get(lastDate) ?? 0) + hoursLeft)
    }
  }

  if (inserts.length > 0) {
    await c.batch(inserts, 'write')
  }
}

async function updateTaskStatus(taskId: number): Promise<void> {
  const task = await dbGet(`SELECT * FROM planned_tasks WHERE id = ?`, taskId)
  if (!task) return
  const row = await dbGet(
    `SELECT COALESCE(SUM(logged_hours),0) AS h FROM work_blocks WHERE task_id = ? AND status = 'done'`,
    taskId
  )
  const doneHours = row?.h ?? 0
  let newStatus = task.status
  if (doneHours >= task.estimated_hours)  newStatus = 'completed'
  else if (doneHours > 0)                 newStatus = 'in_progress'
  if (newStatus !== task.status) {
    await dbRun(`UPDATE planned_tasks SET status = ?, updated_at = datetime('now') WHERE id = ?`, newStatus, taskId)
    if (newStatus === 'completed') await maybeCreateSpacedReview(taskId)
  }
}

const REVIEW_INTERVALS = [1, 3, 7, 14, 30]

async function maybeCreateSpacedReview(taskId: number): Promise<void> {
  const task = await dbGet(`SELECT * FROM planned_tasks WHERE id = ?`, taskId)
  if (!task || task.spaced_review !== 1) return

  // Walk the parent chain to determine depth
  let depth = 0
  let cur = task
  while (cur.parent_task_id && depth < 10) {
    depth++
    const parent = await dbGet(`SELECT * FROM planned_tasks WHERE id = ?`, cur.parent_task_id)
    if (!parent) break
    cur = parent
  }
  if (depth >= REVIEW_INTERVALS.length) return

  const intervalDays = REVIEW_INTERVALS[depth]
  const base         = new Date(task.due_date + 'T12:00:00')
  base.setDate(base.getDate() + intervalDays)
  const nextDue      = base.toISOString().slice(0, 10)

  const r = await dbRun(`
    INSERT INTO planned_tasks
      (project_id, page_id, title, task_type, due_date, estimated_hours, status, priority, spaced_review, parent_task_id)
    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
  `,
    task.project_id, task.page_id ?? null,
    `[Rev ${intervalDays}d] ${task.title.replace(/^\[Rev \d+d\] /, '')}`,
    task.task_type, nextDue, task.estimated_hours,
    task.priority ?? 'medium', taskId
  )
  await scheduleGlobalTasks()
  log.info('spaced-review criada', { taskId, nextDue, depth, reviewId: r.lastInsertRowid })
}

// ── Geração de código académico ───────────────────────────────────────────────
const CODE_STOP_WORDS = new Set([
  'de','do','da','dos','das','e','em','com','a','o','as','os',
  'um','uma','para','por','ao','aos','no','na','nos','nas',
  'se','que','mas','ou','num','duma',
])
const ROMAN_NUMS: Record<string, number> = {
  'i':1,'ii':2,'iii':3,'iv':4,'v':5,'vi':6,'vii':7,'viii':8,'ix':9,
  'x':10,'xi':11,'xii':12,'xiii':13,'xiv':14,'xv':15,'xx':20,
}

function generateAcademicCode(title: string, existingCodes: string[]): string {
  const norm = title
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .trim()

  // Extract number from title (Arabic digits first, then Roman numerals)
  let titleNum: number | null = null
  const arabicMatch = norm.match(/\b(\d+)\b/)
  if (arabicMatch) {
    titleNum = parseInt(arabicMatch[1], 10)
  } else {
    for (const w of norm.split(/\s+/)) {
      if (ROMAN_NUMS[w] !== undefined) { titleNum = ROMAN_NUMS[w]; break }
    }
  }

  // Get meaningful words: non-stop-word, non-numeric, non-roman, length > 1
  const meaningful = norm
    .split(/\s+/)
    .filter(w => w.length > 1 && !CODE_STOP_WORDS.has(w) && !/^\d+$/.test(w) && ROMAN_NUMS[w] === undefined)

  // Generate prefix candidates (ordered by preference)
  const prefixes = generateCodePrefixes(meaningful)
  const suffix   = titleNum != null ? String(titleNum).padStart(3, '0') : '001'

  // Return first non-colliding code
  for (const prefix of prefixes) {
    const code = prefix + suffix
    if (!existingCodes.includes(code)) return code
  }

  // Last resort: increment suffix with the best prefix
  const best    = prefixes[0] ?? 'PAG'
  const pattern = new RegExp(`^${best}(\\d+)$`)
  const used    = existingCodes
    .map(c => c?.match(pattern)?.[1])
    .filter(Boolean).map(Number)
  const next = used.length > 0 ? Math.max(...used) + 1 : (titleNum ?? 1) + 1
  return best + String(next).padStart(3, '0')
}

function generateCodePrefixes(words: string[]): string[] {
  const raw: string[] = []

  if (words.length === 0) return ['PAG']

  if (words.length === 1) {
    const w = words[0]
    raw.push(w.slice(0, 3))                        // MOD, CAL, FUN
    raw.push(w.slice(1, 4))                        // ODU, ALU (chars 2-4)
    raw.push(w[0] + w.slice(-2))                   // MUO, CFO (first + last 2)
  } else if (words.length === 2) {
    const [a, b] = words
    raw.push(a.slice(0, 2) + b[0])                 // FU+C=FUC, FU+E=FUE
    raw.push(a[0] + b.slice(0, 2))                 // F+CI=FCI, F+EA=FEA
    raw.push(a[0] + b[0] + a[1])                   // F+C+U=FCU
    raw.push(a.slice(0, 3))                        // FUN (fallback word1 first 3)
    raw.push(b.slice(0, 3))                        // CID / EAD (fallback word2 first 3)
  } else {
    const [a, b, c] = words
    raw.push(a[0] + b[0] + c[0])                   // initials of first 3 words
    raw.push(a.slice(0, 2) + b[0])                 // first 2 of word1 + first of word2
    raw.push(a[0] + b.slice(0, 2))                 // first of word1 + first 2 of word2
    raw.push(a.slice(0, 3))                        // first 3 of word1
    if (words.length > 3) raw.push(a[0] + b[0] + words[3][0]) // skip word3
  }

  return [...new Set(
    raw
      .map(p => p.toUpperCase().padEnd(3, 'X').slice(0, 3))
      .filter(p => /^[A-Z]{3}$/.test(p))
  )]
}

// ── Handlers ──────────────────────────────────────────────────────────────────

export function registerIpcHandlers(): void {

  // ── Log do renderer ──────────────────────────────────────────────────────
  ipcMain.handle(RENDERER_LOG_CHANNEL, (_event, entry: any) => {
    const rLog = createLogger(`renderer:${entry.module ?? 'unknown'}`)
    if (entry.level === 'WARN')  rLog.warn(entry.message, entry.meta)
    if (entry.level === 'ERROR') rLog.error(entry.message, entry.meta)
  })

  // ── Workspace ────────────────────────────────────────────────────────────
  api('workspace:get', async () =>
    dbGet('SELECT * FROM workspaces LIMIT 1')
  )

  api('workspace:update', async (data) => {
    await dbRun(
      "UPDATE workspaces SET name=?, icon=?, accent_color=?, updated_at=datetime('now') WHERE id=?",
      data.name, data.icon, data.accent_color, data.id
    )
    return dbGet('SELECT * FROM workspaces WHERE id = ?', data.id)
  })
  
  api('workspace:updateSettings', async (data) => {
    await dbRun(
      "UPDATE workspaces SET dashboard_settings = ?, updated_at=datetime('now') WHERE id=?",
      data.dashboard_settings, data.id
    )
    return { ok: true }
  })

  // ── Projetos ─────────────────────────────────────────────────────────────
  api('projects:list', async () =>
    dbAll("SELECT * FROM projects WHERE status != 'archived' ORDER BY sort_order, name")
  )

  api('projects:create', async (data) => {
    const r = await dbRun(`
      INSERT INTO projects
        (workspace_id, name, description, icon, color, project_type,
         subcategory, institution, status, date_start, date_end, sort_order)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
      data.workspace_id, data.name, data.description ?? null,
      data.icon ?? null, data.color ?? null, data.project_type ?? 'custom',
      data.subcategory ?? null, data.institution ?? null,
      data.status ?? 'active',
      data.date_start ?? null, data.date_end ?? null,
      data.sort_order ?? 0
    )

    const projectId = r.lastInsertRowid
    const propIds   = await seedProjectProperties(projectId, data.project_type ?? 'custom', data.subcategory ?? undefined)
    await seedProjectViews(projectId, data.project_type ?? 'custom', propIds, data.subcategory ?? undefined)

    dbLog.info('projects:create', { id: projectId, name: data.name })
    return dbGet('SELECT * FROM projects WHERE id = ?', projectId)
  })

  api('projects:update', async (data) => {
    await dbRun(`
      UPDATE projects SET name=?, description=?, icon=?, color=?,
        project_type=?, subcategory=?, institution=?, semester=?, status=?,
        date_start=?, date_end=?, sort_order=?, updated_at=datetime('now')
      WHERE id=?`,
      data.name, data.description ?? null, data.icon ?? null,
      data.color ?? null, data.project_type, data.subcategory ?? null,
      data.institution ?? null, data.semester ?? null,
      data.status, data.date_start ?? null, data.date_end ?? null,
      data.sort_order ?? 0, data.id
    )
    dbLog.info('projects:update', { id: data.id })
    return dbGet('SELECT * FROM projects WHERE id = ?', data.id)
  })

  api('projects:delete', async ({ id }) => {
    dbLog.info('projects:delete', { id })
    await dbRun('DELETE FROM calendar_events WHERE linked_project_id = ?', id)
    return dbRun('DELETE FROM projects WHERE id = ?', id)
  })

  api('projects:getProperties', async ({ id }) =>
    dbAll(
      'SELECT * FROM project_properties WHERE project_id = ? ORDER BY sort_order, id',
      id
    )
  )

  api('projects:getViews', async ({ id }) =>
    dbAll(
      'SELECT * FROM project_views WHERE project_id = ? ORDER BY sort_order, id',
      id
    )
  )

  // ── Páginas ──────────────────────────────────────────────────────────────
  api('pages:list', async ({ project_id }) => {
    const pages = await dbAll(
      'SELECT * FROM pages WHERE project_id = ? AND is_deleted = 0 ORDER BY sort_order, title',
      project_id
    )
    if (pages.length === 0) return []

    const pageIds      = pages.map((p: any) => p.id)
    const placeholders = pageIds.map(() => '?').join(',')
    const propValues   = await dbAll(
      `SELECT ppv.*, pp.prop_key, pp.prop_type, pp.name AS prop_name
       FROM page_prop_values ppv
       JOIN project_properties pp ON pp.id = ppv.property_id
       WHERE ppv.page_id IN (${placeholders})`,
      ...pageIds
    )

    const valuesByPage = new Map<number, any[]>()
    for (const pv of propValues) {
      if (!valuesByPage.has(pv.page_id)) valuesByPage.set(pv.page_id, [])
      valuesByPage.get(pv.page_id)!.push(pv)
    }

    return pages.map((page: any) => ({
      ...page,
      prop_values: valuesByPage.get(page.id) ?? [],
    }))
  })

  api('pages:get', async ({ id }) => {
    const page = await dbGet('SELECT * FROM pages WHERE id = ? AND is_deleted = 0', id)
    if (!page) return null

    const propValues = await dbAll(
      `SELECT ppv.*, pp.prop_key, pp.prop_type, pp.name AS prop_name
       FROM page_prop_values ppv
       JOIN project_properties pp ON pp.id = ppv.property_id
       WHERE ppv.page_id = ?`,
      id
    )
    return { ...page, prop_values: propValues }
  })

  api('pages:create', async (data) => {
    const r = await dbRun(`
      INSERT INTO pages (project_id, parent_id, title, icon, cover, cover_color, body_json, sort_order)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      data.project_id, data.parent_id ?? null, data.title ?? 'Sem título',
      data.icon ?? null, data.cover ?? null, data.cover_color ?? null,
      data.body_json ?? null, data.sort_order ?? 0
    )
    const pageId = r.lastInsertRowid
    await ftsUpsert(pageId, data.project_id, data.title ?? 'Sem título', extractBodyText(data.body_json))

    // Auto-gerar código PREFIX### para projetos académicos
    if (data.project_id) {
      try {
        const project = await dbGet(`SELECT project_type FROM projects WHERE id = ?`, data.project_id)
        if (project?.project_type === 'academic') {
          const codigoProp = await dbGet(
            `SELECT id FROM project_properties WHERE project_id = ? AND prop_key = 'codigo'`,
            data.project_id
          )
          if (codigoProp) {
            const existingCodes = (await dbAll(
              `SELECT ppv.value_text FROM page_prop_values ppv WHERE ppv.property_id = ? AND ppv.value_text IS NOT NULL`,
              codigoProp.id
            )).map((row: any) => row.value_text as string)

            const codigo = generateAcademicCode(data.title ?? 'Sem título', existingCodes)

            await dbRun(
              `INSERT INTO page_prop_values (page_id, property_id, value_text)
               VALUES (?, ?, ?)
               ON CONFLICT(page_id, property_id) DO UPDATE SET value_text = excluded.value_text`,
              pageId, codigoProp.id, codigo
            )
          }
        }
      } catch { /* não bloqueia a criação da página */ }
    }

    return dbGet('SELECT * FROM pages WHERE id = ?', pageId)
  })

  api('pages:update', async (data) => {
    const cols: string[] = ["updated_at = datetime('now')"]
    const params: any[]  = []
    if (data.title       !== undefined) { cols.push('title = ?');       params.push(data.title) }
    if (data.icon        !== undefined) { cols.push('icon = ?');        params.push(data.icon ?? null) }
    if (data.cover       !== undefined) { cols.push('cover = ?');       params.push(data.cover ?? null) }
    if (data.cover_color !== undefined) { cols.push('cover_color = ?'); params.push(data.cover_color ?? null) }
    if (data.body_json   !== undefined) { cols.push('body_json = ?');   params.push(data.body_json ?? null) }
    if (data.sort_order  !== undefined) { cols.push('sort_order = ?');  params.push(data.sort_order) }
    params.push(data.id)
    await dbRun(`UPDATE pages SET ${cols.join(', ')} WHERE id = ?`, ...params)
    if (data.title !== undefined || data.body_json !== undefined) {
      const page = await dbGet('SELECT project_id, title, body_json FROM pages WHERE id = ?', data.id)
      if (page) await ftsUpsert(data.id, page.project_id, page.title, extractBodyText(page.body_json))
    }
    return dbGet('SELECT * FROM pages WHERE id = ?', data.id)
  })

  api('pages:delete', async ({ id }) => {
    await dbRun(`DELETE FROM search_index WHERE entity_type = 'page' AND entity_id = ?`, id)
    return dbRun("UPDATE pages SET is_deleted=1, updated_at=datetime('now') WHERE id=?", id)
  })

  api('pages:reorder', async (items: { id: number; sort_order: number }[]) => {
    const c = await getClient()
    await c.batch(
      items.map(({ id, sort_order }) => ({
        sql:  'UPDATE pages SET sort_order=? WHERE id=?',
        args: [sort_order, id],
      })),
      'write'
    )
    return { ok: true }
  })

  api('calendar:pagesForMonth', async ({ year, month }) => {
    const start = `${year}-${String(month + 1).padStart(2, '0')}-01`
    const d     = new Date(year, month + 1, 0)
    const end   = `${year}-${String(month + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return dbAll(`
      SELECT p.id, p.title, p.icon, p.project_id,
             ppv.value_date, pp.name AS prop_name,
             pr.name AS project_name, pr.color AS project_color, pr.icon AS project_icon
      FROM pages p
      JOIN page_prop_values ppv ON ppv.page_id = p.id
      JOIN project_properties pp ON pp.id = ppv.property_id
      JOIN projects pr ON pr.id = p.project_id
      WHERE p.is_deleted = 0
        AND pp.prop_type = 'date'
        AND ppv.value_date IS NOT NULL
        AND ppv.value_date >= ?
        AND ppv.value_date <= ?
      ORDER BY ppv.value_date ASC
    `, start, end)
  })

  api('dashboard:stats', async () => {
    const totals = await dbGet(`
      SELECT
        (SELECT COUNT(*) FROM pages    WHERE is_deleted = 0)                                    AS total_pages,
        (SELECT COUNT(*) FROM pages    WHERE is_deleted = 0
           AND date(created_at) >= date('now', '-7 days'))                                      AS pages_this_week,
        (SELECT COUNT(*) FROM projects WHERE status = 'active')                                 AS active_projects,
        (SELECT COUNT(*) FROM projects)                                                         AS total_projects
    `)
    const pageCounts = await dbAll(`
      SELECT project_id, COUNT(*) AS count
      FROM pages WHERE is_deleted = 0
      GROUP BY project_id
    `)
    return { ...(totals ?? {}), page_counts: pageCounts }
  })

  api('pages:search', async ({ query, limit }) => {
    const n = limit ?? 20
    const q = (query ?? '').trim()
    if (!q) return []
    try {
      return await dbAll(`
        SELECT p.id, p.title, p.icon, p.project_id, p.updated_at,
               pr.name AS project_name, pr.color AS project_color, pr.icon AS project_icon
        FROM pages p
        JOIN projects pr ON pr.id = p.project_id
        WHERE p.is_deleted = 0
          AND p.id IN (
            SELECT CAST(entity_id AS INTEGER)
            FROM search_index
            WHERE search_index MATCH ? AND entity_type = 'page'
          )
        ORDER BY p.updated_at DESC
        LIMIT ?
      `, `"${q.replace(/"/g, '""')}"*`, n)
    } catch {
      return dbAll(`
        SELECT p.id, p.title, p.icon, p.project_id, p.updated_at,
               pr.name AS project_name, pr.color AS project_color, pr.icon AS project_icon
        FROM pages p
        JOIN projects pr ON pr.id = p.project_id
        WHERE p.is_deleted = 0
          AND p.title LIKE ?
        ORDER BY p.updated_at DESC
        LIMIT ?
      `, `%${q}%`, n)
    }
  })

  api('pages:reindexAll', async () => {
    const pages = await dbAll(`SELECT id, project_id, title, body_json FROM pages WHERE is_deleted = 0`)
    await dbRun(`DELETE FROM search_index WHERE entity_type = 'page'`)
    for (const p of pages) {
      await ftsUpsert(p.id, p.project_id, p.title, extractBodyText(p.body_json))
    }
    return { indexed: pages.length }
  })

  api('pages:listRecent', async ({ limit }) => {
    const n = limit ?? 8
    return dbAll(`
      SELECT p.id, p.title, p.icon, p.project_id, p.updated_at, p.created_at,
             pr.name AS project_name, pr.color AS project_color, pr.icon AS project_icon
      FROM pages p
      JOIN projects pr ON pr.id = p.project_id
      WHERE p.is_deleted = 0
      ORDER BY p.updated_at DESC
      LIMIT ?
    `, n)
  })

  api('pages:listUpcoming', async ({ days }) => {
    const d       = days ?? 14
    const endDate = new Date()
    endDate.setDate(endDate.getDate() + d)
    const endStr  = endDate.toISOString().slice(0, 10)
    return dbAll(`
      SELECT p.id, p.title, p.icon, p.project_id,
             ppv.value_date, pp.name AS prop_name,
             pr.name AS project_name, pr.color AS project_color
      FROM pages p
      JOIN page_prop_values ppv ON ppv.page_id = p.id
      JOIN project_properties pp ON pp.id = ppv.property_id
      JOIN projects pr ON pr.id = p.project_id
      WHERE p.is_deleted = 0
        AND pp.prop_type = 'date'
        AND ppv.value_date IS NOT NULL
        AND ppv.value_date >= date('now')
        AND ppv.value_date <= ?
      ORDER BY ppv.value_date ASC
      LIMIT 8
    `, endStr)
  })

  api('pages:setPropValue', async (data) => {
    await dbRun(`
      INSERT INTO page_prop_values
        (page_id, property_id, value_text, value_num, value_bool, value_date, value_date2, value_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(page_id, property_id) DO UPDATE SET
        value_text  = excluded.value_text,
        value_num   = excluded.value_num,
        value_bool  = excluded.value_bool,
        value_date  = excluded.value_date,
        value_date2 = excluded.value_date2,
        value_json  = excluded.value_json
    `,
      data.page_id, data.property_id,
      data.value_text  ?? null, data.value_num   ?? null,
      data.value_bool  ?? null, data.value_date  ?? null,
      data.value_date2 ?? null, data.value_json  ?? null
    )
    return { ok: true }
  })

  // ── Propriedades ─────────────────────────────────────────────────────────
  api('properties:create', async (data) => {
    const max = (await dbGet(
      'SELECT COALESCE(MAX(sort_order), -1) AS m FROM project_properties WHERE project_id = ?',
      data.project_id
    ))?.m ?? -1
    const r = await dbRun(`
      INSERT INTO project_properties (project_id, name, prop_key, prop_type, is_required, sort_order)
      VALUES (?, ?, ?, ?, ?, ?)`,
      data.project_id, data.name, data.prop_key, data.prop_type,
      data.is_required ?? 0, data.sort_order ?? (max + 1)
    )
    return dbGet('SELECT * FROM project_properties WHERE id = ?', r.lastInsertRowid)
  })

  api('properties:update', async (data) => {
    await dbRun(
      'UPDATE project_properties SET name=?, prop_type=?, is_required=? WHERE id=?',
      data.name, data.prop_type, data.is_required ?? 0, data.id
    )
    return dbGet('SELECT * FROM project_properties WHERE id = ?', data.id)
  })

  api('properties:delete', async ({ id }) => {
    await dbRun('DELETE FROM project_properties WHERE id = ?', id)
    return { ok: true }
  })

  api('properties:reorder', async (items: { id: number; sort_order: number }[]) => {
    const c = await getClient()
    await c.batch(
      items.map(({ id, sort_order }) => ({
        sql:  'UPDATE project_properties SET sort_order=? WHERE id=?',
        args: [sort_order, id],
      })),
      'write'
    )
    return { ok: true }
  })

  api('properties:getOptions', async ({ id }) =>
    dbAll('SELECT * FROM prop_options WHERE property_id = ? ORDER BY sort_order, id', id)
  )

  api('properties:createOption', async (data) => {
    const max = (await dbGet(
      'SELECT COALESCE(MAX(sort_order), -1) AS m FROM prop_options WHERE property_id = ?',
      data.property_id
    ))?.m ?? -1
    const r = await dbRun(
      'INSERT INTO prop_options (property_id, label, color, sort_order) VALUES (?, ?, ?, ?)',
      data.property_id, data.label, data.color ?? null,
      data.sort_order ?? (max + 1)
    )
    return dbGet('SELECT * FROM prop_options WHERE id = ?', r.lastInsertRowid)
  })

  api('properties:updateOption', async (data) => {
    await dbRun(
      'UPDATE prop_options SET label=?, color=? WHERE id=?',
      data.label, data.color ?? null, data.id
    )
    return dbGet('SELECT * FROM prop_options WHERE id = ?', data.id)
  })

  api('properties:deleteOption', async ({ id }) => {
    await dbRun('DELETE FROM prop_options WHERE id = ?', id)
    return { ok: true }
  })

  api('properties:reorderOptions', async (items: { id: number; sort_order: number }[]) => {
    const c = await getClient()
    await c.batch(
      items.map(({ id, sort_order }) => ({
        sql:  'UPDATE prop_options SET sort_order=? WHERE id=?',
        args: [sort_order, id],
      })),
      'write'
    )
    return { ok: true }
  })

  // ── Views ─────────────────────────────────────────────────────────────────
  api('views:create', async (data) => {
    const max = (await dbGet(
      'SELECT COALESCE(MAX(sort_order), -1) AS m FROM project_views WHERE project_id = ?',
      data.project_id
    ))?.m ?? -1
    const r = await dbRun(`
      INSERT INTO project_views
        (project_id, name, view_type, group_by_property_id, date_property_id,
         visible_props_json, is_default, sort_order)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      data.project_id, data.name, data.view_type,
      data.group_by_property_id ?? null, data.date_property_id ?? null,
      data.visible_props_json ?? null, data.is_default ?? 0,
      data.sort_order ?? (max + 1)
    )
    return dbGet('SELECT * FROM project_views WHERE id = ?', r.lastInsertRowid)
  })

  api('views:update', async (data) => {
    await dbRun(`
      UPDATE project_views SET name=?, view_type=?, group_by_property_id=?,
        date_property_id=?, visible_props_json=?, filter_json=?, sort_json=?,
        include_subpages=?
      WHERE id=?`,
      data.name, data.view_type, data.group_by_property_id ?? null,
      data.date_property_id ?? null, data.visible_props_json ?? null,
      data.filter_json ?? null, data.sort_json ?? null,
      data.include_subpages ?? 0, data.id
    )
    return dbGet('SELECT * FROM project_views WHERE id = ?', data.id)
  })

  api('views:delete', async ({ id }) => {
    await dbRun('DELETE FROM project_views WHERE id = ?', id)
    return { ok: true }
  })

  api('views:setDefault', async ({ id }) => {
    const view = await dbGet('SELECT project_id FROM project_views WHERE id = ?', id)
    if (!view) throw new Error('View não encontrada')
    await dbRun('UPDATE project_views SET is_default=0 WHERE project_id=?', view.project_id)
    await dbRun('UPDATE project_views SET is_default=1 WHERE id=?', id)
    return { ok: true }
  })

  // ── Upload de imagens ─────────────────────────────────────────────────────
  api('uploads:saveImage', ({ data }: { data: string; name: string }) => {
    const crypto = require('crypto')
    const fs     = require('fs')
    const path   = require('path')
    const { UPLOADS_DIR } = require('./paths')

    const match  = data.match(/^data:image\/([a-zA-Z]+);base64,/)
    const ext    = match ? match[1].replace('jpeg', 'jpg') : 'png'
    const base64 = data.replace(/^data:image\/[a-zA-Z]+;base64,/, '')
    const hash   = crypto.createHash('sha256').update(base64).digest('hex').slice(0, 16)
    const fname  = `${hash}.${ext}`
    const fpath  = path.join(UPLOADS_DIR, fname)

    if (!fs.existsSync(fpath)) {
      fs.writeFileSync(fpath, Buffer.from(base64, 'base64'))
    }

    return { url: `file://${fpath}` }
  })

  // ── Configurações ─────────────────────────────────────────────────────────
  api('config:get', async ({ key }) => {
    const row = await dbGet('SELECT value FROM settings WHERE key = ?', key)
    return row ?? null  // retorna { value: '...' } para o renderer poder aceder via r.value?.value
  })

  api('config:set', async ({ key, value }) =>
    dbRun('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', key, value)
  )

  api('config:getAll', async () => {
    const rows = await dbAll('SELECT key, value FROM settings')
    return Object.fromEntries(rows.map((r: any) => [r.key, r.value]))
  })

  // ── Tags globais ──────────────────────────────────────────────────────────
  api('tags:list', async () => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    return dbAll('SELECT * FROM tags WHERE workspace_id = ? ORDER BY name', ws.id)
  })

  api('tags:create', async ({ name, color }) => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    const r  = await dbRun('INSERT OR IGNORE INTO tags (workspace_id, name, color) VALUES (?, ?, ?)',
      ws.id, name, color ?? null)
    return dbGet('SELECT * FROM tags WHERE id = ?', r.lastInsertRowid)
  })

  api('tags:delete', async ({ id }) =>
    dbRun('DELETE FROM tags WHERE id = ?', id)
  )

  api('tags:listForPage', async ({ page_id }) =>
    dbAll(`
      SELECT t.* FROM tags t
      JOIN page_tags pt ON pt.tag_id = t.id
      WHERE pt.page_id = ?
      ORDER BY t.name
    `, page_id)
  )

  api('tags:assign', async ({ page_id, tag_id }) =>
    dbRun('INSERT OR IGNORE INTO page_tags (page_id, tag_id) VALUES (?, ?)', page_id, tag_id)
  )

  api('tags:remove', async ({ page_id, tag_id }) =>
    dbRun('DELETE FROM page_tags WHERE page_id = ? AND tag_id = ?', page_id, tag_id)
  )

  // ── Pré-requisitos entre páginas ──────────────────────────────────────────
  api('prerequisites:list', async ({ page_id }) =>
    dbAll(`
      SELECT pp.prerequisite_id AS id, p.title, p.icon, p.project_id,
             pv.value_text AS status_value
      FROM page_prerequisites pp
      JOIN pages p ON p.id = pp.prerequisite_id
      LEFT JOIN page_prop_values pv ON pv.page_id = p.id
        AND pv.property_id = (
          SELECT id FROM project_properties
          WHERE project_id = p.project_id AND prop_key = 'status' LIMIT 1
        )
      WHERE pp.page_id = ?
      ORDER BY p.sort_order, p.title
    `, page_id)
  )

  api('prerequisites:listDependents', async ({ page_id }) =>
    dbAll(`
      SELECT pp.page_id AS id, p.title, p.icon
      FROM page_prerequisites pp
      JOIN pages p ON p.id = pp.page_id
      WHERE pp.prerequisite_id = ?
      ORDER BY p.sort_order, p.title
    `, page_id)
  )

  api('prerequisites:add', async ({ page_id, prerequisite_id }) => {
    if (page_id === prerequisite_id) return { ok: false, error: 'Uma página não pode ser pré-requisito de si mesma.' }
    const cycle = await dbGet(`SELECT 1 FROM page_prerequisites WHERE page_id = ? AND prerequisite_id = ?`, prerequisite_id, page_id)
    if (cycle) return { ok: false, error: 'Isso criaria uma dependência circular.' }
    try { await dbRun(`INSERT OR IGNORE INTO page_prerequisites (page_id, prerequisite_id) VALUES (?, ?)`, page_id, prerequisite_id) } catch {}
    return { ok: true }
  })

  api('prerequisites:remove', async ({ page_id, prerequisite_id }) =>
    dbRun(`DELETE FROM page_prerequisites WHERE page_id = ? AND prerequisite_id = ?`, page_id, prerequisite_id)
  )

  // ── Backlinks ─────────────────────────────────────────────────────────────
  api('backlinks:list', async ({ page_id }) =>
    dbAll(`
      SELECT pb.source_page_id AS id, p.title, p.icon, p.project_id, pr.name AS project_name
      FROM page_backlinks pb
      JOIN pages p    ON p.id    = pb.source_page_id
      JOIN projects pr ON pr.id = p.project_id
      WHERE pb.target_page_id = ?
      ORDER BY p.title
    `, page_id)
  )

  api('backlinks:listOutgoing', async ({ page_id }) =>
    dbAll(`
      SELECT pb.target_page_id AS id, p.title, p.icon, p.project_id, pr.name AS project_name
      FROM page_backlinks pb
      JOIN pages p     ON p.id   = pb.target_page_id
      JOIN projects pr ON pr.id  = p.project_id
      WHERE pb.source_page_id = ?
      ORDER BY p.title
    `, page_id)
  )

  api('backlinks:add', async ({ source_page_id, target_page_id }) => {
    if (source_page_id === target_page_id) return { ok: true }
    try { await dbRun(`INSERT OR IGNORE INTO page_backlinks (source_page_id, target_page_id) VALUES (?, ?)`, source_page_id, target_page_id) } catch {}
    return { ok: true }
  })

  api('backlinks:remove', async ({ source_page_id, target_page_id }) =>
    dbRun(`DELETE FROM page_backlinks WHERE source_page_id = ? AND target_page_id = ?`, source_page_id, target_page_id)
  )

  // ── Leituras ───────────────────────────────────────────────────────────────
  api('readings:list', async () => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    return dbAll(`SELECT * FROM readings WHERE workspace_id = ? ORDER BY updated_at DESC`, ws.id)
  })

  api('readings:create', async (d) => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    const r = await dbRun(`
      INSERT INTO readings
        (workspace_id, resource_id, title, reading_type, author, publisher, year, isbn, status, rating,
         current_page, total_pages, date_start, date_end, review, progress_type, progress_percent)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
      ws.id, d.resource_id ?? null, d.title, d.reading_type ?? 'book', d.author ?? null,
      d.publisher ?? null, d.year ?? null, d.isbn ?? null, d.status ?? 'want', d.rating ?? null,
      d.current_page ?? 0, d.total_pages ?? null, d.date_start ?? null,
      d.date_end ?? null, d.review ?? null,
      d.progress_type ?? 'pages', d.progress_percent ?? 0
    )
    return dbGet('SELECT * FROM readings WHERE id = ?', r.lastInsertRowid)
  })

  api('readings:update', async (d) => {
    await dbRun(`
      UPDATE readings SET
        resource_id = ?, title = ?, reading_type = ?, author = ?, publisher = ?, year = ?,
        isbn = ?, status = ?, rating = ?, current_page = ?, total_pages = ?,
        date_start = ?, date_end = ?, review = ?, progress_type = ?, progress_percent = ?,
        updated_at = datetime('now')
      WHERE id = ?
    `,
      d.resource_id ?? null, d.title, d.reading_type ?? 'book', d.author ?? null,
      d.publisher ?? null, d.year ?? null, d.isbn ?? null, d.status, d.rating ?? null,
      d.current_page ?? 0, d.total_pages ?? null, d.date_start ?? null, d.date_end ?? null,
      d.review ?? null, d.progress_type ?? 'pages', d.progress_percent ?? 0, d.id
    )
    return dbGet('SELECT * FROM readings WHERE id = ?', d.id)
  })

  api('readings:delete', async ({ id }) =>
    dbRun('DELETE FROM readings WHERE id = ?', id)
  )

  // ── Sessões de leitura ─────────────────────────────────────────────────────
  api('reading_sessions:list', async ({ reading_id }) =>
    dbAll(`SELECT * FROM reading_sessions WHERE reading_id = ? ORDER BY date DESC, id DESC`, reading_id)
  )

  api('reading_sessions:create', async (d) => {
    const r = await dbRun(`
      INSERT INTO reading_sessions (reading_id, date, page_start, page_end, duration_min, notes, percent_end)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `, d.reading_id, d.date, d.page_start ?? 0, d.page_end ?? 0,
       d.duration_min ?? null, d.notes?.trim() || null, d.percent_end ?? null)
    const sess    = await dbGet('SELECT * FROM reading_sessions WHERE id = ?', r.lastInsertRowid)
    const reading = await dbGet('SELECT * FROM readings WHERE id = ?', d.reading_id)
    if (!reading) return sess

    if (reading.progress_type === 'percent' && d.percent_end != null) {
      const pct       = Math.min(100, Math.max(0, d.percent_end))
      const newStatus = pct >= 100
        ? 'done' : reading.status === 'want' ? 'reading' : reading.status
      const dateEnd   = newStatus === 'done' ? d.date : reading.date_end
      await dbRun(`UPDATE readings SET progress_percent = ?, status = ?, date_end = ?, updated_at = datetime('now') WHERE id = ?`,
        pct, newStatus, dateEnd, d.reading_id)
    } else if (sess.page_end > reading.current_page) {
      const newStatus = (reading.total_pages && sess.page_end >= reading.total_pages)
        ? 'done' : reading.status === 'want' ? 'reading' : reading.status
      const dateEnd   = newStatus === 'done' ? d.date : reading.date_end
      await dbRun(`UPDATE readings SET current_page = ?, status = ?, date_end = ?, updated_at = datetime('now') WHERE id = ?`,
        sess.page_end, newStatus, dateEnd, d.reading_id)
    }
    return sess
  })

  api('reading_sessions:delete', async ({ id }) =>
    dbRun('DELETE FROM reading_sessions WHERE id = ?', id)
  )

  // ── Notas de leitura ──────────────────────────────────────────────────────
  api('reading_notes:list', async ({ reading_id }) =>
    dbAll(`SELECT * FROM reading_notes WHERE reading_id = ? ORDER BY created_at ASC`, reading_id)
  )
  api('reading_notes:create', async (d) => {
    const r = await dbRun(`INSERT INTO reading_notes (reading_id, chapter, content) VALUES (?, ?, ?)`,
      d.reading_id, d.chapter?.trim() || null, d.content)
    return dbGet('SELECT * FROM reading_notes WHERE id = ?', r.lastInsertRowid)
  })
  api('reading_notes:delete', async ({ id }) =>
    dbRun('DELETE FROM reading_notes WHERE id = ?', id)
  )

  // ── Citações de leitura ───────────────────────────────────────────────────
  api('reading_quotes:list', async ({ reading_id }) =>
    dbAll(`SELECT * FROM reading_quotes WHERE reading_id = ? ORDER BY created_at ASC`, reading_id)
  )
  api('reading_quotes:create', async (d) => {
    const r = await dbRun(`INSERT INTO reading_quotes (reading_id, text, location) VALUES (?, ?, ?)`,
      d.reading_id, d.text, d.location?.trim() || null)
    return dbGet('SELECT * FROM reading_quotes WHERE id = ?', r.lastInsertRowid)
  })
  api('reading_quotes:delete', async ({ id }) =>
    dbRun('DELETE FROM reading_quotes WHERE id = ?', id)
  )

  // ── Vínculos de leitura ───────────────────────────────────────────────────
  api('reading_links:list', async ({ reading_id }) =>
    dbAll(`
      SELECT rl.reading_id, rl.page_id, p.title, p.project_id, pr.name AS project_name
      FROM reading_links rl
      JOIN pages p ON p.id = rl.page_id
      JOIN projects pr ON pr.id = p.project_id
      WHERE rl.reading_id = ?
    `, reading_id)
  )
  api('reading_links:add', async ({ reading_id, page_id }) => {
    try { await dbRun(`INSERT INTO reading_links (reading_id, page_id) VALUES (?, ?)`, reading_id, page_id) } catch {}
    return { ok: true }
  })
  api('reading_links:remove', async ({ reading_id, page_id }) =>
    dbRun(`DELETE FROM reading_links WHERE reading_id = ? AND page_id = ?`, reading_id, page_id)
  )
  api('reading_links:listForProject', async ({ project_id }) =>
    dbAll(`
      SELECT rd.id, rd.title, rd.cover_path, rd.status, rd.current_page, rd.total_pages,
             rd.author, rd.reading_type, rd.progress_type, rd.progress_percent,
             p.id AS page_id, p.title AS page_title, p.icon AS page_icon,
             res.metadata_json
      FROM reading_links rl
      JOIN pages p        ON p.id        = rl.page_id
      JOIN readings rd    ON rd.id       = rl.reading_id
      LEFT JOIN resources res ON res.id  = rd.resource_id
      WHERE p.project_id = ?
      ORDER BY rd.title
    `, project_id)
  )

  // ── Analytics ─────────────────────────────────────────────────────────────

  api('analytics:global', async () => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    const wsId = ws?.id ?? 1
    const year = new Date().getFullYear()

    const [
      heatmap,
      hoursByProject,
      hoursByType,
      booksByMonth,
      deepWork,
      peakHour,
      tasksCompletion,
      readingAbsorption,
      readingSpeed,
      activityByDow,
      readingGoal,
    ] = await Promise.all([
      // Activity heatmap: last 365 days of time_sessions
      dbAll(`
        SELECT date(started_at) AS day, SUM(duration_min) AS minutes
        FROM time_sessions
        WHERE started_at >= date('now', '-365 days')
        GROUP BY day
        ORDER BY day
      `),
      // Hours by project: last 30 days
      dbAll(`
        SELECT p.id, p.name, p.color, p.icon, p.project_type,
               ROUND(SUM(ts.duration_min) / 60.0, 1) AS hours
        FROM time_sessions ts
        JOIN projects p ON p.id = ts.project_id
        WHERE ts.started_at >= date('now', '-30 days')
          AND ts.project_id IS NOT NULL
        GROUP BY p.id
        ORDER BY hours DESC
        LIMIT 10
      `),
      // Hours by project type: last 30 days (radar)
      dbAll(`
        SELECT p.project_type,
               ROUND(SUM(ts.duration_min) / 60.0, 2) AS hours
        FROM time_sessions ts
        JOIN projects p ON p.id = ts.project_id
        WHERE ts.started_at >= date('now', '-30 days')
          AND ts.project_id IS NOT NULL
        GROUP BY p.project_type
        ORDER BY hours DESC
      `),
      // Books completed by month: last 12 months
      dbAll(`
        SELECT strftime('%Y-%m', date_end) AS month, COUNT(*) AS count
        FROM readings
        WHERE status = 'done'
          AND date_end IS NOT NULL
          AND date_end >= date('now', '-12 months')
          AND workspace_id = ?
        GROUP BY month
        ORDER BY month
      `, wsId),
      // Deep work hours from work_blocks: last 30 days
      dbGet(`
        SELECT ROUND(COALESCE(SUM(logged_hours), 0), 1) AS hours
        FROM work_blocks
        WHERE status = 'done'
          AND date >= date('now', '-30 days')
      `),
      // Peak productivity hour
      dbGet(`
        SELECT CAST(strftime('%H', started_at) AS INTEGER) AS hour,
               SUM(duration_min) AS minutes
        FROM time_sessions
        GROUP BY hour
        ORDER BY minutes DESC
        LIMIT 1
      `),
      // Tasks completion rate: last 30 days
      dbGet(`
        SELECT
          COUNT(CASE WHEN status IN ('completed','done') THEN 1 END) AS done,
          COUNT(*) AS total
        FROM planned_tasks
        WHERE updated_at >= date('now', '-30 days')
      `),
      // Reading absorption: added vs completed per month (last 12 months)
      dbAll(`
        SELECT month, SUM(added) AS added, SUM(completed) AS completed
        FROM (
          SELECT strftime('%Y-%m', created_at) AS month, 1 AS added, 0 AS completed
          FROM readings
          WHERE workspace_id = ? AND created_at >= date('now', '-12 months')
          UNION ALL
          SELECT strftime('%Y-%m', date_end) AS month, 0 AS added, 1 AS completed
          FROM readings
          WHERE workspace_id = ? AND status = 'done'
            AND date_end IS NOT NULL AND date_end >= date('now', '-12 months')
        )
        GROUP BY month ORDER BY month
      `, wsId, wsId),
      // Reading speed: pages per day from reading_sessions (last 7 days)
      dbAll(`
        SELECT date, SUM(page_end - page_start) AS pages
        FROM reading_sessions
        WHERE date >= date('now', '-7 days')
        GROUP BY date ORDER BY date
      `),
      // Activity by day of week: time_sessions last 90 days
      dbAll(`
        SELECT CAST(strftime('%w', started_at) AS INTEGER) AS dow,
               SUM(duration_min) AS minutes
        FROM time_sessions
        WHERE started_at >= date('now', '-90 days')
        GROUP BY dow ORDER BY dow
      `),
      // Reading goal progress
      dbGet(`
        SELECT rg.target,
               (SELECT COUNT(*) FROM readings r2
                WHERE r2.workspace_id = rg.workspace_id
                  AND r2.status = 'done'
                  AND substr(r2.date_end, 1, 4) = CAST(rg.year AS TEXT)
               ) AS done
        FROM reading_goals rg
        WHERE rg.workspace_id = ? AND rg.year = ?
        LIMIT 1
      `, wsId, year),
    ])

    return {
      heatmap:            heatmap          ?? [],
      hours_by_project:   hoursByProject   ?? [],
      hours_by_type:      hoursByType      ?? [],
      books_by_month:     booksByMonth     ?? [],
      deep_work_hours:    deepWork?.hours  ?? 0,
      peak_hour:          peakHour?.hour   ?? null,
      tasks_done:         tasksCompletion?.done  ?? 0,
      tasks_total:        tasksCompletion?.total ?? 0,
      reading_goal:       readingGoal ? { target: readingGoal.target, done: readingGoal.done, year } : null,
      reading_absorption: readingAbsorption ?? [],
      reading_speed:      readingSpeed ?? [],
      activity_by_dow:    activityByDow ?? [],
    }
  })

  api('analytics:project', async ({ project_id }: { project_id: number }) => {
    const [
      pagesCount,
      tasksStats,
      focusTotal,
      focusMonth,
      lastSession,
      nextDeadline,
      heatmap,
      recentPages,
      upcomingTasks,
      upcomingEvents,
      backlinksCount,
      tagsCount,
      recentSessions,
    ] = await Promise.all([
      // Total de páginas
      dbGet(`SELECT COUNT(*) AS count FROM pages WHERE project_id = ?`, project_id),
      // Tarefas: total, concluídas, atrasadas
      dbGet(`
        SELECT
          COUNT(*) AS total,
          COUNT(CASE WHEN status IN ('completed','done') THEN 1 END) AS done,
          COUNT(CASE WHEN status NOT IN ('completed','done')
                      AND deadline IS NOT NULL
                      AND deadline < date('now') THEN 1 END) AS overdue
        FROM planned_tasks WHERE project_id = ?
      `, project_id),
      // Horas de foco total
      dbGet(`
        SELECT ROUND(COALESCE(SUM(duration_min), 0) / 60.0, 1) AS hours
        FROM time_sessions WHERE project_id = ?
      `, project_id),
      // Horas de foco últimos 30 dias
      dbGet(`
        SELECT ROUND(COALESCE(SUM(duration_min), 0) / 60.0, 1) AS hours
        FROM time_sessions
        WHERE project_id = ? AND started_at >= date('now', '-30 days')
      `, project_id),
      // Última sessão de foco
      dbGet(`
        SELECT started_at FROM time_sessions
        WHERE project_id = ? ORDER BY started_at DESC LIMIT 1
      `, project_id),
      // Próximo prazo
      dbGet(`
        SELECT title, deadline FROM planned_tasks
        WHERE project_id = ? AND status NOT IN ('completed','done')
          AND deadline IS NOT NULL AND deadline >= date('now')
        ORDER BY deadline ASC LIMIT 1
      `, project_id),
      // Heatmap últimas 8 semanas (56 dias)
      dbAll(`
        SELECT date(started_at) AS day, SUM(duration_min) AS minutes
        FROM time_sessions
        WHERE project_id = ? AND started_at >= date('now', '-56 days')
        GROUP BY day ORDER BY day
      `, project_id),
      // Páginas recentes (últimas 6 editadas)
      dbAll(`
        SELECT id, title, icon, updated_at FROM pages
        WHERE project_id = ? ORDER BY updated_at DESC LIMIT 6
      `, project_id),
      // Próximas tarefas abertas
      dbAll(`
        SELECT id, title, deadline, priority, status, estimated_hours
        FROM planned_tasks
        WHERE project_id = ? AND status NOT IN ('completed','done')
        ORDER BY
          CASE WHEN deadline IS NOT NULL AND deadline < date('now') THEN 0
               WHEN deadline IS NOT NULL THEN 1
               ELSE 2 END,
          deadline ASC, priority DESC
        LIMIT 7
      `, project_id),
      // Próximos eventos (30 dias)
      dbAll(`
        SELECT id, title, event_type, start_dt AS start_at
        FROM calendar_events
        WHERE project_id = ? AND start_dt >= date('now') AND start_dt <= date('now', '+30 days')
        ORDER BY start_dt ASC LIMIT 6
      `, project_id),
      // Total de backlinks recebidos por páginas do projecto
      dbGet(`
        SELECT COUNT(*) AS count FROM page_backlinks pb
        JOIN pages p ON p.id = pb.target_page_id
        WHERE p.project_id = ?
      `, project_id),
      // Tags usadas no projecto
      dbGet(`
        SELECT COUNT(DISTINCT t.id) AS count
        FROM tags t
        JOIN page_tags pt ON pt.tag_id = t.id
        JOIN pages p ON p.id = pt.page_id
        WHERE p.project_id = ?
      `, project_id),
      // Sessões recentes (para health/hobby)
      dbAll(`
        SELECT id, started_at, duration_min, label FROM time_sessions
        WHERE project_id = ?
        ORDER BY started_at DESC LIMIT 8
      `, project_id),
    ])

    return {
      pages_count:      pagesCount?.count     ?? 0,
      tasks_total:      tasksStats?.total      ?? 0,
      tasks_done:       tasksStats?.done       ?? 0,
      tasks_overdue:    tasksStats?.overdue    ?? 0,
      focus_hours:      focusTotal?.hours      ?? 0,
      focus_hours_30d:  focusMonth?.hours      ?? 0,
      last_session:     lastSession?.started_at ?? null,
      next_deadline:    nextDeadline ?? null,
      heatmap:          heatmap      ?? [],
      recent_pages:     recentPages  ?? [],
      upcoming_tasks:   upcomingTasks ?? [],
      upcoming_events:  upcomingEvents ?? [],
      backlinks_count:  backlinksCount?.count ?? 0,
      tags_count:       tagsCount?.count      ?? 0,
      recent_sessions:  recentSessions ?? [],
    }
  })

  api('analytics:todayFocus', async () => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    const wsId = ws?.id ?? 1
    const result = await dbGet(`
      SELECT COALESCE(SUM(duration_min), 0) AS minutes
      FROM time_sessions
      WHERE workspace_id = ?
        AND date(started_at) = date('now')
    `, wsId)
    return { minutes: result?.minutes ?? 0 }
  })

  // ── Metas de leitura ──────────────────────────────────────────────────────

  api('reading:goals:get', async ({ workspace_id, year }: { workspace_id: number; year: number }) =>
    dbGet(`SELECT * FROM reading_goals WHERE workspace_id = ? AND year = ? LIMIT 1`, workspace_id, year)
  )

  api('reading:goals:set', async ({ workspace_id, year, target }: { workspace_id: number; year: number; target: number }) => {
    const existing = await dbGet(`SELECT id FROM reading_goals WHERE workspace_id = ? AND year = ? LIMIT 1`, workspace_id, year)
    if (existing) {
      await dbRun(`UPDATE reading_goals SET target = ? WHERE id = ?`, target, existing.id)
    } else {
      await dbRun(`INSERT INTO reading_goals (workspace_id, year, target) VALUES (?, ?, ?)`, workspace_id, year, target)
    }
    return dbGet(`SELECT * FROM reading_goals WHERE workspace_id = ? AND year = ? LIMIT 1`, workspace_id, year)
  })

  api('reading:goals:progress', async ({ workspace_id, year }: { workspace_id: number; year: number }) => {
    const goal = await dbGet(
      `SELECT target FROM reading_goals WHERE workspace_id = ? AND year = ? LIMIT 1`,
      workspace_id, year
    )
    const done = await dbGet(
      `SELECT COUNT(*) AS count FROM readings
       WHERE workspace_id = ? AND status = 'done'
         AND (date_end IS NOT NULL AND substr(date_end,1,4) = ?)`,
      workspace_id, String(year)
    )
    return { target: goal?.target ?? null, done: done?.count ?? 0 }
  })

  // ── Recursos ───────────────────────────────────────────────────────────────
  api('resources:list', async () => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    return dbAll(`
      SELECT r.*,
             rd.status        AS reading_status,
             rd.current_page  AS reading_current_page,
             rd.total_pages   AS reading_total_pages,
             rd.rating        AS reading_rating
      FROM resources r
      LEFT JOIN (
        SELECT resource_id, status, current_page, total_pages, rating,
               ROW_NUMBER() OVER (
                 PARTITION BY resource_id
                 ORDER BY CASE status
                   WHEN 'reading' THEN 1 WHEN 'paused' THEN 2
                   WHEN 'want'    THEN 3 WHEN 'done'   THEN 4
                 END, updated_at DESC
               ) AS rn
        FROM readings WHERE resource_id IS NOT NULL
      ) rd ON rd.resource_id = r.id AND rd.rn = 1
      WHERE r.workspace_id = ?
      ORDER BY r.created_at DESC
    `, ws.id)
  })

  api('resources:create', async (d) => {
    const ws = await dbGet('SELECT id FROM workspaces LIMIT 1')
    const r = await dbRun(`
      INSERT INTO resources (workspace_id, title, resource_type, url, description, tags_json, metadata_json)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `,
      ws.id, d.title, d.resource_type ?? null, d.url ?? null,
      d.description ?? null, d.tags_json ?? null, d.metadata_json ?? null
    )
    return dbGet('SELECT * FROM resources WHERE id = ?', r.lastInsertRowid)
  })

  api('resources:update', async (d) => {
    await dbRun(`
      UPDATE resources SET title = ?, resource_type = ?, url = ?, description = ?, tags_json = ?, metadata_json = ?
      WHERE id = ?
    `,
      d.title, d.resource_type ?? null, d.url ?? null,
      d.description ?? null, d.tags_json ?? null, d.metadata_json ?? null, d.id
    )
    return dbGet('SELECT * FROM resources WHERE id = ?', d.id)
  })

  ipcMain.handle('resources:fetchMeta', async (_e, { type, query, url }: { type: string; query: string; url?: string }) => {
    const meta = await fetchMetadata(type, query, url)
    return { ok: true, data: meta }
  })

  ipcMain.handle('resources:searchMeta', async (_e, { type, query }: { type: string; query: string }) => {
    try {
      if (type === 'livro') {
        const fields = 'key,title,author_name,first_publish_year,number_of_pages_median,isbn,publisher,language,cover_i'
        const data = await fetchJson(`https://openlibrary.org/search.json?title=${encodeURIComponent(query)}&limit=6&fields=${fields}`)
        const results = (data?.docs ?? []).map((doc: any) => ({
          title:     doc.title,
          author:    doc.author_name?.join(', ') ?? '',
          year:      doc.first_publish_year ?? null,
          pages:     doc.number_of_pages_median ?? null,
          isbn:      doc.isbn?.[0] ?? null,
          publisher: doc.publisher?.[0] ?? null,
          language:  doc.language?.[0] ?? null,
          cover_url:   doc.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-S.jpg` : null,
          cover_url_m: doc.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg` : null,
        }))
        return { ok: true, data: results }
      }
      if (type === 'artigo') {
        const data = await fetchJson(`https://api.crossref.org/works?query=${encodeURIComponent(query)}&rows=6`)
        const results = (data?.message?.items ?? []).map((w: any) => ({
          title:   w.title?.[0] ?? '',
          authors: w.author?.map((a: any) => `${a.given ?? ''} ${a.family ?? ''}`.trim()).join(', ') ?? '',
          journal: w['container-title']?.[0] ?? null,
          year:    w.published?.['date-parts']?.[0]?.[0] ?? null,
          doi:     w.DOI ?? null,
          volume:  w.volume ?? null,
          issue:   w.issue ?? null,
        }))
        return { ok: true, data: results }
      }
    } catch (e: any) {
      log.warn('searchMeta error', e?.message)
    }
    return { ok: true, data: [] }
  })

  api('resources:delete', async ({ id }) =>
    dbRun('DELETE FROM resources WHERE id = ?', id)
  )

  // ── Vínculos recurso ↔ página ──────────────────────────────────────────────
  api('resource_pages:listForResource', async ({ resource_id }) =>
    dbAll(`
      SELECT rp.resource_id, rp.page_id,
             p.title AS page_title, p.project_id,
             pr.name AS project_name
      FROM resource_pages rp
      JOIN pages    p  ON p.id  = rp.page_id
      JOIN projects pr ON pr.id = p.project_id
      WHERE rp.resource_id = ?
      ORDER BY pr.name, p.title
    `, resource_id)
  )

  api('resource_pages:listForPage', async ({ page_id }) =>
    dbAll(`
      SELECT rp.resource_id, rp.page_id,
             r.title, r.resource_type, r.url, r.description, r.metadata_json
      FROM resource_pages rp
      JOIN resources r ON r.id = rp.resource_id
      WHERE rp.page_id = ?
      ORDER BY r.title
    `, page_id)
  )

  api('resource_pages:add', async ({ resource_id, page_id }) => {
    try { await dbRun(`INSERT INTO resource_pages (resource_id, page_id) VALUES (?, ?)`, resource_id, page_id) } catch {}
    return { ok: true }
  })

  api('resource_pages:remove', async ({ resource_id, page_id }) =>
    dbRun(`DELETE FROM resource_pages WHERE resource_id = ? AND page_id = ?`, resource_id, page_id)
  )

  // ── Eventos de Calendário ─────────────────────────────────────────────────

  api('events:listForMonth', async ({ year, month }) => {
    const y     = String(year)
    const m     = String(month + 1).padStart(2, '0')
    const start = `${y}-${m}-01`
    const next  = month === 11 ? `${year + 1}-01-01` : `${y}-${String(month + 2).padStart(2, '0')}-01`
    return dbAll(`
      SELECT 'calendar' AS source, ce.id, ce.title, ce.description, ce.start_dt, ce.end_dt, ce.all_day, ce.color, ce.event_type, ce.linked_page_id, ce.linked_project_id, p.title AS page_title, pr.name AS project_name, pr.color AS project_color
      FROM calendar_events ce
      LEFT JOIN pages p ON p.id = ce.linked_page_id LEFT JOIN projects pr ON pr.id = ce.linked_project_id
      WHERE ce.workspace_id = (SELECT id FROM workspaces LIMIT 1) AND ce.start_dt >= ? AND ce.start_dt < ?

      UNION ALL

      SELECT 'planner' AS source, pt.id, pt.title, 'Prazo de Entrega' AS description, pt.due_date AS start_dt, pt.due_date AS end_dt, 1 AS all_day, pr.color AS color,
        CASE WHEN pt.task_type IN ('prova','trabalho','seminario','defesa','prazo','reuniao') THEN pt.task_type ELSE 'outro' END AS event_type,
        pt.page_id AS linked_page_id, pt.project_id AS linked_project_id, p.title AS page_title, pr.name AS project_name, pr.color AS project_color
      FROM planned_tasks pt
      LEFT JOIN projects pr ON pr.id = pt.project_id LEFT JOIN pages p ON p.id = pt.page_id
      WHERE pt.status NOT IN ('done') AND pt.due_date >= ? AND pt.due_date < ?

      UNION ALL

      SELECT 'planner' AS source, wb.id, 'Foco: ' || pt.title AS title, 'Sessão de Foco' AS description, wb.date || 'T09:00:00' AS start_dt, wb.date || 'T10:00:00' AS end_dt, 0 AS all_day, pr.color AS color, 'atividade' AS event_type,
        pt.page_id AS linked_page_id, pt.project_id AS linked_project_id, p.title AS page_title, pr.name AS project_name, pr.color AS project_color
      FROM work_blocks wb
      JOIN planned_tasks pt ON pt.id = wb.task_id
      LEFT JOIN projects pr ON pr.id = pt.project_id LEFT JOIN pages p ON p.id = pt.page_id
      WHERE wb.status != 'missed' AND pt.status NOT IN ('done', 'completed') AND wb.date >= ? AND wb.date < ?

      ORDER BY start_dt
    `, start, next, start, next, start, next)
  })

  api('events:listForPage', async ({ page_id }) =>
    dbAll(`SELECT * FROM calendar_events WHERE linked_page_id = ? ORDER BY start_dt`, page_id)
  )

  api('events:listForProject', async ({ project_id }) =>
    dbAll(`
      SELECT ce.*, p.title AS page_title
      FROM calendar_events ce
      LEFT JOIN pages p ON p.id = ce.linked_page_id
      WHERE ce.linked_project_id = ?
      ORDER BY ce.start_dt
    `, project_id)
  )

  api('events:listUpcoming', async ({ days }) => {
    const now    = new Date().toISOString().slice(0, 10)
    const future = new Date(Date.now() + (days ?? 14) * 86_400_000).toISOString().slice(0, 10)
    return dbAll(`
      SELECT 'calendar' AS source, ce.id, ce.title, ce.description,
        ce.start_dt, ce.end_dt, ce.all_day, ce.color, ce.event_type,
        ce.linked_page_id, ce.linked_project_id,
        p.title AS page_title, pr.name AS project_name, pr.color AS project_color
      FROM calendar_events ce
      LEFT JOIN pages    p  ON p.id  = ce.linked_page_id
      LEFT JOIN projects pr ON pr.id = ce.linked_project_id
      WHERE ce.workspace_id = (SELECT id FROM workspaces LIMIT 1)
        AND date(ce.start_dt) >= ? AND date(ce.start_dt) <= ?

      UNION ALL

      SELECT 'planner' AS source, pt.id, pt.title, pt.task_type AS description,
        pt.due_date AS start_dt, pt.due_date AS end_dt, 1 AS all_day,
        pr.color AS color,
        CASE WHEN pt.task_type IN ('prova','trabalho','seminario','defesa','prazo','reuniao')
          THEN pt.task_type ELSE 'outro' END AS event_type,
        pt.page_id AS linked_page_id, pt.project_id AS linked_project_id,
        p.title AS page_title, pr.name AS project_name, pr.color AS project_color
      FROM planned_tasks pt
      LEFT JOIN projects pr ON pr.id = pt.project_id
      LEFT JOIN pages    p  ON p.id  = pt.page_id
      WHERE pt.status NOT IN ('done')
        AND pt.due_date >= ? AND pt.due_date <= ?

      UNION ALL

      SELECT 'planner' AS source, wb.id, 'Foco: ' || pt.title AS title, 'Sessão de Foco' AS description,
        wb.date || 'T09:00:00' AS start_dt, wb.date || 'T10:00:00' AS end_dt, 0 AS all_day,
        pr.color AS color, 'atividade' AS event_type,
        pt.page_id AS linked_page_id, pt.project_id AS linked_project_id,
        p.title AS page_title, pr.name AS project_name, pr.color AS project_color
      FROM work_blocks wb
      JOIN  planned_tasks pt ON pt.id  = wb.task_id
      LEFT JOIN projects pr  ON pr.id  = pt.project_id
      LEFT JOIN pages    p   ON p.id   = pt.page_id
      WHERE wb.status != 'missed'
        AND pt.status NOT IN ('done', 'completed')
        AND wb.date >= ? AND wb.date <= ?

      ORDER BY start_dt
    `, now, future, now, future, now, future)
  })

  api('events:create', async (data) => {
    const wsId = ((await dbGet(`SELECT id FROM workspaces LIMIT 1`)) as any)?.id ?? 1
    const r = await dbRun(`
      INSERT INTO calendar_events
        (workspace_id, title, description, start_dt, end_dt, all_day, color, event_type, linked_page_id, linked_project_id)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      wsId, data.title, data.description ?? null,
      data.start_dt, data.end_dt ?? null, data.all_day ? 1 : 0,
      data.color ?? null, data.event_type ?? 'outro',
      data.linked_page_id ?? null, data.linked_project_id ?? null
    )
    const eventId = r.lastInsertRowid

    if (data.reminder_minutes != null) {
      const base = data.start_dt.includes('T') ? data.start_dt : `${data.start_dt}T09:00:00`
      const t = new Date(base)
      t.setMinutes(t.getMinutes() - data.reminder_minutes)
      await dbRun(`
        INSERT INTO reminders (title, trigger_at, offset_minutes, linked_event_id, linked_page_id)
        VALUES (?, ?, ?, ?, ?)`,
        data.title, t.toISOString().slice(0, 16),
        data.reminder_minutes, eventId, data.linked_page_id ?? null
      )
    }

    return dbGet(`SELECT * FROM calendar_events WHERE id = ?`, eventId)
  })

  api('events:update', async (data) => {
    const allowed = ['title','description','start_dt','end_dt','all_day','color','event_type','linked_page_id','linked_project_id']
    const cols: string[] = [], vals: any[] = []
    for (const key of allowed) {
      if (data[key] !== undefined) { cols.push(`${key} = ?`); vals.push(data[key]) }
    }
    if (cols.length) await dbRun(`UPDATE calendar_events SET ${cols.join(', ')} WHERE id = ?`, ...vals, data.id)
    return dbGet(`SELECT * FROM calendar_events WHERE id = ?`, data.id)
  })

  api('events:delete', async ({ id }) =>
    dbRun(`DELETE FROM calendar_events WHERE id = ?`, id)
  )

  // ── Lembretes ─────────────────────────────────────────────────────────────

  api('reminders:list', async ({ include_dismissed } = {}) =>
    dbAll(`
      SELECT r.*, ce.event_type, ce.start_dt AS event_start
      FROM reminders r
      LEFT JOIN calendar_events ce ON ce.id = r.linked_event_id
      ${include_dismissed ? '' : 'WHERE r.is_dismissed = 0'}
      ORDER BY r.trigger_at
    `)
  )

  api('reminders:create', async (data) => {
    const r = await dbRun(`
      INSERT INTO reminders (title, trigger_at, offset_minutes, linked_event_id, linked_page_id, priority, project_id)
      VALUES (?, ?, ?, ?, ?, ?, ?)`,
      data.title, data.trigger_at, data.offset_minutes ?? null,
      data.linked_event_id ?? null, data.linked_page_id ?? null,
      data.priority ?? 'medium', data.project_id ?? null
    )
    return dbGet(`SELECT * FROM reminders WHERE id = ?`, r.lastInsertRowid)
  })

  api('reminders:dismiss', async ({ id }) =>
    dbRun(`UPDATE reminders SET is_dismissed = 1 WHERE id = ?`, id)
  )

  api('reminders:delete', async ({ id }) =>
    dbRun(`DELETE FROM reminders WHERE id = ?`, id)
  )

  api('reminders:listForProject', async ({ project_id, include_dismissed }) =>
    dbAll(`
      SELECT r.*, p.title AS page_title, p.icon AS page_icon
      FROM reminders r
      LEFT JOIN pages p ON p.id = r.linked_page_id
      WHERE r.project_id = ?
        ${include_dismissed ? '' : 'AND r.is_dismissed = 0'}
      ORDER BY r.trigger_at ASC
    `, project_id)
  )

  // ── Planejador académico ───────────────────────────────────────────────────

  api('planner:listTasks', async ({ project_id }) =>
    dbAll(`
      SELECT pt.*,
        COALESCE((SELECT SUM(wb.logged_hours) FROM work_blocks wb WHERE wb.task_id = pt.id AND wb.status = 'done'), 0) AS done_hours,
        p.title AS page_title, p.icon AS page_icon
      FROM planned_tasks pt
      LEFT JOIN pages p ON p.id = pt.page_id
      WHERE pt.project_id = ?
      ORDER BY pt.due_date ASC, pt.created_at ASC
    `, project_id)
  )

  api('planner:createTask', async (data) => {
    const r = await dbRun(`
      INSERT INTO planned_tasks
        (project_id, page_id, title, task_type, due_date, estimated_hours, status, priority, spaced_review, parent_task_id)
      VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
    `, data.project_id, data.page_id ?? null, data.title, data.task_type ?? 'atividade',
       data.due_date, data.estimated_hours ?? 1,
       data.priority ?? 'medium', data.spaced_review ?? 0, data.parent_task_id ?? null)
    const taskId = r.lastInsertRowid
    await scheduleGlobalTasks()
    return dbGet(`
      SELECT pt.*,
        COALESCE((SELECT SUM(wb.logged_hours) FROM work_blocks wb WHERE wb.task_id = pt.id AND wb.status = 'done'), 0) AS done_hours,
        p.title AS page_title, p.icon AS page_icon,
        proj.name AS project_name, proj.color AS project_color, proj.icon AS project_icon
      FROM planned_tasks pt
      LEFT JOIN pages p ON p.id = pt.page_id
      LEFT JOIN projects proj ON proj.id = pt.project_id
      WHERE pt.id = ?
    `, taskId)
  })

  api('planner:updateTask', async (data) => {
    const allowed = ['title','task_type','due_date','estimated_hours','page_id','status','priority','spaced_review']
    const cols: string[] = [], vals: any[] = []
    for (const key of allowed) {
      if (data[key] !== undefined) { cols.push(`${key} = ?`); vals.push(data[key]) }
    }
    if (cols.length) {
      cols.push(`updated_at = datetime('now')`)
      await dbRun(`UPDATE planned_tasks SET ${cols.join(', ')} WHERE id = ?`, ...vals, data.id)
    }
    const task = await dbGet(`SELECT * FROM planned_tasks WHERE id = ?`, data.id)
    if (task) await scheduleGlobalTasks()
    return dbGet(`
      SELECT pt.*,
        COALESCE((SELECT SUM(wb.logged_hours) FROM work_blocks wb WHERE wb.task_id = pt.id AND wb.status = 'done'), 0) AS done_hours,
        p.title AS page_title, p.icon AS page_icon,
        proj.name AS project_name, proj.color AS project_color, proj.icon AS project_icon
      FROM planned_tasks pt
      LEFT JOIN pages p ON p.id = pt.page_id
      LEFT JOIN projects proj ON proj.id = pt.project_id
      WHERE pt.id = ?
    `, data.id)
  })

  api('planner:deleteTask', async ({ id }) =>
    dbRun(`DELETE FROM planned_tasks WHERE id = ?`, id)
  )

  api('planner:listBlocks', async ({ task_id }) =>
    dbAll(`SELECT * FROM work_blocks WHERE task_id = ? ORDER BY date ASC`, task_id)
  )

  api('planner:logBlock', async ({ id, logged_hours }) => {
    const block = await dbGet(`SELECT * FROM work_blocks WHERE id = ?`, id)
    if (!block) throw new Error('Bloco não encontrado')
    const capped = Math.min(logged_hours, block.planned_hours)
    const status = capped >= block.planned_hours ? 'done' : 'scheduled'
    await dbRun(`UPDATE work_blocks SET logged_hours = ?, status = ? WHERE id = ?`, capped, status, id)
    await updateTaskStatus(block.task_id)
    return dbGet(`SELECT * FROM work_blocks WHERE id = ?`, id)
  })

  api('planner:updateBlock', async (data) => {
    const allowed = ['date', 'planned_hours']
    const cols: string[] = [], vals: any[] = []
    for (const key of allowed) {
      if (data[key] !== undefined) { cols.push(`${key} = ?`); vals.push(data[key]) }
    }
    if (cols.length) {
      await dbRun(`UPDATE work_blocks SET ${cols.join(', ')} WHERE id = ?`, ...vals, data.id)
    }
    return dbGet(`SELECT * FROM work_blocks WHERE id = ?`, data.id)
  })

  api('planner:schedule', async ({ project_id }) => {
    await scheduleGlobalTasks()
    return { ok: true }
  })

  api('planner:rescheduleAll', async () => {
    const today = new Date().toISOString().slice(0, 10)
    await dbRun(
      `UPDATE work_blocks SET status = 'missed' WHERE date < ? AND status = 'scheduled'`,
      today
    )
    await dbRun(`
      UPDATE planned_tasks SET status = 'overdue', updated_at = datetime('now')
      WHERE due_date < ? AND status IN ('pending','in_progress')
    `, today)
    await scheduleGlobalTasks()
    return { ok: true }
  })

  api('planner:listAllTasks', async ({ include_completed }: { include_completed?: boolean }) => {
    const where = include_completed ? '' : `WHERE pt.status != 'completed'`
    return dbAll(`
      SELECT pt.*,
        COALESCE((SELECT SUM(wb.logged_hours) FROM work_blocks wb
                  WHERE wb.task_id = pt.id AND wb.status = 'done'), 0) AS done_hours,
        pg.title AS page_title, pg.icon AS page_icon,
        proj.name AS project_name, proj.color AS project_color, proj.icon AS project_icon
      FROM planned_tasks pt
      LEFT JOIN pages    pg   ON pg.id   = pt.page_id
      LEFT JOIN projects proj ON proj.id = pt.project_id
      ${where}
      ORDER BY pt.due_date ASC, pt.created_at ASC
    `)
  })

  api('planner:todayBlocks', async (dateInput?: any) => {
    let targetDate: string;

    if (dateInput instanceof Date) {
      targetDate = dateInput.toISOString().slice(0, 10);
    } else if (typeof dateInput === 'string' && dateInput.trim() !== '') {
      targetDate = dateInput.slice(0, 10);
    } else {
      // Agora sabemos que o frontend manda {}, então este fallback é quem salva o dia!
      targetDate = new Date().toISOString().slice(0, 10);
    }

    // Remova os colchetes em volta do targetDate aqui embaixo!
    return dbAll(`
      SELECT wb.*,
        pt.title AS task_title, pt.task_type, pt.due_date, pt.estimated_hours,
        p.name AS project_name, p.color AS project_color, p.icon AS project_icon,
        pg.title AS page_title, pg.icon AS page_icon
      FROM work_blocks wb
      JOIN planned_tasks pt ON pt.id = wb.task_id
      JOIN projects p ON p.id = pt.project_id
      LEFT JOIN pages pg ON pg.id = pt.page_id
      WHERE wb.date = ? AND wb.status != 'missed'
      ORDER BY pt.due_date ASC
    `, targetDate) // <-- Passado direto, sem ser array!
  })

  api('planner:logWork', async (data: { block_id: number, task_id: number, hours: number, start_time?: string, end_time?: string, note?: string }) => {
    // Atualiza o bloco no Planner
    await dbRun(`UPDATE work_blocks SET logged_hours = logged_hours + ?, status = 'done' WHERE id = ?`, data.hours, data.block_id)
    
    // Se a tarefa pertencer a uma página (Disciplina), regista no tempo de estudo da página!
    const task = await dbGet(`SELECT project_id, page_id FROM planned_tasks WHERE id = ?`, data.task_id)
    if (task && task.page_id) {
      const dateStr = data.start_time ? data.start_time.slice(0,10) : new Date().toISOString().slice(0,10)
      await dbRun(`
        INSERT INTO time_sessions (project_id, page_id, duration_minutes, start_time, end_time, note)
        VALUES (?, ?, ?, ?, ?, ?)
      `, task.project_id, task.page_id, Math.round(data.hours * 60), data.start_time || null, data.end_time || null, data.note || 'Foco pelo Planner')
    }
    return { success: true }
  })

  // ── Widgets extras ────────────────────────────────────────────────────────

  api('dashboard:projectsProgress', async () =>
    dbAll(`
      SELECT
        p.id, p.name, p.color, p.icon, p.project_type,
        COUNT(DISTINCT pg.id)  AS total_pages,
        COUNT(DISTINCT CASE
          WHEN LOWER(ppv.value_text) LIKE '%conclu%'
            OR LOWER(ppv.value_text) IN ('done','completed','lido','read')
          THEN pg.id END)      AS done_pages,
        COUNT(DISTINCT pt.id)  AS total_tasks,
        COUNT(DISTINCT CASE WHEN pt.status = 'completed' THEN pt.id END) AS done_tasks
      FROM projects p
      LEFT JOIN pages           pg  ON pg.project_id  = p.id AND pg.is_deleted = 0 AND pg.parent_id IS NULL
      LEFT JOIN project_properties pp ON pp.project_id = p.id AND pp.prop_key = 'status'
      LEFT JOIN page_prop_values ppv  ON ppv.page_id   = pg.id AND ppv.property_id = pp.id
      LEFT JOIN planned_tasks   pt  ON pt.project_id  = p.id
      WHERE p.status = 'active'
      GROUP BY p.id
      ORDER BY p.sort_order, p.name
    `)
  )

  api('dashboard:randomQuote', async () =>
    dbGet(`
      SELECT rq.id, rq.text, rq.location,
             r.title AS reading_title, r.author
      FROM reading_quotes rq
      JOIN readings r ON r.id = rq.reading_id
      ORDER BY RANDOM()
      LIMIT 1
    `)
  )

  // ── Sessões de tempo ──────────────────────────────────────────────────────────

  api('time:list', async ({ project_id }: { project_id: number }) =>
    dbAll(`
      SELECT ts.*, p.title AS page_title, p.icon AS page_icon
      FROM   time_sessions ts
      LEFT   JOIN pages p ON p.id = ts.page_id
      WHERE  ts.project_id = ?
      ORDER  BY ts.started_at DESC
    `, project_id)
  )

  api('time:create', async (d: {
    project_id:   number
    workspace_id: number
    page_id?:     number | null
    duration_min: number
    session_type: string
    notes?:       string | null
    tags?:        string | null
    started_at:   string
    ended_at?:    string | null
  }) => {
    const r = await dbRun(`
      INSERT INTO time_sessions
        (workspace_id, project_id, page_id, duration_min, session_type, notes, tags, started_at, ended_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
      d.workspace_id, d.project_id, d.page_id ?? null,
      d.duration_min, d.session_type ?? 'manual',
      d.notes?.trim() || null, d.tags?.trim() || null,
      d.started_at, d.ended_at ?? null
    )
    return dbGet(`
      SELECT ts.*, p.title AS page_title, p.icon AS page_icon
      FROM   time_sessions ts
      LEFT   JOIN pages p ON p.id = ts.page_id
      WHERE  ts.id = ?
    `, r.lastInsertRowid)
  })

  api('time:delete', async ({ id }: { id: number }) =>
    dbRun('DELETE FROM time_sessions WHERE id = ?', id)
  )

  // ── App Settings (data/settings.json) ────────────────────────────────────────

  ipcMain.handle('appSettings:getAll', () => getAllSettings())

  ipcMain.handle('appSettings:get', (_e, { key }: { key: keyof AppSettings }) =>
    getSetting(key) ?? null
  )

  ipcMain.handle('appSettings:set', (_e, { key, value }: { key: keyof AppSettings; value: AppSettings[keyof AppSettings] }) => {
    setSetting(key, value as any)
  })

  // ── Sincronização manual ──────────────────────────────────────────────────────

  ipcMain.handle('db:sync', async () => {
    const { syncClient } = await import('./database')
    try {
      await syncClient()
      return { ok: true }
    } catch (err: any) {
      return { ok: false, error: err.message }
    }
  })

}
