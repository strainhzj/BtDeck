<template>
  <el-dialog
    title="同内容异常排查"
    :visible.sync="dialogVisible"
    width="calc(100% - 32px)"
    custom-class="same-content-inspection-dialog"
    top="5vh"
    :before-close="handleClose"
    :close-on-click-modal="false"
    append-to-body
  >
    <div class="sci-toolbar">
      <div class="sci-mode" role="group" aria-label="排查结果显示范围">
        <span class="sci-mode-label">显示范围</span>
        <el-radio-group v-model="mode" size="small" @change="handleModeChange">
          <el-radio-button label="all">完整排查结果</el-radio-button>
          <el-radio-button label="errors">仅错误种子</el-radio-button>
        </el-radio-group>
      </div>
      <el-button
        size="small"
        icon="el-icon-refresh"
        :loading="loading"
        aria-label="刷新同内容异常排查结果"
        @click="handleRefresh"
      >
        刷新
      </el-button>
    </div>

    <el-alert
      title="按名称完全相同、大小完全相同且 InfoHash 不同进行分组。结果来自数据库同步快照，本功能只查询和展示，不会修改种子。"
      type="info"
      :closable="false"
      show-icon
      class="sci-description"
    />

    <div v-if="result" class="sci-summary" aria-label="排查汇总">
      <div class="sci-summary-item">
        <span class="sci-summary-value">{{ result.summary.candidate_group_count }}</span>
        <span class="sci-summary-label">候选组</span>
      </div>
      <div class="sci-summary-item">
        <span class="sci-summary-value">{{ result.summary.candidate_torrent_count }}</span>
        <span class="sci-summary-label">候选种子</span>
      </div>
      <div class="sci-summary-item is-error">
        <span class="sci-summary-value">{{ result.summary.error_group_count }}</span>
        <span class="sci-summary-label">错误组</span>
      </div>
      <div class="sci-summary-item is-error">
        <span class="sci-summary-value">{{ result.summary.error_torrent_count }}</span>
        <span class="sci-summary-label">错误种子</span>
      </div>
    </div>

    <div v-if="loading && !result" class="sci-state" role="status" aria-live="polite">
      <i class="el-icon-loading sci-state-icon" />
      <span>正在排查同名同大小种子...</span>
    </div>

    <el-alert
      v-else-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
      class="sci-error"
    />

    <template v-else-if="result">
      <div v-if="result.list.length === 0" class="sci-state" role="status">
        <i class="el-icon-circle-check sci-state-icon is-success" />
        <span>{{ emptyStateText }}</span>
      </div>

      <div v-else v-loading="loading" class="sci-groups" aria-live="polite">
        <section
          v-for="group in result.list"
          :key="group.group_key"
          class="sci-group"
          :class="{'has-error': group.error_count > 0}"
        >
          <header class="sci-group-header">
            <div class="sci-group-heading">
              <div class="sci-group-name" :title="group.name">{{ group.name }}</div>
              <div class="sci-group-meta">
                <span>{{ formatSize(group.size) }}</span>
                <span>{{ group.copy_count }} 个种子</span>
                <span>{{ group.distinct_hash_count }} 个 InfoHash</span>
                <span>{{ group.downloader_count }} 个下载器</span>
                <span v-if="mode === 'errors'">当前展示 {{ group.items.length }} 个错误种子</span>
              </div>
            </div>
            <span
              class="sci-error-count"
              :class="{'is-zero': group.error_count === 0}"
            >
              {{ group.error_count > 0 ? `${group.error_count} 个错误` : '未发现错误' }}
            </span>
          </header>

          <div class="sci-table-scroll">
            <table class="sci-table">
              <thead>
                <tr>
                  <th class="sci-col-state">状态</th>
                  <th class="sci-col-downloader">下载器</th>
                  <th class="sci-col-task">任务状态</th>
                  <th class="sci-col-hash">InfoHash</th>
                  <th>排查说明</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in group.items"
                  :key="item.info_id"
                  :class="{'is-error': item.is_error}"
                >
                  <td>
                    <span class="sci-state-badge" :class="item.is_error ? 'is-error' : 'is-normal'">
                      {{ item.is_error ? '错误' : '正常' }}
                    </span>
                  </td>
                  <td>
                    <div class="sci-primary-text" :title="item.downloader_name">
                      {{ item.downloader_name || item.downloader_id }}
                    </div>
                  </td>
                  <td>
                    <span class="sci-task-status" :class="{'is-error': isTaskStatusError(item.status)}">
                      {{ item.status || '未知' }}
                    </span>
                  </td>
                  <td>
                    <code class="sci-hash" :title="item.hash">{{ shortHash(item.hash) }}</code>
                  </td>
                  <td>
                    <div v-if="item.is_error" class="sci-diagnostics">
                      <div class="sci-error-tags">
                        <span
                          v-for="errorType in item.error_types"
                          :key="errorType"
                          class="sci-error-tag"
                        >
                          {{ errorTypeLabel(errorType) }}
                        </span>
                      </div>
                      <div v-if="item.error_reason" class="sci-message">
                        {{ item.error_reason }}
                      </div>
                      <div
                        v-for="(issue, issueIndex) in item.tracker_issues"
                        :key="`${item.info_id}-${issue.tracker_host}-${issueIndex}`"
                        class="sci-tracker-issue"
                      >
                        <span class="sci-tracker-host">{{ issue.tracker_host }}</span>
                        <span>{{ trackerIssueSummary(issue) }}</span>
                      </div>
                    </div>
                    <div v-else class="sci-normal-detail">
                      <span v-if="item.tracker_hosts.length > 0">
                        Tracker：{{ item.tracker_hosts.join('、') }}
                      </span>
                      <span v-else>未发现任务或 Tracker 错误</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <el-pagination
        v-if="result.total > pageSize"
        class="sci-pagination"
        layout="total, prev, pager, next"
        :current-page.sync="currentPage"
        :page-size="pageSize"
        :total="result.total"
        @current-change="handlePageChange"
      />
    </template>

    <span slot="footer" class="dialog-footer">
      <el-button @click="handleClose">关闭</el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import {
  getSameContentInspection,
  type SameContentInspectionMode,
  type SameContentInspectionResponse,
  type SameContentTrackerIssue
} from '@/api/torrents'
import { extractErrorMessage, formatFileSize } from '@/utils/formatters'

