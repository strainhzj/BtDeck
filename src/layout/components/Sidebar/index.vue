<template>
  <div class="sidebar-container">
    <!-- Logo 区域 -->
    <div class="sidebar-header">
      <div class="sidebar-logo">
        <svg-icon name="dashboard" class="logo-icon" />
        <span v-show="!isCollapse" class="sidebar-logo-text">
          BtDeck
        </span>
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

    <!-- 底部折叠按钮 -->
    <div class="sidebar-footer">
      <el-button
        :icon="isCollapse ? 'el-icon-s-unfold' : 'el-icon-s-fold'"
        class="collapse-button"
        @click="toggleSidebar"
      >
        <span v-show="!isCollapse">收起侧边栏</span>
      </el-button>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { AppModule } from '@/store/modules/app'
import SidebarItem from './SidebarItem.vue'

@Component({
  name: 'SideBar',
  components: {
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
  gap: var(--spacing-sm, 8px);
}

.logo-icon {
  width: 32px;
  height: 32px;
  font-size: 32px;
}

.sidebar-logo-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #1F2937);
  white-space: nowrap;
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

/* 底部折叠按钮区域 */
.sidebar-footer {
  padding: var(--spacing-md, 16px);
  border-top: 1px solid var(--color-border-secondary, #F3F4F6);
  flex-shrink: 0;
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

  i {
    font-size: 18px;
    transition: transform var(--transition-base, 200ms);
  }
}
</style>

<style lang="scss" scoped>
.el-scrollbar {
  height: 100%;
  flex: 1;
}
</style>
