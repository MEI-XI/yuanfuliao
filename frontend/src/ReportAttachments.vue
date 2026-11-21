<script setup lang="ts">
import { defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { z } from 'zod'
import { api, ApiError, raw } from './api'

const PdfReportViewer = defineAsyncComponent(() => import('./PdfReportViewer.vue'))

const props = defineProps<{ recordId: number | null; recordVersion: number | null; editable: boolean; pendingFiles: File[] }>()
const attachmentSchema = z.object({
  id: z.number(), record_id: z.number(), owner_id: z.number(), filename: z.string(),
  media_type: z.string(), size: z.number(), created_at: z.string(),
})
const metadataSchema = z.object({
  record_version: z.number(), status: z.enum(['pending', 'checked', 'void']),
  checker_id: z.number().nullable(), checked_at: z.string().nullable(), updated_at: z.string(),
})
type Attachment = z.infer<typeof attachmentSchema>
type RecordMetadata = z.infer<typeof metadataSchema>
const emit = defineEmits<{ recordChanged: [metadata: RecordMetadata & { report_count: number }]; filesChanged: [files: File[]]; loaded: [count: number] }>()
const attachments = ref<Attachment[]>([])
const loading = ref(false)
const busy = ref(false)
const dragging = ref(false)
const error = ref('')
const reportExtensions = ['.jpg', '.jpeg', '.png', '.webp', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv', '.rtf']
const previewOpen = ref(false)
const previewName = ref('')
const previewLoading = ref(false)
const previewError = ref('')
type Preview = { kind: 'image' | 'pdf'; url: string } | { kind: 'text'; text: string }
const preview = ref<Preview | null>(null)
let previewRequest = 0

function clearPreview() {
  previewRequest += 1
  if (preview.value && preview.value.kind !== 'text') URL.revokeObjectURL(preview.value.url)
  preview.value = null
  previewLoading.value = false
}
watch(previewOpen, value => { if (!value) clearPreview() })
watch(() => props.editable, editable => { if (!editable) dragging.value = false })
onBeforeUnmount(clearPreview)
watch(() => props.recordId, async recordId => {
  attachments.value = []; error.value = ''; previewOpen.value = false
  if (recordId === null) return
  loading.value = true
  try {
    const loaded = await api(`/records/${recordId}/reports`, z.array(attachmentSchema))
    if (props.recordId === recordId) { attachments.value = loaded; emit('loaded', loaded.length) }
  } catch (cause) {
    if (props.recordId === recordId) error.value = cause instanceof Error ? cause.message : '无法读取报告附件'
  } finally {
    if (props.recordId === recordId) loading.value = false
  }
}, { immediate: true })

function chooseReports(event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) return
  const files = Array.from(input.files || [])
  input.value = ''
  void uploadReports(files)
}

function dragOver(event: DragEvent) {
  if (!event.dataTransfer?.types.includes('Files')) return
  dragging.value = !busy.value && !loading.value
  event.dataTransfer.dropEffect = dragging.value ? 'copy' : 'none'
}

function dragLeave(event: DragEvent) {
  if (event.relatedTarget instanceof Node && (event.currentTarget as HTMLElement).contains(event.relatedTarget)) return
  dragging.value = false
}

function dropReports(event: DragEvent) {
  dragging.value = false
  void uploadReports(Array.from(event.dataTransfer?.files || []))
}

async function uploadReports(files: File[]) {
  if (!files.length || !props.editable || busy.value || loading.value) return
  const recordId = props.recordId
  let version = props.recordVersion
  error.value = ''
  const failures: string[] = []
  const accepted = files.filter(file => {
    const problem = fileError(file)
    if (problem) failures.push(problem)
    return !problem
  })
  if (!accepted.length || recordId === null) {
    if (accepted.length) emit('filesChanged', [...props.pendingFiles, ...accepted])
    error.value = failures.join('。')
    return
  }
  if (version === null) return
  busy.value = true
  try {
    for (const [index, file] of accepted.entries()) {
      if (props.recordId !== recordId) return
      const body = new FormData()
      body.append('file', file)
      body.append('version', String(version))
      try {
        const result = await api(`/records/${recordId}/reports`, metadataSchema.extend({ attachment: attachmentSchema }), { method: 'POST', body })
        if (props.recordId !== recordId) return
        version = result.record_version
        attachments.value.push(result.attachment)
        notifyRecordChanged(result)
      } catch (cause) {
        failures.push(`“${file.name}”：${cause instanceof Error ? cause.message : '报告上传失败'}`)
        if (!(cause instanceof ApiError) || ![400, 413, 415, 422].includes(cause.status)) {
          const remaining = accepted.length - index - 1
          if (remaining) failures.push(`还有 ${remaining} 个附件未上传，请核对附件列表后重试`)
          break
        }
      }
    }
  } finally {
    if (props.recordId === recordId) error.value = failures.join('。')
    busy.value = false
  }
}

function fileError(file: File) {
  if (file.size > 20 * 1024 * 1024) return `“${file.name}”超过 20 MiB`
  if (!reportExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) return `“${file.name}”的格式不支持`
  return ''
}

function notifyRecordChanged(metadata: RecordMetadata) {
  const { record_version, status, checker_id, checked_at, updated_at } = metadata
  emit('recordChanged', { record_version, status, checker_id, checked_at, updated_at, report_count: attachments.value.length })
}

async function replaceReport(event: Event, attachment: Attachment) {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) return
  const file = input.files?.[0]
  input.value = ''
  const { recordId, recordVersion } = props
  if (!file || !props.editable || busy.value || loading.value || recordId === null || recordVersion === null) return
  error.value = fileError(file)
  if (error.value) return
  const body = new FormData()
  body.append('file', file)
  body.append('version', String(recordVersion))
  busy.value = true
  try {
    const result = await api(`/reports/${attachment.id}/replace`, metadataSchema.extend({ attachment: attachmentSchema }), { method: 'POST', body })
    if (props.recordId === recordId) {
      attachments.value = attachments.value.map(item => item.id === attachment.id ? result.attachment : item)
      notifyRecordChanged(result)
    }
  } catch (cause) {
    if (props.recordId === recordId) error.value = cause instanceof Error ? cause.message : '更换报告失败'
  } finally { busy.value = false }
}

