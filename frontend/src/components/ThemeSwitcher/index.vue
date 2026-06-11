<template>
  <el-dropdown trigger="click" @command="handleThemeChange">
    <div class="theme-switcher">
      <div class="theme-indicator" :style="{backgroundColor: currentThemeColor}"></div>
      <span class="theme-name">{{ currentThemeName }}</span>
      <i class="el-icon-arrow-down el-icon--right"></i>
    </div>
    <el-dropdown-menu slot="dropdown">
      <el-dropdown-item
        v-for="theme in themes"
        :key="theme.value"
        :command="theme.value"
        :class="{'is-active': theme.value === currentTheme}"
      >
        <div class="theme-option">
          <div
            class="theme-color"
            :style="{backgroundColor: theme.color}"
          ></div>
          <div class="theme-info">
            <span class="theme-label">{{ theme.name }}</span>
            <span class="theme-desc">{{ theme.description }}</span>
          </div>
          <i v-if="theme.value === currentTheme" class="el-icon-check"></i>
        </div>
      </el-dropdown-item>
    </el-dropdown-menu>
  </el-dropdown>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { ThemeType, THEMES, getCurrentTheme, setTheme } from '@/utils/theme'

@Component({
  name: 'ThemeSwitcher'
})
export default class ThemeSwitcher extends Vue {
  private currentTheme: ThemeType = getCurrentTheme()
  private themeChangeHandler?: EventListener

  get themes() {
    return THEMES
  }

  get currentThemeName() {
    return THEMES.find(t => t.value === this.currentTheme)?.name || ''
  }

  get currentThemeColor() {
    return THEMES.find(t => t.value === this.currentTheme)?.color || ''
  }

  private handleThemeChange(theme: ThemeType) {
    this.currentTheme = theme
    setTheme(theme)
    this.$message.success(`已切换到${THEMES.find(t => t.value === theme)?.name}主题`)
  }

  private mounted() {
    // 监听主题变更事件
    this.themeChangeHandler = ((event: Event) => {
      const customEvent = event as CustomEvent<{theme: ThemeType}>
      if (customEvent.detail?.theme) {
        this.currentTheme = customEvent.detail.theme
      }
    }) as EventListener
    window.addEventListener('theme-change', this.themeChangeHandler)
  }

  private beforeDestroy() {
    // 清理事件监听器，防止内存泄漏
    if (this.themeChangeHandler) {
      window.removeEventListener('theme-change', this.themeChangeHandler)
    }
  }
}
</script>

<style lang="scss" scoped>
.theme-switcher {
  display: flex;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);

  &:hover {
    background: var(--color-bg-tertiary);
    border-color: var(--color-border-focus);
  }
}

.theme-indicator {
  width: 16px;
  height: 16px;
  border-radius: var(--radius-sm);
  margin-right: var(--spacing-sm);
  box-shadow: var(--shadow-sm);
}

.theme-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  margin-right: var(--spacing-xs);
}

// 下拉菜单样式
::v-deep .el-dropdown-menu__item {
  padding: 0;

  &.is-active {
    background: var(--color-bg-hover);
  }
}

.theme-option {
  display: flex;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  width: 280px;

  &:hover {
    background: var(--color-bg-hover);
  }
}

.theme-color {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  margin-right: var(--spacing-md);
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}

.theme-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.theme-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.theme-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.el-icon-check {
  color: var(--color-primary);
  font-size: var(--font-size-lg);
}
</style>
