# Session Handoff - BtDeck 全栈项目

## 2026-07-04 交接：sync-resource-governance 全部完成

**当前任务**: `sync-resource-governance`
**状态**: 阶段 0/1/2/2.5/3 全部完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮完成（阶段 3 验证与证据归档）

- 新增架构约束测试（ast 扫描请求探针模块不碰治理锁）
- 新增 3 个行为契约测试（heavy_sync/db_write_scope 持有时查询不阻塞）
- 新增可重复压测脚本 `backend/scripts/sync_resource_benchmark.py`（6 场景）
- 跑一轮 mock 压测：所有场景 P50/P95<1ms、P99≤16ms、max 16ms，证明请求侧未被治理锁阻塞
- 全量 1909 passed diff 基线为零

### 已完成阶段总览

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0+1 | TaskAdmissionController（heavy_sync 背压 + 同类去重） | ✅ |
| 2 | DownloaderApiRuntime（三 lane 隔离 + per-downloader 限流 + qB tracker 并发治理） | ✅ |
| 2.5 | DB 写入治理（变更检测 + 批量 upsert + db_write_scope 串行化） | ✅ |
| 3 | 验证与证据归档（架构约束 + 行为契约 + 压测脚本） | ✅ |

### 已知技术债（留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 真实生产环境的压测（含真实多下载器 + 真实 qB/TR 实例 + 真实种子规模）需运维用 sync_resource_benchmark.py 跑。

### 快速恢复

```bash
cd backend
# 跑本轮新测试
python -m pytest tests/test_architecture_constraints.py::test_request_side_endpoints_do_not_use_governance_locks tests/api/test_sync_governance_integration.py -v
# 跑压测脚本（6 场景）
python scripts/sync_resource_benchmark.py --iterations 30
# 全量回归（diff 基线：16 个 tag_aggregation failure 是预先存在的）
python -m pytest tests/ -q
```

### 下一步可选方向

sync-resource-governance 任务已完成。剩余可选方向：
1. **P3 已知技术债**：全量同步 + API 触发路径接入 db_write_scope
2. **真实环境压测**：运维在 staging/生产用 sync_resource_benchmark.py 跑，对比部署前后
3. **DBWriteQueue**（后续独立版本）：当前任务完成后若仍显示 DB 写锁等待，作为独立版本重新设计
4. 切换到其它任务

---

## 2026-07-04 交接：sync-resource-governance 阶段 2.5 完成

**当前任务**: `sync-resource-governance`  
**状态**: planned，已完成 harness 立项与详细计划设计，尚未开始代码实现。  
**计划文件**: `PLANS/sync-resource-governance.md`  
**执行顺序**: 方案二（调度器/资源背压） -> 方案三（下载器 API 调用隔离与调度层）。

**下一步入口**:
1. 阅读 `PLANS/sync-resource-governance.md`。
2. 进入实现前先请用户确认待决策项。
3. 优先实现阶段 0 基线观测，然后实现阶段 1 `TaskAdmissionController` 与任务 profile。
4. 阶段 1 验证稳定后，再推进阶段 2 `downloader_api_runtime` 与 qB tracker 并发治理。

**已确认决策**:
- 重型 cron 任务采用同类去重：按 `task_code` 检查运行中和排队中任务，已有同类任务则跳过本轮。
- `downloader_io` 默认并发为 2。
- qB tracker 明细查询默认并发为 3。
- 允许新增配置项，包括并发、队列限制、下载器 API timeout、DB 批量提交和磁盘写入节流相关配置。
- 必须纳入硬盘写入频率治理，避免逐条写库、逐条日志落盘、高频 commit/flush。
- 暂不实现 `DBWriteQueue`；它只作为后续独立版本候选保留在 harness 中，当前任务不得把它作为完成前置条件。

**关键分析提醒**:
- 不要把 tracker 富集误归因到 `qb_add_torrents_info_only_async`；该路径当前不调用 `_enrich_qb_torrents_with_trackers`。
- 重点关注不同重型后台任务之间的全局资源争用，以及 qB tracker-only/full-sync 路径中的批量下载器 API 调用。

> 用途：会话交接模板，确保上下文不丢失。复制本模板，填写当前状态。

---

## 会话信息

**日期**: 2026-06-28
**版本**: v1.0.5（查询模板系统）+ 后端回归测试补全专项
**功能**: 为"纯 DB 操作、业务逻辑零测试覆盖"的接口补充 API 级回归测试，每个接口经"子代理审查 → 实证核实 → 修订 → 反向验证"闭环
**状态**: 交接文档 3 个优先级全部完成。14 个 commit，+135 个回归测试，全量 tests/api/ 462 passed 无回归。
**分支**: dev（已与 origin/dev 同步）

---

## 完成的工作（14 commit，本会话全部）

