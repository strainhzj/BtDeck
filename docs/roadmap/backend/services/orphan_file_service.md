# orphan_file_service.py — 孤儿文件管理服务

> 路线图第三层（services 分支）。依据源码 grep/Read 实测行号生成。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/services/orphan_file_service.py` |
| 行数 | 3902（实测 2026-08-22） |
| 模块职责 | 孤儿稳定当前明细列表、文件夹懒加载/独立分页、清理与隔离/恢复/彻底删除、硬链接副本位置只读与弹窗删除；硬链接计数直读明细快照列（不逐文件实时 stat），查询与操作排除活动占用条目 |
| 顶层符号 | 2 classes（`HardlinkCopyError` L69、`OrphanFileService` L100）+ 1 模块级工具函数（`_chunk_values` L94） |

---

## 二、关键不变式

- **稳定身份**：候选以 `canonical_path` 为身份并通过 `current_detail_id` 指向可复用的当前明细；已知孤儿后续成功扫描不再每批次新增 `orphan_file`。
- **全选语义（v1.0.6.35）**：`select_all=true` 时以筛选条件重建全量 ID（绑定 scan_id），扣除 `excluded_orphan_ids`。
- **多值过滤（v1.0.6+）**：`_build_orphan_conditions` 对 `downloader_id`/`confidence`/`status` 全部支持逗号分隔多值。downloader_id/confidence 用 `in_`；status 三态(pending/ignored/deleted)互斥，多值时每个用 `and_()` 打包(is_deleted+忽视子查询)再用 `or_()` 取并集——pending 与 ignored/deleted 组合会退化为“所有未删除文件”(前端给提示)。单值仍走原路径(回归保护)。`min_size` 数值区间不动。list/grouped/resolve/prefix_preview 4 个调用点共用此方法。
- **副本定位筛选（2026-08-15）**：`_build_orphan_conditions(hardlink_copies="located")` 追加 EXISTS——候选表最近扫描的 `(device_id, inode)`（字符串列，join 时 CAST inode 为整数）命中 `orphan_hardlink_copy_result` 且 `found_count > 1`（found_count 含源路径自身，>1 即定位到非源副本，与弹框口径一致；NULL 身份/未扫描不命中，fail-closed）。list/grouped/folder_children 3 个调用点透传；resolve/prefix_preview 不参与。
- **安全清理**：预览、前缀预览、手动和定时自动清理共用最新 completed/scan_id 门禁；超 50000 条只保留提醒状态，不再要求路径映射+孤儿样本复核；删除前仍实时复核 manifest、路径授权和文件身份，不提供 force。
- **活动项占用**：查询和用户操作入口通过 `orphan_purge_job_service` 的 JSON 子查询排除 pending/running 清理 ID 或彻底删除路径；后台 worker 读取自身任务快照时不套该过滤。任务进入 completed/partial/failed 后查询自然重新放行未完成项。
- **文件夹/硬链接**：文件夹父页仅 SQL 聚合，不读子项也不 `stat`；展开后 `get_orphan_folder_children` 独立分页，`hardlink_copy_count` 随 `to_dict()` 从明细快照列直出（发现文件时 stat、每日预扫描/每次成功扫描刷新），不再对当前页逐文件实时 `stat`；实时值以副本位置弹窗 stat 复核为准。
- **硬链接位置核对**：点击时只读定时预扫描落库结果（2026-08-15 起）：`get_hardlink_copy_locations` 仅对源文件做廉价 stat 复核实时 `st_nlink - 1`，路径来自 `orphan_hardlink_copy_result` 结果表；未覆盖的身份返回 `pending_scan=true` 等待下一轮预扫描。遍历本身移至 `orphan_hardlink_scan_service.run_round` 定时任务。
- **硬链接副本删除（2026-08-16）**：`delete_hardlink_copies` 仅移除指向同一 inode 的其它路径链接（源文件与数据保留），逐路径 fail-closed：维护租约互斥 → 候选 `status=candidate` 且 `operation_state=stable` 门禁 → 源 stat 身份 + 预扫描结果行存在 → 共享 inode 拒绝集（源路径 + 同身份全部候选 canonical_path）→ 种子目录白名单（`collect_torrent_directory_whitelist` 全量下载器，DB 目录级，加载失败整体拒绝）→ 请求路径与返回前端的 copies 原始字符串一致 + 隔离区/回收站标记/符号链接拒绝 → tombstone 三段式（rename→身份复核→remove，复核失败回滚）。成功后以 setattr payload 同步结果行（copies_json/found_count/copy_count，保留 truncated/scan_note/scanned_at），审计在主事务 commit 后写（restore 模式）。状态类拒绝一律 200 + failed_list。
- **物理操作安全**：仅用 `os.rmdir` 回收记录隔离根内的空 UUID/scan-id 目录。

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L69 | `HardlinkCopyError` | class | 到期删除遇硬链接副本时的安全跳过异常 |
| L79 | `HardlinkCopyError.__init__` | def | 保存候选、隔离路径、副本与原因 |
| L94 | `_chunk_values` | def（模块级） | 把 Sequence 切块 |
| L100 | `OrphanFileService` | class | 孤儿文件管理服务类 |
| L103 | `OrphanFileService.__init__` | def | `(self, db: AsyncSession)` |
| L107 | `_detail_canonical_path` | static | 取明细 canonical_path |
| L113 | `_sync_candidate_owner` | def | 同步候选归属 |
| L135 | `_current_detail_ids_query` | static | 当前候选指向的稳定明细 ID 子查询 |
| L149 | `_build_orphan_conditions` | def | 构造列表/全选筛选并排除活动清理 ID（含 hardlink_copies=located EXISTS） |
| L248 | `_orphan_order_columns` | static | 构造稳定排序列 |
| L270 | `resolve_orphan_selection` | async def | **全选/勾选解析为稳定 ID 快照** |
| L313 | `_load_orphan_details` | async def | 分块加载明细，可选排除活动项 |
| L353 | `_load_candidates` | async def | 按规范化路径分块加载候选（可选 stable 门禁） |
| L378 | `_get_latest_scan` | async def | 取最新扫描（可按 status） |
| L392 | `_get_scan` | async def | 按 scan_id 取扫描记录（判 details_mode） |
| L397 | `_evaluate_cleanup_snapshot` | def | completed/scan_id 共用清理门禁；超量字段仅作提醒 |
| L438 | `_check_cleanup_allowed` | async def | preview/cleanup 共用新鲜度门禁入口 |
| L451 | `_build_realtime_manifest` | async def | 构建删除前实时 manifest |
| L472 | `_identity_complete` | static | 候选身份四字段（size/mtime/device/inode）是否齐全 |
| L484 | `_candidate_inode` | static | 取候选 `(device_id, inode)` 整数元组 |
| L488 | `_path_authorized` | static | 回收站/隔离区标记无条件拒绝 + 扫描根授权校验 |
| L517 | `_path_in_quarantine_root` | static | 隔离路径是否严格位于隔离根内（拒符号链接） |
| L543 | `_quarantine_path_authorized` | static | 隔离物理删除范围校验（只信持久化 quarantine_path/root） |
| L562 | `_quarantine_delete_guard_error` | static | 返回隔离删除路径校验错误（None=通过） |
| L568 | `_ensure_quarantine_identity` | async def | 为旧版隔离记录补齐/复核身份字段（fail-closed） |
| L613 | `_authorize_low_confidence` | static | 低置信度候选的目录白名单兜底授权 |
| L646 | `_owning_root` | static | 取候选命中的最长授权扫描根 |
| L661 | `get_latest_scan_result` | async def | 最新扫描结果 |
| L669 | `_inspect_hardlink_sources` | static | 顺序 stat 源文件 inode/nlink（由调用方放线程） |
| L697 | `_load_hardlink_copy_results` | async def | 按物理身份分片反查结果表 |
| L714 | `get_hardlink_copy_locations` | async def | **批量读取预扫描落库的副本位置（不遍历）** |
| L799 | `_hardlink_copy_marker_reason` | static | 隔离区/回收站标记拒绝原因（settings 口径） |
| L810 | `_in_seed_directory` | static | 副本是否落在种子目录（normalize_path + commonpath） |
| L825 | `_remove_hardlink_copy` | static | tombstone 三段式删除单个副本目录项（同线程，复核失败回滚） |
| L856 | `delete_hardlink_copies` | async def | **弹窗删除已定位副本（租约/状态门禁/共享 inode/种子目录 fail-closed + 审计）** |
| L1141 | `get_orphan_list` | async def | **稳定当前明细分页 + 扫描上下文** |
| L1318 | `get_orphan_list_grouped` | async def | 文件夹父页 SQL 聚合，不加载/不 stat 全部子项 |
| L1568 | `get_orphan_folder_children` | async def | **展开后子项独立分页（副本数直读快照列）** |
| L1640 | `_enrich_items` | async def | 为本页明细批量注入别名/忽视态；`hardlink_copy_count` 快照列直出 |
| L1692 | `reconcile_stable_candidate_details` | async def | keyset 分批对账稳定隔离候选明细，每页统一进入 `db_write_scope` |
| L1850 | `prefix_match_preview` | async def | 路径前缀预览（共用清理门禁） |
| L1896 | `cleanup_preview` | async def | 清理预览 |
| L1942 | `cleanup_orphans` | async def | **后台手动清理任务执行** |
| L2223 | `set_ignored` | async def | 设置忽视 |
| L2394 | `auto_cleanup_expired` | async def | 过期自动清理（共用最新快照与实时安全校验） |
| L2596 | `purge_expired_quarantine` | async def | 过期隔离清除 |
| L2789 | `get_quarantine_list` | async def | 隔离区列表 |
| L2865 | `prune_recorded_empty_quarantine_dirs` | async def | 带租约清理历史空 UUID/scan-id 隔离目录 |
| L2906 | `restore_quarantined` | async def | 恢复隔离 |
| L3090 | `_finalize_restore` | async def | 同一事务回滚候选与明细，可刷新副本数快照 |
| L3136 | `purge_quarantine_now` | async def | 后台立即彻底删除 |
| L3290 | `_purge_single_candidate` | async def | 单个彻底删除 |
| L3414 | `_detect_hardlink_copies` | async def | 删除前枚举硬链接副本 |
| L3507 | `_candidate_scan_roots` | static | 取候选所属 downloader 的扫描根列表 |
| L3514 | `_mark_purged` | async def | 标记候选为已物理删除 |
| L3529 | `_matching_undeleted_details` | async def | 按批次/下载器/规范化路径定位未清理明细 |
| L3559 | `_finalize_quarantine` | async def | 同一最终事务稳定候选并标记扫描明细 |
| L3615 | `_commit_candidate_state` | async def | 提交不涉及扫描明细的候选状态 |
| L3631 | `_quarantine_candidate` | async def | 预写操作状态执行隔离（跨 DB/FS 崩溃窗口） |
| L3681 | `_recover_interrupted_operations` | async def | 中断操作恢复 |

---

## 四、方法签名详情

### `resolve_orphan_selection` — 全选/勾选解析为稳定 ID 快照

```python
async def resolve_orphan_selection(
    self,
    *,
    orphan_ids: Sequence[int],
    select_all: bool,
    excluded_orphan_ids: Sequence[int],
    scan_id: Optional[str],
    downloader_id: Optional[str] = None,
    min_size: Optional[int] = None,
    path_like: Optional[str] = None,
    path_prefix: Optional[str] = None,
    status: Optional[str] = None,
    confidence: Optional[str] = None,
    hardlink_copies: Optional[str] = None,
) -> List[int]:
    """把显式勾选或当前筛选全集解析为稳定的明细 ID 快照。"""
