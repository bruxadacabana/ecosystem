// ============================================================
//  HUB — Wrapper IPC
//  Normaliza invoke() para TauriResult<T>.
//  Padrão idêntico ao AETHER.
// ============================================================

import { invoke as tauriInvoke } from '@tauri-apps/api/core'
import type { AppError, TauriResult, EcosystemConfig, Project, Book, ArticleMeta, ArticleContent, OgmaProject, OgmaPage, LogosStatus } from '../types'

async function call<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<TauriResult<T>> {
  try {
    const data = await tauriInvoke<T>(command, args)
    return { ok: true, data }
  } catch (raw) {
    if (
      raw !== null &&
      typeof raw === 'object' &&
      'kind' in raw &&
      'message' in raw
    ) {
      return { ok: false, error: raw as AppError }
    }
    return {
      ok: false,
      error: {
        kind: 'Io',
        message: typeof raw === 'string' ? raw : 'Erro desconhecido.',
      },
    }
  }
}

// ----------------------------------------------------------
//  Config / Ecosystem
// ----------------------------------------------------------

export const readEcosystemConfig = (): Promise<TauriResult<Partial<EcosystemConfig>>> =>
  call<Partial<EcosystemConfig>>('read_ecosystem_config')

export const validatePath = (path: string): Promise<TauriResult<boolean>> =>
  call<boolean>('validate_path', { path })

export const saveEcosystemConfig = (
  updates: Partial<EcosystemConfig>,
): Promise<TauriResult<void>> =>
  call<void>('save_ecosystem_config', { updates })

export const applySyncRoot = (syncRoot: string): Promise<TauriResult<void>> =>
  call<void>('apply_sync_root', { syncRoot })

// ----------------------------------------------------------
//  Módulo Escrita — vault AETHER
// ----------------------------------------------------------

export const listWritingProjects = (vaultPath: string): Promise<TauriResult<Project[]>> =>
  call<Project[]>('list_writing_projects', { vaultPath })

export const listBooks = (vaultPath: string, projectId: string): Promise<TauriResult<Book[]>> =>
  call<Book[]>('list_books', { vaultPath, projectId })

export const readChapter = (
  vaultPath: string,
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<string>> =>
  call<string>('read_chapter', { vaultPath, projectId, bookId, chapterId })

// ----------------------------------------------------------
//  Módulo Leituras — archive KOSMOS
// ----------------------------------------------------------

export const listArticles = (archivePath: string): Promise<TauriResult<ArticleMeta[]>> =>
  call<ArticleMeta[]>('list_articles', { archivePath })

export const readArticle = (
  archivePath: string,
  path: string,
): Promise<TauriResult<ArticleContent>> =>
  call<ArticleContent>('read_article', { archivePath, path })

export const toggleRead = (
  archivePath: string,
  articlePath: string,
): Promise<TauriResult<boolean>> =>
  call<boolean>('toggle_read', { archivePath, articlePath })

// ----------------------------------------------------------
//  Módulo Projetos — OGMA SQLite
// ----------------------------------------------------------

export const listOgmaProjects = (dataPath: string): Promise<TauriResult<OgmaProject[]>> =>
  call<OgmaProject[]>('list_ogma_projects', { dataPath })

export const listProjectPages = (
  dataPath: string,
  projectId: number,
): Promise<TauriResult<OgmaPage[]>> =>
  call<OgmaPage[]>('list_project_pages', { dataPath, projectId })

// ----------------------------------------------------------
//  Módulo Launcher — apps externos
// ----------------------------------------------------------

export const launchApp = (exePath: string): Promise<TauriResult<void>> =>
  call<void>('launch_app', { exePath })

export const isAppRunning = (exePath: string): Promise<TauriResult<boolean>> =>
  call<boolean>('is_app_running', { exePath })

export const getAllAppStatuses = (
  exePaths: Record<string, string>,
): Promise<TauriResult<Record<string, boolean>>> =>
  call<Record<string, boolean>>('get_all_app_statuses', { exePaths })

export const validateExePath = (path: string): Promise<TauriResult<boolean>> =>
  call<boolean>('validate_exe_path', { path })

export const discoverAppExe = (candidates: string[]): Promise<TauriResult<string | null>> =>
  call<string | null>('discover_app_exe', { candidates })

export const autoDiscoverAllExePaths = (): Promise<TauriResult<Record<string, string>>> =>
  call<Record<string, string>>('auto_discover_all_exe_paths')

// ----------------------------------------------------------
//  LOGOS — Status e controle do proxy LLM
// ----------------------------------------------------------

export const logosGetStatus = (): Promise<TauriResult<LogosStatus>> =>
  call<LogosStatus>('logos_get_status')

export const logosSilence = (): Promise<TauriResult<number>> =>
  call<number>('logos_silence')
