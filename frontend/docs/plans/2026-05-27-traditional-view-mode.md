# 传统模式视图功能实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为种子列表页面新增"传统模式"视图，参考 qui 项目风格，提供左侧过滤面板 + 现代化表格 + 右侧详情面板的布局，与现有列表模式可切换。

**Architecture:** 
1. 复用现有 API 层 (`src/api/torrents.ts`)、格式化工具 (`src/utils/formatters.ts`)、状态配置 (`src/constants/status-config.ts`)
2. 新增视图模式 Vuex module 管理视图状态（list/traditional）和过滤面板展开状态
3. 创建 `TraditionalView.vue` 组件作为独立视图，与现有 `index.vue` 共享数据和逻辑
4. 通过路由参数或组件切换实现两种视图模式切换，状态持久化到 localStorage

**Tech Stack:**
- Vue 2.6.12 + TypeScript 4.x + Class Component
- Vuex 3.6.2 (状态管理)
- Element UI 2.15.13 (现有组件库)
- SCSS (使用现有 `theme-variables.scss` CSS 变量)

---

## Task 1: 创建视图模式 Vuex Module

**Files:**
- Create: `src/store/modules/viewMode.ts`
- Modify: `src/store/index.ts` (注册新模块)

**Step 1: 创建 viewMode module 文件**

```typescript
// src/store/modules/viewMode.ts
import { VuexModule, Module, Mutation, Action, getModule } from 'vuex-module-decorators'
import { getStorage, setStorage } from '@/utils/cookies'
import store from '@/store'

export type ViewModeType = 'list' | 'traditional'

export interface IViewModeState {
  currentMode: ViewModeType
  filterPanelCollapsed: boolean
}

const VIEW_MODE_STORAGE_KEY = 'btdeck_view_mode'
const FILTER_PANEL_STORAGE_KEY = 'btdeck_filter_panel_collapsed'

@Module({ dynamic: true, store, name: 'viewMode' })
class ViewMode extends VuexModule implements IViewModeState {
  public currentMode: ViewModeType = (getStorage(VIEW_MODE_STORAGE_KEY) as ViewModeType) || 'list'
  public filterPanelCollapsed: boolean = getStorage(FILTER_PANEL_STORAGE_KEY) === 'true'

  @Mutation
  private SET_VIEW_MODE(mode: ViewModeType) {
    this.currentMode = mode
    setStorage(VIEW_MODE_STORAGE_KEY, mode)
  }

  @Mutation
  private TOGGLE_FILTER_PANEL() {
    this.filterPanelCollapsed = !this.filterPanelCollapsed
    setStorage(FILTER_PANEL_STORAGE_KEY, String(this.filterPanelCollapsed))
  }

  @Mutation
  private SET_FILTER_PANEL_COLLAPSED(collapsed: boolean) {
    this.filterPanelCollapsed = collapsed
    setStorage(FILTER_PANEL_STORAGE_KEY, String(collapsed))
  }

  @Action({ rawError: true })
  public setViewMode(mode: ViewModeType) {
    this.SET_VIEW_MODE(mode)
  }

  @Action({ rawError: true })
  public toggleFilterPanel() {
    this.TOGGLE_FILTER_PANEL()
  }

  @Action({ rawError: true })
  public setFilterPanelCollapsed(collapsed: boolean) {
    this.SET_FILTER_PANEL_COLLAPSED(collapsed)
  }
}

export const ViewModeModule = getModule(ViewMode)
```

**Step 2: 注册到 store**

```typescript
// src/store/index.ts
import Vue from 'vue'
import Vuex from 'vuex'
import { IAppState } from './modules/app'
import { IUserState } from './modules/user'
import { INotificationState } from './modules/notification'
import { IViewModeState } from './modules/viewMode'  // 新增

Vue.use(Vuex)

export interface IRootState {
  app: IAppState
  user: IUserState
  notification: INotificationState
  viewMode: IViewModeState  // 新增
}

export default new Vuex.Store<IRootState>({})
```

**Step 3: 提交**

```bash
git add src/store/modules/viewMode.ts src/store/index.ts
git commit -m "feat(viewMode): add viewMode Vuex module for managing list/traditional view switching"
```

---

## Task 2: 创建传统模式样式文件

**Files:**
- Create: `src/styles/traditional-view-theme.scss`

**Step 1: 创建传统模式专用样式变量**

