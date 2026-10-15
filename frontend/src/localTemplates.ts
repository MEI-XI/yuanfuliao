import { z } from 'zod'
import { raw } from './api'

export type TemplateKind = 'xlsx' | 'docx'
export const templateNames: Record<TemplateKind, string> = { xlsx: '查验台账.xlsx', docx: '检验报告.docx' }
export const templateFormats: Record<TemplateKind, string[]> = {
  xlsx: ['.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xltm', '.ods', '.csv', '.xml'],
  docx: ['.doc', '.docx', '.docm', '.dot', '.dotx', '.dotm', '.rtf', '.odt', '.xml'],
}
const templateKinds: TemplateKind[] = ['xlsx', 'docx']
const maxTemplateBytes = 10 * 1024 * 1024
const legacyMessage = '旧模板目录暂时无法读取，请重新选择模板文件，或恢复默认模板。'
interface LegacyDirectory extends FileSystemDirectoryHandle {
  queryPermission(options: { mode: 'read' }): Promise<PermissionState>
}
const directorySchema = z.custom<LegacyDirectory>(value => typeof value === 'object' && value !== null && 'getFileHandle' in value && typeof value.getFileHandle === 'function' && 'queryPermission' in value && typeof value.queryPermission === 'function')
const personalSchema = z.object({ source: z.literal('personal'), name: z.string(), selectedAt: z.string(), base64: z.string() })
const fileSchema = z.discriminatedUnion('source', [personalSchema, z.object({ source: z.literal('legacy'), handle: directorySchema, baseline: z.string().optional() })])
const settingSchema = z.object({ version: z.literal(2), files: z.object({ xlsx: fileSchema.nullable(), docx: fileSchema.nullable() }) })
const legacySchema = z.object({
  activeId: z.string().nullable(),
  folders: z.array(z.object({ id: z.string(), handle: directorySchema, baselines: z.object({ xlsx: z.string(), docx: z.string() }).optional() })),
  activeSnapshot: z.boolean().default(false),
  snapshot: z.object({ files: z.object({ xlsx: z.object({ base64: z.string(), baseline: z.string().optional() }).nullable(), docx: z.object({ base64: z.string(), baseline: z.string().optional() }).nullable() }) }).nullable().default(null),
})
type Setting = z.infer<typeof settingSchema>
export type TemplateSource = { source: 'server' } | z.infer<typeof personalSchema> | { source: 'legacy'; message: string }
export type TemplateSources = Record<TemplateKind, TemplateSource>

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
  let value: unknown
  try {
    value = await new Promise((resolve, reject) => {
      const request: IDBRequest<unknown> = database.transaction('users').objectStore('users').get(userId)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(new Error('无法读取个人模板设置，请重新打开“我的模板”。'))
    })
  } finally { database.close() }
  const empty: Setting = { version: 2, files: { xlsx: null, docx: null } }
  if (value === undefined) return empty
  const current = settingSchema.safeParse(value)
  if (current.success) return current.data
  const old = legacySchema.safeParse(value)
  if (!old.success) throw new Error('个人模板设置无法读取，请重新选择模板文件。')
  for (const kind of templateKinds) {
    if (old.data.activeSnapshot && old.data.snapshot) {
      const file = old.data.snapshot.files[kind]
      if (file && file.base64 !== file.baseline) empty.files[kind] = { source: 'personal', name: templateNames[kind], selectedAt: '', base64: file.base64 }
    } else {
      const folder = old.data.folders.find(entry => entry.id === old.data.activeId)
      if (folder) empty.files[kind] = { source: 'legacy', handle: folder.handle, baseline: folder.baselines?.[kind] }
    }
  }
  await saveSetting(userId, empty)
  return empty
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

function toBase64(bytes: ArrayBuffer): string {
  let binary = ''
  const values = new Uint8Array(bytes)
  for (let offset = 0; offset < values.length; offset += 0x8000) binary += String.fromCharCode(...values.subarray(offset, offset + 0x8000))
  return btoa(binary)
}

async function migrateDirectoryFile(setting: Setting, kind: TemplateKind): Promise<boolean> {
  const stored = setting.files[kind]
  if (stored?.source !== 'legacy') return false
  if (await stored.handle.queryPermission({ mode: 'read' }) !== 'granted') throw new Error(legacyMessage)
  try {
    const file = await (await stored.handle.getFileHandle(templateNames[kind])).getFile()
    if (file.size > maxTemplateBytes) throw new Error('旧模板超过 10 MiB，请重新选择文件。')
    const bytes = await file.arrayBuffer()
    const hash = stored.baseline && crypto.subtle ? Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2, '0')).join('') : null
    setting.files[kind] = hash && hash === stored.baseline ? null : { source: 'personal', name: file.name, selectedAt: '', base64: toBase64(bytes) }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'NotFoundError') setting.files[kind] = null
    else throw error
  }
  return true
}

export async function selectedTemplateSources(userId: number): Promise<TemplateSources> {
  const setting = await loadSetting(userId)
  const sources: TemplateSources = { xlsx: { source: 'server' }, docx: { source: 'server' } }
  let changed = false
  for (const kind of templateKinds) {
    try { changed = await migrateDirectoryFile(setting, kind) || changed }
    catch { sources[kind] = { source: 'legacy', message: legacyMessage }; continue }
    const file = setting.files[kind]
    if (file?.source === 'personal') sources[kind] = file
  }
  if (changed) await saveSetting(userId, setting)
  return sources
}

/** Only a successfully validated/converted file replaces the current selection. */
export async function importTemplateFile(userId: number, kind: TemplateKind, file: File): Promise<void> {
  if (file.size > maxTemplateBytes) throw new Error('模板文件超过 10 MiB，请缩小文件后重新选择。')
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!templateFormats[kind].includes(extension)) throw new Error(`请选择支持的 ${kind === 'xlsx' ? 'Excel' : 'Word'} 模板文件。`)
  const body = new FormData()
  body.append('file', file)
  const bytes = await (await raw(`/templates/convert/${kind}`, { method: 'POST', body })).arrayBuffer()
  const setting = await loadSetting(userId)
  setting.files[kind] = { source: 'personal', name: file.name, selectedAt: new Date().toISOString(), base64: toBase64(bytes) }
  await saveSetting(userId, setting)
}

export async function useServerTemplate(userId: number, kind: TemplateKind): Promise<void> {
  const setting = await loadSetting(userId)
  setting.files[kind] = null
  await saveSetting(userId, setting)
}

export async function downloadDefaultTemplate(kind: TemplateKind): Promise<void> {
  const url = URL.createObjectURL(await (await raw(`/templates/${kind}`)).blob())
  const link = document.createElement('a')
  link.href = url; link.download = templateNames[kind]
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function readExportTemplate(userId: number, kind: TemplateKind): Promise<string | null> {
  const setting = await loadSetting(userId)
  try {
    if (await migrateDirectoryFile(setting, kind)) await saveSetting(userId, setting)
  } catch { throw new Error(legacyMessage) }
  const file = setting.files[kind]
  return file?.source === 'personal' ? file.base64 : null
}
