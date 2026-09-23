<template>
  <div class="mp-panel">
    <!-- 全局开关 -->
    <div class="mp-card">
      <h3 class="mp-card-title">{{ $t('moviepilot.panel.title') }}</h3>
      <p class="mp-description">
        {{ $t('moviepilot.panel.description') }}
      </p>

      <div v-if="loading" class="mp-hint">{{ $t('moviepilot.panel.loading') }}</div>
      <div v-else-if="!loaded" class="mp-hint">
        {{ $t('moviepilot.panel.loadFailed') }}
        <el-button size="mini" @click="loadAll">{{ $t('moviepilot.panel.retry') }}</el-button>
      </div>

      <template v-else>
        <div class="mp-global-row">
          <span class="mp-global-label">{{ $t('moviepilot.panel.globalSwitch') }}</span>
          <el-switch v-model="draftEnabled" />
          <span class="mp-global-state">{{ draftEnabled ? $t('moviepilot.panel.stateOn') : $t('moviepilot.panel.stateOff') }}</span>
        </div>
        <p class="mp-description">
          {{ $t('moviepilot.panel.offHint') }}
        </p>
        <div class="mp-actions">
          <span v-if="lastUpdatedText" class="mp-updated">{{ lastUpdatedText }}</span>
          <el-button size="small" :disabled="!dirty || saving" @click="resetDraft">{{ $t('moviepilot.panel.discard') }}</el-button>
          <el-button type="primary" size="small" :loading="saving" :disabled="!dirty" @click="save">
            {{ $t('moviepilot.panel.save') }}
          </el-button>
        </div>
      </template>
    </div>

    <!-- 实例与下载器映射 -->
    <div v-if="loaded" class="mp-card">
      <div class="mp-card-head">
        <h3 class="mp-card-title">{{ $t('moviepilot.panel.instancesTitle') }}</h3>
        <el-button size="mini" :loading="instancesLoading" @click="loadInstances">{{ $t('moviepilot.panel.refresh') }}</el-button>
      </div>
      <p class="mp-description">
        {{ $t('moviepilot.panel.instancesDesc') }}
      </p>

      <div v-if="instances.length === 0" class="mp-hint">
        {{ $t('moviepilot.panel.noInstance') }}
      </div>

      <div v-for="instance in instances" :key="instance.instanceId" class="mp-instance">
        <div class="mp-instance-head">
          <span class="mp-instance-name">{{ instance.name || instance.instanceId }}</span>
          <el-tag size="mini" :type="instance.enabled ? 'success' : 'info'">
            {{ instance.enabled ? $t('moviepilot.panel.instanceEnabled') : $t('moviepilot.panel.instanceDisabled') }}
          </el-tag>
          <el-switch
            :value="instance.enabled"
            :active-text="$t('moviepilot.panel.allowSync')"
            @change="toggleInstance(instance, $event)"
          />
          <span class="mp-instance-meta">
            {{ instanceSummary(instance) }}
          </span>
          <el-button type="text" size="mini" class="mp-instance-danger" @click="removeInstance(instance)">
            {{ $t('moviepilot.panel.deleteInstance') }}
          </el-button>
        </div>
        <div class="mp-instance-meta mp-instance-ids">
          {{ $t('moviepilot.panel.instanceIds', {instanceId: instance.instanceId, username: instance.boundUsername || '-'}) }}
          <template v-if="instance.moviepilotVersion">{{ ' ' + $t('moviepilot.panel.moviepilotVersionSuffix', {version: instance.moviepilotVersion}) }}</template>
          <template v-if="instance.pluginVersion">{{ ' ' + $t('moviepilot.panel.pluginVersionSuffix', {version: instance.pluginVersion}) }}</template>
        </div>
        <div v-if="instance.lastError" class="mp-instance-error">{{ $t('moviepilot.panel.lastErrorPrefix', {error: instance.lastError}) }}</div>

        <!-- 下载器映射编辑（单实例内联编辑） -->
        <div class="mp-mapping">
          <div class="mp-mapping-head">
            <span class="mp-mapping-title">{{ $t('moviepilot.panel.mapping.title') }}</span>
            <el-button
              v-if="editingInstanceId !== instance.instanceId"
              size="mini"
              @click="startEditMapping(instance)"
            >{{ $t('moviepilot.panel.mapping.edit') }}</el-button>
            <template v-else>
              <el-button size="mini" :disabled="mappingSaving" @click="cancelEditMapping">{{ $t('moviepilot.panel.mapping.cancel') }}</el-button>
              <el-button type="primary" size="mini" :loading="mappingSaving" @click="saveMapping(instance)">
                {{ $t('moviepilot.panel.mapping.save') }}
              </el-button>
            </template>
          </div>

          <template v-if="editingInstanceId === instance.instanceId">
            <div v-for="(row, index) in mappingDraft" :key="index" class="mp-mapping-row">
              <el-input
                v-model="row.mpName"
                size="mini"
                :placeholder="$t('moviepilot.panel.mapping.mpPlaceholder')"
                class="mp-mapping-input"
              />
              <span class="mp-mapping-arrow">→</span>
              <el-select
                v-model="row.btDownloaderId"
                size="mini"
                filterable
                :placeholder="$t('moviepilot.panel.mapping.btPlaceholder')"
                class="mp-mapping-select"
              >
                <el-option
                  v-for="dl in downloaders"
                  :key="dl.downloader_id"
                  :label="dl.nickname || dl.downloader_id"
                  :value="dl.downloader_id"
                />
              </el-select>
              <el-button
                type="text"
                size="mini"
                class="mp-instance-danger"
                @click="removeMappingRow(index)"
              >{{ $t('moviepilot.panel.mapping.remove') }}</el-button>
            </div>
            <el-button size="mini" plain @click="addMappingRow">{{ $t('moviepilot.panel.mapping.add') }}</el-button>
            <p class="mp-description">
              {{ $t('moviepilot.panel.mapping.reparseNotice') }}
            </p>
          </template>

          <template v-else>
            <div v-if="mappingCount(instance) === 0" class="mp-hint">{{ $t('moviepilot.panel.mapping.notConfigured') }}</div>
            <div v-else class="mp-mapping-rows">
              <div v-for="(btId, mpName) in instance.downloaderMapping" :key="mpName" class="mp-mapping-row">
                <span class="mp-mapping-name">{{ mpName }}</span>
                <span class="mp-mapping-arrow">→</span>
                <span class="mp-mapping-name">{{ downloaderLabel(btId) }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 路径反查 -->
    <div v-if="loaded" class="mp-card">
      <h3 class="mp-card-title">{{ $t('moviepilot.reverse.title') }}</h3>
      <p class="mp-description">
        {{ $t('moviepilot.reverse.description') }}
      </p>
      <div class="mp-reverse-form">
        <el-input
          v-model="reversePath"
          size="small"
          :placeholder="$t('moviepilot.reverse.placeholder')"
          class="mp-reverse-input"
          clearable
          @keyup.enter.native="runReverse"
        />
        <el-select v-model="reverseMode" size="small" class="mp-reverse-mode">
          <el-option :label="$t('moviepilot.reverse.modeAll')" value="both" />
          <el-option :label="$t('moviepilot.reverse.modeSrc')" value="src" />
          <el-option :label="$t('moviepilot.reverse.modeDest')" value="dest" />
        </el-select>
        <el-button type="primary" size="small" :loading="reverseLoading" @click="runReverse">{{ $t('moviepilot.reverse.query') }}</el-button>
      </div>

      <div v-if="reverseError" class="mp-instance-error">{{ reverseError }}</div>
      <div v-else-if="reverseLoaded && reverseItems.length === 0" class="mp-hint">{{ $t('moviepilot.reverse.notFound') }}</div>
      <table v-if="reverseItems.length > 0" class="mp-reverse-table">
        <thead>
          <tr>
            <th>{{ $t('moviepilot.reverse.colTitle') }}</th>
            <th style="width: 110px;">{{ $t('moviepilot.reverse.colSeason') }}</th>
            <th style="width: 80px;">{{ $t('moviepilot.reverse.colMode') }}</th>
            <th>{{ $t('moviepilot.reverse.colDest') }}</th>
            <th>{{ $t('moviepilot.reverse.colSrc') }}</th>
            <th style="width: 130px;">{{ $t('moviepilot.reverse.colTask') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in reverseItems" :key="item.id">
            <td>
              <div class="mp-cell-title">{{ item.title || '-' }}</div>
              <div class="mp-cell-sub">{{ item.instanceName || item.instanceId }}</div>
            </td>
            <td>{{ seasonsEpisodesText(item) }}</td>
            <td>{{ transferModeLabel(item.transferMode) }}</td>
            <td>
              <div class="mp-cell-path" :title="item.destPath || '-'">{{ item.destPath || '-' }}</div>
            </td>
            <td>
              <div class="mp-cell-path" :title="item.srcPath || '-'">{{ item.srcPath || '-' }}</div>
            </td>
            <td>
              <el-tag v-if="item.task" size="mini" type="success">{{ item.task.name || item.task.infoId }}</el-tag>
              <el-tag v-else size="mini" :type="item.associationStatus === 'unmapped' ? 'warning' : 'info'">
                {{ associationLabel(item.associationStatus) }}
              </el-tag>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  MoviePilotAssociationItem,
  MoviePilotInstance,
  MoviePilotReverseMode,
  deleteMoviePilotInstance,
  getMoviePilotInstances,
  getMoviePilotSettings,
  reverseMoviePilotAssociations,
  updateMoviePilotInstance,
  updateMoviePilotSettings
} from '@/api/moviepilot'
import { getDownloaderList, type DownloaderSimple } from '@/api/torrents'
import { ApiError } from '@/types/api'
import { apiErrorMessage } from '@/i18n'

/** 映射编辑行（草稿态） */
interface MappingDraftRow {
  mpName: string
  btDownloaderId: string
}

/**
 * MoviePilot 集成设置面板（moviepilot-integration）。
 *
 * - 全局开关：revision CAS 保存，409 冲突自动重载；
 * - 实例：启用开关即时生效；下载器映射单实例内联编辑，保存后后端重解析；
 * - 反查卡：路径精确/目录前缀 → 整理历史 + 任务快照（v1 简版，后续可独立页面）；
 * - demo 模式经 @/demo 拦截层提供同形数据，无独立分支；
 * - 移动端经 views/mobile/settings.vue 包装桌面设置页自动同源。
 */
@Component({ name: 'MoviePilotPanel' })
export default class MoviePilotPanel extends Vue {
  private loading = false
  private loaded = false

  // ====== 全局开关（已保存态 + 草稿态） ======
  private settingsEnabled = false
  private revision = 0
  private draftEnabled = false
  private saving = false
  private updatedAt: string | null = null
  private updatedBy: string | null = null

  // ====== 实例与映射 ======
  private instances: MoviePilotInstance[] = []
  private instancesLoading = false
  private downloaders: DownloaderSimple[] = []
  private editingInstanceId = ''
  private mappingDraft: MappingDraftRow[] = []
  private mappingSaving = false

  // ====== 反查 ======
  private reversePath = ''
  private reverseMode: MoviePilotReverseMode = 'both'
  private reverseLoading = false
  private reverseLoaded = false
  private reverseItems: MoviePilotAssociationItem[] = []
  private reverseError = ''

  get dirty(): boolean {
    return this.loaded && this.draftEnabled !== this.settingsEnabled
  }

  get lastUpdatedText(): string {
    if (!this.updatedAt && !this.updatedBy) {
      return this.loaded ? this.$t('moviepilot.panel.neverSaved').toString() : ''
    }
    const time = this.updatedAt ? this.updatedAt.slice(0, 19).replace('T', ' ') : ''
    const by = this.updatedBy ? this.$t('moviepilot.panel.bySuffix', { by: this.updatedBy }).toString() : ''
    return this.$t('moviepilot.panel.revisionInfo', { revision: this.revision, time, by }).toString()
  }

  mounted(): void {
    this.loadAll()
  }

  private async loadAll(): Promise<void> {
    this.loading = true
    try {
      await Promise.all([this.loadSettings(), this.loadInstances(), this.loadDownloaders()])
      this.loaded = true
    } catch (error) {
      this.loaded = false
      console.error('加载 MoviePilot 集成配置失败:', error)
    } finally {
      this.loading = false
    }
  }

  private async loadSettings(): Promise<void> {
    const res = await getMoviePilotSettings()
    this.settingsEnabled = res.data.settings.enabled
    this.revision = res.data.settings.revision
    this.updatedAt = res.data.settings.updatedAt
    this.updatedBy = res.data.settings.updatedBy
    this.resetDraft()
  }

  private async loadInstances(): Promise<void> {
    this.instancesLoading = true
    try {
      const res = await getMoviePilotInstances()
      this.instances = res.data.list || []
      // 正在编辑的实例被外部删除时退出编辑态
      if (this.editingInstanceId && !this.instanceById(this.editingInstanceId)) {
        this.cancelEditMapping()
      }
    } finally {
      this.instancesLoading = false
    }
  }

  private async loadDownloaders(): Promise<void> {
    const res = await getDownloaderList()
    this.downloaders = res.data || []
  }

  private resetDraft(): void {
    this.draftEnabled = this.settingsEnabled
  }

  private async save(): Promise<void> {
    if (!this.dirty || this.saving) return
    this.saving = true
    try {
      const res = await updateMoviePilotSettings({
        enabled: this.draftEnabled,
        expectedRevision: this.revision
      })
      this.settingsEnabled = res.data.settings.enabled
      this.revision = res.data.settings.revision
      this.updatedAt = res.data.settings.updatedAt
      this.updatedBy = res.data.settings.updatedBy
      this.resetDraft()
      this.$message.success(this.$t('moviepilot.panel.msg.saved').toString())
    } catch (error) {
      if (error instanceof ApiError && error.code === '409') {
        this.$message.warning(this.$t('moviepilot.panel.msg.conflict').toString())
        await this.loadSettings()
      } else {
        console.error('保存 MoviePilot 集成配置失败:', error)
        this.$message.error(this.$t('moviepilot.panel.msg.saveFailed').toString())
      }
    } finally {
      this.saving = false
    }
  }

  // ====== 实例操作 ======

  private instanceById(instanceId: string): MoviePilotInstance | null {
    const found = this.instances.find(item => item.instanceId === instanceId)
    return found || null
  }

  private mappingCount(instance: MoviePilotInstance): number {
    return Object.keys(instance.downloaderMapping || {}).length
  }

  private instanceSummary(instance: MoviePilotInstance): string {
    const sync = instance.lastSyncAt
      ? instance.lastSyncAt.slice(0, 19).replace('T', ' ')
      : this.$t('moviepilot.panel.notSyncedYet').toString()
    return `${this.$t('moviepilot.panel.syncedCount', { count: instance.syncedHistoryCount }).toString()} · ${sync}`
  }

  private async toggleInstance(instance: MoviePilotInstance, enabled: boolean | string | number): Promise<void> {
    try {
      await updateMoviePilotInstance(instance.instanceId, { enabled: Boolean(enabled) })
      instance.enabled = Boolean(enabled)
      this.$message.success(instance.enabled
        ? this.$t('moviepilot.panel.msg.instanceEnabled').toString()
        : this.$t('moviepilot.panel.msg.instanceDisabled').toString())
    } catch (error) {
      console.error('更新实例失败:', error)
      this.$message.error(this.$t('moviepilot.panel.msg.instanceUpdateFailed').toString())
      await this.loadInstances()
    }
  }

  private removeInstance(instance: MoviePilotInstance): void {
    this.$confirm(
      this.$t('moviepilot.panel.msg.deleteConfirm', {
        name: instance.name || instance.instanceId,
        count: instance.syncedHistoryCount
      }).toString(),
      this.$t('moviepilot.panel.msg.deleteTitle').toString(),
      {
        type: 'warning',
        confirmButtonText: this.$t('moviepilot.panel.msg.deleteConfirmButton').toString(),
        cancelButtonText: this.$t('common.cancel').toString()
      }
    )
      .then(async() => {
        try {
          await deleteMoviePilotInstance(instance.instanceId)
          this.$message.success(this.$t('moviepilot.panel.msg.instanceDeleted').toString())
          await this.loadInstances()
        } catch (error) {
          console.error('删除实例失败:', error)
          this.$message.error(this.$t('moviepilot.panel.msg.instanceDeleteFailed').toString())
        }
      })
      .catch(() => undefined)
  }

  // ====== 映射编辑 ======

  private startEditMapping(instance: MoviePilotInstance): void {
    this.editingInstanceId = instance.instanceId
    const mapping = instance.downloaderMapping || {}
    this.mappingDraft = Object.keys(mapping).map(mpName => ({
      mpName,
      btDownloaderId: mapping[mpName]
    }))
    if (this.mappingDraft.length === 0) {
      this.addMappingRow()
    }
  }

  private cancelEditMapping(): void {
    this.editingInstanceId = ''
    this.mappingDraft = []
  }

  private addMappingRow(): void {
    this.mappingDraft.push({ mpName: '', btDownloaderId: '' })
  }

  private removeMappingRow(index: number): void {
    this.mappingDraft.splice(index, 1)
  }

  private async saveMapping(instance: MoviePilotInstance): Promise<void> {
    const rows = this.mappingDraft.filter(row => row.mpName.trim() || row.btDownloaderId)
    if (rows.some(row => !row.mpName.trim() || !row.btDownloaderId)) {
      this.$message.warning(this.$t('moviepilot.panel.mapping.rowInvalid').toString())
      return
    }
    const names = rows.map(row => row.mpName.trim())
    if (new Set(names).size !== names.length) {
      this.$message.warning(this.$t('moviepilot.panel.mapping.duplicateName').toString())
      return
    }
    this.mappingSaving = true
    try {
      const mapping: Record<string, string> = {}
      rows.forEach(row => {
        mapping[row.mpName.trim()] = row.btDownloaderId
      })
      const res = await updateMoviePilotInstance(instance.instanceId, { downloaderMapping: mapping })
      instance.downloaderMapping = res.data.downloaderMapping || {}
      this.cancelEditMapping()
      this.$message.success(this.$t('moviepilot.panel.mapping.saved').toString())
    } catch (error) {
      console.error('保存映射失败:', error)
      this.$message.error(this.$t('moviepilot.panel.mapping.saveFailed').toString())
    } finally {
      this.mappingSaving = false
    }
  }

  private downloaderLabel(downloaderId: string): string {
    const found = this.downloaders.find(dl => dl.downloader_id === downloaderId)
    if (found && found.nickname) {
      return found.nickname
    }
    return downloaderId
  }

  // ====== 反查 ======

  private async runReverse(): Promise<void> {
    const path = this.reversePath.trim()
    if (!path) {
      this.$message.warning(this.$t('moviepilot.reverse.pathRequired').toString())
      return
    }
    this.reverseLoading = true
    this.reverseError = ''
    try {
      const res = await reverseMoviePilotAssociations(path, this.reverseMode)
      this.reverseItems = res.data.list || []
      this.reverseLoaded = true
    } catch (error) {
      this.reverseItems = []
      this.reverseLoaded = true
      this.reverseError = error instanceof ApiError
        ? apiErrorMessage(error, this.$t('moviepilot.reverse.failed').toString())
        : this.$t('moviepilot.reverse.failed').toString()
      console.error('MoviePilot 反查失败:', error)
    } finally {
      this.reverseLoading = false
    }
  }

  // ====== 展示辅助 ======

  private seasonsEpisodesText(item: MoviePilotAssociationItem): string {
    const parts: string[] = []
    if (item.seasons) parts.push(item.seasons)
    if (item.episodes) parts.push(item.episodes)
    return parts.length > 0 ? parts.join(' ') : '-'
  }

  private transferModeLabel(mode: string | null): string {
    const labels: Record<string, string> = {
      copy: this.$t('moviepilot.shared.transferMode.copy').toString(),
      move: this.$t('moviepilot.shared.transferMode.move').toString(),
      link: this.$t('moviepilot.shared.transferMode.link').toString(),
      hardlink: this.$t('moviepilot.shared.transferMode.hardlink').toString()
    }
    if (!mode) return '-'
    return labels[mode] || mode
  }

  private associationLabel(status: string): string {
    if (status === 'linked') return this.$t('moviepilot.shared.association.linked').toString()
    if (status === 'unmapped') return this.$t('moviepilot.shared.association.unmapped').toString()
    return this.$t('moviepilot.shared.association.unassociated').toString()
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/settings-panel';

.mp-panel {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg, 16px);
}

// 卡片壳/标题/描述：统一继承系统设置页签规范（960px 宽 + 渐变竖条标题 + 14px 描述）
.mp-card {
  @extend %settings-card;
}

.mp-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mp-card-title {
  @extend %settings-card-title;
}

.mp-description {
  @extend %settings-card-description;
}

.mp-hint {
  color: var(--color-text-secondary, #909399);
  padding: 8px 0;
  font-size: 13px;
}

.mp-global-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}

.mp-global-label {
  font-weight: 600;
}

.mp-global-state {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
}

.mp-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: var(--spacing-md);
}

.mp-updated {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin-right: auto;
}

.mp-instance {
  border: 1px solid var(--color-border-primary, #ebeef5);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.mp-instance-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.mp-instance-name {
  font-size: 14px;
  font-weight: 600;
}

.mp-instance-meta {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
}

.mp-instance-ids {
  margin-top: 4px;
  word-break: break-all;
}

.mp-instance-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-danger, #f56c6c);
}

.mp-instance-danger {
  color: var(--el-color-danger, #f56c6c);
}

.mp-mapping {
  margin-top: 10px;
}

.mp-mapping-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.mp-mapping-title {
  font-size: 13px;
  font-weight: 600;
}

.mp-mapping-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mp-mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.mp-mapping-input {
  width: 220px;
}

.mp-mapping-select {
  width: 220px;
}

.mp-mapping-name {
  font-size: 13px;
}

.mp-mapping-arrow {
  color: var(--color-text-secondary, #909399);
}

.mp-reverse-form {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mp-reverse-input {
  flex: 1;
  min-width: 240px;
}

.mp-reverse-mode {
  width: 120px;
}

.mp-reverse-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
  font-size: 12px;

  th,
  td {
    border-bottom: 1px solid var(--color-border-primary, #ebeef5);
    padding: 6px 8px;
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--color-text-secondary, #909399);
    font-weight: 600;
  }
}

.mp-cell-title {
  font-weight: 600;
  word-break: break-all;
}

.mp-cell-sub {
  color: var(--color-text-secondary, #909399);
  margin-top: 2px;
}

.mp-cell-path {
  word-break: break-all;
  color: var(--color-text-secondary, #606266);
}
</style>
