/**
 * 移动下载器监控页契约（Phase 4 M1，2026-08-24 提入底部 Tab 第一梯队）：
 * 复用桌面 /downloader/getList + testConnection；只读监控（在线徽标 + 测试连接），
 * 管理操作由抽屉「下载器管理」桌面页承载（页面脚注指路）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileDownloader from '@/views/mobile/downloader.vue'
import { getList, testConnection } from '@/api/downloader'

jest.mock('@/api/downloader', () => ({
  getList: jest.fn(),
  testConnection: jest.fn()
}))

const mockedList = [
  {
    id: 'd1',
    nickname: '主力QB',
    host: '192.168.5.51',
    port: '8080',
    downloaderType: 0,
    downloaderTypeName: 'qbittorrent',
    connectStatus: '1'
  },
  {
    id: 'd2',
    nickname: 'TR辅种',
    host: '192.168.5.52',
    port: '9091',
    downloaderType: 1,
    downloaderTypeName: 'transmission',
    connectStatus: '0'
  }
]

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileDownloader, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
    }
  })

/** shallowMount 下 el-button 是 kebab 形态 stub 且不转发 click——直接调组件方法（行为链等价） */
function clickFirstTestButton(wrapper: Wrapper<Vue>): void {
  const vm = wrapper.vm as any
  vm.testOne(vm.list[0])
}

/** 排空 mounted 异步链（load 的 await + 渲染 tick），与 orphan-files.spec 同模式 */
async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileDownloader', () => {
  beforeEach(() => {
    jest.mocked(getList).mockReset()
    jest.mocked(testConnection).mockReset()
  })

  it('挂载即拉取列表并渲染卡片（名称/类型/主机端口/在线离线徽标）', async() => {
    (getList as jest.Mock).mockResolvedValue({ code: '200', data: mockedList })
    const wrapper = mountPage()
    await flushLifecycle()

    expect(getList).toHaveBeenCalledWith({ page: 1, pageSize: 100 })
    const cards = wrapper.findAll('.m-dl-card')
    expect(cards.length).toBe(2)
    expect(cards.at(0).find('.m-dl-name').text()).toBe('主力QB')
    expect(cards.at(0).find('.m-dl-host').text()).toBe('192.168.5.51:8080')
    const badges = wrapper.findAll('.m-dl-badge')
    expect(badges.at(0).classes()).toContain('is-online')
    expect(badges.at(0).text()).toBe('在线')
    expect(badges.at(1).classes()).toContain('is-offline')
    expect(badges.at(1).text()).toBe('离线')
  })

  it('列表为空显示空态提示', async() => {
    (getList as jest.Mock).mockResolvedValue({ code: '200', data: [] })
    const wrapper = mountPage()
    await flushLifecycle()
expect(wrapper.find('.m-hint').text()).toBe('暂无下载器')
  })

  it('接口异常不崩溃并提示错误', async() => {
    (getList as jest.Mock).mockRejectedValue(new Error('boom'))
    const wrapper = mountPage()
    await flushLifecycle()
expect((wrapper.vm.$message as any).error).toHaveBeenCalled()
  })

  it('测试连接成功：提示并刷新列表同步状态', async() => {
    (getList as jest.Mock).mockResolvedValue({ code: '200', data: mockedList })
    const wrapper = mountPage()
    await flushLifecycle()

    ;(testConnection as jest.Mock).mockResolvedValue({ code: '200', msg: 'ok' })
    clickFirstTestButton(wrapper)
    await flushLifecycle()

    expect(testConnection).toHaveBeenCalledWith('d1')
    expect((wrapper.vm.$message as any).success).toHaveBeenCalledWith('主力QB：连接成功')
    // 成功后重拉列表（getList 共被调 2 次：初始 + 测试后刷新）
    expect(getList).toHaveBeenCalledTimes(2)
  })

  it('测试连接失败：弹出失败消息不刷新列表', async() => {
    (getList as jest.Mock).mockResolvedValue({ code: '200', data: mockedList })
    const wrapper = mountPage()
    await flushLifecycle()
const initialCalls = (getList as jest.Mock).mock.calls.length

    ;(testConnection as jest.Mock).mockResolvedValue({ code: '500', msg: '超时' })
    clickFirstTestButton(wrapper)
    await flushLifecycle()

    expect((wrapper.vm.$message as any).error).toHaveBeenCalledWith('主力QB：超时')
    expect((getList as jest.Mock).mock.calls.length).toBe(initialCalls)
  })

  it('在线徽标与脚注使用主题色变量（与桌面端同源）', () => {
    const source = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/views/mobile/downloader.vue'),
      'utf-8'
    )
    expect(source).toContain('.m-dl-badge.is-online')
    expect(source).toContain('var(--color-primary)')
  })
})
