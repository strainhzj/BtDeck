<template>
  <div class="cron-editor">
    <el-tabs v-model="activeTab" @tab-click="handleTabChange">
      <!-- 模板选择 -->
      <el-tab-pane label="模板选择" name="template">
        <div class="template-header">
          <span class="template-title">选择预设模板</span>
          <el-select v-model="templateFilter" placeholder="筛选分类" size="small" style="width: 120px;">
            <el-option label="全部" value="" />
            <el-option label="基础" value="基础" />
            <el-option label="小时" value="小时" />
            <el-option label="日常" value="日常" />
            <el-option label="工作日" value="工作日" />
            <el-option label="周末" value="周末" />
          </el-select>
        </div>

        <div class="template-grid">
          <div
            v-for="template in filteredTemplates"
            :key="template.name"
            class="template-item"
            :class="{
              active: selectedTemplate === template.name,
              ['template-category-' + template.category]: true
            }"
            @click="selectTemplate(template)"
          >
            <div class="template-icon">
              <i :class="template.icon"></i>
            </div>
            <div class="template-info">
              <div class="template-name">{{ template.name }}</div>
              <div class="template-desc">{{ template.description }}</div>
              <div class="template-cron">
                <el-tag size="mini" :type="getTemplateTagType(template.category)">
                  {{ template.expression }}
                </el-tag>
              </div>
            </div>
            <div class="template-check" v-if="selectedTemplate === template.name">
              <i class="el-icon-check"></i>
            </div>
          </div>
        </div>

        <!-- 自定义模板 -->
        <div class="custom-template-section">
          <div class="section-title">
            <i class="el-icon-setting"></i>
            自定义模板
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
            <i class="el-icon-plus"></i> 添加自定义模板
          </el-button>
        </div>
      </el-tab-pane>

      <!-- 自定义表达式 -->
      <el-tab-pane label="自定义表达式" name="custom">
        <el-form :model="customForm" :rules="formRules" ref="customFormRef" label-width="80px">
          <el-form-item label="Cron表达式" prop="expression">
            <el-input
              v-model="customForm.expression"
              placeholder="* * * * *"
              @input="handleCustomExpressionChange"
            >
              <template slot="append">
                <el-button @click="validateCustomExpression" icon="el-icon-check" :loading="validating">
                  验证
                </el-button>
              </template>
            </el-input>
            <div class="expression-help">
              <small>格式：分 时 日 月 周 (0-59 0-23 1-31 1-12 0-6)</small>
            </div>
          </el-form-item>

          <!-- 可视化配置 -->
          <div class="visual-config">
            <div class="config-title">
              <i class="el-icon-s-grid"></i>
              可视化配置
            </div>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="分钟" class="minute-field">
                  <el-input
                    v-model="customForm.minute"
                    placeholder="0-59 或 */5"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip content="分 (0-59)" placement="top">
                        <span>分</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="小时" class="hour-field">
                  <el-input
                    v-model="customForm.hour"
                    placeholder="0-23 或 */2"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip content="时 (0-23)" placement="top">
                        <span>时</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="日期" class="day-field">
                  <el-input
                    v-model="customForm.day"
                    placeholder="1-31 或 1,15,L"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip content="日 (1-31, L=最后一天)" placement="top">
                        <span>日</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="月份" class="month-field">
                  <el-input
                    v-model="customForm.month"
                    placeholder="1-12 或 1,6,12"
                    @input="buildExpressionFromForm"
                  >
                    <template slot="prepend">
                      <el-tooltip content="月 (1-12)" placement="top">
                        <span>月</span>
                      </el-tooltip>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item label="星期" class="weekday-field">
              <el-checkbox-group v-model="customForm.weekdays" @change="buildExpressionFromForm">
                <el-checkbox :label="0">
                  <el-tooltip content="星期日" placement="top">
                    <span>日</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="1">
                  <el-tooltip content="星期一" placement="top">
                    <span>一</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="2">
                  <el-tooltip content="星期二" placement="top">
                    <span>二</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="3">
                  <el-tooltip content="星期三" placement="top">
                    <span>三</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="4">
                  <el-tooltip content="星期四" placement="top">
                    <span>四</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="5">
                  <el-tooltip content="星期五" placement="top">
                    <span>五</span>
                  </el-tooltip>
                </el-checkbox>
                <el-checkbox :label="6">
                  <el-tooltip content="星期六" placement="top">
                    <span>六</span>
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
        <span class="preview-title">下次执行时间预览</span>
        <el-button
          type="text"
          size="mini"
          @click="refreshExecutionTimes"
          :loading="previewLoading"
          style="float: right;"
        >
          刷新
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
            下次执行
          </el-tag>
          <span v-if="getTimeUntilExecution(time)" class="time-until">
            {{ getTimeUntilExecution(time) }}
          </span>
        </div>
      </div>

      <div v-if="nextExecutions.length === 0 && !previewLoading" class="preview-empty">
        <el-empty description="暂无执行时间" :image-size="80" />
      </div>
    </div>

    <!-- 表达式验证状态 -->
    <div class="validation-status" v-if="validationResult">
      <el-alert
        :title="validationResult.valid ? '表达式有效' : '表达式有误'"
        :type="validationResult.valid ? 'success' : 'error'"
        :description="validationResult.message"
        show-icon
        :closable="false"
      >
        <div v-if="validationResult.suggestions && validationResult.suggestions.length > 0" slot="description">
          <div class="suggestions">
            <strong>建议：</strong>
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
    <el-dialog title="添加自定义模板" :visible.sync="showAddCustomTemplate" width="500px">
      <el-form :model="newCustomTemplate" :rules="customTemplateRules" ref="customTemplateRef" label-width="100px">
        <el-form-item label="模板名称" prop="name">
          <el-input v-model="newCustomTemplate.name" placeholder="例如：每小时备份" />
        </el-form-item>
        <el-form-item label="Cron表达式" prop="expression">
          <el-input v-model="newCustomTemplate.expression" placeholder="0 * * * *" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="newCustomTemplate.description" type="textarea" placeholder="模板用途说明" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="showAddCustomTemplate = false">取消</el-button>
        <el-button type="primary" @click="addCustomTemplate" :loading="savingCustom">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import request from '@/utils/request'

