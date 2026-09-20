<template>
  <div class="cron-editor">
    <el-tabs v-model="activeTab" @tab-click="handleTabChange">
      <!-- 模板选择 -->
      <el-tab-pane :label="$t('tasks.cronEditor.tabs.template')" name="template">
        <div class="template-header">
          <span class="template-title">{{ $t('tasks.cronEditor.templateTitle') }}</span>
          <el-select v-model="templateFilter" :placeholder="$t('tasks.cronEditor.filterPlaceholder')" size="small" style="width: 120px;">
            <el-option :label="$t('tasks.cronEditor.category.all')" value="" />
            <el-option :label="$t('tasks.cronEditor.category.basic')" value="基础" />
            <el-option :label="$t('tasks.cronEditor.category.hourly')" value="小时" />
            <el-option :label="$t('tasks.cronEditor.category.daily')" value="日常" />
            <el-option :label="$t('tasks.cronEditor.category.workday')" value="工作日" />
            <el-option :label="$t('tasks.cronEditor.category.weekend')" value="周末" />
          </el-select>
        </div>

        <div class="template-grid">
          <div
            v-for="template in filteredTemplates"
            :key="template.name"
            class="template-item"
            :class="{
              active: selectedTemplate === templateIdentity(template),
              ['template-category-' + template.category]: true
            }"
            @click="selectTemplate(template)"
          >
            <div class="template-icon">
              <i :class="template.icon"></i>
            </div>
            <div class="template-info">
              <div class="template-name">{{ templateDisplayName(template) }}</div>
              <div class="template-desc">{{ templateDescDisplay(template) }}</div>
              <div class="template-cron">
                <el-tag size="mini" :type="getTemplateTagType(template.category)">
                  {{ template.expression }}
                </el-tag>
              </div>
            </div>
            <div class="template-check" v-if="selectedTemplate === templateIdentity(template)">
              <i class="el-icon-check"></i>
            </div>
          </div>
        </div>

        <!-- 自定义模板 -->
        <div class="custom-template-section">
          <div class="section-title">
            <i class="el-icon-setting"></i>
            {{ $t('tasks.cronEditor.customSection') }}
          </div>
          <el-row :gutter="16" class="custom-template-grid">
            <el-col :span="8" v-for="(custom, index) in customTemplates" :key="index">
              <div class="custom-template-item" @click="selectCustomTemplate(custom)">
                <el-tag size="small" :type="custom.enabled ? 'success' : 'info'" closable @close.stop="removeCustomTemplate(index)">
                  {{ custom.name }}
                </el-tag>
                <span class="custom-expression">{{ custom.expression }}</span>
              </div>
            </el-col>
          </el-row>
          <el-button type="text" size="small" @click="showAddCustomTemplate = true">
            <i class="el-icon-plus"></i> {{ $t('tasks.cronEditor.addCustom') }}
          </el-button>
        </div>
      </el-tab-pane>

      <!-- 自定义表达式 -->
      <el-tab-pane :label="$t('tasks.cronEditor.tabs.custom')" name="custom">
        <el-form :model="customForm" :rules="formRules" ref="customFormRef" label-width="80px">
          <el-form-item :label="$t('tasks.cronEditor.expressionLabel')" prop="expression">
            <el-input
              v-model="customForm.expression"
              placeholder="* * * * *"
              @input="handleCustomExpressionChange"
            >
              <template slot="append">
                <el-button @click="validateCustomExpression" icon="el-icon-check" :loading="validating">
                  {{ $t('tasks.cronEditor.validateBtn') }}
                </el-button>
              </template>
            </el-input>
            <div class="expression-help">
              <small>{{ $t('tasks.cronEditor.formatHint') }}</small>
            </div>
          </el-form-item>

          <!-- 可视化配置 -->
          <div class="visual-config">
            <div class="config-title">
              <i class="el-icon-s-grid"></i>
              {{ $t('tasks.cronEditor.visualTitle') }}
            </div>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item :label="$t('tasks.cronEditor.field.minute')" class="minute-field">
                  <el-input
                    v-model="customForm.minute"
                    :placeholder="$t('tasks.cronEditor.field.placeholderMinute')"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip :content="$t('tasks.cronEditor.field.tooltipMinute')" placement="top">
                        <span>{{ $t('tasks.cronEditor.field.minuteShort') }}</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="$t('tasks.cronEditor.field.hour')" class="hour-field">
                  <el-input
                    v-model="customForm.hour"
                    :placeholder="$t('tasks.cronEditor.field.placeholderHour')"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip :content="$t('tasks.cronEditor.field.tooltipHour')" placement="top">
                        <span>{{ $t('tasks.cronEditor.field.hourShort') }}</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item :label="$t('tasks.cronEditor.field.day')" class="day-field">
                  <el-input
                    v-model="customForm.day"
                    :placeholder="$t('tasks.cronEditor.field.placeholderDay')"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip :content="$t('tasks.cronEditor.field.tooltipDay')" placement="top">
                        <span>{{ $t('tasks.cronEditor.field.dayShort') }}</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="$t('tasks.cronEditor.field.month')" class="month-field">
                  <el-input
                    v-model="customForm.month"
                    :placeholder="$t('tasks.cronEditor.field.placeholderMonth')"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip :content="$t('tasks.cronEditor.field.tooltipMonth')" placement="top">
                        <span>{{ $t('tasks.cronEditor.field.monthShort') }}</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item :label="$t('tasks.cronEditor.field.weekday')" class="weekday-field">
              <el-checkbox-group v-model="customForm.weekdays" @change="buildExpressionFromForm">
                <el-checkbox :label="0">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipSun')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdaySun') }}</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="1">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipMon')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdayMon') }}</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="2">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipTue')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdayTue') }}</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="3">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipWed')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdayWed') }}</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="4">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipThu')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdayThu') }}</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="5">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipFri')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdayFri') }}</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="6">
                  <el-tooltip :content="$t('tasks.cronEditor.field.tooltipSat')" placement="top">
                    <span>{{ $t('tasks.cronEditor.field.weekdaySat') }}</span>
                  </el-tooltip>
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </div>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <!-- 执行时间预览 -->
    <div class="execution-preview" v-if="nextExecutions.length > 0 || previewLoading">
      <div class="preview-header">
        <i class="el-icon-time"></i>
        <span class="preview-title">{{ $t('tasks.cronEditor.preview.title') }}</span>
        <el-button
          type="text"
          size="mini"
          @click="refreshExecutionTimes"
          :loading="previewLoading"
          style="float: right;"
        >
          {{ $t('tasks.cronEditor.preview.refresh') }}
        </el-button>
      </div>

      <div v-if="previewLoading" class="preview-loading">
        <el-skeleton :rows="3" animated />
      </div>

      <div v-else class="preview-list">
        <div
          v-for="(time, index) in nextExecutions"
          :key="index"
          class="preview-item"
        >
          <el-tag
            :type="getPreviewTagType(index)"
            size="small"
            :effect="index === 0 ? 'dark' : 'light'"
          >
            #{{ index + 1 }}
          </el-tag>
          <span class="preview-time">{{ formatExecutionTime(time) }}</span>
          <el-tag
            v-if="index === 0"
            type="success"
            size="mini"
            effect="dark"
            class="next-indicator"
          >
            {{ $t('tasks.cronEditor.preview.nextExecute') }}
          </el-tag>
          <span v-if="getTimeUntilExecution(time)" class="time-until">
            {{ getTimeUntilExecution(time) }}
          </span>
        </div>
      </div>

      <div v-if="nextExecutions.length === 0 && !previewLoading" class="preview-empty">
        <el-empty :description="$t('tasks.cronEditor.preview.empty')" :image-size="80" />
      </div>
    </div>

    <!-- 表达式验证状态 -->
    <div class="validation-status" v-if="validationResult">
      <el-alert
        :title="validationResult.valid ? $t('tasks.cronEditor.validation.validTitle') : $t('tasks.cronEditor.validation.invalidTitle')"
        :type="validationResult.valid ? 'success' : 'error'"
        :description="validationResult.message"
        show-icon
        :closable="false"
      >
        <div v-if="validationResult.suggestions && validationResult.suggestions.length > 0" slot="description">
          <div class="suggestions">
            <strong>{{ $t('tasks.cronEditor.validation.suggestion') }}</strong>
            <ul>
              <li v-for="(suggestion, index) in validationResult.suggestions" :key="index">
                {{ suggestion }}
              </li>
            </ul>
          </div>
        </div>
      </el-alert>
    </div>

    <!-- 添加自定义模板对话框 -->
    <el-dialog :title="$t('tasks.cronEditor.addDialog.title')" :visible.sync="showAddCustomTemplate" width="500px">
      <el-form :model="newCustomTemplate" :rules="customTemplateRules" ref="customTemplateRef" label-width="100px">
        <el-form-item :label="$t('tasks.cronEditor.addDialog.nameLabel')" prop="name">
          <el-input v-model="newCustomTemplate.name" :placeholder="$t('tasks.cronEditor.addDialog.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('tasks.cronEditor.addDialog.expressionLabel')" prop="expression">
          <el-input v-model="newCustomTemplate.expression" placeholder="0 * * * *" />
        </el-form-item>
        <el-form-item :label="$t('tasks.cronEditor.addDialog.descLabel')" prop="description">
          <el-input v-model="newCustomTemplate.description" type="textarea" :placeholder="$t('tasks.cronEditor.addDialog.descPlaceholder')" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="showAddCustomTemplate = false">{{ $t('tasks.cronEditor.addDialog.cancel') }}</el-button>
        <el-button type="primary" @click="addCustomTemplate" :loading="savingCustom">{{ $t('tasks.cronEditor.addDialog.save') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import request from '@/utils/request'

interface CronTemplate {
  /** 内置模板身份与展示键（tasks.cronEditor.templates.*）；自定义模板无此字段 */
  key?: string
  /** 自定义模板名称（用户数据，原文直出 Q02）；内置模板不再携带 */
  name?: string
  /** 自定义模板描述；内置模板不再携带 */
  description?: string
  expression: string
  icon: string
  category: string
}

interface ValidationResult {
  valid: boolean
  message: string
  errors?: string[]
  suggestions?: string[]
}

interface CustomTemplate {
  name: string
  expression: string
  description?: string
  enabled: boolean
}

@Component({ name: 'CronEditor' })
export default class CronEditor extends Vue {
  @Prop({ required: true }) value!: string
  @Prop({ default: 5 }) previewCount!: number

  private activeTab = 'template'
  private selectedTemplate = ''
  private templateFilter = ''
  private nextExecutions: Date[] = []
  private validationResult: ValidationResult | null = null
  private validating = false
  private previewLoading = false
  private showAddCustomTemplate = false
  private savingCustom = false

  // 预定义模板
  private templates: CronTemplate[] = [
    {
      key: 'everyMinute',
      expression: '* * * * *',
      icon: 'el-icon-time',
      category: '基础'
    },
    {
      key: 'every5Minutes',
      expression: '*/5 * * * *',
      icon: 'el-icon-timer',
      category: '基础'
    },
    {
      key: 'every15Minutes',
      expression: '*/15 * * * *',
      icon: 'el-icon-timer',
      category: '基础'
    },
    {
      key: 'every30Minutes',
      expression: '*/30 * * * *',
      icon: 'el-icon-timer',
      category: '基础'
    },
    {
      key: 'hourly',
      expression: '0 * * * *',
      icon: 'el-icon-clock',
      category: '小时'
    },
    {
      key: 'every2Hours',
      expression: '0 */2 * * *',
      icon: 'el-icon-clock',
      category: '小时'
    },
    {
      key: 'daily',
      expression: '0 0 * * *',
      icon: 'el-icon-date',
      category: '日常'
    },
    {
      key: 'daily9am',
      expression: '0 9 * * *',
      icon: 'el-icon-sunrise',
      category: '日常'
    },
    {
      key: 'weekly',
      expression: '0 0 * * 0',
      icon: 'el-icon-week',
      category: '日常'
    },
    {
      key: 'monthly',
      expression: '0 0 1 * *',
      icon: 'el-icon-calendar',
      category: '日常'
    },
    {
      key: 'workday',
      expression: '0 9 * * 1-5',
      icon: 'el-icon-office-building',
      category: '工作日'
    },
    {
      key: 'workdayAm',
      expression: '0 9,17 * * 1-5',
      icon: 'el-icon-briefcase',
      category: '工作日'
    },
    {
      key: 'weekend',
      expression: '0 10 * * 6,0',
      icon: 'el-icon-sunny',
      category: '周末'
    }
  ]

  private customTemplates: CustomTemplate[] = []

  private customForm = {
    expression: '',
    minute: '*',
    hour: '0',
    day: '*',
    month: '*',
    weekdays: [] as number[]
  }

  private newCustomTemplate: CustomTemplate = {
    name: '',
    expression: '',
    description: '',
    enabled: true
  }

  private formRules = {
    expression: [
      { required: true, message: this.$t('tasks.cronEditor.rules.expressionRequired'), trigger: 'blur' },
      {
        validator: (rule, value, callback) => {
          if (!value) {
            callback(new Error(this.$t('tasks.cronEditor.rules.expressionEmpty')))
          } else {
            // 基础格式检查：5个字段，用空格分隔
            const parts = value.trim().split(/\s+/)
            if (parts.length !== 5) {
              callback(new Error(this.$t('tasks.cronEditor.rules.expressionFiveFields')))
              return
            }

            // 验证每个字段的格式
            const validPatterns = [
              /^\*$/,                    // * (任意值)
              /^\d+$/,                    // 数字 (如: 5)
              /^\d+\/\d+$/,              // 步长 (如: */5, 1-10)
              /^\d+-\d+$/,              // 范围 (如: 1-5)
              /^\d+(,\d+)+$/             // 列表 (如: 1,5,10)
            ]

            for (let i = 0; i < 5; i++) {
              const part = parts[i].trim()
              if (!part) {
                callback(new Error(this.$t('tasks.cronEditor.rules.fieldEmpty', { index: i + 1 })))
                return
              }

              let isValid = false
              for (const pattern of validPatterns) {
                if (pattern.test(part)) {
                  isValid = true
                  break
                }
              }

              if (!isValid) {
                callback(new Error(this.$t('tasks.cronEditor.rules.fieldInvalid', { index: i + 1, part })))
                return
              }
            }

            callback()
          }
        },
        trigger: 'blur'
      }
    ]
  }

  private customTemplateRules = {
    name: [
      { required: true, message: this.$t('tasks.cronEditor.rules.nameRequired'), trigger: 'blur' },
      { min: 2, max: 50, message: this.$t('tasks.cronEditor.rules.nameLength'), trigger: 'blur' }
    ],
    expression: [
      { required: true, message: this.$t('tasks.cronEditor.rules.expressionRequired'), trigger: 'blur' }
    ],
    description: [
      { max: 200, message: this.$t('tasks.cronEditor.rules.descLength'), trigger: 'blur' }
    ]
  }

  /** 内置模板展示名（按 key 映射；无 key（自定义/未知）原文回退 Q02） */
  private templateDisplayName(template: CronTemplate): string {
    return template.key ? this.$t(`tasks.cronEditor.templates.${template.key}.name`) as string : template.name
  }

  /** 内置模板展示描述 */
  private templateDescDisplay(template: CronTemplate): string {
    return template.key ? this.$t(`tasks.cronEditor.templates.${template.key}.desc`) as string : template.description
  }

  /** 模板身份（内置=key、自定义=name；选中/勾选判定唯一口径） */
  private templateIdentity(template: CronTemplate): string {
    return template.key ?? template.name
  }

  get filteredTemplates(): CronTemplate[] {
    if (!this.templateFilter) {
      return this.templates
    }
    return this.templates.filter(template => template.category === this.templateFilter)
  }

  @Watch('value')
  onValueChange(newValue: string) {
    if (newValue !== this.getCurrentExpression()) {
      this.setExpression(newValue)
    }
  }

  created() {
    if (this.value) {
      this.setExpression(this.value)
    } else {
      this.selectTemplate(this.templates.find(t => t.key === 'daily') || this.templates[0])
    }

    // 加载自定义模板
    this.loadCustomTemplates()
  }

  private selectTemplate(template: CronTemplate) {
    this.selectedTemplate = this.templateIdentity(template)
    this.activeTab = 'template'

    this.customForm.expression = template.expression
    this.updateCustomForm(template.expression)

    this.calculateNextExecutions()
    this.validateExpression()
    this.$emit('input', template.expression)
    this.$emit('change', template.expression)
  }

  private selectCustomTemplate(custom: CustomTemplate) {
    this.selectedTemplate = custom.name
    this.activeTab = 'template'

    this.customForm.expression = custom.expression
    this.updateCustomForm(custom.expression)

    this.calculateNextExecutions()
    this.validateExpression()
    this.$emit('input', custom.expression)
    this.$emit('change', custom.expression)
  }

  private updateCustomForm(expression: string) {
    const parts = expression.split(' ')
    if (parts.length === 5) {
      this.customForm.minute = parts[0]
      this.customForm.hour = parts[1]
      this.customForm.day = parts[2]
      this.customForm.month = parts[3]

      // 解析星期部分
      const weekdayPart = parts[4]
      if (weekdayPart === '*') {
        this.customForm.weekdays = []
      } else if (weekdayPart.includes('-')) {
        const [start, end] = weekdayPart.split('-').map(Number)
        this.customForm.weekdays = Array.from({ length: end - start + 1 }, (_, i) => start + i)
      } else if (weekdayPart.includes(',')) {
        this.customForm.weekdays = weekdayPart.split(',').map(Number)
      } else {
        this.customForm.weekdays = [Number(weekdayPart)]
      }
    }
  }

  private handleCustomExpressionChange(expression: string) {
    this.customForm.expression = expression
    this.validateExpression()

    // 防抖执行时间计算
    this.debounceCalculateExecutions()

    this.$emit('input', expression)
    this.$emit('change', expression)
  }

  private handleTabChange() {
    if (this.activeTab === 'custom' && !this.customForm.expression) {
      this.buildExpressionFromForm()
    }
  }

  private buildExpressionFromForm() {
    const { minute, hour, day, month, weekdays } = this.customForm

    let weekdayPart = '*'
    if (weekdays.length > 0) {
      if (this.isConsecutiveArray(weekdays)) {
        weekdayPart = `${Math.min(...weekdays)}-${Math.max(...weekdays)}`
      } else {
        weekdayPart = weekdays.sort().join(',')
      }
    }

    const expression = `${minute} ${hour} ${day} ${month} ${weekdayPart}`
    this.customForm.expression = expression

    this.validateExpression()
    this.debounceCalculateExecutions()
    this.$emit('input', expression)
    this.$emit('change', expression)
  }

  private isConsecutiveArray(arr: number[]): boolean {
    if (arr.length <= 1) return true
    const sorted = [...arr].sort((a, b) => a - b)
    return sorted.every((val, index) => index === 0 || val === sorted[index - 1] + 1)
  }

  private async validateCustomExpression() {
    this.validating = true
    try {
      const expression = this.customForm.expression
      if (!expression) {
        this.validationResult = { valid: false, message: this.$t('tasks.cronEditor.msg.expressionEmpty') }
        return
      }

      const result = await this.callValidationAPI(expression)
      this.validationResult = result
    } catch (error) {
      console.error('验证表达式失败:', error)
      this.validationResult = { valid: false, message: this.$t('tasks.cronEditor.msg.validateFailed') }
    } finally {
      this.validating = false
    }
  }

  private async calculateNextExecutions() {
    this.previewLoading = true
    try {
      const expression = this.getCurrentExpression()
      if (!expression || !this.isValidExpression(expression)) {
        this.nextExecutions = []
        return
      }

      const times = await this.callCronCalculationAPI(expression, this.previewCount)
      this.nextExecutions = times.map((timeStr: string) => new Date(timeStr))
    } catch (error) {
      console.error('计算执行时间失败:', error)
      this.nextExecutions = []
    } finally {
      this.previewLoading = false
    }
  }

  private debounceCalculateExecutions() {
    if (this.calculateExecutionsTimer) {
      clearTimeout(this.calculateExecutionsTimer)
    }
    this.calculateExecutionsTimer = setTimeout(() => {
      this.calculateNextExecutions()
    }, 1000)
  }

  private getCurrentExpression(): string {
    return this.activeTab === 'template' ? this.customForm.expression : this.customForm.expression
  }

  private setExpression(expression: string) {
    this.customForm.expression = expression

    // 检查是否匹配预定义模板
    const matchedTemplate = this.templates.find(t => t.expression === expression)
    if (matchedTemplate) {
      this.selectedTemplate = matchedTemplate.name
      this.activeTab = 'template'
    } else {
      const matchedCustom = this.customTemplates.find(t => t.expression === expression)
      if (matchedCustom) {
        this.selectedTemplate = matchedCustom.name
        this.activeTab = 'template'
      } else {
        this.selectedTemplate = ''
        this.activeTab = 'custom'
      }
    }

    this.updateCustomForm(expression)
    this.calculateNextExecutions()
    this.validateExpression()
  }

  private isValidExpression(expression: string): boolean {
    const parts = expression.split(' ')
    if (parts.length !== 5) return false

    // 简单验证，具体验证交给后端
    return parts.every(part => part && part.trim() !== '')
  }

  private validateExpression() {
    if (this.customForm.expression) {
      this.validateCustomExpression()
    }
  }

  private formatExecutionTime(time: Date): string {
    const now = new Date()
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)

    let timeStr = time.toLocaleString('zh-CN', {
      year: time.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })

    // 如果是明天，添加"明天"标识
    if (time >= tomorrow && time < tomorrow.getTime() + 24 * 60 * 60 * 1000) {
      timeStr = this.$t('tasks.cronEditor.time.tomorrow', { time: timeStr.split(' ')[1] })
    }

    return timeStr
  }

  private getTimeUntilExecution(time: Date): string {
    const now = new Date()
    const diff = time.getTime() - now.getTime()

    if (diff <= 0) return ''

    const minutes = Math.floor(diff / (1000 * 60))
    const hours = Math.floor(diff / (1000 * 60 * 60))
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days > 0) return this.$t('tasks.cronEditor.time.daysLater', { count: days })
    if (hours > 0) return this.$t('tasks.cronEditor.time.hoursLater', { count: hours })
    if (minutes > 0) return this.$t('tasks.cronEditor.time.minutesLater', { count: minutes })
    return this.$t('tasks.cronEditor.time.soon')
  }

  private getPreviewTagType(index: number): string {
    const types = ['primary', 'success', 'info', 'warning', 'danger']
    return types[index % types.length] || 'info'
  }

  private getTemplateTagType(category: string): string {
    const typeMap: Record<string, string> = {
      '基础': 'primary',
      '小时': 'success',
      '日常': 'info',
      '工作日': 'warning',
      '周末': 'danger'
    }
    return typeMap[category] || 'info'
  }

  private async refreshExecutionTimes() {
    await this.calculateNextExecutions()
  }

  private async callValidationAPI(expression: string): Promise<ValidationResult> {
    try {
      const response = await request.post('/cronTasks/validation/cron', {
        expression
      })
      return response.data.data
    } catch (error) {
      console.error('调用验证API失败:', error)
      return { valid: false, message: this.$t('tasks.cronEditor.msg.validateUnavailable') }
    }
  }

  private async callCronCalculationAPI(expression: string, count: number): Promise<string[]> {
    try {
      // 使用验证API获取执行时间信息
      const response = await request.post('/cronTasks/validation/cron', {
        expression
      })

      console.log('API完整响应:', response.data)

      // 处理两种可能的数据结构：
      // 1. 标准格式：{status, msg, code, data: {validation data}}
      // 2. 基础格式（ImportError情况）：{valid, message, description}
      let validationData = response.data.data || response.data
      console.log('验证数据:', validationData)

      // 安全访问执行时间数据，处理可能的null/undefined情况
      if (validationData && validationData.executionTimes && Array.isArray(validationData.executionTimes.executionTimes)) {
        console.log('找到执行时间数组:', validationData.executionTimes.executionTimes)
        return validationData.executionTimes.executionTimes
      }

      // 如果API没有返回执行时间，使用本地计算
      console.warn('API未返回执行时间数据，使用本地计算，数据结构:', validationData)
      return this.localCronCalculation(expression, count)
    } catch (error) {
      console.error('调用计算API失败:', error)
      // 提供本地计算作为后备
      return this.localCronCalculation(expression, count)
    }
  }

  private localCronCalculation(expression: string, count: number): string[] {
    const now = new Date()
    const times = []

    // 简单的本地计算（仅用于示例）
    for (let i = 0; i < count; i++) {
      const futureTime = new Date(now.getTime() + (i + 1) * 60 * 60 * 1000) // 每小时执行一次
      times.push(futureTime.toISOString())
    }

    return times
  }

  // 自定义模板管理
  private loadCustomTemplates() {
    const saved = localStorage.getItem('cron-templates')
    if (saved) {
      try {
        this.customTemplates = JSON.parse(saved)
      } catch (error) {
        console.error('加载自定义模板失败:', error)
      }
    }
  }

  private saveCustomTemplates() {
    localStorage.setItem('cron-templates', JSON.stringify(this.customTemplates))
  }

  private async addCustomTemplate() {
    try {
      await (this.$refs.customTemplateRef as any).validate()

      this.savingCustom = true

      // 验证表达式
      const result = await this.callValidationAPI(this.newCustomTemplate.expression)
      if (!result.valid) {
        this.$message.error(this.$t('tasks.cronEditor.msg.formatInvalid'))
        return
      }

      const custom = { ...this.newCustomTemplate }
      this.customTemplates.push(custom)
      this.saveCustomTemplates()

      this.showAddCustomTemplate = false
      this.newCustomTemplate = { name: '', expression: '', description: '', enabled: true }

      this.$message.success(this.$t('tasks.cronEditor.msg.customAdded'))
    } catch (error) {
      console.error('添加自定义模板失败:', error)
    } finally {
      this.savingCustom = false
    }
  }

  private removeCustomTemplate(index: number) {
    this.customTemplates.splice(index, 1)
    this.saveCustomTemplates()
  }
}
</script>

