/**
 * 移动下拉刷新 mixin 契约（dual-mode-client Phase 4 M1 余项）：
 * - 仅当真实滚动容器已到顶且手指下拉时进入拉动（阻尼 0.5、封顶 100px）；
 * - 松手超过阈值（60px）触发 onPullRefresh，完成后状态复位；
 * - 未达阈值松手回弹不触发；未到顶/上滑不拦截原生滚动。
 * - 滚动容器判定：.mobile-content 仅在其自身确实可滚时采用，否则回落
 *   文档滚动（实际布局 min-height:100vh 下长列表滚动发生在 window）。
 * jsdom 无真实触摸布局，直调 handler 模拟 touch 事件对象驱动状态机；
 * scrollHeight/clientHeight 需显式 mock（jsdom 中均为 0）。
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

const touchAt = (y: number, x = 300): TouchEvent =>
  ({ touches: [{ clientX: x, clientY: y }], preventDefault: jest.fn(), cancelable: true }) as unknown as TouchEvent

const flushPromises = (): Promise<void> => new Promise((resolve) => { setTimeout(resolve, 0) })

/** jsdom 中 scrollHeight/clientHeight 恒为 0，按需 mock 出“容器确实可滚” */
const mockScrollMetrics = (el: HTMLElement, scrollHeight: number, clientHeight: number): void => {
  Object.defineProperty(el, 'scrollHeight', { value: scrollHeight, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: clientHeight, configurable: true })
}

