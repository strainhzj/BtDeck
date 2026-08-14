# orphan_file_service.py — 孤儿文件管理服务

> 路线图第三层（services 分支）。依据源码 grep/Read 实测行号生成。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/services/orphan_file_service.py` |
| 行数 | 3161（实测 PowerShell `Get-Content`） |
| 模块职责 | 孤儿稳定当前明细列表、文件夹懒加载/独立分页、清理与隔离/恢复/彻底删除；只对可见文件实时统计硬链接，查询与操作排除活动占用条目 |
| 顶层符号 | 2 classes（`HardlinkCopyError` L65、`OrphanFileService` L96）+ 1 模块级工具函数（`_chunk_values` L90） |

---

## 二、关键不变式

- **稳定身份**：候选以 `canonical_path` 为身份并通过 `current_detail_id` 指向可复用的当前明细；已知孤儿后续成功扫描不再每批次新增 `orphan_file`。
- **全选语义（v1.0.6.35）**：`select_all=true` 时以筛选条件重建全量 ID（绑定 scan_id），扣除 `excluded_orphan_ids`。
- **多值过滤（v1.0.6+）**：`_build_orphan_conditions` 对 `downloader_id`/`confidence`/`status` 全部支持逗号分隔多值。downloader_id/confidence 用 `in_`；status 三态(pending/ignored/deleted)互斥，多值时每个用 `and_()` 打包(is_deleted+忽视子查询)再用 `or_()` 取并集——pending 与 ignored/deleted 组合会退化为“所有未删除文件”(前端给提示)。单值仍走原路径(回归保护)。`min_size` 数值区间不动。list/grouped/resolve/prefix_preview 4 个调用点共用此方法。
- **安全清理**：预览、前缀预览、手动和定时自动清理共用最新 completed/scan_id 门禁；超 50000 条只保留提醒状态，不再要求路径映射+孤儿样本复核；删除前仍实时复核 manifest、路径授权和文件身份，不提供 force。
- **活动项占用**：查询和用户操作入口通过 `orphan_purge_job_service` 的 JSON 子查询排除 pending/running 清理 ID 或彻底删除路径；后台 worker 读取自身任务快照时不套该过滤。任务进入 completed/partial/failed 后查询自然重新放行未完成项。
- **文件夹/硬链接**：文件夹父页仅 SQL 聚合，不读子项也不 `stat`；展开后 `get_orphan_folder_children` 独立分页，仅返回页在线读取 `st_nlink - 1`（无副本 `0`，不可访问 `None`）。
- **硬链接位置核对**：点击时重新读取源文件 inode/nlink；`get_hardlink_copy_locations` 复用扫描路径选择并让多个 inode 共用一轮目录遍历，仅返回已配置下载目录内路径，同时明确返回未定位数量。
- **物理操作安全**：仅用 `os.rmdir` 回收记录隔离根内的空 UUID/scan-id 目录。

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L65 | `HardlinkCopyError` | class | 到期删除遇硬链接副本时的安全跳过异常 |
| L75 | `HardlinkCopyError.__init__` | def | 保存候选、隔离路径、副本与原因 |
| L90 | `_chunk_values` | def（模块级） | 把 Sequence 切块 |
| L96 | `OrphanFileService` | class | 孤儿文件管理服务类 |
| L99 | `OrphanFileService.__init__` | def | `(self, db: AsyncSession)` |
| L103 | `_detail_canonical_path` | static | 取明细 canonical_path |
| L109 | `_sync_candidate_owner` | def | 同步候选归属 |
| L131 | `_current_detail_ids_query` | static | 当前候选指向的稳定明细 ID 子查询 |
| L145 | `_build_orphan_conditions` | def | 构造列表/全选筛选并排除活动清理 ID |
| L237 | `_orphan_order_columns` | static | 构造稳定排序列 |
| L259 | `resolve_orphan_selection` | async def | **全选/勾选解析为稳定 ID 快照** |
| L300 | `_load_orphan_details` | async def | 分块加载明细，可选排除活动项 |
| L365 | `_get_latest_scan` | async def | 取最新扫描（可按 status） |
| L384 | `_evaluate_cleanup_snapshot` | def | completed/scan_id 共用清理门禁；超量字段仅作提醒 |
| L438 | `_build_realtime_manifest` | async def | 构建删除前实时 manifest |
| L648 | `get_latest_scan_result` | async def | 最新扫描结果 |
| L684 | `get_hardlink_copy_locations` | async def | **批量按需定位配置目录内副本** |
| L772 | `get_orphan_list` | async def | **稳定当前明细分页 + 扫描上下文** |
| L913 | `get_orphan_list_grouped` | async def | 文件夹父页 SQL 聚合，不加载/不 stat 全部子项 |
| L1147 | `get_orphan_folder_children` | async def | **展开后子项独立分页，仅可见页统计硬链接** |
| L1218 | `_enrich_hardlink_copy_counts` | static | 在线补充 `st_nlink - 1`，不可访问为 `None` |
| L1288 | `reconcile_stable_candidate_details` | async def | keyset 分批对账稳定隔离候选明细，每页统一进入 `db_write_scope` |
| L1446 | `prefix_match_preview` | async def | 路径前缀预览（共用清理门禁） |
| L1487 | `cleanup_preview` | async def | 清理预览 |
| L1533 | `cleanup_orphans` | async def | **后台手动清理任务执行** |
| L1807 | `set_ignored` | async def | 设置忽视 |
| L1974 | `auto_cleanup_expired` | async def | 过期自动清理（共用最新快照与实时安全校验） |
| L2171 | `purge_expired_quarantine` | async def | 过期隔离清除 |
| L2364 | `get_quarantine_list` | async def | 隔离区列表 |
| L2481 | `restore_quarantined` | async def | 恢复隔离 |
| L2691 | `purge_quarantine_now` | async def | 后台立即彻底删除 |
| L2842 | `_purge_single_candidate` | async def | 单个彻底删除 |
| L2966 | `_detect_hardlink_copies` | async def | 删除前枚举硬链接副本 |
| L3230 | `_recover_interrupted_operations` | async def | 中断操作恢复 |

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
) -> List[int]:
    """把显式勾选或当前筛选全集解析为稳定的明细 ID 快照。"""
```