| 任务 | commit | 测试数 |
|------|--------|--------|
| 审计日志查询接口初始（query/statistics/operation-types） | 545fad4 | 34 |
| 审计日志 review 修订（排序完整序列/count解耦/msg排除/401 body/枚举集合/LIKE通配符） | 8197567 | →41 |
| 仪表盘统计接口初始（裸SQL聚合+内存缓存） | 39e4b97 | +21 |
| 仪表盘 review 修订（修60秒窗口flaky+dr身份锁+msg排除+unknown桶） | 1485986 | →23 |
| 仪表盘第二轮 review（set→dict计数/C11+M3漏点+B9 docstring） | 399b68b | 23 |
| 仪表盘第三轮 review（补 keyword_rule 归一化路径） | 1c05d16 | 23 |
| 提取 make_torrent 工厂到 tests/api/conftest.py（3文件去重） | c881d69 | 重构 |
| 种子删除 L4 接口测试（service级，绕开同步/异步库共享问题） | 1e9a10f | +18 |
| 删除测试 review（补降级编排+audit身份锁+OR断言收窄） | 4ac69af | →22 |
| cron 安全策略测试（防脚本注入绕过，纯函数+端点级） | e57bca2 | +23 |
| 种子转移下载器不存在场景（patch 3处AsyncSessionLocal+审计验证） | daf4859 | +10 |
| 下载器设置 PUT 测试（校验+保存回读，patch SM4） | a0d1cef | +15 |
| 3接口审查修订（修2个假通过+强化弱断言） | 08f9e39 | +1 |

**共 +135 个回归测试**，6 个接口覆盖（审计日志/仪表盘/种子删除/cron安全/种子转移/下载器设置），全量 tests/api/ 462 passed。

---

## 各接口的测试范式与关键决策

### 1. 审计日志（41 测试，1 轮审查）
- **范式**：aiosqlite 异步内存库 + AsyncSession + 覆盖 get_async_db（service 异步+依赖注入式）
- **覆盖**：POST /audit-logs/query（11维过滤+子查询count+LIKE模糊+分页）+ statistics（内存聚合）+ operation-types（39枚举）+ download-export（约定差异）
- **关键修复**：排序完整序列断言（非首尾比较）、count 解耦 offset 验证、msg 排除断言防 service 吞异常假通过、401 body 断言、LIKE 通配符已知行为

### 2. 仪表盘（23 测试，4 轮审查完全收敛）
- **范式**：aiosqlite 异步内存库 + SimpleNamespace FakeStore 注入 app.state
- **覆盖**：GET /dashboard（裸SQL聚合 cron_task/torrent_audit_log + 内存缓存 store/torrent_stats）
- **关键修复**：60秒窗口 flaky（now()-10s留50秒裕度）、dr 身份锁（防方向写反）、torrent_stats=None 已知行为、dict 计数（set 漏计数）、keyword_rule 归一化路径
- **4 轮审查收敛性**：第1轮发现 1 真 flaky + 1 假通过；第2-4轮逐轮确认到位+补越来越细盲区

### 3. 种子删除 L4（22 测试，1 轮审查）
- **范式**：**service 级测试**（非 HTTP e2e）—— 同步内存库 + mock request（挂 store）+ mock audit（AsyncMock）
- **设计转折**：原 HTTP e2e 经子代理审查发现 3 个 🔴 致命缺陷（同步/异步库不可共享内存库、响应字段缺失、store未挂载），重设计为 service 级绕开
- **覆盖**：_add_tag_to_string 标签去重 + delete_by_level L4 路径 + delete_batch_by_level L3→L4 降级编排
- **关键修复**：补降级编排测试（service核心复杂度零覆盖）+ audit 身份锁（torrent_info_id）+ OR断言收窄

### 4. cron 安全策略（23+1 测试，1 轮审查）
- **范式**：纯函数测试 + 端点级（同步内存库 + override get_db + require_authenticated_user）
- **覆盖**：_validate_task_type_allowed（内置放行/脚本禁用/未知400）+ _validate_update_task_type（防绕过）+ /add + /{task_id}
- **关键修复**：PUT 成功路径补 mock refresh_task + 落库断言（防 CRUD no-op 假通过）+ PUT 403 补 msg + 未知类型覆盖

### 5. 种子转移（10 测试，1 轮审查）
- **范式**：patch 3 处 AsyncSessionLocal（app.database/endpoints.seed_transfer/services.seed_transfer_service）+ 全局 app.state.store 占位
- **覆盖**：下载器不存在场景（源/目标/都不存在→failed审计）+ schema 校验 + 认证
- **关键修复**：审计补 id 渲染断言 + target_path 锁定
- **已知**：SeedTransferAuditLog.source/target_downloader_id 是 Integer 列但 schema 传 str（生产严格DB可能500，测试用纯数字字符串规避）

