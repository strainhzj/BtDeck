<template>
  <div class="rss-manager-page">
    <div class="page-head">
      <div class="page-head__text">
        <h2>
          <LucideIcon name="rss" :size="18" />
          {{ $t('navigation.routes.rssManagement') }}
        </h2>
        <p>{{ $t('downloader.rssManager.desc') }}</p>
      </div>
    </div>

    <!-- 下载器选择器（跨下载器统一管理入口） -->
    <div class="downloader-bar">
      <span class="downloader-bar__label">{{ $t('downloader.rssManager.selectDownloader') }}</span>
      <el-select
        v-model="selectedId"
        filterable
        size="small"
        style="min-width: 240px;"
        :placeholder="$t('downloader.rssManager.selectPlaceholder')"
        @change="handleSelect"
      >
        <el-option
          v-for="item in downloaderOptions"
          :key="item.downloaderId"
          :label="optionLabel(item)"
          :value="item.downloaderId"
        />
      </el-select>
      <span v-if="selected && selected.downloaderType === 2" class="downloader-bar__hint">
        {{ $t('downloader.rssManager.rtorrentUnsupported') }}
      </span>
    </div>

    <!-- 复用下载器设置弹窗的 RSS 页签组件（多入口共享同一实现） -->
    <div class="panel-shell" :class="{'is-empty': !selected}">
      <rss-subscription-tab :downloader="selected" />
    </div>
  </div>
</template>

<script lang="ts">
import { Message } from 'element-ui'
import { Component, Vue } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'
import { extractErrorMessage } from '@/utils/formatters'
import { getList } from '@/api/downloader'
import { Downloader } from '@/views/downloader/types'
import RssSubscriptionTab from '@/views/downloader/components/RssSubscriptionTab.vue'

@Component({
  name: 'RssManagerPage',
  components: { LucideIcon, RssSubscriptionTab }
})
export default class RssManagerPage extends Vue {
  private downloaderOptions: Downloader[] = []
  private selectedId = ''
  private selected: Downloader | null = null

  mounted() {
    this.loadDownloaders()
  }

  private async loadDownloaders(): Promise<void> {
    try {
      const response = await getList({})
      this.downloaderOptions = (response.data as Downloader[]).filter(
        (item: Downloader) => item.downloaderType === 0 || item.downloaderType === 1
      )
      if (this.downloaderOptions.length > 0 && !this.selectedId) {
        this.selectedId = this.downloaderOptions[0].downloaderId
        this.selected = this.downloaderOptions[0]
      }
    } catch (error) {
      Message.error(extractErrorMessage(error))
    }
  }

  private handleSelect(id: string): void {
    this.selected = this.downloaderOptions.find(item => item.downloaderId === id) || null
  }

  private optionLabel(item: Downloader): string {
    return `${item.nickname} (${item.downloaderTypeName || ''})`
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/settings-panel.scss';

.rss-manager-page {
  padding: 18px 20px 28px;

  .page-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    &__text {
      h2 {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 0 0 6px;
        font-size: 20px;
        @extend %settings-card-title;
      }

      p {
        margin: 0;
        font-size: 13px;
        opacity: 0.65;
      }
    }
  }
}

.downloader-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;

  &__label {
    font-size: 13px;
    font-weight: 600;
  }

  &__hint {
    font-size: 12px;
    color: #e6a23c;
  }
}

.panel-shell {
  max-width: 1080px;

  &.is-empty {
    display: none;
  }
}

@media (max-width: 780px) {
  .rss-manager-page {
    padding: 12px 12px 20px;
  }

  .downloader-bar {
    align-items: stretch;
    flex-direction: column;

    ::v-deep .el-select {
      width: 100%;
    }
  }
}
</style>
