/**
 * 移动布局壳行为契约（dual-mode-client Phase 4 M1 + 2026-08-24 增强）：
 * - 四个 Tab（仪表盘/下载器/种子/通知）渲染与高亮、Tab 切换导航、"桌面版"
 *   出口必须写偏好并离开移动布局（不自锁原则）；
 * - 汉堡抽屉：完整功能菜单（移动组 4 + 桌面组 9），移动项 replace、桌面项
 *   push 且不写 ui_mode 偏好（返回/刷新仍回移动版）；
 * - 通知未读角标：复用 Vuex NotificationModule.unreadCount，挂载即拉一次
 *   + 60s 轮询（fake timers），>99 显示 99+；
 * - 主题色与桌面端同源：头部背景与 Tab 激活色必须用 var(--color-primary)
 *   （静态契约，防回归到深灰 #27303f 头部 / Element 默认蓝 #409eff）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'
import MobileLayout from '@/layout/mobile/index.vue'
import { NotificationModule } from '@/store/modules/notification'

jest.mock('@/store/modules/notification', () => ({
  NotificationModule: {
    unreadCount: 0,
    FetchUnreadCount: jest.fn().mockResolvedValue(undefined)
  }
}))

const setMockUnread = (count: number): void => {
  (NotificationModule as unknown as { unreadCount: number }).unreadCount = count
}

const readLayoutSource = (): string =>
  fs.readFileSync(path.resolve(__dirname, '../../src/layout/mobile/index.vue'), 'utf-8')

describe('layout/mobile/MobileLayout', () => {
  const mountLayout = (currentPath: string): Wrapper<Vue> =>
    shallowMount(MobileLayout, {
      mocks: {
        $route: { path: currentPath },
        $router: { replace: jest.fn().mockResolvedValue(undefined), push: jest.fn().mockResolvedValue(undefined) }
      },
      stubs: {
        'router-view': true,
        // 透传默认插槽，让抽屉菜单内容可断言（避免 Element drawer 的 DOM 副作用）
        'el-drawer': { template: '<div class="drawer-stub"><slot /></div>' }
      }
    })

  afterEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
    jest.useRealTimers()
    setMockUnread(0)
  })

  it('渲染四个底部 Tab（仪表盘/下载器/种子/通知）', () => {
    const wrapper = mountLayout('/m/dashboard')
    const labels = wrapper.findAll('.mobile-tab-label').wrappers.map((w) => w.text())
    expect(labels).toEqual(['仪表盘', '下载器', '种子', '通知'])
  })

  it('当前路由对应 Tab 高亮', () => {
    const wrapper = mountLayout('/m/downloader')
    const tabs = wrapper.findAll('.mobile-tab')
    expect(tabs.at(1).classes()).toContain('is-active')
    expect(tabs.at(0).classes()).not.toContain('is-active')
  })

  it('点击非当前 Tab 导航到目标路径', async() => {
    const wrapper = mountLayout('/m/dashboard')
    wrapper.findAll('.mobile-tab').at(1).trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith('/m/downloader')
  })

  it('点击当前 Tab 不重复导航', async() => {
    const wrapper = mountLayout('/m/dashboard')
    wrapper.findAll('.mobile-tab').at(0).trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.$router.replace).not.toHaveBeenCalled()
  })

  it('桌面版出口：写 desktop 偏好并跳桌面仪表盘（不自锁）', async() => {
    const wrapper = mountLayout('/m/dashboard')
    const desktopButton = wrapper.findAll('.mobile-header-desktop').at(0)
    desktopButton.trigger('click')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('btdeck_ui_mode')).toBe('desktop')
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith('/dashboard')
  })

  // ============ 汉堡抽屉（2026-08-24） ============

  it('汉堡按钮打开抽屉，抽屉含移动组 11 项 + 桌面组 3 项完整菜单（M4 重组）', async() => {
    const wrapper = mountLayout('/m/dashboard')
    expect((wrapper.vm as any).drawerVisible).toBe(false)
    wrapper.find('.mobile-header-menu').trigger('click')
    await wrapper.vm.$nextTick()
    expect((wrapper.vm as any).drawerVisible).toBe(true)

    const items = wrapper.findAll('.mobile-menu-item')
    expect(items.length).toBe(14)
    const mobileLabels = (wrapper.vm as any).mobileMenuItems.map((t: { label: string }) => t.label)
    expect(mobileLabels).toEqual(['仪表盘', '下载器', '种子', '通知', '高级搜索', '查询模板', '回收站', '日志', 'Tracker关键词', '定时任务', '孤儿文件'])
    const desktopLabels = (wrapper.vm as any).desktopMenuItems.map((t: { label: string }) => t.label)
    expect(desktopLabels).toEqual(
      expect.arrayContaining(['种子列表（桌面）', 'Tracker 汇报/测试（桌面）', '系统设置'])
    )
    // M4 已移动化/有意保留的页面不在桌面组
    expect(desktopLabels).not.toContain('孤儿文件')
    expect(desktopLabels).not.toContain('下载器管理')
    expect(desktopLabels).not.toContain('定时任务')
  })

  it('抽屉点移动项：关闭抽屉并 replace 移动路径', async() => {
    const wrapper = mountLayout('/m/dashboard')
    const items = wrapper.findAll('.mobile-menu-item')
    // 第 2 项为移动组"下载器"
    items.at(1).trigger('click')
    await wrapper.vm.$nextTick()
    expect((wrapper.vm as any).drawerVisible).toBe(false)
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith('/m/downloader')
    expect(wrapper.vm.$router.push).not.toHaveBeenCalled()
  })

  it('抽屉点当前移动项：仅关闭抽屉不导航', async() => {
    const wrapper = mountLayout('/m/dashboard')
    wrapper.findAll('.mobile-menu-item').at(0).trigger('click')
    await wrapper.vm.$nextTick()
    expect((wrapper.vm as any).drawerVisible).toBe(false)
    expect(wrapper.vm.$router.replace).not.toHaveBeenCalled()
    expect(wrapper.vm.$router.push).not.toHaveBeenCalled()
  })

  it('抽屉点桌面功能项：关闭抽屉、push 桌面路径且不写 ui_mode 偏好', async() => {
    const wrapper = mountLayout('/m/dashboard')
    const items = wrapper.findAll('.mobile-menu-item')
    // 移动组 11 项之后为桌面组，首项"种子列表（桌面）"
    items.at(11).trigger('click')
    await wrapper.vm.$nextTick()
    expect((wrapper.vm as any).drawerVisible).toBe(false)
    expect(wrapper.vm.$router.push).toHaveBeenCalledWith('/torrents')
    expect(wrapper.vm.$router.replace).not.toHaveBeenCalled()
    expect(localStorage.getItem('btdeck_ui_mode')).toBeNull()
  })

  it('抽屉底部"完整桌面版"与头部出口行为一致（写偏好）', async() => {
    const wrapper = mountLayout('/m/dashboard')
    const footerBtn = wrapper.find('.mobile-menu-desktop-btn')
    footerBtn.trigger('click')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('btdeck_ui_mode')).toBe('desktop')
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith('/dashboard')
  })

  // ============ 主题色契约（与桌面端同源） ============

  it('头部背景与 Tab 激活色均使用 var(--color-primary)，无旧深灰/默认蓝回归', () => {
    const source = readLayoutSource()
    const activeRule = source.slice(
      source.indexOf('.mobile-tab.is-active'),
      source.indexOf('.mobile-tab-label')
    )
    expect(activeRule).toContain('var(--color-primary)')
    const headerRule = source.slice(
      source.indexOf('.mobile-header {'),
      source.indexOf('.mobile-header-title')
    )
    expect(headerRule).toContain('var(--color-primary)')
    const drawerHeaderRule = source.slice(
      source.indexOf('.mobile-menu-header'),
      source.indexOf('.mobile-menu-title')
    )
    expect(drawerHeaderRule).toContain('var(--color-primary)')
    expect(source).not.toContain('#409eff')
    expect(source).not.toContain('#27303f')
    // 抽屉菜单激活态同样走主题变量
    expect(source).toContain('.mobile-menu-item.is-active')
  })

  // ============ 通知未读角标（M1 余项，2026-08-24 第四批） ============

  it('未读数 > 0：通知 Tab 显示数字角标（其余 Tab 无角标）', () => {
    setMockUnread(5)
    const wrapper = mountLayout('/m/dashboard')
    const tabs = wrapper.findAll('.mobile-tab')
    expect(tabs.at(3).find('.mobile-tab-badge').exists()).toBe(true)
    expect(tabs.at(3).find('.mobile-tab-badge').text()).toBe('5')
    expect(tabs.at(0).find('.mobile-tab-badge').exists()).toBe(false)
    expect(tabs.at(1).find('.mobile-tab-badge').exists()).toBe(false)
    expect(tabs.at(2).find('.mobile-tab-badge').exists()).toBe(false)
  })

  it('未读数超过 99：角标显示 99+', () => {
    setMockUnread(120)
    const wrapper = mountLayout('/m/dashboard')
    expect(wrapper.find('.mobile-tab-badge').text()).toBe('99+')
  })

  it('未读数为 0：不渲染角标', () => {
    setMockUnread(0)
    const wrapper = mountLayout('/m/dashboard')
    expect(wrapper.find('.mobile-tab-badge').exists()).toBe(false)
  })

  it('挂载即拉取未读数，60s 轮询，销毁停止', () => {
    jest.useFakeTimers()
    const wrapper = mountLayout('/m/dashboard')
    expect(jest.mocked(NotificationModule.FetchUnreadCount)).toHaveBeenCalledTimes(1)
    jest.advanceTimersByTime(60000)
    expect(jest.mocked(NotificationModule.FetchUnreadCount)).toHaveBeenCalledTimes(2)
    jest.advanceTimersByTime(60000)
    expect(jest.mocked(NotificationModule.FetchUnreadCount)).toHaveBeenCalledTimes(3)
    wrapper.destroy()
    jest.advanceTimersByTime(180000)
    expect(jest.mocked(NotificationModule.FetchUnreadCount)).toHaveBeenCalledTimes(3)
  })
})
