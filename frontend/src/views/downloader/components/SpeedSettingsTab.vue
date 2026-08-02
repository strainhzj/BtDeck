<template>
  <div class="speed-settings-tab">
    <!-- 全局速度限制 -->
    <div class="form-section form-section--limits">
      <div class="form-section-title">
        <span class="section-title-icon"><LucideIcon name="gauge" :size="15" /></span>
        <span>全局速度限制</span>
        <span class="section-index">01</span>
      </div>
      <el-form :model="formData" label-width="140px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="下载速度限制">
              <div class="speed-input-group">
                <el-input-number
                  v-model="formData.download_speed_limit"
                  :min="0"
                  :step="100"
                  controls-position="right"
                  style="flex: 1;"
                />
                <el-select v-model="formData.dl_speed_unit" style="width: 100px;">
                  <el-option label="KB/s" :value="0" />
                  <el-option label="MB/s" :value="1" />
                </el-select>
              </div>
              <p class="form-hint">设置为 0 表示不限制</p>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="上传速度限制">
              <div class="speed-input-group">
                <el-input-number
                  v-model="formData.upload_speed_limit"
                  :min="0"
                  :step="100"
                  controls-position="right"
                  style="flex: 1;"
                />
                <el-select v-model="formData.ul_speed_unit" style="width: 100px;">
                  <el-option label="KB/s" :value="0" />
                  <el-option label="MB/s" :value="1" />
                </el-select>
              </div>
              <p class="form-hint">设置为 0 表示不限制</p>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 分时段限速 -->
    <div class="form-section form-section--schedule">
      <div class="form-section-title">
        <span class="section-title-icon"><LucideIcon name="clock" :size="15" /></span>
        <span>分时段限速</span>
        <span class="section-index">02</span>
      </div>
      <div class="switch-item">
        <span class="switch-label">启用分时段限速</span>
        <el-switch
          v-model="enableScheduling"
          active-color="#059669"
          inactive-color="#d1d5db"
        />
      </div>
    </div>

    <!-- 限速规则列表 -->
    <div class="form-section form-section--rules">
      <div class="form-section-title">
        <span class="section-title-icon"><LucideIcon name="list-checks" :size="15" /></span>
        <span>限速规则</span>
        <span class="section-count">{{ scheduleRules.length }} RULES</span>
      </div>

      <!-- 规则卡片列表 -->
      <div v-if="scheduleRules.length > 0" class="rules-list">
        <div
          v-for="(rule, index) in scheduleRules"
          :key="rule.id || index"
          class="rule-card"
        >
          <div class="rule-header">
            <span class="rule-title">{{ rule.name || `规则 ${index + 1}` }}</span>
            <div class="rule-actions">
              <el-button
                size="mini"
                :disabled="index === 0"
                @click="moveRuleUp(index)"
              >
                <LucideIcon name="arrow-up" :size="13" />
                上移
              </el-button>
              <el-button
                size="mini"
                :disabled="index === scheduleRules.length - 1"
                @click="moveRuleDown(index)"
              >
                <LucideIcon name="arrow-down" :size="13" />
                下移
              </el-button>
              <el-switch
                v-model="rule.enabled"
                active-color="#059669"
                inactive-color="#d1d5db"
              />
              <el-button
                type="danger"
                size="mini"
                @click="removeRule(index)"
              >
                <LucideIcon name="trash-2" :size="13" />
                删除
              </el-button>
            </div>
          </div>
          <div class="rule-content">
            <div class="rule-field">
              <label class="field-label">开始时间</label>
              <el-time-picker
                v-model="rule.start_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="选择时间"
                style="width: 100%;"
              />
            </div>
            <div class="rule-field">
              <label class="field-label">结束时间</label>
              <el-time-picker
                v-model="rule.end_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="选择时间"
                style="width: 100%;"
              />
            </div>
          </div>
          <div class="rule-weekdays">
            <label class="field-label">适用星期</label>
            <div class="weekday-selector">
              <el-checkbox
                v-for="day in weekdays"
                :key="day.value"
                v-model="rule.weekdays"
                :label="day.value"
                class="weekday-checkbox"
              >
                {{ day.label }}
              </el-checkbox>
            </div>
          </div>
          <div class="rule-speed">
            <div class="speed-block">
              <div class="speed-title">
                <span>下载限速</span>
                <el-switch v-model="rule.download.enabled" active-color="#059669" inactive-color="#d1d5db" />
              </div>
              <div class="speed-input-group">
                <el-input-number
                  v-model="rule.download.speed_limit"
                  :min="0"
                  :step="100"
                  controls-position="right"
                  :disabled="!rule.download.enabled"
                  style="flex: 1;"
                />
                <el-select v-model="rule.download.speed_unit" :disabled="!rule.download.enabled" style="width: 100px;">
                  <el-option label="KB/s" :value="0" />
                  <el-option label="MB/s" :value="1" />
                </el-select>
              </div>
            </div>
            <div class="speed-block">
              <div class="speed-title">
                <span>上传限速</span>
                <el-switch v-model="rule.upload.enabled" active-color="#059669" inactive-color="#d1d5db" />
              </div>
              <div class="speed-input-group">
                <el-input-number
                  v-model="rule.upload.speed_limit"
                  :min="0"
                  :step="100"
                  controls-position="right"
                  :disabled="!rule.upload.enabled"
                  style="flex: 1;"
                />
                <el-select v-model="rule.upload.speed_unit" :disabled="!rule.upload.enabled" style="width: 100px;">
                  <el-option label="KB/s" :value="0" />
                  <el-option label="MB/s" :value="1" />
                </el-select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 添加规则按钮 -->
      <el-button
        class="add-rule-btn"
        :disabled="!enableScheduling"
        @click="addRule"
      >
        <LucideIcon class="button-icon" name="plus" :size="15" />
        添加限速规则
      </el-button>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { Downloader, DownloaderSettings, DownloaderCapabilities, SpeedScheduleRule } from '../types'
