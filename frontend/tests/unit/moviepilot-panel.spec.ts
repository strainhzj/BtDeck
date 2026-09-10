/**
 * MoviePilot 集成设置面板回归（moviepilot-integration）。
 *
 * 保护点：
 * 1. 全局开关 dirty 跟踪 + CAS 保存（expectedRevision）+ 服务端态收敛；
 * 2. 409 冲突提示并自动重载最新配置；
 * 3. 实例卡片渲染（名称/同步统计/错误）与启用开关即时 PUT；
 * 4. 下载器映射编辑保存载荷（过滤空行 + 去重校验）；
 * 5. 路径反查：结果渲染任务快照标签与未关联标签；
 * 6. demo 模式不发起任何 API。
 */

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'

import MoviePilotPanel from '@/views/settings/components/MoviePilotPanel.vue'
import {
  getMoviePilotSettings,
  updateMoviePilotSettings,
  getMoviePilotInstances,
  updateMoviePilotInstance,
  reverseMoviePilotAssociations,
  MoviePilotInstance
} from '@/api/moviepilot'
import { getDownloaderList } from '@/api/torrents'
import { isDemoMode } from '@/demo/config'
import { ApiError } from '@/types/api'

jest.mock('@/api/moviepilot', () => ({
  getMoviePilotSettings: jest.fn(),
  updateMoviePilotSettings: jest.fn(),
  getMoviePilotInstances: jest.fn(),
  updateMoviePilotInstance: jest.fn(),
  deleteMoviePilotInstance: jest.fn(),
  reverseMoviePilotAssociations: jest.fn()
}))

jest.mock('@/api/torrents', () => ({
  getDownloaderList: jest.fn()
}))

jest.mock('@/demo/config', () => ({
  isDemoMode: jest.fn(() => false)
}))

const mockGetSettings = getMoviePilotSettings as jest.MockedFunction<typeof getMoviePilotSettings>
const mockUpdateSettings = updateMoviePilotSettings as jest.MockedFunction<typeof updateMoviePilotSettings>
const mockGetInstances = getMoviePilotInstances as jest.MockedFunction<typeof getMoviePilotInstances>
const mockUpdateInstance = updateMoviePilotInstance as jest.MockedFunction<typeof updateMoviePilotInstance>
const mockReverse = reverseMoviePilotAssociations as jest.MockedFunction<typeof reverseMoviePilotAssociations>
const mockGetDownloaders = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
const mockIsDemoMode = isDemoMode as jest.MockedFunction<typeof isDemoMode>

const localVue = createLocalVue()
localVue.use(ElementUI)

/** class 组件的 private 成员运行时即实例成员，经接口重声明访问 */
interface PanelVm {
  save: () => Promise<void>
  dirty: boolean
  revision: number
  instances: MoviePilotInstance[]
  downloaders: { downloader_id: string, nickname: string }[]
  startEditMapping: (instance: MoviePilotInstance) => void
  saveMapping: (instance: MoviePilotInstance) => Promise<void>
  mappingDraft: { mpName: string, btDownloaderId: string }[]
  toggleInstance: (instance: MoviePilotInstance, enabled: boolean | string | number) => Promise<void>
  reversePath: string
  reverseMode: string
  runReverse: () => Promise<void>
  reverseItems: MoviePilotInstance[]
}

const INSTANCE: MoviePilotInstance = {
  id: 1,
  instanceId: 'mp-inst-0001',
  name: '家庭实例',
  enabled: true,
  protocolVersion: 1,
  pluginVersion: '1.0.0',
  moviepilotVersion: '2.9.9',
  downloaderMapping: { 'qb-main': 'dl-a' },
  boundUsername: 'moviepilot',
  lastHandshakeAt: '2026-09-08T10:00:00',
  lastSyncAt: '2026-09-08T11:00:00',
  lastSyncStats: { inserted: 3, updated: 1, skipped: 10, failed: 0 },
  syncedHistoryCount: 14,
  lastError: null,
  createdAt: '2026-09-08T09:00:00',
  updatedAt: '2026-09-08T11:00:00'
}

function settingsResponse(opts: { enabled?: boolean, revision?: number } = {}) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      settings: {
        schemaVersion: 1,
        enabled: opts.enabled ?? false,
        revision: opts.revision ?? 0,
        updatedAt: null,
        updatedBy: null
      },
      protocolVersion: 1
    }
  } as unknown as Awaited<ReturnType<typeof getMoviePilotSettings>>
}

