<template>
  <div class="m-torrents">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div class="m-toolbar">
      <el-button
        class="m-toolbar-filter"
        size="small"
        :type="filtersExpanded ? 'primary' : 'default'"
        :plain="filtersExpanded"
        icon="el-icon-search"
        @click="filtersExpanded = !filtersExpanded"
      >
        筛选<template v-if="activeFilterCount">（{{ activeFilterCount }}）</template>
      </el-button>
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reload">刷新</el-button>
      <!-- 快捷操作（与桌面种子页同语义四项）：查重/排查是列表模式切换，快捷删重是独立弹窗 -->
      <el-dropdown trigger="click" @command="handleQuickActionCommand">
        <el-button size="small" icon="el-icon-s-operation">
          快捷<i class="el-icon-arrow-down el-icon--right" />
        </el-button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="toggle-duplicates">
            <i v-if="listMode === 'duplicates'" class="el-icon-check" />查找重复任务
          </el-dropdown-item>
          <el-dropdown-item command="inspect-same-content">
            <i v-if="listMode === 'same-content'" class="el-icon-check" />辅种异常排查
          </el-dropdown-item>
          <el-dropdown-item command="inspect-single-errors">
            <i v-if="listMode === 'single-errors'" class="el-icon-check" />错误单种排查
          </el-dropdown-item>
          <el-dropdown-item command="delete-duplicates" divided>快捷删除重复种子</el-dropdown-item>
          <!-- 全局操作组（与桌面工具栏同语义）：添加种子/全局替换直接开弹窗；
               Tracker操作/汇报移动端无多选，改为先选下载器再执行 -->
          <el-dropdown-item command="add-torrent" divided>添加种子</el-dropdown-item>
          <el-dropdown-item command="tracker-operation">Tracker操作</el-dropdown-item>
          <el-dropdown-item command="tracker-reannounce">Tracker汇报</el-dropdown-item>
          <el-dropdown-item command="global-replace">全局替换Tracker</el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>

    <!-- 列表模式横幅：查重/排查激活时提示口径与结果数，可一键退出 -->
    <div v-if="listMode !== 'normal'" class="m-mode-banner">
      <span class="m-mode-banner-text">
        {{ modeNoun }}模式<template v-if="!loading"> · 共 {{ total }} 条</template>
      </span>
      <el-button type="text" size="mini" class="m-mode-banner-exit" @click="exitListMode">退出</el-button>
    </div>

    <!-- 简单搜索（自移动高级搜索页迁入）：与桌面 torrents 快捷筛选同字段集（name/下载器/状态/tracker 域） -->
    <div v-if="filtersExpanded" class="m-torrents-filters">
      <el-input
        v-model="filters.name"
        size="small"
        placeholder="种子名称关键词"
        clearable
        prefix-icon="el-icon-search"
        @keyup.enter.native="runFilters"
      />
      <el-select
        v-model="filters.downloaders"
        size="small"
        multiple
        filterable
        collapse-tags
        placeholder="全部下载器"
        clearable
      >
        <el-option v-for="d in downloaderOptions" :key="d.value" :label="d.label" :value="d.value" />
      </el-select>
      <el-select
        v-model="filters.statuses"
        size="small"
        multiple
        collapse-tags
        placeholder="全部状态"
        clearable
      >
        <el-option v-for="opt in TORRENT_STATUS_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-select
        v-model="filters.trackerDomains"
        size="small"
        multiple
        filterable
        allow-create
        default-first-option
        collapse-tags
        placeholder="Tracker 域名"
        clearable
      >
        <el-option v-for="domain in trackerDomainOptions" :key="domain" :label="domain" :value="domain" />
      </el-select>
      <div class="m-torrents-filter-actions">
        <el-button size="small" :loading="loading" @click="resetFilters">重置</el-button>
        <el-button type="primary" size="small" :loading="loading" @click="runFilters">搜索</el-button>
      </div>
    </div>

    <div v-if="!loading && list.length === 0" class="m-hint m-empty">
      <template v-if="listMode !== 'normal'">未发现{{ modeNoun }}</template>
      <template v-else-if="hasFilters">没有匹配的种子</template>
      <template v-else-if="optionsLoaded && downloaderOptions.length === 0">
        <div class="m-empty-title">还没有种子</div>
        <div class="m-empty-desc">先添加下载器，同步后即可在这里管理种子</div>
        <el-button size="small" type="primary" plain class="m-empty-cta" @click="goAddDownloader">
          去添加下载器
        </el-button>
      </template>
      <template v-else-if="optionsLoaded">
        暂无种子——添加下载器并同步后，种子会出现在这里
      </template>
      <template v-else>暂无种子</template>
    </div>

    <!-- 无限滚动：window 滚动驱动（mixins/window-infinite-scroll；Element 指令会被
         从不内滚的 .mobile-content 误判恒在底部，实测页面打开自动连发请求拉满 total）；
         尾部计数提示非交互（替代旧"加载更多"按钮） -->
    <div class="m-torrents-list">
      <div
        v-for="t in list"
        :key="`${t.downloaderId}-${t.hash}`"
        class="m-torrent-card"
        role="button"
        @click="openDetail(t)"
      >
        <div class="m-torrent-name" :title="t.name">{{ t.name }}</div>
        <div class="m-torrent-meta">
          <el-tag size="mini" :type="statusTagType(t.status)">{{ statusLabel(t.status) }}</el-tag>
          <span class="m-torrent-meta-text">{{ t.downloaderName }}</span>
          <span class="m-torrent-meta-text">{{ formatSize(t.size) }}</span>
          <!-- 辅种数量（与桌面列同口径：缺失回退 1） -->
          <span
            class="m-torrent-meta-text m-torrent-aux"
            :class="{'m-torrent-aux-hot': auxiliarySeedCountOf(t) > 1}"
          >辅种 {{ auxiliarySeedCountOf(t) }}</span>
        </div>
        <el-progress
          :percentage="progressOf(t)"
          :status="t.status === 'error' ? 'exception' : undefined"
          :stroke-width="6"
          :show-text="false"
        />
        <div class="m-torrent-progress-text">
          {{ progressOf(t).toFixed(1) }}%<template v-if="t.errorReason"> · {{ t.errorReason }}</template>
        </div>
        <!-- 实时速度（10s 轮询 active-torrents）：速度>0 才显示，min-width 防宽度抖动 -->
        <div v-if="hasLiveSpeed(t)" class="m-torrent-speed">
          <span v-if="speedValue(t, 'download') > 0" class="m-torrent-speed-item">↓ {{ formatSpeedText(t, 'download') }}</span>
          <span v-if="speedValue(t, 'upload') > 0" class="m-torrent-speed-item">↑ {{ formatSpeedText(t, 'upload') }}</span>
        </div>
        <div class="m-torrent-actions" @click.stop>
          <el-button size="mini" :disabled="actionBusy(t)" @click="pause(t)">暂停</el-button>
          <el-button size="mini" :disabled="actionBusy(t)" @click="resume(t)">恢复</el-button>
          <!-- 转移受主机能力矩阵门控（android-server 形态无下载器主机文件系统，fail-closed） -->
          <el-button
            v-if="seedTransferAvailable"
            size="mini"
            :disabled="actionBusy(t)"
            @click="openTransfer(t)"
          >转移</el-button>
          <el-button size="mini" :disabled="actionBusy(t)" @click="openSetLocation(t)">修改路径</el-button>
          <el-button size="mini" type="danger" plain :disabled="actionBusy(t)" @click="remove(t)">删除</el-button>
        </div>
      </div>

      <div v-if="list.length && list.length < total" class="m-load-more-hint">
        已加载 {{ list.length }} / 共 {{ total }}
      </div>
      <div v-if="loading && list.length" class="m-load-more-hint">
        <i class="el-icon-loading" /> 加载中…
      </div>
    </div>

    <!-- 长列表返回顶部浮标（滚动容器 scrollTop 超阈值显示） -->
    <button v-show="showBackTop" type="button" class="m-backtop" aria-label="返回顶部" @click="scrollToTop">
      <i class="el-icon-top" />
    </button>

    <!-- 四级删除（与桌面种子页删除下拉同语义）：点选等级→同款文案二次确认→confirm(level) -->
    <m-delete-level-dialog
      :visible.sync="deleteDialogVisible"
      :name="deleteTargetName"
      :busy="anyBusy"
      @confirm="confirmDelete"
    />

    <!-- 快捷删除重复种子（与桌面同款自包含弹窗；D2 批次补手机样式适配） -->
    <quick-delete-duplicates-dialog
      :visible.sync="quickDeleteVisible"
      @close="quickDeleteVisible = false"
      @deleted="onQuickDeleted"
    />

    <!-- 复用桌面种子操作弹窗（custom-class 供 ≤768 收窄宽度；懒加载控制路由包体）：
         转移/修改路径按单种卡片行执行，添加种子/Tracker操作/全局替换由快捷操作触发 -->
    <transfer-dialog
      :visible.sync="transferVisible"
      :torrent="transferTarget"
      custom-class="m-reuse-dialog"
      @success="onTorrentMutated"
    />
    <set-location-dialog
      :visible.sync="setLocationVisible"
      :torrents="setLocationTorrents"
      custom-class="m-reuse-dialog"
      @success="onTorrentMutated"
    />
    <torrent-add-dialog
      :visible.sync="addDialogVisible"
      :downloaders="downloaderRawList"
      custom-class="m-reuse-dialog"
      @confirm="onTorrentMutated"
      @batch-complete="onTorrentMutated"
    />
    <tracker-operation-dialog
      :visible.sync="trackerOperationVisible"
      :selected-torrents="[]"
      :scope-downloader="trackerOperationScope"
      operation-type=""
      custom-class="m-reuse-dialog"
      @success="onTorrentMutated"
    />
    <global-replace-tracker-dialog
      :visible.sync="globalReplaceVisible"
      custom-class="m-reuse-dialog"
      @success="onTorrentMutated"
    />

    <!-- 下载器选择器（Tracker操作/汇报的批量范围入口，移动端无多选的替代语义） -->
    <el-dialog
      title="选择下载器"
      :visible.sync="pickerVisible"
      width="340px"
      custom-class="m-downloader-picker"
    >
      <div class="m-picker-list">
        <button
          v-if="pickerMode === 'reannounce'"
          type="button"
          class="m-picker-item"
          :disabled="pickerBusy"
          @click="onPickerDownloader('')"
        >
          <span>全部下载器</span>
          <span class="m-picker-item-desc">对全部下载器的所有种子重新汇报 Tracker</span>
        </button>
        <button
          v-for="d in downloaderOptions"
          :key="d.value"
          type="button"
          class="m-picker-item"
          :disabled="pickerBusy"
          @click="onPickerDownloader(d.value)"
        >
          <span>{{ d.label }}</span>
          <span class="m-picker-item-desc">
            {{ pickerMode === 'tracker' ? '对该下载器全部种子批量添加/修改 Tracker' : '对该下载器的所有种子重新汇报 Tracker' }}
          </span>
        </button>
        <div v-if="pickerBusy" class="m-picker-busy"><i class="el-icon-loading" /> 正在获取种子列表…</div>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Mixins, Watch } from 'vue-property-decorator'
