<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import { api, json, raw, userSchema, ledgerSchema, materialSchema, schemeSchema, partnerSchema, type User, type Ledger } from './api'
const emit = defineEmits<{ close: [] }>()
const tab = ref('materials')
const tabs = [{ key: 'materials', name: '物料与检验标准' }, { key: 'partners', name: '单位资料' }, { key: 'users', name: '账号与权限' }, { key: 'ledgers', name: '公司台账' }, { key: 'cloud', name: '云端与模板' }]
const error = ref(''), notice = ref(''), busy = ref(false)
const users = ref<User[]>([]), ledgers = ref<Ledger[]>([])
const materials = ref<z.infer<typeof materialSchema>[]>([]), schemes = ref<z.infer<typeof schemeSchema>[]>([]), partners = ref<z.infer<typeof partnerSchema>[]>([])
const material = reactive({ id: 0, name: '', model: '', aliases: '' })
const scheme = reactive<{ id: number; material_id: number | null; name: string; items: { name: string; standard: string; unit: string }[] }>({ id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] })
const partner = reactive<{ id: number; name: string; kind: 'supplier' | 'manufacturer'; address: string; contact: string }>({ id: 0, name: '', kind: 'supplier', address: '', contact: '' })
const account = reactive<{ id: number; username: string; password: string; role: 'admin' | 'user'; active: boolean }>({ id: 0, username: '', password: '', role: 'user', active: true })
const company = reactive({ id: 0, name: '' })
const cloudKey = ref(''), cloudConfigured = ref(false)
const cloudTesting = ref(false), cloudTestMessage = ref(''), cloudTestOk = ref(false)
async function refresh() {
  const result = await Promise.all([api('/materials', z.array(materialSchema)), api('/schemes', z.array(schemeSchema)), api('/partners', z.array(partnerSchema)), api('/users', z.array(userSchema)), api('/ledgers', z.array(ledgerSchema)), api('/settings/cloud', z.object({ configured: z.boolean() }))])
  ;[materials.value, schemes.value, partners.value, users.value, ledgers.value] = result
  cloudConfigured.value = result[5].configured
}
async function action(work: () => Promise<unknown>, success = '已保存') {
  error.value = ''; notice.value = ''; busy.value = true
  try { await work(); await refresh(); notice.value = success } catch (e) { error.value = e instanceof Error ? e.message : '操作失败' } finally { busy.value = false }
}
async function deleteEntry(resource: 'materials' | 'schemes' | 'partners' | 'users' | 'ledgers', id: number, name: string, reset: () => void) {
  if (!window.confirm(`确定删除「${name}」吗？删除后不可恢复，已有查验记录会保留。`)) return
  await action(async () => { await raw(`/${resource}/${id}`, { method: 'DELETE' }); reset() }, '已删除')
}
function deleteMaterial(entry: z.infer<typeof materialSchema>) {
  return deleteEntry('materials', entry.id, [entry.name, entry.model].filter(Boolean).join(' '), () => {
    if (material.id === entry.id) Object.assign(material, { id: 0, name: '', model: '', aliases: '' })
    if (scheme.material_id === entry.id) scheme.material_id = null
  })
}
function deleteScheme(entry: z.infer<typeof schemeSchema>) {
  return deleteEntry('schemes', entry.id, entry.name, () => {
    if (scheme.id === entry.id) Object.assign(scheme, { id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] })
  })
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
function deleteCompany(entry: Ledger) {
  return deleteEntry('ledgers', entry.id, entry.name, () => {
    if (company.id === entry.id) Object.assign(company, { id: 0, name: '' })
  })
}
onMounted(() => action(refresh))
async function saveMaterial() { await action(async () => { const { id, ...body } = material; await api(id ? `/materials/${id}` : '/materials', materialSchema, json(id ? 'PUT' : 'POST', body)); Object.assign(material, { id: 0, name: '', model: '', aliases: '' }) }) }
async function saveScheme() { await action(async () => { const { id, ...body } = scheme; await api(id ? `/schemes/${id}` : '/schemes', schemeSchema, json(id ? 'PUT' : 'POST', { ...body, items: body.items.map(item => ({ ...item, unit: '' })) })); Object.assign(scheme, { id: 0, material_id: null, name: '', items: [{ name: '', standard: '', unit: '' }] }) }) }
async function savePartner() { await action(async () => { const { id, ...body } = partner; await api(id ? `/partners/${id}` : '/partners', partnerSchema, json(id ? 'PUT' : 'POST', body)); Object.assign(partner, { id: 0, name: '', kind: 'supplier', address: '', contact: '' }) }) }
async function saveAccount() { await action(async () => { const { id, username, password, role, active } = account; const body = id ? { role, active, ...(password ? { password } : {}) } : { username, password, role }; await api(id ? `/users/${id}` : '/users', userSchema, json(id ? 'PATCH' : 'POST', body)); Object.assign(account, { id: 0, username: '', password: '', role: 'user', active: true }) }) }
async function saveCompany() { await action(async () => { await api(company.id ? `/ledgers/${company.id}` : '/ledgers', ledgerSchema, json(company.id ? 'PATCH' : 'POST', { name: company.name })); Object.assign(company, { id: 0, name: '' }) }) }
async function saveCloud() { cloudTestMessage.value = ''; await action(async () => { await api('/settings/cloud', z.object({ configured: z.boolean() }), json('PUT', { api_key: cloudKey.value })); cloudKey.value = '' }) }
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
  <main class="page admin-page"><div class="page-heading"><div><h1>管理与公共资料</h1><p class="muted">所有公司共享物料、检验标准和单位资料。</p></div><button @click="emit('close')">返回公司台账</button></div>
    <div class="admin-tabs"><button v-for="entry in tabs" :key="entry.key" :class="{ active: tab === entry.key }" @click="tab = entry.key">{{ entry.name }}</button></div>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="notice" role="status" class="success admin-notice">{{ notice }}</p>
    <div v-if="tab === 'materials'" class="admin-columns">
      <section class="admin-card"><h2>{{ material.id ? '编辑物料' : '维护共享物料' }}</h2><form @submit.prevent="saveMaterial"><div class="field-grid"><label>物料名称<input v-model="material.name" required></label><label>型号<input v-model="material.model"></label><label class="wide">常用别名<input v-model="material.aliases"></label></div><button class="primary" :disabled="busy">保存物料</button></form><div class="maintenance-list"><div v-for="entry in materials" :key="entry.id" class="maintenance-row"><button class="maintenance-edit" :disabled="busy" @click="Object.assign(material, entry)"><span>{{ entry.name }} {{ entry.model }}</span><small>编辑</small></button><button class="maintenance-delete" :disabled="busy" @click="deleteMaterial(entry)">删除</button></div></div></section>
      <section class="admin-card"><h2>{{ scheme.id ? '编辑检验方案' : '维护检验标准方案' }}</h2><form @submit.prevent="saveScheme"><div class="field-grid"><label>方案所属物料<select v-model="scheme.material_id"><option :value="null">不绑定物料（通用方案）</option><option v-for="entry in materials" :key="entry.id" :value="entry.id">{{ [entry.name, entry.model].filter(Boolean).join(' ') }}</option></select></label><label>方案名称<input v-model="scheme.name" required></label></div><p class="muted">所属物料可不选；所有方案都能用于不同物料，关联仅作提示。</p><div v-for="(item, index) in scheme.items" :key="index" class="standard-edit-row"><label>项目名称<input v-model="item.name"></label><label>标准规定<input v-model="item.standard"></label><button type="button" @click="scheme.items.splice(index, 1)">移除</button></div><div class="button-row"><button type="button" @click="scheme.items.push({ name: '', standard: '', unit: '' })">增加项目</button><button class="primary" :disabled="busy">保存检验方案</button></div></form><div class="maintenance-list"><div v-for="entry in schemes" :key="entry.id" class="maintenance-row"><button class="maintenance-edit" :disabled="busy" @click="Object.assign(scheme, { ...entry, items: entry.items.map(i => ({ name: i.name, standard: i.standard, unit: '' })) })"><span>{{ materials.find(m => m.id === entry.material_id)?.name || '通用' }} / {{ entry.name }}</span><small>编辑</small></button><button class="maintenance-delete" :disabled="busy" @click="deleteScheme(entry)">删除</button></div></div></section>
    </div>
    <div v-else-if="tab === 'partners'" class="admin-columns"><section class="admin-card"><h2>供应商与生产商资料</h2><form @submit.prevent="savePartner"><div class="field-grid"><label>单位名称<input v-model="partner.name" required></label><label>单位类型<select v-model="partner.kind"><option value="supplier">供应商</option><option value="manufacturer">生产商</option></select></label><label class="wide">地址<input v-model="partner.address"></label><label class="wide">联系方式<input v-model="partner.contact"></label></div><button class="primary" :disabled="busy">保存单位资料</button></form></section><section class="admin-card"><h2>已维护单位</h2><div class="maintenance-list"><div v-for="entry in partners" :key="entry.id" class="maintenance-row"><button class="maintenance-edit" :disabled="busy" @click="Object.assign(partner, entry)"><span>{{ entry.name }}</span><small>{{ entry.kind === 'supplier' ? '供应商' : '生产商' }} · 编辑</small></button><button class="maintenance-delete" :disabled="busy" @click="deletePartner(entry)">删除</button></div></div></section></div>
    <div v-else-if="tab === 'users'" class="admin-columns"><section class="admin-card"><h2>{{ account.id ? '维护账号权限' : '创建人员账号' }}</h2><form @submit.prevent="saveAccount"><div class="field-grid"><label>人员账号<input v-model="account.username" :disabled="!!account.id" required></label><label>{{ account.id ? '重置密码，留空则不修改' : '初始密码' }}<input v-model="account.password" type="password" autocomplete="new-password" minlength="10" :required="!account.id"></label><label>角色<select v-model="account.role"><option value="user">普通用户</option><option value="admin">管理员</option></select></label><label v-if="account.id" class="checkbox-label"><input v-model="account.active" type="checkbox">账号启用</label></div><button class="primary" :disabled="busy">保存账号</button><button v-if="account.id" type="button" @click="Object.assign(account, { id: 0, username: '', password: '', role: 'user', active: true })">新增账号</button></form></section><section class="admin-card"><h2>人员列表</h2><div class="maintenance-list"><div v-for="entry in users" :key="entry.id" class="maintenance-row"><button class="maintenance-edit" :disabled="busy" @click="Object.assign(account, { ...entry, password: '' })"><span>{{ entry.username }}</span><small>{{ entry.role === 'admin' ? '管理员' : '普通用户' }} · {{ entry.active ? '启用' : '停用' }} · 编辑</small></button><button class="maintenance-delete" :disabled="busy" @click="deleteAccount(entry)">删除</button></div></div></section></div>
    <div v-else-if="tab === 'ledgers'" class="admin-columns"><section class="admin-card"><h2>公司台账名称</h2><form @submit.prevent="saveCompany"><label>台账名称<input v-model="company.name" maxlength="31" required></label><p class="muted">导出时用作 Excel 工作表名，不增加业务字段。</p><button class="primary" :disabled="busy">保存台账</button></form></section><section class="admin-card"><h2>已建立台账</h2><div class="maintenance-list"><div v-for="entry in ledgers" :key="entry.id" class="maintenance-row"><button class="maintenance-edit" :disabled="busy" @click="Object.assign(company, entry)"><span>{{ entry.name }}</span><small>编辑</small></button><button class="maintenance-delete" :disabled="busy" @click="deleteCompany(entry)">删除</button></div></div></section></div>
    <div v-else class="admin-columns"><section class="admin-card"><h2>智谱云端辅助</h2><p>模型：GLM-4.1V-Thinking-Flash</p><p class="muted">{{ cloudConfigured ? '已配置密钥。更新时输入新密钥，原密钥不回显。' : '尚未配置密钥，本地识别可以独立使用。' }}</p><form @submit.prevent="saveCloud"><label>API 密钥<input v-model="cloudKey" type="password" autocomplete="off" :disabled="busy" @input="cloudTestMessage = ''"></label><div class="button-row"><button class="primary" :disabled="busy || !cloudKey">保存密钥</button><button type="button" :disabled="busy || !cloudConfigured || !!cloudKey" @click="testCloud">{{ cloudTesting ? '测试中…' : '测试连接' }}</button><button type="button" :disabled="busy" @click="cloudKey = ''; saveCloud()">清除密钥</button></div><p v-if="cloudKey" class="muted">请先保存密钥，再测试连接。</p><p v-if="cloudTestMessage" :role="cloudTestOk ? 'status' : 'alert'" :class="cloudTestOk ? 'success' : 'error'">{{ cloudTestMessage }}</p></form></section><section class="admin-card"><h2>个人导出模板</h2><p>请从顶部“我的模板”选择本机文件夹，普通用户也可设置。</p><p class="muted">在 Word/WPS 中修改本地模板的签名图片并保存。导出时优先使用已修改的本地模板，不覆盖服务器默认模板。</p></section></div>
  </main>
</template>

<style scoped>
.maintenance-row{display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--line);padding:8px 0}
.maintenance-edit{flex:1;min-width:0;display:flex;justify-content:space-between;align-items:center;gap:12px;text-align:left;border:0;background:transparent}
.maintenance-edit span{overflow-wrap:anywhere}
.maintenance-edit small{flex-shrink:0}
.maintenance-delete{color:#a83232;flex-shrink:0}
.standard-edit-row{grid-template-columns:1fr 1.5fr auto}
@media(max-width:600px){.standard-edit-row{grid-template-columns:1fr}.maintenance-edit{align-items:flex-start;flex-direction:column;gap:4px}}
</style>
