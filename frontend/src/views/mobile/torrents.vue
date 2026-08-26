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

    <div v-if="appliedTip" class="m-torrents-applied">{{ appliedTip }}</div>
    <div v-if="!loading && list.length === 0" class="m-hint">{{ hasFilters ? '没有匹配的种子' : '暂无种子' }}</div>

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
      <div class="m-torrent-actions" @click.stop>
        <el-button size="mini" :disabled="actionBusy(t)" @click="pause(t)">暂停</el-button>
        <el-button size="mini" :disabled="actionBusy(t)" @click="resume(t)">恢复</el-button>
        <el-button size="mini" type="danger" plain :disabled="actionBusy(t)" @click="remove(t)">删除</el-button>
      </div>
    </div>

    <el-button
      v-if="list.length < total"
      class="m-load-more"
      size="small"
      :loading="loading"
      @click="loadMore"
    >
      加载更多（{{ list.length }}/{{ total }}）
    </el-button>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getTorrentList,
  getTrackerDomains,
  pauseTorrents,
  resumeTorrents,
  deleteTorrents,
  Torrent
} from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  takeAppliedTemplateConditions,
  setAppliedTemplateConditions
} from '@/views/mobile/m2-template-cache'
import {
  TORRENT_STATUS_OPTIONS,
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

const PAGE_SIZE = 20

interface SelectOption {
  label: string
  value: string
}

/**
 * 移动种子卡片列表（Phase 4 M1）：复用 getList API 与常用操作（暂停/恢复/删除入回收站）；
 * 卡片点击进入详情页（快照缓存传递整行数据）；顶部下拉刷新。
 * 简单搜索自移动高级搜索页迁入（与桌面 torrents 快捷筛选同字段集）；查询模板页
 * 「应用」简单模板经 m2-template-cache 进入本页自动回填筛选并执行（高级模板转回 /m/search）。
 */
@Component({
  name: 'MobileTorrents',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileTorrents extends Mixins(PullToRefresh) {
  private list: Torrent[] = []
  private total = 0
  private loading = false
  private busyKey = ''
  private filtersExpanded = false
  private appliedTip = ''
  private filters = {
    name: '',
    downloaders: [] as string[],
    statuses: [] as string[],
    trackerDomains: [] as string[]
  }
  private downloaderOptions: SelectOption[] = []
  private trackerDomainOptions: string[] = []

  private TORRENT_STATUS_OPTIONS = TORRENT_STATUS_OPTIONS

  mounted(): void {
    this.loadFilterOptions()
    this.applyPendingTemplate()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
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

  // ============ 模板应用（查询模板页跳转进入） ============

  private async applyPendingTemplate(): Promise<void> {
    const pending = takeAppliedTemplateConditions()
    if (!pending) {
      await this.reload()
      return
    }
    const { conditions, templateName } = pending
    if (conditions.source !== 'simple') {
      // 高级模板交回缓存并转高级搜索页执行
      setAppliedTemplateConditions(conditions, templateName)
      this.$router.push('/m/search').catch(() => undefined)
      return
    }
    const lq = conditions.listQuery ?? {}
    this.filters = {
      name: lq.name_like ?? '',
      downloaders: Array.isArray(lq.downloader_id) ? [...lq.downloader_id] : [],
      statuses: Array.isArray(lq.status) ? [...lq.status] : [],
      trackerDomains: []
    }
    this.filtersExpanded = true
    this.appliedTip = `已应用模板「${templateName}」`
    await this.reload()
  }

  private async reload(): Promise<void> {
    this.list = []
    this.total = 0
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
    return `${t.downloaderId}-${t.hash}`
  }

  private async pause(t: Torrent): Promise<void> {
    await this.withBusy(t, () => pauseTorrents({ downloader_id: t.downloaderId, hashes: [t.hash] }))
  }

  private async resume(t: Torrent): Promise<void> {
    await this.withBusy(t, () => resumeTorrents({ downloader_id: t.downloaderId, hashes: [t.hash] }))
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

  private async withBusy(t: Torrent, action: () => Promise<{ code?: string }>): Promise<void> {
    this.busyKey = this.keyOf(t)
    try {
      const res = await action()
      if (res && res.code && res.code !== '200') return
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

.m-torrents-applied {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--color-primary);
  text-align: center;
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

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
