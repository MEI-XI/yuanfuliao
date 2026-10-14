<script setup lang="ts">
import { ref, useId } from 'vue'

const props = defineProps<{
  groups: { key: number; images: number[]; fields: { material_name: string } }[]
  activeIndex: number
  selectedImage?: number
  disabled?: boolean
}>()
const emit = defineEmits<{
  select: [index: number]
  merge: [index: number]
  reorder: [from: number, to: number]
  preview: [index: number, imageId: number]
}>()

const list = ref<HTMLElement | null>(null)
const hintId = useId()
const dragging = ref<{ key: number; pointerId: number; target: number } | null>(null)
const announcement = ref('')

function targetAt(clientY: number) {
  const rows = Array.from(list.value?.querySelectorAll<HTMLElement>('.group-tab') || [])
  let target = 0
  let distance = Infinity
  rows.forEach((row, index) => {
    const rect = row.getBoundingClientRect()
    const nextDistance = Math.abs(clientY - (rect.top + rect.height / 2))
    if (nextDistance < distance) { target = index; distance = nextDistance }
  })
  return target
}

function startDrag(event: PointerEvent, key: number, index: number) {
  if (props.disabled || !event.isPrimary || event.button !== 0 || !(event.currentTarget instanceof HTMLElement)) return
  event.preventDefault()
  event.currentTarget.focus()
  event.currentTarget.setPointerCapture(event.pointerId)
  dragging.value = { key, pointerId: event.pointerId, target: index }
}

function moveDrag(event: PointerEvent) {
  if (dragging.value?.pointerId !== event.pointerId) return
  dragging.value.target = targetAt(event.clientY)
}

function reorder(from: number, to: number) {
  if (props.disabled || from < 0 || to < 0 || to >= props.groups.length || from === to) return
  emit('reorder', from, to)
  announcement.value = `记录 ${from + 1} 已移到第 ${to + 1} 位`
}

function finishDrag(event: PointerEvent) {
  if (dragging.value?.pointerId !== event.pointerId) return
  const from = props.groups.findIndex(group => group.key === dragging.value?.key)
  const to = targetAt(event.clientY)
  dragging.value = null
  reorder(from, to)
}

function cancelDrag(event: PointerEvent) {
  if (dragging.value?.pointerId === event.pointerId) dragging.value = null
}
</script>

<template>
  <section class="batch-groups" aria-label="批量记录排序">
    <div class="groups-heading"><strong>图片分组</strong><span aria-hidden="true">拖动排序</span><span :id="hintId" class="sr-only">拖动手柄调整顺序，也可使用上下方向键</span></div>
    <ol ref="list" class="group-list" aria-label="图片分组">
      <li v-for="(entry, index) in groups" :key="entry.key" class="group-tab"
        :class="{ selected: index === activeIndex, dragging: dragging?.key === entry.key,
          'drop-before': dragging && dragging.target === index && index < groups.findIndex(group => group.key === dragging?.key),
          'drop-after': dragging && dragging.target === index && index > groups.findIndex(group => group.key === dragging?.key) }">
        <div class="group-header">
          <button class="drag-handle" :disabled="disabled" :aria-label="`拖动记录 ${index + 1} 排序`" :aria-describedby="hintId"
            @pointerdown="startDrag($event, entry.key, index)" @pointermove="moveDrag" @pointerup="finishDrag"
            @pointercancel="cancelDrag" @lostpointercapture="cancelDrag"
            @keydown.up.prevent="reorder(index, index - 1)" @keydown.down.prevent="reorder(index, index + 1)">
            <span aria-hidden="true">⠿</span>
          </button>
          <div class="group-details">
            <button class="group-select" :class="{ active: index === activeIndex }" :aria-pressed="index === activeIndex" @click="emit('select', index)">记录 {{ index + 1 }} · {{ entry.images.length }} 张</button>
            <span v-if="entry.fields.material_name" class="group-name">{{ entry.fields.material_name }}</span>
          </div>
        </div>
        <div class="group-images" :aria-label="`记录 ${index + 1} 的图片`">
          <button v-for="(photo, photoIndex) in entry.images" :key="photo" class="group-image"
            :class="{ active: index === activeIndex && selectedImage === photo }"
            :aria-label="`预览记录 ${index + 1} 的图片 ${photoIndex + 1}`"
            :aria-pressed="index === activeIndex && selectedImage === photo" @click="emit('preview', index, photo)">
            <img :src="`/api/images/${photo}`" alt="" draggable="false">
            <span>{{ photoIndex + 1 }}</span>
          </button>
        </div>
        <button v-if="index > 0" class="text-button merge-button" :disabled="disabled" @click="emit('merge', index)">合并到上一组</button>
      </li>
    </ol>
    <span class="sr-only" role="status" aria-live="polite">{{ announcement }}</span>
  </section>
