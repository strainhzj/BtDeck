<template>
  <div class="tracker-keywords-board">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>🏷️ Tracker关键词管理</h1>
      <div class="header-actions">
        <el-button
          type="info"
          icon="el-icon-search"
          @click="handleSearch"
        >
          搜索
        </el-button>
        <el-button
          type="primary"
          icon="el-icon-refresh"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 池子看板 -->
    <div class="pools-grid">
      <!-- 候选池 -->
      <div
        v-for="pool in pools"
        :key="pool.type"
        class="pool-card"
        :class="[`pool-${pool.type}`, {'is-drag-over': pool.dragOver}]"
        @dragover.prevent="handleDragOver(pool)"
        @dragleave="handleDragLeave(pool)"
        @drop="handleDrop(pool, $event)"
      >
        <div class="pool-header">
          <span class="pool-title">{{ pool.icon }} {{ pool.label }}</span>
          <div class="pool-header-right">
            <!-- 池子操作按钮 (仅忽略池、成功池、失败池显示) -->
            <div v-if="pool.type !== 'candidate'" class="pool-actions">
              <el-tooltip content="添加关键词" placement="bottom">
                <i class="el-icon-plus pool-action-btn" @click="handleAddKeyword(pool.type)" />
              </el-tooltip>
              <el-tooltip content="导入关键词" placement="bottom">
                <i class="el-icon-upload2 pool-action-btn" @click="handleImportKeywords(pool.type)" />
              </el-tooltip>
              <el-tooltip content="导出关键词" placement="bottom">
                <i class="el-icon-download pool-action-btn" @click="handleExportKeywords(pool.type)" />
              </el-tooltip>
            </div>
            <span class="pool-count">{{ pool.count }}</span>
          </div>
        </div>

        <div
          class="pool-content"
          :class="{'is-drag-over': pool.dragOver}"
        >
          <keyword-tag-card
            v-for="keyword in pool.keywords"
            :key="keyword.keyword_id"
            :keyword="keyword.keyword"
            :max-length="20"
            @dragstart="handleKeywordDragStart(keyword, pool.type)"
            @dragend="handleKeywordDragEnd"
            @delete="handleDeleteKeyword(pool.type, keyword)"
            @click="handleKeywordClick(keyword)"
          />
        </div>

        <el-button
          class="view-all-btn"
          type="text"
          @click="openModal(pool.type)"
        >
          查看全部 →
        </el-button>
      </div>
    </div>

    <!-- 关键词列表弹窗 -->
    <keyword-list-modal
      :visible.sync="modalVisible"
      :pool-type="currentPoolType"
      :keywords="currentPoolKeywords"
      @refresh="loadAllPools"
    />

    <!-- 添加关键词弹窗 -->
    <add-keyword-dialog
      :visible.sync="addDialogVisible"
      :pool-type="currentPoolType"
      :pool-label="currentPoolLabel"
      @success="handleAddSuccess"
    />

    <!-- 导入关键词弹窗 -->
    <import-keywords-dialog
      :visible.sync="importDialogVisible"
      :pool-type="currentPoolType"
      :pool-label="currentPoolLabel"
      @success="handleImportSuccess"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import KeywordTagCard from './components/KeywordTagCard.vue'
import KeywordListModal from './components/KeywordListModal.vue'
import AddKeywordDialog from './components/AddKeywordDialog.vue'
import ImportKeywordsDialog from './components/ImportKeywordsDialog.vue'
import { getPoolKeywords, deleteKeyword, moveKeywordToPool, createKeyword, PoolType } from '@/api/tracker'
import { extractErrorMessage } from '@/utils/tracker'

interface PoolKeyword {
  keyword_id: string
  keyword: string
  pool_type: string
  create_time?: string
}

interface Pool {
  type: string
  label: string
  icon: string
  count: number
  keywords: PoolKeyword[]
  dragOver: boolean
}

@Component({
  name: 'TrackerKeywordsBoard',
  components: {
    KeywordTagCard,
    KeywordListModal,
    AddKeywordDialog,
    ImportKeywordsDialog
  }
})
export default class TrackerKeywordsBoard extends Vue {
  modalVisible = false
  addDialogVisible = false
  importDialogVisible = false
  currentPoolType = ''
  refreshing = false

  draggedKeyword: PoolKeyword | null = null
  draggedPoolType = ''

