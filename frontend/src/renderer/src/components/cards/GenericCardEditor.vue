<template>
  <div class="generic-card-editor">
    <EditorHeader
      :project-name="projectName"
      :card-type="cardTypeDisplayName"
      v-model:title="titleProxy"
      :dirty="isDirty"
      :saving="isSaving"
      :can-save="isDirty && !isSaving"
      :last-saved-at="lastSavedAt"
      :needs-confirmation="props.card.needs_confirmation"
      :can-generate="canGenerate"
      @save="handleSave"
      @generate="handleGenerateClick"
      @open-context="openDrawer = true"
      @delete="handleDelete"
      @open-versions="showVersions = true"
    />
    
    <!-- 自定义内容编辑器（如 CodeMirrorEditor）-->
    <template v-if="activeContentEditor">
      <div v-if="showInlineAiParams" class="toolbar-row param-toolbar">
        <div class="param-inline">
          <AIPerCardParams :card-id="props.card.id" :card-type-name="props.card.card_type?.name" />
        </div>
      </div>
      <component
        :is="activeContentEditor"
        ref="contentEditorRef"
        :card="props.card"
        :prefetched="props.prefetched"
        @switch-tab="handleSwitchTab"
        @update:dirty="handleContentEditorDirtyChange"
      />
    </template>
    
    <!-- 默认表单编辑器 -->
    <template v-else>
      <!-- 参数配置：显示当前模型ID，点击弹出就地配置面板 -->
      <div class="toolbar-row param-toolbar">
        <div class="param-inline">
          <AIPerCardParams :card-id="props.card.id" :card-type-name="props.card.card_type?.name" />
          <el-button size="small" type="primary" plain @click="schemaStudioVisible = true">结构</el-button>
        </div>
      </div>

      <div class="editor-body">
        <div class="main-pane">
          <div v-if="schema" class="form-container">
            <template v-if="sections && sections.length">
              <SectionedForm v-if="wrapperName" :schema="innerSchema" v-model="innerData" :sections="sections" :exclude-fields="formExcludeFields" />
              <SectionedForm v-else :schema="schema" v-model="localData" :sections="sections" :exclude-fields="formExcludeFields" />
            </template>
            <template v-else>
              <ModelDrivenForm v-if="wrapperName" :schema="innerSchema" v-model="innerData" :exclude-fields="formExcludeFields" />
              <ModelDrivenForm v-else :schema="schema" v-model="localData" :exclude-fields="formExcludeFields" />
            </template>
          </div>
          <div v-else class="loading-or-error-container">
            <p v-if="schemaIsLoading">正在加载模型...</p>
            <p v-else>无法加载此卡片内容的编辑模型。</p>
          </div>
        </div>
      </div>
    </template>

    <ContextDrawer
      v-model="openDrawer"
      :context-template="localAiContextTemplate"
      :preview-text="previewText"
      @apply-context="applyContextTemplateAndSave"
      @open-selector="openSelectorFromDrawer"
    >
      <template #params>
        <div class="param-placeholder">参数设置入口（已改为每卡片本地参数）</div>
      </template>
    </ContextDrawer>

    <CardReferenceSelectorDialog v-model="isSelectorVisible" :cards="cards" :currentCardId="props.card.id" @confirm="handleReferenceConfirm" />
    <CardVersionsDialog
      v-if="projectStore.currentProject?.id"
      v-model="showVersions"
      :project-id="projectStore.currentProject!.id"
      :card-id="props.card.id"
      :current-content="wrapperName ? innerData : localData"
      :current-context-template="localAiContextTemplate"
      @restore="handleRestoreVersion"
    />

    <SchemaStudio v-model:visible="schemaStudioVisible" :mode="'card'" :target-id="props.card.id" :context-title="props.card.title" @saved="onSchemaSaved" />

    <!-- 初始提示对话框 -->
    <InitialPromptDialog
      v-model:visible="showInitialPromptDialog"
      :card-type-name="props.card.card_type?.name"
      @confirm="handleStartGeneration"
      @cancel="showInitialPromptDialog = false"
    />

    <!-- 生成面板（悬浮窗）-->
    <GenerationPanel
      ref="generationPanelRef"
      :visible="showGenerationPanel"
      @close="handleCloseGenerationPanel"
      @pause="handlePauseGeneration"
      @continue="handleContinueGeneration"
      @stop="handleStopGeneration"
      @restart="handleRestartGeneration"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { storeToRefs } from 'pinia'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useAIStore } from '@renderer/stores/useAIStore'
