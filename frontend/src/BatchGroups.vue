<script setup lang="ts">
import { ref, useId } from 'vue'

const props = defineProps<{
  groups: { key: number; images: number[]; fields: { material_name: string } }[]
  activeIndex: number
}>()
const emit = defineEmits<{
  select: [index: number]
  merge: [index: number]
  reorder: [from: number, to: number]
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
  if (!event.isPrimary || event.button !== 0 || !(event.currentTarget instanceof HTMLElement)) return
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
  if (from < 0 || to < 0 || to >= props.groups.length || from === to) return
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
    <div class="groups-heading"><strong>图片分组</strong><span :id="hintId">拖动手柄调整顺序，也可使用上下方向键</span></div>
    <ol ref="list" class="group-list" aria-label="图片分组">
      <li v-for="(entry, index) in groups" :key="entry.key" class="group-tab"
        :class="{ selected: index === activeIndex, dragging: dragging?.key === entry.key,
          'drop-before': dragging && dragging.target === index && index < groups.findIndex(group => group.key === dragging?.key),
          'drop-after': dragging && dragging.target === index && index > groups.findIndex(group => group.key === dragging?.key) }">
        <button class="drag-handle" :aria-label="`拖动记录 ${index + 1} 排序`" :aria-describedby="hintId"
          @pointerdown="startDrag($event, entry.key, index)" @pointermove="moveDrag" @pointerup="finishDrag"
          @pointercancel="cancelDrag" @lostpointercapture="cancelDrag"
          @keydown.up.prevent="reorder(index, index - 1)" @keydown.down.prevent="reorder(index, index + 1)">
          <span aria-hidden="true">⠿</span>
        </button>
        <div class="group-details">
          <button class="group-select" :class="{ active: index === activeIndex }" :aria-pressed="index === activeIndex" @click="emit('select', index)">记录 {{ index + 1 }} · {{ entry.images.length }} 张</button>
          <span v-if="entry.fields.material_name" class="group-name">{{ entry.fields.material_name }}</span>
        </div>
        <button v-if="index > 0" class="text-button merge-button" @click="emit('merge', index)">合并到上一组</button>
      </li>
    </ol>
    <span class="sr-only" role="status" aria-live="polite">{{ announcement }}</span>
  </section>
</template>

<style scoped>
.batch-groups { margin: 18px 0; }
.groups-heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 10px; }
.groups-heading strong { font-size: 14px; color: #355966; }
.groups-heading span { font-size: 12px; color: #748591; }
.group-list { display: flex; flex-direction: column; gap: 8px; list-style: none; margin: 0; padding: 0; }
.group-tab { display: flex; flex-direction: row; align-items: center; gap: 10px; min-width: 0; padding: 6px 12px 6px 6px; position: relative; white-space: normal; background: white; border: 1px solid var(--line, #dce5e9); border-radius: 6px; transition: background .12s; }
.group-tab.selected { border-color: var(--teal, #087f8c); background: #f2fafa; }
.group-tab.dragging { opacity: .55; }
.group-tab.drop-before::before, .group-tab.drop-after::after { content: ''; position: absolute; left: 0; right: 0; height: 3px; background: var(--teal, #087f8c); border-radius: 2px; }
.group-tab.drop-before::before { top: -6px; }
.group-tab.drop-after::after { bottom: -6px; }
.drag-handle { flex: 0 0 44px; width: 44px; min-height: 44px; padding: 0; border-color: transparent; background: transparent; color: #567f8a; cursor: grab; touch-action: none; user-select: none; font-size: 26px; }
.dragging .drag-handle { cursor: grabbing; }
.group-details { flex: 1; min-width: 0; display: flex; align-items: center; flex-wrap: wrap; gap: 6px 14px; }
.group-select { flex-shrink: 0; }
.group-name { overflow-wrap: anywhere; font-size: 14px; color: #355966; }
.merge-button { flex-shrink: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 600px) {
  .group-tab { gap: 4px; padding-right: 8px; }
  .group-details { flex-direction: column; align-items: flex-start; gap: 4px; }
  .group-select { padding: 8px; font-size: 13px; }
  .group-name { padding-left: 8px; font-size: 12px; }
  .merge-button { padding: 6px; font-size: 12px; }
}
</style>