<style scoped>
.cron-editor {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  overflow: hidden;
}

/* 模板选择样式 */
.template-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 16px 8px;
  background-color: #f8f9fa;
  border-bottom: 1px solid #e4e7ed;
}

.template-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 16px;
  max-height: 400px;
  overflow-y: auto;
}

.template-item {
  display: flex;
  align-items: flex-start;
  padding: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: white;
  position: relative;
}

.template-item:hover {
  border-color: #409eff;
  background-color: #f5f9ff;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
}

.template-item.active {
  border-color: #409eff;
  background-color: #ecf5ff;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
}

.template-icon {
  margin-right: 12px;
  font-size: 20px;
  color: #409eff;
  margin-top: 2px;
}

.template-info {
  flex: 1;
  min-width: 0;
}

.template-name {
  font-weight: 500;
  color: #303133;
  margin-bottom: 6px;
  font-size: 14px;
}

.template-desc {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
  line-height: 1.4;
}

.template-cron {
  margin-top: 6px;
}

.template-check {
  position: absolute;
  top: 12px;
  right: 12px;
  color: #67c23a;
  font-size: 16px;
}

/* 自定义模板样式 */
.custom-template-section {
  border-top: 1px solid #e4e7ed;
  padding: 16px;
  background-color: #fafbfc;
}

