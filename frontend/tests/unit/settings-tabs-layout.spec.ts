/**
 * 设置页页签布局 + 查询模板菜单归组回归（2026-09-23 UI 重构）。
 *
 * 保护点：
 * 1. 页签排布：桌面（宽视口）左侧垂直导航（el-tabs--left），窄视口
 *    （≤768px，含移动端整页复用）随 resize 即时切回顶部横排；
 * 2. 页签顺序固定：2fa → password → mcp → moviepilot → diagnosis，
 *    每个页签带 Lucide 图标与 i18n 文案（不允许退化为裸 label）；
 * 3. 路由归组：查询模板菜单挂在 /torrents 组内，可见顺序为
 *    种子列表 → 查询模板 → 种子文件管理；旧顶层深链重定向到新路径。
 */

import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import i18n from '@/i18n'

import Settings from '@/views/settings/index.vue'
import router from '@/router'
import LucideIcon from '@/components/common/LucideIcon.vue'

jest.mock('@/store/modules/user', () => ({
  UserModule: {
    userId: '1',
    name: 'admin',
    twoFactorFlag: '0',
    SetMustChangePassword: jest.fn(),
    ResetToken: jest.fn(),
    SetTwoFactorFlag: jest.fn()
  }
}))

jest.mock('@/api/users', () => ({
  changePassword: jest.fn(),
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn()
}))

jest.mock('@/api/health', () => ({
  exportDiagnosisFile: jest.fn()
}))

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: { post: jest.fn() },
  trySilentRefresh: jest.fn()
}))

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueI18n)
// main.ts 全局注册的 LucideIcon 在测试 localVue 上需手动补注册（真渲染 svg，
// 顺带守护：页签用到的图标名必须在 ICONS 清单内，未注册会渲染为占位符而非 svg）
localVue.component('LucideIcon', LucideIcon)

/** class 组件的 private 成员运行时即实例成员，经接口重声明访问 */
interface SettingsVm extends Vue {
  tabPosition: 'left' | 'top'
}

const mountSettings = (): { wrapper: Wrapper<Vue>, vm: SettingsVm } => {
  const wrapper = mount(Settings, {
    localVue,
    i18n,
    stubs: {
      // 子面板行为由 mcp-settings.spec / moviepilot-panel.spec 各自守护，此处聚焦布局
      'mcp-settings-panel': true,
      'movie-pilot-panel': true
    },
    mocks: {
      $route: { query: {}, path: '/settings/index' },
      $router: { push: jest.fn(), replace: jest.fn() },
      $message: jest.fn()
    }
  })
  return { wrapper, vm: wrapper.vm as SettingsVm }
}

const setViewportWidth = async(width: number): Promise<void> => {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true })
  window.dispatchEvent(new Event('resize'))
  await Vue.nextTick()
  await new Promise<void>(resolve => { setTimeout(resolve, 0) })
  await Vue.nextTick()
}

describe('设置页页签布局（2026-09-23 重构）', () => {
  const originalWidth = window.innerWidth

  afterEach(async() => {
    await setViewportWidth(originalWidth)
  })

  it('宽视口：左侧垂直导航渲染，五个页签顺序固定且各带图标', async() => {
    await setViewportWidth(1280)
    const { wrapper, vm } = mountSettings()
    // el-tabs 的 nav 在 mounted 后异步重渲染，需等 flush
    await Vue.nextTick()

    expect(vm.tabPosition).toBe('left')
    expect(wrapper.find('.settings-tabs.el-tabs--left').exists()).toBe(true)

    const items = wrapper.findAll('.settings-tabs .el-tabs__item')
    expect(items).toHaveLength(5)
    // 顺序锚定：2fa → password → mcp → moviepilot → diagnosis
    expect(items.at(0).attributes('id')).toBe('tab-2fa')
    expect(items.at(1).attributes('id')).toBe('tab-password')
    expect(items.at(2).attributes('id')).toBe('tab-mcp')
    expect(items.at(3).attributes('id')).toBe('tab-moviepilot')
    expect(items.at(4).attributes('id')).toBe('tab-diagnosis')

    // 每个页签：Lucide 图标（svg）+ i18n 文案，不允许退化为裸 label
    const labelsZh = ['双因素认证', '修改密码', 'MCP 服务', 'MoviePilot', '状态诊断']
    for (let i = 0; i < 5; i++) {
      const label = items.at(i).find('.settings-tab-label')
      expect(label.exists()).toBe(true)
      expect(label.find('svg').exists()).toBe(true)
      expect(label.text()).toContain(labelsZh[i])
    }

    wrapper.destroy()
  })

  it('窄视口（≤768px）：resize 即时切回顶部横排，恢复宽视口切回左侧', async() => {
    await setViewportWidth(1280)
    const { wrapper, vm } = mountSettings()
    await Vue.nextTick()

    await setViewportWidth(375)
    expect(vm.tabPosition).toBe('top')
    expect(wrapper.find('.settings-tabs.el-tabs--top').exists()).toBe(true)

    await setViewportWidth(1280)
    expect(vm.tabPosition).toBe('left')
    expect(wrapper.find('.settings-tabs.el-tabs--left').exists()).toBe(true)

    wrapper.destroy()
  })

  it('卸载时解绑 resize 监听（beforeDestroy 清理）', async() => {
    const { wrapper } = mountSettings()
    wrapper.destroy()
    // 监听已解绑：再触发 resize 不应抛错（未解绑时会向已销毁实例赋值）
    await setViewportWidth(900)
  })
})

describe('查询模板菜单归组（2026-09-23 调整）', () => {
  const routeRecords = router.options.routes || []

  it('/torrents 组可见子菜单顺序：种子列表 → 查询模板 → 种子文件管理', () => {
    const torrentsGroup = routeRecords.find(r => r.path === '/torrents')
    expect(torrentsGroup).toBeDefined()
    const visibleChildren = (torrentsGroup?.children ?? [])
      .filter(c => !c.meta || !c.meta.hidden)
      .map(c => c.path)
    expect(visibleChildren).toEqual(['index', 'query-templates', 'file-management'])
  })

  it('查询模板路由 meta 完整（titleKey/icon 供侧栏与面包屑渲染）', () => {
    const torrentsGroup = routeRecords.find(r => r.path === '/torrents')
    const qt = (torrentsGroup?.children ?? []).find(c => c.path === 'query-templates')
    expect(qt).toBeDefined()
    expect(qt?.meta?.titleKey).toBe('navigation.routes.queryTemplates')
    expect(qt?.meta?.icon).toBe('layout-template')
  })

  it('旧顶层深链（/query-templates 与 /query-templates/index）重定向到新路径', () => {
    const redirectPaths = ['/query-templates', '/query-templates/index']
    redirectPaths.forEach(p => {
      const record = routeRecords.find(r => r.path === p)
      expect(record).toBeDefined()
      expect((record as { redirect: string }).redirect).toBe('/torrents/query-templates')
    })
  })

  it('路由解析：新路径命中 Layout + 页面组件两层记录', () => {
    const matched = router.match('/torrents/query-templates').matched
    expect(matched).toHaveLength(2)
    expect(matched[1].components).toBeDefined()
  })
})
