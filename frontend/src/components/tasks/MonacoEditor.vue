<template>
  <div class="monaco-editor-container">
    <div ref="editorContainer" class="editor-container" :style="{height: height}"></div>
    <div v-if="loading" class="editor-loading">
      <el-skeleton :rows="5" animated />
    </div>
    <div v-if="loadError" class="editor-error">
      <el-alert
        title="编辑器加载失败"
        type="error"
        description="已切换到基础模式，您可以继续使用文本编辑器"
        show-icon
        :closable="false"
      />
      <el-button type="primary" size="small" @click="retryLoadEditor" style="margin-top: 10px;">
        重试加载
      </el-button>
    </div>
    <!-- 降级文本编辑器 -->
    <el-input
      v-if="loadError"
      type="textarea"
      :rows="8"
      :value="value"
      @input="handleTextareaInput"
      :placeholder="placeholder"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import request from '@/utils/request'

interface ValidationMarker {
  startLineNumber: number
  startColumn: number
  endLineNumber: number
  endColumn: number
  severity: number
  message: string
}

@Component({ name: 'MonacoEditor' })
export default class MonacoEditor extends Vue {
  @Prop({ required: true }) value!: string
  @Prop({ required: true }) language!: 'shell' | 'batch' | 'powershell' | 'python'
  @Prop({ default: '300px' }) height!: string
  @Prop({ default: true }) syntaxValidation!: boolean
  @Prop({ default: '' }) placeholder!: string

  private editor: any = null
  private monaco: any = null
  private loading = true
  private loadError = false
  private loadingProgress = 0
  private errorMarkers: ValidationMarker[] = []
  private validationTimer: number | null = null
  private isInitialized = false

  // 添加缺失的响应式属性
  private syntaxStatus = ''
  private executionStatus = ''
  private 代码语法正确 = false
  private 可以正常执行 = false

  async mounted() {
    await this.initializeMonaco()
  }

  beforeDestroy() {
    this.disposeEditor()
    this.clearValidationTimer()
  }

  private async initializeMonaco() {
    try {
      this.loading = true
      this.loadError = false
      this.loadingProgress = 0

      // 分步加载Monaco Editor
      await this.loadCoreLibrary()
      this.loadingProgress = 30

      await this.loadLanguagePack()
      this.loadingProgress = 70

      await this.loadThemes()
      this.loadingProgress = 100

      await this.createEditor()
      this.setupEditorEvents()
      this.isInitialized = true

    } catch (error) {
      console.error('Monaco Editor初始化失败:', error)
      this.handleLoadError(error)
    } finally {
      this.loading = false
    }
  }

  private async loadCoreLibrary() {
    // 动态加载Monaco Editor核心库
    this.monaco = await import('monaco-editor')
    this.configureMonacoSettings()
  }

  private async loadLanguagePack() {
    // Monaco Editor 0.34.1版本中，大部分语言包已经内置
    // Shell、Python、Batch、PowerShell等语言通常已经包含在Monaco中
    // 不需要手动加载额外的语言包
    // 如果出现语言包加载错误，Monaco会自动降级为纯文本模式
    console.log(`Monaco Editor语言支持: ${this.language} (使用内置语言包或纯文本模式)`)
  }

