<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElSelect, ElOption } from 'element-plus'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
const props = defineProps<{ label: string; placeholder: string; emptyLabel: string; value: string | number; disabled?: boolean; options: { value: string | number; label: string; search?: string }[] }>()
const emit = defineEmits<{ change: [value: string]; 'update:value': [value: string] }>()
const query = ref('')
const matches = computed(() => {
  const words = query.value.normalize('NFKC').trim().toLocaleLowerCase().split(/\s+/)
  return props.options.filter(option => words.every(word => `${option.label} ${option.search || ''}`.normalize('NFKC').toLocaleLowerCase().includes(word)))
})
function choose(value: string) { emit('update:value', value); emit('change', value) }
</script>

<template>
  <div class="searchable-library" @input.stop @change.stop>
    <span class="library-label">{{ label }}</span>
    <ElSelect :model-value="String(value)" :aria-label="label" :disabled="disabled" filterable fit-input-width popper-class="library-select-dropdown"
      :title="options.find(option => String(option.value) === String(value))?.label || emptyLabel"
      :placeholder="placeholder" :filter-method="(value: string) => query = value"
      no-match-text="没有匹配结果，请修改搜索词。" @change="choose" @visible-change="(open: boolean) => { if (!open) query = '' }">
      <ElOption v-if="!query.trim()" value="" :label="emptyLabel" :title="emptyLabel" />
      <ElOption v-for="option in matches" :key="option.value" :value="String(option.value)" :label="option.label" :title="option.label" />
      <template #empty><span class="library-empty">没有匹配结果，请修改搜索词。</span></template>
    </ElSelect>
  </div>
</template>

<style scoped>
.searchable-library{display:grid;gap:8px;min-width:0;width:100%;--el-color-primary:var(--teal)}.library-label{font-size:14px;color:#405767}.library-empty{display:block;padding:12px;color:#647b86;font-size:13px}
.searchable-library :deep(.el-select__wrapper){min-height:42px;padding:9px 11px;border-radius:5px;font-size:14px}.searchable-library :deep(.el-select__input){min-height:0;height:24px;padding:0;border:0;background:transparent;box-shadow:none;outline:none}.searchable-library :deep(.el-select){width:100%;min-width:0}
</style>

<style>
.library-select-dropdown{max-width:calc(100vw - 24px)}
.library-select-dropdown .el-select-dropdown__item{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.library-select-dropdown .el-select-dropdown__wrap{max-height:220px}
.library-select-dropdown .el-select-dropdown{min-width:0!important}
</style>