.section-title {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 12px;
}

.section-title i {
  margin-right: 6px;
  color: #409eff;
}

.custom-template-grid {
  margin-bottom: 12px;
}

.custom-template-item {
  display: flex;
  align-items: center;
  padding: 8px;
  margin-bottom: 8px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.custom-template-item:hover {
  border-color: #409eff;
}

.custom-expression {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
  font-family: 'Monaco', 'Consolas', monospace;
}

/* 可视化配置样式 */
.visual-config {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 16px;
  margin-top: 16px;
  background-color: #fafbfc;
}

.config-title {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 16px;
}

.config-title i {
  margin-right: 6px;
  color: #409eff;
}

/* 字段样式增强 */
.minute-field,
.hour-field,
.day-field,
.month-field,
.weekday-field {
  margin-bottom: 12px;
}

.el-input-group__prepend {
  background-color: #f5f7fa;
  border-color: #dcdfe6;
  color: #606266;
  font-weight: 500;
}

.weekday-field .el-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.weekday-field .el-checkbox {
  margin-right: 8px;
  margin-bottom: 8px;
}

/* 执行时间预览样式 */
.execution-preview {
  border-top: 1px solid #e4e7ed;
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
}

.preview-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.preview-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-left: 6px;
}

.preview-header i {
  color: #409eff;
}

