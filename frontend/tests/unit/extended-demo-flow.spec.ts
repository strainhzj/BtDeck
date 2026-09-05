import {
  getMessageStatistics,
  getPoolKeywords,
  getPoolStatistics,
  keywordPrefixMatchPreview,
  moveKeywordToPool,
  searchAllPools,
  testMatch
} from '@/api/tracker'
import {
  getTaskList,
  getTaskLogStatistics,
  getTaskLogs,
  validateCronExpression
} from '@/api/tasks'
import { archiveAuditLogs, exportAuditLogs, queryAuditLogs } from '@/api/audit-logs'
import {
  cleanupPreview as cleanupOrphanPreview,
  getHardlinkCopyLocations,
  getOrphanList,
  getQuarantineList,
  getScanStatus,
  prefixMatchPreview,
  triggerScan
} from '@/api/orphan-files'
import { demoStore } from '@/demo/demo-store'

describe('extended and read-only demo flow', () => {
  const originalDemoMode = process.env.VUE_APP_DEMO_MODE

  beforeEach(() => {
    demoStore.reset()
    process.env.VUE_APP_DEMO_MODE = 'true'
  })

  afterEach(() => {
    if (originalDemoMode === undefined) {
      delete process.env.VUE_APP_DEMO_MODE
    } else {
      process.env.VUE_APP_DEMO_MODE = originalDemoMode
    }
  })

  it('serves tracker pools, search, match and message statistics locally', async() => {
    const pools = await getPoolStatistics()
    expect(pools.data.candidate_count).toBeGreaterThan(0)

    const candidate = await getPoolKeywords({ pool_type: 'candidate', page: 1, page_size: 20 })
    expect(candidate.data.list[0].pool_type).toBe('candidate')

    const prefix = await keywordPrefixMatchPreview({ pool_type: 'candidate', prefix: '演示' })
    expect(prefix.data.keyword_ids.length).toBeGreaterThan(0)
    const moved = await moveKeywordToPool({ keyword_id: prefix.data.keyword_ids[0], target_pool: 'success' })
    expect(moved.data.success).toBe(true)

    const search = await searchAllPools({ keyword: '演示', page: 1, page_size: 20 })
    expect(search.data.list.every(item => item.pool_label)).toBe(true)
    expect((await testMatch({ tracker_host: 'tracker.example.invalid', msg: '演示消息' })).data.result).toBe('success')
    expect((await getMessageStatistics()).data.unprocessed).toBe(1)
  })

  it('keeps task pages and validation responses renderable without execution', async() => {
    const tasks = await getTaskList({ skip: 0, limit: 20 })
    expect(tasks.data.list?.length).toBeGreaterThan(0)
    const logs = await getTaskLogs({ skip: 0, limit: 20 })
    expect(logs.data.list?.[0].taskName).toContain('演示')
    expect((await getTaskLogStatistics()).data.total_logs).toBeGreaterThan(0)
    const validation = await validateCronExpression({ expression: '0 * * * *' })
    expect(validation.data.valid).toBe(true)
  })

  it('returns complete audit export/archive contracts', async() => {
    const logs = await queryAuditLogs({ page: 1, page_size: 20 })
    expect(logs.data.list.length).toBeGreaterThan(0)
    const exported = await exportAuditLogs({ export_format: 'csv', max_rows: 100 })
    expect(exported.data.file_path).toContain('/demo/')
    expect(exported.data.file_format).toBe('csv')
    const archived = await archiveAuditLogs({ end_time: '2026-09-01T00:00:00+08:00' })
    expect(archived.data.success).toBe(true)
    expect(archived.data.archived_count).toBe(logs.data.total)
  })

  it('exposes safe orphan scan, cleanup preview and quarantine shapes', async() => {
    const list = await getOrphanList({ page: 1, page_size: 20 })
    expect(list.data.scan_context.display_scan?.status).toBe('completed')
    expect(list.data.list).toHaveLength(3)

    const scan = await triggerScan()
    expect(scan.data.task_id).toBeDefined()
    expect((await getScanStatus(scan.data.scan_id)).data.total_orphans).toBeGreaterThan(0)

    const selected = list.data.list.find(item => !('_is_folder' in item) && !item.is_ignored)
    expect(selected).toBeDefined()
    if (!selected || '_is_folder' in selected) return

    const preview = await cleanupOrphanPreview({ scan_id: 'demo-scan-001', orphan_ids: [selected.id] })
    expect(preview.data.total_count).toBe(1)
    expect(preview.data.items[0].file_path).toBe(selected.file_path)
    const prefix = await prefixMatchPreview({ path_prefix: '/demo/', scan_id: 'demo-scan-001' })
    expect(prefix.data.count).toBeGreaterThan(0)
    const copies = await getHardlinkCopyLocations({ orphan_ids: [selected.id] })
    expect(copies.data.items).toHaveLength(1)
    expect((await getQuarantineList({ page: 1, page_size: 20 })).data.list).toEqual([])
  })
})
