<template>
  <div>
    <div
      v-for="task in shown"
      :key="task.taskId"
      class="dash-rowline"
    >
      <span :class="['dash-status-pill', task.enabled ? 'st-online' : 'st-offline']">
        {{ task.enabled ? $t('dashboard.widgets.tasks.enabled') : $t('dashboard.widgets.tasks.disabled') }}
      </span>
      <div
        class="grow dash-ellip"
        :title="task.taskName"
      >
        {{ task.taskName }}
      </div>
    </div>
    <div
      v-if="shown.length === 0"
      class="dash-empty"
    >
      <lucide-icon icon="clock" />
      <span>{{ $t('dashboard.widgets.tasks.empty') }}</span>
    </div>
    <div
      v-if="tasks.length > shown.length"
      class="dash-muted tasks-more"
    >
      {{ $t('dashboard.widgets.tasks.more', {count: tasks.length - shown.length}) }}
    </div>
  </div>
</template>

<script lang="ts">
/**
 * CronTaskCard —— 定时任务 widget（仪表盘一期 W2）。
 *
 * 数据源：现有任务列表端点（getTaskList）拉取清单渲染前 N 行；
 * KPI 数字（已启用口径）走 dashboard 响应 tasks.enabled（决策 #1），
 * 本卡只做名称与启用态展示（任务执行态/next_run_time 为二期，不展示）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { ScheduledTask } from '@/api/tasks'

const MAX_ROWS = 6

@Component({ name: 'CronTaskCard' })
export default class CronTaskCard extends Vue {
  @Prop({ required: true }) private tasks!: ScheduledTask[]

  private get shown(): ScheduledTask[] {
    // 启用优先、再按 id 稳定排序，截断展示行数
    return [...this.tasks]
      .sort((a, b) => Number(b.enabled) - Number(a.enabled) || a.taskId - b.taskId)
      .slice(0, MAX_ROWS)
  }
}
</script>

<style lang="scss" scoped>
.tasks-more {
  font-size: 11.5px;
  margin-top: 6px;
}
</style>