function instancesResponse(list: MoviePilotInstance[] = [INSTANCE]) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: { total: list.length, page: 1, pageSize: 100, list }
  } as unknown as Awaited<ReturnType<typeof getMoviePilotInstances>>
}

/** 单实例信封（PUT /instances/{id} 的返回形状：data 直接是实例对象） */
function instanceResponse(instance: MoviePilotInstance) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: instance
  } as unknown as Awaited<ReturnType<typeof updateMoviePilotInstance>>
}

function downloadersResponse() {
  return {
    code: '200',
    data: [
      { downloader_id: 'dl-a', nickname: '下载器A' },
      { downloader_id: 'dl-b', nickname: '下载器B' }
    ]
  } as unknown as Awaited<ReturnType<typeof getDownloaderList>>
}

function reverseResponse() {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      total: 2,
      page: 1,
      pageSize: 50,
      list: [
        {
          id: 1,
          instanceId: 'mp-inst-0001',
          instanceName: '家庭实例',
          historyId: 100,
          srcStorage: 'local',
          srcPath: '/data/downloads/Movie/movie.mkv',
          destStorage: 'local',
          destPath: '/data/media/Movie.mkv',
          transferMode: 'link',
          mediaType: '电影',
          title: 'Movie',
          year: '2026',
          seasons: null,
          episodes: null,
          tmdbId: 123,
          doubanId: null,
          mpDownloader: 'qb-main',
          downloadHash: 'a'.repeat(40),
          btDownloaderId: 'dl-a',
          associationStatus: 'linked',
          status: true,
          errmsg: null,
          recordedAt: '2026-09-08 10:00:00',
          task: { infoId: 't-1', name: 'Movie 任务', status: 'seeding', downloaderId: 'dl-a', downloaderName: '下载器A', savePath: '/data/downloads', size: 100 }
        },
        {
          id: 2,
          instanceId: 'mp-inst-0001',
          instanceName: '家庭实例',
          historyId: 101,
          srcStorage: 'local',
          srcPath: '/data/downloads/Other/other.mkv',
          destStorage: 'local',
          destPath: '/data/media/Other.mkv',
          transferMode: 'copy',
          mediaType: '电影',
          title: 'Other',
          year: null,
          seasons: null,
          episodes: null,
          tmdbId: null,
          doubanId: null,
          mpDownloader: null,
          downloadHash: null,
          btDownloaderId: null,
          associationStatus: 'unassociated',
          status: true,
          errmsg: null,
          recordedAt: '2026-09-08 10:05:00',
          task: null
        }
      ]
    }
  } as unknown as Awaited<ReturnType<typeof reverseMoviePilotAssociations>>
}

function makeApiError(code: string): ApiError {
  return new ApiError('错误', { code, httpStatus: Number(code) })
}

async function flushPromises(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
}

function findButton(wrapper: Wrapper<Vue>, text: string): Wrapper<Vue> {
  const btn = wrapper.findAllComponents({ name: 'ElButton' }).wrappers.find(b => b.text().includes(text))
  if (!btn) throw new Error(`未找到按钮: ${text}`)
  return btn
}

async function mountPanel(): Promise<Wrapper<Vue>> {
  mockGetSettings.mockResolvedValue(settingsResponse())
  mockGetInstances.mockResolvedValue(instancesResponse())
  mockGetDownloaders.mockResolvedValue(downloadersResponse())
  const wrapper = mount(MoviePilotPanel, { localVue })
  await flushPromises()
  await wrapper.vm.$nextTick()
  return wrapper
}

beforeEach(() => {
  jest.clearAllMocks()
  jest.restoreAllMocks()
  mockIsDemoMode.mockReturnValue(false)
})

