<template>
  <div class="keywords-search-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-button
          icon="el-icon-arrow-left"
          @click="handleBack"
        >
          返回看板
        </el-button>
        <h1 class="search-title">搜索关键词</h1>
      </div>
      <div class="header-stats">
        <el-tag type="info" size="medium">
          共找到 <strong>{{ pagination.total }}</strong> 个关键词
        </el-tag>
      </div>
    </div>

    <!-- 搜索框 -->
    <div class="search-box-wrapper">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchForm.keyword"
          type="text"
          class="search-input"
          placeholder="输入关键词搜索..."
          @input="debouncedSearch"
          @keypress.enter="handleSearch"
        >
        <button class="search-button" @click="handleSearch">搜索</button>
      </div>
    </div>

    <!-- 高级筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="selectedPools"
        placeholder="选择池子"
        multiple
        collapse-tags
        clearable
        size="small"
        @change="handleSearch"
      >
        <el-option label="📋 候选池" value="candidate" />
        <el-option label="⏭️ 忽略池" value="ignored" />
        <el-option label="✅ 成功池" value="success" />
        <el-option label="❌ 失败池" value="failed" />
      </el-select>

      <el-select
        v-model="searchForm.timeRange"
        placeholder="时间范围"
        clearable
        size="small"
        @change="handleSearch"
      >
        <el-option label="📊 全部" value="" />
        <el-option label="📅 今天" value="today" />
        <el-option label="📆 本周" value="week" />
        <el-option label="🗓️ 本月" value="month" />
      </el-select>

      <el-select
        v-model="searchForm.sortBy"
        placeholder="排序方式"
        size="small"
        @change="handleSearch"
      >
        <el-option label="🕐 添加时间 ↓" value="time_desc" />
        <el-option label="🕐 添加时间 ↑" value="time_asc" />
        <el-option label="🔤 关键词 A-Z" value="name_asc" />
      </el-select>
    </div>

    <!-- 搜索结果表格 -->
    <div v-loading="loading" class="results-table-wrapper">
      <table v-if="searchResults.length > 0" class="results-table">
        <thead>
          <tr>
            <th width="80">序号</th>
            <th>关键词</th>
            <th width="120">所在池子</th>
            <th width="180">添加时间</th>
            <th width="260">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, index) in searchResults"
            :key="item.keyword_id"
          >
            <td>{{ (pagination.page - 1) * pagination.pageSize + index + 1 }}</td>
            <td>
              <span v-html="highlightKeyword(item.keyword)"></span>
            </td>
            <td>
              <span class="pool-badge" :class="item.pool_type">
                {{ item.pool_label }}
              </span>
            </td>
            <td>{{ item.create_time || '未知时间' }}</td>
            <td>
              <div class="action-buttons">
                <button class="action-btn" @click="handleViewDetail(item)">查看详情</button>
                <el-dropdown @command="(command) => handleMove(item, command)">
                  <button class="action-btn">
                    移动到池子 <i class="el-icon-arrow-down" />
                  </button>
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
                <button class="action-btn btn-delete" @click="handleDelete(item)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 空状态 -->
      <div v-if="!loading && searchResults.length === 0" class="empty-state">
        <div class="empty-icon">🔍</div>
        <p class="empty-text">暂无搜索结果，请尝试调整搜索条件或关键词</p>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="searchResults.length > 0" class="pagination">
      <el-pagination
        :current-page="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { searchAllPools, moveKeywordToPool, deleteKeyword, type SearchResultItem, type PoolType } from '@/api/tracker'
import { extractErrorMessage, debounce } from '@/utils/tracker'

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
  name: 'KeywordsSearchPage'
})
export default class KeywordsSearchPage extends Vue {
  loading = false
  searchForm: SearchForm = {
    keyword: '',
    timeRange: '',
    sortBy: 'time_desc'
  }
  selectedPools: PoolType[] = []
  pagination: Pagination = {
    page: 1,
    pageSize: 20,
    total: 0
  }
  searchResults: SearchResultItem[] = []

  // 池子配置
  poolConfig = {
    candidate: { label: '📋 候选池', value: 'candidate' as PoolType },
    ignored: { label: '⏭️ 忽略池', value: 'ignored' as PoolType },
    success: { label: '✅ 成功池', value: 'success' as PoolType },
    failed: { label: '❌ 失败池', value: 'failed' as PoolType }
  }

