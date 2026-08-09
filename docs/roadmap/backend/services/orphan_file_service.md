# orphan_file_service.py — 孤儿文件管理服务

> 路线图第三层（services 分支）。依据源码 grep/Read 实测行号生成。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/services/orphan_file_service.py` |
| 行数 | 2883（实测 PowerShell `Get-Content`） |
| 模块职责 | 孤儿文件管理：扫描上下文/清理与隔离/恢复/彻底删除/中断恢复；列表、分组统计、预览、忽视与恢复入口排除持久化任务中 pending/running 的占用条目 |
| 顶层符号 | 1 class（`OrphanFileService` L67）+ 1 模块级工具函数（`_chunk_values` L61） |

---

## 二、关键不变式

- **选择身份**：孤儿候选以 `canonical_path` 为稳定身份；`resolve_orphan_selection` 把显式勾选或当前筛选全集解析为稳定明细 ID 快照。
- **全选语义（v1.0.6.35）**：`select_all=true` 时以筛选条件重建全量 ID（绑定 scan_id），扣除 `excluded_orphan_ids`。
- **多值过滤（v1.0.6+）**：`_build_orphan_conditions` 对 `downloader_id`/`confidence`/`status` 全部支持逗号分隔多值。downloader_id/confidence 用 `in_`；status 三态(pending/ignored/deleted)互斥，多值时每个用 `and_()` 打包(is_deleted+忽视子查询)再用 `or_()` 取并集——pending 与 ignored/deleted 组合会退化为“所有未删除文件”(前端给提示)。单值仍走原路径(回归保护)。`min_size` 数值区间不动。list/grouped/resolve/prefix_preview 4 个调用点共用此方法。
- **安全清理**：`cleanup_orphans` 有新鲜度门禁（最新扫描必须 completed、scan_id 必须最新）+ 删除前实时复核文件身份（size/mtime_ns/inode/符号链接/路径逃逸），不提供 force 绕过。
- **活动项占用**：查询和用户操作入口通过 `orphan_purge_job_service` 的 JSON 子查询排除 pending/running 清理 ID 或彻底删除路径；后台 worker 读取自身任务快照时不套该过滤。任务进入 completed/partial/failed 后查询自然重新放行未完成项。
- **物理操作安全**：仅用 `os.rmdir` 回收记录隔离根内的空 UUID/scan-id 目录。

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L61 | `_chunk_values` | def（模块级） | 把 Sequence 切块 |
| L67 | `OrphanFileService` | class | 孤儿文件管理服务类 |
| L70 | `__init__` | def | `(self, db: AsyncSession)` |
| L74 | `_detail_canonical_path` | static | 取明细 canonical_path |
| L80 | `_sync_candidate_owner` | def | 同步候选归属 |
| L102 | `_build_orphan_conditions` | def | 构造列表/全选筛选并排除活动清理 ID |
| L188 | `_orphan_order_columns` | static | 构造稳定排序列 |
| L210 | `resolve_orphan_selection` | async def | **全选/勾选解析为稳定 ID 快照** |
| L249 | `_load_orphan_details` | async def | 分块加载明细，可选排除活动项 |
| L282 | `_load_candidates` | async def | 加载候选 |
| L307 | `_get_latest_scan` | async def | 取最新扫描（可按 status） |
| L322 | `_evaluate_cleanup_snapshot` | def | 评估清理快照 |
| L359 | `_check_cleanup_allowed` | async def | 清理门禁检查 |
| L372 | `_build_realtime_manifest` | async def | 构建实时 manifest |
| L393 | `_identity_complete` | static | 候选身份完整判定 |
| L405 | `_candidate_inode` | static | 候选 inode |
| L409 | `_path_authorized` | static | 路径授权检查 |
| L438 | `_path_in_quarantine_root` | static | 路径是否在隔离根 |
| L464 | `_quarantine_path_authorized` | static | 隔离路径授权 |
| L483 | `_quarantine_delete_guard_error` | static | 隔离删除守卫错误 |
| L489 | `_ensure_quarantine_identity` | async def | 确保隔离身份 |
| L534 | `_authorize_low_confidence` | static | 低置信度授权 |
| L567 | `_owning_root` | static | 归属根 |
| L582 | `get_latest_scan_result` | async def | 最新扫描结果 |
| L589 | `get_orphan_list` | async def | **列表大分页 + 排除活动项的扫描上下文** |
| L722 | `get_orphan_list_grouped` | async def | 文件夹分组分页，统计口径同样排除活动项 |
| L911 | `_build_folder_row` | def | 构造文件夹聚合行 |
| L947 | `_enrich_items` | async def | 补充条目 |
| L996 | `reconcile_stable_candidate_details` | async def | 对账稳定候选明细 |
| L1082 | `prefix_match_preview` | async def | 路径前缀预览 |
| L1122 | `cleanup_preview` | async def | 清理预览，排除活动清理 ID |
| L1168 | `cleanup_orphans` | async def | **后台手动清理任务执行**（读取自身占用项） |
| L1433 | `set_ignored` | async def | 设置忽视，排除活动清理 ID |
| L1600 | `auto_cleanup_expired` | async def | 过期自动清理 |
| L1786 | `purge_expired_quarantine` | async def | 过期隔离清除 |
| L1932 | `get_quarantine_list` | async def | 隔离区列表，排除活动彻底删除路径 |
| L2007 | `prune_recorded_empty_quarantine_dirs` | async def | 清理空隔离目录 |
| L2048 | `restore_quarantined` | async def | 恢复隔离，拒绝活动彻底删除路径 |
| L2195 | `_finalize_restore` | async def | 恢复收尾 |
| L2227 | `purge_quarantine_now` | async def | 后台立即彻底删除任务执行 |
| L2368 | `_purge_single_candidate` | async def | 单个彻底删除 |
| L2478 | `_mark_purged` | async def | 标记已清除 |
| L2493 | `_matching_undeleted_details` | async def | 匹配未删明细 |
| L2514 | `_finalize_quarantine` | async def | 隔离收尾 |
| L2567 | `_commit_candidate_state` | async def | 提交候选状态 |
| L2583 | `_quarantine_candidate` | async def | 隔离单个候选 |
| L2633 | `_recover_interrupted_operations` | async def | 中断操作恢复 |
| L2843 | `trigger_scan` | async def | 触发扫描 |

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

- **定位**：`orphan_file_service.py:210`
- **职责**：`select_all=false` 时返回去重后的显式 `orphan_ids`（空则报错）；`select_all=true` 时用 `_build_orphan_conditions` 按筛选条件重建全量 ID（须绑定 scan_id），自动排除活动任务占用项并扣除 `excluded_orphan_ids`。
- **调用链**：`_build_orphan_conditions`（L102）→ `db.execute(select(OrphanFile.id))` → 排除集过滤。

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

- **定位**：`orphan_file_service.py:589`
- **职责**：分页查询列表 + `scan_context`；列表、remaining 与 ignored 统计统一排除 pending/running 清理任务占用 ID。
- **前置**：`_get_latest_scan`（L307）。

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

- **定位**：`orphan_file_service.py:1168`
- **职责**：清理门禁（新鲜度 + scan_id 最新 + 实时身份复核）后安全隔离 + 标记 + 审计日志；不提供 force 绕过。
- **前置**：`_check_cleanup_allowed`（L359）、`_build_realtime_manifest`（L372）；worker 读取已由任务占用的 ID 时不启用查询排除。

---

## 调用关系（关键外部依赖）

```
orphan_file_service.py
  ├─→ app.models.orphan_file.{OrphanFile, OrphanCurrentCandidate, OrphanScanResult}
  ├─→ app.services.orphan_quarantine       (隔离区管理)
  ├─→ app.services.orphan_manifest         (有效路径/下载器映射 manifest)
  ├─→ app.services.orphan_lease            (跨进程 lease)
  ├─→ app.services.orphan_purge_job_service (活动任务 ID/路径查询排除)
  └─→ app.services.audit_service           (审计日志)
```
