import { getSyncTaskStatus, SyncTaskStatusData } from '@/api/downloader'
import {
  buildSyncTaskNotice,
  trackSyncTaskStatus
} from '@/views/downloader/sync-task'

jest.mock('@/api/downloader', () => ({
  getSyncTaskStatus: jest.fn()
}))

const mockedGetSyncTaskStatus = jest.mocked(getSyncTaskStatus)

function makeTask(overrides: Partial<SyncTaskStatusData> = {}): SyncTaskStatusData {
  return {
    task_id: 'sync_001',
    task_type: 'sync',
    downloader_id: 'dl-1',
    downloader_nickname: '主力 QB',
    status: 'running',
    created_at: '2026-08-30T00:00:00',
    started_at: '2026-08-30T00:00:01',
    finished_at: null,
    progress: 0,
    result: null,
    error: null,
    execution_time: null,
    ...overrides
  }
}

async function flushPromises(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

describe('下载器异步同步任务跟踪', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    mockedGetSyncTaskStatus.mockReset()
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
  })

  it('pending/running 期间持续轮询，直到真实 success 终态才完成', async() => {
    const terminal = makeTask({
      status: 'success',
      progress: 100,
      result: { status: 'success', outcome: 'success', message: '同步完成：1 个下载器全部成功' }
    })
    mockedGetSyncTaskStatus
      .mockResolvedValueOnce({ code: '200', status: 'success', msg: '查询成功', data: makeTask() })
      .mockResolvedValueOnce({ code: '200', status: 'success', msg: '查询成功', data: terminal })
    const onTerminal = jest.fn()

    trackSyncTaskStatus('sync_001', {
      intervalMs: 100,
      maxAttempts: 5,
      onTerminal,
      onTimeout: jest.fn(),
      onError: jest.fn()
    })

    jest.advanceTimersByTime(0)
    await flushPromises()
    expect(onTerminal).not.toHaveBeenCalled()
    expect(mockedGetSyncTaskStatus).toHaveBeenCalledTimes(1)

    jest.advanceTimersByTime(100)
    await flushPromises()
    expect(onTerminal).toHaveBeenCalledWith(terminal)
    expect(mockedGetSyncTaskStatus).toHaveBeenCalledTimes(2)
  })

  it('cancel 会清理待执行 timer，组件销毁后不再请求状态', async() => {
    mockedGetSyncTaskStatus.mockResolvedValue({
      code: '200', status: 'success', msg: '查询成功', data: makeTask()
    })

    const handle = trackSyncTaskStatus('sync_001', {
      intervalMs: 100,
      onTerminal: jest.fn(),
      onTimeout: jest.fn(),
      onError: jest.fn()
    })
    handle.cancel()
    jest.runOnlyPendingTimers()
    await flushPromises()

    expect(mockedGetSyncTaskStatus).not.toHaveBeenCalled()
  })

  it('连续查询失败达到上限后交给页面释放同步态', async() => {
    mockedGetSyncTaskStatus.mockRejectedValue(new Error('status unavailable'))
    const onError = jest.fn()

    trackSyncTaskStatus('sync_001', {
      intervalMs: 100,
      maxAttempts: 5,
      maxConsecutiveErrors: 2,
      onTerminal: jest.fn(),
      onTimeout: jest.fn(),
      onError
    })

    jest.advanceTimersByTime(0)
    await flushPromises()
    jest.advanceTimersByTime(100)
    await flushPromises()

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'status unavailable' }))
  })

  it('按 result.outcome 区分部分完成，不把后台失败结果提示为完成', () => {
    expect(buildSyncTaskNotice(makeTask({
      status: 'failed',
      result: { status: 'failed', outcome: 'partial', message: '同步完成：1 成功，1 失败' }
    }), '备用名称')).toEqual({
      level: 'warning',
      message: '主力 QB 同步部分完成：同步完成：1 成功，1 失败'
    })

    expect(buildSyncTaskNotice(makeTask({
      status: 'failed',
      result: { status: 'failed', outcome: 'failed', message: '下载器 RPC 不可用' }
    }), '备用名称')).toEqual({
      level: 'error',
      message: '主力 QB 同步失败：下载器 RPC 不可用'
    })
  })
})
