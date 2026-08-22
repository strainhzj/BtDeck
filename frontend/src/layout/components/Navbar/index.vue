<template>
  <div class="navbar">
    <!-- 左侧区域 - 动态贴在侧边栏右侧 -->
    <div class="navbar-left">
      <!-- Logo（可选） -->
      <div class="navbar-logo">
        <LucideIcon name="orbit" :size="28" :stroke-width="1.65" class="logo-icon" />
        <span class="logo-text">BtDeck</span>
      </div>

      <!-- 面包屑导航 -->
      <breadcrumb class="breadcrumb-container" />
    </div>

    <!-- 右侧区域 -->
    <div class="navbar-right">
      <!-- 反馈按钮 -->
      <el-button
        class="icon-button feedback-button"
        circle
        aria-label="提交反馈"
        title="提交反馈"
        @click="handleFeedback"
      >
        <LucideIcon name="message-circle" :size="19" :stroke-width="1.8" />
      </el-button>

      <!-- 通知中心 -->
      <el-badge :value="notificationCount" :hidden="notificationCount === 0" class="notification-badge">
        <el-button
          class="icon-button"
          circle
          aria-label="打开通知中心"
          title="通知中心"
          @click="handleNotification"
        >
          <LucideIcon name="bell" :size="19" :stroke-width="1.8" />
        </el-button>
      </el-badge>

      <!-- 主题切换器 -->
      <theme-switcher class="theme-switcher-wrapper" />

      <!-- 用户信息 -->
      <el-dropdown
        class="avatar-container hover-effect"
        trigger="click"
        @command="handleUserAction"
      >
        <div class="avatar-wrapper">
          <span class="user-avatar">
            <LucideIcon name="user-round" :size="18" :stroke-width="1.8" />
          </span>
          <span class="user-name">{{ userName }}</span>
          <LucideIcon name="chevron-down" :size="14" :stroke-width="1.8" class="user-chevron" />
        </div>
        <el-dropdown-menu slot="dropdown">
          <router-link to="/">
            <el-dropdown-item>
              <LucideIcon name="house" :size="16" :stroke-width="1.8" />
              <span>首页</span>
            </el-dropdown-item>
          </router-link>
          <el-dropdown-item divided command="logout">
            <LucideIcon name="log-out" :size="16" :stroke-width="1.8" />
            <span>退出登录</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { UserModule } from '@/store/modules/user'
import { NotificationModule } from '@/store/modules/notification'
import Breadcrumb from '@/components/Breadcrumb/index.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher/index.vue'

@Component({
  name: 'Navbar',
  components: {
    Breadcrumb,
    ThemeSwitcher
  }
})
export default class extends Vue {
  get avatar() {
    return UserModule.avatar
  }

  get userName() {
    return UserModule.name || '管理员'
  }

  get notificationCount() {
    return NotificationModule.unreadCount
  }

  private handleNotification() {
    NotificationModule.ToggleDrawer(true)
  }

  private handleFeedback() {
    window.open('https://github.com/strainhzj/BtDeck/issues', '_blank')
  }

  private handleUserAction(command: string) {
    if (command === 'logout') {
      this.logout()
    }
  }

  private async logout() {
    await UserModule.LogOut()
    this.$router.push(`/login?redirect=${this.$route.fullPath}`)
  }
}
</script>

<style lang="scss" scoped>
/* ============================================
   导航栏 - 任务13重构
   ============================================ */

.navbar {
  height: var(--navbar-height, 64px);
  line-height: var(--navbar-height, 64px); /* ✅ P1修复：添加line-height */
  overflow: hidden;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  background: var(--glass-bg, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(var(--glass-blur, 12px));
  -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
  border-bottom: var(--glass-border, 1px solid rgba(255, 255, 255, 0.3));
  box-shadow: var(--shadow-navbar, 0 4px 24px rgba(0, 0, 0, 0.06));
  z-index: 1000;
  display: flex;
  align-items: center;
  transition: all var(--transition-layout, 300ms);

  /* 降级方案 */
  @supports not (backdrop-filter: blur(var(--glass-blur, 12px))) {
    background: var(--color-bg-primary, #FFFFFF);
    border-bottom: 1px solid var(--color-border-primary, #E5E7EB);
  }
}

/* 左侧区域 - 动态贴在侧边栏右侧 */
.navbar-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md, 16px);
  height: 100%;
  padding-left: var(--spacing-lg, 24px);
  margin-left: var(--sidebar-width, 240px);
  transition: margin-left var(--transition-layout, 300ms);

  /* 移动端无边距 */
  .mobile & {
    margin-left: 0;
    padding-left: var(--spacing-md, 16px);
  }
}

/* Logo 区域 */
.navbar-logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary, #1F2937);
}

.logo-icon {
  color: var(--color-primary, #059669);
}

.logo-text {
  white-space: nowrap;
}

/* 面包屑导航 */
.breadcrumb-container {
  flex: 1;
}

/* 右侧区域 */
.navbar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md, 16px);
  height: 100%;
  margin-left: auto;
  padding-right: var(--spacing-lg, 24px);
}

/* 图标按钮 */
.icon-button {
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #6B7280);
  transition: all var(--transition-base, 200ms);

  &:hover {
    background: var(--color-bg-hover, #F3F4F6);
    color: var(--color-text-primary, #1F2937);
  }

}

/* 通知徽章 */
.notification-badge {
  ::v-deep .el-badge__content {
    background-color: var(--color-error, #EF4444);
    border-color: var(--color-error, #EF4444);
    top: 12px;
    right: 8px;
  }
}

/* 主题切换器包装器 */
.theme-switcher-wrapper {
  margin: 0 var(--spacing-sm, 8px);
}

/* 用户信息 */
.avatar-container {
  display: flex;
  align-items: center;
  padding: 4px var(--spacing-md, 16px);
  cursor: pointer;
  border-radius: var(--radius-md, 8px);
  transition: background var(--transition-base, 200ms);

  &:hover {
    background: var(--color-bg-hover, #F3F4F6);
  }

  .avatar-wrapper {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm, 8px);
  }

  .user-avatar {
    cursor: pointer;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-full, 9999px);
    border: 2px solid var(--color-border-primary, #E5E7EB);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    background-color: var(--color-bg-secondary, #F9FAFB);
  }

  .user-name {
    font-size: 14px;
    font-weight: 500;
    color: var(--color-text-primary, #1F2937);
    white-space: nowrap;
  }

  .user-chevron {
    cursor: pointer;
    color: var(--color-text-secondary, #6B7280);
    transition: transform var(--transition-base, 200ms);
  }
}

/* 下拉菜单样式优化 */
::v-deep .el-dropdown-menu {
  .el-dropdown-menu__item {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm, 8px);

    .lucide-icon {
      color: var(--color-text-secondary, #6B7280);
    }

    &:hover .lucide-icon {
      color: var(--color-primary, #059669);
    }
  }
}

/* 响应式适配 */
@media (max-width: 768px) {
  .navbar-left {
    margin-left: 0 !important;
    padding-left: var(--spacing-md, 16px);
  }

  .logo-text {
    display: none;
  }

  .theme-switcher-wrapper {
    ::v-deep .theme-name {
      display: none;
    }
  }

  .user-name {
    display: none;
  }
}
</style>
