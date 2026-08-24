<template>
  <div class="m-tracker-kw">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-tracker-kw-pools">
      <button
        v-for="pool in poolTabs"
        :key="pool.type"
        type="button"
        class="m-tracker-kw-pool"
        :class="[`is-${pool.type}`, {'is-active': activePool === pool.type}]"
        @click="switchPool(pool.type)"
      >
        <span class="m-tracker-kw-pool-label">{{ pool.label }}</span>
        <span class="m-tracker-kw-pool-count">{{ poolCount(pool.type) }}</span>
      </button>
    </div>

    <div class="m-toolbar">
      <el-button size="small" icon="el-icon-search" @click="goSearch">搜索</el-button>
      <el-button
        size="small"
        type="primary"
        icon="el-icon-plus"
        :disabled="activePool === 'candidate'"
        @click="addVisible = true"
      >
        添加
      </el-button>
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reload">刷新</el-button>
    </div>

    <div v-if="!loading && keywords.length === 0" class="m-hint">该池暂无关键词</div>

    <div v-for="kw in keywords" :key="kw.keyword_id" class="m-tracker-kw-card">
      <div class="m-tracker-kw-word" :title="kw.keyword">{{ kw.keyword }}</div>
      <div class="m-tracker-kw-meta">
        <span class="m-tracker-kw-time">{{ formatTime(kw.create_time) }}</span>
        <el-dropdown trigger="click" @command="(cmd) => handleCommand(kw, cmd)">
          <el-button size="mini" type="text" icon="el-icon-more" class="m-tracker-kw-more" />
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item
              v-for="pool in moveTargets"
              :key="pool.type"
              :command="pool.type"
            >
              移动到{{ pool.label }}
            </el-dropdown-item>
            <el-dropdown-item command="__delete" divided>
              <span class="m-tracker-kw-danger">删除</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
      </div>
    </div>

    <el-button
      v-if="keywords.length < total"
      class="m-load-more"
      size="small"
      :loading="loading"
      @click="loadMore"
    >
      加载更多（{{ keywords.length }}/{{ total }}）
    </el-button>

    <div class="m-tracker-kw-footnote">
      导入/导出、快捷操作（左匹配）、汇报配置与测试工具请在桌面版「Tracker管理」页操作
    </div>

    <add-keyword-dialog
      :visible.sync="addVisible"
      :pool-type="activePool"
      :pool-label="activePoolLabel"
      @success="onAddSuccess"
    />
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getPoolKeywords,
  getPoolStatistics,
  moveKeywordToPool,
  deleteKeyword,
  PoolType,
  PoolKeyword
} from '@/api/tracker'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import AddKeywordDialog from '@/views/tracker/components/AddKeywordDialog.vue'

const PAGE_SIZE = 20

interface PoolTab {
  type: PoolType
  label: string
}

/**
 * 移动 Tracker 关键词看板（Phase 4 M3）：四池切换 + 卡片流；
 * 桌面拖拽移池在移动端改为关键词卡片下拉「移动到X池」；添加关键词复用桌面
 * AddKeywordDialog。导入/导出、快捷操作（左匹配）保留桌面版承载。
 */
@Component({
  name: 'MobileTrackerKeywords',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    'add-keyword-dialog': AddKeywordDialog
  }
})
export default class MobileTrackerKeywords extends Mixins(PullToRefresh) {
  private poolTabs: PoolTab[] = [
    { type: 'candidate', label: '候选池' },
    { type: 'ignored', label: '忽略池' },
    { type: 'success', label: '成功池' },
    { type: 'failed', label: '失败池' }
  ]

  private poolCounts: Partial<Record<PoolType, number>> = {}
  private activePool: PoolType = 'candidate'
  private keywords: PoolKeyword[] = []
  private total = 0
  private page = 1
  private loading = false
  private addVisible = false

  mounted(): void {
    this.reload()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
  }

  private get activePoolLabel(): string {
    const pool = this.poolTabs.find((p) => p.type === this.activePool)
    return pool ? pool.label : this.activePool
  }

  /** 模板不可用 ??（buble 模板编译不支持 ES2020），计数兜底收进实例方法 */
  private poolCount(poolType: PoolType): number {
    return this.poolCounts[poolType] ?? 0
  }