```

- **定位**：`orphan_file_service.py:270`
- **职责**：`select_all=false` 时返回去重后的显式 `orphan_ids`（空则报错）；`select_all=true` 时用 `_build_orphan_conditions` 按筛选条件（含 `hardlink_copies` 副本筛选）重建全量 ID（须绑定 scan_id），自动排除活动任务占用项并扣除 `excluded_orphan_ids`。
- **调用链**：`_build_orphan_conditions`（L149）→ `db.execute(select(OrphanFile.id))` → 排除集过滤。

### `get_hardlink_copy_locations` — 按需定位硬链接副本路径

```python
async def get_hardlink_copy_locations(
    self,
    orphan_ids: Sequence[int],
) -> Dict[str, Any]:
    """读取定时预扫描任务落库的副本定位结果。"""
```

- **定位**：`orphan_file_service.py:714`
- **职责**：批量加载当前未删除明细，对源文件做廉价 stat 复核实时副本总数；按 `(device_id, inode_id)` 反查结果表并过滤源路径本身，返回定位路径、扫描时间、待扫描标记、未定位数量、失效 ID 与不可访问状态。
- **调用链**：`_load_orphan_details`（L313）→ `_inspect_hardlink_sources`（L669，经 `asyncio.to_thread`）→ `_load_hardlink_copy_results`（L697）。目录遍历在 `orphan_hardlink_scan_service.run_round`（定时任务 `orphan_hardlink_copy_scan`，每日 04:00）。

### `delete_hardlink_copies` — 弹窗删除已定位硬链接副本

```python
async def delete_hardlink_copies(
    self,
    orphan_id: int,
    copy_paths: Sequence[str],
    operator: str,
    audit_service: Any = None,
    ip_address: Optional[str] = None,
    _lease_acquired: bool = False,
    _lease_handle: Any = None,
) -> Dict[str, Any]:
    """删除孤儿文件已定位硬链接副本的目录项（仅移除该路径链接，数据保留）。"""
