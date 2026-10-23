<script setup lang="ts">
import { computed, ref } from 'vue'
const props = defineProps<{ label: string; placeholder: string; emptyLabel: string; value: string | number; options: { value: string | number; label: string; search?: string }[] }>()
const emit = defineEmits<{ change: [event: Event]; 'update:value': [value: string] }>()
const query = ref('')
const matches = computed(() => {
  const words = query.value.normalize('NFKC').trim().toLocaleLowerCase().split(/\s+/)
  return props.options.filter(option => words.every(word => `${option.label} ${option.search || ''}`.normalize('NFKC').toLocaleLowerCase().includes(word)))
})
const selectedOutside = computed(() => props.options.find(option => String(option.value) === String(props.value) && !matches.value.includes(option)))
function choose(event: Event) {
  if (!(event.target instanceof HTMLSelectElement)) return
  emit('update:value', event.target.value)
  emit('change', event)
}
</script>

<template>
  <div class="searchable-library">
    <label class="library-search">搜索{{ label }}<input v-model="query" type="search" :placeholder="placeholder" @input.stop @change.stop></label>
    <label>{{ label }}<select :value="value" :aria-label="label" @change="choose">
      <option value="">{{ emptyLabel }}</option>
      <option v-if="selectedOutside" :value="selectedOutside.value" hidden>{{ selectedOutside.label }}</option>
      <option v-for="option in matches" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select></label>
    <small v-if="!matches.length" role="status">没有匹配结果，请修改搜索词。</small>
  </div>
</template>

<style scoped>
.searchable-library{display:grid;gap:10px;min-width:0;width:100%}.library-search{font-size:13px;color:#647b86}.searchable-library select{min-width:0;max-width:100%;text-overflow:ellipsis}.searchable-library small{color:#647b86;font-size:12px}
</style>
