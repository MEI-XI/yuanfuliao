<script setup lang="ts">
import { ref, useId } from 'vue'

const props = defineProps<{
  groups: { key: number; images: number[]; fields: { material_name: string } }[]
  activeIndex: number
  selectedImage?: number
  selectedKeys?: number[]
  selectionEnabled?: boolean
  disabled?: boolean
}>()
const emit = defineEmits<{
  select: [index: number]
  merge: [from: number, to: number]
  toggleSelection: [key: number]
  reorder: [from: number, to: number]
  preview: [index: number, imageId: number]
}>()

const list = ref<HTMLElement | null>(null)
const hintId = useId()
type DropTarget = { kind: 'merge'; index: number } | { kind: 'reorder'; index: number; side: 'before' | 'after' }
const dragging = ref<{ key: number; pointerId: number; target: DropTarget | null } | null>(null)
const keyboardMerge = ref<{ key: number; target: number } | null>(null)
const announcement = ref('')

function targetAt(clientX: number, clientY: number): DropTarget | null {
  const bounds = list.value?.getBoundingClientRect()
  if (!bounds || clientX < bounds.left || clientX > bounds.right || clientY < bounds.top || clientY > bounds.bottom) return null
  const rows = Array.from(list.value?.querySelectorAll<HTMLElement>('.group-tab') || [])
  for (const [index, row] of rows.entries()) {
    const rect = row.getBoundingClientRect()
    if (clientY < rect.top + rect.height * .2) return { kind: 'reorder', index, side: 'before' }
    if (clientY <= rect.bottom - rect.height * .2) return { kind: 'merge', index }
    if (clientY <= rect.bottom) return { kind: 'reorder', index, side: 'after' }
  }
  return null
}

function startDrag(event: PointerEvent, key: number) {
  if (props.disabled || !event.isPrimary || event.button !== 0 || !(event.currentTarget instanceof HTMLElement)) return
  event.preventDefault()
  event.currentTarget.focus()
  event.currentTarget.setPointerCapture(event.pointerId)
  keyboardMerge.value = null
  dragging.value = { key, pointerId: event.pointerId, target: null }
}

function moveDrag(event: PointerEvent) {
  if (dragging.value?.pointerId !== event.pointerId) return
  dragging.value.target = targetAt(event.clientX, event.clientY)
  const target = dragging.value.target
  if (target?.kind === 'merge' && props.groups[target.index]?.key !== dragging.value.key) {
    announcement.value = `松开合并到记录 ${target.index + 1}`
  } else if (target?.kind === 'reorder') announcement.value = `松开放到记录 ${target.index + 1} ${target.side === 'before' ? '之前' : '之后'}`
  else announcement.value = '移动到其他分组中心合并，边缘排序；在列表外松开取消'
}

function reorder(from: number, to: number) {
  if (props.disabled || from < 0 || to < 0 || to >= props.groups.length || from === to) return
  emit('reorder', from, to)
  announcement.value = `记录 ${from + 1} 已移到第 ${to + 1} 位`
}

function finishDrag(event: PointerEvent) {
  if (dragging.value?.pointerId !== event.pointerId) return
  const from = props.groups.findIndex(group => group.key === dragging.value?.key)
  const target = targetAt(event.clientX, event.clientY)
  dragging.value = null
  if (!target) return
  if (target.kind === 'merge') requestMerge(from, target.index)
  else {
    const insertion = target.index + (target.side === 'after' ? 1 : 0)
    reorder(from, insertion > from ? insertion - 1 : insertion)
  }
}

function cancelDrag(event: PointerEvent) {
  if (dragging.value?.pointerId === event.pointerId) dragging.value = null
}

function requestMerge(from: number, to: number) {
  if (props.disabled || from < 0 || to < 0 || to >= props.groups.length || from === to) return
  emit('merge', from, to)
  announcement.value = `已请求将记录 ${from + 1} 合并到记录 ${to + 1}`
}

function mergeTarget(index: number) {
  if (keyboardMerge.value) return keyboardMerge.value.target === index
  return dragging.value?.target?.kind === 'merge' && dragging.value.target.index === index && props.groups[index]?.key !== dragging.value.key
}

function dropEdge(index: number, side: 'before' | 'after') {
  return dragging.value?.target?.kind === 'reorder' && dragging.value.target.index === index && dragging.value.target.side === side
}

