<template>
  <div class="m-downloader">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
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
          <span class="m-dl-host">{{ d.host }}{{ d.port ? ':' + d.port : '' }}</span>
        </div>
        <div class="m-dl-actions">
          <el-button
            size="mini"
            :loading="testingId === d.id"
            @click="testOne(d)"
          >
            测试连接
          </el-button>
        </div>
      </div>

      <div class="m-dl-footnote">下载器的编辑、设置与路径映射请通过功能菜单 →「下载器管理」（桌面版页面）操作</div>
    </template>
    <div v-else class="m-hint">暂无下载器</div>
    <el-button class="m-refresh" size="small" :loading="loading" @click="load">刷新</el-button>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { getList, testConnection } from '@/api/downloader'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

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
 * 移动下载器监控页（Phase 4 M1，2026-08-24 提入底部 Tab 第一梯队）：
 * 复用桌面 /downloader/getList 与 /downloader/testConnection，仅做只读监控
 * （在线徽标 + 连接测试）；管理操作仍由抽屉「下载器管理」桌面页承载。
 */
@Component({
  name: 'MobileDownloader',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileDownloader extends Mixins(PullToRefresh) {
  private loading = false
  private list: MobileDownloaderItem[] = []
  private testingId = ''

  mounted(): void {
    this.load()
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
      if (res.code === '200') {
        this.$message.success(`${item.nickname || item.id}：连接成功`)
        // 立即刷新列表以同步 connectStatus 缓存
        await this.load()
      } else {
        this.$message.error(`${item.nickname || item.id}：${res.msg || '连接失败'}`)
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.testingId = ''
    }
  }

  private isOnline(item: MobileDownloaderItem): boolean {
    return item.connectStatus === '1'
  }

  private downloaderTypeLabel(type?: number | null): string {
    if (type === 1) return 'Transmission'
    if (type === 0) return 'qBittorrent'
    return '未知类型'
  }
}
</script>

<style scoped>
.m-downloader {
  padding-bottom: 8px;
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
  margin-top: 8px;
}

.m-dl-footnote {
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
  padding: 4px 0;
}

.m-refresh {
  display: flex;
  margin: 12px auto 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