```scss
// src/styles/traditional-view-theme.scss
/**
 * 传统模式视图专用样式
 * 基于 theme-variables.scss 的 CSS 变量派生
 * 适配三种主题色自动切换
 */

/* ========================================
   传统模式布局尺寸
   ======================================== */
--trad-filter-panel-width: 220px;
--trad-detail-panel-width: 360px;
--trad-statusbar-height: 32px;
--trad-toolbar-height: 40px;

/* ========================================
   传统模式专用颜色（基于主题色派生）
   ======================================== */
// 过滤面板背景 - 使用主题色的极浅色变体
--trad-filter-panel-bg: var(--color-primary-lightest);
--trad-filter-panel-border: color-mix(in srgb, var(--color-border-primary), var(--color-primary-lightest) 50%);

// 过滤项激活状态
--trad-filter-item-active-bg: rgba(var(--color-primary-rgb), 0.08);
--trad-filter-item-active-text: var(--color-primary);

// 表格区域
--trad-table-header-bg: var(--color-bg-secondary);
--trad-row-hover-bg: var(--color-bg-hover);
--trad-row-selected-bg: var(--color-primary-lightest);

// 详情面板
--trad-detail-panel-bg: var(--color-bg-primary);

/* ========================================
   过滤面板样式
   ======================================== */
.filter-panel {
  width: var(--trad-filter-panel-width);
  background: var(--trad-filter-panel-bg);
  border-right: 1px solid var(--trad-filter-panel-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s ease, opacity 0.2s ease;
  overflow: hidden;

  &.collapsed {
    width: 0;
    opacity: 0;
    pointer-events: none;
  }
}

.filter-panel-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--trad-filter-panel-border);
  display: flex;
  align-items: center;
  justify-content: space-between;

  h3 {
    font-size: 12px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-primary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0;
  }
}

.filter-panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;

  // 使用项目滚动条变量
  &::-webkit-scrollbar {
    width: var(--scrollbar-width);
  }

  &::-webkit-scrollbar-thumb {
    background: var(--scrollbar-thumb-bg);
    border-radius: var(--scrollbar-border-radius);
  }

  &::-webkit-scrollbar-thumb:hover {
    background: var(--scrollbar-thumb-bg-hover);
  }
}

/* ========================================
   过滤分组和项
   ======================================== */
.filter-group {
  margin-bottom: 2px;
}

.filter-group-header {
  padding: 5px 12px;
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
  transition: color var(--transition-fast);

  &:hover {
    color: var(--color-text-secondary);
  }

  .arrow {
    transition: transform 0.2s;
    font-size: 9px;

    &.collapsed {
      transform: rotate(-90deg);
    }
  }
}

.filter-group-items {
  padding: 2px 6px;
}

.filter-item {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
  gap: 6px;

  &:hover {
    background: rgba(var(--color-primary-rgb), 0.04);
  }

  &.active {
    background: var(--trad-filter-item-active-bg);
    color: var(--trad-filter-item-active-text);
  }

  .filter-icon {
    width: 14px;
    height: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    flex-shrink: 0;
  }

  .filter-label {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 12px;
  }

  .filter-count {
    font-size: 10px;
    color: var(--color-text-tertiary);
    background: rgba(var(--color-primary-rgb), 0.06);
    padding: 1px 5px;
    border-radius: 8px;
    min-width: 18px;
    text-align: center;
    transition: all var(--transition-fast);
  }

  &.active .filter-count {
    background: var(--color-primary-lightest);
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
  }
}

/* ========================================
   传统模式工具栏
   ======================================== */
.traditional-toolbar {
  height: var(--trad-toolbar-height);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-primary);
  display: flex;
  align-items: center;
  padding: 0 10px;
  gap: 3px;
  flex-shrink: 0;
}

/* ========================================
   传统模式表格
   ======================================== */
.traditional-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;

  thead {
    position: sticky;
    top: 0;
    z-index: 10;
  }

  thead th {
    background: var(--trad-table-header-bg);
    border-bottom: 1px solid var(--color-border-primary);
    padding: 7px 8px;
    font-size: 11px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    text-align: left;
    white-space: nowrap;
    user-select: none;
    cursor: pointer;
    transition: color var(--transition-fast);

    &:hover {
      color: var(--color-text-secondary);
    }

    &.sorted {
      color: var(--color-primary);
    }

    .sort-arrow {
      font-size: 9px;
      margin-left: 3px;
    }
  }

  tbody tr {
    border-bottom: 1px solid var(--color-border-secondary);
    transition: background 0.1s;
    cursor: pointer;

    &:hover {
      background: var(--trad-row-hover-bg);
    }

    &.selected {
      background: var(--trad-row-selected-bg);
    }
  }

  tbody td {
    padding: 5px 8px;
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

/* ========================================
   状态图标
   ======================================== */
.status-icon-circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 9px;
  font-weight: var(--font-weight-bold);

  &.downloading {
    background: rgba(59, 130, 246, 0.12);
    color: #3b82f6;
  }

  &.seeding {
    background: rgba(16, 185, 129, 0.12);
    color: var(--color-success);
  }

  &.paused {
    background: rgba(107, 114, 128, 0.12);
    color: #6b7280;
  }

  &.error {
    background: rgba(239, 68, 68, 0.12);
    color: var(--color-error);
  }

  &.checking {
    background: rgba(245, 158, 11, 0.12);
    color: var(--color-warning);
  }

  &.queuedDL {
    background: rgba(139, 92, 246, 0.12);
    color: #8b5cf6;
  }
}

/* ========================================
   状态徽章
   ======================================== */
.status-badge-trad {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: var(--font-weight-medium);
  white-space: nowrap;

  &.downloading {
    background: rgba(59, 130, 246, 0.08);
    color: #3b82f6;
    border: 1px solid rgba(59, 130, 246, 0.15);
  }

  &.seeding {
    background: rgba(16, 185, 129, 0.08);
    color: var(--color-success);
    border: 1px solid rgba(16, 185, 129, 0.15);
  }

  &.paused {
    background: rgba(107, 114, 128, 0.08);
    color: #6b7280;
    border: 1px solid rgba(107, 114, 128, 0.12);
  }

  &.error {
    background: rgba(239, 68, 68, 0.08);
    color: var(--color-error);
    border: 1px solid rgba(239, 68, 68, 0.15);
  }

  &.checking {
    background: rgba(245, 158, 11, 0.08);
    color: var(--color-warning);
    border: 1px solid rgba(245, 158, 11, 0.15);
  }

  &.queuedDL {
    background: rgba(139, 92, 246, 0.08);
    color: #7c3aed;
    border: 1px solid rgba(139, 92, 246, 0.15);
  }
}

/* ========================================
   进度条（紧凑版）
   ======================================== */
.progress-cell-compact {
  display: flex;
  align-items: center;
  gap: 6px;

  .progress-bar-wrapper {
    flex: 1;
    height: 4px;
    background: var(--color-bg-tertiary);
    border-radius: 2px;
    overflow: hidden;
    min-width: 50px;
  }

  .progress-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;

    &.downloading { background: var(--color-info); }
    &.seeding { background: var(--color-success); }
    &.paused { background: var(--color-text-tertiary); }
    &.error { background: var(--color-error); }
    &.checking { background: var(--color-warning); }
    &.queuedDL { background: #8b5cf6; }
  }

  .progress-text {
    font-size: 11px;
    color: var(--color-text-tertiary);
    min-width: 32px;
    text-align: right;
    font-family: var(--font-mono);
  }
}

/* ========================================
   速度值（等宽字体）
   ======================================== */
.speed-value-mono {
  font-family: var(--font-mono);
  font-size: 11px;

  &.download { color: #3b82f6; }
  &.upload { color: var(--color-success); }
  &.zero { color: var(--color-text-tertiary); }
}

/* ========================================
   比率值（颜色分级）
   ======================================== */
.ratio-value-graded {
  font-family: var(--font-mono);
  font-weight: var(--font-weight-semibold);
  font-size: 11px;

  &.low { color: var(--color-error); }
  &.mid { color: var(--color-warning); }
  &.good { color: var(--color-success); }
  &.great { color: var(--color-info); }
}

/* ========================================
   分类/标签徽章
   ======================================== */
.category-tag-mini {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  gap: 2px;

  &.cat {
    background: rgba(139, 92, 246, 0.08);
    color: #7c3aed;
    border: 1px solid rgba(139, 92, 246, 0.12);
  }

  &.tag {
    background: rgba(245, 158, 11, 0.08);
    color: var(--color-warning);
    border: 1px solid rgba(245, 158, 11, 0.12);
    margin-left: 3px;
  }
}

/* ========================================
   操作按钮组
   ======================================== */
.action-buttons-compact {
  display: flex;
  align-items: center;
  gap: 1px;

  .action-btn-mini {
    background: none;
    border: none;
    color: var(--color-text-tertiary);
    cursor: pointer;
    padding: 3px 5px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    transition: all var(--transition-fast);
    line-height: 1;

    &:hover {
      background: var(--color-bg-tertiary);
      color: var(--color-text-primary);
    }

    &.play:hover { color: var(--color-success); }
    &.pause:hover { color: var(--color-warning); }
    &.delete:hover { color: var(--color-error); }
    &.recheck:hover { color: var(--color-info); }
  }
}

/* ========================================
   详情面板
   ======================================== */
.detail-panel-trad {
  width: 0;
  overflow: hidden;
  background: var(--trad-detail-panel-bg);
  border-left: 1px solid var(--color-border-primary);
  transition: width 0.2s ease;
  flex-shrink: 0;

  &.open {
    width: var(--trad-detail-panel-width);
  }
}

.detail-panel-content {
  width: var(--trad-detail-panel-width);
  padding: 12px;
  overflow-y: auto;
  height: 100%;
}

.detail-header-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;

  h3 {
    font-size: 13px;
    font-weight: var(--font-weight-semibold);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 280px;
    margin: 0;
    color: var(--color-text-primary);
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--color-text-tertiary);
    cursor: pointer;
    font-size: 16px;
    padding: 2px 4px;
    border-radius: var(--radius-sm);
    transition: all var(--transition-fast);

    &:hover {
      background: var(--color-bg-tertiary);
      color: var(--color-text-primary);
    }
  }
}

.detail-tabs-compact {
  display: flex;
  gap: 1px;
  border-bottom: 1px solid var(--color-border-primary);
  margin-bottom: 10px;

  .tab-btn {
    padding: 5px 10px;
    font-size: 11px;
    color: var(--color-text-tertiary);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all var(--transition-fast);
    background: none;
    border-top: none;
    border-left: none;
    border-right: none;

    &:hover {
      color: var(--color-text-secondary);
    }

    &.active {
      color: var(--color-primary);
      border-bottom-color: var(--color-primary);
    }
  }
}

.detail-field-row {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid var(--color-border-secondary);

  .field-label {
    color: var(--color-text-tertiary);
    font-size: 11px;
  }

  .field-value {
    font-size: 11px;
    color: var(--color-text-primary);
    text-align: right;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

/* ========================================
   全局状态栏
   ======================================== */
.global-statusbar-compact {
  height: var(--trad-statusbar-height);
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-primary);
  display: flex;
  align-items: center;
  padding: 0 10px;
  gap: 12px;
  flex-shrink: 0;
  font-size: 11px;

  .statusbar-section {
    display: flex;
    align-items: center;
    gap: 4px;

    .label {
      color: var(--color-text-tertiary);
    }
  }

  .global-speed {
    display: flex;
    align-items: center;
    gap: 3px;

    .speed-icon {
      font-size: 11px;

      &.down { color: #3b82f6; }
      &.up { color: var(--color-success); }
    }

    .speed-val {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: var(--font-weight-semibold);
    }
  }

  .statusbar-sep {
    width: 1px;
    height: 14px;
    background: var(--color-border-primary);
  }

  .connection-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--color-success);
  }

  .statusbar-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 10px;
  }
}
```

