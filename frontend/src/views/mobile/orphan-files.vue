<template>
  <div class="m-orphan">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-orphan-tabs">
      <button
        type="button"
        class="m-orphan-tab"
        :class="{'is-active': activeTab === 'orphans'}"
        @click="switchTab('orphans')"
      >
        孤儿文件
      </button>
      <button
        type="button"
        class="m-orphan-tab"
        :class="{'is-active': activeTab === 'quarantine'}"
        @click="switchTab('quarantine')"
      >
        隔离区
      </button>
    </div>

    <!-- ========== 孤儿文件 Tab ========== -->
    <template v-if="activeTab === 'orphans'">
      <div v-if="scanContext" class="m-orphan-scan">
        <div class="m-orphan-scan-time">
          最近扫描：{{ scanTime }}<template v-if="scanRunning">（扫描进行中…）</template>
        </div>
        <div class="m-orphan-scan-stats">
          待清理 {{ scanContext.remaining_count }} 个 · {{ formatSize(scanContext.remaining_size) }}
          <template v-if="scanContext.ignored_count > 0"> · 已忽视 {{ scanContext.ignored_count }}</template>
        </div>
        <div v-if="!scanContext.cleanup_allowed" class="m-orphan-scan-block">
          清理暂不可用：{{ scanContext.cleanup_block_reason || '扫描批次不可用' }}
        </div>
      </div>

      <div class="m-toolbar">
        <el-select v-model="statusFilter" size="small" placeholder="全部状态" clearable @change="reloadOrphans">
          <el-option label="待清理" value="pending" />
          <el-option label="已忽视" value="ignored" />
          <el-option label="已清理" value="deleted" />
        </el-select>
        <el-select v-model="confidenceFilter" size="small" placeholder="全部置信度" clearable @change="reloadOrphans">
          <el-option label="高置信度" value="high" />
          <el-option label="低置信度（有误判风险）" value="low" />
        </el-select>
      </div>
      <div class="m-toolbar m-toolbar--second">
        <el-input
          v-model="pathFilter"
          size="small"
          placeholder="按路径过滤"
          clearable
          prefix-icon="el-icon-search"
          @keyup.enter.native="reloadOrphans"
          @clear="reloadOrphans"
        />
        <el-button size="small" :loading="scanSubmitting || scanRunning" @click="confirmScan">扫描</el-button>
        <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reloadOrphans">刷新</el-button>
      </div>

      <div v-if="!loading && orphans.length === 0" class="m-hint">没有匹配的孤儿文件</div>

      <div v-for="item in orphans" :key="item.id" class="m-orphan-card">
        <div class="m-orphan-path" :title="item.file_path">{{ item.file_path }}</div>
        <div class="m-orphan-meta">
          <el-tag size="mini" :type="statusTagType(item)">{{ statusText(item) }}</el-tag>
          <el-tag size="mini" :type="item.confidence === 'low' ? 'warning' : 'success'" effect="plain">
            {{ item.confidence === 'low' ? '低置信度' : '高置信度' }}
          </el-tag>
          <span class="m-orphan-meta-text">{{ formatSize(item.file_size) }}</span>
          <span v-if="item.hardlink_copy_count !== null && item.hardlink_copy_count > 0" class="m-orphan-copies">
            副本 {{ item.hardlink_copy_count }}
          </span>
        </div>
        <div class="m-orphan-sub">
          <span v-if="item.downloader_name">{{ item.downloader_name }}</span>
          <span>{{ formatTime(item.mtime) }}</span>
        </div>
        <div v-if="!item.is_deleted" class="m-orphan-actions">
          <el-button
            v-if="!item.is_ignored"
            size="mini"
            type="danger"
            plain
            :disabled="busyId === item.id"
            @click="cleanupOne(item)"
          >
            清理
          </el-button>
          <el-button size="mini" :disabled="busyId === item.id" @click="confirmIgnore(item, !item.is_ignored)">
            {{ item.is_ignored ? '取消忽视' : '忽视' }}
          </el-button>
        </div>
      </div>

      <el-button
        v-if="orphans.length < total"
        class="m-load-more"
        size="small"
        :loading="loading"
        @click="loadMoreOrphans"
      >
        加载更多（{{ orphans.length }}/{{ total }}）
      </el-button>
    </template>

    <!-- ========== 隔离区 Tab ========== -->
    <template v-else>
      <div class="m-toolbar">
        <el-input
          v-model="quarantinePathFilter"
          size="small"
          placeholder="按路径过滤"
          clearable
          prefix-icon="el-icon-search"
          @keyup.enter.native="reloadQuarantine"
          @clear="reloadQuarantine"
        />
        <el-button size="small" icon="el-icon-refresh" :loading="quarantineLoading" @click="reloadQuarantine">刷新</el-button>
      </div>

      <div v-if="!quarantineLoading && quarantine.length === 0" class="m-hint">隔离区为空</div>

      <div v-for="item in quarantine" :key="item.canonical_path" class="m-orphan-card">
        <div class="m-orphan-path" :title="item.canonical_path">{{ item.canonical_path }}</div>
        <div class="m-orphan-meta">
          <el-tag size="mini" :type="item.confidence === 'low' ? 'warning' : 'success'" effect="plain">
            {{ item.confidence === 'low' ? '低置信度' : '高置信度' }}
          </el-tag>
          <span class="m-orphan-meta-text">{{ formatSize(item.file_size) }}</span>
        </div>
        <div class="m-orphan-sub">
          <span>隔离：{{ formatTime(item.quarantined_at) }}</span>
          <span>预计清除：{{ formatTime(item.purge_after) }}</span>
          <span v-if="item.purge_delay_count">延迟 {{ item.purge_delay_count }} 次</span>
        </div>
        <div class="m-orphan-actions">
          <el-button size="mini" :disabled="busyPath === item.canonical_path" @click="confirmRestore(item)">恢复</el-button>
          <el-button
            size="mini"
            type="danger"
            plain
            :disabled="busyPath === item.canonical_path"
            @click="confirmPurge(item)"
          >
            立即清除
          </el-button>
        </div>
      </div>

      <el-button
        v-if="quarantine.length < quarantineTotal"
        class="m-load-more"
        size="small"
        :loading="quarantineLoading"
        @click="loadMoreQuarantine"
      >
        加载更多（{{ quarantine.length }}/{{ quarantineTotal }}）
      </el-button>
    </template>

    <div class="m-orphan-footnote">
      文件夹聚合视图、副本位置、前缀快捷操作、批量操作与守卫复核请在桌面版「孤儿文件」页操作
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getOrphanList,
  getQuarantineList,
  restoreQuarantined,
  purgeQuarantineNow,
  triggerScan,
  getScanStatus,
  cleanupPreview,
  cleanupOrphans,
  setIgnored,
  OrphanFileItem,
  OrphanScanContext,
  QuarantineItem,
  IgnoreResult
} from '@/api/orphan-files'
import { formatFileSize, extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

const PAGE_SIZE = 20

/**
 * 移动孤儿文件（Phase 4 M4）：双 Tab（孤儿文件/隔离区）与桌面同构；
 * 清理走桌面同款两段式（cleanupPreview 预览 → 确认 cleanupOrphans，拒绝/空
 * 结果分支提示）；忽视/取消忽视单条；隔离区单条恢复与立即清除（强确认）。
 * 文件夹聚合/副本位置/前缀快捷操作/批量操作/守卫复核保留桌面版承载。
 */
@Component({
  name: 'MobileOrphanFiles',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileOrphanFiles extends Mixins(PullToRefresh) {
  private activeTab: 'orphans' | 'quarantine' = 'orphans'

  // 孤儿文件列表
  private orphans: OrphanFileItem[] = []
  private total = 0
  private page = 1
  private loading = false
  private statusFilter = ''
  private confidenceFilter = ''
  private pathFilter = ''
  private scanContext: OrphanScanContext | null = null
  private busyId = 0

  // 扫描
  private scanSubmitting = false
  private scanPollTimer: number | null = null
  private scanPollSeq = 0
  private scanRunning = false

  // 隔离区
  private quarantine: QuarantineItem[] = []
  private quarantineTotal = 0
  private quarantinePage = 1
  private quarantineLoading = false
  private quarantinePathFilter = ''
  private busyPath = ''

  mounted(): void {
    this.reloadOrphans()
  }

  beforeDestroy(): void {
    this.stopScanPolling()
  }

  protected async onPullRefresh(): Promise<void> {
    if (this.activeTab === 'orphans') {
      await this.reloadOrphans()
    } else {
      await this.reloadQuarantine()
    }
  }

  private switchTab(tab: 'orphans' | 'quarantine'): void {
    if (this.activeTab === tab) return
    this.activeTab = tab
    if (tab === 'quarantine' && this.quarantine.length === 0 && this.quarantineTotal === 0) {
      this.reloadQuarantine()
    }
  }

  // ========== 孤儿文件列表 ==========

  private async reloadOrphans(): Promise<void> {
    this.page = 1
    this.orphans = []
    this.total = 0
    await this.fetchOrphans()
  }

  private async loadMoreOrphans(): Promise<void> {
    await this.fetchOrphans()
  }

  private async fetchOrphans(): Promise<void> {
    this.loading = true
    try {
      const res = await getOrphanList({
        page: this.page,
        page_size: PAGE_SIZE,
        ...(this.pathFilter ? { path_like: this.pathFilter } : {}),
        ...(this.statusFilter ? { status: this.statusFilter } : {}),
        ...(this.confidenceFilter ? { confidence: this.confidenceFilter } : {})
      })
      if (res.code === '200' && res.data) {
        // 移动端不启用文件夹聚合（group_by_folder），防御性过滤掉聚合行
        const rows = (res.data.list ?? []).filter((row): row is OrphanFileItem => !('_is_folder' in row))
        this.orphans = this.orphans.concat(rows)
        this.total = res.data.total ?? 0
        this.page += 1
        if (res.data.scan_context) {
          this.scanContext = res.data.scan_context
        }
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private get scanTime(): string {
    const scan = this.scanContext && this.scanContext.display_scan ? this.scanContext.display_scan : null
    return scan ? this.formatTime(scan.scan_time) : '暂无'
  }

  // ========== 扫描（确认 → 提交 → 轮询） ==========

  private confirmScan(): void {
    this.$confirm('确认立即扫描孤儿文件？扫描可能需要较长时间。', '提示', { type: 'info' })
      .then(() => this.handleScan())
      .catch(() => undefined)
  }

  private async handleScan(): Promise<void> {
    this.scanSubmitting = true
    try {
      const res = await triggerScan()
      if (res.code === '200' && res.data) {
        this.$message.success(res.data.accepted ? '扫描任务已提交到后台' : '已有扫描任务，继续跟踪其状态')
        this.startScanPolling(res.data.scan_id)
      } else {
        this.$message.error(res.msg || '扫描失败')
      }
    } catch (e) {
      this.$message.error('扫描失败：' + extractErrorMessage(e))
    } finally {
      this.scanSubmitting = false
    }
  }

  private startScanPolling(scanId: string): void {
    this.stopScanPolling()
    this.scanRunning = true
    const seq = ++this.scanPollSeq
    const poll = async(): Promise<void> => {
      try {
        const res = await getScanStatus(scanId)
        if (seq !== this.scanPollSeq) return
        if (!res.data) {
          this.scanPollTimer = window.setTimeout(poll, 3000)
          return
        }
        const record = res.data
        if (record.status === 'queued' || record.status === 'running') {
          this.scanPollTimer = window.setTimeout(poll, 2000)
          return
        }
        this.stopScanPolling()
        if (record.status === 'completed') {
          this.$message.success(`扫描完成：孤儿 ${record.total_orphans}，新增明细 ${record.new_orphans}，复用 ${record.known_orphans}`)
        } else {
          this.$message.warning(`扫描失败：${record.error_message || '未知错误'}`)
        }
        await this.reloadOrphans()
      } catch {
        if (seq !== this.scanPollSeq) return
        this.scanPollTimer = window.setTimeout(poll, 3000)
      }
    }
    void poll()
  }

  private stopScanPolling(): void {
    this.scanPollSeq += 1
    if (this.scanPollTimer !== null) {
      window.clearTimeout(this.scanPollTimer)
      this.scanPollTimer = null
    }
    this.scanRunning = false
  }

  // ========== 清理（两段式：预览 → 确认执行） ==========

  private async cleanupOne(item: OrphanFileItem): Promise<void> {
    const scan = this.scanContext ? this.scanContext.display_scan : null
    if (!this.scanContext || !this.scanContext.cleanup_allowed || !scan) {
      this.$message.warning((this.scanContext && this.scanContext.cleanup_block_reason) || '当前扫描批次不可清理，请先完成一次扫描')
      return
    }
    this.busyId = item.id
    try {
      const payload = { scan_id: scan.scan_id, orphan_ids: [item.id] }
      const preview = await cleanupPreview(payload)
      if (preview.code !== '200' || !preview.data) {
        this.$message.error(preview.msg || '预览失败')
        return
      }
      if (preview.data.rejected === true) {
        this.$message.error(preview.data.error || preview.data.reason)
        await this.reloadOrphans()
        return
      }
      if (preview.data.total_count === 0) {
        this.$message.warning('该文件无可清理项：可能是低置信度（需等下载器上线精筛）、已忽视或已清理。')
        return
      }
      const lowWarn = preview.data.low_confidence_count && preview.data.low_confidence_count > 0
        ? `；含低置信度 ${preview.data.low_confidence_count} 个，有误判风险` : ''
      try {
        await this.$confirm(
          `清理 ${preview.data.total_count} 个文件，共 ${this.formatSize(preview.data.total_size)}？${lowWarn}`,
          '清理确认',
          { type: 'warning' }
        )
      } catch {
        return
      }
      const result = await cleanupOrphans(payload)
      if (result.code === '200' && result.data) {
        if (result.data.task_id) {
          const skipped = result.data.skipped_count ? `，跳过处理中 ${result.data.skipped_count} 个` : ''
          this.$message.success(`清理任务已提交（${result.data.task_id.slice(0, 8)}）${skipped}，完成后将在通知中心提醒`)
        } else {
          this.$message.info(result.msg || '该文件已在清理任务中处理')
        }
        await this.reloadOrphans()
      } else {
        this.$message.error(result.msg || '清理失败')
      }
    } catch (e) {
      this.$message.error('清理失败：' + extractErrorMessage(e))
    } finally {
      this.busyId = 0
    }
  }

  // ========== 忽视 / 取消忽视 ==========

  private confirmIgnore(item: OrphanFileItem, ignored: boolean): void {
    const action = ignored ? '忽视' : '取消忽视'
    this.$confirm(`确认${action}该孤儿文件？`, '提示', { type: 'info' })
      .then(() => this.applyIgnore(item, ignored))
      .catch(() => undefined)
  }

  private async applyIgnore(item: OrphanFileItem, ignored: boolean): Promise<void> {
    this.busyId = item.id
    try {
      const scan = this.scanContext ? this.scanContext.display_scan : null
      const res = await setIgnored({
        ...(scan ? { scan_id: scan.scan_id } : {}),
        orphan_ids: [item.id],
        ignored
      })
      if (res.code === '200' && res.data) {
        this.reportIgnoreResult(res.data, ignored)
        await this.reloadOrphans()
      } else {
        this.$message.error(res.msg || (ignored ? '忽视失败' : '取消忽视失败'))
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyId = 0
    }
  }

  private reportIgnoreResult(data: IgnoreResult, ignored: boolean): void {
    const action = ignored ? '忽视' : '取消忽视'
    if (data.rejected === true) {
      this.$message.error(`${action}失败：${data.error || '被拒绝'}`)
      return
    }
    if (data.success_count === 0 && data.failed_count > 0) {
      const reason = data.failed_list[0] ? data.failed_list[0].reason : ''
      this.$message.error(`${action}失败：${reason || '未知原因'}`)
      return
    }
    if (data.failed_count > 0) {
      this.$message.warning(`${action}部分完成：成功 ${data.success_count} 个，失败 ${data.failed_count} 个`)
      return
    }
    this.$message.success(`${action}完成`)
  }

  // ========== 隔离区 ==========

  private async reloadQuarantine(): Promise<void> {
    this.quarantinePage = 1
    this.quarantine = []
    this.quarantineTotal = 0
    await this.fetchQuarantine()
  }

  private async loadMoreQuarantine(): Promise<void> {
    await this.fetchQuarantine()
  }

  private async fetchQuarantine(): Promise<void> {
    this.quarantineLoading = true
    try {
      const res = await getQuarantineList({
        page: this.quarantinePage,
        page_size: PAGE_SIZE,
        ...(this.quarantinePathFilter ? { path_like: this.quarantinePathFilter } : {})
      })
      if (res.code === '200' && res.data) {
        this.quarantine = this.quarantine.concat(res.data.list ?? [])
        this.quarantineTotal = res.data.total ?? 0
        this.quarantinePage += 1
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.quarantineLoading = false
    }
  }

  private confirmRestore(item: QuarantineItem): void {
    this.$confirm(`确认恢复该文件到原位置？`, '恢复确认', { type: 'warning' })
      .then(() => this.restoreOne(item))
      .catch(() => undefined)
  }

  private async restoreOne(item: QuarantineItem): Promise<void> {
    this.busyPath = item.canonical_path
    try {
      const res = await restoreQuarantined({ canonical_paths: [item.canonical_path] })
      if (res.code === '200' && res.data) {
        if (res.data.rejected) {
          const reason = res.data.failed_list[0] ? res.data.failed_list[0].reason : ''
          this.$message.error(reason || '恢复被拒绝')
        } else {
          this.$message.success(`恢复完成${res.data.failed_count ? `：失败 ${res.data.failed_count} 个` : ''}`)
        }
        await this.reloadQuarantine()
      } else {
        this.$message.error(res.msg || '恢复失败')
      }
    } catch (e) {
      this.$message.error('恢复失败：' + extractErrorMessage(e))
    } finally {
      this.busyPath = ''
    }
  }

  private confirmPurge(item: QuarantineItem): void {
    this.$confirm('确认彻底删除该文件？此操作不可恢复，文件将被永久删除！', '彻底删除确认', {
      type: 'error',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消'
    })
      .then(() => this.purgeOne(item))
      .catch(() => undefined)
  }

  private async purgeOne(item: QuarantineItem): Promise<void> {
    this.busyPath = item.canonical_path
    try {
      const res = await purgeQuarantineNow({ canonical_paths: [item.canonical_path] })
      if (res.code === '200' && res.data) {
        const data = res.data
        if (data.status === 'already_running') {
          this.$message.info('该文件已在彻底删除任务中处理')
        } else if (data.task_id) {
          this.$message.success(`彻底删除任务已提交（${data.task_id.slice(0, 8)}），完成后将在通知中心提醒`)
        } else {
          this.$message.warning(data.error_message || '任务提交失败')
        }
        await this.reloadQuarantine()
      } else {
        this.$message.error(res.msg || '彻底删除失败')
      }
    } catch (e) {
      this.$message.error('彻底删除失败：' + extractErrorMessage(e))
    } finally {
      this.busyPath = ''
    }
  }

  // ========== 展示工具 ==========

  private statusText(item: OrphanFileItem): string {
    if (item.is_deleted) return '已清理'
    if (item.is_ignored) return '已忽视'
    return '待清理'
  }

  private statusTagType(item: OrphanFileItem): string {
    if (item.is_deleted) return 'info'
    if (item.is_ignored) return 'warning'
    return 'danger'
  }

  private formatSize(size: number | null | undefined): string {
    return formatFileSize(size)
  }

  private formatTime(value: string | null | undefined): string {
    if (!value) return '—'
    return value.replace('T', ' ').slice(0, 19)
  }
}
</script>

<style scoped>
.m-orphan-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.m-orphan-tab {
  flex: 1;
  border: 1px solid #e4e7ed;
  background: #fff;
  border-radius: 8px;
  padding: 8px 4px;
  font-size: 13px;
  color: #606266;
}

.m-orphan-tab.is-active {
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
  background: rgba(5, 150, 105, 0.06);
}

.m-orphan-scan {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.m-orphan-scan-time {
  font-size: 12px;
  color: #909399;
}

.m-orphan-scan-stats {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.m-orphan-scan-block {
  margin-top: 4px;
  font-size: 12px;
  color: #e6a23c;
}

.m-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.m-toolbar .el-select,
.m-toolbar .el-input {
  flex: 1;
}

.m-orphan-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-orphan-path {
  font-size: 13px;
  color: #303133;
  font-weight: 600;
  word-break: break-all;
  line-height: 1.4;
  max-height: 3.9em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.m-orphan-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.m-orphan-meta-text {
  font-size: 12px;
  color: #909399;
}

.m-orphan-copies {
  font-size: 11px;
  color: #409eff;
  background: rgba(64, 158, 255, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.m-orphan-sub {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  font-size: 11px;
  color: #c0c4cc;
  flex-wrap: wrap;
}

.m-orphan-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
}

.m-orphan-actions .el-button {
  margin-left: 0;
  padding: 5px 10px;
}

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-orphan-footnote {
  margin-top: 14px;
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
