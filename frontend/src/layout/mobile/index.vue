<template>
  <div class="mobile-layout">
    <header class="mobile-header">
      <div class="mobile-header-left">
        <button
          v-if="isSecondaryPage"
          type="button"
          class="mobile-header-back"
          aria-label="返回"
          @click="goBack"
        >
          <LucideIcon name="arrow-left" :size="20" />
        </button>
        <button type="button" class="mobile-header-menu" aria-label="打开功能菜单" @click="drawerVisible = true">
          <span class="mobile-header-menu-bar" />
          <span class="mobile-header-menu-bar" />
          <span class="mobile-header-menu-bar" />
        </button>
      </div>
      <div class="mobile-header-brand">
        <AppLogo v-if="!isSecondaryPage" variant="micro" tone="inverse" alt="" class="mobile-header-logo" />
        <span class="mobile-header-title">{{ headerTitle }}</span>
      </div>
      <el-button type="text" size="mini" class="mobile-header-desktop" @click="switchToDesktop">
        桌面版
      </el-button>
    </header>

    <main
      class="mobile-content"
      :class="swipeAnimClass"
      @touchstart.passive="onContentTouchStart"
      @touchmove.passive="onContentTouchMove"
      @touchend.passive="onContentTouchEnd"
    >
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
        <LucideIcon v-if="tab.icon" :name="tab.icon" :size="18" class="mobile-tab-icon" />
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
      :close-on-click-modal="true"
      custom-class="mobile-menu-drawer"
      :modal-append-to-body="true"
      append-to-body
    >
      <div
        class="mobile-menu"
        @touchstart.passive="onDrawerTouchStart"
        @touchmove.passive="onDrawerTouchMove"
        @touchend.passive="onDrawerTouchEnd"
      >
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
import AppLogo from '@/components/common/AppLogo.vue'

interface MobileTab {
  label: string
  path: string
  /** 底部 Tab 图标（LucideIcon 已注册名）；抽屉菜单项无图标 */
  icon?: string
}

const UNREAD_POLL_INTERVAL_MS = 60000

/** 手势阈值（v1.0.6 移动独有优化）：轴锁定 / Tab 切换位移 / 左边缘宽度 / 最大时长 */
const SWIPE_AXIS_LOCK_PX = 12
const SWIPE_TAB_THRESHOLD_PX = 60
const SWIPE_EDGE_WIDTH_PX = 24
const SWIPE_MAX_DURATION_MS = 800
const SWIPE_ANIM_DURATION_MS = 220

type SwipeAxis = 'none' | 'horizontal' | 'vertical'

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
 *
 * 手势（v1.0.6 移动独有优化）：内容区水平滑动在四个底部 Tab 主页间切换
 * （带切向过渡动画）；左边缘右滑打开汉堡抽屉；抽屉内左滑或点遮罩关闭。
 * 轴锁定判定与页面级下拉刷新 mixin 互斥（横向手势不触发刷新），子页面
 * （详情/管理页）横向滑动不切 Tab，避免误触。
 *
 * 2026-08-28 移动 UX 增强：底部 Tab 图标（LucideIcon 已注册名，与桌面
 * 侧栏种子管理同用 download 保持跨端一致）；二级页头部 ← 返回（固定回退
 * 映射，见 goBack）与汉堡并存；汉堡触控区 44×44；未读轮询后台标签页跳过。
 */
@Component({
  name: 'MobileLayout',
  components: {
    AppLogo
  }
})
export default class MobileLayout extends Vue {
  private drawerVisible = false
  private unreadTimer = 0

  // ============ 手势状态（内容区滑动切 Tab / 左边缘右滑开抽屉） ============

  private swipeStartX = 0
  private swipeStartY = 0
  private swipeStartTime = 0
  private swipeAxis: SwipeAxis = 'none'
  private swipeFromLeftEdge = false
  /** 切向过渡动画类（swipe-anim-next/prev），超时后清空 */
  private swipeAnim: '' | 'next' | 'prev' = ''
  private swipeAnimTimer = 0

  // ============ 抽屉内左滑关闭 ============

  private drawerTouchStartX = 0
  private drawerTouchStartY = 0
  private drawerTouchHorizontal = false

  private tabs: MobileTab[] = [
    { label: '仪表盘', path: '/m/dashboard', icon: 'house' },
    { label: '下载器', path: '/m/downloader', icon: 'hard-drive' },
    { label: '种子', path: '/m/torrents', icon: 'download' },
    { label: '通知', path: '/m/notifications', icon: 'bell' }
  ]

  private get unreadCount(): number {
    return NotificationModule.unreadCount
  }

  // ============ 二级页头部（← 返回 + 页面标题；汉堡保留保证抽屉全局可达） ============