**Step 2: 在样式入口文件中导入**

```scss
// src/styles/index.scss
// 在现有导入后添加
@import './traditional-view-theme.scss';
```

**Step 3: 提交**

```bash
git add src/styles/traditional-view-theme.scss src/styles/index.scss
git commit -m "feat(styles): add traditional view theme styles with CSS variables"
```

---

## Task 3: 创建传统模式视图组件

**Files:**
- Create: `src/views/torrents/TraditionalView.vue`

**Step 1: 创建 TraditionalView 组件骨架**

```vue
<!-- src/views/torrents/TraditionalView.vue -->
<template>
  <div class="traditional-page">
    <!-- 工具栏 -->
    <div class="traditional-toolbar">
      <!-- 左侧操作区 -->
      <div class="toolbar-left">
        <el-button
          class="filter-toggle-btn"
          type="text"
          icon="el-icon-s-fold"
          @click="toggleFilterPanel"
          title="切换过滤面板"
        />
        <div class="tool-divider"></div>
        <el-button
          type="text"
          size="small"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchStart"
        >
          <i class="el-icon-video-play"></i> 开始
        </el-button>
        <el-button
          type="text"
          size="small"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchPause"
        >
          <i class="el-icon-video-pause"></i> 暂停
        </el-button>
        <el-button
          type="text"
          size="small"
          class="danger"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchDelete"
        >
          <i class="el-icon-delete"></i> 删除
        </el-button>
        <div class="tool-divider"></div>
        <el-button
          type="text"
          size="small"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchRecheck"
        >
          <i class="el-icon-refresh"></i> 重检
        </el-button>
        <div class="selection-info" :class="{ visible: multipleSelection.length > 0 }">
          已选 <span class="count">{{ multipleSelection.length }}</span> 个
        </div>
      </div>

      <!-- 中间搜索区 -->
      <div class="toolbar-center">
        <el-input
          v-model="listQuery.name_like"
          placeholder="搜索种子名称..."
          prefix-icon="el-icon-search"
          size="small"
          clearable
          class="search-input"
          @input="debouncedSearch"
          @keyup.enter.native="handleFilter"
        />
      </div>

      <!-- 右侧操作区 -->
      <div class="toolbar-right">
        <el-button
          type="primary"
          size="small"
          icon="el-icon-plus"
          @click="showAddDialog = true"
        >
          添加
        </el-button>
        <div class="tool-divider"></div>
        <div class="view-switcher">
          <el-button
            type="text"
            size="small"
            :class="{ active: viewModeModule.currentMode === 'list' }"
            @click="switchViewMode('list')"
            title="列表模式"
          >
            <i class="el-icon-s-grid"></i>
          </el-button>
          <el-button
            type="text"
            size="small"
            :class="{ active: viewModeModule.currentMode === 'traditional' }"
            @click="switchViewMode('traditional')"
            title="传统模式"
          >
            <i class="el-icon-menu"></i>
          </el-button>
        </div>
      </div>
    </div>

    <!-- 页面主体：过滤面板 + 表格 + 详情 -->
    <div class="page-body">
      <!-- 左侧过滤面板 -->
      <aside class="filter-panel" :class="{ collapsed: viewModeModule.filterPanelCollapsed }">
        <div class="filter-panel-header">
          <h3>过滤器</h3>
          <el-button
            type="text"
            class="filter-toggle-btn"
            icon="el-icon-d-arrow-left"
            @click="toggleFilterPanel"
            title="收起"
          />
        </div>

        <div class="filter-panel-content">
          <!-- 状态过滤 -->
          <FilterGroup
            title="状态"
            :items="statusFilterItems"
            :active-value="listQuery.status"
            @select="handleStatusFilter"
          />

          <!-- 下载器过滤 -->
          <FilterGroup
            title="下载器"
            :items="downloaderFilterItems"
            :active-value="listQuery.downloader_id"
            @select="handleDownloaderFilter"
          />

          <!-- 分类过滤 -->
          <FilterGroup
            title="分类"
            :items="categoryFilterItems"
            :active-value="listQuery.category_like"
            @select="handleCategoryFilter"
          />

          <!-- 标签过滤 -->
          <FilterGroup
            title="标签"
            :items="tagFilterItems"
            :active-value="listQuery.tags_like"
            @select="handleTagFilter"
          />
        </div>
      </aside>

      <!-- 表格区域 -->
      <div class="table-area">
        <div class="table-container" v-loading="listLoading">
          <table class="torrent-table traditional-table">
            <thead>
              <tr>
                <th class="col-checkbox">
                  <el-checkbox
                    :indeterminate="isIndeterminate"
                    v-model="selectAll"
                    @change="handleSelectAll"
                  />
                </th>
                <th class="col-status-icon"></th>
                <th class="col-name" @click="handleSort('name')">
                  名称
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'name'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th class="col-size" @click="handleSort('size')">
                  大小
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'size'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th class="col-progress">进度</th>
                <th class="col-status" @click="handleSort('status')">
                  状态
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'status'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th class="col-downspeed">↓ 下载</th>
                <th class="col-upspeed">↑ 上传</th>
                <th class="col-ratio" @click="handleSort('ratio')">
                  比率
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'ratio'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th class="col-downloader">下载器</th>
                <th class="col-category">分类/标签</th>
                <th class="col-added" @click="handleSort('addedDate')">
                  添加时间
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'addedDate'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(torrent, index) in sortedList"
                :key="`${torrent.hash}-${torrent.downloaderId || torrent.downloader_id}-${index}`"
                :class="{ selected: currentRow?.hash === torrent.hash }"
                @click="handleRowClick(torrent)"
              >
                <td class="col-checkbox">
                  <el-checkbox v-model="torrent.checked" @change="handleSelectionChange" @click.native.stop />
                </td>
                <td class="col-status-icon">
                  <div
                    class="status-icon-circle"
                    :class="torrent.status"
                    :title="getStatusText(torrent.status)"
                  >
                    {{ getStatusIcon(torrent.status) }}
                  </div>
                </td>
                <td class="col-name">
                  <div class="torrent-name-cell">
                    <span class="torrent-name-text" :title="torrent.name">{{ torrent.name }}</span>
                  </div>
                </td>
                <td class="col-size">{{ formatFileSize(torrent.size) }}</td>
                <td class="col-progress">
                  <div class="progress-cell-compact">
                    <div class="progress-bar-wrapper">
                      <div
                        class="progress-bar-fill"
                        :class="torrent.status"
                        :style="{ width: `${torrent.progress || 0}%` }"
                      ></div>
                    </div>
                    <span class="progress-text">{{ torrent.progress || 0 }}%</span>
                  </div>
                </td>
                <td class="col-status">
                  <span class="status-badge-trad" :class="torrent.status">{{ getStatusText(torrent.status) }}</span>
                </td>
                <td class="col-downspeed">
                  <span
                    class="speed-value-mono"
                    :class="getTorrentSpeed(torrent, 'download') ? 'download' : 'zero'"
                  >
                    {{ formatSpeed(getTorrentSpeed(torrent, 'download')) }}
                  </span>
                </td>
                <td class="col-upspeed">
                  <span
                    class="speed-value-mono"
                    :class="getTorrentSpeed(torrent, 'upload') ? 'upload' : 'zero'"
                  >
                    {{ formatSpeed(getTorrentSpeed(torrent, 'upload')) }}
                  </span>
                </td>
                <td class="col-ratio">
                  <span
                    class="ratio-value-graded"
                    :class="getRatioClass(torrent.ratio)"
                  >
                    {{ formatRatio(torrent.ratio) }}
                  </span>
                </td>
                <td class="col-downloader">{{ torrent.downloaderName || '-' }}</td>
                <td class="col-category">
                  <span v-if="torrent.category" class="category-tag-mini cat">{{ torrent.category }}</span>
                  <span v-if="torrent.tags" class="category-tag-mini tag">{{ torrent.tags }}</span>
                  <span v-if="!torrent.category && !torrent.tags" style="color: var(--color-text-tertiary)">-</span>
                </td>
                <td class="col-added">{{ formatDate(torrent.addedDate) }}</td>
                <td class="col-actions">
                  <div class="action-buttons-compact">
                    <button
                      class="action-btn-mini"
                      :class="torrent.status === 'paused' ? 'play' : 'pause'"
                      @click.stop="handleTogglePause(torrent)"
                      :title="torrent.status === 'paused' ? '开始' : '暂停'"
                    >
                      {{ torrent.status === 'paused' ? '▶' : '⏸' }}
                    </button>
                    <button
                      class="action-btn-mini recheck"
                      @click.stop="handleRecheck(torrent)"
                      title="重新检查"
                    >
                      ↻
                    </button>
                    <button
                      class="action-btn-mini delete"
                      @click.stop="handleDelete(torrent)"
                      title="删除"
                    >
                      🗑
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 分页 -->
        <div class="table-pagination">
          <div class="pagination-info">
            <el-select v-model="pageSize" size="mini" class="page-size-select" @change="handlePageSizeChange">
              <el-option
                v-for="size in pageSizeOptions"
                :key="size"
                :label="`${size} 条/页`"
                :value="size"
              />
            </el-select>
            <span>共 <strong>{{ total }}</strong> 条，第 <strong>{{ currentPage }}</strong>/<strong>{{ totalPages }}</strong> 页</span>
          </div>
          <div class="pagination-controls">
            <el-button
              size="mini"
              :disabled="currentPage <= 1"
              @click="handlePageChange(currentPage - 1)"
            >
              ◀
            </el-button>
            <el-button
              v-for="page in visiblePages"
              :key="page"
              size="mini"
              :class="{ active: page === currentPage }"
              @click="handlePageChange(page)"
            >
              {{ page }}
            </el-button>
            <el-button
              size="mini"
              :disabled="currentPage >= totalPages"
              @click="handlePageChange(currentPage + 1)"
            >
              ▶
            </el-button>
          </div>
        </div>
      </div>

      <!-- 右侧详情面板 -->
      <div class="detail-panel-trad" :class="{ open: !!currentRow }">
        <div class="detail-panel-content">
          <div class="detail-header-compact">
            <h3>{{ currentRow?.name }}</h3>
            <button class="close-btn" @click="closeDetailPanel">✕</button>
          </div>
          <div class="detail-tabs-compact">
            <button
              v-for="tab in detailTabs"
              :key="tab.value"
              class="tab-btn"
              :class="{ active: activeDetailTab === tab.value }"
              @click="activeDetailTab = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>
          <div class="detail-content">
            <!-- 常规信息 -->
            <template v-if="activeDetailTab === 'general'">
              <div class="detail-field-row">
                <span class="field-label">状态</span>
                <span class="field-value">
                  <span class="status-badge-trad" :class="currentRow?.status">{{ getStatusText(currentRow?.status) }}</span>
                </span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">进度</span>
                <span class="field-value">{{ currentRow?.progress || 0 }}%</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">大小</span>
                <span class="field-value">{{ formatFileSize(currentRow?.size) }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">下载速度</span>
                <span class="field-value speed-value-mono download">{{ formatSpeed(getTorrentSpeed(currentRow, 'download')) }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">上传速度</span>
                <span class="field-value speed-value-mono upload">{{ formatSpeed(getTorrentSpeed(currentRow, 'upload')) }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">分享率</span>
                <span class="field-value ratio-value-graded" :class="getRatioClass(currentRow?.ratio)">
                  {{ formatRatio(currentRow?.ratio) }}
                </span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">所属下载器</span>
                <span class="field-value">{{ currentRow?.downloaderName }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">分类</span>
                <span class="field-value">{{ currentRow?.category || '-' }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">标签</span>
                <span class="field-value">{{ currentRow?.tags || '-' }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">保存路径</span>
                <span class="field-value" :title="currentRow?.savePath">{{ currentRow?.savePath }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">添加时间</span>
                <span class="field-value">{{ formatDate(currentRow?.addedDate) }}</span>
              </div>
            </template>

            <!-- Tracker 信息 -->
            <template v-else-if="activeDetailTab === 'tracker'">
              <table class="tracker-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>地址</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(tracker, index) in (currentRow?.tracker_info || currentRow?.trackerInfo || [])"
                    :key="index"
                  >
                    <td>{{ tracker.tracker_name || tracker.trackerName || '未知' }}</td>
                    <td>
                      <span class="tracker-status">
                        <span
                          class="dot"
                          :class="isTrackerSuccess(tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded) ? 'ok' : 'fail'"
                        ></span>
                        {{ getTrackerStatusText(tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded) }}
                      </span>
                    </td>
                    <td :title="tracker.tracker_url || tracker.trackerUrl || '-'">
                      {{ (tracker.tracker_url || tracker.trackerUrl || '-').slice(0, 30) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </template>

            <!-- 文件列表（占位） -->
            <template v-else-if="activeDetailTab === 'files'">
              <div style="text-align: center; color: var(--color-text-tertiary); padding: 20px;">
                文件列表功能开发中...
              </div>
            </template>

            <!-- Peers（占位） -->
            <template v-else-if="activeDetailTab === 'peers'">
              <div style="text-align: center; color: var(--color-text-tertiary); padding: 20px;">
                Peers 信息功能开发中...
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部全局状态栏 -->
    <div class="global-statusbar-compact">
      <div class="statusbar-section">
        <div class="connection-dot"></div>
        <span style="color: var(--color-text-secondary);">已连接</span>
      </div>
      <div class="statusbar-sep"></div>
      <div class="statusbar-section">
        <div class="global-speed">
          <span class="speed-icon down">↓</span>
          <span class="speed-val" style="color: #3b82f6;">{{ formatSpeed(globalDownloadSpeed) }}</span>
        </div>
        <div class="global-speed">
          <span class="speed-icon up">↑</span>
          <span class="speed-val" style="color: var(--color-success);">{{ formatSpeed(globalUploadSpeed) }}</span>
        </div>
      </div>
      <div class="statusbar-sep"></div>
      <div class="statusbar-section">
        <span class="label">活动:</span>
        <span style="color: var(--color-text-primary);">{{ activeTorrentCount }}</span>
        <span class="label">/ {{ total }}</span>
      </div>
      <div class="statusbar-right">
        <div
          v-for="downloader in downloaderList"
          :key="downloader.downloader_id"
          class="statusbar-section"
        >
          <span class="label">{{ downloader.nickname }}</span>
          <span style="color: var(--color-success);">●</span>
        </div>
      </div>
    </div>

    <!-- 复用现有对话框组件 -->
    <TorrentAddDialog
      :visible.sync="showAddDialog"
      :downloaders="downloaderList"
      @confirm="handleAdd"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue, Watch } from 'vue-property-decorator'
import { ViewModeModule, ViewModeType } from '@/store/modules/viewMode'
import TorrentAddDialog from './components/TorrentAddDialog.vue'
import FilterGroup from '@/components/torrents/FilterGroup.vue'
// 复用现有 API、工具函数、状态配置
import {
  getTorrentList,
  addTorrent,
  deleteTorrents,
  pauseTorrents,
  resumeTorrents,
  recheckTorrents,
  getDownloaderList,
  type DownloaderSimple
} from '@/api/torrents'
import { STATUS_OPTIONS, getStatusIcon, getStatusText } from '@/constants/status-config'
import {
  formatFileSize,
  formatSpeed,
  formatDate,
  formatRatio,
  truncateText,
  normalizeTorrent,
  normalizePaginatedResponse,
  debounce
} from '@/utils/formatters'

interface FilterItem {
  icon: string
  label: string
  value: string
  count?: number
}

@Component({
  name: 'TraditionalView',
  components: {
    TorrentAddDialog,
    FilterGroup
  }
})
export default class extends Vue {
  // ====== 状态管理 ======
  private viewModeModule = ViewModeModule

  // ====== 数据状态 ======
  private list: any[] = []
  private total = 0
  private listLoading = true
  private multipleSelection: any[] = []

  // 实时速度轮询
  private speedTimer: number | null = null
  private activeSpeedMap: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}

  // 分页
  private currentPage = 1
  private pageSize = 20
  private pageSizeOptions = [10, 20, 50, 100]

  // 复选框
  private selectAll = false
  private isIndeterminate = false

  // 弹窗状态
  private showAddDialog = false

  // 详情面板
  private currentRow: any = null
  private activeDetailTab = 'general'
  private detailTabs = [
    { label: '常规', value: 'general' },
    { label: 'Tracker', value: 'tracker' },
    { label: '文件', value: 'files' },
    { label: 'Peers', value: 'peers' }
  ]

  // 查询参数（复用现有结构）
  private listQuery: any = {
    skip: 0,
    limit: 20,
    name_like: '',
    downloader_id: [],
    status: [],
    category_like: '',
    tags_like: '',
    sort_by: 'addedDate',
    sort_order: 'desc'
  }

  // 下载器列表
  private downloaderList: DownloaderSimple[] = []

  // 防抖搜索
  private debouncedSearch: any = null

  // ====== 计算属性 ======
  get totalPages() {
    return Math.ceil(this.total / this.pageSize)
  }

  get visiblePages() {
    const pages: number[] = []
    const showPages = 5
    let start = Math.max(1, this.currentPage - Math.floor(showPages / 2))
    let end = Math.min(this.totalPages, start + showPages - 1)

    if (end - start < showPages - 1) {
      start = Math.max(1, end - showPages + 1)
    }

    for (let i = start; i <= end; i++) {
      pages.push(i)
    }

    return pages
  }

  get sortedList() {
    // 复用现有排序逻辑：活跃种子优先
    return this.list.slice().sort((a, b) => {
      const aActive = !!this.activeSpeedMap[a.hash]
      const bActive = !!this.activeSpeedMap[b.hash]

      if (aActive && !bActive) return -1
      if (!aActive && bActive) return 1

      return 0
    })
  }

  get globalDownloadSpeed() {
    return Object.values(this.activeSpeedMap).reduce((sum, s) => sum + s.downloadSpeed, 0)
  }

  get globalUploadSpeed() {
    return Object.values(this.activeSpeedMap).reduce((sum, s) => sum + s.uploadSpeed, 0)
  }

  get activeTorrentCount() {
    return Object.keys(this.activeSpeedMap).length
  }

  // ====== 过滤器数据 ======
  get statusFilterItems(): FilterItem[] {
    return [
      { icon: '📥', label: '全部', value: '' },
      ...STATUS_OPTIONS.map(opt => ({
        icon: getStatusIcon(opt.value),
        label: opt.label.replace(/^[^\s]+\s*/, ''),
        value: opt.value
      }))
    ]
  }

  get downloaderFilterItems(): FilterItem[] {
    return [
      { icon: '🖥', label: '全部', value: '' },
      ...this.downloaderList.map(d => ({
        icon: '🔵',
        label: d.nickname,
        value: d.downloader_id
      }))
    ]
  }

  get categoryFilterItems(): FilterItem[] {
    // TODO: 从 API 获取分类列表
    return [
      { icon: '📂', label: '全部', value: '' },
      { icon: '🎬', label: '电影', value: '电影' },
      { icon: '📺', label: '剧集', value: '剧集' },
      { icon: '🎵', label: '音乐', value: '音乐' },
      { icon: '💿', label: '软件', value: '软件' }
    ]
  }

  get tagFilterItems(): FilterItem[] {
    // TODO: 从 API 获取标签列表
    return [
      { icon: '🏷', label: 'PT', value: 'PT' },
      { icon: '🏷', label: 'BT', value: 'BT' }
    ]
  }

  // ====== 生命周期 ======
  public async created() {
    this.debouncedSearch = debounce(this.handleFilter, 300)
    await this.fetchDownloaderList()
    await this.getList()
    this.startSpeedPolling()
  }

  public beforeDestroy() {
    this.stopSpeedPolling()
  }

  // ====== 数据获取 ======
  private async getList() {
    this.listLoading = true
    try {
      const params = { ...this.listQuery }
      params.skip = (this.currentPage - 1) * this.pageSize
      params.limit = this.pageSize

      // 处理数组参数
      if (Array.isArray(params.downloader_id) && params.downloader_id.length > 0) {
        params.downloader_id = params.downloader_id.join(',')
      } else {
        delete params.downloader_id
      }

      if (Array.isArray(params.status) && params.status.length > 0) {
        params.status = params.status.join(',')
      } else {
        delete params.status
      }

      // 清理空值
      Object.keys(params).forEach(key => {
        if (params[key] === '' || params[key] === null || params[key] === undefined) {
          delete params[key]
        }
      })

      const response = await getTorrentList(params)
      const { list, total } = normalizePaginatedResponse(response)

      this.list = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))
      this.total = total
    } catch (error) {
      console.error('获取种子列表失败:', error)
      this.$message.error('获取种子列表失败')
    } finally {
      this.listLoading = false
    }
  }

  private async fetchDownloaderList() {
    try {
      const response = await getDownloaderList()
      this.downloaderList = response.data || []
    } catch (error) {
      console.error('获取下载器列表失败:', error)
    }
  }

  // ====== 实时速度轮询 ======
  private startSpeedPolling() {
    const poll = async () => {
      await this.loadActiveSpeed()
      this.speedTimer = window.setTimeout(poll, 1000)
    }
    poll()
  }

  private stopSpeedPolling() {
    if (this.speedTimer) {
      window.clearTimeout(this.speedTimer)
      this.speedTimer = null
    }
  }

  private async loadActiveSpeed() {
    try {
      const response = await fetch(`${process.env.VUE_APP_BASE_API}/torrents/active-torrents`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })
      const data = await response.json()

      if (data.code === '200' && data.data) {
        this.activeSpeedMap = {}
        data.data.forEach((t: any) => {
          this.activeSpeedMap[t.hash] = {
            downloadSpeed: t.downloadSpeed,
            uploadSpeed: t.uploadSpeed,
            progress: t.progress
          }

          // 直接更新列表
          const torrentInList = this.list.find(item => item.hash === t.hash)
          if (torrentInList) {
            torrentInList.downloadSpeed = t.downloadSpeed
            torrentInList.uploadSpeed = t.uploadSpeed
            torrentInList.progress = t.progress
          }
        })
      }
    } catch (error) {
      console.error('获取活跃种子速度失败:', error)
    }
  }

  private getTorrentSpeed(torrent: any, type: 'download' | 'upload'): number | null {
    const active = this.activeSpeedMap[torrent.hash]
    if (active) {
      return type === 'download' ? active.downloadSpeed : active.uploadSpeed
    }
    return type === 'download' ? torrent.downloadSpeed : torrent.uploadSpeed
  }

  // ====== 工具方法 ======
  private formatFileSize = formatFileSize
  private formatSpeed = formatSpeed
  private formatDate = formatDate
  private formatRatio = formatRatio
  private getStatusIcon = getStatusIcon
  private getStatusText = getStatusText

  private getRatioClass(ratio: number | string) {
    const r = typeof ratio === 'string' ? parseFloat(ratio) : ratio
    if (r < 0.5) return 'low'
    if (r < 1.0) return 'mid'
    if (r < 2.0) return 'good'
    return 'great'
  }

  private isTrackerSuccess(status: string): boolean {
    return status === '工作中' || status === 'success' || status === true
  }

  private getTrackerStatusText(status: string): string {
    if (this.isTrackerSuccess(status)) return '工作中'
    return '失败'
  }

  // ====== 事件处理 ======
  private handleFilter() {
    this.currentPage = 1
    this.getList()
  }

  private handleSort(field: string) {
    if (this.listQuery.sort_by === field) {
      this.listQuery.sort_order = this.listQuery.sort_order === 'asc' ? 'desc' : 'asc'
    } else {
      this.listQuery.sort_by = field
      this.listQuery.sort_order = 'desc'
    }
    this.getList()
  }

  private handlePageChange(page: number) {
    this.currentPage = page
    this.getList()
  }

  private handlePageSizeChange() {
    this.currentPage = 1
    this.getList()
  }

  private handleSelectAll(checked: boolean) {
    this.list.forEach(item => {
      item.checked = checked
    })
    this.handleSelectionChange()
  }

  private handleSelectionChange() {
    this.multipleSelection = this.list.filter(item => item.checked)
    this.isIndeterminate = this.multipleSelection.length > 0 && this.multipleSelection.length < this.list.length
    this.selectAll = this.multipleSelection.length === this.list.length
  }

  private handleRowClick(torrent: any) {
    if (this.currentRow?.hash === torrent.hash) {
      this.currentRow = null
      return
    }
    this.currentRow = torrent
    this.activeDetailTab = 'general'
  }

  private closeDetailPanel() {
    this.currentRow = null
  }

  private toggleFilterPanel() {
    this.viewModeModule.toggleFilterPanel()
  }

  private switchViewMode(mode: ViewModeType) {
    this.viewModeModule.setViewMode(mode)
    // 触发父组件切换
    this.$emit('switch-view', mode)
  }

  // 过滤器选择
  private handleStatusFilter(value: string) {
    if (value === '') {
      this.listQuery.status = []
    } else {
      this.listQuery.status = [value]
    }
    this.handleFilter()
  }

  private handleDownloaderFilter(value: string) {
    if (value === '') {
      this.listQuery.downloader_id = []
    } else {
      this.listQuery.downloader_id = [value]
    }
    this.handleFilter()
  }

  private handleCategoryFilter(value: string) {
    this.listQuery.category_like = value
    this.handleFilter()
  }

  private handleTagFilter(value: string) {
    this.listQuery.tags_like = value
    this.handleFilter()
  }

  // 批量操作（复用现有逻辑）
  private async handleBatchStart() {
    // TODO: 实现批量开始逻辑
    console.log('批量开始:', this.multipleSelection)
  }

  private async handleBatchPause() {
    // TODO: 实现批量暂停逻辑
    console.log('批量暂停:', this.multipleSelection)
  }

  private async handleBatchDelete() {
    // TODO: 实现批量删除逻辑
    console.log('批量删除:', this.multipleSelection)
  }

  private async handleBatchRecheck() {
    // TODO: 实现批量重检逻辑
    console.log('批量重检:', this.multipleSelection)
  }

  private async handleTogglePause(torrent: any) {
    // TODO: 实现单个种子暂停/开始逻辑
    console.log('切换暂停状态:', torrent)
  }

  private async handleRecheck(torrent: any) {
    // TODO: 实现单个种子重检逻辑
    console.log('重检种子:', torrent)
  }

  private async handleDelete(torrent: any) {
    // TODO: 实现单个种子删除逻辑
    console.log('删除种子:', torrent)
  }

  private async handleAdd(torrentData: any) {
    // TODO: 实现添加种子逻辑
    console.log('添加种子:', torrentData)
  }
}
</script>

<style lang="scss" scoped>
// 复用现有样式变量
@import '@/styles/traditional-view-theme.scss';

.traditional-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.page-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
}

.toolbar-center {
  flex: 1;
  justify-content: center;
  gap: 8px;
}

.filter-toggle-btn {
  font-size: 16px;
}

.tool-divider {
  width: 1px;
  height: 18px;
  background: var(--color-border-primary);
  margin: 0 3px;
}

.search-input {
  width: 220px;

  ::v-deep .el-input__inner {
    font-size: 12px;
  }
}

.selection-info {
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 3px 7px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  display: none;

  &.visible {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .count {
    color: var(--color-primary);
    font-weight: var(--font-weight-semibold);
  }
}

.view-switcher {
  display: flex;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  padding: 2px;
  gap: 1px;

  .el-button--text {
    &.active {
      background: var(--color-primary);
      color: white;
    }
  }
}

.table-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.table-container {
  flex: 1;
  overflow: auto;
  position: relative;

  // 使用项目滚动条样式
  &::-webkit-scrollbar {
    width: var(--scrollbar-width);
    height: var(--scrollbar-height);
  }

  &::-webkit-scrollbar-thumb {
    background: var(--scrollbar-thumb-bg);
    border-radius: var(--scrollbar-border-radius);
  }

  &::-webkit-scrollbar-thumb:hover {
    background: var(--scrollbar-thumb-bg-hover);
  }
}

// 表格列宽
.col-checkbox { width: 36px; text-align: center !important; }
.col-status-icon { width: 32px; text-align: center !important; }
.col-name { /* auto */ }
.col-size { width: 80px; }
.col-progress { width: 130px; }
.col-status { width: 90px; }
.col-downspeed { width: 90px; }
.col-upspeed { width: 90px; }
.col-ratio { width: 60px; }
.col-downloader { width: 100px; }
.col-category { width: 130px; }
.col-added { width: 120px; }
.col-actions { width: 100px; }

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-primary);
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;

  .pagination-info {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .pagination-controls {
    display: flex;
    align-items: center;
    gap: 1px;

    .el-button--mini {
      &.active {
        background: var(--color-primary);
        color: white;
        border-color: var(--color-primary);
      }
    }
  }

  .page-size-select {
    width: 90px;
  }
}
</style>
```

