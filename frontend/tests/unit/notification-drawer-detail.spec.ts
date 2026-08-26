/**
 * 桌面 NotificationDrawer 详情契约（2026-08-26 渲染逻辑抽共享后回归锁）：
 * - detailHtml 必须委托 utils/notification-markdown（与移动端同源），禁止内联
 *   Markdown 转换回归（本组件曾是渲染逻辑唯一持有者，抽取属行为零变化重构）；
 * - handleView 打开详情：未读自动标记已读、已读不重复调用；失败明细目标回退链
 *   与 Release 外链同移动端。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'
import NotificationDrawer from '@/layout/components/NotificationDrawer/index.vue'
import { NotificationItem } from '@/api/notification'
import { NotificationModule } from '@/store/modules/notification'

jest.mock('@/store/modules/notification', () => ({
  NotificationModule: {
    drawerVisible: false,
    notifications: [],
    unreadCount: 0,
    loading: false,
    total: 0,
    FetchNotifications: jest.fn().mockResolvedValue(undefined),
    FetchUnreadCount: jest.fn().mockResolvedValue(undefined),
    MarkAsRead: jest.fn().mockResolvedValue(undefined),
    MarkAsUnread: jest.fn().mockResolvedValue(undefined),
    MarkAllAsRead: jest.fn().mockResolvedValue(undefined),
    DeleteNotification: jest.fn().mockResolvedValue(undefined),
    ToggleDrawer: jest.fn()
  }
}))

const makeItem = (overrides: Partial<NotificationItem>): NotificationItem => ({
  id: 1,
  type: 'version_update',
  title: 'v1.0.7 发布',
  content: '## 新特性\n- **查询模板**：支持保存\n- 使用 `docker compose` 部署',
  priority: 'info',
  is_read: false,
  extra_data: null,
  created_at: '2026-08-26T09:00:00',
  read_at: null,
  ...overrides
})

const mountDrawer = (): Wrapper<Vue> =>
  shallowMount(NotificationDrawer, {
    stubs: {
      // 透传默认插槽：详情内容/失败明细/外链均在 el-dialog 默认插槽内
      'el-drawer': { template: '<div class="drawer-stub"><slot /></div>' },
      'el-dialog': { template: '<div class="dialog-stub"><slot /></div>' }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('layout/components/NotificationDrawer 详情渲染', () => {
  afterEach(() => {
    jest.clearAllMocks()
  })

  it('handleView 未读通知：打开详情 + 自动标记已读 + 内容经共享函数渲染', async() => {
    const wrapper = mountDrawer()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { handleView(n: NotificationItem): void, detailVisible: boolean }
    vm.handleView(makeItem({ id: 21 }))
    await flushLifecycle()
    expect(NotificationModule.MarkAsRead).toHaveBeenCalledWith(21)
    expect(vm.detailVisible).toBe(true)
    const html = wrapper.find('.detail-content').element.innerHTML
    expect(html).toContain('<h3>新特性</h3>')
    expect(html).toContain('<li><strong>查询模板</strong>：支持保存</li>')
    expect(html).toContain('<code>docker compose</code>')
    expect(html).not.toContain('## ')
    expect(html).not.toContain('**')
    wrapper.destroy()
  })

  it('handleView 已读通知：详情可打开，不重复 MarkAsRead', async() => {
    const wrapper = mountDrawer()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { handleView(n: NotificationItem): void, detailVisible: boolean }
    vm.handleView(makeItem({ id: 22, is_read: true }))
    await flushLifecycle()
    expect(NotificationModule.MarkAsRead).not.toHaveBeenCalled()
    expect(vm.detailVisible).toBe(true)
    wrapper.destroy()
  })

  it('失败明细：failed_list 渲染目标名与原因，无 extra_data 不渲染', async() => {
    const wrapper = mountDrawer()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { handleView(n: NotificationItem): void }
    vm.handleView(makeItem({
      id: 23,
      type: 'system',
      extra_data: {
        failed_list: [
          { id: 1, file_name: 'x.pack', reason: '被占用' },
          { file_path: '/data/y.pack', reason: '权限' }
        ]
      }
    }))
    await flushLifecycle()
    const failures = wrapper.find('.detail-failures')
    expect(failures.exists()).toBe(true)
    expect(failures.text()).toContain('x.pack')
    expect(failures.text()).toContain('被占用')
    expect(failures.text()).toContain('/data/y.pack')

    vm.handleView(makeItem({ id: 24, is_read: true }))
    await flushLifecycle()
    expect(wrapper.find('.detail-failures').exists()).toBe(false)
    wrapper.destroy()
  })

  it('Release 外链：release_url 渲染链接，无则不渲染', async() => {
    const wrapper = mountDrawer()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { handleView(n: NotificationItem): void }
    vm.handleView(makeItem({ id: 25, is_read: true, extra_data: { release_url: 'https://github.com/btdeck/v1.0.7' } }))
    await flushLifecycle()
    const link = wrapper.find('.detail-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://github.com/btdeck/v1.0.7')

    vm.handleView(makeItem({ id: 26, is_read: true, extra_data: null }))
    await flushLifecycle()
    expect(wrapper.find('.detail-link').exists()).toBe(false)
    wrapper.destroy()
  })

  it('handleDetailClose 清空详情状态', async() => {
    const wrapper = mountDrawer()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as {
      handleView(n: NotificationItem): void
      handleDetailClose(): void
      detailVisible: boolean
      detailContent: string
    }
    vm.handleView(makeItem({ id: 27, is_read: true }))
    await flushLifecycle()
    expect(vm.detailVisible).toBe(true)
    vm.handleDetailClose()
    await flushLifecycle()
    expect(vm.detailVisible).toBe(false)
    expect(vm.detailContent).toBe('')
    wrapper.destroy()
  })

  it('源码契约：详情渲染必须委托共享 util，禁止内联转换逻辑回归', () => {
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../src/layout/components/NotificationDrawer/index.vue'),
      'utf-8'
    )
    // 委托关系存在
    expect(source).toContain("from '@/utils/notification-markdown'")
    expect(source).toContain('renderNotificationContent(this.detailContent)')
    expect(source).toContain('notificationFailureTarget(item)')
    // 内联实现回归守卫：抽取前的私有转换细节不得回流入组件
    expect(source).not.toContain("startsWith('### ')")
    expect(source).not.toContain('/\\*\\*(.+?)\\*\\*/')
    expect(source).not.toContain("replace(/&/g, '&amp;')")
  })

  it('挂载即拉取未读数并启动轮询（60s），销毁停止', async() => {
    jest.useFakeTimers()
    const wrapper = mountDrawer()
    await flushLifecycle()
    expect(NotificationModule.FetchUnreadCount).toHaveBeenCalledTimes(1)
    jest.advanceTimersByTime(120000)
    expect(NotificationModule.FetchUnreadCount).toHaveBeenCalledTimes(3)
    wrapper.destroy()
    jest.advanceTimersByTime(120000)
    expect(NotificationModule.FetchUnreadCount).toHaveBeenCalledTimes(3)
    jest.useRealTimers()
  })
})
