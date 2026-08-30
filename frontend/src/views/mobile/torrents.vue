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
      <template v-if="hasFilters">没有匹配的种子</template>
      <template v-else-if="optionsLoaded && downloaderOptions.length === 0">
        <div class="m-empty-title">还没有种子</div>
        <div class="m-empty-desc">先添加下载器，同步后即可在这里管理种子</div>
        <el-button size="small" type="primary" plain class="m-empty-cta" @click="goAddDownloader">
          去添加下载器
        </el-button>
      </template>
      <template v-else-if="optionsLoaded">
        暂无种子——去<el-button type="text" size="mini" class="m-empty-link" @click="goDesktopTorrents">桌面版</el-button>添加，或等待下载器同步
      </template>
      <template v-else>暂无种子</template>
    </div>

    <!-- 无限滚动：滚动容器为布局壳 .mobile-content（Element 指令自动上溯挂载）；
         尾部计数提示非交互（替代旧"加载更多"按钮） -->
    <div
      v-infinite-scroll="loadMore"
      class="m-torrents-list"
      :infinite-scroll-disabled="infiniteDisabled"
      :infinite-scroll-distance="60"
    >
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
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getTorrentList,
  getTrackerDomains,
  getActiveTorrents,
  reconcileRuntimeTorrentStates,
  pauseTorrents,
  resumeTorrents,
  deleteTorrents,
  Torrent
} from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'
import { extractErrorMessage, formatSpeed, normalizeTorrentStatus } from '@/utils/formatters'
import { setStoredUiMode } from '@/utils/ui-mode'
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
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  TORRENT_STATUS_OPTIONS,
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

const PAGE_SIZE = 20
/** 返回顶部浮标显示阈值（滚动容器 scrollTop） */
const BACK_TOP_THRESHOLD_PX = 600

interface SelectOption {
  label: string
  value: string
}

/**
 * 移动种子卡片列表（Phase 4 M1）：复用 getList API 与常用操作（暂停/恢复/删除入回收站）；
 * 卡片点击进入详情页（快照缓存传递整行数据）；顶部下拉刷新。
 * 简单搜索自移动高级搜索页迁入（与桌面 torrents 快捷筛选同字段集）；移动端查询模板页
 * 已裁撤（仅保留高级搜索），本页不再承接模板应用回填（跨页缓存链路随之移除）。
 *
 * 2026-08-28 UX 增强：卡片实时速度行（SpeedPollingMixin 10s 省电轮询 +
 * visibilitychange 后台暂停，复用桌面 buildSpeedSnapshot 合并状态与完成证据，未命中行清零防冻结）；
 * v-infinite-scroll 无限滚动替代"加载更多"按钮 + 返回顶部浮标；暂停/恢复乐观状态
 * 更新（active 轮询包含 status/完成证据）；空状态 CTA（无下载器→去添加，零种子→桌面版引导）。
 */
@Component({
  name: 'MobileTorrents',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileTorrents extends Mixins(PullToRefresh, SpeedPollingMixin) {
  private list: Torrent[] = []
  private total = 0
  private loading = false
  private busyKey = ''
  private filtersExpanded = false
  private optionsLoaded = false
  private showBackTop = false
  private filters = {
    name: '',
    downloaders: [] as string[],
    statuses: [] as string[],
    trackerDomains: [] as string[]
  }
  private downloaderOptions: SelectOption[] = []
  private trackerDomainOptions: string[] = []
  private runtimeStateMisses: Record<string, number> = {}
  private runtimeStateReconcileInFlight = false
  private runtimeListMembership = new RuntimeListMembershipTracker()

  private TORRENT_STATUS_OPTIONS = TORRENT_STATUS_OPTIONS

  /** 移动端速度轮询节奏（桌面 1s 的省电版；mixin 默认值覆写） */
  protected speedPollIntervalMs = 10000

  mounted(): void {
    this.loadFilterOptions()
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
      const terminalObserved = this.applySpeedUpdates(snapshot.updates)
      if (terminalObserved && this.filters.statuses.includes('downloading')) {
        await this.reload()
      }
      return true
    } catch {
      return false
    } finally {
      this.runtimeStateReconcileInFlight = false
    }
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
      let terminalObserved = this.applySpeedUpdates(snapshot.updates)
      if (newlyUnlistedKeys.length > 0) {
        // eslint-disable-next-line @typescript-eslint/no-this-alias
        const component = this
        terminalObserved = (await component.runtimeListMembership.refresh(
          () => component.list,
          snapshot.updates,
          () => component.reload(),
          updates => component.applySpeedUpdates(updates)
        )) || terminalObserved
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
      if (terminalObserved && this.filters.statuses.includes('downloading')) {
        await this.reload()
      }
      return snapshot.ready
    } catch {
      return false
    }
  }

  private get infiniteDisabled(): boolean {
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

  private async loadFilterOptions(): Promise<void> {
    try {
      const [dlRes, domainRes] = await Promise.all([
        getDownloaderList({ page: 1, pageSize: 100 }),
        getTrackerDomains()
      ])
      if (dlRes.code === '200' && Array.isArray(dlRes.data)) {
        this.downloaderOptions = dlRes.data.map(
          (d: { id: string, nickname?: string | null }) => ({
            label: String(d.nickname || d.id),
            value: d.id
          })
        )
      }
      if (domainRes.code === '200' && Array.isArray(domainRes.data)) {
        this.trackerDomainOptions = domainRes.data
      }
    } catch {
      // 选项加载失败不阻塞手输条件
    } finally {
      this.optionsLoaded = true
    }
  }

  // ============ 简单搜索（迁入） ============

  private async runFilters(): Promise<void> {
    await this.reload()
  }

  private async resetFilters(): Promise<void> {
    this.filters = {
      name: '',
      downloaders: [],
      statuses: [],
      trackerDomains: []
    }
    await this.reload()
  }

  private async reload(): Promise<void> {
    this.list = []
    this.total = 0
    this.runtimeStateMisses = {}
    await this.fetchPage()
  }

  private async loadMore(): Promise<void> {
    await this.fetchPage()
  }

  private async fetchPage(): Promise<void> {
    this.loading = true
    try {
      const res = await getTorrentList({
        skip: this.list.length,
        limit: PAGE_SIZE,
        sort_by: 'added_date',
        sort_order: 'desc',
        ...(this.filters.name ? { name_like: this.filters.name } : {}),
        ...(this.filters.downloaders.length ? { downloader_id: this.filters.downloaders } : {}),
        ...(this.filters.statuses.length ? { status: this.filters.statuses } : {}),
        ...(this.filters.trackerDomains.length ? { tracker_domain: this.filters.trackerDomains } : {})
      })
      if (res.code === '200' && res.data) {
        this.list = this.list.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
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
    this.$confirm(`删除种子「${t.name}」？文件移入回收站，可从回收站恢复。`, '删除确认', { type: 'warning' })
      .then(async() => {
        await this.withBusy(t, () =>
          deleteTorrents({
            info_id: t.infoId,
            downloader_id: t.downloaderId,
            delete_data: 0,
            id_recycle: 1
          })
        )
        await this.reload()
      })
      .catch(() => undefined)
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
      .replace({ path: '/m/downloader', query: { create: '1' } })
      .catch(() => undefined)
  }

  private goDesktopTorrents(): void {
    setStoredUiMode('desktop')
    this.$router.replace('/torrents').catch(() => undefined)
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

.m-empty-link {
  padding: 0 2px;
  font-size: 12px;
  vertical-align: baseline;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
