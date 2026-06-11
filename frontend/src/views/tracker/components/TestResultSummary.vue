<template>
  <div class="result-summary">
    <div class="result-icon" :class="resultClass">
      <svg v-if="result === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M22 11.08V12a10 10 0 11-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="15" y1="9" x2="9" y2="15"></line>
        <line x1="9" y1="9" x2="15" y2="15"></line>
      </svg>
    </div>
    <div class="result-info">
      <div class="result-title">
        <span class="result-icon-emoji">{{ result === 'success' ? '✅' : '❌' }}</span>
        <span>判断结果: {{ result === 'success' ? '成功' : '失败' }}</span>
      </div>
      <div class="result-desc">
        {{ result === 'success' ? '该消息判定为成功状态' : '该消息判定为失败状态（失败优先）' }}
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

@Component({
  name: 'TestResultSummary'
})
export default class TestResultSummary extends Vue {
  @Prop({ type: String, required: true })
  readonly result!: 'success' | 'failed'

  get resultClass() {
    return this.result
  }
}
</script>

<style lang="scss" scoped>
.result-summary {
  display: flex;
  align-items: center;
  padding: 24px;
  background-color: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 24px;
  transition: all 0.3s ease;

  &:hover {
    background-color: #edeff2;
  }

  .result-icon {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 24px;
    flex-shrink: 0;
    transition: transform 0.3s ease;

    &:hover {
      transform: scale(1.05);
    }

    svg {
      width: 36px;
      height: 36px;
    }

    &.success {
      background-color: #e1f3d8;
      svg {
        color: #67c23a;
      }
    }

    &.failure {
      background-color: #fef0f0;
      svg {
        color: #f56c6c;
      }
    }
  }

  .result-info {
    flex: 1;

    .result-title {
      font-size: 20px;
      font-weight: 600;
      color: #303133;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 8px;

      .result-icon-emoji {
        font-size: 22px;
      }
    }

    .result-desc {
      font-size: 14px;
      color: #909399;
    }
  }
}
</style>
