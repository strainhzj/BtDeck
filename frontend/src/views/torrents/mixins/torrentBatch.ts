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
  deleteTorrentsWithLevel,
  deleteBatchAsync,
  getBatchDeleteStatus,
  type ApiResponse
} from '@/api/torrents'
import {
  groupTorrentsByDownloader,
  deleteTorrentsBatch,
  runBatchAction,
  sortByActive,
  resetSelection,
  buildDeleteLevelRequest,
  buildDeleteConfirmMessage,
  parseDeleteTaskResult,
  parseSyncDeleteResponse,
  DELETE_LEVEL_NAMES,
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

  // P2-I：4 等级删除的 loading 遮罩引用（组件销毁时需清理，避免遮罩残留）
  private deleteLoadingInstance: any = null

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

  // ====== 4 等级删除（P2-I 分层：mixin 入口层，含 API + loading + 轮询） ======
  // 无副作用的「构造请求/解析结果」在 utils 纯函数层（已单测）。
  // 此处只保留带 Vue 实例依赖的逻辑（$loading/$message/$notify/$confirm + 轮询）。

  /** 单条种子按等级删除命令（el-dropdown command 触发，level 为字符串） */
  protected async handleDeleteByLevelCommand(level: string | number, torrent: any): Promise<void> {
    const levelNum = typeof level === 'string' ? parseInt(level, 10) : level
    const message = buildDeleteConfirmMessage(levelNum, 1)
    try {
      await this.$confirm(message, '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: levelNum === 1 ? 'error' : 'warning'
      })
      await this.executeDeleteByLevel([torrent], levelNum)
    } catch (error: any) {
      if (error !== 'cancel') {
        this.$message.error(error?.message || '删除失败')
      }
    }
  }

  /** 批量种子按等级删除命令 */
  protected async handleBatchDeleteByLevelCommand(level: string | number): Promise<void> {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要删除的种子')
      return
    }
    const levelNum = typeof level === 'string' ? parseInt(level, 10) : level
    const message = buildDeleteConfirmMessage(levelNum, this.multipleSelection.length)
    try {
      await this.$confirm(message, '批量删除确认', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: levelNum === 1 ? 'error' : 'warning'
      })
      await this.executeDeleteByLevel(this.multipleSelection, levelNum)
    } catch (error: any) {
      if (error !== 'cancel') {
        this.$message.error(error?.message || '批量删除失败')
      }
    }
  }

  /**
   * 执行 4 等级删除（统一入口）
   * - ≥2 个种子：走异步批量接口 deleteBatchAsync + 轮询
   * - 单个种子：走同步接口 deleteTorrentsWithLevel
   * 请求构造/结果解析委托纯函数，此处只处理 API 调用 + loading + 提示。
   */
  protected async executeDeleteByLevel(torrents: any[], level: number): Promise<void> {
    const req = buildDeleteLevelRequest(torrents, level)
    try {
      if (torrents.length >= 2) {
        const response = await deleteBatchAsync(req)
        if (response.code !== '200') {
          throw new Error(response.msg || '提交删除任务失败')
        }
        const taskId = response.data?.task_id
        if (!taskId) {
          this.$message.info(response.msg || '所选种子均已在删除任务中处理')
          await this.getList()
          return
        }
        const skippedCount = response.data?.skipped_count || 0
        if (skippedCount > 0) {
          this.$message.warning(`已跳过 ${skippedCount} 个正在处理的种子`)
        }
        // 提交成功即刷新；后端列表会排除 pending/running 任务里的种子。
        await this.getList()
        await this.pollDeleteTaskStatus(taskId)
      } else {
        const response = await deleteTorrentsWithLevel(req)
        if (response.code !== '200') {
          throw new Error(response.msg || '删除失败')
        }
        const parsed = parseSyncDeleteResponse(response.data, level)
        this.$message[parsed.type](parsed.message)
        if (parsed.downgradeDetail) {
          this.$notify.warning({ title: '降级详情', message: parsed.downgradeDetail, duration: 5000 })
        }
      }
      await this.getList()
    } catch (error: any) {
      const errorMessage = error?.response?.data?.msg ?? error?.message ?? '删除失败，请稍后重试'
      console.error('[删除异常]', { level, error: errorMessage })
      this.$message.error(errorMessage)
    }
  }

  /**
   * 轮询批量删除任务状态（带 loading 遮罩）
   * @param taskId 任务ID
   */
  private async pollDeleteTaskStatus(taskId: string): Promise<void> {
    const pollInterval = 5000
    const maxPollAttempts = 120 // 10 分钟
    let pollAttempts = 0

    this.deleteLoadingInstance = this.$loading({
      lock: true,
      text: '批量删除中，请稍候...',
      spinner: 'el-icon-loading',
      background: 'rgba(0, 0, 0, 0.7)'
    })

    try {
      while (pollAttempts < maxPollAttempts) {
        const response = await getBatchDeleteStatus(taskId)
        if (response.code !== '200') {
          throw new Error(response.msg || '查询任务状态失败')
        }
        const taskData = response.data

        if (taskData.status === 'running' && this.deleteLoadingInstance) {
          const progress = taskData.success_count + taskData.failed_count
          this.deleteLoadingInstance.text = `批量删除中... (${progress}/${taskData.total_count})`
        }

        if (['completed', 'failed', 'partial'].includes(taskData.status)) {
          const parsed = parseDeleteTaskResult(taskData, this.list)
          this.$message[parsed.type](parsed.message)
          if (parsed.failedDetail) {
            this.$notify.warning({ title: '删除失败详情', message: parsed.failedDetail, duration: 5000 })
          }
          break
        }

        await new Promise(resolve => setTimeout(resolve, pollInterval))
        pollAttempts++
      }

      if (pollAttempts >= maxPollAttempts) {
        this.$message.warning('批量删除任务执行时间过长，请稍后查看任务状态')
      }
    } finally {
      this.closeDeleteLoading()
    }
  }

  /** 关闭 loading 遮罩（幂等，防残留） */
  private closeDeleteLoading(): void {
    if (this.deleteLoadingInstance) {
      try {
        this.deleteLoadingInstance.close()
      } catch (e) {
        // 静默：遮罩可能已被关闭
      }
      this.deleteLoadingInstance = null
    }
  }

  /**
   * 组件销毁前清理 loading（防回归 P2-I：长轮询期间组件销毁会残留遮罩）
   * 子类若重写 beforeDestroy，需 super 调用或自行调 closeDeleteLoading。
   */
  protected beforeDestroy(): void {
    this.closeDeleteLoading()
  }

  /** 等级名称映射（供视图 dropdown 菜单文案） */
  protected get deleteLevelNames(): Record<number, string> {
    return DELETE_LEVEL_NAMES
  }
}
