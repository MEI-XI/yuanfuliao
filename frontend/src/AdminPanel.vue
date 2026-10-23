<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { z } from 'zod'
import AuditLog from './AuditLog.vue'
import PaginationBar from './PaginationBar.vue'
import SearchableLibrary from './SearchableLibrary.vue'
import { api, json, raw, userSchema, ledgerSchema, materialSchema, materialDetailsSchema, schemeSchema, partnerSchema, normalizeShelfLife, shelfLifeDayNotice, type User, type Ledger } from './api'
const emit = defineEmits<{ close: []; userUpdated: [user: User]; reauthenticate: [] }>()
const props = defineProps<{ currentUser: User }>()
const superadmin = computed(() => props.currentUser.role === 'superadmin')
const roleNames = { superadmin: '超级管理员', admin: '管理员', user: '普通用户' }
const tab = ref('materials')
const tabs = computed(() => [{ key: 'materials', name: '物料维护' }, { key: 'schemes', name: '检验标准方案' }, { key: 'partners', name: '单位资料' }, { key: 'users', name: '账号与权限' }, { key: 'ledgers', name: '公司台账' }, { key: 'cloud', name: '云端与模板' }, ...(superadmin.value ? [{ key: 'audit', name: '操作日志' }] : [])])
const error = ref(''), notice = ref(''), busy = ref(false)
const users = ref<User[]>([]), ledgers = ref<Ledger[]>([])
const materials = ref<z.infer<typeof materialSchema>[]>([]), schemes = ref<z.infer<typeof schemeSchema>[]>([]), partners = ref<z.infer<typeof partnerSchema>[]>([])
const partnerSearch = ref(''), accountSearch = ref(''), companySearch = ref('')
const filteredPartners = computed(() => partners.value.filter(entry => matchesSearch(partnerSearch.value, [entry.name, entry.address, entry.contact, entry.kind === 'supplier' ? '供应商' : '生产商'])))
const filteredUsers = computed(() => users.value.filter(entry => matchesSearch(accountSearch.value, [entry.username, roleNames[entry.role], entry.active ? '启用' : '停用'])))
const filteredLedgers = computed(() => ledgers.value.filter(entry => matchesSearch(companySearch.value, [entry.name])))
const materialSearch = ref(''), schemeSearch = ref(''), schemeBinding = ref('')
const materialDates = reactive({ field: 'created_at', from: '', to: '' })
const schemeDates = reactive({ field: 'created_at', from: '', to: '' })
watch(materialDates, () => { selectedMaterials.value = [] })
watch(schemeDates, () => { selectedSchemes.value = [] })
function matchesDates(entry: { created_at: string | null; updated_at: string | null }, filter: { field: string; from: string; to: string }) {
  if (!filter.from && !filter.to) return true
  const value = filter.field === 'created_at' ? entry.created_at : entry.updated_at
  if (!value) return false
  const day = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value))
  return (!filter.from || day >= filter.from) && (!filter.to || day <= filter.to)
}
const selectedMaterials = ref<number[]>([]), selectedSchemes = ref<number[]>([])
watch(materialSearch, () => { selectedMaterials.value = [] })
watch([schemeSearch, schemeBinding], () => { selectedSchemes.value = [] })
function catalogTime(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '未记录' }
function matchesSearch(query: string, values: string[]) {
  const text = values.join(' ').normalize('NFKC').toLocaleLowerCase()
  return query.trim().normalize('NFKC').toLocaleLowerCase().split(/\s+/).every(word => text.includes(word))
}
const filteredMaterials = computed(() => materials.value.filter(entry => matchesDates(entry, materialDates) && matchesSearch(materialSearch.value, [entry.name, entry.model, entry.aliases, entry.specification, entry.company_name, entry.packaging])))
const filteredSchemes = computed(() => schemes.value.filter(entry => {
  const linked = materials.value.find(m => m.id === entry.material_id)
  return matchesDates(entry, schemeDates) && (!schemeBinding.value || (schemeBinding.value === 'general' ? entry.material_id === null : entry.material_id !== null)) &&
    matchesSearch(schemeSearch.value, [entry.name, linked?.name || '', linked?.model || '', ...entry.items.flatMap(item => [item.name, item.standard])])
}))
const materialView = reactive({ page: 1, sort: 'id', descending: false })
const schemeView = reactive({ page: 1, sort: 'id', descending: false })
type CatalogEntry = z.infer<typeof materialSchema> | z.infer<typeof schemeSchema>
function sortValue(entry: CatalogEntry, field: string): string | number | null {
  if (field === 'items') return 'items' in entry ? entry.items.length : 0
  if (field === 'material_id') return 'material_id' in entry ? materials.value.find(m => m.id === entry.material_id)?.name || '通用方案' : ''
  if (field === 'created_at' || field === 'updated_at') return entry[field] ? Date.parse(entry[field]!) : null
  if (field === 'id' || field === 'name') return entry[field]
  return field in entry ? String(Reflect.get(entry, field) ?? '') : ''
}
function sortedCatalog<T extends CatalogEntry>(entries: T[], view: { sort: string; descending: boolean }): T[] {
  return [...entries].sort((a, b) => {
    const left = sortValue(a, view.sort), right = sortValue(b, view.sort)
    if (left === null || right === null) return left === right ? a.id - b.id : left === null ? 1 : -1
    const result = typeof left === 'number' && typeof right === 'number' ? left - right : String(left).localeCompare(String(right), 'zh-CN', { numeric: true })
    return (view.descending ? -result : result) || a.id - b.id
  })
}
function toggleCatalogSort(view: typeof materialView, field: string) {
  view.descending = view.sort === field ? !view.descending : false
  view.sort = field; view.page = 1
}
function sortMark(view: typeof materialView, field: string) { return view.sort === field ? view.descending ? ' ↓' : ' ↑' : ' ↕' }
const sortedMaterials = computed(() => sortedCatalog(filteredMaterials.value, materialView))
const sortedSchemes = computed(() => sortedCatalog(filteredSchemes.value, schemeView))
const materialPages = computed(() => Math.max(1, Math.ceil(sortedMaterials.value.length / 50)))
const schemePages = computed(() => Math.max(1, Math.ceil(sortedSchemes.value.length / 50)))
const pageMaterials = computed(() => sortedMaterials.value.slice((materialView.page - 1) * 50, materialView.page * 50))
const pageSchemes = computed(() => sortedSchemes.value.slice((schemeView.page - 1) * 50, schemeView.page * 50))
watch([materialSearch, materialDates], () => { materialView.page = 1 })
watch([schemeSearch, schemeBinding, schemeDates], () => { schemeView.page = 1 })
watch(materialPages, count => { materialView.page = Math.min(materialView.page, count) })
watch(schemePages, count => { schemeView.page = Math.min(schemeView.page, count) })
const material = reactive({ id: 0, name: '', model: '', aliases: '', ...materialDetailsSchema.parse({}) })
const scheme = reactive<{ id: number; material_id: number | null; name: string; items: { name: string; standard: string; unit: string }[] }>({ id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] })
const partner = reactive<{ id: number; name: string; kind: 'supplier' | 'manufacturer'; address: string; contact: string }>({ id: 0, name: '', kind: 'supplier', address: '', contact: '' })
const account = reactive<User & { password: string }>({ id: 0, username: '', password: '', role: 'user', active: true })
const credential = ref<{ kind: 'hidden' } | { kind: 'unavailable' } | { kind: 'visible'; password: string }>({ kind: 'hidden' })
const company = reactive({ id: 0, name: '' })
const cloudKey = ref(''), cloudConfigured = ref(false)
const cloudTesting = ref(false), cloudTestMessage = ref(''), cloudTestOk = ref(false)
type EditorKind = 'material' | 'scheme' | 'partner' | 'account' | 'company'
const editorNames = { material: '物料', scheme: '检验方案', partner: '单位', account: '账号', company: '台账' }
const editor = ref<{ kind: EditorKind | 'cloud'; title: string } | null>(null)
const formHeading = ref<HTMLElement | null>(null)
let returnPosition: { tab: string; kind: EditorKind; id: number; scrollY: number } | null = null
async function restoreListPosition() {
  if (!editor.value && returnPosition && tab.value === returnPosition.tab) {
    const list = returnPosition.kind === 'material' ? sortedMaterials.value : returnPosition.kind === 'scheme' ? sortedSchemes.value : []
    const index = list.findIndex(entry => entry.id === returnPosition!.id)
    if (index >= 0) (returnPosition.kind === 'material' ? materialView : schemeView).page = Math.floor(index / 50) + 1
  }
  await nextTick()
  if (editor.value || !returnPosition || tab.value !== returnPosition.tab) return
  const row = document.querySelector<HTMLElement>(`[data-catalog-row="${returnPosition.kind}-${returnPosition.id}"]`)
  window.scrollTo({ top: returnPosition.scrollY, behavior: 'instant' })
  if (row) {
    row.querySelector<HTMLButtonElement>('.maintenance-edit')?.focus({ preventScroll: true })
    const box = row.getBoundingClientRect()
    if (box.top < 80 || box.bottom > window.innerHeight) row.scrollIntoView({ block: 'center', behavior: 'instant' })
  }
}
async function showEditor(kind: EditorKind, originalName?: string) {
  returnPosition = originalName === undefined ? null : { tab: tab.value, kind, id: { material, scheme, partner, account, company }[kind].id, scrollY: window.scrollY }
  editor.value = { kind, title: originalName === undefined ? `新增${editorNames[kind]}` : `修改${editorNames[kind]}：${originalName}` }
  error.value = ''; notice.value = ''
  await nextTick(); formHeading.value?.focus(); formHeading.value?.scrollIntoView({ block: 'start' })
}
function openMaterial(entry?: z.infer<typeof materialSchema>) {
  Object.assign(material, (entry ? { id: entry.id, name: entry.name, model: entry.model, aliases: entry.aliases, ...materialDetailsSchema.parse(entry) } : null) || { id: 0, name: '', model: '', aliases: '', ...materialDetailsSchema.parse({}) })
  void showEditor('material', entry?.name)
}
async function normalizeMaterialShelfLife() {
  const value = material.shelf_life
  const currentEditor = editor.value
  if (!value) return
  try {
    const normalized = await normalizeShelfLife(value)
    if (editor.value === currentEditor && material.shelf_life === value) material.shelf_life = normalized
  } catch (problem) {
    if (editor.value === currentEditor && material.shelf_life === value) error.value = problem instanceof Error ? problem.message : '保质期格式转换失败'
  }
}
function openScheme(entry?: z.infer<typeof schemeSchema>) {
  Object.assign(scheme, entry ? { id: entry.id, name: entry.name, material_id: entry.material_id, items: entry.items.map(item => ({ name: item.name, standard: item.standard, unit: '' })) } : { id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] })
  void showEditor('scheme', entry?.name)
}
function openPartner(entry?: z.infer<typeof partnerSchema>) {
  Object.assign(partner, entry || { id: 0, name: '', kind: 'supplier', address: '', contact: '' })
  void showEditor('partner', entry?.name)
}
function openAccount(entry?: User) {
  credential.value = { kind: 'hidden' }
  Object.assign(account, entry ? { ...entry, password: '' } : { id: 0, username: '', password: '', role: 'user', active: true })
  void showEditor('account', entry?.username)
}
function openCompany(entry?: Ledger) {
  Object.assign(company, entry || { id: 0, name: '' })
  void showEditor('company', entry?.name)
}
async function openCloud() {
  cloudKey.value = ''; cloudTestMessage.value = ''; error.value = ''; notice.value = ''
  editor.value = { kind: 'cloud', title: cloudConfigured.value ? '更新密钥' : '配置密钥' }
  await nextTick(); formHeading.value?.focus(); formHeading.value?.scrollIntoView({ block: 'start' })
}
function closeEditor() {
  credential.value = { kind: 'hidden' }
  editor.value = null
  Object.assign(material, { id: 0, name: '', model: '', aliases: '', ...materialDetailsSchema.parse({}) })
  Object.assign(scheme, { id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] })
  Object.assign(partner, { id: 0, name: '', kind: 'supplier', address: '', contact: '' })
  Object.assign(account, { id: 0, username: '', password: '', role: 'user', active: true })
  Object.assign(company, { id: 0, name: '' })
  cloudKey.value = ''
  error.value = ''
  void restoreListPosition()
}
async function refresh() {
  const result = await Promise.all([api('/materials', z.array(materialSchema)), api('/schemes', z.array(schemeSchema)), api('/partners', z.array(partnerSchema)), api('/users', z.array(userSchema)), api('/ledgers', z.array(ledgerSchema)), api('/settings/cloud', z.object({ configured: z.boolean() }))])
  ;[materials.value, schemes.value, partners.value, users.value, ledgers.value] = result
  selectedMaterials.value = selectedMaterials.value.filter(id => materials.value.some(entry => entry.id === id))
  selectedSchemes.value = selectedSchemes.value.filter(id => schemes.value.some(entry => entry.id === id))
  cloudConfigured.value = result[5].configured
}
async function action(work: () => Promise<unknown>, success = '已保存') {
  error.value = ''; notice.value = ''; busy.value = true
  try { await work(); await refresh(); notice.value = success; await restoreListPosition() } catch (e) { error.value = e instanceof Error ? e.message : '操作失败' } finally { busy.value = false }
}
async function deleteEntry(resource: 'materials' | 'schemes' | 'partners' | 'users', id: number, name: string, reset: () => void) {
  const message = `确定删除「${name}」吗？删除后不可恢复，已有查验记录会保留。`
  if (!window.confirm(message)) return
  await action(async () => { await raw(`/${resource}/${id}`, { method: 'DELETE' }); reset() }, '已删除')
}
function deleteMaterial(entry: z.infer<typeof materialSchema>) {
  return deleteEntry('materials', entry.id, [entry.name, entry.model].filter(Boolean).join(' '), () => {
    if (material.id === entry.id) Object.assign(material, { id: 0, name: '', model: '', aliases: '', ...materialDetailsSchema.parse({}) })
    if (scheme.material_id === entry.id) scheme.material_id = null
  })
}
function deleteScheme(entry: z.infer<typeof schemeSchema>) {
  return deleteEntry('schemes', entry.id, entry.name, () => {
    if (scheme.id === entry.id) Object.assign(scheme, { id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] })
  })
}
async function deleteSelectedCatalog(resource: 'materials' | 'schemes') {
  if (busy.value) return
  const selection = resource === 'materials' ? selectedMaterials : selectedSchemes
  const entries = (resource === 'materials' ? materials.value : schemes.value).filter(entry => selection.value.includes(entry.id))
  if (!entries.length) return
  const label = resource === 'materials' ? '物料' : '检验标准方案'
  if (!window.confirm(`确定删除所选的 ${entries.length} 条${label}吗？删除后不可恢复，已有查验记录内容会保留。${resource === 'materials' ? '绑定这些物料的方案将改为通用方案。' : ''}`)) return
  busy.value = true; error.value = ''; notice.value = ''; returnPosition = null
  let deleted = 0
  const failures: string[] = []
  try {
    for (const entry of entries) {
      try {
        await raw(`/${resource}/${entry.id}`, { method: 'DELETE' })
        selection.value = selection.value.filter(id => id !== entry.id)
        if (resource === 'materials') materials.value = materials.value.filter(item => item.id !== entry.id)
        else schemes.value = schemes.value.filter(item => item.id !== entry.id)
        deleted++
      } catch (problem) { failures.push(`${entry.name}：${problem instanceof Error ? problem.message : '删除失败'}`) }
    }
    notice.value = `已删除 ${deleted} 条${label}`
    await refresh()
  } catch (problem) { failures.push(`刷新列表失败：${problem instanceof Error ? problem.message : '请刷新页面'}`) }
  finally { error.value = failures.join('；'); busy.value = false }
}
function deletePartner(entry: z.infer<typeof partnerSchema>) {
  return deleteEntry('partners', entry.id, entry.name, () => {
    if (partner.id === entry.id) Object.assign(partner, { id: 0, name: '', kind: 'supplier', address: '', contact: '' })
  })
}
function deleteAccount(entry: User) {
  return deleteEntry('users', entry.id, entry.username, () => {
    if (account.id === entry.id) Object.assign(account, { id: 0, username: '', password: '', role: 'user', active: true })
  })
}
async function deleteCompany(entry: Ledger) {
  if (busy.value) return
  await action(async () => {
    const check = await api(`/ledgers/${entry.id}/deletion-check`, z.object({ allowed: z.boolean(), reason: z.string() }))
    if (!check.allowed) { window.alert(check.reason); return }
    if (!window.confirm(`确定删除空台账「${entry.name}」吗？删除后不可恢复。`)) return
    await raw(`/ledgers/${entry.id}`, { method: 'DELETE' })
    if (company.id === entry.id) Object.assign(company, { id: 0, name: '' })
  }, '')
}
onMounted(() => action(refresh, ''))
async function saveMaterial() { await action(async () => { const { id, ...body } = material; await api(id ? `/materials/${id}` : '/materials', materialSchema, json(id ? 'PUT' : 'POST', body)); closeEditor() }) }
async function saveScheme() { await action(async () => { const { id, ...body } = scheme; await api(id ? `/schemes/${id}` : '/schemes', schemeSchema, json(id ? 'PUT' : 'POST', { ...body, items: body.items.map(item => ({ ...item, unit: '' })) })); closeEditor() }) }
async function savePartner() { await action(async () => { const { id, ...body } = partner; await api(id ? `/partners/${id}` : '/partners', partnerSchema, json(id ? 'PUT' : 'POST', body)); closeEditor() }) }
async function saveAccount() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const { id, username, password, role, active } = account
    const body = id ? { ...(superadmin.value ? { username, role } : {}), active, ...(password ? { password } : {}) } : { username, password, role: superadmin.value ? role : 'user' }
    const saved = await api(id ? `/users/${id}` : '/users', userSchema, json(id ? 'PATCH' : 'POST', body))
    closeEditor()
    if (id === props.currentUser.id) {
      if (password) { emit('reauthenticate'); return }
      emit('userUpdated', saved)
    }
    await refresh(); notice.value = '已保存'
  } catch (e) { error.value = e instanceof Error ? e.message : '账号保存失败' }
  finally { busy.value = false }
}
async function revealPassword() {
  busy.value = true; error.value = ''; credential.value = { kind: 'hidden' }
  try {
    const result = await api(`/users/${account.id}/password`, z.object({ password: z.string().nullable() }), { cache: 'no-store' })
    credential.value = result.password === null ? { kind: 'unavailable' } : { kind: 'visible', password: result.password }
  } catch (e) { error.value = e instanceof Error ? e.message : '密码读取失败' }
  finally { busy.value = false }
}
async function saveCompany() { await action(async () => { await api(company.id ? `/ledgers/${company.id}` : '/ledgers', ledgerSchema, json(company.id ? 'PATCH' : 'POST', { name: company.name })); closeEditor() }) }
async function saveCloud() { cloudTestMessage.value = ''; await action(async () => { await api('/settings/cloud', z.object({ configured: z.boolean() }), json('PUT', { api_key: cloudKey.value })); closeEditor() }) }
async function testCloud() {
  cloudTesting.value = true; busy.value = true; cloudTestMessage.value = ''; error.value = ''; notice.value = ''
  try {
    const result = await api('/settings/cloud/test', z.object({ ok: z.boolean(), message: z.string() }), json('POST', {}))
    cloudTestOk.value = result.ok; cloudTestMessage.value = result.message
  } catch (e) { cloudTestOk.value = false; cloudTestMessage.value = e instanceof Error ? e.message : '连接测试失败' }
  finally { cloudTesting.value = false; busy.value = false }
}
</script>

