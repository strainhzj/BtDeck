<template>
  <div class="m-logs">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-toolbar">
      <el-select v-model="typeFilter" size="small" placeholder="全部操作" clearable @change="reload">
        <el-option
          v-for="opt in operationTypes"
          :key="opt.value"
          :label="opt.display_name"
          :value="opt.value"
        />
      </el-select>
      <el-select v-model="resultFilter" size="small" placeholder="全部结果" clearable @change="reload">
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failure" />
      </el-select>
    </div>
    <div class="m-toolbar m-toolbar--second">
      <el-input
        v-model="nameFilter"
        size="small"
        placeholder="按种子名称过滤"
        clearable
        prefix-icon="el-icon-search"
        @keyup.enter.native="reload"
        @clear="reload"
      />
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reload">刷新</el-button>
    </div>

    <div v-if="!loading && list.length === 0" class="m-hint">没有匹配的审计日志</div>

    <div v-for="log in list" :key="log.log_id" class="m-log-card" @click="toggleExpand(log)">
      <div class="m-log-head">
        <el-tag size="mini" :type="logTagType(log)">{{ typeLabel(log.operation_type) }}</el-tag>
        <span class="m-log-result" :class="isSuccess(log) ? 'is-ok' : 'is-fail'">
          {{ isSuccess(log) ? '成功' : '失败' }}
        </span>
        <span class="m-log-time">{{ formatTime(log.operation_time || log.create_time) }}</span>
      </div>
      <div v-if="log.torrent_name" class="m-log-torrent" :title="log.torrent_name">{{ log.torrent_name }}</div>
      <div class="m-log-detail" :class="{'is-expanded': expandedId === log.log_id}">
        {{ log.operation_detail }}
      </div>
      <div v-if="!isSuccess(log) && log.error_message" class="m-log-error">{{ log.error_message }}</div>
      <div class="m-log-foot">
        <span>{{ log.operator }}</span>
        <span v-if="log.downloader_name">{{ log.downloader_name }}</span>
        <span v-if="log.ip_address">{{ log.ip_address }}</span>
      </div>
    </div>

    <el-button
      v-if="list.length < total"
      class="m-load-more"
      size="small"
      :loading="loading"
      @click="loadMore"
    >
      加载更多（{{ list.length }}/{{ total }}）
    </el-button>

    <div class="m-log-footnote">统计图表与 CSV/Excel 导出请在桌面版「日志管理」页操作</div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { queryAuditLogs, getOperationTypes, AuditLogItem, OperationTypeItem } from '@/api/audit-logs'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

const PAGE_SIZE = 20

/**
 * 移动审计日志（Phase 4 M2）：复用 /audit-logs 查询与操作类型 API 的卡片流；
 * 支持操作类型/结果/种子名称筛选与分页加载。导出与统计保留桌面版承载。
 */
@Component({
  name: 'MobileLogs',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileLogs extends Mixins(PullToRefresh) {
  private list: AuditLogItem[] = []
  private total = 0
  private page = 1
  private loading = false
  private typeFilter = ''
  private resultFilter = ''
  private nameFilter = ''
  private expandedId = ''
  private operationTypes: OperationTypeItem[] = []

  mounted(): void {
    this.loadOperationTypes()
    this.reload()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
  }

  private async loadOperationTypes(): Promise<void> {
    try {
      const res = await getOperationTypes()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.operationTypes = res.data
      }
    } catch {
      // 操作类型下拉加载失败不阻塞日志列表，仅选项为空
    }
  }

  private async reload(): Promise<void> {
    this.page = 1
    this.list = []
    this.total = 0
    await this.fetchPage()
  }

  private async loadMore(): Promise<void> {
    await this.fetchPage()
  }

  private async fetchPage(): Promise<void> {
    this.loading = true
    try {
      const res = await queryAuditLogs({
        page: this.page,
        page_size: PAGE_SIZE,
        ...(this.typeFilter ? { operation_type: this.typeFilter } : {}),
        ...(this.resultFilter ? { operation_result: this.resultFilter } : {}),
        ...(this.nameFilter ? { torrent_name: this.nameFilter } : {})
      })
      if (res.code === '200' && res.data) {
        this.list = this.list.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
        this.page += 1
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private toggleExpand(log: AuditLogItem): void {
    this.expandedId = this.expandedId === log.log_id ? '' : log.log_id
  }

  private isSuccess(log: AuditLogItem): boolean {
    return log.operation_result === 'success'
  }

  private typeLabel(value: string): string {
    const found = this.operationTypes.find((opt) => opt.value === value)
    return found ? found.display_name : value
  }

  private logTagType(log: AuditLogItem): string {
    switch (log.operation_type) {
      case 'delete':
      case 'cleanup':
        return 'danger'
      case 'update':
      case 'edit':
        return 'warning'
      case 'add':
      case 'create':
        return 'success'
      default:
        return 'info'
    }
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
  gap: 8px;
  margin-bottom: 8px;
}

.m-toolbar .el-select,
.m-toolbar .el-input {
  flex: 1;
}

.m-log-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-log-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.m-log-result {
  font-size: 12px;
  font-weight: 600;
}

.m-log-result.is-ok {
  color: var(--color-primary);
}

.m-log-result.is-fail {
  color: #f56c6c;
}

.m-log-time {
  margin-left: auto;
  font-size: 11px;
  color: #c0c4cc;
  white-space: nowrap;
}

.m-log-torrent {
  margin-top: 6px;
  font-size: 13px;
  color: #303133;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-log-detail {
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
  max-height: 3.2em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}

.m-log-detail.is-expanded {
  max-height: none;
  -webkit-line-clamp: unset;
}

.m-log-error {
  margin-top: 4px;
  font-size: 12px;
  color: #f56c6c;
  word-break: break-all;
}

.m-log-foot {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  font-size: 11px;
  color: #c0c4cc;
  overflow: hidden;
}

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-log-footnote {
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
</style>
