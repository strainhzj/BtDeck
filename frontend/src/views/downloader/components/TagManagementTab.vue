<template>
  <div class="tag-management-tab">
    <!-- 新增模式提示 -->
    <div v-if="!downloader" class="empty-state">
      <LucideIcon class="empty-icon" name="lock-keyhole" :size="42" :stroke-width="1.4" />
      <h3>请先保存基本信息</h3>
      <p>标签/分类管理需要下载器创建后才能使用</p>
    </div>

    <!-- 标签管理内容 -->
    <div v-else class="tag-content">
      <!-- 工具栏 -->
      <div class="toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索标签名称"
            style="width: 280px;"
            @input="handleSearchInput"
          >
            <template slot="prefix"><LucideIcon name="search" :size="14" /></template>
            <template slot="suffix">
              <button v-if="searchKeyword" class="input-clear" type="button" aria-label="清空搜索" @click="handleSearchClear">
                <LucideIcon name="x" :size="13" />
              </button>
            </template>
          </el-input>
        </div>
        <div class="toolbar-right">
          <el-button
            type="primary"
            :disabled="downloader === null"
            @click="handleCreate"
          >
            <LucideIcon name="plus" :size="14" />
            新增标签
          </el-button>
        </div>
      </div>

      <!-- 类型筛选标签页 -->
      <div class="type-tabs">
        <div
          v-for="type in typeOptions"
          :key="type.value"
          :class="['type-tab', {active: activeType === type.value}]"
          @click="handleTypeChange(type.value)"
        >
          <LucideIcon class="type-icon" :name="type.value === 'category' ? 'folder-open' : 'tag'" :size="14" />
          <span>{{ type.label }}</span>
          <span class="count">({{ getTypeCount(type.value) }})</span>
        </div>
      </div>

      <!-- 排序选项 -->
      <div class="sort-bar">
        <span class="sort-label">排序：</span>
        <el-select
          v-model="sortBy"
          size="small"
          @change="loadTags"
        >
          <el-option label="创建时间" value="created_at" />
          <el-option label="标签名称" value="tag_name" />
        </el-select>
        <el-button
          size="mini"
          @click="toggleSortOrder"
        >
          <LucideIcon :name="sortOrder === 'asc' ? 'arrow-down' : 'arrow-up'" :size="13" />
          {{ sortOrder === 'asc' ? '升序' : '降序' }}
        </el-button>
      </div>

      <!-- 标签列表 -->
      <div
        v-loading="loading"
        class="tag-list"
        element-loading-text="加载中..."
      >
        <!-- 空状态 -->
        <div v-if="filteredTags.length === 0 && !loading" class="empty-tags">
          <LucideIcon class="empty-icon" :name="searchKeyword ? 'search-x' : 'tags'" :size="42" :stroke-width="1.4" />
          <p>{{ searchKeyword ? '未找到匹配的标签' : '暂无标签数据' }}</p>
        </div>

        <!-- 标签网格 -->
        <div v-else class="tag-grid">
          <div
            v-for="tag in filteredTags"
            :key="tag.tag_id"
            :class="['tag-card', `tag-${tag.tag_type}`]"
            :style="{borderLeftColor: tag.color || 'var(--color-primary)'}"
          >
            <div class="tag-header">
              <div class="tag-type-badge">
                <LucideIcon class="badge-icon" :name="tag.tag_type === 'category' ? 'folder-open' : 'tag'" :size="13" />
                <span>{{ tag.tag_type === 'category' ? '分类' : '标签' }}</span>
              </div>
              <el-dropdown trigger="click" @command="(cmd) => handleTagAction(cmd, tag)">
                <span class="tag-menu-trigger">
                  <LucideIcon name="ellipsis-vertical" :size="15" />
                </span>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="edit">
                    <LucideIcon class="menu-icon" name="pencil" :size="13" />
                    编辑
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <LucideIcon class="menu-icon danger" name="trash-2" :size="13" />
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </el-dropdown>
            </div>
            <div class="tag-body">
              <div class="tag-name" :style="{color: tag.color || 'var(--color-text-primary)'}">
                {{ tag.tag_name }}
              </div>
            </div>
            <div class="tag-footer">
              <span class="tag-time">创建于 {{ formatTime(tag.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      :visible.sync="showDialog"
      :title="dialogTitle"
      width="500px"
      :before-close="handleDialogClose"
      :close-on-click-modal="false"
      modal-append-to-body
      append-to-body
    >
      <el-form
        ref="tagFormRef"
        :model="tagForm"
        :rules="tagFormRules"
        label-width="100px"
      >
        <el-form-item label="标签名称" prop="tag_name">
          <el-input
            v-model="tagForm.tag_name"
            placeholder="请输入标签名称"
            maxlength="255"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="标签类型" prop="tag_type">
          <el-radio-group v-model="tagForm.tag_type">
            <el-radio label="category">分类</el-radio>
            <el-radio label="tag">标签</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="颜色" prop="color">
          <el-color-picker
            v-model="tagForm.color"
            :predefine="predefineColors"
            show-alpha
            size="medium"
          />
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :disabled="submitting" @click="handleSubmit">
          <LucideIcon :name="submitting ? 'refresh-cw' : 'save'" :size="14" :class="{'is-spinning': submitting}" />
          {{ editingTag ? '保存' : '创建' }}
        </el-button>
      </div>
    </el-dialog>

    <!-- 批量删除确认对话框 -->
    <el-dialog
      :visible.sync="showBatchDeleteDialog"
      title="批量删除确认"
      width="400px"
    >
      <div class="batch-delete-content">
        <LucideIcon class="warning-icon" name="alert-triangle" :size="40" :stroke-width="1.5" />
        <p>确定要删除选中的 <strong>{{ selectedTags.length }}</strong> 个标签吗？</p>
        <p class="warning-text">此操作不可撤销，删除后将无法恢复</p>
      </div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="showBatchDeleteDialog = false">取消</el-button>
        <el-button type="danger" :disabled="batchDeleting" @click="handleConfirmBatchDelete">
          <LucideIcon :name="batchDeleting ? 'refresh-cw' : 'trash-2'" :size="14" :class="{'is-spinning': batchDeleting}" />
          确定删除
        </el-button>
      </div>
    </el-dialog>

    <!-- 分类选择弹窗 -->
    <el-dialog
      :visible.sync="showCategorySelectDialog"
      title="选择目标分类"
      width="500px"
      :before-close="handleCancelDeleteCategory"
      :close-on-click-modal="false"
      append-to-body
    >
      <div class="category-select-content">
        <LucideIcon class="warning-icon" name="alert-triangle" :size="40" :stroke-width="1.5" />
        <p class="dialog-title">
          分类"<strong>{{ deletingTag ? deletingTag.tag_name : '' }}</strong>"下还有种子，
        </p>
        <p class="dialog-desc">请选择将这些种子转移到哪个分类：</p>
        
        <el-form label-width="80px" style="margin-top: 20px;">
          <el-form-item label="目标分类">
            <el-select
              v-model="targetCategory"
              placeholder="选择目标分类（不选则转移到未分类）"
              clearable
              style="width: 100%;"
            >
              <el-option label="未分类" value=""></el-option>
              <el-option
                v-for="cat in allTags.filter(t => t.tag_type === 'category' && t.tag_id !== deletingTag?.tag_id)"
                :key="cat.tag_id"
                :label="cat.tag_name"
                :value="cat.tag_name"
              >
                <span>{{ cat.tag_name }}</span>
              </el-option>
            </el-select>
          </el-form-item>
        </el-form>
      </div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="handleCancelDeleteCategory">取消</el-button>
        <el-button type="primary" :disabled="transferring" @click="handleConfirmDeleteCategory">
          <LucideIcon :name="transferring ? 'refresh-cw' : 'folder-sync'" :size="14" :class="{'is-spinning': transferring}" />
          确定转移并删除
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import { Downloader } from '../types'
import {
  getTagList,
  createTag,
  updateTag,
  deleteTag,
  batchDeleteTags,
  TorrentTag,
  CreateTagRequest,
  UpdateTagRequest
} from '@/api/tag-management'
import { Message, MessageBox } from 'element-ui'

interface FormDataHost extends Vue {
  formData?: Record<string, unknown>
}

@Component({
  name: 'TagManagementTab'
})
export default class TagManagementTab extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null

  // ==================== 数据状态 ====================

  private allTags: TorrentTag[] = []
  private loading = false
  private submitting = false
  private batchDeleting = false

  // 搜索和筛选
  private searchKeyword = ''
  private activeType: 'category' | 'tag' | 'all' = 'all'
  private sortBy: 'created_at' | 'tag_name' = 'created_at'
  private sortOrder: 'asc' | 'desc' = 'desc'

  // 对话框状态
  private showDialog = false
  private showBatchDeleteDialog = false
  private showCategorySelectDialog = false
  private deletingTag: TorrentTag | null = null
  private targetCategory = ''
  private categoryList: TorrentTag[] = []
  private transferring = false

  private editingTag: TorrentTag | null = null
  private selectedTags: TorrentTag[] = []

  // 表单数据
  private tagForm: CreateTagRequest & { tag_id?: string } = {
    downloader_id: '',
    tag_name: '',
    tag_type: 'tag',
    color: '#409EFF'
  }

  // 预定义颜色
  private predefineColors = [
    '#409EFF',
    '#67C23A',
    '#E6A23C',
    '#F56C6C',
    '#909399',
    '#C0C4EB',
    '#E6EEF1',
    '#F4E4A5',
    '#FF9800',
    '#FFB300',
    '#4CAF50',
    '#00BCD4'
  ]

  // ==================== 类型选项 ====================

  private typeOptions = [
    { label: '全部', value: 'all' as const },
    { label: '分类', value: 'category' as const },
    { label: '标签', value: 'tag' as const }
  ]

  // ==================== 计算属性 ====================

  get dialogTitle(): string {
    return this.editingTag ? '编辑标签' : '新增标签'
  }

  get filteredTags(): TorrentTag[] {
    let tags = [...this.allTags]

    // 类型筛选
    if (this.activeType !== 'all') {
      tags = tags.filter(tag => tag.tag_type === this.activeType)
    }

    // 搜索过滤
    if (this.searchKeyword.trim()) {
      const keyword = this.searchKeyword.trim().toLowerCase()
      tags = tags.filter(tag =>
        tag.tag_name.toLowerCase().includes(keyword)
      )
    }

    return tags
  }

  get tagFormRules() {
    return {
      tag_name: [
        { required: true, message: '请输入标签名称', trigger: 'blur' },
        { min: 1, max: 255, message: '长度为1-255个字符', trigger: 'blur' }
      ],
      tag_type: [
        { required: true, message: '请选择标签类型', trigger: 'change' }
      ]
    }
  }

  // ==================== 生命周期 ====================

  @Watch('downloader', { immediate: true })
  onDownloaderChange() {
    if (this.downloader) {
      this.loadTags()
    }
  }

  // ==================== 方法 ====================

  /**
   * 获取类型计数
   */
  private getTypeCount(type: 'all' | 'category' | 'tag'): number {
    if (type === 'all') {
      return this.allTags.length
    }
    return this.allTags.filter(tag => tag.tag_type === type).length
  }

  /**
   * 加载标签列表
   */
  private async loadTags() {
    if (!this.downloader) return

    this.loading = true
    try {
      const response = await getTagList({
        downloader_id: this.downloader.id || this.downloader.downloaderId,
        tag_type: this.activeType === 'all' ? undefined : this.activeType,
        search: this.searchKeyword || undefined,
        sort_by: this.sortBy,
        sort_order: this.sortOrder
      })

      if (response.code === '200') {
        this.allTags = response.data.list || []
      }
    } catch (error) {
      console.error('加载标签列表失败:', error)
      Message.error('加载标签列表失败')
    } finally {
      this.loading = false
    }
  }

  /**
   * 搜索输入处理（防抖）
   */
  private searchTimer: number | null = null
  private handleSearchInput(_value: string) {
    if (this.searchTimer) {
      clearTimeout(this.searchTimer)
    }
    this.searchTimer = setTimeout(() => {
      this.loadTags()
    }, 300) as unknown as number
  }

  private handleSearchClear() {
    this.searchKeyword = ''
    this.loadTags()
  }

  /**
   * 类型切换
   */
  private handleTypeChange(type: 'all' | 'category' | 'tag') {
    this.activeType = type
    this.loadTags()
  }

  /**
   * 排序切换
   */
  private toggleSortOrder() {
    this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc'
    this.loadTags()
  }

  /**
   * 创建标签
   */
  private handleCreate() {
    this.editingTag = null
    this.tagForm = {
      downloader_id: this.downloader.id || this.downloader.downloaderId,
      tag_name: '',
      tag_type: 'tag',
      color: '#409EFF'
    }
    // 使用$nextTick确保Vue正确响应showDialog的变化
    this.$nextTick(() => {
      this.showDialog = true
    })
  }

  /**
   * 编辑标签
   */
  private handleTagAction(command: string, tag: TorrentTag) {
    if (command === 'edit') {
      this.editingTag = tag
      this.tagForm = {
        tag_id: tag.tag_id,
        downloader_id: this.downloader.id || this.downloader.downloaderId,
        tag_name: tag.tag_name,
        tag_type: tag.tag_type,
        color: tag.color || '#409EFF'
      }
      // 使用$nextTick确保Vue正确响应showDialog的变化
      this.$nextTick(() => {
        this.showDialog = true
      })
    } else if (command === 'delete') {
      this.handleDelete(tag)
    }
  }

  /**
   * 删除标签
   */
  private handleDelete(tag: TorrentTag) {
    // 如果是分类，显示分类选择弹窗
    if (tag.tag_type === 'category') {
      this.deletingTag = tag
      this.targetCategory = ''
      this.showCategorySelectDialog = true
    } else {
      // 标签直接删除确认
      MessageBox.confirm(
        `确定要删除标签"${tag.tag_name}"吗？`,
        '删除确认',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      ).then(async() => {
        try {
          await deleteTag(tag.tag_id)
          Message.success('删除成功')
          await this.loadTags()
        } catch (error) {
          console.error('删除失败:', error)
          Message.error('删除失败')
        }
      }).catch(() => {
        // 取消删除
      })
    }
  }


  /**
   * 确认删除分类（选择目标分类后调用）
   */
  private async handleConfirmDeleteCategory() {
    if (!this.deletingTag) return

    this.transferring = true
    try {
      await deleteTag(this.deletingTag.tag_id, {
        target_category: this.targetCategory
      })
      Message.success('删除成功')
      this.showCategorySelectDialog = false
      await this.loadTags()
    } catch (error) {
      console.error('删除失败:', error)
      Message.error('删除失败')
    } finally {
      this.transferring = false
    }
  }

  /**
   * 取消分类删除
   */
  private handleCancelDeleteCategory() {
    this.showCategorySelectDialog = false
    this.deletingTag = null
    this.targetCategory = ''
  }

  /**
   * 批量删除
   */
  private handleBatchDelete() {
    if (this.selectedTags.length === 0) {
      Message.warning('请先选择要删除的标签')
      return
    }
    this.showBatchDeleteDialog = true
  }

  private async handleConfirmBatchDelete() {
    this.batchDeleting = true
    try {
      const tagIds = this.selectedTags.map(tag => tag.tag_id)
      await batchDeleteTags(tagIds)
      Message.success(`成功删除 ${tagIds.length} 个标签`)
      this.showBatchDeleteDialog = false
      this.selectedTags = []
      await this.loadTags()
    } catch (error) {
      console.error('批量删除失败:', error)
      Message.error('批量删除失败')
    } finally {
      this.batchDeleting = false
    }
  }

  /**
   * 提交表单
   */
  private async handleSubmit() {
    const form = this.$refs.tagFormRef as ElForm
    try {
      await form.validate()

      this.submitting = true

      if (this.editingTag) {
        // 编辑模式
        const updateData: UpdateTagRequest = {
          tag_name: this.tagForm.tag_name,
          color: this.tagForm.color
        }
        if (this.tagForm.tag_id === undefined) {
          throw new Error('Missing tag_id for tag update')
        }
        await updateTag(this.tagForm.tag_id, updateData)
        Message.success('更新成功')
      } else {
        // 创建模式
        await createTag(this.tagForm as CreateTagRequest)
        Message.success('创建成功')
      }

      this.showDialog = false
      await this.loadTags()
    } catch (error) {
      if (error !== false) { // 表单验证失败时 error 为 false
        console.error('提交失败:', error)
        Message.error('操作失败')
      }
    } finally {
      this.submitting = false
    }
  }

  /**
   * 对话框关闭前
   */
  private handleDialogClose() {
    if (this.submitting) {
      return false // 提交中不允许关闭
    }
    this.showDialog = false
  }

  /**
   * 格式化时间
   */
  private formatTime(timeStr: string): string {
    if (!timeStr) return '-'
    const date = new Date(timeStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days} 天前`
    if (days < 30) return `${Math.floor(days / 7)} 周前`
    if (days < 365) return `${Math.floor(days / 30)} 月前`
    return `${Math.floor(days / 365)} 年前`
  }

  /**
   * 获取表单引用
   */
  get tagFormRef(): ElForm {
    return this.$refs.tagFormRef as ElForm
  }

  /**
   * 获取父组件方法
   */
  get formData(): Record<string, unknown> {
    const host = this.$parent.$parent as FormDataHost | undefined
    return host?.formData || {}
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.tag-management-tab {
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: 0;
  text-align: left;
}

// ==================== 空状态 ====================
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl) var(--spacing-xl);
  min-height: 400px;
  text-align: center;

  .empty-icon {
    width: 64px;
    height: 64px;
    color: var(--color-text-tertiary);
    margin-bottom: var(--spacing-lg);
    opacity: 0.5;
  }

  h3 {
    font-size: 18px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
    margin: 0 0 var(--spacing-sm) 0;
  }

  p {
    font-size: 14px;
    color: var(--color-text-secondary);
    margin: 0;
  }
}

// ==================== 工具栏 ====================
.tag-content {
  .toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-lg);
    padding: var(--spacing-md);
    background: var(--color-bg-secondary);
    border-radius: var(--radius-lg);
  }

  .toolbar-left,
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
  }
}

// ==================== 类型筛选 ====================
.type-tabs {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  padding: 0 var(--spacing-md);

  .type-tab {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--color-bg-tertiary);
    border: 1px solid var(--color-border-primary);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-base);
    font-size: 14px;
    color: var(--color-text-secondary);

    .type-icon {
      width: 16px;
      height: 16px;
      color: var(--color-text-tertiary);
    }

    .count {
      font-size: 12px;
      color: var(--color-text-tertiary);
    }

    &:hover {
      border-color: var(--color-primary);
      color: var(--color-primary);
    }

    &.active {
      background: var(--color-primary);
      border-color: var(--color-primary);
      color: white;

      .type-icon,
      .count {
        color: white;
      }
    }
  }
}

// ==================== 排序栏 ====================
.sort-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);

  .sort-label {
    font-size: 13px;
    color: var(--color-text-secondary);
  }

  ::v-deep .el-select {
    width: 140px;
  }
}

// ==================== 标签列表 ====================
.tag-list {
  min-height: 300px;

  .empty-tags {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--spacing-xxl) var(--spacing-xl);
    min-height: 300px;
    text-align: center;

    .empty-icon {
      width: 64px;
      height: 64px;
      color: var(--color-text-tertiary);
      margin-bottom: var(--spacing-lg);
      opacity: 0.4;
    }

    p {
      font-size: 14px;
      color: var(--color-text-secondary);
      margin: 0;
    }
  }

  .tag-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: var(--spacing-md);
  }
}

// ==================== 标签卡片 ====================
.tag-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-left: 4px solid;
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  transition: all var(--transition-base);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);

  &:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--color-border-focus);
  }

  .tag-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .tag-type-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: var(--font-weight-medium);

    .tag-card[data-tag-type="category"] & {
      background: var(--color-warning-light);
      color: var(--color-warning);
    }

    .tag-card[data-tag-type="tag"] & {
      background: var(--color-primary-light);
      color: var(--color-primary);
    }

    .badge-icon {
      width: 14px;
      height: 14px;
    }

    span {
      font-size: 12px;
    }
  }

  .tag-menu-trigger {
    cursor: pointer;
    padding: 4px;
    border-radius: var(--radius-sm);
    transition: all var(--transition-base);
    color: var(--color-text-tertiary);

    svg {
      width: 16px;
      height: 16px;
    }

    &:hover {
      background: var(--color-bg-tertiary);
      color: var(--color-text-primary);
    }
  }

  .tag-body {
    .tag-name {
      font-size: 16px;
      font-weight: var(--font-weight-semibold);
      word-break: break-word;
    }
  }

  .tag-footer {
    .tag-time {
      font-size: 12px;
      color: var(--color-text-tertiary);
    }
  }
}

// ==================== 对话框 ====================
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

// ==================== 批量删除对话框 ====================
.batch-delete-content {
  text-align: center;
  padding: var(--spacing-lg) 0;

  .warning-icon {
    width: 48px;
    height: 48px;
    color: var(--color-warning);
    margin-bottom: var(--spacing-md);
  }

  p {
    font-size: 14px;
    color: var(--color-text-primary);
    margin: var(--spacing-sm) 0;

    &.warning-text {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }

  strong {
    font-weight: var(--font-weight-semibold);
    color: var(--color-error);
  }
}

// ==================== 下拉菜单 ====================
::v-deep .el-dropdown-menu {
  .menu-icon {
    width: 14px;
    height: 14px;
    margin-right: 8px;
    color: var(--color-text-secondary);

    &.danger {
      color: var(--color-error);
    }
  }

  .el-dropdown-menu__item {
    display: flex;
    align-items: center;
    padding: 8px 16px;

    &:hover {
      background: var(--color-bg-secondary);
    }
  }
}

// ==================== 分类选择弹窗 ====================
.category-select-content {
  text-align: center;
  padding: var(--spacing-lg) 0;

  .warning-icon {
    width: 48px;
    height: 48px;
    color: var(--color-warning);
    margin-bottom: var(--spacing-md);
  }

  .dialog-title {
    font-size: 16px;
    color: var(--color-text-primary);
    margin: var(--spacing-sm) 0;

    strong {
      font-weight: var(--font-weight-semibold);
      color: var(--color-error);
    }
  }

  .dialog-desc {
    font-size: 14px;
    color: var(--color-text-secondary);
    margin: var(--spacing-sm) 0;
  }
}

// ==================== 下拉菜单 ====================
::v-deep .el-dropdown-menu {
  .menu-icon {
    width: 14px;
    height: 14px;
    margin-right: 8px;
    color: var(--color-text-secondary);

    &.danger {
      color: var(--color-error);
    }
  }

  .el-dropdown-menu__item {
    display: flex;
    align-items: center;
    padding: 8px 16px;

    &:hover {
      background: var(--color-bg-secondary);
    }
  }
}

// Compact catalog treatment for dense tag operations.
.empty-state {
  min-height: 220px;
  padding: 38px 24px;

  .empty-icon {
    width: 42px;
    height: 42px;
    margin-bottom: 10px;
  }

  h3 {
    margin-bottom: 4px;
    font-size: 14px;
  }

  p {
    font-size: 10px;
  }
}

.toolbar {
  margin-bottom: 8px;
  padding: 8px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  background:
    linear-gradient(110deg, rgba(var(--color-primary-rgb), 0.06), transparent 42%),
    rgba(255, 255, 255, 0.66);
}

.toolbar ::v-deep .el-input__inner {
  height: 32px;
  font-size: 10px;
}

.toolbar ::v-deep .el-input__prefix,
.toolbar ::v-deep .el-input__suffix {
  display: inline-flex;
  align-items: center;
}

.toolbar ::v-deep .el-button {
  height: 32px;
  padding: 0 11px;
  font-size: 9px;
}

.toolbar ::v-deep .el-button span,
.sort-bar ::v-deep .el-button span,
.dialog-footer ::v-deep .el-button span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.input-clear {
  display: inline-flex;
  padding: 3px;
  border: 0;
  color: var(--color-text-tertiary);
  background: transparent;
  cursor: pointer;
}

.type-tabs {
  gap: 5px;
  margin-bottom: 8px;
}

.type-tab {
  min-height: 32px;
  padding: 0 11px;
  border-radius: 8px;
  font-size: 10px;

  .count {
    font-family: var(--font-mono);
    font-size: 8px;
  }
}

.sort-bar {
  min-height: 38px;
  margin-bottom: 8px;
  padding: 4px 8px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.56);

  .sort-label {
    font-size: 9px;
  }
}

.sort-bar ::v-deep .el-button {
  height: 28px;
  padding: 0 8px;
  font-size: 9px;
}

.tag-list {
  min-height: 208px;

  .empty-tags {
    min-height: 208px;
    padding: 36px 20px;

    .empty-icon {
      width: 42px;
      height: 42px;
      margin-bottom: 9px;
    }

    p {
      font-size: 10px;
    }
  }

  .tag-grid {
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 7px;
  }
}

.tag-card {
  gap: 6px;
  min-height: 96px;
  padding: 9px 10px;
  border-left-width: 3px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.64);

  &:hover {
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.07);
    transform: translateY(-1px);
  }

  .tag-type-badge {
    gap: 4px;
    padding: 3px 6px;
    font-size: 8px;

    span {
      font-size: 8px;
    }
  }

  .tag-body .tag-name {
    font-size: 12px;
  }

  .tag-footer .tag-time {
    font-family: var(--font-mono);
    font-size: 8px;
  }
}

.warning-icon {
  display: inline-flex;
}

.is-spinning {
  animation: tag-control-spin 0.8s linear infinite;
}

@keyframes tag-control-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .toolbar {
    align-items: stretch;
    flex-direction: column;
    gap: 6px;
  }

  .toolbar-left,
  .toolbar-left .el-input,
  .toolbar-right .el-button {
    width: 100% !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tag-card {
    transition-duration: 0.01ms;
  }

  .is-spinning {
    animation: none;
  }
}
</style>
