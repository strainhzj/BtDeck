# torrent_crud.py — 种子 CRUD 端点

> 本文件是路线图第三层样例，演示后端 Python 四节模板的产出形态。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/api/endpoints/torrent_crud.py` |
| 行数 | 485（实测 2026-09-21；2026-08-22 样例产出时为 727 行，此后单个添加主体抽取至 `torrent_add_service`、批量添加主体抽取至 `torrent_batch_add_service`） |
| 模块职责 | 种子 CRUD 端点：列表同步、单个/批量添加、按主键查询、通用条件查询、Tracker 主域名候选 |
| 路由前缀 | 由 `torrents.py` 聚合后挂到 `/torrents`（最终 `/api/v1/torrents/*`） |
| 顶层符号 | 1 class（`TorrentOperationRequest`）+ 6 路由函数（实测 2026-09-21） |

---

## 二、关键不变式

阅读本模块前必须知道的约束（全部来自源码注释与代码证据，行号 2026-09-21 实测）：

### INV-1：下载器连接必须走 `app.state.store` 缓存（强制规范）

源码证据：`create_torrent` L157（`store=getattr(request.app.state, "store", None)` 注入服务）、`create_torrents_batch` L206-233（缓存校验链）

```python
# L206: 批量添加先校验 app.state.store 存在
if not hasattr(app.state, "store"): ...
# L214: 从 app.state.store 获取缓存的下载器快照（强制规范）
cached_downloaders = await app.state.store.get_snapshot()
# L215/223/227: 依次校验 下载器在缓存中 / fail_time 未失效 / client 连接存在
downloader = next((item for item in cached_downloaders if item.downloader_id == downloader_id), None)
```

> 严禁 `db.query(BtDownloaders)` 后重复创建客户端连接。详见 [约束](../../../../backend/docs/constraints/downloader-connection.md)。

### INV-2：下载器类型判断走模型属性 / 服务层

`torrent_list` L88/L92 用 `downloader.is_qbittorrent` / `downloader.is_transmission` 模型属性分流（替代直读 `downloader_type` 数字）；单添加/批量添加的双类型分支（0=qBittorrent, 1=Transmission）已随主体移至 `torrent_add_service` / `torrent_batch_add_service`。

### INV-3：批量上传暂存必须 fail-closed 回收

源码证据：`create_torrents_batch` L235-252

```python
# L236-238: 逐文件 stage_torrent_file 暂存
# L239-245: 任一失败 → cleanup_staged_files(staged_files) 回收 + 动态 str(exc) 只进日志
# L283-289: 后台任务创建失败同样回收暂存文件
```

### INV-4：失败路径 data 携带稳定 reasonCode（双语 P4 错误契约，2026-09-21）

动态 `str(e)` 不进 msg（只进日志），信封四字段不变。本文件 10 处：`DB_OPERATION_FAILED`（L126）、`TORRENT_SYNC_FAILED`（L131）、单添加 `result.reason_code` 透传（L175）、`TORRENT_FILES_REQUIRED`（L200）、`INTERNAL_ERROR`（L203）、`DOWNLOADER_CACHE_UNAVAILABLE`（L211）、`DOWNLOADER_NOT_FOUND`（L221）、`DOWNLOADER_OFFLINE`（L225）、`DOWNLOADER_CONNECTION_MISSING`（L232）、`TORRENT_STAGE_FAILED`（L244）、`TORRENT_BATCH_SUBMIT_FAILED`（L288）。

### INV-5：ORM 实体不能直接作为响应返回

源码证据：`get_torrent` docstring L301-306——`response_model=CommonResponse` 下 Pydantic 无法从 ORM 属性构造信封（实测响应全 null），必须经 `convert_to_vo`（L320，与 getList 同源转换）包装。

### INV-6：异常兜底覆盖整个分支并返回信封而非抛出

源码证据：`torrent_list` L123-134——`SQLAlchemyError`（L123 → `DB_OPERATION_FAILED`）+ 通用 `Exception`（L128 → `TORRENT_SYNC_FAILED`）两层捕获，均返回 `CommonResponse(code="500")`；`get_torrents` L432-433 同款单层兜底。

### INV-7：审计上下文与操作人从认证态推导

单添加经 `AuditContext.from_request(request)`（L164）传入服务；批量添加经 `extract_audit_info_from_request(request)`（L253-256，失败兜空 dict）+ `operator` 从 `_user.username` 推导（L257-260，兜底 `"admin"` 仅留字符串字面量）。旧"operator 硬编码 admin"缺陷已随服务化修复。

### INV-8：所有路由统一认证 + 统一响应

- 认证：`_user=Depends(require_authenticated_user)`（6 个路由均有）
- 响应：`response_model=CommonResponse`（除 `get_torrents` 与 `get_tracker_domains` 外，二者手工构造信封）

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L40 | `logger` | 模块常量 | `logging.getLogger(__name__)` |
| L41 | `router` | 模块常量 | `APIRouter()` |
| L42 | `urllib3.disable_warnings(...)` | 模块副作用 | 关闭 InsecureRequestWarning |
| L47-48 | `_QB_CALL_TIMEOUT` / `_TR_CALL_TIMEOUT` | 模块常量 | 单次下载器 API 调用 30s 预算（与 tracker.py 切片同风格） |
| L54 | `TorrentOperationRequest` | class（BaseModel） | 种子操作请求统一基类 |
| L62 | `torrent_list` | def（路由） | `POST /list` 同步下载器种子到 DB（装饰器 L61） |
| L136 | `create_torrent` | async def（路由） | `POST /add` 单个添加（2026-09-05 起为 TorrentAddService HTTP 薄壳；装饰器 L135） |
| L180 | `create_torrents_batch` | async def（路由） | `POST /add-batch` 提交异步批量添加（装饰器 L179） |
| L300 | `get_torrent` | def（路由） | `GET /torrents/{info_id}/{downloader_id}/{downloader_name}` 按主键查（装饰器 L299） |
| L325 | `get_torrents` | def（路由） | `GET /getList` 通用条件查询（含 Tracker 主域名、错误单种、同内容、活动快照筛选；装饰器 L324） |
| L452 | `get_tracker_domains` | def（路由） | `GET /tracker-domains` 返回定时 Tracker 同步采集的主机域名（60s TTL 缓存；装饰器 L451） |

> 2026-09-05 起 `create_torrent` 的主体（原嵌套 write_temp_file / read_file_data / read_file_data_qb / write_audit_log_async 与双类型分支/轮询/落库）原样抽取至 `app/services/torrent_add_service.py`（`TorrentAddService.add_torrent`），端点仅做 Form 解析与结果映射。批量添加的逐文件处理主体位于 `app/services/torrent_batch_add_service.py`（`process_torrent_batch_job`）。

---

## 四、方法签名详情

### 路由处理函数

#### `torrent_list` — 同步下载器种子到 DB

```python
@router.post("/list", response_model=CommonResponse)
def torrent_list(
    request: Request,
    _user=Depends(require_authenticated_user),
    name: str = Query(default="default", alias="name", description="种子名称"),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:62`
- **职责**：查询所有启用的下载器（`dr=0, enabled=True, status="1"`，L74-79），按 `is_qbittorrent`/`is_transmission` 属性调用 `qb_add_torrents` / `tr_add_torrents` 同步种子到 DB（L88-96），返回成功/失败计数。
- **不变式**：异常分两层捕获（`SQLAlchemyError` L123 + 通用 `Exception` L128），均返回 `CommonResponse(code="500")` + reasonCode 而非抛出。

#### `create_torrent` — 单个添加种子

```python
@router.post("/add", response_model=CommonResponse)
async def create_torrent(
    request: Request,
    _user=Depends(require_authenticated_user),
    downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
    save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
    tags: Optional[str | None] = Form("", description="标签"),
    category: Optional[str | None] = Form("", description="分类"),
    paused: Optional[bool] = Form(False, description="是否暂停,0代表false，1代表true"),
    skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验,0代表false，1代表true"),
    is_sequential_download: Optional[bool | None] = Form(False, description="是否按顺序下载,0代表false，1代表true"),
    is_first_last_piece_priority: Optional[bool | None] = Form(
        False, description="是否先下载首尾文件块,0代表false，1代表true"
    ),
    upload_limit: Optional[str | int | None] = Form(False, description="上传速度，单位bytes/second"),
    download_limit: Optional[str | int | None] = Form(False, description="下载速度，单位bytes/second"),
    torrent_file: Optional[UploadFile] = File(description="种子文件"),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:136`（2026-09-05 起薄壳，主体在服务层）
- **职责**：读取上传字节（L155）→ 构造 `TorrentAddParams` + `TorrentAddService(db, store=...)`（L157）→ `add_torrent(..., audit_context=AuditContext.from_request(request))` → 映射 `TorrentAddResult` 为 CommonResponse（失败路径 data.reasonCode，L174-176）。
- **关键调用链**（主体位于 [torrent_add_service](../../../services/README.md) `add_torrent`）：
  - 服务内 `store.get_snapshot()` → 缓存下载器（store 由端点注入 `getattr(request.app.state, "store", None)`）
  - `calculate_info_hash` / 双类型分支（TR `add_torrent`、qB `torrents_add` 经 `call_downloader_api` INTERACTIVE lane）/ 轮询 / 落库 / 异步审计——全部原样保留，status/code/msg 契约与抽取前逐字一致
- **不变式**：INV-1/2/4/7/8 适用（行为零变化，由 tests/api/test_torrent_crud_add_fallback.py 41 例守护）。

#### `create_torrents_batch` — 批量添加种子

```python
@router.post("/add-batch", response_model=CommonResponse)
async def create_torrents_batch(
    request: Request,
    _user=Depends(require_authenticated_user),
    torrent_files: List[UploadFile] = File(..., description="种子文件列表，数量不限"),
    downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
    save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
    tags: Optional[str | None] = Form("", description="标签"),
    category: Optional[str | None] = Form("", description="分类"),
    paused: Optional[bool] = Form(False, description="是否暂停"),
    skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验"),
    is_sequential_download: Optional[bool | None] = Form(False, description="是否顺序下载"),
    is_first_last_piece_priority: Optional[bool | None] = Form(False, description="是否优先首尾文件块"),
    upload_limit: Optional[str | int | None] = Form(False, description="上传速度，单位 bytes/second"),
    download_limit: Optional[str | int | None] = Form(False, description="下载速度，单位 bytes/second"),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:180`
- **职责**：文件非空校验（L198-201）→ 下载器缓存校验链（L205-233：store 存在 L206 / 快照查找 L214-215 / fail_time 失效 503 L223 / client 缺失 500 L227）→ 逐文件 `stage_torrent_file` 暂存（L235-245，失败 `cleanup_staged_files` 回收）→ 审计信息与 operator 推导（L252-260）→ 构建 `TorrentBatchAddOptions`（L262-275，operator 兜底 `"admin"`）→ `asyncio.create_task(process_torrent_batch_job(...))` + `register_torrent_batch_task`（L277-282，失败同样回收 L283-289）→ 立即返回 `202 accepted` + `task_id`（L290-295），完成结果经通知中心告知用户。
- **逐文件逻辑**：原内联的"每文件独立 try/except、200/500/207 汇总"处理已全部移至 `app/services/torrent_batch_add_service.py` 的 `process_torrent_batch_job`。
- **响应码**：无文件 `400`、下载器不在缓存 `404`、下载器失效 `503`、下载器连接缺失/暂存/任务创建失败 `500`、提交成功 `202`。

#### `get_torrent` — 按复合主键查询

```python
@router.get("/torrents/{info_id}/{downloader_id}/{downloader_name}", response_model=CommonResponse)
def get_torrent(
    info_id: str,
    downloader_id: str,
    downloader_name: str,
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:300`
- **职责**：委托 `get_torrent_info(db, info_id, downloader_id)`（services 层，L313）查询，未找到抛 `CommonResponse(404)`；找到经 `convert_to_vo`（L320）包装信封。
- **注意**：`downloader_name` 是路径参数但**未在函数体内使用**（仅用于前端 URL 语义）。

#### `get_torrents` — 通用条件查询

```python
@router.get("/getList")
def get_torrents(
    downloader_id: Optional[str] = Query(None, description="所属下载器主键（支持多选，逗号分隔）", examples=[""]),
    downloader_name_like: Optional[str] = Query(None, description="所属下载器名模糊查询"),
    name_like: Optional[str] = Query(None, description="种子名称模糊查询"),
    save_path_like: Optional[str] = Query(None, description="种子文件保存路径模糊查询"),
    size_min: Optional[str] = Query(None, description="种子大小最小值"),
    size_max: Optional[str] = Query(None, description="种子大小最大值"),
    added_date_min: Optional[str] = Query(None, description="添加时间最小值"),
    added_date_max: Optional[str] = Query(None, description="添加时间最大值"),
    completed_date_min: Optional[str] = Query(None, description="完成时间最小值"),
    completed_date_max: Optional[str] = Query(None, description="完成时间最大值"),
    tags_like: Optional[str] = Query(None, description="标签模糊查询"),
    category_like: Optional[str] = Query(None, description="分类模糊查询"),
    tracker_like: Optional[str] = Query(None, description="tracker地址模糊查询"),
    tracker_domain: Optional[str] = Query(
        None,
        description="Tracker主域名筛选（支持多选，逗号分隔；例如 tracker.example.com）",
    ),
    status: Optional[str] = Query(
        None,
        description="种子状态筛选(支持多选，逗号分隔；error状态满足status='error'或has_tracker_error=True之一即可)",
    ),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100000, description="限制记录数"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
    active_only: bool = Query(False, description="仅显示活动种子（实时速度>0，由活动集合缓存驱动）"),
    same_content_only: bool = Query(
        False,
        description="仅显示名称、大小相同且规范化 InfoHash 至少两个不同值的种子",
    ),
    single_error_only: bool = Query(
        False,
        description="仅显示错误且全局同名同大小内容唯一的种子",
    ),
    with_trackers: bool = Query(
        True,
        description="是否在行内携带 tracker_info 明细数组（移动端列表不展示时传 false 省去批量预取与序列化开销；默认 true 兼容桌面视图）",
    ),
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:325`
- **职责**：支持普通筛选、Tracker 主域名、活动快照、同内容/错误单种条件、排序与分页的通用查询，委托 `get_torrent_infos(...)`（torrent_helpers，L392-418）。
- **活动种子特殊处理**（L373-389）：`active_only=True` 时读取 `get_active_keys_snapshot()`，若快照未就绪返回 `206`（partial，L387），响应携带 `activeSnapshotReady/activeSnapshotStatus`。
- **Tracker 主域名筛选**（参数 L339，委托 L412）：`tracker_domain` 接受逗号分隔多选，使用已同步的 TrackerInfo URL hostname/host 关系筛选；域名列表由 `/torrents/tracker-domains` 提供。✨2026-08-27（torrent_helpers.py）：EXISTS/ANY 语义保留（种子任一 tracker 命中即返回），入口统一归一 `requested_tracker_domains` 后由 SQL 8 条件（like 已 `escape="\\"` 字面量化，`_`/`%` 不再通配）与 Python 谓词 `tracker_row_matches_domains`（torrent_helpers.py L53）同口径过滤，并在 VO 的 `tracker_info[].matched_domain` 上标记命中的域名；同批修复 `tracker_like` 子查询空结果由"静默返回全部"改为"返回空列表"。观察日志：`[tracker-domain-filter]`/`[tracker-filter]`/`[torrent-list]` 三组 debug 锚点，`LOG_LEVEL=DEBUG` 开启。
- **同内容筛选**（参数 L347，委托 L414）：`same_content_only=True` 委托共享查询按"名称 + 大小 + 至少两个不同规范化 Hash"过滤，并继续按种子行 `skip/limit` 分页。
- **错误单种筛选**（参数 L352，委托 L415）：`single_error_only=True` 只保留错误任务，并用不受当前 Tracker/状态筛选影响的全局名称+大小分组确认任务唯一；同一任务的多个 Tracker 服务不增加任务计数。
- **tracker 明细瘦身**（参数 L360，委托 L416 `include_trackers=with_trackers`）：false 时 VO 免装 tracker_info（移动端列表瘦身，2026-09-10）。
- **响应字段**：`total/list/pageSize`（分页固定字段，见 [API 响应格式约束](../../../../backend/docs/constraints/api-response-format.md)）。

#### `get_tracker_domains` — 已同步 Tracker 主域名

```python
@router.get("/tracker-domains")
def get_tracker_domains(
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:452`
- **职责**：读取 `TrackerInfo` 中仍有效的 `tracker_url/tracker_host`（L467），复用 `extract_domains_from_trackers()` 提取 URL hostname，去重排序后返回 `CommonResponse.data`。
- **性能决策**：✨2026-09-10 起（mobile-ux-fixes）加 60s 进程内 TTL 缓存（`_TRACKER_DOMAINS_CACHE_TTL_S` L441 / `_tracker_domains_cache` L442 / 测试钩子 `reset_tracker_domains_cache` L445；uvicorn 单 Worker 无跨进程一致性问题，新域名最多延迟一个 TTL 出现）。此前实测 30475 条 Tracker 记录提取 90 个域名耗时 231-262ms，移动端每次挂载/展开筛选都拉、多客户端并发会放大扫描成本，故加缓存。

---

## 调用关系图

```
torrent_crud.py
  │
  ├─→ app.api.responseVO.CommonResponse          (统一响应)
  ├─→ app.database.get_db                        (DB 会话)
  ├─→ app.auth.dependencies.require_authenticated_user  (认证)
  ├─→ app.downloader.models.BtDownloaders        (下载器 ORM，仅 /list 直查)
  ├─→ app.torrents.models.TrackerInfo            (Tracker ORM，tracker-domains)
  │
  ├─→ app.services.torrent_add_service.{TorrentAddParams, TorrentAddService}  (单添加主体)
  ├─→ app.services.torrent_batch_add_service.{TorrentBatchAddOptions, stage_torrent_file,
  │       cleanup_staged_files, process_torrent_batch_job, register_torrent_batch_task}  (批添加)
  ├─→ app.services.torrent_crud_service.get_torrent_info  (按主键查)
  ├─→ app.services.audit_context.AuditContext    (审计四元组)
  ├─→ app.services.audit_service.extract_audit_info_from_request  (批量审计信息)
  │
  ├─→ app.api.endpoints.torrent_helpers          (横向复用)
  │     └─ get_torrent_infos
  ├─→ app.services.torrent_vo_conversion.convert_to_vo  (VO 转换族，2026-09-08 W4/G4 自 torrent_helpers 迁入服务层)
  ├─→ app.services.torrent_add_service.{TorrentAddService, TorrentAddParams}  (单添加协议无关主体，2026-09-05 抽取；MCP torrent_add_file 共用；2026-09-22 合并后携双语 P4 reason_code 与 MCP 领域事实字段并存)
  ├─→ app.services.torrent_add_helpers           (add 家族辅助，2026-09-08 自 torrent_helpers 迁入服务层)
  │     ├─ calculate_info_hash
  │     ├─ get_transmission_torrent_info
  │     ├─ create_qbittorrent_torrent_record
  │     └─ create_transmission_torrent_record
  ├─→ app.core.reannounce_config_operations.extract_domains_from_trackers (主机域名归一)
  ├─→ app.api.endpoints.torrent_speed.get_active_keys_snapshot  (活动种子快照)
  └─→ app.api.endpoints.torrent_sync.{qb_add_torrents, tr_add_torrents}  (/list 同步)
```

## 反模式与技术债

- **已消除**：`create_torrent` 双分支代码重复（`read_file_data`/`read_file_data_qb`/轮询/落库）与嵌套函数定义，已随 2026-09-05 服务化（`torrent_add_service`）移出本文件；批添加逐文件处理移至 `torrent_batch_add_service`。
- **已修复**：审计 operator 硬编码 "admin" → 从 `_user.username` 推导（L257-260，`str(operator or "admin")` 兜底字面量保留）。
- **`get_torrent` 的 `downloader_name` 参数未使用**：仅作 URL 语义，未在函数体内引用。
- **`torrent_list` 仍直查 `BtDownloaders` ORM**（L74-79）：同步专用路径惯例（只读 enabled 列表），不走 `app.state.store`；与 INV-1 不冲突（不创建连接，同步主体在 torrent_sync 内部走缓存）。
