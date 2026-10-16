<script setup lang="ts">
defineProps<{ label: string; values: unknown[]; warnings: string[]; disabled: boolean }>()
defineEmits<{ choose: [value: unknown] }>()
function display(value: unknown) { return Array.isArray(value) ? value.join('、') : String(value ?? '') }
</script>

<template>
  <span v-if="values.length || warnings.length" class="field-suggestions" role="group" :aria-label="`${label}识别建议`">
    <span v-if="values.length" class="suggestion-heading">请对照图片确认后填入：</span>
    <span v-for="warning in warnings" :key="warning" class="suggestion-warning">{{ warning }}</span>
    <button v-for="(value, index) in values" :key="index" type="button" :disabled="disabled" :aria-label="`填入：${display(value)}`" @click.prevent="$emit('choose', value)">{{ display(value) }} <span aria-hidden="true">↳ 填入</span></button>
  </span>
</template>

<style scoped>
.field-suggestions{display:flex;flex-wrap:wrap;gap:6px;padding:9px;border:1px solid #ead2a1;background:#fff9ed;border-radius:6px}.suggestion-heading,.suggestion-warning{width:100%;font-size:12px;line-height:1.5;color:#886026}.field-suggestions button{font-size:12px;min-height:32px;padding:5px 8px;text-align:left;overflow-wrap:anywhere}.field-suggestions button span{color:var(--teal)}
</style>
