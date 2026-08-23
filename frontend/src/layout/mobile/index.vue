<template>
  <div class="mobile-layout">
    <header class="mobile-header">
      <span class="mobile-header-title">BtDeck</span>
      <el-button type="text" size="mini" class="mobile-header-desktop" @click="switchToDesktop">
        桌面版
      </el-button>
    </header>

    <main class="mobile-content">
      <router-view />
    </main>

    <nav class="mobile-tabbar">
      <button
        v-for="tab in tabs"
        :key="tab.path"
        type="button"
        class="mobile-tab"
        :class="{'is-active': isActive(tab)}"
        @click="go(tab)"
      >
        <span class="mobile-tab-label">{{ tab.label }}</span>
      </button>
    </nav>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { setStoredUiMode } from '@/utils/ui-mode'

interface MobileTab {
  label: string
  path: string
}

/**
 * 移动布局壳（dual-mode-client Phase 4 M1）：
 * 顶部标题 + 切桌面出口、内容区 router-view、底部 Tab 导航。
 * 原则：不自锁——任何时刻都能切回桌面版（偏好持久化）。
 */
@Component({ name: 'MobileLayout' })
export default class MobileLayout extends Vue {
  private tabs: MobileTab[] = [
    { label: '仪表盘', path: '/m/dashboard' },
    { label: '种子', path: '/m/torrents' },
    { label: '通知', path: '/m/notifications' }
  ]

  private isActive(tab: MobileTab): boolean {
    return this.$route.path === tab.path || this.$route.path.startsWith(tab.path + '/')
  }

  private go(tab: MobileTab): void {
    if (!this.isActive(tab)) {
      this.$router.replace(tab.path).catch(() => undefined)
    }
  }

  private switchToDesktop(): void {
    setStoredUiMode('desktop')
    this.$router.replace('/dashboard').catch(() => undefined)
  }
}
</script>

<style scoped>
.mobile-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #f5f7fa;
}

.mobile-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 48px;
  background: #27303f;
  color: #fff;
}

.mobile-header-title {
  font-size: 16px;
  font-weight: 600;
}

.mobile-header-desktop {
  color: #cfd8e3;
  padding: 4px 0;
}

.mobile-content {
  flex: 1;
  padding: 12px 12px 72px;
  overflow-y: auto;
}

.mobile-tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  padding-bottom: env(safe-area-inset-bottom);
  z-index: 10;
}

.mobile-tab {
  flex: 1;
  height: 56px;
  border: none;
  background: transparent;
  color: #909399;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mobile-tab.is-active {
  color: #409eff;
  font-weight: 600;
}

.mobile-tab-label {
  line-height: 1.2;
}
</style>
