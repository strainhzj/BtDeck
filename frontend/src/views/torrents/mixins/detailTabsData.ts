/**
 * 种子详情卡片数据 Mixin（TrackerDetailCard 文件/Peers/媒体库 页签）
 *
 * 两视图（index.vue / TraditionalView.vue）共用 TrackerDetailCard，文件/Peers/
 * 媒体库数据的加载、缓存与轮询逻辑完全一致，抽到本 mixin 单点维护。卡片保持
 * 纯 props 展示，不发起 API 调用。
 *
 * 职责：
 * - 文件页签：切入时按 `${downloader_id}:${hash}` 键控懒加载一次，手动刷新强制重取
 * - Peers 页签：切入时立即加载并启动 5s 链式轮询（照抄 SpeedPollingMixin 骨架：
 *   请求完成后再 arm 下一次，不堆叠；后台标签页 visibilitychange 暂停/恢复）
 * - 媒体库页签：MoviePilot 整理历史关联（键控懒加载同文件页签，无轮询）；
 *   空列表是合法业务态（该任务未整理过），与错误态区分展示
 * - 生命周期：currentRow 置空（卡片关闭）停轮询清数据；非空→非空（换种子）停旧
 *   轮询并使缓存失效；beforeDestroy 兜底清理
 * - 竞态守卫：请求序号 + 当前键比对双重校验，过期响应/换种子在途响应一律丢弃
 * - 错误分类：信封 code='404'（种子/下载器已不存在）自动停轮询——兜住列表模式
 *   删除当前种子后未清 currentRow 的既有缺口；其余错误保留上次数据仅置错误态
 *
 * 子类需提供（definite assignment，同 TorrentBatchMixin 先例）：
 * - currentRow：当前选中行（含 hash / downloader_id|downloaderId）
 * - activeDetailTab：当前激活页签（'tracker' | 'files' | 'peers' | 'media'）
 */
import Component from 'vue-class-component'
import { Vue, Watch } from 'vue-property-decorator'
import {
  getTorrentFiles,
  getTorrentPeers,
  type TorrentFileInfo,
  type TorrentPeerInfo
} from '@/api/torrents'
import {
  getTorrentMoviePilotAssociations,
  type MoviePilotAssociationItem
} from '@/api/moviepilot'
import { extractErrorMessage } from '@/utils/formatters'

// ts-jest/tsc 无法从 .vue 解析命名类型导出（TS2614，.vue→.vue 可过是因为
// vue-jest 不做类型检查）。此处内联同款定义解除阻塞；类型源头统一请后续
// 批次把 TrackerDetailTabValue 迁到 .ts 再让 TrackerDetailCard.vue 反向导入。
export type TrackerDetailTabValue = 'tracker' | 'files' | 'peers' | 'media'

/** 页签数据状态（卡片按 {list, loading, error} 聚合消费） */
export interface DetailTabDataState<T> {
  list: T[]
  loading: boolean
  error: string
}

/** 种子身份的最小结构（currentRow 行对象的结构子集） */
interface DetailTorrentRowLike {
  hash: string
  downloader_id?: string
  downloaderId?: string
}

function emptyState<T>(): DetailTabDataState<T> {
  return { list: [], loading: false, error: '' }
}

@Component({ name: 'TrackerDetailDataMixin' })
export default class TrackerDetailDataMixin extends Vue {
  // ====== 子类提供的数据成员（definite assignment，避免 tsc 报错） ======
  protected currentRow!: DetailTorrentRowLike | null
  protected activeDetailTab!: TrackerDetailTabValue

  // ====== 页签数据状态 ======
  protected detailFilesState: DetailTabDataState<TorrentFileInfo> = emptyState()
  protected detailPeersState: DetailTabDataState<TorrentPeerInfo> = emptyState()
  protected detailMediaState: DetailTabDataState<MoviePilotAssociationItem> = emptyState()

  /** 文件/媒体库页签缓存键（`${downloader_id}:${hash}`）：换种子自动失效 */
  private detailFilesKey = ''
  private detailMediaKey = ''

  /** Peers 轮询（SpeedPollingMixin 同款链式骨架） */
  protected detailPeersPollIntervalMs = 5000
  private detailPeersTimer: number | null = null
  private detailPeersActive = false

  /** 请求序号守卫：停轮询/换种子时自增使在途响应失效 */
  private detailFilesSeq = 0
  private detailPeersSeq = 0
  private detailMediaSeq = 0