import { resolveEnableSchedule } from '../settings'

interface LegacySpeedScheduleRule {
  dl_speed_limit?: number
  ul_speed_limit?: number
  dl_speed_unit?: number
  ul_speed_unit?: number
  speed_limit?: number
  speed_unit?: number
  download?: SpeedScheduleRule['download']
  upload?: SpeedScheduleRule['upload']
}

@Component({
  name: 'SpeedSettingsTab'
})
export default class SpeedSettingsTab extends Vue {
  @Prop({ required: true }) downloader!: Downloader
  @Prop({ required: true }) settings!: DownloaderSettings
  @Prop({ required: true }) capabilities!: DownloaderCapabilities

  // 表单数据
  private formData = {
    download_speed_limit: 0,
    upload_speed_limit: 0,
    dl_speed_unit: 0 as 0 | 1,  // 下载速度单位
    ul_speed_unit: 0 as 0 | 1   // 上传速度单位
  }

  // 分时段限速开关
  private enableScheduling = false

  // 限速规则列表
  private scheduleRules: (SpeedScheduleRule & { name?: string })[] = []

  // 星期选项
  private weekdays = [
    { label: '周一', value: 0 },
    { label: '周二', value: 1 },
    { label: '周三', value: 2 },
    { label: '周四', value: 3 },
    { label: '周五', value: 4 },
    { label: '周六', value: 5 },
    { label: '周日', value: 6 }
  ]

  // 计算属性：下载器类型
  get downloaderType(): 0 | 1 {
    // 优先使用驼峰命名（后端API返回格式），如果不存在则使用蛇形命名（兼容旧数据）
    const type = this.downloader.downloaderType ?? this.downloader.downloader_type
    return type ?? 0  // 默认 qBittorrent
  }