  /** 移动目标：除当前池外的三个池（与桌面拖拽同规则：不允许原地移动） */
  private get moveTargets(): PoolTab[] {
    return this.poolTabs.filter((p) => p.type !== this.activePool)
  }

  private async reload(): Promise<void> {
    this.page = 1
    this.keywords = []
    this.total = 0
    await Promise.all([this.fetchPool(), this.fetchCounts()])
  }

  private async loadMore(): Promise<void> {
    await this.fetchPool()
  }

  private async fetchPool(): Promise<void> {
    this.loading = true
    try {
      const res = await getPoolKeywords({
        pool_type: this.activePool,
        page: this.page,
        page_size: PAGE_SIZE
      })
      if (res.code === '200' && res.data) {
        this.keywords = this.keywords.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
        this.page += 1
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private async fetchCounts(): Promise<void> {
    try {
      const res = await getPoolStatistics()
      if (res.code === '200' && res.data) {
        this.poolCounts = {
          candidate: res.data.candidate_count,
          ignored: res.data.ignored_count,
          success: res.data.success_count,
          failed: res.data.failed_count
        }
      }
    } catch {
      // 池子计数加载失败不阻塞列表，Tab 显示 0
    }
  }

  private switchPool(poolType: PoolType): void {
    if (this.activePool === poolType) return
    this.activePool = poolType
    this.page = 1
    this.keywords = []
    this.total = 0
    this.fetchPool()
  }

  private async handleCommand(kw: PoolKeyword, command: string): Promise<void> {
    if (command === '__delete') {
      this.confirmDelete(kw)
      return
    }
    await this.moveKeyword(kw, command as PoolType)
  }

  private async moveKeyword(kw: PoolKeyword, targetPool: PoolType): Promise<void> {
    try {
      await moveKeywordToPool({ keyword_id: kw.keyword_id, target_pool: targetPool })
      const label = this.poolTabs.find((p) => p.type === targetPool)?.label ?? targetPool
      this.$message.success(`关键词已移动到${label}`)
      await this.reload()
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  private confirmDelete(kw: PoolKeyword): void {
    this.$confirm(`确定要删除关键词 "${kw.keyword}" 吗？`, '提示', { type: 'warning' })
      .then(async() => {
        try {
          await deleteKeyword(kw.keyword_id)
          this.$message.success('删除成功')
          await this.reload()
        } catch (e) {
          this.$message.error(extractErrorMessage(e))
        }
      })
      .catch(() => undefined)
  }

  private async onAddSuccess(): Promise<void> {
    await this.reload()
  }

  private goSearch(): void {
    this.$router.push('/m/tracker/keywords-search').catch(() => undefined)
  }

  private formatTime(value?: string): string {
    if (!value) return '-'
    return value.replace('T', ' ').slice(0, 19)
  }
}
</script>

<style scoped>
.m-tracker-kw-pools {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.m-tracker-kw-pool {
  flex: 1;
  border: 1px solid #e4e7ed;
  background: #fff;
  border-radius: 8px;
  padding: 6px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.m-tracker-kw-pool.is-active {
  border-color: var(--color-primary);
  background: rgba(5, 150, 105, 0.06);
}

.m-tracker-kw-pool-label {
  font-size: 12px;
  color: #606266;
}

.m-tracker-kw-pool.is-active .m-tracker-kw-pool-label {
  color: var(--color-primary);
  font-weight: 600;
}

.m-tracker-kw-pool-count {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.m-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.m-toolbar .el-button {
  flex: 1;
  margin-left: 0;
  padding: 9px 4px;
}

.m-tracker-kw-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-tracker-kw-word {
  font-size: 14px;
  color: #303133;
  font-weight: 600;
  word-break: break-all;
  line-height: 1.4;
}

.m-tracker-kw-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.m-tracker-kw-time {
  font-size: 11px;
  color: #c0c4cc;
}

.m-tracker-kw-more {
  padding: 3px;
}

.m-tracker-kw-danger {
  color: #f56c6c;
}

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-tracker-kw-footnote {
  margin-top: 14px;
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}

@media (max-width: 768px) {
  /* AddKeywordDialog（el-dialog 定宽 500px）窄屏收缩 */
  ::v-deep .el-dialog {
    width: 92% !important;
  }
}
</style>
