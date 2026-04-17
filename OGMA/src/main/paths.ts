import { app } from 'electron'
import path from 'path'
import fs from 'fs'
import os from 'os'

// Em produção: pasta do executável. Em dev: raiz do projeto.
const ROOT = app.isPackaged
  ? path.dirname(app.getPath('exe'))
  : path.resolve(__dirname, '..', '..')

function readEcosystemDataPath(): string | null {
  try {
    const ecosystemJson = path.join(os.homedir(), 'AppData', 'Roaming', 'ecosystem', 'ecosystem.json')
    const raw = fs.readFileSync(ecosystemJson, 'utf-8')
    const parsed = JSON.parse(raw)
    return parsed?.ogma?.data_path || null
  } catch {
    return null
  }
}

const _ecoDataPath = readEcosystemDataPath()

export const DATA_DIR    = _ecoDataPath ?? path.join(ROOT, 'data')
export const DB_PATH     = path.join(DATA_DIR, 'ogma.db')
export const UPLOADS_DIR = path.join(DATA_DIR, 'uploads')
export const EXPORTS_DIR = path.join(DATA_DIR, 'exports')
export const LOGS_DIR    = path.join(DATA_DIR, 'logs')
export const SETTINGS    = path.join(DATA_DIR, 'settings.json')

export function ensureDirs(): void {
  for (const dir of [DATA_DIR, UPLOADS_DIR, EXPORTS_DIR, LOGS_DIR]) {
    fs.mkdirSync(dir, { recursive: true })
  }
}
