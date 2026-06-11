<template>
  <div class="tag-management-tab">
    <!-- 新增模式提示 -->
    <div v-if="!downloader" class="empty-state">
      <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
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
            prefix-icon="el-icon-search"
            clearable
            style="width: 280px;"
            @input="handleSearchInput"
            @clear="handleSearchClear"
          />
        </div>
        <div class="toolbar-right">
          <el-button
            type="primary"
            icon="el-icon-plus"
            :disabled="downloader === null"
            @click="handleCreate"
          >
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
          <svg class="type-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path v-if="type.value === 'category'" d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            <path v-else d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h2l5.41 13.59a2 2 0 0 1 2.83 0L21.59 13.41z"></path>
          </svg>
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
          :icon="sortOrder === 'asc' ? 'el-icon-bottom' : 'el-icon-top'"
          @click="toggleSortOrder"
        >
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
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h2l5.41 13.59a2 2 0 0 1 2.83 0L21.59 13.41z"></path>
            <line x1="12" y1="2" x2="12" y2="22"></line>
          </svg>
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
                <svg v-if="tag.tag_type === 'category'" class="badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                </svg>
                <svg v-else class="badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h2l5.41 13.59a2 2 0 0 1 2.83 0L21.59 13.41z"></path>
                  <line x1="12" y1="2" x2="12" y2="22"></line>
                </svg>
                <span>{{ tag.tag_type === 'category' ? '分类' : '标签' }}</span>
              </div>
              <el-dropdown trigger="click" @command="(cmd) => handleTagAction(cmd, tag)">
                <span class="tag-menu-trigger">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="1"></circle>
                    <circle cx="12" cy="5" r="1"></circle>
                    <circle cx="12" cy="19" r="1"></circle>
                  </svg>
                </span>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="edit">
                    <svg class="menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-1 5L13.5 5.5a2.121 2.121 0 0 1 3-3z"></path>
                    </svg>
                    编辑
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <svg class="menu-icon danger" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v2"></path>
                    </svg>
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
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
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
        <svg class="warning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3.71l10.59 10.59a2 2 0 0 0 2.83 0l1.41-1.41a2 2 0 0 0-2.83 0L10.29 3.86z"></path>
          <line x1="12" y1="9" x2="12" y2="17"></line>
          <line x1="4.93" y1="14.07" x2="7.76" y2="16.9"></line>
          <line x1="16.24" y1="7.1" x2="19.07" y2="9.93"></line>
        </svg>
        <p>确定要删除选中的 <strong>{{ selectedTags.length }}</strong> 个标签吗？</p>
        <p class="warning-text">此操作不可撤销，删除后将无法恢复</p>
      </div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="showBatchDeleteDialog = false">取消</el-button>
        <el-button type="danger" :loading="batchDeleting" @click="handleConfirmBatchDelete">
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
        <svg class="warning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 1 2.83 0l12.59 12.59a2 2 0 0 1 2.83 0L17.59 5.41a2 2 0 0 0 0-3.42 0z"></path>
          <line x1="12" y1="9" x2="12" y2="17"></line>
          <line x1="4.93" y1="14.07" x2="7.76" y2="16.9"></line>
          <line x1="16.24" y1="7.1" x2="19.07" y2="9.93"></line>
        </svg>
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
        <el-button type="primary" :loading="transferring" @click="handleConfirmDeleteCategory">
          确定转移并删除
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import {
  getTagList,
  createTag,
  updateTag,
  deleteTag,
  batchDeleteTags,
  checkCategorySupport,
  TorrentTag,
  TagType,
  CreateTagRequest,
  UpdateTagRequest
} from '@/api/tag-management'
import { Message, MessageBox } from 'element-ui'

@Component({
  name: 'TagManagementTab'
})
export default class TagManagementTab extends Vue {
  @Prop({ default: null }) downloader!: any

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
  private handleSearchInput(value: string) {
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
        await updateTag(this.tagForm.tag_id!, updateData)
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
  get formData(): any {
    return this.$parent.$parent?.formData || {}
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.tag-management-tab {
  padding: 0;
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
</style>
