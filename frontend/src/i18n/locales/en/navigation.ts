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
 * 英文导航文案（与 zh-CN/navigation.ts 键集合严格一致，由 parity 测试钉住）。
 * 术语依据 PLANS/bilingual/terminology.md。
 */

export const navigation = {
  routes: {
    login: 'Sign in',
    notFound: 'Page not found',
    dashboard: 'Home',
    downloader: 'Downloaders',
    downloaderGroup: 'Downloaders',
    rssManagement: 'RSS Manager',
    downloaderList: 'Downloader List',
    torrents: 'Torrents',
    torrentsGroup: 'Torrents',
    torrentsTraditional: 'Torrents (classic view)',
    fileManagement: 'File management',
    torrentDetail: 'Torrent detail',
    tasks: 'Scheduled tasks',
    tracker: 'Tracker',
    keywordsBoard: 'Keyword board',
    keywordsSearch: 'Keyword search',
    reannounceConfig: 'Reannounce settings',
    trackerTest: 'Test tools',
    logs: 'Logs',
    audit: 'Audit log',
    recycleBin: 'Recycle bin',
    orphanFiles: 'Orphan files',
    settings: 'Settings',
    queryTemplates: 'Query templates',
    statisticsGroup: 'Statistics',
    statisticsOverview: 'Overview',
    statisticsTrends: 'Trends',
    statisticsSeeding: 'Seeding',
    statisticsTrackers: 'Trackers',
    statisticsFunReport: 'Fun report'
  },
  sidebar: {
    /** Sidebar footer buttons (P1 shell leftover fix: mobile entry + collapse toggle) */
    switchToMobile: 'Switch to the mobile version',
    mobileEntry: 'Mobile',
    expand: 'Expand sidebar',
    collapse: 'Collapse sidebar'
  },
  navbar: {
    home: 'Home',
    logout: 'Sign out',
    feedback: 'Submit feedback',
    notifications: 'Notifications',
    openNotifications: 'Open notifications',
    language: 'Switch language'
  }
}
