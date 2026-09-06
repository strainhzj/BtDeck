<template>
  <el-drawer
    custom-class="m-cond-sheet"
    direction="btt"
    size="76%"
    :visible="visible"
    :with-header="false"
    :append-to-body="true"
    :close-on-click-modal="true"
    @update:visible="onVisibleUpdate"
  >
    <div class="m-cond-sheet__body">
      <div class="m-cond-sheet__grabber" aria-hidden="true" />
      <div class="m-cond-sheet__header">
        <span class="m-cond-sheet__title">编辑条件</span>
        <button type="button" class="m-cond-sheet__done" @click="confirm">完成</button>
      </div>

      <!-- 字段 -->
      <div class="m-cond-sheet__row">
        <span class="m-cond-sheet__label">字段</span>
        <el-select
          v-model="draft.field"
          placeholder="选择字段"
          size="small"
          class="m-cond-sheet__control"
          @change="onFieldChange"
        >
          <el-option-group
            v-for="section in fieldSections"
            :key="section.label"
            :label="section.label"
          >
            <el-option
              v-for="field in section.fields"
              :key="field.key"
              :label="field.label"
              :value="field.key"
            />
          </el-option-group>
        </el-select>
      </div>

      <!-- 操作符 -->
      <div class="m-cond-sheet__row">
        <span class="m-cond-sheet__label">操作</span>
        <el-select
          v-model="draft.operator"
          placeholder="选择操作"
          size="small"
          class="m-cond-sheet__control"
          :disabled="!draft.field"
          @change="onOperatorChange"
        >
          <el-option-group
            v-for="group in operatorGroups"
            :key="group.type"
            :label="group.label"
          >
            <el-option
              v-for="op in group.operators"
              :key="op.value"
              :label="op.label"
              :value="op.value"
            />
          </el-option-group>
        </el-select>
      </div>

      <!-- 条件值：复用桌面 ConditionValueInput，输入语义两端一致 -->
      <div class="m-cond-sheet__row">
        <span class="m-cond-sheet__label m-cond-sheet__label--value">内容</span>
        <div class="m-cond-sheet__value">
          <ConditionValueInput
            :field="draft.field"
            :operator="draft.operator"
            :value="draft.value"
            :field-options="fieldOptionsForDraft"
            @input="onValueChange"
            @change="onValueChange"
          />
        </div>
      </div>

      <!-- 包含/排除 -->
      <div class="m-cond-sheet__row">
        <span class="m-cond-sheet__label">方式</span>
        <el-radio-group
          v-model="draft.mode"
          size="small"
          class="m-cond-sheet__control"
          :disabled="!excludeSupported"
        >
          <el-radio-button label="include">包含</el-radio-button>
          <el-radio-button label="exclude" :disabled="!excludeSupported">排除</el-radio-button>
        </el-radio-group>
      </div>
    </div>
  </el-drawer>
</template>

<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import ConditionValueInput from '@/components/torrents/ConditionValueInput.vue'
import {
  AdvancedSearchConditionState,
  AdvancedSearchConditionValue,
  operatorSupportsExclude,
  transitionConditionValue
} from '@/components/torrents/advancedSearchState'
import {
  ADVANCED_SEARCH_FIELD_SECTIONS,
  AdvancedSearchDynamicOptionSet,
  OperatorDisplayGroup,
  SearchField,
  generateConditionId,
  getOperatorGroupsForField,
  getSearchFieldInfo,
  getSearchFieldOptions
} from '@/components/torrents/advancedSearchFields'

interface FieldSection {
  label: string
  fields: readonly SearchField[]
}

/**
 * 移动端单条条件编辑底部弹层（方案三移动原生重构）：
 * - 打开时克隆父级条件为本地草稿，确认才回写（中途下滑关闭即放弃）；
 * - 字段/操作符/值/包含排除的联动语义与桌面 AdvancedSearchBuilder 同源
 *   （共享层 advancedSearchFields + ConditionValueInput）。
 */
@Component({
  name: 'ConditionEditSheet',
  components: {
    ConditionValueInput
  }
})
export default class ConditionEditSheet extends Vue {
  @Prop({ type: Boolean, default: false }) readonly visible!: boolean
  @Prop({ type: Object, default: null })
  readonly condition!: AdvancedSearchConditionState | null
  @Prop({ type: Object, default: () => ({}) })
  readonly dynamicOptions!: AdvancedSearchDynamicOptionSet

  private draft: AdvancedSearchConditionState = {
    id: '',
    field: '',
    operator: '',
    value: null,
    mode: 'include'
  }

