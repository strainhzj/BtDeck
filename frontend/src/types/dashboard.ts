export interface DownloaderStats {
  total: number
  online: number
  offline: number
}

export interface TorrentStats {
  active: number
  downloading: number
  seeding: number
  paused: number
}

export interface TaskStats {
  total: number
  running: number
  stopped: number
}

export interface SystemStats {
  uptime: number
  uptime_display: string
  version: string
}

export interface DownloaderListItem {
  downloader_id: string
  nickname: string
  downloader_type: number
  status: 'online' | 'offline'
  downloading: number
  seeding: number
}

export interface ActivityItem {
  time: string
  source: string
  action: string
  type: 'torrent' | 'tracker' | 'tag' | 'downloader' | 'scheduled_task' | 'system'
}

export interface DashboardData {
  downloaders: DownloaderStats
  torrents: TorrentStats
  tasks: TaskStats
  system: SystemStats
  downloader_list: DownloaderListItem[]
  activities: ActivityItem[]
}

export interface DashboardResponse {
  code: string
  msg: string
  data: DashboardData
  status: string
}
