/**
 * 移动定时任务契约（Phase 4 M3）：任务卡片流 + 启用/名称筛选；
 * 操作集为立即执行（禁用任务拦截）/启停（PUT 部分更新 enabled）/中断/删除；
 * 最近结果六态与数据陈旧语义复用 api/tasks 桌面同源工具函数。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileTasks from '@/views/mobile/tasks.vue'
import {
  getTaskList,
  executeTask,
  updateTask,
  interruptTask,
  deleteTasks,
  ScheduledTask
} from '@/api/tasks'

jest.mock('@/api/tasks', () => {
  const actual = jest.requireActual('@/api/tasks')
  return {
    ...actual,
    getTaskList: jest.fn(),
    executeTask: jest.fn(),
    updateTask: jest.fn(),
    interruptTask: jest.fn(),
    deleteTasks: jest.fn()
  }
})

const makeTask = (overrides: Partial<ScheduledTask> = {}): ScheduledTask => ({
  taskId: 7,
  taskName: '回收站自动清理',
  taskCode: 'recycle_cleanup',
  taskStatus: 2,
  taskType: 5,
  taskTypeName: '清理回收站',
  executor: '{}',
  cronPlan: '0 3 * * *',
  enabled: true,
  taskStatusName: '空闲',
  lastExecuteTime: '2026-08-23T03:00:00',
  lastExecuteDuration: 12,
  createTime: '2026-08-01T00:00:00',
  updateTime: '2026-08-22T00:00:00',
  description: '每日凌晨清理回收站过期种子',
  ...overrides
})

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileTasks, {
    mocks: {
      $route: { path: '/m/tasks', query: {} },
      $router: { push: jest.fn(), replace: jest.fn() },
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm')
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileTasks', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    jest.mocked(getTaskList).mockReset()
    jest.mocked(getTaskList).mockResolvedValue({
      code: '200',
      data: { total: 1, list: [makeTask()] }
    } as never)
    jest.mocked(executeTask).mockReset()
    jest.mocked(executeTask).mockResolvedValue({ code: '200' } as never)
    jest.mocked(updateTask).mockReset()
    jest.mocked(updateTask).mockResolvedValue({ code: '200', msg: '' } as never)
    jest.mocked(interruptTask).mockReset()
    jest.mocked(interruptTask).mockResolvedValue({ code: '200', msg: '' } as never)
    jest.mocked(deleteTasks).mockReset()
    jest.mocked(deleteTasks).mockResolvedValue({ code: '200' } as never)
  })

  afterEach(() => {
    jest.useRealTimers()
    jest.clearAllMocks()
  })

  it('卡片渲染：状态/类型/cron/名称/描述/启用标记', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('回收站自动清理')
    expect(wrapper.text()).toContain('清理回收站')
    expect(wrapper.text()).toContain('0 3 * * *')
    expect(wrapper.text()).toContain('空闲')
    expect(wrapper.text()).toContain('已启用')
    expect(wrapper.text()).toContain('每日凌晨清理回收站过期种子')
    expect(wrapper.text()).toContain('上次执行：2026-08-23 03:00:00')
  })

  it('最近结果六态：partial 展示「部分成功」而非折叠失败（api/tasks 同源映射）', async() => {
    jest.mocked(getTaskList).mockResolvedValue({
      code: '200',
      data: {
        total: 2,
        list: [
          makeTask({ taskId: 1, lastOutcome: 'partial' }),
          makeTask({ taskId: 2, lastOutcome: 'skipped' })
        ]
      }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('部分成功')
    expect(wrapper.text()).toContain('已跳过')
    const vm = wrapper.vm as any
    expect(vm.outcomeMeta('failed')).toMatchObject({ text: '失败' })
    expect(vm.outcomeMeta('no_action')).toMatchObject({ text: '无变化' })
    expect(vm.outcomeMeta(undefined)).toBeNull()
  })

  it('数据陈旧语义：stale 标记展示告警并复用桌面工具文案', async() => {
    const task = makeTask({ stale: true, lastSuccessfulDataAt: null, lastAttemptAt: '2026-08-23T03:00:00' })
    jest.mocked(getTaskList).mockResolvedValue({
      code: '200',
      data: { total: 1, list: [task] }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('数据陈旧')
    const vm = wrapper.vm as any
    expect(vm.staleText(task)).toContain('2026-08-23T03:00:00')
    // 无成功数据 + 已有尝试 → 陈旧（isTaskDataStale 语义透传）
    expect(vm.isStale(task)).toBe(true)
    expect(vm.isStale(makeTask({ stale: false, lastSuccessfulDataAt: '2026-08-23T03:00:00' }))).toBe(false)
  })

  it('筛选透传：启用状态与任务名称', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.enabledFilter = false
    vm.nameFilter = '清理'
    await vm.reload()
    expect(getTaskList).toHaveBeenLastCalledWith(expect.objectContaining({
      enabled: false,
      task_name: '清理'
    }))
  })

  it('立即执行：禁用任务拦截不调 API；启用任务 executeTask({id})', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.execute(makeTask({ enabled: false }))
    expect(executeTask).not.toHaveBeenCalled()
    expect(wrapper.vm.$message.warning).toHaveBeenCalled()

    await vm.execute(makeTask())
    expect(executeTask).toHaveBeenCalledWith({ id: 7 })
    // 延迟刷新走 setTimeout（与桌面端一致）
    jest.advanceTimersByTime(1100)
  })

  it('启停：updateTask 传 id + 取反 enabled（PUT 部分更新契约）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.toggleEnabled(makeTask({ enabled: true }))
    expect(updateTask).toHaveBeenCalledWith({ id: 7, enabled: false })
    await vm.toggleEnabled(makeTask({ enabled: false }))
    expect(updateTask).toHaveBeenLastCalledWith({ id: 7, enabled: true })
  })

  it('中断：interruptTask(taskId)', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.interrupt(makeTask())
    expect(interruptTask).toHaveBeenCalledWith(7)
  })

  it('删除：$confirm 确认后 deleteTasks({ids:[taskId]})', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.confirmDelete(makeTask())
    await flushLifecycle()
    expect(wrapper.vm.$confirm).toHaveBeenCalled()
    expect(deleteTasks).toHaveBeenCalledWith({ ids: [7] })
  })

  it('分页：skip 随已加载数递增', async() => {
    jest.mocked(getTaskList).mockResolvedValue({
      code: '200',
      data: { total: 40, list: [makeTask()] }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadMore()
    expect(getTaskList).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 1 }))
  })
})