  pools: Pool[] = [
    {
      type: 'candidate',
      label: '候选池',
      icon: '📋',
      count: 0,
      keywords: [],
      dragOver: false
    },
    {
      type: 'ignored',
      label: '忽略池',
      icon: '⏭️',
      count: 0,
      keywords: [],
      dragOver: false
    },
    {
      type: 'success',
      label: '成功池',
      icon: '✅',
      count: 0,
      keywords: [],
      dragOver: false
    },
    {
      type: 'failed',
      label: '失败池',
      icon: '❌',
      count: 0,
      keywords: [],
      dragOver: false
    }
  ]

  mounted() {
    this.loadAllPools()
  }

  async loadAllPools() {
    try {
      this.refreshing = true
      const promises = this.pools.map(pool => this.loadPoolData(pool.type))
      await Promise.all(promises)
    } catch (error: any) {
      console.error('加载池数据失败:', error)
      const errorMsg = extractErrorMessage(error, '加载池数据失败')
      this.$message.error(errorMsg)
    } finally {
      this.refreshing = false
    }
  }

  async loadPoolData(poolType: string) {
    try {
      // 调用实际的API获取池子关键词列表
      const response = await getPoolKeywords({
        pool_type: poolType as PoolType,
        page: 1,
        page_size: 20  // 看板显示前20个关键词
      })

      if (response.code === '200' && response.data) {
        const pool = this.pools.find(p => p.type === poolType)
        if (pool) {
          pool.keywords = response.data.list || []
          pool.count = response.data.total || 0
        }
      } else {
        this.$message.error(response.msg || '加载失败')
        const pool = this.pools.find(p => p.type === poolType)
        if (pool) {
          pool.keywords = []
          pool.count = 0
        }
      }
    } catch (error: any) {
      console.error(`加载 ${poolType} 数据失败:`, error)
      const errorMsg = extractErrorMessage(error, `加载${this.getPoolLabel(poolType)}数据失败`)
      this.$message.error(errorMsg)
      const pool = this.pools.find(p => p.type === poolType)
      if (pool) {
        pool.keywords = []
        pool.count = 0
      }
      throw error
    }
  }

  handleRefresh() {
    this.loadAllPools()
  }

  handleSearch() {
    // 跳转到全局搜索页面
    this.$router.push('/tracker/keywords-search')
  }

  openModal(poolType: string) {
    this.currentPoolType = poolType
    this.modalVisible = true
  }

  get currentPoolKeywords() {
    const pool = this.pools.find(p => p.type === this.currentPoolType)
    return pool?.keywords || []
  }

  get currentPoolLabel(): string {
    return this.getPoolLabel(this.currentPoolType)
  }

  // 拖拽相关方法
  handleKeywordDragStart(keyword: PoolKeyword, poolType: string) {
    this.draggedKeyword = keyword
    this.draggedPoolType = poolType
  }

  handleKeywordDragEnd() {
    this.draggedKeyword = null
    this.draggedPoolType = ''
    this.pools.forEach(pool => {
      pool.dragOver = false
    })
  }

  handleDragOver(pool: Pool) {
    if (this.draggedKeyword && this.draggedPoolType !== pool.type) {
      pool.dragOver = true
    }
  }

  handleDragLeave(pool: Pool) {
    pool.dragOver = false
  }

  /**
   * 验证拖拽操作是否有效
   */
  private validateDrop(targetPool: Pool): boolean {
    if (!this.draggedKeyword) {
      return false
    }
    if (this.draggedPoolType === targetPool.type) {
      return false
    }
    return true
  }

  /**
   * 从源池子中移除关键词
   */
  private removeKeywordFromSourcePool(
    sourcePoolType: string,
    keywordId: string
  ): boolean {
    const sourcePool = this.pools.find(p => p.type === sourcePoolType)
    if (!sourcePool) {
      return false
    }

    const index = sourcePool.keywords.findIndex(
      kw => kw.keyword_id === keywordId
    )
    if (index === -1) {
      return false
    }

    sourcePool.keywords.splice(index, 1)
    sourcePool.count = sourcePool.keywords.length
    return true
  }

  /**
   * 将关键词添加到目标池子
   */
  private addKeywordToTargetPool(
    targetPool: Pool,
    keyword: PoolKeyword
  ): void {
    const updatedKeyword = {
      ...keyword,
      pool_type: targetPool.type
    }
    targetPool.keywords.push(updatedKeyword)
    targetPool.count = targetPool.keywords.length
  }

  /**
   * 调用API移动关键词到目标池子
   */
  private async callMoveKeywordApi(
    keywordId: string,
    targetPoolType: string
  ): Promise<void> {
    await moveKeywordToPool({
      keyword_id: keywordId,
      target_pool: targetPoolType
    })
  }

