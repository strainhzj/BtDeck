<template>
  <el-tooltip :content="tooltip" :placement="placement">
    <el-button
      :type="type"
      :icon="lucideIcon ? '' : icon"
      :circle="circle"
      :size="size"
      :disabled="disabled"
      :loading="loading"
      @click="handleClick"
    >
      <LucideIcon v-if="lucideIcon" :name="lucideIcon" :size="lucideSize" />
      <slot v-if="!circle"></slot>
    </el-button>
  </el-tooltip>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'

@Component({
  name: 'BatchButton',
  components: { LucideIcon }
})
export default class extends Vue {
  // ========== Props 定义 ==========

  /**
   * 按钮类型
   * @type {'primary' | 'success' | 'warning' | 'danger' | 'info' | 'text' | 'default'}
   */
  @Prop({ default: 'default' })
  private type!: string

  /**
   * Element UI 图标类名（与 lucide-icon 二选一，优先 lucide-icon）
   * @example 'el-icon-check' | 'el-icon-delete' | 'el-icon-refresh'
   */
  @Prop({ default: '' })
  private icon!: string

  /**
   * Lucide 图标名（提供时用 LucideIcon 渲染，替代 el-icon）
   * @example 'play' | 'trash' | 'settings'
   */
  @Prop({ default: '' })
  private lucideIcon!: string

  /**
   * Lucide 图标尺寸（px）
   * @default 16
   */
  @Prop({ default: 16 })
  private lucideSize!: number

  /**
   * 鼠标悬停时显示的提示文字
   */
  @Prop({ required: true })
  private tooltip!: string

  /**
   * Tooltip 显示位置
   * @type {'top' | 'bottom' | 'left' | 'right'}
   */
  @Prop({ default: 'top' })
  private placement!: string

  /**
   * 是否为圆形按钮
   * @default true（批量操作默认使用圆形按钮）
   */
  @Prop({ default: true })
  private circle!: boolean

  /**
   * 按钮尺寸
   * @type {'medium' | 'small' | 'mini'}
   * @default 'medium'
   */
  @Prop({ default: 'medium' })
  private size!: string

  /**
   * 是否禁用
   * @default false
   */
  @Prop({ default: false })
  private disabled!: boolean

  /**
   * 是否加载中
   * @default false
   */
  @Prop({ default: false })
  private loading!: boolean

  // ========== Methods ==========

  /**
   * 处理按钮点击事件
   */
  private handleClick() {
    if (!this.disabled && !this.loading) {
      this.$emit('click')
    }
  }
}
</script>

<style lang="scss" scoped>
// 批量操作按钮的统一样式
.el-button + .el-button {
  margin-left: 8px;
}
</style>
