<template>
  <div class="m-rss">
    <!-- 工具栏：下载器切换（跨下载器统一管理，整页复用桌面 RSS 组件） -->
    <div class="m-toolbar">
      <el-select v-model="selectedId" size="small" filterable placeholder="选择下载器" style="flex: 1;" @change="handleSelect">
        <el-option
          v-for="item in downloaderOptions"
          :key="item.downloaderId"
          :label="`${item.nickname} (${item.downloaderTypeName || ''})`"
          :value="item.downloaderId"
        />
      </el-select>
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="loadDownloaders">刷新</el-button>
    </div>

    <!-- 复用桌面 RssSubscriptionTab（组件内含 ≤780 移动适配） -->
    <rss-subscription-tab v-if="selected" :downloader="selected" />
    <div v-else class="m-hint">
      {{ loading ? '加载下载器中…' : '暂无可用的 qB/TR 下载器' }}
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { getList } from '@/api/downloader'
import { Downloader } from '@/views/downloader/types'
import RssSubscriptionTab from '@/views/downloader/components/RssSubscriptionTab.vue'

@Component({
  name: 'MobileRssPage',
  components: { RssSubscriptionTab }
})
export default class MobileRssPage extends Vue {
  private downloaderOptions: Downloader[] = []
  private selectedId = ''
  private selected: Downloader | null = null
  private loading = false

  mounted() {
    this.loadDownloaders()
  }

  private async loadDownloaders(): Promise<void> {
    this.loading = true
    try {
      const response = await getList({})
      this.downloaderOptions = (response.data as Downloader[]).filter(
        (item: Downloader) => item.downloaderType === 0 || item.downloaderType === 1
      )
      if (this.downloaderOptions.length > 0) {
        const found = this.downloaderOptions.find(item => item.downloaderId === this.selectedId)
        this.selected = found || this.downloaderOptions[0]
        this.selectedId = this.selected.downloaderId
      } else {
        this.selected = null
        this.selectedId = ''
      }
    } catch {
      this.downloaderOptions = []
      this.selected = null
    } finally {
      this.loading = false
    }
  }

  private handleSelect(id: string): void {
    this.selected = this.downloaderOptions.find(item => item.downloaderId === id) || null
  }
}
</script>

<style lang="scss" scoped>
.m-rss {
  padding: 10px 12px 20px;
}

.m-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.m-hint {
  text-align: center;
  padding: 48px 16px;
  font-size: 13px;
  opacity: 0.6;
}
</style>
