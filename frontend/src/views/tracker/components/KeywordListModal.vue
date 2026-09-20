<template>
  <el-dialog
    :visible.sync="dialogVisible"
    :title="dialogTitle"
    width="70%"
    :close-on-click-modal="false"
    :close-on-press-escape="true"
    top="10vh"
    class="keyword-list-modal"
    @close="handleClose"
  >
    <div class="modal-container">
      <!-- 搜索和筛选栏 -->
      <div class="search-bar">
        <!-- 全选复选框 -->
        <el-checkbox
          v-model="allSelected"
          :indeterminate="isIndeterminate"
          @change="handleSelectAll"
        />

        <div class="search-input-wrapper">
          <el-input
            v-model="searchForm.keyword"
            :placeholder="$t('tracker.listModal.searchPlaceholder')"
            clearable
            @input="handleSearch"
          >
            <i slot="prefix" class="search-prefix-icon"><LucideIcon name="search" :size="14" /></i>
          </el-input>
        </div>

        <!-- 快捷操作（按前缀左匹配），位于搜索框右侧 -->
        <el-tooltip :content="$t('tracker.pools.quickActionTip')" placement="top">
          <i class="quick-action-btn" @click="openQuickAction">
            <LucideIcon name="wand-sparkles" :size="16" />
          </i>
        </el-tooltip>

        <el-select
          v-model="searchForm.timeRange"
          :placeholder="$t('tracker.search.timeRange')"
          clearable
          @change="handleSearch"
        >
          <el-option :label="$t('tracker.search.all')" value="">
            <LucideIcon name="list-filter" :size="13" /> {{ $t('tracker.search.all') }}
          </el-option>
          <el-option :label="$t('tracker.search.today')" value="today">
            <LucideIcon name="calendar-days" :size="13" /> {{ $t('tracker.search.today') }}
          </el-option>
          <el-option :label="$t('tracker.search.week')" value="week">
            <LucideIcon name="calendar-range" :size="13" /> {{ $t('tracker.search.week') }}
          </el-option>
          <el-option :label="$t('tracker.search.month')" value="month">
            <LucideIcon name="calendar-range" :size="13" /> {{ $t('tracker.search.month') }}
          </el-option>
        </el-select>

        <el-select
          v-model="searchForm.sortBy"
          :placeholder="$t('tracker.search.sortPlaceholder')"
          @change="handleSearch"
        >
          <el-option :label="$t('tracker.search.sortTimeDesc')" value="time_desc">
            <LucideIcon name="clock" :size="13" /> {{ $t('tracker.search.sortTimeDesc') }}
          </el-option>
          <el-option :label="$t('tracker.search.sortTimeAsc')" value="time_asc">
            <LucideIcon name="clock" :size="13" /> {{ $t('tracker.search.sortTimeAsc') }}
          </el-option>
          <el-option :label="$t('tracker.search.sortNameAsc')" value="name_asc">
            <LucideIcon name="arrow-down-a-z" :size="13" /> {{ $t('tracker.search.sortNameAsc') }}
          </el-option>
        </el-select>
      </div>

      <!-- 批量操作栏 -->
      <div v-show="selectedKeywords.length > 0" class="batch-actions">
        <span class="batch-info">
          <LucideIcon name="circle-check-big" :size="14" style="margin-right: 4px" /> {{ $t('tracker.listModal.selectedPrefix') }}<strong>{{ selectedKeywords.length }}</strong>{{ $t('tracker.listModal.selectedSuffix') }}
        </span>
        <el-button
          type="danger"
          size="small"
          @click="handleBatchDelete"
        >
          <LucideIcon name="trash-2" :size="14" style="margin-right: 6px" />
          {{ $t('tracker.listModal.batchDelete') }}
        </el-button>
        <el-dropdown @command="handleBatchMove">
          <el-button
            type="primary"
            size="small"
          >
            <LucideIcon name="list-filter" :size="14" style="margin-right: 6px" />
            {{ $t('tracker.pools.batchMoveTo') }} <LucideIcon name="chevron-down" :size="12" style="margin-left: 2px" />
          </el-button>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item
              v-for="pool in availablePools"
              :key="pool.value"
              :command="pool.value"
            >
              {{ pool.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
      </div>

      <!-- 关键词列表 -->
      <div v-loading="loading" class="keyword-list">
        <div
          v-for="item in keywordList"
          :key="item.keyword_id"
          class="keyword-card"
        >
          <el-checkbox
            v-model="item.selected"
            @change="handleSelectChange"
          />

          <div class="keyword-info">
            <div class="keyword-text" :title="item.keyword">
              {{ item.keyword }}
            </div>
            <div class="keyword-time">
              <LucideIcon name="clock" :size="12" style="margin-right: 2px" /> {{ item.create_time || $t('tracker.pools.unknownTime') }}
            </div>
          </div>

          <div class="keyword-actions">
            <el-dropdown @command="(command) => handleMove(item, command)">
              <el-button size="small" type="text">
                <LucideIcon name="list-filter" :size="13" style="margin-right: 4px" />{{ $t('tracker.pools.moveTo') }} <LucideIcon name="chevron-down" :size="12" style="margin-left: 2px" />
              </el-button>
              <el-dropdown-menu slot="dropdown">
                <el-dropdown-item
                  v-for="pool in availablePools"
                  :key="pool.value"
                  :command="pool.value"
                >
                  {{ pool.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </el-dropdown>

            <el-button
              size="small"
              type="text"
              class="btn-delete"
              icon="el-icon-delete"
              @click="handleDelete(item)"
            >
              {{ $t('tracker.search.delete') }}
            </el-button>
          </div>
        </div>

        <el-empty v-if="!loading && keywordList.length === 0" :description="$t('tracker.listModal.empty')" />
      </div>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          :current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>

    <!-- 快捷操作（左匹配）对话框：可复用组件，与关键词看板共用 -->
    <keyword-quick-action-dialog
      :visible.sync="quickActionVisible"
      :source-pool="quickActionSourcePool"
      :source-pool-label="quickActionSourcePoolLabel"
      @success="handleQuickActionSuccess"
    />

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleClose">{{ $t('tracker.pools.dialog.close') }}</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { moveKeywordToPool, deleteKeyword, batchMoveKeywords, batchDeleteKeywords, getPoolKeywords } from '@/api/tracker'
import type { PoolType } from '@/api/tracker'
import { poolLabel, poolOptions } from '@/utils/tracker'
import { apiResponseMessage } from '@/i18n'
import KeywordQuickActionDialog from './KeywordQuickActionDialog.vue'

interface KeywordItem {
  keyword_id: string
  keyword: string
  pool_type: string
  create_time: string
  selected?: boolean
}

interface SearchForm {
  keyword: string
  timeRange: string
  sortBy: string
}

interface Pagination {
  page: number
  pageSize: number
  total: number
}

@Component({
  name: 'KeywordListModal',
  components: {
    KeywordQuickActionDialog
  }
})
export default class KeywordListModal extends Vue {
  @Prop({ required: true }) visible!: boolean
  @Prop({ required: true }) poolType!: string
  @Prop({ default: () => [] }) keywords!: KeywordItem[]

  dialogVisible = false
  loading = false
  searchForm: SearchForm = {
    keyword: '',
    timeRange: '',
    sortBy: 'time_desc'
  }
  pagination: Pagination = {
    page: 1,
    pageSize: 20,
    total: 0
  }
  keywordList: KeywordItem[] = []

  // 快捷操作（左匹配）状态：实际逻辑在 KeywordQuickActionDialog 组件内
  quickActionVisible = false
  quickActionSourcePool: PoolType | '' = ''

  // 全选相关
  allSelected = false
  isIndeterminate = false

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.loadData()
    }
  }

  @Watch('dialogVisible')
  onDialogVisibleChange(val: boolean) {
    this.$emit('update:visible', val)
  }

  get dialogTitle(): string {
    const label = poolLabel(this.poolType) || this.$t('tracker.pools.poolFallback')
    return this.$t('tracker.listModal.titleSuffix', { pool: label })
  }

  get quickActionSourcePoolLabel(): string {
    return poolLabel(this.quickActionSourcePool) || this.$t('tracker.pools.poolFallback')
  }

  get availablePools() {
    // 双语 P6-3：排除当前池子，标签随语言切换响应式
    return poolOptions([this.poolType])
  }

  get selectedKeywords(): KeywordItem[] {
    return this.keywordList.filter(item => item.selected)
  }

  // 更新全选状态
  updateSelectAllStatus() {
    const selectedCount = this.selectedKeywords.length
    const totalCount = this.keywordList.length

    if (selectedCount === 0) {
      this.allSelected = false
      this.isIndeterminate = false
    } else if (selectedCount === totalCount && totalCount > 0) {
      this.allSelected = true
      this.isIndeterminate = false
    } else {
      this.allSelected = false
      this.isIndeterminate = true
    }
  }

  // 全选/取消全选
  handleSelectAll(checked: boolean) {
    this.keywordList.forEach(item => {
      item.selected = checked
    })
    this.isIndeterminate = false
    this.$forceUpdate()
  }

  async loadData() {
    this.loading = true
    try {
      // 调用API获取数据
      const response = await getPoolKeywords({
        pool_type: this.poolType as PoolType,
        keyword: this.searchForm.keyword,
        page: this.pagination.page,
        page_size: this.pagination.pageSize
      })

      if (response.code === '200' && response.data) {
        this.keywordList = response.data.list.map((kw: any) => ({
          ...kw,
          selected: false,
          create_time: kw.create_time || this.$t('tracker.pools.unknownTime')
        }))
        this.pagination.total = response.data.total || 0
        // 重置全选状态
        this.updateSelectAllStatus()
      } else {
        this.$message.error(apiResponseMessage(response, this.$t('tracker.listModal.loadFailed')))
        this.keywordList = []
        this.pagination.total = 0
      }
    } catch (error) {
      this.$message.error(this.$t('tracker.listModal.loadFailed'))
      console.error(error)
      this.keywordList = []
      this.pagination.total = 0
    } finally {
      this.loading = false
    }
  }

  handleSearch() {
    this.pagination.page = 1
    this.loadData()
  }

  handleSelectChange() {
    // 更新全选状态
    this.updateSelectAllStatus()
    // 触发响应式更新
    this.$forceUpdate()
  }

  handleSizeChange(size: number) {
    this.pagination.pageSize = size
    this.pagination.page = 1
    this.loadData()
  }

  handlePageChange(page: number) {
    this.pagination.page = page
    this.loadData()
  }

  async handleMove(item: KeywordItem, targetPool: string) {
    try {
      await moveKeywordToPool({
        keyword_id: item.keyword_id,
        target_pool: targetPool
      })
      this.$message.success(this.$t('tracker.listModal.moveSuccess', { pool: poolLabel(targetPool) }))
      this.$emit('refresh')
      this.loadData()
    } catch (error) {
      this.$message.error(this.$t('tracker.listModal.moveFailed'))
      console.error(error)
    }
  }

  async handleDelete(item: KeywordItem) {
    try {
      await this.$confirm(this.$t('tracker.listModal.deleteConfirm', { keyword: item.keyword }), this.$t('tracker.pools.dialog.notice'), {
        confirmButtonText: this.$t('tracker.pools.dialog.confirm'),
        cancelButtonText: this.$t('tracker.pools.dialog.cancel'),
        type: 'warning'
      })

      await deleteKeyword(item.keyword_id)
      this.$message.success(this.$t('tracker.listModal.deleteSuccess'))
      this.$emit('refresh')
      this.loadData()
    } catch (error) {
      if (error !== 'cancel') {
        this.$message.error(this.$t('tracker.listModal.deleteFailed'))
        console.error(error)
      }
    }
  }

  async handleBatchMove(targetPool: string) {
    const selectedIds = this.selectedKeywords.map(item => item.keyword_id)
    try {
      await batchMoveKeywords({
        keyword_ids: selectedIds,
        target_pool: targetPool
      })
      this.$message.success(this.$t('tracker.listModal.batchMoveSuccess', { count: selectedIds.length, pool: poolLabel(targetPool) }))
      this.$emit('refresh')
      this.loadData()
    } catch (error) {
      this.$message.error(this.$t('tracker.listModal.batchMoveFailed'))
      console.error(error)
    }
  }

  async handleBatchDelete() {
    const selectedIds = this.selectedKeywords.map(item => item.keyword_id)
    try {
      await this.$confirm(this.$t('tracker.listModal.batchDeleteConfirm', { count: selectedIds.length }), this.$t('tracker.pools.dialog.notice'), {
        confirmButtonText: this.$t('tracker.pools.dialog.confirm'),
        cancelButtonText: this.$t('tracker.pools.dialog.cancel'),
        type: 'warning'
      })

      await batchDeleteKeywords({ keyword_ids: selectedIds })
      this.$message.success(this.$t('tracker.listModal.batchDeleteSuccess', { count: selectedIds.length }))
      this.$emit('refresh')
      this.loadData()
    } catch (error) {
      if (error !== 'cancel') {
        this.$message.error(this.$t('tracker.listModal.batchDeleteFailed'))
        console.error(error)
      }
    }
  }

  // ==================== 快捷操作（左匹配） ====================

  openQuickAction() {
    this.quickActionSourcePool = this.poolType as PoolType
    this.quickActionVisible = true
  }

  handleQuickActionSuccess() {
    // 快捷操作执行成功后：通知父组件（看板）刷新池计数，并刷新本弹窗列表
    this.$emit('refresh')
    this.loadData()
  }

  handleClose() {
    this.dialogVisible = false
    this.searchForm = {
      keyword: '',
      timeRange: '',
      sortBy: 'time_desc'
    }
    this.pagination = {
      page: 1,
      pageSize: 20,
      total: 0
    }
  }
}
</script>

<style lang="scss" scoped>
.keyword-list-modal {
  ::v-deep .el-dialog {
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  }

  ::v-deep .el-dialog__header {
    background: linear-gradient(135deg, #f9fafb 0%, #ffffff 100%);
    border-bottom: 1px solid #e5e7eb;
    padding: 24px 28px;
  }

  ::v-deep .el-dialog__title {
    font-size: 22px;
    font-weight: 600;
  }

  ::v-deep .el-dialog__body {
    padding: 28px;
    max-height: 60vh;
    overflow-y: auto;
  }
}

.modal-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.search-bar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-end;

  .el-checkbox {
    flex-shrink: 0;
    font-weight: 500;
    margin-bottom: 1px;
  }

  .search-input-wrapper {
    flex: 1;
    min-width: 200px;
  }

  // 快捷操作按钮（搜索框右侧）
  .quick-action-btn {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 6px;
    color: var(--color-text-secondary);
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      color: var(--color-info);
      background: var(--color-info-light);
      transform: scale(1.05);
    }
  }

  .el-select {
    width: 150px;
    flex-shrink: 0;
  }

  ::v-deep .el-input__inner {
    height: 32px;
  }

  ::v-deep .el-input__prefix {
    display: flex;
    align-items: center;
  }

  ::v-deep .el-select .el-input__inner {
    height: 32px;
    line-height: 32px;
  }

  ::v-deep .el-select .el-input__prefix {
    display: flex;
    align-items: center;
  }

  ::v-deep .el-select .el-input__suffix {
    display: flex;
    align-items: center;
  }

  ::v-deep .el-select .el-icon-arrow-down {
    display: flex;
    align-items: center;
  }
}

.batch-actions {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  padding: 16px 20px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 2px solid #bfdbfe;
  border-radius: 10px;
  align-items: center;
  gap: 16px;
  animation: slideDown 0.2s ease;

  .batch-info {
    font-weight: 500;
    color: #1e40af;
  }
}

@keyframes slideDown {
  from {
    transform: translateY(-10px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.keyword-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 300px;
}

.keyword-card {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: #3b82f6;
    transform: scaleY(0);
    transition: transform 0.2s;
  }

  &:hover {
    border-color: #bfdbfe;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
    transform: translateX(4px);

    &::before {
      transform: scaleY(1);
    }

    .keyword-actions {
      opacity: 1;
    }
  }
}

.keyword-info {
  flex: 1;
  margin-left: 12px;
}

.keyword-text {
  font-size: 15px;
  font-weight: 500;
  color: #111827;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.keyword-time {
  font-size: 12px;
  color: #6b7280;
}

.keyword-actions {
  display: flex;
  gap: 10px;
  opacity: 0;
  transition: opacity 0.2s;

  .btn-delete {
    color: #ef4444;

    &:hover {
      background: #fef2f2;
    }
  }
}

.pagination-container {
  display: flex;
  justify-content: center;
  padding: 16px;
  background: #f9fafb;
  border-radius: 10px;
}
</style>
