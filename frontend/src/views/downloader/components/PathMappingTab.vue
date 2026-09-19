<template>
  <div class="path-mapping-tab">
    <!-- 头部说明和操作区 -->
    <div class="tab-header">
      <div class="header-info">
        <span class="header-icon"><LucideIcon name="route" :size="18" /></span>
        <div class="header-text">
          <h3 class="header-title">{{ $t('downloader.pathMapping.headerTitle') }}</h3>
          <p class="header-desc">{{ $t('downloader.pathMapping.headerDesc') }}</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button type="success" size="medium" :disabled="refreshing" @click="handleRefresh">
          <LucideIcon class="button-icon" name="refresh-cw" :size="14" :class="{'is-spinning': refreshing}" />
          {{ $t('downloader.pathMapping.refresh') }}
        </el-button>
        <el-button type="primary" size="medium" @click="handleAddMapping">
          <LucideIcon class="button-icon" name="plus" :size="14" />
          {{ $t('downloader.pathMapping.add') }}
        </el-button>
      </div>
    </div>

    <!-- 映射表格 -->
    <div class="mapping-table-wrapper">
      <el-table
        :data="mappings"
        style="width: 100%"
        header-row-class-name="mapping-table-header"
      >
        <!-- 映射名称 -->
        <el-table-column :label="$t('downloader.pathMapping.colName')" min-width="150">
          <template #default="{row, $index}">
            <div class="mapping-name-cell">
              <el-input
                v-model="row.name"
                :placeholder="$t('downloader.pathMapping.namePlaceholder')"
                size="small"
                @blur="validateMappingName($index)"
              >
                <template slot="prefix">
                  <LucideIcon class="input-icon" name="tag" :size="13" />
                </template>
              </el-input>
              <!-- 自动发现标记 -->
              <el-tooltip
                v-if="row.description?.includes($t('downloader.pathMapping.autoDiscovered').toString())"
                :content="$t('downloader.pathMapping.autoDiscoveredHint')"
                placement="top"
              >
                <LucideIcon class="auto-discovered-icon" name="info" :size="14" />
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <!-- 映射类型 -->
        <el-table-column :label="$t('downloader.pathMapping.colType')" min-width="130">
          <template #default="{row}">
            <el-select v-model="row.mapping_type" :placeholder="$t('downloader.pathMapping.typePlaceholder')" size="small">
              <el-option
                v-for="option in mappingTypeOptions"
                :key="option.value"
                :label="$t(option.labelKey)"
                :value="option.value"
              >
                <div class="mapping-type-option">
                  <span class="option-label">{{ $t(option.labelKey) }}</span>
                  <span class="option-desc">{{ $t(option.descriptionKey) }}</span>
                </div>
              </el-option>
            </el-select>
          </template>
        </el-table-column>

        <!-- 内部路径 -->
        <el-table-column :label="$t('downloader.pathMapping.colInternal')" min-width="220">
          <template #default="{row, $index}">
            <el-input
              v-model="row.internal"
              :placeholder="getPathPlaceholder(row.mapping_type, 'internal')"
              :title="getPathHint(row.mapping_type, 'internal')"
              size="small"
              @blur="validateInternalPath($index)"
            >
              <template slot="prefix">
                <LucideIcon class="input-icon" name="container" :size="13" />
              </template>
            </el-input>
          </template>
        </el-table-column>

        <!-- 外部路径 -->
        <el-table-column :label="$t('downloader.pathMapping.colExternal')" min-width="220">
          <template #default="{row, $index}">
            <el-input
              v-model="row.external"
              :placeholder="getPathPlaceholder(row.mapping_type, 'external')"
              :title="getPathHint(row.mapping_type, 'external')"
              size="small"
              @blur="validateExternalPath($index)"
            >
              <template slot="prefix">
                <LucideIcon class="input-icon" name="monitor" :size="13" />
              </template>
            </el-input>
          </template>
        </el-table-column>

        <!-- 描述 -->
        <el-table-column :label="$t('downloader.pathMapping.colDesc')" min-width="180">
          <template #default="{row}">
            <el-input
              v-model="row.description"
              :placeholder="$t('downloader.pathMapping.descPlaceholder')"
              size="small"
            />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column :label="$t('downloader.pathMapping.colActions')" width="100" fixed="right">
          <template #default="{$index}">
            <el-button
              type="danger"
              size="mini"
              @click="handleDeleteMapping($index)"
            >
              <LucideIcon name="trash-2" :size="13" />
              {{ $t('downloader.pathMapping.delete') }}
            </el-button>
          </template>
        </el-table-column>

        <!-- 空状态 -->
        <template #empty>
          <div class="empty-state">
            <LucideIcon class="empty-icon" name="route" :size="40" :stroke-width="1.35" />
            <p class="empty-text">{{ $t('downloader.pathMapping.emptyText') }}</p>
            <p class="empty-hint">{{ $t('downloader.pathMapping.emptyHint') }}</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 测试区域 -->
    <div class="test-section">
      <div class="test-header">
        <h4 class="test-title">{{ $t('downloader.pathMapping.testTitle') }}</h4>
        <el-button
          type="success"
          size="small"
          :disabled="mappings.length === 0 || testing"
          @click="handleTestConfig"
        >
          <LucideIcon class="button-icon" name="test-tube-2" :size="14" :class="{'is-spinning': testing}" />
          {{ $t('downloader.pathMapping.testButton') }}
        </el-button>
      </div>
      <div v-if="testResult" :class="['test-result', testResult.valid ? 'success' : 'error']">
        <LucideIcon
          class="result-icon"
          :name="testResult.valid ? 'circle-check-big' : 'circle-x'"
          :size="16"
        />
        <span class="result-message">{{ testResult.message }}</span>
        <div v-if="!testResult.valid && testResult.backend_validation?.errors?.length" class="error-details">
          <strong>{{ $t('downloader.pathMapping.errorDetail') }}</strong>
          <ul>
            <li v-for="(error, idx) in testResult.backend_validation.errors" :key="idx">
              {{ error }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import {
  Downloader,
  DownloaderSettings,
  PathMappingItem,
  PathMappingConfig,
  MappingType,
  MappingTypeOption,
  PathMappingTestResponse
} from '../types'
import { apiErrorMessage, apiResponseMessage, translate } from '@/i18n'
import { testPathMapping } from '@/api/downloader'
import { generateExternalPathFromRules } from '../path-mapping-rules'

interface VueLifecycleFlags {
  _isDestroyed?: boolean
  _isBeingDestroyed?: boolean
}

interface ApiErrorLike {
  response?: { data?: { msg?: string } }
  message?: string
}

@Component({
  name: 'PathMappingTab'
})
export default class PathMappingTab extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null
  @Prop({ default: () => ({}) as DownloaderSettings }) settings!: DownloaderSettings
  // 规则以详情表单为准，允许弹窗在异步详情回填后实时更新。
  // 未传入时回退到旧的 downloader 字段，兼容独立使用该组件的调用方。
  @Prop({ default: undefined }) pathMappingRules!: string | undefined

  // 路径映射列表
  private mappings: PathMappingItem[] = []

  // 测试状态
  private testing = false
  private testResult: PathMappingTestResponse | null = null

  // 刷新状态
  private refreshing = false

  // 映射类型选项
  // 双语 P6-2：展示文案改 labelKey/descriptionKey/placeholderKey，按当前语言渲染
  private mappingTypeOptions: MappingTypeOption[] = [
    {
      value: 'local',
      labelKey: 'downloader.pathMapping.preset.local',
      descriptionKey: 'downloader.pathMapping.preset.localDesc',
      placeholderKey: 'downloader.pathMapping.preset.localExternalPlaceholder'
    },
    {
      value: 'docker',
      labelKey: 'downloader.pathMapping.preset.docker',
      descriptionKey: 'downloader.pathMapping.preset.dockerDesc',
      placeholderKey: 'downloader.pathMapping.preset.dockerExternalPlaceholder'
    },
    {
      value: 'nas',
      labelKey: 'downloader.pathMapping.preset.nas',
      descriptionKey: 'downloader.pathMapping.preset.nasDesc',
      placeholderKey: 'downloader.pathMapping.preset.nasExternalPlaceholder'
    },
    {
      value: 'wsl',
      labelKey: 'downloader.pathMapping.preset.local',
      descriptionKey: 'downloader.pathMapping.preset.windowsInternalPlaceholder',
      placeholderKey: 'downloader.pathMapping.preset.windowsExternalPlaceholder'
    },
    {
      value: 'network',
      labelKey: 'downloader.pathMapping.preset.network',
      descriptionKey: 'downloader.pathMapping.preset.networkDesc',
      placeholderKey: 'downloader.pathMapping.preset.networkExternalPlaceholder'
    }
  ]

  private get isComponentDestroyed(): boolean {
    const flags = this as unknown as VueLifecycleFlags
    return Boolean(flags._isDestroyed || flags._isBeingDestroyed)
  }

  // 初始化
  mounted() {
    this.loadPathMappings()
  }

  // 监听下载器变化
  @Watch('downloader')
  onDownloaderChange() {
    // 清空旧数据，避免显示上一个下载器的路径映射
    this.mappings = []
    this.testResult = null
    // 重新加载当前下载器的路径映射数据
    this.loadPathMappings()
  }

  // 监听路径映射配置变化（处理异步数据加载）
  @Watch('settings', { deep: true })
  onSettingsChange(newSettings: DownloaderSettings) {
    const newMapping = newSettings?.path_mapping

    // 检查是否有映射数据（通过内容判断，而不是引用）
    if (newMapping && newMapping.mappings && Array.isArray(newMapping.mappings)) {
      // 如果当前没有数据，或者数据长度不同，则重新加载
      if (this.mappings.length === 0 || this.mappings.length !== newMapping.mappings.length) {
        this.loadPathMappings()
      }
    } else if (newMapping && !newMapping.mappings) {
      // path_mapping 存在但 mappings 为空或未定义
      this.mappings = []
    }
  }

  // 加载路径映射配置
  private async loadPathMappings() {
    if (this.settings.path_mapping?.mappings) {
      this.mappings = [...this.settings.path_mapping.mappings]
    } else {
      this.mappings = []
    }
  }

  // 刷新路径映射配置
  private async handleRefresh() {
    if (!this.downloader) {
      this.$message.error(this.$t('downloader.pathMapping.msg.downloaderMissing').toString())
      return
    }

    // 提示用户确认
    try {
      await this.$confirm(
        this.$t('downloader.pathMapping.msg.reloadConfirm').toString(),
        this.$t('downloader.pathMapping.msg.reloadTitle').toString(),
        {
          confirmButtonText: this.$t('downloader.pathMapping.msg.confirm').toString(),
          cancelButtonText: this.$t('downloader.pathMapping.msg.cancel').toString(),
          type: 'warning'
        }
      )
    } catch {
      // 用户取消
      return
    }

    this.refreshing = true

    try {
      // 重新加载路径映射配置
      const { getPathMappings } = await import('@/api/downloader')
      const response = await getPathMappings(this.downloader.id)

      // 检查组件是否已销毁
      if (this.isComponentDestroyed) {
        return
      }

      if (response.code === '200' && response.data) {
        // 更新 settings（通过父组件更新）
        this.$emit('update:settings', {
          ...this.settings,
          path_mapping: response.data
        })

        // 更新本地映射列表
        if (response.data.mappings) {
          this.mappings = [...response.data.mappings]
        } else {
          this.mappings = []
        }

        this.$message.success(this.$t('downloader.pathMapping.msg.refreshSuccess').toString())
      } else {
        this.$message.error(apiResponseMessage(response, this.$t('downloader.pathMapping.msg.refreshFailed')))
      }
    } catch (error: unknown) {
      // 再次检查组件状态
      if (this.isComponentDestroyed) {
        return
      }
      console.error('刷新路径映射配置失败:', error)
      const apiError = error as ApiErrorLike
      this.$message.error(apiErrorMessage(apiError, this.$t('downloader.pathMapping.msg.refreshFailed')))
    } finally {
      // 安全地更新状态
      if (!this.isComponentDestroyed) {
        this.refreshing = false
      }
    }
  }

  // 获取路径输入框占位符
  private getPathPlaceholder(mappingType: MappingType, _pathType: 'internal' | 'external'): string {
    const option = this.mappingTypeOptions.find(opt => opt.value === mappingType)
    return option?.placeholderKey
      ? translate(option.placeholderKey)
      : translate('downloader.pathMapping.pathPlaceholder')
  }

  // 获取路径格式提示
  private getPathHint(mappingType: MappingType, pathType: 'internal' | 'external'): string {
    const hints: Record<MappingType, { internal: string, external: string }> = {
      local: {
        internal: 'downloader.pathMapping.preset.localInternalPlaceholder',
        external: 'downloader.pathMapping.preset.localExternalInputPlaceholder'
      },
      docker: {
        internal: 'downloader.pathMapping.preset.dockerInternalPlaceholder',
        external: 'downloader.pathMapping.preset.dockerExternalInputPlaceholder'
      },
      nas: {
        internal: 'downloader.pathMapping.preset.nasInternalPlaceholder',
        external: 'downloader.pathMapping.preset.nasExternalInputPlaceholder'
      },
      wsl: {
        internal: 'downloader.pathMapping.preset.windowsInternalPlaceholder',
        external: 'downloader.pathMapping.preset.windowsExternalInputPlaceholder'
      },
      network: {
        internal: 'downloader.pathMapping.preset.networkInternalPlaceholder',
        external: 'downloader.pathMapping.preset.networkExternalInputPlaceholder'
      }
    }
    const key = hints[mappingType]?.[pathType]
    return key ? translate(key) : ''
  }

  // {{ $t('downloader.pathMapping.add') }}
  private handleAddMapping() {
    const newMapping: PathMappingItem = {
      name: '',
      internal: '',
      external: '',
      description: '',
      mapping_type: 'local'
    }
    this.mappings.push(newMapping)
  }

  // 删除映射
  private handleDeleteMapping(index: number) {
    this.$confirm(this.$t('downloader.pathMapping.msg.deleteConfirm').toString(), this.$t('downloader.pathMapping.msg.deleteTitle').toString(), {
      confirmButtonText: this.$t('downloader.pathMapping.msg.confirm').toString(),

      cancelButtonText: this.$t('downloader.pathMapping.msg.cancel').toString(),
      type: 'warning'
    }).then(() => {
      this.mappings.splice(index, 1)
      this.$message.success(this.$t('downloader.pathMapping.msg.deleteSuccess').toString())
    }).catch(() => {
      // 用户取消
    })
  }

  // 验证映射名称
  private validateMappingName(index: number) {
    // 边界检查
    if (index < 0 || index >= this.mappings.length) {
      console.warn(`Invalid mapping index: ${index}`)
      return false
    }

    const mapping = this.mappings[index]
    if (!mapping?.name?.trim()) {
      this.$message.warning(this.$t('downloader.pathMapping.msg.nameRequired').toString())
      return false
    }

    // 检查名称唯一性
    const duplicateCount = this.mappings.filter(
      (m, i) => i !== index && m.name === mapping.name
    ).length

    if (duplicateCount > 0) {
      this.$message.error(this.$t('downloader.pathMapping.msg.nameDuplicate').toString())
      return false
    }

    return true
  }

  // 验证内部路径
  private validateInternalPath(index: number) {
    // 边界检查
    if (index < 0 || index >= this.mappings.length) {
      console.warn(`Invalid mapping index: ${index}`)
      return false
    }

    const mapping = this.mappings[index]
    if (!mapping?.internal?.trim()) {
      this.$message.warning(this.$t('downloader.pathMapping.msg.internalRequired').toString())
      return false
    }

    // 路径格式基本验证
    const path = mapping.internal.trim()
    if (!path.startsWith('/') && !path.startsWith('//')) {
      this.$message.warning(this.$t('downloader.pathMapping.msg.internalFormat').toString())
      return false
    }

    return true
  }

  // 验证外部路径
  private validateExternalPath(index: number) {
    // 边界检查
    if (index < 0 || index >= this.mappings.length) {
      console.warn(`Invalid mapping index: ${index}`)
      return false
    }

    const mapping = this.mappings[index]
    if (!mapping?.external?.trim()) {
      this.$message.warning(this.$t('downloader.pathMapping.msg.externalRequired').toString())
      return false
    }

    // 路径格式基本验证
    const path = mapping.external.trim()
    const isValid = path.startsWith('/') || path.startsWith('//') ||
                   /^[A-Za-z]:/.test(path) || path.startsWith('\\')

    if (!isValid) {
      this.$message.warning(this.$t('downloader.pathMapping.msg.externalFormat').toString())
      return false
    }

    return true
  }

  // {{ $t('downloader.pathMapping.testButton') }}
  private async handleTestConfig() {
    // 在第一个 await 前保存快照
    const downloader = this.downloader
    const mappings = [...this.mappings]

    if (!downloader) {
      this.$message.error(this.$t('downloader.pathMapping.msg.downloaderMissing').toString())
      return
    }

    // 验证所有必填字段
    for (let i = 0; i < mappings.length; i++) {
      const mapping = mappings[i]
      if (!mapping.name?.trim()) {
        this.$message.error(this.$t('downloader.pathMapping.msg.rowNameRequired', { index: i + 1 }).toString())
        return
      }
      if (!mapping.internal?.trim()) {
        this.$message.error(this.$t('downloader.pathMapping.msg.rowInternalRequired', { index: i + 1 }).toString())
        return
      }
      if (!mapping.external?.trim()) {
        this.$message.error(this.$t('downloader.pathMapping.msg.rowExternalRequired', { index: i + 1 }).toString())
        return
      }
    }

    this.testing = true
    this.testResult = null

    try {
      const formData = this.getFormData()
      if (!formData) {
        this.$message.error(this.$t('downloader.pathMapping.msg.invalidData').toString())
        return
      }

      const response = await testPathMapping(downloader.id, formData)

      // 检查组件是否已销毁
      if (this.isComponentDestroyed) {
        return
      }

      if (response.code === '200') {
        this.testResult = response.data
        if (this.testResult.valid) {
          this.$message.success(this.$t('downloader.pathMapping.msg.testSuccess').toString())
        } else {
          this.$message.warning(this.$t('downloader.pathMapping.msg.testFailed').toString())
        }
      } else {
        this.$message.error(apiResponseMessage(response, this.$t('downloader.pathMapping.msg.testError')))
      }
    } catch (error: unknown) {
      // 再次检查组件状态
      if (this.isComponentDestroyed) {
        return
      }
      console.error('测试路径映射失败:', error)
      const apiError = error as ApiErrorLike
      this.$message.error(apiErrorMessage(apiError, this.$t('downloader.pathMapping.msg.testError')))
    } finally {
      // 安全地更新状态
      if (!this.isComponentDestroyed) {
        this.testing = false
      }
    }
  }

  // 根据路径映射规则自动生成外部路径
  private generateExternalFromRules(internalPath: string): string | null {
    const rulesText = this.pathMappingRules !== undefined
      ? this.pathMappingRules
      : this.downloader?.path_mapping_rules
    return generateExternalPathFromRules(internalPath, rulesText)
  }

  // 获取表单数据（供父组件调用）
  public getFormData(): PathMappingConfig | null {
    // ✨ 保存时自动生成：遍历所有映射，为空的 external 字段自动生成
    const processedMappings = this.mappings.map(mapping => {
      // 如果 external 为空，尝试根据规则生成
      if (!mapping.external?.trim() && mapping.internal?.trim()) {
        const generatedExternal = this.generateExternalFromRules(mapping.internal.trim())

        if (generatedExternal) {
          // 生成成功，填充 external 字段
          return {
            ...mapping,
            external: generatedExternal
          }
        } else {
          // 生成失败，保持 external 为空
          // 用户需要手动填写，或保存时会有错误提示
          return mapping
        }
      }

      return mapping
    })

    // 验证必填字段
    for (let i = 0; i < processedMappings.length; i++) {
      const mapping = processedMappings[i]
      if (!mapping.name?.trim() || !mapping.internal?.trim()) {
        this.$message.error(this.$t('downloader.pathMapping.msg.rowNameAndInternalRequired', { index: i + 1 }).toString())
        return null
      }

      // 检查是否为自动发现的路径
      const isAutoDiscovered = mapping.description?.includes(this.$t('downloader.pathMapping.autoDiscovered').toString())

      // 自动发现的路径允许 external 为空，但需要提示
      if (!mapping.external?.trim()) {
        if (isAutoDiscovered) {
          this.$message.warning({
            message: this.$t('downloader.pathMapping.msg.rowAutoDiscovered', { index: i + 1, name: mapping.name }).toString(),
            duration: 5000
          })
          return null
        } else {
          this.$message.error(this.$t('downloader.pathMapping.msg.rowExternalRequiredManual', { index: i + 1 }).toString())
          return null
        }
      }
    }

    if (processedMappings.length === 0) {
      // 空配置也是有效的
      return {
        mappings: [],
        default_mapping: undefined
      }
    }

    // 自动设置 default_mapping 为第一个映射的 name
    const config: PathMappingConfig = {
      mappings: processedMappings,
      default_mapping: processedMappings[0]?.name?.trim() || undefined
    }

    return config
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.path-mapping-tab {
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: 0;
  text-align: left;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.header-icon {
  width: 32px;
  height: 32px;
  color: var(--color-primary);
  flex-shrink: 0;
}

.header-text {
  flex: 1;
}

.header-title {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 4px 0;
}

.header-desc {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin: 0;
}

.button-icon {
  display: inline;
  vertical-align: middle;
  margin-right: 6px;
  width: 16px;
  height: 16px;
}

.header-actions {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
}

.mapping-table-wrapper {
  margin-bottom: var(--spacing-lg);
}

// 表头整行渐变背景（修复：应用在tr元素而非单个th上）
::v-deep .mapping-table-header {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));

  th {
    background: transparent;
    font-weight: var(--font-weight-semibold);
    color: white;
  }
}

.mapping-type-option {
  display: flex;
  flex-direction: column;

  .option-label {
    font-size: 14px;
    font-weight: var(--font-weight-medium);
    color: var(--color-text-primary);
  }

  .option-desc {
    font-size: 12px;
    color: var(--color-text-tertiary);
    margin-top: 2px;
  }
}

.input-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-tertiary);
  // 图标垂直居中对齐
  vertical-align: middle;
}

