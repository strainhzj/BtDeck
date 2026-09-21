import { readFileSync } from 'fs'
import { resolve } from 'path'
import { compileString } from 'sass'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueRouter, { RouteConfig } from 'vue-router'
import LucideIcon from '@/components/common/LucideIcon.vue'
import SidebarItem from '@/layout/components/Sidebar/SidebarItem.vue'

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueRouter)
localVue.component('LucideIcon', LucideIcon)

const sidebarItemSource = readFileSync(
  resolve(__dirname, '../../src/layout/components/Sidebar/SidebarItem.vue'),
  'utf8'
)

const unscopedStyle = sidebarItemSource.match(/<style lang="scss">([\s\S]*?)<\/style>/)?.[1]
if (!unscopedStyle) throw new Error('SidebarItem.vue unscoped style block not found')

const sidebarStyle = document.createElement('style')
sidebarStyle.textContent = compileString(unscopedStyle).css

interface SidebarHost extends Vue {
  collapsed: boolean
}

interface LucideIconVm extends Vue {
  name: string
}

const torrentRoute: RouteConfig = {
  path: '/torrents',
  meta: { title: '种子管理', icon: 'download' },
  children: [
    { path: 'index', meta: { title: '种子列表', icon: 'list' } },
    { path: 'file-management', meta: { title: '种子文件管理', icon: 'folder' } }
  ]
}

const trackerRoute: RouteConfig = {
  path: '/tracker',
  meta: { title: 'Tracker管理', icon: 'link' },
  children: [
    { path: 'keywords-board', meta: { title: '关键词看板', icon: 'panels-top-left' } },
    { path: 'reannounce-config', meta: { title: '汇报配置', icon: 'settings' } },
    { path: 'test', meta: { title: '测试工具', icon: 'wrench' } }
  ]
}

const downloaderRoute: RouteConfig = {
  path: '/downloader',
  children: [
    { path: 'index', meta: { title: '下载器管理', icon: 'server' } }
  ]
}

const mountedWrappers: Array<Wrapper<Vue>> = []

const mountSidebarItem = (routeItem: RouteConfig, collapsed = true): Wrapper<Vue> => {
  const router = new VueRouter({ routes: [] })
  const Host = localVue.extend({
    components: { SidebarItem },
    data() {
      return { collapsed, routeItem }
    },
    template: `
      <el-menu :collapse="collapsed">
        <sidebar-item
          :item="routeItem"
          :base-path="routeItem.path"
          :is-collapse="collapsed"
        />
      </el-menu>
    `
  })
  const wrapper = mount(Host, { localVue, router, attachTo: document.body })
  mountedWrappers.push(wrapper)
  return wrapper
}

describe('桌面侧栏折叠态 Lucide 父菜单图标', () => {
  beforeAll(() => {
    document.head.appendChild(sidebarStyle)
  })

  afterEach(() => {
    while (mountedWrappers.length > 0) mountedWrappers.pop()?.destroy()
  })

  afterAll(() => {
    sidebarStyle.remove()
  })

  it.each([
    ['种子管理', torrentRoute, 'download'],
    ['Tracker管理', trackerRoute, 'link']
  ])('%s 多子菜单折叠时保留主图标，仅隐藏标题和箭头', (_title, routeItem, iconName) => {
    const wrapper = mountSidebarItem(routeItem)
    const title = wrapper.find('.el-submenu__title')
    const icon = title.find('.menu-icon')
    const label = title.find('.submenu-label')
    const chevron = title.find('.submenu-chevron')

    expect(wrapper.find('.menu-wrapper.simple-mode.first-level').exists()).toBe(true)
    expect(icon.element.tagName).toBe('SPAN')
    expect(icon.find('svg').exists()).toBe(true)
    expect((icon.vm as LucideIconVm).name).toBe(iconName)
    expect(window.getComputedStyle(icon.element).visibility).toBe('visible')
    expect(window.getComputedStyle(label.element).visibility).toBe('hidden')
    expect(window.getComputedStyle(chevron.element).visibility).toBe('hidden')
  })

  it('展开多子菜单后恢复标题和箭头显示', async() => {
    const wrapper = mountSidebarItem(torrentRoute)
    const vm = wrapper.vm as SidebarHost

    vm.collapsed = false
    await vm.$nextTick()

    const title = wrapper.find('.el-submenu__title')
    expect(wrapper.find('.menu-wrapper.full-mode.first-level').exists()).toBe(true)
    expect(window.getComputedStyle(title.find('.menu-icon').element).visibility).toBe('visible')
    expect(window.getComputedStyle(title.find('.submenu-label').element).visibility).toBe('visible')
    expect(window.getComputedStyle(title.find('.submenu-chevron').element).visibility).toBe('visible')
  })

  it('单子路由菜单折叠态保持既有 Lucide 图标显示', () => {
    const wrapper = mountSidebarItem(downloaderRoute)
    const icon = wrapper.find('.el-menu-item .menu-icon')

    expect(wrapper.find('.el-submenu').exists()).toBe(false)
    expect(icon.find('svg').exists()).toBe(true)
    expect(window.getComputedStyle(icon.element).visibility).toBe('visible')
  })

  it('源码只按语义类隐藏子菜单标题和箭头，不回退为广泛 span 选择器', () => {
    expect(sidebarItemSource).toContain('class="submenu-label"')
    expect(sidebarItemSource).toMatch(/&>\.submenu-label,\s*&>\.submenu-chevron\s*\{\s*visibility: hidden;/)
    expect(sidebarItemSource).toMatch(/&>\.menu-icon\s*\{\s*visibility: visible;/)
    expect(sidebarItemSource).not.toMatch(/&>span\s*\{\s*visibility: hidden;/)
  })
})
