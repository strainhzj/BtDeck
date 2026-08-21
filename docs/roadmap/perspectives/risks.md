# risks — 风险与技术债

> 路线图视角发现的风险与技术债。已在他处论述的（如 lint 基线）只放索引链接。

## R1：孤儿文件（0 引用，建议清理或归档）

`app/core/` 目录混有真正的核心基础设施与若干**0 引用孤儿文件**，引用计数实测（`backend/app/` 范围内 `from app.core.<mod>` 的 .py 文件数）：

| 文件 | 行数 | 引用数 | 问题 |
|------|------|--------|------|
| [core/security.py](../../backend/app/core/security.py) | 263 | **0** | Tracker 解密模块（`TrackerDecryptionKeyManager`、`decrypt_tracker_info` 等）完全未接入。与 [auth/security.py](../../backend/app/auth/security.py) 和 [utils/encryption.py](../../backend/app/utils/encryption.py) 功能重叠，疑似旧实现残留 |
| [core/downloader.py](../../backend/app/core/downloader.py) | 29 | **0** | 自身 `from app.downloader import models` 指向不存在的包路径，已失效 |
| [core/torrent_operations.py](../../backend/app/core/torrent_operations.py) | 250 | **0** | ⚠ v1.0.6.27 内容已重写为 ratio/ratio_limit 工具（与 [services/torrent_ratio_values.py](../../backend/app/services/torrent_ratio_values.py) 功能重叠），但**生产路径未 import** —— 实际生效的是 services 版。存在"两份 ratio 规范化逻辑"风险（见 R10） |
| [core/tracker_operations.py](../../backend/app/core/tracker_operations.py) | 292 | **0** | DatabaseResult 重构产物，被 services 层取代 |
| [core/init_schema_from_production.py](../../backend/app/core/init_schema_from_production.py) | 146 | **0** | 文件头自述"已下线"，`main.py` 不再调用 |

详见 [../backend/core/README.md](../backend/core/README.md) "孤儿/低使用文件清单"。

## R2：入口分散（三处对启动有发言权）

| 入口 | 角色 | 位置 |
|------|------|------|
| `app/main.py` | uvicorn server 配置；仅 `__main__` 直跑路径在 L145 初始化配置、L159 提前迁移 | [main.py](../../backend/app/main.py) |
| `app/factory.py` | app 工厂（CORS/异常/路由/SPA fallback/lifespan） | [factory.py:84-117](../../backend/app/factory.py) |
| `btdeck_startup.sh` | Docker 入口，校验单 worker 后在 L102 执行 uvicorn | [btdeck_startup.sh](../../backend/btdeck_startup.sh) |

**风险**：Docker 的 `uvicorn app.main:app` 不进入 `main.py.__main__`，配置、迁移、seed 由 `lifespan` L285/L302/L318 负责；直接运行与桌面入口会在启动 server 前提前迁移，随后 lifespan 再做幂等校验。入口语义仍分散，任一路径都必须保持“迁移失败不进入 seed/对账/调度器”的 fail-fast 不变量。

## R3：双 SPA fallback（部署模式分叉）

| 模式 | SPA fallback 机制 | 位置 |
|------|------------------|------|
| Docker | nginx `try_files $uri $uri/ /index.html` | [frontend/nginx.conf:123](../../frontend/nginx.conf) |
| PyInstaller 单机 | `factory.py:_mount_frontend_static` | [factory.py:37-60](../../backend/app/factory.py) |

**风险**：两种模式的前端静态文件服务完全独立，修改一处容易忘记另一处。详见 [../deploy/README.md](../deploy/README.md)。

## R4：文档/代码漂移（前端组件范式）

**声明**（[AGENTS.md](../../AGENTS.md) 第 5 条、[frontend/CLAUDE.md](../../frontend/CLAUDE.md)）：前端"必须使用 Options API，禁止 Composition API 和 `<script setup>`"

**实际**（grep 实测）：

| 范式 | 数量 | 占比（.vue 口径） |
|------|------|------|
| class-component（`export default class` + `@Component`） | **81**（src 全口径，含 2 个 .ts mixin） | 79/82 ≈ 96.3% |
| Options API（`export default {`） | **3** | 3/82 ≈ 3.7% |

3 个 Options API 文件：
- [views/recycle-bin/index.vue:369](../../frontend/src/views/recycle-bin/index.vue)
- [views/tracker/reannounce-config.vue:299](../../frontend/src/views/tracker/reannounce-config.vue)
- [components/torrents/CompactTable.vue:301](../../frontend/src/components/torrents/CompactTable.vue)

**差距**：约束文档的措辞（"Options API"）与实际主流范式（class-component，基于 `vue-class-component` + `vue-property-decorator`）不一致。class-component 是第三种范式，既非 Composition API 也非传统 Options API。

