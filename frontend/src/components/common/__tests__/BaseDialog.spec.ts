import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import i18n from '@/i18n'
import BaseDialog from '../BaseDialog.vue'
import LucideIcon from '../LucideIcon.vue'

/**
 * BaseDialog 单测
 *
 * 覆盖：
 * - 渲染契约：visible 控制蒙层激活态、标题/图标/关闭钮
 * - 关闭路径：关闭钮 / 蒙层点击(click.self) / ESC，及 closeOnOverlay/closeOnEsc 开关
 * - body 滚动锁：开启锁定、关闭恢复、销毁兜底
 * - footer 插槽出现性
 * - ≤768 移动端源码契约（自 TorrentAddDialog 迁入：顶铆全宽/接管滚动/role=dialog）
 */
const localVue = createLocalVue()
localVue.component('LucideIcon', LucideIcon)

const mountDialog = (propsData: Record<string, unknown> = {}): Wrapper<Vue> =>
  mount(BaseDialog, {
    localVue,
    i18n,
    propsData: { title: 'Test dialog', ...propsData }
  })

describe('BaseDialog 全自定义弹窗壳', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
    document.body.style.overflow = ''
  })

  it('visible 控制蒙层激活态；标题与关闭钮渲染', async() => {
    wrapper = mountDialog({ visible: false })
    expect(wrapper.find('.modal-overlay').exists()).toBe(true)
    expect(wrapper.find('.modal-overlay.active').exists()).toBe(false)

    await wrapper.setProps({ visible: true })
    expect(wrapper.find('.modal-overlay.active').exists()).toBe(true)
    expect(wrapper.find('.modal-title').text()).toBe('Test dialog')
    // 传入 icon 时渲染 LucideIcon 真实 svg
    await wrapper.setProps({ icon: 'plus-circle' })
    expect(wrapper.find('.modal-header__icon svg').exists()).toBe(true)
    const closeBtn = wrapper.find('.modal-close')
    expect(closeBtn.attributes('aria-label')).toBe('关闭')
  })

  it('关闭钮点击：发出 update:visible(false) 与 close', async() => {
    wrapper = mountDialog({ visible: true })
    await wrapper.find('.modal-close').trigger('click')
    expect(wrapper.emitted('update:visible')).toEqual([[false]])
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('蒙层点击自身关闭；点击弹窗内容不关闭（click.self 语义）', async() => {
    wrapper = mountDialog({ visible: true })
    await wrapper.find('.modal-dialog').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()

    await wrapper.find('.modal-overlay').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('closeOnOverlay=false：点击蒙层不关闭', async() => {
    wrapper = mountDialog({ visible: true, closeOnOverlay: false })
    await wrapper.find('.modal-overlay').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('ESC 关闭；closeOnEsc=false 不响应', async() => {
    wrapper = mountDialog({ visible: true })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await Vue.nextTick()
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.destroy()

    wrapper = mountDialog({ visible: true, closeOnEsc: false })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await Vue.nextTick()
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('body 滚动锁：visible 开启锁定、关闭恢复、销毁兜底恢复', async() => {
    wrapper = mountDialog({ visible: true })
    expect(document.body.style.overflow).toBe('hidden')

    await wrapper.setProps({ visible: false })
    expect(document.body.style.overflow).not.toBe('hidden')

    await wrapper.setProps({ visible: true })
    expect(document.body.style.overflow).toBe('hidden')
    wrapper.destroy()
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('footer 插槽：无插槽不渲染容器；提供 footer-right 时渲染', () => {
    wrapper = mountDialog({ visible: true })
    expect(wrapper.find('.modal-footer').exists()).toBe(false)
    wrapper.destroy()

    wrapper = mount(BaseDialog, {
      localVue,
      i18n,
      propsData: { visible: true, title: 'T' },
      slots: { 'footer-right': '<button class="stub-btn">OK</button>' }
    })
    expect(wrapper.find('.modal-footer').exists()).toBe(true)
    expect(wrapper.find('.stub-btn').exists()).toBe(true)
  })

  it('≤768 源码契约：顶铆全宽（!important 压制内联宽度）+ overlay 接管滚动 + 对话框语义', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/components/common/BaseDialog.vue', 'utf-8')
    expect(source).toContain('@media (max-width: 768px)')
    // 根元素带内联 max-width（prop 注入），非 !important 压不下去
    expect(source).toContain('max-width: calc(100vw - 24px) !important')
    expect(source).toContain('align-items: flex-start')
    // overlay 接管滚动（弹窗自身 85vh 上限让位）
    expect(source).toMatch(/\.modal-overlay\.active\s*{[^}]*overflow-y: auto/s)
    // 对话框可访问性语义
    expect(source).toContain('role="dialog"')
    expect(source).toContain('aria-modal="true"')
  })
})

describe('BaseDialog 滚动结构整体化（源码契约）', () => {
  // jsdom 不做真实布局：三段纵列（头/底固定、仅 body 滚动）与主题色滚动条走源码契约，
  // 视觉由真机/模拟器兜底（本仓既有模式）
  const readSource = (): string => {
    const fs = require('fs') as typeof import('fs')
    return fs.readFileSync('src/components/common/BaseDialog.vue', 'utf-8')
  }

  it('三段纵列：dialog 整窗滚动禁回流（割裂感根因），头/底固定仅 body 滚动', () => {
    const source = readSource()
    // 整窗滚动（overflow-y:auto 贯穿渐变头到 footer）不得回流：滚动条贴边像“另一块”
    const dialogRule = source.match(/\.modal-dialog\s*{([^}]*)}/s)?.[1] ?? ''
    expect(dialogRule).toContain('display: flex')
    expect(dialogRule).toContain('flex-direction: column')
    expect(dialogRule).toContain('overflow: hidden')
    expect(dialogRule).not.toContain('overflow-y')

    // 头/底固定不随内容滚走：渐变头常驻、操作钮始终可见
    expect(source.match(/\.modal-header\s*{([^}]*)}/s)?.[1]).toContain('flex-shrink: 0')
    expect(source.match(/\.modal-footer\s*{([^}]*)}/s)?.[1]).toContain('flex-shrink: 0')

    // 唯一滚动区收敛在表单主体：flex 占位 + overflow-y + 主题色滚动条接入
    const bodyRule = source.match(/\.modal-body\s*{([^}]*)}/s)?.[1] ?? ''
    expect(bodyRule).toContain('flex: 1 1 auto')
    expect(bodyRule).toContain('min-height: 0')
    expect(bodyRule).toContain('overflow-y: auto')
    expect(bodyRule).toContain('@include themed-scrollbar')
  })

  it('themed-scrollbar 滑块用主题色着色：禁中性灰回流（与全局通用样式视觉无法区分的回归）', () => {
    const fs = require('fs') as typeof import('fs')
    const mixin = fs.readFileSync('src/styles/_mixins.scss', 'utf-8')
    expect(mixin).toContain('@mixin themed-scrollbar')
    // 主题色着色：rgba(--color-primary-rgb) 静止 0.45 / 悬停 0.75（emerald/orange/graphite 自适应）
    expect(mixin).toContain('rgba(var(--color-primary-rgb), 0.45)')
    expect(mixin).toContain('rgba(var(--color-primary-rgb), 0.75)')
    // Firefox 标准属性双覆盖
    expect(mixin).toContain('scrollbar-width: thin')
    expect(mixin).toContain('scrollbar-color: rgba(var(--color-primary-rgb), 0.45) transparent')
    // 中性灰禁令：--color-border-primary（#E5E7EB）与全局 rgba(0,0,0,0.2) 视觉无法区分，
    // 用了即“看不见主题化”（2026-10-18 首版实现的回归根因）
    expect(mixin).not.toContain('--color-border-primary')
  })
})
