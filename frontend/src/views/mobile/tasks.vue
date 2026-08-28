<template>
  <div class="m-tasks">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-toolbar">
      <el-select v-model="enabledFilter" size="small" placeholder="全部任务" clearable @change="reload">
        <el-option label="已启用" :value="true" />
        <el-option label="已禁用" :value="false" />
      </el-select>
      <el-input
        v-model="nameFilter"
        size="small"
        placeholder="按任务名称过滤"
        clearable
        prefix-icon="el-icon-search"
        @keyup.enter.native="reload"
        @clear="reload"
      />
    </div>
    <div class="m-toolbar m-toolbar--second">
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reload">刷新</el-button>
    </div>

    <div v-if="!loading && list.length === 0" class="m-hint">暂无定时任务</div>

    <div v-for="task in list" :key="task.taskId" class="m-task-card">
      <div class="m-task-head">
        <el-tag size="mini" :type="statusTagType(task.taskStatusName)">{{ task.taskStatusName }}</el-tag>
        <el-tag v-if="outcomeMeta(task.lastOutcome)" size="mini" :type="outcomeMeta(task.lastOutcome).type">
          {{ outcomeMeta(task.lastOutcome).text }}
        </el-tag>
        <el-tag v-if="isStale(task)" size="mini" type="danger" effect="plain">数据陈旧</el-tag>
        <span class="m-task-enabled" :class="task.enabled ? 'is-on' : 'is-off'">
          {{ task.enabled ? '已启用' : '已禁用' }}
        </span>
      </div>
      <div class="m-task-name" :title="task.taskName">{{ task.taskName }}</div>
      <div class="m-task-meta">
        <el-tag size="mini" type="info" effect="plain">{{ task.taskTypeName }}</el-tag>
        <code class="m-task-cron">{{ task.cronPlan }}</code>
      </div>
      <div v-if="task.description" class="m-task-desc">{{ task.description }}</div>
      <div class="m-task-time">
        上次执行：{{ formatTime(task.lastExecuteTime) }}
        <template v-if="isStale(task)">（{{ staleText(task) }}）</template>
      </div>
      <div class="m-task-actions">
        <el-button
          size="mini"
          type="primary"
          plain
          :disabled="!task.enabled || busyId === task.taskId"
          @click="execute(task)"
        >
          立即执行
        </el-button>
        <el-button size="mini" :disabled="busyId === task.taskId" @click="toggleEnabled(task)">
          {{ task.enabled ? '禁用' : '启用' }}
        </el-button>
        <el-button
          v-if="task.taskStatusName === '运行中'"
          size="mini"
          type="warning"
          plain
          :disabled="busyId === task.taskId"
          @click="interrupt(task)"
        >
          中断
        </el-button>
        <el-button
          size="mini"
          type="danger"
          plain
          class="m-task-delete"
          :disabled="busyId === task.taskId"
          @click="confirmDelete(task)"
        >
          删除
        </el-button>
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

    <div class="m-task-footnote">任务新建/编辑与完整执行日志请在桌面版「定时任务」页操作</div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getTaskList,
  executeTask,
  updateTask,
  interruptTask,
  deleteTasks,
  ScheduledTask,
  TaskOutcome,
  getTaskOutcomeMeta,
  isTaskDataStale,
  getStaleTooltipText
} from '@/api/tasks'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

const PAGE_SIZE = 20

/**
 * 移动定时任务（Phase 4 M3）：任务卡片流 + 启用筛选/名称过滤；
 * 操作保留立即执行/启停（PUT 部分更新 enabled）/中断/删除，最近结果六态
 * 与数据陈旧语义复用 api/tasks 的桌面同源工具函数。新建/编辑与完整
 * 日志保留桌面版承载（编辑器含 Monaco，不适合移动端）。
 */