// 输入框前缀容器位置调整，与表头对齐
::v-deep .el-input__prefix {
  left: 8px;
  // 前缀容器垂直居中对齐
  display: inline-flex;
  align-items: center;
  height: 100%;
}

// 输入框文字padding调整，确保与图标、表头对齐
::v-deep .el-input--prefix .el-input__inner {
  padding-left: 32px;
}

// 表头单元格左padding调整，与输入框对齐
::v-deep .mapping-table-header th {
  padding-left: 8px !important;
}

// Table header border radius
::v-deep .el-table th {
  &:first-child {
    border-top-left-radius: 12px;
  }

  &:last-child {
    border-top-right-radius: 12px;
  }
}

// 普通表格单元格左padding调整，与输入框对齐
::v-deep .el-table td {
  padding-left: 8px !important;
}

// 映射名称单元格样式
.mapping-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;

  .el-input {
    flex: 1;
  }
}

// 自动发现标记图标
.auto-discovered-icon {
  width: 16px;
  height: 16px;
  color: var(--color-warning);
  flex-shrink: 0;
  cursor: help;
}

.empty-state {
  padding: var(--spacing-xxl) 0;
  text-align: center;
}

.empty-icon {
  width: 64px;
  height: 64px;
  color: var(--color-border-primary);
  margin-bottom: var(--spacing-md);
}

