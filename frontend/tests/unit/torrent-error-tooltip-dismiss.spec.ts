import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'

import TorrentErrorTooltipDismissMixin from '@/views/torrents/mixins/errorTooltipDismiss'

describe('TorrentErrorTooltipDismissMixin', () => {
  const localVue = createLocalVue()
  const elementLocalVue = createLocalVue()
  elementLocalVue.use(ElementUI)

  const hideTooltip = jest.fn()
  let wrapper: Wrapper<Vue> | null = null

  const TooltipStub = localVue.extend({
    name: 'ElTooltipStub',
    data() {
      return { visible: true }
    },
    methods: {
      hide() {
        hideTooltip()
        this.visible = false
      }
    },
    template: '<span class="tooltip-stub" :data-visible="String(visible)"><slot /></span>'
  })

  const Harness = localVue.extend({
    name: 'TorrentErrorTooltipHarness',
    mixins: [TorrentErrorTooltipDismissMixin],
    components: {
      ElTooltip: TooltipStub
    },
    data() {
      return { rows: ['first', 'second'] }
    },
    template: `
      <div class="scroll-target">
        <el-tooltip
          v-for="row in rows"
          :key="row"
          ref="torrentErrorTooltips"
        >
          <span>{{ row }}</span>
        </el-tooltip>
      </div>
    `
  })

  const SingletonHarness = localVue.extend({
    name: 'TorrentErrorTooltipSingletonHarness',
    mixins: [TorrentErrorTooltipDismissMixin],
    components: {
      ElTooltip: TooltipStub
    },
    template: `
      <div class="scroll-target">
        <el-tooltip ref="torrentErrorTooltips">
          <span>single</span>
        </el-tooltip>
      </div>
    `
  })

  const EmptyHarness = localVue.extend({
    name: 'TorrentErrorTooltipEmptyHarness',
    mixins: [TorrentErrorTooltipDismissMixin],
    template: '<div class="scroll-target">empty</div>'
  })

  const DomRefHarness = localVue.extend({
    name: 'TorrentErrorTooltipDomRefHarness',
    mixins: [TorrentErrorTooltipDismissMixin],
    template: '<div><span ref="torrentErrorTooltips">plain element</span></div>'
  })

  const ElementTooltipHarness = elementLocalVue.extend({
    name: 'TorrentErrorTooltipElementHarness',
    mixins: [TorrentErrorTooltipDismissMixin],
    template: `
      <el-tooltip
        ref="torrentErrorTooltips"
        content="真实错误原因"
        :enterable="false"
        :open-delay="0"
      >
        <button type="button">错误种子</button>
      </el-tooltip>
    `
  })

  beforeEach(() => {
    hideTooltip.mockClear()
  })

  afterEach(() => {
    wrapper?.destroy()
    wrapper = null
    document.querySelectorAll('.el-tooltip__popper').forEach(node => node.remove())
  })

  it('以同一监听器注册捕获阶段滚动和被动滚轮，并在销毁时对称解绑', () => {
    const addEventListenerSpy = jest.spyOn(window, 'addEventListener')
    const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener')

    try {
      wrapper = mount(Harness, { localVue })

      const scrollRegistration = addEventListenerSpy.mock.calls.find(call => call[0] === 'scroll')
      const wheelRegistration = addEventListenerSpy.mock.calls.find(call => call[0] === 'wheel')
      expect(scrollRegistration).toBeDefined()
      expect(wheelRegistration).toBeDefined()
      expect(scrollRegistration?.[2]).toBe(true)
      expect(wheelRegistration?.[2]).toEqual({ capture: true, passive: true })
      expect(wheelRegistration?.[1]).toBe(scrollRegistration?.[1])

      const listener = scrollRegistration?.[1]
      wrapper.destroy()
      wrapper = null

      expect(removeEventListenerSpy).toHaveBeenCalledWith('scroll', listener, true)
      expect(removeEventListenerSpy).toHaveBeenCalledWith('wheel', listener, true)
    } finally {
      addEventListenerSpy.mockRestore()
      removeEventListenerSpy.mockRestore()
    }
  })

  it('滚轮手势和非冒泡后代滚动都会关闭当前页全部错误提示', async() => {
    wrapper = mount(Harness, {
      localVue,
      attachTo: document.body
    })

    wrapper.element.dispatchEvent(new Event('wheel', { bubbles: true }))
    await localVue.nextTick()
    expect(hideTooltip).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.tooltip-stub').wrappers.every(
      tooltip => tooltip.attributes('data-visible') === 'false'
    )).toBe(true)

    wrapper.element.dispatchEvent(new Event('scroll', { bubbles: false }))
    expect(hideTooltip).toHaveBeenCalledTimes(4)
  })

  it('window 自身滚动也会关闭全部错误提示', () => {
    wrapper = mount(Harness, { localVue })

    window.dispatchEvent(new Event('scroll'))

    expect(hideTooltip).toHaveBeenCalledTimes(2)
  })

  it('兼容 Vue 对单个 tooltip ref 返回组件实例而非数组', async() => {
    wrapper = mount(SingletonHarness, { localVue })

    window.dispatchEvent(new Event('wheel'))
    await localVue.nextTick()

    expect(hideTooltip).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.tooltip-stub').attributes('data-visible')).toBe('false')
  })

  it('没有 tooltip ref 或 ref 不是组件时滚动不会抛错', () => {
    wrapper = mount(EmptyHarness, { localVue })
    expect(() => window.dispatchEvent(new Event('wheel'))).not.toThrow()
    wrapper.destroy()

    wrapper = mount(DomRefHarness, { localVue })
    expect(() => window.dispatchEvent(new Event('scroll'))).not.toThrow()
    expect(hideTooltip).not.toHaveBeenCalled()
  })

  it('组件销毁后不再响应事件，重新挂载也不会叠加旧监听器', () => {
    wrapper = mount(Harness, {
      localVue,
      attachTo: document.body
    })
    wrapper.destroy()
    wrapper = null

    window.dispatchEvent(new Event('wheel'))
    window.dispatchEvent(new Event('scroll'))
    expect(hideTooltip).not.toHaveBeenCalled()

    wrapper = mount(Harness, { localVue })
    window.dispatchEvent(new Event('wheel'))
    expect(hideTooltip).toHaveBeenCalledTimes(2)
  })

  it('真实 Element UI Tooltip 在滚轮后清除期望状态并完成关闭', async() => {
    jest.useFakeTimers()
    try {
      wrapper = mount(ElementTooltipHarness, {
        localVue: elementLocalVue,
        attachTo: document.body
      })
      const tooltip = wrapper.findComponent({ name: 'ElTooltip' }).vm as Vue & {
        show(): void
        expectedState: boolean
        showPopper: boolean
      }

      tooltip.show()
      jest.runOnlyPendingTimers()
      await elementLocalVue.nextTick()
      expect(tooltip.expectedState).toBe(true)
      expect(tooltip.showPopper).toBe(true)

      wrapper.element.dispatchEvent(new Event('wheel', { bubbles: true }))
      expect(tooltip.expectedState).toBe(false)

      jest.advanceTimersByTime(250)
      await elementLocalVue.nextTick()
      expect(tooltip.showPopper).toBe(false)
    } finally {
      wrapper?.destroy()
      wrapper = null
      jest.runOnlyPendingTimers()
      jest.useRealTimers()
    }
  })
})
