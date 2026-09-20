<template>
  <div class="python-class-selector">
    <el-tabs v-model="activeTab" @tab-click="handleTabChange">
      <!-- 预定义类选择 -->
      <el-tab-pane :label="$t('tasks.pythonSelector.tabs.preset')" name="preset">
        <div class="preset-header">
          <span class="preset-title">{{ $t('tasks.pythonSelector.presetTitle') }}</span>
          <el-input
            v-model="searchKeyword"
            :placeholder="$t('tasks.pythonSelector.searchPlaceholder')"
            prefix-icon="el-icon-search"
            size="small"
            style="width: 200px;"
            clearable
          />
        </div>

        <div class="class-tree-container" v-loading="loadingClasses">
          <el-tree
            ref="classTree"
            :data="filteredClassTree"
            :props="treeProps"
            node-key="path"
            :expand-on-click-node="false"
            :default-expanded-keys="expandedKeys"
            :filter-node-method="filterNode"
            @node-click="handleNodeClick"
            @node-expand="handleNodeExpand"
            @node-collapse="handleNodeCollapse"
            class="class-tree"
          >
            <span class="custom-tree-node" slot-scope="{node, data}">
              <span class="node-content">
                <span class="node-icon">
                  <i :class="data.icon" v-if="data.icon"></i>
                </span>
                <span class="node-label" :title="node.label">
                  {{ node.label }}
                </span>
                <span v-if="data.type === 'class'" class="node-badge">
                  <el-tag size="mini" :type="getClassTypeColor(data.category)">
                    {{ data.category || $t('tasks.pythonSelector.categoryFallback') }}
                  </el-tag>
                </span>
              </span>
              <span v-if="data.description" class="node-description" :title="data.description">
                {{ data.description }}
              </span>
              <span v-if="data.type === 'class'" class="node-actions">
                <el-tooltip :content="$t('tasks.pythonSelector.viewDetailTip')" placement="top">
                  <i class="el-icon-info" @click.stop="showClassDetail(data)"></i>
                </el-tooltip>
                <el-tooltip :content="$t('tasks.pythonSelector.selectTip')" placement="top">
                  <i class="el-icon-check" @click.stop="selectClass(data)"></i>
                </el-tooltip>
              </span>
            </span>
          </el-tree>
        </div>

        <!-- 选中类信息 -->
        <div v-if="selectedClass" class="selected-class-info">
          <div class="info-header">
            <i class="el-icon-collection"></i>
            <span class="info-title">{{ $t('tasks.pythonSelector.selectedTitle') }}</span>
          </div>
          <div class="info-content">
            <div class="info-item">
              <label>{{ $t('tasks.pythonSelector.classPathLabel') }}</label>
              <el-tag type="success">{{ selectedClass.path }}</el-tag>
            </div>
            <div class="info-item">
              <label>{{ $t('tasks.pythonSelector.descLabel') }}</label>
              <span>{{ selectedClass.description || $t('tasks.pythonSelector.noDesc') }}</span>
            </div>
            <div v-if="selectedClass.parameters && Object.keys(selectedClass.parameters).length > 0" class="info-item">
              <label>{{ $t('tasks.pythonSelector.paramsLabel') }}</label>
              <div class="parameters-list">
                <div
                  v-for="(param, key) in selectedClass.parameters"
                  :key="key"
                  class="parameter-item"
                >
                  <el-tag size="mini" :type="param.required ? 'warning' : 'info'">
                    {{ key }}
                  </el-tag>
                  <span class="param-desc">
                    {{ param.description }} ({{ param.type }})
                    <strong v-if="param.required" class="required-indicator">*</strong>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 手动输入 -->
      <el-tab-pane :label="$t('tasks.pythonSelector.tabs.manual')" name="manual">
        <el-form :model="manualForm" :rules="formRules" ref="manualFormRef" label-width="100px">
          <el-form-item :label="$t('tasks.pythonSelector.manual.classPathLabel')" prop="classPath">
            <el-input
              v-model="manualForm.classPath"
              :placeholder="$t('tasks.pythonSelector.manual.placeholder')"
              @input="handleManualInput"
              clearable
            >
              <template slot="prepend">
                <el-tooltip :content="$t('tasks.pythonSelector.manual.tooltip')" placement="top">
                  <i class="el-icon-s-unfold"></i>
                </el-tooltip>
              </template>
            </el-input>
            <div class="input-help">
              <small>{{ $t('tasks.pythonSelector.manual.formatHint') }}</small>
            </div>
          </el-form-item>

          <!-- 快速输入模板 -->
          <el-collapse v-model="quickInputExpanded">
            <el-collapse-item :title="$t('tasks.pythonSelector.manual.templatesTitle')" name="templates">
              <div class="quick-templates">
                <el-button
                  v-for="template in quickTemplates"
                  :key="template.path"
                  size="mini"
                  @click="useQuickTemplate(template)"
                  class="template-btn"
                >
                  {{ template.name }}
                </el-button>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 历史记录 -->
          <el-form-item :label="$t('tasks.pythonSelector.manual.historyLabel')" v-if="historyList.length > 0">
            <div class="history-list">
              <div
                v-for="(item, index) in historyList"
                :key="index"
                class="history-item"
                @click="useHistoryItem(item)"
              >
                <el-tag size="mini" :type="item.valid ? 'success' : 'danger'">
                  {{ item.path }}
                </el-tag>
                <span class="history-time">{{ formatTime(item.time) }}</span>
                <el-button
                  size="mini"
                  type="text"
                  icon="el-icon-delete"
                  @click.stop="removeHistoryItem(index)"
                  class="history-delete"
                />
              </div>
            </div>
          </el-form-item>

          <!-- 验证状态 -->
          <el-form-item :label="$t('tasks.pythonSelector.manual.validationLabel')" v-if="validationResult || manualForm.classPath">
            <div v-if="validating" class="validation-loading">
              <el-skeleton :rows="2" animated />
            </div>
            <el-alert
              v-else-if="validationResult"
              :title="validationResult.valid ? $t('tasks.pythonSelector.manual.validTitle') : $t('tasks.pythonSelector.manual.invalidTitle')"
              :type="validationResult.valid ? 'success' : 'error'"
              :description="validationResult.message"
              show-icon
              :closable="false"
            >
              <div v-if="validationResult.details" slot="description">
                <div class="validation-details">
                  <p v-if="validationResult.details.exists">
                    <i class="el-icon-check-circle" style="color: #67c23a;"></i>
                    {{ $t('tasks.pythonSelector.manual.importable') }}
                  </p>
                  <p v-if="validationResult.details.module_path">
                    <i class="el-icon-folder" style="color: #409eff;"></i>
                    {{ $t('tasks.pythonSelector.manual.modulePath') }}{{ validationResult.details.module_path }}
                  </p>
                  <p v-if="validationResult.details.class_info">
                    <i class="el-icon-document" style="color: #909399;"></i>
                    {{ $t('tasks.pythonSelector.manual.classInfo') }}{{ validationResult.details.class_info }}
                  </p>
                </div>
              </div>
            </el-alert>
            <div v-else-if="manualForm.classPath" class="validation-pending">
              <el-alert
                :title="$t('tasks.pythonSelector.manual.waitingTitle')"
                type="info"
                :description="$t('tasks.pythonSelector.manual.waitingDesc')"
                show-icon
                :closable="false"
              />
            </div>
          </el-form-item>

          <!-- 验证按钮 -->
          <el-form-item>
            <el-button
              type="primary"
              :loading="validating"
              @click="validateManualClass"
              :disabled="!manualForm.classPath"
            >
              <i class="el-icon-check"></i>
              {{ $t('tasks.pythonSelector.manual.validateBtn') }}
            </el-button>
            <el-button @click="clearManualForm">
              <i class="el-icon-refresh-left"></i>
              {{ $t('tasks.pythonSelector.manual.clearBtn') }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <!-- 类详情对话框 -->
    <el-dialog
      :title="$t('tasks.pythonSelector.detail.title')"
      :visible.sync="showDetailDialog"
      width="600px"
      class="class-detail-dialog"
    >
      <div v-if="detailClass" class="class-detail">
        <div class="detail-header">
          <h3>{{ detailClass.name }}</h3>
          <el-tag :type="getClassTypeColor(detailClass.category)">
            {{ detailClass.category }}
          </el-tag>
        </div>

        <div class="detail-content">
          <div class="detail-section">
            <h4>{{ $t('tasks.pythonSelector.detail.basic') }}</h4>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item :label="$t('tasks.pythonSelector.detail.path')">{{ detailClass.path }}</el-descriptions-item>
              <el-descriptions-item :label="$t('tasks.pythonSelector.detail.module')">{{ detailClass.module }}</el-descriptions-item>
              <el-descriptions-item :label="$t('tasks.pythonSelector.detail.category')">{{ detailClass.category }}</el-descriptions-item>
              <el-descriptions-item :label="$t('tasks.pythonSelector.detail.status')">
                <el-tag :type="detailClass.available ? 'success' : 'danger'">
                  {{ detailClass.available ? $t('tasks.pythonSelector.detail.available') : $t('tasks.pythonSelector.detail.unavailable') }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <div class="detail-section">
            <h4>{{ $t('tasks.pythonSelector.detail.descTitle') }}</h4>
            <p>{{ detailClass.description || $t('tasks.pythonSelector.detail.noDesc') }}</p>
          </div>

          <div v-if="detailClass.parameters" class="detail-section">
            <h4>{{ $t('tasks.pythonSelector.detail.paramsTitle') }}</h4>
            <el-table :data="parameterTableData" size="small" border>
              <el-table-column prop="name" :label="$t('tasks.pythonSelector.detail.colName')" width="150" />
              <el-table-column prop="type" :label="$t('tasks.pythonSelector.detail.colType')" width="100" />
              <el-table-column prop="required" :label="$t('tasks.pythonSelector.detail.colRequired')" width="80">
                <template slot-scope="scope">
                  <el-tag size="mini" :type="scope.row.required ? 'warning' : 'info'">
                    {{ scope.row.required ? $t('tasks.pythonSelector.detail.requiredYes') : $t('tasks.pythonSelector.detail.requiredNo') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="description" :label="$t('tasks.pythonSelector.detail.colDesc')" />
              <el-table-column prop="default" :label="$t('tasks.pythonSelector.detail.colDefault')" width="100" />
            </el-table>
          </div>

          <div v-if="detailClass.methods" class="detail-section">
            <h4>{{ $t('tasks.pythonSelector.detail.methodsTitle') }}</h4>
            <div class="methods-list">
              <div
                v-for="method in detailClass.methods"
                :key="method.name"
                class="method-item"
              >
                <el-tag size="small" type="info">{{ method.name }}</el-tag>
                <span class="method-desc">{{ method.description }}</span>
              </div>
            </div>
          </div>
        </div>

        <div slot="footer" class="dialog-footer">
          <el-button @click="showDetailDialog = false">{{ $t('tasks.pythonSelector.detail.close') }}</el-button>
          <el-button type="primary" @click="selectClass(detailClass)">
            {{ $t('tasks.pythonSelector.detail.select') }}
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { getTaskTypeConfig, validatePythonClass } from '@/api/tasks'
import type { PythonClassInfo } from '@/api/tasks'

interface ClassNode {
  label: string
  path: string
  type: 'module' | 'class'
  icon: string
  description?: string
  category?: string
  module?: string
  children?: ClassNode[]
  parameters?: Record<string, any>
  methods?: Array<{ name: string, description: string }>
  available?: boolean
}

interface ValidationResult {
  valid: boolean
  message: string
  exists?: boolean
  details?: {
    exists: boolean
    module_path: string
    class_info: string
  }
}

interface HistoryItem {
  path: string
  time: Date
  valid: boolean
}

interface QuickTemplate {
  name: string
  path: string
  description: string
}

@Component({ name: 'PythonClassSelector' })
export default class PythonClassSelector extends Vue {
  @Prop({ required: true }) value!: string

  private activeTab = 'preset'
  private searchKeyword = ''
  private selectedClass: ClassNode | null = null
  private detailClass: ClassNode | null = null
  private showDetailDialog = false
  private loadingClasses = false
  private validating = false
  private validationResult: ValidationResult | null = null
  private expandedKeys: string[] = []

  private manualForm = {
    classPath: ''
  }

  private historyList: HistoryItem[] = []
  private quickInputExpanded = ['templates']

  // 预定义Python类树数据
  /**
   * 预定义类树（P6-4a 起由后端 type-config pythonClasses 驱动——getTaskTypeConfig
   * 此前已定义但零调用，本批补全接线；后端中文描述按 Q02 原始数据透传，
   * 原硬编码假树（BackupTask 等后端不存在的类，选择后必然后端校验失败）删除。
   */
  private classTree: ClassNode[] = []

  private treeProps = {
    children: 'children',
    label: 'label'
  }

  private formRules = {
    classPath: [
      { required: true, message: this.$t('tasks.pythonSelector.rules.classPathRequired'), trigger: 'blur' },
      {
        pattern: /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)*$/,
        message: this.$t('tasks.pythonSelector.rules.classPathFormat'),
        trigger: 'blur'
      }
    ]
  }

  /** 常用路径模板（由后端真实类派生，最多 6 个；原硬编码假路径删除） */
  private quickTemplates: QuickTemplate[] = []

  get filteredClassTree(): ClassNode[] {
    if (!this.searchKeyword) {
      return this.classTree
    }

    return this.filterTree(this.classTree, this.searchKeyword.toLowerCase())
  }

  get parameterTableData() {
      if (!this.detailClass?.parameters) {
        return []
      }

      return Object.entries(this.detailClass.parameters).map(([key, param]: [string, any]) => ({
        name: key,
        type: param.type,
        required: param.required || false,
        description: param.description || '',
        default: param.default || (param.required ? this.$t('tasks.pythonSelector.detail.defaultRequired') : this.$t('tasks.pythonSelector.detail.defaultOptional'))
      }))
    }

  @Watch('value')
  onValueChange(newValue: string) {
    console.log('PythonClassSelector value changed:', newValue, 'current selection:', this.getCurrentSelection())
    if (newValue !== this.getCurrentSelection()) {
      this.setSelection(newValue)
    }
  }

  @Watch('searchKeyword')
  onSearchKeywordChange(keyword: string) {
    if (this.$refs.classTree) {
      (this.$refs.classTree as any).filter(keyword)
    }
  }

  created() {
    // 初始化时设置值
    if (this.value) {
      this.setSelection(this.value)
    }

    // 加载历史记录
    this.loadHistory()

    // 预定义类树由后端 type-config 驱动（加载完成后展开第一层模块）
    this.loadClasses()
  }

  /** 从后端 type-config pythonClasses 构建类树（按模块分组；失败保持空树） */
  private async loadClasses() {
    this.loadingClasses = true
    try {
      const response = await getTaskTypeConfig()
      if (response.code === '200' && response.data?.pythonClasses) {
        this.classTree = this.buildTreeFromClasses(response.data.pythonClasses)
        this.expandedKeys = this.classTree.map(node => node.path)
        this.quickTemplates = this.classTree
          .flatMap(node => node.children || [])
          .filter((node): node is ClassNode => node.type === 'class')
          .slice(0, 6)
          .map(cls => ({ name: cls.label, path: cls.path, description: cls.description || '' }))
      }
    } catch (error) {
      console.error('加载Python类列表失败:', error)
    } finally {
      this.loadingClasses = false
    }
  }

  /** pythonClasses 扁平列表 → 模块分组的 ClassNode 树 */
  private buildTreeFromClasses(classes: PythonClassInfo[]): ClassNode[] {
    const modules = new Map<string, ClassNode[]>()
    classes.forEach(cls => {
      const modulePath = cls.module || 'unknown'
      const children = modules.get(modulePath) ?? []
      children.push({
        label: cls.className,
        path: `${modulePath}.${cls.className}`,
        type: 'class',
        icon: 'el-icon-document',
        description: cls.description || undefined,
        module: modulePath,
        // 后端参数值为简单类型字符串或对象两种形态，统一归一为表格所需结构
        parameters: this.normalizeParameters(cls.parameters),
        methods: (cls.methods || []).map(name => ({ name, description: '' })),
        available: true
      })
      modules.set(modulePath, children)
    })
    return Array.from(modules.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([modulePath, children]) => ({
        label: modulePath,
        path: modulePath,
        type: 'module' as const,
        icon: 'el-icon-folder',
        module: modulePath,
        children: children.sort((a, b) => a.label.localeCompare(b.label))
      }))
  }

  /** 参数字典归一化（后端形如 {timeout: "int"} 或对象形态） */
  private normalizeParameters(parameters?: Record<string, any>): Record<string, any> | undefined {
    if (!parameters || Object.keys(parameters).length === 0) {
      return undefined
    }
    const normalized: Record<string, any> = {}
    Object.entries(parameters).forEach(([key, value]) => {
      normalized[key] = typeof value === 'string' ? { type: value } : value
    })
    return normalized
  }

  mounted() {
    // 确保DOM渲染完成后再次检查值的设置
    this.$nextTick(() => {
      if (this.value && !this.getCurrentSelection()) {
        this.setSelection(this.value)
      }
    })
  }

  private handleTabChange() {
    // 切换标签页时的处理逻辑
  }

  private handleNodeClick(data: ClassNode) {
    if (data.type === 'class') {
      this.selectClass(data)
    }
  }

  private handleNodeExpand(_data: ClassNode) {
    // 节点展开时的处理
  }

  private handleNodeCollapse(_data: ClassNode) {
    // 节点折叠时的处理
  }

  private filterNode(value: string, data: ClassNode): boolean {
    if (!value) return true
    return data.label.toLowerCase().includes(value.toLowerCase()) ||
           (data.description && data.description.toLowerCase().includes(value.toLowerCase()))
  }

  private filterTree(tree: ClassNode[], keyword: string): ClassNode[] {
    return tree.filter(node => {
      // 检查当前节点是否匹配
      const matchesNode = node.label.toLowerCase().includes(keyword) ||
                          (node.description && node.description.toLowerCase().includes(keyword))

      // 检查子节点是否匹配
      const hasMatchingChild = node.children && node.children.length > 0 &&
                             this.filterTree(node.children, keyword).length > 0

      return matchesNode || hasMatchingChild
    }).map(node => {
      if (node.children) {
        return {
          ...node,
          children: this.filterTree(node.children, keyword)
        }
      }
      return node
    })
  }

  private selectClass(cls: ClassNode) {
    this.selectedClass = cls
    this.$emit('input', cls.path)
    this.$emit('change', cls.path)
    this.$emit('select-class', cls)

    // 添加到历史记录
    this.addToHistory(cls.path, true)
  }

  private showClassDetail(cls: ClassNode) {
    this.detailClass = cls
    this.showDetailDialog = true
  }

  private getClassTypeColor(category?: string): string {
    const colorMap: Record<string, string> = {
      '备份': 'warning',
      '清理': 'info',
      '同步': 'success',
      '监控': 'danger',
      '自定义': 'primary'
    }
    return colorMap[category || ''] || 'info'
  }

  private handleManualInput(path: string) {
    this.manualForm.classPath = path
    this.validationResult = null

    // 防抖验证
    if (this.validationTimer) {
      clearTimeout(this.validationTimer)
    }
    this.validationTimer = setTimeout(() => {
      if (path) {
        this.validateManualClass()
      }
    }, 1000)

    this.$emit('input', path)
    this.$emit('change', path)
  }

  private async validateManualClass() {
    if (!this.manualForm.classPath) {
      return
    }

    this.validating = true
    try {
      const result = await this.callClassCheckAPI(this.manualForm.classPath)
      this.validationResult = result

      // 添加到历史记录
      this.addToHistory(this.manualForm.classPath, result.valid)

    } catch (error) {
      console.error('验证类路径失败:', error)
      this.validationResult = {
        valid: false,
        message: this.$t('tasks.pythonSelector.msg.validateFailed')
      }
    } finally {
      this.validating = false
    }
  }

  private useQuickTemplate(template: QuickTemplate) {
    this.manualForm.classPath = template.path
    this.validateManualClass()
  }

  private clearManualForm() {
    this.manualForm.classPath = ''
    this.validationResult = null
    this.$emit('input', '')
    this.$emit('change', '')
  }

  private getCurrentSelection(): string {
    return this.activeTab === 'manual' ? this.manualForm.classPath : this.selectedClass?.path || ''
  }

  private setSelection(path: string) {
    if (!path) {
      this.activeTab = 'preset'
      this.selectedClass = null
      this.manualForm.classPath = ''
      return
    }

    if (this.isPresetClass(path)) {
      this.activeTab = 'preset'
      const cls = this.findNodeInTree(this.classTree, path)
      if (cls) {
        this.selectedClass = cls
      } else {
        // 如果在预定义中找不到，回退到手动输入
        this.activeTab = 'manual'
        this.manualForm.classPath = path
      }
    } else {
      this.activeTab = 'manual'
      this.manualForm.classPath = path
      // 延迟验证，避免初始化时的重复调用
      this.$nextTick(() => {
        if (path) {
          this.validateManualClass()
        }
      })
    }
  }

  private isPresetClass(path: string): boolean {
    return this.findNodeInTree(this.classTree, path) !== null
  }

  private findNodeInTree(nodes: ClassNode[], path: string): ClassNode | null {
    for (const node of nodes) {
      if (node.path === path) {
        return node
      }
      if (node.children) {
        const found = this.findNodeInTree(node.children, path)
        if (found) {
          return found
        }
      }
    }
    return null
  }

  private async callClassCheckAPI(path: string): Promise<ValidationResult> {
    try {
      const response = await validatePythonClass({ class_path: path })
      return response.data
    } catch (error) {
      console.error('调用类检查API失败:', error)
      // 本地基础验证作为后备
      return this.localClassValidation(path)
    }
  }

  private localClassValidation(path: string): ValidationResult {
    // 本地基础验证
    const formatValid = this.validateClassPathFormat(path)
    if (!formatValid.valid) {
      return formatValid
    }

    // 检查是否在允许的模块中
    const allowedPrefixes = [
      'app.tasks.backup',
      'app.tasks.cleanup',
      'app.tasks.sync',
      'app.tasks.monitor',
      'app.tasks.custom',
      'app.tasks.scheduler'
    ]

    const pathParts = path.split(".")
    const modulePath = pathParts.slice(0, -1).join(".")
    if (!allowedPrefixes.some(prefix => modulePath.startsWith(prefix))) {
      return {
        valid: false,
        message: this.$t('tasks.pythonSelector.msg.notAllowed'),
        details: {
          exists: false,
          module_path: modulePath,
          class_info: this.$t('tasks.pythonSelector.msg.notAllowedClassInfo')
        }
      }
    }

    return {
      valid: true,
      message: this.$t('tasks.pythonSelector.msg.formatOkWaiting'),
      details: {
        exists: false,
        module_path: modulePath,
        class_info: this.$t('tasks.pythonSelector.msg.needRuntimeCheck'),
      }
    }
  }

  private validateClassPathFormat(path: string): ValidationResult {
    if (!path) {
      return { valid: false, message: this.$t('tasks.pythonSelector.msg.emptyPath') }
    }

    const validPattern = /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)*$/
    if (!validPattern.test(path)) {
      return {
        valid: false,
        message: this.$t('tasks.pythonSelector.validation.formatInvalid')
      }
    }

    const parts = path.split('.')
    if (parts.length < 2) {
      return {
        valid: false,
        message: this.$t('tasks.pythonSelector.validation.missingParts')
      }
    }

    const className = parts[parts.length - 1]
    if (!/^[A-Z][a-zA-Z0-9]*$/.test(className)) {
      return {
        valid: false,
        message: this.$t('tasks.pythonSelector.validation.classNameCase')
      }
    }

    return { valid: true, message: this.$t('tasks.pythonSelector.validation.formatOk') }
  }

  // 历史记录管理
  private loadHistory() {
    const saved = localStorage.getItem('python-class-history')
    if (saved) {
      try {
        this.historyList = JSON.parse(saved).map((item: any) => ({
          ...item,
          time: new Date(item.time)
        }))
      } catch (error) {
        console.error('加载历史记录失败:', error)
      }
    }
  }

  private saveHistory() {
    localStorage.setItem('python-class-history', JSON.stringify(this.historyList))
  }

  private addToHistory(path: string, valid: boolean) {
    // 移除已存在的相同路径
    this.historyList = this.historyList.filter(item => item.path !== path)

    // 添加到开头
    this.historyList.unshift({
      path,
      time: new Date(),
      valid
    })

    // 限制历史记录数量
    if (this.historyList.length > 10) {
      this.historyList = this.historyList.slice(0, 10)
    }

    this.saveHistory()
  }

  private useHistoryItem(item: HistoryItem) {
    this.manualForm.classPath = item.path
    this.validateManualClass()
  }

  private removeHistoryItem(index: number) {
    this.historyList.splice(index, 1)
    this.saveHistory()
  }

  private formatTime(time: Date): string {
    return time.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }
}
</script>

<style scoped>
.python-class-selector {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  overflow: hidden;
}

/* 预定义类选择样式 */
.preset-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 16px 8px;
  background-color: #f8f9fa;
  border-bottom: 1px solid #e4e7ed;
}

.preset-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.class-tree-container {
  max-height: 500px;
  overflow-y: auto;
  padding: 16px;
}

.class-tree {
  background: white;
}

.custom-tree-node {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  padding: 4px 0;
}

.node-content {
  display: flex;
  align-items: center;
  width: 100%;
  margin-bottom: 2px;
}

.node-icon {
  margin-right: 8px;
  color: #409eff;
  font-size: 16px;
  width: 16px;
  text-align: center;
}

.node-label {
  font-weight: 500;
  color: #303133;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-badge {
  margin-left: 8px;
}

.node-description {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  padding-left: 24px;
  white-space: normal;
  word-wrap: break-word;
  line-height: 1.4;
}

.node-actions {
  margin-left: 8px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.custom-tree-node:hover .node-actions {
  opacity: 1;
}

.node-actions i {
  font-size: 14px;
  color: #909399;
  cursor: pointer;
  transition: color 0.2s ease;
}

.node-actions i:hover {
  color: #409eff;
}

/* 选中类信息 */
.selected-class-info {
  border-top: 1px solid #e4e7ed;
  padding: 16px;
  background: linear-gradient(135deg, #f0f9ff 0%, #ffffff 100%);
}

.info-header {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 12px;
}

.info-header i {
  margin-right: 6px;
  color: #409eff;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-item label {
  font-weight: 500;
  color: #606266;
  min-width: 80px;
}

.parameters-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.parameter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.param-desc {
  font-size: 12px;
  color: #606266;
}

.required-indicator {
  color: #f56c6c;
  margin-left: 4px;
}

/* 手动输入样式 */
.el-form {
  padding: 16px;
}

.input-help {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}

.quick-templates {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
}

.template-btn {
  margin: 0;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 150px;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 8px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-item:hover {
  border-color: #409eff;
  background-color: #f5f9ff;
}

.history-time {
  font-size: 11px;
  color: #909399;
  margin-left: 8px;
}

.history-delete {
  opacity: 0;
  transition: opacity 0.2s ease;
}

.history-item:hover .history-delete {
  opacity: 1;
}

.validation-loading {
  padding: 16px;
}

.validation-pending {
  padding: 0;
}

.validation-details {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}

.validation-details p {
  margin: 4px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 类详情对话框 */
.class-detail-dialog .el-dialog__body {
  padding: 20px;
}

.class-detail {
  max-height: 60vh;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.detail-header h3 {
  margin: 0;
  color: #303133;
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section {
  border-left: 3px solid #409eff;
  padding-left: 16px;
}

.detail-section h4 {
  margin: 0 0 12px 0;
  color: #303133;
  font-size: 14px;
  font-weight: 500;
}

.methods-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.method-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #f8f9fa;
  border-radius: 4px;
}

.method-desc {
  font-size: 12px;
  color: #606266;
}

/* 滚动条样式 */
.class-tree-container::-webkit-scrollbar {
  width: 6px;
}

.class-tree-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.class-tree-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.class-tree-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.history-list::-webkit-scrollbar {
  width: 4px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .preset-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .info-content {
    gap: 6px;
  }

  .quick-templates {
    justify-content: flex-start;
  }

  .node-content {
    flex-wrap: wrap;
  }

  .node-description {
    padding-left: 0;
    margin-left: 0;
  }
}

/* 动画效果 */
.custom-tree-node {
  transition: background-color 0.2s ease;
}

.custom-tree-node:hover {
  background-color: #f5f9ff;
}

.class-detail-dialog {
  animation: slideInUp 0.3s ease-out;
}

@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 加载状态 */
.el-loading-parent--relative {
  position: relative;
}
</style>
