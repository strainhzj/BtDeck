/**
 * 移动布局壳行为契约（dual-mode-client Phase 4 M1）：
 * 三个 Tab 渲染与高亮、Tab 切换导航、"桌面版"出口必须写偏好并离开移动布局
 * （不自锁原则：任何时刻都能切回桌面版）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileLayout from '@/layout/mobile/index.vue'

describe('layout/mobile/MobileLayout', () => {
  const mountLayout = (currentPath: string): Wrapper<Vue> =>
    shallowMount(MobileLayout, {
      mocks: {
        $route: { path: currentPath },
        $router: { replace: jest.fn().mockResolvedValue(undefined) }
      },
      stubs: { 'router-view': true }
    })

  afterEach(() => {
    localStorage.clear()
  })

  it('渲染三个底部 Tab（仪表盘/种子/通知）', () => {
    const wrapper = mountLayout('/m/dashboard')
    const labels = wrapper.findAll('.mobile-tab-label').wrappers.map((w) => w.text())
    expect(labels).toEqual(['仪表盘', '种子', '通知'])
  })

  it('当前路由对应 Tab 高亮', () => {
    const wrapper = mountLayout('/m/torrents')
    const tabs = wrapper.findAll('.mobile-tab')
    expect(tabs.at(1).classes()).toContain('is-active')
    expect(tabs.at(0).classes()).not.toContain('is-active')
  })

  it('点击非当前 Tab 导航到目标路径', async() => {
    const wrapper = mountLayout('/m/dashboard')
    wrapper.findAll('.mobile-tab').at(2).trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith('/m/notifications')
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
})
