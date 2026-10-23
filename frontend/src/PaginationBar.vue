<script setup lang="ts">
import { computed, ref, watch } from 'vue'
const props = withDefaults(defineProps<{ page: number; total: number; label: string; pageSize?: number; disabled?: boolean }>(), { pageSize: 50, disabled: false })
const emit = defineEmits<{ 'update:page': [page: number] }>()
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const target = ref<string | number>(props.page)
watch(() => props.page, value => { target.value = value })
function jump(value: string | number = target.value) {
  if (props.disabled) return
  const number = Number(value)
  const next = String(value).trim() && Number.isFinite(number) ? Math.max(1, Math.min(pages.value, Math.trunc(number))) : props.page
  target.value = next
  if (next !== props.page) emit('update:page', next)
}
</script>

<template>
  <nav class="pagination-bar" :aria-label="label">
    <span>每页 {{ pageSize }} 条 · 第 {{ page }} / {{ pages }} 页</span>
    <div class="page-buttons">
      <button :disabled="disabled || page <= 1" @click="jump(1)">首页</button>
      <button :disabled="disabled || page <= 1" @click="jump(page - 1)">上一页</button>
      <button :disabled="disabled || page >= pages" @click="jump(page + 1)">下一页</button>
      <button :disabled="disabled || page >= pages" @click="jump(pages)">末页</button>
    </div>
    <form class="page-jump" novalidate @submit.prevent="jump()">
      <label>跳至<input v-model="target" type="number" min="1" :max="pages" step="1" aria-label="目标页码" :disabled="disabled">页</label>
      <button :disabled="disabled">跳转</button>
    </form>
  </nav>
</template>

<style scoped>
.pagination-bar{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:12px;padding:20px 0;color:#687f8a;font-size:14px}
.page-buttons,.page-jump,.page-jump label{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0}
.page-jump label{flex-direction:row}.page-jump input{width:76px}.pagination-bar button{white-space:nowrap}
@media(max-width:600px){.pagination-bar{justify-content:flex-start}.pagination-bar>span{width:100%}.pagination-bar button{padding:8px 10px}}
</style>