  mounted() {
    // 从路由参数获取初始搜索关键词
    const keyword = this.$route.query.keyword as string
    if (keyword) {
      this.searchForm.keyword = keyword
    }
    this.loadData()

    // 添加键盘快捷键支持
    document.addEventListener('keydown', this.handleKeyboard)
  }

  beforeDestroy() {
    // 清理防抖定时器,避免内存泄漏
    // 注意: 使用debounce工具函数后,不需要手动清理,因为内部已处理

    // 移除键盘事件监听
    document.removeEventListener('keydown', this.handleKeyboard)
  }

  // 键盘快捷键处理
  handleKeyboard(event: KeyboardEvent) {
    // Ctrl/Cmd + F: 聚焦搜索框
    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
      event.preventDefault()
      const searchInput = this.$el.querySelector('.search-input') as HTMLInputElement
      if (searchInput) {
        searchInput.focus()
        searchInput.select()
      }
    }

    // Escape: 清空搜索
    if (event.key === 'Escape' && this.searchForm.keyword) {
      this.searchForm.keyword = ''
      this.handleSearch()
    }

    // Enter: 执行搜索(已在模板中处理)
  }

  get availablePools() {
    return Object.values(this.poolConfig)
  }

  async loadData() {
    this.loading = true
    try {
      // 构建请求参数
      const params: any = {
        page: this.pagination.page,
        page_size: this.pagination.pageSize
      }

      // 关键词筛选
      if (this.searchForm.keyword) {
        params.keyword = this.searchForm.keyword
      }

      // 池子类型筛选
      if (this.selectedPools.length > 0) {
        params.pool_types = this.selectedPools.join(',')
      }

      // 时间范围筛选
      if (this.searchForm.timeRange) {
        params.time_range = this.searchForm.timeRange
      }

      // 排序方式
      if (this.searchForm.sortBy) {
        params.sort_by = this.searchForm.sortBy
      }

      const response = await searchAllPools(params)

      if (response.code === '200' && response.data) {
        // 添加pool_label默认值,确保类型安全
        this.searchResults = (response.data.list || []).map(item => ({
          ...item,
          pool_label: item.pool_label || this.getPoolLabel(item.pool_type)
        }))
        this.pagination.total = response.data.total || 0
      } else {
        this.$message.error(response.msg || '搜索失败')
        this.searchResults = []
        this.pagination.total = 0
      }
    } catch (error) {
      console.error('搜索失败:', error)
      const errorMsg = extractErrorMessage(error)
      this.$message.error(errorMsg || '搜索失败')
      this.searchResults = []
      this.pagination.total = 0
    } finally {
      this.loading = false
    }
  }

  // 防抖搜索 (使用统一的防抖工具函数)
  debouncedSearch = debounce(this.handleSearch, 500)

  handleSearch() {
    this.pagination.page = 1
    this.loadData()
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

  handleBack() {
    this.$router.push('/tracker/keywords-board')
  }

  handleViewDetail(item: SearchResultItem) {
    // 跳转到关键词看板并定位到对应池子
    this.$router.push({
      path: '/tracker/keywords-board',
      query: {
        highlight: item.keyword_id
      }
    })
  }

  async handleMove(item: SearchResultItem, targetPool: PoolType) {
    try {
      await moveKeywordToPool({
        keyword_id: item.keyword_id,
        target_pool: targetPool
      })
      this.$message.success(`关键词已移动到 ${this.poolConfig[targetPool].label}`)
      this.loadData()
    } catch (error) {
      console.error('移动关键词失败:', error)
      const errorMsg = extractErrorMessage(error)
      this.$message.error(errorMsg || '移动失败')
    }
  }

  async handleDelete(item: SearchResultItem) {
    try {
      await this.$confirm(`确定要删除关键词 "${item.keyword}" 吗？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })

      await deleteKeyword(item.keyword_id)
      this.$message.success('删除成功')
      this.loadData()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('删除关键词失败:', error)
        const errorMsg = extractErrorMessage(error)
        this.$message.error(errorMsg || '删除失败')
      }
    }
  }

  /**
   * 获取池子标签类型
   */
  getPoolTagType(poolType: PoolType): string {
    const typeMap: Record<PoolType, string> = {
      candidate: '',
      ignored: 'info',
      success: 'success',
      failed: 'danger'
    }
    return typeMap[poolType] || ''
  }

  /**
   * 获取池子显示标签
   */
  getPoolLabel(poolType: PoolType): string {
    const pool = this.poolConfig[poolType]
    return pool?.label || poolType
  }

  /**
   * 高亮关键词中的搜索词（防 XSS）
   */
  highlightKeyword(keyword: string): string {
    // 先转义 HTML，避免 XSS 攻击
    const escapedKeyword = this.escapeHtml(keyword)

    // 如果没有搜索词，直接返回转义后的文本
    if (!this.searchForm.keyword) {
      return escapedKeyword
    }

    // 转义搜索词
    const escapedSearchTerm = this.escapeHtml(this.searchForm.keyword)

    // 使用正则表达式进行不区分大小写的替换
    const regex = new RegExp(`(${escapedSearchTerm})`, 'gi')
    return escapedKeyword.replace(regex, '<mark>$1</mark>')
  }

  /**
   * HTML 转义，防止 XSS 攻击
   */
  private escapeHtml(text: string): string {
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
  }
}
</script>

<style lang="scss" scoped>
.keywords-search-page {
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
  min-height: 100vh;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);

  .header-left {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
  }

  .search-title {
    font-size: var(--font-size-3xl);
    font-weight: var(--font-weight-bold);
    margin: 0;
    background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
}

// 搜索框样式
.search-box-wrapper {
  max-width: 600px;
  margin: 0 auto var(--spacing-xl);
}

.search-box {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  background: var(--color-bg-primary);
  border: 2px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-sm) var(--spacing-md);
  transition: all 0.3s;

  &:focus-within {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1);
  }
}

.search-icon {
  font-size: 20px;
  color: var(--color-text-secondary);
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: var(--font-size-md);
  padding: var(--spacing-sm);
  background: transparent;
  color: var(--color-text-primary);

  &::placeholder {
    color: var(--color-text-secondary);
  }
}

.search-button {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  color: white;
  border: none;
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
}

// 筛选栏
.filter-bar {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);

  .el-select {
    width: 180px;
  }
}

// 表格容器
.results-table-wrapper {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  min-height: 400px;
}

.results-table {
  width: 100%;
  border-collapse: collapse;

  thead {
    background: var(--color-bg-secondary);
  }

  th {
    padding: var(--spacing-md);
    text-align: left;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-secondary);
    border-bottom: 2px solid var(--color-border-primary);
    font-size: var(--font-size-sm);
  }

  td {
    padding: var(--spacing-md);
    border-bottom: 1px solid var(--color-border-primary);
    color: var(--color-text-primary);
  }

  tbody tr {
    transition: background 0.2s;

    &:hover {
      background: var(--color-bg-secondary);
    }
  }
}

// 池子徽章
.pool-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);

  &.candidate {
    background: rgba(59, 130, 246, 0.1);
    color: #1E40AF;
  }

  &.ignored {
    background: rgba(107, 114, 128, 0.1);
    color: #374151;
  }

  &.success {
    background: rgba(16, 185, 129, 0.1);
    color: #065F46;
  }

  &.failed {
    background: rgba(239, 68, 68, 0.1);
    color: #991B1B;
  }
}

// 操作按钮
.action-buttons {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.action-btn {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-primary);
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 4px;

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  &.btn-delete {
    &:hover {
      border-color: var(--color-error);
      color: var(--color-error);
    }
  }
}

// 空状态
.empty-state {
  text-align: center;
  padding: var(--spacing-xl);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: var(--spacing-md);
}

.empty-text {
  font-size: var(--font-size-lg);
  color: var(--color-text-secondary);
}

// 分页
.pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  margin-top: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
}

// 高亮搜索关键词
::v-deep mark {
  background: #fef08a;
  color: #111827;
  padding: 2px 4px;
  border-radius: 4px;
  font-weight: var(--font-weight-semibold);
}

// 响应式设计
@media (max-width: 768px) {
  .keywords-search-page {
    padding: var(--spacing-md);
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;

    .el-select {
      width: 100%;
    }
  }

  .results-table {
    font-size: var(--font-size-xs);

    th,
    td {
      padding: var(--spacing-sm);
    }
  }

  .action-buttons {
    flex-direction: column;
  }
}
</style>
