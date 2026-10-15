<script setup lang="ts">
import { onMounted, ref, shallowRef } from 'vue'
import { chooseTemplateDirectory, downloadDefaultTemplate, importTemplateDirectory, selectedTemplateSource, supportsLocalTemplates, useServerTemplates, type TemplateSource } from './localTemplates'

const props = withDefaults(defineProps<{ userId: number; returnLabel?: string }>(), { returnLabel: '返回公司台账' })
const emit = defineEmits<{ close: [] }>()
const directory = shallowRef<FileSystemDirectoryHandle | null>(null)
const source = shallowRef<TemplateSource>({ kind: 'server' })
const folderInput = ref<HTMLInputElement | null>(null)
const busy = ref(true)
const error = ref('')
const supported = supportsLocalTemplates()

async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await work() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法访问个人模板目录，请重新选择目录。' }
  finally { busy.value = false }
}

async function refresh() {
  source.value = await selectedTemplateSource(props.userId)
  directory.value = source.value.kind === 'directory' ? source.value.handle : null
}
onMounted(() => action(refresh))
function choose() {
  if (!supported) { folderInput.value?.click(); return }
  return action(async () => { await chooseTemplateDirectory(props.userId, directory.value); await refresh() })
}
function importFolder(event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement) || !input.files?.length) return
  const files = Array.from(input.files)
  input.value = ''
  return action(async () => { await importTemplateDirectory(props.userId, files); await refresh() })
}
function reset() {
  return action(async () => { await useServerTemplates(props.userId); await refresh() })
}
</script>

<template>
  <main class="page">
    <div class="page-heading"><div><h1>我的模板</h1><p class="muted">本账号在当前浏览器使用的个人模板</p></div><button :disabled="busy" @click="emit('close')">{{ props.returnLabel }}</button></div>
    <section class="admin-card">
      <h2>本机模板目录</h2>
      <p>在自己的电脑上选择一个项目目录之外的专用文件夹。</p>
      <p v-if="supported">直接选择目录会补齐缺少的模板，已有文件会保留；导出时重新读取文件。</p>
      <p role="status">{{ busy ? '正在读取模板设置…' : source.kind === 'directory' ? `已选择文件夹：${source.handle.name}` : source.kind === 'snapshot' ? `已导入文件夹副本：${source.name}` : '当前使用服务器默认模板' }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="button-row">
        <button class="primary" :disabled="busy" @click="choose">选择 / 更换模板目录</button>
        <button v-if="supported" :disabled="busy || !directory" @click="choose">打开模板目录选择器</button>
        <button v-if="supported" :disabled="busy" @click="folderInput?.click()">导入模板文件夹副本</button>
        <button :disabled="busy" @click="reset">使用服务器默认模板</button>
      </div>
      <input ref="folderInput" type="file" webkitdirectory multiple hidden :disabled="busy" aria-label="导入模板文件夹" @change="importFolder">
      <p v-if="!supported || source.kind === 'snapshot'" class="muted">当前使用文件夹副本模式：只读取本次选择的文件并保存到当前浏览器，无法自动读取后续修改，也不能向文件夹补齐模板。用 Word、Excel 或 WPS 修改并保存后，请重新选择文件夹刷新副本。</p>
      <div class="button-row">
        <button :disabled="busy" @click="action(() => downloadDefaultTemplate('xlsx'))">下载默认 Excel 模板</button>
        <button :disabled="busy" @click="action(() => downloadDefaultTemplate('docx'))">下载默认 Word 模板</button>
      </div>
      <p class="muted">可将下载的默认模板保存到自己的模板文件夹，再选择该文件夹。</p>
      <ul><li>查验台账.xlsx：用于 Excel 导出</li><li>检验报告.docx：用于 Word 导出</li></ul>
      <ul v-if="source.kind === 'snapshot'">
        <li>查验台账.xlsx：{{ source.importedKinds.includes('xlsx') ? '已保存副本' : '未找到同名文件，使用服务器默认模板' }}</li>
        <li>检验报告.docx：{{ source.importedKinds.includes('docx') ? '已保存副本' : '未找到同名文件，使用服务器默认模板' }}</li>
      </ul>
      <p>未修改或缺少对应文件时，使用服务器最新默认模板。每次重新导入都会替换之前的副本，缺少的文件不会沿用旧副本。</p>
      <p class="muted">修改过的模板仅在本次导出时临时发送到服务器，服务器不保存个人模板。此设置仅保存在当前浏览器，按登录账号区分。</p>
      <p v-if="supported" class="muted">“打开模板目录选择器”会从已选文件夹开始，仍由浏览器显示系统选择窗口。网页只能显示文件夹名称，无法获取完整路径。</p>
    </section>
  </main>
</template>