**Step 2: 提交**

```bash
git add src/views/torrents/TraditionalView.vue
git commit -m "feat(torrents): add TraditionalView component with filter panel, table and detail panel"
```

---

## Task 4: 创建过滤分组组件

**Files:**
- Create: `src/components/torrents/FilterGroup.vue`

**Step 1: 创建 FilterGroup 组件**

```vue
<!-- src/components/torrents/FilterGroup.vue -->
<template>
  <div class="filter-group">
    <div class="filter-group-header" @click="toggleCollapsed">
      <span>{{ title }}</span>
      <span class="arrow" :class="{ collapsed }">▾</span>
    </div>
    <div class="filter-group-items" v-show="!collapsed">
      <div
        v-for="item in items"
        :key="item.value"
        class="filter-item"
        :class="{ active: isActive(item.value) }"
        @click="$emit('select', item.value)"
      >
        <span class="filter-icon">{{ item.icon }}</span>
        <span class="filter-label" :title="item.label">{{ item.label }}</span>
        <span v-if="item.count !== undefined" class="filter-count">{{ item.count }}</span>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

export interface FilterItem {
  icon: string
  label: string
  value: string
  count?: number
}

@Component({
  name: 'FilterGroup'
})
export default class extends Vue {
  @Prop(String) readonly title!: string
  @Prop({ type: Array as () => FilterItem[], default: () => [] }) readonly items!: FilterItem[]
  @Prop({ type: [String, Array] as () => string | string[], default: '' }) readonly activeValue!: string | string[]

  private collapsed = false

  private toggleCollapsed() {
    this.collapsed = !this.collapsed
  }

  private isActive(value: string): boolean {
    if (Array.isArray(this.activeValue)) {
      return this.activeValue.includes(value)
    }
    return this.activeValue === value
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/traditional-view-theme.scss';
</style>
```

