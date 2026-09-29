<template>
  <div
    class="fun-slide"
    :class="{'fun-slide--active': active}"
    data-testid="fun-slide"
  >
    <div class="fun-slide__badge">{{ badge }}</div>
    <h2 class="fun-slide__title">{{ title }}</h2>
    <div class="fun-slide__body">
      <slot />
    </div>
  </div>
</template>

<script lang="ts">
/**
 * 趣味报告翻页卡（statistics-reports W6，fun-report 专属）。
 *
 * 纯展示卡面：徽标 + 标题 + 内容插槽；翻页/过渡由父级 fun-report 驱动
 * （过渡作用于卡片内容层，不影响根覆盖层的 fixed 定位——决策 10）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'FunSlide' })
export default class FunSlide extends Vue {
  @Prop({ type: String, default: '' })
  private readonly badge!: string

  @Prop({ type: String, required: true })
  private readonly title!: string

  @Prop({ type: Boolean, default: false })
  private readonly active!: boolean
}
</script>

<style scoped>
.fun-slide {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  width: min(720px, 92vw);
  min-height: 60vh;
  padding: 32px 36px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.35);
  text-align: center;
}

.fun-slide__badge {
  font-size: 40px;
  line-height: 1;
}

.fun-slide__title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}

.fun-slide__body {
  width: 100%;
  font-size: 16px;
  color: #303133;
  overflow-y: auto;
  max-height: 50vh;
}
</style>