describe('views/mobile/mixins/pull-to-refresh', () => {
  let wrapper: Wrapper<Vue>
  let scroller: HTMLDivElement
  const vm = (): any => wrapper.vm

  beforeEach(() => {
    scroller = document.createElement('div')
    scroller.className = 'mobile-content'
    // 默认模拟“布局壳自身可滚”的传统布局；window 滚动布局用例按需改写为 0/0
    mockScrollMetrics(scroller, 500, 400)
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

  // ============ 横向手势互斥（v1.0.6 手势：布局壳 Tab 滑动切换） ============

  it('横向主导手势（伴随下滑分量）：中止下拉不触发刷新（让位 Tab 切换）', async() => {
    scroller.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    // 水平 -150px、垂直 +40px：横向主导
    vm().onTouchMove(touchAt(540, 150))
    expect(vm().pullDistance).toBe(0)
    vm().onTouchEnd()
    expect(onPullRefresh).not.toHaveBeenCalled()
  })

  it('纵向主导手势（伴随水平分量）：仍正常进入拉动', () => {
    scroller.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    // 垂直 +150px、水平 -20px：纵向主导
    vm().onTouchMove(touchAt(650, 280))
    expect(vm().pullDistance).toBe(Math.min(150 * 0.5, 100))
  })

  it('同手势滚动回顶后再下拉：重置起点防指示条跳变（从 0 跟手）', () => {
    scroller.scrollTop = 50
    vm().onTouchStart(touchAt(500))
    // 未到顶时下拉：交给原生滚动（scrollTop 递减），不进入拉动
    vm().onTouchMove(touchAt(530))
    expect(vm().pullDistance).toBe(0)
    // 原生滚动追平，scrollTop 归 0；同手势继续下拉 30px
    scroller.scrollTop = 0
    // 回顶后第一帧：重置起点，距离归零（旧行为会把 (560-500)*0.5=30px 整段兑现成跳变）
    vm().onTouchMove(touchAt(560))
    expect(vm().pullDistance).toBe(0)
    // 后续从重置点跟手：+40px → 20px
    vm().onTouchMove(touchAt(600))
    expect(vm().pullDistance).toBe(20)
    // 阈值判定也从重置点起算：+130px → 65px 达到就绪
    vm().onTouchMove(touchAt(690))
    expect(vm().pullReady).toBe(true)
  })

  // ============ 滚动容器判定修复（2026-09-05：列表中部下滑误触发整页刷新） ============
  // 实际布局（.mobile-layout min-height:100vh）下长列表撑高布局，滚动发生在
  // window，.mobile-content 自身 scrollTop 恒为 0；修复前任意位置都被判为
  // “已到顶”，往上翻列表的下滑手势每 120px 就触发一次整页 reload。

  it('.mobile-content 不自身可滚且文档已滚：中部下滑不进入拉动、不触发刷新', () => {
    mockScrollMetrics(scroller, 0, 0)
    document.documentElement.scrollTop = 800
    const move = touchAt(700)
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(move)
    expect(vm().pullDistance).toBe(0)
    expect(move.preventDefault).not.toHaveBeenCalled()
    vm().onTouchEnd()
    expect(onPullRefresh).not.toHaveBeenCalled()
    document.documentElement.scrollTop = 0
  })

  it('.mobile-content 不自身可滚且文档已滚：先上滑再下滑的翻列表手势不触发刷新', () => {
    mockScrollMetrics(scroller, 0, 0)
    document.documentElement.scrollTop = 800
    vm().onTouchStart(touchAt(500))
    // 先上滑（滚列表）：标记手势内滚动
    vm().onTouchMove(touchAt(400))
    expect(vm().pullDistance).toBe(0)
    // 再下滑 300px（翻回上方内容）：不得进入拉动
    const move = touchAt(700)
    vm().onTouchMove(move)
    expect(vm().pullDistance).toBe(0)
    expect(move.preventDefault).not.toHaveBeenCalled()
    vm().onTouchEnd()
    expect(onPullRefresh).not.toHaveBeenCalled()
    document.documentElement.scrollTop = 0
  })

  it('.mobile-content 不自身可滚但文档在顶部：真下拉仍正常触发（修复不误伤）', async() => {
    mockScrollMetrics(scroller, 0, 0)
    document.documentElement.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(touchAt(700))
    expect(vm().pullReady).toBe(true)
    vm().onTouchEnd()
    expect(onPullRefresh).toHaveBeenCalledTimes(1)
    await flushPromises()
    expect(vm().pullRefreshing).toBe(false)
  })

  // ============ 容器可滚判定的亚像素边界（2026-09-05 回归加固） ============

  it('边界：scrollHeight-clientHeight=1px 视为不可滚（忽略容器自身 scrollTop，回落文档）', () => {
    // 差 1px 未过 >1 容差 → 容器被忽略；容器自身 scrollTop=50 不参与判定，
    // 文档在顶部 → 下拉应正常进入拉动（证明该容器确实被跳过）
    mockScrollMetrics(scroller, 401, 400)
    scroller.scrollTop = 50
    document.documentElement.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(touchAt(700))
    expect(vm().pullDistance).toBe(100)
    expect(vm().pullReady).toBe(true)
    document.documentElement.scrollTop = 0
  })

  it('边界：scrollHeight-clientHeight=2px 视为可滚（采用容器自身滚动语义）', () => {
    // 差 2px 过容差 → 容器路径；容器未到顶（scrollTop=50）→ 不进入拉动
    // （同时文档在顶部，若误走文档路径则会拉动——两用例共同钉死容差线）
    mockScrollMetrics(scroller, 402, 400)
    scroller.scrollTop = 50
    document.documentElement.scrollTop = 0
    const move = touchAt(700)
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(move)
    expect(vm().pullDistance).toBe(0)
    expect(move.preventDefault).not.toHaveBeenCalled()
  })

  it('.mobile-content 完全不存在：回落文档滚动（独立挂载/测试环境场景）', async() => {
    // 组件 $el 移出布局壳 → closest 找不到 .mobile-content
    document.body.appendChild(wrapper.element)
    document.documentElement.scrollTop = 0
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(touchAt(700))
    expect(vm().pullReady).toBe(true)
    vm().onTouchEnd()
    await flushPromises()
    expect(vm().pullRefreshing).toBe(false)
    document.documentElement.scrollTop = 800
    vm().onTouchStart(touchAt(500))
    vm().onTouchMove(touchAt(700))
    expect(vm().pullDistance).toBe(0)
    document.documentElement.scrollTop = 0
  })

  it('文档滚动布局：同手势滚回顶部后继续下拉进入拉动（橡胶带语义保留）', () => {
    mockScrollMetrics(scroller, 0, 0)
    document.documentElement.scrollTop = 800
    vm().onTouchStart(touchAt(500))
    // 未到顶时下滑 30px：交给原生滚动（文档向上滚），不进入拉动
    vm().onTouchMove(touchAt(530))
    expect(vm().pullDistance).toBe(0)
    // 原生滚动把文档滚回顶部；同手势继续下滑
    document.documentElement.scrollTop = 0
    // 回顶后第一帧：重置起点，距离归零
    vm().onTouchMove(touchAt(560))
    expect(vm().pullDistance).toBe(0)
    // 后续从重置点跟手：+130px → 65px 达到就绪
    vm().onTouchMove(touchAt(690))
    expect(vm().pullDistance).toBe(65)
    expect(vm().pullReady).toBe(true)
    document.documentElement.scrollTop = 0
  })
})
