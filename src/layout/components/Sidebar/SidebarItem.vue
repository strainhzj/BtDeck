<template>
  <div
    v-if="!item.meta || !item.meta.hidden"
    :class="['menu-wrapper', isCollapse ? 'simple-mode' : 'full-mode', {'first-level': isFirstLevel}]"
  >
    <template v-if="theOnlyOneChild && !theOnlyOneChild.children">
      <sidebar-item-link
        v-if="theOnlyOneChild.meta"
        :to="resolvePath(theOnlyOneChild.path)"
      >
        <el-menu-item
          :index="resolvePath(theOnlyOneChild.path)"
          :class="{'submenu-title-noDropdown': isFirstLevel, 'menu-item-with-indicator': isFirstLevel}"
        >
          <svg-icon
            v-if="theOnlyOneChild.meta.icon"
            :name="theOnlyOneChild.meta.icon"
            class="menu-icon"
          />
          <span
            v-if="theOnlyOneChild.meta.title"
            slot="title"
          >{{ theOnlyOneChild.meta.title }}</span>
        </el-menu-item>
      </sidebar-item-link>
    </template>
    <el-submenu
      v-else
      :index="resolvePath(item.path)"
      popper-append-to-body
    >
      <template slot="title">
        <svg-icon
          v-if="item.meta && item.meta.icon"
          :name="item.meta.icon"
          class="menu-icon"
        />
        <span
          v-if="item.meta && item.meta.title"
          slot="title"
        >{{ item.meta.title }}</span>
      </template>
      <template v-if="item.children">
        <sidebar-item
          v-for="child in item.children"
          :key="child.path"
          :item="child"
          :is-collapse="isCollapse"
          :is-first-level="false"
          :base-path="resolvePath(child.path)"
          class="nest-menu"
        />
      </template>
    </el-submenu>
  </div>
</template>

<script lang="ts">
import path from 'path'
import { Component, Prop, Vue } from 'vue-property-decorator'
import { RouteConfig } from 'vue-router'
import { isExternal } from '@/utils/validate'
import SidebarItemLink from './SidebarItemLink.vue'

@Component({
  // Set 'name' here to prevent uglifyjs from causing recursive component not work
  // See https://medium.com/haiiro-io/element-component-name-with-vue-class-component-f3b435656561 for detail
  name: 'SidebarItem',
  components: {
    SidebarItemLink
  }
})
export default class extends Vue {
  @Prop({ required: true }) private item!: RouteConfig
  @Prop({ default: false }) private isCollapse!: boolean
  @Prop({ default: true }) private isFirstLevel!: boolean
  @Prop({ default: '' }) private basePath!: string

  get showingChildNumber() {
    if (this.item.children) {
      const showingChildren = this.item.children.filter((item) => {
        if (item.meta && item.meta.hidden) {
          return false
        } else {
          return true
        }
      })
      return showingChildren.length
    }
    return 0
  }

  get theOnlyOneChild() {
    if (this.showingChildNumber > 1) {
      return null
    }
    if (this.item.children) {
      for (const child of this.item.children) {
        if (!child.meta || !child.meta.hidden) {
          return child
        }
      }
    }
    // If there is no children, return itself with path removed,
    // because this.basePath already conatins item's path information
    return { ...this.item, path: '' }
  }

  private resolvePath(routePath: string) {
    if (isExternal(routePath)) {
      return routePath
    }
    if (isExternal(this.basePath)) {
      return this.basePath
    }
    return path.resolve(this.basePath, routePath)
  }
}
</script>

<style lang="scss">
/* ============================================
   侧边栏菜单项样式 - 任务14重构
   ============================================ */

.el-submenu.is-active > .el-submenu__title {
  color: var(--color-primary, #059669) !important;
}

/* 菜单项图标 */
.menu-icon {
  margin-right: 16px;
  font-size: 20px;
  color: var(--color-text-secondary, #6B7280);
  transition: color var(--transition-base, 200ms);
  vertical-align: middle;
  transform: translateY(0px);
}

.el-menu-item.is-active .menu-icon {
  color: var(--color-primary, #059669);
}

/* 全屏模式 */
.full-mode {
  .nest-menu .el-submenu>.el-submenu__title,
  .el-submenu .el-menu-item {
    min-width: var(--sidebar-width, 240px) !important; /* ✅ P1修复：统一使用CSS变量 */

    /* ✅ P1修复：使用CSS变量替代硬编码颜色值 */
    &:hover {
      background-color: var(--color-menu-hover-bg);
      color: var(--color-menu-hover-text);
    }

    &:hover .menu-icon {
      color: var(--color-menu-hover-text);
    }
  }
}

/* 简化模式（折叠状态） */
.simple-mode {
  &.first-level {
    .submenu-title-noDropdown {
      padding: 0 !important;
      position: relative;

      .el-tooltip {
        padding: 0 !important;
      }
    }

    .el-submenu {
      overflow: hidden;

      &>.el-submenu__title {
        padding: 0px !important;

        .el-submenu__icon-arrow {
          display: none;
        }

        &>span {
          visibility: hidden;
        }
      }
    }

    .menu-icon {
      margin-left: 20px;
      margin-right: 0;
    }
  }
}

/* 左侧指示条 */
.menu-item-with-indicator {
  position: relative;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 0;
    background: var(--color-primary, #059669);
    border-radius: 0 2px 2px 0;
    transition: height var(--transition-base, 200ms);
    opacity: 0;
  }

  &:hover::before {
    opacity: 1;
    height: 16px;
  }
}

.el-menu-item.is-active.menu-item-with-indicator::before {
  opacity: 1;
  height: 24px;
}
</style>

<style lang="scss" scoped>
.svg-icon {
  margin-right: 16px;
}

.simple-mode {
  .svg-icon {
    margin-left: 20px;
  }
}
</style>
