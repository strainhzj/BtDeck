<template>
  <div class="mp-panel">
    <!-- 全局开关 -->
    <div class="mp-card">
      <h3 class="mp-card-title">MoviePilot 集成</h3>
      <p class="mp-description">
        通过 MoviePilot 插件 BtDeckBridge 将其整理历史同步为只读镜像，建立
        「媒体库文件 ↔ 整理源文件 ↔ BT 任务」关联。本功能不产生任何对生产任务
        或 MoviePilot 侧的写操作；MoviePilot 历史消失不会触发本地清理。
      </p>

      <div v-if="isDemo" class="mp-hint">演示模式不支持修改 MoviePilot 集成配置。</div>

      <template v-else>
        <div v-if="loading" class="mp-hint">加载中…</div>
        <div v-else-if="!loaded" class="mp-hint">
          MoviePilot 集成配置加载失败。
          <el-button size="mini" @click="loadAll">重试</el-button>
        </div>

        <template v-else>
          <div class="mp-global-row">
            <span class="mp-global-label">集成开关</span>
            <el-switch v-model="draftEnabled" />
            <span class="mp-global-state">{{ draftEnabled ? '已开启' : '已关闭' }}</span>
          </div>
          <p class="mp-description">
            关闭后插件握手与同步会被拒绝（403）；已同步的镜像数据保留。插件侧需配置
            BtDeck 地址与专用集成账号（建议单独创建账号，勿开启两步验证）。
          </p>
          <div class="mp-actions">
            <span v-if="lastUpdatedText" class="mp-updated">{{ lastUpdatedText }}</span>
            <el-button size="small" :disabled="!dirty || saving" @click="resetDraft">放弃更改</el-button>
            <el-button type="primary" size="small" :loading="saving" :disabled="!dirty" @click="save">
              保存配置
            </el-button>
          </div>
        </template>
      </template>
    </div>

    <!-- 实例与下载器映射 -->
    <div v-if="!isDemo && loaded" class="mp-card">
      <div class="mp-card-head">
        <h3 class="mp-card-title">已注册实例</h3>
        <el-button size="mini" :loading="instancesLoading" @click="loadInstances">刷新</el-button>
      </div>
      <p class="mp-description">
        MoviePilot 插件首次握手后自动注册。配置「MoviePilot 下载器 → BtDeck 下载器」
        映射后，同步的历史才能按 (下载器, Hash) 关联到任务；映射名须与 MoviePilot
        侧下载器名称一致。
      </p>

      <div v-if="instances.length === 0" class="mp-hint">
        暂无实例。在 MoviePilot 中安装 BtDeckBridge 插件并完成握手后，此处会出现实例。
      </div>

      <div v-for="instance in instances" :key="instance.instanceId" class="mp-instance">
        <div class="mp-instance-head">
          <span class="mp-instance-name">{{ instance.name || instance.instanceId }}</span>
          <el-tag size="mini" :type="instance.enabled ? 'success' : 'info'">
            {{ instance.enabled ? '已启用' : '已禁用' }}
          </el-tag>
          <el-switch
            :value="instance.enabled"
            active-text="允许同步"
            @change="toggleInstance(instance, $event)"
          />
          <span class="mp-instance-meta">
            {{ instanceSummary(instance) }}
          </span>
          <el-button type="text" size="mini" class="mp-instance-danger" @click="removeInstance(instance)">
            删除实例
          </el-button>
        </div>
        <div class="mp-instance-meta mp-instance-ids">
          实例 {{ instance.instanceId }} · 绑定账号 {{ instance.boundUsername || '-' }}
          <template v-if="instance.moviepilotVersion">· MoviePilot {{ instance.moviepilotVersion }}</template>
          <template v-if="instance.pluginVersion">· 插件 {{ instance.pluginVersion }}</template>
        </div>
        <div v-if="instance.lastError" class="mp-instance-error">最近错误：{{ instance.lastError }}</div>

        <!-- 下载器映射编辑（单实例内联编辑） -->
        <div class="mp-mapping">
          <div class="mp-mapping-head">
            <span class="mp-mapping-title">下载器映射</span>
            <el-button
              v-if="editingInstanceId !== instance.instanceId"
              size="mini"
              @click="startEditMapping(instance)"
            >编辑映射</el-button>
            <template v-else>
              <el-button size="mini" :disabled="mappingSaving" @click="cancelEditMapping">取消</el-button>
              <el-button type="primary" size="mini" :loading="mappingSaving" @click="saveMapping(instance)">
                保存映射
              </el-button>
            </template>
          </div>

          <template v-if="editingInstanceId === instance.instanceId">
            <div v-for="(row, index) in mappingDraft" :key="index" class="mp-mapping-row">
              <el-input
                v-model="row.mpName"
                size="mini"
                placeholder="MoviePilot 下载器名"
                class="mp-mapping-input"
              />
              <span class="mp-mapping-arrow">→</span>
              <el-select
                v-model="row.btDownloaderId"
                size="mini"
                filterable
                placeholder="BtDeck 下载器"
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
              >删除</el-button>
            </div>
            <el-button size="mini" plain @click="addMappingRow">+ 添加映射</el-button>
            <p class="mp-description">
              保存后该实例全部历史会立即按新映射重新解析关联状态。
            </p>
          </template>

          <template v-else>
            <div v-if="mappingCount(instance) === 0" class="mp-hint">尚未配置映射（历史将标记为未映射）。</div>
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
    <div v-if="!isDemo && loaded" class="mp-card">
      <h3 class="mp-card-title">关联反查</h3>
      <p class="mp-description">
        输入媒体库文件/目录或源文件路径，反查关联的整理历史与 BT 任务。
        目录会按前缀匹配其下文件；无 Hash 的历史标记为未关联。
      </p>
      <div class="mp-reverse-form">
        <el-input
          v-model="reversePath"
          size="small"
          placeholder="如 /data/media/电影 或 /data/downloads/xxx.mkv"
          class="mp-reverse-input"
          clearable
          @keyup.enter.native="runReverse"
        />
        <el-select v-model="reverseMode" size="small" class="mp-reverse-mode">
          <el-option label="全部路径" value="both" />
          <el-option label="仅源文件" value="src" />
          <el-option label="仅媒体库" value="dest" />
        </el-select>
        <el-button type="primary" size="small" :loading="reverseLoading" @click="runReverse">查询</el-button>
      </div>

      <div v-if="reverseError" class="mp-instance-error">{{ reverseError }}</div>
      <div v-else-if="reverseLoaded && reverseItems.length === 0" class="mp-hint">未找到匹配的整理历史。</div>
      <table v-if="reverseItems.length > 0" class="mp-reverse-table">
        <thead>
          <tr>
            <th>媒体标题</th>
            <th style="width: 110px;">季 / 集</th>
            <th style="width: 80px;">整理方式</th>
            <th>媒体库路径</th>
            <th>源文件路径</th>
            <th style="width: 130px;">关联任务</th>
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
import { isDemoMode } from '@/demo/config'
import { ApiError } from '@/types/api'

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
 * - 移动端经 views/mobile/settings.vue 包装桌面设置页自动同源。
 */
