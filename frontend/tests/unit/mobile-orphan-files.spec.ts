/**
 * 移动孤儿文件契约（Phase 4 M4）：双 Tab（孤儿文件/隔离区）；
 * 清理走桌面同款两段式（cleanupPreview 预览 → 确认 cleanupOrphans，
 * rejected/空结果分支提示）；忽视/取消忽视；隔离区单条恢复与立即清除
 * （强确认，用户拍板含清除）；扫描确认 → 提交 → 轮询。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileOrphanFiles from '@/views/mobile/orphan-files.vue'
import {
  getOrphanList,
  getQuarantineList,
  restoreQuarantined,
  purgeQuarantineNow,
  triggerScan,
  getScanStatus,
  cleanupPreview,
  cleanupOrphans,
  setIgnored,
  OrphanFileItem,
  QuarantineItem,
  OrphanScanContext
} from '@/api/orphan-files'

jest.mock('@/api/orphan-files', () => ({
  getOrphanList: jest.fn(),
  getQuarantineList: jest.fn(),
  restoreQuarantined: jest.fn(),
  purgeQuarantineNow: jest.fn(),
  triggerScan: jest.fn(),
  getScanStatus: jest.fn(),
  cleanupPreview: jest.fn(),
  cleanupOrphans: jest.fn(),
  setIgnored: jest.fn()
}))

const scanContext: OrphanScanContext = {
  latest_attempt: null,
  display_scan: {
    scan_id: 'scan-1',
    scan_time: '2026-08-24T10:00:00',
    scan_type: 'manual',
    total_paths_scanned: 100,
    total_files_scanned: 100,
    total_orphans: 3,
    total_orphan_size: 1024,
    status: 'completed',
    error_message: null,
    operator: 'admin',
    details_mode: 'snapshot',
    new_orphans: 1,
    known_orphans: 2,
    resolved_orphans: 0,
    cleanup_review_required: false,
    cleanup_reviewed_at: null,
    cleanup_reviewed_by: null,
    cleanup_review_note: null,
    created_at: null
  },
  remaining_count: 2,
  remaining_size: 512,
  ignored_count: 1,
  cleanup_allowed: true,
  cleanup_block_reason: null
}

const mockedOrphans: OrphanFileItem[] = [
  {
    id: 1,
    scan_id: 'scan-1',
    file_path: '/downloads/anime/EP01.mkv',
    file_size: 512,
    hardlink_copy_count: 2,
    mtime: '2026-08-01T00:00:00',
    downloader_id: 'd1',
    confidence: 'high',
    canonical_path: null,
    downloader_name: 'qb',
    is_ignored: false,
    ignored_at: null,
    ignored_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: null
  },
  {
    id: 2,
    scan_id: 'scan-1',
    file_path: '/downloads/tmp/EP02.mkv',
    file_size: 256,
    hardlink_copy_count: null,
    mtime: null,
    downloader_id: null,
    confidence: 'low',
    canonical_path: null,
    downloader_name: null,
    is_ignored: true,
    ignored_at: '2026-08-20T00:00:00',
    ignored_by: 'admin',
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: null
  }
]

const mockedQuarantine: QuarantineItem[] = [
  {
    canonical_path: '/downloads/anime/EP03.mkv',
    downloader_id: 'd1',
    downloader_name: 'qb',
    quarantine_path: '/quarantine/EP03.mkv',
    quarantine_root: '/quarantine',
    mtime: null,
    quarantined_at: '2026-08-22T00:00:00',
    purge_after: '2026-08-29T00:00:00',
    purge_delay_count: 1,
    file_size: 128,
    confidence: 'high'
  }
]

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileOrphanFiles, {
    mocks: {
      $route: { path: '/m/orphan-files', query: {} },
      $router: { push: jest.fn(), replace: jest.fn() },
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm')
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileOrphanFiles', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    jest.mocked(getOrphanList).mockReset()
    jest.mocked(getOrphanList).mockResolvedValue({
      code: '200',
      data: {
        total: 2,
        page: 1,
        pageSize: 20,
        list: mockedOrphans,
        scan_context: scanContext
      }
    } as never)
    jest.mocked(getQuarantineList).mockReset()
    jest.mocked(getQuarantineList).mockResolvedValue({
      code: '200',
      data: { total: 1, page: 1, pageSize: 20, list: mockedQuarantine }
    } as never)
    jest.mocked(restoreQuarantined).mockReset()
    jest.mocked(restoreQuarantined).mockResolvedValue({
      code: '200',
      data: { restored_count: 1, failed_count: 0, failed_list: [] }
    } as never)
    jest.mocked(purgeQuarantineNow).mockReset()
    jest.mocked(purgeQuarantineNow).mockResolvedValue({
      code: '200',
      data: {
        task_id: 'task-abcd1234',
        status: 'pending',
        total_count: 1,
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        error_message: null,
        created_at: null,
        started_at: null,
        completed_at: null
      }
    } as never)
    jest.mocked(triggerScan).mockReset()
    jest.mocked(getScanStatus).mockReset()
    jest.mocked(cleanupPreview).mockReset()
    jest.mocked(cleanupPreview).mockResolvedValue({
      code: '200',
      data: {
        total_count: 1,
        total_size: 512,
        low_confidence_count: 0,
        items: [{ id: 1, file_path: '/downloads/anime/EP01.mkv', file_size: 512 }]
      }
    } as never)
    jest.mocked(cleanupOrphans).mockReset()
    jest.mocked(cleanupOrphans).mockResolvedValue({
      code: '200',
      data: {
        task_id: 'task-ef567890',
        status: 'pending',
        requested_count: 1,
        accepted_count: 1,
        skipped_count: 0,
        skipped_items: [],
        failed_list: [],
        failed_count: 0
      }
    } as never)
    jest.mocked(setIgnored).mockReset()
    jest.mocked(setIgnored).mockResolvedValue({
      code: '200',
      data: { success_count: 1, failed_count: 0, failed_list: [] }
    } as never)
  })

  afterEach(() => {
    jest.useRealTimers()
    jest.clearAllMocks()
  })

  it('孤儿文件 Tab：扫描上下文卡 + 卡片（状态三态/置信度/副本徽标）+ 筛选', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('最近扫描：2026-08-24 10:00:00')
    expect(wrapper.text()).toContain('待清理 2 个')
    expect(wrapper.text()).toContain('已忽视 1')
    expect(wrapper.text()).toContain('/downloads/anime/EP01.mkv')
    expect(wrapper.text()).toContain('待清理')
    expect(wrapper.text()).toContain('已忽视')
    expect(wrapper.text()).toContain('高置信度')
    expect(wrapper.text()).toContain('低置信度')
    expect(wrapper.text()).toContain('副本 2')
    expect(wrapper.text()).toContain('qb')
  })

  it('筛选透传：状态/置信度/路径', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.statusFilter = 'pending'
    vm.confidenceFilter = 'low'
    vm.pathFilter = 'tmp'
    await vm.reloadOrphans()
    expect(getOrphanList).toHaveBeenLastCalledWith(expect.objectContaining({
      status: 'pending',
      confidence: 'low',
      path_like: 'tmp'
    }))
  })

  it('两段式清理：预览成功 → 确认框含条数/大小 → cleanupOrphans 同载荷', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.cleanupOne(mockedOrphans[0])
    await flushLifecycle()
    expect(cleanupPreview).toHaveBeenCalledWith({ scan_id: 'scan-1', orphan_ids: [1] })
    expect(wrapper.vm.$confirm).toHaveBeenCalledWith(
      expect.stringContaining('清理 1 个文件'),
      '清理确认',
      expect.anything()
    )
    expect(cleanupOrphans).toHaveBeenCalledWith({ scan_id: 'scan-1', orphan_ids: [1] })
    // task_id 提示截前 8 位（与桌面端一致）
    expect(wrapper.vm.$message.success).toHaveBeenCalledWith(expect.stringContaining('task-ef5'))
  })

  it('清理分支：预览空结果给针对性提示且不执行；rejected 报错并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(cleanupPreview).mockResolvedValue({
      code: '200',
      data: { total_count: 0, total_size: 0, items: [] }
    } as never)
    await vm.cleanupOne(mockedOrphans[0])
    expect(cleanupOrphans).not.toHaveBeenCalled()
    expect(wrapper.vm.$message.warning).toHaveBeenCalledWith(expect.stringContaining('无可清理项'))

    jest.mocked(cleanupPreview).mockResolvedValue({
      code: '200',
      data: { rejected: true, reason: 'stale scan', error: '扫描批次已过期', total_count: 0, total_size: 0, items: [] }
    } as never)
    await vm.cleanupOne(mockedOrphans[0])
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('扫描批次已过期')
  })

  it('门禁拦截：cleanup_allowed=false 时提示 block_reason 不调预览', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.scanContext = { ...scanContext, cleanup_allowed: false, cleanup_block_reason: '最新扫描未完成' }
    await vm.cleanupOne(mockedOrphans[0])
    expect(cleanupPreview).not.toHaveBeenCalled()
    expect(wrapper.vm.$message.warning).toHaveBeenCalledWith('最新扫描未完成')
  })

  it('忽视/取消忽视：setIgnored 单条载荷（含 scan_id），结果分支提示', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.applyIgnore(mockedOrphans[0], true)
    expect(setIgnored).toHaveBeenCalledWith({ scan_id: 'scan-1', orphan_ids: [1], ignored: true })
    expect(wrapper.vm.$message.success).toHaveBeenCalled()

    jest.mocked(setIgnored).mockResolvedValue({
      code: '200',
      data: { rejected: true, error: '批次已过期', success_count: 0, failed_count: 1, failed_list: [] }
    } as never)
    await vm.applyIgnore(mockedOrphans[1], false)
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith(expect.stringContaining('批次已过期'))
  })

  it('扫描：确认 → triggerScan → 轮询至完成提示并刷新（fake timers）', async() => {
    const baseScan = scanContext.display_scan
    if (!baseScan) throw new Error('测试前置失败：display_scan 为空')
    jest.mocked(getScanStatus)
      .mockResolvedValueOnce({ code: '200', data: { ...baseScan, status: 'running' } } as never)
      .mockResolvedValue({
        code: '200',
        data: { ...baseScan, status: 'completed', total_orphans: 3, new_orphans: 1, known_orphans: 2 }
      } as never)
    jest.mocked(triggerScan).mockResolvedValue({
      code: '200',
      data: { scan_id: 'scan-2', task_id: 't1', status: 'queued', accepted: true }
    } as never)

    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.handleScan()
    await flushLifecycle()
    // 第一次轮询 running → 2s 后再轮询 → completed
    jest.advanceTimersByTime(2100)
    await flushLifecycle()
    expect(getScanStatus).toHaveBeenCalledWith('scan-2')
    expect(wrapper.vm.$message.success).toHaveBeenCalledWith(expect.stringContaining('扫描完成：孤儿 3'))
    expect(vm.scanRunning).toBe(false)
  })

  it('隔离区 Tab：切 Tab 加载卡片，单条恢复与立即清除（强确认文案）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.switchTab('quarantine')
    await flushLifecycle()
    expect(getQuarantineList).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
    expect(wrapper.text()).toContain('/downloads/anime/EP03.mkv')
    expect(wrapper.text()).toContain('预计清除：2026-08-29 00:00:00')
    expect(wrapper.text()).toContain('延迟 1 次')

    await vm.confirmRestore(mockedQuarantine[0])
    await flushLifecycle()
    expect(restoreQuarantined).toHaveBeenCalledWith({ canonical_paths: ['/downloads/anime/EP03.mkv'] })
    expect(wrapper.vm.$message.success).toHaveBeenCalledWith(expect.stringContaining('恢复完成'))

    await vm.confirmPurge(mockedQuarantine[0])
    await flushLifecycle()
    expect(purgeQuarantineNow).toHaveBeenCalledWith({ canonical_paths: ['/downloads/anime/EP03.mkv'] })
    expect(wrapper.vm.$message.success).toHaveBeenCalledWith(expect.stringContaining('task-abc'))
    // 强确认文案含「不可恢复」
    const confirmCalls = (wrapper.vm.$confirm as jest.Mock).mock.calls
    expect(confirmCalls.some((c) => String(c[0]).includes('不可恢复'))).toBe(true)
  })

  it('隔离区分支：rejected 恢复报原因；already_running 清除提示已处理', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.activeTab = 'quarantine'
    await flushLifecycle()

    jest.mocked(restoreQuarantined).mockResolvedValue({
      code: '200',
      data: {
        rejected: true,
        restored_count: 0,
        failed_count: 1,
        failed_list: [{ canonical_path: '/x', reason: '原位置被占用' }]
      }
    } as never)
    await vm.restoreOne(mockedQuarantine[0])
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('原位置被占用')

    jest.mocked(purgeQuarantineNow).mockResolvedValue({
      code: '200',
      data: {
        task_id: null,
        status: 'already_running',
        total_count: 1,
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        error_message: null,
        created_at: null,
        started_at: null,
        completed_at: null
      }
    } as never)
    await vm.purgeOne(mockedQuarantine[0])
    expect(wrapper.vm.$message.info).toHaveBeenCalledWith(expect.stringContaining('已在彻底删除任务中处理'))
  })

  it('分页：孤儿文件与隔离区页码各自递增', async() => {
    jest.mocked(getOrphanList).mockResolvedValue({
      code: '200',
      data: { total: 40, page: 1, pageSize: 20, list: mockedOrphans, scan_context: scanContext }
    } as never)
    jest.mocked(getQuarantineList).mockResolvedValue({
      code: '200',
      data: { total: 40, page: 1, pageSize: 20, list: mockedQuarantine }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadMoreOrphans()
    expect(getOrphanList).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    // 隔离区先切 Tab 加载第一页，再加载更多递增页码
    vm.switchTab('quarantine')
    await flushLifecycle()
    await vm.loadMoreQuarantine()
    expect(getQuarantineList).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })
})
