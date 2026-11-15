/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/** 仪表盘文案（dashboard 组；仪表盘风格改造一期 W2 扩展：KPI 行/widget 卡/预设/编辑模式）。 */
export const dashboard = {
  title: '数据仪表盘',
  subtitle: '今天是 {date}',
  card: {
    downloaders: '下载器',
    activeTorrents: '活跃种子',
    tasks: '定时任务',
    system: '系统状态'
  },
  allOnline: '全部在线',
  onlineCount: '{count} 在线',
  running: '运行中',
  uptime: '运行时间 {duration}',
  section: {
    downloaderStatus: '下载器状态',
    manage: '管理 →',
    recentActivity: '最近活动',
    viewAll: '查看全部 →',
    quickActions: '快捷操作'
  },
  online: '在线',
  offline: '离线',
  downloading: '下载中',
  seeding: '做种中',
  downloadSpeed: '下载速度',
  uploadSpeed: '上传速度',
  quick: {
    addDownloader: '添加下载器',
    newTask: '新建任务',
    searchTorrents: '搜索种子',
    viewLogs: '查看日志',
    addTorrent: '添加种子',
    advancedSearch: '高级搜索'
  },
  noActivities: '暂无活动记录',
  aria: {
    viewDownloaders: '查看下载器管理',
    viewTorrents: '查看种子管理',
    viewTasks: '查看定时任务',
    viewDownloaderDetail: '查看{name}详情',
    addDownloader: '添加下载器',
    newTask: '新建任务',
    searchTorrents: '搜索种子',
    viewLogs: '查看日志'
  },
  msg: {
    refreshSuccess: '数据刷新成功',
    refreshFailed: '数据刷新失败',
    exportWip: '报告导出功能开发中',
    offlineNoView: '下载器离线，无法查看',
    activitiesWip: '活动详情功能开发中'
  },
  preset: {
    label: '布局预设',
    overview: '概览',
    focus: '聚焦',
    pulse: '脉冲',
    custom: '自定义'
  },
  kpi: {
    downloaders: '下载器在线',
    activeTorrents: '活跃种子',
    enabledTasks: '定时任务',
    systemSpeed: '系统总速度',
    enabledUnit: '已启用',
    enabledNote: '已启用口径（执行态二期）',
    dlSplit: '下载 {count}',
    sdSplit: '做种 {count}'
  },
  edit: {
    button: '编辑布局',
    done: '完成编辑',
    reset: '恢复默认',
    hint: '编辑模式：拖拽卡片调整顺序，「宽度」按钮循环切换列宽（3/4/6/8/12 列）。布局保存在本浏览器（多标签页以最后保存为准），账号级同步为二期范围。',
    cycleWidth: '循环切换列宽'
  },
  screen: {
    enter: '进入大屏',
    title: 'BtDeck 数据大屏',
    exit: '退出大屏（Esc）',
    uptime: '系统连续运行 {duration}',
    onlineCount: '{count} 实例在线',
    upload24h: '近 24h 上传',
    enabledTasks: '已启用任务',
    uptimeLabel: '系统运行时长',
    radarTitle: '实例链路雷达',
    waveTitle: '系统吞吐 · 实时波动',
    tickerTitle: '活跃任务播报',
    refreshNote: '数据每 5s 更新（SSE 推送为二期另立项）',
    brand: 'BtDeck · 数据大屏',
    dateLine: '{y} 年 {m} 月 {d} 日 星期{w}',
    weekday: {
      0: '日',
      1: '一',
      2: '二',
      3: '三',
      4: '四',
      5: '五',
      6: '六'
    }
  },
  mobile: {
    loading: '加载中…',
    viewAllTorrents: '查看全部种子',
    noDownloaders: '还没有下载器，添加后即可管理种子',
    addDownloader: '去添加下载器'
  },
  widgets: {
    liveTag: '实时',
    health: {
      title: '实例健康',
      empty: '暂无下载器',
      dlCount: '下载 {count}',
      sdCount: '做种 {count}'
    },
    spark: {
      title: '速度曲线 · 60s',
      sampling: '采样中…（速度曲线即将呈现）',
      note: '采样 3s · 实时活跃种子'
    },
    statusPie: {
      title: '状态分布',
      total: '种子总数',
      error: '错误',
      downloading: '下载',
      seeding: '做种',
      paused: '暂停',
      other: '其他'
    },
    traffic: {
      title: '近 24h 流量 · 分时',
      loading: '加载中…',
      empty: '暂无流量数据',
      rangeEmpty: '--',
      upload: '上传',
      download: '下载'
    },
    sites: {
      title: 'Tracker 站点分布',
      empty: '暂无站点数据',
      note: '按 Tracker host 去端口聚合 · 按种子去重计数',
      other: '其他',
      countLabel: '种子数'
    },
    hot: {
      title: '热门种子 · 按速度',
      empty: '当前无活跃速度'
    },
    tasks: {
      title: '定时任务',
      empty: '暂无定时任务',
      enabled: '已启用',
      disabled: '已停用',
      more: '还有 {count} 个任务'
    },
    activity: {
      title: '最近活动'
    },
    quick: {
      title: '快捷操作'
    },
    radar: {
      title: '链路雷达'
    },
    tubes: {
      title: '吞吐管道'
    },
    hero: {
      title: '实时脉搏',
      activeDownloading: '活跃下载',
      activeSeeding: '活跃做种',
      downloading: '下载中',
      empty: '当前无下载任务'
    }
  }
}