  // 监听设置变化
  @Watch('settings', { immediate: true, deep: true })
  onSettingsChange(val: DownloaderSettings) {
    if (val) {
      // 处理下载速度单位（优先使用新字段，回退到旧字段）
      const dlSpeedUnitValue = val.dlSpeedUnit ?? val.dl_speed_unit ?? val.speed_unit ?? 0
      const dlSpeedUnitNumber = typeof dlSpeedUnitValue === 'number' ? dlSpeedUnitValue : parseInt(dlSpeedUnitValue, 10)

      // 处理上传速度单位（优先使用新字段，回退到旧字段）
      const ulSpeedUnitValue = val.ulSpeedUnit ?? val.ul_speed_unit ?? val.speed_unit ?? 0
      const ulSpeedUnitNumber = typeof ulSpeedUnitValue === 'number' ? ulSpeedUnitValue : parseInt(ulSpeedUnitValue, 10)

      // 使用 ?? 而不是 ||，避免 0 被当作 falsy 值
      this.formData.download_speed_limit = val.download_speed_limit ?? val.dlSpeedLimit ?? 0
      this.formData.upload_speed_limit = val.upload_speed_limit ?? val.ulSpeedLimit ?? 0
      this.formData.dl_speed_unit = dlSpeedUnitNumber
      this.formData.ul_speed_unit = ulSpeedUnitNumber

      // 处理分时段规则（确保正确清空或加载）
      const scheduleEnabled = resolveEnableSchedule(val)

      if (val.schedule_rules && val.schedule_rules.length > 0) {
        // 后端返回了规则数据，加载规则
        this.scheduleRules = val.schedule_rules.map((rule, index) => {
          const weekdays = this.normalizeWeekdays(rule.weekdays || [])
          const legacyRule = rule as unknown as LegacySpeedScheduleRule
          const legacyDownloadLimit = legacyRule.dl_speed_limit
          const legacyUploadLimit = legacyRule.ul_speed_limit
          const downloadConfig = rule.download || {
            enabled: legacyDownloadLimit !== undefined ? legacyDownloadLimit > 0 : true,
            speed_limit: legacyDownloadLimit ?? legacyRule.speed_limit ?? 500,
            speed_unit: this.normalizeSpeedUnit(legacyRule.dl_speed_unit ?? legacyRule.speed_unit)
          }
          const uploadConfig = rule.upload || {
            enabled: legacyUploadLimit !== undefined ? legacyUploadLimit > 0 : false,
            speed_limit: legacyUploadLimit ?? legacyRule.speed_limit ?? 0,
            speed_unit: this.normalizeSpeedUnit(legacyRule.ul_speed_unit ?? legacyRule.speed_unit)
          }

          return {
            ...rule,
            id: rule.id,
            name: `规则 ${index + 1}`,
            sort_order: rule.sort_order ?? index,
            start_time: rule.start_time || '09:00',
            end_time: rule.end_time || '18:00',
            weekdays,
            download: {
              enabled: downloadConfig.enabled !== false,
              speed_limit: downloadConfig.speed_limit ?? 0,
              speed_unit: downloadConfig.speed_unit ?? 0
            },
            upload: {
              enabled: uploadConfig.enabled !== false,
              speed_limit: uploadConfig.speed_limit ?? 0,
              speed_unit: uploadConfig.speed_unit ?? 0
            },
            enabled: rule.enabled !== false
          }
        })
        this.enableScheduling = scheduleEnabled
      } else {
        // 后端返回空数组或 undefined，清空规则
        this.scheduleRules = []
        this.enableScheduling = scheduleEnabled
      }
    } else {
      // settings 为空时也要清空规则
      this.scheduleRules = []
      this.enableScheduling = false
    }
  }

  private normalizeSpeedUnit(value: number | undefined): 0 | 1 {
    return value === 1 ? 1 : 0
  }

  private normalizeWeekdays(weekdays: number[]): number[] {
    if (!Array.isArray(weekdays)) {
      return [0, 1, 2, 3, 4]
    }

    const hasLegacy = weekdays.some((day) => day > 6)
    const normalized = weekdays.map((day) => {
      if (hasLegacy) {
        return day - 1
      }
      return day
    }).filter((day) => day >= 0 && day <= 6)

    return Array.from(new Set(normalized)).sort()
  }