import { usePerCardAISettingsStore, type PerCardAIParams, getPresetForCardType } from '@renderer/stores/usePerCardAISettingsStore'
import { getCardAIParams } from '@renderer/api/setting'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { getCardTypeDisplayName } from '@renderer/utils/cardTypeDisplay'
import { schemaService } from '@renderer/api/schema'
import type { JSONSchema } from '@renderer/api/schema'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import ModelDrivenForm from '../dynamic-form/ModelDrivenForm.vue'
import SectionedForm from '../dynamic-form/SectionedForm.vue'
import { mergeSections, autoGroup, type SectionConfig } from '@renderer/services/uiLayoutService'
import CardReferenceSelectorDialog from './CardReferenceSelectorDialog.vue'
import EditorHeader from '../common/EditorHeader.vue'
import ContextDrawer from '../common/ContextDrawer.vue'
import CardVersionsDialog from '../common/CardVersionsDialog.vue'
import { cloneDeep, isEqual } from 'lodash-es'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { ElMessage, ElMessageBox } from 'element-plus'
import { addVersion } from '@renderer/services/versionService'
import SchemaStudio from '../shared/SchemaStudio.vue'
import AIPerCardParams from '../common/AIPerCardParams.vue'
// 移除 AssistantSidebar 相关导入与逻辑
import { resolveTemplate } from '@renderer/services/contextResolver'
// 指令流生成相关导入
import GenerationPanel from '../generation/GenerationPanel.vue'
import InitialPromptDialog from '../generation/InitialPromptDialog.vue'
import { InstructionExecutor } from '@renderer/services/instructionExecutor'
import { generateWithInstructionStream } from '@renderer/api/generation'
import type { Instruction, ConversationMessage } from '@renderer/types/instruction'

const props = defineProps<{ 
  card: CardRead
  prefetched?: any
}>()

const cardStore = useCardStore()
const aiStore = useAIStore()
const perCardStore = usePerCardAISettingsStore()
const projectStore = useProjectStore()

const { cards } = storeToRefs(cardStore)

const openDrawer = ref(false)
const isSelectorVisible = ref(false)
const showVersions = ref(false)
const schemaStudioVisible = ref(false)
const assistantVisible = ref(false)
const assistantResolvedContext = ref<string>('')
const assistantEffectiveSchema = ref<any>(null)
// 指令流生成相关状态
const showInitialPromptDialog = ref(false)
const showGenerationPanel = ref(false)
const generationPanelRef = ref<InstanceType<typeof GenerationPanel>>()
const instructionExecutor = ref<InstructionExecutor | null>(null)
const currentAbortController = ref<AbortController | null>(null)
const conversationHistory = ref<ConversationMessage[]>([])

// --- 内容编辑器动态映射 ---
// 类似 CardEditorHost 的 editorMap，但这里是内容编辑器（共享外壳）
const contentEditorMap: Record<string, any> = {
  CodeMirrorEditor: defineAsyncComponent(() => import('../editors/CodeMirrorEditor.vue')),
  MarkdownTextEditor: defineAsyncComponent(() => import('../editors/MarkdownTextEditor.vue')),
  // 未来可以添加更多内容编辑器，例如：
  // RichTextEditor: defineAsyncComponent(() => import('../editors/RichTextEditor.vue')),
  // MarkdownEditor: defineAsyncComponent(() => import('../editors/MarkdownEditor.vue')),
}

// 根据 card_type.editor_component 选择内容编辑器
const activeContentEditor = computed(() => {
  const editorName = props.card?.card_type?.editor_component
  if (editorName && contentEditorMap[editorName]) {
    return contentEditorMap[editorName]
  }
  return null // null 表示使用默认的表单编辑器
})

const canGenerate = computed(() => {
  const isAIEnabled = Boolean(props.card?.card_type?.is_ai_enabled)
  if (!isAIEnabled) return false
  return props.card?.card_type?.editor_component !== 'CodeMirrorEditor'
})
const showInlineAiParams = computed(() => Boolean(props.card?.card_type?.is_ai_enabled))
const cardTypeDisplayName = computed(() => getCardTypeDisplayName(props.card?.card_type?.name))

function getResolvedContextTemplateValue(): string {
  const raw = localAiContextTemplate.value
  if (typeof raw === 'string' && raw.trim()) {
    return raw
  }
  return getEffectiveContextTemplate(props.card)
}

// 通用的内容编辑器引用（可以是 CodeMirrorEditor 或其他）
const contentEditorRef = ref<any>(null)
const contentEditorDirty = ref(false)

function handleSwitchTab(tab: string) {
  const evt = new CustomEvent('nf:switch-right-tab', { detail: { tab } })
  window.dispatchEvent(evt)
}

function handleContentEditorDirtyChange(dirty: boolean) {
  contentEditorDirty.value = dirty
}

function openAssistant() {
  const editingContent = wrapperName.value ? innerData.value : localData.value
  const currentCardForResolve = { ...props.card, content: editingContent }
  const effectiveTemplate = getResolvedContextTemplateValue()
  const resolved = resolveTemplate({ template: effectiveTemplate, cards: cards.value, currentCard: currentCardForResolve as any })
  assistantResolvedContext.value = resolved
  // 读取有效 Schema 作为对话指导
  import('@renderer/api/setting').then(async ({ getCardSchema }) => {
    try {
      const resp = await getCardSchema(props.card.id)
      assistantEffectiveSchema.value = resp?.effective_schema || resp?.json_schema || null
    } catch { assistantEffectiveSchema.value = null }
  })
  assistantVisible.value = true
}

const isSaving = ref(false)
const localData = ref<any>({})
const localAiContextTemplate = ref<string>('')
const originalData = ref<any>({})
const originalAiContextTemplate = ref<string>('')

const ARCHITECTURE_STEP_PROMPTS: Record<number, string> = {
  1: '步骤一-分卷使命宣言',
  2: '步骤二-世界观与冲突发生器',
  3: '步骤三-情节线与推进机制',
  4: '步骤四-核心角色规划',
  5: '步骤五-叙事风格与文本策略'
}

