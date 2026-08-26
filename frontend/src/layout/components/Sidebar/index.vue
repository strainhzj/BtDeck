<template>
  <div class="sidebar-container">
    <!-- Logo 区域 -->
    <div class="sidebar-header">
      <div class="sidebar-logo" :class="{'is-collapsed': isCollapse}">
        <AppLogo
          :variant="isCollapse ? 'mark' : 'full'"
          class="sidebar-logo-image"
        />
      </div>
    </div>

    <!-- 菜单区域 -->
    <el-scrollbar wrap-class="scrollbar-wrapper">
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        background-color="transparent"
        text-color="var(--sidebar-text-color, #6B7280)"
        active-text-color="var(--sidebar-text-color-active, #059669)"
        :unique-opened="false"
        :collapse-transition="false"
        mode="vertical"
        class="sidebar-menu"
      >
        <sidebar-item
          v-for="route in routes"
          :key="route.path"
          :item="route"
          :base-path="route.path"
          :is-collapse="isCollapse"
        />
      </el-menu>
    </el-scrollbar>

    <!-- 底部操作区：移动版入口 + 折叠按钮 -->
    <div class="sidebar-footer">
      <el-button
        class="collapse-button"
        aria-label="切换到移动版"
        @click="switchToMobile"
      >
        <LucideIcon
          name="smartphone"
          :size="17"
          :stroke-width="1.8"
        />
        <span v-show="!isCollapse">移动版</span>
      </el-button>
      <el-button
        class="collapse-button"
        :aria-label="isCollapse ? '展开侧边栏' : '收起侧边栏'"
        @click="toggleSidebar"
      >
        <LucideIcon
          :name="isCollapse ? 'panel-left-open' : 'panel-left-close'"
          :size="17"
          :stroke-width="1.8"
        />
        <span v-show="!isCollapse">收起侧边栏</span>
      </el-button>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { AppModule } from '@/store/modules/app'
import { setStoredUiMode } from '@/utils/ui-mode'
import AppLogo from '@/components/common/AppLogo.vue'
import SidebarItem from './SidebarItem.vue'

@Component({
  name: 'SideBar',
  components: {
    AppLogo,
    SidebarItem
  }
})
export default class extends Vue {
  get sidebar() {
    return AppModule.sidebar
  }

  get routes() {
    return (this.$router as any).options.routes
  }

  get activeMenu() {
    const route = this.$route
    const { meta, path } = route
    if (meta && meta.activeMenu) {
      return meta.activeMenu
    }
    return path
  }

  get isCollapse() {
    return !this.sidebar.opened
  }

  private toggleSidebar() {
    AppModule.ToggleSideBar(false)
  }

  /**
   * 手动切换移动版（Phase 4 M1 余项）：写 mobile 偏好后进入移动版。
   * 显式偏好优先于视口（ui-mode 三原则），宽屏桌面也可预览移动版；
   * 守卫按解析后的模式放行 /m/*，SPA 内直接换壳无需刷新页面。
   */
  private switchToMobile() {
    setStoredUiMode('mobile')
    this.$router.push('/m/dashboard').catch(() => undefined)
  }
}
</script>

<style lang="scss">
/* ============================================
   侧边栏容器 - 任务14重构
   ============================================ */

.sidebar-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--glass-bg, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(var(--glass-blur, 12px));
  -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
  border-right: var(--glass-border, 1px solid rgba(255, 255, 255, 0.3));

  /* 降级方案 */
  @supports not (backdrop-filter: blur(var(--glass-blur, 12px))) {
    background: var(--color-bg-primary, #FFFFFF);
    border-right: 1px solid var(--color-border-primary, #E5E7EB);
  }

  /* Reset element-ui css */
  .horizontal-collapse-transition {
    transition: 0s width ease-in-out, 0s padding-left ease-in-out, 0s padding-right ease-in-out;
  }

  .scrollbar-wrapper {
    overflow-x: hidden !important;
    flex: 1;
  }

  .el-scrollbar__view {
    height: 100%
  }

  .el-scrollbar__bar {
    &.is-vertical {
      right: 0px;
    }

    &.is-horizontal {
      display: none;
    }
  }
}

/* Logo 区域 */
.sidebar-header {
  height: var(--navbar-height, 64px);
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--color-border-secondary, #F3F4F6);
  padding: 0 var(--spacing-md, 16px);
  flex-shrink: 0;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.sidebar-logo-image {
  width: 184px;
  height: 46px;
}

.sidebar-logo.is-collapsed .sidebar-logo-image {
  width: 32px;
  height: 32px;
}

/* 菜单样式 */
.sidebar-menu {
  border: none;
  height: 100%;
  width: 100% !important;
  flex: 1;
}

/* 左侧指示条 - 激活状态 */
.el-menu-item.is-active {
  position: relative;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 24px;
    background: var(--color-primary, #059669);
    border-radius: 0 2px 2px 0;
  }
}

/* 底部操作按钮区域（移动版入口 + 折叠按钮） */
.sidebar-footer {
  padding: var(--spacing-md, 16px);
  border-top: 1px solid var(--color-border-secondary, #F3F4F6);
  flex-shrink: 0;

  .collapse-button + .collapse-button {
    margin-top: var(--spacing-sm, 8px);
    margin-left: 0; /* 覆盖 Element 相邻按钮默认左间距 */
  }
}

.collapse-button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm, 8px);
  border: 1px solid var(--color-border-primary, #E5E7EB);
  border-radius: var(--radius-md, 8px);
  background: var(--color-bg-primary, #FFFFFF);
  color: var(--color-text-secondary, #6B7280);
  font-size: 14px;
  font-weight: 500;
  transition: all var(--transition-base, 200ms);

  &:hover {
    background: var(--color-bg-hover, #F3F4F6);
    border-color: var(--color-primary, #059669);
    color: var(--color-primary, #059669);
  }

}
</style>

<style lang="scss" scoped>
.el-scrollbar {
  height: 100%;
  flex: 1;
}
</style>