import {
  getTorrentList,
  getTrackerDomains,
  getActiveTorrents,
  getDuplicateTorrents,
  reconcileRuntimeTorrentStates,
  pauseTorrents,
  resumeTorrents,
  deleteTorrentsWithLevel,
  reannounceByDownloader,
  reannounceAll,
  Torrent
} from '@/api/torrents'
import type { DownloaderSimple } from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'
import { isCapabilityAvailable } from '@/api/platform-capabilities'
import { extractErrorMessage, formatSpeed, normalizeTorrent, normalizeTorrentStatus } from '@/utils/formatters'
import SpeedPollingMixin from '@/views/torrents/mixins/speedPolling'
import {
  buildSpeedSnapshot,
  collectRuntimeStateReconcileCandidates,
  RuntimeListMembershipTracker
} from '@/views/torrents/utils/torrentBatch'
import type { SpeedUpdate } from '@/views/torrents/utils/torrentBatch'
import {
  buildTorrentSpeedTargetIndex,
  resolveTorrentSpeedTargets
} from '@/views/torrents/utils/traditionalTorrentIdentity'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import { WindowInfiniteScroll } from '@/views/mobile/mixins/window-infinite-scroll'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import MobileDeleteLevelDialog from '@/views/mobile/components/DeleteLevelDialog.vue'
import QuickDeleteDuplicatesDialog from '@/components/torrents/QuickDeleteDuplicatesDialog.vue'
import { DELETE_LEVEL_SUCCESS_TEXT } from '@/views/mobile/delete-level'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import type { TrackerScopeDownloader } from '@/views/torrents/components/TrackerOperationDialog.vue'
import {
  TORRENT_STATUS_OPTIONS,
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

const PAGE_SIZE = 20
/** 返回顶部浮标显示阈值（滚动容器 scrollTop） */
const BACK_TOP_THRESHOLD_PX = 600

/**
 * 列表数据源模式（快捷操作切换，三模式互斥、normal 为常规 getList）：
 * duplicates 走 POST /torrents/duplicates（1-based page/pageSize 分页），
 * same-content/single-errors 走 getList 的 same_content_only/single_error_only
 * 过滤参数——与桌面 index.vue 快捷操作同语义。
 */
type MobileTorrentListMode = 'normal' | 'duplicates' | 'same-content' | 'single-errors'

interface SelectOption {
  label: string
  value: string
}

/**
 * 移动种子卡片列表（Phase 4 M1）：复用 getList API 与常用操作（暂停/恢复/四级删除）；
 * 卡片点击进入详情页（快照缓存传递整行数据）；顶部下拉刷新。
 * 简单搜索自移动高级搜索页迁入（与桌面 torrents 快捷筛选同字段集）；移动端查询模板页
 * 已裁撤（仅保留高级搜索），本页不再承接模板应用回填（跨页缓存链路随之移除）。
 *
 * 2026-08-28 UX 增强：卡片实时速度行（SpeedPollingMixin 10s 省电轮询 +
 * visibilitychange 后台暂停，复用桌面 buildSpeedSnapshot 合并状态与完成证据，未命中行清零防冻结）；
 * 无限滚动 + 返回顶部浮标（2026-09-05 无限滚动改 WindowInfiniteScroll mixin 以 window
 * 驱动——Element 指令被从不内滚的 .mobile-content 误判恒在底部，页面打开自动连发
 * 请求拉满 total）；暂停/恢复乐观状态
 * 更新（active 轮询包含 status/完成证据）；空状态 CTA（无下载器→去添加，零种子→桌面版引导）。
 *
 * 2026-09-05：删除改走四级（DeleteLevelDialog 与桌面删除下拉同语义：4 标记待删除/
 * 3 回收站/2 删任务保数据/1 完全删除，等级1 error 级二次确认），复用 deleteTorrentsWithLevel。
 *
 * 2026-09-12：卡片补辅种数量（>1 主题色强调）与单种转移（能力矩阵 fail-closed）/
 * 修改路径（复用桌面 TransferDialog/SetLocationDialog）；快捷操作补全局组——
 * 添加种子/Tracker操作/Tracker汇报/全局替换（Tracker操作与汇报移动端无多选，
 * 改为先选下载器再执行：汇报走 reannounce-by-downloader/reannounce-all；操作
 * 走 by-downloader 端点由服务端解析该下载器全部种子（无种子列表 URL 上限），
 * 弹窗经 scopeDownloader 进入按下载器触发模式，limit:1 轻取 total 作范围计数）。
 */
@Component({
  name: 'MobileTorrents',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    'm-delete-level-dialog': MobileDeleteLevelDialog,
    'quick-delete-duplicates-dialog': QuickDeleteDuplicatesDialog,
    // 桌面种子操作弹窗按需懒加载（路由包体不随弹窗集合膨胀）
    'transfer-dialog': () => import('@/views/torrents/components/TransferDialog.vue'),
    'set-location-dialog': () => import('@/views/torrents/components/SetLocationDialog.vue'),
    'torrent-add-dialog': () => import('@/views/torrents/components/TorrentAddDialog.vue'),
    'tracker-operation-dialog': () => import('@/views/torrents/components/TrackerOperationDialog.vue'),
    'global-replace-tracker-dialog': () => import('@/views/torrents/components/GlobalReplaceTrackerDialog.vue')
  }
})
export default class MobileTorrents extends Mixins(PullToRefresh, SpeedPollingMixin, WindowInfiniteScroll) {
  private list: Torrent[] = []
  private total = 0
  private loading = false
  private busyKey = ''
  private filtersExpanded = false
  private optionsLoaded = false
  private showBackTop = false
  /** 四级删除对话框：目标行与可见性（confirm 由 DeleteLevelDialog 二次确认后回调） */
  private deleteDialogVisible = false
  private deleteTarget: Torrent | null = null
  /** 快捷删除重复种子弹窗可见性（自包含组件，自行拉取启用中的下载器） */
  private quickDeleteVisible = false
  /** 列表数据源模式（快捷操作切换；reload/fetchPage 按模式分发数据源） */
  private listMode: MobileTorrentListMode = 'normal'
  /** 单种转移弹窗（与桌面详情同款 TransferDialog） */
  private transferVisible = false
  private transferTarget: Torrent | null = null
  /** 单种修改路径弹窗（桌面 SetLocationDialog 的 torrents=[单行] 形态） */
  private setLocationVisible = false
  private setLocationTarget: Torrent | null = null
  /** 添加种子弹窗（桌面 TorrentAddDialog，需要下载器原始行） */
  private addDialogVisible = false
  /** Tracker操作弹窗（先选下载器，按下载器触发——服务端解析该下载器全部种子） */
  private trackerOperationVisible = false
  private trackerOperationScope: TrackerScopeDownloader | null = null
  /** 全局替换 Tracker 弹窗（桌面同款自包含） */
  private globalReplaceVisible = false
  /** 下载器选择器（Tracker操作/汇报的范围入口） */
  private pickerVisible = false
  private pickerMode: 'tracker' | 'reannounce' = 'tracker'
  private pickerBusy = false
  /** 下载器原始行（downloader_id/nickname，喂给 TorrentAddDialog 的 downloaders prop） */
  private downloaderRawList: DownloaderSimple[] = []
  private filters = {
    name: '',
    downloaders: [] as string[],
    statuses: [] as string[],
    trackerDomains: [] as string[]
  }
  private downloaderOptions: SelectOption[] = []
  private trackerDomainOptions: string[] = []
  /** tracker 域名候选懒加载状态（失败不清 loaded 标记，下次展开自然重试） */
  private trackerDomainsLoaded = false
  private trackerDomainsLoading = false
  private runtimeStateMisses: Record<string, number> = {}
  private runtimeStateReconcileInFlight = false
  private runtimeListMembership = new RuntimeListMembershipTracker()
  /** 已触发过终态整页刷新的种子 hash：库内状态滞后时同一种子每轮轮询都会带回
   * downloadComplete 证据，不去重会在 downloading 筛选下形成 10s reload 循环 */
  private terminalReloadedHashes = new Set<string>()