const ARCHITECTURE_STEP_SYSTEM_FIELDS = ['step', 'step_name', 'prompt_name', 'ai_context_template']

function isArchitectureStepCard(card?: CardRead | null): boolean {
  return card?.card_type?.name === '小说架构步骤'
}

function getArchitectureStepNumber(card?: CardRead | null): number | null {
  const stepVal = Number((card?.content as any)?.step)
  return Number.isFinite(stepVal) && stepVal > 0 ? stepVal : null
}

function mergeArchitectureStepSystemFields(content: Record<string, any> | null | undefined): Record<string, any> {
  const nextContent = content && typeof content === 'object' ? cloneDeep(content) : {}
  if (!isArchitectureStepCard(props.card)) return nextContent

  const existingContent = ((props.card?.content as any) && typeof props.card.content === 'object')
    ? (props.card.content as Record<string, any>)
    : {}

  for (const field of ARCHITECTURE_STEP_SYSTEM_FIELDS) {
    if (nextContent[field] === undefined && existingContent[field] !== undefined) {
      nextContent[field] = existingContent[field]
    }
  }

  return nextContent
}

const formExcludeFields = computed(() => {
  return isArchitectureStepCard(props.card) ? ARCHITECTURE_STEP_SYSTEM_FIELDS : []
})

function getGenerationSchema(card: CardRead, sourceSchema: any) {
  if (!isArchitectureStepCard(card)) {
    return sourceSchema
  }

  const contentSchema = sourceSchema?.properties?.content || {
    type: 'string',
    title: '步骤内容',
    description: '当前架构步骤正文内容',
  }

  return {
    ...sourceSchema,
    type: 'object',
    properties: {
      content: contentSchema,
    },
    required: ['content'],
  }
}

function buildArchitectureStepContextTemplate(card: CardRead): string {
  if (!isArchitectureStepCard(card)) return ''

  const stepVal = getArchitectureStepNumber(card)
  if (!stepVal) return ''

  const lines: string[] = [
    '作品标签: @作品标签.content',
    '故事大纲: @故事大纲.content.overview'
  ]

  if (stepVal <= 1) {
    lines.push('小说架构: @小说架构.content.content')
  } else {
    for (let i = 1; i < stepVal; i++) {
      lines.push(`步骤${i}结果: @type:小说架构步骤[index=${i}].content.content`)
    }
  }

  return lines.join('\n')
}

function getEffectiveContextTemplate(card: CardRead): string {
  const instanceTemplate = card.ai_context_template
  const contentTemplate = (card.content as any)?.ai_context_template
  const architectureStepTemplate = buildArchitectureStepContextTemplate(card)
  const typeDefault = (card.card_type as any)?.default_ai_context_template

  if (architectureStepTemplate) {
    const instanceText = typeof instanceTemplate === 'string' ? instanceTemplate.trim() : ''
    const contentText = typeof contentTemplate === 'string' ? contentTemplate.trim() : ''
    const defaultText = typeof typeDefault === 'string' ? typeDefault.trim() : ''

    // 增强流程在 content 里写入步骤专用模板；只有当根字段是用户显式保存的自定义模板时才优先使用根字段。
    if (instanceText && instanceText !== defaultText) {
      return instanceTemplate!
    }

    if (contentText && contentText.includes('@')) {
      return contentTemplate
    }

    if (instanceText) {
      return instanceTemplate!
    }

    return architectureStepTemplate
  }

  if (typeof instanceTemplate === 'string' && instanceTemplate.trim()) {
    return instanceTemplate
  }

  if (typeof contentTemplate === 'string' && contentTemplate.trim()) {
    return contentTemplate
  }

  if (typeof typeDefault === 'string' && typeDefault.trim()) {
    return typeDefault
  }
  return ''
}

function getEffectivePromptName(card: CardRead, params?: Partial<PerCardAIParams> | null): string | undefined {
  if (isArchitectureStepCard(card)) {
    const stepVal = getArchitectureStepNumber(card)
    if (stepVal && ARCHITECTURE_STEP_PROMPTS[stepVal]) {
      return ARCHITECTURE_STEP_PROMPTS[stepVal]
    }
  }

  const contentPromptName = (card.content as any)?.prompt_name
  if (typeof contentPromptName === 'string' && contentPromptName.trim()) {
    return contentPromptName.trim()
  }

  const paramPromptName = params?.prompt_name
  if (typeof paramPromptName === 'string' && paramPromptName.trim()) {
    return paramPromptName.trim()
  }

  return undefined
}

function buildArchitectureStepGenerationData(currentCard: CardRead, allCards: CardRead[]): Record<string, any> {
  if (!isArchitectureStepCard(currentCard)) return {}

  const stepVal = getArchitectureStepNumber(currentCard)
  if (!stepVal || stepVal <= 1) return {}

  const sameParentSteps = allCards
    .filter(card => card.card_type?.name === '小说架构步骤' && card.parent_id === currentCard.parent_id)
    .sort((a, b) => a.display_order - b.display_order)

  const data: Record<string, any> = {}
  for (let i = 1; i < stepVal; i++) {
    const stepCard = sameParentSteps.find(card => Number((card.content as any)?.step) === i)
    const stepResult = String((stepCard?.content as any)?.content || '').trim()
    if (stepResult) {
      data[`step${i}_result`] = stepResult
    }
  }

  return data
}

