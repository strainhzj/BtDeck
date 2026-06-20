# Session Handoff - BtDeck 全栈项目

> 用途：会话交接模板，确保上下文不丢失。复制本模板，填写当前状态。

---

## 会话信息

**日期**: 2026-06-20
**版本**: v1.0.5-audit（契约审计修复，技术债版本）
**功能**: 基于 backend/docs/style-and-contract-audit.md 的 P1 确定性 bug + P0 契约归一化
**状态**: P0-2 全部完成（P0-2a/b/c/d）。剩余 P2/P3 为推迟项。
**分支**: fix/contract-audit（基于 dev）

---

## 完成的工作（10 commit，含本会话 6 commit）

| 任务 | commit | 验证 |
|------|--------|------|
| P0-3 后端全局异常处理器（归一化 HTTPException/422/未捕获异常为 CommonResponse） | ac324bc | pytest 1524 passed |
| P0-1 前端 ApiError 归一化（4 分支 detail 解包 + 兼容 getter + 双 header 收敛） | 0e55469 | jest 25/25, eslint 0 error |
| P1-A 后端补 4 项端点（statistics装饰器/模板详情/logout/cronTasks日志） | efc6574 | auth+cron 189 passed |
| P1-B 前端修 4 项契约（apply对齐/articles删除/2FA改Action/删getTorrentDetail/接通logout） | 0e8f007 | jest 25/25, eslint 0 error |
| P0-2c 认证基础设施补强（AuthenticatedUserInfo 加 user_id 字段，兜底解析） | 9e19822 | auth 125 passed |
| P0-2a Batch A 迁移 10 个 token-only 端点 | fc7760b+ | pytest tests/api/ 218 passed |
| P0-2a Batch B 迁移 downloader/cron_tasks/tracker/torrent_crud/sync | (Batch B) | 218 passed |
| P0-2a Batch C 迁移 3 个 user_id 端点（advanced_search/tag_management/tracker_keywords） | (Batch C) | 218 passed |
| P0-2a Batch D 完成 4 个 mixed 部分迁移文件 | deab3ac | 218 passed |
| P0-2d 弃用 verify_token_dependency | 33f2481 | 1523 passed |

---

## 本会话完成的工作（P0-2a/b/d，6 commit）

### P0-2a 后端认证迁移到 require_authenticated_user（24 文件全部完成）

**实际调研修正**：交接文档预估 ~21 文件 + ~40 处测试断言。调研发现：
- 实际 **24 个 endpoint 文件**（多识别 3 个）
- 测试改造量 **32 处 inline 断言**（非 ~102，因 test_auth_protection_extended.py 的 62 处走 _is_auth_rejected helper，已兼容 HTTP 401 无需改）

**分 4 批执行（每批 commit + 跑针对性 pytest）**：
- **Batch A**（10 简单 token-only）：tasks/tracker_test/downloader_capabilities/torrent_speed/tracker_reannounce/downloader_path_maintenance/downloader_capabilities_management/seed_transfer/torrent_backup/torrent_status/tracker_keywords_pools
- **Batch B**（较大 token-only + downloader 簇）：downloader.py(13)/cron_tasks.py(20)/tracker.py(3)/torrent_sync.py(2)/torrent_crud.py(5)
- **Batch C**（3 user_id 文件 + 401 兜底）：advanced_search.py(9)/tag_management.py(13)/tracker_keywords.py(10)
- **Batch D**（4 mixed 部分迁移）：setting_templates.py(5)/tracker_messages.py(8)/cuser.py(6)/torrent_deletion.py(6)

**关键决策**：
- advanced_search 旧 token 缺 user_id → HTTP 401 拒绝（对齐 torrent_location 模板，用户确认）
- tag_management/tracker_keywords username = user_info.username or "admin"（保留原 helper 的 admin 兜底）
- 修复多处预存在的"不安全 try/except 认证"（verify_access_token 失败返回 None 而非抛异常，旧代码 try/except 形同虚设）

### P0-2b 测试断言改造（穿插在各批中完成）
- test_auth_protection.py：TestTorrentStatusAuth/TestTrackerKeywordsPoolsAuth/TestTorrentCrudAuth + 2 个"不崩溃"测试改 401
- test_auth_protection_extended.py：test_get_status_all 改用 _is_auth_rejected（helper 本身无需改）
- test_reannounce_api.py：3 个认证失败测试断言改 401
- test_search_templates.py：11 个认证失败测试断言改 401
- test_tag_aggregation_api.py：mock_auth 改用 dependency_overrides[require_authenticated_user]；3 个无认证测试断言改 401

### P0-2d 弃用 verify_token_dependency
- verify_token_dependency 加 DeprecationWarning（保留定义供过渡兼容）
- cron_tasks.verify_token 已在 Batch B 删除
- README 过期描述更新

---

## 下一步行动

P0-2 全部完成。剩余均为推迟项（非阻塞）：

1. **P2 REST 路由迁移**（推迟）：见 PLANS/v1.0.5-audit.md
2. **P3 前端 any/as unknown as 治理**（推迟）
3. **OpenAPI schema 完善**（推迟）
4. **分页字段统一**（推迟）
5. **API 对照表 CI**（推迟）

**可选收尾**：若希望彻底移除 verify_token_dependency（当前仅加 DeprecationWarning），确认无外部引用后可删除 dependencies.py:139 定义。

---

## 关键上下文

- **计划文档**: `PLANS/v1.0.5-audit.md`（详细任务分解 + 手动 e2e 清单 + 推迟项）
- **审计文档**: `backend/docs/style-and-contract-audit.md`
- **认证统一完成**: 所有 24 个 endpoint 文件使用 `require_authenticated_user`（dependencies.py），旧 `verify_token_dependency` 已弃用，cron_tasks.verify_token 已删除
- **异常处理器已就绪**: P0-3 全局 handler 兜底所有未捕获异常
- **前端归一化已就绪**: P0-1 ApiError 兼容 HTTP 200+code 和 HTTP 4xx/5xx 两种错误形态
- **审计修正（不动项）**: /tags/batch-delete 误报；tag_management helper 字典是私有返回值；tracker statistics 已修
- **已知遗留（预存在，与本次无关）**:
  - test_unified_token_expiry 在 Windows 全量跑失败（路径分隔符 bug）
  - test_concurrent_requests flaky（baseline 同样失败）

---

## 阻塞问题

- 无。P0-2 已全部完成。

---

## 快速恢复

```bash
# 切换到审计修复分支
git checkout fix/contract-audit

# 全栈环境验证（轻量模式）
./init.sh

# 后端测试（注意 deselect 预存在的 Windows 路径失败）
cd backend
python -m pytest --deselect tests/test_architecture_constraints.py::test_unified_token_expiry -q

# 前端 jest 单测
cd frontend
node_modules/.bin/jest --config jest.config.js

# 前端依赖未安装时先 npm ci

# 启动后端
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# 启动前端（新终端）
cd frontend
npm run serve
```

访问: http://localhost:8080 | API文档: http://localhost:5001/docs

---

**最后更新**: 2026-06-20
