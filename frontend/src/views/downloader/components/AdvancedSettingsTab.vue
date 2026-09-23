<template>
  <!--
    【已废弃】高级设置页签组件已废弃
    原因: qBittorrent客户端支持不完整，部分字段无法生效
    处理: 在父组件DownloaderSettingsDialog中使用v-if="false"隐藏
    未来: 可能完全移除此组件
  -->
  <div class="advanced-settings-tab">
    <!-- {{ $t('downloader.advanced.qbSection') }} -->
    <div class="form-section">
      <div class="form-section-title">
        {{ $t('downloader.advanced.qbSection') }}
        <span v-if="downloaderType === 0" class="capability-badge supported">
          <LucideIcon name="check" :size="13" />
          {{ $t('downloader.advanced.supported') }}
        </span>
      </div>

      <div v-if="downloaderType === 0" class="settings-grid">
        <div v-for="field in qbittorrentFields" :key="field.key" class="setting-field">
          <label class="field-label">{{ $t(field.labelKey) }}</label>
          <el-input-number
            v-model="formData[field.key]"
            :min="field.min"
            :max="field.max"
            controls-position="right"
            style="width: 100%;"
          />
          <p class="field-hint">{{ $t(field.hintKey) }}</p>
        </div>
      </div>

      <div v-else class="unsupported-hint">
        <LucideIcon name="info" :size="16" />
        <span>{{ $t('downloader.advanced.qbUnavailable') }}</span>
      </div>
    </div>

    <!-- {{ $t('downloader.advanced.trSection') }} -->
    <div class="form-section">
      <div class="form-section-title">
        {{ $t('downloader.advanced.trSection') }}
        <span v-if="downloaderType === 1" class="capability-badge supported">
          <LucideIcon name="check" :size="13" />
          {{ $t('downloader.advanced.supported') }}
        </span>
        <span v-else class="capability-badge unsupported">
          <LucideIcon name="circle-x" :size="13" />
          {{ $t('downloader.advanced.notApplicable') }}
        </span>
      </div>

      <div v-if="downloaderType === 1" class="transmission-settings">
        <el-form label-width="180px">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="$t('downloader.advanced.downloadQueueSize')">
                <el-input-number
                  v-model="formData.download_queue_size"
                  :min="1"
                  :max="1000"
                  controls-position="right"
                  style="width: 100%;"
                />
                <p class="field-hint">{{ $t('downloader.advanced.downloadQueueHint') }}</p>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('downloader.advanced.uploadQueueSize')">
                <el-input-number
                  v-model="formData.seed_queue_size"
                  :min="1"
                  :max="1000"
                  controls-position="right"
                  style="width: 100%;"
                />
                <p class="field-hint">{{ $t('downloader.advanced.uploadQueueHint') }}</p>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </div>

      <div v-else class="unsupported-hint">
        <LucideIcon name="info" :size="16" />
        <span>{{ $t('downloader.advanced.trUnavailable') }}</span>
      </div>
    </div>

    <!-- 其他高级选项 -->
    <div class="form-section">
      <div class="form-section-title">{{ $t('downloader.advanced.otherSection') }}</div>
      <div class="switches-grid">
        <div class="switch-item">
          <span class="switch-label">{{ $t('downloader.advanced.enableDht') }}</span>
          <el-switch
            v-model="formData.dht_enabled"
            active-color="#059669"
            inactive-color="#d1d5db"
          />
        </div>
        <div class="switch-item">
          <span class="switch-label">{{ $t('downloader.advanced.enableLsd') }}</span>
          <el-switch
            v-model="formData.lsd_enabled"
            active-color="#059669"
            inactive-color="#d1d5db"
          />
        </div>
        <div class="switch-item">
          <span class="switch-label">{{ $t('downloader.advanced.enableUtp') }}</span>
          <el-switch
            v-model="formData.utp_enabled"
            active-color="#059669"
            inactive-color="#d1d5db"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * 【已废弃】高级设置页签组件
 *
 * 废弃原因:
 * - qBittorrent客户端对高级设置支持不完整
 * - 部分字段无法正确应用到客户端（如DHT/LSD/uTP等）
 * - 前端UI已在父组件中隐藏（v-if="false"）
 *
 * 当前状态:
 * - 代码保留以避免破坏现有功能
 * - 数据库中的advanced_settings数据保留
 * - 后端API接口保留但标记为废弃
 *
 * 未来计划:
 * - 可能完全移除此组件及相关API
 * - 如需类似功能，请直接在qBittorrent客户端中配置
 */
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { Downloader, DownloaderSettings } from '../types'