  private async loadThemes() {
    // 加载主题
    this.monaco.editor.defineTheme('custom-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '6A9955' },
        { token: 'keyword', foreground: '569CD6' },
        { token: 'string', foreground: '98C379' },
        { token: 'number', foreground: 'B5CEA8' },
        { token: 'type', foreground: '4EC9B0' }
      ],
      colors: {
        'editor.background': '#1E1E1E',
        'editor.foreground': '#D4D4D4',
        'editorCursor.foreground': '#FFFFFF',
        'editor.lineHighlightBackground': '#2D2D30',
        'editor.selectionBackground': '#264F78',
        'editor.inactiveSelectionBackground': '#3A3D41'
      }
    })
  }

  private configureMonacoSettings() {
    // 配置Monaco Editor全局设置
    this.monaco.languages.typescript.javascriptDefaults.setCompilerOptions({
      noLib: true,
      allowNonTsExtensions: true
    })

    // 配置编辑器选项
    this.monaco.editor.setTheme('custom-dark')
  }

  private async createEditor() {
    if (!this.monaco || !this.$refs.editorContainer) {
      return
    }

    this.editor = this.monaco.editor.create(this.$refs.editorContainer as HTMLElement, {
      value: this.value,
      language: this.getMonacoLanguage(),
      theme: 'custom-dark',
      minimap: {
        enabled: false
      },
      scrollBeyondLastLine: false,
      fontSize: 14,
      lineHeight: 1.6,
      wordWrap: 'on',
      automaticLayout: true,
      lineNumbers: 'on',
      renderWhitespace: 'boundary',
      renderIndentGuides: true,
      cursorStyle: 'line',
      mouseWheelZoom: true,
      contextmenu: true,
      quickSuggestions: {
        other: true,
        comments: true,
        strings: true
      },
      suggestOnTriggerCharacters: true,
      acceptSuggestionOnEnter: 'on',
      tabCompletion: 'on',
      wordBasedSuggestions: 'allDocuments',
      parameterHints: {
        enabled: true
      },
      autoIndent: 'advanced',
      formatOnPaste: true,
      formatOnType: true
    })

    // 设置模型选项
    const model = this.editor.getModel()
    if (model) {
      this.monaco.editor.setModelLanguage(model, this.getMonacoLanguage())
      model.updateOptions({
        tabSize: 2,
        insertSpaces: true
      })
    }

    // 设置初始内容
    if (this.value) {
      this.editor.setValue(this.value)
    }
  }

  private setupEditorEvents() {
    if (!this.editor) return

    // 监听内容变化
    this.editor.onDidChangeModelContent(() => {
      const newValue = this.editor.getValue()
      this.$emit('input', newValue)
      this.$emit('change', newValue)

      // 防抖语法校验
      if (this.syntaxValidation) {
        this.debounceSyntaxValidation()
      }
    })

    // 监听语言切换
    this.editor.onDidChangeModelLanguage(() => {
      this.$emit('language-change', this.language)
    })

    // 监听光标位置变化
    this.editor.onDidChangeCursorPosition((e: any) => {
      this.$emit('cursor-change', {
        lineNumber: e.position.lineNumber,
        column: e.position.column
      })
    })

    // 监听选择变化
    this.editor.onDidChangeCursorSelection((e: any) => {
      const selection = this.editor.getSelection()
      const selectedText = this.editor.getModel().getValueInRange(selection)
      this.$emit('selection-change', {
        selectedText,
        selection
      })
    })

    // 监听焦点变化
    this.editor.onDidFocusEditorWidget(() => {
      this.$emit('focus')
    })

    this.editor.onDidBlurEditorWidget(() => {
      this.$emit('blur')
    })

    // 监听错误标记变化
    if (this.monaco.editor) {
      this.monaco.editor.onDidChangeMarkers((uris) => {
        this.updateErrorMarkers()
      })
    }
  }

  private getMonacoLanguage(): string {
    const languageMap: Record<string, string> = {
      shell: 'shell',
      batch: 'batch',
      powershell: 'powershell',
      python: 'python'
    }
    return languageMap[this.language] || 'plaintext'
  }

  private debounceSyntaxValidation() {
    this.clearValidationTimer()
    this.validationTimer = setTimeout(() => {
      this.validateSyntax()
    }, 800)
  }

  private clearValidationTimer() {
    if (this.validationTimer) {
      clearTimeout(this.validationTimer)
      this.validationTimer = null
    }
  }

  private async validateSyntax() {
    if (!this.syntaxValidation || !this.editor || !this.monaco) {
      return
    }

    try {
      const content = this.editor.getValue()
      if (!content) {
        this.errorMarkers = []
        this.代码语法正确 = false
        this.可以正常执行 = false
        this.syntaxStatus = ''
        this.executionStatus = ''
        this.$emit('validation-change', [])
        return
      }

      // 调用后端语法校验API
      const validationResult = await this.callSyntaxValidationAPI(content)

      // 确保validationResult有有效的结构
      const validResult = {
        valid: Boolean(validationResult && validationResult.valid),
        errors: Array.isArray(validationResult?.errors) ? validationResult.errors : []
      }

      this.updateErrorMarkers(validResult.errors)

      // 更新响应式状态属性
      this.代码语法正确 = validResult.valid
      this.可以正常执行 = validResult.valid
      this.syntaxStatus = validResult.valid ? '语法正确' : '存在语法错误'
      this.executionStatus = validResult.valid ? '可以执行' : '执行可能失败'

      this.$emit('validation-change', validResult.errors)

    } catch (error) {
      console.error('语法校验失败:', error)
      this.代码语法正确 = false
      this.可以正常执行 = false
      this.syntaxStatus = '语法校验失败'
      this.executionStatus = '无法执行'
      // 发出空错误数组，确保前端能正常处理
      this.$emit('validation-change', [])
    }
  }

  private updateErrorMarkers(markers: ValidationMarker[]) {
    if (!this.monaco || !this.editor || !this.editor.getModel()) {
      return
    }

    const monacoMarkers = markers.map(error => ({
      severity: this.monaco.MarkerSeverity.Error,
      message: error.message,
      startLineNumber: error.startLineNumber,
      startColumn: error.startColumn,
      endLineNumber: error.endLineNumber,
      endColumn: error.endColumn
    }))

    this.monaco.editor.setModelMarkers(this.editor.getModel(), 'monaco-editor', monacoMarkers)
    this.errorMarkers = markers
  }

  private async callSyntaxValidationAPI(content: string): Promise<{ valid: boolean, errors: ValidationMarker[] }> {
    try {
      // 这里调用后端API进行语法校验
      const response = await request({
        method: 'post',
        url: '/cronTasks/validation/script',
        data: {
          content,
          script_type: this.getScriptTypeCode()
        }
      })

      // 确保返回的数据结构正确
      const result = response.data
      if (result && typeof result === 'object') {
        return {
          valid: Boolean(result.valid),
          errors: Array.isArray(result.errors) ? result.errors : []
        }
      } else {
        console.warn('API返回的数据格式不正确:', result)
        return this.localSyntaxValidation(content)
      }
    } catch (error) {
      console.error('调用语法校验API失败:', error)
      // 返回本地基础校验结果
      return this.localSyntaxValidation(content)
    }
  }

  private getScriptTypeCode(): number {
    const scriptTypeMap = {
      shell: 0,
      batch: 1,
      powershell: 2,
      python: 3
    }
    return scriptTypeMap[this.language] || 0
  }

  private localSyntaxValidation(content: string): { valid: boolean, errors: ValidationMarker[] } {
    const errors: ValidationMarker[] = []
    const lines = content.split('\n')

    for (let lineNum = 0; lineNum < lines.length; lineNum++) {
      const line = lines[lineNum]
      const trimmedLine = line.trim()

      if (!trimmedLine || trimmedLine.startsWith('#') || trimmedLine.startsWith('//')) {
        continue
      }

      // 基础语法检查
      if (this.language === 'python') {
        // Python 基础检查
        if (line.includes('print(') && !line.includes('")')) {
          errors.push({
            startLineNumber: lineNum + 1,
            startColumn: line.indexOf('print(') + 8,
            endLineNumber: lineNum + 1,
            endColumn: line.indexOf('print(') + 10,
            severity: 8,
            message: 'print语句可能缺少引号'
          })
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors
    }
  }

  private handleTextareaInput(event: any) {
    this.$emit('input', event.target.value)
  }

  private handleLoadError(error: any) {
    this.loadError = true
    this.$emit('init-error', error)
  }

  private async retryLoadEditor() {
    this.loadError = false
    await this.initializeMonaco()
  }

  private disposeEditor() {
    if (this.validationTimer) {
      clearTimeout(this.validationTimer)
      this.validationTimer = null
    }

    if (this.editor) {
      const model = this.editor.getModel()
      if (model) {
        model.dispose()
      }
      this.editor.dispose()
      this.editor = null
    }
  }

  @Watch('value')
  onValueChange(newValue: string) {
    if (this.editor && this.editor.getValue() !== newValue) {
      this.editor.setValue(newValue)
    }
  }

  @Watch('language')
  onLanguageChange(newLanguage: string) {
    if (this.editor && this.isInitialized) {
      const monacoLanguage = this.getMonacoLanguage()
      this.monaco.editor.setModelLanguage(this.editor.getModel(), monacoLanguage)
    }
  }

  // 公共方法供外部调用
  public getValue(): string {
    return this.editor ? this.editor.getValue() : this.value
  }

  public getSelection(): any {
    return this.editor ? this.editor.getSelection() : null
  }

  public focus() {
    if (this.editor) {
      this.editor.focus()
    }
  }

  public setValue(newValue: string) {
    if (this.editor) {
      this.editor.setValue(newValue)
    }
  }

  public setLanguage(language: string) {
    this.$emit('update:language', language)
  }

  public async validate(): Promise<{ valid: boolean, errors: ValidationMarker[] }> {
    await this.validateSyntax()
    return {
      valid: this.errorMarkers.length === 0,
      errors: this.errorMarkers
    }
  }

  public resize() {
    if (this.editor) {
      this.editor.layout()
    }
  }
}
</script>

<style scoped>
.monaco-editor-container {
  position: relative;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
  background-color: #1e1e1e;
}

.editor-container {
  width: 100%;
  min-height: 200px;
}

.editor-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(30, 30, 30, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  padding: 20px;
}

.editor-error {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(30, 30, 30, 0.95);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 10;
  padding: 20px;
  text-align: center;
}

.editor-error .el-alert {
  max-width: 400px;
  margin-bottom: 15px;
}

/* 加载动画 */
.editor-loading::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 40px;
  height: 40px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #409eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: translate(-50%, -50%) rotate(0deg); }
  100% { transform: translate(-50%, -50%) rotate(360deg); }
}

/* 编辑器容器样式优化 */
.monaco-editor-container:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.monaco-editor-container:hover {
  border-color: #c0c4cc;
}

/* 错误状态样式 */
.monaco-editor-container.has-errors {
  border-color: #f56c6c;
}

/* 进度显示 */
.editor-container::after {
  content: attr(data-progress) '';
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  background: #409eff;
  transition: width 0.3s ease;
  z-index: 5;
}

.editor-container[data-progress="10"]::after {
  width: 10%;
}

.editor-container[data-progress="30"]::after {
  width: 30%;
}

.editor-container[data-progress="70"]::after {
  width: 70%;
}

.editor-container[data-progress="100"]::after {
  width: 100%;
  display: none;
}

/* 降级文本编辑器样式 */
.el-textarea {
  width: 100%;
  min-height: 200px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 12px;
  font-family: 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  background-color: #f5f7fa;
  color: #303133;
}

.el-textarea:focus {
  border-color: #409eff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .editor-loading,
  .editor-error {
    padding: 15px;
  }

  .editor-loading::before {
    width: 30px;
    height: 30px;
  }
}
</style>