```

- **定位**：`orphan_file_service.py:856`
- **职责**：tombstone 三段式（`_remove_hardlink_copy` L825）删除指向同一 inode 的其它路径；门禁链见「关键不变式·硬链接副本删除」。状态类拒绝以 `failed_list` 返回（HTTP 200），租约 busy 返回 `rejected=true`。
- **调用链**：`orphan_maintenance_scope`（lease）→ `_load_orphan_details`（exclude_in_flight）→ `_load_candidates`（status/operation_state 门禁）→ `_inspect_hardlink_sources`（源身份）→ `_load_hardlink_copy_results` → 同身份候选反查 + `collect_torrent_directory_whitelist`（to_thread，全量下载器）→ `_remove_hardlink_copy`（to_thread）→ setattr payload 更新结果行 + commit → 审计（restore 模式）。
- **端点**：`POST /orphan-files/hardlink-copies/delete`（`orphan_files.py:352`，请求 `{orphan_id, copy_paths≤50}`）。

### `get_orphan_list` — 列表大分页 + 扫描上下文

```python
async def get_orphan_list(
    self,
    page: int = 1,
    page_size: int = 20,
    downloader_id: Optional[str] = None,
    min_size: Optional[int] = None,
    include_deleted: bool = False,
    path_like: Optional[str] = None,
    path_prefix: Optional[str] = None,
    status: Optional[str] = None,
    confidence: Optional[str] = None,
    hardlink_copies: Optional[str] = None,
) -> Dict[str, Any]:
    """分页查询孤儿文件列表与同一批次的页面扫描上下文。"""