  private TORRENT_STATUS_OPTIONS = TORRENT_STATUS_OPTIONS

  /** 移动端速度轮询节奏（桌面 1s 的省电版；mixin 默认值覆写） */
  protected speedPollIntervalMs = 10000

  mounted(): void {
    // 下载器选项 mount 即拉（纯 DB 轻查询，空态判断需要区分"没有下载器"）；
    // tracker 域名候选懒加载——后端是 TrackerInfo 全表扫描，仅在用户展开筛选
    // 面板时才值得付出（配合后端 TTL 缓存，多客户端挂载不再放大全表扫描）
    this.loadDownloaderOptions()
    this.reload()
    // 实际滚动容器是 window（.mobile-layout min-height:100vh 会被长列表撑高，
    // .mobile-content 不产生内部滚动——2026-08-28 模拟器实测 scrollHeight==clientHeight）
    window.addEventListener('scroll', this.onListScroll, { passive: true })
    this.startSpeedPolling(false)
  }

  beforeDestroy(): void {
    this.stopSpeedPolling()
    window.removeEventListener('scroll', this.onListScroll)
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
  }

  private applySpeedUpdates(updates: SpeedUpdate[]): boolean {
    const index = buildTorrentSpeedTargetIndex(this.list)
    let terminalObserved = false
    updates.forEach(update => {
      resolveTorrentSpeedTargets(index, update).forEach(row => {
        row.downloadSpeed = update.downloadSpeed
        row.uploadSpeed = update.uploadSpeed
        row.progress = update.downloadComplete ? 100 : update.progress
        if (update.status) {
          row.status = normalizeTorrentStatus(update.status, update.status)
        }
        if (update.downloadComplete) {
          row.downloadComplete = true
          terminalObserved = true
        }
      })
    })
    return terminalObserved
  }

