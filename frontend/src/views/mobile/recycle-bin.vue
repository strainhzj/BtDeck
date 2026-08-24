<template>
  <div class="m-recycle-bin">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-toolbar">
      <el-input
        v-model="search"
        size="small"
        placeholder="搜索种子名称"
        clearable
        prefix-icon="el-icon-search"
        @keyup.enter.native="reload"
        @clear="reload"
      />
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="reload">刷新</el-button>
    </div>

    <div v-if="!loading && list.length === 0" class="m-hint">
      {{ search ? '没有匹配的回收站记录' : '回收站为空' }}
    </div>

    <div v-for="item in list" :key="item.info_id" class="m-rb-card">
      <div class="m-rb-name" :title="item.name">{{ item.name }}</div>
      <div class="m-rb-meta">
        <el-tag size="mini" type="info">已删除</el-tag>
        <span class="m-rb-meta-text">{{ formatSize(item.size) }}</span>
        <span class="m-rb-meta-text">{{ item.downloader_name }}</span>
      </div>
      <div class="m-rb-path" :title="item.save_path">{{ item.save_path }}</div>
      <div class="m-rb-time">删除于 {{ formatTime(item.deleted_at) }}</div>
      <div class="m-rb-actions">
        <el-button
          size="mini"
          :disabled="busyKey === item.info_id || !item.torrent_id"
          @click="restore(item)"
        >
          {{ item.torrent_id ? '恢复' : '无法恢复' }}
        </el-button>
        <el-button
          size="mini"
          type="danger"
          plain
          :disabled="busyKey === item.info_id || !item.torrent_id"
          @click="destroy(item)"
        >
          彻底删除
        </el-button>
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

    <div class="m-rb-footnote">
      批量清理、按天数清理与上传种子文件手动恢复请在桌面版「回收站」页操作
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getRecycleBinList,
  restoreTorrents,
  manualCleanup,
  RecycleBinItem
} from '@/api/recycle-bin'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { formatTorrentSize } from '@/views/mobile/torrent-status'

const PAGE_SIZE = 20

/**
 * 移动回收站（Phase 4 M2）：复用 /recycle-bin API 的卡片列表；
 * 只做单条恢复/彻底删除（降低移动端误触风险），批量与手动恢复（上传
 * 种子文件）保留桌面版承载。
 */
@Component({
  name: 'MobileRecycleBin',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileRecycleBin extends Mixins(PullToRefresh) {
  private list: RecycleBinItem[] = []
  private total = 0
  private page = 1
  private loading = false
  private search = ''
  private busyKey = ''

  mounted(): void {
    this.reload()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.reload()
  }

  private async reload(): Promise<void> {
    this.page = 1
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
      const res = await getRecycleBinList({
        page: this.page,
        page_size: PAGE_SIZE,
        ...(this.search ? { search: this.search } : {})
      })
      if (res.code === '200' && res.data) {
        this.list = this.list.concat(res.data.list ?? [])
        this.total = res.data.total ?? 0
        this.page += 1
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private async restore(item: RecycleBinItem): Promise<void> {
    if (!item.torrent_id) return
    this.busyKey = item.info_id
    try {
      const res = await restoreTorrents({ torrent_ids: [item.torrent_id] })
      if (res.code === '200' && res.data) {
        const { success_count: ok, failed_count: fail } = res.data
        if (fail > 0) {
          this.$message.warning(`恢复 ${ok} 条成功、${fail} 条失败`)
        } else {
          this.$message.success(`已恢复「${item.name}」`)
        }
        await this.reload()
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busyKey = ''
    }
  }

  private destroy(item: RecycleBinItem): void {
    if (!item.torrent_id) return
    this.$confirm(
      `彻底删除「${item.name}」？种子与文件将被永久删除，无法恢复。`,
      '彻底删除确认',
      { type: 'warning', confirmButtonText: '永久删除', cancelButtonText: '取消' }
    )
      .then(async() => {
        this.busyKey = item.info_id
        try {
          const res = await manualCleanup({ torrent_ids: [item.torrent_id as string] })
          if (res.code === '200' && res.data && res.data.failed_count > 0) {
            this.$message.error(`删除失败：${res.data.failed_list?.[0]?.error || '未知原因'}`)
          } else {
            this.$message.success('已彻底删除')
          }
          await this.reload()
        } catch (e) {
          this.$message.error(extractErrorMessage(e))
        } finally {
          this.busyKey = ''
        }
      })
      .catch(() => undefined)
  }

  private formatSize(bytes: number): string {
    return formatTorrentSize(bytes)
  }

  private formatTime(value: string): string {
    if (!value) return '-'
    return value.replace('T', ' ').slice(0, 16)
  }
}
</script>

<style scoped>
.m-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.m-toolbar .el-input {
  flex: 1;
}

.m-rb-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-rb-name {
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

.m-rb-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 2px;
}

.m-rb-meta-text {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-rb-path {
  font-size: 12px;
  color: #c0c4cc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-rb-time {
  margin-top: 2px;
  font-size: 11px;
  color: #c0c4cc;
}

.m-rb-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.m-rb-actions .el-button {
  margin-left: 0;
  padding: 5px 10px;
}

.m-load-more {
  display: flex;
  margin: 8px auto 0;
}

.m-rb-footnote {
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