@Component({
  name: 'AdvancedSettingsTab'
})
export default class AdvancedSettingsTab extends Vue {
  @Prop({ required: true }) downloader!: Downloader
  @Prop({ required: true }) settings!: DownloaderSettings

  // qBittorrent 字段配置
  private qbittorrentFields = [
    {
      key: 'max_connections',
      labelKey: 'downloader.advanced.fields.globalMaxConnections',
      hintKey: 'downloader.advanced.fields.globalMaxConnectionsHint',
      min: 1,
      max: 10000,
      default: 500
    },
    {
      key: 'max_connections_per_torrent',
      labelKey: 'downloader.advanced.fields.maxConnectionsPerTorrent',
      hintKey: 'downloader.advanced.fields.maxConnectionsPerTorrentHint',
      min: 1,
      max: 1000,
      default: 100
    },
    {
      key: 'max_uploads',
      labelKey: 'downloader.advanced.fields.globalUploadSlots',
      hintKey: 'downloader.advanced.fields.globalUploadSlotsHint',
      min: 1,
      max: 500,
      default: 50
    },
    {
      key: 'max_uploads_per_torrent',
      labelKey: 'downloader.advanced.fields.uploadSlotsPerTorrent',
      hintKey: 'downloader.advanced.fields.uploadSlotsPerTorrentHint',
      min: 1,
      max: 100,
      default: 4
    },
    {
      key: 'max_download_slots',
      labelKey: 'downloader.advanced.fields.downloadQueue',
      hintKey: 'downloader.advanced.fields.downloadQueueHint',
      min: 1,
      max: 100,
      default: 10
    },
    {
      key: 'max_upload_slots',
      labelKey: 'downloader.advanced.fields.uploadQueue',
      hintKey: 'downloader.advanced.fields.uploadQueueHint',
      min: 1,
      max: 500,
      default: 50
    }
  ]

  // 表单数据
  private formData = {
    // qBittorrent
    max_connections: 500,
    max_connections_per_torrent: 100,
    max_uploads: 50,
    max_uploads_per_torrent: 4,
    max_download_slots: 10,
    max_upload_slots: 50,

    // Transmission
    download_queue_size: 10,
    seed_queue_size: 50,

    // 通用
    dht_enabled: false,
    lsd_enabled: false,
    utp_enabled: false
  }

  // 计算属性：下载器类型（三路：2=rTorrent 未知语义不回退 qB/TR）
  get downloaderType(): 0 | 1 | 2 {
    // 优先使用驼峰命名（后端API返回格式），如果不存在则使用蛇形命名（兼容旧数据）
    const type = this.downloader.downloaderType ?? this.downloader.downloader_type
    return (type === 1 || type === 2) ? type : 0  // 非法/缺失值保守归 qBittorrent
  }

  // 监听设置变化
  @Watch('settings', { immediate: true, deep: true })
  onSettingsChange(val: DownloaderSettings) {
    if (val) {
      interface DownloaderSettingsWithAdvanced extends DownloaderSettings {
        advanced_settings?: Record<string, any>
        advancedSettings?: Record<string, any>
      }

      const settings = val as DownloaderSettingsWithAdvanced
      const advancedSettings = settings.advanced_settings || settings.advancedSettings || {}
      const normalizedAdvanced = this.normalizeAdvancedSettings(
        advancedSettings,
        this.downloaderType
      )

      // qBittorrent 设置
      this.formData.max_connections =
        normalizedAdvanced.max_connections ?? (val as any).max_connections ?? 500
      this.formData.max_connections_per_torrent =
        normalizedAdvanced.max_connections_per_torrent ??
        (val as any).max_connections_per_torrent ??
        100
      this.formData.max_uploads =
        normalizedAdvanced.max_uploads ?? (val as any).max_uploads ?? 50
      this.formData.max_uploads_per_torrent =
        normalizedAdvanced.max_uploads_per_torrent ??
        (val as any).max_uploads_per_torrent ??
        4
      this.formData.max_download_slots =
        normalizedAdvanced.max_download_slots ??
        (val as any).max_download_slots ??
        10
      this.formData.max_upload_slots =
        normalizedAdvanced.max_upload_slots ??
        (val as any).max_upload_slots ??
        50

      // Transmission 设置
      this.formData.download_queue_size =
        normalizedAdvanced.download_queue_size ??
        (val as any).download_queue_size ??
        10
      this.formData.seed_queue_size =
        normalizedAdvanced.seed_queue_size ?? (val as any).seed_queue_size ?? 50

      // 通用设置（默认关闭）
      this.formData.dht_enabled =
        normalizedAdvanced.dht_enabled ?? (val as any).dht_enabled ?? false
      this.formData.lsd_enabled =
        normalizedAdvanced.lsd_enabled ?? (val as any).lsd_enabled ?? false
      this.formData.utp_enabled =
        normalizedAdvanced.utp_enabled ?? (val as any).utp_enabled ?? false
    }
  }

