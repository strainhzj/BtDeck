<template>
  <div class="m-search">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <!-- 高级搜索：移动原生构建器（摘要卡+底部弹层编辑，逻辑与桌面同源），
         已保存搜索横滑胶囊与 Web 端同源数据 -->
    <mobile-advanced-search
      ref="builder"
      :searching="searching"
      @search="onBuilderSearch"
      @reset="onBuilderReset"
    />

    <!-- 结果区：搜索完成后自动滚动定位至此（锚点让开吸顶头部） -->
    <div ref="resultsAnchor" class="m-search-results-anchor" />
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
import MobileAdvancedSearch from '@/views/mobile/components/MobileAdvancedSearch.vue'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

/** 移动构建器公开入口（MobileAdvancedSearch 同签名透传） */
interface SearchBuilderRef extends Vue {
  onSearch(): void
  refreshFieldOptions(): void
}

const RESULT_LIMIT = 20

/**
 * 移动高级搜索（方案三移动原生重构）：
 * - MobileAdvancedSearch：条件摘要卡 + 底部弹层编辑 + 已保存搜索横滑胶囊
 *   + 吸底执行按钮；字段/操作符/校验/请求构造与桌面共享同源实现；
 * - search 事件 → buildAdvancedSearchRequest → advancedSearch POST；
 * - 搜索完成后自动滚动定位到结果区（构建器很长，不让用户手滚）；
 * - 简单搜索已迁至移动种子页（/m/torrents）；移动端查询模板页已裁撤，
 *   模板能力收敛进已保存搜索胶囊。
 */
@Component({
  name: 'MobileSearch',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    'mobile-advanced-search': MobileAdvancedSearch
  }
})
export default class MobileSearch extends Mixins(PullToRefresh) {
  private results: Torrent[] = []
  private total = 0
  private searching = false
  private searched = false

  private get builder(): SearchBuilderRef | undefined {
    return this.$refs.builder as SearchBuilderRef | undefined
  }

  protected async onPullRefresh(): Promise<void> {
    if (this.searched) {
      this.rerunAdvanced()
    } else {
      // 未搜索过：刷新构建器字段候选与已保存搜索列表
      this.builder?.refreshFieldOptions()
    }
  }

  // ============ 高级搜索（移动构建器） ============

  private async onBuilderSearch(params: AdvancedSearchBuilderParams): Promise<void> {
    const { request, error } = buildAdvancedSearchRequest(params, 'added_date', RESULT_LIMIT)
    if (!request || error) {
      this.$message.error(error || '搜索条件格式错误')
      return
    }
    await this.executeAdvanced(request)
  }

  /** 高级模式重复执行（下拉刷新统一出口）：构建器校验并转发 search 事件 */
  private rerunAdvanced(): void {
    this.builder?.onSearch()
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
        this.scrollToResults()
      } else {
        this.$message.error(res.msg || '搜索失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.searching = false
    }
  }

  /** 搜索完成后定位到结果区（jsdom 无 scrollIntoView，静默跳过） */
  private scrollToResults() {
    this.$nextTick(() => {
      const anchor = this.$refs.resultsAnchor as Element | undefined
      if (anchor && typeof anchor.scrollIntoView === 'function') {
        anchor.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    })
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
/* 结果锚点：让开 48px 吸顶头部（scroll-margin-top 平滑滚动同样生效） */
.m-search-results-anchor {
  height: 1px;
  scroll-margin-top: 56px;
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
