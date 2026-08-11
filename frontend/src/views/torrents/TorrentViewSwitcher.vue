<template>
  <div class="torrent-view-switcher">
    <component :is="currentViewComponent" ref="currentViewRef" />
  </div>
</template>

<script lang="ts">
import { Component, Vue, Watch } from 'vue-property-decorator'
import { ViewModeModule, ViewModeType } from '@/store/modules/viewMode'
import ListView from './index.vue'
import TraditionalView from './TraditionalView.vue'

@Component({
  name: 'TorrentViewSwitcher',
  components: {
    ListView,
    TraditionalView
  }
})
export default class extends Vue {
  private viewModeModule = ViewModeModule
  private sharedState: any = null

  get currentViewComponent() {
    return this.viewModeModule.currentMode === 'traditional' ? 'TraditionalView' : 'ListView'
  }

  get currentMode(): ViewModeType {
    return this.viewModeModule.currentMode
  }

  // 监听视图模式变化，确保状态不丢失
  @Watch('currentMode')
  onModeChange(newMode: ViewModeType, oldMode: ViewModeType) {
    console.log(`[TorrentViewSwitcher] 视图切换: ${oldMode} → ${newMode}`)

    // 在切换前保存当前视图状态
    this.saveCurrentViewState()

    // 在切换后恢复状态到新视图
    this.$nextTick(() => {
      this.restoreViewState()
    })
  }

  // 保存当前视图的状态
  private saveCurrentViewState() {
    const currentView = this.$refs.currentViewRef as any
    if (!currentView) return

    // 提取可共享的状态
    this.sharedState = {
      listQuery: { ...currentView.listQuery },
      currentPage: currentView.currentPage,
      pageSize: currentView.pageSize,
      multipleSelection: [...currentView.multipleSelection],
      list: [...currentView.list],
      total: currentView.total,
      downloaderList: [...currentView.downloaderList],
      showingDuplicates: currentView.showingDuplicates === true
    }

    console.log('[TorrentViewSwitcher] 状态已保存:', {
      mode: this.currentMode,
      total: this.sharedState.total,
      selected: this.sharedState.multipleSelection.length
    })
  }

  // 恢复状态到新视图
  private restoreViewState() {
    if (!this.sharedState) return

    const newView = this.$refs.currentViewRef as any
    if (!newView) return

    // 恢复共享状态
    Object.assign(newView.listQuery, this.sharedState.listQuery)
    newView.currentPage = this.sharedState.currentPage
    newView.pageSize = this.sharedState.pageSize
    newView.multipleSelection = this.sharedState.multipleSelection
    newView.list = this.sharedState.list
    newView.total = this.sharedState.total
    newView.downloaderList = this.sharedState.downloaderList
    newView.showingDuplicates = this.sharedState.showingDuplicates

    console.log('[TorrentViewSwitcher] 状态已恢复:', {
      mode: this.currentMode,
      total: newView.total,
      selected: newView.multipleSelection.length
    })
  }

  // 初始化时加载状态（从 localStorage 读取视图模式）
  public mounted() {
    console.log('[TorrentViewSwitcher] 初始化，当前模式:', this.currentMode)
  }
}
</script>

<style lang="scss" scoped>
.torrent-view-switcher {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
}
</style>
