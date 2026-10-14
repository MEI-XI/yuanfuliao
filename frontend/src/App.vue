<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import { api, raw, json, today, userSchema, ledgerSchema, recordSchema, fieldsSchema, reportSchema, jobSchema, type User, type Ledger, type CheckRecord, type Fields, type Item, type Job } from './api'
import './style.css'
import AdminPanel from './AdminPanel.vue'
import BatchGroups from './BatchGroups.vue'
import LocalTemplatesPanel from './LocalTemplatesPanel.vue'
import { readExportTemplate } from './localTemplates'
import { materialSchema, schemeSchema, partnerSchema } from './api'

const user = ref<User | null>(null)
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
const actionNames: Record<string, string> = { created: '创建记录', checked: '核对记录', edited: '修改记录', voided: '作废记录' }
const view = ref<'home' | 'ledger' | 'editor' | 'admin' | 'templates'>('home')
const returnToEditor = ref(false)
function openTemplates() {
  if (view.value === 'templates') return
  returnToEditor.value = view.value === 'editor'; view.value = 'templates'
}
function closeTemplates() { view.value = returnToEditor.value ? 'editor' : 'home'; if (!returnToEditor.value) ledger.value = null }
const createLedger = ref(false)
const ledgerName = ref('')
const records = ref<CheckRecord[]>([])
const selectedIds = ref<number[]>([])
const filter = reactive({ text: '', status: '', from: '', to: '', mine: false, creator: 0 })
const editing = ref<CheckRecord | null>(null)
const fields = ref(fieldsSchema.parse({}))
const report = ref(reportSchema.parse({}))
const items = ref<Item[]>([])
type DraftGroup = { key: number; inspectionEnabled: boolean; images: number[]; fields: Fields; report: z.infer<typeof reportSchema>; items: Item[]; dirty: Set<string>; job: Job | null; jobId: number | null; generation: number; materialId: number | null; schemeId: number | null; schemeChanged: boolean; materialChanged: boolean; requestState: 'idle' | 'submitting' | 'polling' | 'error'; pollError: string }
let nextGroupKey = 0
const groups = ref<DraftGroup[]>([])
const activeGroup = ref(0)
const group = computed(() => groups.value[activeGroup.value])
const mode = ref<'same' | 'batch'>('same')
const cloudEnabled = ref(true)
const selectedImage = ref(0)
const angle = ref(0)
const showLarge = ref(false)
const showPhoto = ref(true)
const suggestedFields = computed(() => Object.entries(group.value?.job?.cloud_fields || {}))
const localSuggestions = computed(() => Object.entries(group.value?.job?.fields || {}))
const fieldNames: Record<string, string> = { arrival_date: '到货日期', received_quantity: '接收数量', certificates: '随车证件', sensory: '感官检验', sampling_items: '抽检项目', notes: '备注', material_name: '物料名称、型号', production_dates: '生产日期', specification: '规格', company_name: '供应商或生产商', address: '地址', contact: '联系方式', shelf_life: '保质期', address_source: '地址来源', contact_source: '联系方式来源' }
function makeGroup(images: number[] = []): DraftGroup { return { key: ++nextGroupKey, inspectionEnabled: false, images, fields: fieldsSchema.parse({ arrival_date: today() }), report: reportSchema.parse({ inspection_date: today() }), items: [], dirty: new Set(), job: null, jobId: null, generation: 0, materialId: null, schemeId: null, schemeChanged: false, materialChanged: false, requestState: 'idle', pollError: '' } }
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
const availableSchemes = computed(() => standards.value)
const maintainedItemKey = ref('')
const maintainedItems = computed(() => standards.value.flatMap(scheme => scheme.items.map((item, index) => ({ key: `${scheme.id}:${index}`, label: `${scheme.name} / ${item.name} / ${item.standard}`, item }))))
function addMaintainedItem() {
  const choice = maintainedItems.value.find(entry => entry.key === maintainedItemKey.value)
  if (!choice) return
  items.value.push({ ...choice.item, result: '', conclusion: '' })
  fields.value.sampling_items = items.value.map(item => item.name).filter(Boolean).join('、')
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
  const scheme = standards.value.find(s => s.id === schemeId)
  group.value.schemeId = schemeId; group.value.schemeChanged = true
  group.value.items = scheme ? scheme.items.map(i => ({ ...i, result: '', conclusion: '' })) : []
  items.value = group.value.items
  fields.value.sampling_items = items.value.map(i => i.name).filter(Boolean).join('、')
}
function chooseMaterial(event: Event) {
  if (!(event.target instanceof HTMLSelectElement) || !group.value) return
  group.value.materialId = Number(event.target.value) || null
  group.value.materialChanged = true
  const material = catalog.value.find(m => m.id === group.value?.materialId)
  if (material) { fields.value.material_name = [material.name, material.model].filter(Boolean).join(' '); markDirty('material_name') }
  const choices = standards.value.filter(s => s.material_id === group.value?.materialId)
  if (group.value.inspectionEnabled && !items.value.length && !group.value.schemeId && choices.length === 1) replaceScheme(choices[0]?.id || null)
}
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
function markDirty(key: string) { group.value?.dirty.add(key) }
function reorderGroups(from: number, to: number) {
  if (busy.value) return
  const current = group.value
  const moved = groups.value.splice(from, 1)[0]
  if (!moved) return
  groups.value.splice(to, 0, moved)
  activeGroup.value = Math.max(0, groups.value.findIndex(entry => entry === current))
}
function applyReviewSuggestion(key: string, value: unknown) {
  applySuggestion(key, value)
  if (key === 'address' || key === 'contact') {
    const sourceKey = key + '_source'
    applySuggestion(sourceKey, Reflect.get(group.value?.job?.review_suggestions.fields || {}, sourceKey) || '')
  }
}
function applySuggestion(key: string, value: unknown) {
  const parsed = fieldsSchema.safeParse({ ...fields.value, [key]: value })
  if (parsed.success) { Object.assign(fields.value, parsed.data); markDirty(key) }
}
function formatSuggestion(value: unknown) { return Array.isArray(value) ? value.join('、') : String(value ?? '') }
const editable = computed(() => !editing.value || (editing.value.status !== 'void' && (user.value?.role === 'admin' || editing.value.creator_id === user.value?.id)))
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
  (!filter.text || [r.fields.material_name, r.fields.company_name].some(v => v.includes(filter.text))) &&
  (!filter.status || r.status === filter.status) && (!filter.mine || r.creator_id === user.value?.id) && (!filter.creator || r.creator_id === filter.creator) &&
  (!filter.from || (r.fields.arrival_date || '') >= filter.from) && (!filter.to || (!!r.fields.arrival_date && r.fields.arrival_date <= filter.to)),
))

