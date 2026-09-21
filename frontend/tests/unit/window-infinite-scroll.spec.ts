/**
 * 移动端 window 无限滚动 mixin 契约（2026-09-05 无限加载失控根修）：
 * - 挂载注册 window 滚动监听、销毁移除（原型方法，this 指向正确）；
 * - 距视口底部阈值内触发子类 loadMore；未达阈值/门禁禁用不触发；
 * - 短内容页（scrollHeight ≤ clientHeight）视为在底部（供加载后补页）；
 * - infiniteDisabled 门禁由子类覆写承担。
 * jsdom 无真实布局，documentElement 的 scrollHeight/clientHeight/scrollTop 需显式 mock。
 */

import Vue from 'vue'
import { shallowMount, Wrapper } from '@vue/test-utils'
import {
  WindowInfiniteScroll,
  WINDOW_LOAD_MORE_DISTANCE_PX
} from '@/views/mobile/mixins/window-infinite-scroll'

const loadMore = jest.fn().mockResolvedValue(undefined)

const Host = Vue.extend({
  mixins: [WindowInfiniteScroll],
  template: '<div class="host">list</div>',
  data() {
    return { loading: false, done: false }
  },
  computed: {
    infiniteDisabled(): boolean {
      return this.loading || this.done
    }
  },
  methods: { loadMore }
})

const mockGeometry = (scrollHeight: number, clientHeight: number, scrollTop = 0): void => {
  Object.defineProperty(document.documentElement, 'scrollHeight', { value: scrollHeight, configurable: true })
  Object.defineProperty(document.documentElement, 'clientHeight', { value: clientHeight, configurable: true })
  Object.defineProperty(document.documentElement, 'scrollTop', { value: scrollTop, configurable: true })
}

describe('views/mobile/mixins/window-infinite-scroll', () => {
  let wrapper: Wrapper<Vue>
  const vm = (): any => wrapper.vm

  beforeEach(() => {
    // 默认“内容远高于一屏、未滚到底”
    mockGeometry(20000, 844, 0)
    wrapper = shallowMount(Host)
  })

  afterEach(() => {
    wrapper.destroy()
    jest.clearAllMocks()
  })

  it('挂载注册 window 滚动监听：滚动到底部触发一次 loadMore', async() => {
    expect(loadMore).not.toHaveBeenCalled()
    // 滚到距底 60px 内：scrollTop = 20000 - 844 - 60
    mockGeometry(20000, 844, 20000 - 844 - WINDOW_LOAD_MORE_DISTANCE_PX)
    window.dispatchEvent(new Event('scroll'))
    await Promise.resolve()
    expect(loadMore).toHaveBeenCalledTimes(1)
  })

  it('未到阈值不触发：距底超过 60px 的普通滚动', () => {
    mockGeometry(20000, 844, 20000 - 844 - WINDOW_LOAD_MORE_DISTANCE_PX - 1)
    window.dispatchEvent(new Event('scroll'))
    expect(loadMore).not.toHaveBeenCalled()
  })

  it('门禁禁用（loading/拉满）不触发', () => {
    mockGeometry(20000, 844, 20000)
    ;(wrapper.vm as any).loading = true
    window.dispatchEvent(new Event('scroll'))
    expect(loadMore).not.toHaveBeenCalled()
    ;(wrapper.vm as any).loading = false
    ;(wrapper.vm as any).done = true
    window.dispatchEvent(new Event('scroll'))
    expect(loadMore).not.toHaveBeenCalled()
  })

  it('短内容页（scrollHeight ≤ clientHeight）视为在底部：maybeLoadMore 触发补页', () => {
    mockGeometry(600, 844)
    vm().maybeLoadMore()
    expect(loadMore).toHaveBeenCalledTimes(1)
  })

  it('isNearViewportBottom 读取 window.scrollY 优先（与返回顶部浮标同源读法）', () => {
    mockGeometry(20000, 844, 0)
    const original = window.scrollY
    Object.defineProperty(window, 'scrollY', { value: 20000 - 844 - 10, configurable: true, writable: true })
    expect(vm().isNearViewportBottom()).toBe(true)
    Object.defineProperty(window, 'scrollY', { value: 100, configurable: true, writable: true })
    expect(vm().isNearViewportBottom()).toBe(false)
    Object.defineProperty(window, 'scrollY', { value: original, configurable: true, writable: true })
  })

  it('销毁移除监听：destroy 后滚动不再触发', async() => {
    wrapper.destroy()
    mockGeometry(20000, 844, 20000)
    window.dispatchEvent(new Event('scroll'))
    expect(loadMore).not.toHaveBeenCalled()
  })

  it('滚动风暴重入门禁：门禁置位期间连续滚动事件不叠加 loadMore', () => {
    mockGeometry(20000, 844, 20000)
    window.dispatchEvent(new Event('scroll'))
    expect(loadMore).toHaveBeenCalledTimes(1)
    // 子类 loadMore 在途（loading=true → infiniteDisabled）期间的滚动风暴只被吞掉
    ;(wrapper.vm as any).loading = true
    for (let i = 0; i < 10; i += 1) window.dispatchEvent(new Event('scroll'))
    expect(loadMore).toHaveBeenCalledTimes(1)
    // 门禁解除后下一次滚动才允许再次加载
    ;(wrapper.vm as any).loading = false
    window.dispatchEvent(new Event('scroll'))
    expect(loadMore).toHaveBeenCalledTimes(2)
  })

  it('阈值常量为 60（沿原 infinite-scroll-distance 语义）', () => {
    expect(WINDOW_LOAD_MORE_DISTANCE_PX).toBe(60)
  })
})