async function remove(attachment: Attachment) {
  if (props.recordVersion === null || !props.editable || busy.value || loading.value || !window.confirm(`删除报告“${attachment.filename}”？`)) return
  const recordId = props.recordId
  busy.value = true; error.value = ''
  try {
    const result = await api(`/reports/${attachment.id}?version=${props.recordVersion}`, metadataSchema, { method: 'DELETE' })
    if (props.recordId === recordId) {
      attachments.value = attachments.value.filter(item => item.id !== attachment.id)
      notifyRecordChanged(result)
    }
  } catch (cause) {
    if (props.recordId === recordId) error.value = cause instanceof Error ? cause.message : '报告删除失败'
  } finally { busy.value = false }
}

async function showPreview(attachment: Attachment) {
  clearPreview()
  const request = previewRequest
  previewName.value = attachment.filename; previewError.value = ''; previewOpen.value = true; previewLoading.value = true
  try {
    const response = await raw(`/reports/${attachment.id}/preview`)
    if (attachment.media_type === 'text/plain') {
      const text = await response.text()
      if (request === previewRequest) preview.value = { kind: 'text', text }
    } else {
      const blob = await response.blob()
      if (request === previewRequest) preview.value = { kind: attachment.media_type.startsWith('image/') ? 'image' : 'pdf', url: URL.createObjectURL(blob) }
    }
  } catch (cause) {
    if (request === previewRequest) previewError.value = cause instanceof Error ? cause.message : '报告预览失败，请下载后查看'
  } finally { if (request === previewRequest) previewLoading.value = false }
}

