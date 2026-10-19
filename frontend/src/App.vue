<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { z } from 'zod'
import { ApiError, api, raw, json, today, entryDate, userSchema, ledgerSchema, recordSchema, fieldsSchema, reportSchema, jobSchema, type User, type Ledger, type CheckRecord, type Fields, type Item, type Job } from './api'
import './style.css'
import AdminPanel from './AdminPanel.vue'
import BatchGroups from './BatchGroups.vue'
import RecycleBin from './RecycleBin.vue'
import LocalTemplatesPanel from './LocalTemplatesPanel.vue'
import ReportAttachments from './ReportAttachments.vue'
import ReportPreview from './ReportPreview.vue'
import FieldSuggestions from './FieldSuggestions.vue'
import CertificatePicker from './CertificatePicker.vue'
import InspectionChoice from './InspectionChoice.vue'
import { readExportTemplate } from './localTemplates'
import { materialSchema, materialDetailsSchema, schemeSchema, partnerSchema, partyOptionSchema, normalizeShelfLife, shelfLifeDayNotice } from './api'

const user = ref<User | null>(null)
const administrator = computed(() => user.value?.role === 'admin' || user.value?.role === 'superadmin')
const setup = ref(false)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const credentials = reactive({ username: '', password: '' })
const ledgers = ref<Ledger[]>([])
const ledger = ref<Ledger | null>(null)
const allCompanies = ref(false)
const people = ref<{ id: number; username: string }[]>([])
const historyOpen = ref(false)
const histories = ref<{ actor_id: number; action: string; at: string; snapshot: CheckRecord }[]>([])
const actionNames: Record<string, string> = { created: '创建记录', checked: '核对记录', edited: '修改记录', voided: '作废记录', restored: '还原记录', report_uploaded: '上传检验报告', report_deleted: '删除检验报告' }
const view = ref<'home' | 'ledger' | 'editor' | 'admin' | 'templates' | 'recycle'>('home')
const returnToEditor = ref(false)
const editorReturn = ref<'ledger' | 'recycle'>('ledger')
const recycleReturn = ref<'home' | 'ledger'>('home')
function openRecycle() { if (busy.value || batchRetry.value || view.value === 'recycle') return; recycleReturn.value = view.value === 'ledger' ? 'ledger' : 'home'; view.value = 'recycle' }
async function closeRecycle() { await perform(async () => { if (recycleReturn.value === 'ledger') await loadRecords(); view.value = recycleReturn.value }) }
async function leaveEditor() { if (busy.value || batchRetry.value) return; await perform(async () => { if (editorReturn.value === 'ledger') await loadRecords(); view.value = editorReturn.value }) }
function reauthenticate() { user.value = null; credentials.password = ''; view.value = 'home'; notice.value = '密码已修改，请使用新密码重新登录' }
async function openRecycledRecord(record: CheckRecord) { await openEditor(record); editorReturn.value = 'recycle' }
function openTemplates() {
  if (view.value === 'templates') return
  returnToEditor.value = view.value === 'editor'; view.value = 'templates'
}
function closeTemplates() { view.value = returnToEditor.value ? 'editor' : 'home'; if (!returnToEditor.value) ledger.value = null }
const createLedger = ref(false)
const ledgerName = ref('')
const records = ref<CheckRecord[]>([])
const selectedIds = ref<number[]>([])
const previewIds = ref<number[]>([])
function openPreview(recordIds: number[]) { if (recordIds.length) previewIds.value = recordIds }
const filter = reactive({ text: '', status: '', from: '', to: '', mine: false, creator: 0, inspection: '', ledger: 0 })
function clearRecordFilters() { Object.assign(filter, { text: '', status: '', from: '', to: '', mine: false, creator: 0, inspection: '', ledger: 0 }) }
const editing = ref<CheckRecord | null>(null)
function updateAttachmentRecord(metadata: Pick<CheckRecord, 'status' | 'checker_id' | 'checked_at' | 'updated_at'> & { record_version: number }) {
  const record = editing.value || group.value?.savedRecord
  if (!record) return
  Object.assign(record, { version: metadata.record_version, status: metadata.status, checker_id: metadata.checker_id, checked_at: metadata.checked_at, updated_at: metadata.updated_at })
}
const fields = ref(fieldsSchema.parse({}))
const report = ref(reportSchema.parse({}))
const items = ref<Item[]>([])
type ExpiryDerivation = { inputKey: string | null; generation: number; changed: boolean; autoShelfLife: string | null; autoExpiryDate: string | null; warnings: string[] }
type DraftGroup = { historyAppliedKey: string; pendingReports: File[]; savedRecord: CheckRecord | null; key: number; expiry: ExpiryDerivation; basisAutoValue: string; inspectionEnabled: boolean; images: number[]; fields: Fields; report: z.infer<typeof reportSchema>; items: Item[]; dirty: Set<string>; job: Job | null; jobId: number | null; generation: number; materialId: number | null; schemeId: number | null; schemeChanged: boolean; materialChanged: boolean; requestState: 'idle' | 'submitting' | 'polling' | 'error'; pollError: string }
let nextGroupKey = 0
const groups = ref<DraftGroup[]>([])
const activeGroup = ref(0)
const group = computed(() => groups.value[activeGroup.value])
const mode = ref<'same' | 'batch'>('same')
const markBatchChecked = ref(false)
const batchRetry = ref<string | null>(null)
const selectedGroupKeys = ref<number[]>([])
const batchPendingKeys = ref<number[]>([])
const selectedGroups = computed(() => groups.value.filter(entry => selectedGroupKeys.value.includes(entry.key)))
const selectionSaving = computed(() => !editing.value && mode.value === 'batch' && (selectedGroups.value.length > 0 || !!batchRetry.value))
function toggleGroupSelection(key: number) {
  if (busy.value || batchRetry.value) return
  selectedGroupKeys.value = selectedGroupKeys.value.includes(key) ? selectedGroupKeys.value.filter(value => value !== key) : [...selectedGroupKeys.value, key]
}
const cloudEnabled = ref(true)
const selectedImage = ref(0)
const angle = ref(0)
const showLarge = ref(false)
const showPhoto = ref(true)
const suggestedFields = computed(() => Object.entries(group.value?.job?.cloud_fields || {}))
const localSuggestions = computed(() => Object.entries(group.value?.job?.fields || {}))
const fieldNames: Record<string, string> = { packaging: '包装', batch_number: '产品批号', basis: '检验依据', inspection_date: '检验日期', internal_report: '是否提供内检报告', arrival_date: '到货日期', received_quantity: '接收数量', certificates: '随车证件', sensory: '感官检验', sampling_items: '抽检项目', notes: '备注', material_name: '物料名称、型号', production_dates: '生产日期', specification: '规格', company_name: '供应商或生产商', address: '地址', contact: '联系方式', shelf_life: '保质期', expiry_date: '保质期至', address_source: '地址来源', contact_source: '联系方式来源' }
function makeGroup(images: number[] = []): DraftGroup { return { historyAppliedKey: '', pendingReports: [], savedRecord: null, key: ++nextGroupKey, expiry: { inputKey: null, generation: 0, changed: false, autoShelfLife: null, autoExpiryDate: null, warnings: [] }, basisAutoValue: '', inspectionEnabled: false, images, fields: fieldsSchema.parse({ arrival_date: today() }), report: reportSchema.parse({ inspection_date: today() }), items: [], dirty: new Set(), job: null, jobId: null, generation: 0, materialId: null, schemeId: null, schemeChanged: false, materialChanged: false, requestState: 'idle', pollError: '' } }
const recognizing = computed(() => groups.value.some(g => g.requestState === 'submitting' || g.requestState === 'polling'))
const interrupted = computed(() => groups.value.some(g => g.requestState === 'error'))
const recognitionLabel = computed(() => {
  const current = group.value
  if (!current) return ''
  if (current.requestState === 'error') return current.pollError
  if (current.requestState === 'submitting') return '正在提交识别任务…'
  const job = current.job
  if (!job) return ''
  if (job.local_status === 'queued') return `本地排队中 · 前方约 ${job.queue_ahead} 个任务`
  if (job.local_status === 'running') return `本地识别中 · 共 ${job.image_ids.length} 张图片`
  if (job.local_status === 'failed') return job.error || '本地识别失败，可以重试或手动填写'
  return '本地识别已完成'
})
const catalog = ref<z.infer<typeof materialSchema>[]>([])
const standards = ref<z.infer<typeof schemeSchema>[]>([])
const partners = ref<z.infer<typeof partnerSchema>[]>([])
const partnerId = ref(0)
const saveMaterialOpen = ref(false)
const materialDraft = reactive({ name: '', model: '', aliases: '', ...materialDetailsSchema.parse({}) })
const materialSaveError = ref('')
function reviewMaterial() {
  const selected = catalog.value.find(entry => entry.id === group.value?.materialId)
  const matchesSelected = selected && fields.value.material_name === [selected.name, selected.model].filter(Boolean).join(' ')
  Object.assign(materialDraft, { name: matchesSelected ? selected.name : fields.value.material_name, model: matchesSelected ? selected.model : '', aliases: selected?.aliases || '', ...materialDetailsSchema.parse({ ...fields.value, packaging: report.value.packaging }) })
  materialSaveError.value = ''; saveMaterialOpen.value = true
}
async function normalizeMaterialDraftShelfLife() {
  const value = materialDraft.shelf_life
  if (!value) return
  try {
    const normalized = await normalizeShelfLife(value)
    if (saveMaterialOpen.value && materialDraft.shelf_life === value) materialDraft.shelf_life = normalized
  } catch (problem) {
    if (saveMaterialOpen.value && materialDraft.shelf_life === value) materialSaveError.value = problem instanceof Error ? problem.message : '保质期格式转换失败'
  }
}
async function saveMaterialInfo() {
  if (!administrator.value || busy.value) return
  busy.value = true; materialSaveError.value = ''
  try {
    const saved = await api('/materials', materialSchema, json('POST', materialDraft))
    catalog.value.push(saved)
    saveMaterialOpen.value = false
    notice.value = '已新增共享物料；本次查验记录仍需保存'
  } catch (problem) { materialSaveError.value = problem instanceof Error ? problem.message : '物料保存失败' }
  finally { busy.value = false }
}
const saveSchemeOpen = ref(false)
const schemeDraft = reactive<{ name: string; material_id: number | null; items: Pick<Item, 'name' | 'standard'>[] }>({ name: '', material_id: null, items: [] })
const schemeSaveError = ref('')
function reviewScheme() {
  Object.assign(schemeDraft, { name: report.value.basis, material_id: group.value?.materialId || null, items: items.value.map(item => ({ name: item.name, standard: item.standard })) })
  schemeSaveError.value = ''; saveSchemeOpen.value = true
}
async function saveSchemeInfo() {
  if (!administrator.value || busy.value) return
  busy.value = true; schemeSaveError.value = ''
  try {
    const saved = await api('/schemes', schemeSchema, json('POST', { ...schemeDraft, name: schemeDraft.name.trim() }))
    standards.value.push(saved)
    saveSchemeOpen.value = false
    notice.value = '已新增检验标准方案；本次查验记录仍需保存'
  } catch (problem) { schemeSaveError.value = problem instanceof Error ? problem.message : '检验标准方案保存失败' }
  finally { busy.value = false }
}
const availableSchemes = computed(() => standards.value)
const maintainedItemKey = ref('')
function removeInspectionItem(index: number) {
  items.value.splice(index, 1)
  markDirty('items')
}
const maintainedItems = computed(() => standards.value.flatMap(scheme => scheme.items.map((item, index) => ({ key: `${scheme.id}:${index}`, label: `${scheme.name} / ${item.name} / ${item.standard}`, item }))))
function addMaintainedItem() {
  const choice = maintainedItems.value.find(entry => entry.key === maintainedItemKey.value)
  if (!choice) return
  items.value.push({ ...choice.item, result: '', conclusion: '' })
  markDirty('items')
  maintainedItemKey.value = ''
}
const groupingSuggestions = computed(() => groups.value.flatMap((entry, index) => {
  const fields = entry.job?.fields
  if (!fields?.material_name) return []
  const target = groups.value.findIndex((other, i) => i < index && other.job?.fields.material_name === fields.material_name &&
    (other.job?.fields.company_name || '') === (fields.company_name || '') && (other.job?.fields.specification || '') === (fields.specification || ''))
  return target >= 0 ? [`记录 ${target + 1} 与记录 ${index + 1}：识别到相同物料，建议核对后合并（${fields.material_name}）`] : []
}))
async function loadLibrary() {
  ;[catalog.value, standards.value, partners.value] = await Promise.all([api('/materials', z.array(materialSchema)), api('/schemes', z.array(schemeSchema)), api('/partners', z.array(partnerSchema))])
}
function replaceScheme(schemeId: number | null) {
  if (!group.value) return
  markDirty('items')
  const scheme = standards.value.find(s => s.id === schemeId)
  if (scheme || (!group.value.dirty.has('report.basis') && report.value.basis === group.value.basisAutoValue)) report.value.basis = scheme?.name || ''
  group.value.basisAutoValue = scheme?.name || ''
  group.value.schemeId = schemeId; group.value.schemeChanged = true
  group.value.items = scheme ? scheme.items.map(i => ({ ...i, result: '', conclusion: '' })) : []
  items.value = group.value.items
}
function chooseMaterial(event: Event) {
  if (!(event.target instanceof HTMLSelectElement) || !group.value) return
  group.value.materialId = Number(event.target.value) || null
  group.value.materialChanged = true
  group.value.historyAppliedKey = ''; markDirty('material_id')
  const material = catalog.value.find(m => m.id === group.value?.materialId)
  if (material) {
    fields.value.material_name = [material.name, material.model].filter(Boolean).join(' '); markDirty('material_name')
    if (material.packaging) { report.value.packaging = material.packaging; markDirty('report.packaging') }
    for (const key of ['specification', 'company_name', 'address', 'contact', 'shelf_life'] as const) {
      if (!material[key]) continue
      fields.value[key] = material[key]; markDirty(key)
      if (key === 'address' || key === 'contact') {
        const sourceKey = key === 'address' ? 'address_source' : 'contact_source'
        fields.value[sourceKey] = material[sourceKey]; markDirty(sourceKey)
      }
    }
  }
  applyOnlyBoundScheme()
}
function applyOnlyBoundScheme() {
  const current = group.value
  if (!current?.inspectionEnabled || current.historyAppliedKey || !current.materialId || current.items.length || current.schemeId) return
  const choices = standards.value.filter(scheme => scheme.material_id === current.materialId)
  if (choices.length === 1) replaceScheme(choices[0]?.id || null)
}
watch(() => group.value?.inspectionEnabled, enabled => { if (enabled) applyOnlyBoundScheme() })
function chooseScheme(event: Event) {
  if (!(event.target instanceof HTMLSelectElement) || !group.value) return
  if (items.value.some(i => i.result || i.conclusion) && !window.confirm('更换方案会清空当前检验结果和结论，继续吗？')) { event.target.value = String(group.value.schemeId || ''); return }
  replaceScheme(Number(event.target.value) || null)
}
function fillPartner(part: 'name' | 'contact') {
  const partner = partners.value.find(p => p.id === partnerId.value)
  if (!partner) return
  if (part === 'name') { fields.value.company_name = partner.name; markDirty('company_name') }
  else { fields.value.address = partner.address; fields.value.contact = partner.contact; fields.value.address_source = partner.kind; fields.value.contact_source = partner.kind; markDirty('address'); markDirty('contact'); markDirty('address_source'); markDirty('contact_source') }
}
function switchGroup(index: number) {
  activeGroup.value = index
  const current = groups.value[index]
  if (!current) return
  fields.value = current.fields; report.value = current.report; items.value = current.items
  selectedImage.value = current.images[0] || 0; angle.value = 0
}
function previewGroup(index: number, imageId: number) { switchGroup(index); selectedImage.value = imageId }
function markDirty(key: string) {
  const current = group.value
  if (!current) return
  current.dirty.add(key)
  if (key === 'shelf_life') current.expiry.autoShelfLife = null
  if (key === 'expiry_date') current.expiry.autoExpiryDate = null
}
const expiryResultSchema = fieldsSchema.pick({ shelf_life: true, expiry_date: true }).extend({ warnings: z.array(z.string()) })
const expiryWarnings = computed(() => [...new Set([shelfLifeDayNotice(fields.value.shelf_life), ...(group.value?.expiry.warnings || [])].filter(Boolean))])
const expiryTimers = new Map<number, ReturnType<typeof setTimeout>>()
function hasExpiryConflict(current: DraftGroup) {
  return ['shelf_life', 'expiry_date'].some(key => current.job?.conflicts[key]?.length && !current.dirty.has(key))
}
function expiryInputKey(current: DraftGroup) {
  return JSON.stringify([current.fields.production_dates, current.fields.shelf_life, current.fields.expiry_date, current.dirty.has('shelf_life'), current.dirty.has('expiry_date'), hasExpiryConflict(current)])
}
async function deriveExpiry(current: DraftGroup) {
  clearTimeout(expiryTimers.get(current.key)); expiryTimers.delete(current.key)
  const generation = ++current.expiry.generation
  const inputKey = expiryInputKey(current)
  if (hasExpiryConflict(current)) {
    current.expiry.warnings = ['识别到多个保质期或有效期，请先核对冲突字段再计算。']
    current.expiry.changed = false
    return
  }
  const fillShelfLife = !current.dirty.has('shelf_life') && (!current.fields.shelf_life || current.fields.shelf_life === current.expiry.autoShelfLife)
  const fillExpiryDate = !current.dirty.has('expiry_date') && (!current.fields.expiry_date || current.fields.expiry_date === current.expiry.autoExpiryDate)
  const body = { production_dates: current.fields.production_dates, shelf_life: fillShelfLife ? '' : current.fields.shelf_life, expiry_date: fillExpiryDate ? null : current.fields.expiry_date || null }
  try {
    const result = await api('/shelf-life/derive', expiryResultSchema, json('POST', body))
    if (!groups.value.includes(current) || current.expiry.generation !== generation || expiryInputKey(current) !== inputKey) return
    if (fillShelfLife) { current.fields.shelf_life = result.shelf_life; current.expiry.autoShelfLife = result.shelf_life || null }
    if (fillExpiryDate) { current.fields.expiry_date = result.expiry_date; current.expiry.autoExpiryDate = result.expiry_date }
    current.expiry.inputKey = expiryInputKey(current)
    current.expiry.warnings = result.warnings
    current.expiry.changed = false
  } catch (problem) {
    if (current.expiry.generation !== generation || expiryInputKey(current) !== inputKey) return
    current.expiry.warnings = [problem instanceof ApiError && problem.status === 422 ? '生产日期或保质期至格式不正确，请核对后再计算。' : '保质期自动计算暂不可用，可以手动填写。']
    current.expiry.changed = false
  }
}
async function normalizeEntryShelfLife() {
  const current = group.value
  const value = current?.fields.shelf_life
  if (!current || !value) return
  try {
    const normalized = await normalizeShelfLife(value)
    if (groups.value.includes(current) && current.fields.shelf_life === value) {
      current.fields.shelf_life = normalized
      if (current.expiry.autoShelfLife === value) current.expiry.autoShelfLife = normalized
    }
  } catch (problem) {
    if (groups.value.includes(current) && current.fields.shelf_life === value) current.expiry.warnings = [problem instanceof Error ? problem.message : '保质期格式转换失败']
  }
}
watch(() => groups.value.map(expiryInputKey), () => {
  for (const current of groups.value) {
    const inputKey = expiryInputKey(current)
    if (current.expiry.inputKey === null) { current.expiry.inputKey = inputKey; continue }
    if (current.expiry.inputKey === inputKey) continue
    current.expiry.inputKey = inputKey; current.expiry.changed = true; current.expiry.generation++
    clearTimeout(expiryTimers.get(current.key))
    expiryTimers.set(current.key, setTimeout(() => { if (groups.value.includes(current)) void deriveExpiry(current) }, 250))
  }
})
function reorderGroups(from: number, to: number) {
  if (busy.value || batchRetry.value) return
  const current = group.value
  const moved = groups.value.splice(from, 1)[0]
  if (!moved) return
  groups.value.splice(to, 0, moved)
  activeGroup.value = Math.max(0, groups.value.findIndex(entry => entry === current))
}
function applyMatchedHistory(current: DraftGroup, job: Job) {
  const history = job.review_suggestions
  const source = history.sources[0]
  if (!source || !history.inspection) return
  const key = `${job.id}:${source.record_id}:${source.version}`
  if (current.historyAppliedKey === key) return
  current.historyAppliedKey = key
  const newRecord = !editing.value && !current.savedRecord
  for (const [field, value] of Object.entries(history.fields)) {
    if (field.endsWith('_source') || value === '' || value === null || current.dirty.has(field)) continue
    if ((field === 'company_name' || field === 'address') && (job.conflicts[field]?.length || 0) > 1) continue
    const existing: unknown = Reflect.get(current.fields, field)
    if (!newRecord && existing) continue
    const paired = field === 'address' || field === 'contact'
    const sourceKey = field + '_source'
    if (paired && current.dirty.has(sourceKey)) continue
    const parsed = fieldsSchema.safeParse({ ...current.fields, [field]: value,
      ...(paired ? { [sourceKey]: Reflect.get(history.fields, sourceKey) || '' } : {}) })
    if (parsed.success) Object.assign(current.fields, parsed.data)
  }
  const inspection = history.inspection
  if (!current.dirty.has('items') && (newRecord || !current.items.length)) {
    current.items.splice(0, current.items.length, ...inspection.items.map(item => ({ ...item })))
    const scheme = standards.value.find(entry => entry.name === inspection.scheme_name)
    current.schemeId = scheme?.id || null
    current.schemeChanged = true
  }
  for (const field of ['packaging', 'basis', 'internal_report', 'conclusion'] as const) {
    const value = inspection.report[field]
    if (value && !current.dirty.has('report.' + field) && (newRecord || !current.report[field])) current.report[field] = value
  }
  if (newRecord && !current.dirty.has('material_id')) {
    current.materialId = inspection.material_id
    current.materialChanged = true
  }
  if (newRecord && !current.dirty.has('inspection_enabled')) current.inspectionEnabled = inspection.inspection_enabled
}
function applySuggestion(key: string, value: unknown) {
  if (busy.value || batchRetry.value) return
  if (key === 'company_name' || key === 'address') {
    const option = partyOptionSchema.safeParse(value)
    if (option.success) value = option.data.value
  }
  if (reportOcrKeys.has(key)) {
    const parsed = reportSchema.safeParse({ ...report.value, [key]: value })
    if (parsed.success) { Object.assign(report.value, parsed.data); markDirty('report.' + key) }
  } else {
    const normalized = key === 'production_dates' && typeof value === 'string' ? value.split(/[、,，;；]+/).map(part => part.trim().replaceAll('.', '-')) : value
    const parsed = fieldsSchema.safeParse({ ...fields.value, [key]: normalized })
    if (parsed.success) { Object.assign(fields.value, parsed.data); markDirty(key) }
  }
}
const reportOcrKeys = new Set(['packaging', 'batch_number', 'basis', 'inspection_date', 'internal_report'])
function suggestionsFor(key: string): unknown[] {
  const job = group.value?.job
  if (!job) return []
  const current: unknown = Reflect.get(reportOcrKeys.has(key) ? report.value : fields.value, key)
  const values: unknown[] = [...(job.conflicts[key] || []), ...(job.review_suggestions.conflicts[key] || [])]
  for (const proposals of [job.fields, job.cloud_fields, job.review_suggestions.fields]) values.push(Reflect.get(proposals, key))
  if (key === 'company_name' || key === 'address') {
    const options = [...job.party_options[key]]
    for (const value of values) if (typeof value === 'string' && value && !options.some(option => option.value === value)) options.push({ value, source: '' })
    return options
  }
  const unique = new Map<string, unknown>()
  for (const value of values) {
    const display = formatSuggestion(value)
    if (display && display !== formatSuggestion(current)) unique.set(display, value)
  }
  return [...unique.values()]
}
function warningsFor(key: string) { return group.value?.job?.cloud_warnings.filter(warning => warning.field === key).map(warning => warning.message) || [] }
function formatSuggestion(value: unknown) { return Array.isArray(value) ? value.join('、') : String(value ?? '') }
const editable = computed(() => !editing.value || (editing.value.status !== 'void' && (administrator.value || editing.value.creator_id === user.value?.id)))
const statusText = { pending: '待核对', checked: '已核对', void: '作废' }
const productionDates = computed({
  get: () => fields.value.production_dates.map(d => d.replaceAll('-', '.')).join('、'),
  set: (value: string) => { fields.value.production_dates = value.split(/[、,，\n;；]+/).map(d => d.trim().replaceAll('.', '-').replaceAll('/', '-')).filter(Boolean); markDirty('production_dates') },
})
const textFields: { key: keyof Pick<Fields, 'material_name' | 'specification' | 'company_name' | 'address' | 'contact' | 'shelf_life' | 'received_quantity'>; label: string }[] = [
  { key: 'material_name', label: '物料名称、型号' }, { key: 'specification', label: '规格' },
  { key: 'company_name', label: '供应商或生产商' }, { key: 'address', label: '地址' },
  { key: 'contact', label: '联系方式' }, { key: 'shelf_life', label: '保质期' }, { key: 'received_quantity', label: '接收数量' },
]
const filteredRecords = computed(() => records.value.filter(r =>
  (!filter.text.trim() || [r.fields.material_name, r.fields.company_name, r.fields.specification, r.fields.notes, String(r.id)].some(v => v.toLowerCase().includes(filter.text.trim().toLowerCase()))) &&
  (!allCompanies.value || !filter.ledger || r.ledger_id === filter.ledger) &&
  (!filter.inspection || r.inspection_enabled === (filter.inspection === 'inspected')) &&
  (!filter.status || r.status === filter.status) && (!filter.mine || r.creator_id === user.value?.id) && (!filter.creator || r.creator_id === filter.creator) &&
  (!filter.from || (r.fields.arrival_date || '') >= filter.from) && (!filter.to || (!!r.fields.arrival_date && r.fields.arrival_date <= filter.to)),
))