  /** 二级页：路由不精确落在四个底部 Tab 主页（与手势切 Tab 的精确匹配口径一致） */
  private get isSecondaryPage(): boolean {
    return !this.tabs.some(tab => this.$route.path === tab.path)
  }

  /** 头部标题：主页固定品牌名，二级页用路由 meta.title（空值兜底） */
  private get headerTitle(): string {
    if (!this.isSecondaryPage) return 'BtDeck'
    const meta = this.$route.meta as { title?: string } | undefined
    return (meta && meta.title) || 'BtDeck'
  }

  /**
   * 二级页返回用固定回退映射（replace 单栈下 history.back 会弹回登录页/出站，
   * 不可靠）：详情回归属列表、设置回归属下载器、关键词搜索回看板、其余回仪表盘。
   */
  private goBack(): void {
    const path = this.$route.path
    let target = '/m/dashboard'
    if (path.startsWith('/m/torrents/detail/')) {
      target = '/m/torrents'
    } else if (path.startsWith('/m/downloader/settings/')) {
      target = '/m/downloader'
    } else if (path === '/m/tracker/keywords-search') {
      target = '/m/tracker/keywords-board'
    }
    this.$router.replace(target).catch(() => undefined)
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
    if (this.swipeAnimTimer) {
      window.clearTimeout(this.swipeAnimTimer)
      this.swipeAnimTimer = 0
    }
  }

  private fetchUnreadCount(): void {
    // 后台标签页跳过本轮（省电；恢复可见后下一轮周期自然补拉）
    if (document.hidden) return
    NotificationModule.FetchUnreadCount().catch(() => undefined)
  }

  /** 移动版已有页面（抽屉内导航）：底部 Tab 四项 + 管理页。 */
  private mobileMenuItems: MobileTab[] = [
    ...this.tabs,
    { label: '高级搜索', path: '/m/search' },
    { label: '回收站', path: '/m/recycle-bin' },
    { label: '日志', path: '/m/logs' },
    { label: 'Tracker关键词', path: '/m/tracker/keywords-board' },
    { label: '定时任务', path: '/m/tasks' },
    { label: '孤儿文件', path: '/m/orphan-files' },
    { label: '系统设置', path: '/m/settings' }
  ]

