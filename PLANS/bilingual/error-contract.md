# 错误契约清单（P0）

> 生成：2026-09-18；**2026-09-21 P4 批回填落地状态**（§3 样例覆盖情况见各行 ✅ 标记与 §5 汇总）。目标：为 P4（`desktop-bilingual-20260918.p4`）提供 M1 核心失败路径的 reasonCode 提案与参数化翻译依据。
> 原则（摘自主计划 §3.3）：信封/分页/202/206/207/认证语义不变；前端禁止按中文字符串匹配翻译；未知错误给本地化兜底说明，原始详情遵守脱敏。

## 1. 现有架构（实测）

- 全局处理器 `app/exception_handlers.py`：
  - `HTTPException` 归一化为 CommonResponse；默认中文 msg 按 HTTP 码分派：`请求错误` / `认证失败`(401) / `无权限`(403) / `资源不存在`(404) / `服务器内部错误`(≥500)。
  - `PlatformCapabilityUnsupportedError` → 403 + `data.reasonCode=PLATFORM_CAPABILITY_UNSUPPORTED`（**reasonCode 先例**，含 capability/platform/operation/retryable）。
  - 422：保持 `data.errors=[{loc,msg,type,...}]` 数组语义，`msg` 取首条（pydantic 英文原文），前端按 `type/loc` 分类展示。
  - 500：生产不带堆栈；DEBUG 才附 `exception_type/message/traceback`（`data.error` 为兼容别名）。
- 端点层大量 `CommonResponse(status=..., msg=中文, code=...)`，msg 为用户可见文案主通道（downloader.py 47 处、torrent_crud.py 22 处等）。
- 历史 status 语义不一：如「该下载器已被删除或不存在」在 downloader.py:67 为 `status="success", code="200"`、:565 为 `status="error", code="404"`——列入 E02 兼容测试，不顺带改协议。
- 前端链路：`utils/request.ts`（401 静默续期 + 重放一次 + 三态分流 + 3 秒防抖登出；登录请求豁免）→ `utils/error-normalize.ts`（ApiError，`pickErrorPayload` 只读 body.msg）→ 组件 toast/确认框。

## 2. reasonCode 既有使用面

`grep reasonCode/reason_code` 命中：`exception_handlers.py`、`api/endpoints/cron_tasks.py`（capability 透传）、`api/endpoints/health.py`、`desktop_companion/health.py`、`tasks/cleanup_executor.py`、`tasks/task_capabilities.py`。业务错误（登录/下载器/删除）尚无 reasonCode——P4 的主要增量。

## 3. M1 核心失败路径样例（提案）

| # | 触发场景 | 现响应（实测） | 提案 reasonCode | 提案参数 | 英文显示策略 |
|---|---|---|---|---|---|
| E1 | 登录限流 | 429 `尝试次数过多，请稍后再试` | `AUTH_RATE_LIMITED` | retryAfter? | `Too many attempts. Try again later.` |
| E2 | 登录凭证错 | 401 `用户名或密码错误` | `AUTH_INVALID_CREDENTIALS` | — | `Incorrect username or password.` |
| E3 | 2FA 缺码 | 400 `请填写两步验证码` | `AUTH_TOTP_REQUIRED` | — | `Enter your two-factor code.` |
| E4 | 2FA 错码 | 401 `验证码错误，请重试` | `AUTH_TOTP_INVALID` | — | `Invalid verification code.` |
| E5 | 刷新令牌失效 | 401 `refresh token 无效、已撤销或已过期` | `AUTH_REFRESH_INVALID` | — | 静默登出 + `Session expired, sign in again.` |
| E6 | 登录未捕获异常 | 500 `系统异常: {str(e)}` ⚠️动态拼接 | `AUTH_INTERNAL_ERROR` | — | 固定文案；`str(e)` 只进日志不进 msg（脱敏） |
| E7 | 下载器认证失败（添加/测试） | 400 `用户名或密码错误` | `DOWNLOADER_AUTH_FAILED` | downloaderType | `Username or password rejected by {type}.` |
| E8 | 下载器不存在 | 404（一处 200+success ⚠️） | `DOWNLOADER_NOT_FOUND` | downloaderId | `Downloader no longer exists.` |
| E9 | 修改凭据缺原密码 | 400 `修改用户名或密码时必须提供原密码` | `DOWNLOADER_ORIG_PASSWORD_REQUIRED` | — | 按字段提示 |
| E10 | 原密码错 / 验证失败 | 400 `原密码错误`；500 `验证原密码失败`/`无法验证原密码` | `DOWNLOADER_ORIG_PASSWORD_INVALID` / `DOWNLOADER_ORIG_PASSWORD_UNVERIFIED` | — | 后者提示可重试（瞬时） |
| E11 | 缓存未初始化 | 200+`缓存服务未初始化`（getList 空列表）⚠️成功信封携带错误语义 | `DOWNLOADER_CACHE_UNAVAILABLE` ✅P4 批定稿：**双形态冻结**（ getList 空列表保留 success+200+data=[] 历史形状不改协议，B03；测试 test_reason_contract_p4 钉住；写路径 500 错误码形态已带 reasonCode） | — | fail-closed 提示「服务暂不可用」；写路径按 reasonCode 分流而非 msg |
| E12 | 下载器离线 | 200 `下载器离线`（列表查询路径） | `DOWNLOADER_OFFLINE` | downloaderId | 非错误提示，状态语义，进卡片徽标文案 |
| E13 | 删除时缓存/连接缺失 | 500 `下载器缓存未初始化` / `下载器客户端连接不存在` | `DOWNLOADER_CACHE_UNAVAILABLE` / `DOWNLOADER_CONNECTION_MISSING` | — | 「连接不可用，请稍后重试」，不误导为密码错误（D02） |
| E14 | 批量删除已提交【留 P5：与 R01-R05 危险操作审校同批】 | 200 `批量删除任务已提交，正在后台执行`；`所选种子均已在删除任务中处理` | `TORRENT_DELETE_ACCEPTED` / `TORRENT_DELETE_ALREADY_PROCESSED` | counts | **202 语义：不报「已完成」**（R05）；部分失败计数进参数 |
| E15 | 删除后端异常 | 500 `服务器内部错误`/`系统内部错误`/`数据库操作失败` | `INTERNAL_ERROR` / `DB_OPERATION_FAILED` ✅P4 批（torrent sync/通用键已落；删除链路本体随 P5） | — | 固定兜底 + 「稍后重试」 |
| E16 | 回收站功能未开放【留 P5】 | 501 `功能开发中，请稍后再试` | `NOT_IMPLEMENTED` | feature | 明示未开放而非失败 |
| E17 | 字段校验（422） | `data.errors[].{loc,type,msg}`（msg 英文 pydantic 原文） | 前端按 `type` 映射本地文案 ✅P4 批（errors.validation 10 键 + apiErrorMessage 422 分支） | field/loc | 不逐条翻译 pydantic msg；按 type 字典化 |
| E18 | 平台能力拒绝 | 403 `PLATFORM_CAPABILITY_UNSUPPORTED`（已有） | 复用 ✅既有 | capability/operation | 前端已有能力门控文案，核对不重复提示 |
| E19 | 网络错误（前端本地） | axios 层 `网络错误`（errors 组 14 处高频） | 前端本地键 `errors.network` ✅P2 批已落 | — | 不依赖后端 |

