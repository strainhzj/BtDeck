<template>
  <div class="path-mapping-tab">
    <!-- 头部说明和操作区 -->
    <div class="tab-header">
      <div class="header-info">
        <span class="header-icon"><LucideIcon name="route" :size="18" /></span>
        <div class="header-text">
          <h3 class="header-title">路径映射配置</h3>
          <p class="header-desc">配置下载器内部路径到主机实际路径的映射关系，适用于 Docker、NAS 等场景</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button type="success" size="medium" :disabled="refreshing" @click="handleRefresh">
          <LucideIcon class="button-icon" name="refresh-cw" :size="14" :class="{'is-spinning': refreshing}" />
          刷新配置
        </el-button>
        <el-button type="primary" size="medium" @click="handleAddMapping">
          <LucideIcon class="button-icon" name="plus" :size="14" />
          添加映射
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
        <el-table-column label="映射名称" min-width="150">
          <template #default="{row, $index}">
            <div class="mapping-name-cell">
              <el-input
                v-model="row.name"
                placeholder="输入映射名称"
                size="small"
                @blur="validateMappingName($index)"
              >
                <template slot="prefix">
                  <LucideIcon class="input-icon" name="tag" :size="13" />
                </template>
              </el-input>
              <!-- 自动发现标记 -->
              <el-tooltip
                v-if="row.description?.includes('系统自动发现')"
                content="系统自动发现的路径，请补充外部路径配置"
                placement="top"
              >
                <LucideIcon class="auto-discovered-icon" name="info" :size="14" />
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <!-- 映射类型 -->
        <el-table-column label="映射类型" min-width="130">
          <template #default="{row}">
            <el-select v-model="row.mapping_type" placeholder="选择类型" size="small">
              <el-option
                v-for="option in mappingTypeOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              >
                <div class="mapping-type-option">
                  <span class="option-label">{{ option.label }}</span>
                  <span class="option-desc">{{ option.description }}</span>
                </div>
              </el-option>
            </el-select>
          </template>
        </el-table-column>

        <!-- 内部路径 -->
        <el-table-column label="内部路径" min-width="220">
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
        <el-table-column label="外部路径" min-width="220">
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
        <el-table-column label="描述" min-width="180">
          <template #default="{row}">
            <el-input
              v-model="row.description"
              placeholder="可选，添加备注说明"
              size="small"
            />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{$index}">
            <el-button
              type="danger"
              size="mini"
              @click="handleDeleteMapping($index)"
            >
              <LucideIcon name="trash-2" :size="13" />
              删除
            </el-button>
          </template>
        </el-table-column>

        <!-- 空状态 -->
        <template #empty>
          <div class="empty-state">
            <LucideIcon class="empty-icon" name="route" :size="40" :stroke-width="1.35" />
            <p class="empty-text">暂无路径映射配置</p>
            <p class="empty-hint">点击上方"添加映射"按钮创建配置</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 测试区域 -->
    <div class="test-section">
      <div class="test-header">
        <h4 class="test-title">配置验证</h4>
        <el-button
          type="success"
          size="small"
          :disabled="mappings.length === 0 || testing"
          @click="handleTestConfig"
        >
          <LucideIcon class="button-icon" name="test-tube-2" :size="14" :class="{'is-spinning': testing}" />
          测试配置
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
          <strong>错误详情：</strong>
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
import { testPathMapping } from '@/api/downloader'

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

  // 路径映射列表
  private mappings: PathMappingItem[] = []

  // 测试状态
  private testing = false
  private testResult: PathMappingTestResponse | null = null

  // 刷新状态
  private refreshing = false

  // 映射类型选项
  private mappingTypeOptions: MappingTypeOption[] = [
    {
      value: 'local',
      label: '本地路径',
      description: '同一主机路径映射',
      placeholder: '如: D:/Downloads/ 或 /mnt/data/'
    },
    {
      value: 'docker',
      label: 'Docker容器',
      description: 'Docker容器内外路径映射',
      placeholder: '主机挂载路径，如: D:/DockerData/Downloads/'
    },
    {
      value: 'nas',
      label: 'NAS存储',
      description: 'NAS网络存储映射',
      placeholder: 'NAS实际路径，如: //192.168.1.100/volume1/'
    },
    {
      value: 'wsl',
      label: 'WSL',
      description: 'Windows Subsystem for Linux',
      placeholder: 'Windows路径，如: C:\\Downloads\\'
    },
    {
      value: 'network',
      label: '网络路径',
      description: 'SMB/NFS等网络共享',
      placeholder: '建议使用 // 开头，如：//192.168.5.51/pt2/'
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
      this.$message.error('下载器信息不存在')
      return
    }

    // 提示用户确认
    try {
      await this.$confirm(
        '当前编辑内容将丢失，确认重新加载路径映射配置？',
        '刷新确认',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
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

        this.$message.success('配置刷新成功')
      } else {
        this.$message.error(response.msg || '刷新失败')
      }
    } catch (error: unknown) {
      // 再次检查组件状态
      if (this.isComponentDestroyed) {
        return
      }
      console.error('刷新路径映射配置失败:', error)
      const apiError = error as ApiErrorLike
      this.$message.error(apiError.response?.data?.msg || apiError.message || '刷新失败')
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
    return option?.placeholder || '输入路径'
  }

  // 获取路径格式提示
  private getPathHint(mappingType: MappingType, pathType: 'internal' | 'external'): string {
    const hints: Record<MappingType, { internal: string, external: string }> = {
      local: {
        internal: '下载器内路径，如: /downloads/',
        external: '主机实际路径，如: D:/Downloads/'
      },
      docker: {
        internal: '容器内路径，如: /downloads/torrents/',
        external: '主机挂载路径，如: D:/DockerData/Downloads/'
      },
      nas: {
        internal: '下载器访问路径，如: /mnt/nas/downloads/',
        external: 'NAS实际路径，如: /volume1/downloads/'
      },
      wsl: {
        internal: 'WSL内路径，如: /mnt/c/downloads/',
        external: 'Windows路径，如: C:\\Downloads\\'
      },
      network: {
        internal: '本地挂载点，如: /mnt/network-share/',
        external: '网络共享地址，如: //192.168.1.100/downloads/'
      }
    }
    return hints[mappingType]?.[pathType] || ''
  }

  // 添加映射
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
    this.$confirm('确认删除此路径映射配置吗？', '删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      this.mappings.splice(index, 1)
      this.$message.success('删除成功')
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
      this.$message.warning('映射名称不能为空')
      return false
    }

    // 检查名称唯一性
    const duplicateCount = this.mappings.filter(
      (m, i) => i !== index && m.name === mapping.name
    ).length

    if (duplicateCount > 0) {
      this.$message.error('映射名称已存在，请使用不同的名称')
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
      this.$message.warning('内部路径不能为空')
      return false
    }

    // 路径格式基本验证
    const path = mapping.internal.trim()
    if (!path.startsWith('/') && !path.startsWith('//')) {
      this.$message.warning('路径格式不正确，应以 / 或 // 开头')
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
      this.$message.warning('外部路径不能为空')
      return false
    }

    // 路径格式基本验证
    const path = mapping.external.trim()
    const isValid = path.startsWith('/') || path.startsWith('//') ||
                   /^[A-Za-z]:/.test(path) || path.startsWith('\\')

    if (!isValid) {
      this.$message.warning('外部路径格式不正确')
      return false
    }

    return true
  }

  // 测试配置
  private async handleTestConfig() {
    // 在第一个 await 前保存快照
    const downloader = this.downloader
    const mappings = [...this.mappings]

    if (!downloader) {
      this.$message.error('下载器信息不存在')
      return
    }

    // 验证所有必填字段
    for (let i = 0; i < mappings.length; i++) {
      const mapping = mappings[i]
      if (!mapping.name?.trim()) {
        this.$message.error(`第 ${i + 1} 行：映射名称不能为空`)
        return
      }
      if (!mapping.internal?.trim()) {
        this.$message.error(`第 ${i + 1} 行：内部路径不能为空`)
        return
      }
      if (!mapping.external?.trim()) {
        this.$message.error(`第 ${i + 1} 行：外部路径不能为空`)
        return
      }
    }

    this.testing = true
    this.testResult = null

    try {
      const formData = this.getFormData()
      if (!formData) {
        this.$message.error('配置数据无效')
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
          this.$message.success('配置验证通过')
        } else {
          this.$message.warning('配置验证失败，请查看错误详情')
        }
      } else {
        this.$message.error(response.msg || '测试失败')
      }
    } catch (error: unknown) {
      // 再次检查组件状态
      if (this.isComponentDestroyed) {
        return
      }
      console.error('测试路径映射失败:', error)
      const apiError = error as ApiErrorLike
      this.$message.error(apiError.response?.data?.msg || apiError.message || '测试失败')
    } finally {
      // 安全地更新状态
      if (!this.isComponentDestroyed) {
        this.testing = false
      }
    }
  }

  // 根据路径映射规则自动生成外部路径
  private generateExternalFromRules(internalPath: string): string | null {
    // 如果 downloader 对象不存在，无法生成
    if (!this.downloader || !this.downloader.path_mapping_rules) {
      return null
    }

    const rulesText = this.downloader.path_mapping_rules.trim()
    if (!rulesText) {
      return null
    }

    // 解析规则（格式：/Downloads/ipan/{#**#}//192.168.5.51/pt1/）
    const rules = rulesText.split('\n').filter(line => line.trim())

    // 按规则长度降序排序（最长的规则优先匹配）
    rules.sort((a, b) => b.length - a.length)

    for (const rule of rules) {
      const separator = '{#**#}'
      if (!rule.includes(separator)) {
        continue
      }

      const [source, target] = rule.split(separator)
      if (!source || !target) {
        continue
      }

      const normalizedSource = source.trim()
      const normalizedTarget = target.trim()

      // 前缀匹配
      if (internalPath.startsWith(normalizedSource)) {
        // 替换前缀
        const relativePath = internalPath.substring(normalizedSource.length)
        return normalizedTarget + relativePath
      }
    }

    // 没有找到匹配规则
    return null
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
        this.$message.error(`第 ${i + 1} 行：映射名称和内部路径不能为空`)
        return null
      }

      // 检查是否为自动发现的路径
      const isAutoDiscovered = mapping.description?.includes('系统自动发现')

      // 自动发现的路径允许 external 为空，但需要提示
      if (!mapping.external?.trim()) {
        if (isAutoDiscovered) {
          this.$message.warning({
            message: `第 ${i + 1} 行（${mapping.name}）为自动发现的路径，外部路径为空。请补充外部路径配置后再保存。`,
            duration: 5000
          })
          return null
        } else {
          this.$message.error(`第 ${i + 1} 行：外部路径不能为空（无法根据 path_mapping_rules 自动生成，请手动填写）`)
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
  padding: var(--spacing-lg);
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
  .tab-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;

    .el-button {
      flex: 1;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .is-spinning {
    animation: none;
  }
}
</style>
