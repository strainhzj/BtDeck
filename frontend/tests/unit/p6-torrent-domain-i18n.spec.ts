/**
 * P6-1 种子域收尾双语回归（传统视图 + 转移/改路径/全局替换 + 文件管理）。
 *
 * 覆盖两类保护：
 * A. 行为契约：新增/复用文案键在 zh 下逐字节保持原内联文案（零回归），
 *    en 下输出英文（含插值），语言切换不改业务参数；
 * B. 源码契约：6 个文件全部走 $t/translate（无硬编码中文字面量的关键位置），
 *    传统视图状态筛选与列设置按当前语言渲染（不再消费静态中文常量）。
 *
 * 审计门禁（i18n-leftover-guard.spec）已把本批 6 文件纳入扫描集，
 * 此处补「键存在性」与「插值正确性」的正面契约。
 */
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import VueI18n from 'vue-i18n'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import ElementUI from 'element-ui'
import i18n, { setLocale, translate } from '@/i18n'
import TransferDialog from '@/views/torrents/components/TransferDialog.vue'

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn().mockResolvedValue({ code: '200', data: { list: [], total: 0, pageSize: 20 } }),
  getActiveTorrents: jest.fn().mockResolvedValue({ code: '200', data: [] }),
  getDownloaderList: jest.fn().mockResolvedValue({ code: '200', data: [] }),
  getDownloaderPaths: jest.fn().mockResolvedValue({ code: '200', data: [] }),
  getTrackerDomains: jest.fn().mockResolvedValue({ code: '200', data: [] }),
  transferSeed: jest.fn(),
  transferSeedsBatch: jest.fn(),
  setTorrentLocation: jest.fn(),
  replaceTracker: jest.fn(),
  getDuplicateTorrents: jest.fn(),
  applySearchTemplate: jest.fn(),
  resumeTorrents: jest.fn(),
  pauseTorrents: jest.fn(),
  recheckTorrents: jest.fn(),
  reannounceTorrents: jest.fn(),
  deleteTorrents: jest.fn(),
  reconcileRuntimeTorrentStates: jest.fn()
}))

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.use(ElementUI)

const read = (file: string): string => readFileSync(resolve(__dirname, '../../', file), 'utf-8')

// ====================================================================
// A. 行为契约：zh 逐字节 / en 插值
// ====================================================================

describe('P6-1 传统视图文案分片（torrent.list.*）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：分片与计数文案与原内联逐字节一致', () => {
    setLocale('zh-CN')
    expect(translate('torrent.list.selectedPrefix')).toBe('已选')
    expect(translate('torrent.list.selectedSuffix')).toBe('个')
    expect(translate('torrent.list.pagination.prefix')).toBe('共')
    expect(translate('torrent.list.pagination.middle')).toBe('条，第')
    expect(translate('torrent.list.pagination.suffix')).toBe('页')
    expect(translate('torrent.list.filters.title')).toBe('过滤器')
    expect(translate('torrent.list.connected')).toBe('已连接')
    expect(translate('torrent.list.activeLabel')).toBe('活动:')
    expect(translate('torrent.list.column.nameShort')).toBe('名称')
    expect(translate('torrent.list.column.downloaderShort')).toBe('下载器')
    expect(translate('torrent.list.column.downloadShort')).toBe('↓ 下载')
    expect(translate('torrent.list.column.uploadShort')).toBe('↑ 上传')
    expect(translate('torrent.list.toolbar.addShort')).toBe('添加')
  })

  it('en：输出英文（分页后缀允许为空以保持语句通顺）', () => {
    setLocale('en')
    expect(translate('torrent.list.selectedPrefix')).toBe('Selected')
    expect(translate('torrent.list.pagination.prefix')).toBe('Total')
    expect(translate('torrent.list.filters.title')).toBe('Filters')
    expect(translate('torrent.list.column.downloadShort')).toBe('↓ Download')
    expect(translate('torrent.list.trackerErrorTitle', { status: 'Seeding' })).toBe('Seeding (tracker error)')
  })

  it('四级删除菜单与 P5 确认框同键（en 模式不再出现「中文菜单 → 英文确认」割裂）', () => {
    const source = read('src/views/torrents/TraditionalView.vue')
    // 菜单项走 list.deleteMenu.*（与 index.vue 同源）
    expect(source.includes("$t('torrent.list.deleteMenu.level4')")).toBe(true)
    expect(source.includes("$t('torrent.list.deleteMenu.level1')")).toBe(true)
    // 菜单不再硬编码「等级N: ...」
    expect(source.includes('等级4: 标记为待删除')).toBe(false)
    // 确认链路来自 mixin（P5 收敛），两视图共用 buildDeleteConfirmMessage
    expect(source.includes("$t('torrent.list.toolbar.delete')")).toBe(true)
  })

  it('状态筛选改为 localizedStatusOptions（不再消费静态中文常量）', () => {
    const source = read('src/views/torrents/TraditionalView.vue')
    expect(source.includes("import { localizedStatusOptions, getStatusIcon, getStatusText } from '@/constants/status-config'")).toBe(true)
    expect(source.includes('localizedStatusOptions().map')).toBe(true)
    expect(/\bSTATUS_OPTIONS\.map/.test(source)).toBe(false)
  })
})

