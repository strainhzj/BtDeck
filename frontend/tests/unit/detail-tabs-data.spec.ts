import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Component from 'vue-class-component'

/**
 * TrackerDetailDataMixin 生命周期与竞态回归（TrackerDetailCard 文件/Peers 页签数据源）：
 * - 文件页签按 `${downloader_id}:${hash}` 键控懒加载，同键缓存不重复拉取，手动刷新强制重取
 * - Peers 页签切入立即拉取并按 5s 链式轮询（请求完成后再 arm 下一次，不堆叠）
 * - 离开 peers / currentRow 置空（卡片关闭）/ 组件销毁：停轮询且在途请求不再写入
 * - 信封 404（种子/下载器已不存在）自动停轮询，兜住删除当前种子后未清 currentRow 的缺口
 * - 后台标签页（document.hidden）暂停轮询，恢复可见时先补一次刷新再续轮询
 */

jest.mock('@/api/torrents', () => ({
  getTorrentFiles: jest.fn(),
  getTorrentPeers: jest.fn()
}))

import TrackerDetailDataMixin from '@/views/torrents/mixins/detailTabsData'
import { getTorrentFiles, getTorrentPeers } from '@/api/torrents'

const mockedGetFiles = getTorrentFiles as jest.Mock
const mockedGetPeers = getTorrentPeers as jest.Mock

@Component({
  name: 'DetailTabsHarness',
  template: '<div class="detail-tabs-harness" />'
})
class DetailTabsHarness extends TrackerDetailDataMixin {
  // 初始化器保证字段成为实例自有属性（Vue data 观测 → watcher 可触发），
  // 同真实父组件 index.vue / TraditionalView.vue 的声明方式
  protected currentRow: any = null
  protected activeDetailTab: any = 'tracker'

  public setRow(row: any) {
    this.currentRow = row
  }

  public setTab(tab: 'tracker' | 'files' | 'peers') {
    this.activeDetailTab = tab
  }
}

const localVue = createLocalVue()

