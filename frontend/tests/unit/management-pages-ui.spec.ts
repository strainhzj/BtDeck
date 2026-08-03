import { readFileSync } from 'fs'
import { resolve } from 'path'

const queryTemplatesSource = readFileSync(
  resolve(__dirname, '../../src/views/query-templates/index.vue'),
  'utf8'
)
const orphanFilesSource = readFileSync(
  resolve(__dirname, '../../src/views/orphan-files/index.vue'),
  'utf8'
)
const auditLogsSource = readFileSync(
  resolve(__dirname, '../../src/views/logs/audit.vue'),
  'utf8'
)
const sharedStyles = readFileSync(
  resolve(__dirname, '../../src/styles/management-list-page.scss'),
  'utf8'
)
const appEntrySource = readFileSync(
  resolve(__dirname, '../../src/main.ts'),
  'utf8'
)

describe.each([
  ['查询模板', queryTemplatesSource],
  ['孤儿文件', orphanFilesSource]
])('%s管理页布局契约', (_pageName, source) => {
  it('使用统一的页头、筛选面板和数据面板骨架', () => {
    expect(source).toContain('class="app-container management-page')
    expect(source).toContain('<header class="management-page__header"')
    expect(source).toContain('class="management-filter"')
    expect(source).toContain('class="management-panel__header"')
    expect(source).toContain('class="management-table-scroll')
    expect(source).toContain('class="management-table"')
  })

  it('页头和主要内容区具有可访问的标题关联', () => {
    expect(source).toMatch(/<header[^>]+aria-labelledby="[^"]+"/)
    expect(source).toMatch(/<h1[^>]+class="management-page__title"/)
    expect(source).toMatch(/<section[^>]+aria-labelledby="[^"]+"/)
    expect(source).toMatch(/<h2[^>]+class="management-panel__title"/)
  })
})

describe('查询模板管理页操作分组', () => {
  it('将刷新和新建放在页头，将筛选操作留在筛选面板', () => {
    const header = queryTemplatesSource.match(/<header[\s\S]*?<\/header>/)?.[0] || ''
    const filterPanel = queryTemplatesSource.match(/<!-- 筛选条件 -->[\s\S]*?<\/section>/)?.[0] || ''

    expect(header).toContain('刷新')
    expect(header).toContain('新建模板')
    expect(filterPanel).toContain('搜索')
    expect(filterPanel).not.toContain('新建模板')
  })
})

describe('孤儿文件管理页信息层级', () => {
  it('使用响应式统计摘要，并将清理动作与文件列表放在一起', () => {
    expect(orphanFilesSource).toContain('class="management-stats-grid"')
    expect(orphanFilesSource).toContain('class="management-stat-card"')
    expect(orphanFilesSource).toContain('已选择 {{ selectedCount }} 项')
    expect(orphanFilesSource).toContain('management-pagination')

    const listPanel = orphanFilesSource.match(/<!-- 孤儿文件列表 -->[\s\S]*?<\/section>/)?.[0] || ''
    expect(listPanel).toContain('清理选中')
  })

  it('隔离区表格复用孤儿列表的共享表头样式', () => {
    const quarantinePanel = orphanFilesSource.match(/<!-- 隔离区管理 -->[\s\S]*?<\/el-tab-pane>/)?.[0] || ''
    expect(quarantinePanel).toContain('class="management-table-scroll quarantine-table-scroll"')
    expect(quarantinePanel).toContain('class="management-table"')
  })
})

describe('操作日志搜索与操作栏', () => {
  it('将查询字段和数据操作分成两个主题化面板', () => {
    expect(auditLogsSource).toContain('class="app-container management-page audit-logs-container"')
    expect(auditLogsSource).toContain('class="management-panel audit-filter-panel"')
    expect(auditLogsSource).toContain('class="management-filter audit-filter-grid"')
    expect(auditLogsSource).toContain('class="management-panel audit-action-panel"')
    expect(auditLogsSource).toContain('class="audit-action-bar__actions"')
    expect(auditLogsSource).not.toContain('class="filter-container"')
  })

  it('复制 JSON 使用兼容剪贴板工具且按钮不再使用表情符号', () => {
    expect(auditLogsSource).toContain("import { copyTextToClipboard } from '@/utils/clipboard'")
    expect(auditLogsSource).toContain('await copyTextToClipboard(JSON.stringify(currentLog, null, 2))')
    expect(auditLogsSource).not.toContain('📋 复制JSON')
  })
})

describe('共享管理页样式', () => {
  it('复用主题变量并为窄屏提供表格滚动和栅格降级', () => {
    expect(appEntrySource).toContain("import '@/styles/management-list-page.scss'")
    expect(sharedStyles).toContain('max-width: 1600px;')
    expect(sharedStyles).toContain('overflow-x: auto;')
    expect(sharedStyles).toContain('var(--color-bg-primary)')
    expect(sharedStyles).toContain('var(--spacing-lg)')
    expect(sharedStyles).toContain('@media (max-width: 768px)')
    expect(sharedStyles).toContain('grid-template-columns: repeat(2, minmax(0, 1fr));')
    expect(sharedStyles).toContain('grid-template-columns: 1fr;')
  })
})
