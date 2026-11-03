<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const textarea = ref<HTMLTextAreaElement | null>(null)
let observer: ResizeObserver | undefined
let previousWidth = -1

function resize() {
  const element = textarea.value
  if (!element || !element.clientWidth) return
  element.style.height = 'auto'
  const style = getComputedStyle(element)
  element.style.height = `${element.scrollHeight + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth)}px`
}

function edit(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
  resize()
}

watch(() => props.modelValue, resize, { flush: 'post' })
onMounted(() => {
  resize()
  observer = new ResizeObserver(entries => {
    const width = entries[0]?.contentRect.width
    if (width !== undefined && width !== previousWidth) {
      previousWidth = width
      resize()
    }
  })
  if (textarea.value) observer.observe(textarea.value)
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <textarea ref="textarea" :value="modelValue" rows="1" class="auto-grow-textarea" @input="edit" />
</template>

<style scoped>
.auto-grow-textarea { display: block; min-width: 0; min-height: 44px; resize: none; overflow: hidden; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
