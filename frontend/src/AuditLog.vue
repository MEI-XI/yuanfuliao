<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { z } from 'zod'
import { api, auditPageSchema } from './api'

const result = ref<z.infer<typeof auditPageSchema> | null>(null)
const busy = ref(false), error = ref('')
async function load(page = 1) {
  busy.value = true; error.value = ''
  try { result.value = await api(`/audit-logs?page=${page}&page_size=50`, auditPageSchema) }
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
.audit-table time { white-space: nowrap; }
.audit-pagination { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 18px; flex-wrap: wrap; }
.audit-pagination .button-row { margin: 0; }
</style>