@Component({
  name: 'MobileTasks',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileTasks extends Mixins(PullToRefresh) {
  private list: ScheduledTask[] = []
  private total = 0
  private loading = false
  private enabledFilter: boolean | undefined = undefined
  private nameFilter = ''
  private busyId = 0

  mounted(): void {
    this.reload()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
  }

  /** 模板不可直调模块级函数，以下三个为实例包装（M1 已知约束） */
  private outcomeMeta(outcome?: TaskOutcome | string | null) {
    return getTaskOutcomeMeta(outcome)
  }

  private isStale(task: ScheduledTask): boolean {
    return isTaskDataStale(task.stale, task.lastSuccessfulDataAt, task.lastAttemptAt)
  }

  private staleText(task: ScheduledTask): string {
    return getStaleTooltipText(task.lastSuccessfulDataAt, task.lastAttemptAt)
  }

  private async reload(): Promise<void> {
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
      const res = await getTaskList({
        skip: this.list.length,
        limit: PAGE_SIZE,
        ...(this.nameFilter ? { task_name: this.nameFilter } : {}),
        ...(this.enabledFilter !== undefined ? { enabled: this.enabledFilter } : {})
      })
      if (res.code === '200' && res.data) {
        this.list = this.list.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private statusTagType(statusName: string): string {
    const tags: Record<string, string> = {
      '等待运行': 'info',
      '运行中': 'success',
      '空闲': 'info',
      '已暂停': 'warning',
      '已停止': 'info',
      '已完成': 'success',
      '失败': 'danger'
    }
    return tags[statusName] || 'info'
  }

  private formatTime(value: string | null): string {
    if (!value) return '—'
    return value.replace('T', ' ').slice(0, 19)
  }

  private async execute(task: ScheduledTask): Promise<void> {
    if (!task.enabled) {
      this.$message.warning(`任务 "${task.taskName}" 已禁用，请先启用后再执行`)
      return
    }
    this.busyId = task.taskId
    try {
      await executeTask({ id: task.taskId })
      this.$message.success('任务已触发执行')
      // 与桌面端一致：延迟刷新等待执行状态更新
      setTimeout(() => {
        this.reload()
      }, 1000)
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyId = 0
    }
  }

  /** 启停走 PUT /cronTasks/{id} 部分更新（CronTaskUpdate 全字段可选，exclude_none 语义） */
  private async toggleEnabled(task: ScheduledTask): Promise<void> {
    this.busyId = task.taskId
    try {
      const res = await updateTask({ id: task.taskId, enabled: !task.enabled })
      if (res.code === '200') {
        this.$message.success(!task.enabled ? '任务已启用' : '任务已禁用')
        await this.reload()
      } else {
        this.$message.error(res.msg || '操作失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyId = 0
    }
  }

  private async interrupt(task: ScheduledTask): Promise<void> {
    this.busyId = task.taskId
    try {
      const res = await interruptTask(task.taskId)
      if (res.code === '200') {
        this.$message.success('任务中断成功')
        await this.reload()
      } else {
        this.$message.error(res.msg || '中断失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyId = 0
    }
  }

  private confirmDelete(task: ScheduledTask): void {
    this.$confirm(`确定要删除任务「${task.taskName}」吗？`, '删除确认', { type: 'warning' })
      .then(async() => {
        this.busyId = task.taskId
        try {
          await deleteTasks({ ids: [task.taskId] })
          this.$message.success('删除成功')
          await this.reload()
        } catch (e) {
          this.$message.error(extractErrorMessage(e))
        } finally {
          this.busyId = 0
        }
      })
      .catch(() => undefined)
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

.m-task-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-task-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.m-task-enabled {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
}

.m-task-enabled.is-on {
  color: var(--color-primary);
}

.m-task-enabled.is-off {
  color: #909399;
}

.m-task-name {
  margin-top: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-task-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.m-task-cron {
  font-size: 12px;
  color: #606266;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 4px;
}

.m-task-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.m-task-time {
  margin-top: 4px;
  font-size: 11px;
  color: #c0c4cc;
  word-break: break-all;
}

.m-task-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.m-task-actions .el-button {
  margin-left: 0;
  padding: 5px 10px;
}

/* 危险操作分隔（2026-08-28 UX 审查）：删除推到行尾与常规操作拉开距离，
   换行时自然独占一行右端；触控区略放宽 */
.m-task-actions .m-task-delete {
  margin-left: auto;
  padding: 5px 12px;
}

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-task-footnote {
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