.preview-loading {
  padding: 12px;
}

.preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.preview-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 4px rgba(64, 158, 255, 0.1);
}

.preview-time {
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 13px;
  color: #303133;
  font-weight: 500;
}

.next-indicator {
  margin-left: auto;
}

.time-until {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}

.preview-empty {
  text-align: center;
  padding: 20px;
}

/* 验证状态样式 */
.validation-status {
  border-top: 1px solid #e4e7ed;
  padding: 12px 16px;
}

.suggestions {
  margin-top: 8px;
}

.suggestions ul {
  margin: 8px 0 0 0;
  padding-left: 16px;
}

.suggestions li {
  margin-bottom: 4px;
  color: #606266;
  font-size: 12px;
}

/* 表达式帮助提示 */
.expression-help {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .template-grid {
    grid-template-columns: 1fr;
    padding: 12px;
  }

  .template-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .template-item {
    padding: 12px;
  }

  .custom-template-grid {
    grid-template-columns: 1fr;
  }

  .visual-config {
    padding: 12px;
  }
}

/* 动画效果 */
.template-item {
  animation: fadeInUp 0.3s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 分类标签颜色 */
.template-category-基础 {
  border-left: 3px solid #409eff;
}

.template-category-小时 {
  border-left: 3px solid #67c23a;
}

.template-category-日常 {
  border-left: 3px solid #909399;
}

.template-category-工作日 {
  border-left: 3px solid #e6a23c;
}

.template-category-周末 {
  border-left: 3px solid #f56c6c;
}

/* 滚动条样式 */
.template-grid::-webkit-scrollbar {
  width: 6px;
}

.template-grid::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.template-grid::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.template-grid::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>