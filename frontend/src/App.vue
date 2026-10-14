<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import { api, raw, json, today, userSchema, ledgerSchema, recordSchema, fieldsSchema, reportSchema, jobSchema, type User, type Ledger, type CheckRecord, type Fields, type Item, type Job } from './api'
import './style.css'
import AdminPanel from './AdminPanel.vue'
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
const view = ref<'home' | 'ledger' | 'editor' | 'admin'>('home')
const createLedger = ref(false)
const ledgerName = ref('')
const records = ref<CheckRecord[]>([])
const selectedIds = ref<number[]>([])
const filter = reactive({ text: '', status: '', from: '', to: '', mine: false, creator: 0 })
const editing = ref<CheckRecord | null>(null)
const fields = ref(fieldsSchema.parse({}))
const report = ref(reportSchema.parse({}))
const items = ref<Item[]>([])
type DraftGroup = { key: number; images: number[]; fields: Fields; report: z.infer<typeof reportSchema>; items: Item[]; dirty: Set<string>; job: Job | null; jobId: number | null; generation: number; materialId: number | null; schemeId: number | null; schemeChanged: boolean }
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
function makeGroup(images: number[] = []): DraftGroup { return { key: ++nextGroupKey, images, fields: fieldsSchema.parse({ arrival_date: today() }), report: reportSchema.parse({}), items: [], dirty: new Set(), job: null, jobId: null, generation: 0, materialId: null, schemeId: null, schemeChanged: false } }
const catalog = ref<z.infer<typeof materialSchema>[]>([])
const standards = ref<z.infer<typeof schemeSchema>[]>([])
const partners = ref<z.infer<typeof partnerSchema>[]>([])
const partnerId = ref(0)
const availableSchemes = computed(() => standards.value.filter(s => s.material_id === group.value?.materialId))
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
  if (items.value.some(i => i.result || i.conclusion) && !window.confirm('更换物料会清空当前检验结果和结论，继续吗？')) { event.target.value = String(group.value.materialId || ''); return }
  group.value.materialId = Number(event.target.value) || null
  const material = catalog.value.find(m => m.id === group.value?.materialId)
  if (material) { fields.value.material_name = [material.name, material.model].filter(Boolean).join(' '); markDirty('material_name') }
  const choices = standards.value.filter(s => s.material_id === group.value?.materialId)
  replaceScheme(choices.length === 1 ? choices[0]?.id || null : null)
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
function openEditor(record: CheckRecord | null = null) {
  if (record) ledger.value = ledgers.value.find(l => l.id === record.ledger_id) || null
  editing.value = record
  fields.value = fieldsSchema.parse(record?.fields || { arrival_date: today() })
  report.value = reportSchema.parse(record?.report || {})
  items.value = record ? record.items.map(i => ({ ...i })) : []
  groups.value = [{ ...makeGroup(record?.image_ids || []), fields: fields.value, report: report.value, items: items.value, jobId: record?.recognition_job_id || null, materialId: record?.material_id || null }]
  switchGroup(0)
  const current = group.value
  if (record?.recognition_job_id && current) {
    void api(`/recognition/${record.recognition_job_id}`, jobSchema).then(job => {
      if (groups.value.includes(current) && current.generation === 0) current.job = job
    }).catch(problem => { error.value = problem instanceof Error ? problem.message : '识别原文加载失败' })
  }
  void loadLibrary().catch(problem => { error.value = problem instanceof Error ? problem.message : '公共资料加载失败' })
  error.value = ''; notice.value = ''; view.value = 'editor'
}
async function save(check: boolean) {
  await perform(async () => {
    if (!ledger.value) return
    const body = { fields: { ...fields.value, arrival_date: fields.value.arrival_date || null }, report: { ...report.value, inspection_date: report.value.inspection_date || null }, items: items.value, image_ids: group.value?.images || [], recognition_job_id: group.value?.jobId || null }
    const record = editing.value
      ? await api(`/records/${editing.value.id}`, recordSchema, json('PATCH', { ...body, version: editing.value.version, ...(group.value?.schemeChanged ? { material_id: group.value.materialId, scheme_id: group.value.schemeId } : {}) }))
      : await api(`/ledgers/${ledger.value.id}/records`, recordSchema, json('POST', { ...body, material_id: group.value?.materialId, scheme_id: group.value?.schemeId }))
    editing.value = record
    if (check) await api(`/records/${record.id}/check`, recordSchema, json('POST', { version: record.version }))
    if (groups.value.length > 1) {
      groups.value.splice(activeGroup.value, 1); editing.value = null; switchGroup(0)
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
  const current = group.value; const target = groups.value.find(g => g.key === targetKey)
  if (!current || !target || target === current) return
  current.images = current.images.filter(id => id !== imageId); invalidateRecognition(current)
  target.images.push(imageId); invalidateRecognition(target)
  selectedImage.value = current.images[0] || 0
}
function imageDestination(event: Event, imageId: number) { if (event.target instanceof HTMLSelectElement) moveImage(imageId, Number(event.target.value)) }
function splitImage(imageId: number) {
  const target = makeGroup(); groups.value.push(target); moveImage(imageId, target.key)
}
function invalidateRecognition(current: DraftGroup) { current.generation++; current.job = null; current.jobId = null }
function removeImage(imageId: number) {
  if (!group.value) return
  group.value.images = group.value.images.filter(id => id !== imageId); invalidateRecognition(group.value)
  selectedImage.value = group.value.images[0] || 0
}
async function recognizeGroup(current: DraftGroup) {
  if (!ledger.value || !current.images.length) return
  const generation = ++current.generation
  const result = await api(`/ledgers/${ledger.value.id}/recognition`, jobSchema, json('POST', { image_ids: current.images, cloud_enabled: cloudEnabled.value }))
  if (current.generation !== generation) return
  current.job = result; current.jobId = result.id
  let applied = false
  while (current.generation === generation) {
    const job = await api(`/recognition/${result.id}`, jobSchema)
    if (current.generation !== generation) return
    current.job = job
    if (!applied && job.local_status === 'done') {
      for (const [key, value] of Object.entries(job.fields)) {
        const existing: unknown = Reflect.get(current.fields, key)
        if (!current.dirty.has(key) && !job.conflicts[key] && (!existing || (Array.isArray(existing) && !existing.length))) {
          const parsed = fieldsSchema.safeParse({ ...current.fields, [key]: value })
          if (parsed.success) Object.assign(current.fields, parsed.data)
        }
      }
      applied = true
    }
    if (['done', 'failed'].includes(job.local_status) && ['done', 'failed', 'disabled'].includes(job.cloud_status)) break
    await new Promise(resolve => setTimeout(resolve, 500))
  }
}
function startRecognition() {
  for (const current of groups.value) {
    void recognizeGroup(current).catch(problem => { error.value = problem instanceof Error ? problem.message : '识别失败，可以手动填写' })
  }
}
async function download(kind: 'xlsx' | 'docx') {
  await perform(async () => {
    const selected = records.value.filter(r => selectedIds.value.includes(r.id))
    if (!selected.length) throw new Error('请先选择要导出的记录')
    const pending = selected.some(r => r.status === 'pending')
    if (pending && !window.confirm('所选记录包含待核对内容，仍要导出吗？')) return
    const response = await raw(`/exports/${kind}`, json('POST', { record_ids: selectedIds.value, include_pending: pending }))
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a'); anchor.href = url
    anchor.download = kind === 'xlsx' ? '原辅料查验记录.xlsx' : selected.length === 1 ? '原辅料检验报告.docx' : '原辅料检验报告.zip'
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
    <header class="topbar"><button class="brand-button" @click="view = 'home'; ledger = null"><span class="brand-mark small-mark">验</span>原辅料查验</button><div class="company-context">{{ ledger?.name || '公司台账' }}</div><div class="account"><button v-if="user.role === 'admin'" class="quiet admin-entry" @click="view = 'admin'">管理与公共资料</button><span>{{ user.username }} <small>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</small></span><button class="quiet" @click="logout">退出</button></div></header>
    <div v-if="error" class="global-message error" role="alert">{{ error }}<button class="quiet" @click="error = ''">关闭</button></div>
    <div v-if="notice" class="global-message success" role="status">{{ notice }}</div>
    <AdminPanel v-if="view === 'admin' && user.role === 'admin'" @close="view = 'home'; ledger = null; loadLedgers()" /><main v-else-if="view === 'home'" class="page home-page">
      <div class="page-heading"><div><h1>选择公司台账</h1><p class="muted">先进入台账，再上传图片或录入查验记录。</p></div><div class="button-row"><button @click="showAllRecords">查看全部记录</button><button v-if="user.role === 'admin'" class="primary" @click="createLedger = true">新建公司台账</button></div></div>
      <div v-if="!ledgers.length" class="empty">{{ user.role === 'admin' ? '还没有公司台账，请先建立。' : '还没有公司台账，请联系管理员建立。' }}</div>
      <div class="ledger-grid"><button v-for="entry in ledgers" :key="entry.id" class="ledger-entry" :aria-label="`进入${entry.name}`" @click="enterLedger(entry)"><span class="ledger-symbol">册</span><strong>{{ entry.name }}</strong><span class="muted">查验记录与检验报告</span><span class="enter-label">进入台账</span></button></div>
    </main>
    <main v-else-if="view === 'ledger'" class="page">
      <nav class="breadcrumb"><button @click="view = 'home'; ledger = null">公司台账</button><span>/</span><span>{{ allCompanies ? '全部台账' : ledger?.name }}</span></nav>
      <div class="page-heading"><div><h1>原辅料查验记录</h1><p class="muted">查看全部记录，核对与修改自己的记录。</p></div><button v-if="!allCompanies" class="primary" @click="openEditor()">上传与录入</button></div>
      <section class="table-panel">
        <div class="filters"><label class="search-label">查找记录<input v-model="filter.text" type="search" placeholder="物料名称、供应商或生产商"></label><label>状态<select v-model="filter.status"><option value="">全部状态</option><option value="pending">待核对</option><option value="checked">已核对</option><option value="void">作废</option></select></label><label>到货日期从<input v-model="filter.from" type="date"></label><label>到<input v-model="filter.to" type="date"></label><label>创建人<select v-model="filter.creator"><option :value="0">所有人员</option><option v-for="person in people" :key="person.id" :value="person.id">{{ person.username }}</option></select></label><label class="checkbox-label"><input v-model="filter.mine" type="checkbox">我创建的</label></div>
        <div class="table-actions"><span>共 {{ filteredRecords.length }} 条 · 已选 {{ selectedIds.length }} 条</span><div><button :disabled="busy || !selectedIds.length" @click="download('xlsx')">导出 Excel</button><button :disabled="busy || !selectedIds.length" @click="download('docx')">导出 Word</button></div></div>
        <div class="table-scroll"><table class="ledger-table"><thead><tr><th>选择</th><th v-if="allCompanies">公司台账</th><th>到货日期</th><th>物料名称、型号</th><th>生产日期</th><th>供应商或生产商</th><th>接收数量</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="record in filteredRecords" :key="record.id"><td><input v-model="selectedIds" type="checkbox" :value="record.id" :disabled="record.status === 'void'" :aria-label="`选择记录${record.id}`"></td><td v-if="allCompanies">{{ ledgers.find(l => l.id === record.ledger_id)?.name }}</td><td>{{ record.fields.arrival_date || '—' }}</td><td class="material-cell">{{ record.fields.material_name || '未填写物料' }}</td><td class="dates-cell">{{ record.fields.production_dates.join('、') || '—' }}</td><td>{{ record.fields.company_name || '—' }}</td><td>{{ record.fields.received_quantity || '—' }}</td><td><span class="status" :class="record.status">{{ statusText[record.status] }}</span></td><td><button class="text-button" @click="openEditor(record)">{{ record.status !== 'void' && (user.role === 'admin' || user.id === record.creator_id) ? '核对 / 编辑' : '查看' }}</button></td></tr></tbody></table></div>
        <div v-if="!filteredRecords.length" class="empty">暂无记录。点击“上传与录入”开始。</div>
      </section>
    </main>
    <main v-else class="editor-page">
      <nav class="breadcrumb"><button @click="view = 'ledger'">{{ ledger?.name }}台账</button><span>/</span><span>{{ editing ? '查看与核对' : '新增查验记录' }}</span></nav>
      <div class="editor-heading"><div><h1>{{ editing ? fields.material_name || '查验记录' : '图片识别与核对' }}</h1><p class="muted">对照原图核对，未获取的信息可以手动填写或留空。</p></div><div v-if="editing" class="record-meta"><span class="status" :class="editing.status">{{ statusText[editing.status] }}</span><small>创建人：{{ people.find(p => p.id === editing?.creator_id)?.username }}<br>核对人：{{ people.find(p => p.id === editing?.checker_id)?.username || '未核对' }}</small><button @click="showHistory">查看修改历史</button><button v-if="user.role === 'admin' && editing.status !== 'void'" class="danger-button" @click="voidRecord">作废记录</button></div></div>
      <section v-if="editable" class="upload-toolbar"><div class="mode-switch"><button :class="{ active: mode === 'same' }" @click="mode = 'same'">同一物料多图</button><button :class="{ active: mode === 'batch' }" :disabled="!!editing" @click="mode = 'batch'">多种物料批量</button></div><label class="checkbox-label"><input v-model="cloudEnabled" type="checkbox">云端辅助</label><small>启用后会将照片发送给智谱；不可用时保留本地结果</small><button class="primary" :disabled="!groups.some(g => g.images.length)" @click="startRecognition">开始识别</button></section>
      <div v-if="groups.length > 1" class="group-strip"><div v-for="(entry, index) in groups" :key="entry.key" class="group-tab"><button :class="{ active: index === activeGroup }" @click="switchGroup(index)">记录 {{ index + 1 }} · {{ entry.images.length }} 张</button><button v-if="index > 0" class="text-button" @click="mergePrevious(index)">合并到上一组</button></div></div>
      <p v-for="suggestion in groupingSuggestions" :key="suggestion" class="notice">{{ suggestion }}</p><div class="editor-grid"><aside class="image-panel"><div class="panel-heading"><h2>包装图片</h2><button class="text-button" @click="showPhoto = !showPhoto">{{ showPhoto ? '折叠图片' : '展开图片' }}</button></div><p aria-label="当前图片分组" class="muted">记录 {{ activeGroup + 1 }} · {{ group?.images.length || 0 }} 张</p>
        <div v-if="editable" class="upload-drop" @dragover.prevent @drop.prevent="uploadFiles($event.dataTransfer?.files || null)"><label class="file-picker">选择照片 / 相册<input type="file" accept="image/jpeg,image/png,image/webp" multiple aria-label="选择包装照片" :disabled="busy" @change="fileChosen"></label><label class="file-picker camera-picker">拍照<input type="file" accept="image/*" capture="environment" aria-label="拍摄包装照片" :disabled="busy" @change="fileChosen"></label><small>支持拖入照片，每张最多 20MB</small></div>
        <template v-if="showPhoto"><div v-if="selectedImage" class="photo-viewer"><img :src="`/api/images/${selectedImage}`" alt="当前包装原图" :style="{ transform: `rotate(${angle}deg)` }" @click="showLarge = true"></div><div v-else class="image-placeholder"><div class="picture-icon">▧</div><p>本条记录暂无图片</p><small>可以先手动填写并保存</small></div><div v-if="selectedImage" class="photo-actions"><button @click="angle += 90">旋转查看</button><button @click="showLarge = true">放大原图</button></div><div class="thumbnails"><div v-for="photo in group?.images || []" :key="photo" class="thumbnail"><button :class="{ active: selectedImage === photo }" @click="selectedImage = photo; angle = 0"><img :src="`/api/images/${photo}`" alt="包装图片缩略图"></button><template v-if="editable"><button class="text-button" @click="removeImage(photo)">移除</button><button v-if="!editing && (group?.images.length || 0) > 1" class="text-button" @click="splitImage(photo)">拆成一组</button><select v-if="!editing && groups.length > 1" aria-label="移动图片到分组" :value="group?.key" @change="imageDestination($event, photo)"><option v-for="(entry, index) in groups" :key="entry.key" :value="entry.key">记录 {{ index + 1 }}</option></select></template></div></div></template>
        <div v-if="group?.job" class="recognition-result"><p>本地识别：{{ { queued: '排队中', running: '识别中', done: '已完成', failed: '未完成' }[group.job.local_status] }}</p><p v-if="group.job.error" class="error">{{ group.job.error }}</p><p class="muted">云端辅助：{{ { queued: '等待本地结果', running: '处理中，可先填写或保存', done: '建议已返回', failed: '不可用，本地结果仍可使用', disabled: '未启用' }[group.job.cloud_status] }}</p>
          <details v-if="group.job.evidence.length"><summary>原始识别文字</summary><pre>{{ group.job.evidence.map(e => [e.texts.join('\n'), ...e.supplements.map(s => '局部或倾斜校正识别：\n' + s.texts.join('\n'))].join('\n\n')).join('\n\n') }}</pre></details>
          <details v-if="localSuggestions.length"><summary>本地字段建议</summary><div v-for="[key, value] in localSuggestions" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" @click="applySuggestion(key, value)">填入</button></div></details>
          <div v-for="(values, key) in group.job.conflicts" :key="key" class="conflict"><p>{{ fieldNames[key] || key }}存在多个识别值，请对照原图选择：</p><button v-for="value in values" :key="value" @click="applySuggestion(key, value)">{{ value }}</button></div>
          <div v-if="suggestedFields.length"><h3>云端建议</h3><p class="muted">按需填入，不自动覆盖人工修改。</p><div v-for="[key, value] in suggestedFields" :key="key" class="suggestion"><span>{{ fieldNames[key] || key }}<strong>{{ formatSuggestion(value) }}</strong></span><button v-if="editable" @click="applySuggestion(key, value)">填入</button></div></div>
        </div>
      </aside>
        <div class="form-panel"><fieldset :disabled="!editable || busy" @input="markDirty('manual')" @change="markDirty('manual')"><section class="form-section"><h2>基本信息</h2><label class="library-selector">选择共享物料<select :value="group?.materialId || ''" @change="chooseMaterial"><option value="">不选择，手动填写</option><option v-for="material in catalog" :key="material.id" :value="material.id">{{ [material.name, material.model].filter(Boolean).join(' ') }}</option></select></label><div class="field-grid"><label>到货日期<input v-model="fields.arrival_date" type="date" aria-label="到货日期"><small>默认录入日期，可修改或清空</small></label><label v-for="field in textFields" :key="field.key">{{ field.label }}<input v-model="fields[field.key]" @input="markDirty(field.key)"></label><label class="wide">生产日期<input v-model="productionDates" placeholder="2026.01.14，多个日期用顿号分隔"></label></div></section>
          <section class="form-section"><h2>选用单位资料</h2><label>共享单位<select v-model="partnerId"><option :value="0">选择供应商或生产商资料</option><option v-for="partner in partners" :key="partner.id" :value="partner.id">{{ partner.name }}（{{ partner.kind === 'supplier' ? '供应商' : '生产商' }}）</option></select></label><div class="button-row"><button :disabled="!partnerId" @click="fillPartner('name')">填入单位名称</button><button :disabled="!partnerId" @click="fillPartner('contact')">填入地址和联系方式</button></div><div class="field-grid"><label>地址来源<select v-model="fields.address_source" @change="markDirty('address_source')"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商，导出时注明</option></select></label><label>联系方式来源<select v-model="fields.contact_source" @change="markDirty('contact_source')"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商，导出时注明</option></select></label></div></section>
          <section class="form-section"><h2>随车证件与感官检查</h2><div class="field-grid"><label class="wide">随车证件<input v-model="fields.certificates"></label><label class="wide">感官检验<textarea v-model="fields.sensory" rows="2" placeholder="外包装、感官状态、标签情况；本次手动填写"></textarea></label><label class="wide">抽检项目<input v-model="fields.sampling_items"></label><label class="wide">备注<textarea v-model="fields.notes" rows="2"></textarea></label></div></section>
          <section class="form-section"><h2>检验项目</h2><label class="library-selector">检验标准方案<select :value="group?.schemeId || ''" @change="chooseScheme"><option value="">不选择方案</option><option v-for="scheme in availableSchemes" :key="scheme.id" :value="scheme.id">{{ scheme.name }}</option></select></label><p v-if="editing" class="muted">保存时采用：{{ editing.scheme_name || '未选择方案' }}，当前项目为保存时的快照。</p><p class="muted">结果与结论每次手动填写，可以留空。</p><div v-for="(item, index) in items" :key="index" class="inspection-row"><label>项目<input v-model="item.name"></label><label>标准规定<input v-model="item.standard"></label><label>单位<input v-model="item.unit"></label><label>检验结果<input v-model="item.result"></label><label>判定结论<input v-model="item.conclusion"></label></div><button type="button" @click="items.push({ name: '', standard: '', unit: '', result: '', conclusion: '' })">添加检验项目</button></section>
          <section class="form-section"><h2>报告信息</h2><div class="field-grid"><label>包装<input v-model="report.packaging"></label><label>检验依据<input v-model="report.basis"></label><label>检验日期<input v-model="report.inspection_date" type="date"></label><label>是否提供内检报告<select v-model="report.internal_report"><option value="">留空</option><option>是</option><option>否</option></select></label><label class="wide">结论<textarea v-model="report.conclusion" rows="2"></textarea></label><label>检验员<input v-model="report.inspector"></label><label>批准<input v-model="report.approver"></label></div><p class="muted">报告会使用模板文件夹中的签名图片。</p></section>
        </fieldset></div></div>
      <footer class="savebar"><span>{{ editable ? '业务字段允许留空' : '当前记录只读' }}</span><div><button @click="view = 'ledger'">返回台账</button><button v-if="editable" :disabled="busy" @click="save(false)">保存记录</button><button v-if="editable" class="primary" :disabled="busy" @click="save(true)">保存并标记已核对</button></div></footer>
    </main>
    <el-dialog v-model="createLedger" title="新建公司台账" width="min(480px, 92vw)"><form @submit.prevent="addLedger"><label>公司台账名称<input v-model="ledgerName" maxlength="31" required></label><p class="muted">将用作 Excel 工作表名称，最多31个字符。</p><button class="primary" :disabled="busy">建立台账</button></form></el-dialog>
    <el-dialog v-model="historyOpen" title="修改历史" width="min(850px, 95vw)"><article v-for="entry in histories" :key="entry.at" class="history-entry"><h3>{{ actionNames[entry.action] || entry.action }}</h3><p class="muted">{{ people.find(p => p.id === entry.actor_id)?.username }} · {{ new Date(entry.at).toLocaleString('zh-CN') }} · 版本 {{ entry.snapshot.version }}</p><details><summary>查看当时内容</summary><dl><template v-for="(value, key) in entry.snapshot.fields" :key="key"><dt>{{ fieldNames[key] || key }}</dt><dd>{{ formatSuggestion(value) || '（空白）' }}</dd></template></dl><div v-for="(item, index) in entry.snapshot.items" :key="index">{{ item.name }} / {{ item.standard }} / {{ item.result }} / {{ item.conclusion }}</div></details></article><button @click="historyOpen = false">关闭历史</button></el-dialog><el-dialog v-model="showLarge" title="包装原图" width="min(1100px, 96vw)"><img v-if="selectedImage" :src="`/api/images/${selectedImage}`" alt="包装图片放大预览" class="large-photo"></el-dialog>
  </div>
</template>