interface CronTemplate {
  name: string
  description: string
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
      name: '每分钟',
      description: '每分钟执行一次',
      expression: '* * * * *',
      icon: 'el-icon-time',
      category: '基础'
    },
    {
      name: '每5分钟',
      description: '每5分钟执行一次',
      expression: '*/5 * * * *',
      icon: 'el-icon-timer',
      category: '基础'
    },
    {
      name: '每15分钟',
      description: '每15分钟执行一次',
      expression: '*/15 * * * *',
      icon: 'el-icon-timer',
      category: '基础'
    },
    {
      name: '每30分钟',
      description: '每30分钟执行一次',
      expression: '*/30 * * * *',
      icon: 'el-icon-timer',
      category: '基础'
    },
    {
      name: '每小时',
      description: '每小时的第0分钟执行',
      expression: '0 * * * *',
      icon: 'el-icon-clock',
      category: '小时'
    },
    {
      name: '每2小时',
      description: '每2小时执行一次',
      expression: '0 */2 * * *',
      icon: 'el-icon-clock',
      category: '小时'
    },
    {
      name: '每天',
      description: '每天0点执行',
      expression: '0 0 * * *',
      icon: 'el-icon-date',
      category: '日常'
    },
    {
      name: '每天9点',
      description: '每天上午9点执行',
      expression: '0 9 * * *',
      icon: 'el-icon-sunrise',
      category: '日常'
    },
    {
      name: '每周',
      description: '每周日0点执行',
      expression: '0 0 * * 0',
      icon: 'el-icon-week',
      category: '日常'
    },
    {
      name: '每月',
      description: '每月1日0点执行',
      expression: '0 0 1 * *',
      icon: 'el-icon-calendar',
      category: '日常'
    },
    {
      name: '工作日',
      description: '周一到周五9点执行',
      expression: '0 9 * * 1-5',
      icon: 'el-icon-office-building',
      category: '工作日'
    },
    {
      name: '工作日上午',
      description: '工作日9点和17点执行',
      expression: '0 9,17 * * 1-5',
      icon: 'el-icon-briefcase',
      category: '工作日'
    },
    {
      name: '周末',
      description: '周六和周日10点执行',
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
      { required: true, message: '请输入Cron表达式', trigger: 'blur' },
      {
        validator: (rule, value, callback) => {
          if (!value) {
            callback(new Error('请输入Cron表达式'))
          } else {
            // 基础格式检查：5个字段，用空格分隔
            const parts = value.trim().split(/\s+/)
            if (parts.length !== 5) {
              callback(new Error('Cron表达式必须包含5个字段：分 时 日 月 周'))
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
                callback(new Error(`第${i + 1}个字段不能为空`))
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
                callback(new Error(`第${i + 1}个字段格式不正确: ${part}`))
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
      { required: true, message: '请输入模板名称', trigger: 'blur' },
      { min: 2, max: 50, message: '模板名称长度在2-50个字符', trigger: 'blur' }
    ],
    expression: [
      { required: true, message: '请输入Cron表达式', trigger: 'blur' }
    ],
    description: [
      { max: 200, message: '描述不能超过200个字符', trigger: 'blur' }
    ]
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
      this.selectTemplate(this.templates.find(t => t.name === '每天') || this.templates[0])
    }

    // 加载自定义模板
    this.loadCustomTemplates()
  }

  private selectTemplate(template: CronTemplate) {
    this.selectedTemplate = template.name
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
        this.validationResult = { valid: false, message: 'Cron表达式不能为空' }
        return
      }

      const result = await this.callValidationAPI(expression)
      this.validationResult = result
    } catch (error) {
      console.error('验证表达式失败:', error)
      this.validationResult = { valid: false, message: '验证失败，请检查表达式格式' }
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
      timeStr = `明天 ${timeStr.split(' ')[1]}`
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

    if (days > 0) return `${days}天后`
    if (hours > 0) return `${hours}小时后`
    if (minutes > 0) return `${minutes}分钟后`
    return '即将执行'
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
      return { valid: false, message: '验证服务不可用' }
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
        this.$message.error('Cron表达式格式不正确')
        return
      }

      const custom = { ...this.newCustomTemplate }
      this.customTemplates.push(custom)
      this.saveCustomTemplates()

      this.showAddCustomTemplate = false
      this.newCustomTemplate = { name: '', expression: '', description: '', enabled: true }

      this.$message.success('自定义模板添加成功')
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