<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { z } from 'zod'
import { api } from './api'

const props = defineProps<{ modelValue: string; kind: 'result' | 'conclusion' }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const label = computed(() => props.kind === 'result' ? '检验结果' : '判定结论')
const defaults = computed(() => props.kind === 'result' ? ['符合', '不符合'] : ['合格', '不合格'])
const history = ref<string[]>([])
const typed = ref('')
const choices = computed(() => [...new Set([...defaults.value, ...history.value, ...(typed.value ? [typed.value] : [])])])
const open = ref(false)
const error = ref('')
const root = ref<HTMLElement | null>(null)
let requests = Promise.resolve()
function request(method = 'GET', name = '') {
  requests = requests.then(async () => {
    try {
      history.value = await api(`/inspection-options/${props.kind}${name ? '?name=' + encodeURIComponent(name) : ''}`, z.array(z.string()), { method })
      error.value = ''
    } catch { error.value = '历史选项更新失败，仍可填写并保存记录；重新展开可重试加载。' }
  })
  return requests
}
function outside(event: PointerEvent) { if (event.target instanceof Node && !root.value?.contains(event.target)) open.value = false }
function edit(event: Event) {
  if (!(event.target instanceof HTMLInputElement)) return
  emit('update:modelValue', event.target.value)
  typed.value = event.target.value.trim()
  open.value = true
}
function remember() {
  if (typed.value && !defaults.value.includes(typed.value)) void request('POST', typed.value)
  typed.value = ''
}
function choose(value: string) { remember(); emit('update:modelValue', value); open.value = false }
async function remove(value: string) {
  await request('DELETE', value)
  if (!error.value && typed.value === value) typed.value = ''
}
function focusOut(event: FocusEvent) {
  if (!(event.relatedTarget instanceof Node) || !root.value?.contains(event.relatedTarget)) open.value = false
}
onMounted(() => { void request(); document.addEventListener('pointerdown', outside) })
onUnmounted(() => document.removeEventListener('pointerdown', outside))
</script>

<template>
  <div ref="root" class="inspection-choice" @keydown.esc.stop.prevent="open = false" @focusout="focusOut">
    <label>{{ label }}
      <span class="choice-input">
      <input :value="modelValue" :aria-label="label" role="combobox" :aria-expanded="open" aria-autocomplete="none" placeholder="选择或输入"
        @focus="open = true; request()" @click="open = true" @input="edit" @blur="remember" @keydown.down.prevent="open = true">
      <span class="choice-arrow" aria-hidden="true">▾</span>
      </span>
    </label>
    <div v-if="open" class="choice-menu">
      <div role="listbox" :aria-label="label + '选项'">
        <div v-for="value in choices" :key="value" class="choice-row">
          <button type="button" role="option" :aria-selected="modelValue === value" @pointerdown.prevent @click="choose(value)">{{ value }}</button>
          <button v-if="!defaults.includes(value)" type="button" class="remove-choice" :aria-label="`删除${label}历史选项：${value}`" title="仅删除历史选项，保留已填内容" @pointerdown.prevent @click="remove(value)">×</button>
        </div>
      </div>
      <small>单选；输入新内容后自动记住</small>
    </div>
    <small v-if="error" role="status">{{ error }}</small>
  </div>
</template>

<style scoped>
.inspection-choice { position: relative; min-width: 0; }
.choice-input { position: relative; display: block; }
.choice-input input { padding-right: 24px; }
.choice-arrow { position: absolute; right: 9px; top: 50%; transform: translateY(-50%); pointer-events: none; color: #687f8a; }
.choice-menu { position: absolute; z-index: 22; top: 100%; left: 0; min-width: 100%; width: max-content; max-width: min(280px, 70vw); padding: 6px; background: white; border: 1px solid #b9cfcc; border-radius: 6px; box-shadow: 0 8px 24px #163c3826; }
[role=listbox] { max-height: 200px; overflow: auto; }
.choice-row { display: flex; align-items: center; }
.choice-row button { border: 0; text-align: left; overflow-wrap: anywhere; }
[role=option] { flex: 1; min-width: 0; }
[aria-selected=true] { background: #e5f5f2; color: #087f8c; }
.remove-choice { flex-shrink: 0; width: 32px; padding: 4px; text-align: center !important; color: #6b7e7b; font-size: 20px; }
.remove-choice:hover { color: #b33a3a; background: #fff0f0; }
small { display: block; color: #687f8a; font-size: 12px; padding: 6px; }
</style>
