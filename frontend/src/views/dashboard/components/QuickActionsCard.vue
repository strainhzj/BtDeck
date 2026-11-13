<template>
  <div class="dash-qa-grid">
    <div
      class="dash-qa"
      role="button"
      tabindex="0"
      :aria-label="$t('dashboard.quick.addDownloader')"
      @click="go('/downloader/index')"
      @keypress.enter="go('/downloader/index')"
    >
      <lucide-icon name="server" />
      <span>{{ $t('dashboard.quick.addDownloader') }}</span>
    </div>
    <div
      class="dash-qa"
      role="button"
      tabindex="0"
      :aria-label="$t('dashboard.quick.addTorrent')"
      @click="go('/torrents/index')"
      @keypress.enter="go('/torrents/index')"
    >
      <lucide-icon name="download" />
      <span>{{ $t('dashboard.quick.addTorrent') }}</span>
    </div>
    <div
      class="dash-qa"
      role="button"
      tabindex="0"
      :aria-label="$t('dashboard.quick.advancedSearch')"
      @click="go('/query-templates/index')"
      @keypress.enter="go('/query-templates/index')"
    >
      <lucide-icon name="list-filter" />
      <span>{{ $t('dashboard.quick.advancedSearch') }}</span>
    </div>
    <div
      class="dash-qa"
      role="button"
      tabindex="0"
      :aria-label="$t('dashboard.quick.viewLogs')"
      @click="go('/logs/audit')"
      @keypress.enter="go('/logs/audit')"
    >
      <lucide-icon name="file-text" />
      <span>{{ $t('dashboard.quick.viewLogs') }}</span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * QuickActionsCard —— 快捷操作 widget（仪表盘一期 W2，纯前端导航）。
 *
 * 四项对齐验收示意图：添加下载器 / 添加种子 / 高级搜索（查询模板页）/
 * 查看日志。图标 Lucide（替换原 emoji）。
 */
import { Component, Vue } from 'vue-property-decorator'

@Component({ name: 'QuickActionsCard' })
export default class QuickActionsCard extends Vue {
  private go(path: string) {
    this.$router.push(path).catch(() => undefined)
  }
}
</script>