@Component({ name: 'MoviePilotPanel' })
export default class MoviePilotPanel extends Vue {
  private isDemo = isDemoMode()
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
      return this.loaded ? '尚未保存过配置' : ''
    }
    const time = this.updatedAt ? this.updatedAt.slice(0, 19).replace('T', ' ') : ''
    const by = this.updatedBy ? `（${this.updatedBy}）` : ''
    return `当前 revision ${this.revision} · ${time}${by}`
  }

  mounted(): void {
    if (!this.isDemo) {
      this.loadAll()
    }
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
      this.$message.success('MoviePilot 集成配置已保存')
    } catch (error) {
      if (error instanceof ApiError && error.code === '409') {
        this.$message.warning('配置已被其他会话修改，已重新加载最新配置，请确认后重试')
        await this.loadSettings()
      } else {
        console.error('保存 MoviePilot 集成配置失败:', error)
        this.$message.error('保存失败，请稍后重试')
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
      : '尚未同步'
    return `已同步 ${instance.syncedHistoryCount} 条 · ${sync}`
  }

  private async toggleInstance(instance: MoviePilotInstance, enabled: boolean | string | number): Promise<void> {
    try {
      await updateMoviePilotInstance(instance.instanceId, { enabled: Boolean(enabled) })
      instance.enabled = Boolean(enabled)
      this.$message.success(instance.enabled ? '实例已启用' : '实例已禁用（握手/同步将被拒绝）')
    } catch (error) {
      console.error('更新实例失败:', error)
      this.$message.error('更新实例失败')
      await this.loadInstances()
    }
  }

  private removeInstance(instance: MoviePilotInstance): void {
    this.$confirm(
      `删除实例「${instance.name || instance.instanceId}」将连带删除其 ${instance.syncedHistoryCount} 条同步历史，且不可恢复。确定删除？`,
      '删除实例',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
      .then(async() => {
        try {
          await deleteMoviePilotInstance(instance.instanceId)
          this.$message.success('实例已删除')
          await this.loadInstances()
        } catch (error) {
          console.error('删除实例失败:', error)
          this.$message.error('删除实例失败')
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
      this.$message.warning('映射行的 MoviePilot 下载器名与 BtDeck 下载器均不能为空')
      return
    }
    const names = rows.map(row => row.mpName.trim())
    if (new Set(names).size !== names.length) {
      this.$message.warning('存在重复的 MoviePilot 下载器名')
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
      this.$message.success('映射已保存，历史关联状态已重新解析')
    } catch (error) {
      console.error('保存映射失败:', error)
      this.$message.error('保存映射失败')
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
      this.$message.warning('请输入要反查的路径')
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
      this.reverseError = error instanceof ApiError ? error.msg : '反查失败，请稍后重试'
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
      copy: '复制',
      move: '移动',
      link: '软链接',
      hardlink: '硬链接'
    }
    if (!mode) return '-'
    return labels[mode] || mode
  }

  private associationLabel(status: string): string {
    if (status === 'linked') return '已关联'
    if (status === 'unmapped') return '未映射'
    return '未关联'
  }
}
</script>

<style lang="scss" scoped>
.mp-panel {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg, 16px);
}

.mp-card {
  width: 100%;
  max-width: 760px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-md);
}

.mp-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mp-card-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-sm);
}

.mp-description {
  color: var(--color-text-secondary, #909399);
  font-size: 13px;
  line-height: 1.6;
  margin: var(--spacing-sm) 0 var(--spacing-md);
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