async function showPendingPreview(file: File) {
  clearPreview()
  const request = previewRequest
  previewName.value = file.name; previewError.value = ''; previewOpen.value = true; previewLoading.value = true
  try {
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (['jpg', 'jpeg', 'png', 'webp', 'pdf'].includes(extension || '')) {
      preview.value = { kind: extension === 'pdf' ? 'pdf' : 'image', url: URL.createObjectURL(file) }
    } else {
      const body = new FormData(); body.append('file', file)
      const response = await raw('/reports/preview', { method: 'POST', body })
      if (response.headers.get('content-type')?.startsWith('text/plain')) {
        const text = await response.text()
        if (request === previewRequest) preview.value = { kind: 'text', text }
      } else {
        const blob = await response.blob()
        if (request === previewRequest) preview.value = { kind: 'pdf', url: URL.createObjectURL(blob) }
      }
    }
  } catch (cause) {
    if (request === previewRequest) previewError.value = cause instanceof Error ? cause.message : '报告预览失败'
  } finally { if (request === previewRequest) previewLoading.value = false }
}

function fileSize(size: number) {
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MiB` : `${Math.max(1, Math.ceil(size / 1024))} KiB`
}
</script>

<template>
  <section class="report-attachments" aria-label="报告附件">
    <div class="reports-heading"><h3>报告附件</h3><p class="muted">保存供应商报告、合格证或其他查验资料，可直接查看。</p></div>
    <div v-if="editable" class="report-attachment-drop" :class="{ dragging, disabled: busy || loading }"
      role="region" aria-label="报告附件拖入上传区域" @dragover.prevent="dragOver" @dragleave="dragLeave" @drop.prevent="dropReports">
      <strong>{{ dragging ? '松开以上传附件' : '将报告附件拖到这里' }}</strong>
      <span>支持一次拖入多份文件</span>
      <label class="report-upload" :class="{ disabled: busy || loading }">选择报告文件
        <input type="file" :accept="reportExtensions.join(',')" multiple aria-label="上传报告文件" :disabled="busy || loading" @change="chooseReports">
      </label>
    </div>
    <p v-if="recordId === null || pendingFiles.length" class="muted">已选文件随当前记录保存上传；关闭或刷新页面前请先保存。</p>
    <ul v-if="pendingFiles.length" class="report-list">
      <li v-for="(file, index) in pendingFiles" :key="index"><div class="report-details"><strong>{{ file.name }}</strong><span class="muted">{{ fileSize(file.size) }} · 待上传</span></div><button type="button" :aria-label="`查看待上传报告 ${file.name}`" @click="showPendingPreview(file)">查看</button><button v-if="editable" type="button" :aria-label="`移除待上传报告 ${file.name}`" @click="emit('filesChanged', pendingFiles.filter((_, position) => position !== index))">移除</button></li>
    </ul>
    <div>
      <p v-if="editable" class="muted report-formats">支持图片、PDF、Word、Excel和文本，每个文件不超过20 MiB。附件有变动后需重新核对记录。</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="loading || busy" class="muted" role="status">{{ loading ? '正在读取报告附件…' : '正在保存报告附件…' }}</p>
      <p v-if="!loading && !attachments.length && !pendingFiles.length" class="muted">暂无报告附件</p>
      <ul v-else class="report-list">
        <li v-for="attachment in attachments" :key="attachment.id">
          <button type="button" class="report-thumbnail" :aria-label="`查看报告 ${attachment.filename}`" @click="showPreview(attachment)">
            <img v-if="attachment.media_type.startsWith('image/')" :src="`/api/reports/${attachment.id}/file?v=${encodeURIComponent(attachment.created_at)}`" alt="报告缩略图">
            <span v-else aria-hidden="true">{{ attachment.filename.split('.').pop()?.toUpperCase() }}</span>
          </button>
          <div class="report-details"><strong>{{ attachment.filename }}</strong><span class="muted">{{ fileSize(attachment.size) }} · {{ new Date(attachment.created_at).toLocaleString('zh-CN', { hour12: false }) }}</span></div>
          <div class="report-actions">
            <button type="button" @click="showPreview(attachment)">查看</button>
            <a :href="`/api/reports/${attachment.id}/file?download=true`" :download="attachment.filename">下载</a>
            <template v-if="editable">
              <label class="report-replace" :class="{ disabled: busy || loading }">更换
                <input type="file" :accept="reportExtensions.join(',')" :aria-label="`更换报告 ${attachment.filename}`"
                  :disabled="busy || loading" @change="replaceReport($event, attachment)">
              </label>
              <button type="button" class="text-button" :disabled="busy" :aria-label="`删除报告 ${attachment.filename}`" @click="remove(attachment)">删除</button>
            </template>
          </div>
        </li>
      </ul>
    </div>
  </section>
  <el-dialog v-model="previewOpen" :title="previewName || '报告预览'" width="min(1100px, 96vw)" class="report-preview-dialog" append-to-body>
    <p v-if="previewLoading" class="muted" role="status">正在生成报告预览…</p>
    <p v-if="previewError" class="error" role="alert">{{ previewError }}</p>
    <img v-if="preview?.kind === 'image'" :src="preview.url" :alt="previewName" class="report-image-preview">
    <PdfReportViewer v-else-if="preview?.kind === 'pdf'" :key="preview.url" :url="preview.url" />
    <pre v-else-if="preview?.kind === 'text'" class="report-text-preview">{{ preview.text }}</pre>
    <template #footer><button type="button" aria-label="关闭报告预览" @click="previewOpen = false">关闭</button></template>
  </el-dialog>
</template>

<style scoped>
.report-attachments{margin-top:24px;padding:20px 28px 24px;border-top:1px solid var(--line)}.reports-heading h3{margin:0 0 6px}.reports-heading p{margin:0}.report-upload{position:relative;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;padding:10px 16px;min-height:42px;background:var(--teal);color:#fff;border-radius:6px;cursor:pointer;overflow:hidden}.report-upload input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:inherit}.report-upload:focus-within{outline:3px solid #087f8c66;outline-offset:2px}.report-upload.disabled{opacity:.55;cursor:default}.report-formats{font-size:13px}.report-list{list-style:none;margin:18px 0 0;padding:0}.report-list li{display:flex;align-items:center;gap:12px;border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:10px}.report-thumbnail{width:64px;height:64px;flex-shrink:0;padding:0;background:#edf3f5;color:#496575;overflow:hidden}.report-thumbnail img{width:100%;height:100%;object-fit:contain}.report-thumbnail span{font-size:13px;font-weight:700}.report-details{display:flex;flex:1;min-width:0;flex-direction:column;gap:6px}.report-details strong{overflow-wrap:anywhere}.report-details span{font-size:12px}.report-actions{display:flex;align-items:center;gap:14px}.report-actions a{color:var(--teal);text-decoration:none}.report-image-preview{display:block;max-width:100%;max-height:72vh;object-fit:contain;margin:auto}.report-pdf-preview{width:100%;height:70vh;border:1px solid var(--line)}.report-text-preview{white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto;font-family:inherit}@media(max-width:600px){.report-list li{flex-wrap:wrap}.report-actions{width:100%;justify-content:flex-end}.report-details span{line-height:1.5}}

.report-attachment-drop {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 8px;
  min-height: 160px;
  margin-top: 16px;
  padding: 20px 12px;
  border: 2px dashed #3d9b9c;
  border-radius: 8px;
  background: #f0f9f8;
  color: #526f7a;
  text-align: center;
}
.report-attachment-drop:not(.disabled):is(.dragging, :focus-within) {
  border-color: var(--teal);
  background: #ddf2ef;
}
.report-attachment-drop strong {
  color: #087f8c;
}
.report-attachment-drop span {
  font-size: 13px;
}
.report-actions {
  flex-wrap: wrap;
}
.report-replace {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  color: var(--teal);
  cursor: pointer;
}
.report-replace input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: inherit;
}
.report-replace:focus-within {
  outline: 2px solid var(--teal);
  outline-offset: 3px;
}
.report-replace.disabled {
  opacity: .55;
  cursor: default;
}
</style>
