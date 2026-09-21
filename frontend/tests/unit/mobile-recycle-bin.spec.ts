/**
 * 移动回收站契约（Phase 4 M2；2026-08-27 info_id 契约修复回归加固）：
 * - 卡片列表 + 单条恢复/彻底删除，批量与手动恢复保留桌面版；
 * - 恢复/彻底删除的守卫与载荷均按 info_id（torrent_ids），失败提示用 reason 字段；
 * - 按钮禁用态：恢复按钮保留「缺 torrent_id 禁用」现有语义，彻底删除仅 busyKey 锁定；
 * - 源码契约锁死上述不变式。交互直调组件方法（el-button stub 不转发 click）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'
import MobileRecycleBin from '@/views/mobile/recycle-bin.vue'
import { getRecycleBinList, restoreTorrents, manualCleanup } from '@/api/recycle-bin'

jest.mock('@/api/recycle-bin', () => ({
  getRecycleBinList: jest.fn(),
  restoreTorrents: jest.fn(),
  manualCleanup: jest.fn()
}))

// item1 字段齐全；item2 有 torrent_id 无 info_id（专测守卫按 info_id 拦截）；
// item3 有 info_id 无 torrent_id（专测按钮禁用态：仅恢复禁用）
const mockedItems = [
  {
    info_id: 'i1',
    name: '已删种子A',
    size: 1073741824,
    save_path: '/downloads/a',
    deleted_at: '2026-08-20T10:00:00',
    downloader_name: 'qb',
    torrent_id: 't1'
  },
  {
    name: '无记录种子B',
    size: 52428800,
    save_path: '/downloads/b',
    deleted_at: '2026-08-21T11:00:00',
    downloader_name: 'tr',
    torrent_id: 't2'
  },
  {
    info_id: 'i3',
    name: '无下载器ID种子C',
    size: 20971520,
    save_path: '/downloads/c',
    deleted_at: '2026-08-22T12:00:00',
    downloader_name: 'qb',
    torrent_id: undefined
  }
]

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileRecycleBin, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm')
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

const readSource = (): string =>
  fs.readFileSync(path.resolve(__dirname, '../../src/views/mobile/recycle-bin.vue'), 'utf-8')

describe('views/mobile/MobileRecycleBin', () => {
  beforeEach(() => {
    jest.mocked(getRecycleBinList).mockReset()
    jest.mocked(getRecycleBinList).mockResolvedValue({
      code: '200',
      data: { total: 3, page: 1, pageSize: 20, list: mockedItems }
    } as never)
    jest.mocked(restoreTorrents).mockReset()
    jest.mocked(manualCleanup).mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('列表渲染：名称/大小/路径/删除时间/下载器', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('已删种子A')
    expect(wrapper.text()).toContain('1.0 GB')
    expect(wrapper.text()).toContain('/downloads/a')
    expect(wrapper.text()).toContain('2026-08-20 10:00')
    expect(wrapper.text()).toContain('qb')
    wrapper.destroy()
  })

  it('空列表显示空态', async() => {
    jest.mocked(getRecycleBinList).mockResolvedValue({
      code: '200',
      data: { total: 0, page: 1, pageSize: 20, list: [] }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('回收站为空')
    wrapper.destroy()
  })

  it('搜索词作为 search 参数提交', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.search = '关键词'
    await vm.reload()
    expect(getRecycleBinList).toHaveBeenLastCalledWith(expect.objectContaining({ search: '关键词' }))
    wrapper.destroy()
  })

  it('恢复：携带 torrent_ids（info_id）单条恢复并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(restoreTorrents).mockResolvedValue({
      code: '200',
      data: { success_count: 1, failed_count: 0, skipped_count: 0, success_list: [], failed_list: [] }
    } as never)
    await vm.restore(vm.list[0])
    expect(restoreTorrents).toHaveBeenCalledWith({ torrent_ids: ['i1'] })
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
    wrapper.destroy()
  })

  it('恢复部分失败：给出警告提示', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(restoreTorrents).mockResolvedValue({
      code: '200',
      data: { success_count: 0, failed_count: 1, skipped_count: 0, success_list: [], failed_list: [] }
    } as never)
    await vm.restore(vm.list[0])
    expect(wrapper.vm.$message.warning).toHaveBeenCalled()
    wrapper.destroy()
  })

  it('有 torrent_id 但无 info_id 的记录：恢复/删除方法直接返回（守卫按 info_id 拦截）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.restore(vm.list[1])
    vm.destroy(vm.list[1])
    await flushLifecycle()
    expect(restoreTorrents).not.toHaveBeenCalled()
    expect(manualCleanup).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('彻底删除：确认后调 manualCleanup 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(manualCleanup).mockResolvedValue({
      code: '200',
      data: { success_count: 1, failed_count: 0, success_list: [], failed_list: [] }
    } as never)
    await vm.destroy(vm.list[0])
    await flushLifecycle()
    expect(manualCleanup).toHaveBeenCalledWith({ torrent_ids: ['i1'] })
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
    wrapper.destroy()
  })

  it('彻底删除失败：提示中展示后端返回的 reason', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(manualCleanup).mockResolvedValue({
      code: '200',
      data: {
        success_count: 0,
        failed_count: 1,
        success_list: [],
        failed_list: [{ torrent_id: 'i1', reason: '种子不存在' }]
      }
    } as never)
    await vm.destroy(vm.list[0])
    await flushLifecycle()
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('删除失败：种子不存在')
    wrapper.destroy()
  })

  it('恢复失败：提示中展示后端返回的 reason', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(restoreTorrents).mockResolvedValue({
      code: '200',
      data: {
        success_count: 0,
        failed_count: 1,
        skipped_count: 0,
        success_list: [],
        failed_list: [{ torrent_id: 'i1', reason: '种子文件备份不存在，请手动提供种子文件' }]
      }
    } as never)
    await vm.restore(vm.list[0])
    expect(wrapper.vm.$message.warning).toHaveBeenCalledWith(
      expect.stringContaining('种子文件备份不存在，请手动提供种子文件')
    )
    wrapper.destroy()
  })

  it('按钮禁用态契约：缺 torrent_id 仅禁用恢复并显示「无法恢复」，彻底删除可用；busyKey 期间两按钮均禁用', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const cards = wrapper.findAll('.m-rb-card')
    expect(cards).toHaveLength(3)
    // 本环境未全局注册 ElementUI，el-button 以未知原生元素渲染（attrs 绑定仍生效）
    const cardButtons = (index: number) => cards.at(index).findAll('.m-rb-actions el-button')
    const isDisabled = (btn: Wrapper<Vue>): boolean => (btn.element as Element).hasAttribute('disabled')
    // item3（有 info_id、无 torrent_id）：恢复按钮禁用且文案「无法恢复」（锁 L34/L37 现有语义）
    const item3Buttons = cardButtons(2)
    expect(item3Buttons.at(0).text()).toBe('无法恢复')
    expect(isDisabled(item3Buttons.at(0))).toBe(true)
    // 彻底删除按钮可用（锁 L43 修复：仅缺 torrent_id 不得禁用彻底删除）
    expect(item3Buttons.at(1).text()).toBe('彻底删除')
    expect(isDisabled(item3Buttons.at(1))).toBe(false)
    // item1（字段齐全）：两按钮均可用
    expect(isDisabled(cardButtons(0).at(0))).toBe(false)
    expect(isDisabled(cardButtons(0).at(1))).toBe(false)

    // busyKey 期间 item1 两按钮均禁用，请求结束后复位
    let release!: (value: unknown) => void
    jest.mocked(restoreTorrents).mockImplementation(
      () => new Promise(resolve => { release = resolve }) as never
    )
    const vm = wrapper.vm as any
    const restoring = vm.restore(vm.list[0])
    await wrapper.vm.$nextTick()
    expect(isDisabled(cardButtons(0).at(0))).toBe(true)
    expect(isDisabled(cardButtons(0).at(1))).toBe(true)
    release({
      code: '200',
      data: { success_count: 1, failed_count: 0, skipped_count: 0, success_list: [], failed_list: [] }
    } as never)
    await restoring
    await flushLifecycle()
    const item1ButtonsAfter = wrapper.findAll('.m-rb-card').at(0).findAll('.m-rb-actions el-button')
    expect(isDisabled(item1ButtonsAfter.at(0))).toBe(false)
    expect(isDisabled(item1ButtonsAfter.at(1))).toBe(false)
    wrapper.destroy()
  })

  it('彻底删除失败且 reason 缺失：兜底提示「未知原因」', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(manualCleanup).mockResolvedValue({
      code: '200',
      data: { success_count: 0, failed_count: 1, success_list: [], failed_list: [{}] }
    } as never)
    await vm.destroy(vm.list[0])
    await flushLifecycle()
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('删除失败：未知原因')
    wrapper.destroy()
  })

  it('彻底删除网络异常：走 error 提示、无成功提示、busyKey 复位', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(manualCleanup).mockRejectedValue(new Error('网络错误') as never)
    await vm.destroy(vm.list[0])
    await flushLifecycle()
    // extractErrorMessage 对 Error 取 message 字段
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('网络错误')
    expect(wrapper.vm.$message.success).not.toHaveBeenCalled()
    expect(vm.busyKey).toBe('')
    wrapper.destroy()
  })

  it('源码契约：载荷用 info_id、守卫按 info_id、reason 字段与按钮禁用表达式锁定', () => {
    const source = readSource()
    // 载荷：恢复/彻底删除均以 info_id 组装 torrent_ids（不得回退 torrent_id）
    expect(source.match(/torrent_ids: \[item\.info_id\]/g)).toHaveLength(2)
    expect(source).not.toContain('torrent_ids: [item.torrent_id]')
    // 守卫：两处方法级防护均按 info_id 拦截
    expect(source.match(/if \(!item\.info_id\) return/g)).toHaveLength(2)
    expect(source).not.toContain('if (!item.torrent_id) return')
    // 失败原因字段：reason（两处提示均依赖，不得回退 error）
    expect(source.match(/failed_list\?\.\[0\]\?\.reason/g)).toHaveLength(2)
    expect(source).not.toContain('failed_list?.[0]?.error')
    // 按钮禁用：第一个 :disabled 属恢复按钮（保留缺 torrent_id 禁用现有语义），
    // 第二个属彻底删除按钮（仅 busyKey 锁定，不得因缺 torrent_id 禁用）
    const disabledLines = source.split(/\r?\n/).filter(line => line.includes(':disabled='))
    expect(disabledLines).toHaveLength(2)
    expect(disabledLines[0]).toContain('busyKey === item.info_id || !item.torrent_id')
    expect(disabledLines[1].trim()).toBe(':disabled="busyKey === item.info_id"')
    expect(disabledLines[1]).not.toContain('torrent_id')
  })
})
