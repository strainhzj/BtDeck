# 快捷删除重复种子 — 设计文档

- 日期：2026-08-06
- 模块：种子管理（torrents）
- 范围：列表模式（`index.vue`）+ 传统模式（`TraditionalView.vue`）共用的"快捷操作 → 快捷删除重复种子"

## 一、需求概述

在种子列表页工具栏新增**快捷操作**下拉按钮，本期仅包含一个菜单项"快捷删除重复种子"：

1. 弹窗中通过 **AdvancedMultiSelect** 选择 **2 个及以上**下载器（待检测下载器集合）。
2. 另一 AdvancedMultiSelect 选择**保留下载器**（第一个选择的子集，可多选，如"qbittorrent1 + transmission1"）。
3. 预览：列出将被删除的重复种子（hash 分组 + 保留副本对照）。
4. 确认后，仅对"非保留下载器"中的重复种子执行 **等级2 删除（只删种子、不删文件）**。
5. 删除完成后**发送系统通知**，并按种子**记录审计日志**。

判定规则（用户确认）：

- 在所选下载器间，同一 hash 出现 ≥2 次视为重复。
- **仅删除"保留下载器"中存在同 hash 副本的重复种子**（保护最后一份数据）。
- 某 hash 只在"待删下载器"间重复、而保留集合中无副本时，**不删除**，仅在预览中**提醒**（skipped 组）。

## 二、复用与新增

| 类型 | 内容 |
|------|------|
| 复用（前端） | `AdvancedMultiSelect.vue`、`getDownloaderList`、`deleteBatchAsync`、`getBatchDeleteStatus`、`api/torrents.ts` |
| 复用（后端） | `TorrentInfo`/`BtDownloaders` 模型、`get_db`、`CommonResponse`、删除流程（审计日志已内建）、`NotificationService.create_notification` |
| 新增（前端） | `QuickDeleteDuplicatesDialog.vue`（两视图共享）、`api/torrents.ts` 预览请求/响应类型与函数、两视图"快捷操作"下拉按钮 |
| 新增（后端） | `api/endpoints/duplicate_quick_delete.py`（预览 + 执行两个端点，注册于 `app/api/api.py`）、`services/duplicate_quick_delete_service.py`（预览/执行共享的分类逻辑）、`AsyncDeletionExecutor` 两处增强：① `execute_deletion_task` 增加可选 `notify_on_complete: bool = False` 并在完成时发系统通知；② 接入 `audit_service` 使按种子审计日志生效 |

## 三、后端设计

### 3.1 预览端点（新增，轻量，分页）

```
POST /api/v1/torrents/duplicates/quick-delete-preview
```

请求体：

```json
{
  "downloader_ids": ["qb1", "qb2"],            // ≥2，去重
  "keep_downloader_ids": ["qb2"],              // ≥1，必须是 downloader_ids 的子集
  "page": 1,
  "pageSize": 20
}
```

响应（`CommonResponse`，`data`，分页字段固定 `total/page/pageSize/list`，对齐项目分页约定）：

```json
{
  "total": 3,          // 分页命中总数（含 skipped 组）
  "page": 1,
  "pageSize": 20,
  "total_groups": 3,   // 全量重复组总数（不受分页影响）
  "total_delete": 5,   // 全量待删除种子数（不受分页影响）
  "skipped_groups": 1, // 全量 skipped 组数
  "list": [
    {
      "hash": "ab12...",
      "name": "影视资源.2024",
      "size": 21474836480,
      "kept":   [ { "info_id": "10", "downloader_id": "qb2", "downloader_name": "qbittorrent2", "status": "seeding" } ],
      "to_delete": [ { "info_id": "8", "downloader_id": "qb1", "downloader_name": "qbittorrent1", "status": "seeding" } ],
      "skipped": false
    }
  ]
}
```

> 说明：`total/total_delete/skipped_groups` 为**全量汇总**（用于顶部统计与提醒条），`list` 按 hash 组分页返回（用于逐页浏览）。汇总字段在服务层一次算好，分页只作用于 `list`。

实现逻辑：

1. 校验参数：`downloader_ids ≥2`、`keep_downloader_ids ≥1`、`keep ⊆ downloader_ids`（否则 400）。
2. 查询 `TorrentInfo`：`dr == 0`、`hash` 非空、`downloader_id ∈ downloader_ids`。
3. 按标准化 hash（`str(hash).strip().lower()`，对齐 `duplicate_torrents.py:_normalized_hash`）分组。
4. 仅保留组内不同下载器数 ≥2 的组（跨下载器重复）。
5. 分类：
   - `kept` = 组内 `downloader_id ∈ keep_downloader_ids`；
   - `to_delete` = 组内 `downloader_id ∉ keep_downloader_ids`；
   - `kept` 非空 且 `to_delete` 非空 → 正常组（计入 total_groups / total_delete）；
   - `kept` 为空 → **skipped 组**（仅提示，不产生删除候选）。