function handleKey(event: KeyboardEvent, key: number, index: number) {
  if (props.disabled) return
  if (event.key === 'Escape') {
    dragging.value = null
    keyboardMerge.value = null
    announcement.value = '已取消移动或合并'
    event.preventDefault()
    return
  }
  if (event.key.toLowerCase() === 'm' && props.groups.length > 1) {
    event.preventDefault()
    keyboardMerge.value = { key, target: index === props.groups.length - 1 ? index - 1 : index + 1 }
  } else if (keyboardMerge.value?.key === key) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      const target = keyboardMerge.value.target
      keyboardMerge.value = null
      requestMerge(index, target)
      return
    }
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
    event.preventDefault()
    const step = event.key === 'ArrowUp' ? -1 : 1
    let target = keyboardMerge.value.target + step
    if (target === index) target += step
    if (target >= 0 && target < props.groups.length) keyboardMerge.value.target = target
  } else {
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault()
      reorder(index, index + (event.key === 'ArrowUp' ? -1 : 1))
    }
    return
  }
  announcement.value = `合并目标为记录 ${keyboardMerge.value.target + 1}，上下键选择，回车合并，Esc 取消`
}
</script>

<template>
  <section class="batch-groups" aria-label="批量记录排序">
    <div class="groups-heading"><strong>图片分组</strong><span aria-hidden="true">拖到组内合并，边缘排序</span><span :id="hintId" class="sr-only">拖动手柄到分组中心合并，到边缘排序。上下键排序；按 M 选择合并目标，上下键切换目标，回车确认，Esc 取消。</span></div>
    <ol ref="list" class="group-list" aria-label="图片分组">
      <li v-for="(entry, index) in groups" :key="entry.key" class="group-tab"
        :class="{ selected: index === activeIndex, dragging: dragging?.key === entry.key,
          'merge-target': mergeTarget(index), 'drop-before': dropEdge(index, 'before'), 'drop-after': dropEdge(index, 'after') }">
        <div class="group-header">
          <input v-if="selectionEnabled" class="group-checkbox" type="checkbox" :aria-label="`选择分组 ${index + 1}`" :checked="selectedKeys?.includes(entry.key) || false" :disabled="disabled" @click.stop @change="emit('toggleSelection', entry.key)">
          <button class="drag-handle" :disabled="disabled" :aria-label="`拖动记录 ${index + 1} 排序`" :aria-describedby="hintId" title="拖到组内合并，边缘排序；按 M 选择合并目标"
            @pointerdown="startDrag($event, entry.key)" @pointermove="moveDrag" @pointerup="finishDrag"
            @pointercancel="cancelDrag" @lostpointercapture="cancelDrag"
            @keydown="handleKey($event, entry.key, index)" @blur="keyboardMerge = null">
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
        <span v-if="mergeTarget(index)" class="merge-indicator" aria-hidden="true">{{ keyboardMerge ? '回车合并到此组' : '松开合并到此组' }}</span>
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
.group-tab.merge-target { border-color: #087f8c; background: #d4f2eb; box-shadow: 0 0 0 2px #087f8c; }
.merge-indicator { position: absolute; left: 2px; right: 2px; bottom: 2px; padding: 3px 1px; background: #087f8c; color: white; border-radius: 3px; font-size: 11px; text-align: center; pointer-events: none; }
.group-tab.drop-before::before, .group-tab.drop-after::after { content: ''; position: absolute; left: 0; right: 0; height: 3px; background: var(--teal, #087f8c); border-radius: 2px; }
.group-tab.drop-before::before { top: -6px; }
.group-tab.drop-after::after { bottom: -6px; }
.group-header { display: flex; align-items: flex-start; min-width: 0; }
.group-checkbox { flex: 0 0 14px; width: 14px; min-height: 14px; height: 14px; margin: 11px 3px 0 0; padding: 0; }
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
.drag-handle:disabled { cursor: default; opacity: .4; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 600px) {
  .batch-groups { width: 108px; flex-basis: 108px; }
  .groups-heading { gap: 2px; }
  .groups-heading strong { font-size: 12px; }
  .groups-heading > span[aria-hidden] { display: none; }
  .group-tab { padding: 3px; }
  .drag-handle { flex-basis: 18px; width: 18px; min-height: 40px; font-size: 21px; }
  .group-select { min-height: 40px; font-size: 11px; }
  .group-name { font-size: 10px; }
  .group-images { gap: 4px; margin-left: 11px; padding-left: 8px; }
  .group-image { width: 52px; height: 54px; }
}
</style>
