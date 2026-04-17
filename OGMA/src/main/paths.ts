import { app } from 'electron'
import path from 'path'
import fs from 'fs'
import os from 'os'

// Em produção: pasta do executável. Em dev: raiz do projeto.
const ROOT = app.isPackaged
  ? path.dirname(app.getPath('exe'))
  : path.resolve(__dirname, '..', '..')

function readEcosystemSection(app: string): Record<string, string> | null {
  try {
    const candidates = [
      path.join(os.homedir(), 'AppData', 'Roaming', 'ecosystem', 'ecosystem.json'),
      path.join(os.homedir(), '.local', 'share', 'ecosystem', 'ecosystem.json'),
    ]
    for (const p of candidates) {
      if (fs.existsSync(p)) {
        const parsed = JSON.parse(fs.readFileSync(p, 'utf-8'))
        return parsed?.[app] ?? null
      }
    }
  } catch { /* ecosystem opcional */ }
  return null
}

const _eco = readEcosystemSection('ogma')

export const DATA_DIR    = _eco?.data_path    || path.join(ROOT, 'data')
export const DB_PATH     = path.join(DATA_DIR, 'ogma.db')
export const UPLOADS_DIR = path.join(DATA_DIR, 'uploads')
export const EXPORTS_DIR = path.join(DATA_DIR, 'exports')
export const LOGS_DIR    = path.join(DATA_DIR, 'logs')

// settings.json: pasta .config/ sincronizada se config_path estiver definido,
// senão cai para dentro de DATA_DIR (migração transparente)
const _configDir = _eco?.config_path || DATA_DIR
export const SETTINGS = path.join(_configDir, 'settings.json')

export function ensureDirs(): void {
  for (const dir of [DATA_DIR, UPLOADS_DIR, EXPORTS_DIR, LOGS_DIR, _configDir]) {
    fs.mkdirSync(dir, { recursive: true })
  }
}
