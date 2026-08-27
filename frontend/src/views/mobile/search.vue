<template>
  <div class="m-search">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <!-- 高级搜索：直接复用桌面 AdvancedSearchWorkspace（左侧已保存搜索与 Web 端同源数据，
         选择/新建/保存更改/删除与桌面一致；构建器条件组/字段/操作符零缺省） -->
    <div class="m-search-builder">
      <advanced-search-workspace
        ref="workspace"
        :searching="searching"
        @search="onBuilderSearch"
        @reset="onBuilderReset"
      />
    </div>

    <!-- 结果区 -->
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
import { Component, Mixins, Vue } from 'vue-property-decorator'
import {
  advancedSearch,
  Torrent,
  AdvancedSearchRequest,
  AdvancedSearchBuilderParams
} from '@/api/torrents'
import { extractErrorMessage } from '@/utils/formatters'
import { buildAdvancedSearchRequest } from '@/views/torrents/utils/torrentBatch'
import AdvancedSearchWorkspace from '@/components/torrents/AdvancedSearchWorkspace.vue'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

/** 桌面工作区公开入口（AdvancedSearchWorkspace 同签名透传） */
interface SearchWorkspaceRef extends Vue {
  onSearch(): void
  refreshFieldOptions(): void
}

const RESULT_LIMIT = 20

/**
 * 移动高级搜索（Phase 4 M2）：
 * - 直接复用桌面 AdvancedSearchWorkspace——已保存搜索列表与 Web 端同源
 *   （getSearchTemplates({is_public:true}) 过滤 source=advanced），选择/新建/
 *   保存更改/删除全量对齐桌面；简单搜索已迁至移动种子页（/m/torrents）；
 * - search 事件 → buildAdvancedSearchRequest → advancedSearch POST。
 * 移动端查询模板页已裁撤（仅保留高级搜索）：模板能力收敛进工作区左侧
 * 已保存搜索，跨页模板应用缓存链路随之移除。
 */
@Component({
  name: 'MobileSearch',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    'advanced-search-workspace': AdvancedSearchWorkspace
  }
})
export default class MobileSearch extends Mixins(PullToRefresh) {
  private results: Torrent[] = []
  private total = 0
  private searching = false
  private searched = false

  private get workspace(): SearchWorkspaceRef | undefined {
    return this.$refs.workspace as SearchWorkspaceRef | undefined
  }

  protected async onPullRefresh(): Promise<void> {
    if (this.searched) {
      this.rerunAdvanced()
    } else {
      // 未搜索过：刷新工作区字段候选与已保存搜索列表
      this.workspace?.refreshFieldOptions()
    }
  }

  // ============ 高级搜索（复用桌面工作区） ============

  private async onBuilderSearch(params: AdvancedSearchBuilderParams): Promise<void> {
    const { request, error } = buildAdvancedSearchRequest(params, 'added_date', RESULT_LIMIT)
    if (!request || error) {
      this.$message.error(error || '搜索条件格式错误')
      return
    }
    await this.executeAdvanced(request)
  }

  /** 高级模式重复执行（下拉刷新统一出口）：工作区校验并转发构建器 search 事件 */
  private rerunAdvanced(): void {
    this.workspace?.onSearch()
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
/* 工作区为桌面组件（窄屏自动上下堆叠）：卡片容器承接移动页白底圆角风格 */
.m-search-builder {
  background: #fff;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 10px;
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