type InspectionErrorType = 'torrent_status' | 'error_reason' | 'tracker_aggregate' | 'tracker_detail'

const ERROR_TYPE_LABELS: Record<InspectionErrorType, string> = {
  torrent_status: '任务状态错误',
  error_reason: '任务错误原因',
  tracker_aggregate: 'Tracker 整体错误',
  tracker_detail: 'Tracker 明细异常'
}

@Component({
  name: 'SameContentInspectionDialog'
})
export default class SameContentInspectionDialog extends Vue {
  @Prop({ type: Boolean, default: false }) readonly visible!: boolean

  private dialogVisible = false
  private mode: SameContentInspectionMode = 'all'
  private result: SameContentInspectionResponse | null = null
  private loading = false
  private errorMessage = ''
  private currentPage = 1
  private readonly pageSize = 10
  private requestSequence = 0

  get emptyStateText(): string {
    return this.mode === 'errors'
      ? '排查完成，当前没有错误种子'
      : '未发现名称、大小相同且 InfoHash 不同的种子组'
  }

  @Watch('visible', { immediate: true })
  onVisibleChange(value: boolean) {
    this.dialogVisible = value
    if (value) {
      this.initializeAndLoad()
    } else {
      this.requestSequence += 1
    }
  }

  private initializeAndLoad() {
    this.mode = 'all'
    this.result = null
    this.errorMessage = ''
    this.currentPage = 1
    void this.fetchResults()
  }

  private async fetchResults() {
    const requestId = ++this.requestSequence
    const mode = this.mode
    const page = this.currentPage
    const pageSize = this.pageSize

    this.loading = true
    this.errorMessage = ''
    try {
      const response = await getSameContentInspection({ mode, page, pageSize })
      if (requestId !== this.requestSequence) return
      if (response.code !== '200') {
        this.result = null
        this.errorMessage = response.msg || '排查失败'
        return
      }
      this.result = response.data
    } catch (error) {
      if (requestId !== this.requestSequence) return
      this.result = null
      this.errorMessage = extractErrorMessage(error)
    } finally {
      if (requestId === this.requestSequence) {
        this.loading = false
      }
    }
  }

  private handleModeChange(mode: SameContentInspectionMode) {
    this.mode = mode
    this.currentPage = 1
    this.result = null
    void this.fetchResults()
  }

  private handleRefresh() {
    void this.fetchResults()
  }

  private handlePageChange(page: number) {
    this.currentPage = page
    void this.fetchResults()
  }

  private formatSize(size: number): string {
    return formatFileSize(size)
  }

  private shortHash(hash: string): string {
    if (!hash) return ''
    return hash.length > 22 ? `${hash.slice(0, 10)}…${hash.slice(-8)}` : hash
  }

  private isTaskStatusError(status: string): boolean {
    return status.trim().toLowerCase() === 'error'
  }

  private errorTypeLabel(errorType: InspectionErrorType): string {
    return ERROR_TYPE_LABELS[errorType] || errorType
  }

  private trackerIssueSummary(issue: SameContentTrackerIssue): string {
    const parts: string[] = []
    if (issue.issue_types.includes('tracker_status')) {
      parts.push(`Tracker 状态异常${issue.status_message ? `：${issue.status_message}` : ''}`)
    }
    if (issue.issue_types.includes('announce')) {
      const detail = issue.announce_message || issue.announce_status || '失败'
      parts.push(`汇报异常：${detail}`)
    }
    if (issue.issue_types.includes('scrape')) {
      const detail = issue.scrape_message || issue.scrape_status || '失败'
      parts.push(`抓取异常：${detail}`)
    }
    return parts.join('；') || 'Tracker 异常'
  }

