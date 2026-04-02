<template>
	<div class="ai-param-inline">
		<el-popover placement="bottom" trigger="manual" v-model:visible="visible" width="360">
			<template #reference>
				<el-button type="primary" size="small" class="model-trigger" @click="visible = !visible">
					<template #icon>
						<el-icon><Setting /></el-icon>
					</template>
					<span class="model-label">模型：</span>
					<span class="model-name">{{ selectedModelName || '未设置' }}</span>
				</el-button>
			</template>
			<div class="ai-config-form">
				<el-form label-width="92px" size="small">
					<el-form-item label="模型ID">
						<el-select v-model="editing.llm_config_id" placeholder="选择模型" style="width: 240px;" :teleported="false">
							<el-option v-for="m in (aiOptions?.llm_configs || [])" :key="m.id" :label="m.display_name || String(m.id)" :value="Number(m.id)" />
						</el-select>
					</el-form-item>
					<el-form-item label="提示词">
						<el-select v-model="editing.prompt_name" placeholder="选择提示词" filterable style="width: 240px;" :teleported="false">
							<el-option
								v-for="p in (aiOptions?.prompts || [])"
								:key="p.id"
								:label="getPromptOptionLabel(p)"
								:value="p.name"
							/>
						</el-select>
					</el-form-item>
					<el-form-item label="温度">
						<el-input-number v-model="editing.temperature" :min="0" :max="2" :step="0.1" />
					</el-form-item>
					<el-form-item label="最大tokens">
						<el-input-number v-model="editing.max_tokens" :min="1" :step="256" />
					</el-form-item>
					<el-form-item label="超时(秒)">
						<el-input-number v-model="editing.timeout" :min="1" :step="5" />
					</el-form-item>
					<el-form-item>
						<div class="ai-actions">
							<div class="left">
								<el-button type="primary" size="small" @click="saveLocal">保存</el-button>
								<el-button size="small" @click="resetToPreset">重置为预设</el-button>
							</div>
							<div class="right">
								<el-button size="small" type="warning" plain @click="restoreFollowType">恢复跟随类型</el-button>
								<el-button size="small" type="primary" plain @click="applyToType">应用到类型</el-button>
							</div>
						</div>
					</el-form-item>
				</el-form>
			</div>
		</el-popover>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { usePerCardAISettingsStore, type PerCardAIParams, getPresetForCardType } from '@renderer/stores/usePerCardAISettingsStore'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import { getCardAIParams, updateCardAIParams, applyCardAIParamsToType } from '@renderer/api/setting'
import { ElMessage } from 'element-plus'

const props = defineProps<{ cardId: number; cardTypeName?: string }>()

const store = usePerCardAISettingsStore()
const visible = ref(false)
const aiOptions = ref<AIConfigOptions | null>(null)
const editing = ref<PerCardAIParams>({})

const PROMPT_DISPLAY_MAP: Record<string, { name: string; description: string }> = {
	'ANG.M0.architecture_step1_mission': {
		name: 'M0 架构步骤1：分卷使命宣言',
		description: '为整部作品定义分卷战略目标与卷级使命。',
	},
	'ANG.M0.architecture_step2_worldview': {
		name: 'M0 架构步骤2：世界观与冲突发生器',
		description: '构建世界规则并生成推动剧情的核心冲突。',
	},
	'ANG.M0.architecture_step3_plot': {
		name: 'M0 架构步骤3：情节线与推进机制',
		description: '设计主线/支线与关键推进节点。',
	},
	'ANG.M0.architecture_step4_character': {
		name: '步骤四：核心角色规划',
		description: '生成服务后续角色建卡的角色规划稿。',
	},
	'ANG.M0.architecture_step5_style': {
		name: 'M0 架构步骤5：叙事风格与文本策略',
		description: '确定叙事口吻、节奏与语言风格约束。',
	},
	'ANG.M0.volume_design_format': {
		name: 'M0 分卷格式模板',
		description: '分卷输出的标准结构模板。',
	},
	'ANG.M0.volume_outline': {
		name: 'M0 首卷分卷大纲',
		description: '生成首卷的卷级剧情与章节级推进方案。',
	},
	'ANG.M0.subsequent_volume': {
		name: 'M0 中间卷分卷大纲',
		description: '生成中间卷递进结构与承接关系。',
	},
	'ANG.M0.final_volume': {
		name: 'M0 终卷收束大纲',
		description: '生成终卷收束路径与主线回收方案。',
	},
	'ANG.M0.chapter_blueprint': {
		name: 'M0 章节目录蓝图',
		description: '将卷级结构拆解为章节目录与每章目标。',
	},
	'ANG.M0.chapter_draft': {
		name: 'M0 章节正文草稿',
		description: '根据章节蓝图生成正文草稿。',
	},
}

