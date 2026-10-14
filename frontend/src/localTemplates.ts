import { z } from 'zod'
import { raw } from './api'

type PermissionMode = 'read' | 'readwrite'
declare global {
  interface FileSystemHandle {
    queryPermission(options: { mode: PermissionMode }): Promise<PermissionState>
    requestPermission(options: { mode: PermissionMode }): Promise<PermissionState>
  }
  interface Window {
    showDirectoryPicker?: (options: { mode: PermissionMode; startIn?: FileSystemHandle }) => Promise<FileSystemDirectoryHandle>
  }
}

export type TemplateKind = 'xlsx' | 'docx'
export const templateNames: Record<TemplateKind, string> = { xlsx: '查验台账.xlsx', docx: '检验报告.docx' }
const templateKinds: TemplateKind[] = ['xlsx', 'docx']
const maxTemplateBytes = 10 * 1024 * 1024
const permissionMessage = '无法读取个人模板目录。请到“我的模板”点击“打开模板目录选择器”重新授权，或明确选择“使用服务器默认模板”。'

const folderSchema = z.object({
  id: z.string(),
  handle: z.custom<FileSystemDirectoryHandle>(value => typeof FileSystemDirectoryHandle !== 'undefined' && value instanceof FileSystemDirectoryHandle),
  baselines: z.object({ xlsx: z.string(), docx: z.string() }),
})
const settingSchema = z.object({ activeId: z.string().nullable(), folders: z.array(folderSchema) })
type Folder = z.infer<typeof folderSchema>
type Setting = z.infer<typeof settingSchema>

export function supportsLocalTemplates(): boolean {
  return window.isSecureContext && typeof window.showDirectoryPicker === 'function'
}

async function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('personal-local-templates', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('users')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error('浏览器无法保存个人模板设置，请允许此网站使用本地存储。'))
  })
}

async function loadSetting(userId: number): Promise<Setting> {
  const database = await openDatabase()
  try {
    const value: unknown = await new Promise((resolve, reject) => {
      const request: IDBRequest<unknown> = database.transaction('users').objectStore('users').get(userId)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(new Error('无法读取个人模板设置，请重新打开“我的模板”。'))
    })
    if (value === undefined) return { activeId: null, folders: [] }
    return settingSchema.parse(value)
  } finally { database.close() }
}

async function saveSetting(userId: number, setting: Setting): Promise<void> {
  const database = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction('users', 'readwrite')
      transaction.objectStore('users').put(setting, userId)
      transaction.oncomplete = () => resolve()
      transaction.onerror = transaction.onabort = () => reject(new Error('个人模板设置未能保存，请允许此网站使用本地存储后重试。'))
    })
  } finally { database.close() }
}

function activeFolder(setting: Setting): Folder | null {
  if (setting.activeId === null) return null
  const folder = setting.folders.find(entry => entry.id === setting.activeId)
  if (!folder) throw new Error('个人模板目录设置无法读取，请在“我的模板”重新选择目录。')
  return folder
}

export async function selectedTemplateDirectory(userId: number): Promise<FileSystemDirectoryHandle | null> {
  return activeFolder(await loadSetting(userId))?.handle || null
}

async function requirePermission(handle: FileSystemDirectoryHandle, mode: PermissionMode): Promise<void> {
  try {
    if (await handle.queryPermission({ mode }) === 'granted') return
    if (navigator.userActivation.isActive && await handle.requestPermission({ mode }) === 'granted') return
  } catch { /* The browser can reject a prompt after transient activation expires. */ }
  throw new Error(permissionMessage)
}

async function findFile(directory: FileSystemDirectoryHandle, kind: TemplateKind): Promise<FileSystemFileHandle | null> {
  try { return await directory.getFileHandle(templateNames[kind]) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'NotFoundError') return null
    throw error
  }
}

async function digest(bytes: ArrayBuffer): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2, '0')).join('')
}

export async function chooseTemplateDirectory(userId: number, startIn: FileSystemDirectoryHandle | null): Promise<FileSystemDirectoryHandle | null> {
  if (!supportsLocalTemplates() || !window.showDirectoryPicker) throw new Error('选择本机目录需要桌面版 Chrome 或 Edge，并通过 HTTPS 或 localhost 访问。仍可使用服务器默认模板。')
  let directory: FileSystemDirectoryHandle
  try {
    // Invoke the OS chooser before any asynchronous storage or network work.
    directory = await window.showDirectoryPicker({ mode: 'readwrite', ...(startIn ? { startIn } : {}) })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return startIn
    throw new Error('无法打开目录选择器，请允许浏览器访问文件夹后重试。')
  }
  await requirePermission(directory, 'readwrite')
  const setting = await loadSetting(userId)
  let previous: Folder | undefined
  for (const folder of setting.folders) {
    if (await folder.handle.isSameEntry(directory)) { previous = folder; break }
  }
  const baselines = previous ? { ...previous.baselines } : { xlsx: '', docx: '' }
  for (const kind of templateKinds) {
    const existing = await findFile(directory, kind)
    if (existing && previous) continue
    const bytes = await (await raw(`/templates/${kind}`)).arrayBuffer()
    baselines[kind] = await digest(bytes)
    // An existing file is never written, including empty or invalid documents.
    if (!existing) {
      const handle = await directory.getFileHandle(templateNames[kind], { create: true })
      const writer = await handle.createWritable()
      try { await writer.write(bytes); await writer.close() }
      catch (error) { await writer.abort().catch(() => undefined); throw error }
    }
  }
  const folder: Folder = { id: previous?.id || crypto.randomUUID(), handle: directory, baselines }
  setting.folders = [...setting.folders.filter(entry => entry.id !== folder.id), folder]
  setting.activeId = folder.id
  await saveSetting(userId, setting)
  return directory
}

export async function useServerTemplates(userId: number): Promise<void> {
  const setting = await loadSetting(userId)
  setting.activeId = null
  await saveSetting(userId, setting)
}

/** Call from the export button: permission requests must retain user activation. */
export async function readExportTemplate(userId: number, kind: TemplateKind): Promise<string | null> {
  const folder = activeFolder(await loadSetting(userId))
  if (!folder) return null
  await requirePermission(folder.handle, 'read')
  try {
    const handle = await findFile(folder.handle, kind)
    if (!handle) return null
    const file = await handle.getFile()
    if (file.size > maxTemplateBytes) throw new Error(`${templateNames[kind]} 超过 10 MiB，请缩小文件，或在“我的模板”选择服务器默认模板。`)
    const bytes = await file.arrayBuffer()
    if (await digest(bytes) === folder.baselines[kind]) return null
    let binary = ''
    const values = new Uint8Array(bytes)
    for (let offset = 0; offset < values.length; offset += 0x8000) {
      binary += String.fromCharCode(...values.subarray(offset, offset + 0x8000))
    }
    return btoa(binary)
  } catch (error) {
    if (error instanceof DOMException) throw new Error(permissionMessage)
    throw error
  }
}
