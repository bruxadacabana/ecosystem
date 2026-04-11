// ============================================================
//  AETHER — Wrapper tipado para commands Tauri
//
//  Por que este wrapper existe:
//    O invoke() do @tauri-apps/api lança exceção quando o Rust
//    retorna Err. Isso força try/catch em todo lugar e perde
//    a tipagem do erro. Este módulo normaliza tudo para
//    TauriResult<T>, permitindo uso seguro sem try/catch externo.
//
//  Uso:
//    const result = await cmd.listProjects()
//    if (!result.ok) {
//      toast.error(result.error.message)
//      return
//    }
//    setProjects(result.data)
// ============================================================

import { invoke as tauriInvoke } from '@tauri-apps/api/core'

import type {
  Annotation,
  AppError,
  Book,
  BookMeta,
  Character,
  ChapterMeta,
  ChapterStatus,
  CustomField,
  Project,
  ProjectType,
  Relationship,
  SnapshotMeta,
  TauriResult,
  TimelineEvent,
  WorldCategory,
  WorldNote,
  WritingSession,
} from '../types'

// ----------------------------------------------------------
//  Utilitário interno: captura exceção do Tauri e normaliza
// ----------------------------------------------------------

async function call<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<TauriResult<T>> {
  try {
    const data = await tauriInvoke<T>(command, args)
    return { ok: true, data }
  } catch (raw) {
    // Tauri serializa AppError como objeto { kind, message }
    if (
      raw !== null &&
      typeof raw === 'object' &&
      'kind' in raw &&
      'message' in raw
    ) {
      return { ok: false, error: raw as AppError }
    }
    // Fallback para erros inesperados (strings, etc.)
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
//  Vault
// ----------------------------------------------------------

export const getVaultPath = (): Promise<TauriResult<string | null>> =>
  call<string | null>('get_vault_path')

export const setVaultPath = (path: string): Promise<TauriResult<void>> =>
  call<void>('set_vault_path', { path })

// ----------------------------------------------------------
//  Projetos
// ----------------------------------------------------------

export const listProjects = (): Promise<TauriResult<Project[]>> =>
  call<Project[]>('list_projects')

export interface CreateProjectInput {
  name: string
  projectType: ProjectType
  description?: string
  subtitle?: string
  genre?: string
  targetAudience?: string
  language?: string
  tags?: string[]
  hasMagicSystem?: boolean
  techLevel?: string
  inspirations?: string
}

export const createProject = (
  input: CreateProjectInput,
): Promise<TauriResult<Project>> =>
  call<Project>('create_project', {
    name: input.name,
    projectType: input.projectType,
    description: input.description,
    subtitle: input.subtitle,
    genre: input.genre,
    targetAudience: input.targetAudience,
    language: input.language,
    tags: input.tags,
    hasMagicSystem: input.hasMagicSystem,
    techLevel: input.techLevel,
    inspirations: input.inspirations,
  })

export const openProject = (projectId: string): Promise<TauriResult<Project>> =>
  call<Project>('open_project', { projectId })

export const deleteProject = (projectId: string): Promise<TauriResult<void>> =>
  call<void>('delete_project', { projectId })

export const updateProject = (
  projectId: string,
  name?: string,
  description?: string,
): Promise<TauriResult<Project>> =>
  call<Project>('update_project', { projectId, name, description })

// ----------------------------------------------------------
//  Livros
// ----------------------------------------------------------

export const listBooks = (projectId: string): Promise<TauriResult<BookMeta[]>> =>
  call<BookMeta[]>('list_books', { projectId })

export const createBook = (
  projectId: string,
  name: string,
  seriesName?: string,
): Promise<TauriResult<BookMeta>> =>
  call<BookMeta>('create_book', { projectId, name, seriesName })

export const openBook = (
  projectId: string,
  bookId: string,
): Promise<TauriResult<Book>> =>
  call<Book>('open_book', { projectId, bookId })

export const updateBook = (
  projectId: string,
  bookId: string,
  name: string,
  seriesName?: string,
): Promise<TauriResult<BookMeta>> =>
  call<BookMeta>('update_book', { projectId, bookId, name, seriesName })

export const deleteBook = (
  projectId: string,
  bookId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_book', { projectId, bookId })

export const reorderBooks = (
  projectId: string,
  orderedIds: string[],
): Promise<TauriResult<void>> =>
  call<void>('reorder_books', { projectId, orderedIds })

// ----------------------------------------------------------
//  Capítulos
// ----------------------------------------------------------

export const createChapter = (
  projectId: string,
  bookId: string,
  title: string,
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('create_chapter', { projectId, bookId, title })

export const readChapter = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<string>> =>
  call<string>('read_chapter', { projectId, bookId, chapterId })

export const saveChapter = (
  projectId: string,
  bookId: string,
  chapterId: string,
  content: string,
): Promise<TauriResult<void>> =>
  call<void>('save_chapter', { projectId, bookId, chapterId, content })

export const deleteChapter = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_chapter', { projectId, bookId, chapterId })

export const reorderChapters = (
  projectId: string,
  bookId: string,
  orderedIds: string[],
): Promise<TauriResult<void>> =>
  call<void>('reorder_chapters', { projectId, bookId, orderedIds })

export const updateChapterTitle = (
  projectId: string,
  bookId: string,
  chapterId: string,
  title: string,
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('update_chapter_title', { projectId, bookId, chapterId, title })

export const updateChapterStatus = (
  projectId: string,
  bookId: string,
  chapterId: string,
  status: ChapterStatus,
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('update_chapter_status', { projectId, bookId, chapterId, status })

export const updateChapterSynopsis = (
  projectId: string,
  bookId: string,
  chapterId: string,
  synopsis: string | null,
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('update_chapter_synopsis', { projectId, bookId, chapterId, synopsis })

// ----------------------------------------------------------
//  Lixeira
// ----------------------------------------------------------

export const trashChapter = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<void>> =>
  call<void>('trash_chapter', { projectId, bookId, chapterId })

export const restoreChapter = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('restore_chapter', { projectId, bookId, chapterId })

export const listTrash = (
  projectId: string,
  bookId: string,
): Promise<TauriResult<ChapterMeta[]>> =>
  call<ChapterMeta[]>('list_trash', { projectId, bookId })

export const listBooksForTrash = (
  projectId: string,
): Promise<TauriResult<BookMeta[]>> =>
  call<BookMeta[]>('list_books_for_trash', { projectId })

// ----------------------------------------------------------
//  Scratchpad
// ----------------------------------------------------------

export const readScratchpad = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<string>> =>
  call<string>('read_scratchpad', { projectId, bookId, chapterId })

export const saveScratchpad = (
  projectId: string,
  bookId: string,
  chapterId: string,
  content: string,
): Promise<TauriResult<void>> =>
  call<void>('save_scratchpad', { projectId, bookId, chapterId, content })

// ----------------------------------------------------------
//  Personagens (4.1)
// ----------------------------------------------------------

export const listCharacters = (
  projectId: string,
): Promise<TauriResult<Character[]>> =>
  call<Character[]>('list_characters', { projectId })

export const createCharacter = (
  projectId: string,
  name: string,
): Promise<TauriResult<Character>> =>
  call<Character>('create_character', { projectId, name })

export const loadCharacter = (
  projectId: string,
  characterId: string,
): Promise<TauriResult<Character>> =>
  call<Character>('load_character', { projectId, characterId })

export const saveCharacter = (
  projectId: string,
  characterId: string,
  data: {
    name: string
    role: string | null
    description: string | null
    fields: CustomField[]
    imagePath: string | null
    chapterIds: string[]
  },
): Promise<TauriResult<Character>> =>
  call<Character>('save_character', {
    projectId,
    characterId,
    name: data.name,
    role: data.role,
    description: data.description,
    fields: data.fields,
    imagePath: data.imagePath,
    chapterIds: data.chapterIds,
  })

export const deleteCharacter = (
  projectId: string,
  characterId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_character', { projectId, characterId })

// ----------------------------------------------------------
//  Relacionamentos (4.2)
// ----------------------------------------------------------

export const listRelationships = (
  projectId: string,
): Promise<TauriResult<Relationship[]>> =>
  call<Relationship[]>('list_relationships', { projectId })

export const addRelationship = (
  projectId: string,
  fromId: string,
  toId: string,
  kind: string,
  note: string | null,
): Promise<TauriResult<Relationship>> =>
  call<Relationship>('add_relationship', { projectId, fromId, toId, kind, note })

export const updateRelationship = (
  projectId: string,
  relationshipId: string,
  kind: string,
  note: string | null,
): Promise<TauriResult<Relationship>> =>
  call<Relationship>('update_relationship', { projectId, relationshipId, kind, note })

export const deleteRelationship = (
  projectId: string,
  relationshipId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_relationship', { projectId, relationshipId })

// ----------------------------------------------------------
//  Worldbuilding (4.3)
// ----------------------------------------------------------

export const listWorldNotes = (
  projectId: string,
): Promise<TauriResult<WorldNote[]>> =>
  call<WorldNote[]>('list_world_notes', { projectId })

export const createWorldNote = (
  projectId: string,
  name: string,
  category: WorldCategory,
): Promise<TauriResult<WorldNote>> =>
  call<WorldNote>('create_world_note', { projectId, name, category })

export const loadWorldNote = (
  projectId: string,
  noteId: string,
): Promise<TauriResult<WorldNote>> =>
  call<WorldNote>('load_world_note', { projectId, noteId })

export const saveWorldNote = (
  projectId: string,
  noteId: string,
  data: {
    name: string
    category: WorldCategory
    description: string | null
    fields: CustomField[]
    imagePath: string | null
    chapterIds: string[]
  },
): Promise<TauriResult<WorldNote>> =>
  call<WorldNote>('save_world_note', {
    projectId,
    noteId,
    name: data.name,
    category: data.category,
    description: data.description,
    fields: data.fields,
    imagePath: data.imagePath,
    chapterIds: data.chapterIds,
  })

export const deleteWorldNote = (
  projectId: string,
  noteId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_world_note', { projectId, noteId })

// ----------------------------------------------------------
//  Timeline (4.4)
// ----------------------------------------------------------

export const loadTimeline = (
  projectId: string,
): Promise<TauriResult<TimelineEvent[]>> =>
  call<TimelineEvent[]>('load_timeline', { projectId })

export const createTimelineEvent = (
  projectId: string,
  title: string,
  dateLabel: string,
): Promise<TauriResult<TimelineEvent>> =>
  call<TimelineEvent>('create_timeline_event', { projectId, title, dateLabel })

export const saveTimelineEvent = (
  projectId: string,
  eventId: string,
  data: {
    title: string
    dateLabel: string
    description: string | null
    characterIds: string[]
    noteIds: string[]
    chapterIds: string[]
  },
): Promise<TauriResult<TimelineEvent>> =>
  call<TimelineEvent>('save_timeline_event', {
    projectId,
    eventId,
    title: data.title,
    dateLabel: data.dateLabel,
    description: data.description,
    characterIds: data.characterIds,
    noteIds: data.noteIds,
    chapterIds: data.chapterIds,
  })

export const reorderTimeline = (
  projectId: string,
  orderedIds: string[],
): Promise<TauriResult<void>> =>
  call<void>('reorder_timeline', { projectId, orderedIds })

export const deleteTimelineEvent = (
  projectId: string,
  eventId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_timeline_event', { projectId, eventId })

// ----------------------------------------------------------
//  Imagens (4.5)
// ----------------------------------------------------------

export const attachImage = (
  projectId: string,
  entityPrefix: string,
  sourcePath: string,
): Promise<TauriResult<string>> =>
  call<string>('attach_image', { projectId, entityPrefix, sourcePath })

export const loadImage = (
  relativePath: string,
): Promise<TauriResult<string>> =>
  call<string>('load_image', { relativePath })

export const removeImage = (
  relativePath: string,
): Promise<TauriResult<void>> =>
  call<void>('remove_image', { relativePath })

// ----------------------------------------------------------
//  Vínculos capítulo ↔ personagens/notas (4.6)
// ----------------------------------------------------------

export const updateChapterLinks = (
  projectId: string,
  bookId: string,
  chapterId: string,
  characterIds: string[],
  noteIds: string[],
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('update_chapter_links', {
    projectId,
    bookId,
    chapterId,
    characterIds,
    noteIds,
  })

// ----------------------------------------------------------
//  Metas de palavras (5.1)
// ----------------------------------------------------------

export const setChapterWordGoal = (
  projectId: string,
  bookId: string,
  chapterId: string,
  goal: number | null,
): Promise<TauriResult<ChapterMeta>> =>
  call<ChapterMeta>('set_chapter_word_goal', { projectId, bookId, chapterId, goal })

export const setBookWordGoal = (
  projectId: string,
  bookId: string,
  goal: number | null,
): Promise<TauriResult<void>> =>
  call<void>('set_book_word_goal', { projectId, bookId, goal })

// ----------------------------------------------------------
//  Sessões (5.2) e Streak (5.3)
// ----------------------------------------------------------

export const startSession = (
  projectId: string,
  bookId: string,
  chapterId: string,
  wordsAtStart: number,
  goalMinutes?: number,
): Promise<TauriResult<WritingSession>> =>
  call<WritingSession>('start_session', { projectId, bookId, chapterId, wordsAtStart, goalMinutes })

export const endSession = (
  sessionId: string,
  wordsAtEnd: number,
): Promise<TauriResult<WritingSession>> =>
  call<WritingSession>('end_session', { sessionId, wordsAtEnd })

export const listSessions = (
  projectId?: string,
): Promise<TauriResult<WritingSession[]>> =>
  call<WritingSession[]>('list_sessions', { projectId })

export const getWritingStreak = (
  projectId: string,
): Promise<TauriResult<number>> =>
  call<number>('get_writing_streak', { projectId })

// ----------------------------------------------------------
//  Snapshots (5.5)
// ----------------------------------------------------------

export const listSnapshots = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<SnapshotMeta[]>> =>
  call<SnapshotMeta[]>('list_snapshots', { projectId, bookId, chapterId })

export const createSnapshot = (
  projectId: string,
  bookId: string,
  chapterId: string,
  label?: string,
): Promise<TauriResult<SnapshotMeta>> =>
  call<SnapshotMeta>('create_snapshot', { projectId, bookId, chapterId, label })

export const loadSnapshotContent = (
  projectId: string,
  bookId: string,
  snapshotId: string,
): Promise<TauriResult<string>> =>
  call<string>('load_snapshot_content', { projectId, bookId, snapshotId })

export const restoreSnapshot = (
  projectId: string,
  bookId: string,
  chapterId: string,
  snapshotId: string,
): Promise<TauriResult<void>> =>
  call<void>('restore_snapshot', { projectId, bookId, chapterId, snapshotId })

export const deleteSnapshot = (
  projectId: string,
  bookId: string,
  snapshotId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_snapshot', { projectId, bookId, snapshotId })

// ----------------------------------------------------------
//  Anotações inline (5.6)
// ----------------------------------------------------------

export const listAnnotations = (
  projectId: string,
  bookId: string,
  chapterId: string,
): Promise<TauriResult<Annotation[]>> =>
  call<Annotation[]>('list_annotations', { projectId, bookId, chapterId })

export const createAnnotation = (
  projectId: string,
  bookId: string,
  chapterId: string,
  text: string,
  quote: string,
): Promise<TauriResult<Annotation>> =>
  call<Annotation>('create_annotation', { projectId, bookId, chapterId, text, quote })

export const updateAnnotation = (
  projectId: string,
  bookId: string,
  chapterId: string,
  annotationId: string,
  text: string,
  resolved: boolean,
): Promise<TauriResult<Annotation>> =>
  call<Annotation>('update_annotation', { projectId, bookId, chapterId, annotationId, text, resolved })

export const deleteAnnotation = (
  projectId: string,
  bookId: string,
  chapterId: string,
  annotationId: string,
): Promise<TauriResult<void>> =>
  call<void>('delete_annotation', { projectId, bookId, chapterId, annotationId })
