const CARD_TYPE_DISPLAY_NAME_MAP: Record<string, string> = {
  '增强核心蓝图': '核心蓝图',
  '增强分卷大纲': '分卷大纲',
  '增强写作指南': '写作指南',
  '增强阶段大纲': '阶段大纲',
  '增强章节拆解': '章节拆解',
  '增强章节大纲': '章节大纲',
  '增强章节正文': '章节正文'
}

export function getCardTypeDisplayName(typeName?: string | null): string {
  const key = (typeName || '').trim()
  if (!key) return ''
  return CARD_TYPE_DISPLAY_NAME_MAP[key] || key
}
