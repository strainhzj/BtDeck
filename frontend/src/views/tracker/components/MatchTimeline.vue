<template>
  <div class="match-timeline">
    <div class="timeline-title">
      <span class="title-icon">⏱️</span>
      <span>匹配过程时间线</span>
    </div>
    <div class="timeline-steps">
      <div
        v-for="(step, index) in steps"
        :key="index"
        class="timeline-step"
      >
        <div class="step-number">{{ index + 1 }}</div>
        <div class="step-content">
          <div class="step-title">{{ step.title }}</div>
          <div class="step-desc" v-html="step.description"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

/**
 * 时间线步骤接口
 */
interface TimelineStep {
  title: string
  description: string
}

@Component({
  name: 'MatchTimeline'
})
export default class MatchTimeline extends Vue {
  @Prop({ type: Array, required: true })
  readonly steps!: TimelineStep[]
}
</script>

<style lang="scss" scoped>
.match-timeline {
  margin-bottom: 24px;
  padding: 16px;
  background-color: #f5f7fa;
  border-radius: 8px;

  .timeline-title {
    font-size: 15px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 4px;

    .title-icon {
      font-size: 16px;
    }
  }

  .timeline-steps {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .timeline-step {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 12px;
      background: #ffffff;
      border-radius: 4px;
      transition: all 0.2s ease;

      &:hover {
        background: #fafafa;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
      }

      .step-number {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        background: #ecf5ff;
        color: #409eff;
        border-radius: 50%;
        font-size: 12px;
        font-weight: 600;
        flex-shrink: 0;
      }

      .step-content {
        flex: 1;

        .step-title {
          font-size: 14px;
          font-weight: 500;
          color: #303133;
          margin-bottom: 4px;
        }

        .step-desc {
          font-size: 12px;
          color: #909399;
          line-height: 1.5;

          :deep(.highlight) {
            color: #67c23a;
            font-weight: 500;
          }
        }
      }
    }
  }
}
</style>