  // 添加规则
  private addRule() {
    const newRule: SpeedScheduleRule & { name: string } = {
      id: undefined,
      name: `规则 ${this.scheduleRules.length + 1}`,
      sort_order: this.scheduleRules.length,
      start_time: '09:00',
      end_time: '18:00',
      weekdays: [0, 1, 2, 3, 4], // 默认周一到周五
      download: {
        enabled: true,
        speed_limit: 500,
        speed_unit: 0
      },
      upload: {
        enabled: false,
        speed_limit: 0,
        speed_unit: 0
      },
      enabled: true
    }

    // 按创建时间倒序排序（最新的在最前）
    this.scheduleRules.unshift(newRule)
  }

  // 删除规则
  private removeRule(index: number) {
    this.scheduleRules.splice(index, 1)

    // 重新命名规则
    this.refreshRuleOrder()
  }

  private moveRuleUp(index: number) {
    if (index <= 0) return
    const temp = this.scheduleRules[index - 1]
    this.scheduleRules.splice(index - 1, 1, this.scheduleRules[index])
    this.scheduleRules.splice(index, 1, temp)
    this.refreshRuleOrder()
  }

  private moveRuleDown(index: number) {
    if (index >= this.scheduleRules.length - 1) return
    const temp = this.scheduleRules[index + 1]
    this.scheduleRules.splice(index + 1, 1, this.scheduleRules[index])
    this.scheduleRules.splice(index, 1, temp)
    this.refreshRuleOrder()
  }

  private refreshRuleOrder() {
    this.scheduleRules.forEach((rule, idx) => {
      rule.name = `规则 ${idx + 1}`
      rule.sort_order = idx
    })
  }

  // 获取表单数据（供父组件调用）
  public getFormData(): Partial<DownloaderSettings> {
    return {
      // 驼峰命名,匹配后端API期望的字段名
      dlSpeedLimit: this.formData.download_speed_limit,
      ulSpeedLimit: this.formData.upload_speed_limit,
      dlSpeedUnit: this.formData.dl_speed_unit,
      ulSpeedUnit: this.formData.ul_speed_unit,
      enableSchedule: this.enableScheduling,
      // 保留旧字段名用于兼容
      download_speed_limit: this.formData.download_speed_limit,
      upload_speed_limit: this.formData.upload_speed_limit,
      speed_unit: this.formData.dl_speed_unit,  // 使用下载单位作为旧字段
      schedule_rules: this.enableScheduling ? this.scheduleRules : undefined
    }
  }

  // 验证表单
  public async validateForm(): Promise<boolean> {
    // 验证速度值
    if (this.formData.download_speed_limit < 0) {
      return false
    }
    if (this.formData.upload_speed_limit < 0) {
      return false
    }

    // 验证分时段规则
    if (this.enableScheduling && this.scheduleRules.length > 0) {
      for (const rule of this.scheduleRules) {
        // 验证时间范围
        if (!rule.start_time || !rule.end_time) {
          return false
        }

        // 验证星期选择
        if (!rule.weekdays || rule.weekdays.length === 0) {
          return false
        }

        // 验证下载速度限制
        if (rule.download?.enabled && rule.download.speed_limit < 0) {
          return false
        }

        // 验证上传速度限制
        if (rule.upload?.enabled && rule.upload.speed_limit < 0) {
          return false
        }

        // 验证开始时间必须早于结束时间
        if (rule.start_time >= rule.end_time) {
          return false
        }
      }
    }

    return true
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.speed-settings-tab {
  padding: var(--spacing-md) 0;
}

.form-section {
  margin-bottom: var(--spacing-xl);
}

.form-section-title {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);

  &::before {
    content: '';
    width: 4px;
    height: 16px;
    background: var(--color-primary);
    border-radius: 2px;
  }
}

.speed-input-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.form-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 4px 0 0 0;
  display: flex;
  align-items: center;
  gap: 6px;

  &.warning-hint {
    color: #92400E;
    background: var(--color-warning-light);
    padding: var(--spacing-sm);
    border-radius: var(--radius-md);
  }
}

.hint-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-sm);
}

.switch-label {
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

// 规则卡片列表
.rules-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.rule-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
}

.rule-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}