  @Watch('activeDetailTab')
  private onActiveDetailTabChange(newTab: TrackerDetailTabValue, oldTab: TrackerDetailTabValue) {
    if (oldTab === 'peers') {
      this.stopPeersPolling()
    }
    if (newTab === 'files') {
      this.loadDetailFiles(false)
    } else if (newTab === 'peers') {
      this.startPeersPolling()
    } else if (newTab === 'media') {
      this.loadDetailMedia(false)
    }
  }

  @Watch('currentRow')
  private onCurrentRowChange(
    newRow: DetailTorrentRowLike | null,
    oldRow: DetailTorrentRowLike | null
  ) {
    if (!newRow) {
      // 卡片关闭：停轮询、清数据、丢弃在途
      this.stopPeersPolling()
      this.resetDetailTabsData()
      return
    }
    if (oldRow && this.detailTorrentKey(oldRow) !== this.detailTorrentKey(newRow)) {
      // 换种子：停旧轮询并使缓存失效（两视图换行时都会重置页签为 tracker，
      // 下方分支仅为页签未重置的防御路径）
      this.stopPeersPolling()
      this.resetDetailTabsData()
      if (this.activeDetailTab === 'files') {
        this.loadDetailFiles(false)
      } else if (this.activeDetailTab === 'peers') {
        this.startPeersPolling()
      } else if (this.activeDetailTab === 'media') {
        this.loadDetailMedia(false)
      }
    }
  }

  protected beforeDestroy(): void {
    this.stopPeersPolling()
  }

  /** 手动刷新入口（卡片内刷新按钮 → $emit('refresh', tab)） */
  protected handleDetailRefresh(tab: TrackerDetailTabValue): void {
    if (tab === 'files') {
      this.loadDetailFiles(true)
    } else if (tab === 'peers') {
      // 先停（使在途失效）再立即拉取，并重置轮询节奏，避免与轮询竞争
      this.stopPeersPolling()
      this.startPeersPolling()
    } else if (tab === 'media') {
      this.loadDetailMedia(true)
    }
  }

  /** 加载文件列表；force=true 跳过同键缓存强制重取 */
  protected async loadDetailFiles(force = false): Promise<void> {
    const row = this.currentRow
    const key = this.detailTorrentKey(row)
    if (!row || !key) return
    if (!force && this.detailFilesKey === key && !this.detailFilesState.error) return

    const seq = ++this.detailFilesSeq
    this.detailFilesState = { ...this.detailFilesState, loading: true }
    try {
      const res = await getTorrentFiles(row.hash, row.downloader_id || row.downloaderId || '')
      if (seq !== this.detailFilesSeq || key !== this.detailTorrentKey(this.currentRow)) return
      if (res.code === '200' && res.data) {
        this.detailFilesState = { list: res.data.list || [], loading: false, error: '' }
        this.detailFilesKey = key
      } else {
        // 失败保留上次数据，仅置错误态
        this.detailFilesState = {
          ...this.detailFilesState,
          loading: false,
          error: res.msg || '获取文件列表失败'
        }
      }
    } catch (error) {
      if (seq !== this.detailFilesSeq || key !== this.detailTorrentKey(this.currentRow)) return
      this.detailFilesState = {
        ...this.detailFilesState,
        loading: false,
        error: extractErrorMessage(error)
      }
    }
  }

  /**
   * 加载 MoviePilot 媒体库关联（整理历史）；force=true 跳过同键缓存强制重取。
   * 空列表是合法业务态（该任务从未被 MoviePilot 整理过），卡片侧与错误态区分展示。
   */
  protected async loadDetailMedia(force = false): Promise<void> {
    const row = this.currentRow
    const key = this.detailTorrentKey(row)
    if (!row || !key) return
    if (!force && this.detailMediaKey === key && !this.detailMediaState.error) return

    const seq = ++this.detailMediaSeq
    this.detailMediaState = { ...this.detailMediaState, loading: true }
    try {
      const res = await getTorrentMoviePilotAssociations(
        row.downloader_id || row.downloaderId || '',
        row.hash
      )
      if (seq !== this.detailMediaSeq || key !== this.detailTorrentKey(this.currentRow)) return
      if (res.code === '200' && res.data) {
        this.detailMediaState = { list: res.data.list || [], loading: false, error: '' }
        this.detailMediaKey = key
      } else {
        // 失败保留上次数据，仅置错误态
        this.detailMediaState = {
          ...this.detailMediaState,
          loading: false,
          error: res.msg || '获取媒体库关联失败'
        }
      }
    } catch (error) {
      if (seq !== this.detailMediaSeq || key !== this.detailTorrentKey(this.currentRow)) return
      this.detailMediaState = {
        ...this.detailMediaState,
        loading: false,
        error: extractErrorMessage(error)
      }
    }
  }

