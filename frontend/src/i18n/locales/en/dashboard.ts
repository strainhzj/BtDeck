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

/** 仪表盘文案（dashboard 组，en）。 */
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
  downloadSpeed: 'Down speed',
  uploadSpeed: 'Up speed',
  quick: {
    addDownloader: 'Add downloader',
    newTask: 'New task',
    searchTorrents: 'Search torrents',
    viewLogs: 'View logs'
  },
  noActivities: 'No recent activity',
  aria: {
    viewDownloaders: 'View downloader management',
    viewTorrents: 'View torrent management',
    viewTasks: 'View scheduled tasks',
    viewDownloaderDetail: 'View details of {name}',
    addDownloader: 'Add downloader',
    newTask: 'New task',
    searchTorrents: 'Search torrents',
    viewLogs: 'View logs'
  },
  msg: {
    refreshSuccess: 'Data refreshed successfully',
    refreshFailed: 'Failed to refresh data',
    exportWip: 'Report export is under development',
    offlineNoView: 'Downloader is offline, cannot view',
    activitiesWip: 'Activity details are under development'
  }
}
