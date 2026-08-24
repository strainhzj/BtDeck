/**
 * 移动下拉刷新 mixin 契约（dual-mode-client Phase 4 M1 余项）：
 * - 仅当滚动容器（.mobile-content）已到顶且手指下拉时进入拉动（阻尼 0.5、封顶 100px）；
 * - 松手超过阈值（60px）触发 onPullRefresh，完成后状态复位；
 * - 未达阈值松手回弹不触发；未到顶/上滑不拦截原生滚动。
 * jsdom 无真实触摸布局，直调 handler 模拟 touch 事件对象驱动状态机。
 */

import Vue from 'vue'
import { shallowMount, Wrapper } from '@vue/test-utils'
import { PullToRefresh, PULL_REFRESH_THRESHOLD } from '@/views/mobile/mixins/pull-to-refresh'

const onPullRefresh = jest.fn().mockResolvedValue(undefined)

const Host = Vue.extend({
  mixins: [PullToRefresh],
  template: '<div class="host">page</div>',
  methods: { onPullRefresh }
})

const touchAt = (y: number): TouchEvent =>
  ({ touches: [{ clientY: y }], preventDefault: jest.fn(), cancelable: true }) as unknown as TouchEvent

const flushPromises = (): Promise<void> => new Promise((resolve) => { setTimeout(resolve, 0) })

describe('views/mobile/mixins/pull-to-refresh', () => {
  let wrapper: Wrapper<Vue>
  let scroller: HTMLDivElement
  const vm = (): any => wrapper.vm

  beforeEach(() => {
    scroller = document.createElement('div')
    scroller.className = 'mobile-content'
    document.body.appendChild(scroller)
    wrapper = shallowMount(Host)
    scroller.appendChild(wrapper.element)
  })

  afterEach(() => {
    wrapper.destroy()
    if (scroller.parentNode) scroller.parentNode.removeChild(scroller)
    jest.clearAllMocks()
  })

  it('到顶下拉超过阈值松手：触发 onPullRefresh 并复位状态', async() => {
    scroller.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(touchAt(700))
    // 阻尼 0.5：delta 200 → 100px（同时验证封顶）
    expect(vm().pullDistance).toBe(100)
    expect(vm().pullReady).toBe(true)
    vm().onTouchEnd()
    expect(onPullRefresh).toHaveBeenCalledTimes(1)
    await flushPromises()
    expect(vm().pullRefreshing).toBe(false)
    expect(vm().pullDistance).toBe(0)
  })

  it('下拉未达阈值松手：回弹且不触发刷新', () => {
    scroller.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    // delta 60 → 阻尼后 30px < 阈值 60px
    vm().onTouchMove(touchAt(560))
    expect(vm().pullDistance).toBe(30)
    expect(vm().pullReady).toBe(false)
    vm().onTouchEnd()
    expect(onPullRefresh).not.toHaveBeenCalled()
    expect(vm().pullDistance).toBe(0)
  })

  it('滚动容器未到顶：不进入拉动、不 preventDefault（交给原生滚动）', () => {
    scroller.scrollTop = 50
    const move = touchAt(700)
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(move)
    expect(vm().pullDistance).toBe(0)
    expect(move.preventDefault).not.toHaveBeenCalled()
  })

  it('上滑（delta<=0）：距离归零不拦截', () => {
    scroller.scrollTop = 0
    const move = touchAt(480)
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(move)
    expect(vm().pullDistance).toBe(0)
    expect(move.preventDefault).not.toHaveBeenCalled()
  })

  it('拉动时 preventDefault 阻止原生滚动/回弹', () => {
    scroller.scrollTop = 0
    const move = touchAt(700)
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(move)
    expect(move.preventDefault).toHaveBeenCalled()
  })

  it('阈值常量导出为 60（与产品约定一致）', () => {
    expect(PULL_REFRESH_THRESHOLD).toBe(60)
  })
})