describe('P6-1 列设置 labelKey 渲染', () => {
  afterEach(() => setLocale('zh-CN'))

  it('列设置数据用 labelKey，模板按当前语言渲染', () => {
    const source = read('src/views/torrents/TraditionalView.vue')
    expect(source.includes("{ key: 'name', labelKey: 'torrent.list.column.nameShort', visible: true }")).toBe(true)
    expect(source.includes('{{ $t(column.labelKey) }}')).toBe(true)
    expect(source.includes('{{ column.label }}')).toBe(false)
    // 12 列全部键化
    expect(source.match(/labelKey: 'torrent\.list\.column\./g)?.length).toBe(12)
  })
})

describe('P6-1 转移/改路径文案（transfer 模块）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：确认/源任务移除/结果文案语义一致', () => {
    setLocale('zh-CN')
    expect(translate('transfer.title')).toBe('转移种子')
    expect(translate('transfer.batchTitle', { count: 3 })).toBe('批量转移种子（已选择3个）')
    expect(translate('transfer.torrentCount', { count: 2 })).toBe('(2个种子)')
    expect(translate('transfer.deleteConfirmQuestion')).toBe('是否移除原下载器中的种子任务？数据文件将保留。')
    expect(translate('transfer.deleteConfirmIrreversible')).toBe('此操作只会移除原种子任务，数据文件仍会保留。')
    expect(translate('transfer.resultTitle')).toBe('批量转移完成')
    expect(translate('transfer.resultFailedList')).toBe('失败列表：')
    expect(translate('transfer.validate.sameAsCurrentDownloader')).toBe('目标下载器不能与当前下载器相同')
    expect(translate('transfer.setLocation.title', { count: 2 })).toBe('修改保存路径（已选择2个种子）')
    expect(translate('transfer.setLocation.confirmMove', { count: 2, path: '/data' }))
      .toBe('确认将 2 个种子移动到新路径？\n这将移动已下载的文件到: /data')
    expect(translate('transfer.setLocation.confirmChange', { count: 2 }))
      .toBe('确认修改 2 个种子的保存路径？\n仅修改路径，不移动文件。')
    expect(translate('transfer.setLocation.submitted', { moved: 5 }))
      .toBe('成功提交5个种子路径修改请求，正在后台处理...')
  })

  it('en：危险语义（任务移除/数据保留）与插值输出英文', () => {
    setLocale('en')
    expect(translate('transfer.deleteConfirmQuestion')).toContain('original downloader')
    expect(translate('transfer.deleteConfirmIrreversible').toLowerCase()).toContain('data files will remain')
    expect(translate('transfer.batchTitle', { count: 3 })).toContain('3')
    expect(translate('transfer.setLocation.confirmChange', { count: 2 })).toContain('files are not moved')
  })

  it('校验消息经弹窗挂载后按语言渲染（TransferDialog 表单规则）', () => {
    setLocale('en')
    const wrapper: Wrapper<Vue> = shallowMount(TransferDialog, {
      localVue,
      i18n,
      propsData: { visible: true, torrent: { infoId: 't1', downloaderId: 'd1', name: 'x' } },
      mocks: { $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }
    })
    expect(wrapper.vm.$t('transfer.validate.targetPathRequired').toString())
      .toBe('Enter the target path')
    wrapper.destroy()
    setLocale('zh-CN')
    expect(translate('transfer.validate.targetPathRequired')).toBe('请输入目标路径')
  })
})

