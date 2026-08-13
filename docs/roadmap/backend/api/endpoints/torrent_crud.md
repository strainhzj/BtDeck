# torrent_crud.py — 种子 CRUD 端点

> 本文件是路线图第三层样例，演示后端 Python 四节模板的产出形态。

---

## 一、文件元信息

| 项目 | 值 |
|------|-----|
| 源路径 | `backend/app/api/endpoints/torrent_crud.py` |
| 行数 | 648（实测 PowerShell `Get-Content`） |
| 模块职责 | 种子 CRUD 端点：列表同步、单个/批量添加、按主键查询、通用条件查询 |
| 路由前缀 | 由 `torrents.py` 聚合后挂到 `/torrents`（最终 `/api/v1/torrents/*`） |
| 顶层符号 | 1 class（`TorrentOperationRequest`）+ 5 路由函数 |

---

## 二、关键不变式

阅读本模块前必须知道的约束（全部来自源码注释与代码证据）：

### INV-1：下载器连接必须走 `app.state.store` 缓存（强制规范）

源码证据：`create_torrent` L143-181、`create_torrents_batch` L470-499

```python
# L143-145: 从 app.state.store 获取缓存的下载器（强制规范）
app = request.app
if not hasattr(app.state, "store"): ...
# L155: 使用异步版本 get_snapshot() 避免线程问题
cached_downloaders = await app.state.store.get_snapshot()
```

> 严禁 `db.query(BtDownloaders)` 后重复创建客户端连接。详见 [约束](../../../../backend/docs/constraints/downloader-connection.md)。

### INV-2：下载器类型判断用 `downloader_type` 字段（0=qBittorrent, 1=Transmission）

源码证据：L221 `if downloader.downloader_type == 1:  # Transmission`、L302 `if downloader.downloader_type == 0:  # qBittorrent`

### INV-3：临时文件写入必须 `flush + fsync + close` 后返回路径

源码证据：`write_temp_file` L187-203（内嵌函数）

```python
tmp_file.flush()       # L192 确保数据写入磁盘
os.fsync(tmp_file.fileno())  # L193 强制同步
tmp_file.close()       # L194
```

文件 I/O 通过 `asyncio.to_thread` 放入线程池执行（L205），避免阻塞事件循环。

### INV-4：添加种子后轮询验证（最多 30 秒）

源码证据：L247-257（Transmission）、L330-341（qBittorrent）

```python
max_retries = 30
while tr_torrent is None and retry_count < max_retries:
    await asyncio.sleep(1)
    tr_torrent = await get_transmission_torrent_info(tr_client, info_hash)
```

### INV-5：DB 查询必须返回完整实体（不能只 select info_id）

源码证据：L260-269、L346-355、L564-574、L621-631（4 处重复注释）

```python
# ⚠️ 必须查询完整实体而非仅 info_id 列：审计日志构造时会访问 .name/.hash/.size，
# 若只 select info_id 返回 Row 对象，访问未选中列会触发 AttributeError("name")
# （SQLAlchemy 2.0 Row.__getattr__ 行为）
```

### INV-6：异常兜底必须覆盖整个分支（含 ORM 写入）

源码证据：L285-299（Transmission 兜底）、L370-392（qBittorrent 兜底）

> `prod-hotfix-2026-07-19` 修复：早期 try 块只覆盖 `torrents_add/torrents_info` 轮询，把 `create_qbittorrent_torrent_record + db.commit()` 留在 try 之外，导致 `TypeError("Object of type ValueError is not JSON serializable")` 冒泡到全局 500。本修复把整个分支纳入 try，与 batch add 端点结构对齐。

### INV-7：审计日志异步写入，失败不影响主业务

源码证据：`write_audit_log_async` L395-426

```python
asyncio.create_task(write_audit_log_async())  # L426 后台执行
# 审计日志失败不影响主业务（L420-422 catch all）
```

> ⚠ 注释警告：异步任务异常会被静默忽略（L425）。

### INV-8：所有路由统一认证 + 统一响应

- 认证：`_user=Depends(require_authenticated_user)`（4 个路由均有）
- 响应：`response_model=CommonResponse`（除 `get_torrents` 外）

---

## 三、类与函数索引（按源码出现顺序）

