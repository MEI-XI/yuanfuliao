<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { z } from 'zod'
import { api, json, recordSchema, type CheckRecord, type Ledger } from './api'

const props = defineProps<{ administrator: boolean; ledgers: Ledger[]; ledgerId: number | null }>()
const emit = defineEmits<{ close: []; open: [record: CheckRecord] }>()
const rows = ref<CheckRecord[]>([])
const selectedLedger = ref(props.ledgerId || 0)
const query = ref('')
const busy = ref(false)
const error = ref('')
const visible = computed(() => rows.value.filter(row => (!selectedLedger.value || row.ledger_id === selectedLedger.value) &&
  (!query.value || [row.fields.material_name, row.fields.company_name].some(value => value.includes(query.value)))))
async function load() { rows.value = await api('/recycle-bin', z.array(recordSchema)) }
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
    <section class="ledger-card">
      <div class="filters"><label>公司台账<select v-model="selectedLedger"><option :value="0">全部公司</option><option v-for="ledger in ledgers" :key="ledger.id" :value="ledger.id">{{ ledger.name }}</option></select></label><label>查找回收记录<input v-model="query" type="search" placeholder="物料或供应商名称"></label></div>
      <div class="table-scroll"><table class="ledger-table"><thead><tr><th>公司台账</th><th>物料名称、型号</th><th>供应商或生产商</th><th>作废时间</th><th>自动删除时间</th><th>操作</th></tr></thead><tbody>
        <tr v-for="record in visible" :key="record.id"><td>{{ ledgers.find(ledger => ledger.id === record.ledger_id)?.name }}</td><td>{{ record.fields.material_name || '未填写物料' }}</td><td>{{ record.fields.company_name || '—' }}</td><td>{{ formatTime(record.voided_at) }}</td><td>{{ formatTime(record.voided_at, 30) }} 后</td><td><button class="text-button" :disabled="busy" @click="emit('open', record)">查看</button><button v-if="administrator" :disabled="busy" @click="restore(record)">还原</button></td></tr>
      </tbody></table></div>
      <p v-if="!visible.length" class="empty">{{ busy ? '正在读取回收站…' : '回收站中没有符合条件的记录' }}</p>
    </section>
  </main>
</template>