  private handleClose() {
    this.requestSequence += 1
    this.loading = false
    this.dialogVisible = false
    this.$emit('update:visible', false)
    this.$emit('close')
  }
}
</script>

<style lang="scss" scoped>
.sci-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.sci-mode {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sci-mode-label {
  color: var(--color-text-secondary, #606266);
  font-size: 13px;
  font-weight: 600;
}

.sci-description {
  margin-bottom: 12px;
}

.sci-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.sci-summary-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--color-border-primary, #ebeef5);
  border-radius: 6px;
  background: var(--color-bg-secondary, #f5f7fa);

  &.is-error .sci-summary-value {
    color: var(--theme-error, #f56c6c);
  }
}

.sci-summary-value {
  color: var(--color-primary, #409eff);
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
}

.sci-summary-label {
  color: var(--color-text-secondary, #606266);
  font-size: 12px;
}

.sci-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 180px;
  color: var(--color-text-secondary, #909399);
  font-size: 14px;
}

.sci-state-icon {
  font-size: 22px;

  &.is-success {
    color: var(--theme-success, #67c23a);
  }
}

.sci-error {
  margin-top: 12px;
}

.sci-groups {
  max-height: 58vh;
  overflow-y: auto;
  padding-right: 4px;
}

.sci-group {
  margin-bottom: 12px;
  overflow: hidden;
  border: 1px solid var(--color-border-primary, #dcdfe6);
  border-radius: 7px;
  background: var(--color-bg-primary, #fff);

  &.has-error {
    border-color: rgba(245, 108, 108, 0.45);
  }
}

.sci-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-primary, #ebeef5);
  background: var(--color-bg-secondary, #f5f7fa);
}

.sci-group-heading {
  min-width: 0;
}

.sci-group-name {
  overflow: hidden;
  color: var(--color-text-primary, #303133);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sci-group-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 5px;
  color: var(--color-text-secondary, #909399);
  font-size: 11px;
}

.sci-error-count {
  flex-shrink: 0;
  padding: 3px 9px;
  border: 1px solid rgba(245, 108, 108, 0.35);
  border-radius: 999px;
  background: rgba(245, 108, 108, 0.1);
  color: var(--theme-error, #f56c6c);
  font-size: 11px;
  font-weight: 600;

  &.is-zero {
    border-color: rgba(103, 194, 58, 0.35);
    background: rgba(103, 194, 58, 0.1);
    color: var(--theme-success, #67c23a);
  }
}

.sci-table-scroll {
  overflow-x: auto;
}

.sci-table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  table-layout: fixed;

  th,
  td {
    padding: 9px 10px;
    border-bottom: 1px solid var(--color-border-primary, #ebeef5);
    color: var(--color-text-primary, #303133);
    font-size: 12px;
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--color-text-secondary, #606266);
    font-weight: 600;
  }

  tbody tr:last-child td {
    border-bottom: 0;
  }

  tbody tr.is-error {
    background: rgba(245, 108, 108, 0.035);
  }
}

.sci-col-state {
  width: 68px;
}

.sci-col-downloader {
  width: 145px;
}

.sci-col-task {
  width: 100px;
}

.sci-col-hash {
  width: 180px;
}

.sci-state-badge,
.sci-error-tag {
  display: inline-flex;
  align-items: center;
  border-radius: 4px;
  font-size: 11px;
  white-space: nowrap;
}

.sci-state-badge {
  padding: 2px 7px;

  &.is-error {
    background: rgba(245, 108, 108, 0.12);
    color: var(--theme-error, #f56c6c);
  }

  &.is-normal {
    background: rgba(103, 194, 58, 0.12);
    color: var(--theme-success, #67c23a);
  }
}

.sci-primary-text {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sci-task-status.is-error {
  color: var(--theme-error, #f56c6c);
  font-weight: 600;
}

.sci-hash {
  color: var(--color-text-secondary, #606266);
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.sci-diagnostics {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.sci-error-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.sci-error-tag {
  padding: 1px 6px;
  border: 1px solid rgba(245, 108, 108, 0.28);
  background: rgba(245, 108, 108, 0.08);
  color: var(--theme-error, #f56c6c);
}

.sci-message {
  color: var(--theme-error, #f56c6c);
  line-height: 1.45;
  word-break: break-word;
}

.sci-tracker-issue {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: var(--color-text-secondary, #606266);
  line-height: 1.45;
  word-break: break-word;
}

.sci-tracker-host {
  flex-shrink: 0;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--color-bg-secondary, #f5f7fa);
  color: var(--color-primary, #409eff);
  font-family: 'Courier New', monospace;
}

.sci-normal-detail {
  color: var(--color-text-secondary, #909399);
  line-height: 1.45;
  word-break: break-word;
}

.sci-pagination {
  margin-top: 12px;
  text-align: right;
}

@media (max-width: 900px) {
  .sci-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .sci-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

<style lang="scss">
.same-content-inspection-dialog {
  max-width: 1080px;
}
</style>
