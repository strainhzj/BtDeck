<template>
  <div class="api-log-viewer">
    <div class="api-log-header" @click="toggleExpanded">
      <span class="api-log-title">
        <span class="title-icon">📋</span>
        <span>API日志</span>
      </span>
      <span class="api-log-toggle" :class="{expanded: expanded}">
        <span>{{ expanded ? '收起' : '展开' }}</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </span>
    </div>
    <div class="api-log-content" :class="{expanded: expanded}">
      <pre class="api-log-code" v-html="safeHighlightedJson"></pre>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

@Component({
  name: 'ApiLogViewer'
})
export default class ApiLogViewer extends Vue {
  @Prop({ type: Object, required: true })
  readonly logData!: any

  @Prop({ type: Boolean, default: false })
  readonly value!: boolean

  expanded: boolean = this.value

  /**
   * 切换展开状态
   */
  toggleExpanded() {
    this.expanded = !this.expanded
    this.$emit('input', this.expanded)
  }

  /**
   * 安全地格式化JSON并添加语法高亮
   * 先进行HTML转义，再添加语法高亮标签
   */
  get safeHighlightedJson(): string {
    const jsonStr = JSON.stringify(this.logData, null, 2)
    // 先转义HTML特殊字符
    const escaped = this.escapeHtml(jsonStr)
    // 再添加语法高亮（此时操作的是安全的文本）
    return this.syntaxHighlight(escaped)
  }

  /**
   * HTML转义 - 防止XSS攻击
   */
  escapeHtml(text: string): string {
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
  }

  /**
   * JSON语法高亮（仅在已转义的HTML上操作）
   */
  syntaxHighlight(json: string): string {
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function(match) {
      let cls = 'json-number'
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          cls = 'json-key'
        } else {
          cls = 'json-string'
        }
      } else if (/true|false/.test(match)) {
        cls = 'json-boolean'
      } else if (/null/.test(match)) {
        cls = 'json-null'
      }
      return '<span class="' + cls + '">' + match + '</span>'
    })
  }
}
</script>

<style lang="scss" scoped>
.api-log-viewer {
  margin-bottom: 24px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;

  .api-log-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #f5f7fa;
    border-bottom: 1px solid #ebeef5;
    cursor: pointer;
    user-select: none;
    transition: background 0.2s ease;

    &:hover {
      background: #edeff2;
    }

    .api-log-title {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 14px;
      font-weight: 500;
      color: #606266;

      .title-icon {
        font-size: 16px;
      }
    }

    .api-log-toggle {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: #909399;
      transition: all 0.3s ease;

      svg {
        width: 16px;
        height: 16px;
        transition: transform 0.3s ease;
      }

      &.expanded svg {
        transform: rotate(180deg);
      }
    }
  }

  .api-log-content {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease;

    &.expanded {
      max-height: 300px;
      overflow-y: auto;

      &::-webkit-scrollbar {
        width: 6px;
      }

      &::-webkit-scrollbar-thumb {
        background: #dcdfe6;
        border-radius: 3px;

        &:hover {
          background: #c0c4cc;
        }
      }
    }

    .api-log-code {
      margin: 0;
      padding: 16px;
      background: #2b2b2b;
      color: #a9b7c6;
      font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
      font-size: 13px;
      line-height: 1.6;

      // JSON语法高亮
      :deep(.json-key) { color: #9876aa; }
      :deep(.json-string) { color: #6a8759; }
      :deep(.json-number) { color: #6897bb; }
      :deep(.json-boolean) { color: #cc7832; }
      :deep(.json-null) { color: #cc7832; }
    }
  }
}
</style>
