/**
 * M2 模板应用条件缓存（移动端）：
 * 查询模板页「应用」时写入模板 conditions，执行页 mounted 取走执行——
 * 简单模板由种子页（/m/torrents）回填筛选并 getList；
 * 高级模板由高级搜索页（/m/search）回填构建器并 advancedSearch。
 * 内存级、单条、不持久化，take 语义取走即清空（与 torrent-detail-cache 同款约定）；
 * 两执行页遇来源不符的模板会交回缓存并跳转到对端页面。
 */
import { QueryTemplateConditions } from '@/api/torrents'

let cached: { conditions: QueryTemplateConditions, templateName: string } | null = null

export function setAppliedTemplateConditions(conditions: QueryTemplateConditions, templateName: string): void {
  cached = { conditions, templateName }
}

export function takeAppliedTemplateConditions(): { conditions: QueryTemplateConditions, templateName: string } | null {
  const snapshot = cached
  cached = null
  return snapshot
}