**Step 2: 提交**

```bash
git add src/components/torrents/FilterGroup.vue
git commit -m "feat(components): add FilterGroup component for traditional view filter panel"
```

---

## Task 5: 修改路由配置添加传统模式路由

**Files:**
- Modify: `src/router.ts`

**Step 1: 添加传统模式路由**

```typescript
// 在 src/router.ts 的 torrents 子路由中添加新路由
{
  path: 'traditional',
  component: () => import(/* webpackChunkName: "torrents-traditional" */ '@/views/torrents/TraditionalView.vue'),
  meta: {
    keepAlive: true,
    title: '种子列表（传统模式）',
    icon: 'list',
    hidden: true // 不在侧边栏显示
  }
}
```

**Step 2: 提交**

```bash
git add src/router.ts
git commit -m "feat(router): add traditional view route for torrents page"
```

---

## Task 6: 创建视图切换包装组件

**Files:**
- Create: `src/views/torrents/TorrentViewSwitcher.vue`

**Step 1: 创建视图切换器组件**

```vue
<!-- src/views/torrents/TorrentViewSwitcher.vue -->
<template>
  <component :is="currentViewComponent" />
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { ViewModeModule, ViewModeType } from '@/store/modules/viewMode'
import ListView from './index.vue'
import TraditionalView from './TraditionalView.vue'

@Component({
  name: 'TorrentViewSwitcher',
  components: {
    ListView,
    TraditionalView
  }
})
export default class extends Vue {
  private viewModeModule = ViewModeModule

  get currentViewComponent() {
    return this.viewModeModule.currentMode === 'traditional' ? 'TraditionalView' : 'ListView'
  }

  get currentMode(): ViewModeType {
    return this.viewModeModule.currentMode
  }
}
</script>
```

