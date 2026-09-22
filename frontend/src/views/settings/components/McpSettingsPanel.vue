<template>
  <div class="mcp-settings-panel">
    <div class="mcp-card">
      <h3 class="mcp-card-title">{{ $t('mcp.panel.title') }}</h3>
      <p class="mcp-description">
        {{ $t('mcp.panel.description') }}
      </p>

      <div v-if="loading" class="mcp-hint">{{ $t('mcp.panel.loading') }}</div>
      <div v-else-if="!loaded" class="mcp-hint">
        {{ $t('mcp.panel.loadFailed') }}
        <el-button size="mini" @click="load">{{ $t('mcp.panel.retry') }}</el-button>
      </div>

      <template v-else>
        <!-- 环境紧急开关：只读提示，UI 不可覆盖（§4.2） -->
        <el-alert
          v-if="forceDisabled"
          type="warning"
          :closable="false"
          show-icon
          class="mcp-alert"
          :title="$t('mcp.panel.forceDisabledTitle')"
          :description="$t('mcp.panel.forceDisabledDesc')"
        />

        <div class="mcp-global-row">
          <span class="mcp-global-label">{{ $t('mcp.panel.globalSwitch') }}</span>
          <el-switch v-model="draftEnabled" />
          <span class="mcp-global-state">{{ draftEnabled ? $t('mcp.panel.stateOn') : $t('mcp.panel.stateOff') }}</span>
          <span v-if="forceDisabled" class="mcp-muted">{{ $t('mcp.panel.forceEffectiveOff') }}</span>
        </div>
        <p class="mcp-description">
          {{ $t('mcp.panel.capabilityHint') }}
        </p>

        <div class="mcp-capability-list">
          <div v-for="cap in catalog" :key="cap.code" class="mcp-capability">
            <div class="mcp-capability-main">
              <el-switch v-model="draftCapabilities[cap.code]" />
              <span class="mcp-capability-name">{{ cap.tool }}</span>
              <el-tag :type="riskTagType(cap.risk)" size="mini" :effect="cap.risk === 'read' ? 'light' : 'plain'">
                {{ riskLabel(cap.risk) }}
              </el-tag>
            </div>
            <div class="mcp-capability-desc">{{ cap.description }}</div>
            <div v-if="cap.risk !== 'read'" class="mcp-capability-note">{{ riskNote(cap.risk) }}</div>
          </div>
        </div>

        <div class="mcp-actions">
          <span v-if="lastUpdatedText" class="mcp-updated">{{ lastUpdatedText }}</span>
          <el-button size="small" @click="resetDraft" :disabled="!dirty || saving">{{ $t('mcp.panel.discard') }}</el-button>
          <el-button type="primary" size="small" :loading="saving" :disabled="!dirty" @click="save">
            {{ $t('mcp.panel.save') }}
          </el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  McpCapabilityMeta,
  McpCapabilityRisk,
  McpSettingsData,
  getMcpSettings,
  updateMcpSettings
} from '@/api/mcp-settings'
import { ApiError } from '@/types/api'

/** 能力开关键值对（键为后端目录能力码，全集由 GET catalog 下发） */
type CapabilityDraftMap = Record<string, boolean>

/**
 * MCP 服务设置面板（mcp-service-capabilities W1）。
 *
 * - 能力目录文案/风险分级全部来自后端 GET 下发（单一事实源 contracts.py），
 *   前端不维护能力清单副本；
 * - 保存携带 expectedRevision 做 CAS，409 冲突提示后自动重载最新配置；
 * - kill switch（forceDisabled）只读展示，保存仍允许（保留意图）；
 * - demo 模式经 @/demo 拦截层提供同形数据，无独立分支；
 * - 移动端经 views/mobile/settings.vue 包装桌面设置页自动同源，无独立实现。
 */
@Component({ name: 'McpSettingsPanel' })
export default class extends Vue {
  private loading = false
  private saving = false
  private loaded = false

  // 已保存态（服务端真相，dirty 比对基准）
  private settingsEnabled = false
  private settingsCapabilities: CapabilityDraftMap = {}
  private revision = 0
  private forceDisabled = false
  private updatedAt: string | null = null
  private updatedBy: string | null = null
  private catalog: McpCapabilityMeta[] = []

  // 草稿态（v-model 绑定）
  private draftEnabled = false
  private draftCapabilities: CapabilityDraftMap = {}

