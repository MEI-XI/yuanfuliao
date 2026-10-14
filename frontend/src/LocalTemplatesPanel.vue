<script setup lang="ts">
import { onMounted, ref, shallowRef } from 'vue'
import { chooseTemplateDirectory, selectedTemplateDirectory, supportsLocalTemplates, useServerTemplates } from './localTemplates'

const props = withDefaults(defineProps<{ userId: number; returnLabel?: string }>(), { returnLabel: '返回公司台账' })
const emit = defineEmits<{ close: [] }>()
const directory = shallowRef<FileSystemDirectoryHandle | null>(null)
const busy = ref(true)
const error = ref('')
const supported = supportsLocalTemplates()

async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await work() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法访问个人模板目录，请重新选择目录。' }
  finally { busy.value = false }
}

onMounted(() => action(async () => { directory.value = await selectedTemplateDirectory(props.userId) }))
function choose() {
  return action(async () => { directory.value = await chooseTemplateDirectory(props.userId, directory.value) })
}
function reset() {
  return action(async () => { await useServerTemplates(props.userId); directory.value = null })
}
</script>

<template>
  <main class="page">
    <div class="page-heading"><div><h1>我的模板</h1><p class="muted">本账号在当前浏览器使用的个人模板</p></div><button :disabled="busy" @click="emit('close')">{{ props.returnLabel }}</button></div>
    <section class="admin-card">
      <h2>本机模板目录</h2>
      <p>在自己的电脑上选择一个项目目录之外的专用文件夹。首次选择时会补齐缺少的模板，已有文件会保留。</p>
      <p role="status">{{ busy ? '正在读取模板设置…' : directory ? `已选择文件夹：${directory.name}` : '当前使用服务器默认模板' }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="button-row">
        <button class="primary" :disabled="busy || !supported" @click="choose">选择 / 更换模板目录</button>
        <button :disabled="busy || !supported || !directory" @click="choose">打开模板目录选择器</button>
        <button :disabled="busy" @click="reset">使用服务器默认模板</button>
      </div>
      <p v-if="!supported" class="muted">当前浏览器无法选择本机目录。请使用桌面版 Chrome 或 Edge，并通过 HTTPS 或 localhost 访问；本设备可继续使用服务器默认模板。</p>
      <ul><li>查验台账.xlsx：用于 Excel 导出</li><li>检验报告.docx：用于 Word 导出</li></ul>
      <p>用 Word、Excel 或 WPS 打开文件进行修改并保存。每次导出都会重新读取文件；未修改或缺少对应文件时，使用服务器最新默认模板。</p>
      <p class="muted">修改过的模板仅在本次导出时临时发送到服务器，服务器不保存个人模板。此设置仅保存在当前浏览器，按登录账号区分。</p>
      <p class="muted">“打开模板目录选择器”会从已选文件夹开始，仍由浏览器显示系统选择窗口。网页只能显示文件夹名称，无法获取完整路径。</p>
    </section>
  </main>
</template>
