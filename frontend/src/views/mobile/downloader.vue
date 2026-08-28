<template>
  <div class="m-downloader">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div class="m-toolbar">
      <span class="m-toolbar-title">共 {{ list.length }} 个下载器</span>
      <el-button size="small" type="primary" plain icon="el-icon-plus" @click="openCreate">新增下载器</el-button>
    </div>
    <div v-if="loading && !list.length" class="m-hint">加载中…</div>
    <template v-else-if="list.length">
      <div v-for="d in list" :key="d.id" class="m-dl-card">
        <div class="m-dl-head">
          <span class="m-dl-name">{{ d.nickname || d.downloaderId || '-' }}</span>
          <span class="m-dl-badge" :class="isOnline(d) ? 'is-online' : 'is-offline'">
            {{ isOnline(d) ? '在线' : '离线' }}
          </span>
        </div>
        <div class="m-dl-meta">
          <span>{{ d.downloaderTypeName || downloaderTypeLabel(d.downloaderType) }}</span>
          <span class="m-dl-host">{{ hostDisplay(d) }}</span>
        </div>
        <div class="m-dl-actions">
          <el-button
            size="mini"
            :loading="testingId === d.id"
            @click="testOne(d)"
          >
            测试
          </el-button>
          <el-button
            size="mini"
            :loading="syncingId === d.id"
            @click="syncOne(d)"
          >
            同步
          </el-button>
          <el-button size="mini" @click="openSettings(d)">设置</el-button>
          <el-button size="mini" @click="openEdit(d)">编辑</el-button>
          <el-button size="mini" type="danger" plain :disabled="busyId === d.id" @click="removeOne(d)">删除</el-button>
        </div>
      </div>

      <div class="m-dl-footnote">路径映射在设置 → 路径维护中配置；能力矩阵等高级信息见桌面版</div>
    </template>
    <div v-else class="m-hint">暂无下载器</div>

    <!-- 新增/编辑：复用桌面 DownloaderDialog（submit 后由本页显式落库） -->
    <downloader-dialog
      :visible.sync="editDialogVisible"
      :downloader="editingItem"
      @submit="onDialogSubmit"
    />
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getList,
  testConnection,
  syncDownloader,
  addDownloader,
  upDownloader,
  deleteDownloader
} from '@/api/downloader'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import DownloaderDialog from '@/views/downloader/components/DownloaderDialog.vue'
import { Downloader } from '@/views/downloader/types'

/** 单个下载器的移动卡片形状（getList 返回字段的子集，camelCase 与后端 VO 一致） */
interface MobileDownloaderItem {
  id: string
  nickname?: string | null
  downloaderId?: string | null
  host?: string | null
  port?: string | null
  downloaderType?: number | null
  downloaderTypeName?: string | null
  connectStatus?: string | null
}

/**
 * 移动下载器页（Phase 4 M2 升级为完整管理）：
 * 复用桌面 /downloader 全套 API——监控（在线徽标/测试/同步）+ 新增/编辑
 * （DownloaderDialog 复用，submit 由本页显式调 add/up 落库）+ 删除；
 * 高级设置（速度/调度/路径/标签）经 /m/downloader/settings/:id 承载。
 */
@Component({
  name: 'MobileDownloader',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    'downloader-dialog': DownloaderDialog
  }
})
export default class MobileDownloader extends Mixins(PullToRefresh) {
  private loading = false
  private list: MobileDownloaderItem[] = []
  private testingId = ''
  private syncingId = ''
  private busyId = ''
  private editDialogVisible = false
  private editingItem: Downloader | null = null

  mounted(): void {
    this.load()
    // 种子页空态 CTA 直达新增（?create=1）：一步弹出新增表单，省掉找按钮
    if (this.$route.query.create === '1') {
      this.openCreate()
    }
  }