```

- **定位**：`orphan_file_service.py:1141`
- **职责**：按稳定 `current_detail_id` 范围分页查询 + `scan_context`；当前返回页经 `_enrich_items` 注入别名/忽视态，`hardlink_copy_count` 直读明细快照列，remaining/ignored 统计排除活动任务。`hardlink_copies="located"` 仅保留快照列 `hardlink_copy_count > 0` 的文件。
- **前置**：`_get_latest_scan`（L378）、`_current_detail_ids_query`（L135）。

### `get_orphan_folder_children` — 文件夹子项懒加载

- **定位**：`orphan_file_service.py:1568`
- **职责**：以父目录和当前筛选独立计数/分页；仅返回页进入 `_enrich_items`（别名/忽视态/快照列副本数均为 DB 批量查询，不实时 stat），因此不会扫整个文件夹。

### `cleanup_orphans` — 手动清理选中孤儿

```python
async def cleanup_orphans(
    self,
    orphan_ids: List[int],
    operator: str,
    audit_service: Any = None,
    store: Any = None,
    scan_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    _lease_acquired: bool = False,
    _lease_handle: Any = None,
) -> Dict[str, Any]:
    """手动清理选中的孤儿文件（安全隔离 + 标记 + 审计日志）。"""
```

- **定位**：`orphan_file_service.py:1942`
- **职责**：清理门禁（最新 completed + scan_id + 实时 manifest/身份复核）后安全隔离 + 标记 + 审计；超量字段仅作为页面提醒，不提供 force 绕过。
- **前置**：`_check_cleanup_allowed`（L438）、`_build_realtime_manifest`（L451）；worker 读取已占用 ID 时不启用查询排除。

---

## 调用关系（关键外部依赖）

```
orphan_file_service.py
  ├─→ app.models.orphan_file.{OrphanFile, OrphanCurrentCandidate, OrphanScanResult}
  ├─→ app.models.orphan_hardlink_copy.{OrphanHardlinkCopyResult} (located 筛选 EXISTS + 副本位置只读 + 删除后结果行同步)
  ├─→ app.services.orphan_quarantine       (隔离区管理 + 多 inode 路径定位)
  ├─→ app.services.orphan_manifest         (有效路径/下载器映射 manifest + 扫描根选择 + 种子目录白名单)
  ├─→ app.services.orphan_lease            (跨进程 lease)
  ├─→ app.services.orphan_purge_job_service (活动任务 ID/路径查询排除)
  └─→ app.services.audit_service           (审计日志)
```
