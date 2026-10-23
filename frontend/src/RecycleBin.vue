<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { z } from 'zod'
import PaginationBar from './PaginationBar.vue'
import { api, json, raw, entryDate, recordSchema, type CheckRecord, type Ledger } from './api'

const props = defineProps<{ administrator: boolean; ledgers: Ledger[]; ledgerId: number | null }>()
const emit = defineEmits<{ close: []; open: [record: CheckRecord] }>()
const rows = ref<CheckRecord[]>([])
const selectedLedger = ref(props.ledgerId || 0)
const query = ref('')
const filters = reactive({ inspection: '', creator: 0, arrivalFrom: '', arrivalTo: '', voidFrom: '', voidTo: '' })
const people = ref<{ id: number; username: string }[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const selectedIds = ref<number[]>([])
const visible = computed(() => rows.value.filter(row => (!selectedLedger.value || row.ledger_id === selectedLedger.value) &&
  (!query.value.trim() || (query.value.trim() === '未填写物料' && !row.fields.material_name.trim()) || [row.fields.material_name, row.fields.company_name, row.fields.specification, row.fields.notes, String(row.id)].some(value => value.toLowerCase().includes(query.value.trim().toLowerCase()))) &&
  (!filters.inspection || row.inspection_enabled === (filters.inspection === 'inspected')) &&
  (!filters.creator || row.creator_id === filters.creator) &&
  (!filters.arrivalFrom || (row.fields.arrival_date || '') >= filters.arrivalFrom) &&
  (!filters.arrivalTo || (!!row.fields.arrival_date && row.fields.arrival_date <= filters.arrivalTo)) &&
  (!filters.voidFrom || localDate(row.voided_at) >= filters.voidFrom) &&
  (!filters.voidTo || (!!row.voided_at && localDate(row.voided_at) <= filters.voidTo))))
const page = ref(1)
const pages = computed(() => Math.max(1, Math.ceil(visible.value.length / 50)))
const pageRows = computed(() => visible.value.slice((page.value - 1) * 50, page.value * 50))
watch([selectedLedger, query, filters], () => { page.value = 1 })
watch(pages, value => { page.value = Math.min(page.value, value) })
const selected = computed(() => visible.value.filter(row => selectedIds.value.includes(row.id)))
function localDate(value: string | null) { return value ? new Date(value).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) : '' }
function clearFilters() {
  selectedLedger.value = props.ledgerId || 0; query.value = ''
  Object.assign(filters, { inspection: '', creator: 0, arrivalFrom: '', arrivalTo: '', voidFrom: '', voidTo: '' })
}
async function load() {
  const results = await Promise.all([api('/recycle-bin', z.array(recordSchema)), api('/people', z.array(z.object({ id: z.number(), username: z.string() })))])
  rows.value = results[0]; people.value = results[1]; selectedIds.value = []
}
async function action(work: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await work() } catch (cause) { error.value = cause instanceof Error ? cause.message : '操作失败' }
  finally { busy.value = false }
}
function restore(record: CheckRecord) {
  return action(async () => {
    await api(`/records/${record.id}/restore`, recordSchema, json('POST', { version: record.version }))
    await load()
  })
}
async function batchAction(kind: 'restore' | 'delete') {
  const selection = selected.value.map(row => ({ id: row.id, version: row.version }))
  if (busy.value || !props.administrator || !selection.length) return
  if (selection.length > 200) { error.value = '单次最多处理 200 条记录，请减少勾选后分批操作'; return }
  const message = kind === 'restore'
    ? `确定还原所选 ${selection.length} 条记录？还原后均为待核对。`
    : `确定永久删除所选 ${selection.length} 条记录及其报告附件？删除后无法还原。`
  if (!window.confirm(message)) return
  await action(async () => {
    await raw(`/recycle-bin/batch-${kind}`, json('POST', { records: selection }))
    await load()
    notice.value = `已${kind === 'restore' ? '还原' : '永久删除'} ${selection.length} 条记录`
  })
}
async function remove(record: CheckRecord) {
  if (!props.administrator || !window.confirm(`永久删除“${record.fields.material_name || '未填写物料'}”及其报告附件？删除后无法还原。`)) return
  await action(async () => {
    await raw(`/recycle-bin/${record.id}?version=${record.version}`, { method: 'DELETE' })
    await load()
  })
}
function formatTime(value: string | null, days = 0) {
  if (!value) return '—'
  return new Date(new Date(value).getTime() + days * 86400000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
onMounted(() => action(load))
</script>

<template>
  <main class="page">
    <div class="page-heading"><div><h1>回收站</h1></div><button :disabled="busy" @click="emit('close')">返回台账</button></div>
    <div class="retention-notice" role="note" aria-label="回收站保留期限"><strong>作废记录超过 30 天自动永久删除</strong><p>按作废时间计算，删除后无法还原，相关报告附件也会删除。管理员可在删除前还原记录，还原后需重新核对。</p></div>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="notice" role="status" class="notice">{{ notice }}</p>
    <section class="table-panel recycle-panel">
      <div class="filters">
        <label>公司台账<select v-model="selectedLedger"><option :value="0">全部公司</option><option v-for="ledger in ledgers" :key="ledger.id" :value="ledger.id">{{ ledger.name }}</option></select></label>
        <label class="search-label">查找回收记录<input v-model="query" type="search" placeholder="物料、供应商、规格、备注或记录编号"></label>
        <label>检验状态<select v-model="filters.inspection" aria-label="筛选检验状态"><option value="">全部</option><option value="inspected">检验</option><option value="uninspected">未检验</option></select></label>
        <label>创建人<select v-model="filters.creator"><option :value="0">所有人员</option><option v-for="person in people" :key="person.id" :value="person.id">{{ person.username }}</option></select></label>
        <label>到货日期从<input v-model="filters.arrivalFrom" type="date" aria-label="回收到货日期从"></label><label>到货日期至<input v-model="filters.arrivalTo" type="date" aria-label="回收到货日期至"></label>
        <label>作废日期从<input v-model="filters.voidFrom" type="date"></label><label>作废日期至<input v-model="filters.voidTo" type="date"></label>
        <button @click="clearFilters">清空筛选</button>
      </div>
      <p class="muted">符合条件 {{ visible.length }} 条</p>
      <div v-if="administrator" class="table-actions"><span>已选 {{ selected.length }} 条</span><div>
        <button :disabled="busy || !visible.length" @click="selectedIds = visible.map(row => row.id)">全选筛选结果</button>
        <button :disabled="busy || !selectedIds.length" @click="selectedIds = []">清空选择</button>
        <button :disabled="busy || !selected.length" @click="batchAction('restore')">批量还原</button>
        <button class="danger-button" :disabled="busy || !selected.length" @click="batchAction('delete')">批量永久删除</button>
      </div></div>
      <div class="table-scroll"><table class="ledger-table"><thead><tr><th v-if="administrator">选择</th><th>公司台账</th><th>录入日期</th><th>物料名称、型号</th><th>供应商或生产商</th><th>作废时间</th><th>自动删除时间</th><th>操作</th></tr></thead><tbody>
        <tr v-for="record in pageRows" :key="record.id"><td v-if="administrator"><input v-model="selectedIds" type="checkbox" :value="record.id" :disabled="busy" :aria-label="`选择回收记录${record.id}`"></td><td>{{ ledgers.find(ledger => ledger.id === record.ledger_id)?.name }}</td><td class="dates-cell">{{ entryDate(record.created_at) }}</td><td>{{ record.fields.material_name || '未填写物料' }}</td><td>{{ record.fields.company_name || '—' }}</td><td>{{ formatTime(record.voided_at) }}</td><td>{{ formatTime(record.voided_at, 30) }} 后</td><td><button class="text-button" :disabled="busy" @click="emit('open', record)">查看</button><button v-if="administrator" :disabled="busy" @click="restore(record)">还原</button><button v-if="administrator" class="danger-button" :disabled="busy" @click="remove(record)">永久删除</button></td></tr>
      </tbody></table></div>
      <p v-if="!visible.length" class="empty">{{ busy ? '正在读取回收站…' : '回收站中没有符合条件的记录' }}</p>
      <PaginationBar v-model:page="page" :total="visible.length" :disabled="busy" label="回收站分页" class="recycle-pagination" />
    </section>
  </main>
</template>

<style scoped>
.recycle-pagination { padding: 20px 24px; }
.recycle-panel > .muted { margin: 14px 24px; }
.ledger-table { min-width: 1050px; }
.ledger-table td:nth-child(n+4) { white-space: nowrap; }
.ledger-table td:last-child button + button { margin-left: 8px; }
</style>
