# 同内容异常排查 API

## 接口

`POST /api/v1/torrents/same-content-inspection`

该接口只读取数据库同步快照，不连接下载器、不修改种子、不触发 Tracker 操作。

## 请求

```json
{
  "mode": "all",
  "page": 1,
  "pageSize": 10
}
```

- `mode=all`：返回候选组及组内全部种子。
- `mode=errors`：只返回至少含一个错误种子的候选组，且组内只保留错误种子。
- `page` / `pageSize`：按“名称与大小相同的候选组”分页，不按单条种子分页；`pageSize` 最大 50。

## 候选组口径

同时满足以下条件才进入排查结果：

1. 种子名称完全相同；
2. 种子大小完全相同且大于 0；
3. 组内至少存在 2 个不同的规范化 InfoHash（去首尾空白、不区分大小写）；
4. 种子未逻辑删除、未进入回收站、未被活动删除任务占用。

这与现有“重复种子”接口的同 Hash 口径不同：本接口专门发现不同站点发布的同名、同大小、不同 Hash 任务。

## 错误口径

任一条件成立即将种子标记为错误：

- 种子任务 `status=error`；
- `error_reason` 非空；
- 聚合标记 `has_tracker_error=true`；
- 任一 Tracker 持久化状态为 `error`；
- 任一 Tracker announce/scrape 原始状态码为失败或超时（3/4）；
- 最新 announce/scrape 消息命中启用的 `failed` Tracker 关键词。

## 响应与安全边界

响应使用统一 `CommonResponse`，分页字段固定为 `total` / `page` / `pageSize` / `list`。`summary` 同时返回候选组、候选种子、错误组和错误种子总数。

Tracker 响应只返回主机名。完整 Tracker URL、query、fragment、userinfo 与路径均不返回；错误消息中的 URL 和常见 `passkey/authkey/api-key/token/secret` 参数会脱敏，避免站点凭据泄露。
