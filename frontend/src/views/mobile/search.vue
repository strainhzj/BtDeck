<template>
  <div class="m-search">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-search-mode">
      <button
        type="button"
        class="m-search-mode-btn"
        :class="{'is-active': mode === 'simple'}"
        @click="switchMode('simple')"
      >
        简单查询
      </button>
      <button
        type="button"
        class="m-search-mode-btn"
        :class="{'is-active': mode === 'advanced'}"
        @click="switchMode('advanced')"
      >
        高级搜索
      </button>
    </div>

    <!-- 简单查询：与桌面 torrents 快捷筛选同字段集（name/下载器/状态/tracker 域） -->
    <div v-if="mode === 'simple'" class="m-search-form">
      <el-input
        v-model="simpleForm.name"
        size="small"
        placeholder="种子名称关键词"
        clearable
        prefix-icon="el-icon-search"
        @keyup.enter.native="runSimpleSearch"
      />
      <el-select
        v-model="simpleForm.downloaders"
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
        v-model="simpleForm.statuses"
        size="small"
        multiple
        collapse-tags
        placeholder="全部状态"
        clearable
      >
        <el-option v-for="opt in TORRENT_STATUS_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-select
        v-model="simpleForm.trackerDomains"
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
      <el-button class="m-search-run" type="primary" size="small" :loading="searching" @click="runSimpleSearch">
        搜索
      </el-button>
    </div>

    <!-- 高级搜索：直接复用桌面 AdvancedSearchBuilder（条件组/字段/操作符与桌面完全一致） -->
    <div v-else class="m-search-builder">
      <advanced-search-builder
        ref="builder"
        :searching="searching"
        @search="onBuilderSearch"
        @reset="onBuilderReset"
        @save-template="onSaveTemplate"
      />
    </div>

    <!-- 结果区 -->
    <div v-if="appliedTip" class="m-search-applied">{{ appliedTip }}</div>
    <div v-if="searched && !searching && results.length === 0" class="m-hint">没有匹配的种子</div>
    <div
      v-for="t in results"
      :key="`${t.downloaderId}-${t.hash}`"
      class="m-search-card"
      role="button"
      @click="openDetail(t)"
    >
      <div class="m-search-name" :title="t.name">{{ t.name }}</div>
      <div class="m-search-meta">
        <el-tag size="mini" :type="statusTagType(t.status)">{{ statusLabel(t.status) }}</el-tag>
        <span class="m-search-meta-text">{{ t.downloaderName }}</span>
        <span class="m-search-meta-text">{{ formatSize(t.size) }}</span>
      </div>
      <el-progress
        :percentage="progressOf(t)"
        :status="t.status === 'error' ? 'exception' : undefined"
        :stroke-width="6"
        :show-text="false"
      />
      <div class="m-search-progress-text">{{ progressOf(t).toFixed(1) }}%</div>
    </div>

    <div v-if="searched && results.length > 0" class="m-search-summary">共 {{ total }} 条结果</div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getTorrentList,
  advancedSearch,
  createSearchTemplate,
  getTrackerDomains,
  Torrent,
  AdvancedSearchRequest,
  AdvancedSearchBuilderParams,
  QueryTemplateConditionGroup,
  QueryTemplateConditions,
  CreateSearchTemplateRequest
} from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'
import { extractErrorMessage } from '@/utils/formatters'
import {
  buildAdvancedSearchRequest,
  buildAdvancedSearchRequestFromTemplateGroups
} from '@/views/torrents/utils/torrentBatch'
import AdvancedSearchBuilder from '@/components/torrents/AdvancedSearchBuilder.vue'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import { takeAppliedTemplateConditions } from '@/views/mobile/m2-template-cache'
import {
  TORRENT_STATUS_OPTIONS,
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

interface SelectOption {
  label: string
  value: string
}

/** 桌面构建器 save-template 事件载荷（AdvancedSearchBuilder confirmSaveTemplate） */
interface BuilderTemplatePayload {
  id: string
  name: string
  description: string
  isDefault: boolean
  conditions: QueryTemplateConditionGroup[]
  createdTime: string
}

const RESULT_LIMIT = 20

/**
 * 移动高级搜索（Phase 4 M2）：
 * - 简单查询：与桌面 torrents 快捷筛选同字段集（名称/下载器/状态/Tracker 域）→ getList；
 * - 高级搜索：直接复用桌面 AdvancedSearchBuilder 组件（条件组/字段/操作符零缺省）
 *   → buildAdvancedSearchRequest → advancedSearch POST；
 * - 查询模板页「应用」经 m2-template-cache 进入本页自动回填并执行
 *   （简单模板填表单，高级模板走 builder.applyTemplateGroups + FromTemplateGroups 构建）；
 * - builder 的 save-template 事件接 createSearchTemplate（source=advanced）。
 */
@Component({
  name: 'MobileSearch',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    'advanced-search-builder': AdvancedSearchBuilder
  }
})
export default class MobileSearch extends Mixins(PullToRefresh) {
  private mode: 'simple' | 'advanced' = 'simple'
  private simpleForm = {
    name: '',
    downloaders: [] as string[],
    statuses: [] as string[],
    trackerDomains: [] as string[]
  }
  private downloaderOptions: SelectOption[] = []
  private trackerDomainOptions: string[] = []
  private results: Torrent[] = []
  private total = 0
  private searching = false
  private searched = false
  private appliedTip = ''

