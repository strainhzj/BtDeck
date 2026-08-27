import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import { Loading } from 'element-ui'

interface LoadingHarnessVm extends Vue {
  listLoading: boolean
}

interface LoadingDirectiveTarget extends HTMLElement {
  domVisible?: boolean
  instance?: Vue & { visible: boolean }
}

describe('种子查询全屏锁滚动蒙版', () => {
  const localVue = createLocalVue()
  localVue.use(Loading.directive)

  const Harness = localVue.extend({
    name: 'TorrentLoadingMaskHarness',
    data() {
      return { listLoading: false }
    },
    template: `
      <section
        class="torrent-query-target"
        v-loading.fullscreen.lock="listLoading"
        element-loading-text="加载中..."
      >
        query content
      </section>
    `
  })

  let wrapper: Wrapper<Vue> | null = null

  async function flushDirective(): Promise<void> {
    await localVue.nextTick()
    await Promise.resolve()
    await localVue.nextTick()
  }

  afterEach(() => {
    wrapper?.destroy()
    wrapper = null
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
    document.body.classList.remove(
      'el-loading-parent--relative',
      'el-loading-parent--hidden'
    )
    document.querySelectorAll('.el-loading-mask').forEach(node => node.remove())
  })

  it('加载时把 fullscreen mask 挂到 body 并锁定页面滚动，结束后解除锁定', async() => {
    jest.useFakeTimers()
    wrapper = mount(Harness, {
      localVue,
      attachTo: document.body
    })
    const vm = wrapper.vm as LoadingHarnessVm
    const target = wrapper.find('.torrent-query-target').element as LoadingDirectiveTarget

    vm.listLoading = true
    await flushDirective()

    const mask = document.body.querySelector('.el-loading-mask.is-fullscreen') as HTMLElement | null
    expect(mask).not.toBeNull()
    expect(wrapper.element.contains(mask)).toBe(false)
    expect(document.body.classList.contains('el-loading-parent--hidden')).toBe(true)
    expect(target.domVisible).toBe(true)
    expect(target.instance?.visible).toBe(true)

    vm.listLoading = false
    await flushDirective()
    // Element UI after-leave 的无动画兜底为 speed(300ms) + 100ms。
    jest.advanceTimersByTime(450)
    await flushDirective()

    expect(document.body.classList.contains('el-loading-parent--hidden')).toBe(false)
    expect(target.domVisible).toBe(false)
    expect(target.instance?.visible).toBe(false)
  })

  it('组件在加载期间销毁会移除全屏 mask 并释放 body 滚动锁', async() => {
    jest.useFakeTimers()
    wrapper = mount(Harness, {
      localVue,
      attachTo: document.body
    })
    const vm = wrapper.vm as LoadingHarnessVm
    vm.listLoading = true
    await flushDirective()

    expect(document.body.querySelector('.el-loading-mask.is-fullscreen')).not.toBeNull()
    expect(document.body.classList.contains('el-loading-parent--hidden')).toBe(true)

    wrapper.destroy()
    wrapper = null
    jest.advanceTimersByTime(450)
    await flushDirective()

    expect(document.body.querySelector('.el-loading-mask.is-fullscreen')).toBeNull()
    expect(document.body.classList.contains('el-loading-parent--hidden')).toBe(false)
  })
})
