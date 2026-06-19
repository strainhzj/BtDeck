# Session Handoff - BtDeck 全栈项目

> 用途：会话交接模板，确保上下文不丢失。复制本模板，填写当前状态。

---

## 会话信息

**日期**: 2026-06-19
**版本**: v1.0.5-audit（契约审计修复，技术债版本）
**功能**: 基于 backend/docs/style-and-contract-audit.md 的 P1 确定性 bug + P0 契约归一化
**状态**: in-progress（P0-3/P0-1/P1-A/P1-B/P0-2c 已完成；P0-2a/b 进行中）
**分支**: fix/contract-audit（基于 dev）

---

## 完成的工作（5 commit）

| 任务 | commit | 验证 |
|------|--------|------|
| P0-3 后端全局异常处理器（归一化 HTTPException/422/未捕获异常为 CommonResponse） | ac324bc | pytest 1524 passed |
| P0-1 前端 ApiError 归一化（4 分支 detail 解包 + 兼容 getter + 双 header 收敛） | 0e55469 | jest 25/25, eslint 0 error |
| P1-A 后端补 4 项端点（statistics装饰器/模板详情/logout/cronTasks日志） | efc6574 | auth+cron 189 passed |
| P1-B 前端修 4 项契约（apply对齐/articles删除/2FA改Action/删getTorrentDetail/接通logout） | 0e8f007 | jest 25/25, eslint 0 error |
| P0-2c 认证基础设施补强（AuthenticatedUserInfo 加 user_id 字段，兜底解析） | 9e19822 | auth 125 passed |

---

## 进行中的工作

### P0-2a 后端认证迁移到 require_authenticated_user（最大块，未完成）

**规模**（3 个独立 Explore agent 核实）：
- 21 个 endpoint 文件含手写 `x-access-token` 验证（~195 处）
- ~40 处测试断言需改造（status_code==200+code=='401' → status_code==401）

**完整文件清单**（需逐文件迁移，按是否消费 user_id 分两类）：
- 只校验 token 的（删手写验证 + 加 Depends）：downloader.py、tracker_keywords.py、tracker_keywords_pools.py、tasks.py、torrent_location.py、torrent_sync.py
- 取 user_id 的（同步改 get_current_user_id(token) → user_info.user_id）：setting_templates.py、tag_management.py、advanced_search.py、cuser.py、torrent_crud.py、torrent_deletion.py、downloader_settings.py、downloader_capabilities_management.py、downloader_path_maintenance.py、tracker.py、tracker_messages.py（statistics 已迁移）

**登录豁免**：login.py:45 保留 HTTP 200 + code="401"（密码错误业务语义），严禁迁移。
**废弃旧依赖**：verify_token_dependency（dependencies.py:124）和 cron_tasks.verify_token（cron_tasks.py:235）。

### P0-2b 认证测试改造（未完成）
- test_auth_protection.py、test_search_templates.py、test_tag_aggregation_api.py、test_reannounce_api.py 中 ~40 处断言
- + 新增 P1-A 端点（statistics/模板详情/logout/cronTasks日志）的认证测试

---

## 下一步行动

1. **P0-2a batch1**：迁移"只校验 token"的文件（downloader.py、tracker_keywords.py 等），每文件单独 commit + 跑 pytest
2. **P0-2a batch2**：迁移"取 user_id"的文件（setting_templates.py、tag_management.py 等）
3. **P0-2a batch3**：迁移剩余文件 + 废弃 verify_token_dependency/cron_tasks.verify_token
4. **P0-2b**：改造 ~40 处认证测试断言 + 新端点认证测试
5. **验证**：全量 pytest + jest + 手动 e2e 清单（见 PLANS/v1.0.5-audit.md）+ init.sh
6. **回滚阈值**：>5 个 test_auth_protection*.py 用例失败 → 整体回滚 P0-2

---

## 关键上下文

- **计划文档**: `PLANS/v1.0.5-audit.md`（详细任务分解 + 手动 e2e 清单 + 推迟项）
- **审计文档**: `backend/docs/style-and-contract-audit.md`
- **依赖基础设施已就绪**: `require_authenticated_user`（dependencies.py:68）返回 HTTP 401；`AuthenticatedUserInfo` 已含 user_id 字段（P0-2c）
- **异常处理器已就绪**: P0-3 全局 handler 兜底所有未捕获异常
- **前端归一化已就绪**: P0-1 ApiError 兼容 HTTP 200+code 和 HTTP 4xx/5xx 两种错误形态
- **审计修正（不动项）**: /tags/batch-delete 误报；tag_management helper 字典是私有返回值；tracker statistics 已修
- **推迟项**: P2 REST 路由迁移、P3 前端 any/as unknown as 治理、OpenAPI schema、分页字段统一、API 对照表 CI
- **已知遗留**: test_unified_token_expiry 在 Windows 全量跑失败（路径分隔符 bug，预存在，与本次无关）

---

## 阻塞问题

- 无。P0-2a/b 是工作量问题，非技术阻塞。

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

**最后更新**: 2026-06-19
