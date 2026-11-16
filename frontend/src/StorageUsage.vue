<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { z } from 'zod'
import { api } from './api'

const usageSchema = z.object({
  measured_at: z.string(),
  categories: z.array(z.object({ key: z.string(), label: z.string(), bytes: z.number().nonnegative(), files: z.number().nullable(), note: z.string() })),
  database_bytes: z.number().nonnegative(),
  disk: z.object({ total: z.number().nonnegative(), free: z.number().nonnegative() }),
  cleanup: z.object({ interval_hours: z.number(), retention_days: z.number(), notes: z.array(z.string()) }),
})
const usage = ref<z.infer<typeof usageSchema> | null>(null)
const loading = ref(false)
const error = ref('')
const controller = new AbortController()
const measuredTotal = computed(() => usage.value ? usage.value.database_bytes + usage.value.categories.reduce((sum, item) => sum + item.bytes, 0) : 0)
function size(bytes: number) {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** unit).toLocaleString('zh-CN', { maximumFractionDigits: unit ? 2 : 0 })} ${units[unit]}`
}
function date(value: string) { return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) }
async function refresh() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try { usage.value = await api('/storage-usage', usageSchema, { signal: controller.signal }) }
  catch (cause) { if (!controller.signal.aborted) error.value = cause instanceof Error ? cause.message : '占用空间统计失败，请重试。' }
  finally { loading.value = false }
}
onMounted(refresh)
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <section class="admin-card storage-usage" aria-label="占用空间明细">
    <div class="storage-heading"><div><h2>占用空间明细</h2><p class="muted">查看业务文件、数据库和临时文件占用，以及自动回收规则。</p></div><button type="button" :disabled="loading" @click="refresh">{{ loading ? '统计中…' : error ? '重试统计' : '刷新统计' }}</button></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading" class="muted" role="status">正在统计占用空间，文件较多时请稍候…</p>
    <template v-if="usage">
      <p class="storage-time muted">统计时间：{{ date(usage.measured_at) }}<span v-if="error">（上次成功结果）</span></p>
      <div class="storage-summary">
        <div><span>已统计项目占用</span><strong>{{ size(measuredTotal) }}</strong><small>下表文件分类与数据库之和</small></div>
        <div><span>业务文件所在磁盘剩余</span><strong>{{ size(usage.disk.free) }}</strong><small>磁盘总容量 {{ size(usage.disk.total) }}</small></div>
      </div>
      <p class="storage-scope muted">项目占用不等于整块磁盘已用空间；数据库可能位于其他服务器，不能用项目合计计算此磁盘剩余容量。</p>
      <div class="table-scroll"><table class="ledger-table storage-table"><thead><tr><th>分类</th><th>占用空间</th><th>文件数量</th><th>说明与保留规则</th></tr></thead><tbody>
        <tr v-for="item in usage.categories" :key="item.key"><td>{{ item.label }}</td><td>{{ size(item.bytes) }}</td><td>{{ item.files === null ? '—' : item.files.toLocaleString('zh-CN') }}</td><td>{{ item.note }}</td></tr>
        <tr><td>业务数据库</td><td>{{ size(usage.database_bytes) }}</td><td>—</td><td>包含业务数据、索引等。删除数据后空间可能供数据库复用，不会立即全部归还磁盘。</td></tr>
      </tbody></table></div>
      <div class="storage-cleanup"><h3>资源回收与保留规则</h3><p class="notice">服务启动后自动检查，并每 {{ usage.cleanup.interval_hours }} 小时执行一次。回收站记录与操作日志保留 {{ usage.cleanup.retention_days }} 天。</p><ul><li v-for="note in usage.cleanup.notes" :key="note">{{ note }}</li></ul><p class="muted">正常业务记录及其仍被引用的图片、报告附件和模板不作为缓存清理。个人电脑上的下载文件、个人模板不计入服务器占用。</p></div>
    </template>
  </section>
</template>

<style scoped>
.storage-usage{min-width:0}.storage-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.storage-heading h2{margin:0 0 8px}.storage-heading p{margin:0}.storage-heading button{flex-shrink:0}.storage-time{margin:16px 0 12px;font-size:13px}.storage-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:12px}.storage-summary>div{padding:16px 18px;border:1px solid var(--line);border-radius:6px;display:flex;flex-direction:column;gap:6px;background:#f5faf9}.storage-summary span{font-size:14px;color:#405767}.storage-summary strong{font-size:26px;color:var(--teal);font-weight:650}.storage-summary small{font-size:12px;color:#647b86}.storage-scope{font-size:13px}.storage-table{min-width:620px}.storage-table td{padding:13px 15px;vertical-align:top}.storage-table td:first-child{font-weight:600;min-width:130px}.storage-table td:nth-child(2),.storage-table td:nth-child(3){white-space:nowrap}.storage-table td:last-child{white-space:normal;overflow-wrap:anywhere;min-width:240px}.storage-cleanup{margin-top:24px}.storage-cleanup h3{font-size:16px;margin:0 0 12px}.storage-cleanup ul{padding-left:22px;line-height:1.8;font-size:14px;color:#405767}.storage-cleanup li+li{margin-top:6px}.storage-cleanup>.muted{font-size:13px}@media(max-width:600px){.storage-usage{padding:18px}.storage-heading{align-items:flex-start}.storage-heading h2{font-size:18px}.storage-heading p{font-size:13px}.storage-heading button{padding:8px 10px}.storage-summary{grid-template-columns:1fr;gap:10px}.storage-summary>div{padding:12px 14px}.storage-summary strong{font-size:23px}}
</style>