**建议**：要么更新约束文档明确允许 class-component，要么启动范式统一（将 81 个 class-component 转为 Options API，工作量巨大）。

## R5：迁移双轨（应用层 vs schema）

| 迁移类型 | 位置 | 职责 |
|---------|------|------|
| 应用层数据/字段迁移 | [app/migrations/database_migrator.py](../../backend/app/migrations/database_migrator.py)（764 行） | 运行时执行，含 SM4 加密字段升级 |
| Schema 版本迁移 | [backend/alembic/](../../backend/alembic/)（**9 个** revision；v1.0.6.25/27 新增 `6132b66d14a7_ratio_columns_to_float`、`8f4c2d1a9b7e_ratio_value_constraints`） | 版本管理 |

**风险**：两套迁移并存，边界不清（何时用哪个）。v1.0.6.25~27 的 ratio 列治本迁移（String→Float + CHECK 约束）走的是 alembic schema 通道，配套的数据清洗/诊断在 `app/core/ratio_data_diagnostics.py` + `scripts/ratio_migration_report.py`，三层（schema 迁移 / 运行时数据清洗 / 诊断报告）边界需注意。完整论述见 [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md) "二、数据库迁移双轨"与 [../../backend/docs/operations/rollback-guide.md](../../backend/docs/operations/rollback-guide.md)。

## R6：代码重复（违反复用约束）

| 位置 | 重复内容 | 相似度 |
|------|---------|--------|
| [torrent_crud.py](../../backend/app/api/endpoints/torrent_crud.py) `create_torrent`（L122-436）vs `create_torrents_batch`（L440-718） | Transmission/qBittorrent 添加分支（临时文件/读文件/轮询/落库）几乎完全重复 | >70% |
| 同文件内 `write_temp_file`（L187/L514）、`read_file_data`（L231/L543） | 嵌套函数在两个路由内各定义一次 | 高 |

**违反**：[../../backend/docs/constraints/code-reuse.md](../../backend/docs/constraints/code-reuse.md)（相似度 >50% 必须扩展）。

## R7：枚举/类型重复定义

| 重复项 | 位置 |
|--------|------|
| `SpeedUnitEnum` | [models/downloader_settings.py](../../backend/app/models/downloader_settings.py) 与 [models/enums.py](../../backend/app/models/enums.py) |
| 下载器类型常量（0=qB/1=Trans） | 前端 [utils/downloaderType.ts](../../frontend/src/utils/downloaderType.ts) 与后端多处硬编码（`torrent_crud.py:221` 注释） |

## R8：审计日志 operator 硬编码

[torrent_crud.py:402](../../backend/app/api/endpoints/torrent_crud.py) 与 L655：`operator="admin"` 硬编码，注释"当前API没有认证，使用默认操作人"——但实际路由已有 `Depends(require_authenticated_user)`，应从 `_user` 取真实用户。审计准确性受损。

## R9：构建产物入库

`deploy/dist/btdeck.exe`、`deploy/build/`、根目录 `btdeck-backend.latest.tar`、`btdeck-frontend.latest.tar` 已提交到仓库（体积数百 MB），可能是误提交。建议加入 `.gitignore`。

## R10：ratio 规范化逻辑双份（v1.0.6.27 引入）

| 位置 | 状态 | 说明 |
|------|------|------|
| [services/torrent_ratio_values.py](../../backend/app/services/torrent_ratio_values.py)（150 行） | ✅ **生产生效** | 被 `api/endpoints/{torrent_helpers,torrent_sync,torrents_async}.py` + `services/torrent_crud_service.py` 引用 |
| [core/torrent_operations.py](../../backend/app/core/torrent_operations.py)（250 行） | ⚠️ **0 引用孤儿**（内容已重写为 ratio 工具） | v1.0.6.27 重写但未接线 |

**风险**：两份 ratio/ratio_limit 规范化逻辑并存，未来修改易只改其一导致行为分叉。**建议**：删除 `core/torrent_operations.py`，或将其逻辑并入 `services/torrent_ratio_values.py` 后归档。详见 R1 与 [../backend/core/README.md](../backend/core/README.md)。

> 注：v1.0.6.27 的 `app/contracts/` 是"单一真相"的正向实践（advanced_search 操作符契约收敛为一份 JSON），可作为 ratio 逻辑收敛的参照模式。

---

## 相关文档

- Lint 基线与代码风格技术债 → [../../backend/docs/tech-debt-lint-baseline.md](../../backend/docs/tech-debt-lint-baseline.md)
- 风格与契约审计 → [../../backend/docs/style-and-contract-audit.md](../../backend/docs/style-and-contract-audit.md)
- Panic 修复分析 → [../../backend/docs/code_review_panic_analysis.md](../../backend/docs/code_review_panic_analysis.md)