  /**
   * 显示移动成功消息
   */
  private showMoveSuccessMessage(keyword: string, targetPoolLabel: string): void {
    this.$message.success(`关键词 "${keyword}" 已移动到 ${targetPoolLabel}`)
  }

  /**
   * 重置拖拽状态
   */
  private resetDragState(): void {
    this.draggedKeyword = null
    this.draggedPoolType = ''
  }

  /**
   * 处理关键词拖放事件
   * 将关键词从一个池子移动到另一个池子
   */
  async handleDrop(targetPool: Pool, event: DragEvent) {
    event.preventDefault()
    targetPool.dragOver = false

    // 验证拖拽操作
    if (!this.validateDrop(targetPool)) {
      return
    }

    // 保存拖拽数据的深拷贝副本，避免在异步操作中被修改
    const draggedKeywordCopy = JSON.parse(JSON.stringify(this.draggedKeyword))
    const sourcePoolTypeCopy = this.draggedPoolType

    try {
      // 调用API移动关键词
      await this.callMoveKeywordApi(draggedKeywordCopy.keyword_id, targetPool.type)

      // 从源池子移除
      this.removeKeywordFromSourcePool(sourcePoolTypeCopy, draggedKeywordCopy.keyword_id)

      // 添加到目标池子
      this.addKeywordToTargetPool(targetPool, draggedKeywordCopy)

      // 显示成功消息
      this.showMoveSuccessMessage(draggedKeywordCopy.keyword, targetPool.label)

      // 重置拖拽状态
      this.resetDragState()
    } catch (error: any) {
      console.error('移动关键词失败:', error)
      const errorMsg = extractErrorMessage(error, '移动失败')
      this.$message.error(errorMsg)
    }
  }

  // 删除关键词
  async handleDeleteKeyword(poolType: string, keyword: PoolKeyword) {
    try {
      await this.$confirm(
        `确定要删除关键词 "${keyword.keyword}" 吗？`,
        '提示',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )

      await deleteKeyword(keyword.keyword_id)

      const pool = this.pools.find(p => p.type === poolType)
      if (pool) {
        const index = pool.keywords.findIndex(
          kw => kw.keyword_id === keyword.keyword_id
        )
        if (index > -1) {
          pool.keywords.splice(index, 1)
          pool.count = pool.keywords.length
        }
      }

      this.$message.success('删除成功')
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('删除关键词失败:', error)
        const errorMsg = extractErrorMessage(error, '删除失败')
        this.$message.error(errorMsg)
      }
    }
  }

  // 点击关键词
  handleKeywordClick(keyword: PoolKeyword) {
    // TODO: 实现点击后的操作，比如显示详情
    console.log('点击关键词:', keyword)
  }

  // 池子操作方法
  handleAddKeyword(poolType: string) {
    const keywordType = this.getPoolKeywordType(poolType)

    // 候选池不支持手动添加关键词
    if (!keywordType) {
      this.$message.warning('候选池不支持手动添加关键词,请将关键词拖拽到其他池子')
      return
    }

    this.currentPoolType = poolType
    this.addDialogVisible = true
  }

  handleImportKeywords(poolType: string) {
    const keywordType = this.getPoolKeywordType(poolType)

    // 候选池不支持导入关键词
    if (!keywordType) {
      this.$message.warning('候选池不支持导入关键词,请将关键词拖拽到其他池子')
      return
    }

    this.currentPoolType = poolType
    this.importDialogVisible = true
  }

  // 添加关键词成功回调
  async handleAddSuccess() {
    await this.loadPoolData(this.currentPoolType)
  }

  // 导入关键词成功回调
  async handleImportSuccess(count: number) {
    if (count > 0) {
      await this.loadPoolData(this.currentPoolType)
    }
  }

  handleExportKeywords(poolType: string) {
    this.$message.info(`导出功能开发中 - ${this.getPoolLabel(poolType)}`)
    // TODO: 实现导出功能
    // 1. 获取池子所有关键词
    // 2. 生成文件（JSON/CSV/TXT）
    // 3. 触发下载
  }

  getPoolLabel(poolType: string): string {
    const pool = this.pools.find(p => p.type === poolType)
    return pool?.label || poolType
  }

  /**
   * 将池子类型映射到关键词类型
   * candidate -> 不支持添加（候选池由系统自动生成）
   * ignored -> ignored（忽略关键词）
   * success -> success（成功关键词）
   * failed -> failed（失败关键词）
   */
  private getPoolKeywordType(poolType: string): 'success' | 'failed' | 'ignored' | null {
    const typeMap: Record<string, 'success' | 'failed' | 'ignored' | null> = {
      'candidate': null,
      'ignored': 'ignored',
      'success': 'success',
      'failed': 'failed'
    }
    return typeMap[poolType] ?? null
  }
}
</script>