const flush = async() => {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

const nextTick = async(wrapper: Wrapper<DetailTabsHarness>) => {
  await wrapper.vm.$nextTick()
}

const okEnvelope = (list: any[]) => ({
  status: 'success',
  code: '200',
  msg: '获取成功',
  data: { total: list.length, page: 1, pageSize: 100000, list }
})

const notFoundEnvelope = () => ({
  status: 'error',
  code: '404',
  msg: '种子不存在或已被删除 [h1]',
  data: null
})

const setHidden = (hidden: boolean) => {
  Object.defineProperty(document, 'hidden', { value: hidden, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('TrackerDetailDataMixin 文件页签（懒加载 + 键控缓存）', () => {
  let wrapper: Wrapper<DetailTabsHarness>

  beforeEach(() => {
    jest.useFakeTimers()
    mockedGetFiles.mockReset()
    mockedGetPeers.mockReset()
  })

  afterEach(() => {
    if (wrapper && wrapper.exists()) {
      wrapper.destroy()
    }
    jest.useRealTimers()
  })

  it('切入 files 页签懒加载一次；同键再切不重复拉取；手动刷新强制重取', async() => {
    mockedGetFiles.mockResolvedValue(okEnvelope([{ name: 'a.iso', size: 1, progress: 1 }]))
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm

    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.setTab('files')
    await nextTick(wrapper)
    await flush()
    expect(mockedGetFiles).toHaveBeenCalledTimes(1)
    expect(mockedGetFiles).toHaveBeenCalledWith('h1', 'dl1')
    expect(vm.detailFilesState.list).toHaveLength(1)
    expect(vm.detailFilesState.loading).toBe(false)

    // 切走再切回：同键缓存命中，不重复拉取
    vm.setTab('tracker')
    await nextTick(wrapper)
    vm.setTab('files')
    await nextTick(wrapper)
    await flush()
    expect(mockedGetFiles).toHaveBeenCalledTimes(1)

    // 手动刷新：强制重取
    vm.handleDetailRefresh('files')
    await flush()
    expect(mockedGetFiles).toHaveBeenCalledTimes(2)
  })

  it('换种子使缓存失效：非空→非空切换后重新拉取新键', async() => {
    mockedGetFiles.mockResolvedValue(okEnvelope([{ name: 'a.bin', size: 1, progress: 0 }]))
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm

    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.setTab('files')
    await nextTick(wrapper)
    await flush()
    expect(mockedGetFiles).toHaveBeenCalledTimes(1)

    vm.setRow({ hash: 'h2', downloader_id: 'dl1' })
    await nextTick(wrapper)
    await flush()
    // 防御路径：换行未重置页签时，watcher 应以新键重取
    expect(mockedGetFiles).toHaveBeenCalledTimes(2)
    expect(mockedGetFiles).toHaveBeenLastCalledWith('h2', 'dl1')
    expect(vm.detailFilesState.list).toHaveLength(1)
  })

  it('错误响应置错误态保留旧数据；下一轮重新拉取', async() => {
    mockedGetFiles
      .mockResolvedValueOnce(okEnvelope([{ name: 'old.bin', size: 1, progress: 0 }]))
      .mockResolvedValueOnce({ status: 'error', code: '500', msg: '下载器超时', data: null })
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm

    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.setTab('files')
    await nextTick(wrapper)
    await flush()
    expect(vm.detailFilesState.error).toBe('')

    vm.handleDetailRefresh('files')
    await flush()
    expect(vm.detailFilesState.loading).toBe(false)
    expect(vm.detailFilesState.error).toBe('下载器超时')
    // 失败不清空上次数据
    expect(vm.detailFilesState.list).toHaveLength(1)
    // 错误态未缓存成功键：再次切入重取
    mockedGetFiles.mockResolvedValueOnce(okEnvelope([{ name: 'new.bin', size: 1, progress: 1 }]))
    vm.setTab('tracker')
    await nextTick(wrapper)
    vm.setTab('files')
    await nextTick(wrapper)
    await flush()
    expect(vm.detailFilesState.error).toBe('')
    expect(vm.detailFilesState.list[0].name).toBe('new.bin')
  })
})

describe('TrackerDetailDataMixin Peers 页签（5s 链式轮询 + 生命周期）', () => {
  let wrapper: Wrapper<DetailTabsHarness>

  beforeEach(() => {
    jest.useFakeTimers()
    setHidden(false)
    mockedGetFiles.mockReset()
    mockedGetPeers.mockReset()
  })

  afterEach(() => {
    if (wrapper && wrapper.exists()) {
      wrapper.destroy()
    }
    jest.useRealTimers()
  })

  const mountWithPeers = async(peerList: any[] = [{ ip: '1.1.1.1', port: 80, client: 'x', progress: 0.5, down_speed: 1, up_speed: 1, flags: '', country: '' }]) => {
    mockedGetPeers.mockResolvedValue(okEnvelope(peerList))
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm
    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.setTab('peers')
    await nextTick(wrapper)
    await flush()
    return vm
  }

  it('切入 peers 立即拉取一次，之后按 5s 周期续轮询', async() => {
    const vm = await mountWithPeers()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
    expect(vm.detailPeersState.list).toHaveLength(1)

    jest.advanceTimersByTime(5000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(2)

    jest.advanceTimersByTime(5000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(3)
  })

  it('离开 peers 页签停轮询：不再续发，重复停止幂等', async() => {
    await mountWithPeers()
    const vm: any = wrapper.vm
    vm.setTab('tracker')
    await nextTick(wrapper)
    await flush()

    jest.advanceTimersByTime(15000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
  })

  it('currentRow 置空（卡片关闭）：停轮询并清空数据', async() => {
    await mountWithPeers()
    const vm: any = wrapper.vm
    expect(vm.detailPeersState.list).toHaveLength(1)

    vm.setRow(null)
    await nextTick(wrapper)
    await flush()
    expect(vm.detailPeersState.list).toHaveLength(0)
    expect(vm.detailFilesState.list).toHaveLength(0)

    jest.advanceTimersByTime(15000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
  })

  it('信封 404（种子已删）自动停轮询，不产生后续请求', async() => {
    mockedGetPeers.mockResolvedValue(notFoundEnvelope())
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm
    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.setTab('peers')
    await nextTick(wrapper)
    await flush()

    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
    expect(vm.detailPeersState.error).toContain('种子不存在')

    jest.advanceTimersByTime(15000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
  })

  it('序号守卫：停止轮询后的在途响应不写入状态', async() => {
    let resolvePeers: (value: any) => void = () => undefined
    mockedGetPeers.mockImplementation(
      () => new Promise(resolve => {
        resolvePeers = resolve
      })
    )
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm
    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.setTab('peers')
    await nextTick(wrapper)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
    expect(vm.detailPeersState.loading).toBe(true)

    // 卡片关闭（请求在途）→ 迟到的响应必须被丢弃
    vm.setRow(null)
    await nextTick(wrapper)
    resolvePeers(okEnvelope([{ ip: 'late', port: 1, client: '', progress: 0, down_speed: 0, up_speed: 0, flags: '', country: '' }]))
    await flush()

    expect(vm.detailPeersState.list).toHaveLength(0)
  })

  it('后台标签页暂停轮询，恢复可见先补一次刷新再续轮询', async() => {
    await mountWithPeers()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)

    setHidden(true)
    jest.advanceTimersByTime(20000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)

    setHidden(false)
    await flush()
    // 恢复时立即补一次刷新
    expect(mockedGetPeers).toHaveBeenCalledTimes(2)

    jest.advanceTimersByTime(5000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(3)
  })

  it('组件销毁后无定时器残留、无监听器泄漏（visibility 事件不恢复轮询）', async() => {
    await mountWithPeers()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)

    wrapper.destroy()
    setHidden(false)
    await flush()
    jest.advanceTimersByTime(20000)
    await flush()
    expect(mockedGetPeers).toHaveBeenCalledTimes(1)
  })
})

describe('TrackerDetailDataMixin 分支补充（refresh(tracker) 与空行保护）', () => {
  let wrapper: Wrapper<DetailTabsHarness>

  beforeEach(() => {
    jest.useFakeTimers()
    mockedGetFiles.mockReset()
    mockedGetPeers.mockReset()
  })

  afterEach(() => {
    if (wrapper && wrapper.exists()) {
      wrapper.destroy()
    }
    jest.useRealTimers()
  })

  it('tracker 页签的 refresh 事件不触发任何明细请求', async() => {
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm
    vm.setRow({ hash: 'h1', downloader_id: 'dl1' })
    vm.handleDetailRefresh('tracker')
    await flush()
    expect(mockedGetFiles).not.toHaveBeenCalled()
    expect(mockedGetPeers).not.toHaveBeenCalled()
  })

  it('无选中行（currentRow 为空）时切入 files 页签不发请求', async() => {
    wrapper = mount(DetailTabsHarness, { localVue })
    const vm: any = wrapper.vm
    vm.setTab('files')
    await wrapper.vm.$nextTick()
    await flush()
    expect(mockedGetFiles).not.toHaveBeenCalled()
    expect(mockedGetPeers).not.toHaveBeenCalled()
  })
})