</template>

<style scoped>
.batch-groups { width: 180px; min-width: 0; flex: 0 0 180px; align-self: stretch; }
.groups-heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 8px; margin-bottom: 8px; }
.groups-heading strong { font-size: 14px; color: #355966; }
.groups-heading span { font-size: 11px; color: #748591; }
.group-list { display: flex; flex-direction: column; gap: 8px; list-style: none; margin: 0; padding: 0; }
.group-tab { display: block; min-width: 0; padding: 5px; position: relative; white-space: normal; background: white; border: 1px solid var(--line, #dce5e9); border-radius: 6px; transition: background .12s; }
.group-tab.selected { border-color: var(--teal, #087f8c); background: #f2fafa; }
.group-tab.dragging { opacity: .55; }
.group-tab.drop-before::before, .group-tab.drop-after::after { content: ''; position: absolute; left: 0; right: 0; height: 3px; background: var(--teal, #087f8c); border-radius: 2px; }
.group-tab.drop-before::before { top: -6px; }
.group-tab.drop-after::after { bottom: -6px; }
.group-header { display: flex; align-items: flex-start; min-width: 0; }
.drag-handle { flex: 0 0 28px; width: 28px; min-height: 36px; padding: 0; border-color: transparent; background: transparent; color: #567f8a; cursor: grab; touch-action: none; user-select: none; font-size: 22px; }
.dragging .drag-handle { cursor: grabbing; }
.group-details { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
.group-select { width: 100%; min-height: 36px; padding: 4px 0; border: 0; text-align: left; background: transparent; color: #355966; font-size: 12px; font-weight: 600; line-height: 1.4; }
.group-select.active { color: var(--teal, #087f8c); background: transparent; }
.group-name { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: #647b85; }
.group-images { display: flex; flex-wrap: wrap; gap: 5px; margin: 5px 0 3px 13px; padding: 3px 0 3px 12px; border-left: 1px solid #cbdce0; }
.group-image { width: 52px; height: 58px; padding: 2px; position: relative; border: 1px solid #dce5e9; border-radius: 4px; background: #fff; overflow: hidden; }
.group-image.active { border-color: var(--teal, #087f8c); box-shadow: 0 0 0 1px var(--teal, #087f8c); }
.group-image img { width: 100%; height: 100%; object-fit: contain; display: block; }
.group-image span { position: absolute; right: 1px; bottom: 1px; min-width: 14px; padding: 1px 3px; border-radius: 3px 0 2px 0; background: #edf4f5; color: #496974; font-size: 10px; }
.merge-button { margin-left: 26px; padding: 4px 0; font-size: 11px; }
.drag-handle:disabled { cursor: default; opacity: .4; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 600px) {
  .batch-groups { width: 108px; flex-basis: 108px; }
  .groups-heading { gap: 2px; }
  .groups-heading strong { font-size: 12px; }
  .groups-heading > span[aria-hidden] { display: none; }
  .group-tab { padding: 3px; }
  .drag-handle { flex-basis: 24px; width: 24px; min-height: 40px; font-size: 21px; }
  .group-select { min-height: 40px; font-size: 11px; }
  .group-name { font-size: 10px; }
  .group-images { gap: 4px; margin-left: 11px; padding-left: 8px; }
  .group-image { width: 52px; height: 54px; }
  .merge-button { margin-left: 0; width: 100%; font-size: 10px; padding: 5px 0; }
}
</style>
