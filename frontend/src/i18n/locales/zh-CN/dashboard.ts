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

/** 仪表盘文案（dashboard 组，P3-1：标题/统计卡/下载器状态卡/最近活动/快捷操作）。 */
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
    viewLogs: '查看日志'
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
  }
}
