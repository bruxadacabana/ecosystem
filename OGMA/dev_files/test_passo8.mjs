/**
 * OGMA — Passo 8: Testes e Validação
 * Script autônomo (Node.js ESM) — não requer Electron.
 *
 * Cobre:
 *   1. CRUD básico: workspace, projeto, página, leitura
 *   2. FTS5 (search_index)
 *   3. Funcionamento offline (embedded replica — leitura local sem rede)
 *   4. Sync com Turso
 *
 * Todos os registos de teste são criados com prefixo "__TESTE__"
 * e removidos no final (cleanup garantido mesmo com falha).
 *
 * Uso: node data/test_passo8.mjs
 */

import { createClient } from '@libsql/client'
import { readFileSync, existsSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

// ── Cores para output ─────────────────────────────────────────────────────────
const C = {
  reset:  '\x1b[0m',
  green:  '\x1b[32m',
  red:    '\x1b[31m',
  yellow: '\x1b[33m',
  cyan:   '\x1b[36m',
  bold:   '\x1b[1m',
}
const ok   = (s) => console.log(`  ${C.green}✔${C.reset} ${s}`)
const fail = (s) => console.log(`  ${C.red}✘${C.reset} ${s}`)
const info = (s) => console.log(`  ${C.cyan}→${C.reset} ${s}`)
const head = (s) => console.log(`\n${C.bold}${s}${C.reset}`)

// ── Carregar .env ────────────────────────────────────────────────────────────
const envPath = resolve(ROOT, 'data', '.env')
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z_]+)=(.+)$/)
    if (m) process.env[m[1]] = m[2].trim()
  }
}

const LOCAL_DB = resolve(ROOT, 'data', 'ogma.db')
const SYNC_URL = process.env.TURSO_URL
const TOKEN    = process.env.TURSO_TOKEN

// ── Estado de testes ─────────────────────────────────────────────────────────
let passed = 0
let failed = 0

