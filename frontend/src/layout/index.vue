<template>
  <div
    :class="classObj"
    class="app-wrapper"
  >
    <div
      v-if="classObj.mobile && sidebar.opened"
      class="drawer-bg drawer-bg-visible"
      @click="handleClickOutside"
    />
    <sidebar class="sidebar-container" />
    <div class="main-container">
      <navbar />
      <app-main />
    </div>
    <notification-drawer />
  </div>
</template>

<script lang="ts">
import { Component } from 'vue-property-decorator'
import { mixins } from 'vue-class-component'
import { DeviceType, AppModule } from '@/store/modules/app'
import { AppMain, Navbar, Sidebar } from './components'
import NotificationDrawer from './components/NotificationDrawer/index.vue'
import ResizeMixin from './mixin/resize'

@Component({
  name: 'Layout',
  components: {
    AppMain,
    Navbar,
    Sidebar,
    NotificationDrawer
  }
})
export default class extends mixins(ResizeMixin) {
  get classObj() {
    return {
      hideSidebar: !this.sidebar.opened,
      openSidebar: this.sidebar.opened,
      withoutAnimation: this.sidebar.withoutAnimation,
      mobile: this.device === DeviceType.Mobile
    }
  }

  private handleClickOutside() {
    AppModule.CloseSideBar(false)
  }
}
</script>

<style lang="scss" scoped>
/* ============================================
   主布局容器 - 任务12重构
   ============================================ */

.app-wrapper {
  @include clearfix;
  position: relative;
  height: 100%;
  width: 100%;
  background: var(--color-bg-secondary);
}

/* 移动端遮罩层 */
.drawer-bg {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  /* Glassmorphism 毛玻璃效果 */
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 999;
  opacity: 0;
  visibility: hidden;
  transition: all var(--transition-slow);

  /* 降级方案：不支持 backdrop-filter 时使用纯色半透明 */
  @supports not (backdrop-filter: blur(4px)) {
    background: rgba(0, 0, 0, 0.5);
  }
}

/* 遮罩层可见状态 - 通过v-if和独立类名控制，逻辑更清晰 */
.drawer-bg-visible {
  opacity: 1;
  visibility: visible;
}

/* 主内容容器 */
.main-container {
  min-height: 100vh;
  margin-left: var(--sidebar-width, 240px);
  margin-top: var(--navbar-height, 64px);
  padding: var(--spacing-lg, 24px);
  transition: margin-left var(--transition-layout, 300ms);
  position: relative;

  /* 移动端无边距 */
  .mobile & {
    margin-left: 0;
  }
}

/* 侧边栏容器样式 */
.sidebar-container {
  transition: width var(--transition-layout, 300ms);
  width: var(--sidebar-width, 240px) !important;
  height: 100%;
  position: fixed;
  font-size: 0px;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 1001;
  overflow: hidden;

  /* Glassmorphism 毛玻璃效果 */
  background: var(--glass-bg, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(var(--glass-blur, 12px));
  -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
  border-right: var(--glass-border, 1px solid rgba(255, 255, 255, 0.3));

  /* 降级方案 */
  @supports not (backdrop-filter: blur(var(--glass-blur, 12px))) {
    background: var(--color-bg-primary, #FFFFFF);
    border-right: 1px solid var(--color-border-primary, #E5E7EB);
  }
}

/* 侧边栏折叠状态 */
.hideSidebar {
  .main-container {
    margin-left: var(--sidebar-collapsed-width, 64px);
  }

  .sidebar-container {
    width: var(--sidebar-collapsed-width, 64px) !important;
  }
}

/* 移动端响应式适配 */
.mobile {
  .main-container {
    margin-left: 0;
  }

  .sidebar-container {
    transition: transform var(--transition-layout, 300ms);
    width: var(--sidebar-width, 240px) !important;
  }

  /* 移动端隐藏侧边栏 */
  &.hideSidebar {
    .sidebar-container {
      pointer-events: none;
      transition-duration: 0.3s;
      transform: translate3d(calc(var(--sidebar-width, 240px) * -1), 0, 0);
    }
  }
}

/* 无动画状态（用于初始化） */
.withoutAnimation {
  .main-container,
  .sidebar-container {
    transition: none;
  }
}
</style>