describe('MoviePilotPanel', () => {
  it('渲染全局开关与实例卡片（映射/统计/绑定账号）', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    expect(mockGetSettings).toHaveBeenCalledTimes(1)
    expect(mockGetInstances).toHaveBeenCalledTimes(1)
    expect(mockGetDownloaders).toHaveBeenCalledTimes(1)
    expect(vm.instances.length).toBe(1)
    expect(wrapper.text()).toContain('家庭实例')
    expect(wrapper.text()).toContain('已同步 14 条')
    expect(wrapper.text()).toContain('绑定账号 moviepilot')
    // 映射展示：MP 名 → BtDeck 下载器昵称
    expect(wrapper.text()).toContain('qb-main')
    expect(wrapper.text()).toContain('下载器A')
  })

  it('未改动时保存禁用；改动后携带 expectedRevision 保存并收敛', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    expect(vm.dirty).toBe(false)
    const saveButton = findButton(wrapper, '保存配置')
    expect(saveButton.attributes('disabled')).toBeDefined()

    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    mockUpdateSettings.mockResolvedValue(settingsResponse({ enabled: true, revision: 1 }) as unknown as Awaited<ReturnType<typeof updateMoviePilotSettings>>)
    await switches.at(0).vm.$emit('input', true)
    expect(vm.dirty).toBe(true)

    await vm.save()
    expect(mockUpdateSettings).toHaveBeenCalledTimes(1)
    const payload = mockUpdateSettings.mock.calls[0][0]
    expect(payload.enabled).toBe(true)
    expect(payload.expectedRevision).toBe(0)
    expect(vm.revision).toBe(1)
    expect(vm.dirty).toBe(false)
  })

  it('409 冲突提示并自动重载最新配置', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    const warningSpy = jest.spyOn(wrapper.vm.$message, 'warning').mockImplementation((() => ({})) as unknown as () => never)
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    await switches.at(0).vm.$emit('input', true)

    mockUpdateSettings.mockRejectedValue(makeApiError('409'))
    mockGetSettings.mockClear()
    mockGetSettings.mockResolvedValue(settingsResponse({ enabled: false, revision: 3 }))
    await vm.save()
    await flushPromises()

    expect(mockGetSettings).toHaveBeenCalledTimes(1)
    expect(vm.revision).toBe(3)
    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('已被其他会话修改'))
  })

  it('实例启用开关即时 PUT 并本地生效', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    const target = vm.instances[0]
    mockUpdateInstance.mockResolvedValue(instanceResponse({ ...target, enabled: false }))
    await vm.toggleInstance(target, false)
    expect(mockUpdateInstance).toHaveBeenCalledWith('mp-inst-0001', { enabled: false })
    expect(vm.instances[0].enabled).toBe(false)
  })

  it('映射编辑：空行校验拒绝，有效行组装载荷保存', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    const target = vm.instances[0]
    const warningSpy = jest.spyOn(wrapper.vm.$message, 'warning').mockImplementation((() => ({})) as unknown as () => never)
    vm.startEditMapping(target)
    expect(vm.mappingDraft).toEqual([{ mpName: 'qb-main', btDownloaderId: 'dl-a' }])

    // 添加一行只有 MP 名没有 BtDeck 下载器 → 校验拒绝
    vm.mappingDraft.push({ mpName: 'tr-second', btDownloaderId: '' })
    await vm.saveMapping(target)
    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('不能为空'))
    expect(mockUpdateInstance).not.toHaveBeenCalled()

    vm.mappingDraft[1].btDownloaderId = 'dl-b'
    mockUpdateInstance.mockResolvedValue(
      instanceResponse({ ...target, downloaderMapping: { 'qb-main': 'dl-a', 'tr-second': 'dl-b' } })
    )
    await vm.saveMapping(target)
    expect(mockUpdateInstance).toHaveBeenCalledWith('mp-inst-0001', {
      downloaderMapping: { 'qb-main': 'dl-a', 'tr-second': 'dl-b' }
    })
    expect(vm.instances[0].downloaderMapping['tr-second']).toBe('dl-b')
  })

  it('反查渲染任务快照与未关联标签', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    mockReverse.mockResolvedValue(reverseResponse())
    vm.reversePath = '/data/media/Movie.mkv'
    vm.reverseMode = 'dest'
    await vm.runReverse()
    await wrapper.vm.$nextTick()

    expect(mockReverse).toHaveBeenCalledWith('/data/media/Movie.mkv', 'dest')
    expect(wrapper.text()).toContain('Movie 任务')
    expect(wrapper.text()).toContain('未关联')
    expect(wrapper.text()).toContain('软链接')
    expect(wrapper.text()).toContain('复制')
  })

  it('反查 API 失败显示错误提示', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    mockReverse.mockRejectedValue(new Error('boom'))
    vm.reversePath = '/data/media/Movie.mkv'
    await vm.runReverse()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('反查失败，请稍后重试')
  })

  it('demo 模式不发起任何 API', async() => {
    mockIsDemoMode.mockReturnValue(true)
    const wrapper = mount(MoviePilotPanel, { localVue })
    await flushPromises()
    expect(mockGetSettings).not.toHaveBeenCalled()
    expect(mockGetInstances).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('演示模式不支持修改 MoviePilot 集成配置')
  })
})
