<template>
  <div class="m-kw-search">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-toolbar">
      <el-input
        v-model="keyword"
        size="small"
        placeholder="输入关键词搜索"
        clearable
        prefix-icon="el-icon-search"
        @keyup.enter.native="reload"
        @clear="reload"
      />
      <el-button size="small" type="primary" :loading="loading" @click="reload">搜索</el-button>
    </div>

    <div class="m-toolbar m-toolbar--second">
      <el-select
        v-model="selectedPools"
        size="small"
        multiple
        collapse-tags
        placeholder="全部池子"
        clearable
        @change="reload"
      >
        <el-option v-for="pool in poolTabs" :key="pool.type" :label="pool.label" :value="pool.type" />
      </el-select>
      <el-select v-model="timeRange" size="small" placeholder="全部时间" clearable @change="reload">
        <el-option label="今天" value="today" />
        <el-option label="本周" value="week" />
        <el-option label="本月" value="month" />
      </el-select>
      <el-select v-model="sortBy" size="small" placeholder="排序" @change="reload">
        <el-option label="最新添加" value="time_desc" />
        <el-option label="最早添加" value="time_asc" />
        <el-option label="关键词 A-Z" value="name_asc" />
      </el-select>
    </div>

    <div v-if="!loading && results.length === 0" class="m-hint">没有匹配的关键词</div>

    <div v-for="item in results" :key="item.keyword_id" class="m-kw-search-card">
      <div class="m-kw-search-word" :title="item.keyword">{{ item.keyword }}</div>
      <div class="m-kw-search-meta">
        <span class="m-kw-search-pool" :class="`is-${item.pool_type}`">{{ poolLabel(item.pool_type) }}</span>
        <span class="m-kw-search-time">{{ formatTime(item.create_time) }}</span>
      </div>
      <div class="m-kw-search-actions">
        <el-dropdown trigger="click" @command="(cmd) => handleMove(item, cmd)">
          <el-button size="mini">移动到池子</el-button>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item
              v-for="pool in poolTabs"
              :key="pool.type"
              :command="pool.type"
              :disabled="pool.type === item.pool_type"
            >
              {{ pool.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
        <el-button size="mini" type="danger" plain @click="confirmDelete(item)">删除</el-button>
      </div>
    </div>

    <el-button
      v-if="results.length < total"
      class="m-load-more"
      size="small"
      :loading="loading"
      @click="loadMore"
    >
      加载更多（{{ results.length }}/{{ total }}）
    </el-button>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  searchAllPools,
  moveKeywordToPool,
  deleteKeyword,
  PoolType,
  SearchResultItem
} from '@/api/tracker'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

const PAGE_SIZE = 20

interface PoolTab {
  type: PoolType
  label: string
}

/**
 * 移动关键词全局搜索（Phase 4 M3）：复用 searchAllPools 全池检索；
 * 支持关键词/池子/时间/排序筛选与卡片移动/删除（与桌面搜索页同字段集）。
 */
@Component({
  name: 'MobileTrackerKeywordsSearch',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileTrackerKeywordsSearch extends Mixins(PullToRefresh) {
  private poolTabs: PoolTab[] = [
    { type: 'candidate', label: '候选池' },
    { type: 'ignored', label: '忽略池' },
    { type: 'success', label: '成功池' },
    { type: 'failed', label: '失败池' }
  ]

  private keyword = ''
  private selectedPools: PoolType[] = []
  private timeRange = ''
  private sortBy = 'time_desc'
  private results: SearchResultItem[] = []
  private total = 0
  private page = 1
  private loading = false

  mounted(): void {
    const initial = this.$route.query.keyword as string
    if (initial) {
      this.keyword = initial
    }
    this.fetchPage()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
  }

  private async reload(): Promise<void> {
    this.page = 1
    this.results = []
    this.total = 0
    await this.fetchPage()
  }

  private async loadMore(): Promise<void> {
    await this.fetchPage()
  }

  private async fetchPage(): Promise<void> {
    this.loading = true
    try {
      const res = await searchAllPools({
        page: this.page,
        page_size: PAGE_SIZE,
        ...(this.keyword ? { keyword: this.keyword } : {}),
        ...(this.selectedPools.length > 0 ? { pool_types: this.selectedPools.join(',') } : {}),
        ...(this.timeRange ? { time_range: this.timeRange } : {}),
        sort_by: this.sortBy
      })
      if (res.code === '200' && res.data) {
        this.results = this.results.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
        this.page += 1
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private poolLabel(poolType: PoolType): string {
    const pool = this.poolTabs.find((p) => p.type === poolType)
    return pool ? pool.label : poolType
  }

  private async handleMove(item: SearchResultItem, targetPool: string): Promise<void> {
    if (targetPool === item.pool_type) return
    try {
      await moveKeywordToPool({ keyword_id: item.keyword_id, target_pool: targetPool as PoolType })
      this.$message.success(`关键词已移动到${this.poolLabel(targetPool as PoolType)}`)
      await this.reload()
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  private confirmDelete(item: SearchResultItem): void {
    this.$confirm(`确定要删除关键词 "${item.keyword}" 吗？`, '提示', { type: 'warning' })
      .then(async() => {
        try {
          await deleteKeyword(item.keyword_id)
          this.$message.success('删除成功')
          await this.reload()
        } catch (e) {
          this.$message.error(extractErrorMessage(e))
        }
      })
      .catch(() => undefined)
  }

  private formatTime(value: string): string {
    if (!value) return '-'
    return value.replace('T', ' ').slice(0, 19)
  }
}
</script>

<style scoped>
.m-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.m-toolbar .el-select,
.m-toolbar .el-input {
  flex: 1;
}

.m-kw-search-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-kw-search-word {
  font-size: 14px;
  color: #303133;
  font-weight: 600;
  word-break: break-all;
  line-height: 1.4;
}

.m-kw-search-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.m-kw-search-pool {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 4px;
}

.m-kw-search-pool.is-candidate {
  color: #1e40af;
  background: rgba(59, 130, 246, 0.12);
}

.m-kw-search-pool.is-ignored {
  color: #4b5563;
  background: rgba(107, 114, 128, 0.14);
}

.m-kw-search-pool.is-success {
  color: #065f46;
  background: rgba(16, 185, 129, 0.14);
}

.m-kw-search-pool.is-failed {
  color: #991b1b;
  background: rgba(239, 68, 68, 0.12);
}

.m-kw-search-time {
  font-size: 11px;
  color: #c0c4cc;
}

.m-kw-search-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
}

.m-kw-search-actions .el-button {
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