  get dirty(): boolean {
    if (!this.loaded) return false
    if (this.draftEnabled !== this.settingsEnabled) return true
    const savedKeys = Object.keys(this.settingsCapabilities)
    const draftKeys = Object.keys(this.draftCapabilities)
    if (savedKeys.length !== draftKeys.length) return true
    return savedKeys.some(key => this.draftCapabilities[key] !== this.settingsCapabilities[key])
  }

  get lastUpdatedText(): string {
    if (!this.updatedAt && !this.updatedBy) {
      return this.loaded ? this.$t('mcp.panel.neverSaved').toString() : ''
    }
    const time = this.updatedAt ? this.updatedAt.slice(0, 19).replace('T', ' ') : ''
    const by = this.updatedBy ? this.$t('mcp.panel.bySuffix', { by: this.updatedBy }).toString() : ''
    return this.$t('mcp.panel.revisionInfo', { revision: this.revision, time, by }).toString()
  }

  mounted(): void {
    this.load()
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getMcpSettings()
      this.applyData(res.data)
    } catch (error) {
      // 失败保持 !loaded 占位（重试按钮），不弹全局错误（请求层已节流提示）
      this.loaded = false
      console.error('加载 MCP 配置失败:', error)
    } finally {
      this.loading = false
    }
  }

  private applyData(data: McpSettingsData): void {
    this.catalog = data.catalog
    this.settingsEnabled = data.settings.enabled
    this.settingsCapabilities = { ...data.settings.capabilities }
    this.revision = data.settings.revision
    this.forceDisabled = data.settings.forceDisabled
    this.updatedAt = data.settings.updatedAt
    this.updatedBy = data.settings.updatedBy
    this.resetDraft()
    this.loaded = true
  }

  private resetDraft(): void {
    this.draftEnabled = this.settingsEnabled
    this.draftCapabilities = { ...this.settingsCapabilities }
  }

  private async save(): Promise<void> {
    if (!this.dirty || this.saving) return
    this.saving = true
    try {
      const res = await updateMcpSettings({
        enabled: this.draftEnabled,
        capabilities: { ...this.draftCapabilities },
        expectedRevision: this.revision
      })
      this.applyData(res.data)
      this.$message.success(this.$t('mcp.msg.saved').toString())
    } catch (error) {
      if (error instanceof ApiError && error.code === '409') {
        this.$message.warning(this.$t('mcp.msg.conflict').toString())
        await this.load()
      } else {
        console.error('保存 MCP 配置失败:', error)
        this.$message.error(this.$t('mcp.msg.saveFailed').toString())
      }
    } finally {
      this.saving = false
    }
  }

  private riskLabel(risk: McpCapabilityRisk): string {
    if (risk === 'high') return this.$t('mcp.risk.high').toString()
    if (risk === 'write') return this.$t('mcp.risk.write').toString()
    return this.$t('mcp.risk.read').toString()
  }

  private riskTagType(risk: McpCapabilityRisk): string {
    if (risk === 'high') return 'danger'
    if (risk === 'write') return 'warning'
    return 'success'
  }

  private riskNote(risk: McpCapabilityRisk): string {
    if (risk === 'high') {
      return this.$t('mcp.risk.noteHigh').toString()
    }
    return this.$t('mcp.risk.noteWrite').toString()
  }
}
</script>

<style lang="scss" scoped>
.mcp-settings-panel {
  width: 100%;
}

.mcp-card {
  width: 100%;
  max-width: 600px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-md);
}

.mcp-card-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
}

.mcp-description {
  color: var(--color-text-secondary, #909399);
  font-size: 13px;
  line-height: 1.6;
  margin: var(--spacing-sm) 0 var(--spacing-md);
}

.mcp-hint {
  color: var(--color-text-secondary, #909399);
  padding: 12px 0;
}

.mcp-alert {
  margin-bottom: var(--spacing-md);
}

.mcp-global-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}

.mcp-global-label {
  font-weight: 600;
}

.mcp-global-state {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
}

.mcp-muted {
  font-size: 13px;
  color: var(--el-color-warning, #e6a23c);
}

.mcp-capability-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: var(--spacing-sm) 0 var(--spacing-md);
}

.mcp-capability {
  border: 1px solid var(--color-border-primary, #ebeef5);
  border-radius: 6px;
  padding: 10px 12px;
}

.mcp-capability-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mcp-capability-name {
  font-size: 13px;
  font-weight: 600;
}

.mcp-capability-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
  margin-top: 6px;
  line-height: 1.5;
}

.mcp-capability-note {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin-top: 4px;
  line-height: 1.5;
}

.mcp-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: var(--spacing-md);
}

.mcp-updated {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin-right: auto;
}
</style>
