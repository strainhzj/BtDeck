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

/** 仪表盘文案（dashboard 组，en；仪表盘风格改造一期 W2 扩展）。 */
export const dashboard = {
  title: 'Dashboard',
  subtitle: 'Today is {date}',
  card: {
    downloaders: 'Downloaders',
    activeTorrents: 'Active torrents',
    tasks: 'Scheduled tasks',
    system: 'System status'
  },
  allOnline: 'All online',
  onlineCount: '{count} online',
  running: 'Running',
  uptime: 'Uptime {duration}',
  section: {
    downloaderStatus: 'Downloader status',
    manage: 'Manage →',
    recentActivity: 'Recent activity',
    viewAll: 'View all →',
    quickActions: 'Quick actions'
  },
  online: 'Online',
  offline: 'Offline',
  downloading: 'Downloading',
  seeding: 'Seeding',
  downloadSpeed: 'Download speed',
  uploadSpeed: 'Upload speed',
  quick: {
    addDownloader: 'Add downloader',
    newTask: 'New task',
    searchTorrents: 'Search torrents',
    viewLogs: 'View logs',
    addTorrent: 'Add torrent',
    advancedSearch: 'Advanced search'
  },
  noActivities: 'No recent activity',
  aria: {
    viewDownloaders: 'View downloader management',
    viewTorrents: 'View torrent management',
    viewTasks: 'View scheduled tasks',
    viewDownloaderDetail: 'View {name} details',
    addDownloader: 'Add downloader',
    newTask: 'New task',
    searchTorrents: 'Search torrents',
    viewLogs: 'View logs'
  },
  msg: {
    refreshSuccess: 'Data refreshed',
    refreshFailed: 'Failed to refresh data',
    exportWip: 'Report export is under development',
    offlineNoView: 'Downloader is offline, cannot view',
    activitiesWip: 'Activity details are under development'
  },
  preset: {
    label: 'Layout preset',
    overview: 'Overview',
    focus: 'Focus',
    pulse: 'Pulse',
    custom: 'Custom'
  },
  kpi: {
    downloaders: 'Downloaders online',
    activeTorrents: 'Active torrents',
    enabledTasks: 'Scheduled tasks',
    systemSpeed: 'System speed',
    enabledUnit: 'enabled',
    enabledNote: 'Enabled count (runtime state in phase 2)',
    dlSplit: 'DL {count}',
    sdSplit: 'Seed {count}'
  },
  edit: {
    button: 'Edit layout',
    done: 'Done editing',
    reset: 'Reset to default',
    hint: 'Edit mode: drag cards to reorder; the width button cycles columns (3/4/6/8/12). Layout is stored in this browser (last save wins across tabs); account-level sync is phase 2.',
    cycleWidth: 'Cycle column width'
  },
  screen: {
    enter: 'Data screen'
  },
  widgets: {
    liveTag: 'Live',
    health: {
      title: 'Instance health',
      empty: 'No downloaders',
      dlCount: 'DL {count}',
      sdCount: 'Seed {count}'
    },
    spark: {
      title: 'Speed · 60s',
      sampling: 'Sampling… (speed chart coming)',
      note: '3s sampling · live active torrents'
    },
    statusPie: {
      title: 'Status distribution',
      total: 'Total torrents',
      error: 'Error',
      downloading: 'Downloading',
      seeding: 'Seeding',
      paused: 'Paused',
      other: 'Other'
    },
    traffic: {
      title: 'Last 24h traffic',
      loading: 'Loading…',
      empty: 'No traffic data',
      rangeEmpty: '--',
      upload: 'Upload',
      download: 'Download'
    },
    sites: {
      title: 'Tracker site distribution',
      empty: 'No site data',
      note: 'Grouped by tracker host (port-stripped) · deduplicated by torrent',
      other: 'Other',
      countLabel: 'Torrents'
    },
    hot: {
      title: 'Hot torrents · by speed',
      empty: 'No active speeds right now'
    },
    tasks: {
      title: 'Scheduled tasks',
      empty: 'No scheduled tasks',
      enabled: 'Enabled',
      disabled: 'Disabled',
      more: '{count} more tasks'
    },
    activity: {
      title: 'Recent activity'
    },
    quick: {
      title: 'Quick actions'
    },
    radar: {
      title: 'Link radar'
    },
    tubes: {
      title: 'Throughput tubes'
    },
    hero: {
      title: 'Live pulse',
      activeDownloading: 'Active downloads',
      activeSeeding: 'Active seeds',
      downloading: 'Downloading',
      empty: 'No active downloads'
    }
  }
}
