# 下载器客户端连接管理（强制）

🔴 **核心原则**：所有涉及下载器操作的接口，必须使用 `app.state.store` 缓存中的客户端连接，严禁重复创建连接。

## 使用规范

### 1. 从缓存获取下载器

```python
cached_downloaders = app.state.store.get_snapshot_sync()
downloader_vo = next(
    (d for d in cached_downloaders if d.downloader_id == downloader_id),
    None
)
```

### 2. 验证连接有效性

```python
if not downloader_vo or downloader_vo.fail_time > 0:
    return error_response("下载器不可用")

client = downloader_vo.client
```

### 3. 使用缓存的客户端

```python
if downloader_vo.downloader_type == 0:  # qBittorrent
    client.torrents_pause(torrent_hashes=hashes)
elif downloader_vo.downloader_type == 1:  # Transmission
    client.stop_torrent(hashes)
```

## 严格禁止

- ❌ 在业务接口中创建新的客户端连接（`qbClient(...)` 或 `trClient(...)`）
- ❌ 手动释放缓存连接（`client.logout()`）

## 适用范围

所有下载器操作接口（pause/resume/recheck 等）
