<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import { api, auditPageSchema } from './api'

const result = ref<z.infer<typeof auditPageSchema> | null>(null)
const busy = ref(false), error = ref('')
const filters = reactive({ actor: '', action: '', target: '', from_date: '', to_date: '' })
let appliedFilters = { ...filters }
function search() { appliedFilters = { ...filters }; void load() }
function clearFilters() {
  Object.assign(filters, { actor: '', action: '', target: '', from_date: '', to_date: '' })
  search()
}
async function load(page = 1) {
  busy.value = true; error.value = ''
  const params = new URLSearchParams({ page: String(page), page_size: '50' })
  for (const [key, value] of Object.entries(appliedFilters)) if (value) params.set(key, value)
  try { result.value = await api(`/audit-logs?${params}`, auditPageSchema) }
  catch (e) { error.value = e instanceof Error ? e.message : '日志读取失败，请重试' }
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
    <p class="muted">记录账号、公共资料与查验业务操作，按发生时间倒序显示。时间为北京时间。</p>
    <form class="filters" @submit.prevent="search">
      <label>操作人<input v-model="filters.actor" aria-label="日志操作人" list="audit-actors" placeholder="账号名称，可模糊查找" :disabled="busy"><datalist id="audit-actors"><option v-for="actor in result?.actors" :key="actor" :value="actor" /></datalist></label>
      <label>操作类型<select v-model="filters.action" aria-label="日志操作类型" :disabled="busy"><option value="">全部操作</option><option v-for="action in result?.actions" :key="action" :value="action">{{ action }}</option></select></label>
      <label>操作对象<input v-model="filters.target" aria-label="日志操作对象" placeholder="路径或记录编号" :disabled="busy"></label>
      <label>开始日期<input v-model="filters.from_date" type="date" aria-label="日志开始日期" :disabled="busy"></label>
      <label>结束日期<input v-model="filters.to_date" type="date" aria-label="日志结束日期" :disabled="busy"></label>
      <button type="submit" class="primary" :disabled="busy">筛选日志</button><button type="button" :disabled="busy" @click="clearFilters">清空筛选</button>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="busy" role="status">正在读取日志…</p>
    <div v-if="result" class="table-scroll">
      <table class="ledger-table audit-table">
        <thead><tr><th>时间</th><th>操作人</th><th>操作</th><th>操作对象</th><th>结果</th></tr></thead>
        <tbody><tr v-for="entry in result.items" :key="entry.id">
          <td><time :datetime="entry.at">{{ displayTime(entry.at) }}</time></td>
          <td>{{ entry.actor_username }}</td><td>{{ entry.action }}</td><td>{{ entry.target }}</td>
          <td>{{ entry.status_code < 400 ? '成功' : '失败' }}<small v-if="entry.status_code >= 400">（{{ entry.status_code }}）</small></td>
        </tr></tbody>
      </table>
      <p v-if="!result.items.length" class="module-empty">暂无操作日志。</p>
    </div>
    <nav v-if="result" class="audit-pagination" aria-label="日志分页">
      <span>共 {{ result.total }} 条 · 第 {{ result.page }} 页</span>
      <div class="button-row"><button :disabled="busy || result.page <= 1" @click="load(result.page - 1)">上一页</button><button :disabled="busy || result.page * result.page_size >= result.total" @click="load(result.page + 1)">下一页</button></div>
    </nav>
  </section>
</template>

<style scoped>
.module-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.module-heading h2 { margin: 0; }
.audit-table td { vertical-align: top; overflow-wrap: anywhere; }
.audit-table { min-width: 720px; }
.audit-table time { white-space: nowrap; }
.audit-pagination { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 18px; flex-wrap: wrap; }
.audit-pagination .button-row { margin: 0; }
</style>
