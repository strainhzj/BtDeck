# 数据库迁移运维手册（database-migration-ui Runbook）

> **适用**: v1.0.8 数据库迁移控制面（SQLite ⇄ PostgreSQL）
> **技术约束**: `backend/docs/constraints/database-migration.md`（§4 生命周期 / §6 目标清理 / §7 提交与交接 / §8 端点鉴权）
> **用户配置**: `docs/database-setup.md`；**契约**: `backend/docs/postgresql-contract.md` §2.4

---

## 1. 标准迁移流程（SQLite → PG）

| 阶段 | 现象 | 操作 |
|------|------|------|
| 1. 预检 | 设置 →「数据库」面板 | 目标 PG 表单填五档 TLS（verify-ca/full 需 CA 路径）→「测试连接」三态（版本≥16 / 空库 / 可达）；非空库须先 §6 discard 或换库 |
| 2. 启动 | 面板入口→进入维护模式 | 业务写冻结（PREPARING→DRAINING→FROZEN）；进度页 `/maintenance` 登录维护账号 |
| 3. 导入 | IMPORTING/VERIFYING | 无人工动作；进度 done/total+phase 徽标；**卡 NEEDS_CREDENTIALS** → §3 重输 |
| 4. 校验 | VERIFYING/READY_TO_SWITCH | 只读等待；任一差异自动失败进入回退决策（§5） |
| 5. 提交 | switch | B=应用托管 / A=env 交接（面板预览 plan.steps）；提交即持久（不可撤销，见 §5 决策树） |
| 6. 重启 | RESTART_PENDING | 托管环境（systemd/docker）+ `BTD_MIGRATION_MANAGED_RESTART=1` 自动退出；否则**手动重启进程**；未重启前数据只读安全 |
| 7. 激活 | 重启后自动 | 目标 ACK → 本地 `ACTIVATED_ACK` → 正常启动（无需人工确认；失败保持维护并显示原因） |

## 2. 提交后未重启（COMMITTED 待 ACK）

- 现象：维护页显示「配置已提交，需手动重启」；业务保持只读。
- 处理：直接重启即可——重启路径幂等 redo（补发布配置+目标 ACK+本地 ACK），重复重启安全。
- **绝不**手工改 `config.yaml` / `db-migration/` 任何文件（journal 是唯一写者；外部改动导致 fail-closed 拒绝启动）。

## 3. 凭据丢失（NEEDS_CREDENTIALS）

- 现象：维护页出现凭据重输表单（源或目标密码未持久，只保存在内存/受保护候选）。
- 处理：表单重输后恢复；丢失且无法提供 → cancel 迁移（CANCELLING→worker 确认→CANCELLED）→ 回 §1 或 §5。

## 4. 取消与放弃（leave / discard）

- **cancel**：进行中取消——worker 协作停止后才落 CANCELLED（期间不重复发请求）。
- **leave**：放弃迁移回 NORMAL——已冻结源会解冻；**COMMITTED 后禁 leave**（决定已持久，只能走 §2 完成激活）。
- **discard 目标库**（§6.5）：仅 manifest 固定目标+对象清单+双确认 token；PG 逐对象 DROP **无 CASCADE**；出现外部内容即拒；清理后非空即隔离拒重建。COMMITTED/PREPARED 后禁 discard。

## 5. 故障决策树

| 故障 | 判定 | 动作 |
|------|------|------|
| 导入/校验失败 | 进度页 phase=failed+detail | cancel → 修因（网络/凭据/磁盘）→ 重新发起；目标残留按 §4 discard |
| 提交后无法重启 | RESTART_PENDING 持续 | 保持现状（只读安全）；用前代恢复见下 |
| 需回退到前代 | ACTIVATED 前异常 | 受保护前代 `attempts/<id>/prior.yaml` 仍在；经维护流程恢复（勿手工拷贝为 config.yaml——先咨询支持/看 constraints §7.2） |
| 掉电/进程被杀 | 任意阶段 | 重启即自愈：journal 原子写保证 control/manifest 要么旧要么新；COMMITTED 决定不丢（§2 路径继续） |
| `db-migration/` 文件损坏 | 启动 fail-closed 拒绝 | 这是保护；**不要**删除重建——按 constraints §9 损坏处理流程（诊断模式） |
| 维护页打不开 | 前端未部署 W4 版本 | 用 curl 直连 `/health/control-ready` 与 `/api/v1/database/status`（维护 token） |

## 6. 同库交接（A ↔ B 模式转换）

- **B→A（clear）**：设置面板「env 交接」预览（要求 env 指向**同一当前服务库**：同 dialect+同 host:port/db 或 samefile；异库被拒，引导新迁移）。确认后在维护流程执行：单连接核旧 generation→CAS 新 generation→本地 ACK→B 管理交还 A。
- **A→B**：正常发起迁移，目标=当前库所在集群的空库或经 §6.5 清理后的库。

## 7. 平台与边界

- Android 本机（伴侣 App WebView）/ demo：不支持 PG 与迁移（bootstrap→API→页面三层拒）。
- 多实例/多 worker PG 模式 fail-fast（契约 §1）；迁移期**必须**单实例。

## 8. 证据与测试索引

- 单元/注入面：`backend/tests/services/test_db_migration_{journal,config_store,manager,activation,failure_matrix}.py`
- 端点鉴权矩阵：`backend/tests/api/test_database_endpoints.py`
- 真 PG 实库（CI pg-integration job）：`backend/tests/pg_integration/test_pg_{fence,migration_flow,tls}.py`——本地 skip 不计通过，以 CI 执行为准
- 前端：`frontend/tests/unit/{database-api,maintenance-client,database-settings,maintenance-page,database-platform-gating,mobile-maintenance}.spec.ts`
