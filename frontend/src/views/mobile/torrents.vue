<template>
  <div class="m-torrents">
    <div class="m-toolbar">
      <el-select v-model="statusFilter" size="small" placeholder="全部状态" clearable @change="reload">
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reload">刷新</el-button>
    </div>

    <div v-if="!loading && list.length === 0" class="m-hint">暂无种子</div>

    <div
      v-for="t in list"
      :key="`${t.downloaderId}-${t.hash}`"
      class="m-torrent-card"
    >
      <div class="m-torrent-name" :title="t.name">{{ t.name }}</div>
      <div class="m-torrent-meta">
        <el-tag size="mini" :type="statusTagType(t.status)">{{ statusLabel(t.status) }}</el-tag>
        <span class="m-torrent-meta-text">{{ t.downloaderName }}</span>
        <span class="m-torrent-meta-text">{{ formatSize(t.size) }}</span>
      </div>
      <el-progress
        :percentage="progressOf(t)"
        :status="t.status === 'error' ? 'exception' : undefined"
        :stroke-width="6"
        :show-text="false"
      />
      <div class="m-torrent-progress-text">
        {{ progressOf(t).toFixed(1) }}%<template v-if="t.errorReason"> · {{ t.errorReason }}</template>
      </div>
      <div class="m-torrent-actions">
        <el-button size="mini" :disabled="actionBusy(t)" @click="pause(t)">暂停</el-button>
        <el-button size="mini" :disabled="actionBusy(t)" @click="resume(t)">恢复</el-button>
        <el-button size="mini" type="danger" plain :disabled="actionBusy(t)" @click="remove(t)">删除</el-button>
      </div>
    </div>

    <el-button
      v-if="list.length < total"
      class="m-load-more"
      size="small"
      :loading="loading"
      @click="loadMore"
    >
      加载更多（{{ list.length }}/{{ total }}）
    </el-button>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  getTorrentList,
  pauseTorrents,
  resumeTorrents,
  deleteTorrents,
  Torrent
} from '@/api/torrents'
import { extractErrorMessage } from '@/utils/formatters'

interface StatusOption {
  label: string
  value: string
}

const PAGE_SIZE = 20

/** 移动种子卡片列表（Phase 4 M1）：复用 getList API 与常用操作（暂停/恢复/删除入回收站） */
@Component({ name: 'MobileTorrents' })
export default class MobileTorrents extends Vue {
  private list: Torrent[] = []
  private total = 0
  private loading = false
  private statusFilter = ''
  private busyKey = ''

  private statusOptions: StatusOption[] = [
    { label: '下载中', value: 'downloading' },
    { label: '做种中', value: 'seeding' },
    { label: '已暂停', value: 'paused' },
    { label: '错误', value: 'error' }
  ]

  mounted(): void {
    this.reload()
  }

  private async reload(): Promise<void> {
    this.list = []
    this.total = 0
    await this.fetchPage()
  }

  private async loadMore(): Promise<void> {
    await this.fetchPage()
  }

  private async fetchPage(): Promise<void> {
    this.loading = true
    try {
      const res = await getTorrentList({
        skip: this.list.length,
        limit: PAGE_SIZE,
        sort_by: 'added_date',
        sort_order: 'desc',
        ...(this.statusFilter ? { status: this.statusFilter } : {})
      })
      if (res.code === '200' && res.data) {
        this.list = this.list.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private actionBusy(t: Torrent): boolean {
    return this.busyKey === this.keyOf(t)
  }

  private keyOf(t: Torrent): string {
    return `${t.downloaderId}-${t.hash}`
  }

  private async pause(t: Torrent): Promise<void> {
    await this.withBusy(t, () => pauseTorrents({ downloader_id: t.downloaderId, hashes: [t.hash] }))
  }

  private async resume(t: Torrent): Promise<void> {
    await this.withBusy(t, () => resumeTorrents({ downloader_id: t.downloaderId, hashes: [t.hash] }))
  }

  private remove(t: Torrent): void {
    this.$confirm(`删除种子「${t.name}」？文件移入回收站，可从回收站恢复。`, '删除确认', { type: 'warning' })
      .then(async() => {
        await this.withBusy(t, () =>
          deleteTorrents({
            info_id: t.infoId,
            downloader_id: t.downloaderId,
            delete_data: 0,
            id_recycle: 1
          })
        )
        await this.reload()
      })
      .catch(() => undefined)
  }

  private async withBusy(t: Torrent, action: () => Promise<{ code?: string }>): Promise<void> {
    this.busyKey = this.keyOf(t)
    try {
      const res = await action()
      if (res && res.code && res.code !== '200') return
      this.$message.success('操作成功')
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyKey = ''
    }
  }

  private progressOf(t: Torrent): number {
    const value = typeof t.progress === 'number' ? t.progress : 0
    return Math.min(100, Math.max(0, value))
  }

  private statusLabel(status: string): string {
    const found = this.statusOptions.find((opt) => opt.value === status)
    return found ? found.label : status
  }

  private statusTagType(status: string): string {
    switch (status) {
      case 'downloading':
        return 'primary'
      case 'seeding':
        return 'success'
      case 'paused':
        return 'info'
      case 'error':
        return 'danger'
      default:
        return 'warning'
    }
  }

  private formatSize(bytes: number): string {
    if (!bytes || bytes <= 0) return '-'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let value = bytes
    let unit = 0
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024
      unit += 1
    }
    return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`
  }
}
</script>

<style scoped>
.m-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.m-toolbar .el-select {
  flex: 1;
}

.m-torrent-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-torrent-name {
  font-size: 14px;
  color: #303133;
  line-height: 1.35;
  max-height: 2.7em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}

.m-torrent-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
}

.m-torrent-meta-text {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-torrent-progress-text {
  margin-top: 2px;
  font-size: 11px;
  color: #c0c4cc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-torrent-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.m-torrent-actions .el-button {
  margin-left: 0;
  padding: 5px 10px;
}

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