  private async reconcileRuntimeStates(
    candidates: Array<{ downloader_id: string, hash: string }>
  ): Promise<boolean> {
    if (!candidates.length || this.runtimeStateReconcileInFlight) return false
    this.runtimeStateReconcileInFlight = true
    try {
      const response = await reconcileRuntimeTorrentStates(candidates)
      const data = response.code === '200' && response.data
        ? response.data
        : null
      if (!data || !Array.isArray(data.list)) return false
      const snapshot = buildSpeedSnapshot({
        status: response.status,
        msg: response.msg,
        code: '200',
        data: data.list
      })
      this.applySpeedUpdates(snapshot.updates)
      if (this.shouldReloadForTerminal(snapshot.updates)) {
        await this.reload()
      }
      return true
    } catch {
      return false
    } finally {
      this.runtimeStateReconcileInFlight = false
    }
  }

  /**
   * downloading 筛选下的终态整页刷新判定：仅“新出现”的完成种子触发一次。
   * 库内状态未收敛时（同步任务滞后），reload 会把 DB 仍标下载中的完成行拉回
   * 列表，下一轮轮询又带回 downloadComplete——按 hash 去重斩断该循环；筛选
   * 条件变化时清空（runFilters/resetFilters），重新建立终态处理上下文。
   */
  private shouldReloadForTerminal(updates: SpeedUpdate[]): boolean {
    if (!this.filters.statuses.includes('downloading')) return false
    const newHashes = updates
      .filter(update => update.downloadComplete)
      .map(update => update.hash)
      .filter(hash => Boolean(hash) && !this.terminalReloadedHashes.has(hash))
    if (!newHashes.length) return false
    newHashes.forEach(hash => this.terminalReloadedHashes.add(hash))
    return true
  }