const schema = ref<JSONSchema | undefined>(undefined)
const schemaIsLoading = ref(false)
let atIndexForInsertion = -1
const sections = ref<SectionConfig[] | undefined>(undefined)
const wrapperName = ref<string | undefined>(undefined)
const innerSchema = ref<JSONSchema | undefined>(undefined)
const innerData = computed({
  get: () => {
    if (!wrapperName.value) return localData.value
    return (localData.value && localData.value[wrapperName.value]) || {}
  },
  set: (v: any) => {
    if (!wrapperName.value) { localData.value = v; return }
    localData.value = { ...(localData.value || {}), [wrapperName.value]: v }
  }
})

// AI 可选项（模型/提示词/输出模型）
const aiOptions = ref<AIConfigOptions | null>(null)
async function loadAIOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }

const projectName = '当前项目'
const lastSavedAt = ref<string | undefined>(undefined)

// 顶部标题与表单 Title 字段保持同步
// 1) 初始化为 card.title，切换卡片时重置
const titleProxy = ref(props.card.title)
watch(
  () => props.card.title,
  (v) => {
    titleProxy.value = v
  }
)

// 2) 顶部标题变更 -> 写回表单数据中的 title（若存在）
watch(
  titleProxy,
  (v) => {
    if (!localData.value) {
      localData.value = { title: v }
      return
    }
    if ((localData.value as any).title === v) return
    localData.value = { ...(localData.value || {}), title: v }
  }
)

// 3) 表单中的 title 字段变更 -> 回写到标题栏
watch(
  () => (localData.value && (localData.value as any).title),
  (v) => {
    if (typeof v === 'string' && v !== titleProxy.value) {
      titleProxy.value = v
    }
  }
)

const isDirty = computed(() => {
  const ctxDirty = localAiContextTemplate.value !== originalAiContextTemplate.value
  const titleDirty = titleProxy.value !== props.card.title

  // 使用自定义内容编辑器（如章节正文）：
  // 只要正文内容、上下文模板或标题有任一改动，都视为未保存
  if (activeContentEditor.value) {
    return contentEditorDirty.value || ctxDirty || titleDirty
  }

  // 默认表单编辑器：比较内容 + 上下文模板 + 标题
  return !isEqual(localData.value, originalData.value) || ctxDirty || titleDirty
})

watch(
  () => props.card,
  async (newCard) => {
    if (newCard) {
      localData.value = cloneDeep(newCard.content) || {}
      const effectiveContextTemplate = getEffectiveContextTemplate(newCard)
      localAiContextTemplate.value = effectiveContextTemplate
      originalData.value = cloneDeep(newCard.content) || {}
      originalAiContextTemplate.value = effectiveContextTemplate
      titleProxy.value = newCard.title
      await loadSchemaForCard(newCard)
      // 载入每卡片参数
      await loadAIOptions()
      // 优先从后端读取有效参数
      try {
        const resp = await getCardAIParams(newCard.id)
        const eff = resp?.effective_params
        if (eff) editingParams.value = { ...eff }
      } catch {}
      if (!editingParams.value || Object.keys(editingParams.value).length === 0) {
        const preset = getPresetForCardType(newCard.card_type?.name) || {}
        editingParams.value = { ...preset }
      }
      if (!editingParams.value.llm_config_id) {
        const first = aiOptions.value?.llm_configs?.[0]
        if (first) editingParams.value.llm_config_id = first.id
      }
      const effectivePromptName = getEffectivePromptName(newCard, editingParams.value)
      if (effectivePromptName) {
        editingParams.value.prompt_name = effectivePromptName
      }
      // 本地兼容保存
      perCardStore.setForCard(newCard.id, editingParams.value)
    }
  },
  { immediate: true, deep: true }
)

const editingParams = ref<PerCardAIParams>({})

async function loadSchemaForCard(card: CardRead) {
  schemaIsLoading.value = true
  try {
    // 优先从后端按类型/实例读取 schema
    try {
      const { getCardSchema } = await import('@renderer/api/setting')
      const resp = await getCardSchema(card.id)
      const effective = (resp?.effective_schema || resp?.json_schema)
      if (effective) {
        schema.value = effective
      }
    } catch {}
    if (!schema.value) {
      // 回退：仍走原有 schemaService 以避免首轮迁移空值导致空白
      const typeName = (card.card_type as any)?.name as string | undefined
      await schemaService.loadSchemas()
      if (!typeName) {
        schema.value = undefined
        sections.value = undefined
        wrapperName.value = undefined
        innerSchema.value = undefined
        return
      }
      schema.value = schemaService.getSchema(typeName)
      if (!schema.value) {
        await schemaService.refreshSchemas()
        schema.value = schemaService.getSchema(typeName)
      }
    }
    const props: any = (schema.value as any)?.properties || {}
    const keys = Object.keys(props)
    const onlyKey = keys.length === 1 ? keys[0] : undefined
    const isObject = onlyKey && (props[onlyKey]?.type === 'object' || props[onlyKey]?.$ref || props[onlyKey]?.anyOf)
    if (onlyKey && isObject) {
      wrapperName.value = onlyKey
      const maybeRef = props[onlyKey]
      if (maybeRef && typeof maybeRef === 'object' && '$ref' in maybeRef && typeof maybeRef.$ref === 'string') {
        const refName = maybeRef.$ref.split('/').pop() || ''
        const localDefs = (schema.value as any)?.$defs || {}
        innerSchema.value = localDefs[refName] || schemaService.getSchema(refName) || maybeRef
      } else {
        innerSchema.value = maybeRef
      }
    } else {
      wrapperName.value = undefined
      innerSchema.value = undefined
    }
    const schemaForLayout = (wrapperName.value ? innerSchema.value : schema.value) as any
    const schemaMeta = schemaForLayout?.['x-ui'] || undefined
    const backendLayout = (schemaForLayout?.['ui_layout'] || undefined)
    sections.value = mergeSections({ schemaMeta, backendLayout, frontendDefault: autoGroup(schemaForLayout) })
  } finally { schemaIsLoading.value = false }
}

