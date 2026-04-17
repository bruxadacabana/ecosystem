/**
 * OGMA Database — v4 (better-sqlite3, local-only)
 *
 * SQLite puro local. Sincronização via Proton Drive (pasta configurada pelo HUB).
 * API async preservada para compatibilidade com ipc.ts.
 */

import Database from 'better-sqlite3'
import { DB_PATH } from './paths'
import { createLogger } from './logger'

const log = createLogger('database')

let _db: Database.Database | null = null

// ── Ciclo de vida ──────────────────────────────────────────────────────────────

export async function getClient(): Promise<Database.Database> {
  if (_db) return _db
  _db = new Database(DB_PATH)
  _db.pragma('foreign_keys = ON')
  await initSchema(_db)
  seedDefaults(_db)
  log.info('Banco SQLite aberto', { path: DB_PATH })
  return _db
}

export function closeClient(): void {
  if (_db) {
    _db.close()
    _db = null
    log.info('Banco fechado')
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────────

export type DbRunResult = { lastInsertRowid: number; rowsAffected: number }

export async function dbGet<T = any>(sql: string, ...args: any[]): Promise<T | null> {
  const db = await getClient()
  return (db.prepare(sql).get(...args) as T) ?? null
}

export async function dbAll<T = any>(sql: string, ...args: any[]): Promise<T[]> {
  const db = await getClient()
  return db.prepare(sql).all(...args) as T[]
}

export async function dbRun(sql: string, ...args: any[]): Promise<DbRunResult> {
  const db = await getClient()
  const r = db.prepare(sql).run(...args)
  return {
    lastInsertRowid: Number(r.lastInsertRowid),
    rowsAffected:   r.changes,
  }
}

export async function dbTransaction(statements: { sql: string; args: any[] }[]): Promise<void> {
  const db = await getClient()
  const run = db.transaction((stmts: { sql: string; args: any[] }[]) => {
    for (const { sql, args } of stmts) {
      db.prepare(sql).run(...args)
    }
  })
  run(statements)
}

// ── Schema ─────────────────────────────────────────────────────────────────────

async function initSchema(db: Database.Database): Promise<void> {
  createTables(db)
  runIncrementalMigrations(db)
}

function createTables(db: Database.Database): void {
  const statements = [
    // ── Core ────────────────────────────────────────────────────────────────
    `CREATE TABLE IF NOT EXISTS workspaces (
      id                 INTEGER PRIMARY KEY AUTOINCREMENT,
      name               TEXT NOT NULL DEFAULT 'Meu Workspace',
      icon               TEXT DEFAULT '✦',
      accent_color       TEXT DEFAULT '#b8860b',
      dashboard_settings TEXT,
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

  for (const sql of statements) {
    try { db.exec(sql) } catch { /* já existe */ }
  }
}

function runIncrementalMigrations(db: Database.Database): void {
  const migrations = [
    `ALTER TABLE workspaces ADD COLUMN dashboard_settings TEXT`,
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
    `UPDATE projects SET project_type = 'writing' WHERE project_type = 'creative'`,
    `ALTER TABLE projects ADD COLUMN aether_project_id TEXT`,
  ]

  for (const sql of migrations) {
    try { db.exec(sql) } catch { /* já existe */ }
  }

  ensureAcademicProperties(db)
}

function ensureAcademicProperties(db: Database.Database): void {
  try {
    const projects = db.prepare(`SELECT id FROM projects WHERE project_type = 'academic'`).all() as { id: number }[]
    for (const { id: pid } of projects) {
      const hasCodigo = db.prepare(
        `SELECT id FROM project_properties WHERE project_id = ? AND prop_key = 'codigo'`
      ).get(pid)
      if (!hasCodigo) {
        db.prepare(
          `INSERT INTO project_properties (project_id, name, prop_key, prop_type, is_built_in, sort_order) VALUES (?, 'Código', 'codigo', 'text', 1, 0)`
        ).run(pid)
      }

      const hasTrimestre = db.prepare(
        `SELECT id FROM project_properties WHERE project_id = ? AND prop_key = 'trimestre'`
      ).get(pid)
      if (!hasTrimestre) {
        const year = new Date().getFullYear()
        const r = db.prepare(
          `INSERT INTO project_properties (project_id, name, prop_key, prop_type, is_built_in, sort_order) VALUES (?, 'Trimestre', 'trimestre', 'select', 1, 1)`
        ).run(pid)
        const propId = Number(r.lastInsertRowid)
        const labels = [
          `${year - 1}.1`, `${year - 1}.2`, `${year - 1}.3`, `${year - 1}.4`,
          `${year}.1`,     `${year}.2`,     `${year}.3`,     `${year}.4`,
          `${year + 1}.1`, `${year + 1}.2`, `${year + 1}.3`, `${year + 1}.4`,
        ]
        const insertOpt = db.prepare(
          `INSERT INTO prop_options (property_id, label, color, sort_order) VALUES (?, ?, null, ?)`
        )
        labels.forEach((label, i) => insertOpt.run(propId, label, i))
      }
    }
  } catch { /* falha silenciosa */ }
}

function seedDefaults(db: Database.Database): void {
  const exists = db.prepare('SELECT id FROM workspaces LIMIT 1').get()
  if (exists) return
  log.info('Criando workspace padrão')
  db.prepare(
    `INSERT INTO workspaces (name, icon, accent_color) VALUES ('Meu Workspace', '✦', '#b8860b')`
  ).run()
}
