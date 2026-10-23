<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import PaginationBar from './PaginationBar.vue'
import { api, auditPageSchema, json, raw } from './api'

const result = ref<z.infer<typeof auditPageSchema> | null>(null)
const detailEntry = ref<z.infer<typeof auditPageSchema>['items'][number] | null>(null)
const detailOpen = ref(false)
function showDetails(entry: z.infer<typeof auditPageSchema>['items'][number]) {
  detailEntry.value = entry
  detailOpen.value = true
}
const busy = ref(false), error = ref('')
const notice = ref('')
const selectedIds = ref<number[]>([])
const selected = computed(() => (result.value?.items || []).filter(row => selectedIds.value.includes(row.id)))
const filters = reactive({ actor: '', action: '', target: '', from_date: '', to_date: '' })
let appliedFilters = { ...filters }
function search() { appliedFilters = { ...filters }; void load() }
function clearFilters() {
  Object.assign(filters, { actor: '', action: '', target: '', from_date: '', to_date: '' })
  search()
}
async function readPage(page: number) {
  selectedIds.value = []
  const params = new URLSearchParams({ page: String(page), page_size: '50' })
  for (const [key, value] of Object.entries(appliedFilters)) if (value) params.set(key, value)
  const response = await api(`/audit-logs?${params}`, auditPageSchema)
  const lastPage = Math.max(1, Math.ceil(response.total / response.page_size))
  if (page > lastPage) { await readPage(lastPage); return }
  result.value = response
}
async function load(page = 1) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await readPage(page) }
  catch (e) { error.value = e instanceof Error ? e.message : '日志读取失败，请重试' }
  finally { busy.value = false }
}
async function removeSelected() {
  const ids = selected.value.map(row => row.id)
  if (busy.value || !ids.length || !window.confirm(`确定永久删除所选 ${ids.length} 条操作日志？删除后无法恢复，不影响查验台账。`)) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await raw('/audit-logs/batch-delete', json('POST', { ids }))
    await readPage(result.value?.page || 1)
    notice.value = `已删除 ${ids.length} 条操作日志`
  } catch (e) { error.value = e instanceof Error ? e.message : '日志删除失败，请刷新后重试' }
  finally { busy.value = false }
}
function displayTime(at: string) {
  return new Date(at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
onMounted(() => load())
</script>

<template>
  <section class="admin-card" aria-label="所有人员操作日志" :aria-busy="busy">
    <div class="module-heading"><h2>所有人员操作日志</h2><button :disabled="busy" @click="load()">刷新日志</button></div>
    <div class="retention-notice" role="note" aria-label="操作日志保留期限"><strong>操作日志超过 30 天自动永久删除</strong><p>按操作发生时间计算。服务启动时及后台每小时自动清理，无需打开此页面。删除后无法恢复，请及时查阅所需日志。</p></div>
    <p class="muted">记录账号、公共资料与查验业务操作，按发生时间倒序显示。时间为北京时间。</p>
    <form class="filters" @submit.prevent="search">
      <label>操作人<input v-model="filters.actor" aria-label="日志操作人" list="audit-actors" placeholder="账号名称，可模糊查找" :disabled="busy"><datalist id="audit-actors"><option v-for="actor in result?.actors" :key="actor" :value="actor" /></datalist></label>
      <label>操作类型<select v-model="filters.action" aria-label="日志操作类型" :disabled="busy"><option value="">全部操作</option><option v-for="action in result?.actions" :key="action" :value="action">{{ action }}</option></select></label>
      <label>操作内容<input v-model="filters.target" aria-label="日志操作对象" placeholder="物料、方案、公司名称或记录编号" :disabled="busy"></label>
      <label>开始日期<input v-model="filters.from_date" type="date" aria-label="日志开始日期" :disabled="busy"></label>
      <label>结束日期<input v-model="filters.to_date" type="date" aria-label="日志结束日期" :disabled="busy"></label>
      <button type="submit" class="primary" :disabled="busy">筛选日志</button><button type="button" :disabled="busy" @click="clearFilters">清空筛选</button>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="notice" role="status" class="notice">{{ notice }}</p>
    <p v-if="busy" role="status">正在读取日志…</p>
    <div v-if="result" class="table-actions"><span role="status">筛选 {{ result.total }} 条 · 已选 {{ selected.length }} 条本页日志</span><div>
      <button :disabled="busy || !result.items.length" @click="selectedIds = result.items.map(row => row.id)">全选本页日志</button>
      <button :disabled="busy || !selected.length" @click="selectedIds = []">清空选择</button>
      <button class="danger-button" :disabled="busy || !selected.length" @click="removeSelected">批量删除日志</button>
    </div></div>
    <div v-if="result" class="table-scroll">
      <table class="ledger-table audit-table">
        <colgroup><col style="width: 60px"><col style="width: 190px"><col style="width: 130px"><col style="width: 140px"><col><col style="width: 80px"><col style="width: 100px"></colgroup>
        <thead><tr><th>选择</th><th>时间</th><th>操作人</th><th>操作</th><th>操作内容</th><th>结果</th><th>详情</th></tr></thead>
        <tbody><tr v-for="entry in result.items" :key="entry.id">
          <td><input v-model="selectedIds" type="checkbox" :value="entry.id" :disabled="busy" :aria-label="`选择操作日志${entry.id}`"></td>
          <td><time :datetime="entry.at">{{ displayTime(entry.at) }}</time></td>
          <td :title="entry.actor_username">{{ entry.actor_username }}</td><td :title="entry.action">{{ entry.action }}</td><td><button class="audit-content" :title="entry.description || entry.action" aria-label="展开完整操作内容" @click="showDetails(entry)">{{ entry.description || entry.action }}</button></td>
          <td>{{ entry.status_code < 400 ? '成功' : '失败' }}<small v-if="entry.status_code >= 400">（{{ entry.status_code }}）</small></td>
          <td><button class="text-button audit-detail-button" @click="showDetails(entry)">查看详情</button></td>
        </tr></tbody>
      </table>
      <p v-if="!result.items.length" class="module-empty">暂无操作日志。</p>
    </div>
    <PaginationBar v-if="result" :page="result.page" :total="result.total" :page-size="result.page_size" :disabled="busy" label="日志分页" @update:page="load" />
    <el-dialog v-model="detailOpen" title="操作日志详情" width="min(780px, 94vw)" append-to-body>
      <dl v-if="detailEntry" class="audit-detail">
        <dt>日志编号</dt><dd>{{ detailEntry.id }}</dd>
        <dt>时间</dt><dd>{{ displayTime(detailEntry.at) }}</dd>
        <dt>操作人</dt><dd>{{ detailEntry.actor_username }}</dd>
        <dt>操作</dt><dd>{{ detailEntry.action }}</dd>
        <dt>结果</dt><dd>{{ detailEntry.status_code < 400 ? '成功' : '失败' }}</dd>
        <dt>操作内容</dt><dd>{{ detailEntry.description || detailEntry.action }}</dd>
      </dl>
      <template #footer><button @click="detailOpen = false">关闭详情</button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.module-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.module-heading h2 { margin: 0; }
.audit-table th, .audit-table td { vertical-align: middle; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 12px; }
.audit-table { min-width: 1040px; width: 100%; table-layout: fixed; }
.audit-content { display: block; width: 100%; min-width: 0; min-height: 0; padding: 0; border: 0; border-radius: 0; background: transparent; text-align: left; font: inherit; color: inherit; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.audit-content:hover { color: var(--teal); text-decoration: underline; }
.audit-detail-button { min-height: 32px; padding: 4px 0; white-space: nowrap; }
.audit-detail { display: grid; grid-template-columns: 80px minmax(0, 1fr); gap: 14px 16px; max-height: 65vh; overflow: auto; margin: 0; }
.audit-detail dt { color: #64748b; }
.audit-detail dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
.audit-table time { white-space: nowrap; }
.filters{padding:16px 0;margin:12px 0 0;gap:12px}.filters label{flex:1 1 140px;min-width:0;margin:0}.filters input[type="date"]{width:150px}.table-actions{padding:12px 0;gap:10px}.table-actions [role="status"]{font-weight:600;color:var(--teal)}.table-actions>div{display:flex;flex-wrap:wrap;gap:8px}.table-actions button+button{margin-left:0}
@media(max-width:600px){.filters label{flex:1 1 125px}.filters input[type="date"]{width:100%}.module-heading h2{font-size:17px}.module-heading button{padding:8px 10px;font-size:13px}}
</style>