.empty-text {
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
}

.empty-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 0;
}

.test-section {
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
}

.test-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}

.test-title {
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.test-result {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: 13px;

  &.success {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  &.error {
    background: var(--color-error-light);
    color: var(--color-error);
  }
}

.result-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 2px;
}

.result-message {
  flex: 1;
  font-weight: var(--font-weight-medium);
}

.error-details {
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid currentColor;
  opacity: 0.9;

  strong {
    font-weight: var(--font-weight-semibold);
  }

  ul {
    margin: var(--spacing-xs) 0 0 0;
    padding-left: 20px;

    li {
      margin: 4px 0;
    }
  }
}

.tab-header {
  margin-bottom: 9px;
  padding: 10px 12px;
  border-color: var(--color-border-secondary);
  border-radius: 11px;
  background:
    linear-gradient(110deg, rgba(var(--color-primary-rgb), 0.075), transparent 42%),
    rgba(255, 255, 255, 0.66);
}

.header-info {
  min-width: 0;
  gap: 9px;
}

.header-icon {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--color-primary-rgb), 0.2);
  border-radius: 9px;
  background: rgba(var(--color-primary-rgb), 0.07);
}

.header-title {
  margin-bottom: 2px;
  font-size: 12px;
  letter-spacing: 0.03em;
}

