/**
 * 移动通知中心契约（2026-08-26 内容渲染对齐桌面）：
 * - 列表摘要纯文本三行截断，点击卡片打开详情弹层；
 * - 详情内容经 utils/notification-markdown 与桌面同源渲染（标题/列表/粗体/行内代码），
 *   含失败明细与 Release 外链（本页此前 {{ content }} 裸文本裸露 Markdown 记号的直接锁死）；
 * - 查看未读即标记已读并联动布局壳角标（FetchUnreadCount）；
 * - 源码契约：必须复用共享渲染函数，禁止回退裸文本直渲/复制私有实现。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'
import MobileNotifications from '@/views/mobile/notifications.vue'
import { getNotificationList, markAsRead, NotificationItem } from '@/api/notification'
import { NotificationModule } from '@/store/modules/notification'

jest.mock('@/api/notification', () => ({
  getNotificationList: jest.fn(),
  markAsRead: jest.fn()
}))

jest.mock('@/store/modules/notification', () => ({
  NotificationModule: {
    unreadCount: 0,
    FetchUnreadCount: jest.fn().mockResolvedValue(undefined)
  }
}))

const CONTENT_MARKDOWN = [
  '## v1.0.6 更新',
  '- **新增**：查询模板管理',
  '- 优化 `docker compose` 部署',
  '---',
  '详情见 Release'
].join('\n')

const makeItem = (overrides: Partial<NotificationItem>): NotificationItem => ({
  id: 1,
  type: 'system',
  title: '系统通知',
  content: CONTENT_MARKDOWN,
  priority: 'info',
  is_read: false,
  extra_data: null,
  created_at: '2026-08-26T10:30:00',
  read_at: null,
  ...overrides
})

const makeList = (): NotificationItem[] => [
  makeItem({ id: 11, title: '版本发布', type: 'version_update' }),
  makeItem({
    id: 12,
    title: '清理任务完成',
    is_read: true,
    content: '清理完成',
    extra_data: {
      failed_list: [
        { id: 101, file_name: 'a.iso', reason: '文件被占用' },
        { file_path: '/data/b.iso', reason: '权限不足' }
      ]
    }
  }),
  makeItem({
    id: 13,
    title: '新版本可用',
    type: 'version_update',
    content: 'v1.0.7 已发布',
    extra_data: { release_url: 'https://github.com/btdeck/release/v1.0.7' }
  })
]

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileNotifications, {
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

const readSource = (): string =>
  fs.readFileSync(path.resolve(__dirname, '../../src/views/mobile/notifications.vue'), 'utf-8')

describe('views/mobile/MobileNotifications', () => {
  beforeEach(() => {
    jest.mocked(getNotificationList).mockReset()
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: { total: 3, page: 1, pageSize: 50, list: makeList() }
    } as never)
    jest.mocked(markAsRead).mockReset()
    jest.mocked(markAsRead).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: null
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('挂载即拉取并渲染通知卡片：标题/摘要/时间，未读标识与已读区分', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledWith({ page: 1, pageSize: 50 })
    const cards = wrapper.findAll('.m-notice')
    expect(cards.length).toBe(3)
    expect(cards.at(0).find('.m-notice-title-text').text()).toBe('版本发布')
    expect(cards.at(0).classes()).toContain('is-unread')
    expect(cards.at(1).classes()).not.toContain('is-unread')
    expect(wrapper.text()).toContain('2026-08-26 10:30')
  })

  it('列表摘要为纯文本：Markdown 记号原样可见但不渲染 HTML（渲染只发生在详情弹层）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const summary = wrapper.find('.m-notice-content')
    expect(summary.text()).toContain('## v1.0.6 更新')
    expect(summary.element.innerHTML).not.toContain('<h3>')
    expect(summary.element.innerHTML).not.toContain('<strong>')
  })

  it('点击未读卡片：打开详情 + 标记已读 + 联动布局壳角标（FetchUnreadCount）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    expect(markAsRead).toHaveBeenCalledWith(11)
    expect(NotificationModule.FetchUnreadCount).toHaveBeenCalled()
    const vm = wrapper.vm as unknown as { detailVisible: boolean, detail: NotificationItem }
    expect(vm.detailVisible).toBe(true)
    expect(vm.detail.id).toBe(11)
    // 卡片就地置为已读
    expect(wrapper.findAll('.m-notice').at(0).classes()).not.toContain('is-unread')
    wrapper.destroy()
  })

  it('点击已读卡片：详情仍可打开，但不重复调用 markAsRead', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(1).trigger('click')
    await flushLifecycle()
    expect(markAsRead).not.toHaveBeenCalled()
    const vm = wrapper.vm as unknown as { detailVisible: boolean }
    expect(vm.detailVisible).toBe(true)
    wrapper.destroy()
  })

  it('详情内容与桌面同源渲染：标题/列表/粗体/行内代码/分隔线，原始记号不再裸露', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    const html = wrapper.find('.m-detail-content').element.innerHTML
    expect(html).toContain('<h3>v1.0.6 更新</h3>')
    expect(html).toContain('<li><strong>新增</strong>：查询模板管理</li>')
    expect(html).toContain('<code>docker compose</code>')
    // jsdom innerHTML 会把 <hr /> 序列化为 <hr>
    expect(html).toContain('<hr')
    expect(html).toContain('<p>详情见 Release</p>')
    expect(html).not.toContain('## ')
    expect(html).not.toContain('**')
  })

  it('详情失败明细：extra_data.failed_list 渲染目标名回退链与原因；无失败不渲染块', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(1).trigger('click')
    await flushLifecycle()
    const failures = wrapper.find('.m-detail-failures')
    expect(failures.exists()).toBe(true)
    expect(failures.text()).toContain('a.iso')
    expect(failures.text()).toContain('文件被占用')
    expect(failures.text()).toContain('/data/b.iso')
    expect(failures.text()).toContain('权限不足')

    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    expect(wrapper.find('.m-detail-failures').exists()).toBe(false)
    wrapper.destroy()
  })

  it('详情 Release 外链：extra_data.release_url 渲染为链接，无则不渲染', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(2).trigger('click')
    await flushLifecycle()
    const link = wrapper.find('.m-detail-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://github.com/btdeck/release/v1.0.7')
    expect(link.text()).toContain('在 GitHub 上查看完整 Release')

    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    expect(wrapper.find('.m-detail-link').exists()).toBe(false)
    wrapper.destroy()
  })

  it('详情类型标签：version_update 显版本更新，system 显系统通知', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    expect(wrapper.find('.m-detail-meta').text()).toContain('版本更新')
    // 卡片 1 为默认 type=system（清理任务完成）
    await wrapper.findAll('.m-notice').at(1).trigger('click')
    await flushLifecycle()
    expect(wrapper.find('.m-detail-meta').text()).toContain('系统通知')
    wrapper.destroy()
  })

  it('markAsRead 失败：提示错误、卡片保持未读、不联动角标', async() => {
    jest.mocked(markAsRead).mockRejectedValue(new Error('boom') as never)
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { $message: { error: jest.Mock } }
    expect(vm.$message.error).toHaveBeenCalled()
    expect(wrapper.findAll('.m-notice').at(0).classes()).toContain('is-unread')
    expect(NotificationModule.FetchUnreadCount).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('信封契约：code 非 200 停留空态不误报错；接口 reject 提示错误', async() => {
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '500', status: 'error', msg: 'x', data: null
    } as never)
    let wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无通知')
    let vm = wrapper.vm as unknown as { $message: { error: jest.Mock } }
    expect(vm.$message.error).not.toHaveBeenCalled()
    wrapper.destroy()

    jest.mocked(getNotificationList).mockRejectedValue(new Error('net') as never)
    wrapper = mountPage()
    await flushLifecycle()
    vm = wrapper.vm as unknown as { $message: { error: jest.Mock } }
    expect(vm.$message.error).toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无通知')
    wrapper.destroy()
  })

  it('刷新链路：刷新按钮与下拉刷新 onPullRefresh 都重新拉取', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledTimes(1)
    await wrapper.find('.m-refresh').trigger('click')
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledTimes(2)
    const vm = wrapper.vm as unknown as { onPullRefresh(): Promise<void> }
    await vm.onPullRefresh()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledTimes(3)
  })

  it('源码契约：必须复用共享渲染函数渲染详情，禁止裸文本直渲与私有实现复制', () => {
    const source = readSource()
    // 同源渲染：详情内容必须经 utils/notification-markdown 渲染
    expect(source).toContain("from '@/utils/notification-markdown'")
    expect(source).toContain('renderNotificationContent(')
    // 禁止回退：v-html 直塞原始 content、或模板内联大段转换
    expect(source).not.toContain('v-html="detail.content"')
    expect(source).not.toContain('v-html="n.content"')
    expect(source).not.toContain("startsWith('### ')")
    // 摘要三行截断对齐桌面列表
    expect(source).toContain('-webkit-line-clamp: 3')
    // 详情弹层样式收口类名存在（v-html 产物非 scoped）
    expect(source).toContain('m-notification-detail-dialog')
    // vue-jest buble 编译约束（M3 三坑）
    const templateBlock = source.slice(source.indexOf('<template>'), source.lastIndexOf('</template>'))
    expect(templateBlock).not.toContain('?.')
    expect(templateBlock).not.toContain('??')
  })
})
