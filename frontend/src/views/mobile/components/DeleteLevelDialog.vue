<template>
  <el-dialog
    :visible="visible"
    title="删除种子"
    width="92%"
    append-to-body
    custom-class="m-delete-level-dialog"
    @update:visible="onVisibleChange"
  >
    <div class="m-delete-target" :title="name">「{{ name }}」</div>
    <div class="m-delete-level-list">
      <button
        v-for="opt in levelOptions"
        :key="opt.level"
        type="button"
        class="m-delete-level-option"
        :class="{'is-danger': opt.level === 1}"
        :disabled="busy"
        @click="choose(opt)"
      >
        <LucideIcon
          :name="opt.icon"
          :size="16"
          :class="{'m-delete-level-icon-danger': opt.level === 1}"
        />
        <span class="m-delete-level-text">{{ opt.label }}</span>
      </button>
    </div>
    <div class="m-delete-hint">等级1 删除任务与数据、不可恢复；等级3 备份失败时自动降级为标记待删除</div>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'

/**
 * 移动端按等级删除种子对话框（2026-09-05 移动验收补齐）：
 * 桌面端种子页删除按钮的四级下拉在移动端的等价物——底部弹层列出四个等级，
 * 点选后按桌面同款文案二次确认（等级1/3 警告式、等级1 error 级），确认通过才
 * 向父页面 emit confirm(level)，由父页面调用 deleteTorrentsWithLevel 执行。
 * 列表页与详情页共用（语义与 api/torrents.ts deleteTorrentsWithLevel 对齐）。
 */

interface DeleteLevelOption {
  level: number
  label: string
  icon: string
}

const DELETE_LEVEL_OPTIONS: DeleteLevelOption[] = [
  { level: 4, label: '等级4：标记为待删除（推荐）', icon: 'tag' },
  { level: 3, label: '等级3：移至回收站', icon: 'trash-2' },
  { level: 2, label: '等级2：删除任务（保留数据）', icon: 'trash' },
  { level: 1, label: '等级1：完全删除', icon: 'alert-triangle' }
]

/** 确认文案用短名（与桌面 index.vue handleDeleteCommand 同源） */
const LEVEL_NAMES: Record<number, string> = {
  4: '标记为待删除',
  3: '移至回收站',
  2: '删除任务（保留数据）',
  1: '完全删除'
}

@Component({ name: 'MobileDeleteLevelDialog' })
export default class MobileDeleteLevelDialog extends Vue {
  @Prop({ type: Boolean, default: false }) private visible!: boolean
  @Prop({ type: String, default: '' }) private name!: string
  /** 父页面删除请求在途时禁用选项，防重复提交 */
  @Prop({ type: Boolean, default: false }) private busy!: boolean

  private levelOptions = DELETE_LEVEL_OPTIONS

  private onVisibleChange(value: boolean): void {
    this.$emit('update:visible', value)
  }

  private async choose(opt: DeleteLevelOption): Promise<void> {
    const levelName = LEVEL_NAMES[opt.level] || '删除'
    // 与桌面端确认文案同款：破坏性等级（1/3）用警告句式，等级1 error 级
    const message = opt.level === 1 || opt.level === 3
      ? `警告：此操作将${levelName}，是否继续？`
      : `确定要将种子${levelName}吗？`
    try {
      await this.$confirm(message, '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: opt.level === 1 ? 'error' : 'warning'
      })
    } catch {
      return
    }
    this.onVisibleChange(false)
    this.$emit('confirm', opt.level)
  }
}
</script>

<style scoped>
.m-delete-target {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
  word-break: break-all;
  margin-bottom: 10px;
}

.m-delete-level-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 全宽选项行：44px 最低触控标准（2026-08-28 移动 UX 审查同款约束） */
.m-delete-level-option {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid var(--color-border-primary, #e5e7eb);
  border-radius: 8px;
  background: #fff;
  color: #303133;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.m-delete-level-option.is-danger {
  border-color: #f56c6c;
  color: #f56c6c;
  margin-top: 4px;
}

.m-delete-level-icon-danger {
  color: #f56c6c;
}

.m-delete-level-text {
  flex: 1;
}

.m-delete-hint {
  margin-top: 10px;
  font-size: 11px;
  color: #909399;
  line-height: 1.5;
}
</style>
