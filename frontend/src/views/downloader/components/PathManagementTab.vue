<template>
  <div class="path-management-tab">
    <!-- 子页签切换 -->
    <el-tabs v-model="activeSubTab" type="card" class="management-sub-tabs">
      <!-- 子页签1: 路径映射配置 -->
      <el-tab-pane label="路径映射配置" name="pathMapping">
        <div class="sub-tab-content">
          <!-- 原有的路径映射配置组件 -->
          <PathMappingConfig
            v-if="downloader"
            :downloader="downloader"
            :settings="settings"
            ref="pathMappingConfigRef"
          />
          <div v-else class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <h3>请先保存下载器基本信息</h3>
            <p>路径映射配置需要下载器创建后才能使用</p>
          </div>
        </div>
      </el-tab-pane>

      <!-- 子页签2: 下载器路径管理 -->
      <el-tab-pane label="下载器路径管理" name="downloaderPaths">
        <div class="sub-tab-content">
          <!-- 下载器路径管理组件 -->
          <DownloaderPathManagement
            v-if="downloader"
            :downloader="downloader"
            ref="downloaderPathManagementRef"
          />
          <div v-else class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <h3>请先保存下载器基本信息</h3>
            <p>下载器路径管理需要下载器创建后才能使用</p>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import {
  Downloader,
  DownloaderSettings
} from '../types'
import PathMappingConfig from './PathMappingTab.vue'
import DownloaderPathManagement from './DownloaderPathManagement.vue'

@Component({
  name: 'PathManagementTab',
  components: {
    PathMappingConfig,
    DownloaderPathManagement
  }
})
export default class PathManagementTab extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null
  @Prop({ default: () => ({}) as DownloaderSettings }) settings!: DownloaderSettings

  // 当前激活的子页签
  private activeSubTab = 'pathMapping'

  // 监听下载器变化，重置到第一个子页签
  @Watch('downloader')
  onDownloaderChange() {
    this.activeSubTab = 'pathMapping'
  }

  // 获取路径映射配置数据（供父组件调用）
  public getPathMappingData() {
    return (this.$refs.pathMappingConfigRef as any)?.getFormData()
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.path-management-tab {
  padding: 0;
}

.management-sub-tabs {
  border: none;
  box-shadow: none;

  ::v-deep .el-tabs__header {
    background: var(--color-bg-secondary);
    margin: 0 0 var(--spacing-lg) 0;
    padding: var(--spacing-sm) var(--spacing-lg);
    border-radius: var(--radius-lg);
    border: 1px solid var(--color-border-primary);
  }

  ::v-deep .el-tabs__content {
    padding: 0;
  }

  ::v-deep .el-tabs__item {
    border: none;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: var(--font-weight-medium);
    color: var(--color-text-secondary);
    transition: all var(--transition-base);
    display: inline-flex;
    align-items: center;
    justify-content: center;

    &:hover {
      color: var(--color-primary);
    }

    &.is-active {
      color: var(--color-primary);
      background: var(--color-primary-lightest);
      border-radius: var(--radius-md);
    }
  }
}

.sub-tab-content {
  padding: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl) var(--spacing-xl);
  min-height: 300px;
  text-align: center;

  .empty-icon {
    width: 64px;
    height: 64px;
    color: var(--color-text-tertiary);
    margin-bottom: var(--spacing-lg);
    opacity: 0.5;
  }

  h3 {
    font-size: 18px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
    margin: 0 0 var(--spacing-sm) 0;
  }

  p {
    font-size: 14px;
    color: var(--color-text-secondary);
    margin: 0;
    line-height: 1.5;
  }
}
</style>