const selectedVisible = computed(() => filteredRecords.value.filter(r => r.status !== 'void' && selectedIds.value.includes(r.id)))
type SortKey = 'ledger' | 'created_at' | 'arrival_date' | 'material_name' | 'production_dates' | 'company_name' | 'received_quantity' | 'inspection' | 'status'
const sort = ref<{ key: SortKey; ascending: boolean } | null>(null)
const ledgerColumns: { key: SortKey; label: string }[] = [
  { key: 'created_at', label: '录入日期' },
  { key: 'arrival_date', label: '到货日期' }, { key: 'material_name', label: '物料名称、型号' },
  { key: 'production_dates', label: '生产日期' }, { key: 'company_name', label: '供应商或生产商' },
  { key: 'received_quantity', label: '接收数量' }, { key: 'inspection', label: '检验状态' }, { key: 'status', label: '状态' },
]
function toggleSort(key: SortKey) { sort.value = { key, ascending: sort.value?.key === key ? !sort.value.ascending : true } }
function sortDirection(key: SortKey) { return sort.value?.key === key ? (sort.value.ascending ? 'ascending' : 'descending') : 'none' }
function sortValue(record: CheckRecord, key: SortKey): string {
  if (key === 'created_at') return record.created_at
  if (key === 'ledger') return ledgers.value.find(value => value.id === record.ledger_id)?.name || ''
  if (key === 'inspection') return record.inspection_enabled ? '检验' : '未检验'
  if (key === 'status') return statusText[record.status]
  if (key === 'production_dates') return record.fields.production_dates.join('、')
  return record.fields[key] || ''
}
const tableRecords = computed(() => {
  const order = sort.value
  if (!order) return filteredRecords.value
  const collator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })
  return [...filteredRecords.value].sort((a, b) => {
    const left = sortValue(a, order.key), right = sortValue(b, order.key)
    if (!left || !right) return left ? -1 : right ? 1 : a.id - b.id
    return collator.compare(left, right) * (order.ascending ? 1 : -1) || a.id - b.id
  })
})