describe('P6-1 全局替换 Tracker 危险文案（tracker.replace）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh 逐字节 + en 明示不可撤销', () => {
    setLocale('zh-CN')
    expect(translate('tracker.replace.title')).toBe('全局替换Tracker')
    expect(translate('tracker.replace.warning')).toBe('此功能将全局替换所有种子中匹配的tracker地址，操作不可撤销！')
    expect(translate('tracker.replace.oldPlaceholder'))
      .toBe('输入要被替换的tracker地址，例如: https://tracker.old.com/announce')
    expect(translate('tracker.replace.validate.invalidUrl')).toBe('请输入有效的tracker地址格式')

    setLocale('en')
    expect(translate('tracker.replace.warning').toLowerCase()).toContain('cannot be undone')
    expect(translate('tracker.replace.validate.invalidUrl')).toContain('valid tracker URL')
  })

  it('成功/失败提示复用 torrent.msg 既有键（不重复定义）', () => {
    const source = read('src/views/torrents/components/GlobalReplaceTrackerDialog.vue')
    expect(source.includes("$t('torrent.msg.globalReplaceSuccess')")).toBe(true)
    expect(source.includes("torrent.msg.globalReplaceFailed")).toBe(true)
    // 失败路径走 reasonCode 本地化入口
    expect(source.includes('apiResponseMessage(response,')).toBe(true)
  })
})

describe('P6-1 文件管理页文案（fileManagement 模块）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh 逐字节（页面/筛选/表格/弹窗/删除确认）', () => {
    setLocale('zh-CN')
    expect(translate('fileManagement.title')).toBe('种子文件管理')
    expect(translate('fileManagement.subtitle')).toBe('管理种子文件备份，支持去重、导出、导入操作')
    expect(translate('fileManagement.filter.searchPlaceholder')).toBe('搜索任务名称或Info Hash...')
    expect(translate('fileManagement.filter.downloaderPlaceholder')).toBe('全部下载器')
    expect(translate('fileManagement.table.uploadedAt')).toBe('上传时间')
    expect(translate('fileManagement.detailDialog.title')).toBe('种子文件详情')
    expect(translate('fileManagement.importDialog.dropPrefix')).toBe('将文件拖到此处，或')
    expect(translate('fileManagement.importDialog.dropAction')).toBe('点击上传')
    expect(translate('fileManagement.msg.deleteConfirm')).toBe('确认删除该种子文件备份吗？')
    expect(translate('fileManagement.msg.importPartialFailed', { list: 'a.torrent' }))
      .toBe('部分文件导入失败:\na.torrent')
  })

  it('en：页面与危险确认输出英文，导入失败文案保留 \n 结构', () => {
    setLocale('en')
    expect(translate('fileManagement.title')).toBe('Torrent File Management')
    expect(translate('fileManagement.msg.deleteConfirm').toLowerCase()).toContain('delete')
    expect(translate('fileManagement.msg.importPartialFailed', { list: 'a.torrent' })).toContain('\n')
  })
})

// ====================================================================
// B. 源码契约：本批 6 文件的关键接线
// ====================================================================