**Step 2: 提交**

```bash
git add src/views/torrents/TorrentViewSwitcher.vue
git commit -m "feat(torrents): add TorrentViewSwitcher component for view mode switching"
```

---

## Task 7: 更新路由使用视图切换器

**Files:**
- Modify: `src/router.ts`

**Step 1: 将种子列表主路由改为使用切换器**

```typescript
// 修改 src/router.ts 中的种子列表路由
{
  path: 'index',
  component: () => import(/* webpackChunkName: "torrents" */ '@/views/torrents/TorrentViewSwitcher.vue'),
  meta: {
    keepAlive: true,
    title: '种子列表',
    icon: 'list'
  }
}
```

**Step 2: 提交**

```bash
git add src/router.ts
git commit -m "feat(router): update torrents index route to use TorrentViewSwitcher"
```

---

## Task 8: 在传统模式工具栏添加视图切换按钮

**Files:**
- Modify: `src/views/torrents/TraditionalView.vue`

**Step 1: 更新视图切换按钮逻辑（移除冗余）**

由于已经通过路由切换实现视图模式，工具栏中的视图切换按钮可以改为触发路由跳转：

```vue
<!-- 替换视图切换器部分 -->
<div class="view-switcher">
  <el-button
    type="text"
    size="small"
    :class="{ active: $route.path === '/torrents/index' }"
    @click="navigateToListView"
    title="列表模式"
  >
    <i class="el-icon-s-grid"></i>
  </el-button>
  <el-button
    type="text"
    size="small"
    :class="{ active: $route.path === '/torrents/traditional' }"
    @click="navigateToTraditionalView"
    title="传统模式"
  >
    <i class="el-icon-menu"></i>
  </el-button>
</div>
```

