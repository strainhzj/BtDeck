/**
 * 移动通知中心契约（2026-08-26 内容渲染对齐桌面；2026-08-27 摘要纯文本化）：
 * - 列表摘要经 utils/notification-markdown plainNotificationContent 剥离 Markdown
 *   记号（标题、列表、粗体、行内代码、分隔线）后纯文本三行截断，未打开详情前
 *   不裸露渲染字符；
 * - 详情内容经 utils/notification-markdown 与桌面同源渲染（标题/列表/粗体/行内代码），
 *   含失败明细与 Release 外链（本页此前 {{ content }} 裸文本裸露 Markdown 记号的直接锁死）；
 * - 查看未读即标记已读并联动布局壳角标（FetchUnreadCount）；
 * - 源码契约：必须复用共享渲染/纯文本化函数，禁止回退裸文本直渲/复制私有实现。
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
    // jsdom 无布局：mock 出“内容远高于一屏、停在顶部”，避免 load()/loadMore()
    // 完成后的补页检查（maybeLoadMore）在既有用例里自动链式加载改变计数；
    // scrollTop 一并重置防跨用例残留伪造“已在底部”
    Object.defineProperty(document.documentElement, 'scrollHeight', { value: 20000, configurable: true })
    Object.defineProperty(document.documentElement, 'clientHeight', { value: 844, configurable: true })
    Object.defineProperty(document.documentElement, 'scrollTop', { value: 0, configurable: true })
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

  it('列表摘要剥离 Markdown 记号：纯文本可见且不渲染 HTML（渲染只发生在详情弹层）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const summary = wrapper.find('.m-notice-content')
    // 记号 ##/- **/`/--- 已剥离，正文文本保留
    expect(summary.text()).toContain('v1.0.6 更新')
    expect(summary.text()).toContain('新增：查询模板管理')
    expect(summary.text()).toContain('优化 docker compose 部署')
    expect(summary.text()).toContain('详情见 Release')
    expect(summary.text()).not.toContain('##')
    expect(summary.text()).not.toContain('**')
    expect(summary.text()).not.toContain('`')
    // 摘要保持纯文本插值，不产生 HTML 节点
    expect(summary.element.innerHTML).not.toContain('<h3>')
    expect(summary.element.innerHTML).not.toContain('<strong>')
    expect(summary.element.innerHTML).not.toContain('<code>')
  })

  it('摘要与详情双层分离契约：同一条通知摘要剥离记号（精确全文）、详情完整 Markdown 渲染', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    // 列表层：摘要精确全文（锁死行级剥离 + 单空格连接 + 内联去记号的整体行为）
    const summary = wrapper.find('.m-notice-content')
    expect(summary.text()).toBe('v1.0.6 更新 新增：查询模板管理 优化 docker compose 部署 详情见 Release')
    // 详情层：同一通知点击后走 renderNotificationContent 完整渲染
    await wrapper.findAll('.m-notice').at(0).trigger('click')
    await flushLifecycle()
    const html = wrapper.find('.m-detail-content').element.innerHTML
    expect(html).toContain('<h3>v1.0.6 更新</h3>')
    expect(html).toContain('<strong>新增</strong>')
    expect(html).toContain('<code>docker compose</code>')
    wrapper.destroy()
  })

  it('剥离后无可见文本的通知（content 仅分隔线/空行）不渲染摘要块', async() => {
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { total: 1, page: 1, pageSize: 50, list: [makeItem({ id: 99, title: '空摘要通知', content: '---\n \n---' })] }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.findAll('.m-notice').length).toBe(1)
    expect(wrapper.find('.m-notice-content').exists()).toBe(false)
    wrapper.destroy()
  })

  it('summaryText 为纯函数：不修改通知原始 content（详情渲染源不被摘要污染）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { list: NotificationItem[], summaryText(n: NotificationItem): string }
    const original = vm.list[0].content
    const summary = vm.summaryText(vm.list[0])
    expect(summary).not.toContain('##')
    expect(vm.list[0].content).toBe(original)
    wrapper.destroy()
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

  it('刷新链路：下拉刷新 onPullRefresh 重新拉取并重置回第 1 页（m-refresh 按钮已移除）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.m-refresh').exists()).toBe(false)
    const vm = wrapper.vm as unknown as { onPullRefresh(): Promise<void>, page: number }
    await vm.onPullRefresh()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledTimes(2)
    expect(getNotificationList).toHaveBeenLastCalledWith({ page: 1, pageSize: 50 })
    expect(vm.page).toBe(1)
  })

  it('无限滚动追加：loadMore 拉下一页并按 id 去重（跨页重复被过滤）', async() => {
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { total: 6, page: 1, pageSize: 3, list: makeList() }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    // 第 2 页返回两条：一条与第 1 页 id 重复（模拟新通知插入使 offset 前移），一条新
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: {
        total: 6, page: 2, pageSize: 3,
        list: [makeItem({ id: 11, title: '重复项' }), makeItem({ id: 14, title: '新通知' })]
      }
    } as never)
    await vm.loadMore()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenLastCalledWith({ page: 2, pageSize: 50 })
    expect(vm.list.map((n: NotificationItem) => n.id)).toEqual([11, 12, 13, 14])
    expect(vm.page).toBe(2)
    wrapper.destroy()
  })

  it('静默刷新互斥：未翻页整表替换；已翻页跳过本轮只同步未读角标', async() => {
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { total: 6, page: 1, pageSize: 3, list: makeList() }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any

    // 未翻页（page=1）：静默刷新 = 整表重载
    await vm.loadActiveSpeed()
    await flushLifecycle()
    expect(getNotificationList).toHaveBeenCalledTimes(2)

    // 翻到第 2 页后：静默刷新不再拉列表，只同步角标（防把用户重置回第 1 页）
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { total: 6, page: 2, pageSize: 3, list: [makeItem({ id: 14 })] }
    } as never)
    await vm.loadMore()
    await flushLifecycle()
    const callsBefore = jest.mocked(getNotificationList).mock.calls.length
    jest.mocked(NotificationModule.FetchUnreadCount).mockClear()
    await vm.loadActiveSpeed()
    await flushLifecycle()
    expect(jest.mocked(getNotificationList).mock.calls.length).toBe(callsBefore)
    expect(NotificationModule.FetchUnreadCount).toHaveBeenCalled()
    expect(vm.page).toBe(2)
    wrapper.destroy()
  })

  it('源码契约：必须复用共享渲染/纯文本化函数，禁止裸文本直渲与私有实现复制', () => {
    const source = readSource()
    // 同源渲染：详情内容必须经 utils/notification-markdown 渲染
    expect(source).toContain("from '@/utils/notification-markdown'")
    expect(source).toContain('renderNotificationContent(')
    // 同源摘要：列表必须走共享纯文本化，禁止模板直塞原始 content
    expect(source).toContain('plainNotificationContent(')
    expect(source).not.toContain('{{ n.content }}')
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

  it('源码契约：无限滚动由 WindowInfiniteScroll（window 驱动）承担，Element 指令禁回流', () => {
    const source = readSource()
    // 2026-09-05 根修：v-infinite-scroll 会把从不内滚的 .mobile-content 判为恒在
    // 底部，页面打开自动连发请求拉满 total（与种子页同源缺陷）
    expect(source).not.toContain('v-infinite-scroll')
    expect(source).toContain('WindowInfiniteScroll')
    expect(source).toContain('maybeLoadMore()')
  })

  it('无限滚动补页：load 完成后内容不足一屏时自动链式加载（短内容页无滚动事件可依赖）', async() => {
    jest.mocked(getNotificationList)
      .mockResolvedValueOnce({
        code: '200', status: 'success', msg: 'ok',
        data: { total: 5, page: 1, pageSize: 50, list: makeList() }
      } as never)
      .mockResolvedValue({
        code: '200', status: 'success', msg: 'ok',
        data: { total: 5, page: 2, pageSize: 50, list: [makeItem({ id: 21 }), makeItem({ id: 22 })] }
      } as never)
    Object.defineProperty(document.documentElement, 'scrollHeight', { value: 600, configurable: true })
    Object.defineProperty(document.documentElement, 'clientHeight', { value: 844, configurable: true })
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    // 首屏 3 条 + 补页 1 次（5 条后 list.length >= total 停止，不失控连发）
    expect(jest.mocked(getNotificationList).mock.calls.length).toBe(2)
    expect(vm.list.map((n: NotificationItem) => n.id)).toEqual([11, 12, 13, 21, 22])
    wrapper.destroy()
  })

  it('失控根修核心性质：内容高于一屏时首屏仅 1 次请求，静默刷新与已翻页轮询零追加', async() => {
    // beforeEach 几何 mock：内容 20000px >> 视口 844px
    const pageOne = {
      code: '200', status: 'success', msg: 'ok',
      data: { total: 999, page: 1, pageSize: 50, list: makeList() }
    } as never
    jest.mocked(getNotificationList)
      .mockResolvedValueOnce(pageOne)   // 首屏
      .mockResolvedValueOnce(pageOne)   // 静默刷新整表重载
      .mockResolvedValue({              // 翻页及其后
        code: '200', status: 'success', msg: 'ok',
        data: { total: 999, page: 2, pageSize: 50, list: [makeItem({ id: 21 })] }
      } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(jest.mocked(getNotificationList).mock.calls.length).toBe(1)
    // 静默刷新（page=1 整表重载）：恰好 1 次请求，无补页链
    await vm.loadActiveSpeed()
    await flushLifecycle()
    expect(jest.mocked(getNotificationList).mock.calls.length).toBe(2)
    // 翻到第 2 页（高内容不触发补页链，恰 +1 次）
    await vm.loadMore()
    await flushLifecycle()
    expect(jest.mocked(getNotificationList).mock.calls.length).toBe(3)
    expect(vm.page).toBe(2)
    // 已翻页的静默刷新只同步角标：零列表请求
    jest.mocked(getNotificationList).mockClear()
    jest.mocked(NotificationModule.FetchUnreadCount).mockClear()
    await vm.loadActiveSpeed()
    await flushLifecycle()
    expect(getNotificationList).not.toHaveBeenCalled()
    expect(NotificationModule.FetchUnreadCount).toHaveBeenCalled()
    wrapper.destroy()
  })
})