function handleReferenceConfirm(reference: string) {
  if (atIndexForInsertion < 0) {
    // 若未通过 @ 触发，则直接在末尾追加
    localAiContextTemplate.value = `${localAiContextTemplate.value}${reference}`
    ElMessage.success('已插入引用')
    return
  }
  const text = localAiContextTemplate.value
  const isAt = text.charAt(atIndexForInsertion) === '@'
  const before = text.substring(0, atIndexForInsertion)
  const after = text.substring(atIndexForInsertion + (isAt ? 1 : 0))
  localAiContextTemplate.value = before + reference + after
  atIndexForInsertion = -1
  ElMessage.success('已插入引用')
}

function applyContextTemplate(text: string) {
  localAiContextTemplate.value = text
}

async function applyContextTemplateAndSave(text: string) {
  localAiContextTemplate.value = typeof text === 'string' ? text : String(text)
  ElMessage.success('上下文模板已应用')
  openDrawer.value = false
  await handleSave()
}

// Alt+K 打开抽屉
function keyHandler(e: KeyboardEvent) {
  if ((e.altKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    openDrawer.value = true
  }
  if ((e.altKey || e.metaKey) && (e.key === 'j' || e.key === 'J')) {
    e.preventDefault()
    openAssistant()
  }
}

onMounted(() => { window.addEventListener('keydown', keyHandler) })
onBeforeUnmount(() => { window.removeEventListener('keydown', keyHandler) })

// 在抽屉中输入 @ 时弹出选择器
let drawerTextarea: HTMLTextAreaElement | null = null
watch(() => openDrawer.value, (v) => {
  if (v) {
    nextTick(() => {
      drawerTextarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
      drawerTextarea?.addEventListener('input', handleDrawerInput)
    })
  } else {
    drawerTextarea?.removeEventListener('input', handleDrawerInput)
    drawerTextarea = null
    atIndexForInsertion = -1
  }
})

function handleDrawerInput(ev: Event) {
  const textarea = ev.target as HTMLTextAreaElement
  // 同步抽屉内文本到本地模板，避免选择器插入时丢失前缀
  localAiContextTemplate.value = textarea.value
  const cursorPos = textarea.selectionStart
  const lastChar = textarea.value.substring(cursorPos - 1, cursorPos)
  if (lastChar === '@') {
    atIndexForInsertion = cursorPos - 1
    isSelectorVisible.value = true
  }
}

function openSelectorFromDrawer() {
  const textarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
  if (textarea) {
    localAiContextTemplate.value = textarea.value
    // 在光标当前位置插入，不回退一位
    atIndexForInsertion = textarea.selectionStart
  }
  isSelectorVisible.value = true
}

const previewText = computed(() => localAiContextTemplate.value)

async function handleSave() {
  // 自定义内容编辑器的保存逻辑（如 CodeMirrorEditor）
  if (activeContentEditor.value && contentEditorRef.value) {
    try {
      isSaving.value = true
      // 在保存正文前先截取当前模板与旧值，避免保存正文时触发的 card 更新把本地模板重置为旧值
      const templateBeforeSave = localAiContextTemplate.value
      const prevTemplateOnCard = props.card.ai_context_template || ''

      // 将当前标题传递给内容编辑器，由内容编辑器统一负责保存 title 与正文内容
      const savedContent = await contentEditorRef.value.handleSave(titleProxy.value)

      // 如有上下文模板变更，单独保存 ai_context_template（不覆盖正文内容）
      if (templateBeforeSave !== prevTemplateOnCard) {
        try {
          await cardStore.modifyCard(props.card.id, {
            ai_context_template: templateBeforeSave,
          } as any)
        } catch {}
      }

      // 保存历史版本
      try {
        if (projectStore.currentProject?.id && savedContent) {
          await addVersion(projectStore.currentProject.id, {
            cardId: props.card.id,
            projectId: projectStore.currentProject.id,
            title: titleProxy.value,
            content: savedContent,
            ai_context_template: templateBeforeSave,
          })
        }
      } catch (e) {
        console.error('Failed to add version:', e)
      }
      
      contentEditorDirty.value = false
      originalAiContextTemplate.value = templateBeforeSave
      lastSavedAt.value = new Date().toLocaleTimeString()
      ElMessage.success('保存成功')
    } catch (e) {
      ElMessage.error('保存失败')
    } finally {
      isSaving.value = false
    }
    return
  }
  
  // 默认表单编辑器的保存逻辑
  try {
    isSaving.value = true
    const mergedContent = mergeArchitectureStepSystemFields(localData.value as Record<string, any>)
    const updatePayload: CardUpdate = {
      title: titleProxy.value,
      content: mergedContent,
      ai_context_template: localAiContextTemplate.value,
      needs_confirmation: false,  // 清除 AI 修改标记，触发工作流
    }
    await cardStore.modifyCard(props.card.id, updatePayload)
    try {
      await addVersion(projectStore.currentProject!.id!, {
        cardId: props.card.id,
        projectId: projectStore.currentProject!.id!,
        title: titleProxy.value,
        content: updatePayload.content as any,
        ai_context_template: localAiContextTemplate.value,
      })
    } catch {}
    originalData.value = cloneDeep(mergedContent)
    localData.value = cloneDeep(mergedContent)
    originalAiContextTemplate.value = localAiContextTemplate.value
    lastSavedAt.value = new Date().toLocaleTimeString()
    ElMessage.success('保存成功！')
  } finally { isSaving.value = false }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(`确认删除卡片「${props.card.title}」？此操作不可恢复`, '删除确认', { type: 'warning' })
    await cardStore.removeCard(props.card.id)
    ElMessage.success('卡片已删除')
    const evt = new CustomEvent('nf:navigate', { detail: { to: 'market' } })
    window.dispatchEvent(evt)
  } catch (e) {
  }
}

