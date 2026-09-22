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
            <div class="mcp-capability-desc">{{ capDescription(cap) }}</div>
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

    <!-- W5 服务密钥卡：独立加载态（设置加载失败不影响密钥查看/生成） -->
    <div class="mcp-card mcp-apikey-card">
      <h3 class="mcp-card-title">{{ $t('mcp.apikey.title') }}</h3>
      <p class="mcp-description">
        {{ $t('mcp.apikey.description') }}
      </p>

      <div v-if="apikeyLoading" class="mcp-hint">{{ $t('mcp.apikey.loading') }}</div>
      <div v-else-if="!apikeyLoaded" class="mcp-hint">
        {{ $t('mcp.panel.loadFailed') }}
        <el-button size="mini" @click="loadApiKey">{{ $t('mcp.panel.retry') }}</el-button>
      </div>

      <template v-else-if="apikeyView">
        <div class="mcp-apikey-meta-row">
          <span class="mcp-apikey-label">{{ $t('mcp.apikey.endpointLabel') }}</span>
          <code class="mcp-apikey-value">{{ endpointHint }}</code>
        </div>
        <div class="mcp-apikey-meta-row">
          <span class="mcp-apikey-label">{{ $t('mcp.apikey.authLabel') }}</span>
          <span class="mcp-apikey-value">{{ $t('mcp.apikey.authHint') }}</span>
        </div>

        <div v-if="apikeyView.status === 'absent'" class="mcp-hint">
          {{ $t('mcp.apikey.statusAbsent') }}
        </div>
        <div v-else-if="apikeyView.status === 'unreadable'" class="mcp-hint mcp-apikey-warn">
          {{ $t('mcp.apikey.statusUnreadable') }}
        </div>
        <template v-else>
          <div class="mcp-apikey-row">
            <el-input
              :value="apikeyView.key"
              type="password"
              show-password
              readonly
              class="mcp-apikey-input"
            />
            <el-button size="small" @click="copyKey">{{ $t('mcp.apikey.copy') }}</el-button>
          </div>
          <div class="mcp-apikey-times">
            <span v-if="apikeyView.createdAt">
              {{ $t('mcp.apikey.createdInfo', {time: formatApiKeyTime(apikeyView.createdAt), by: apikeyView.createdBy || ''}) }}
            </span>
            <span v-if="apikeyView.updatedAt" class="mcp-apikey-times-second">
              {{ $t('mcp.apikey.updatedInfo', {time: formatApiKeyTime(apikeyView.updatedAt), by: apikeyView.updatedBy || ''}) }}
            </span>
          </div>
        </template>

        <p class="mcp-description mcp-apikey-note">{{ $t('mcp.apikey.securityNote') }}</p>

        <div class="mcp-actions">
          <el-button
            type="danger"
            size="small"
            :loading="apikeyRotating"
            @click="confirmRotate"
          >
            {{ apikeyView.status === 'absent' ? $t('mcp.apikey.generate') : $t('mcp.apikey.rotate') }}
          </el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { getLocale } from '@/i18n'
import { copyTextToClipboard } from '@/utils/clipboard'
import {
  McpApiKeyView,
  McpCapabilityMeta,
  McpCapabilityRisk,
  McpSettingsData,
  getMcpApiKey,
  getMcpSettings,
  rotateMcpApiKey,
  updateMcpSettings
} from '@/api/mcp-settings'
import { ApiError } from '@/types/api'

/** 能力开关键值对（键为后端目录能力码，全集由 GET catalog 下发） */
type CapabilityDraftMap = Record<string, boolean>