> 表格为「样例+提案」，P4 落地时逐接口补全 M1 全集（预计 40～60 条 reasonCode），并补 pytest 兼容断言（信封不变、data 形状不变、仅新增字段）。

## 3.1 P4 批落地汇总（2026-09-21，M1 剩余子范围）

- **已落地契约码（累计）**：P2 批 25 键（AUTH_*5/USER_*3/2FA_*9/DOWNLOADER_*7）+ P4 批 33 键 = `errors.byCode` 共 58 键（zh/en 成对，parity 门禁覆盖）。P4 批分布：种子操作 8（TORRENT_HASHES_REQUIRED/RECORDS_NOT_FOUND/OPERATION_FAILED/OPERATION_INTERNAL/FILE_REQUIRED/FILE_INVALID/INFO_TIMEOUT/INFO_UNAVAILABLE）、添加链路 4（TORRENT_ADD_FAILED/FILES_REQUIRED/STAGE_FAILED/BATCH_SUBMIT_FAILED）、同步 2（TORRENT_SYNC_FAILED/DB_OPERATION_FAILED）、下载器 4（CACHE_UNAVAILABLE/OFFLINE/CONNECTION_MISSING/NO_TORRENTS）、Tracker 3（URL_REQUIRED/NOT_FOUND/OPERATION_INTERNAL）、查询模板 9（NOT_FOUND/FORBIDDEN/INVALID_CONDITIONS + CREATE/LIST/UPDATE/DELETE/APPLY_FAILED）、通用 1（INTERNAL_ERROR）。
- **动态 msg 收敛**：outer `操作异常：{error_detail}`（6 处）、添加兜底 `添加种子失败: {type}: {e}`（2 处）、暂存/后台任务提交 `{str(exc)}`（2 处）、模板 CRUD 500 `{str(e)}`（6 处）→ 固定文案 + logger；**保留**：inner 操作失败 msg（含异常类名，测试钉住语义）与受控 RPC 错误文本（TransmissionError/APIError/calculate_info_hash）。
- **E14/E16 删除链路**：留 P5（与 R01-R05 危险操作英文审校同批收口），本批不动删除链路。
- **pytest 契约锚**：`tests/api/test_reason_contract_p4.py` 30 例（含 E02 双形态钉住、E17 data.errors 形态、E03 事件键）；`tests/api/test_reason_contract_p2.py` 11 例（P2 批）。

## 4. 已识别的坑（P4 必读）

1. **动态拼接 msg 不可翻译**：`f"系统异常: {str(e)}"`（login.py 等）——reasonCode 化时原始异常只进日志，msg 固定；避免把 `str(e)` 暴露给用户（信息泄露面）。
2. **成功信封携带失败语义**（E8/E11）：历史分支不改协议，前端归一化层加 reasonCode 分支，兼容测试钉住两形态。
3. **401 三态**：断言「 definite failure」仅 `code==='401'`；翻译不得触碰 request.ts 分流逻辑，只改登出/失败提示文案键。
4. **422 首条 msg 已透传英文 pydantic 原文**：中文用户当前也看到英文校验消息——本地化后中文界面反而改善；按 `type/loc` 字典化是双向收益，P4 与双语同批实施。
5. **能力受限 vs 错误**：`requiredCapability` 路由（回收站/孤儿文件/文件管理）被拒时走 PLATFORM_CAPABILITY_UNSUPPORTED 或路由门控隐藏——英文提示复用既有门控文案，不新造错误。