6. 名称/大小取组内非空最大值（对齐 `duplicate_torrents.py` 的 intrinsic 回填思想）；`downloader_name` 联查 `BtDownloaders.nickname`。
7. 只返回 DB 静态字段（hash/name/size/downloader/status/info_id），**不拉实时元数据**（轻量）。
8. **实现方式**：一次 SQL 取回所选下载器种子（`dr==0`、hash 非空）后在 **Python 层**按 `str(hash).strip().lower()` 分组（对齐 `duplicate_torrents.py:_normalized_hash`），避免 SQL `GROUP BY` 无法同时完成 kept 归属与 skipped 判定的问题；注意 SQLite 32766 bind 上限先例（`duplicate_torrents.py:203-210`），数量大时按下载器分批取。
9. **路由注册**：新 router 在 `app/api/api.py` import 并以 `prefix="/torrents"` include（对齐现有 `duplicate_torrents.router`，最终顶层 `/api/v1` 由 `routers_initializer` 统一挂载）。

### 3.2 执行端点（新增，服务端重算）

```
POST /api/v1/torrents/duplicates/quick-delete
```

请求体：

```json
{
  "downloader_ids": ["qb1", "qb2"],
  "keep_downloader_ids": ["qb2"],
  "delete_level": 2,          // 本期固定 2（只删种子、不删文件）
  "notify_on_complete": true
}
```

响应：`{ "task_id": "...", "total_count": 5, "delete_level": 2 }`（与 `delete-batch-async` 同构）。

实现逻辑：

1. 复用**与预览相同的分类服务**（`duplicate_quick_delete_service.py`）重新计算全部 `to_delete`（服务端权威，不依赖前端分页快照）。
2. 若 `to_delete` 为空 → 返回空任务（`total_count=0`），前端提示无删除项。
3. 否则复用 `deletion_task_manager.create_task` + `AsyncDeletionExecutor.execute_deletion_task`（与 `delete-batch-async` 同流程）提交后台删除任务，`delete_level=2`，`notify_on_complete` 透传；**`operator` 传 `user_info.username`**（非默认 "admin"），`request: Request` 参数注入（`AsyncDeletionExecutor` 构造需要，见 `torrent_deletion.py:808` 先例）。
4. 返回 task_id，前端沿用 `getBatchDeleteStatus` 轮询进度。

> 选型理由：预览分页后，删除动作若由前端逐页拉取会引入多次请求与快照漂移；服务端在提交任务时**重算**当前重复集合，既保证一致性又避免前端循环拉分页。

### 3.3 审计日志与完成通知

**审计日志（审查修正，高优先级）**：现有 `AsyncDeletionExecutor._delete_single_torrent` 调用 `delete_by_level(...)` 时**未传 `audit_service`**（`async_deletion_executor.py:142-144`），而 `TorrentDeletionByLevelService.delete_by_level` 仅在 `if audit_service:` 时写审计（`torrent_deletion_by_level.py`）。因此**不能**声称"已内建"。修正：在 `execute_deletion_task` 中创建一次 async 审计服务（`AsyncSessionLocal` + `get_audit_service`，先例 `torrent_deletion.py:657-660`），传入 `_delete_single_torrent` → `delete_by_level(audit_service=...)`，使每个种子按 `AuditOperationType.DELETE_L2` 写入审计日志；获取失败时降级为仅日志告警（不阻断删除）。

**完成通知**：`AsyncDeletionExecutor.execute_deletion_task` 增加可选参数 `notify_on_complete: bool = False`（默认关闭，不影响既有删除流程；`delete-batch-async` 端点与 `BatchDeleteRequest` **不改**）。在写入最终状态后，若该标志为 true，创建系统通知（`type=system`，标题"快捷删除重复种子完成"，内容含成功/失败/总数，`priority=info`）。
  - 实现注意：executor 使用同步 `db_session_factory`，而 `NotificationService` 需要 `AsyncSession`。在 executor 内使用独立 async session（`app.database.AsyncSessionLocal`）创建通知，避免与同步 session 混用；异常时仅记日志不中断任务。

## 四、前端设计

### 4.1 新组件 `frontend/src/components/torrents/QuickDeleteDuplicatesDialog.vue`

class-component（与项目一致），props：`visible`。

内部结构（三段式）：