  private normalizeAdvancedSettings(
    advancedSettings: Record<string, any>,
    downloaderType: 0 | 1 | 2
  ): Record<string, any> {
    if (!advancedSettings || typeof advancedSettings !== 'object') {
      return {}
    }

    const normalized: Record<string, any> = { ...advancedSettings }

    if (downloaderType === 0) {
      if (advancedSettings.connection_limit !== undefined) {
        normalized.max_connections = advancedSettings.connection_limit
      }
      if (advancedSettings.max_connec_per_torrent !== undefined) {
        normalized.max_connections_per_torrent = advancedSettings.max_connec_per_torrent
      }
      if (advancedSettings.max_active_downloads !== undefined) {
        normalized.max_download_slots = advancedSettings.max_active_downloads
      }
      if (advancedSettings.max_active_uploads !== undefined) {
        normalized.max_upload_slots = advancedSettings.max_active_uploads
      }
    }

    return normalized
  }

  // 获取表单数据（供父组件调用）
  public getFormData(): Partial<DownloaderSettings> {
    const data: Partial<DownloaderSettings> = {
      dht_enabled: this.formData.dht_enabled,
      lsd_enabled: this.formData.lsd_enabled,
      utp_enabled: this.formData.utp_enabled
    }

    if (this.downloaderType === 0) {
      Object.assign(data, {
        max_connections: this.formData.max_connections,
        max_connections_per_torrent: this.formData.max_connections_per_torrent,
        max_uploads: this.formData.max_uploads,
        max_uploads_per_torrent: this.formData.max_uploads_per_torrent,
        max_download_slots: this.formData.max_download_slots,
        max_upload_slots: this.formData.max_upload_slots
      })
    } else if (this.downloaderType === 1) {
      Object.assign(data, {
        download_queue_size: this.formData.download_queue_size,
        seed_queue_size: this.formData.seed_queue_size
      })
    }

    return data
  }

  // 验证表单
  public async validateForm(): Promise<boolean> {
    // 验证数值范围
    if (this.downloaderType === 0) {
      if (this.formData.max_connections < 1 || this.formData.max_connections > 10000) {
        return false
      }
      if (this.formData.max_connections_per_torrent < 1 || this.formData.max_connections_per_torrent > 1000) {
        return false
      }
      if (this.formData.max_uploads < 1 || this.formData.max_uploads > 500) {
        return false
      }
      if (this.formData.max_uploads_per_torrent < 1 || this.formData.max_uploads_per_torrent > 100) {
        return false
      }
      if (this.formData.max_download_slots < 1 || this.formData.max_download_slots > 100) {
        return false
      }
      if (this.formData.max_upload_slots < 1 || this.formData.max_upload_slots > 500) {
        return false
      }
    } else if (this.downloaderType === 1) {
      if (this.formData.download_queue_size < 1 || this.formData.download_queue_size > 1000) {
        return false
      }
      if (this.formData.seed_queue_size < 1 || this.formData.seed_queue_size > 1000) {
        return false
      }
    }

    return true
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.advanced-settings-tab {
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

// 能力标签
.capability-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  margin-left: auto;

  &.supported {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  &.unsupported {
    background: var(--color-warning-light);
    color: #92400E;
  }

  svg {
    width: 12px;
    height: 12px;
  }
}

// qBittorrent 设置网格
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
}

.setting-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.field-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 0;
}

// 不支持提示
.unsupported-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-warning-light);
  border-radius: var(--radius-md);
  color: #92400E;
  font-size: 14px;

  svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }
}

// Transmission 设置
.transmission-settings {
  ::v-deep .el-form-item__label {
    font-size: 14px;
    font-weight: var(--font-weight-medium);
    color: var(--color-text-primary);
  }

  ::v-deep .el-form-item {
    margin-bottom: 0;
  }
}

// 开关网格
.switches-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
}

.switch-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  text-align: center;
}

.switch-label {
  font-size: 13px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: 1.5;
}
</style>
