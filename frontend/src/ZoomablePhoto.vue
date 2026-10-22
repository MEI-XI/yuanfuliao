<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ src: string }>()
const viewport = ref<HTMLElement | null>(null)
const scale = ref(1), offsetX = ref(0), offsetY = ref(0)
type Point = { x: number; y: number }
const pointers = new Map<number, Point>()

function reset() { scale.value = 1; offsetX.value = 0; offsetY.value = 0 }
function clampPosition() {
  const box = viewport.value?.getBoundingClientRect()
  if (!box) return
  const limitX = box.width * (scale.value - 1) / 2
  const limitY = box.height * (scale.value - 1) / 2
  offsetX.value = Math.max(-limitX, Math.min(limitX, offsetX.value))
  offsetY.value = Math.max(-limitY, Math.min(limitY, offsetY.value))
}
function zoom(value: number, from: Point, to: Point = from) {
  const box = viewport.value?.getBoundingClientRect()
  if (!box) return
  const next = Math.max(1, Math.min(6, value))
  const ratio = next / scale.value
  offsetX.value = to.x - box.left - box.width / 2 - (from.x - box.left - box.width / 2 - offsetX.value) * ratio
  offsetY.value = to.y - box.top - box.height / 2 - (from.y - box.top - box.height / 2 - offsetY.value) * ratio
  scale.value = next
  clampPosition()
}
function wheel(event: WheelEvent) {
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 300 : 1)
  zoom(scale.value * Math.exp(-delta * 0.002), { x: event.clientX, y: event.clientY })
}
function down(event: PointerEvent) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  viewport.value?.setPointerCapture(event.pointerId)
}
function pairGeometry(points: Point[]) {
  const [a, b] = points
  if (!a || !b) return null
  return { center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, distance: Math.hypot(a.x - b.x, a.y - b.y) }
}
function move(event: PointerEvent) {
  const previous = pointers.get(event.pointerId)
  if (!previous) return
  const before = pairGeometry([...pointers.values()])
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  const after = pairGeometry([...pointers.values()])
  if (before && after && before.distance > 0) {
    zoom(scale.value * after.distance / before.distance, before.center, after.center)
  } else if (pointers.size === 1) {
    offsetX.value += event.clientX - previous.x
    offsetY.value += event.clientY - previous.y
    clampPosition()
  }
}
function end(event: PointerEvent) { pointers.delete(event.pointerId) }
</script>

<template>
  <div class="zoom-photo">
    <div ref="viewport" role="region" aria-label="原图缩放区域" class="zoom-viewport" :class="{ zoomed: scale > 1 }"
      @wheel.prevent="wheel" @pointerdown.prevent="down" @pointermove.prevent="move"
      @pointerup="end" @pointercancel="end" @lostpointercapture="end">
      <img :src="src" alt="包装图片放大预览" draggable="false" :style="{ transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})` }">
    </div>
    <div class="zoom-tools"><span>{{ Math.round(scale * 100) }}%</span><button type="button" @click="reset">恢复原始比例</button></div>
    <p class="zoom-help">滚轮或双指缩放，放大后拖动查看</p>
  </div>
</template>

<style scoped>
.zoom-photo { min-width: 0; }
.zoom-viewport { height: 55vh; height: 55dvh; overflow: hidden; position: relative; background: #eef3f5; touch-action: none; user-select: none; border-radius: 6px; }
.zoom-viewport img { display: block; width: 100%; height: 100%; object-fit: contain; pointer-events: none; transform-origin: center; }
.zoom-viewport.zoomed { cursor: grab; }
.zoom-viewport.zoomed:active { cursor: grabbing; }
.zoom-tools { display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 10px; font-variant-numeric: tabular-nums; }
.zoom-tools button { padding: 5px 10px; min-height: 32px; font-size: 13px; }
.zoom-help { margin: 8px 0 0; text-align: center; color: #64748b; font-size: 12px; }
</style>