.header-desc {
  overflow: hidden;
  max-width: 680px;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-actions {
  gap: 6px;
}

.header-actions ::v-deep .el-button,
.test-header ::v-deep .el-button {
  height: 30px;
  padding: 0 10px;
  font-size: 9px;
}

.header-actions ::v-deep .el-button span,
.test-header ::v-deep .el-button span,
::v-deep .el-table .el-button span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.button-icon {
  margin-right: 0;
}

.mapping-table-wrapper {
  overflow: hidden;
  margin-bottom: 9px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 11px;
}

::v-deep .mapping-table-header {
  background: var(--color-bg-tertiary);

  th {
    height: 31px;
    color: var(--color-text-secondary);
    font-size: 9px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
}

::v-deep .el-table td {
  height: 42px;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}

::v-deep .el-table .cell {
  font-size: 10px;
}

.test-section {
  padding: 9px 11px;
  border-color: var(--color-border-secondary);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.62);
}

.test-header {
  min-height: 30px;
  margin: 0;
}

.test-title {
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.test-result {
  margin-top: 7px;
  padding: 8px 9px;
  font-size: 9px;
}

.empty-state {
  padding: 38px 0;
}

.empty-icon {
  width: 40px;
  height: 40px;
  margin-bottom: 9px;
}

.empty-text {
  font-size: 11px;
}

.empty-hint {
  font-size: 9px;
}

.is-spinning {
  animation: path-control-spin 0.8s linear infinite;
}

@keyframes path-control-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 780px) {
  /* Element 表格自带横向滚动；手机下增大单元格行高与字号提升可读性 */
  ::v-deep .el-table .cell {
    font-size: 12px;
    line-height: 1.5;
  }

  ::v-deep .el-table .el-button--mini {
    min-height: 30px;
    padding: 5px 8px;
  }

  .tab-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
    /* 与上方描述文案拉开间距（2026-09-12 用户反馈：按钮贴着描述） */
    margin-top: 12px;

    /* 触控友好（2026-09-12 用户反馈）：压过全局紧凑重制的 30px/9px 小按钮 */
    ::v-deep .el-button {
      flex: 1;
      min-height: 40px;
      margin-left: 0;
      padding: 0 10px;
      font-size: 13px;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .is-spinning {
    animation: none;
  }
}
</style>
