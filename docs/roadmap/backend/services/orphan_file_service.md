# orphan_file_service.py — 孤儿文件管理服务

> 路线图第三层（services 分支）。依据源码 grep/Read 实测行号生成。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/services/orphan_file_service.py` |
| 行数 | 2791（实测 `wc -l`） |
| 模块职责 | 孤儿文件管理：扫描上下文/清理与隔离/恢复/彻底删除/中断恢复；候选以 canonical_path 为稳定身份；v1.0.6.34~36 扩展列表大分页/真全选/忽视过滤；v1.0.6+ downloader_id/confidence/status 全部支持逗号多值(单值==/多值in_ 或 OR 并集)，status 三态互斥时 OR 退化为“所有未删除文件”(前端给提示) |
| 顶层符号 | 1 class（`OrphanFileService` L62）+ 1 模块级工具函数（`_chunk_values` L56） |

---

## 二、关键不变式

- **选择身份**：孤儿候选以 `canonical_path` 为稳定身份；`resolve_orphan_selection` 把显式勾选或当前筛选全集解析为稳定明细 ID 快照。
- **全选语义（v1.0.6.35）**：`select_all=true` 时以筛选条件重建全量 ID（绑定 scan_id），扣除 `excluded_orphan_ids`。
- **多值过滤（v1.0.6+）**：`_build_orphan_conditions` 对 `downloader_id`/`confidence`/`status` 全部支持逗号分隔多值。downloader_id/confidence 用 `in_`；status 三态(pending/ignored/deleted)互斥，多值时每个用 `and_()` 打包(is_deleted+忽视子查询)再用 `or_()` 取并集——pending 与 ignored/deleted 组合会退化为“所有未删除文件”(前端给提示)。单值仍走原路径(回归保护)。`min_size` 数值区间不动。list/grouped/resolve/prefix_preview 4 个调用点共用此方法。
- **安全清理**：`cleanup_orphans` 有新鲜度门禁（最新扫描必须 completed、scan_id 必须最新）+ 删除前实时复核文件身份（size/mtime_ns/inode/符号链接/路径逃逸），不提供 force 绕过。
- **物理操作安全**：仅用 `os.rmdir` 回收记录隔离根内的空 UUID/scan-id 目录。

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L55 | `_chunk_values` | def（模块级） | 把 Sequence 切块 |
| L61 | `OrphanFileService` | class | 孤儿文件管理服务类 |
| L64 | `__init__` | def | `(self, db: AsyncSession)` |
| L68 | `_detail_canonical_path` | static | 取明细 canonical_path |
| L74 | `_sync_candidate_owner` | def | 同步候选归属 |
| L97 | `_build_orphan_conditions` | def | 构造筛选条件（downloader/path/status/confidence/min_size；downloader_id/confidence 支持逗号多值 in_） |
| L199 | `resolve_orphan_selection` | async def | **全选/勾选解析为稳定 ID 快照** |
| L180 | `_load_orphan_details` | async def | 按 ID 加载明细 |
| L210 | `_load_candidates` | async def | 加载候选 |
| L235 | `_get_latest_scan` | async def | 取最新扫描（可按 status） |
| L250 | `_evaluate_cleanup_snapshot` | def | 评估清理快照 |
| L287 | `_check_cleanup_allowed` | async def | 清理门禁检查 |
| L300 | `_build_realtime_manifest` | async def | 构建实时 manifest |
| L321 | `_identity_complete` | static | 候选身份完整判定 |
| L333 | `_candidate_inode` | static | 候选 inode |
| L337 | `_path_authorized` | static | 路径授权检查 |
| L353 | `_path_in_quarantine_root` | static | 路径是否在隔离根 |
| L379 | `_quarantine_path_authorized` | static | 隔离路径授权 |
| L398 | `_quarantine_delete_guard_error` | static | 隔离删除守卫错误 |
| L404 | `_ensure_quarantine_identity` | async def | 确保隔离身份 |
| L449 | `_authorize_low_confidence` | static | 低置信度授权 |
| L482 | `_owning_root` | static | 归属根 |
| L497 | `get_latest_scan_result` | async def | 最新扫描结果 |
| L562 | `get_orphan_list` | async def | **列表大分页 + 扫描上下文** |
| L645 | `_enrich_items` | async def | 补充条目 |
| L694 | `reconcile_stable_candidate_details` | async def | 对账稳定候选明细 |
| L780 | `cleanup_preview` | async def | 清理预览 |
| L825 | `cleanup_orphans` | async def | **手动清理选中孤儿** |
| L1087 | `set_ignored` | async def | 设置忽视 |
| L1250 | `auto_cleanup_expired` | async def | 过期自动清理 |
| L1436 | `purge_expired_quarantine` | async def | 过期隔离清除 |
| L1582 | `get_quarantine_list` | async def | 隔离区列表 |
| L1658 | `prune_recorded_empty_quarantine_dirs` | async def | 清理空隔离目录 |
| L1699 | `restore_quarantined` | async def | 恢复隔离 |
| L1845 | `_finalize_restore` | async def | 恢复收尾 |
| L1877 | `purge_quarantine_now` | async def | 立即彻底删除 |
| L1978 | `_purge_single_candidate` | async def | 单个彻底删除 |
| L2077 | `_mark_purged` | async def | 标记已清除 |
| L2092 | `_matching_undeleted_details` | async def | 匹配未删明细 |
| L2113 | `_finalize_quarantine` | async def | 隔离收尾 |
| L2166 | `_commit_candidate_state` | async def | 提交候选状态 |
| L2182 | `_quarantine_candidate` | async def | 隔离单个候选 |
| L2232 | `_recover_interrupted_operations` | async def | 中断操作恢复 |
| L2442 | `trigger_scan` | async def | 触发扫描 |

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
    status: Optional[str] = None,
    confidence: Optional[str] = None,
) -> List[int]:
    """把显式勾选或当前筛选全集解析为稳定的明细 ID 快照。"""
```

