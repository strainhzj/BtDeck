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
import { translate, apiResponseMessage } from '@/i18n'
import {
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
  runBatchAction,
  sortByActive,
  resetSelection,
  buildDeleteLevelRequest,
  buildDeleteConfirmMessage,
  parseDeleteTaskResult,
  parseSyncDeleteResponse,
  type BatchActionResult
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
   * @param actionKey 操作键（'start' / 'pause' / 'recheck'，映射 torrent.batch.action.* 文案）
   * @returns 批量操作结果（调用方可据此做额外处理）
   */
  protected async runTorrentBatchAction(
    apiFn: (p: { downloader_id: string, hashes: string[] }) => Promise<ApiResponse<any>>,
    actionKey: 'start' | 'pause' | 'recheck'
  ): Promise<BatchActionResult> {
    const result = await runBatchAction(this.multipleSelection, apiFn)
    const actionLabel = translate(`torrent.batch.action.${actionKey}`)

    // 统一文案（对齐列表模式 index.vue），消除两视图漂移
    if (result.failed > 0) {
      this.$message.warning(
        translate('torrent.batch.partial', {
          action: actionLabel,
          succeeded: result.succeeded,
          failed: result.failed,
          total: result.total
        })
      )
    } else {
      this.$message.success(
        translate('torrent.batch.success', {
          action: actionLabel,
          total: result.total,
          downloaderCount: result.downloaderCount
        })
      )
    }

    await this.getList()
    return result
  }

  /** 批量开始 */
  protected async handleBatchStart(): Promise<void> {
    if (this.multipleSelection.length === 0) return
    try {
      await this.runTorrentBatchAction(resumeTorrents, 'start')
    } catch (error) {
      console.error('批量开始失败:', error)
      this.$message.error(translate('torrent.batch.failed.start'))
    }
  }

  /** 批量暂停 */
  protected async handleBatchPause(): Promise<void> {
    if (this.multipleSelection.length === 0) return
    try {
      await this.runTorrentBatchAction(pauseTorrents, 'pause')
    } catch (error) {
      console.error('批量暂停失败:', error)
      this.$message.error(translate('torrent.batch.failed.pause'))
    }
  }

  /** 批量重检 */
  protected async handleBatchRecheck(): Promise<void> {
    if (this.multipleSelection.length === 0) return
    try {
      await this.runTorrentBatchAction(recheckTorrents, 'recheck')
    } catch (error) {
      console.error('批量重检失败:', error)
      this.$message.error(translate('torrent.batch.failed.recheck'))
    }
  }

  // ====== 删除（单点收敛：双语 P5 起两视图共用四级删除链路，见下方 P2-I 分层） ======

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
      await this.$confirm(message, translate('torrent.deleteLevel.confirm.titleSingle'), {
        confirmButtonText: translate('torrent.deleteLevel.confirm.confirmButton'),
        cancelButtonText: translate('torrent.deleteLevel.confirm.cancelButton'),
        type: levelNum === 1 ? 'error' : 'warning'
      })
      await this.executeDeleteByLevel([torrent], levelNum)
    } catch (error: any) {
      if (error !== 'cancel') {
        this.$message.error(error?.message || translate('torrent.deleteLevel.msg.deleteFailed'))
      }
    }
  }

  /** 批量种子按等级删除命令 */
  protected async handleBatchDeleteByLevelCommand(level: string | number): Promise<void> {
    if (this.multipleSelection.length === 0) {
      this.$message.warning(translate('torrent.deleteLevel.msg.selectFirst'))
      return
    }
    const levelNum = typeof level === 'string' ? parseInt(level, 10) : level
    const message = buildDeleteConfirmMessage(levelNum, this.multipleSelection.length)
    try {
      await this.$confirm(message, translate('torrent.deleteLevel.confirm.titleBatch'), {
        confirmButtonText: translate('torrent.deleteLevel.confirm.confirmButton'),
        cancelButtonText: translate('torrent.deleteLevel.confirm.cancelButton'),
        type: levelNum === 1 ? 'error' : 'warning'
      })
      await this.executeDeleteByLevel(this.multipleSelection, levelNum)
    } catch (error: any) {
      if (error !== 'cancel') {
        this.$message.error(error?.message || translate('torrent.deleteLevel.msg.batchDeleteFailed'))
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
          // 双语 P5：优先 data.reasonCode 本地化，未契约化路径回退固定文案
          throw new Error(
            apiResponseMessage(response, translate('torrent.deleteLevel.msg.submitFailed'))
          )
        }
        const taskId = response.data?.task_id
        if (!taskId) {
          this.$message.info(
            apiResponseMessage(response, translate('torrent.deleteLevel.msg.alreadyProcessed'))
          )
          await this.getList()
          return
        }
        const skippedCount = response.data?.skipped_count || 0
        if (skippedCount > 0) {
          this.$message.warning(translate('torrent.deleteLevel.msg.skipped', { count: skippedCount }))
        }
        // 提交成功即刷新；后端列表会排除 pending/running 任务里的种子。
        await this.getList()
        await this.pollDeleteTaskStatus(taskId)
      } else {
        const response = await deleteTorrentsWithLevel(req)
        if (response.code !== '200') {
          throw new Error(
            apiResponseMessage(response, translate('torrent.deleteLevel.msg.deleteFailed'))
          )
        }
        const parsed = parseSyncDeleteResponse(response.data, level)
        this.$message[parsed.type](parsed.message)
        if (parsed.downgradeDetail) {
          this.$notify.warning({
            title: translate('torrent.deleteLevel.notify.downgradeTitle'),
            message: parsed.downgradeDetail,
            duration: 5000
          })
        }
        if (parsed.fileMissingDetail) {
          this.$notify.warning({
            title: translate('torrent.deleteLevel.notify.fileMissingTitle'),
            message: parsed.fileMissingDetail,
            duration: 5000
          })
        }
      }
      await this.getList()
    } catch (error: any) {
      const errorMessage = error?.response?.data?.msg ??
                           error?.message ??
                           translate('torrent.deleteLevel.msg.retryLater')
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
      text: translate('torrent.deleteLevel.progress.loading'),
      spinner: 'el-icon-loading',
      background: 'rgba(0, 0, 0, 0.7)'
    })

    try {
      while (pollAttempts < maxPollAttempts) {
        const response = await getBatchDeleteStatus(taskId)
        if (response.code !== '200') {
          throw new Error(
            apiResponseMessage(response, translate('torrent.deleteLevel.msg.statusQueryFailed'))
          )
        }
        const taskData = response.data

        if (taskData.status === 'running' && this.deleteLoadingInstance) {
          const progress = taskData.success_count + taskData.failed_count
          this.deleteLoadingInstance.text = translate('torrent.deleteLevel.progress.running', {
            done: progress,
            total: taskData.total_count
          })
        }

        if (['completed', 'failed', 'partial'].includes(taskData.status)) {
          const parsed = parseDeleteTaskResult(taskData, this.list)
          this.$message[parsed.type](parsed.message)
          if (parsed.failedDetail) {
            this.$notify.warning({
              title: translate('torrent.deleteLevel.notify.failedTitle'),
              message: parsed.failedDetail,
              duration: 5000
            })
          }
          if (parsed.fileMissingDetail) {
            this.$notify.warning({
              title: translate('torrent.deleteLevel.notify.fileMissingTitle'),
              message: parsed.fileMissingDetail,
              duration: 5000
            })
          }
          break
        }

        await new Promise(resolve => setTimeout(resolve, pollInterval))
        pollAttempts++
      }

      if (pollAttempts >= maxPollAttempts) {
        this.$message.warning(translate('torrent.deleteLevel.progress.timeout'))
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
}
