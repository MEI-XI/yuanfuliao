<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { z } from 'zod'
import { api, raw } from './api'

const props = defineProps<{ recordId: number | null; recordVersion: number | null; editable: boolean }>()
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
const emit = defineEmits<{ recordChanged: [metadata: RecordMetadata] }>()
const attachments = ref<Attachment[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
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
onBeforeUnmount(clearPreview)
watch(() => props.recordId, async recordId => {
  attachments.value = []; error.value = ''; previewOpen.value = false
  if (recordId === null) return
  loading.value = true
  try {
    const loaded = await api(`/records/${recordId}/reports`, z.array(attachmentSchema))
    if (props.recordId === recordId) attachments.value = loaded
  } catch (cause) {
    if (props.recordId === recordId) error.value = cause instanceof Error ? cause.message : '无法读取报告附件'
  } finally {
    if (props.recordId === recordId) loading.value = false
  }
}, { immediate: true })

async function upload(event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) return
  const file = input.files?.[0]
  input.value = ''
  const recordId = props.recordId
  if (!file || recordId === null || props.recordVersion === null || !props.editable) return
  error.value = ''
  if (file.size > 20 * 1024 * 1024) { error.value = '单个报告文件不能超过20 MiB'; return }
  const body = new FormData()
  body.append('file', file)
  body.append('version', String(props.recordVersion))
  busy.value = true
  try {
    const result = await api(`/records/${recordId}/reports`, metadataSchema.extend({ attachment: attachmentSchema }), { method: 'POST', body })
    if (props.recordId === recordId) {
      attachments.value.push(result.attachment)
      emit('recordChanged', result)
    }
  } catch (cause) {
    if (props.recordId === recordId) error.value = cause instanceof Error ? cause.message : '报告上传失败'
  } finally { busy.value = false }
}

async function remove(attachment: Attachment) {
  if (props.recordVersion === null || !props.editable || !window.confirm(`删除报告“${attachment.filename}”？`)) return
  const recordId = props.recordId
  busy.value = true; error.value = ''
  try {
    const result = await api(`/reports/${attachment.id}?version=${props.recordVersion}`, metadataSchema, { method: 'DELETE' })
    if (props.recordId === recordId) {
      attachments.value = attachments.value.filter(item => item.id !== attachment.id)
      emit('recordChanged', result)
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

function fileSize(size: number) {
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MiB` : `${Math.max(1, Math.ceil(size / 1024))} KiB`
}
</script>

<template>
  <section class="report-attachments" aria-label="报告附件">
    <div class="reports-heading"><div><h3>报告附件</h3><p class="muted">保存供应商报告、合格证或其他查验资料，可直接查看。</p></div>
      <label v-if="recordId !== null && editable" class="report-upload" :class="{ disabled: busy || loading }">上传报告
        <input type="file" accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx,.txt,.csv,.rtf" aria-label="上传报告文件" :disabled="busy || loading" @change="upload">
      </label>
    </div>
    <p v-if="recordId === null" class="muted">先保存记录，再打开记录上传报告附件。</p>
    <template v-else>
      <p v-if="editable" class="muted report-formats">支持图片、PDF、Word、Excel和文本，每个文件不超过20 MiB。上传或删除后需重新核对记录。</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="loading || busy" class="muted" role="status">{{ loading ? '正在读取报告附件…' : '正在保存报告附件…' }}</p>
      <p v-if="!loading && !attachments.length" class="muted">暂无报告附件</p>
      <ul v-else class="report-list">
        <li v-for="attachment in attachments" :key="attachment.id">
          <button type="button" class="report-thumbnail" :aria-label="`查看报告 ${attachment.filename}`" @click="showPreview(attachment)">
            <img v-if="attachment.media_type.startsWith('image/')" :src="`/api/reports/${attachment.id}/file`" alt="报告缩略图">
            <span v-else aria-hidden="true">{{ attachment.filename.split('.').pop()?.toUpperCase() }}</span>
          </button>
          <div class="report-details"><strong>{{ attachment.filename }}</strong><span class="muted">{{ fileSize(attachment.size) }} · {{ new Date(attachment.created_at).toLocaleString('zh-CN', { hour12: false }) }}</span></div>
          <div class="report-actions"><button type="button" @click="showPreview(attachment)">查看</button><a :href="`/api/reports/${attachment.id}/file?download=true`" :download="attachment.filename">下载</a><button v-if="editable" type="button" class="text-button" :disabled="busy" :aria-label="`删除报告 ${attachment.filename}`" @click="remove(attachment)">删除</button></div>
        </li>
      </ul>
    </template>
  </section>
  <el-dialog v-model="previewOpen" :title="previewName || '报告预览'" width="min(1100px, 96vw)" class="report-preview-dialog" append-to-body>
    <p v-if="previewLoading" class="muted" role="status">正在生成报告预览…</p>
    <p v-if="previewError" class="error" role="alert">{{ previewError }}</p>
    <img v-if="preview?.kind === 'image'" :src="preview.url" :alt="previewName" class="report-image-preview">
    <iframe v-else-if="preview?.kind === 'pdf'" :src="preview.url" :title="previewName" class="report-pdf-preview"></iframe>
    <pre v-else-if="preview?.kind === 'text'" class="report-text-preview">{{ preview.text }}</pre>
    <template #footer><button type="button" aria-label="关闭报告预览" @click="previewOpen = false">关闭</button></template>
  </el-dialog>
</template>

<style scoped>
.report-attachments{margin-top:24px;padding:20px 28px 24px;border-top:1px solid var(--line)}.reports-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.reports-heading h3{margin:0 0 6px}.reports-heading p{margin:0}.report-upload{position:relative;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;padding:10px 16px;min-height:42px;background:var(--teal);color:#fff;border-radius:6px;cursor:pointer;overflow:hidden}.report-upload input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:inherit}.report-upload:focus-within{outline:3px solid #087f8c66;outline-offset:2px}.report-upload.disabled{opacity:.55;cursor:default}.report-formats{font-size:13px}.report-list{list-style:none;margin:18px 0 0;padding:0}.report-list li{display:flex;align-items:center;gap:12px;border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:10px}.report-thumbnail{width:64px;height:64px;flex-shrink:0;padding:0;background:#edf3f5;color:#496575;overflow:hidden}.report-thumbnail img{width:100%;height:100%;object-fit:contain}.report-thumbnail span{font-size:13px;font-weight:700}.report-details{display:flex;flex:1;min-width:0;flex-direction:column;gap:6px}.report-details strong{overflow-wrap:anywhere}.report-details span{font-size:12px}.report-actions{display:flex;align-items:center;gap:14px}.report-actions a{color:var(--teal);text-decoration:none}.report-image-preview{display:block;max-width:100%;max-height:72vh;object-fit:contain;margin:auto}.report-pdf-preview{width:100%;height:70vh;border:1px solid var(--line)}.report-text-preview{white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto;font-family:inherit}@media(max-width:600px){.reports-heading{align-items:flex-start}.report-list li{flex-wrap:wrap}.report-actions{width:100%;justify-content:flex-end}.report-details span{line-height:1.5}}
</style>