.rule-title {
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-content {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.rule-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
}

.field-label {
  font-size: 13px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.field-unit {
  position: absolute;
  right: 8px;
  bottom: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  pointer-events: none;
}

::v-deep .rule-field .el-input-number {
  width: 100%;
}

::v-deep .rule-field .el-input-number .el-input__inner {
  padding-right: 50px;
}

.rule-weekdays {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.rule-speed {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.speed-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--spacing-sm);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
}

.speed-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.weekday-selector {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

::v-deep .weekday-checkbox {
  margin-right: 0;
}

::v-deep .weekday-checkbox .el-checkbox__input {
  display: none;
}

::v-deep .weekday-checkbox .el-checkbox__label {
  padding-left: 0;
  padding-right: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  padding: 6px 16px;
  transition: all var(--transition-base);
  cursor: pointer;
  user-select: none;
  min-width: 48px;
  text-align: center;
}

::v-deep .weekday-checkbox.is-checked .el-checkbox__label {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

// 添加规则按钮
.add-rule-btn {
  width: 100%;
  padding: var(--spacing-md);
  border: 2px dashed var(--color-border-primary);
  background: transparent;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: all var(--transition-base);

  &:hover:not(:disabled) {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: var(--color-primary-lightest);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
}

.button-icon {
  width: 16px;
  height: 16px;
}

// Dense control-room treatment. These overrides intentionally keep the
// existing form model and validation behavior while reducing vertical travel.
.speed-settings-tab {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.58fr);
  gap: 10px;
  padding: 0;
}

.form-section {
  min-width: 0;
  margin: 0;
  padding: 13px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 12px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.55)),
    var(--color-bg-secondary);

  &--limits {
    grid-column: 1;
  }

  &--schedule {
    grid-column: 2;
  }

  &--rules {
    grid-column: 1 / -1;
  }
}

.form-section-title {
  min-height: 24px;
  margin-bottom: 10px;
  gap: 7px;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;

  &::before {
    display: none;
  }
}

.section-title-icon {
  display: inline-flex;
  width: 25px;
  height: 25px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--color-primary-rgb), 0.22);
  border-radius: 7px;
  color: var(--color-primary);
  background: rgba(var(--color-primary-rgb), 0.07);
}

.section-index,
.section-count {
  margin-left: auto;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  font-size: 8px;
  letter-spacing: 0.12em;
}

.speed-settings-tab ::v-deep .el-form-item {
  margin-bottom: 0;
}

.speed-settings-tab ::v-deep .el-form-item__label,
.field-label {
  font-size: 10px;
}

.form-hint {
  font-size: 9px;
}

.switch-item {
  min-height: 54px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 9px;
  background: rgba(var(--color-primary-rgb), 0.035);
}

.switch-label {
  font-size: 11px;
}

.rules-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 9px;
}

.rule-card {
  min-width: 0;
  padding: 11px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.66);
}

.rule-header {
  margin-bottom: 9px;
}

.rule-title {
  font-size: 11px;
}

.rule-actions {
  gap: 4px;
}

.rule-actions ::v-deep .el-button {
  height: 26px;
  margin-left: 0;
  padding: 0 7px;
  font-size: 9px;
}

.rule-actions ::v-deep .el-button span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.rule-content,
.rule-speed {
  gap: 7px;
  margin-bottom: 8px;
}

.rule-speed {
  margin-top: 8px;
}

.speed-block {
  gap: 6px;
  padding: 8px;
}

.speed-title {
  font-size: 10px;
}

.weekday-selector {
  gap: 4px;
}

::v-deep .weekday-checkbox .el-checkbox__label {
  min-width: 30px;
  padding: 4px 7px;
  font-size: 9px;
}

.add-rule-btn {
  height: 34px;
  padding: 0 12px;
  border-width: 1px;
  font-size: 10px;
}

.add-rule-btn ::v-deep span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

@media (max-width: 1080px) {
  .speed-settings-tab,
  .rules-list {
    grid-template-columns: 1fr;
  }

  .form-section:nth-child(n) {
    grid-column: 1;
  }
}
</style>
