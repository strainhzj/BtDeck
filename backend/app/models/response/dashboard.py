from typing import List

from pydantic import BaseModel, Field


class DownloaderStats(BaseModel):
    """Downloader statistics."""
    total: int = Field(..., description="Total downloaders")
    online: int = Field(..., description="Online downloaders")
    offline: int = Field(..., description="Offline downloaders")


class TorrentStats(BaseModel):
    """Torrent statistics."""
    active: int = Field(0, description="Active torrents")
    downloading: int = Field(0, description="Downloading torrents")
    seeding: int = Field(0, description="Seeding torrents")
    paused: int = Field(0, description="Paused torrents")


class TaskStats(BaseModel):
    """Task statistics."""
    total: int = Field(..., description="Total tasks")
    running: int = Field(..., description="Running tasks")
    stopped: int = Field(..., description="Stopped tasks")


class SystemStats(BaseModel):
    """System statistics."""
    uptime: int = Field(..., description="Uptime in seconds")
    uptime_display: str = Field(..., description="Formatted uptime display")
    version: str = Field(..., description="Version")


class DownloaderListItem(BaseModel):
    """Downloader list item."""
    downloader_id: str
    nickname: str
    downloader_type: int  # 0=qBittorrent, 1=Transmission
    status: str  # online/offline
    downloading: int = Field(0, description="Current downloading count")
    seeding: int = Field(0, description="Current seeding count")


class ActivityItem(BaseModel):
    """Activity record item."""
    time: str = Field(..., description="Relative time")
    source: str = Field(..., description="Source")
    action: str = Field(..., description="Action description")
    type: str = Field(..., description="Category")


class DashboardData(BaseModel):
    """Dashboard response payload."""
    downloaders: DownloaderStats
    torrents: TorrentStats
    tasks: TaskStats
    system: SystemStats
    downloader_list: List[DownloaderListItem]
    activities: List[ActivityItem]