| 行号 | 符号 | 类型 | 说明 |
|------|------|------|------|
| L36 | `logger` | 模块常量 | `logging.getLogger(__name__)` |
| L37 | `router` | 模块常量 | `APIRouter()` |
| L38 | `urllib3.disable_warnings(...)` | 模块副作用 | 关闭 InsecureRequestWarning |
| L59 | `TorrentOperationRequest` | class（BaseModel） | 种子操作请求统一基类 |
| L67 | `torrent_list` | def（路由） | `POST /list` 同步下载器种子到 DB |
| L137 | `create_torrent` | async def（路由） | `POST /add` 单个添加 |
| L206 | `write_temp_file` | def（嵌套） | 安全写入临时文件（内嵌于 create_torrent） |
| L250 | `read_file_data` | def（嵌套） | 读文件到 bytes（Transmission 分支） |
| L336 | `read_file_data_qb` | def（嵌套） | 读文件到 bytes（qBittorrent 分支） |
| L439 | `write_audit_log_async` | async def（嵌套） | 异步审计日志写入 |
| L484 | `create_torrents_batch` | async def（路由） | `POST /add-batch` 提交异步批量添加 |
| L581 | `get_torrent` | def（路由） | `GET /torrents/{info_id}/{downloader_id}/{downloader_name}` 按主键查 |
| L596 | `get_torrents` | def（路由） | `GET /getList` 通用条件查询（含同内容列表筛选） |

> 嵌套函数（write_temp_file / read_file_data / write_audit_log）不计入"顶层符号"，但按提示词要求收录在索引中以便定位。

---

## 四、方法签名详情

### 路由处理函数

#### `torrent_list` — 同步下载器种子到 DB

```python
@router.post("/list", response_model=CommonResponse)
def torrent_list(
    _user=Depends(require_authenticated_user),
    request: Request = None,
    name: str = Query(default="default", alias="name", description="种子名称"),
    db: Session = Depends(get_db),
) -> CommonResponse:
```

- **定位**：`torrent_crud.py:52`
- **职责**：查询所有启用的下载器（`dr=0, enabled=True, status="1"`），按类型调用 `qb_add_torrents` / `tr_add_torrents` 同步种子到 DB，返回成功/失败计数。
- **不变式**：异常分两层捕获（`SQLAlchemyError` L113 + 通用 `Exception` L116），均返回 `CommonResponse(code="500")` 而非抛出。

#### `create_torrent` — 单个添加种子

```python
@router.post("/add", response_model=CommonResponse)
async def create_torrent(
    _user=Depends(require_authenticated_user),
    request: Request = None,
    downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
    save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
    tags: Optional[str | None] = Form("", description="标签"),
    category: Optional[str | None] = Form("", description="分类"),
    paused: Optional[bool] = Form(False, description="是否暂停"),
    skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验"),
    is_sequential_download: Optional[bool | None] = Form(False, description="是否按顺序下载"),
    is_first_last_piece_priority: Optional[bool | None] = Form(False, description="是否先下载首尾文件块"),
    upload_limit: Optional[str | int | None] = Form(False, description="上传速度 bytes/second"),
    download_limit: Optional[str | int | None] = Form(False, description="下载速度 bytes/second"),
    torrent_file: Optional[UploadFile] = File(description="种子文件"),
    db: Session = Depends(get_db),
) -> CommonResponse:
```

- **定位**：`torrent_crud.py:122`
- **职责**：从缓存获取下载器 → 写临时文件 → 计算 info_hash → 按下载器类型调用 SDK 添加 → 轮询验证 → 写 DB → 异步审计日志。
- **关键调用链**：
  - L155 `app.state.store.get_snapshot()` → 缓存下载器
  - L209 `calculate_info_hash(tmp_file_path)` → [torrent_helpers](./torrent_helpers.md 待建)
  - L221/L302 分支：Transmission（`tr_client.add_torrent` L239）/ qBittorrent（`qb_client.torrents_add` L315）
  - L251/L334 轮询：`get_transmission_torrent_info` / `qb_client.torrents_info`
  - L273/L359 落库：`create_transmission_torrent_record` / `create_qbittorrent_torrent_record`
  - L426 审计：`asyncio.create_task(write_audit_log_async())`
- **不变式**：INV-1/2/3/4/5/6/7/8 全部适用。

#### `create_torrents_batch` — 批量添加种子

```python
@router.post("/add-batch", response_model=CommonResponse)
async def create_torrents_batch(
    _user=Depends(require_authenticated_user),
    request: Request = None,
    torrent_files: List[UploadFile] = File(..., description="种子文件列表（最多10个）"),
    downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
    save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
    tags: Optional[str | None] = Form("", description="标签"),
    category: Optional[str | None] = Form("", description="分类"),
    paused: Optional[bool] = Form(False, description="是否暂停"),
    skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验"),
    is_sequential_download: Optional[bool | None] = Form(False, description="是否按顺序下载"),
    is_first_last_piece_priority: Optional[bool | None] = Form(False, description="是否先下载首尾文件块"),
    upload_limit: Optional[str | int | None] = Form(False, description="上传速度 bytes/second"),
    download_limit: Optional[str | int | None] = Form(False, description="下载速度 bytes/second"),
    db: Session = Depends(get_db),
) -> CommonResponse:
```

