<template>
  <div ref="editorContainer" class="monaco-editor-container" :style="{height: height}"></div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import * as monaco from 'monaco-editor'

@Component({
  name: 'MonacoEditor'
})
export default class MonacoEditor extends Vue {
  @Prop({ default: '100%' }) width!: string
  @Prop({ default: '300px' }) height!: string
  @Prop({ default: 'plaintext' }) language!: string
  @Prop({ default: 'vs' }) theme!: string
  @Prop({ default: '' }) value!: string
  @Prop({ default: false }) readonly!: boolean
  @Prop({ default: true }) options!: any

  private editor: monaco.editor.IStandaloneCodeEditor | null = null

  mounted() {
    this.initMonaco()
  }

  beforeDestroy() {
    this.destroy()
  }

  @Watch('value')
  onValueChange(newValue: string) {
    if (this.editor && newValue !== this.editor.getValue()) {
      this.editor.setValue(newValue)
    }
  }

  @Watch('language')
  onLanguageChange(newLanguage: string) {
    if (this.editor) {
      monaco.editor.setModelLanguage(this.editor.getModel()!, newLanguage)
    }
  }

  @Watch('theme')
  onThemeChange(newTheme: string) {
    if (this.editor) {
      monaco.editor.setTheme(newTheme)
    }
  }

  @Watch('options')
  onOptionsChange(newOptions: any) {
    if (this.editor) {
      this.editor.updateOptions(newOptions)
    }
  }

  private initMonaco() {
    const monacoOptions = {
      value: this.value,
      language: this.language,
      theme: this.theme,
      readOnly: this.readonly,
      ...this.options
    }

    this.editor = monaco.editor.create(this.$refs.editorContainer as HTMLElement, monacoOptions)

    // Emit change event
    this.editor.onDidChangeModelContent(() => {
      const value = this.editor!.getValue()
      this.$emit('input', value)
      this.$emit('change', value)
    })

    // Emit editor instance
    this.$emit('editor-ready', this.editor)
  }

  private destroy() {
    if (this.editor) {
      this.editor.dispose()
      this.editor = null
    }
  }

  // Public methods
  public getValue(): string {
    return this.editor ? this.editor.getValue() : ''
  }

  public setValue(value: string): void {
    if (this.editor) {
      this.editor.setValue(value)
    }
  }

  public focus(): void {
    if (this.editor) {
      this.editor.focus()
    }
  }

  public getEditor(): monaco.editor.IStandaloneCodeEditor | null {
    return this.editor
  }
}
</script>

<style lang="scss" scoped>
.monaco-editor-container {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}
</style>