```typescript
// 在 script 中添加方法
private navigateToListView() {
  this.$router.push('/torrents/index')
}

private navigateToTraditionalView() {
  this.$router.push('/torrents/traditional')
}
```

**Step 2: 提交**

```bash
git add src/views/torrents/TraditionalView.vue
git commit -m "feat(torrents): update view switcher to use router navigation"
```

---

## Task 9: 修复 theme-variables.scss 添加主色调 RGB 值

**Files:**
- Modify: `src/styles/theme-variables.scss`

**Step 1: 为每个主题添加 RGB 变量（用于 rgba 计算）**

```scss
// 在 :root, [data-theme="emerald"] 中添加
--color-primary-rgb: 5, 150, 105;  /* #059669 */

// 在 [data-theme="orange"] 中添加
--color-primary-rgb: 234, 88, 12;  /* #EA580C */

// 在 [data-theme="graphite"] 中添加
--color-primary-rgb: 55, 65, 81;  /* #374151 */
```

**Step 2: 提交**

```bash
git add src/styles/theme-variables.scss
git commit -m "feat(styles): add primary color RGB values for rgba calculations"
```

---

## Task 10: 创建 utils/cookies 工具函数（如不存在）

**Files:**
- Check: `src/utils/cookies.ts`

**Step 1: 检查是否存在 getStorage/setStorage 函数**