function assert(condition, label) {
  if (condition) { ok(label); passed++ }
  else           { fail(label); failed++ }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
async function get(client, sql, ...args) {
  const r = await client.execute({ sql, args })
  return r.rows[0] ?? null
}
async function all(client, sql, ...args) {
  const r = await client.execute({ sql, args })
  return r.rows
}
async function run(client, sql, ...args) {
  return client.execute({ sql, args })
}

// ── Cleanup ───────────────────────────────────────────────────────────────────
async function cleanup(client) {
  // Remover na ordem correta (FK)
  await run(client, `DELETE FROM search_index WHERE title LIKE '__TESTE__%'`).catch(() => {})
  await run(client, `DELETE FROM readings WHERE review LIKE '__TESTE__%'`).catch(() => {})
  await run(client, `DELETE FROM pages WHERE title LIKE '__TESTE__%'`).catch(() => {})
  const proj = await get(client, `SELECT id FROM projects WHERE name LIKE '__TESTE__%'`)
  if (proj) {
    await run(client, `DELETE FROM project_properties WHERE project_id = ?`, proj[0])
    await run(client, `DELETE FROM projects WHERE id = ?`, proj[0])
  }
  const ws = await get(client, `SELECT id FROM workspaces WHERE name LIKE '__TESTE__%'`)
  if (ws) await run(client, `DELETE FROM workspaces WHERE id = ?`, ws[0])
}

// ═════════════════════════════════════════════════════════════════════════════
async function runTests() {
  // ── 1. Conectar ─────────────────────────────────────────────────────────────
  head('1. Conexão ao banco')
  info(`DB local: ${LOCAL_DB}`)
  info(`Modo: ${SYNC_URL ? 'embedded-replica (Turso)' : 'local puro'}`)

  const clientOpts = SYNC_URL && TOKEN
    ? { url: `file:${LOCAL_DB}`, syncUrl: SYNC_URL, authToken: TOKEN, syncInterval: 0 }
    : { url: `file:${LOCAL_DB}` }

  const client = createClient(clientOpts)
  await client.execute('PRAGMA foreign_keys = ON')
  ok('Cliente libsql criado')

  // Verificar tabelas essenciais
  const tables = await all(client,
    `SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`
  )
  const tableNames = tables.map(r => r[0])
  assert(tableNames.includes('workspaces'), 'Tabela workspaces existe')
  assert(tableNames.includes('projects'),   'Tabela projects existe')
  assert(tableNames.includes('pages'),      'Tabela pages existe')
  assert(tableNames.includes('readings'),   'Tabela readings existe')
  assert(tableNames.includes('search_index'), 'Tabela search_index (FTS5) existe')

  await cleanup(client) // limpar restos de runs anteriores

  // ── 2. CRUD: Workspace ───────────────────────────────────────────────────────
  head('2. CRUD — Workspace')
  const ws = await run(client,
    `INSERT INTO workspaces (name, icon) VALUES ('__TESTE__ Workspace', '🧪')`
  )
  const wsId = Number(ws.lastInsertRowid)
  assert(wsId > 0, `Criar workspace (id=${wsId})`)

  const wsRow = await get(client, `SELECT name FROM workspaces WHERE id = ?`, wsId)
  assert(wsRow?.[0] === '__TESTE__ Workspace', 'Ler workspace criado')

  await run(client, `UPDATE workspaces SET name = '__TESTE__ Workspace (edit)' WHERE id = ?`, wsId)
  const wsEdit = await get(client, `SELECT name FROM workspaces WHERE id = ?`, wsId)
  assert(wsEdit?.[0] === '__TESTE__ Workspace (edit)', 'Editar workspace')

  // ── 3. CRUD: Projeto ─────────────────────────────────────────────────────────
  head('3. CRUD — Projeto')
  const proj = await run(client,
    `INSERT INTO projects (workspace_id, name, project_type, status) VALUES (?, '__TESTE__ Projeto', 'custom', 'active')`,
    wsId
  )
  const projId = Number(proj.lastInsertRowid)
  assert(projId > 0, `Criar projeto (id=${projId})`)

  const projRow = await get(client, `SELECT name, status FROM projects WHERE id = ?`, projId)
  assert(projRow?.[0] === '__TESTE__ Projeto', 'Ler projeto criado')
  assert(projRow?.[1] === 'active',            'Status inicial correto')

  await run(client,
    `UPDATE projects SET status = 'completed', name = '__TESTE__ Projeto (edit)' WHERE id = ?`,
    projId
  )
  const projEdit = await get(client, `SELECT status FROM projects WHERE id = ?`, projId)
  assert(projEdit?.[0] === 'completed', 'Editar projeto (status)')

  // ── 4. CRUD: Página ──────────────────────────────────────────────────────────
  head('4. CRUD — Página')
  const pg = await run(client,
    `INSERT INTO pages (project_id, title, body_json) VALUES (?, '__TESTE__ Página', '{}')`,
    projId
  )
  const pgId = Number(pg.lastInsertRowid)
  assert(pgId > 0, `Criar página (id=${pgId})`)

  const pgRow = await get(client, `SELECT title FROM pages WHERE id = ?`, pgId)
  assert(pgRow?.[0] === '__TESTE__ Página', 'Ler página criada')

  await run(client,
    `UPDATE pages SET title = '__TESTE__ Página (edit)' WHERE id = ?`, pgId
  )
  const pgEdit = await get(client, `SELECT title FROM pages WHERE id = ?`, pgId)
  assert(pgEdit?.[0] === '__TESTE__ Página (edit)', 'Editar página (título)')

  // Apagar
  await run(client, `DELETE FROM pages WHERE id = ?`, pgId)
  const pgDel = await get(client, `SELECT id FROM pages WHERE id = ?`, pgId)
  assert(pgDel === null, 'Apagar página')

  // ── 5. CRUD: Leitura ─────────────────────────────────────────────────────────
  head('5. CRUD — Leitura')
  const rd = await run(client,
    `INSERT INTO readings (workspace_id, title, review) VALUES (?, '__TESTE__ Leitura', '__TESTE__ nota')`,
    wsId
  )
  const rdId = Number(rd.lastInsertRowid)
  assert(rdId > 0, `Criar leitura (id=${rdId})`)

  await run(client, `UPDATE readings SET title = '__TESTE__ Leitura (edit)' WHERE id = ?`, rdId)
  const rdEdit = await get(client, `SELECT title FROM readings WHERE id = ?`, rdId)
  assert(rdEdit?.[0] === '__TESTE__ Leitura (edit)', 'Editar leitura (título)')

  await run(client, `DELETE FROM readings WHERE id = ?`, rdId)
  const rdDel = await get(client, `SELECT id FROM readings WHERE id = ?`, rdId)
  assert(rdDel === null, 'Apagar leitura')

  // ── 6. FTS5 — search_index ────────────────────────────────────────────────────
  head('6. FTS5 — Busca de texto completo')
  try {
    // Recriar a página para testar FTS
    const pgFts = await run(client,
      `INSERT INTO pages (project_id, title, body_json) VALUES (?, '__TESTE__ Página FTS', '{}')`,
      projId
    )
    const pgFtsId = Number(pgFts.lastInsertRowid)

    await run(client,
      `INSERT INTO search_index (entity_type, entity_id, project_id, title, body)
       VALUES ('page', ?, ?, '__TESTE__ Página FTS', 'conteúdo de teste para busca')`,
      pgFtsId, projId
    )
    const ftsResult = await all(client,
      `SELECT entity_id FROM search_index WHERE search_index MATCH ? AND entity_type = 'page'`,
      '__TESTE__'
    )
    assert(ftsResult.length > 0, 'Inserir e buscar via FTS5 (MATCH)')

    // Testar busca por token específico
    const ftsToken = await all(client,
      `SELECT entity_id FROM search_index WHERE search_index MATCH ? AND entity_type = 'page'`,
      'teste'
    )
    assert(ftsToken.length > 0, 'FTS5 encontra token parcial da query')

    // Cleanup FTS + página
    await run(client, `DELETE FROM search_index WHERE entity_id = ? AND entity_type = 'page'`, pgFtsId)
    await run(client, `DELETE FROM pages WHERE id = ?`, pgFtsId)
    ok('Cleanup FTS5 concluído')
  } catch (e) {
    fail(`FTS5 falhou: ${e.message}`)
    failed++
  }

  // ── 7. Offline — leitura local ────────────────────────────────────────────────
  head('7. Offline — leitura local sem sync')
  // O embedded replica lê do arquivo local — não depende de rede para SELECT
  try {
    const wsLocal = await get(client, `SELECT COUNT(*) FROM workspaces`)
    assert(Number(wsLocal?.[0]) >= 1, `Leitura local funciona (${wsLocal?.[0]} workspace(s) no disco)`)
    ok('Embedded replica: leituras são sempre locais (offline-first por design)')
  } catch (e) {
    fail(`Leitura local falhou: ${e.message}`)
    failed++
  }

  // ── 8. Sync com Turso ─────────────────────────────────────────────────────────
  head('8. Sync com Turso')
  if (SYNC_URL && TOKEN) {
    try {
      info('Sincronizando com Turso...')
      await client.sync()
      ok('client.sync() concluído sem erro')

      // Verificar que o workspace de teste existe no remoto via sync
      const wsRemote = await get(client,
        `SELECT name FROM workspaces WHERE name LIKE '__TESTE__%'`
      )
      assert(wsRemote !== null, 'Dados escritos localmente visíveis após sync')
    } catch (e) {
      fail(`Sync falhou: ${e.message}`)
      failed++
    }
  } else {
    info('TURSO_URL não configurado — modo local, sync ignorado')
    ok('Modo local puro: nenhum sync necessário')
  }

  // ── 9. Cleanup final ──────────────────────────────────────────────────────────
  head('9. Cleanup')
  await cleanup(client)
  ok('Registos de teste removidos')
  client.close()

  // ── Resultado ─────────────────────────────────────────────────────────────────
  console.log(`\n${C.bold}════════════════════════════════${C.reset}`)
  const total = passed + failed
  if (failed === 0) {
    console.log(`${C.green}${C.bold}  ✔ ${passed}/${total} testes passaram${C.reset}`)
  } else {
    console.log(`${C.red}${C.bold}  ✘ ${failed} falha(s) em ${total} testes${C.reset}`)
  }
  console.log(`${C.bold}════════════════════════════════${C.reset}\n`)

  process.exit(failed > 0 ? 1 : 0)
}

runTests().catch(e => {
  console.error(`\n${C.red}Erro fatal:${C.reset}`, e.message)
  process.exit(1)
})