  /** SpeedPollingMixin 轮询体：拉活跃速度并就地合并进列表行（桌面同款纯函数工具） */
  protected async loadActiveSpeed(): Promise<boolean> {
    try {
      const res = await getActiveTorrents()
      const snapshot = buildSpeedSnapshot(res)
      if (!snapshot.ready && !snapshot.partial) return false
      const newlyUnlistedKeys = this.runtimeListMembership.observe(
        this.list,
        snapshot.updates,
        snapshot.ready
      )
      this.applySpeedUpdates(snapshot.updates)
      if (newlyUnlistedKeys.length > 0) {
        // eslint-disable-next-line @typescript-eslint/no-this-alias
        const component = this
        await component.runtimeListMembership.refresh(
          () => component.list,
          snapshot.updates,
          () => component.reload(),
          updates => component.applySpeedUpdates(updates)
        )
      }
      const activeKeys = new Set<string>()
      const currentIndex = buildTorrentSpeedTargetIndex(this.list)
      snapshot.updates.forEach(update => {
        resolveTorrentSpeedTargets(currentIndex, update).forEach(row => activeKeys.add(this.keyOf(row)))
      })
      // 206 只覆盖成功下载器，不能清掉其它下载器上一轮的速度；完整快照才允许清零未命中行。
      if (snapshot.ready) {
        this.list.forEach(row => {
          if (!activeKeys.has(this.keyOf(row))) {
            row.downloadSpeed = 0
            row.uploadSpeed = 0
          }
        })
        const reconcile = collectRuntimeStateReconcileCandidates(
          this.list,
          snapshot.updates,
          this.runtimeStateMisses
        )
        this.runtimeStateMisses = reconcile.misses
        if (reconcile.candidates.length) {
          await this.reconcileRuntimeStates(reconcile.candidates)
        }
      }
      if (this.shouldReloadForTerminal(snapshot.updates)) {
        await this.reload()
      }
      return snapshot.ready
    } catch {
      return false
    }
  }

  protected get infiniteDisabled(): boolean {
    return this.loading || this.list.length >= this.total
  }

  // 注意：必须用方法而非箭头函数类字段——vue-class-component 收集 data 时
  // new 一次类即丢弃，箭头字段的 this 指向被丢弃的收集实例，写 this 数据
  // 会静默失效（2026-08-28 视觉验证抓出：浮标因此永不显示）
  private onListScroll(): void {
    const top = window.scrollY || document.documentElement.scrollTop
    this.showBackTop = top > BACK_TOP_THRESHOLD_PX
  }

  private scrollToTop(): void {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  private get hasFilters(): boolean {
    return Boolean(
      this.filters.name ||
        this.filters.downloaders.length ||
        this.filters.statuses.length ||
        this.filters.trackerDomains.length
    )
  }

  private get activeFilterCount(): number {
    let count = 0
    if (this.filters.name) count += 1
    count += this.filters.downloaders.length ? 1 : 0
    count += this.filters.statuses.length ? 1 : 0
    count += this.filters.trackerDomains.length ? 1 : 0
    return count
  }

  private async loadDownloaderOptions(): Promise<void> {
    try {
      const res = await getDownloaderList({ page: 1, pageSize: 100 })
      if (res.code === '200' && Array.isArray(res.data)) {
        // 后端 /downloader/getList 实际返回 downloader_id/nickname（DownloaderSimpleVO）；
        // 旧映射读 d.id 会让筛选值恒为 undefined，一并修正（兼容两字段名）
        this.downloaderRawList = (res.data as Array<{
          downloader_id?: string
          id?: string
          nickname?: string | null
        }>).map(d => ({
          downloader_id: String(d.downloader_id ?? d.id ?? ''),
          nickname: String(d.nickname || d.downloader_id || d.id || '')
        }))
        this.downloaderOptions = this.downloaderRawList.map(d => ({
          label: d.nickname,
          value: d.downloader_id
        }))
      }
    } catch {
      // 选项加载失败不阻塞列表（空态判断退化为"暂无种子"）
    } finally {
      this.optionsLoaded = true
    }
  }

  /** 首次展开筛选面板时拉取 tracker 域名候选（页内缓存；失败下次展开重试） */
  private async ensureTrackerDomainOptions(): Promise<void> {
    if (this.trackerDomainsLoaded || this.trackerDomainsLoading) return
    this.trackerDomainsLoading = true
    try {
      const res = await getTrackerDomains()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.trackerDomainOptions = res.data
        this.trackerDomainsLoaded = true
      }
    } catch {
      // 选项加载失败不阻塞手输条件
    } finally {
      this.trackerDomainsLoading = false
    }
  }

  @Watch('filtersExpanded')
  private onFiltersExpandedChange(expanded: boolean): void {
    if (expanded) {
      this.ensureTrackerDomainOptions()
    }
  }

  // ============ 简单搜索（迁入） ============

  private async runFilters(): Promise<void> {
    // 筛选上下文变化：重置终态刷新去重（重新建立 downloading 终态处理）
    this.terminalReloadedHashes.clear()
    await this.reload()
  }

  private async resetFilters(): Promise<void> {
    this.filters = {
      name: '',
      downloaders: [],
      statuses: [],
      trackerDomains: []
    }
    this.terminalReloadedHashes.clear()
    await this.reload()
  }

  private async reload(): Promise<void> {
    this.runtimeStateMisses = {}
    // 原子替换（replace）：刷新期间保留旧列表渲染，消除整列塌陷闪烁与滚动跳顶
    await this.fetchPage(true)
  }

  /** WindowInfiniteScroll 子类实现：追加下一页（门禁由 maybeLoadMore 与 fetchPage 的 loading 承担） */
  protected async loadMore(): Promise<void> {
    await this.fetchPage()
  }