  private TORRENT_STATUS_OPTIONS = TORRENT_STATUS_OPTIONS

  mounted(): void {
    this.loadFilterOptions()
    this.applyPendingTemplate()
  }

  protected async onPullRefresh(): Promise<void> {
    if (this.mode === 'simple' && this.searched) {
      await this.runSimpleSearch()
    } else if (this.mode === 'advanced' && this.searched) {
      await this.rerunAdvanced()
    } else {
      await this.loadFilterOptions()
    }
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

  private switchMode(mode: 'simple' | 'advanced'): void {
    this.mode = mode
  }

  // ============ 简单查询 ============

  private async runSimpleSearch(): Promise<void> {
    this.searching = true
    try {
      const res = await getTorrentList({
        ...(this.simpleForm.name ? { name_like: this.simpleForm.name } : {}),
        ...(this.simpleForm.downloaders.length ? { downloader_id: this.simpleForm.downloaders } : {}),
        ...(this.simpleForm.statuses.length ? { status: this.simpleForm.statuses } : {}),
        ...(this.simpleForm.trackerDomains.length ? { tracker_domain: this.simpleForm.trackerDomains } : {}),
        skip: 0,
        limit: RESULT_LIMIT,
        sort_by: 'added_date',
        sort_order: 'desc'
      })
      if (res.code === '200' && res.data) {
        this.results = res.data.list ?? []
        this.total = res.data.total ?? 0
        this.searched = true
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.searching = false
    }
  }

  // ============ 高级搜索（复用桌面构建器） ============

  private async onBuilderSearch(params: AdvancedSearchBuilderParams): Promise<void> {
    const { request, error } = buildAdvancedSearchRequest(params, 'added_date', RESULT_LIMIT)
    if (!request || error) {
      this.$message.error(error || '搜索条件格式错误')
      return
    }
    await this.executeAdvanced(request)
  }

  /** 高级模式重复执行（下拉刷新/模板执行后的统一出口） */
  private async rerunAdvanced(): Promise<void> {
    const builder = this.$refs.builder as AdvancedSearchBuilder | undefined
    if (builder && typeof (builder as unknown as { buildSearchParams?: () => AdvancedSearchBuilderParams }).buildSearchParams === 'function') {
      try {
        const params = (builder as unknown as { buildSearchParams: () => AdvancedSearchBuilderParams }).buildSearchParams()
        await this.onBuilderSearch(params)
      } catch {
        // 构建器校验失败已自行提示
      }
    }
  }

  private async executeAdvanced(request: AdvancedSearchRequest): Promise<void> {
    this.searching = true
    try {
      const res = await advancedSearch(request)
      if (res.code === '200' && res.data) {
        this.results = res.data.list ?? []
        this.total = res.data.total ?? 0
        this.searched = true
        this.$message.success(`搜索完成，共 ${this.total} 条结果`)
      } else {
        this.$message.error(res.msg || '搜索失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.searching = false
    }
  }

  private onBuilderReset(): void {
    this.results = []
    this.total = 0
    this.searched = false
  }

  /** 构建器「保存为模板」：转换为 v1.0.5 createSearchTemplate（source=advanced） */
  private async onSaveTemplate(payload: BuilderTemplatePayload): Promise<void> {
    try {
      const conditions: QueryTemplateConditions = {
        source: 'advanced',
        version: 1,
        condition_groups: payload.conditions
      }
      const data: CreateSearchTemplateRequest = {
        name: payload.name,
        ...(payload.description ? { description: payload.description } : {}),
        conditions,
        is_public: false
      }
      const res = await createSearchTemplate(data)
      if (res.code === '200') {
        this.$message.success(`模板「${payload.name}」已保存`)
      } else {
        this.$message.error(res.msg || '模板保存失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  // ============ 模板应用（查询模板页跳转进入） ============

  private async applyPendingTemplate(): Promise<void> {
    const pending = takeAppliedTemplateConditions()
    if (!pending) return
    const { conditions, templateName } = pending
    this.appliedTip = `已应用模板「${templateName}」`
    if (conditions.source === 'advanced') {
      this.mode = 'advanced'
      await this.$nextTick()
      const groups = conditions.condition_groups ?? []
      const sortBy = conditions.sort_by || 'added_date'
      const sortOrder = conditions.sort_order || 'desc'
      const builder = this.$refs.builder as unknown as {
        applyTemplateGroups?: (g: QueryTemplateConditionGroup[], s: { sort_by: string, sort_order: string }) => void
      } | undefined
      if (builder && typeof builder.applyTemplateGroups === 'function') {
        builder.applyTemplateGroups(groups, { sort_by: sortBy, sort_order: sortOrder })
      }
      const { request, error } = buildAdvancedSearchRequestFromTemplateGroups(groups, sortBy, sortOrder, RESULT_LIMIT)
      if (!request || error) {
        this.$message.error(error || '模板条件格式错误')
        return
      }
      await this.executeAdvanced(request)
    } else {
      const lq = conditions.listQuery ?? {}
      this.simpleForm = {
        name: lq.name_like ?? '',
        downloaders: Array.isArray(lq.downloader_id) ? [...lq.downloader_id] : [],
        statuses: Array.isArray(lq.status) ? [...lq.status] : [],
        trackerDomains: []
      }
      await this.runSimpleSearch()
    }
  }

  private openDetail(t: Torrent): void {
    setCachedTorrent(t)
    this.$router
      .push(`/m/torrents/detail/${encodeURIComponent(t.downloaderId)}/${encodeURIComponent(t.hash)}`)
      .catch(() => undefined)
  }

  // ============ 展示辅助 ============

  private statusLabel(status: string): string {
    return torrentStatusLabel(status)
  }

  /** 模板不能直调模块级函数，须实例方法包装（同 torrent-detail 约定） */
  private formatSize(bytes: number): string {
    return formatTorrentSize(bytes)
  }

  private statusTagType(status: string): string {
    return torrentStatusTagType(status)
  }

  private progressOf(t: Torrent): number {
    const value = typeof t.progress === 'number' ? t.progress : 0
    return Math.min(100, Math.max(0, value))
  }
}
</script>

<style scoped>
.m-search-mode {
  display: flex;
  background: #fff;
  border-radius: 8px;
  padding: 4px;
  margin-bottom: 10px;
}

.m-search-mode-btn {
  flex: 1;
  border: none;
  background: transparent;
  padding: 8px 0;
  border-radius: 6px;
  font-size: 14px;
  color: #606266;
}

.m-search-mode-btn.is-active {
  background: var(--color-primary);
  color: #fff;
  font-weight: 600;
}

.m-search-form {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.m-search-run {
  align-self: stretch;
}

/* 构建器为桌面组件：容器横向可滚，内部表单控件全宽 */
.m-search-builder {
  background: #fff;
  border-radius: 8px;
  padding: 10px 10px 4px;
  margin-bottom: 10px;
  overflow-x: auto;
}

.m-search-builder > div {
  max-width: 100%;
}

.m-search-applied {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--color-primary);
  text-align: center;
}

.m-search-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
}

.m-search-name {
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

.m-search-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
}

.m-search-meta-text {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-search-progress-text {
  margin-top: 2px;
  font-size: 11px;
  color: #c0c4cc;
  text-align: right;
}

.m-search-summary {
  text-align: center;
  font-size: 12px;
  color: #909399;
  padding: 6px 0 12px;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
