<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { z } from 'zod'
import { api } from './api'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const defaults = ['出厂检验报告', '检疫证', '肉品品质合格证', '进关检疫证', '报关单']
const history = ref<string[]>([])
const error = ref('')
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
onMounted(load)
</script>

<template>
  <div class="certificate-picker">
    <label>随车证件<input :value="modelValue" aria-label="随车证件" @input="edit"></label>
    <small>可多选，也可直接修改文字；多个证件用顿号分隔。保存记录后，自定义文字会加入历史选项。</small>
    <div class="certificate-choices" role="group" aria-label="常用及历史随车证件">
      <label v-for="name in choices" :key="name" :class="{ selected: selected.includes(name) }"><input type="checkbox" :checked="selected.includes(name)" @change="toggle(name)">{{ name }}</label>
    </div>
    <p v-if="error" role="status">{{ error }} <button type="button" @click="load">重试</button></p>
  </div>
</template>

<style scoped>
.certificate-picker { display: grid; gap: 8px; }
.certificate-choices { display: flex; flex-wrap: wrap; gap: 8px; max-height: 180px; overflow: auto; }
.certificate-choices label { display: flex; align-items: center; gap: 6px; padding: 7px 10px; border: 1px solid #d3e2e1; border-radius: 8px; cursor: pointer; font-weight: 400; }
.certificate-choices label.selected { background: #e5f5f2; border-color: #218577; }
.certificate-choices input { width: 16px; height: 16px; margin: 0; }
</style>