- **定位**：`orphan_file_service.py:259`
- **职责**：`select_all=false` 时返回去重后的显式 `orphan_ids`（空则报错）；`select_all=true` 时用 `_build_orphan_conditions` 按筛选条件重建全量 ID（须绑定 scan_id），自动排除活动任务占用项并扣除 `excluded_orphan_ids`。
- **调用链**：`_build_orphan_conditions`（L145）→ `db.execute(select(OrphanFile.id))` → 排除集过滤。

### `get_hardlink_copy_locations` — 按需定位硬链接副本路径

```python
async def get_hardlink_copy_locations(
    self,
    orphan_ids: Sequence[int],
) -> Dict[str, Any]:
    """按需定位孤儿文件在已配置扫描目录内的其它硬链接路径。"""
```

- **定位**：`orphan_file_service.py:686`
- **职责**：重新读取所选源文件 inode/nlink，批量加载当前未删除明细，并把多个目标 inode 合并为一次配置目录遍历；返回已定位完整路径、未定位数量、失效 ID 与不可访问状态。
- **调用链**：`_load_orphan_details`（L300）→ `_inspect_hardlink_sources`（L658，经 `asyncio.to_thread`）→ `collect_scan_path_selection` → `find_hardlink_paths`。

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
) -> Dict[str, Any]:
    """分页查询孤儿文件列表与同一批次的页面扫描上下文。"""
```

- **定位**：`orphan_file_service.py:772`
- **职责**：按稳定 `current_detail_id` 范围分页查询 + `scan_context`；只为当前返回的文件页补充 `hardlink_copy_count`，remaining/ignored 统计排除活动任务。
- **前置**：`_get_latest_scan`（L365）、`_current_detail_ids_query`（L131）。

### `get_orphan_folder_children` — 文件夹子项懒加载

- **定位**：`orphan_file_service.py:1147`
- **职责**：以父目录和当前筛选独立计数/分页；仅返回页进入 `_enrich_items`，因此网络盘 `stat` 与硬链接统计不会扫整个文件夹。

### `cleanup_orphans` — 手动清理选中孤儿

```python
async def cleanup_orphans(
    self,
    orphan_ids: List[int],
    operator: str,
    audit_service: Any = None,
    store: Any = None,
    scan_id: Optional[str] = None,
    _lease_acquired: bool = False,
    _lease_handle: Any = None,
) -> Dict[str, Any]:
    """手动清理选中的孤儿文件（安全隔离 + 标记 + 审计日志）。"""
```

- **定位**：`orphan_file_service.py:1533`
- **职责**：清理门禁（最新 completed + scan_id + 实时 manifest/身份复核）后安全隔离 + 标记 + 审计；超量字段仅作为页面提醒，不提供 force 绕过。
- **前置**：`_check_cleanup_allowed`（L425）、`_build_realtime_manifest`（L438）；worker 读取已占用 ID 时不启用查询排除。

---

## 调用关系（关键外部依赖）

```
orphan_file_service.py
  ├─→ app.models.orphan_file.{OrphanFile, OrphanCurrentCandidate, OrphanScanResult}
  ├─→ app.services.orphan_quarantine       (隔离区管理 + 多 inode 路径定位)
  ├─→ app.services.orphan_manifest         (有效路径/下载器映射 manifest + 扫描根选择)
  ├─→ app.services.orphan_lease            (跨进程 lease)
  ├─→ app.services.orphan_purge_job_service (活动任务 ID/路径查询排除)
  └─→ app.services.audit_service           (审计日志)
```
