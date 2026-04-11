/**
 * OGMA Database — v3 (libsql / Turso)
 *
 * Embedded replica: leitura local (offline-first), escrita sincroniza com Turso Cloud.
 * Se TURSO_URL não estiver definido, funciona em modo local puro (ficheiro SQLite).
 *
 * Variáveis de ambiente (carregar de data/.env antes de chamar getClient):
 *   TURSO_URL   — libsql://ogma-<nome>.turso.io
 *   TURSO_TOKEN — token de autenticação Turso
 */

import { createClient, Client, InArgs } from '@libsql/client'
import { DB_PATH } from './paths'
import { createLogger } from './logger'

const log = createLogger('database')

let _client: Client | null = null
// Garante que todos os chamadores aguardam a inicialização completa
let _initPromise: Promise<Client> | null = null

function toFileUrl(p: string): string {
  return p.startsWith('file:') ? p : `file:${p}`
}

// ── Ciclo de vida ──────────────────────────────────────────────────────────────
export function getClient(): Promise<Client> {
  if (_client) return Promise.resolve(_client)
  if (_initPromise) return _initPromise
  _initPromise = _initClient()
  return _initPromise
}

async function _initClient(): Promise<Client> {
    const localUrl  = toFileUrl(DB_PATH)
    const syncUrl   = process.env.TURSO_URL
    const authToken = process.env.TURSO_TOKEN
    let client: Client

    if (syncUrl && authToken) {
      // Embedded replica — garante o schema local; sync em background
      client = createClient({
        url: localUrl,
        syncUrl: syncUrl,
        authToken: authToken,
        syncInterval: 60000,
      })
      await initSchema(client)
      await seedDefaults(client)
      // Sync em background após inicialização — não bloqueia o startup
      client.sync().catch(e => log.warn('Sync background falhou', { e }))
    } else {
      // Local puro
      client = createClient({ url: localUrl })
      await client.execute('PRAGMA foreign_keys = ON')
      await initSchema(client)
      await seedDefaults(client)
    }

    await client.execute('PRAGMA foreign_keys = ON')
    _client = client
    log.info('Cliente libsql aberto', {
      local: DB_PATH,
      sync: syncUrl ?? 'local-only',
      mode: syncUrl ? 'embedded-replica' : 'local'
    })
    log.info('Banco pronto')
    return _client
}

export function closeClient(): void {
  if (_client) {
    _client.close()
    _client = null
    log.info('Cliente fechado')
  }
}

export async function syncClient(): Promise<void> {
  if (_client && process.env.TURSO_URL) {
    await _client.sync()
    log.info('Sync concluído')
  }
}

// ── Helpers assíncronos ────────────────────────────────────────────────────────

export type DbRunResult = { lastInsertRowid: number; rowsAffected: number }

export async function dbGet<T = any>(sql: string, ...args: any[]): Promise<T | null> {
  const c = await getClient()
  const r = await c.execute({ sql, args: args as InArgs })
  return (r.rows[0] as unknown as T) ?? null
}

export async function dbAll<T = any>(sql: string, ...args: any[]): Promise<T[]> {
  const c = await getClient()
  const r = await c.execute({ sql, args: args as InArgs })
  return r.rows as unknown as T[]
}

export async function dbRun(sql: string, ...args: any[]): Promise<DbRunResult> {
  const c = await getClient()
  const r = await c.execute({ sql, args: args as InArgs })
  return {
    lastInsertRowid: Number(r.lastInsertRowid ?? 0),
    rowsAffected:   r.rowsAffected,
  }
}

// ── Schema ─────────────────────────────────────────────────────────────────────

async function initSchema(client: Client): Promise<void> {
  // Sem nuclear migration: schema já está em v2 e CREATE TABLE IF NOT EXISTS
  // é idempotente. PRAGMA user_version = N não é suportado pelo Turso remoto.
  await createTables(client)
  await runIncrementalMigrations(client)
}

