/**
 * 移动审计日志契约（Phase 4 M2）：卡片流 + 操作类型/结果/种子名筛选 + 分页；
 * 统计与导出保留桌面版。交互直调组件方法。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileLogs from '@/views/mobile/logs.vue'
import { queryAuditLogs, getOperationTypes } from '@/api/audit-logs'

jest.mock('@/api/audit-logs', () => ({
  queryAuditLogs: jest.fn(),
  getOperationTypes: jest.fn()
}))

const mockedLogs = [
  {
    log_id: 'L1',
    torrent_info_id: 'i1',
    operation_type: 'delete',
    operation_detail: '删除种子并移入回收站',
    old_value: null,
    new_value: null,
    operator: 'admin',
    operation_time: '2026-08-22T10:00:00',
    operation_result: 'success',
    error_message: null,
    downloader_id: 'd1',
    create_time: '2026-08-22T10:00:00',
    ip_address: '127.0.0.1',
    user_agent: null,
    request_id: null,
    session_id: null,
    torrent_name: '示例种子',
    downloader_name: 'qb'
  },
  {
    log_id: 'L2',
    torrent_info_id: null,
    operation_type: 'sync',
    operation_detail: '同步下载器失败',
    old_value: null,
    new_value: null,
    operator: 'system',
    operation_time: '2026-08-22T11:00:00',
    operation_result: 'failure',
    error_message: '连接超时',
    downloader_id: null,
    create_time: '2026-08-22T11:00:00',
    ip_address: null,
    user_agent: null,
    request_id: null,
    session_id: null,
    torrent_name: null,
    downloader_name: null
  }
]

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileLogs, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileLogs', () => {
  beforeEach(() => {
    jest.mocked(queryAuditLogs).mockReset()
    jest.mocked(queryAuditLogs).mockResolvedValue({
      code: '200',
      data: { total: 2, page: 1, pageSize: 20, list: mockedLogs }
    } as never)
    jest.mocked(getOperationTypes).mockReset()
    jest.mocked(getOperationTypes).mockResolvedValue({
      code: '200',
      data: [{ value: 'delete', display_name: '删除种子', category: 'torrent' }]
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('卡片渲染：类型标签（display_name 映射）/结果着色/种子名/错误信息/操作人', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('删除种子')
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('连接超时')
    expect(wrapper.text()).toContain('示例种子')
    expect(wrapper.text()).toContain('admin')
    expect(wrapper.text()).toContain('127.0.0.1')
  })

  it('空结果显示空态', async() => {
    jest.mocked(queryAuditLogs).mockResolvedValue({
      code: '200',
      data: { total: 0, page: 1, pageSize: 20, list: [] }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('没有匹配的审计日志')
  })

  it('筛选条件透传：类型/结果/种子名', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.typeFilter = 'delete'
    vm.resultFilter = 'failure'
    vm.nameFilter = '示例'
    await vm.reload()
    expect(queryAuditLogs).toHaveBeenLastCalledWith(expect.objectContaining({
      operation_type: 'delete',
      operation_result: 'failure',
      torrent_name: '示例'
    }))
  })

  it('点击卡片切换详情展开态', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.toggleExpand(mockedLogs[0])
    expect(vm.expandedId).toBe('L1')
    vm.toggleExpand(mockedLogs[0])
    expect(vm.expandedId).toBe('')
  })

  it('分页：加载更多递增页码', async() => {
    jest.mocked(queryAuditLogs).mockResolvedValue({
      code: '200',
      data: { total: 40, page: 1, pageSize: 20, list: mockedLogs }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadMore()
    expect(queryAuditLogs).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })
})
