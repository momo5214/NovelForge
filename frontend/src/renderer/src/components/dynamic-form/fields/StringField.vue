<template>
  <el-form-item :label="label" :prop="prop">
    <el-input
      v-if="!isLongText"
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      clearable
    />
    <el-input
      v-else
      type="textarea"
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      :autosize="autosizeConfig"
      clearable
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

const props = defineProps<{
  modelValue: string | undefined
  label: string
  prop: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

const LONG_TEXT_FIELD_NAMES = new Set([
  'thinking',
  'character_thinking',
  'plot_milestone',
  'worldview_evolution',
  'protagonist_growth_node',
  'ending_hook',
  'core_setting_expansion',
  'core_conflict',
  'protagonist_progress',
  'protagonist_team_dynamic',
  'chapter_range',
  'content',
  'overview',
  'description',
])

// 一个简单的启发式方法：如果描述或标题表明它是一个长文本字段，则使用文本区域。
// 一个更健 robuste 解决方案可能是在 schema 中包含一个自定义属性，比如 `x-ui-control: 'textarea'`。
const isLongText = computed(() => {
  const uiMeta = (props.schema as any)?.['x-ui'] || {}
  if (uiMeta?.control === 'textarea' || uiMeta?.multiline === true) {
    return true
  }
  // 新增规则：如果 schema 中定义了 minLength 且大于 50，则视为长文本。
  if (props.schema.minLength !== undefined && props.schema.minLength > 50) {
    return true
  }
  const description = props.schema.description?.toLowerCase() || ''
  const title = props.schema.title?.toLowerCase() || ''
  if (LONG_TEXT_FIELD_NAMES.has(props.prop)) return true
  return (
    description.includes('思考') ||
    description.includes('过程') ||
    description.includes('描述') ||
    description.includes('概述') ||
    description.includes('展开') ||
    description.includes('冲突') ||
    description.includes('成长') ||
    description.includes('悬念') ||
    title.includes('thinking')
  )
})

const autosizeConfig = computed(() => {
  const uiMeta = (props.schema as any)?.['x-ui'] || {}
  const minRows = Number(uiMeta?.minRows)
  const maxRows = Number(uiMeta?.maxRows)
  return {
    minRows: Number.isFinite(minRows) && minRows > 0 ? minRows : 4,
    maxRows: Number.isFinite(maxRows) && maxRows > 0 ? maxRows : 14
  }
})

const placeholder = computed(() => {
  return props.schema.description || `请输入 ${props.label}`
})
</script> 