describe('P6-1 源码契约', () => {
  const FILES = {
    traditional: 'src/views/torrents/TraditionalView.vue',
    transfer: 'src/views/torrents/components/TransferDialog.vue',
    batchTransfer: 'src/views/torrents/components/BatchTransferDialog.vue',
    setLocation: 'src/views/torrents/components/SetLocationDialog.vue',
    globalReplace: 'src/views/torrents/components/GlobalReplaceTrackerDialog.vue',
    fileManagement: 'src/views/torrents/FileManagement.vue'
  }

  it('传统视图：模板文案全部走键（工具栏/表头/筛选/分页/列设置）', () => {
    const src = read(FILES.traditional)
    for (const key of [
      'torrent.list.filters.toggle', 'torrent.list.filters.title', 'torrent.list.filters.all',
      'torrent.list.selectedPrefix', 'torrent.list.selectedSuffix', 'torrent.list.connected',
      'torrent.list.activeLabel', 'torrent.list.pagination.prefix', 'torrent.list.column.nameShort',
      'torrent.list.column.savePath', 'torrent.list.resizeHint', 'torrent.list.columnSettings.resetWidths'
    ]) {
      expect(src).toContain(`$t('${key}')`)
    }
    // 关键旧中文字面量不得回流
    expect(src.includes('拖拽调整列宽，双击恢复默认')).toBe(false)
    expect(src.includes('退出排查并返回普通列表')).toBe(false)
  })

  it('传统视图：错误/提示走契约入口（apiResponseMessage），单种操作走 torrent.msg.*', () => {
    const src = read(FILES.traditional)
    expect(src.includes("import { apiResponseMessage } from '@/i18n'")).toBe(true)
    expect(src.includes("torrent.msg.missingDownloaderShort")).toBe(true)
    expect(src.includes("torrent.msg.recheckSubmitted")).toBe(true)
    expect(src.includes("torrent.msg.reannouncePartial")).toBe(true)
    expect(src.includes("torrent.msg.selectFirstReannounce")).toBe(true)
  })

  it('转移/改路径弹窗：确认与校验全部键化，删除原种子危险提示在', () => {
    for (const file of [FILES.transfer, FILES.batchTransfer, FILES.setLocation]) {
      const src = read(file)
      expect(src).toContain("$t('transfer.")
      expect(src.includes('placeholder="请输入或选择目标路径"')).toBe(false)
      expect(src.includes("'请选择目标下载器'")).toBe(false)
    }
    // 危险操作三要素（勾选建议/二次确认/不可逆）在 TransferDialog 中齐备
    const transfer = read(FILES.transfer)
    expect(transfer.includes("$t('transfer.deleteSourceHint')")).toBe(true)
    expect(transfer.includes("$t('transfer.deleteConfirmTitle')")).toBe(true)
    expect(transfer.includes("$t('transfer.deleteConfirmIrreversible')")).toBe(true)
    expect(transfer.includes("'删除原种子失败'")).toBe(false)
    expect(read(FILES.batchTransfer).includes("$t('transfer.msg.batchDeleteSourceFailed')")).toBe(true)
  })

  it('文件管理页：删除确认/导入弹窗/筛选全部键化，错误兜底走键', () => {
    const src = read(FILES.fileManagement)
    expect(src.includes("$t('fileManagement.title')")).toBe(true)
    expect(src.includes("$t('fileManagement.importDialog.dropPrefix')")).toBe(true)
    expect(src.includes("fileManagement.msg.deleteConfirm")).toBe(true)
    expect(src.includes("fileManagement.msg.downloadFailedWithStatus")).toBe(true)
    expect(src.includes("'确认删除该种子文件备份吗？'")).toBe(false)
    expect(src.includes('只能上传 .torrent 文件，支持批量上传')).toBe(false)
  })
})


describe('语义对齐回归', () => {
  afterEach(() => setLocale('zh-CN'))

  it('英文多选与删除结果使用总数而不是额外数量', () => {
    setLocale('en')
    expect(translate('common.multiSelect.multiSelected', { first: 'Alpha', count: 2 }))
      .toBe('Alpha (2 selected)')
    expect(translate('torrent.deleteLevel.result.failedDetailMore', { names: 'A, B, C, D, E', count: 8 }))
      .toBe('The following torrents failed to delete: A, B, C, D, E (8 torrents in total)')
    expect(translate('torrent.deleteLevel.result.fileMissingDetailMore', { names: 'A, B, C, D, E', count: 8 }))
      .toContain('(8 torrents in total)')
    expect(translate('torrent.deleteLevel.result.downgradeDetailMore', { names: 'A, B, C, D, E', count: 8 }))
      .toContain('(8 torrents in total)')
  })

  it('孤儿清理明确是隔离，可在永久删除前恢复', () => {
    setLocale('zh-CN')
    expect(translate('orphanFiles.cleanup.confirmTitle')).toContain('移入隔离区')
    expect(translate('orphanFiles.cleanup.confirmTitle')).toContain('可从隔离区恢复')
    setLocale('en')
    expect(translate('orphanFiles.cleanup.confirmTitle')).toContain('to quarantine')
    expect(translate('orphanFiles.cleanup.confirmTitle')).toContain('restored from quarantine')
    expect(translate('orphanFiles.cleanup.confirmTitle')).not.toContain('cannot be undone')
  })

  it('路径映射说明与转换器的实际前缀替换结果一致', () => {
    expect(translate('downloader.dialog.pathMappingPlaceholderFull', { sep: '{#**#}' }))
      .toContain('/downloads/movie.mkv')
    setLocale('en')
    const text = translate('downloader.dialog.pathMappingPlaceholderFull', { sep: '{#**#}' })
    expect(text).toContain('/downloads/movie.mkv → /volume1/movie.mkv')
    expect(text).toContain('/downloads/movie.mkv → /volume1/downloads/movie.mkv')
    expect(text).not.toContain('append')
  })

  it('转移源任务提示明确保留数据文件', () => {
    setLocale('zh-CN')
    expect(translate('transfer.deleteSourceHint')).toContain('保留数据文件')
    expect(translate('transfer.deleteConfirmQuestion')).toContain('数据文件将保留')
    setLocale('en')
    expect(translate('transfer.deleteSourceHint')).toContain('keep its data files')
    expect(translate('transfer.deleteConfirmQuestion')).toContain('data files will be kept')
  })
})