### 6. 下载器设置 PUT（15 测试，1 轮审查）
- **范式**：同步内存库 + override get_db + patch encrypt_password（避SM4 YAML依赖）
- **覆盖**：空body默认配置 + 全局速度保存 + 规则落库 + 密码加密 + 9个参数校验422 + 404/401
- **关键修复**：变量遮蔽回读断言（钉死规则循环内 dl_speed_limit 被规则值遮蔽全局值的已知行为）+ 5处弱断言补 msg
- **发现的真实bug**：downloader_settings.py:408 规则循环内重赋 dl_speed_limit，遮蔽外层全局值（last-rule-wins 污染全局设置）

### 基础设施：conftest.py 去重（c881d69）
- 提取 make_torrent 工厂到 tests/api/conftest.py（3文件去重→1共享工厂，13业务kwarg超集签名）
- 设计决策：普通函数（非fixture，接db参数多次调用）；test_torrent_models的MagicMock工厂不合并（不同关注点）

---

## 子代理审查的工作流（本会话核心方法论）

每个新接口测试都经过闭环：
1. **子代理独立审查**（聚焦假通过/假失败/flaky/mock设计/盲区）
2. **逐条实证核实**（不盲信子代理，实测每个发现，否决误报）
3. **修订实施**（采纳真问题，补断言强度/覆盖盲区）
4. **反向验证**（mutation 测试：改被测代码看测试报红，证明测试有效）

**审查价值**：
- 仪表盘第1轮发现 1 个真 flaky（60秒窗口）+ 1 个假通过（dr方向写反）—— 高价值
- 种子删除审查发现 HTTP e2e 方案的 3 个 🔴 致命缺陷 —— 拯救了整个实施
- cron/种子转移/下载器设置审查各发现 1-2 个假通过（PUT弱断言/变量遮蔽/审计缺身份）—— 中价值
- 多次否决子代理误报（如"len==len 恒真"实际能抓到）—— 实证核实的重要性

---

## 关键测试质量教训（多轮审查沉淀）

1. **flaky 防护**：时间断言用绝对时间/足够裕度/身份标记，不用"恰好当前时间"
2. **防假通过**：降级/空数据场景加 msg 排除断言（防 service 吞异常返回空结构仍 code=200）
3. **身份锁定**：过滤测试断"返回哪条"而非"返回几条"（防方向写反）；audit 断 torrent_info_id
4. **完整序列 + 计数**：排序用完整顺序断言（非首尾比较）；分类用 dict 计数（set 漏计数）
5. **service 级 vs HTTP e2e**：当 endpoint 有同步/异步双 session + 响应字段裁剪时，service 级测试绕开共享库与字段缺失问题，且能测到完整返回字典
6. **mutation 反向验证**：每个测试组至少 1-3 处 mutation，确认测试验证真实逻辑而非 mock 自证

---

## 下一步行动

交接文档 3 个优先级全部完成。剩余可选方向（按价值排序）：

1. **修复测试中发现的真实代码问题**：
   - 下载器设置变量遮蔽（downloader_settings.py:408，规则污染全局 dl_speed_limit）
   - 种子转移 Integer 列存 str（SeedTransferAuditLog.source/target_downloader_id 类型不一致）
2. **扩展测试覆盖更多接口**：Tracker add/replace、标签管理、下载器CRUD 等零覆盖接口
3. **P2/P3 推迟项**：REST 路由迁移、前端 any 治理、OpenAPI schema 完善（见 PLANS/v1.0.5-audit.md）

---

## 关键上下文

- **计划文档**: PLANS/v1.0.5.md（查询模板系统，当前开发版本）
- **审计修复**: PLANS/v1.0.5-audit.md（上一会话的 P0-2 契约归一化，已完成）
- **进度日志**: progress.md（已更新 2026-06-28 会话记录）
- **测试范式**：4 种成熟模式（同步GET/POST+get_db / GET+Query+require_auth / 同步service自建session / 异步service+aiosqlite），见各测试文件 docstring
- **共享工厂**: tests/api/conftest.py 的 make_torrent（13 业务 kwarg 超集，收口 24 位置参数 + has_tracker_error NOT NULL 陷阱）
- **认证依赖**: 新接口统一 require_authenticated_user（401 detail 是 dict），旧接口部分用 get_current_user（401 detail 是 str "Could not validate credentials"）

---

## 阻塞问题

- 无。所有测试通过，无遗留阻塞。

---

## 快速恢复

```bash
# 后端测试（全量 API 级）
cd backend
python -m pytest tests/api/ -q

# 单个测试文件
python -m pytest tests/api/test_audit_logs_api.py -v

# 全栈环境验证（轻量模式）
./init.sh

# 启动后端
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# 启动前端（新终端）
cd frontend
npm run serve
```

访问: http://localhost:8080 | API文档: http://localhost:5001/docs

---

**最后更新**: 2026-06-28
