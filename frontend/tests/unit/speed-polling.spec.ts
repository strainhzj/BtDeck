import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Component from 'vue-class-component'
import SpeedPollingMixin from '@/views/torrents/mixins/speedPolling'

/**
 * SpeedPollingMixin 生命周期回归：
 * - 1 秒链式轮询按间隔持续请求
 * - 后台标签页（document.hidden）暂停轮询，在途请求返回后不续发
 * - 恢复可见时先补一次刷新再重启轮询
 * - stopSpeedPolling / 组件销毁后无定时器残留、监听器移除
 */
@Component({
  name: 'SpeedPollingHarness',
  template: '<div class="speed-polling-harness" />'
})
class SpeedPollingHarness extends SpeedPollingMixin {
  public callCount = 0

  protected async loadActiveSpeed(): Promise<boolean> {
    this.callCount += 1
    return true
  }

  // 镜像真实组件（index.vue / TraditionalView.vue）的销毁清理模式
  public beforeDestroy() {
    this.stopSpeedPolling()
  }
}

const localVue = createLocalVue()

/** 冲刷微任务队列（await loadActiveSpeed 的 Promise 链） */
const flush = async() => {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

const setHidden = (hidden: boolean) => {
  Object.defineProperty(document, 'hidden', { value: hidden, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('SpeedPollingMixin 轮询生命周期', () => {
  let wrapper: Wrapper<SpeedPollingHarness>

  beforeEach(() => {
    jest.useFakeTimers()
    setHidden(false)
  })

  afterEach(() => {
    if (wrapper && wrapper.exists()) {
      wrapper.destroy()
    }
    jest.useRealTimers()
  })

  it('startSpeedPolling 后按 1 秒间隔持续轮询', async() => {
    wrapper = mount(SpeedPollingHarness, { localVue })
    const vm = wrapper.vm
    ;(vm as any).startSpeedPolling()
    await flush()
    expect(vm.callCount).toBe(1)

    jest.advanceTimersByTime(1000)
    await flush()
    expect(vm.callCount).toBe(2)

    jest.advanceTimersByTime(1000)
    await flush()
    expect(vm.callCount).toBe(3)

    jest.advanceTimersByTime(1000)
    await flush()
    expect(vm.callCount).toBe(4)
  })

  it('文档隐藏时暂停轮询：暂停期间不再发请求', async() => {
    wrapper = mount(SpeedPollingHarness, { localVue })
    const vm = wrapper.vm
    ;(vm as any).startSpeedPolling()
    await flush()
    expect(vm.callCount).toBe(1)

    setHidden(true)
    jest.advanceTimersByTime(5000)
    await flush()
    expect(vm.callCount).toBe(1)
  })

  it('恢复可见时先补一次刷新，再按间隔继续轮询', async() => {
    wrapper = mount(SpeedPollingHarness, { localVue })
    const vm = wrapper.vm
    ;(vm as any).startSpeedPolling()
    await flush()

    setHidden(true)
    await flush()

    setHidden(false)
    await flush()
    // 恢复时立即补一次刷新
    expect(vm.callCount).toBe(2)

    jest.advanceTimersByTime(1000)
    await flush()
    expect(vm.callCount).toBe(3)
  })

  it('stopSpeedPolling 后不再轮询，且监听器被移除（后续 visibility 事件不恢复）', async() => {
    wrapper = mount(SpeedPollingHarness, { localVue })
    const vm = wrapper.vm
    ;(vm as any).startSpeedPolling()
    await flush()
    ;(vm as any).stopSpeedPolling()
    await flush()

    setHidden(true)
    await flush()
    setHidden(false)
    await flush()
    jest.advanceTimersByTime(5000)
    await flush()
    expect(vm.callCount).toBe(1)
  })

  it('组件销毁后定时器被清理，不再有任何请求', async() => {
    wrapper = mount(SpeedPollingHarness, { localVue })
    const vm = wrapper.vm
    ;(vm as any).startSpeedPolling()
    await flush()
    expect(vm.callCount).toBe(1)

    wrapper.destroy()
    jest.advanceTimersByTime(10000)
    await flush()
    expect(vm.callCount).toBe(1)
  })

  it('重复 startSpeedPolling 幂等：不产生并发轮询', async() => {
    wrapper = mount(SpeedPollingHarness, { localVue })
    const vm = wrapper.vm
    ;(vm as any).startSpeedPolling()
    ;(vm as any).startSpeedPolling()
    await flush()

    jest.advanceTimersByTime(1000)
    await flush()
    // 若并发双轮询，1 秒后会同时触发两个请求
    expect(vm.callCount).toBe(2)
  })
})