  /** 桌面版承载的功能页（父路径均有 redirect 到真实子页）；系统设置已移动化（/m/settings）。 */
  private desktopMenuItems: MobileTab[] = [
    { label: '种子列表（桌面）', path: '/torrents' },
    { label: 'Tracker 汇报/测试（桌面）', path: '/tracker/reannounce-config' }
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

  // ============ 手势（v1.0.6 移动独有优化） ============

  private get swipeAnimClass(): string {
    return this.swipeAnim ? `swipe-anim-${this.swipeAnim}` : ''
  }

  private onContentTouchStart(e: TouchEvent): void {
    const touch = e.touches[0]
    if (!touch) return
    this.swipeStartX = touch.clientX
    this.swipeStartY = touch.clientY
    this.swipeStartTime = Date.now()
    this.swipeAxis = 'none'
    this.swipeFromLeftEdge = touch.clientX <= SWIPE_EDGE_WIDTH_PX
  }

  private onContentTouchMove(e: TouchEvent): void {
    if (this.swipeAxis !== 'none') return
    const touch = e.touches[0]
    if (!touch) return
    const dx = Math.abs(touch.clientX - this.swipeStartX)
    const dy = Math.abs(touch.clientY - this.swipeStartY)
    if (dx > SWIPE_AXIS_LOCK_PX || dy > SWIPE_AXIS_LOCK_PX) {
      this.swipeAxis = dx > dy ? 'horizontal' : 'vertical'
    }
  }

  private onContentTouchEnd(e: TouchEvent): void {
    const axis = this.swipeAxis
    const fromEdge = this.swipeFromLeftEdge
    const duration = Date.now() - this.swipeStartTime
    this.swipeAxis = 'none'
    this.swipeFromLeftEdge = false
    if (axis !== 'horizontal' || duration > SWIPE_MAX_DURATION_MS) return

    const touch = e.changedTouches[0]
    if (!touch) return
    const dx = touch.clientX - this.swipeStartX
    if (Math.abs(dx) < SWIPE_TAB_THRESHOLD_PX) return

    // 左边缘右滑优先开抽屉（与"切上一个 Tab"手势区分），且仅底部 Tab 主页
    // 精确匹配生效（startsWith 会命中 /m/torrents/detail 等子页面，须排除，
    // 避免详情页横向滑动误切 Tab）
    if (dx > 0 && fromEdge) {
      this.drawerVisible = true
      return
    }
    const index = this.tabs.findIndex(tab => this.$route.path === tab.path)
    if (index < 0) return
    if (dx < 0 && index < this.tabs.length - 1) {
      this.goWithSwipeAnim(this.tabs[index + 1], 'next')
    } else if (dx > 0 && index > 0) {
      this.goWithSwipeAnim(this.tabs[index - 1], 'prev')
    }
  }

  private goWithSwipeAnim(tab: MobileTab, direction: 'next' | 'prev'): void {
    this.go(tab)
    this.swipeAnim = direction
    if (this.swipeAnimTimer) window.clearTimeout(this.swipeAnimTimer)
    this.swipeAnimTimer = window.setTimeout(() => {
      this.swipeAnim = ''
      this.swipeAnimTimer = 0
    }, SWIPE_ANIM_DURATION_MS)
  }

  private onDrawerTouchStart(e: TouchEvent): void {
    const touch = e.touches[0]
    if (!touch) return
    this.drawerTouchStartX = touch.clientX
    this.drawerTouchStartY = touch.clientY
    this.drawerTouchHorizontal = false
  }

  private onDrawerTouchMove(e: TouchEvent): void {
    if (this.drawerTouchHorizontal) return
    const touch = e.touches[0]
    if (!touch) return
    const dx = Math.abs(touch.clientX - this.drawerTouchStartX)
    const dy = Math.abs(touch.clientY - this.drawerTouchStartY)
    if (dx > SWIPE_AXIS_LOCK_PX || dy > SWIPE_AXIS_LOCK_PX) {
      this.drawerTouchHorizontal = dx > dy
    }
  }

  private onDrawerTouchEnd(e: TouchEvent): void {
    if (!this.drawerTouchHorizontal) return
    const touch = e.changedTouches[0]
    if (!touch) return
    const dx = touch.clientX - this.drawerTouchStartX
    // 抽屉自左滑出（ltr），左滑（dx 为负）合拢方向一致
    if (dx <= -SWIPE_TAB_THRESHOLD_PX) {
      this.drawerVisible = false
    }
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mobile-header-brand {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.mobile-header-logo {
  width: 22px;
  height: 22px;
}

.mobile-header-menu {
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  /* 44×44 最低触控标准（2026-08-28 移动 UX 审查） */
  width: 44px;
  height: 44px;
  padding: 10px 9px;
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

/* 头部左侧操作组：二级页 ← 返回与汉堡并存（抽屉全局可达） */
.mobile-header-left {
  display: flex;
  align-items: center;
}

.mobile-header-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 44px;
  border: none;
  background: transparent;
  color: #fff;
  padding: 0;
}

.mobile-content {
  flex: 1;
  /* 底部留白 = 悬浮 Tab 栏高 56 + 底距 8 + 16px 间距，并补偿安全区 */
  padding: 12px 12px calc(80px + env(safe-area-inset-bottom));
  overflow-y: auto;
}

/* 滑动切 Tab 的切向过渡（v1.0.6 手势）：新页从滑动方向进入 */
.mobile-content.swipe-anim-next {
  animation: mobile-swipe-in-next 0.22s ease both;
}

.mobile-content.swipe-anim-prev {
  animation: mobile-swipe-in-prev 0.22s ease both;
}

@keyframes mobile-swipe-in-next {
  from {
    opacity: 0.4;
    transform: translateX(18px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@keyframes mobile-swipe-in-prev {
  from {
    opacity: 0.4;
    transform: translateX(-18px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

/* 悬浮圆角玻璃 Tab 栏：安全区避让由 bottom 偏移承担 */
.mobile-tabbar {
  position: fixed;
  left: 12px;
  right: 12px;
  bottom: calc(8px + env(safe-area-inset-bottom));
  display: flex;
  border-radius: var(--radius-xl, 16px);
  background: var(--glass-bg, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(var(--glass-blur, 12px));
  -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
  border: var(--glass-border, 1px solid rgba(255, 255, 255, 0.3));
  box-shadow: var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05));
  z-index: 10;
}

/* @supports 条件须用字面量 blur(12px)：var() 写进条件会被部分引擎判 unknown 使 not() 恒真
   （勿对齐 Navbar 的 var() 写法）；无前缀检测对 iOS ≤17 误降实色，属保守取舍，
   目标环境 Android WebView + 桌面均原生支持无前缀 backdrop-filter */
@supports not (backdrop-filter: blur(12px)) {
  .mobile-tabbar {
    background: var(--color-bg-primary, #FFFFFF);
    border: 1px solid var(--color-border-primary, #E5E7EB);
  }
}

.mobile-tab {
  flex: 1;
  height: 56px;
  border: none;
  background: transparent;
  color: #909399;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
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

.mobile-tab-icon {
  /* 图标描边走 currentColor，随 .mobile-tab / .is-active 的 color 生效 */
  flex-shrink: 0;
}

/* 通知未读角标：红底白字（语义色与桌面 Navbar el-badge 一致），绝对定位于 Tab 右上 */
.mobile-tab-badge {
  position: absolute;
  top: 5px;
  right: 16px;
  display: inline-block;
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
