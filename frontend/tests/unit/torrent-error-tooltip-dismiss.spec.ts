import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'

import TorrentErrorTooltipDismissMixin from '@/views/torrents/mixins/errorTooltipDismiss'

describe('TorrentErrorTooltipDismissMixin', () => {
  const localVue = createLocalVue()
  const hideTooltip = jest.fn()
  let wrapper: Wrapper<Vue> | null = null

  const TooltipStub = localVue.extend({
    name: 'ElTooltipStub',
    methods: {
      hide: hideTooltip
    },
    template: '<span class="tooltip-stub"><slot /></span>'
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

  beforeEach(() => {
    hideTooltip.mockClear()
  })

  afterEach(() => {
    wrapper?.destroy()
    wrapper = null
  })

  it('滚轮手势和后代滚动都会关闭当前页全部错误提示', () => {
    wrapper = mount(Harness, {
      localVue,
      attachTo: document.body
    })

    wrapper.element.dispatchEvent(new Event('wheel', { bubbles: true }))
    expect(hideTooltip).toHaveBeenCalledTimes(2)

    wrapper.element.dispatchEvent(new Event('scroll', { bubbles: false }))
    expect(hideTooltip).toHaveBeenCalledTimes(4)
  })

  it('组件销毁后不再响应全局滚轮或滚动事件', () => {
    wrapper = mount(Harness, {
      localVue,
      attachTo: document.body
    })
    wrapper.destroy()
    wrapper = null

    window.dispatchEvent(new Event('wheel'))
    window.dispatchEvent(new Event('scroll'))
    expect(hideTooltip).not.toHaveBeenCalled()
  })
})