async function createTables(client: Client): Promise<void> {
  // Executar cada CREATE TABLE individualmente — batch DDL pode falhar em algumas
  // implementações libsql com FTS5 virtual tables
  const statements = [
    // ── Core ────────────────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS workspaces (
      id                 INTEGER PRIMARY KEY AUTOINCREMENT,
      name               TEXT NOT NULL DEFAULT 'Meu Workspace',
      icon               TEXT DEFAULT '✦',
      accent_color       TEXT DEFAULT '#b8860b',
      dashboard_settings TEXT, -- <--- NOVA COLUNA AQUI
      created_at         TEXT DEFAULT (datetime('now')),
      updated_at         TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS projects (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      name         TEXT NOT NULL,
      description  TEXT,
      icon         TEXT,
      color        TEXT,
      project_type TEXT NOT NULL DEFAULT 'custom',
      subcategory  TEXT,
      status       TEXT DEFAULT 'active',
      date_start   TEXT,
      date_end     TEXT,
      sort_order   INTEGER DEFAULT 0,
      created_at   TEXT DEFAULT (datetime('now')),
      updated_at   TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS pages (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      parent_id   INTEGER REFERENCES pages(id) ON DELETE CASCADE,
      title       TEXT NOT NULL DEFAULT 'Sem título',
      icon        TEXT,
      cover       TEXT,
      cover_color TEXT,
      body_json   TEXT,
      sort_order  INTEGER DEFAULT 0,
      is_deleted  INTEGER DEFAULT 0,
      created_at  TEXT DEFAULT (datetime('now')),
      updated_at  TEXT DEFAULT (datetime('now'))
    )`,
    // ── Propriedades de Projeto ──────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS project_properties (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      name        TEXT NOT NULL,
      prop_key    TEXT NOT NULL,
      prop_type   TEXT NOT NULL,
      is_required INTEGER DEFAULT 0,
      is_built_in INTEGER DEFAULT 0,
      sort_order  INTEGER DEFAULT 0,
      created_at  TEXT DEFAULT (datetime('now')),
      UNIQUE (project_id, prop_key)
    )`,
    `CREATE TABLE IF NOT EXISTS prop_options (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      property_id INTEGER NOT NULL REFERENCES project_properties(id) ON DELETE CASCADE,
      label       TEXT NOT NULL,
      color       TEXT,
      sort_order  INTEGER DEFAULT 0
    )`,
    `CREATE TABLE IF NOT EXISTS page_prop_values (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      page_id     INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      property_id INTEGER NOT NULL REFERENCES project_properties(id) ON DELETE CASCADE,
      value_text  TEXT,
      value_num   REAL,
      value_bool  INTEGER,
      value_date  TEXT,
      value_date2 TEXT,
      value_json  TEXT,
      UNIQUE (page_id, property_id)
    )`,
    // ── Views de Projeto ─────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS project_views (
      id                   INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id           INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      name                 TEXT NOT NULL,
      view_type            TEXT NOT NULL,
      group_by_property_id INTEGER REFERENCES project_properties(id) ON DELETE SET NULL,
      date_property_id     INTEGER REFERENCES project_properties(id) ON DELETE SET NULL,
      visible_props_json   TEXT,
      filter_json          TEXT,
      sort_json            TEXT,
      include_subpages     INTEGER DEFAULT 0,
      is_default           INTEGER DEFAULT 0,
      sort_order           INTEGER DEFAULT 0
    )`,
    // ── Tags globais ─────────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS tags (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      name         TEXT NOT NULL,
      color        TEXT
    )`,
    `CREATE TABLE IF NOT EXISTS page_tags (
      page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
      tag_id  INTEGER REFERENCES tags(id) ON DELETE CASCADE,
      PRIMARY KEY (page_id, tag_id)
    )`,
    // ── Versionamento e backlinks ────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS page_backlinks (
      source_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      target_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      PRIMARY KEY (source_page_id, target_page_id)
    )`,
    `CREATE TABLE IF NOT EXISTS page_versions (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      page_id    INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      body_json  TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    )`,
    // ── Calendário global ────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS calendar_events (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id   INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      title          TEXT NOT NULL,
      description    TEXT,
      start_dt       TEXT NOT NULL,
      end_dt         TEXT,
      all_day        INTEGER DEFAULT 0,
      color          TEXT,
      linked_page_id INTEGER REFERENCES pages(id) ON DELETE SET NULL,
      created_at     TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS reminders (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      title           TEXT NOT NULL,
      trigger_at      TEXT NOT NULL,
      offset_minutes  INTEGER,
      linked_event_id INTEGER REFERENCES calendar_events(id) ON DELETE CASCADE,
      linked_page_id  INTEGER REFERENCES pages(id) ON DELETE SET NULL,
      is_dismissed    INTEGER DEFAULT 0,
      created_at      TEXT DEFAULT (datetime('now'))
    )`,
    // ── Recursos e leituras ──────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS resources (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id  INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      project_id    INTEGER REFERENCES projects(id) ON DELETE SET NULL,
      title         TEXT NOT NULL,
      resource_type TEXT,
      url           TEXT,
      description   TEXT,
      tags_json     TEXT,
      created_at    TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS readings (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      resource_id  INTEGER REFERENCES resources(id) ON DELETE SET NULL,
      title        TEXT NOT NULL,
      reading_type TEXT DEFAULT 'book',
      author       TEXT,
      publisher    TEXT,
      year         INTEGER,
      isbn         TEXT,
      cover_path   TEXT,
      status       TEXT DEFAULT 'want',
      rating       INTEGER,
      current_page INTEGER DEFAULT 0,
      total_pages  INTEGER,
      date_start   TEXT,
      date_end     TEXT,
      review       TEXT,
      api_source   TEXT,
      api_id       TEXT,
      created_at   TEXT DEFAULT (datetime('now')),
      updated_at   TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS reading_tags (
      reading_id INTEGER REFERENCES readings(id) ON DELETE CASCADE,
      tag_id     INTEGER REFERENCES tags(id) ON DELETE CASCADE,
      PRIMARY KEY (reading_id, tag_id)
    )`,
    `CREATE TABLE IF NOT EXISTS reading_notes (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      reading_id INTEGER NOT NULL REFERENCES readings(id) ON DELETE CASCADE,
      chapter    TEXT,
      content    TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS reading_quotes (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      reading_id INTEGER NOT NULL REFERENCES readings(id) ON DELETE CASCADE,
      text       TEXT NOT NULL,
      location   TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS reading_links (
      reading_id INTEGER NOT NULL REFERENCES readings(id) ON DELETE CASCADE,
      page_id    INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      PRIMARY KEY (reading_id, page_id)
    )`,
    `CREATE TABLE IF NOT EXISTS reading_goals (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      year         INTEGER NOT NULL,
      target       INTEGER NOT NULL
    )`,
    // ── Sessões de tempo ─────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS time_sessions (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
      page_id      INTEGER REFERENCES pages(id) ON DELETE SET NULL,
      project_id   INTEGER REFERENCES projects(id) ON DELETE SET NULL,
      duration_min INTEGER NOT NULL,
      session_type TEXT DEFAULT 'manual',
      notes        TEXT,
      started_at   TEXT NOT NULL,
      ended_at     TEXT
    )`,
    // ── Configurações ────────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS settings (
      key   TEXT PRIMARY KEY,
      value TEXT
    )`,
    // ── Busca full-text ──────────────────────────────────────────────────────
    `CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
      entity_type, entity_id, project_id, title, body
    )`,
  ]

  // Separar FTS5 (virtual table) do resto — batch DDL pode rejeitar virtual tables
  const fts5 = statements.find(s => s.includes('fts5'))
  const regular = statements.filter(s => !s.includes('fts5'))
  await client.batch(regular.map(sql => ({ sql, args: [] })), 'write')
  if (fts5) try { await client.execute(fts5) } catch { /* já existe */ }
}

async function runIncrementalMigrations(client: Client): Promise<void> {
  // Cada migration é idempotente — falha silenciosa se já existir
  const migrations = [
    `ALTER TABLE workspaces ADD COLUMN dashboard_settings TEXT`, // <--- NOVA MIGRATION AQUI
    `ALTER TABLE readings ADD COLUMN resource_id INTEGER REFERENCES resources(id) ON DELETE SET NULL`,
    `ALTER TABLE resources ADD COLUMN metadata_json TEXT`,
    `ALTER TABLE projects ADD COLUMN semester TEXT`,
    `CREATE TABLE IF NOT EXISTS resource_pages (
      resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
      page_id     INTEGER NOT NULL REFERENCES pages(id)     ON DELETE CASCADE,
      PRIMARY KEY (resource_id, page_id)
    )`,
    `CREATE TABLE IF NOT EXISTS reading_sessions (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      reading_id   INTEGER NOT NULL REFERENCES readings(id) ON DELETE CASCADE,
      date         TEXT NOT NULL DEFAULT (date('now')),
      page_start   INTEGER NOT NULL DEFAULT 0,
      page_end     INTEGER NOT NULL DEFAULT 0,
      duration_min INTEGER,
      notes        TEXT,
      created_at   TEXT DEFAULT (datetime('now'))
    )`,
    `ALTER TABLE calendar_events ADD COLUMN event_type TEXT DEFAULT 'outro'`,
    `ALTER TABLE calendar_events ADD COLUMN linked_project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL`,
    `CREATE TABLE IF NOT EXISTS page_prerequisites (
      page_id         INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      prerequisite_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
      PRIMARY KEY (page_id, prerequisite_id)
    )`,
    `ALTER TABLE readings ADD COLUMN progress_type TEXT DEFAULT 'pages'`,
    `ALTER TABLE readings ADD COLUMN progress_percent INTEGER DEFAULT 0`,
    `ALTER TABLE reading_sessions ADD COLUMN percent_end INTEGER`,
    `CREATE TABLE IF NOT EXISTS planned_tasks (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      page_id         INTEGER REFERENCES pages(id) ON DELETE SET NULL,
      title           TEXT NOT NULL,
      task_type       TEXT DEFAULT 'atividade',
      due_date        TEXT NOT NULL,
      estimated_hours REAL NOT NULL DEFAULT 1,
      status          TEXT DEFAULT 'pending',
      created_at      TEXT DEFAULT (datetime('now')),
      updated_at      TEXT DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS work_blocks (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id       INTEGER NOT NULL REFERENCES planned_tasks(id) ON DELETE CASCADE,
      date          TEXT NOT NULL,
      planned_hours REAL NOT NULL DEFAULT 1,
      logged_hours  REAL DEFAULT 0,
      status        TEXT DEFAULT 'scheduled',
      created_at    TEXT DEFAULT (datetime('now'))
    )`,
    `ALTER TABLE time_sessions ADD COLUMN tags TEXT`,
    `ALTER TABLE planned_tasks ADD COLUMN priority TEXT DEFAULT 'medium'`,
    `ALTER TABLE planned_tasks ADD COLUMN spaced_review INTEGER DEFAULT 0`,
    `ALTER TABLE planned_tasks ADD COLUMN parent_task_id INTEGER REFERENCES planned_tasks(id) ON DELETE SET NULL`,
    `ALTER TABLE reminders ADD COLUMN priority TEXT DEFAULT 'medium'`,
    `ALTER TABLE reminders ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE`,
    `ALTER TABLE projects ADD COLUMN institution TEXT`,
  ]

  for (const sql of migrations) {
    try { await client.execute(sql) } catch { /* já existe */ }
  }

  await ensureAcademicProperties(client)
}

async function ensureAcademicProperties(client: Client): Promise<void> {
  try {
    const result = await client.execute(
      `SELECT id FROM projects WHERE project_type = 'academic'`
    )
    for (const row of result.rows) {
      const pid = Number(row[0])

      // Propriedade "Código"
      const hasCodigo = await client.execute({
        sql:  `SELECT id FROM project_properties WHERE project_id = ? AND prop_key = 'codigo'`,
        args: [pid],
      })
      if (hasCodigo.rows.length === 0) {
        await client.execute({
          sql:  `INSERT INTO project_properties (project_id, name, prop_key, prop_type, is_built_in, sort_order) VALUES (?, 'Código', 'codigo', 'text', 1, 0)`,
          args: [pid],
        })
      }

      // Propriedade "Trimestre"
      const hasTrimestre = await client.execute({
        sql:  `SELECT id FROM project_properties WHERE project_id = ? AND prop_key = 'trimestre'`,
        args: [pid],
      })
      if (hasTrimestre.rows.length === 0) {
        const year = new Date().getFullYear()
        const r = await client.execute({
          sql:  `INSERT INTO project_properties (project_id, name, prop_key, prop_type, is_built_in, sort_order) VALUES (?, 'Trimestre', 'trimestre', 'select', 1, 1)`,
          args: [pid],
        })
        const propId = Number(r.lastInsertRowid)
        const labels = [
          `${year - 1}.1`, `${year - 1}.2`, `${year - 1}.3`, `${year - 1}.4`,
          `${year}.1`,     `${year}.2`,     `${year}.3`,     `${year}.4`,
          `${year + 1}.1`, `${year + 1}.2`, `${year + 1}.3`, `${year + 1}.4`,
        ]
        for (let i = 0; i < labels.length; i++) {
          await client.execute({
            sql:  `INSERT INTO prop_options (property_id, label, color, sort_order) VALUES (?, ?, null, ?)`,
            args: [propId, labels[i], i],
          })
        }
      }
    }
  } catch { /* falha silenciosa */ }
}

async function seedDefaults(client: Client): Promise<void> {
  const result = await client.execute('SELECT id FROM workspaces LIMIT 1')
  if (result.rows.length > 0) return

  log.info('Criando workspace padrão')
  await client.execute({
    sql:  `INSERT INTO workspaces (name, icon, accent_color) VALUES ('Meu Workspace', '✦', '#b8860b')`,
    args: [],
  })
}