// ==================== 指令流生成相关方法 ====================

/**
 * 点击生成按钮时触发
 */
function handleGenerateClick() {
  // 显示初始提示对话框
  showInitialPromptDialog.value = true
}

/**
 * 开始生成（用户确认初始提示后）
 */
async function handleStartGeneration(userPrompt: string, useExistingContent: boolean) {
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) {
    ElMessage.error('请先设置有效的模型ID')
    return
  }

  try {
    // 1. 获取有效 Schema
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) {
      ElMessage.error('未找到此卡片的结构（Schema）。')
      return
    }

    // 2. 解析上下文
    const editingContent = wrapperName.value ? innerData.value : localData.value
    const currentCardForResolve = { ...props.card, content: editingContent }
    const effectiveTemplate = getResolvedContextTemplateValue()
    const resolvedContext = resolveTemplate({
      template: effectiveTemplate,
      cards: cards.value,
      currentCard: currentCardForResolve as any
    })

    // 3. 初始化指令执行器（根据选项决定是否使用现有内容）
    const initialData = useExistingContent ? (editingContent || {}) : {}
    instructionExecutor.value = new InstructionExecutor(initialData)
    const architectureStepData = buildArchitectureStepGenerationData(props.card, cards.value)
    const requestCurrentData = {
      ...(useExistingContent ? (instructionExecutor.value?.getData() || {}) : {}),
      ...architectureStepData
    }

    // 4. 重置对话历史
    conversationHistory.value = []

    // 5. 显示生成面板并重置状态
    showGenerationPanel.value = true
    await nextTick()
    
    // 重置面板状态（清空消息）
    if (generationPanelRef.value) {
      generationPanelRef.value.reset()
    }

    // 6. 显示用户要求（如果有）
    // 必须要要在 reset 之后添加，否则会被 reset 清空
    if (userPrompt && generationPanelRef.value) {
      console.log('Adding user prompt to panel:', userPrompt)
      // 使用 setTimeout 确保在 reset 的 DOM 更新后执行
      setTimeout(() => {
        generationPanelRef.value?.addMessage('user', userPrompt)
      }, 0)
    }

    // 7. 开始生成
    if (generationPanelRef.value) {
      generationPanelRef.value.startGeneration()
    }

    // 8. 调用生成 API
    await performGeneration(userPrompt, getGenerationSchema(props.card, effective), resolvedContext, p, requestCurrentData)
  } catch (e) {
    console.error('启动生成失败:', e)
    ElMessage.error('启动生成失败')
  }
}

/**
 * 执行生成
 */
async function performGeneration(
  userPrompt: string,
  schema: any,
  contextInfo: string,
  params: PerCardAIParams,
  currentData: Record<string, any>
) {
  // 创建 AbortController
  currentAbortController.value = new AbortController()

  try {
    await generateWithInstructionStream(
      {
        llm_config_id: params.llm_config_id!,
        user_prompt: userPrompt,
        response_model_schema: schema,
        current_data: currentData,
        conversation_context: conversationHistory.value,
        context_info: contextInfo,
        prompt_template: getEffectivePromptName(props.card, params),
        temperature: params.temperature,
        max_tokens: params.max_tokens,
        timeout: params.timeout
      },
      {
        onThinking: (text) => {
          generationPanelRef.value?.addMessage('thinking', text)
        },
        onInstruction: (instruction: Instruction) => {
          // 执行指令
          instructionExecutor.value?.execute(instruction)

          // 更新 UI
          const data = instructionExecutor.value?.getData()
          if (data) {
            import('lodash-es').then(({ cloneDeep }) => {
              const clonedData = cloneDeep(data)
              if (wrapperName.value) {
                innerData.value = clonedData
              } else {
                localData.value = clonedData
              }
            })
          }

          // 显示指令执行消息
          const actionText = formatInstructionAction(instruction)
          generationPanelRef.value?.addMessage('action', actionText)
          generationPanelRef.value?.incrementCompletedFields()
        },
        onWarning: (text) => {
          generationPanelRef.value?.addMessage('warning', text)
        },
        onError: (text) => {
          generationPanelRef.value?.addMessage('error', text)
          generationPanelRef.value?.finishGeneration(false, text)
        },
        onDone: async (success, message, finalData) => {
          if (success) {
            // 如果后端回传了最终完整数据（包含默认值注入），则合并更新
            if (finalData) {
              console.log('Received final data from backend:', finalData)
              const { mergeWith, isArray } = await import('lodash-es')
              const arrayOverwrite = (objValue: any, srcValue: any) => {
                if (isArray(objValue) || isArray(srcValue)) {
                  return srcValue
                }
                return undefined
              }
              if (wrapperName.value) {
                const mergedInner = mergeWith({}, innerData.value || {}, finalData, arrayOverwrite)
                innerData.value = mergedInner
              } else {
                const merged = mergeWith({}, localData.value || {}, finalData, arrayOverwrite)
                localData.value = merged
              }
            }
            generationPanelRef.value?.finishGeneration(true, message)
            ElMessage.success(message || '生成完成！')
          } else {
            generationPanelRef.value?.finishGeneration(false, message)
          }
        }
      },
      currentAbortController.value.signal
    )
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      console.error('生成失败:', error)
      generationPanelRef.value?.addMessage('error', error.message || '生成失败')
      generationPanelRef.value?.finishGeneration(false)
    }
  }
}

