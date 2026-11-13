<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'

GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps<{ url: string }>()
const container = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const pageNumber = ref(1)
const pages = ref(0)
const zoom = ref(100)
const loading = ref(true)
const error = ref('')
let document: PDFDocumentProxy | undefined
let loadingTask: ReturnType<typeof getDocument> | undefined
let renderTask: RenderTask | undefined
let observer: ResizeObserver | undefined
let disposed = false
let generation = 0
let queue = Promise.resolve()
let width = 0

function draw() {
  const ticket = ++generation
  renderTask?.cancel()
  loading.value = true
  error.value = ''
  queue = queue.catch(() => {}).then(async () => {
    if (disposed || ticket !== generation || !document || !canvas.value || !container.value) return
    try {
      const page = await document.getPage(pageNumber.value)
      if (disposed || ticket !== generation) return
      const original = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: Math.max(1, container.value.clientWidth - 16) / original.width * zoom.value / 100 })
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      const target = canvas.value
      target.width = Math.ceil(viewport.width * ratio)
      target.height = Math.ceil(viewport.height * ratio)
      target.style.width = `${viewport.width}px`
      target.style.height = `${viewport.height}px`
      renderTask = page.render({ canvas: target, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
      await renderTask.promise
    } catch (cause) {
      if (!disposed && ticket === generation) error.value = 'PDF 页面显示失败，请重新打开预览或下载查看。'
    } finally {
      if (!disposed && ticket === generation) loading.value = false
    }
  })
}
watch([pageNumber, zoom], draw)
onMounted(async () => {
  try {
    loadingTask = getDocument({ url: props.url, cMapUrl: '/pdfjs/cmaps/', cMapPacked: true,
      standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/' })
    document = await loadingTask.promise
    if (disposed) return
    pages.value = document.numPages
    observer = new ResizeObserver(() => {
      const next = container.value?.clientWidth || 0
      if (next && next !== width) { width = next; draw() }
    })
    observer.observe(container.value!)
    draw()
  } catch {
    if (!disposed) { error.value = '无法预览此 PDF，可能已损坏或设置了密码，请下载后检查。'; loading.value = false }
  }
})
onBeforeUnmount(() => {
  disposed = true
  generation++
  observer?.disconnect()
  renderTask?.cancel()
  void loadingTask?.destroy()
})
</script>

<template>
  <div class="pdf-reader">
    <div class="pdf-toolbar" aria-label="PDF 阅读工具">
      <div><button type="button" :disabled="loading || pageNumber <= 1" @click="pageNumber--">上一页</button><span>第 {{ pageNumber }} / {{ pages }} 页</span><button type="button" :disabled="loading || pageNumber >= pages" @click="pageNumber++">下一页</button></div>
      <div><button type="button" aria-label="缩小" :disabled="loading || zoom <= 75" @click="zoom -= 25">−</button><span>{{ zoom }}%</span><button type="button" aria-label="放大" :disabled="loading || zoom >= 200" @click="zoom += 25">＋</button></div>
    </div>
    <p v-if="loading" role="status">正在显示 PDF 页面…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div ref="container" class="pdf-pages" :aria-busy="loading">
      <canvas ref="canvas" v-show="!loading && !error" role="img" :aria-label="`PDF 第 ${pageNumber} 页`" />
    </div>
  </div>
</template>

<style scoped>
.pdf-toolbar{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;margin-bottom:10px}.pdf-toolbar>div{display:flex;align-items:center;gap:8px}.pdf-toolbar button{padding:6px 10px}.pdf-toolbar span{white-space:nowrap;font-size:13px}.pdf-pages{max-height:65vh;min-height:100px;overflow:auto;padding:8px;background:#edf2f4;overscroll-behavior:contain}.pdf-pages canvas{display:block;margin:auto;background:white}.pdf-reader{min-width:0}
</style>