async function perform(work: () => Promise<void>) {
  if (busy.value) return
  error.value = ''; notice.value = ''; busy.value = true
  try { await work() } catch (problem) {
    error.value = problem instanceof Error ? problem.message : '操作失败，请重试'
    await nextTick()
    document.querySelector('[role="alert"]')?.scrollIntoView({ block: 'center' })
  }
  finally { busy.value = false }
}
async function loadLedgers() {
  ledgers.value = await api('/ledgers', z.array(ledgerSchema))
  people.value = await api('/people', z.array(z.object({ id: z.number(), username: z.string() })))
}
async function loadRecords() {
  if (!ledger.value && !allCompanies.value) return
  records.value = await api(allCompanies.value ? '/records' : `/ledgers/${ledger.value?.id}/records`, z.array(recordSchema))
  selectedIds.value = records.value.filter(r => r.status === 'checked').map(r => r.id)
}
onMounted(async () => {
  await perform(async () => {
    setup.value = (await api('/setup', z.object({ required: z.boolean() }))).required
    if (!setup.value) {
      try { user.value = await api('/me', userSchema); await loadLedgers() } catch { user.value = null }
    }
  }); loading.value = false
})
async function login() {
  await perform(async () => {
    if (setup.value) { await api('/setup', userSchema, json('POST', credentials)); setup.value = false }
    user.value = await api('/login', userSchema, json('POST', credentials))
    credentials.password = ''; await loadLedgers()
  })
}
async function logout() { await perform(async () => { await raw('/logout', { method: 'POST' }); user.value = null; ledger.value = null; view.value = 'home' }) }
async function enterLedger(value: Ledger) { await perform(async () => { allCompanies.value = false; ledger.value = value; await loadRecords(); view.value = 'ledger' }) }
async function showAllRecords() { await perform(async () => { allCompanies.value = true; ledger.value = null; await loadRecords(); view.value = 'ledger' }) }
async function showHistory() {
  if (!editing.value) return
  await perform(async () => {
    histories.value = await api(`/records/${editing.value?.id}/history`, z.array(z.object({ actor_id: z.number(), action: z.string(), at: z.string(), snapshot: recordSchema })))
    historyOpen.value = true
  })
}
async function voidRecord(record: CheckRecord | null = editing.value) {
  if (busy.value || !administrator.value || !record || record.status === 'void') return
  if (!window.confirm(`确定作废记录 #${record.id}「${record.fields.material_name || '未填写物料'}」吗？作废后移入回收站，30 天内可还原，超过 30 天自动永久删除。`)) return
  await perform(async () => { await api(`/records/${record.id}/void`, recordSchema, json('POST', { version: record.version })); await loadRecords(); view.value = 'ledger'; notice.value = '记录已移入回收站，30 天内可还原' })
}
async function voidSelected() {
  const selected = selectedVisible.value
  if (busy.value || !administrator.value || !selected.length) return
  if (selected.length > 200) { error.value = '单次最多作废 200 条记录，请减少勾选后分批操作'; return }
  if (!window.confirm(`确定将所选 ${selected.length} 条记录移入回收站？30 天内可还原，超过 30 天自动永久删除。`)) return
  await perform(async () => {
    await api('/records/batch-void', z.array(recordSchema), json('POST', { records: selected.map(record => ({ id: record.id, version: record.version })) }))
    await loadRecords(); notice.value = `已将 ${selected.length} 条记录移入回收站`
  })
}
async function addLedger() {
  await perform(async () => {
    await api('/ledgers', ledgerSchema, json('POST', { name: ledgerName.value }))
    ledgerName.value = ''; createLedger.value = false; await loadLedgers()
  })
}
async function openEditor(record: CheckRecord | null = null) {
  if (busy.value) return
  await perform(async () => {
  if (record) {
    record = await api(`/records/${record.id}`, recordSchema, { cache: 'no-store' })
    const index = records.value.findIndex(entry => entry.id === record?.id)
    if (index >= 0) records.value[index] = record
  }
  for (const previous of groups.value) previous.generation++
  if (record) {
    const ledgerId = record.ledger_id
    ledger.value = ledgers.value.find(l => l.id === ledgerId) || null
  }
  editing.value = record
  editorReturn.value = 'ledger'
  markBatchChecked.value = false; batchRetry.value = null; selectedGroupKeys.value = []; batchPendingKeys.value = []
  fields.value = fieldsSchema.parse(record?.fields || { arrival_date: today() })
  report.value = reportSchema.parse(record?.report || { inspection_date: today() })
  items.value = record ? record.items.map(i => ({ ...i })) : []
  groups.value = [{ ...makeGroup(record?.image_ids || []), basisAutoValue: record?.scheme_name || '', inspectionEnabled: record?.inspection_enabled ?? false, fields: fields.value, report: report.value, items: items.value, jobId: record?.recognition_job_id || null, materialId: record?.material_id || null }]
  switchGroup(0)
  const current = group.value
  if (record?.recognition_job_id && current) {
    void api(`/recognition/${record.recognition_job_id}`, jobSchema).then(job => {
      if (groups.value.includes(current) && current.generation === 0) {
        current.job = job
        if (jobActive(job)) void monitorJob(current, job.id, 0, false)
      }
    }).catch(problem => { error.value = problem instanceof Error ? problem.message : '识别原文加载失败' })
  }
  void loadLibrary().catch(problem => { error.value = problem instanceof Error ? problem.message : '公共资料加载失败' })
  error.value = ''; notice.value = ''; view.value = 'editor'
  })
}
async function savePendingReports(entry: DraftGroup): Promise<CheckRecord> {
  const saved = entry.savedRecord
  if (!saved) throw new Error('请先保存查验记录')
  let record: CheckRecord = saved
  while (entry.pendingReports.length) {
    const file = entry.pendingReports[0]
    if (!file) break
    const body = new FormData()
    body.append('file', file); body.append('version', String(record.version))
    try {
      const result = await api(`/records/${record.id}/reports`, z.object({ record_version: z.number(), status: z.enum(['pending', 'checked', 'void']), checker_id: z.number().nullable(), checked_at: z.string().nullable(), updated_at: z.string() }), { method: 'POST', body })
      record = { ...record, ...result, version: result.record_version }
      entry.savedRecord = record
      entry.pendingReports.shift()
    } catch (cause) {
      throw new Error(`记录已保存，报告“${file.name}”上传未完成：${cause instanceof Error ? cause.message : '请重试'}。待上传文件已保留，再次保存不会重复创建记录。`)
    }
  }
  return record
}
async function save(check: boolean) {
  await perform(async () => {
    if (!ledger.value) return
    const savedLedgerId = ledger.value.id
    const editorRecord = editing.value
    const savedGroup = group.value
    if (!savedGroup) return
    const savedRecord = editorRecord || savedGroup.savedRecord
    if (savedGroup.expiry.changed) await deriveExpiry(savedGroup)
    const body = { inspection_enabled: savedGroup.inspectionEnabled, fields: { ...savedGroup.fields, arrival_date: savedGroup.fields.arrival_date || null, expiry_date: savedGroup.fields.expiry_date || null }, report: { ...savedGroup.report, inspection_date: savedGroup.report.inspection_date || null }, items: savedGroup.items, image_ids: savedGroup.images, recognition_job_id: savedGroup.jobId }
    let record = savedRecord
      ? await api(`/records/${savedRecord.id}`, recordSchema, json('PATCH', { ...body, version: savedRecord.version, ...(savedGroup.materialChanged ? { material_id: savedGroup.materialId } : {}), ...(savedGroup.schemeChanged ? { scheme_id: savedGroup.schemeId } : {}) }))
      : await api(`/ledgers/${savedLedgerId}/records`, recordSchema, json('POST', { ...body, material_id: savedGroup.materialId, scheme_id: savedGroup.schemeId }))
    savedGroup.savedRecord = record
    record = await savePendingReports(savedGroup)
    if (check) { record = await api(`/records/${record.id}/check`, recordSchema, json('POST', { version: record.version })); savedGroup.savedRecord = record }
    if (!groups.value.includes(savedGroup) || editing.value !== editorRecord) { notice.value = check ? '记录已保存并核对' : '记录已保存，待核对'; return }
    editing.value = record
    if (groups.value.length > 1) {
      const selectedGroup = group.value
      const savedIndex = groups.value.findIndex(entry => entry === savedGroup)
      if (savedIndex >= 0) groups.value.splice(savedIndex, 1)
      selectedGroupKeys.value = selectedGroupKeys.value.filter(key => key !== savedGroup?.key)
      editing.value = null
      switchGroup(Math.max(0, groups.value.findIndex(entry => entry === selectedGroup)))
      notice.value = '当前记录已保存，请继续核对下一组'
    } else { await loadRecords(); if (view.value === 'editor') view.value = 'ledger'; notice.value = check ? '记录已保存并核对' : '记录已保存，待核对' }
  })
}
function newBatchId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = ((bytes[6] ?? 0) & 15) | 64
  bytes[8] = ((bytes[8] ?? 0) & 63) | 128
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
async function saveBatch() {
  if (busy.value || !ledger.value || editing.value || (!batchRetry.value && !selectedGroups.value.length)) return
  const savedLedgerId = ledger.value.id
  if (!batchRetry.value && selectedGroups.value.length > 200) { error.value = '单次最多保存 200 条记录，请减少勾选后分批操作'; return }
  await perform(async () => {
    if (!batchRetry.value) {
      const savedGroups = selectedGroups.value
      await Promise.all(savedGroups.filter(entry => entry.expiry.changed).map(entry => deriveExpiry(entry)))
      for (const entry of savedGroups) if (entry.savedRecord) {
        entry.savedRecord = await api(`/records/${entry.savedRecord.id}`, recordSchema, json('PATCH', {
          version: entry.savedRecord.version, inspection_enabled: entry.inspectionEnabled,
          fields: entry.fields, report: entry.report, items: entry.items, image_ids: entry.images,
          ...(entry.materialChanged ? { material_id: entry.materialId } : {}), ...(entry.schemeChanged ? { scheme_id: entry.schemeId } : {}),
        }))
      }
      batchPendingKeys.value = savedGroups.map(entry => entry.key)
      batchRetry.value = JSON.stringify({
      request_id: newBatchId(), mark_checked: markBatchChecked.value && !savedGroups.some(entry => entry.pendingReports.length),
      records: savedGroups.filter(entry => !entry.savedRecord).map(entry => ({
        inspection_enabled: entry.inspectionEnabled,
        fields: { ...entry.fields, arrival_date: entry.fields.arrival_date || null, expiry_date: entry.fields.expiry_date || null },
        report: { ...entry.report, inspection_date: entry.report.inspection_date || null },
        items: entry.items, image_ids: entry.images, recognition_job_id: entry.jobId,
        material_id: entry.materialId, scheme_id: entry.schemeId,
      })),
      })
    }
    const submittedGroups = batchPendingKeys.value.flatMap(key => groups.value.filter(entry => entry.key === key))
    const newGroups = submittedGroups.filter(entry => !entry.savedRecord)
    try {
      if (newGroups.length) {
        const created = await api(`/ledgers/${savedLedgerId}/records/batch`, z.array(recordSchema), { method: 'POST', body: batchRetry.value })
        newGroups.forEach((entry, index) => { entry.savedRecord = created[index] || null })
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status < 500 && cause.status !== 408) { batchRetry.value = null; batchPendingKeys.value = []; throw cause }
      throw new Error('批量保存结果尚未确认，请点击重试；同一批次不会重复保存。')
    }
    for (const entry of submittedGroups) {
      const record = await savePendingReports(entry)
      if (markBatchChecked.value && record.status !== 'checked') entry.savedRecord = await api(`/records/${record.id}/check`, recordSchema, json('POST', { version: record.version }))
    }
    const currentKey = group.value?.key
    for (const entry of groups.value) if (batchPendingKeys.value.includes(entry.key)) entry.generation++
    groups.value = groups.value.filter(entry => !batchPendingKeys.value.includes(entry.key))
    selectedGroupKeys.value = selectedGroupKeys.value.filter(key => !batchPendingKeys.value.includes(key))
    batchRetry.value = null; batchPendingKeys.value = []; editing.value = null
    notice.value = `已保存 ${submittedGroups.length} 条记录${markBatchChecked.value ? '，并标记为已核对' : '，待核对'}`
    if (groups.value.length) {
      switchGroup(Math.max(0, groups.value.findIndex(entry => entry.key === currentKey)))
      notice.value += `；还剩 ${groups.value.length} 条未保存`
    } else { if (view.value === 'editor') view.value = 'ledger'; await loadRecords() }
  })
}
async function uploadFiles(files: FileList | File[] | null) {
  if (!files || !ledger.value || !editable.value || busy.value || batchRetry.value) return
  await perform(async () => {
    for (const file of Array.from(files)) {
      const form = new FormData(); form.append('file', file)
      const photo = await api(`/ledgers/${ledger.value?.id}/images`, z.object({ id: z.number() }), { method: 'POST', body: form })
      if (mode.value === 'same' || editing.value) { const current = group.value; if (current) { invalidateRecognition(current); current.images.push(photo.id) } }
      else if (groups.value.length === 1 && !groups.value[0]?.images.length) groups.value[0]?.images.push(photo.id)
      else groups.value.push(makeGroup([photo.id]))
    }
    switchGroup(activeGroup.value)
  })
}
function fileChosen(event: Event) { if (event.target instanceof HTMLInputElement) { void uploadFiles(event.target.files); event.target.value = '' } }
function mergeGroups(index: number, targetIndex: number) {
  if (busy.value || batchRetry.value) return
  const current = groups.value[index]; const previous = groups.value[targetIndex]
  if (!current || !previous || current === previous) return
  if (current.savedRecord || previous.savedRecord) { error.value = '这组记录已保存，请先完成附件上传；已保存记录不能合并。'; return }
  const results = (entry: DraftGroup) => entry.items.filter(i => i.result || i.conclusion).map(i => [i.name, i.result, i.conclusion])
  if (results(current).length && results(previous).length && JSON.stringify(results(current)) !== JSON.stringify(results(previous))) {
    error.value = '两组检验结果不同，请分别保存记录'; return
  }
  const hasSourceContent = current.dirty.size || current.items.some(item => item.result || item.conclusion) || Object.entries(current.fields).some(([key, value]) => key !== 'arrival_date' && key !== 'production_dates' && !!value && JSON.stringify(value) !== JSON.stringify(Reflect.get(previous.fields, key)))
  if (hasSourceContent && !window.confirm(`合并到记录 ${targetIndex + 1}：保留目标组已填内容，用来源组补充空白字段，并汇总图片及生产日期。接收总数量请合并后核对。继续吗？`)) return
  current.generation++
  previous.pendingReports.push(...current.pendingReports); previous.images.push(...current.images); invalidateRecognition(previous)
  for (const key of Object.keys(current.fields)) {
    if (key !== 'production_dates' && !Reflect.get(previous.fields, key)) Reflect.set(previous.fields, key, Reflect.get(current.fields, key))
  }
  for (const key of Object.keys(current.report)) if (!Reflect.get(previous.report, key)) Reflect.set(previous.report, key, Reflect.get(current.report, key))
  if (!previous.items.length || (!results(previous).length && results(current).length)) {
    previous.items = current.items; previous.schemeId = current.schemeId; previous.basisAutoValue = current.basisAutoValue
  }
  previous.inspectionEnabled ||= current.inspectionEnabled
  previous.materialId ||= current.materialId
  current.dirty.forEach(key => previous.dirty.add(key))
  previous.fields.production_dates = [...new Set([...previous.fields.production_dates, ...current.fields.production_dates])]
  if (selectedGroupKeys.value.includes(current.key) && !selectedGroupKeys.value.includes(previous.key)) selectedGroupKeys.value.push(previous.key)
  selectedGroupKeys.value = selectedGroupKeys.value.filter(key => key !== current.key)
  groups.value.splice(index, 1); switchGroup(groups.value.indexOf(previous))
}
function moveImage(imageId: number, targetKey: number) {
  if (busy.value || batchRetry.value) return
  const current = group.value; const target = groups.value.find(g => g.key === targetKey)
  if (!current || !target || target === current) return
  current.images = current.images.filter(id => id !== imageId); invalidateRecognition(current)
  target.images.push(imageId); invalidateRecognition(target)
  selectedImage.value = current.images[0] || 0
}
function imageDestination(event: Event, imageId: number) { if (event.target instanceof HTMLSelectElement) moveImage(imageId, Number(event.target.value)) }
function splitImage(imageId: number) {
  if (busy.value || batchRetry.value) return
  const target = makeGroup(); groups.value.push(target); moveImage(imageId, target.key)
}
function invalidateRecognition(current: DraftGroup) { current.generation++; current.job = null; current.jobId = null; current.requestState = 'idle'; current.pollError = '' }
function removeImage(imageId: number) {
  if (busy.value || batchRetry.value) return
  if (!group.value) return
  group.value.images = group.value.images.filter(id => id !== imageId); invalidateRecognition(group.value)
  selectedImage.value = group.value.images[0] || 0
}
async function recognizeGroup(current: DraftGroup) {
  if (!ledger.value || !current.images.length) return
  const generation = ++current.generation
  current.pollError = ''; current.requestState = 'submitting'
  try {
    const result = current.job && jobActive(current.job) ? current.job : await api(`/ledgers/${ledger.value.id}/recognition`, jobSchema, { ...json('POST', { image_ids: current.images, cloud_enabled: cloudEnabled.value }), signal: AbortSignal.timeout(15000) })
    if (current.generation !== generation) return
    current.job = result; current.jobId = result.id
    await monitorJob(current, result.id, generation, true)
  } catch {
    if (current.generation === generation) { current.requestState = 'error'; current.pollError = '识别提交未确认，请重试；已提交的任务会继续处理' }
  }
}
function jobActive(job: Job) { return ['queued', 'running'].includes(job.local_status) || ['queued', 'running'].includes(job.cloud_status) }
async function monitorJob(current: DraftGroup, jobId: number, generation: number, fill: boolean) {
  current.requestState = 'polling'
  let localApplied = false
  let cloudApplied = false
  try { while (current.generation === generation && groups.value.includes(current)) {
    const job = await api(`/recognition/${jobId}`, jobSchema, { cache: 'no-store', signal: AbortSignal.timeout(15000) })
    if (current.generation !== generation) return
    current.job = job
    if (fill && ((!localApplied && job.local_status === 'done') || (!cloudApplied && job.cloud_status === 'done'))) {
      // Current-photo values fill blanks. Verified material history is applied below.
      const sources = [...(job.local_status === 'done' ? [job.fields] : []), ...(job.cloud_status === 'done' ? [job.cloud_fields] : [])]
      for (const proposals of sources) for (const [key, value] of Object.entries(proposals)) {
        // Keep English prose as a selectable original; let Chinese translations
        // fill blanks when they arrive. Codes, numbers and dates remain usable.
        if (job.english_detected &&
            ['material_name', 'company_name', 'address', 'specification', 'packaging', 'sensory', 'notes', 'certificates'].includes(key) &&
            typeof value === 'string' && /[a-z]{3}/i.test(value) && !/[\u4e00-\u9fff]/.test(value)) continue
        if (key === 'sampling_items') continue
        if (value === null || value === '' || (Array.isArray(value) && !value.length)) continue
        if (key.endsWith('_source')) continue
        if (reportOcrKeys.has(key)) {
          const existing: unknown = Reflect.get(current.report, key)
          if (!current.dirty.has('report.' + key) && !job.conflicts[key] && (!existing || (!editing.value && !current.savedRecord && key === 'batch_number' && existing === '\\'))) {
            const parsed = reportSchema.safeParse({ ...current.report, [key]: value })
            if (parsed.success) Object.assign(current.report, parsed.data)
          }
          continue
        }
        const existing: unknown = Reflect.get(current.fields, key)
        const paired = key === 'contact'
        const sourceKey = key + '_source'
        const source: unknown = Reflect.get(proposals, sourceKey) || ''
        if (paired) {
          const existingSource: unknown = Reflect.get(current.fields, sourceKey)
          if (current.dirty.has(sourceKey) || (existingSource && existingSource !== source)) continue
        }
        if (!current.dirty.has(key) && !job.conflicts[key] && (!existing || (Array.isArray(existing) && !existing.length))) {
          const parsed = fieldsSchema.safeParse({ ...current.fields, [key]: value, ...(paired ? { [sourceKey]: source } : {}) })
          if (parsed.success) Object.assign(current.fields, parsed.data)
        }
      }
      localApplied ||= job.local_status === 'done'
      cloudApplied ||= job.cloud_status === 'done'
    }
    if (fill) applyMatchedHistory(current, job)
    if (!jobActive(job)) break
    await new Promise(resolve => setTimeout(resolve, 500))
  } } catch {
    if (current.generation === generation) { current.requestState = 'error'; current.pollError = '状态更新中断，请重试获取状态；后台任务仍会继续' }
  } finally {
    if (current.generation === generation && current.requestState !== 'error') current.requestState = 'idle'
  }
}
function startRecognition() {
  if (busy.value || batchRetry.value) return
  if (recognizing.value) return
  const retries = groups.value.filter(entry => entry.requestState === 'error')
  if (retries.length) {
    for (const current of retries) {
      current.pollError = ''
      if (current.jobId !== null) void monitorJob(current, current.jobId, ++current.generation, true)
      else void recognizeGroup(current)
    }
    return
  }
  for (const current of groups.value) {
    void recognizeGroup(current).catch(problem => { error.value = problem instanceof Error ? problem.message : '识别失败，可以手动填写' })
  }
}
async function download(kind: 'xlsx' | 'docx') {
  await perform(async () => {
    const selected = selectedVisible.value
    if (!selected.length) throw new Error('请先选择要导出的记录')
    if (kind === 'docx' && selected.some(record => !record.inspection_enabled)) {
      window.alert('所选记录中有未检验记录，请取消勾选未检验记录后导出 Word')
      return
    }
    const pending = selected.some(r => r.status === 'pending')
    if (pending && !window.confirm('所选记录包含待核对内容，仍要导出吗？')) return
    const template = user.value ? await readExportTemplate(user.value.id, kind) : null
    const response = await raw(`/exports/${kind}`, json('POST', { record_ids: selected.map(r => r.id), include_pending: pending, template_base64: template }))
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a'); anchor.href = url
    const encodedName = response.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    anchor.download = encodedName ? decodeURIComponent(encodedName) : kind === 'xlsx' ? '原辅料查验记录.xlsx' : selected.length === 1 ? '原辅料检验报告.docx' : '原辅料检验报告.zip'
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}
</script>

<template>
  <div v-if="loading" class="loading">正在加载台账…</div>
  <main v-else-if="!user" class="login-page">
    <section class="login-brand"><span class="brand-mark">验</span><h1>原辅料查验</h1><p>从包装照片到查验记录，<br>每一项信息，由人员核对。</p><div class="brand-line"></div><p class="small">公司台账 · 图片核对 · 检验报告</p></section>
    <form class="login-form" @submit.prevent="login">
      <h2>{{ setup ? '建立第一个管理员账号' : '登录工作台' }}</h2>
      <p class="muted">{{ setup ? '完成后，其他人员账号由管理员建立。' : '使用管理员分配的账号登录。' }}</p>
      <label>账号<input v-model="credentials.username" autocomplete="username" required maxlength="80"></label>
      <label>密码<input v-model="credentials.password" type="password" :autocomplete="setup ? 'new-password' : 'current-password'" required minlength="10"></label>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <button class="primary" :disabled="busy">{{ setup ? '创建管理员' : '登录' }}</button>
    </form>
  </main>
  <div v-else class="workspace">
    <header class="topbar"><button class="brand-button" @click="view = 'home'; ledger = null"><span class="brand-mark small-mark">验</span>原辅料查验</button><div class="company-context">{{ ledger?.name || '公司台账' }}</div><div class="account"><button class="quiet" :disabled="busy || !!batchRetry" @click="openRecycle">回收站</button><button class="quiet" @click="openTemplates">我的模板</button><button v-if="administrator" class="quiet admin-entry" @click="view = 'admin'">管理与公共资料</button><span>{{ user.username }} <small>{{ user.role === 'superadmin' ? '超级管理员' : administrator ? '管理员' : '普通用户' }}</small></span><button class="quiet" @click="logout">退出</button></div></header>
    <div v-if="error" class="global-message error" role="alert">{{ error }}<button class="quiet" @click="error = ''">关闭</button></div>
    <div v-if="notice" class="global-message success" role="status">{{ notice }}</div>
    <RecycleBin v-if="view === 'recycle'" :administrator="administrator" :ledgers="ledgers" :ledger-id="allCompanies ? null : ledger?.id || null" @close="closeRecycle" @open="openRecycledRecord" /><LocalTemplatesPanel v-else-if="view === 'templates'" :user-id="user.id" :return-label="returnToEditor ? '返回录入界面' : '返回公司台账'" @close="closeTemplates" /><AdminPanel :current-user="user" @user-updated="user = $event" @reauthenticate="reauthenticate" v-else-if="view === 'admin' && administrator" @close="view = 'home'; ledger = null; loadLedgers()" /><main v-else-if="view === 'home'" class="page home-page">
      <div class="page-heading"><div><h1>选择公司台账</h1><p class="muted">先进入台账，再上传图片或录入查验记录。</p></div><div class="button-row"><button @click="showAllRecords">查看全部记录</button><button v-if="administrator" class="primary" @click="createLedger = true">新建公司台账</button></div></div>
      <div v-if="!ledgers.length" class="empty">{{ administrator ? '还没有公司台账，请先建立。' : '还没有公司台账，请联系管理员建立。' }}</div>
      <div class="ledger-grid"><button v-for="entry in ledgers" :key="entry.id" class="ledger-entry" :aria-label="`进入${entry.name}`" @click="enterLedger(entry)"><span class="ledger-symbol">{{ Array.from(entry.name.trim())[0] }}</span><strong>{{ entry.name }}</strong><span class="muted">查验记录与检验报告</span><span class="enter-label">进入台账</span></button></div>
    </main>
    <main v-else-if="view === 'ledger'" class="page">
      <nav class="breadcrumb"><button @click="view = 'home'; ledger = null">公司台账</button><span>/</span><span>{{ allCompanies ? '全部台账' : ledger?.name }}</span></nav>
      <div class="page-heading"><div><h1>原辅料查验记录</h1><p class="muted">查看全部记录，核对与修改自己的记录。</p></div><button v-if="!allCompanies" class="primary" @click="openEditor()">上传与录入</button></div>
      <section class="table-panel">
        <div class="filters"><label class="search-label">查找记录<input v-model="filter.text" type="search" placeholder="物料、供应商、规格、备注或记录编号"></label><label>状态<select v-model="filter.status"><option value="">全部状态</option><option value="pending">待核对</option><option value="checked">已核对</option></select></label><label>到货日期从<input v-model="filter.from" type="date"></label><label>到<input v-model="filter.to" type="date"></label><label>创建人<select v-model="filter.creator"><option :value="0">所有人员</option><option v-for="person in people" :key="person.id" :value="person.id">{{ person.username }}</option></select></label><label>检验状态<select v-model="filter.inspection" aria-label="筛选检验状态"><option value="">全部</option><option value="inspected">检验</option><option value="uninspected">未检验</option></select></label><label v-if="allCompanies">公司台账<select v-model="filter.ledger" aria-label="筛选公司台账"><option :value="0">全部公司</option><option v-for="company in ledgers" :key="company.id" :value="company.id">{{ company.name }}</option></select></label><label class="checkbox-label"><input v-model="filter.mine" type="checkbox">我创建的</label><button @click="clearRecordFilters">清空筛选</button></div>
        <p class="muted">先勾选需要导出的记录。Excel 按公司分表；多条 Word 每条一份报告，打包为 ZIP 下载。</p><div class="table-actions"><span>共 {{ filteredRecords.length }} 条 · 已选 {{ selectedVisible.length }} 条</span><div><button @click="selectedIds = filteredRecords.filter(r => r.status !== 'void').map(r => r.id)">全选当前记录</button><button @click="selectedIds = []">清空选择</button><button v-if="administrator" class="danger-button" :disabled="busy || !selectedVisible.length" @click="voidSelected">批量作废</button><button :disabled="busy || !selectedVisible.length" @click="openPreview(selectedVisible.map(record => record.id))">预览 / 打印</button><button :disabled="busy || !selectedVisible.length" @click="download('xlsx')">导出 Excel</button><button :disabled="busy || !selectedVisible.length" @click="download('docx')">导出 Word</button></div></div>
        <div class="table-scroll"><table class="ledger-table"><thead><tr><th>选择</th><th v-if="allCompanies" :aria-sort="sortDirection('ledger')"><button class="sort-heading" aria-label="按公司台账排序" @click="toggleSort('ledger')">公司台账 <span aria-hidden="true">{{ sort?.key === 'ledger' ? (sort.ascending ? '↑' : '↓') : '↕' }}</span></button></th><th v-for="column in ledgerColumns" :key="column.key" :aria-sort="sortDirection(column.key)"><button class="sort-heading" :aria-label="`按${column.label}排序`" @click="toggleSort(column.key)">{{ column.label }} <span aria-hidden="true">{{ sort?.key === column.key ? (sort.ascending ? '↑' : '↓') : '↕' }}</span></button></th><th>操作</th></tr></thead><tbody><tr v-for="record in tableRecords" :key="record.id"><td><input v-model="selectedIds" type="checkbox" :value="record.id" :disabled="record.status === 'void'" :aria-label="`选择记录${record.id}`"></td><td v-if="allCompanies">{{ ledgers.find(l => l.id === record.ledger_id)?.name }}</td><td class="dates-cell">{{ entryDate(record.created_at) }}</td><td class="arrival-date">{{ record.fields.arrival_date || '—' }}</td><td class="material-cell">{{ record.fields.material_name || '未填写物料' }}</td><td class="dates-cell">{{ record.fields.production_dates.join('、') || '—' }}</td><td>{{ record.fields.company_name || '—' }}</td><td>{{ record.fields.received_quantity || '—' }}</td><td><span class="inspection-status" :class="{ enabled: record.inspection_enabled }">{{ record.inspection_enabled ? '检验' : '未检验' }}</span></td><td><span class="status" :class="record.status">{{ statusText[record.status] }}</span></td><td><button class="text-button" @click="openPreview([record.id])">查看</button><button class="text-button" @click="openEditor(record)">{{ record.status !== 'void' && (administrator || user.id === record.creator_id) ? '核对 / 编辑' : '查看记录' }}</button><button v-if="administrator && record.status !== 'void'" class="text-button danger-button" :disabled="busy" @click="voidRecord(record)">作废</button></td></tr></tbody></table></div>
        <div v-if="!filteredRecords.length" class="empty">暂无记录。点击“上传与录入”开始。</div>
      </section>
    </main>
    <main v-else class="editor-page">
      <nav class="breadcrumb"><button @click="leaveEditor">{{ editorReturn === 'recycle' ? '回收站' : ledger?.name + '台账' }}</button><span>/</span><span>{{ editing ? '查看与核对' : '新增查验记录' }}</span></nav>
      <div class="editor-heading"><div><h1>{{ editing ? fields.material_name || '查验记录' : '图片识别与核对' }}</h1><p class="muted">对照原图核对，未获取的信息可以手动填写或留空。</p></div><div v-if="editing" class="record-meta"><span class="status" :class="editing.status">{{ statusText[editing.status] }}</span><small>创建人：{{ people.find(p => p.id === editing?.creator_id)?.username }}<br>核对人：{{ people.find(p => p.id === editing?.checker_id)?.username || '未核对' }}</small><button @click="showHistory">查看修改历史</button><button v-if="administrator && editing.status !== 'void'" class="danger-button" :disabled="busy" @click="voidRecord()">作废记录</button></div></div>
      <section v-if="editable" class="upload-toolbar"><div class="mode-switch"><button :class="{ active: mode === 'same' }" :disabled="busy || !!batchRetry" @click="mode = 'same'">同一物料多图</button><button :class="{ active: mode === 'batch' }" :disabled="!!editing || busy || !!batchRetry" @click="mode = 'batch'">多种物料批量</button></div><label class="checkbox-label"><input v-model="cloudEnabled" type="checkbox" :disabled="recognizing">云端辅助</label><small>启用后会将照片发送给智谱；不可用时保留本地结果</small>
        <section class="recognition-controls" aria-label="识别操作与进度">
          <button class="primary" :disabled="busy || !!batchRetry || recognizing || !groups.some(g => g.images.length)" @click="startRecognition">{{ recognizing ? '识别处理中…' : interrupted ? '重试获取状态' : '开始识别' }}</button>
          <div v-if="recognitionLabel" class="recognition-progress" :class="{ working: recognizing, failed: group?.requestState === 'error' || group?.job?.local_status === 'failed' }" role="status" aria-live="polite">
            <strong><span v-if="recognizing" class="recognition-spinner" aria-hidden="true"></span>{{ recognitionLabel }}</strong>
            <span v-if="group?.job">云端辅助：{{ { queued: '等待本地结果', running: '处理中，可先填写或保存', done: '建议已返回', failed: '不可用，本地结果仍可使用', disabled: '未启用' }[group.job.cloud_status] }}</span>
            <span v-if="group?.job?.cloud_status === 'failed' && group.job.cloud_error" class="error">{{ group.job.cloud_error }}</span>
            <span v-if="recognizing">可继续人工填写，无需重复点击识别</span>
          </div>
        </section>
      </section>
      <p v-for="suggestion in groupingSuggestions" :key="suggestion" class="notice">{{ suggestion }}</p><div class="editor-grid"><aside class="image-panel"><div class="panel-heading"><h2>包装图片</h2><button class="text-button" @click="showPhoto = !showPhoto">{{ showPhoto ? '折叠图片' : '展开图片' }}</button></div><p aria-label="当前图片分组" class="muted">记录 {{ activeGroup + 1 }} · {{ group?.images.length || 0 }} 张</p>
        <div v-if="editable" class="upload-drop" @dragover.prevent @drop.prevent="uploadFiles($event.dataTransfer?.files || null)"><label class="file-picker">选择照片 / 相册<input type="file" accept="image/jpeg,image/png,image/webp" multiple aria-label="选择包装照片" :disabled="busy || !!batchRetry" @change="fileChosen"></label><label class="file-picker camera-picker">拍照<input type="file" accept="image/*" capture="environment" aria-label="拍摄包装照片" :disabled="busy || !!batchRetry" @change="fileChosen"></label><small>支持拖入照片，每张最多 20MB</small></div>
        <div v-if="showPhoto" class="photo-workspace"><BatchGroups v-if="groups.length > 1 || (!editing && mode === 'batch')" :groups="groups" :active-index="activeGroup" :selected-image="selectedImage" :selected-keys="selectedGroupKeys" :selection-enabled="!editing && mode === 'batch'" :disabled="busy || !!batchRetry" @select="switchGroup" @preview="previewGroup" @merge="mergeGroups" @toggle-selection="toggleGroupSelection" @reorder="reorderGroups" /><div class="image-stage"><div v-if="selectedImage" class="photo-viewer"><img :src="`/api/images/${selectedImage}`" alt="当前包装原图" :style="{ transform: `rotate(${angle}deg)` }" @click="showLarge = true"></div><div v-else class="image-placeholder"><div class="picture-icon">▧</div><p>本条记录暂无图片</p><small>可以先手动填写并保存</small></div><div v-if="selectedImage" class="photo-actions"><button @click="angle += 90">旋转查看</button><button @click="showLarge = true">放大原图</button></div><div class="thumbnails"><div v-for="photo in group?.images || []" :key="photo" class="thumbnail"><button :class="{ active: selectedImage === photo }" @click="selectedImage = photo; angle = 0"><img :src="`/api/images/${photo}`" alt="包装图片缩略图"></button><template v-if="editable"><button class="text-button" @click="removeImage(photo)">移除</button><button v-if="!editing && (group?.images.length || 0) > 1" class="text-button" @click="splitImage(photo)">拆成一组</button><select v-if="!editing && groups.length > 1" aria-label="移动图片到分组" :value="group?.key" @change="imageDestination($event, photo)"><option v-for="(entry, index) in groups" :key="entry.key" :value="entry.key">记录 {{ index + 1 }}</option></select></template></div></div></div></div>
        <div v-if="group?.job" class="recognition-result">
          <section v-if="group.job.review_suggestions.sources.length" class="review-feedback" aria-label="历史复核参考">
            <h3>{{ group.historyAppliedKey ? '已自动带入历史台账' : '同种物料历史台账' }}</h3>
            <p v-if="group.historyAppliedKey">本次识别为同种物料，已采用最近一次已核对台账及检验信息，可继续修改，需按本次实际检验核对。人工已填写内容保留；日期、保质期、数量及批号使用本次信息。</p>
            <p v-else>找到同种物料最近一次已核对记录，当前已保存内容保持不变。</p>
            <p v-for="source in group.job.review_suggestions.sources" :key="source.record_id">来源：{{ source.ledger_name }} · 记录 #{{ source.record_id }} · 版本 {{ source.version }} · {{ new Date(source.checked_at).toLocaleDateString('zh-CN') }} 已核对</p>
          </section>
          <p v-else-if="group.job.review_suggestions.message" class="muted" role="status" aria-label="历史匹配状态">{{ group.job.review_suggestions.message }}</p>
          <p v-if="group.job.english_detected" class="notice" role="status" aria-label="英文包装识别">已识别到英文包装。{{ group.job.cloud_status === 'done' ? '中文翻译建议已返回，请对照英文原文确认；未翻译的原文仍可手动选择填入。' : group.job.cloud_status === 'failed' || group.job.cloud_status === 'disabled' ? '中文翻译暂不可用，本地英文原文和字段建议已保留，可直接选择填入或人工翻译。' : '正在请求云端中文翻译；原文保留供核对。' }}</p>
          <details v-if="group.job.evidence.length"><summary>原始识别文字</summary><pre>{{ group.job.evidence.map(e => [e.texts.join('\n'), ...e.supplements.map(s => '局部或倾斜校正识别：\n' + s.texts.join('\n'))].join('\n\n')).join('\n\n') }}</pre></details>
          <details v-if="localSuggestions.length"><summary>本地字段建议</summary><div v-for="[key, value] in localSuggestions" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" :disabled="busy || !!batchRetry" @click="applySuggestion(key, value)">填入</button></div></details>
          <div v-for="(values, key) in group.job.conflicts" :key="key" class="conflict"><p>{{ fieldNames[key] || key }}存在多个识别值，请对照原图选择：</p><button v-for="value in values" :key="value" :disabled="!editable || busy || !!batchRetry" @click="applySuggestion(key, value)">{{ value }}</button></div>
          <div v-if="suggestedFields.length"><h3>云端建议</h3><p class="muted">按需填入，不自动覆盖人工修改。</p><div v-for="[key, value] in suggestedFields" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" :disabled="busy || !!batchRetry" @click="applySuggestion(key, value)">填入</button></div></div>
        </div>
      </aside>
        <div class="form-panel"><fieldset :disabled="!editable || busy || !!batchRetry" @input="markDirty('manual')" @change="markDirty('manual')"><section class="form-section"><h2>基本信息</h2><p class="muted">匹配同种物料后自动带入最近已核对台账；人工已填内容保留，日期、保质期和数量使用本次信息。</p><button v-if="administrator" type="button" @click="reviewMaterial">保存为物料信息</button><label class="library-selector">选择共享物料<select :value="group?.materialId || ''" @change="chooseMaterial"><option value="">不选择，手动填写</option><option v-for="material in catalog" :key="material.id" :value="material.id">{{ [material.name, material.model].filter(Boolean).join(' ') }}</option></select></label><div class="field-grid"><label>到货日期<input v-model="fields.arrival_date" type="date" aria-label="到货日期"><FieldSuggestions label="到货日期" :values="suggestionsFor('arrival_date')" :warnings="warningsFor('arrival_date')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('arrival_date', $event)" /><small>默认录入日期，可修改或清空</small></label><template v-for="field in textFields" :key="field.key"><label>{{ field.label }}<input v-model="fields[field.key]" @input="markDirty(field.key)" @blur="field.key === 'shelf_life' && normalizeEntryShelfLife()" :aria-label="field.label"><FieldSuggestions :label="field.label" :values="suggestionsFor(field.key)" :warnings="warningsFor(field.key)" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion(field.key, $event)" /></label><label v-if="field.key === 'shelf_life'">保质期至<input v-model="fields.expiry_date" type="date" @input="markDirty('expiry_date')" aria-label="保质期至"><FieldSuggestions label="保质期至" :values="suggestionsFor('expiry_date')" :warnings="warningsFor('expiry_date')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('expiry_date', $event)" /></label></template><label class="wide">生产日期<input v-model="productionDates" placeholder="2026.01.14，多个日期用顿号分隔" aria-label="生产日期"><FieldSuggestions label="生产日期" :values="suggestionsFor('production_dates')" :warnings="warningsFor('production_dates')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('production_dates', $event)" /></label></div><p v-for="warning in expiryWarnings" :key="warning" class="notice" role="status">{{ warning }}</p></section>
          <section class="form-section"><h2>选用单位资料</h2><label>共享单位<select v-model="partnerId"><option :value="0">选择供应商或生产商资料</option><option v-for="partner in partners" :key="partner.id" :value="partner.id">{{ partner.name }}（{{ partner.kind === 'supplier' ? '供应商' : '生产商' }}）</option></select></label><div class="button-row"><button :disabled="!partnerId" @click="fillPartner('name')">填入单位名称</button><button :disabled="!partnerId" @click="fillPartner('contact')">填入地址和联系方式</button></div><div class="field-grid"><label>地址来源<select aria-label="地址来源" v-model="fields.address_source" @change="markDirty('address_source')"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商，导出时注明</option></select></label><label>联系方式来源<select aria-label="联系方式来源" v-model="fields.contact_source" @change="markDirty('contact_source')"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商，导出时注明</option></select></label></div></section>
          <section class="form-section"><h2>随车证件与感官检查</h2><div class="field-grid"><div class="wide"><CertificatePicker v-model="fields.certificates" @update:model-value="markDirty('certificates')" /><FieldSuggestions label="随车证件" :values="suggestionsFor('certificates')" :warnings="warningsFor('certificates')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('certificates', $event)" /></div><label class="wide">感官检验<textarea v-model="fields.sensory" @input="markDirty('sensory')" rows="2" placeholder="外包装、感官状态、标签情况；本次手动填写" aria-label="感官检验"></textarea><FieldSuggestions label="感官检验" :values="suggestionsFor('sensory')" :warnings="warningsFor('sensory')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('sensory', $event)" /></label><label class="wide">抽检项目<input v-model="fields.sampling_items" @input="markDirty('sampling_items')" aria-label="抽检项目"><FieldSuggestions label="抽检项目" :values="suggestionsFor('sampling_items')" :warnings="warningsFor('sampling_items')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('sampling_items', $event)" /></label><label class="wide">备注<textarea v-model="fields.notes" @input="markDirty('notes')" rows="2" aria-label="备注"></textarea><FieldSuggestions label="备注" :values="suggestionsFor('notes')" :warnings="warningsFor('notes')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('notes', $event)" /></label></div></section>
          <section v-if="group" class="form-section inspection-mode"><h2>检验</h2><div class="button-row"><label><input v-model="group.inspectionEnabled" type="radio" name="inspection-mode" @change="markDirty('inspection_enabled')" :value="false">未检验</label><label><input v-model="group.inspectionEnabled" type="radio" name="inspection-mode" @change="markDirty('inspection_enabled')" :value="true">检验</label></div><p v-if="!group.inspectionEnabled" class="muted">检验项目与报告信息已收起并锁定，已有内容保留；未检验记录不能导出 Word 报告。</p></section>
          <section v-if="group?.inspectionEnabled" class="form-section"><h2>检验项目</h2><button v-if="administrator" type="button" @click="reviewScheme">保存为检验标准方案</button><label class="library-selector">检验标准方案<select aria-label="检验标准方案" :value="group?.schemeId || ''" @change="chooseScheme"><option value="">不选择方案</option><option v-for="scheme in availableSchemes" :key="scheme.id" :value="scheme.id">{{ scheme.name }}</option></select></label><p v-if="editing" class="muted">保存时采用：{{ editing.scheme_name || '未选择方案' }}，当前项目为保存时的快照。</p><p class="muted">所有物料均可选用任一方案。结果与结论支持选择或输入，可以留空；沿用历史内容后请核对本次结果。</p><div class="button-row"><label>已维护检验项目<select aria-label="已维护检验项目" v-model="maintainedItemKey"><option value="">选择单个项目</option><option v-for="entry in maintainedItems" :key="entry.key" :value="entry.key">{{ entry.label }}</option></select></label><button type="button" :disabled="!maintainedItemKey" @click="addMaintainedItem">添加选中项目</button></div><div v-for="(item, index) in items" :key="index" class="inspection-row"><label>项目<input v-model="item.name" @input="markDirty('items')"></label><label>标准规定<input v-model="item.standard" @input="markDirty('items')"></label><InspectionChoice v-model="item.result" kind="result" @update:model-value="markDirty('items')" /><InspectionChoice v-model="item.conclusion" kind="conclusion" @update:model-value="markDirty('items')" /><button type="button" class="text-button remove-inspection" :aria-label="`移除检验项目 ${item.name || index + 1}`" @click="removeInspectionItem(index)">移除项目</button></div><button type="button" @click="items.push({ name: '', standard: '', unit: '', result: '', conclusion: '' }); markDirty('items')">添加检验项目</button></section>
          <section v-if="group?.inspectionEnabled" class="form-section"><h2>报告信息</h2><div class="field-grid"><label>包装<input v-model="report.packaging" @input="markDirty('report.packaging')" aria-label="包装"><FieldSuggestions label="包装" :values="suggestionsFor('packaging')" :warnings="warningsFor('packaging')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('packaging', $event)" /></label><label>产品批号<input v-model="report.batch_number" aria-label="产品批号" @input="markDirty('report.batch_number')"><FieldSuggestions label="产品批号" :values="suggestionsFor('batch_number')" :warnings="warningsFor('batch_number')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('batch_number', $event)" /></label><label>检验依据<input v-model="report.basis" aria-label="检验依据" @input="markDirty('report.basis')"><FieldSuggestions label="检验依据" :values="suggestionsFor('basis')" :warnings="warningsFor('basis')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('basis', $event)" /><small>默认选用方案名称，可自行修改</small></label><label>检验日期<input v-model="report.inspection_date" type="date" aria-label="检验日期" @input="markDirty('report.inspection_date')"><FieldSuggestions label="检验日期" :values="suggestionsFor('inspection_date')" :warnings="warningsFor('inspection_date')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('inspection_date', $event)" /></label><label>是否提供内检报告<select v-model="report.internal_report" aria-label="是否提供内检报告" @change="markDirty('report.internal_report')"><option value="">留空</option><option>是</option><option>否</option></select><FieldSuggestions label="是否提供内检报告" :values="suggestionsFor('internal_report')" :warnings="warningsFor('internal_report')" :disabled="!editable || busy || !!batchRetry" @choose="applySuggestion('internal_report', $event)" /></label><label class="wide">结论<textarea v-model="report.conclusion" rows="2" @input="markDirty('report.conclusion')"></textarea></label></div><p class="muted">如需修改检验员和批准签名，请修改模板中的签名图片。<button type="button" class="text-button" @click="openTemplates">修改模板文件</button></p></section>
        </fieldset><ReportAttachments v-if="group" :key="group.key" :pending-files="group.pendingReports" @files-changed="group.pendingReports = $event" :record-id="editing?.id || group.savedRecord?.id || null" :record-version="editing?.version || group.savedRecord?.version || null" :editable="editable && !busy && (!batchRetry || !!group.savedRecord)" @record-changed="updateAttachmentRecord" /></div></div>
      <footer class="savebar save-bar">
        <div class="save-summary"><span>{{ editable ? '业务字段允许留空' : '当前记录只读' }}</span><template v-if="editable && !editing && mode === 'batch'"><span>共 {{ groups.length }} 条，已选 {{ selectedGroups.length }} 条</span><button :disabled="busy || !!batchRetry" @click="selectedGroupKeys = groups.map(entry => entry.key)">全选分组</button><button :disabled="busy || !!batchRetry" @click="selectedGroupKeys = []">全部清空</button></template></div>
        <div class="save-actions"><button :disabled="busy || !!batchRetry" @click="leaveEditor">{{ editorReturn === 'recycle' ? '返回回收站' : '返回台账' }}</button>
          <template v-if="editable && selectionSaving"><label class="checkbox-label"><input v-model="markBatchChecked" type="checkbox" :disabled="busy || !!batchRetry">同时标记为已核对</label><button class="primary" :disabled="busy || recognizing" @click="saveBatch">{{ busy ? '正在保存…' : batchRetry ? '重试批量保存' : `保存所选 ${selectedGroups.length} 条记录` }}</button></template>
          <template v-else-if="editable"><button :disabled="busy || !!batchRetry" @click="save(false)">保存记录</button><button class="primary" :disabled="busy || !!batchRetry" @click="save(true)">保存并标记已核对</button></template>
        </div>
      </footer>
    </main>
    <ReportPreview v-if="previewIds.length" :user-id="user.id" :record-ids="previewIds" @close="previewIds = []" />
    <el-dialog v-model="saveSchemeOpen" title="保存为检验标准方案" width="min(720px, 95vw)" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy"><form @submit.prevent="saveSchemeInfo"><fieldset :disabled="busy"><p class="muted">核对后新增共享方案，只保存项目名称和标准规定。本次检验结果与结论保留在当前记录中，记录仍需另行保存。</p><p v-if="schemeSaveError" role="alert" class="error">{{ schemeSaveError }}</p><div class="field-grid"><label>方案名称<input v-model="schemeDraft.name" maxlength="120" required></label><label>方案所属物料<select v-model="schemeDraft.material_id" aria-label="方案所属物料"><option :value="null">不绑定物料（通用方案）</option><option v-for="material in catalog" :key="material.id" :value="material.id">{{ [material.name, material.model].filter(Boolean).join(' ') }}</option></select></label></div><div v-for="(item, index) in schemeDraft.items" :key="index" class="field-grid"><label>项目名称<input v-model="item.name"></label><label>标准规定<input v-model="item.standard"></label></div><p v-if="!schemeDraft.items.length" class="muted">当前没有检验项目，可返回录入界面添加后再保存。</p><div class="button-row"><button type="submit" class="primary" :disabled="!schemeDraft.items.length">确认新增方案</button><button type="button" @click="saveSchemeOpen = false">取消</button></div></fieldset></form></el-dialog>
    <el-dialog v-model="saveMaterialOpen" title="保存为物料信息" width="min(720px, 95vw)" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy"><form @submit.prevent="saveMaterialInfo"><fieldset :disabled="busy"><p class="muted">核对后新增一条共享物料，不覆盖已有物料。只保存共享物料资料，本次查验记录仍需另行保存。</p><p v-if="materialSaveError" role="alert" class="error">{{ materialSaveError }}</p><div class="field-grid"><label>物料名称<input v-model="materialDraft.name" required></label><label>型号<input v-model="materialDraft.model"></label><label>常用别名<input v-model="materialDraft.aliases"></label><label>规格<input v-model="materialDraft.specification"></label><label>包装<input v-model="materialDraft.packaging"></label><label>供应商或生产商<input v-model="materialDraft.company_name"></label><label>地址<input v-model="materialDraft.address"></label><label>联系方式<input v-model="materialDraft.contact"></label><label>保质期<input v-model="materialDraft.shelf_life" @blur="normalizeMaterialDraftShelfLife"></label><label>地址来源<select v-model="materialDraft.address_source"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商</option></select></label><label>联系方式来源<select v-model="materialDraft.contact_source"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商</option></select></label></div><p v-if="shelfLifeDayNotice(materialDraft.shelf_life)" class="notice" role="status">{{ shelfLifeDayNotice(materialDraft.shelf_life) }}</p><div class="button-row"><button type="submit" class="primary">确认新增物料</button><button type="button" @click="saveMaterialOpen = false">取消</button></div></fieldset></form></el-dialog>
    <el-dialog v-model="createLedger" title="新建公司台账" width="min(480px, 92vw)"><form @submit.prevent="addLedger"><label>公司台账名称<input v-model="ledgerName" maxlength="31" required></label><p class="muted">将用作 Excel 工作表名称，最多31个字符。</p><button class="primary" :disabled="busy">建立台账</button></form></el-dialog>
    <el-dialog v-model="historyOpen" title="修改历史" width="min(850px, 95vw)"><article v-for="entry in histories" :key="entry.at" class="history-entry"><h3>{{ actionNames[entry.action] || entry.action }}</h3><p class="muted">{{ people.find(p => p.id === entry.actor_id)?.username }} · {{ new Date(entry.at).toLocaleString('zh-CN') }} · 版本 {{ entry.snapshot.version }}</p><details><summary>查看当时内容</summary><dl><template v-for="(value, key) in entry.snapshot.fields" :key="key"><dt>{{ fieldNames[key] || key }}</dt><dd>{{ formatSuggestion(value) || '（空白）' }}</dd></template></dl><div v-for="(item, index) in entry.snapshot.items" :key="index">{{ item.name }} / {{ item.standard }} / {{ item.result }} / {{ item.conclusion }}</div></details></article><button @click="historyOpen = false">关闭历史</button></el-dialog><el-dialog v-model="showLarge" title="包装原图" width="min(1100px, 96vw)"><img v-if="selectedImage" :src="`/api/images/${selectedImage}`" alt="包装图片放大预览" class="large-photo"></el-dialog>
  </div>
</template>