如果文件不存在或函数不完整，添加：

```typescript
// src/utils/cookies.ts
export function getStorage(key: string): string | null {
  const value = localStorage.getItem(key)
  return value ? value : null
}

export function setStorage(key: string, value: string): void {
  localStorage.setItem(key, value)
}
```

**Step 2: 提交（如果需要）**

```bash
git add src/utils/cookies.ts
git commit -m "feat(utils): ensure getStorage/setStorage functions exist"
```

---

## Task 11: 完善批量操作逻辑

**Files:**
- Modify: `src/views/torrents/TraditionalView.vue`

**Step 1: 从 index.vue 复制批量操作方法**

将现有 `index.vue` 中的以下方法复制到 `TraditionalView.vue`：

- `handleBatchStart`
- `handleBatchPause`
- `handleBatchDelete`
- `handleBatchRecheck`
- `handleTogglePause`
- `handleRecheck`
- `handleDelete`
- `handleAdd`

这些方法已包含完整的 API 调用和错误处理逻辑。

**Step 2: 提交**

```bash
git add src/views/torrents/TraditionalView.vue
git commit -m "feat(torrents): implement batch operations in TraditionalView"
```

---

## Task 12: 测试视图切换功能

**Files:**
- No file changes (testing)

**Step 1: 启动开发服务器**

```bash
cd /c/software/full_stack/BtDeck/frontend
npm run serve
```

**Step 2: 手动测试清单**

- [ ] 访问 http://localhost:8080/#/torrents/index 显示列表模式
- [ ] 访问 http://localhost:8080/#/torrents/traditional 显示传统模式
- [ ] 工具栏视图切换按钮正常工作
- [ ] 过滤面板展开/收起正常
- [ ] 状态/下载器/分类过滤正常工作
- [ ] 表格排序功能正常
- [ ] 分页功能正常
- [ ] 详情面板展开/收起正常
- [ ] 实时速度更新正常
- [ ] 批量操作按钮状态正确
- [ ] 主题切换时传统模式颜色正确适配

**Step 3: 提交（如发现 bug）**

```bash
git add .
git commit -m "fix: fix issues found during testing"
```

---

## Task 13: 清理预览 HTML 文件

**Files:**
- Delete: `public/preview-traditional-view.html`

**Step 1: 删除预览文件**

```bash
rm /c/software/full_stack/BtDeck/frontend/public/preview-traditional-view.html
git add public/preview-traditional-view.html
git commit -m "chore: remove preview HTML file after implementation"
```

---

## 执行说明

计划完成并保存到 `docs/plans/2026-05-27-traditional-view-mode.md`。

**两种执行选项：**

**1. Subagent-Driven (当前会话)** - 我在每个任务间启动新的 subagent 执行并审查代码，快速迭代

**2. Parallel Session (独立会话)** - 在新会话中使用 executing-plans 批量执行，定期检查点

**请选择执行方式？**
