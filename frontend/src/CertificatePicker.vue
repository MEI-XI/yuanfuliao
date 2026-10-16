<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { z } from 'zod'
import { api } from './api'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const defaults = ['出厂检验报告', '检疫证', '肉品品质合格证', '进关检疫证', '报关单']
const history = ref<string[]>([])
const error = ref('')
const dropdown = ref<HTMLDetailsElement | null>(null)
function close() { if (dropdown.value) dropdown.value.open = false }
function outside(event: PointerEvent) {
  if (event.target instanceof Node && !dropdown.value?.contains(event.target)) close()
}
const selected = computed(() => [...new Set(props.modelValue.split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean))])
const choices = computed(() => [...new Set([...defaults, ...history.value, ...selected.value])])
function toggle(name: string) {
  const values = selected.value.includes(name) ? selected.value.filter(value => value !== name) : [...selected.value, name]
  emit('update:modelValue', values.join('、'))
}
function edit(event: Event) {
  if (event.target instanceof HTMLInputElement) emit('update:modelValue', event.target.value)
}
async function load() {
  try { history.value = await api('/certificate-options', z.array(z.string())); error.value = '' }
  catch { error.value = '历史选项加载失败，仍可手动填写。' }
}
onMounted(() => { void load(); document.addEventListener('pointerdown', outside) })
onUnmounted(() => document.removeEventListener('pointerdown', outside))
</script>

<template>
  <div class="certificate-picker">
    <span>随车证件</span>
    <details ref="dropdown" @keydown.esc.stop.prevent="close">
    <summary>{{ selected.length ? selected.join('、') : '请选择随车证件（可多选）' }}<span aria-hidden="true">▾</span></summary>
    <div class="certificate-menu">
    <label>输入或修改证件<input :value="modelValue" aria-label="随车证件" placeholder="多个证件用顿号分隔" @input="edit"></label>
    <small>勾选下方选项，或直接输入文字；保存记录后可复用。</small>
    <div class="certificate-choices" role="group" aria-label="常用及历史随车证件">
      <label v-for="name in choices" :key="name" :class="{ selected: selected.includes(name) }"><input type="checkbox" :checked="selected.includes(name)" @change="toggle(name)">{{ name }}</label>
    </div>
    <p v-if="error" role="status">{{ error }} <button type="button" @click="load">重试</button></p>
    <button type="button" class="certificate-done" @click="close">完成选择</button>
    </div>
    </details>
  </div>
</template>

<style scoped>
.certificate-picker { display: grid; gap: 8px; }
details { position: relative; min-width: 0; }
summary { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid #b9cfcc; border-radius: 8px; background: white; cursor: pointer; list-style: none; overflow-wrap: anywhere; }
summary::-webkit-details-marker { display: none; }
details[open] summary { border-color: #218577; }
.certificate-menu { position: absolute; z-index: 20; top: calc(100% + 5px); left: 0; right: 0; display: grid; gap: 10px; padding: 12px; background: white; border: 1px solid #b9cfcc; border-radius: 8px; box-shadow: 0 8px 24px #163c3826; }
.certificate-choices { display: grid; gap: 4px; max-height: 190px; overflow: auto; }
.certificate-choices label { display: flex; flex-direction: row; align-items: center; gap: 8px; padding: 8px; border-radius: 6px; cursor: pointer; font-weight: 400; overflow-wrap: anywhere; }
.certificate-choices label.selected { background: #e5f5f2; border-color: #218577; }
.certificate-choices input { flex-shrink: 0; width: 16px; height: 16px; margin: 0; }
.certificate-done { justify-self: end; }
</style>