- **定位**：`orphan_file_service.py:199`
- **职责**：`select_all=false` 时返回去重后的显式 `orphan_ids`（空则报错）；`select_all=true` 时用 `_build_orphan_conditions` 按筛选条件重建全量 ID（须绑定 scan_id），扣除 `excluded_orphan_ids`。
- **调用链**：`_build_orphan_conditions`（L97）→ `db.execute(select(OrphanFile.id))` → 排除集过滤。

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
    status: Optional[str] = None,
    confidence: Optional[str] = None,
) -> Dict[str, Any]:
    """分页查询孤儿文件列表与同一批次的页面扫描上下文。"""
```

- **定位**：`orphan_file_service.py:504`
- **职责**：分页查询列表 + `scan_context`；`status` 语义：`pending`=待清理（默认）、`ignored`=已忽视（联表 is_ignored=1）、`deleted`=已清理；`None` 时由 `include_deleted` 控制（兼容旧调用）。
- **前置**：`_get_latest_scan`（L235）。

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

- **定位**：`orphan_file_service.py:825`
- **职责**：清理门禁（新鲜度 + scan_id 最新 + 实时身份复核）后安全隔离 + 标记 + 审计日志；不提供 force 绕过。
- **前置**：`_check_cleanup_allowed`（L287）、`_build_realtime_manifest`（L300）。

---

## 调用关系（关键外部依赖）

```
orphan_file_service.py
  ├─→ app.models.orphan_file.{OrphanFile, OrphanCurrentCandidate, OrphanScanResult}
  ├─→ app.services.orphan_quarantine       (隔离区管理)
  ├─→ app.services.orphan_manifest         (有效路径/下载器映射 manifest)
  ├─→ app.services.orphan_lease            (跨进程 lease)
  └─→ app.services.audit_service           (审计日志)
```