- **定位**：`torrent_crud.py:440`
- **职责**：批量处理最多 10 个种子文件，逐个走与 `create_torrent` 相同的流程，返回 `total/success_count/failed_count/results`。
- **响应码**：全成功 `200`、全失败 `500`、部分成功 `207`（Multi-Status，L711）。
- **与单添加的差异**：每个文件独立 try/except（L510/L678），单文件失败不影响其他文件；审计日志在成功分支内异步写入（L676）。

#### `get_torrent` — 按复合主键查询

```python
@router.get("/torrents/{info_id}/{downloader_id}/{downloader_name}", response_model=CommonResponse)
def get_torrent(
    info_id: str,
    downloader_id: str,
    downloader_name: str,
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CommonResponse:
```

- **定位**：`torrent_crud.py:722`
- **职责**：委托 `get_torrent_info(db, info_id, downloader_id)`（services 层）查询，未找到抛 `HTTPException(404)`。
- **注意**：`downloader_name` 是路径参数但**未在函数体内使用**（仅用于前端 URL 语义）。

#### `get_torrents` — 通用条件查询

```python
@router.get("/getList")
def get_torrents(
    downloader_id: Optional[str] = Query(None, description="所属下载器主键（支持多选，逗号分隔）"),
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
    status: Optional[str] = Query(None, description="种子状态筛选(支持多选，逗号分隔)"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100000, description="限制记录数"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
    active_only: bool = Query(False, description="仅显示活动种子"),
    same_content_only: bool = Query(False, description="仅显示同名同大小且不同 InfoHash 的种子"),
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
```

- **定位**：`torrent_crud.py:596`
- **职责**：支持普通筛选、活动快照、同内容条件、排序与分页的通用查询，委托 `get_torrent_infos(...)`（torrent_helpers）。
- **活动种子特殊处理**（L633–654）：`active_only=True` 时读取 `get_active_keys_snapshot()`，若快照未就绪返回 `206`（partial）。
- **同内容筛选**（L621–624、L674）：`same_content_only=True` 委托共享查询按“名称 + 大小 + 至少两个不同规范化 Hash”过滤，并继续按种子行 `skip/limit` 分页。
- **响应字段**：`total/list/pageSize`（分页固定字段，见 [API 响应格式约束](../../../../backend/docs/constraints/api-response-format.md)）。

---

## 调用关系图

```
torrent_crud.py
  │
  ├─→ app.api.responseVO.CommonResponse          (统一响应)
  ├─→ app.database.{get_db, AsyncSessionLocal}   (DB 会话)
  ├─→ app.auth.dependencies.require_authenticated_user  (认证)
  ├─→ app.downloader.models.BtDownloaders        (下载器 ORM)
  ├─→ app.torrents.models.TorrentInfo            (种子 ORM)
  ├─→ app.torrents.audit_enums.{AuditOperationType, AuditOperationResult}
  │
  ├─→ app.api.endpoints.torrent_helpers          (横向复用)
  │     ├─ calculate_info_hash
  │     ├─ get_transmission_torrent_info
  │     ├─ create_qbittorrent_torrent_record
  │     ├─ create_transmission_torrent_record
  │     └─ get_torrent_infos
  ├─→ app.api.endpoints.torrent_speed.get_active_keys_snapshot  (活动种子快照)
  ├─→ app.api.endpoints.torrent_sync.{qb_add_torrents, tr_add_torrents}  (同步)
  │
  ├─→ app.services.torrent_crud_service.get_torrent_info  (按主键查)
  └─→ app.services.audit_service.{extract_audit_info_from_request, get_audit_service}  (审计)
```

## 反模式与技术债

- **代码重复**：`create_torrent`（L122-436）与 `create_torrents_batch`（L440-718）的 Transmission/qBittorrent 分支逻辑高度重复（write_temp_file / read_file_data / 轮询 / 落库），相似度 >70%，违反 [代码复用约束](../../../../backend/docs/constraints/code-reuse.md)，建议抽取共享辅助函数。
- **嵌套函数重复定义**：`write_temp_file` / `read_file_data` 在两处路由内各定义一次（L187/L514、L231/L543）。
- **`get_torrent` 的 `downloader_name` 参数未使用**：仅作 URL 语义，未在函数体内引用。
- **审计日志 operator 硬编码 "admin"**：L402、L655 注释"当前API没有认证，使用默认操作人"——实际已有 `require_authenticated_user`，应从 `_user` 取真实用户。