1. **配置区**
   - 待检测下载器：`AdvancedMultiSelect`（`options` = `getDownloaderList` 返回的 `{value: downloader_id, label: nickname}`；`v-model` 绑定数组）。**显式传 `:allow-create="false"`、`:show-mode-toggle="false"`**（其默认值为 true，见 index.vue:17-18 先例，避免出现"创建选项/包含排除"非预期 UI）。
   - 保留下载器：`AdvancedMultiSelect`，`options` 联动为**已选待检测下载器**（排除逻辑前端计算），`v-model` 绑定保留数组。
   - **联动剪裁（审查修正）**：`AdvancedMultiSelect` 不会随 options 变化自动清空已选 value（`onOptionsChange` 仅刷新虚拟滚动，`AdvancedMultiSelect.vue:461`）。当待检测下载器变化时，父组件必须**显式剪裁**保留数组（过滤掉不在新待检测集合中的项），否则旧 chip/value 残留导致请求参数非法。
   - "预览"按钮：校验（待检测 ≥2、保留 ≥1 且 ⊆ 待检测）后调用预览 API。
2. **预览区**（loading / error / empty / 列表）
   - 列表按 hash 分组渲染（`el-table` 或分组卡片），每页 `pageSize` 条组；`el-pagination` 分页浏览（`page`/`total`）。
   - 每组显示 hash、名称、大小；`to_delete` 种子列出"将被删除"（下载器/状态）；`kept` 副本浅色对照展示。
   - skipped 组收敛到顶部提醒条："另有 N 组重复仅在待删下载器间存在、无保留副本，已跳过不删除"（可展开）。
   - 顶部/底部统计用**全量汇总**（`total_groups` / `total_delete` / `skipped_groups`，不受分页影响）："共 N 组重复，将删除 M 个种子"。
3. **底部操作**
   - `total_delete > 0` 时启用"确认删除"（danger），否则仅"关闭"。
   - 确认 → 调用新执行端点 `quickDeleteDuplicates({ downloader_ids, keep_downloader_ids, delete_level: 2, notify_on_complete: true })` → 轮询 `getBatchDeleteStatus` → 完成后 toast 结果、`$emit('deleted')` 通知父级刷新列表。

### 4.2 两视图接入

- `index.vue`：在"查找重复任务"按钮旁新增 `el-dropdown`（触发按钮"快捷操作"），菜单项"快捷删除重复种子" → 打开共享弹窗；`@deleted` 刷新列表。
- `TraditionalView.vue`：同样新增下拉按钮（放工具栏-center 区域"重复"按钮旁）。
- 两视图复用同一组件实例逻辑，避免重复实现。

### 4.3 `api/torrents.ts` 新增

- 类型：`QuickDeletePreviewRequest`（含 `page`/`pageSize`）、`QuickDeletePreviewItem`（kept/to_delete 元素）、`QuickDeletePreviewGroup`、`QuickDeletePreviewResponse`（含全量汇总 `total_groups/total_delete/skipped_groups`）。
- 函数：`getQuickDeleteDuplicatePreview(params)` → `POST /torrents/duplicates/quick-delete-preview`。
- 函数：`quickDeleteDuplicates(params)` → `POST /torrents/duplicates/quick-delete`（返回 `task_id`）。

## 五、测试

- **后端**（pytest）：
  - 预览端点：参数校验（待检测 <2 / 保留空 / 保留非子集 → 400）；跨下载器重复分组；keep/delete 分类正确；skipped 规则（保留集合无副本时仅提示）；hash 大小写/空白标准化；名称/大小回填；**分页正确性与全量汇总字段不受分页影响**。
  - 执行端点：无删除候选时返回空任务；有候选时正确重算全部 `to_delete` 并提交异步任务（task_id/total_count 正确）；`operator` 使用真实用户名。
  - executor 增强：`notify_on_complete=True` 时完成写系统通知，False 时不影响既有行为；**接入 `audit_service` 后每个被删种子写入审计日志（DELETE_L2）**。
- **前端**（Vue 单测）：组件校验逻辑、预览分页渲染分组、skipped 提醒、**待检测变化时保留数组联动剪裁**、确认删除调用执行端点与参数组装（复用现有测试基建）。

## 六、风险与边界

- **大批量删除**：走异步任务 + 轮询，不阻塞界面。
- **预览与执行间数据漂移**：执行端点在提交任务时**服务端重算**当前重复集合（不依赖分页快照），保证删除的是最新一致的重复集；删除后刷新列表。
- **同下载器内重复**（同 hash 在同一下载器出现 2 次）：若该下载器在保留集合 → 全部保留；否则 kept 为空 → skipped，符合规则。
- **通知服务 AsyncSession 适配**：executor 内独立 async session 创建通知，失败仅告警不阻断删除任务。
- **无数据库迁移**：新增请求/响应均为 Pydantic 模型，`Notification` 表已存在（含 dedupe 唯一索引），**不需要 Alembic 迁移**。
- **下载器被禁用/失效**：`getDownloaderList` 默认仅返回启用下载器；执行删除时失效下载器计入 `failed_items`，任务状态 partial，通知含失败数。