  @Watch('visible')
  private onVisibleChange(visible: boolean) {
    if (!visible) return
    const source = this.condition
    this.draft = source
      ? JSON.parse(JSON.stringify(source)) as AdvancedSearchConditionState
      : {
          id: generateConditionId(),
          field: '',
          operator: '',
          value: null,
          mode: 'include'
        }
  }

  // 模板禁直调模块级函数：以下均为实例包装
  private get fieldSections(): FieldSection[] {
    return ADVANCED_SEARCH_FIELD_SECTIONS.map(section => ({
      label: section.label,
      fields: section.fields
    }))
  }

  private get operatorGroups(): OperatorDisplayGroup[] {
    return getOperatorGroupsForField(this.draft.field)
  }

  private get excludeSupported(): boolean {
    return operatorSupportsExclude(this.draft.operator)
  }

  private get fieldOptionsForDraft(): Array<{ label: string, value: string }> {
    return getSearchFieldOptions(this.draft.field, {
      categoryOptions: this.dynamicOptions.categoryOptions || [],
      tagOptions: this.dynamicOptions.tagOptions || [],
      downloaderOptions: this.dynamicOptions.downloaderOptions || []
    })
  }

  // 字段变更：清空操作符并按字段类型重置值（与桌面 onFieldChange 同源）
  private onFieldChange() {
    this.draft.operator = ''
    const field = getSearchFieldInfo(this.draft.field)
    this.draft.value = transitionConditionValue(
      this.draft.field,
      field?.type,
      this.draft.operator
    )
    this.draft.mode = 'include'
  }

  // 操作符变更：按新操作符重置值形态；不支持排除时回落包含
  private onOperatorChange() {
    const field = getSearchFieldInfo(this.draft.field)
    this.draft.value = transitionConditionValue(
      this.draft.field,
      field?.type,
      this.draft.operator
    )
    if (!operatorSupportsExclude(this.draft.operator)) {
      this.draft.mode = 'include'
    }
  }

  private onValueChange(value: AdvancedSearchConditionValue) {
    this.draft.value = value
  }

  private onVisibleUpdate(visible: boolean) {
    this.$emit('update:visible', visible)
  }

  private confirm() {
    this.$emit('confirm', JSON.parse(JSON.stringify(this.draft)) as AdvancedSearchConditionState)
    this.$emit('update:visible', false)
  }
}
</script>

<style scoped>
/* 弹层挂 body（append-to-body），scoped 够不到：核心样式走全局块（下方） */
</style>

<style>
.m-cond-sheet {
  border-radius: 16px 16px 0 0;
  background: #fff;
}

.m-cond-sheet__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  padding: 8px 16px calc(16px + env(safe-area-inset-bottom));
  overflow-y: auto;
}

.m-cond-sheet__grabber {
  align-self: center;
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: #e4e7ed;
}

.m-cond-sheet__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.m-cond-sheet__title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.m-cond-sheet__done {
  padding: 6px 12px;
  font-size: 14px;
  color: var(--color-primary, #059669);
  background: transparent;
  border: none;
}

.m-cond-sheet__row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.m-cond-sheet__label {
  font-size: 12px;
  line-height: 1;
  color: #909399;
}

/* “内容”行是用户要找的填写目标，用主题色与中性行区分（同桌面堆叠布局取舍） */
.m-cond-sheet__label--value {
  color: var(--color-primary, #059669);
  font-weight: 600;
}

.m-cond-sheet__control {
  width: 100%;
}

/* 内容行唯一强调底色：让“填内容”从一排灰框里跳出来（边框随主题色阶联动） */
.m-cond-sheet__value {
  padding: 8px;
  background: var(--color-primary-lightest, #d1fae5);
  border: 1px solid rgba(var(--color-primary-rgb, 5, 150, 105), 0.35);
  border-radius: 6px;
}

/* 移动端触控目标：弹层内输入/选择控件 32px→40px（同桌面窄屏断点） */
.m-cond-sheet .el-input__inner,
.m-cond-sheet .el-input-number .el-input__inner {
  height: 40px;
  line-height: 40px;
  font-size: 14px;
}

.m-cond-sheet .el-input__icon {
  line-height: 40px;
}

.m-cond-sheet .el-radio-group {
  display: flex;
  width: 100%;
}

.m-cond-sheet .el-radio-button {
  flex: 1;
}

.m-cond-sheet .el-radio-button__inner {
  width: 100%;
  padding: 12px 0;
  font-size: 14px;
}
</style>
