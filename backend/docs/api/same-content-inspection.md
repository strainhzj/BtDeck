# 同内容异常排查（种子列表查询）

## 接口

`GET /api/v1/torrents/getList`

同内容排查不再使用独立端点。它是现有种子列表查询的可组合筛选条件，因此沿用列表的筛选、排序和 `skip` / `limit` 分页，只加载当前页种子及其 Tracker 数据。

## 请求参数

- `same_content_only=true`：仅显示名称完全相同、大小完全相同且规范化 InfoHash 至少存在两个不同值的种子。
- 其余参数与种子列表一致，包括 `name_like`、`downloader_id`、`status`、`tracker_like`、`tracker_domain`、`active_only`、`sort_by`、`sort_order`、`skip` 和 `limit`。

筛选分两类口径：

- **参与候选组判定**（决定某个名称/大小组合能否成组）：`name_like`、下载器、保存路径、大小、时间、标签、分类、活动种子。
- **仅过滤组内显示行**（组是否成立不受其影响）：`status`、`tracker_like`、`tracker_domain`。状态与 Tracker 是行级属性——例如某组 20 条任务里只有 1 条处于错误状态，`status=error` 仍返回该行，而不是因组内只剩一个 Hash 导致整组被筛塌。

## 候选口径

1. 种子名称非空且完全相同；
2. 种子大小完全相同且大于 0；
3. 组内至少存在两个不同的规范化 InfoHash（去首尾空白、不区分大小写）；
4. 种子未逻辑删除、未进入回收站、未被活动删除任务占用；
5. 同时满足第 1 类（参与候选组判定）的当前列表筛选条件。

这与“重复种子”的同 Hash 口径不同：该条件用于发现不同站点发布的同名、同大小、不同 Hash 任务。

## 响应

响应复用种子列表 `CommonResponse`：

```json
{
  "status": "success",
  "msg": "获取列表成功",
  "code": "200",
  "data": {
    "total": 42,
    "pageSize": 20,
    "list": []
  }
}
```

`total` 是符合条件的种子行数，`list` 只包含当前页；不返回全量分组、汇总或独立 Tracker 诊断结构。
