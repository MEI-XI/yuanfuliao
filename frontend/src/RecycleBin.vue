<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import { api, json, raw, recordSchema, type CheckRecord, type Ledger } from './api'

const props = defineProps<{ administrator: boolean; ledgers: Ledger[]; ledgerId: number | null }>()
const emit = defineEmits<{ close: []; open: [record: CheckRecord] }>()
const rows = ref<CheckRecord[]>([])
const selectedLedger = ref(props.ledgerId || 0)
const query = ref('')
const filters = reactive({ inspection: '', creator: 0, arrivalFrom: '', arrivalTo: '', voidFrom: '', voidTo: '' })
const people = ref<{ id: number; username: string }[]>([])
const busy = ref(false)
const error = ref('')
const visible = computed(() => rows.value.filter(row => (!selectedLedger.value || row.ledger_id === selectedLedger.value) &&
  (!query.value.trim() || [row.fields.material_name, row.fields.company_name, row.fields.specification, row.fields.notes, String(row.id)].some(value => value.toLowerCase().includes(query.value.trim().toLowerCase()))) &&
  (!filters.inspection || row.inspection_enabled === (filters.inspection === 'inspected')) &&
  (!filters.creator || row.creator_id === filters.creator) &&
  (!filters.arrivalFrom || (row.fields.arrival_date || '') >= filters.arrivalFrom) &&
  (!filters.arrivalTo || (!!row.fields.arrival_date && row.fields.arrival_date <= filters.arrivalTo)) &&
  (!filters.voidFrom || localDate(row.voided_at) >= filters.voidFrom) &&
  (!filters.voidTo || (!!row.voided_at && localDate(row.voided_at) <= filters.voidTo))))
function localDate(value: string | null) { return value ? new Date(value).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) : '' }
function clearFilters() {
  selectedLedger.value = props.ledgerId || 0; query.value = ''
  Object.assign(filters, { inspection: '', creator: 0, arrivalFrom: '', arrivalTo: '', voidFrom: '', voidTo: '' })
}
async function load() {
  const results = await Promise.all([api('/recycle-bin', z.array(recordSchema)), api('/people', z.array(z.object({ id: z.number(), username: z.string() })))])
  rows.value = results[0]; people.value = results[1]
}
async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await work() } catch (cause) { error.value = cause instanceof Error ? cause.message : '操作失败' }
  finally { busy.value = false }
}
function restore(record: CheckRecord) {
  return action(async () => {
    await api(`/records/${record.id}/restore`, recordSchema, json('POST', { version: record.version }))
    await load()
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
    <div class="page-heading"><div><h1>回收站</h1><p class="muted">作废记录超过 30 天自动永久删除；管理员可在删除前还原，还原后需重新核对。</p></div><button :disabled="busy" @click="emit('close')">返回台账</button></div>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
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
      <div class="table-scroll"><table class="ledger-table"><thead><tr><th>公司台账</th><th>物料名称、型号</th><th>供应商或生产商</th><th>作废时间</th><th>自动删除时间</th><th>操作</th></tr></thead><tbody>
        <tr v-for="record in visible" :key="record.id"><td>{{ ledgers.find(ledger => ledger.id === record.ledger_id)?.name }}</td><td>{{ record.fields.material_name || '未填写物料' }}</td><td>{{ record.fields.company_name || '—' }}</td><td>{{ formatTime(record.voided_at) }}</td><td>{{ formatTime(record.voided_at, 30) }} 后</td><td><button class="text-button" :disabled="busy" @click="emit('open', record)">查看</button><button v-if="administrator" :disabled="busy" @click="restore(record)">还原</button><button v-if="administrator" class="danger-button" :disabled="busy" @click="remove(record)">永久删除</button></td></tr>
      </tbody></table></div>
      <p v-if="!visible.length" class="empty">{{ busy ? '正在读取回收站…' : '回收站中没有符合条件的记录' }}</p>
    </section>
  </main>
</template>

<style scoped>
.recycle-panel > .muted { margin: 14px 24px; }
.ledger-table { min-width: 1050px; }
.ledger-table td:nth-child(n+4) { white-space: nowrap; }
.ledger-table td:last-child button + button { margin-left: 8px; }
</style>
