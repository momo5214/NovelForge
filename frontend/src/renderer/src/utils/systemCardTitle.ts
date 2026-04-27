const exactTitleMap = new Map<string, string>([
  ['系统开关/步骤四规划转角色卡', '系统开关/步骤四规划转角色卡'],
  ['系统开关/步骤四自动生成角色卡', '系统开关/步骤四自动生成角色卡'],
  ['系统开关/步骤二自动生成组织卡', '系统开关/步骤二自动生成组织卡'],
  ['伏笔管理/总台账', '伏笔管理/总台账'],
  ['伏笔管理/未回收台账', '伏笔管理/未回收台账'],
])

function normalizeChapterScopedTitle(prefix: string, chapter: string, rawTitle: string): string {
  const title = String(rawTitle || '').trim()
  if (!title) return `${prefix}-第${chapter}章`
  const duplicatedPrefix = new RegExp(`^第${chapter}章(?:[\\s\\-:：、.．]*)`)
  const normalizedTitle = title.replace(duplicatedPrefix, '').trim() || title
  return `${prefix}-第${chapter}章-${normalizedTitle}`
}

const regexTitleRules: Array<[RegExp, (...args: string[]) => string]> = [
  [/^一致性审校-第(\d+)章-(.+)$/, (chapter, title) => normalizeChapterScopedTitle('一致性审校', chapter, title)],
  [/^伏笔治理-第(\d+)章-(.+)$/, (chapter, title) => normalizeChapterScopedTitle('伏笔治理', chapter, title)],
  [/^剧情要点-第(\d+)章-(.+)$/, (chapter, title) => normalizeChapterScopedTitle('剧情要点', chapter, title)],
]

export function isSystemCardTitle(title?: string | null): boolean {
  const raw = String(title || '').trim()
  if (!raw) return false
  if (exactTitleMap.has(raw)) return true
  return regexTitleRules.some(([pattern]) => pattern.test(raw))
}

export function getSystemCardDisplayTitle(title?: string | null): string {
  const raw = String(title || '').trim()
  if (!raw) return ''

  const exact = exactTitleMap.get(raw)
  if (exact) return exact

  for (const [pattern, formatter] of regexTitleRules) {
    const match = raw.match(pattern)
    if (match) {
      return formatter(...match.slice(1))
    }
  }

  return raw
}
