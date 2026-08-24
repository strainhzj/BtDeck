/**
 * M2 模板应用条件缓存（移动端）：
 * 查询模板页「应用」时写入模板 conditions，高级搜索页 mounted 取走执行
 * （简单模板回填简单筛选并 getList；高级模板回填构建器并 advancedSearch）。
 * 内存级、单条、不持久化，take 语义取走即清空（与 torrent-detail-cache 同款约定）。
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
