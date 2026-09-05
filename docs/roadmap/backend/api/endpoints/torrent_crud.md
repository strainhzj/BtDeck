# torrent_crud.py — 种子 CRUD 端点

> 本文件是路线图第三层样例，演示后端 Python 四节模板的产出形态。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/api/endpoints/torrent_crud.py` |
| 行数 | 727（实测 2026-08-22） |
| 模块职责 | 种子 CRUD 端点：列表同步、单个/批量添加、按主键查询、通用条件查询 |
| 路由前缀 | 由 `torrents.py` 聚合后挂到 `/torrents`（最终 `/api/v1/torrents/*`） |
| 顶层符号 | 1 class（`TorrentOperationRequest`）+ 6 路由函数 |

---

## 二、关键不变式

阅读本模块前必须知道的约束（全部来自源码注释与代码证据）：

### INV-1：下载器连接必须走 `app.state.store` 缓存（强制规范）

源码证据：`create_torrent` L159-194、`create_torrents_batch` L508-521

```python
# L161-163: 从 app.state.store 获取缓存的下载器（强制规范）
app = request.app
if not hasattr(app.state, "store"): ...
# L171: 使用异步版本 get_snapshot() 避免线程问题
cached_downloaders = await app.state.store.get_snapshot()
```

> 严禁 `db.query(BtDownloaders)` 后重复创建客户端连接。详见 [约束](../../../../backend/docs/constraints/downloader-connection.md)。

### INV-2：下载器类型判断用 `downloader_type` 字段（0=qBittorrent, 1=Transmission）

源码证据：L241 `if downloader.downloader_type == 1:  # Transmission`、L331 `if downloader.downloader_type == 0:  # qBittorrent`

### INV-3：临时文件写入必须 `flush + fsync + close` 后返回路径

源码证据：`write_temp_file` L207-223（内嵌函数）

```python
tmp_file.flush()       # L212 确保数据写入磁盘
os.fsync(tmp_file.fileno())  # L213 强制同步
tmp_file.close()       # L214
```

文件 I/O 通过 `asyncio.to_thread` 放入线程池执行（L225），避免阻塞事件循环。

### INV-4：添加种子后轮询验证（最多 30 秒）

源码证据：L274-286（Transmission）、L365-386（qBittorrent）

```python
max_retries = 30
while tr_torrent is None and retry_count < max_retries:
    await asyncio.sleep(1)
    tr_torrent = await get_transmission_torrent_info(tr_client, info_hash)
```

### INV-5：DB 查询必须返回完整实体（不能只 select info_id）

源码证据：L289-298、L391-400（2 处重复注释；批添加路由原有 2 处已随批处理逻辑外移而移出本文件）

```python
# ⚠️ 必须查询完整实体而非仅 info_id 列：审计日志构造时会访问 .name/.hash/.size，
# 若只 select info_id 返回 Row 对象，访问未选中列会触发 AttributeError("name")
# （SQLAlchemy 2.0 Row.__getattr__ 行为）
```

### INV-6：异常兜底必须覆盖整个分支（含 ORM 写入）

源码证据：L310-328（Transmission 兜底）、L411-437（qBittorrent 兜底）

> `prod-hotfix-2026-07-19` 修复：早期 try 块只覆盖 `torrents_add/torrents_info` 轮询，把 `create_qbittorrent_torrent_record + db.commit()` 留在 try 之外，导致 `TypeError("Object of type ValueError is not JSON serializable")` 冒泡到全局 500。本修复把整个分支纳入 try（批添加流程现已重构至 `torrent_batch_add_service.py`）。

### INV-7：审计日志异步写入，失败不影响主业务

源码证据：`write_audit_log_async` L440-467

```python
asyncio.create_task(write_audit_log_async())  # L471 后台执行
# 审计日志失败不影响主业务（L465-467 catch all）
```

> ⚠ 注释警告：异步任务异常会被静默忽略（L470）。

### INV-8：所有路由统一认证 + 统一响应

- 认证：`_user=Depends(require_authenticated_user)`（6 个路由均有）
- 响应：`response_model=CommonResponse`（除 `get_torrents` 与 `get_tracker_domains` 外）

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L46 | `logger` | 模块常量 | `logging.getLogger(__name__)` |
| L47 | `router` | 模块常量 | `APIRouter()` |
| L48 | `urllib3.disable_warnings(...)` | 模块副作用 | 关闭 InsecureRequestWarning |
| L60 | `TorrentOperationRequest` | class（BaseModel） | 种子操作请求统一基类 |
| L68 | `torrent_list` | def（路由） | `POST /list` 同步下载器种子到 DB |
| L130 | `create_torrent` | async def（路由） | `POST /add` 单个添加（2026-09-05 起为 TorrentAddService HTTP 薄壳） |
| L172 | `create_torrents_batch` | async def（路由） | `POST /add-batch` 提交异步批量添加 |
| L582 | `get_torrent` | def（路由） | `GET /torrents/{info_id}/{downloader_id}/{downloader_name}` 按主键查 |
| L597 | `get_torrents` | def（路由） | `GET /getList` 通用条件查询（含 Tracker 主域名和错误单种全局唯一筛选） |
| L705 | `get_tracker_domains` | def（路由） | `GET /tracker-domains` 返回定时 Tracker 同步采集的主机域名列表 |

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

- **定位**：`torrent_crud.py:68`
- **职责**：查询所有启用的下载器（`dr=0, enabled=True, status="1"`），按类型调用 `qb_add_torrents` / `tr_add_torrents` 同步种子到 DB，返回成功/失败计数。
- **不变式**：异常分两层捕获（`SQLAlchemyError` L129 + 通用 `Exception` L132），均返回 `CommonResponse(code="500")` 而非抛出。

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

- **定位**：`torrent_crud.py:130`（2026-09-05 起薄壳，主体在服务层）
- **职责**：Form/UploadFile 解析 → 构造 `TorrentAddParams` + 读取字节 → `TorrentAddService(db, store).add_torrent(...)` → 映射 `TorrentAddResult` 为 CommonResponse。
- **关键调用链**（主体位于 [torrent_add_service](../../../services/README.md) `add_torrent`）：
  - 服务内 `store.get_snapshot()` → 缓存下载器（store 由端点注入 `getattr(request.app.state, "store", None)`）
  - `calculate_info_hash` / 双类型分支（TR `add_torrent`、qB `torrents_add` 经 `call_downloader_api` INTERACTIVE lane）/ 轮询 / 落库 / 异步审计——全部原样保留，status/code/msg 契约与抽取前逐字一致
- **不变式**：INV-1/2/3/4/5/6/7/8 全部适用（行为零变化，由 tests/api/test_torrent_crud_add_fallback.py 41 例守护）。

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

- **定位**：`torrent_crud.py:485`
- **职责**：校验下载器缓存（L508-521）后，将上传文件逐个 `stage_torrent_file` 暂存（失败时 `cleanup_staged_files` 回收），构建 `TorrentBatchAddOptions`（operator 从 `_user` 推导，L542-558），随后 `asyncio.create_task(process_torrent_batch_job(...))` 交后台处理（L562-567）并 `register_torrent_batch_task` 注册任务，立即返回 `202 accepted` + `task_id`（L573-578），完成结果经通知中心告知用户。
- **逐文件逻辑**：原内联的"每文件独立 try/except、200/500/207 汇总"处理已全部移至 `app/services/torrent_batch_add_service.py` 的 `process_torrent_batch_job`。
- **响应码**：无文件 `400`、下载器不在缓存 `404`、下载器失效 `503`、暂存/任务创建失败 `500`、提交成功 `202`。

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

- **定位**：`torrent_crud.py:582`
- **职责**：委托 `get_torrent_info(db, info_id, downloader_id)`（services 层）查询，未找到抛 `HTTPException(404)`。
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
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:597`
- **职责**：支持普通筛选、Tracker 主域名、活动快照、同内容/错误单种条件、排序与分页的通用查询，委托 `get_torrent_infos(...)`（torrent_helpers）。
- **活动种子特殊处理**（L641–657）：`active_only=True` 时读取 `get_active_keys_snapshot()`，若快照未就绪返回 `206`（partial）。
- **Tracker 主域名筛选**（L611–614、L680）：`tracker_domain` 接受逗号分隔多选，使用已同步的 TrackerInfo URL hostname/host 关系筛选；域名列表由 `/torrents/tracker-domains` 提供。✨2026-08-27（torrent_helpers.py）：EXISTS/ANY 语义保留（种子任一 tracker 命中即返回），入口统一归一 `requested_tracker_domains` 后由 SQL 8 条件（like 已 `escape="\\"` 字面量化，`_`/`%` 不再通配）与 Python 谓词 `tracker_row_matches_domains`（L53）同口径过滤，并在 VO 的 `tracker_info[].matched_domain` 上标记命中的域名（`convert_to_vo(s)_with_trackers` 新增 `requested_tracker_domains` 可选参数）；同批修复 `tracker_like` 子查询空结果由“静默返回全部”改为“返回空列表”。观察日志：`[tracker-domain-filter]`/`[tracker-filter]`/`[torrent-list]` 三组 debug 锚点，`LOG_LEVEL=DEBUG` 开启。
- **同内容筛选**（L624–627、L682）：`same_content_only=True` 委托共享查询按“名称 + 大小 + 至少两个不同规范化 Hash”过滤，并继续按种子行 `skip/limit` 分页。
- **错误单种筛选**（L628–631、L683）：`single_error_only=True` 只保留错误任务，并用不受当前 Tracker/状态筛选影响的全局名称+大小分组确认任务唯一；同一任务的多个 Tracker 服务不增加任务计数。
- **响应字段**：`total/list/pageSize`（分页固定字段，见 [API 响应格式约束](../../../../backend/docs/constraints/api-response-format.md)）。

#### `get_tracker_domains` — 已同步 Tracker 主域名

```python
@router.get("/tracker-domains")
def get_tracker_domains(
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:705`
- **职责**：读取 `TrackerInfo` 中仍有效的 `tracker_url/tracker_host`，复用 `extract_domains_from_trackers()` 提取 URL hostname，去重排序后返回 `CommonResponse.data`。
- **性能决策**：实际数据库中 30475 条 Tracker 记录提取 90 个域名，5 次查询+解析耗时 231.515–262.118ms，低于 1 秒，因此当前不做进程内持久化缓存。

---

## 调用关系图

```
torrent_crud.py
  │
  ├─→ app.api.responseVO.CommonResponse          (统一响应)
  ├─→ app.database.{get_db, AsyncSessionLocal}   (DB 会话)
  ├─→ app.auth.dependencies.require_authenticated_user  (认证)
  ├─→ app.downloader.models.BtDownloaders        (下载器 ORM)
  ├─→ app.torrents.models.{TorrentInfo, TrackerInfo} (种子/Tracker ORM)
  ├─→ app.torrents.audit_enums.{AuditOperationType, AuditOperationResult}
  │
  ├─→ app.api.endpoints.torrent_helpers          (横向复用)
  │     ├─ calculate_info_hash
  │     ├─ get_transmission_torrent_info
  │     ├─ create_qbittorrent_torrent_record
  │     ├─ create_transmission_torrent_record
  │     └─ get_torrent_infos
  ├─→ app.core.reannounce_config_operations.extract_domains_from_trackers (主机域名归一)
  ├─→ app.api.endpoints.torrent_speed.get_active_keys_snapshot  (活动种子快照)
  ├─→ app.api.endpoints.torrent_sync.{qb_add_torrents, tr_add_torrents}  (同步)
  │
  ├─→ app.services.downloader_api_runtime.{call_downloader_api, DownloadLane}  (下载器 API 线程池通道)
  ├─→ app.services.torrent_crud_service.get_torrent_info  (按主键查)
  ├─→ app.services.torrent_batch_add_service.{stage_torrent_file, process_torrent_batch_job}  (批添加暂存与后台处理)
  └─→ app.services.audit_service.{extract_audit_info_from_request, get_audit_service}  (审计)
```

## 反模式与技术债

- **代码重复**：`create_torrent`（L138-481）内部 Transmission/qBittorrent 两分支的文件读取（`read_file_data` L251 / `read_file_data_qb` L337）、添加、轮询、落库逻辑高度相似，违反 [代码复用约束](../../../../backend/docs/constraints/code-reuse.md)，建议抽取共享辅助函数；批添加路由重构后逐文件处理已收敛至 `torrent_batch_add_service.py`。
- **嵌套函数定义**：`write_temp_file`（L207）/ `read_file_data`（L251）/ `read_file_data_qb`（L337）仅在 `create_torrent` 内定义一次；批添加路由已无嵌套定义（改为 `stage_torrent_file` 暂存 + 后台任务）。
- **`get_torrent` 的 `downloader_name` 参数未使用**：仅作 URL 语义，未在函数体内引用。
- **审计日志 operator 硬编码 "admin"**：单添加仍在 L447 硬编码 `operator="admin"`（注释"当前API没有认证，使用默认操作人"）——实际已有 `require_authenticated_user`，应从 `_user` 取真实用户；批添加已改为从 `_user` 推导（`operator=str(operator or "admin")`，L542-558）。