  protected async onPullRefresh(): Promise<void> {
    await this.load()
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getList({ page: 1, pageSize: 100 })
      if (res.code === '200' && Array.isArray(res.data)) {
        this.list = res.data
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private async testOne(item: MobileDownloaderItem): Promise<void> {
    if (!item.id) return
    this.testingId = item.id
    try {
      const res = await testConnection(item.id)
      // 后端约定：信封 code=200 仅代表请求执行成功，连接成败看 data.success（与桌面端 handleTest 同口径）
      const result = (res.data ?? {}) as { success?: boolean, message?: string }
      if (res.code === '200' && result.success) {
        this.$message.success(`${item.nickname || item.id}：连接成功`)
        // 立即刷新列表以同步 connectStatus 缓存
        await this.load()
      } else {
        this.$message.error(`${item.nickname || item.id}：${result.message || res.msg || '连接失败'}`)
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.testingId = ''
    }
  }

  private async syncOne(item: MobileDownloaderItem): Promise<void> {
    if (!item.id) return
    this.syncingId = item.id
    try {
      const res = await syncDownloader(item.id)
      if (res.code === '200') {
        this.$message.success(`${item.nickname || item.id}：同步完成`)
        await this.load()
      } else {
        this.$message.error(res.msg || '同步失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.syncingId = ''
    }
  }

  private openSettings(item: MobileDownloaderItem): void {
    this.$router
      .push(`/m/downloader/settings/${encodeURIComponent(item.id)}`)
      .catch(() => undefined)
  }

  private openCreate(): void {
    this.editingItem = null
    this.editDialogVisible = true
  }

  private openEdit(item: MobileDownloaderItem): void {
    this.editingItem = item as unknown as Downloader
    this.editDialogVisible = true
  }

  /** 桌面对话框 submit 仅抛表单数据不落库，此处显式按模式调新增/更新 */
  private async onDialogSubmit(formData: object): Promise<void> {
    try {
      const res = this.editingItem
        ? await upDownloader({ ...(formData as { id?: string }), id: this.editingItem.id ?? this.editingItem.downloaderId })
        : await addDownloader(formData)
      if (res.code === '200') {
        this.$message.success(this.editingItem ? '下载器已更新' : '下载器已添加')
        this.editDialogVisible = false
        await this.load()
      } else {
        this.$message.error(res.msg || '保存失败')
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  private removeOne(item: MobileDownloaderItem): void {
    this.$confirm(
      `删除下载器「${item.nickname || item.id}」？仅移除配置记录，不影响远端下载器与其数据。`,
      '删除确认',
      { type: 'warning' }
    )
      .then(async() => {
        this.busyId = item.id
        try {
          const res = await deleteDownloader(item.id)
          if (res.code === '200') {
            this.$message.success('下载器已删除')
            await this.load()
          } else {
            this.$message.error(res.msg || '删除失败')
          }
        } catch (e) {
          this.$message.error(extractErrorMessage(e))
        } finally {
          this.busyId = ''
        }
      })
      .catch(() => undefined)
  }

  private isOnline(item: MobileDownloaderItem): boolean {
    return item.connectStatus === '1'
  }

  /** host 本身可能已含端口（如 "1.2.3.4:8080"），含冒号时不再重复拼 port */
  private hostDisplay(item: MobileDownloaderItem): string {
    const host = item.host || ''
    const port = item.port ? String(item.port) : ''
    if (!port || host.includes(':')) return host
    return `${host}:${port}`
  }

  private downloaderTypeLabel(type?: number | null): string {
    if (type === 1) return 'Transmission'
    if (type === 0) return 'qBittorrent'
    return '未知类型'
  }
}
</script>

<style scoped>
.m-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.m-toolbar-title {
  font-size: 13px;
  color: #606266;
}

.m-dl-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}

.m-dl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.m-dl-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-dl-badge {
  flex-shrink: 0;
  margin-left: 8px;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.m-dl-badge.is-online {
  color: var(--color-primary);
  background: var(--color-primary-lightest);
}

.m-dl-badge.is-offline {
  color: #909399;
  background: #f4f4f5;
}

.m-dl-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

.m-dl-host {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: 8px;
}

.m-dl-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.m-dl-actions .el-button {
  margin-left: 0;
  padding: 5px 10px;
}

.m-dl-footnote {
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
  padding: 4px 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>

<!-- 新增/编辑对话框挂 body（append-to-body 缺省），窄视口下压宽度提升可用性 -->
<style>
@media (max-width: 768px) {
  .downloader-dialog {
    width: 94% !important;
  }
}
</style>