  /** 启动 Peers 链式轮询（立即执行首轮；重复调用幂等） */
  protected startPeersPolling(): void {
    this.registerPeersVisibilityListener()
    if (this.detailPeersActive) return
    this.detailPeersActive = true
    const poll = async() => {
      if (!this.detailPeersActive) return
      await this.loadDetailPeers()
      if (!this.detailPeersActive) return
      // 请求完成后再等一个周期发下一次（不堆叠请求）
      this.detailPeersTimer = window.setTimeout(poll, this.detailPeersPollIntervalMs)
    }
    poll()
  }

  /** 停止 Peers 轮询并使在途响应失效（幂等） */
  protected stopPeersPolling(): void {
    this.detailPeersActive = false
    this.detailPeersSeq += 1
    if (this.detailPeersTimer) {
      clearTimeout(this.detailPeersTimer)
      this.detailPeersTimer = null
    }
    this.removePeersVisibilityListener()
  }

  /** 拉取一次 Peers 列表（轮询与手动刷新共用；始终重取不缓存） */
  private async loadDetailPeers(): Promise<void> {
    const row = this.currentRow
    const key = this.detailTorrentKey(row)
    if (!row || !key) return
    const seq = ++this.detailPeersSeq
    this.detailPeersState = { ...this.detailPeersState, loading: true }
    try {
      const res = await getTorrentPeers(row.hash, row.downloader_id || row.downloaderId || '')
      if (seq !== this.detailPeersSeq || key !== this.detailTorrentKey(this.currentRow)) return
      if (res.code === '200' && res.data) {
        this.detailPeersState = { list: res.data.list || [], loading: false, error: '' }
      } else {
        this.detailPeersState = {
          ...this.detailPeersState,
          loading: false,
          error: res.msg || '获取Peer列表失败'
        }
        // 种子/下载器已不存在：轮询无意义，自动停止（列表模式删除当前种子后
        // 未清 currentRow 的场景由该分支兜住）
        if (res.code === '404') {
          this.stopPeersPolling()
        }
      }
    } catch (error) {
      if (seq !== this.detailPeersSeq || key !== this.detailTorrentKey(this.currentRow)) return
      this.detailPeersState = {
        ...this.detailPeersState,
        loading: false,
        error: extractErrorMessage(error)
      }
    }
  }

  private resetDetailTabsData(): void {
    this.detailFilesState = emptyState()
    this.detailPeersState = emptyState()
    this.detailMediaState = emptyState()
    this.detailFilesKey = ''
    this.detailMediaKey = ''
    this.detailFilesSeq += 1
    this.detailPeersSeq += 1
    this.detailMediaSeq += 1
  }

  private detailTorrentKey(row: DetailTorrentRowLike | null): string {
    if (!row || !row.hash) return ''
    return `${row.downloader_id || row.downloaderId || ''}:${row.hash}`
  }

  // ====== 后台标签页暂停/恢复（同 SpeedPollingMixin 语义） ======

  // 注意：不能用类字段箭头函数做事件 handler——vue-class-component 的字段默认值
  // 共享机制会使箭头捕获非组件实例的 this（实测 pause 写到幽灵对象上，真实组件
  // 轮询停不下来）。handler 闭包在方法内创建（方法调用的 this 是真实组件实例，
  // 已实证），实例字段只保存引用。
  private detailVisibilityHandler: (() => void) | null = null

  private registerPeersVisibilityListener(): void {
    if (!this.detailVisibilityHandler) {
      this.detailVisibilityHandler = () => {
        if (document.hidden) {
          this.detailPeersActive = false
          if (this.detailPeersTimer) {
            clearTimeout(this.detailPeersTimer)
            this.detailPeersTimer = null
          }
        } else if (this.activeDetailTab === 'peers' && this.currentRow) {
          this.startPeersPolling()
        }
      }
    }
    document.addEventListener('visibilitychange', this.detailVisibilityHandler)
  }

  private removePeersVisibilityListener(): void {
    if (this.detailVisibilityHandler) {
      document.removeEventListener('visibilitychange', this.detailVisibilityHandler)
      this.detailVisibilityHandler = null
    }
  }
}