/**
 * MCP 服务设置面板（mcp-service-capabilities W1；W5 增服务密钥卡）。
 *
 * - 能力目录文案/风险分级全部来自后端 GET 下发（单一事实源 contracts.py），
 *   前端不维护能力清单副本；描述按 locale 在 description/descriptionEn 间选取
 *   （W5 双语化，与高级搜索契约 labelEn 同模式）；
 * - 保存携带 expectedRevision 做 CAS，409 冲突提示后自动重载最新配置；
 * - kill switch（forceDisabled）只读展示，保存仍允许（保留意图）；
 * - 服务密钥卡独立加载：查看（GET，active 才返回明文）/ 生成 / 刷新（rotate，
 *   CAS 冲突 409 后重载）；明文仅存组件内存，不落 localStorage/Vuex；
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

  // 服务密钥态（W5；明文仅在组件内存，刷新页面后需重新查看）
  private apikeyLoading = false
  private apikeyLoaded = false
  private apikeyRotating = false
  private apikeyView: McpApiKeyView | null = null

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

  /** 客户端对接端点提示（当前部署 origin + /mcp/，Streamable HTTP） */
  get endpointHint(): string {
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    return this.$t('mcp.apikey.endpointHint', { origin }).toString()
  }

  mounted(): void {
    this.load()
    this.loadApiKey()
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

  /** 能力描述按 locale 选取（W5：后端成对下发 description/descriptionEn） */
  private capDescription(cap: McpCapabilityMeta): string {
    return getLocale() === 'en' ? cap.descriptionEn || cap.description : cap.description
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

  // ------------------------------------------------------------------ 服务密钥（W5）

  private async loadApiKey(): Promise<void> {
    this.apikeyLoading = true
    try {
      const res = await getMcpApiKey()
      this.apikeyView = res.data
      this.apikeyLoaded = true
    } catch (error) {
      // 失败保持 !apikeyLoaded 占位（重试按钮），不弹全局错误（请求层已节流提示）
      this.apikeyLoaded = false
      console.error('加载 MCP 服务密钥失败:', error)
    } finally {
      this.apikeyLoading = false
    }
  }

  private formatApiKeyTime(value: string): string {
    return value.slice(0, 19).replace('T', ' ')
  }

  private async copyKey(): Promise<void> {
    const key = this.apikeyView?.key
    if (!key) return
    try {
      await copyTextToClipboard(key)
      this.$message.success(this.$t('mcp.apikey.copied').toString())
    } catch (error) {
      console.error('复制 MCP 服务密钥失败:', error)
      this.$message.error(this.$t('mcp.apikey.copyFailed').toString())
    }
  }

  /** 生成（absent）/ 刷新（active·unreadable）前的危险确认 */
  private confirmRotate(): void {
    const generating = this.apikeyView?.status === 'absent'
    const title = generating ? this.$t('mcp.apikey.confirmGenerateTitle') : this.$t('mcp.apikey.confirmRotateTitle')
    const message = generating ? this.$t('mcp.apikey.confirmGenerateMessage') : this.$t('mcp.apikey.confirmRotateMessage')
    this.$confirm(message.toString(), title.toString(), {
      confirmButtonText: generating ? this.$t('mcp.apikey.generate').toString() : this.$t('mcp.apikey.rotate').toString(),
      cancelButtonText: this.$t('common.cancel').toString(),
      type: 'warning'
    })
      .then(async() => {
        await this.rotateApiKey()
      })
      .catch(() => undefined) // 用户取消：MessageBox 以 'cancel' 拒绝，无需处理
  }

  private async rotateApiKey(): Promise<void> {
    if (this.apikeyRotating || !this.apikeyView) return
    const generating = this.apikeyView.status === 'absent'
    this.apikeyRotating = true
    try {
      const res = await rotateMcpApiKey(this.apikeyView.revision)
      this.apikeyView = res.data
      this.$message.success(this.$t(generating ? 'mcp.msg.generated' : 'mcp.msg.rotated').toString())
    } catch (error) {
      if (error instanceof ApiError && error.code === '409') {
        this.$message.warning(this.$t('mcp.msg.apikeyConflict').toString())
        await this.loadApiKey()
      } else {
        console.error('刷新 MCP 服务密钥失败:', error)
        this.$message.error(this.$t('mcp.msg.rotateFailed').toString())
      }
    } finally {
      this.apikeyRotating = false
    }
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

.mcp-apikey-card {
  margin-top: var(--spacing-lg);
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

.mcp-apikey-warn {
  color: var(--el-color-warning, #e6a23c);
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

.mcp-apikey-meta-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
  padding: 2px 0;
}

.mcp-apikey-label {
  font-weight: 600;
  white-space: nowrap;
}

.mcp-apikey-value {
  color: var(--color-text-secondary, #909399);
  word-break: break-all;
}

.mcp-apikey-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: var(--spacing-sm);
}

.mcp-apikey-input {
  flex: 1;
  min-width: 0;
}

.mcp-apikey-times {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin-top: 6px;
  line-height: 1.6;
}

.mcp-apikey-times-second {
  margin-left: 12px;
}

.mcp-apikey-note {
  margin-bottom: 0;
}
</style>
