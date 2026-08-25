/**
 * SW 新版本提示组件契约（v1.0.6 PWA 完整启用）：
 * - registerServiceWorker updated() 派发 SW_UPDATED_EVENT 后弹条可见，可手动关闭；
 * - 「立即刷新」：有 waiting worker 时 postMessage SKIP_WAITING，controllerchange
 *   到达后重载一次（去抖）；无容器/无 waiting 直接重载兜底；
 * - 销毁时解绑全局事件。
 * jsdom 无 SW 实现，serviceWorkerContainer 通过 defineProperty 注入替身。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import RefreshPrompt from '@/components/common/RefreshPrompt.vue'
import { SW_UPDATED_EVENT } from '@/registerServiceWorker'

// register-service-worker 为纯 ESM 包（Jest 不转换 node_modules），mock 掉
// register；测试环境 NODE_ENV=test，registerServiceWorker 本身也不会执行注册。
jest.mock('register-service-worker', () => ({ register: jest.fn() }))

interface FakeContainer {
  listeners: Record<string, Array<EventListener>>
  addEventListener: (type: string, listener: EventListener) => void
  removeEventListener: (type: string, listener: EventListener) => void
}

const makeContainer = (): FakeContainer => {
  const listeners: Record<string, Array<EventListener>> = {}
  return {
    listeners,
    addEventListener(type, listener) {
      listeners[type] = listeners[type] || []
      listeners[type].push(listener)
    },
    removeEventListener(type, listener) {
      listeners[type] = (listeners[type] || []).filter(item => item !== listener)
    }
  }
}

const defineServiceWorker = (container: FakeContainer | undefined): void => {
  Object.defineProperty(navigator, 'serviceWorker', {
    value: container,
    configurable: true
  })
}

const dispatchUpdate = (registration: unknown): void => {
  window.dispatchEvent(new CustomEvent(SW_UPDATED_EVENT, { detail: { registration } }))
}

describe('components/common/RefreshPrompt', () => {
  let wrapper: Wrapper<Vue>
  let doReload: jest.Mock<void, []>

  const mountPrompt = (): Wrapper<Vue> => {
    wrapper = shallowMount(RefreshPrompt)
    doReload = jest.fn<void, []>()
    ;(wrapper.vm as unknown as { doReload: jest.Mock<void, []> }).doReload = doReload
    return wrapper
  }

  afterEach(() => {
    if (wrapper) wrapper.destroy()
    defineServiceWorker(undefined)
    window.dispatchEvent(new Event('noop'))
    jest.clearAllMocks()
  })

  it('默认不可见；SW_UPDATED_EVENT 到达后弹条显示', async() => {
    const w = mountPrompt()
    expect(w.find('.btdeck-refresh-prompt').exists()).toBe(false)
    dispatchUpdate({ waiting: { postMessage: jest.fn() } })
    await w.vm.$nextTick()
    expect(w.find('.btdeck-refresh-prompt').exists()).toBe(true)
    expect(w.find('.btdeck-refresh-text').text()).toBe('发现新版本')
  })

  it('关闭按钮隐藏弹条（下轮 updated 事件可再次弹出）', async() => {
    const w = mountPrompt()
    dispatchUpdate({ waiting: { postMessage: jest.fn() } })
    await w.vm.$nextTick()
    w.find('.btdeck-refresh-dismiss').trigger('click')
    await w.vm.$nextTick()
    expect(w.find('.btdeck-refresh-prompt').exists()).toBe(false)
    dispatchUpdate({ waiting: { postMessage: jest.fn() } })
    await w.vm.$nextTick()
    expect(w.find('.btdeck-refresh-prompt').exists()).toBe(true)
  })

  it('无 serviceWorker 容器：点刷新直接重载兜底', async() => {
    defineServiceWorker(undefined)
    const w = mountPrompt()
    dispatchUpdate({ waiting: { postMessage: jest.fn() } })
    await w.vm.$nextTick()
    w.find('.btdeck-refresh-apply').trigger('click')
    expect(doReload).toHaveBeenCalledTimes(1)
  })

  it('有容器与 waiting：postMessage SKIP_WAITING，controllerchange 后重载一次', async() => {
    const container = makeContainer()
    defineServiceWorker(container)
    const postMessage = jest.fn()
    const w = mountPrompt()
    dispatchUpdate({ waiting: { postMessage } })
    await w.vm.$nextTick()
    w.find('.btdeck-refresh-apply').trigger('click')
    expect(postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    expect(doReload).not.toHaveBeenCalled()

    const changeListeners = container.listeners.controllerchange || []
    expect(changeListeners.length).toBe(1)
    changeListeners.forEach(listener => listener(new Event('controllerchange')))
    changeListeners.forEach(listener => listener(new Event('controllerchange')))
    expect(doReload).toHaveBeenCalledTimes(1)
  })

  it('registration 无 waiting（他页已激活）：点刷新直接重载', async() => {
    const container = makeContainer()
    defineServiceWorker(container)
    const w = mountPrompt()
    dispatchUpdate({ waiting: null })
    await w.vm.$nextTick()
    w.find('.btdeck-refresh-apply').trigger('click')
    expect(doReload).toHaveBeenCalledTimes(1)
  })

  it('销毁后不再响应 updated 事件', async() => {
    const w = mountPrompt()
    w.destroy()
    dispatchUpdate({ waiting: { postMessage: jest.fn() } })
    await Promise.resolve()
    expect((w.vm as unknown as { visible: boolean }).visible).toBe(false)
  })
})
