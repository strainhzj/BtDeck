<template>
  <div class="keyword-item" :class="getItemClass">
    <div class="keyword-header">
      <el-tag :type="getTagType" size="small">
        {{ getTagLabel }}
      </el-tag>
      <span class="keyword-content">"{{ keyword.keyword }}"</span>
    </div>
    <div class="keyword-meta">
      优先级: {{ keyword.priority }}
      <span v-if="keyword.language"> | 语言: {{ languageLabel }}</span>
    </div>
    <div v-if="keyword.description" class="keyword-desc">
      说明: {{ keyword.description }}
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'
import { getLanguageLabel } from '@/utils/tracker'
import { TrackerKeyword } from '@/api/tracker'

@Component({
  name: 'KeywordCard'
})
export default class KeywordCard extends Vue {
  @Prop({ type: Object, required: true })
  readonly keyword!: TrackerKeyword

  /**
   * 获取语言的中文标签
   */
  get languageLabel(): string {
    return getLanguageLabel(this.keyword.language || '')
  }

  /**
   * 获取标签类型
   */
  get getTagType(): string {
    if (this.keyword.keyword_type === 'success') {
      return 'success'
    } else if (this.keyword.keyword_type === 'failed') {
      return 'danger'
    } else if (this.keyword.keyword_type === 'candidate') {
      return 'info'
    } else {
      return 'warning'
    }
  }

  /**
   * 获取标签文字
   */
  get getTagLabel(): string {
    const typeMap: Record<string, string> = {
      success: '成功',
      failed: '失败',
      candidate: '候选',
      ignored: '忽略'
    }
    return typeMap[this.keyword.keyword_type] || this.keyword.keyword_type
  }

  /**
   * 获取项目CSS类
   */
  get getItemClass(): string {
    if (this.keyword.keyword_type === 'success') {
      return 'type-success'
    } else if (this.keyword.keyword_type === 'failed') {
      return 'type-failed'
    } else {
      return 'type-other'
    }
  }
}
</script>

<style lang="scss" scoped>
.keyword-item {
  padding: 16px;
  background-color: #f5f7fa;
  border-radius: 8px;
  border-left: 4px solid transparent;
  transition: all 0.3s ease;

  &:hover {
    background-color: #edeff2;
    transform: translateX(2px);
  }

  &.type-success {
    border-left-color: #67c23a;
  }

  &.type-failed {
    border-left-color: #f56c6c;
  }

  &.type-other {
    border-left-color: #e6a23c;
  }

  .keyword-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .keyword-content {
    font-size: 15px;
    font-weight: 500;
    color: #303133;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  }

  .keyword-meta {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
  }

  .keyword-desc {
    font-size: 13px;
    color: #606266;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #ebeef5;
  }
}
</style>