<template>
  <main class="page admin-page" :class="{ 'catalog-page': !editor }">
    <div class="page-heading"><div><h1>管理与公共资料</h1><p class="muted">所有公司共享物料、检验标准和单位资料。</p></div><button :disabled="busy" @click="emit('close')">返回公司台账</button></div>
    <div class="admin-tabs"><button v-for="entry in tabs" :key="entry.key" :disabled="busy" :class="{ active: tab === entry.key }" @click="closeEditor(); tab = entry.key">{{ entry.name }}</button></div>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="notice" role="status" class="success admin-notice">{{ notice }}</p>
    <section v-if="editor" class="admin-card admin-form" role="region" :aria-label="editor.title">
      <div class="module-heading"><h2 ref="formHeading" tabindex="-1">{{ editor.title }}</h2><button :disabled="busy" @click="closeEditor">返回列表</button></div>
      <form v-if="editor.kind === 'material'" @submit.prevent="saveMaterial"><fieldset :disabled="busy">
        <div class="field-grid"><label>物料名称<input v-model="material.name" required></label><label>型号<input v-model="material.model"></label><label class="wide">常用别名<input v-model="material.aliases"></label><label>规格<input v-model="material.specification"></label><label>包装<input v-model="material.packaging"></label><label>供应商或生产商<input v-model="material.company_name"></label><label>地址<input v-model="material.address"></label><label>联系方式<input v-model="material.contact"></label><label>保质期<input v-model="material.shelf_life" @blur="normalizeMaterialShelfLife"></label><label>地址来源<select v-model="material.address_source"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商</option></select></label><label>联系方式来源<select v-model="material.contact_source"><option value="">未注明</option><option value="supplier">供应商</option><option value="manufacturer">生产商</option></select></label></div>
        <p v-if="shelfLifeDayNotice(material.shelf_life)" class="notice" role="status">{{ shelfLifeDayNotice(material.shelf_life) }}</p><div class="button-row"><button class="primary">{{ material.id ? '保存修改' : '创建物料' }}</button><button type="button" @click="closeEditor">取消返回</button></div>
      </fieldset></form>
      <form v-else-if="editor.kind === 'scheme'" @submit.prevent="saveScheme"><fieldset :disabled="busy">
        <div class="field-grid"><SearchableLibrary label="方案所属物料" placeholder="输入物料名称、型号或别名" empty-label="不绑定物料（通用方案）" :disabled="busy" :value="scheme.material_id || ''" :options="materials.map(entry => ({ value: entry.id, label: [entry.name, entry.model].filter(Boolean).join(' '), search: entry.aliases }))" @update:value="scheme.material_id = Number($event) || null" /><label>方案名称<input v-model="scheme.name" required></label></div>
        <p class="muted">所属物料可不选；所有方案都能用于不同物料，关联仅作提示。</p>
        <div v-for="(item, index) in scheme.items" :key="index" class="standard-edit-row"><label>项目名称<input v-model="item.name"></label><label>标准规定<input v-model="item.standard"></label><button type="button" @click="scheme.items.splice(index, 1)">移除</button></div>
        <button type="button" @click="scheme.items.push({ name: '', standard: '', unit: '' })">增加项目</button>
        <div class="button-row"><button class="primary">{{ scheme.id ? '保存修改' : '创建检验方案' }}</button><button type="button" @click="closeEditor">取消返回</button></div>
      </fieldset></form>
      <form v-else-if="editor.kind === 'partner'" @submit.prevent="savePartner"><fieldset :disabled="busy">
        <div class="field-grid"><label>单位名称<input v-model="partner.name" required></label><label>单位类型<select v-model="partner.kind"><option value="supplier">供应商</option><option value="manufacturer">生产商</option></select></label><label class="wide">地址<input v-model="partner.address"></label><label class="wide">联系方式<input v-model="partner.contact"></label></div>
        <div class="button-row"><button class="primary">{{ partner.id ? '保存修改' : '创建单位' }}</button><button type="button" @click="closeEditor">取消返回</button></div>
      </fieldset></form>
      <form v-else-if="editor.kind === 'account'" @submit.prevent="saveAccount"><fieldset :disabled="busy">
        <div class="field-grid"><label>人员账号<input v-model="account.username" :disabled="!!account.id && !superadmin" required></label><label>{{ account.id ? '重置密码，留空则不修改' : '初始密码' }}<input v-model="account.password" type="password" autocomplete="new-password" minlength="10" :required="!account.id"></label><label>角色<select v-model="account.role" :disabled="!superadmin || account.role === 'superadmin'"><option value="user">普通用户</option><option value="admin">管理员</option><option v-if="account.role === 'superadmin'" value="superadmin">超级管理员</option></select></label><label v-if="account.id" class="checkbox-label"><input v-model="account.active" type="checkbox" :disabled="account.role === 'superadmin'">账号启用</label></div>
        <div v-if="account.id && superadmin" class="credential-view">
          <p class="muted">查看密码会记录在操作日志中。历史账号的原密码可能无法查看，可通过重置设置新密码。</p>
          <button v-if="credential.kind === 'hidden'" type="button" @click="revealPassword">查看密码</button>
          <template v-else-if="credential.kind === 'visible'"><label>当前密码<input :value="credential.password" readonly autocomplete="off"></label><button type="button" @click="credential = { kind: 'hidden' }">隐藏密码</button></template>
          <p v-else role="status">原密码不可查看，重置后可查看。</p>
        </div>
        <div class="button-row"><button class="primary">{{ account.id ? '保存修改' : '创建账号' }}</button><button type="button" @click="closeEditor">取消返回</button></div>
      </fieldset></form>
      <form v-else-if="editor.kind === 'company'" @submit.prevent="saveCompany"><fieldset :disabled="busy">
        <label>台账名称<input v-model="company.name" maxlength="31" required></label><p class="muted">导出时用作 Excel 工作表名，不增加业务字段。</p>
        <div class="button-row"><button class="primary">{{ company.id ? '保存修改' : '创建台账' }}</button><button type="button" @click="closeEditor">取消返回</button></div>
      </fieldset></form>
      <form v-else-if="editor.kind === 'cloud'" @submit.prevent="saveCloud"><fieldset :disabled="busy">
        <p class="muted">{{ cloudConfigured ? '输入新密钥替换现有配置，原密钥不回显。' : '配置后可使用云端辅助识别，本地识别可以独立使用。' }}</p>
        <label>API 密钥<input v-model="cloudKey" type="password" autocomplete="off" required></label>
        <p class="muted">保存后返回列表测试连接。</p>
        <div class="button-row"><button class="primary" :disabled="!cloudKey">{{ cloudConfigured ? '保存更新' : '保存配置' }}</button><button type="button" @click="closeEditor">取消返回</button></div>
      </fieldset></form>
    </section>
    <section v-else-if="tab === 'materials'" class="admin-card">
      <div class="module-heading"><h2>共享物料</h2><button class="primary" :disabled="busy" @click="openMaterial()">新增物料</button></div>
      <div class="filters catalog-filters"><label>查找物料<input v-model="materialSearch" type="search" placeholder="名称、型号、别名、规格、供应商或包装"></label><label title="按北京时间筛选，包含起止日期；未记录时间的条目不计入日期范围。">时间类型<select v-model="materialDates.field" aria-label="物料时间类型"><option value="created_at">添加时间</option><option value="updated_at">最后修改时间</option></select></label><label>开始日期<input v-model="materialDates.from" type="date" aria-label="物料开始日期" :max="materialDates.to || undefined"></label><label>结束日期<input v-model="materialDates.to" type="date" aria-label="物料结束日期" :min="materialDates.from || undefined"></label><button @click="materialSearch = ''; materialDates.from = ''; materialDates.to = ''; materialDates.field = 'created_at'">清空筛选</button></div>
      <div class="table-actions catalog-selection"><span role="status">合计 {{ materials.length }} 条 · 筛选 {{ filteredMaterials.length }} 条 · 已选 {{ selectedMaterials.length }} 条</span><div><button :disabled="busy || !filteredMaterials.length" @click="selectedMaterials = filteredMaterials.map(entry => entry.id)">全选筛选结果</button><button :disabled="busy || !selectedMaterials.length" @click="selectedMaterials = []">取消全选</button><button class="maintenance-delete" :disabled="busy || !selectedMaterials.length" @click="deleteSelectedCatalog('materials')">批量删除</button></div></div>
      <div class="maintenance-list"><div class="table-scroll"><table class="ledger-table catalog-table"><thead><tr><th>选择</th><th :aria-sort="materialView.sort === 'name' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'name')">物料名称{{ sortMark(materialView, 'name') }}</button></th><th :aria-sort="materialView.sort === 'model' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'model')">型号{{ sortMark(materialView, 'model') }}</button></th><th :aria-sort="materialView.sort === 'specification' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'specification')">规格{{ sortMark(materialView, 'specification') }}</button></th><th :aria-sort="materialView.sort === 'company_name' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'company_name')">供应商或生产商{{ sortMark(materialView, 'company_name') }}</button></th><th :aria-sort="materialView.sort === 'packaging' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'packaging')">包装{{ sortMark(materialView, 'packaging') }}</button></th><th :aria-sort="materialView.sort === 'created_at' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'created_at')">添加时间{{ sortMark(materialView, 'created_at') }}</button></th><th :aria-sort="materialView.sort === 'updated_at' ? (materialView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(materialView, 'updated_at')">最后修改时间{{ sortMark(materialView, 'updated_at') }}</button></th><th>操作</th></tr></thead><tbody><tr v-for="entry in pageMaterials" :key="entry.id" :data-catalog-row="`material-${entry.id}`" class="maintenance-row"><td><input v-model="selectedMaterials" :value="entry.id" type="checkbox" :disabled="busy" :aria-label="`选择${entry.name}`"></td><td class="catalog-name">{{ entry.name }}</td><td>{{ entry.model || '—' }}</td><td>{{ entry.specification || '—' }}</td><td class="catalog-wrap">{{ entry.company_name || '—' }}</td><td>{{ entry.packaging || '—' }}</td><td>{{ catalogTime(entry.created_at) }}</td><td>{{ catalogTime(entry.updated_at) }}</td><td class="catalog-actions"><button class="maintenance-edit" :disabled="busy" @click="openMaterial(entry)">修改</button><button class="maintenance-delete" :disabled="busy" @click="deleteMaterial(entry)">删除</button></td></tr></tbody></table></div><p v-if="!filteredMaterials.length" class="module-empty">{{ materials.length ? '没有匹配的物料，请调整或清空筛选。' : '暂无共享物料，点击“新增物料”建立资料。' }}</p></div>
    <PaginationBar v-model:page="materialView.page" :total="filteredMaterials.length" :disabled="busy" label="物料分页" />
    </section>
    <section v-else-if="tab === 'schemes'" class="admin-card">
      <div class="module-heading"><h2>检验标准方案</h2><button class="primary" :disabled="busy" @click="openScheme()">新增检验方案</button></div>
      <div class="filters catalog-filters"><label>查找检验方案<input v-model="schemeSearch" type="search" placeholder="方案名称、关联物料、检验项目或标准规定"></label><label>方案类型<select v-model="schemeBinding" aria-label="方案类型"><option value="">全部</option><option value="general">通用方案</option><option value="bound">已绑定物料</option></select></label><label title="按北京时间筛选，包含起止日期；未记录时间的条目不计入日期范围。">时间类型<select v-model="schemeDates.field" aria-label="方案时间类型"><option value="created_at">添加时间</option><option value="updated_at">最后修改时间</option></select></label><label>开始日期<input v-model="schemeDates.from" type="date" aria-label="方案开始日期" :max="schemeDates.to || undefined"></label><label>结束日期<input v-model="schemeDates.to" type="date" aria-label="方案结束日期" :min="schemeDates.from || undefined"></label><button @click="schemeSearch = ''; schemeBinding = ''; schemeDates.from = ''; schemeDates.to = ''; schemeDates.field = 'created_at'">清空筛选</button></div>
      <div class="table-actions catalog-selection"><span role="status">合计 {{ schemes.length }} 条 · 筛选 {{ filteredSchemes.length }} 条 · 已选 {{ selectedSchemes.length }} 条</span><div><button :disabled="busy || !filteredSchemes.length" @click="selectedSchemes = filteredSchemes.map(entry => entry.id)">全选筛选结果</button><button :disabled="busy || !selectedSchemes.length" @click="selectedSchemes = []">取消全选</button><button class="maintenance-delete" :disabled="busy || !selectedSchemes.length" @click="deleteSelectedCatalog('schemes')">批量删除</button></div></div>
      <div class="maintenance-list"><div class="table-scroll"><table class="ledger-table catalog-table"><thead><tr><th>选择</th><th :aria-sort="schemeView.sort === 'name' ? (schemeView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(schemeView, 'name')">方案名称{{ sortMark(schemeView, 'name') }}</button></th><th :aria-sort="schemeView.sort === 'material_id' ? (schemeView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(schemeView, 'material_id')">关联物料{{ sortMark(schemeView, 'material_id') }}</button></th><th :aria-sort="schemeView.sort === 'items' ? (schemeView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(schemeView, 'items')">检验项目数{{ sortMark(schemeView, 'items') }}</button></th><th :aria-sort="schemeView.sort === 'created_at' ? (schemeView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(schemeView, 'created_at')">添加时间{{ sortMark(schemeView, 'created_at') }}</button></th><th :aria-sort="schemeView.sort === 'updated_at' ? (schemeView.descending ? 'descending' : 'ascending') : 'none'"><button class="sort-heading" @click="toggleCatalogSort(schemeView, 'updated_at')">最后修改时间{{ sortMark(schemeView, 'updated_at') }}</button></th><th>操作</th></tr></thead><tbody><tr v-for="entry in pageSchemes" :key="entry.id" :data-catalog-row="`scheme-${entry.id}`" class="maintenance-row"><td><input v-model="selectedSchemes" :value="entry.id" type="checkbox" :disabled="busy" :aria-label="`选择${entry.name}`"></td><td class="catalog-name">{{ entry.name }}</td><td class="catalog-wrap">{{ materials.find(m => m.id === entry.material_id)?.name || '通用方案' }}</td><td>{{ entry.items.length }}</td><td>{{ catalogTime(entry.created_at) }}</td><td>{{ catalogTime(entry.updated_at) }}</td><td class="catalog-actions"><button class="maintenance-edit" :disabled="busy" @click="openScheme(entry)">修改</button><button class="maintenance-delete" :disabled="busy" @click="deleteScheme(entry)">删除</button></td></tr></tbody></table></div><p v-if="!filteredSchemes.length" class="module-empty">{{ schemes.length ? '没有匹配的方案，请调整或清空筛选。' : '暂无检验方案，点击“新增检验方案”维护项目与标准。' }}</p></div>
    <PaginationBar v-model:page="schemeView.page" :total="filteredSchemes.length" :disabled="busy" label="方案分页" />
    </section>
    <section v-else-if="tab === 'partners'" class="admin-card">
      <div class="module-heading"><h2>供应商与生产商资料</h2><button class="primary" :disabled="busy" @click="openPartner()">新增单位</button></div>
      <div class="filters catalog-filters"><label>查找单位<input v-model="partnerSearch" type="search" placeholder="名称、类型、地址或联系方式"></label><button @click="partnerSearch = ''">清空筛选</button></div>
      <div class="table-actions catalog-selection"><span role="status">合计 {{ partners.length }} 条 · 筛选 {{ filteredPartners.length }} 条</span></div>
      <div class="maintenance-list"><div class="table-scroll"><table class="ledger-table catalog-table compact-catalog"><thead><tr><th>单位名称</th><th>类型</th><th>地址</th><th>联系方式</th><th>操作</th></tr></thead><tbody><tr v-for="entry in filteredPartners" :key="entry.id" :data-catalog-row="`partner-${entry.id}`" class="maintenance-row"><td class="catalog-name">{{ entry.name }}</td><td class="">{{ entry.kind === 'supplier' ? '供应商' : '生产商' }}</td><td class="catalog-wrap">{{ entry.address || '—' }}</td><td class="">{{ entry.contact || '—' }}</td><td class="catalog-actions"><button class="maintenance-edit" :disabled="busy" @click="openPartner(entry)">修改</button><button class="maintenance-delete" :disabled="busy" @click="deletePartner(entry)">删除</button></td></tr></tbody></table></div><p v-if="!filteredPartners.length" class="module-empty">{{ partners.length ? '没有匹配的记录，请调整或清空筛选。' : '暂无记录，点击右上方按钮新增。' }}</p></div>
    </section>
    <section v-else-if="tab === 'users'" class="admin-card">
      <div class="module-heading"><h2>人员列表</h2><button class="primary" :disabled="busy" @click="openAccount()">新增账号</button></div>
      <div class="filters catalog-filters"><label>查找账号<input v-model="accountSearch" type="search" placeholder="账号、角色或启用状态"></label><button @click="accountSearch = ''">清空筛选</button></div>
      <div class="table-actions catalog-selection"><span role="status">合计 {{ users.length }} 条 · 筛选 {{ filteredUsers.length }} 条</span></div>
      <div class="maintenance-list"><div class="table-scroll"><table class="ledger-table catalog-table compact-catalog"><thead><tr><th>人员账号</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="entry in filteredUsers" :key="entry.id" :data-catalog-row="`account-${entry.id}`" class="maintenance-row"><td class="catalog-name">{{ entry.username }}</td><td class="">{{ roleNames[entry.role] }}</td><td class="">{{ entry.active ? '启用' : '停用' }}</td><td class="catalog-actions"><button class="maintenance-edit" :disabled="busy || (!superadmin && entry.role === 'superadmin')" @click="openAccount(entry)">修改</button><button v-if="entry.role !== 'superadmin'" class="maintenance-delete" :disabled="busy" @click="deleteAccount(entry)">删除</button></td></tr></tbody></table></div><p v-if="!filteredUsers.length" class="module-empty">{{ users.length ? '没有匹配的记录，请调整或清空筛选。' : '暂无记录，点击右上方按钮新增。' }}</p></div>
    </section>
    <AuditLog v-else-if="tab === 'audit' && superadmin" />
    <section v-else-if="tab === 'ledgers'" class="admin-card">
      <div class="module-heading"><h2>已建立台账</h2><button class="primary" :disabled="busy" @click="openCompany()">新增台账</button></div>
      <div class="filters catalog-filters"><label>查找台账<input v-model="companySearch" type="search" placeholder="公司台账名称"></label><button @click="companySearch = ''">清空筛选</button></div>
      <div class="table-actions catalog-selection"><span role="status">合计 {{ ledgers.length }} 条 · 筛选 {{ filteredLedgers.length }} 条</span></div>
      <div class="maintenance-list"><div class="table-scroll"><table class="ledger-table catalog-table compact-catalog"><thead><tr><th>台账名称</th><th>操作</th></tr></thead><tbody><tr v-for="entry in filteredLedgers" :key="entry.id" :data-catalog-row="`company-${entry.id}`" class="maintenance-row"><td class="catalog-name">{{ entry.name }}</td><td class="catalog-actions"><button class="maintenance-edit" :disabled="busy" @click="openCompany(entry)">修改</button><button class="maintenance-delete" :disabled="busy" @click="deleteCompany(entry)">删除</button></td></tr></tbody></table></div><p v-if="!filteredLedgers.length" class="module-empty">{{ ledgers.length ? '没有匹配的记录，请调整或清空筛选。' : '暂无记录，点击右上方按钮新增。' }}</p></div>
    </section>
    <div v-else class="admin-columns settings-columns"><section class="admin-card"><div class="module-heading"><h2>智谱云端辅助</h2></div><p>模型：GLM-4.1V-Thinking-Flash</p><p class="muted">{{ cloudConfigured ? '已配置密钥，可测试连接或更新密钥。' : '尚未配置密钥，本地识别可以独立使用。' }}</p><div class="button-row"><button class="primary" :disabled="busy" @click="openCloud">{{ cloudConfigured ? '更新密钥' : '配置密钥' }}</button><button :disabled="busy || !cloudConfigured" @click="testCloud">{{ cloudTesting ? '测试中…' : '测试连接' }}</button><button :disabled="busy || !cloudConfigured" @click="cloudKey = ''; saveCloud()">清除密钥</button></div><p v-if="cloudTestMessage" :role="cloudTestOk ? 'status' : 'alert'" :class="cloudTestOk ? 'success' : 'error'">{{ cloudTestMessage }}</p></section><section class="admin-card"><div class="module-heading"><h2>个人导出模板</h2></div><p>请从顶部“我的模板”选择本机 Word 或 Excel 模板文件，普通用户也可设置。</p><p class="muted">在 Word/WPS 中修改本地模板的签名图片并保存。导出时优先使用已修改的本地模板，不覆盖服务器默认模板。</p></section></div>
  </main>