/**
 * 格式化指令为可读文本
 */
function formatInstructionAction(instruction: Instruction): string {
  if (instruction.op === 'set') {
    const path = instruction.path.replace(/^\//, '').replace(/\//g, ' > ')
    return `设置字段: ${path}`
  } else if (instruction.op === 'append') {
    const path = instruction.path.replace(/^\//, '').replace(/\//g, ' > ')
    return `添加元素到: ${path}`
  } else if (instruction.op === 'done') {
    return '生成完成'
  }
  return '执行指令'
}

/**
 * 关闭生成面板
 */
function handleCloseGenerationPanel() {
  // 中断当前生成
  if (currentAbortController.value) {
    currentAbortController.value.abort()
    currentAbortController.value = null
  }

  showGenerationPanel.value = false
  instructionExecutor.value = null
  conversationHistory.value = []
}

/**
 * 暂停生成
 */
function handlePauseGeneration() {
  if (currentAbortController.value) {
    currentAbortController.value.abort()
    currentAbortController.value = null
  }
}

/**
 * 继续生成
 */
async function handleContinueGeneration(userMessage: string) {
  // 将用户消息添加到对话历史
  conversationHistory.value.push({
    role: 'user',
    content: userMessage
  })

  // 获取参数
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) {
    ElMessage.error('请先设置有效的模型ID')
    return
  }

  try {
    // 获取 Schema 和上下文
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) {
      ElMessage.error('未找到此卡片的结构（Schema）。')
      return
    }

    const editingContent = wrapperName.value ? innerData.value : localData.value
    const currentCardForResolve = { ...props.card, content: editingContent }
    const effectiveTemplate = getResolvedContextTemplateValue()
    const resolvedContext = resolveTemplate({
      template: effectiveTemplate,
      cards: cards.value,
      currentCard: currentCardForResolve as any
    })

    // 继续生成（总是基于现有内容）
    const architectureStepData = buildArchitectureStepGenerationData(props.card, cards.value)
    const requestCurrentData = {
      ...(instructionExecutor.value?.getData() || {}),
      ...architectureStepData
    }
    await performGeneration(userMessage, getGenerationSchema(props.card, effective), resolvedContext, p, requestCurrentData)
  } catch (e) {
    console.error('继续生成失败:', e)
    ElMessage.error('继续生成失败')
  }
}

/**
 * 停止生成
 */
function handleStopGeneration() {
  handleCloseGenerationPanel()
}

/**
 * 重新开始生成
 */
function handleRestartGeneration() {
  // 重置执行器
  const editingContent = wrapperName.value ? innerData.value : localData.value
  instructionExecutor.value = new InstructionExecutor(editingContent || {})

  // 重置对话历史
  conversationHistory.value = []

  // 显示初始提示对话框
  showGenerationPanel.value = false
  showInitialPromptDialog.value = true
}

// ==================== 原有的生成方法（保留作为备用）====================

async function handleGenerate() {
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) { ElMessage.error('请先设置有效的模型ID'); return }
  const editingContent = wrapperName.value ? innerData.value : localData.value
  const currentCardForResolve = { ...props.card, content: editingContent }
  const effectiveTemplate = getResolvedContextTemplateValue()
  const resolvedContext = resolveTemplate({ template: effectiveTemplate, cards: cards.value, currentCard: currentCardForResolve as any })
  try {
    // 直接读取有效 Schema 并作为 response_model_schema 发送
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) { ElMessage.error('未找到此卡片的结构（Schema）。'); return }
    const generationSchema = getGenerationSchema(props.card, effective)
    const sampling = { temperature: p.temperature, max_tokens: p.max_tokens, timeout: p.timeout }
    const result = await aiStore.generateContentWithSchema(generationSchema as any, resolvedContext, p.llm_config_id!, getEffectivePromptName(props.card, p), sampling)
    if (result) {
      const { mergeWith, isArray } = await import('lodash-es')
      const arrayOverwrite = (objValue: any, srcValue: any) => {
        if (isArray(objValue) || isArray(srcValue)) {
          return srcValue
        }
        return undefined
      }
      if (wrapperName.value) {
        const mergedInner = mergeWith({}, innerData.value || {}, result, arrayOverwrite)
        innerData.value = mergedInner
      } else {
        const merged = mergeWith({}, localData.value || {}, result, arrayOverwrite)
        localData.value = merged
      }
      ElMessage.success('内容生成成功！')
    }
  } catch (e) { console.error('AI generation failed:', e) }
}

