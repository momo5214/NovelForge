import { defineStore } from 'pinia'

export interface PerCardAIParams {
  llm_config_id?: number
  prompt_name?: string
  response_model_name?: string
  temperature?: number
  max_tokens?: number
  timeout?: number
}

export const CARD_TYPE_AI_PRESETS: Record<string, PerCardAIParams> = {
  '金手指': { prompt_name: '金手指生成', response_model_name: 'SpecialAbilityResponse', temperature: 0.6, max_tokens: 1024, timeout: 60 },
  '一句话梗概': { prompt_name: '一句话梗概', response_model_name: 'OneSentence', temperature: 0.6, max_tokens: 1024, timeout: 60 },
  '故事大纲': { prompt_name: '一段话大纲', response_model_name: 'ParagraphOverview', temperature: 0.6, max_tokens: 2048, timeout: 60 },
  '世界观设定': { prompt_name: '世界观设定', response_model_name: 'WorldBuilding', temperature: 0.6, max_tokens: 8192, timeout: 120 },
  '核心蓝图': { prompt_name: '核心蓝图', response_model_name: 'Blueprint', temperature: 0.6, max_tokens: 8192, timeout: 120 },
  '分卷大纲': { prompt_name: '分卷大纲', response_model_name: 'VolumeOutline', temperature: 0.6, max_tokens: 8192, timeout: 120 },
  '阶段大纲': { prompt_name: '阶段大纲', response_model_name: 'StageLine', temperature: 0.6, max_tokens: 8192, timeout: 120 },
  '章节大纲': { prompt_name: '章节大纲', response_model_name: 'ChapterOutline', temperature: 0.6, max_tokens: 4096, timeout: 60 },
  '写作指南': { prompt_name: '写作指南', response_model_name: 'WritingGuide', temperature: 0.7, max_tokens: 8192, timeout: 60 },
  '章节正文': { prompt_name: '内容生成', temperature: 0.7, max_tokens: 8192, timeout: 60 },
  '增强章节正文': { prompt_name: '增强章节正文草稿-续写版', temperature: 0.7, max_tokens: 8192, timeout: 60 },
  '小说架构': { prompt_name: '一段话大纲', response_model_name: 'ParagraphOverview', temperature: 0.7, max_tokens: 8192, timeout: 120 },
  '小说架构步骤': { prompt_name: '步骤一-分卷使命宣言', temperature: 0.7, max_tokens: 4096, timeout: 120 },
}

export function getPresetForCardType(typeName?: string): PerCardAIParams {
  return CARD_TYPE_AI_PRESETS[typeName || ''] || {}
}

export const usePerCardAISettingsStore = defineStore('perCardAISettings', {
  state: () => ({
    byCardId: {} as Record<string | number, PerCardAIParams>
  }),

  getters: {
    getByCardId: (state) => {
      return (cardId: string | number | undefined) => {
        if (cardId == null) return undefined
        return state.byCardId[String(cardId)]
      }
    }
  },

  actions: {
    loadFromLocal() {
      try {
        const s = localStorage.getItem('per-card-ai-settings')
        if (s) this.byCardId = JSON.parse(s)
      } catch {}
    },
    saveToLocal() {
      try { localStorage.setItem('per-card-ai-settings', JSON.stringify(this.byCardId)) } catch {}
    },
    setForCard(cardId: string | number, params: PerCardAIParams) {
      this.byCardId[String(cardId)] = { ...(this.byCardId[String(cardId)] || {}), ...params }
      this.saveToLocal()
    },
    removeForCard(cardId: string | number) {
      delete this.byCardId[String(cardId)]
      this.saveToLocal()
    }
  }
}) 