</template>
<style scoped>
.admin-form{max-width:960px;margin:auto;border-top:3px solid var(--teal)}.module-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.module-heading h2{margin:0;overflow-wrap:anywhere;scroll-margin-top:100px}.module-heading button{flex-shrink:0}.admin-form form{margin-top:28px}.module-empty{margin:0;color:#647b86;font-size:14px}.row-details{display:block;font-size:13px;color:#647b86;margin-top:6px}
.maintenance-row{display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--line);padding:8px 0}
.maintenance-edit{flex:1;min-width:0;display:flex;justify-content:space-between;align-items:center;gap:12px;text-align:left;border:0;background:transparent}
.maintenance-edit span{overflow-wrap:anywhere}
.maintenance-edit small{flex-shrink:0;color:var(--teal);border:1px solid var(--line);border-radius:5px;padding:6px 12px}
.maintenance-delete{color:#a83232;flex-shrink:0}
.catalog-table{min-width:1050px}.catalog-table .maintenance-row{display:table-row}.catalog-table td{white-space:nowrap;padding:12px;vertical-align:middle}.catalog-table .catalog-name{font-size:17px;font-weight:600;min-width:220px;max-width:380px;white-space:normal;overflow-wrap:anywhere}.catalog-table .catalog-wrap{min-width:150px;max-width:240px;white-space:normal;overflow-wrap:anywhere}.catalog-table .maintenance-edit{display:inline-block;border:1px solid var(--line);color:var(--teal);padding:7px 12px}.catalog-actions button+button{margin-left:8px}.catalog-table input[type="checkbox"]{width:18px;height:18px}.catalog-table th{padding:12px}
.catalog-selection{align-items:center}.maintenance-row > input[type="checkbox"]{width:18px;height:18px;flex-shrink:0;margin:0 8px}
.maintenance-list{margin-top:0}.module-empty{padding:24px 0}.compact-catalog{min-width:640px}.catalog-actions{width:180px}.settings-columns{grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch}.settings-columns .module-heading{margin-bottom:24px}.settings-columns .button-row{margin-bottom:0}@media(max-width:900px){.settings-columns{grid-template-columns:1fr}}
.catalog-page{max-width:1800px}.catalog-filters{padding:16px 0;margin:12px 0 0;gap:12px}.catalog-filters label{margin:0;flex:0 0 auto;min-width:0}.catalog-filters label:first-child{flex:1 1 240px;min-width:220px}.catalog-filters input[type="date"]{width:150px}.catalog-filters select{min-width:120px}.catalog-selection{padding:12px 0;margin:0}.catalog-selection [role="status"]{font-weight:600;color:var(--teal);white-space:nowrap}.catalog-selection>div{display:flex;flex-wrap:wrap;gap:8px}.catalog-selection button+button{margin-left:0}
@media(max-width:600px){.catalog-filters{gap:10px}.catalog-filters label:first-child{flex-basis:100%;min-width:0}.catalog-filters label{flex:1 1 125px}.catalog-filters input[type="date"],.catalog-filters select{width:100%;min-width:0}.catalog-selection{gap:10px}}
.credential-view{margin-top:24px;padding-top:20px;border-top:1px solid var(--line)}.credential-view label{max-width:440px;margin-bottom:12px}
.standard-edit-row{grid-template-columns:1fr 1.5fr auto}
@media(max-width:600px){.standard-edit-row{grid-template-columns:1fr}.module-heading{align-items:flex-start;gap:12px}.module-heading h2{font-size:17px}.module-heading button{padding:8px 10px;font-size:13px}.maintenance-edit{gap:8px;padding:10px 4px}.maintenance-edit small{padding:6px 8px}.admin-form{padding:20px 16px}}
</style>