const selectedVisible = computed(() => filteredRecords.value.filter(r => r.status !== 'void' && selectedIds.value.includes(r.id)))

async function perform(work: () => Promise<void>) {
  error.value = ''; notice.value = ''; busy.value = true
  try { await work() } catch (problem) { error.value = problem instanceof Error ? problem.message : '操作失败，请重试' }
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
async function voidRecord() {
  const record = editing.value
  if (!record || !window.confirm('作废后保留历史供查阅，但不能修改或导出。确定作废这条记录吗？')) return
  await perform(async () => { await api(`/records/${record.id}/void`, recordSchema, json('POST', { version: record.version })); await loadRecords(); view.value = 'ledger'; notice.value = '记录已作废' })
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
  fields.value = fieldsSchema.parse(record?.fields || { arrival_date: today() })
  report.value = reportSchema.parse(record?.report || { inspection_date: today() })
  items.value = record ? record.items.map(i => ({ ...i })) : []
  groups.value = [{ ...makeGroup(record?.image_ids || []), inspectionEnabled: record?.inspection_enabled ?? false, fields: fields.value, report: report.value, items: items.value, jobId: record?.recognition_job_id || null, materialId: record?.material_id || null }]
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
async function save(check: boolean) {
  await perform(async () => {
    if (!ledger.value) return
    const savedGroup = group.value
    const body = { inspection_enabled: group.value?.inspectionEnabled ?? false, fields: { ...fields.value, arrival_date: fields.value.arrival_date || null }, report: { ...report.value, inspection_date: report.value.inspection_date || null }, items: items.value, image_ids: group.value?.images || [], recognition_job_id: group.value?.jobId || null }
    const record = editing.value
      ? await api(`/records/${editing.value.id}`, recordSchema, json('PATCH', { ...body, version: editing.value.version, ...(group.value?.materialChanged ? { material_id: group.value.materialId } : {}), ...(group.value?.schemeChanged ? { scheme_id: group.value.schemeId } : {}) }))
      : await api(`/ledgers/${ledger.value.id}/records`, recordSchema, json('POST', { ...body, material_id: group.value?.materialId, scheme_id: group.value?.schemeId }))
    editing.value = record
    if (check) await api(`/records/${record.id}/check`, recordSchema, json('POST', { version: record.version }))
    if (groups.value.length > 1) {
      const selectedGroup = group.value
      const savedIndex = groups.value.findIndex(entry => entry === savedGroup)
      if (savedIndex >= 0) groups.value.splice(savedIndex, 1)
      editing.value = null
      switchGroup(Math.max(0, groups.value.findIndex(entry => entry === selectedGroup)))
      notice.value = '当前记录已保存，请继续核对下一组'
    } else { await loadRecords(); view.value = 'ledger'; notice.value = check ? '记录已保存并核对' : '记录已保存，待核对' }
  })
}
async function uploadFiles(files: FileList | File[] | null) {
  if (!files || !ledger.value || !editable.value) return
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
function mergePrevious(index: number) {
  if (busy.value) return
  const current = groups.value[index]; const previous = groups.value[index - 1]
  if (!current || !previous) return
  const results = (entry: DraftGroup) => entry.items.filter(i => i.result || i.conclusion).map(i => [i.name, i.result, i.conclusion])
  if (results(current).length && results(previous).length && JSON.stringify(results(current)) !== JSON.stringify(results(previous))) {
    error.value = '两组检验结果不同，请分别保存记录'; return
  }
  if (current.dirty.size && !window.confirm('此组已有人工作业，合并后保留上一组的字段和检验结果。继续吗？')) return
  current.generation++
  previous.images.push(...current.images); invalidateRecognition(previous)
  previous.fields.production_dates = [...new Set([...previous.fields.production_dates, ...current.fields.production_dates])]
  groups.value.splice(index, 1); switchGroup(index - 1)
}
function moveImage(imageId: number, targetKey: number) {
  if (busy.value) return
  const current = group.value; const target = groups.value.find(g => g.key === targetKey)
  if (!current || !target || target === current) return
  current.images = current.images.filter(id => id !== imageId); invalidateRecognition(current)
  target.images.push(imageId); invalidateRecognition(target)
  selectedImage.value = current.images[0] || 0
}
function imageDestination(event: Event, imageId: number) { if (event.target instanceof HTMLSelectElement) moveImage(imageId, Number(event.target.value)) }
function splitImage(imageId: number) {
  if (busy.value) return
  const target = makeGroup(); groups.value.push(target); moveImage(imageId, target.key)
}
function invalidateRecognition(current: DraftGroup) { current.generation++; current.job = null; current.jobId = null; current.requestState = 'idle'; current.pollError = '' }
function removeImage(imageId: number) {
  if (busy.value) return
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
  let applied = false
  try { while (current.generation === generation && groups.value.includes(current)) {
    const job = await api(`/recognition/${jobId}`, jobSchema, { cache: 'no-store', signal: AbortSignal.timeout(15000) })
    if (current.generation !== generation) return
    current.job = job
    if (fill && !applied && job.local_status === 'done') {
      // Checked corrections take precedence only while the destination is blank.
      const proposals = { ...job.fields, ...job.review_suggestions.fields }
      for (const [key, value] of Object.entries(proposals)) {
        if (key.endsWith('_source')) continue
        const existing: unknown = Reflect.get(current.fields, key)
        const paired = key === 'address' || key === 'contact'
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
      applied = true
    }
    if (!jobActive(job)) break
    await new Promise(resolve => setTimeout(resolve, 500))
  } } catch {
    if (current.generation === generation) { current.requestState = 'error'; current.pollError = '状态更新中断，请重试获取状态；后台任务仍会继续' }
  } finally {
    if (current.generation === generation && current.requestState !== 'error') current.requestState = 'idle'
  }
}
function startRecognition() {
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
    if (kind === 'docx' && selected.some(record => !record.inspection_enabled)) throw new Error('所选记录中有未检验记录，请取消勾选未检验记录后导出 Word')
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
    <header class="topbar"><button class="brand-button" @click="view = 'home'; ledger = null"><span class="brand-mark small-mark">验</span>原辅料查验</button><div class="company-context">{{ ledger?.name || '公司台账' }}</div><div class="account"><button class="quiet" @click="openTemplates">我的模板</button><button v-if="user.role === 'admin'" class="quiet admin-entry" @click="view = 'admin'">管理与公共资料</button><span>{{ user.username }} <small>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</small></span><button class="quiet" @click="logout">退出</button></div></header>
    <div v-if="error" class="global-message error" role="alert">{{ error }}<button class="quiet" @click="error = ''">关闭</button></div>
    <div v-if="notice" class="global-message success" role="status">{{ notice }}</div>
    <LocalTemplatesPanel v-if="view === 'templates'" :user-id="user.id" :return-label="returnToEditor ? '返回录入界面' : '返回公司台账'" @close="closeTemplates" /><AdminPanel v-else-if="view === 'admin' && user.role === 'admin'" @close="view = 'home'; ledger = null; loadLedgers()" /><main v-else-if="view === 'home'" class="page home-page">
      <div class="page-heading"><div><h1>选择公司台账</h1><p class="muted">先进入台账，再上传图片或录入查验记录。</p></div><div class="button-row"><button @click="showAllRecords">查看全部记录</button><button v-if="user.role === 'admin'" class="primary" @click="createLedger = true">新建公司台账</button></div></div>
      <div v-if="!ledgers.length" class="empty">{{ user.role === 'admin' ? '还没有公司台账，请先建立。' : '还没有公司台账，请联系管理员建立。' }}</div>
      <div class="ledger-grid"><button v-for="entry in ledgers" :key="entry.id" class="ledger-entry" :aria-label="`进入${entry.name}`" @click="enterLedger(entry)"><span class="ledger-symbol">{{ Array.from(entry.name.trim())[0] }}</span><strong>{{ entry.name }}</strong><span class="muted">查验记录与检验报告</span><span class="enter-label">进入台账</span></button></div>
    </main>
    <main v-else-if="view === 'ledger'" class="page">
      <nav class="breadcrumb"><button @click="view = 'home'; ledger = null">公司台账</button><span>/</span><span>{{ allCompanies ? '全部台账' : ledger?.name }}</span></nav>
      <div class="page-heading"><div><h1>原辅料查验记录</h1><p class="muted">查看全部记录，核对与修改自己的记录。</p></div><button v-if="!allCompanies" class="primary" @click="openEditor()">上传与录入</button></div>
      <section class="table-panel">
        <div class="filters"><label class="search-label">查找记录<input v-model="filter.text" type="search" placeholder="物料名称、供应商或生产商"></label><label>状态<select v-model="filter.status"><option value="">全部状态</option><option value="pending">待核对</option><option value="checked">已核对</option><option value="void">作废</option></select></label><label>到货日期从<input v-model="filter.from" type="date"></label><label>到<input v-model="filter.to" type="date"></label><label>创建人<select v-model="filter.creator"><option :value="0">所有人员</option><option v-for="person in people" :key="person.id" :value="person.id">{{ person.username }}</option></select></label><label class="checkbox-label"><input v-model="filter.mine" type="checkbox">我创建的</label></div>
        <p class="muted">先勾选需要导出的记录。Excel 按公司分表；多条 Word 每条一份报告，打包为 ZIP 下载。</p><div class="table-actions"><span>共 {{ filteredRecords.length }} 条 · 已选 {{ selectedVisible.length }} 条</span><div><button @click="selectedIds = filteredRecords.filter(r => r.status !== 'void').map(r => r.id)">全选当前记录</button><button @click="selectedIds = []">清空选择</button><button :disabled="busy || !selectedVisible.length" @click="download('xlsx')">导出 Excel</button><button :disabled="busy || !selectedVisible.length" @click="download('docx')">导出 Word</button></div></div>
        <div class="table-scroll"><table class="ledger-table"><thead><tr><th>选择</th><th v-if="allCompanies">公司台账</th><th>到货日期</th><th>物料名称、型号</th><th>生产日期</th><th>供应商或生产商</th><th>接收数量</th><th>检验状态</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="record in filteredRecords" :key="record.id"><td><input v-model="selectedIds" type="checkbox" :value="record.id" :disabled="record.status === 'void'" :aria-label="`选择记录${record.id}`"></td><td v-if="allCompanies">{{ ledgers.find(l => l.id === record.ledger_id)?.name }}</td><td>{{ record.fields.arrival_date || '—' }}</td><td class="material-cell">{{ record.fields.material_name || '未填写物料' }}</td><td class="dates-cell">{{ record.fields.production_dates.join('、') || '—' }}</td><td>{{ record.fields.company_name || '—' }}</td><td>{{ record.fields.received_quantity || '—' }}</td><td><span class="inspection-status" :class="{ enabled: record.inspection_enabled }">{{ record.inspection_enabled ? '检验' : '未检验' }}</span></td><td><span class="status" :class="record.status">{{ statusText[record.status] }}</span></td><td><button class="text-button" @click="openEditor(record)">{{ record.status !== 'void' && (user.role === 'admin' || user.id === record.creator_id) ? '核对 / 编辑' : '查看' }}</button></td></tr></tbody></table></div>
        <div v-if="!filteredRecords.length" class="empty">暂无记录。点击“上传与录入”开始。</div>
      </section>
    </main>
    <main v-else class="editor-page">
      <nav class="breadcrumb"><button @click="view = 'ledger'">{{ ledger?.name }}台账</button><span>/</span><span>{{ editing ? '查看与核对' : '新增查验记录' }}</span></nav>
      <div class="editor-heading"><div><h1>{{ editing ? fields.material_name || '查验记录' : '图片识别与核对' }}</h1><p class="muted">对照原图核对，未获取的信息可以手动填写或留空。</p></div><div v-if="editing" class="record-meta"><span class="status" :class="editing.status">{{ statusText[editing.status] }}</span><small>创建人：{{ people.find(p => p.id === editing?.creator_id)?.username }}<br>核对人：{{ people.find(p => p.id === editing?.checker_id)?.username || '未核对' }}</small><button @click="showHistory">查看修改历史</button><button v-if="user.role === 'admin' && editing.status !== 'void'" class="danger-button" @click="voidRecord">作废记录</button></div></div>
      <section v-if="editable" class="upload-toolbar"><div class="mode-switch"><button :class="{ active: mode === 'same' }" @click="mode = 'same'">同一物料多图</button><button :class="{ active: mode === 'batch' }" :disabled="!!editing" @click="mode = 'batch'">多种物料批量</button></div><label class="checkbox-label"><input v-model="cloudEnabled" type="checkbox" :disabled="recognizing">云端辅助</label><small>启用后会将照片发送给智谱；不可用时保留本地结果</small>
        <section class="recognition-controls" aria-label="识别操作与进度">
          <button class="primary" :disabled="busy || recognizing || !groups.some(g => g.images.length)" @click="startRecognition">{{ recognizing ? '识别处理中…' : interrupted ? '重试获取状态' : '开始识别' }}</button>
          <div v-if="recognitionLabel" class="recognition-progress" :class="{ working: recognizing, failed: group?.requestState === 'error' || group?.job?.local_status === 'failed' }" role="status" aria-live="polite">
            <strong><span v-if="recognizing" class="recognition-spinner" aria-hidden="true"></span>{{ recognitionLabel }}</strong>
            <span v-if="group?.job">云端辅助：{{ { queued: '等待本地结果', running: '处理中，可先填写或保存', done: '建议已返回', failed: '不可用，本地结果仍可使用', disabled: '未启用' }[group.job.cloud_status] }}</span>
            <span v-if="group?.job?.cloud_status === 'failed' && group.job.cloud_error" class="error">{{ group.job.cloud_error }}</span>
            <span v-if="recognizing">可继续人工填写，无需重复点击识别</span>
          </div>
        </section>
      </section>
      <BatchGroups v-if="groups.length > 1" :groups="groups" :active-index="activeGroup" @select="switchGroup" @merge="mergePrevious" @reorder="reorderGroups" />
      <p v-for="suggestion in groupingSuggestions" :key="suggestion" class="notice">{{ suggestion }}</p><div class="editor-grid"><aside class="image-panel"><div class="panel-heading"><h2>包装图片</h2><button class="text-button" @click="showPhoto = !showPhoto">{{ showPhoto ? '折叠图片' : '展开图片' }}</button></div><p aria-label="当前图片分组" class="muted">记录 {{ activeGroup + 1 }} · {{ group?.images.length || 0 }} 张</p>
        <div v-if="editable" class="upload-drop" @dragover.prevent @drop.prevent="uploadFiles($event.dataTransfer?.files || null)"><label class="file-picker">选择照片 / 相册<input type="file" accept="image/jpeg,image/png,image/webp" multiple aria-label="选择包装照片" :disabled="busy" @change="fileChosen"></label><label class="file-picker camera-picker">拍照<input type="file" accept="image/*" capture="environment" aria-label="拍摄包装照片" :disabled="busy" @change="fileChosen"></label><small>支持拖入照片，每张最多 20MB</small></div>
        <template v-if="showPhoto"><div v-if="selectedImage" class="photo-viewer"><img :src="`/api/images/${selectedImage}`" alt="当前包装原图" :style="{ transform: `rotate(${angle}deg)` }" @click="showLarge = true"></div><div v-else class="image-placeholder"><div class="picture-icon">▧</div><p>本条记录暂无图片</p><small>可以先手动填写并保存</small></div><div v-if="selectedImage" class="photo-actions"><button @click="angle += 90">旋转查看</button><button @click="showLarge = true">放大原图</button></div><div class="thumbnails"><div v-for="photo in group?.images || []" :key="photo" class="thumbnail"><button :class="{ active: selectedImage === photo }" @click="selectedImage = photo; angle = 0"><img :src="`/api/images/${photo}`" alt="包装图片缩略图"></button><template v-if="editable"><button class="text-button" @click="removeImage(photo)">移除</button><button v-if="!editing && (group?.images.length || 0) > 1" class="text-button" @click="splitImage(photo)">拆成一组</button><select v-if="!editing && groups.length > 1" aria-label="移动图片到分组" :value="group?.key" @change="imageDestination($event, photo)"><option v-for="(entry, index) in groups" :key="entry.key" :value="entry.key">记录 {{ index + 1 }}</option></select></template></div></div></template>
        <div v-if="group?.job" class="recognition-result">
          <section v-if="group.job.review_suggestions.sources.length" class="review-feedback" aria-label="历史复核参考">
            <h3>已核对记录参考</h3><p>物料名称、单位及规格匹配时，仅自动补入空白字段；日期、数量和检验结果不沿用。</p>
            <p v-for="source in group.job.review_suggestions.sources" :key="source.record_id">来源：{{ source.ledger_name }} · 记录 #{{ source.record_id }} · 版本 {{ source.version }} · {{ new Date(source.checked_at).toLocaleDateString('zh-CN') }} 已核对</p>
            <div v-for="(value, key) in group.job.review_suggestions.fields" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" @click="applyReviewSuggestion(key, value)">采用</button></div>
            <p v-for="(values, key) in group.job.review_suggestions.conflicts" :key="key" class="conflict">历史{{ fieldNames[key] || key }}不一致：{{ values.join(' / ') }}，未自动采用，请核对。</p>
          </section>
          <details v-if="group.job.evidence.length"><summary>原始识别文字</summary><pre>{{ group.job.evidence.map(e => [e.texts.join('\n'), ...e.supplements.map(s => '局部或倾斜校正识别：\n' + s.texts.join('\n'))].join('\n\n')).join('\n\n') }}</pre></details>
          <details v-if="localSuggestions.length"><summary>本地字段建议</summary><div v-for="[key, value] in localSuggestions" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" @click="applySuggestion(key, value)">填入</button></div></details>
          <div v-for="(values, key) in group.job.conflicts" :key="key" class="conflict"><p>{{ fieldNames[key] || key }}存在多个识别值，请对照原图选择：</p><button v-for="value in values" :key="value" @click="applySuggestion(key, value)">{{ value }}</button></div>
          <div v-if="suggestedFields.length"><h3>云端建议</h3><p class="muted">按需填入，不自动覆盖人工修改。</p><div v-for="[key, value] in suggestedFields" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" @click="applySuggestion(key, value)">填入</button></div></div>
        </div>
      </aside>
        <div class="form-panel"><fieldset :disabled="!editable || busy" @input="markDirty('manual')" @change="markDirty('manual')"><section class="form-section"><h2>基本信息</h2><label class="library-selector">选择共享物料<select :value="group?.materialId || ''" @change="chooseMaterial"><option value="">不选择，手动填写</option><option v-for="material in catalog" :key="material.id" :value="material.id">{{ [material.name, material.model].filter(Boolean).join(' ') }}</option></select></label><div class="field-grid"><label>到货日期<input v-model="fields.arrival_date" type="date" aria-label="到货日期"><small>默认录入日期，可修改或清空</small></label><label v-for="field in textFields" :key="field.key">{{ field.label }}<input v-model="fields[field.key]" @input="markDirty(field.key)"></label><label class="wide">生产日期<input v-model="productionDates" placeholder="2026.01.14，多个日期用顿号分隔"></label></div></section>
          <section class="form-section"><h2>选用单位资料</h2><label>共享单位<select v-model="partnerId"><option :value="0">选择供应商或生产商资料</option><option v-for="partner in partners" :key="partner.id" :value="partner.id">{{ partner.name }}（{{ partner.kind === 'supplier' ? '供应商' : '生产商' }}）</option></select></label><div class="button-row"><button :disabled="!partnerId" @click="fillPartner('name')">填入单位名称</button><button :disabled="!partnerId" @click="fillPartner('contact')">填入地址和联系方式</button></div><div class="field-grid"><label>地址来源<select aria-label="地址来源" v-model="fields.address_source" @change="markDirty('address_source')"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商，导出时注明</option></select></label><label>联系方式来源<select aria-label="联系方式来源" v-model="fields.contact_source" @change="markDirty('contact_source')"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商，导出时注明</option></select></label></div></section>
          <section class="form-section"><h2>随车证件与感官检查</h2><div class="field-grid"><label class="wide">随车证件<input v-model="fields.certificates"></label><label class="wide">感官检验<textarea v-model="fields.sensory" rows="2" placeholder="外包装、感官状态、标签情况；本次手动填写"></textarea></label><label class="wide">抽检项目<input v-model="fields.sampling_items"></label><label class="wide">备注<textarea v-model="fields.notes" rows="2"></textarea></label></div></section>
          <section v-if="group" class="form-section inspection-mode"><h2>检验</h2><div class="button-row"><label><input v-model="group.inspectionEnabled" type="radio" name="inspection-mode" :value="false">未检验</label><label><input v-model="group.inspectionEnabled" type="radio" name="inspection-mode" :value="true">检验</label></div><p v-if="!group.inspectionEnabled" class="muted">检验项目与报告信息已收起并锁定，已有内容保留；未检验记录不能导出 Word 报告。</p></section>
          <section v-if="group?.inspectionEnabled" class="form-section"><h2>检验项目</h2><label class="library-selector">检验标准方案<select aria-label="检验标准方案" :value="group?.schemeId || ''" @change="chooseScheme"><option value="">不选择方案</option><option v-for="scheme in availableSchemes" :key="scheme.id" :value="scheme.id">{{ scheme.name }}</option></select></label><p v-if="editing" class="muted">保存时采用：{{ editing.scheme_name || '未选择方案' }}，当前项目为保存时的快照。</p><p class="muted">所有物料均可选用任一方案。结果与结论每次手动填写，可以留空。</p><div class="button-row"><label>已维护检验项目<select aria-label="已维护检验项目" v-model="maintainedItemKey"><option value="">选择单个项目</option><option v-for="entry in maintainedItems" :key="entry.key" :value="entry.key">{{ entry.label }}</option></select></label><button type="button" :disabled="!maintainedItemKey" @click="addMaintainedItem">添加选中项目</button></div><div v-for="(item, index) in items" :key="index" class="inspection-row"><label>项目<input v-model="item.name"></label><label>标准规定<input v-model="item.standard"></label><label>检验结果<input v-model="item.result"></label><label>判定结论<input v-model="item.conclusion"></label></div><button type="button" @click="items.push({ name: '', standard: '', unit: '', result: '', conclusion: '' })">添加检验项目</button></section>
          <section v-if="group?.inspectionEnabled" class="form-section"><h2>报告信息</h2><div class="field-grid"><label>包装<input v-model="report.packaging"></label><label>检验依据<input v-model="report.basis"></label><label>检验日期<input v-model="report.inspection_date" type="date"></label><label>是否提供内检报告<select v-model="report.internal_report"><option value="">留空</option><option>是</option><option>否</option></select></label><label class="wide">结论<textarea v-model="report.conclusion" rows="2"></textarea></label></div><p class="muted">如需修改检验员和批准签名，请修改模板中的签名图片。<button type="button" class="text-button" @click="openTemplates">修改模板文件</button></p></section>
        </fieldset></div></div>
      <footer class="savebar"><span>{{ editable ? '业务字段允许留空' : '当前记录只读' }}</span><div><button @click="view = 'ledger'">返回台账</button><button v-if="editable" :disabled="busy" @click="save(false)">保存记录</button><button v-if="editable" class="primary" :disabled="busy" @click="save(true)">保存并标记已核对</button></div></footer>
    </main>
    <el-dialog v-model="createLedger" title="新建公司台账" width="min(480px, 92vw)"><form @submit.prevent="addLedger"><label>公司台账名称<input v-model="ledgerName" maxlength="31" required></label><p class="muted">将用作 Excel 工作表名称，最多31个字符。</p><button class="primary" :disabled="busy">建立台账</button></form></el-dialog>
    <el-dialog v-model="historyOpen" title="修改历史" width="min(850px, 95vw)"><article v-for="entry in histories" :key="entry.at" class="history-entry"><h3>{{ actionNames[entry.action] || entry.action }}</h3><p class="muted">{{ people.find(p => p.id === entry.actor_id)?.username }} · {{ new Date(entry.at).toLocaleString('zh-CN') }} · 版本 {{ entry.snapshot.version }}</p><details><summary>查看当时内容</summary><dl><template v-for="(value, key) in entry.snapshot.fields" :key="key"><dt>{{ fieldNames[key] || key }}</dt><dd>{{ formatSuggestion(value) || '（空白）' }}</dd></template></dl><div v-for="(item, index) in entry.snapshot.items" :key="index">{{ item.name }} / {{ item.standard }} / {{ item.result }} / {{ item.conclusion }}</div></details></article><button @click="historyOpen = false">关闭历史</button></el-dialog><el-dialog v-model="showLarge" title="包装原图" width="min(1100px, 96vw)"><img v-if="selectedImage" :src="`/api/images/${selectedImage}`" alt="包装图片放大预览" class="large-photo"></el-dialog>
  </div>
</template>