function getPromptOptionLabel(prompt: { name: string; description?: string | null }): string {
	const mapped = PROMPT_DISPLAY_MAP[prompt.name]
	if (mapped?.name) return mapped.name
	const desc = (prompt.description || '').trim()
	if (desc) return desc
	return prompt.name
}

async function loadOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }

const saved = computed(() => store.getByCardId(props.cardId))
const selectedModelName = computed(() => {
	try {
		const raw = (saved.value || editing.value)?.llm_config_id as any
		const id = raw == null ? undefined : Number(raw)
		const list = aiOptions.value?.llm_configs || []
		const found = list.find(m => Number(m.id) === id)
		return found?.display_name || (id != null ? String(id) : '')
	} catch { return '' }
})

watch(() => props.cardId, async (id) => {
	if (!id) return
	await loadOptions()
	try {
		const resp = await getCardAIParams(id)
		const eff = (resp as any)?.effective_params
		if (eff && Object.keys(eff).length) {
			const fixed = { ...eff, llm_config_id: eff.llm_config_id == null ? eff.llm_config_id : Number(eff.llm_config_id) }
			editing.value = fixed
			store.setForCard(id, { ...fixed })
			return
		}
	} catch {}
	// fallback to saved or preset
	if (saved.value) {
		const sv = saved.value as any
		editing.value = { ...sv, llm_config_id: sv?.llm_config_id == null ? sv?.llm_config_id : Number(sv.llm_config_id) }
	} else {
		const preset = getPresetForCardType(props.cardTypeName)
		if (!preset.llm_config_id) {
			const first = aiOptions.value?.llm_configs?.[0]; if (first) preset.llm_config_id = Number(first.id)
		}
		editing.value = { ...preset, llm_config_id: preset.llm_config_id == null ? preset.llm_config_id : Number(preset.llm_config_id) }
		store.setForCard(id, editing.value)
	}
}, { immediate: true })

function saveLocal() {
	try {
		const payload = { ...editing.value, llm_config_id: editing.value.llm_config_id == null ? editing.value.llm_config_id : Number(editing.value.llm_config_id) }
		// 先写入后端数据库
		updateCardAIParams(props.cardId, payload)
			.then(() => {
				store.setForCard(props.cardId, { ...payload })
				ElMessage.success('已保存')
				visible.value = false
			})
			.catch(() => { ElMessage.error('保存到后端失败') })
	} catch { ElMessage.error('保存失败') }
}
function resetToPreset() {
	const preset = getPresetForCardType(props.cardTypeName)
	editing.value = { ...preset, llm_config_id: preset.llm_config_id == null ? preset.llm_config_id : Number(preset.llm_config_id) }
	store.setForCard(props.cardId, editing.value)
}
async function restoreFollowType() {
	try { await updateCardAIParams(props.cardId, null); ElMessage.success('已恢复跟随类型'); const resp = await getCardAIParams(props.cardId); const eff = (resp as any)?.effective_params; if (eff) { editing.value = { ...eff }; store.setForCard(props.cardId, { ...eff }) } } catch { ElMessage.error('操作失败') }
}
async function applyToType() {
	try {
		await updateCardAIParams(props.cardId, { ...editing.value })
		await applyCardAIParamsToType(props.cardId)
		window.dispatchEvent(new Event('card-types-updated'))
		await updateCardAIParams(props.cardId, null)
		const resp = await getCardAIParams(props.cardId)
		const eff = (resp as any)?.effective_params
		if (eff) { editing.value = { ...eff }; store.setForCard(props.cardId, { ...eff }) }
		ElMessage.success('已应用到类型，并恢复本卡片跟随类型')
	} catch { ElMessage.error('应用失败') }
}

</script>

<style scoped>
.ai-param-inline { 
  display: inline-flex; 
  align-items: center; 
}

.model-trigger { 
  min-width: 200px;
  max-width: 320px;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  overflow: hidden; /* 确保按钮本身不超出 */
}

.model-trigger :deep(.el-button__content) {
  display: flex;
  align-items: center;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

.model-label { 
  flex-shrink: 0;
  margin-right: 4px;
  font-weight: 500;
}

.model-name { 
  flex: 1; 
  min-width: 0; 
  overflow: hidden; 
  text-overflow: ellipsis; 
  white-space: nowrap;
  text-align: left;
}
</style> 
