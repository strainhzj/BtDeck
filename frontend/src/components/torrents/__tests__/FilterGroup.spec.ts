import { mount, createLocalVue } from '@vue/test-utils'
import ElementUI from 'element-ui'
import FilterGroup from '../FilterGroup.vue'
import LucideIcon from '../../common/LucideIcon.vue'

/**
 * FilterGroup 回归测试
 *
 * 背景：传统视图 TraditionalView 左侧的「状态/下载器/分类/标签」过滤器都走 FilterGroup。
 * 本次 emoji→Lucide 改造把 .filter-icon 从文本插值 {{ item.icon }} 改为
 * <LucideIcon :name="item.icon">，且 TraditionalView 各 filterItems 的 icon 值
 * 从 emoji（🖥/🔵/📂/🏷/📥/⚡）改为 Lucide 图标名（server/circle/folder/...）。
 *
 * 不变量（任一回退都会让过滤器图标列渲染成字面字符串或空白）：
 *   1. icon 字段以 Lucide 图标名形式渲染为真实 svg（非文本插值）；
 *   2. 文本 "trending-up" 等图标名不会原样打印到 DOM 文本里；
 *   3. icon 缺省时该 span 仍渲染但不出现 svg。
 */
const localVue = createLocalVue()
localVue.use(ElementUI)
// FilterGroup.vue 在生产环境通过 main.ts 全局注册 LucideIcon；
// 单测 mount 不经 main.ts，需在此显式注册，否则 <LucideIcon> 不渲染 svg。
localVue.component('LucideIcon', LucideIcon)

interface FilterItem {
  icon: string
  label: string
  value: string
  count?: number
}

describe('FilterGroup —— emoji→Lucide 改造契约', () => {
  const items: FilterItem[] = [
    { icon: 'inbox', label: '全部', value: '' },
    { icon: 'trending-up', label: '做种中', value: 'seeding' },
    { icon: 'server', label: '下载器A', value: 'dl1' }
  ]

  it('filter-icon 应渲染 LucideIcon 真实 svg（而非把图标名当文本打印）', () => {
    const wrapper = mount(FilterGroup, {
      localVue,
      propsData: { title: '状态', items }
    })
    const icons = wrapper.findAll('.filter-icon')
    expect(icons.length).toBe(items.length)
    // 每个 filter-icon 内应有真实 svg（v-if=item.icon 已守护）
    for (let i = 0; i < items.length; i++) {
      expect(icons.at(i).find('svg').exists()).toBe(true)
      expect(icons.at(i).find('.lucide-icon--missing').exists()).toBe(false)
    }
    // 图标名不应作为纯文本出现在 DOM 里（旧实现会原样打印 "trending-up"）
    const domText = wrapper.text()
    expect(domText).not.toContain('trending-up')
    expect(domText).not.toContain('server')
    expect(domText).not.toContain('inbox')
    wrapper.destroy()
  })

  it('filter-label 仍渲染纯文本 label', () => {
    const wrapper = mount(FilterGroup, {
      localVue,
      propsData: { title: '状态', items }
    })
    const domText = wrapper.text()
    expect(domText).toContain('全部')
    expect(domText).toContain('做种中')
    expect(domText).toContain('下载器A')
    wrapper.destroy()
  })

  it('icon 缺省时不渲染 svg，不报错', () => {
    const partialItems: FilterItem[] = [
      { icon: 'tag', label: '有图标', value: 'a' },
      { icon: '', label: '无图标', value: 'b' }
    ]
    const wrapper = mount(FilterGroup, {
      localVue,
      propsData: { title: '分类', items: partialItems }
    })
    const icons = wrapper.findAll('.filter-icon')
    expect(icons.at(0).find('svg').exists()).toBe(true)
    // 空 icon（v-if=false）→ 不渲染 svg
    expect(icons.at(1).find('svg').exists()).toBe(false)
    wrapper.destroy()
  })

  it('点击 item 仍向上 emit select 事件与对应 value', async() => {
    const wrapper = mount(FilterGroup, {
      localVue,
      propsData: { title: '状态', items }
    })
    await wrapper.findAll('.filter-item').at(1).trigger('click')
    const events = wrapper.emitted('select')
    expect(events?.[0][0]).toBe('seeding')
    wrapper.destroy()
  })
})
