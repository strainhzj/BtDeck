<template>
  <div class="mobile-layout">
    <header class="mobile-header">
      <button type="button" class="mobile-header-menu" aria-label="打开功能菜单" @click="drawerVisible = true">
        <span class="mobile-header-menu-bar" />
        <span class="mobile-header-menu-bar" />
        <span class="mobile-header-menu-bar" />
      </button>
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
        <span class="mobile-tab-label">
          {{ tab.label }}<span
            v-if="tab.path === '/m/notifications' && unreadCount > 0"
            class="mobile-tab-badge"
          >{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
        </span>
      </button>
    </nav>

    <el-drawer
      direction="ltr"
      size="78%"
      :visible.sync="drawerVisible"
      :with-header="false"
      custom-class="mobile-menu-drawer"
      :modal-append-to-body="true"
      append-to-body
    >
      <div class="mobile-menu">
        <div class="mobile-menu-header">
          <span class="mobile-menu-title">功能菜单</span>
          <button type="button" class="mobile-menu-close" aria-label="关闭菜单" @click="drawerVisible = false">
            ✕
          </button>
        </div>

        <div class="mobile-menu-group-title">移动版</div>
        <button
          v-for="item in mobileMenuItems"
          :key="item.path"
          type="button"
          class="mobile-menu-item"
          :class="{'is-active': isActive(item)}"
          @click="goMenuItem(item)"
        >
          <span>{{ item.label }}</span>
          <span v-if="isActive(item)" class="mobile-menu-item-current">当前</span>
        </button>

        <div class="mobile-menu-group-title">全部功能（桌面版页面）</div>
        <button
          v-for="item in desktopMenuItems"
          :key="item.path"
          type="button"
          class="mobile-menu-item"
          @click="goMenuItem(item)"
        >
          <span>{{ item.label }}</span>
          <span class="mobile-menu-item-arrow">›</span>
        </button>

        <div class="mobile-menu-footer">
          <el-button size="small" class="mobile-menu-desktop-btn" @click="switchToDesktop">
            完整桌面版
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { setStoredUiMode } from '@/utils/ui-mode'
import { NotificationModule } from '@/store/modules/notification'

interface MobileTab {
  label: string
  path: string
}

const UNREAD_POLL_INTERVAL_MS = 60000

/**
 * 移动布局壳（dual-mode-client Phase 4 M1）：
 * 顶部标题 + 汉堡功能菜单 + 切桌面出口、内容区 router-view、底部 Tab 导航。
 * 原则：不自锁——任何时刻都能切回桌面版（偏好持久化）。
 *
 * 主题色统一走全局 var(--color-primary)（与桌面端 #059669 同源）；
 * 完整功能 11 项塞不进底部 Tab（>5 不可用），低频管理页经抽屉跳
 * 桌面版路由承载（桌面管理页有窄屏断点基础），返回键/刷新回移动版。
 *
 * 通知未读角标（M1 余项）：复用桌面同款 Vuex NotificationModule.unreadCount
 * （/notifications/unread-count 现有接口），挂载即拉一次 + 60s 轮询（移动端
 * 省电节奏；桌面 Navbar 无轮询先例，此处为移动新增行为）。
 */
@Component({ name: 'MobileLayout' })
export default class MobileLayout extends Vue {
  private drawerVisible = false
  private unreadTimer = 0

  private tabs: MobileTab[] = [
    { label: '仪表盘', path: '/m/dashboard' },
    { label: '下载器', path: '/m/downloader' },
    { label: '种子', path: '/m/torrents' },
    { label: '通知', path: '/m/notifications' }
  ]

  private get unreadCount(): number {
    return NotificationModule.unreadCount
  }

  mounted(): void {
    this.fetchUnreadCount()
    this.unreadTimer = window.setInterval(this.fetchUnreadCount, UNREAD_POLL_INTERVAL_MS)
  }

  beforeDestroy(): void {
    if (this.unreadTimer) {
      window.clearInterval(this.unreadTimer)
      this.unreadTimer = 0
    }
  }

  private fetchUnreadCount(): void {
    NotificationModule.FetchUnreadCount().catch(() => undefined)
  }

  /** 移动版已有页面（抽屉内导航）：底部 Tab 四项 + M2 管理页四项。 */
  private mobileMenuItems: MobileTab[] = [
    ...this.tabs,
    { label: '高级搜索', path: '/m/search' },
    { label: '查询模板', path: '/m/query-templates' },
    { label: '回收站', path: '/m/recycle-bin' },
    { label: '日志', path: '/m/logs' }
  ]

  /** 桌面版承载的功能页（父路径均有 redirect 到真实子页）；M2 后日志/回收站/查询模板已移动化。 */
  private desktopMenuItems: MobileTab[] = [
    { label: '下载器管理', path: '/downloader' },
    { label: '种子列表（桌面）', path: '/torrents' },
    { label: 'Tracker管理', path: '/tracker' },
    { label: '定时任务', path: '/tasks' },
    { label: '孤儿文件', path: '/orphan-files' },
    { label: '系统设置', path: '/settings' }
  ]

  private isActive(tab: MobileTab): boolean {
    return this.$route.path === tab.path || this.$route.path.startsWith(tab.path + '/')
  }

  private go(tab: MobileTab): void {
    if (!this.isActive(tab)) {
      this.$router.replace(tab.path).catch(() => undefined)
    }
  }

  /** 抽屉菜单点击：一律关闭抽屉；移动项 replace 保持单栈，桌面项 push 保留返回。 */
  private goMenuItem(item: MobileTab): void {
    this.drawerVisible = false
    if (this.isActive(item) && item.path.startsWith('/m/')) return
    // 不从 $router 解构方法（丢 this），显式调用
    if (item.path.startsWith('/m/')) {
      this.$router.replace(item.path).catch(() => undefined)
    } else {
      this.$router.push(item.path).catch(() => undefined)
    }
  }

  private switchToDesktop(): void {
    this.drawerVisible = false
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
  padding: 0 12px;
  height: 48px;
  /* 头部主题色（2026-08-24 用户确认）：与桌面端主色同源变量 */
  background: var(--color-primary);
  color: #fff;
}

.mobile-header-title {
  font-size: 16px;
  font-weight: 600;
}

.mobile-header-menu {
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  width: 36px;
  height: 36px;
  padding: 8px 7px;
  border: none;
  background: transparent;
}

.mobile-header-menu-bar {
  display: block;
  height: 2px;
  width: 100%;
  /* 主题色头部上的白色系前景（#059669 上对比度充足） */
  background: rgba(255, 255, 255, 0.9);
  border-radius: 1px;
}

.mobile-header-desktop {
  color: #fff;
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
  position: relative;
}

.mobile-tab.is-active {
  /* 与桌面端主题同源（theme-variables.scss --color-primary #059669） */
  color: var(--color-primary);
  font-weight: 600;
}

.mobile-tab-label {
  line-height: 1.2;
}

/* 通知未读角标：红底白字（语义色与桌面 Navbar el-badge 一致），绝对定位于 Tab 文案右上 */
.mobile-tab-badge {
  display: inline-block;
  margin-left: 4px;
  padding: 0 5px;
  min-width: 16px;
  box-sizing: border-box;
  border-radius: 8px;
  background: #f56c6c;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 15px;
  text-align: center;
  vertical-align: middle;
}
</style>

<!-- 抽屉内容挂在 body 下（append-to-body），scoped 选择器够不到，走全局块 -->
<style>
.mobile-menu-drawer {
  background: #fff;
}

.mobile-menu {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-bottom: env(safe-area-inset-bottom);
  overflow-y: auto;
}

.mobile-menu-header {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 48px;
  /* 与页面头部同源主题色 */
  background: var(--color-primary);
  color: #fff;
  z-index: 1;
}

.mobile-menu-title {
  font-size: 15px;
  font-weight: 600;
}

.mobile-menu-close {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.9);
  font-size: 16px;
  padding: 6px 8px;
}

.mobile-menu-group-title {
  padding: 14px 16px 6px;
  font-size: 12px;
  color: #909399;
}

.mobile-menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px 16px;
  border: none;
  background: transparent;
  color: #303133;
  font-size: 15px;
  text-align: left;
}

.mobile-menu-item.is-active {
  color: var(--color-primary);
  font-weight: 600;
}

.mobile-menu-item-current {
  font-size: 12px;
  color: var(--color-primary);
}

.mobile-menu-item-arrow {
  color: #c0c4cc;
  font-size: 18px;
  line-height: 1;
}

.mobile-menu-footer {
  margin-top: auto;
  padding: 16px;
  border-top: 1px solid #e4e7ed;
}

.mobile-menu-desktop-btn {
  width: 100%;
}
</style>
