/**
 * 桌面侧栏「移动版」入口契约（dual-mode-client Phase 4 M1 余项）：
 * - 侧栏底部提供「移动版」动作按钮（非路由菜单项）；
 * - 点击：写 ui_mode=mobile 偏好（显式偏好优先于视口，宽屏可预览移动版）
 *   并 push /m/dashboard；守卫按解析后模式放行，SPA 内换壳无需刷新。
 * 注：el-button 用透传 click 的 stub（默认 stub 不转发事件）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import SideBar from '@/layout/components/Sidebar/index.vue'
import { AppModule } from '@/store/modules/app'

jest.mock('@/store/modules/app', () => ({
  AppModule: {
    sidebar: { opened: true },
    ToggleSideBar: jest.fn()
  }
}))

const mountSidebar = (): Wrapper<Vue> =>
  shallowMount(SideBar, {
    stubs: {
      SidebarItem: true,
      LucideIcon: true,
      'el-scrollbar': { template: '<div><slot /></div>' },
      'el-menu': { template: '<div><slot /></div>' },
      'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' }
    },
    mocks: {
      $route: { path: '/dashboard', meta: {} },
      $router: {
        options: { routes: [] },
        push: jest.fn().mockResolvedValue(undefined),
        replace: jest.fn().mockResolvedValue(undefined)
      }
    }
  })

const findButtonByText = (wrapper: Wrapper<Vue>, text: string): Wrapper<Vue> => {
  const found = wrapper.findAll('button').wrappers.find((w) => w.text().includes(text))
  if (!found) throw new Error(`button not found: ${text}`)
  return found
}

describe('layout/components/Sidebar 移动版入口', () => {
  afterEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  it('底部渲染「移动版」按钮（位于收起侧栏按钮上方）', () => {
    const wrapper = mountSidebar()
    expect(findButtonByText(wrapper, '移动版').exists()).toBe(true)
    const labels = wrapper.findAll('button').wrappers.map((w) => w.text())
    expect(labels.findIndex((t) => t.includes('收起侧'))).toBeGreaterThan(-1)
    expect(labels.findIndex((t) => t.includes('移动版'))).toBeLessThan(labels.findIndex((t) => t.includes('收起侧')))
  })

  it('点击：写 mobile 偏好并 push 移动仪表盘', async() => {
    const wrapper = mountSidebar()
    await findButtonByText(wrapper, '移动版').trigger('click')
    expect(localStorage.getItem('btdeck_ui_mode')).toBe('mobile')
    expect(wrapper.vm.$router.push).toHaveBeenCalledWith('/m/dashboard')
  })

  it('点击移动版不影响折叠按钮职责（不触发 ToggleSideBar）', async() => {
    const wrapper = mountSidebar()
    await findButtonByText(wrapper, '移动版').trigger('click')
    expect(AppModule.ToggleSideBar).not.toHaveBeenCalled()
  })
})
