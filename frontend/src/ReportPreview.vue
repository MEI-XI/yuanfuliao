<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, json, raw, recordSchema, type CheckRecord } from './api'
import { readExportTemplate, selectedTemplateSources, type TemplateKind } from './localTemplates'

const props = defineProps<{ userId: number; recordIds: number[] }>()
const emit = defineEmits<{ close: [] }>()
const records = ref<CheckRecord[]>([])
const kind = ref<TemplateKind>('xlsx')
const frame = ref<HTMLIFrameElement | null>(null)
const pdfLoaded = ref(false)
type PreviewState = { kind: 'loading' } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'ready'; url: string; source: string }
const state = ref<PreviewState>({ kind: 'loading' })
const printError = ref('')
const controller = new AbortController()
const pending = computed(() => records.value.some(record => record.status === 'pending'))
let pendingConfirmed = false
let generation = 0

function releasePdf() {
  if (state.value.kind === 'ready') URL.revokeObjectURL(state.value.url)
}

async function generate(next: TemplateKind) {
  if (!records.value.length || state.value.kind === 'loading') return
  if (next === 'docx' && records.value.some(record => !record.inspection_enabled)) {
    window.alert('所选记录中有未检验记录，请取消勾选未检验记录后预览 Word。')
    return
  }
  if (pending.value && !pendingConfirmed) {
    if (!window.confirm('所选记录包含待核对内容，仍要生成导出预览吗？')) return
    pendingConfirmed = true
  }
  const ticket = ++generation
  releasePdf()
  kind.value = next
  state.value = { kind: 'loading' }
  printError.value = ''
  pdfLoaded.value = false
  try {
    const template = await readExportTemplate(props.userId, next)
    const sources = await selectedTemplateSources(props.userId)
    const source = sources[next]
    const response = await raw(`/previews/${next}`, {
      ...json('POST', { record_ids: props.recordIds, include_pending: pending.value, template_base64: template }),
      signal: controller.signal,
    })
    const blob = await response.blob()
    if (ticket !== generation) return
    state.value = { kind: 'ready', url: URL.createObjectURL(blob),
      source: source.source === 'personal' ? `个人模板：${source.name}` : source.source === 'legacy' ? '个人模板：原模板目录文件' : '服务器默认模板' }
  } catch (error) {
    if (ticket === generation && !controller.signal.aborted) state.value = { kind: 'error', message: error instanceof Error ? error.message : '预览生成失败，请重试' }
  }
}

function print() {
  if (state.value.kind !== 'ready' || !pdfLoaded.value) return
  try {
    if (!frame.value?.contentWindow) return
    frame.value.contentWindow.focus()
    frame.value.contentWindow.print()
  } catch {
    printError.value = '当前浏览器无法直接打印内嵌 PDF，请点击“打开 PDF”后打印。'
  }
}

onMounted(async () => {
  try {
    records.value = await Promise.all(props.recordIds.map(id => api(`/records/${id}`, recordSchema, { signal: controller.signal })))
    if (controller.signal.aborted) return
    state.value = { kind: 'empty' }
    await generate('xlsx')
  } catch (error) {
    if (!controller.signal.aborted) state.value = { kind: 'error', message: error instanceof Error ? error.message : '读取记录失败' }
  }
})

onBeforeUnmount(() => {
  generation++
  controller.abort()
  releasePdf()
})
</script>

<template>
  <el-dialog :model-value="true" title="导出预览" width="min(1200px, 96vw)" top="3vh" @close="emit('close')">
    <div class="preview-toolbar">
      <div class="preview-formats" aria-label="预览格式">
        <button type="button" :class="{ active: kind === 'xlsx' }" :aria-pressed="kind === 'xlsx'" :disabled="state.kind === 'loading'" @click="generate('xlsx')">Excel 查验台账</button>
        <button type="button" :class="{ active: kind === 'docx' }" :aria-pressed="kind === 'docx'" :disabled="state.kind === 'loading'" @click="generate('docx')">Word 检验报告</button>
      </div>
      <div class="preview-print"><a v-if="state.kind === 'ready'" :href="state.url" target="_blank" rel="noopener">打开 PDF</a><button type="button" class="primary" :disabled="state.kind !== 'ready' || !pdfLoaded" @click="print">打印</button></div>
    </div>
    <p class="preview-context">共 {{ recordIds.length }} 条记录<span v-if="state.kind === 'ready'"> · {{ state.source }}</span>。{{ kind === 'xlsx' ? '按公司分表，横向打印。' : '每条记录一份报告，连续分页显示。' }}</p>
    <p v-if="printError" class="error" role="alert">{{ printError }}</p>
    <div v-if="state.kind === 'loading'" class="preview-placeholder" role="status">正在生成导出预览，请稍候…</div>
    <div v-else-if="state.kind === 'error'" class="preview-placeholder"><p class="error" role="alert">{{ state.message }}</p><button v-if="records.length" @click="generate(kind)">重新生成</button></div>
    <div v-else-if="state.kind === 'empty'" class="preview-placeholder"><p>确认待核对记录后即可预览。</p><button @click="generate(kind)">生成预览</button></div>
    <iframe v-else ref="frame" :src="state.url + '#view=FitH&navpanes=0'" title="导出文件预览" class="export-preview-frame" @load="pdfLoaded = true"></iframe>
    <template #footer><button type="button" @click="emit('close')">关闭预览</button></template>
  </el-dialog>
</template>

<style scoped>
.preview-toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px}.preview-formats{display:flex;gap:8px}.preview-formats .active{background:#e2f3f3;color:#076b76;border-color:var(--teal)}.preview-print{display:flex;align-items:center;gap:18px}.preview-print a{color:var(--teal);white-space:nowrap}.preview-context{margin:14px 0;color:#58717f;font-size:14px}.preview-placeholder{padding:80px 24px;text-align:center;background:#f4f8fb;min-height:45vh}.export-preview-frame{width:100%;height:68vh;border:1px solid var(--line);background:#e9edef}@media(max-width:600px){.preview-toolbar{align-items:stretch;flex-direction:column}.preview-formats>button{flex:1;padding:10px}.preview-print{justify-content:flex-end}.export-preview-frame{height:60vh}}
</style>