  private async fetchPage(replace = false): Promise<void> {
    // 查重模式走独立端点（1-based page/pageSize 分页），其余模式（含排查过滤）走 getList
    if (this.listMode === 'duplicates') {
      await this.fetchDuplicatePage(replace)
      return
    }
    this.loading = true
    try {
      const res = await getTorrentList({
        skip: replace ? 0 : this.list.length,
        limit: PAGE_SIZE,
        sort_by: 'added_date',
        sort_order: 'desc',
        // 卡片不展示 tracker 明细：跳过后端批量预取与序列化（详情页 refreshBase
        // 全量回查补齐 tracker 明细，快照短暂缺省属可接受）
        with_trackers: false,
        ...(this.listMode === 'same-content' ? { same_content_only: true } : {}),
        ...(this.listMode === 'single-errors' ? { single_error_only: true } : {}),
        ...(this.filters.name ? { name_like: this.filters.name } : {}),
        ...(this.filters.downloaders.length ? { downloader_id: this.filters.downloaders } : {}),
        ...(this.filters.statuses.length ? { status: this.filters.statuses } : {}),
        ...(this.filters.trackerDomains.length ? { tracker_domain: this.filters.trackerDomains } : {})
      })
      if (res.code === '200' && res.data) {
        const pageList = res.data.list ?? []
        this.list = replace ? pageList : this.list.concat(pageList)
        this.total = res.data.total ?? 0
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
      // 每页完成后检查：内容仍不足一屏时主动补页（window 滚动驱动，无指令观察器）
      this.maybeLoadMore()
    }
  }

  /** duplicates 模式分页体：skip/limit（getList 口径）换算为 1-based page/pageSize */
  private async fetchDuplicatePage(replace: boolean): Promise<void> {
    this.loading = true
    try {
      const res = await getDuplicateTorrents({
        page: replace ? 1 : Math.floor(this.list.length / PAGE_SIZE) + 1,
        pageSize: PAGE_SIZE,
        sort_by: 'added_date',
        sort_order: 'desc',
        ...(this.filters.name ? { name_like: this.filters.name } : {}),
        ...(this.filters.downloaders.length ? { downloader_id: this.filters.downloaders.join(',') } : {}),
        ...(this.filters.statuses.length ? { status: this.filters.statuses.join(',') } : {})
      })
      if (res.code === '200' && res.data) {
        const pageList = (res.data.list ?? []).map(normalizeTorrent)
        this.list = replace ? pageList : this.list.concat(pageList)
        this.total = res.data.total ?? 0
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
      this.maybeLoadMore()
    }
  }

  // ============ 快捷操作（与桌面 index.vue 同语义四项） ============

  private get modeNoun(): string {
    switch (this.listMode) {
      case 'duplicates':
        return '重复种子'
      case 'same-content':
        return '同内容种子'
      case 'single-errors':
        return '错误单种'
      default:
        return ''
    }
  }

  private async handleQuickActionCommand(command: string): Promise<void> {
    // 全局操作组：打开弹窗/选择器，不改列表数据源（不重置终态刷新去重上下文）
    if (command === 'add-torrent') {
      if (this.downloaderRawList.length === 0) {
        this.$message.warning('暂无启用中的下载器，请先添加下载器')
        return
      }
      this.addDialogVisible = true
      return
    }
    if (command === 'tracker-operation') {
      this.openDownloaderPicker('tracker')
      return
    }
    if (command === 'tracker-reannounce') {
      this.openDownloaderPicker('reannounce')
      return
    }
    if (command === 'global-replace') {
      this.globalReplaceVisible = true
      return
    }
    // 模式切换等效换筛选：重置终态刷新去重
    this.terminalReloadedHashes.clear()
    if (command === 'delete-duplicates') {
      this.quickDeleteVisible = true
      return
    }
    const modeByCommand: Record<string, MobileTorrentListMode> = {
      'toggle-duplicates': 'duplicates',
      'inspect-same-content': 'same-content',
      'inspect-single-errors': 'single-errors'
    }
    const next = modeByCommand[command]
    if (!next) return
    // 再点当前模式 = 退出（三模式互斥，切换即退出旧模式）
    this.listMode = this.listMode === next ? 'normal' : next
    await this.reload()
    if (this.listMode !== 'normal') {
      const prefix = this.listMode === 'duplicates' ? '查找完成，共找到' : '排查完成，共找到'
      this.$message.success(`${prefix} ${this.total} 条${this.modeNoun}`)
    }
  }

  private async exitListMode(): Promise<void> {
    if (this.listMode === 'normal') return
    this.terminalReloadedHashes.clear()
    this.listMode = 'normal'
    await this.reload()
  }

  /** 快捷删重完成回调：刷新当前模式列表（查重模式下重取去重结果） */
  private async onQuickDeleted(): Promise<void> {
    await this.reload()
  }

  /** 卡片点击：快照缓存整行（详情页含 trackerInfo 的数据源），带复合键进详情 */
  private openDetail(t: Torrent): void {
    setCachedTorrent(t)
    this.$router
      .push(`/m/torrents/detail/${encodeURIComponent(t.downloaderId)}/${encodeURIComponent(t.hash)}`)
      .catch(() => undefined)
  }

  private actionBusy(t: Torrent): boolean {
    return this.busyKey === this.keyOf(t)
  }

  private keyOf(t: Torrent): string {
    return `${t.downloaderId || t.downloader_id || ''}-${t.hash}`
  }

  private async pause(t: Torrent): Promise<void> {
    await this.withBusy(t, () => pauseTorrents({ downloader_id: t.downloaderId, hashes: [t.hash] }), 'paused')
  }

  private async resume(t: Torrent): Promise<void> {
    await this.withBusy(t, () => resumeTorrents({ downloader_id: t.downloaderId, hashes: [t.hash] }), 'downloading')
  }

  private remove(t: Torrent): void {
    this.deleteTarget = t
    this.deleteDialogVisible = true
  }

  // ============ 单种转移/修改路径（复用桌面弹窗） ============

  private get seedTransferAvailable(): boolean {
    // android-server 等无下载器主机文件系统的形态 fail-closed 隐藏入口
    return isCapabilityAvailable('seed_transfer')
  }

  /** normalizeTorrent 补齐 camelCase 字段（TransferDialog/SetLocationDialog 读取
   * downloaderId/savePath/infoId；normal 模式列表行是后端蛇形原始行） */
  private openTransfer(t: Torrent): void {
    this.transferTarget = normalizeTorrent(t) as Torrent
    this.transferVisible = true
  }

  private openSetLocation(t: Torrent): void {
    this.setLocationTarget = normalizeTorrent(t) as Torrent
    this.setLocationVisible = true
  }

  private get setLocationTorrents(): Torrent[] {
    return this.setLocationTarget ? [this.setLocationTarget] : []
  }

  /** 桌面弹窗 @success 统一刷新（弹窗自带成功提示，这里只拉新列表） */
  private async onTorrentMutated(): Promise<void> {
    await this.reload()
  }

  // ============ 快捷操作全局组（先选下载器的批量语义） ============

  private openDownloaderPicker(mode: 'tracker' | 'reannounce'): void {
    if (this.downloaderOptions.length === 0) {
      this.$message.warning('暂无启用中的下载器')
      return
    }
    this.pickerMode = mode
    this.pickerVisible = true
  }

  private async onPickerDownloader(downloaderId: string): Promise<void> {
    if (this.pickerMode === 'reannounce') {
      this.pickerVisible = false
      await this.confirmAndReannounce(downloaderId)
      return
    }
    await this.openTrackerOperationByDownloader(downloaderId)
  }

  /** Tracker汇报：空 id = 全部下载器（reannounce-all），否则按下载器（reannounce-by-downloader） */
  private async confirmAndReannounce(downloaderId: string): Promise<void> {
    const scopeText = downloaderId
      ? `下载器「${this.downloaderLabelOf(downloaderId)}」的全部种子`
      : '全部下载器的全部种子'
    try {
      await this.$confirm(`确定对${scopeText}重新汇报 Tracker？`, 'Tracker汇报确认', {
        confirmButtonText: '汇报',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch {
      return
    }
    try {
      const res = downloaderId
        ? await reannounceByDownloader(downloaderId)
        : await reannounceAll()
      if (res.code === '200' && res.data) {
        const ok = res.data.success_count
        const fail = res.data.failed_count
        const suffix = typeof ok === 'number'
          ? `（成功 ${ok}${typeof fail === 'number' && fail > 0 ? `，失败 ${fail}` : ''}）`
          : ''
        this.$message.success(`Tracker汇报完成${suffix}`)
      } else {
        this.$message.error(res.msg || 'Tracker汇报失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  /**
   * Tracker操作（先选下载器→按下载器触发）：不再前端拉种子列表（旧口径受
   * torrentInfoIds Query 参数 URL 长度上限约束），改调 by-downloader 端点由
   * 服务端解析该下载器全部种子；此处仅轻量取 total（limit:1）作范围计数展示。
   */
  private async openTrackerOperationByDownloader(downloaderId: string): Promise<void> {
    this.pickerBusy = true
    let total: number | undefined
    try {
      const res = await getTorrentList({
        skip: 0,
        limit: 1,
        downloader_id: [downloaderId],
        with_trackers: false
      })
      if (res.code === '200' && res.data) {
        total = res.data.total ?? 0
      }
    } catch {
      // 计数失败不阻塞操作（弹窗范围行省略计数）
    } finally {
      this.pickerBusy = false
    }
    if (total === 0) {
      this.pickerVisible = false
      this.$message.info('该下载器暂无种子')
      return
    }
    this.trackerOperationScope = {
      id: downloaderId,
      name: this.downloaderLabelOf(downloaderId),
      ...(total !== undefined ? { total } : {})
    }
    this.pickerVisible = false
    this.trackerOperationVisible = true
  }

  private downloaderLabelOf(downloaderId: string): string {
    const hit = this.downloaderOptions.find(d => d.value === downloaderId)
    return hit ? hit.label : downloaderId
  }

  private get deleteTargetName(): string {
    return this.deleteTarget ? this.deleteTarget.name : ''
  }

  private get anyBusy(): boolean {
    return this.busyKey !== ''
  }

  /** DeleteLevelDialog 确认后的执行体：按等级调 delete-with-level，成功后整页刷新 */
  private async confirmDelete(level: number): Promise<void> {
    const target = this.deleteTarget
    if (!target) return
    this.busyKey = this.keyOf(target)
    try {
      const res = await deleteTorrentsWithLevel({
        torrent_info_ids: [target.infoId],
        delete_level: level
      })
      if (res && res.code && res.code !== '200') return
      this.$message.success(DELETE_LEVEL_SUCCESS_TEXT[level] || '删除完成')
      this.deleteTarget = null
      await this.reload()
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyKey = ''
    }
  }

  private async withBusy(
    t: Torrent,
    action: () => Promise<{ code?: string }>,
    nextStatus?: string
  ): Promise<void> {
    this.busyKey = this.keyOf(t)
    try {
      const res = await action()
      if (res && res.code && res.code !== '200') return
      // 乐观状态更新：实时快照也会带 status；操作成功后立即覆盖，避免等待下一轮轮询
      if (nextStatus) t.status = nextStatus
      this.$message.success('操作成功')
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyKey = ''
    }
  }

  private progressOf(t: Torrent): number {
    const value = typeof t.progress === 'number' ? t.progress : 0
    return Math.min(100, Math.max(0, value))
  }

  // ============ 实时速度展示（camel/snake 双兼容读取） ============

  private speedValue(t: Torrent, field: 'download' | 'upload'): number {
    const camel = field === 'download' ? t.downloadSpeed : t.uploadSpeed
    const snake = field === 'download' ? t.download_speed : t.upload_speed
    const value = camel ?? snake ?? 0
    return typeof value === 'number' ? value : 0
  }

  private hasLiveSpeed(t: Torrent): boolean {
    return this.speedValue(t, 'download') > 0 || this.speedValue(t, 'upload') > 0
  }

  private formatSpeedText(t: Torrent, field: 'download' | 'upload'): string {
    return formatSpeed(this.speedValue(t, field))
  }

  // ============ 空状态 CTA 导航 ============

  private goAddDownloader(): void {
    this.$router
      .replace('/m/downloader/settings/new')
      .catch(() => undefined)
  }

  private statusLabel(status: string): string {
    return torrentStatusLabel(status)
  }

  private statusTagType(status: string): string {
    return torrentStatusTagType(status)
  }

  private formatSize(bytes: number): string {
    return formatTorrentSize(bytes)
  }

  /** 辅种数量（与桌面列 {{ torrent.auxiliarySeedCount || 1 }} 同口径：非正数/缺失回退 1） */
  private auxiliarySeedCountOf(t: Torrent): number {
    const raw = t.auxiliarySeedCount ?? t.auxiliary_seed_count
    const value = typeof raw === 'number' ? raw : Number(raw)
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 1
  }
}
</script>

<style scoped>
.m-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.m-toolbar-filter {
  flex: 1;
}

/* 列表模式横幅（查重/排查激活时）：口径提示 + 结果数 + 一键退出 */
.m-mode-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px;
  margin-bottom: 10px;
  border-radius: 8px;
  background: rgba(5, 150, 105, 0.08);
  color: var(--color-primary, #059669);
}

.m-mode-banner-text {
  font-size: 13px;
  font-weight: 600;
}

.m-mode-banner-exit {
  color: var(--color-primary, #059669);
  font-weight: 600;
  padding: 4px 6px;
}

.m-torrents-filters {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.m-torrents-filter-actions {
  display: flex;
  gap: 8px;
}

.m-torrents-filter-actions .el-button {
  flex: 1;
  margin-left: 0;
}

.m-torrent-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  /* 长列表渲染减负：视口外卡片跳过布局/绘制（content-visibility，Chromium WebView
     支持）。contain-intrinsic-size 用实测平均卡片高度兜底估算，auto 前缀保留最近
     渲染尺寸——scrollHeight 估算偏差过大时会误导 window-infinite-scroll 的补页判定 */
  content-visibility: auto;
  contain-intrinsic-size: auto 148px;
}

.m-torrent-name {
  font-size: 14px;
  color: #303133;
  line-height: 1.35;
  max-height: 2.7em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}

.m-torrent-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
}

.m-torrent-meta-text {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 辅种数量：>1（存在同内容异 InfoHash 种子）时主题色强调 */
.m-torrent-aux-hot {
  color: var(--color-primary, #059669);
  font-weight: 600;
}

.m-torrent-progress-text {
  margin-top: 2px;
  font-size: 11px;
  color: #c0c4cc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 实时速度行：min-width 防速度文本宽度变化引起卡片抖动 */
.m-torrent-speed {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}

.m-torrent-speed-item {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary);
  min-width: 72px;
}

.m-torrent-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.m-torrent-actions .el-button {
  margin-left: 0;
  padding: 5px 10px;
}

/* 无限滚动尾部非交互计数/加载提示（替代旧"加载更多"按钮） */
.m-load-more-hint {
  text-align: center;
  color: #909399;
  font-size: 12px;
  padding: 10px 0;
}

/* 返回顶部浮标：固定于悬浮 Tab 栏上方，避开安全区；玻璃底与 Tab 栏同源（theme-variables.scss --glass-*） */
.m-backtop {
  position: fixed;
  right: 16px;
  bottom: calc(80px + env(safe-area-inset-bottom));
  width: 40px;
  height: 40px;
  border: var(--glass-border, 1px solid rgba(255, 255, 255, 0.3));
  border-radius: var(--radius-lg, 12px);
  background: var(--glass-bg, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(var(--glass-blur, 12px));
  -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
  color: var(--color-primary);
  font-size: 18px;
  box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06));
  z-index: 9;
}

/* 降级条件用字面量（同 .mobile-tabbar 注释）；无前缀检测对 iOS ≤17 误降实色属保守取舍 */
@supports not (backdrop-filter: blur(12px)) {
  .m-backtop {
    background: var(--color-bg-primary, #FFFFFF);
    border: 1px solid var(--color-border-primary, #E5E7EB);
  }
}

/* 空状态引导（无下载器 CTA） */
.m-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 6px;
}

.m-empty-desc {
  font-size: 12px;
  color: #909399;
  margin-bottom: 12px;
}

.m-empty-cta {
  margin-top: 2px;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}

/* 下载器选择器：原生按钮触控行（≥44px），桌面弹窗体系外的轻量选择面 */
.m-picker-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.m-picker-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-height: 48px;
  padding: 8px 14px;
  border: 1px solid var(--color-border-primary, #e5e7eb);
  border-radius: 10px;
  background: var(--color-bg-secondary, #f9fafb);
  color: #303133;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.m-picker-item:active {
  background: rgba(5, 150, 105, 0.08);
}

.m-picker-item:disabled {
  opacity: 0.6;
}

.m-picker-item-desc {
  font-size: 12px;
  color: #909399;
}

.m-picker-busy {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 2px;
  font-size: 13px;
  color: #909399;
}
</style>

<style lang="scss">
/* 复用的桌面弹窗（未 append-to-body，渲染在本页 DOM 内）：custom-class 打标后
   仅 ≤768 收窄。类名本页专属，chunk 常驻也不会命中其它页面弹窗。
   宽度 prop 生成内联 style，须 !important 覆盖；长内容（Tracker操作种子标签列表）
   限制弹窗体高度内滚。 */
@media (max-width: 768px) {
  .m-reuse-dialog {
    width: 94vw !important;
    margin-top: 5vh !important;

    .el-dialog__body {
      max-height: 64vh;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }
  }

  .m-downloader-picker {
    width: 88vw !important;
    max-width: 360px;
    margin-top: 20vh !important;
  }
}
</style>