<style lang="scss" scoped>
.tracker-keywords-board {
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
  min-height: 100vh;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-lg) var(--spacing-xl);
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);

  h1 {
    font-size: var(--font-size-2xl);
    font-weight: var(--font-weight-semibold);
    margin: 0;
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
  }

  .header-actions {
    display: flex;
    gap: var(--spacing-md);
  }
}

.pools-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-lg);
}

.pool-card {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  min-height: 320px;
  box-shadow: var(--shadow-md);
  transition: all 0.3s;
  border: 2px solid transparent;
  display: flex;
  flex-direction: column;

  &:hover {
    box-shadow: var(--shadow-lg);
    transform: translateY(-2px);
  }

  &.is-drag-over {
    transform: scale(1.02);
    box-shadow: var(--shadow-xl);
  }
}

.pool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 2px solid;
}

.pool-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.pool-header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.pool-actions {
  display: flex;
  gap: var(--spacing-sm);
  padding-right: var(--spacing-md);
  border-right: 1px solid var(--color-border-primary);
}

.pool-action-btn {
  font-size: var(--font-size-lg);
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: all 0.2s;

  &:hover {
    color: var(--color-info);
    background: var(--color-info-light);
    transform: scale(1.1);
  }
}

.pool-count {
  font-size: var(--font-size-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-medium);
}

.pool-content {
  flex: 1;
  min-height: 200px;
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  transition: all 0.3s;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  align-content: flex-start;
  overflow-y: auto;
  max-height: 400px;

  &.is-drag-over {
    background: rgba(59, 130, 246, 0.05);
    border: 3px dashed;
  }
}

.view-all-btn {
  display: block;
  margin-top: var(--spacing-md);
  padding: 10px var(--spacing-lg);
  border: 2px solid;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  width: 100%;
  transition: all 0.2s;
  background: transparent;

  &:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
  }
}

// 候选池样式
.pool-candidate {
  border-color: #bfdbfe;
  background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);

  .pool-header {
    border-bottom-color: #3b82f6;
  }

  .pool-title {
    color: #1e40af;
  }

  .pool-count {
    background: #dbeafe;
    color: #1e40af;
  }

  .pool-content.is-drag-over {
    border-color: #3b82f6;
    background: rgba(59, 130, 246, 0.08);
  }

  .view-all-btn {
    border-color: #3b82f6;
    color: #3b82f6;

    &:hover {
      background: #eff6ff;
    }
  }
}

// 忽略池样式
.pool-ignored {
  border-color: #e5e7eb;
  background: linear-gradient(135deg, #ffffff 0%, #f9fafb 100%);

  .pool-header {
    border-bottom-color: #9ca3af;
  }

  .pool-title {
    color: #4b5563;
  }

  .pool-count {
    background: #f3f4f6;
    color: #4b5563;
  }

  .pool-content.is-drag-over {
    border-color: #9ca3af;
    background: rgba(156, 163, 175, 0.08);
  }

  .view-all-btn {
    border-color: #9ca3af;
    color: #6b7280;

    &:hover {
      background: #f3f4f6;
    }
  }
}

// 成功池样式
.pool-success {
  border-color: #a7f3d0;
  background: linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%);

  .pool-header {
    border-bottom-color: #10b981;
  }

  .pool-title {
    color: #065f46;
  }

  .pool-count {
    background: #d1fae5;
    color: #065f46;
  }

  .pool-content.is-drag-over {
    border-color: #10b981;
    background: rgba(16, 185, 129, 0.08);
  }

  .view-all-btn {
    border-color: #10b981;
    color: #10b981;

    &:hover {
      background: #ecfdf5;
    }
  }
}

// 失败池样式
.pool-failed {
  border-color: #fecaca;
  background: linear-gradient(135deg, #ffffff 0%, #fef2f2 100%);

  .pool-header {
    border-bottom-color: #ef4444;
  }

  .pool-title {
    color: #991b1b;
  }

  .pool-count {
    background: #fee2e2;
    color: #991b1b;
  }

  .pool-content.is-drag-over {
    border-color: #ef4444;
    background: rgba(239, 68, 68, 0.08);
  }

  .view-all-btn {
    border-color: #ef4444;
    color: #ef4444;

    &:hover {
      background: #fef2f2;
    }
  }
}

// 响应式设计
@media (max-width: 1200px) {
  .pools-grid {
    grid-template-columns: 1fr;
  }
}
</style>
