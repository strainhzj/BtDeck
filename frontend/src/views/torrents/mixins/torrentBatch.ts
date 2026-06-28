/**
 * 种子批量操作 Mixin（防回归基础设施 v2 / L2）
 *
 * 薄封装层：把 utils/torrentBatch.ts 的纯函数接入 Vue 组件上下文。
 * - 注入真实 API（deleteTorrents / resume / pause / recheck）
 * - 绑定 this（multipleSelection / list / activeSpeedMap / getList）
 * - 统一提示文案（对齐列表模式，消除两视图文案漂移）
 *
 * 两视图（index.vue / TraditionalView.vue）用 mixins(TorrentBatchMixin) 引入，
 * 删除各自重复实现，逻辑单点维护在 utils/torrentBatch.ts + 本 mixin。
 *
 * 对应 bug：Bug#1/#2/#4/#6/#7/#8。
 */
import Component from 'vue-class-component'
import { Vue } from 'vue-property-decorator'
import {
  deleteTorrents,
  resumeTorrents,
  pauseTorrents,
  recheckTorrents,
  type ApiResponse
} from '@/api/torrents'
import {
  groupTorrentsByDownloader,
  deleteTorrentsBatch,
  runBatchAction,
  sortByActive,
  resetSelection,
  type BatchActionResult,
  type BatchDeleteResult
} from '@/views/torrents/utils/torrentBatch'

@Component({ name: 'TorrentBatchMixin' })
export default class TorrentBatchMixin extends Vue {
  // ====== 子类提供的数据成员（definite assignment，避免 tsc 报错） ======
  // 这些成员由引入本 mixin 的视图组件（index.vue / TraditionalView.vue）声明并提供。
  protected multipleSelection!: any[]
  protected list!: any[]
  protected activeSpeedMap!: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }>
  protected getList!: () => Promise<void>

  // ====== 批量操作（文案对齐列表模式） ======

  /**
   * 批量开始/暂停/重检 的通用入口
   * @param actionLabel 操作名（'开始' / '暂停' / '重检'），用于提示文案
   * @returns 批量操作结果（调用方可据此做额外处理）
   */
  protected async runTorrentBatchAction(
    apiFn: (p: { downloader_id: string, hashes: string[] }) => Promise<ApiResponse<any>>,
    actionLabel: string
  ): Promise<BatchActionResult> {
    const result = await runBatchAction(this.multipleSelection, apiFn)

    // 统一文案（对齐列表模式 index.vue），消除两视图漂移
    if (result.failed > 0) {
      this.$message.warning(
        `批量${actionLabel}部分完成：成功${result.succeeded}个下载器，失败${result.failed}个下载器（共${result.total}个种子）`
      )
    } else {
      this.$message.success(`批量${actionLabel}成功(${result.total}个种子, ${result.downloaderCount}个下载器)`)
    }

    await this.getList()
    return result
  }

  /** 批量开始 */
  protected async handleBatchStart(): Promise<void> {
    if (this.multipleSelection.length === 0) return
    try {
      await this.runTorrentBatchAction(resumeTorrents, '开始')
    } catch (error) {
      console.error('批量开始失败:', error)
      this.$message.error('批量开始失败，请查看控制台')
    }
  }

  /** 批量暂停 */
  protected async handleBatchPause(): Promise<void> {
    if (this.multipleSelection.length === 0) return
    try {
      await this.runTorrentBatchAction(pauseTorrents, '暂停')
    } catch (error) {
      console.error('批量暂停失败:', error)
      this.$message.error('批量暂停失败，请查看控制台')
    }
  }

  /** 批量重检 */
  protected async handleBatchRecheck(): Promise<void> {
    if (this.multipleSelection.length === 0) return
    try {
      await this.runTorrentBatchAction(recheckTorrents, '重检')
    } catch (error) {
      console.error('批量重检失败:', error)
      this.$message.error('批量重检失败，请查看控制台')
    }
  }

  // ====== 删除（批量 + 单条，统一对齐列表模式） ======

  /**
   * 批量删除内部逻辑（调用纯函数 deleteTorrentsBatch，注入真实 deleteTorrents）
   * 防回归 Bug#1（计数）、Bug#4（参数 info_id/delete_data/id_recycle）
   */
  protected async deleteTorrentsInternal(
    torrents: any[],
    deleteData: number
  ): Promise<BatchDeleteResult> {
    return deleteTorrentsBatch(torrents, deleteData, deleteTorrents)
  }

  // ====== 排序与选中状态（抽自视图，行为单点） ======

  /** 按活跃度排序后的列表（防回归 Bug#7） */
  protected get sortedActiveList(): any[] {
    return sortByActive(this.list, this.activeSpeedMap)
  }

  /** 重置批量选中状态（防回归 Bug#8，分页/筛选切换后调用） */
  protected resetBatchSelection(): void {
    resetSelection(this as any)
  }

  // ====== 分组工具（供子类独有 handler 复用，如 handleBatchReannounce） ======

  protected groupTorrentsByDownloader(torrents: any[]): Record<string, any[]> {
    return groupTorrentsByDownloader(torrents)
  }
}
