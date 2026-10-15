<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { downloadDefaultTemplate, importTemplateFile, selectedTemplateSources, templateFormats, templateNames, useServerTemplate, type TemplateKind, type TemplateSources } from './localTemplates'

const props = withDefaults(defineProps<{ userId: number; returnLabel?: string }>(), { returnLabel: '返回公司台账' })
const emit = defineEmits<{ close: [] }>()
const sources = ref<TemplateSources>({ xlsx: { source: 'server' }, docx: { source: 'server' } })
const rows: { kind: TemplateKind; label: string; title: string }[] = [
  { kind: 'xlsx', label: 'Excel', title: 'Excel 查验台账模板' },
  { kind: 'docx', label: 'Word', title: 'Word 检验报告模板' },
]
const displayedRows = computed(() => rows.map(row => ({ ...row, source: sources.value[row.kind] })))
const busy = ref(true)
const error = ref('')
async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await work() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '模板未能保存，请重新选择文件。' }
  finally { busy.value = false }
}
async function refresh() { sources.value = await selectedTemplateSources(props.userId) }
onMounted(() => action(refresh))
function importFile(kind: TemplateKind, event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) return
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  return action(async () => { await importTemplateFile(props.userId, kind, file); await refresh() })
}
function reset(kind: TemplateKind) {
  return action(async () => { await useServerTemplate(props.userId, kind); await refresh() })
}
function selectedTime(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '从之前的设置保留'
}
</script>

<template>
  <main class="page">
    <div class="page-heading"><div><h1>我的模板</h1><p class="muted">分别选择 Excel 和 Word 文件，文件名可以自定。</p></div><button :disabled="busy" @click="emit('close')">{{ props.returnLabel }}</button></div>
    <section class="admin-card template-settings" aria-label="个人导出模板">
      <p>导出 Excel 使用查验台账模板；导出 Word 使用检验报告模板。</p>
      <p v-if="busy" class="muted" aria-live="polite">正在处理模板…</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <section v-for="row in displayedRows" :key="row.kind" class="template-row" :aria-label="row.title">
        <div class="template-details">
          <h2>{{ row.title }}</h2>
          <div role="status" class="template-source">
            <template v-if="row.source.source === 'personal'">
              <span class="source-badge personal">个人模板</span>
              <strong>{{ row.source.name }}</strong>
              <span class="muted">选择时间：{{ selectedTime(row.source.selectedAt) }}</span>
            </template>
            <template v-else-if="row.source.source === 'legacy'">
              <span class="source-badge">原个人模板待更新</span><span>{{ row.source.message }}</span>
            </template>
            <template v-else><span class="source-badge">服务器默认模板</span><strong>{{ templateNames[row.kind] }}</strong></template>
          </div>
        </div>
        <div class="template-controls">
          <label class="template-file-button" :class="{ disabled: busy }">
            {{ row.source.source === 'server' ? '选择' : '更换' }} {{ row.label }} 模板文件
            <input type="file" :accept="templateFormats[row.kind].join(',')" :disabled="busy" :aria-label="`选择 ${row.label} 模板文件`" @change="importFile(row.kind, $event)">
          </label>
          <button :disabled="busy || row.source.source === 'server'" @click="reset(row.kind)">恢复默认 {{ row.label }} 模板</button>
          <button :disabled="busy" @click="action(() => downloadDefaultTemplate(row.kind))">下载默认 {{ row.label }} 模板</button>
        </div>
        <p class="muted formats">支持 {{ templateFormats[row.kind].join('、') }}；每个文件不超过 10 MiB。导出统一为 .{{ row.kind }}。</p>
        <p v-if="row.kind === 'xlsx'" class="muted formats">Excel 模板需保留默认模板的 13 列标题与顺序。</p>
      </section>
      <div class="template-help">
        <p>个人模板保存在当前浏览器，按登录账号分别保存。用 Word、Excel 或 WPS 修改本地文件后，请重新选择该文件。</p>
        <p class="muted">可以先下载默认模板，在其基础上修改。选择文件时会发送到服务器进行格式转换和模板结构检查；个人模板不会保存在服务器，导出时会临时发送。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.template-settings{max-width:1080px}.template-row{padding:24px 0;border-top:1px solid var(--line)}.template-details h2{margin:0 0 12px}.template-source{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-height:30px}.template-source strong{overflow-wrap:anywhere}.source-badge{background:#edf2f5;color:#405767;padding:4px 9px;border-radius:4px;font-size:13px;white-space:nowrap}.source-badge.personal{background:#e4f4ef;color:#186c55}.template-controls{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 12px}.template-file-button{position:relative;display:inline-flex;justify-content:center;align-items:center;background:var(--teal);color:white;border-radius:6px;padding:10px 16px;min-height:42px;font-size:16px;cursor:pointer;overflow:hidden}.template-file-button:hover{background:#076b76}.template-file-button:focus-within{outline:3px solid #087f8c66;outline-offset:2px}.template-file-button.disabled{opacity:.5;cursor:default}.template-file-button input{position:absolute;inset:0;opacity:0;cursor:inherit;width:100%;height:100%}.formats{margin:0;font-size:13px;overflow-wrap:anywhere}.template-help{border-top:1px solid var(--line);padding-top:20px}.template-help p{margin-bottom:8px}@media(max-width:600px){.template-controls{flex-direction:column;align-items:stretch}.template-source{align-items:start}.template-source .muted{width:100%}}
</style>
