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

/**
 * 中文导航文案（P1 范围：路由标题 + 顶栏壳层）。
 * 键为语义名；移动端路由标题继续消费 router meta.title 原值，不进本表。
 */

export const navigation = {
  routes: {
    login: '登录',
    notFound: '页面不存在',
    dashboard: '首页',
    downloader: '下载器管理',
    downloaderGroup: '下载器管理',
    rssManagement: 'RSS 管理',
    downloaderList: '下载器列表',
    torrents: '种子列表',
    torrentsGroup: '种子管理',
    torrentsTraditional: '种子列表（传统模式）',
    fileManagement: '种子文件管理',
    torrentDetail: '种子详情',
    tasks: '定时任务',
    tracker: 'Tracker管理',
    keywordsBoard: '关键词看板',
    keywordsSearch: '关键词搜索',
    reannounceConfig: '汇报配置',
    trackerTest: '测试工具',
    logs: '日志管理',
    audit: '操作日志',
    recycleBin: '回收站',
    orphanFiles: '孤儿文件',
    settings: '系统设置',
    queryTemplates: '查询模板',
    statisticsGroup: '统计数据',
    statisticsOverview: '总览',
    statisticsTrends: '趋势',
    statisticsSeeding: '做种',
    statisticsTrackers: 'Tracker',
    statisticsFunReport: '趣味报告'
  },
  sidebar: {
    /** 侧栏底部双按钮（P1 壳层遗留补译：移动版入口 + 折叠开关） */
    switchToMobile: '切换到移动版',
    mobileEntry: '移动版',
    expand: '展开侧边栏',
    collapse: '收起侧边栏'
  },
  navbar: {
    home: '首页',
    logout: '退出登录',
    feedback: '提交反馈',
    notifications: '通知中心',
    openNotifications: '打开通知中心',
    language: '切换语言'
  }
}
