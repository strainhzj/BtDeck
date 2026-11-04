export interface DownloaderStats {
  total: number
  online: number
  offline: number
}

export type StatusBucketKey = 'error' | 'downloading' | 'seeding' | 'paused' | 'other'

export interface StatusBuckets {
  error: number
  downloading: number
  seeding: number
  paused: number
  other: number
}

export interface SiteBucket {
  /** 站点显示名 = tracker host（去端口归一；"other" 为 TopN 之外的汇总量） */
  host: string
  count: number
}

export interface TorrentStats {
  active: number
  downloading: number
  seeding: number
  paused: number
  /** 五桶状态分布（W1；口径与 /reports/overview statusDist 一致，error 桶优先） */
  statusBuckets: StatusBuckets
  /** 站点分布（W1；按种子去重计数，TopN + other；5min 独立节流） */
  siteBuckets: SiteBucket[]
}

export interface TaskStats {
  total: number
  running: number
  stopped: number
  /** 已启用任务数（决策 #1：enabled 口径，非 task_status 执行态；60s 缓存） */
  enabled: number
}

export interface SystemStats {
  uptime: number
  uptime_display: string
  version: string
  total_download_speed: number
  total_upload_speed: number
}

export interface DownloaderListItem {
  downloader_id: string
  nickname: string
  downloader_type: number
  status: 'online' | 'offline'
  downloading: number
  seeding: number
  paused: number
  download_speed: number
  upload_speed: number
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
