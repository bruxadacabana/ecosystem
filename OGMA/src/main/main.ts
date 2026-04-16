import { app, BrowserWindow, shell } from 'electron'
import path from 'path'
import { ensureDirs } from './paths'
import { getClient, closeClient, syncClient } from './database'
import { registerIpcHandlers } from './ipc'
import { startReminderScheduler } from './scheduler'
import { createLogger, setupGlobalErrorHandlers } from './logger'
import { initSettings } from './settings'

const log = createLogger('main')
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

const ICON_PATH = app.isPackaged
  ? path.join(path.dirname(app.getPath('exe')), 'assets', 'ogma.ico')
  : path.resolve(__dirname, '..', '..', 'assets', 'ogma.ico')

let mainWindow: BrowserWindow | null = null

// MUDANÇA 1: Agora a função retorna o BrowserWindow criado
function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    icon: ICON_PATH,
    backgroundColor: '#F5F0E8',
    titleBarStyle: 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  mainWindow = win

  if (isDev) {
    win.loadURL('http://localhost:5175')
  } else {
    win.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'))
  }

  win.once('ready-to-show', () => {
    win.show()
  })

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  return win
}

// Compatibilidade no Linux
app.commandLine.appendSwitch('disable-gpu-vsync')

app.whenReady().then(async () => {
  setupGlobalErrorHandlers()
  ensureDirs()
  log.info('OGMA iniciando', { version: '0.1.0', platform: process.platform })

  // Carregar credenciais Turso
  try {
    const dotenv = await import('dotenv')
    const { DATA_DIR } = await import('./paths')
    dotenv.config({ path: path.join(DATA_DIR, '.env') })
  } catch { /* dotenv opcional */ }

  initSettings()
  registerIpcHandlers()
  startReminderScheduler()

  // Iniciar janela e fluxo de sincronia
  log.info('Criando janela principal')
  const mainWin = createWindow()
  iniciarFluxoSincronia(mainWin)
})

// FUNÇÃO DE SINCRONIA: Envia o status para o Splash no Renderer
async function iniciarFluxoSincronia(win: BrowserWindow) {
  const notifySplash = (msg: string) => {
    if (win && !win.isDestroyed()) {
      win.webContents.send('splash-status', msg)
    }
  }

  // Espera o React carregar para começar a narrar
  setTimeout(async () => {
    try {
      notifySplash("Conectando ao repositório local...")
      await getClient() 

      notifySplash("A biblioteca universal está atualizada.")
    } catch (dbError) {
      log.error('Falha crítica no banco:', { error: String(dbError) })
      notifySplash("Erro ao acessar a sabedoria local.")
    }
  }, 500)
}

// --- EVENTOS DE CICLO DE VIDA ---

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    const newWin = createWindow()
    iniciarFluxoSincronia(newWin)
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', async () => {
  log.info('OGMA encerrando')
  await syncClient().catch(() => {})
  closeClient()
})