async function handleRestoreVersion(v: any) {
  showVersions.value = false
  
  // 自定义内容编辑器的恢复逻辑（如 CodeMirrorEditor）
  if (activeContentEditor.value && contentEditorRef.value) {
    try {
      ElMessage.success('已恢复版本，自动保存中...')
      
      // 通知内容编辑器恢复内容（需要编辑器实现 restoreContent 方法）
      if (typeof contentEditorRef.value.restoreContent === 'function') {
        await contentEditorRef.value.restoreContent(v.content)
      }
      
      // 恢复上下文模板
      localAiContextTemplate.value = v.ai_context_template || localAiContextTemplate.value
      
      // 保存恢复的内容
      await handleSave()
      
      // 刷新卡片数据
      await cardStore.fetchCards(projectStore.currentProject!.id!)
      
      ElMessage.success('版本已恢复并保存')
    } catch (e) {
      console.error('Failed to restore content editor version:', e)
      ElMessage.error('恢复版本失败')
    }
    return
  }
  
  // 默认表单编辑器的恢复逻辑
  if (wrapperName.value) innerData.value = v.content
  else localData.value = v.content
  localAiContextTemplate.value = v.ai_context_template || localAiContextTemplate.value
  ElMessage.success('已恢复版本，自动保存中...')
  await handleSave()
}

async function onSchemaSaved() {
  // 保存结构后刷新 schema 并重算分区
  await loadSchemaForCard(props.card)
}

async function handleAssistantFinalize(summary: string) {
  try {
    const p = perCardStore.getByCardId(props.card.id) || editingParams.value
    if (!p?.llm_config_id) { ElMessage.error('请先设置有效的模型ID'); return }
    // 将对话要点与上下文合并，作为输入文本（不再附加卡片提示词模板）
    const editingContent = wrapperName.value ? innerData.value : localData.value
    const currentCardForResolve = { ...props.card, content: editingContent }
    const effectiveTemplate = getResolvedContextTemplateValue()
    const resolvedContextText = resolveTemplate({ template: effectiveTemplate, cards: cards.value, currentCard: currentCardForResolve as any })
    const inputText = `${resolvedContextText}\n\n[对话要点]\n${summary}`
    // 读取有效 Schema
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) { ElMessage.error('未找到此卡片的结构（Schema）。'); return }
    const generationSchema = getGenerationSchema(props.card, effective)
    const sampling = { temperature: p.temperature, max_tokens: p.max_tokens, timeout: p.timeout }
    const result = await aiStore.generateContentWithSchema(generationSchema as any, inputText, p.llm_config_id!, getEffectivePromptName(props.card, p), sampling)
    if (result) {
      const { mergeWith, isArray } = await import('lodash-es')
      const arrayOverwrite = (objValue: any, srcValue: any) => {
        if (isArray(objValue) || isArray(srcValue)) {
          return srcValue
        }
        return undefined
      }
      if (wrapperName.value) {
        const mergedInner = mergeWith({}, innerData.value || {}, result, arrayOverwrite)
        innerData.value = mergedInner
      } else {
        const merged = mergeWith({}, localData.value || {}, result, arrayOverwrite)
        localData.value = merged
      }
      assistantVisible.value = false
      ElMessage.success('定稿生成完成！')
    }
  } catch (e) { console.error('Finalize generate failed:', e) }
}
</script>

<style scoped>
.generic-card-editor { 
  display: flex; 
  flex-direction: column; 
  height: 100%; 
  overflow: hidden; /* 防止整体滚动 */
}

/* 确保自定义内容编辑器（如 CodeMirrorEditor）占据剩余空间 */
.generic-card-editor > :deep(.chapter-studio),
.generic-card-editor > :deep([class*="-editor"]) {
  flex: 1;
  min-height: 0;
}

.editor-body { display: grid; grid-template-columns: 1fr; gap: 0; flex: 1; overflow: hidden; }
.main-pane { overflow: auto; padding: 12px; }
.form-container { display: flex; flex-direction: column; gap: 12px; }
.loading-or-error-container { text-align: center; padding: 2rem; color: var(--el-text-color-secondary); }
.toolbar-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-light); }
.param-toolbar { padding: 6px 12px; border-bottom: 1px solid var(--el-border-color-light); justify-content: flex-end; }
.param-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ai-config-form { padding: 4px 2px; }
/* 固定按钮宽度并对模型名称省略显示 */
:deep(.model-trigger) { width: 230px; min-width: 220px; max-width: 260px; box-sizing: border-box; }
:deep(.model-trigger .el-button__content) { width: 100%; display: inline-flex; align-items: center; gap: 4px; overflow: hidden; }
.model-label { flex: 0 0 auto; }
.model-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; flex-wrap: wrap; }
.ai-actions .left, .ai-actions .right { display: flex; gap: 6px; align-items: center; }
</style> 
