<template>
  <div v-if="demoEnabled" class="demo-mode-banner" role="status" aria-live="polite">
    <lucide-icon name="flask-conical" :size="15" :stroke-width="2" />
    <strong>演示模式</strong>
    <span>数据为本地模拟，不产生后端副作用</span>
    <button type="button" class="demo-mode-banner__reset" @click.stop="resetDemoData">
      <lucide-icon name="rotate-ccw" :size="13" :stroke-width="2" />
      重置数据
    </button>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'
import { Message } from 'element-ui'
import LucideIcon from '@/components/common/LucideIcon.vue'
import { emitDemoReset, isDemoMode } from '@/demo/config'
import { demoStore } from '@/demo/demo-store'

export default Vue.extend({
  name: 'DemoModeBanner',
  components: { LucideIcon },
  computed: {
    demoEnabled(): boolean {
      return isDemoMode()
    }
  },
  methods: {
    resetDemoData(): void {
      demoStore.reset()
      emitDemoReset()
      Message.success('演示数据已重置')
      if (typeof window !== 'undefined') window.location.reload()
    }
  }
})
</script>

<style lang="scss" scoped>
.demo-mode-banner {
  position: fixed;
  top: 10px;
  left: 50%;
  z-index: 2100;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 32px;
  padding: 0 13px;
  border: 1px solid var(--color-warning, #d97706);
  border-radius: var(--radius-full, 9999px);
  background: var(--color-warning-lightest, #fffbeb);
  color: var(--color-warning-dark, #92400e);
  box-shadow: var(--shadow-sm, 0 2px 8px rgba(15, 23, 42, 0.08));
  font-size: 12px;
  line-height: 1.2;
  transform: translateX(-50%);
  pointer-events: auto;

  strong {
    font-weight: 700;
  }

  span {
    color: var(--color-text-secondary, #6b7280);
  }

  &__reset {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 7px;
    border: 0;
    border-radius: 5px;
    color: var(--color-warning-dark, #92400e);
    background: rgba(217, 119, 6, 0.12);
    cursor: pointer;
    font: inherit;

    &:hover {
      background: rgba(217, 119, 6, 0.2);
    }
  }
}

@media (max-width: 640px) {
  .demo-mode-banner {
    top: 6px;
    max-width: calc(100vw - 24px);
    white-space: nowrap;

    span {
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
}
</style>
