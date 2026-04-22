# AGENTS.md - BTDeck 项目指南

> **项目**: BTDeck - BitTorrent 全栈管理器
> **技术栈**: Vue 2 + FastAPI + Python
> **更新**: 2026-04-22

---

## 🎯 项目定位

BTDeck 是统一管理多种 BitTorrent 客户端（qBittorrent、Transmission）的全栈 Web 应用。

**核心价值**: 提供统一界面管理多下载器，支持种子添加、状态监控、批量操作等功能。

---

## 🚀 启动工作流

### 开始任何工作前，按顺序执行：

```
1. 阅读 AGENTS.md（本文件） ← 你在这里
2. 阅读 PLANS/v1.0.4.md（当前功能规范）
3. 运行 ./init.sh（验证环境）
4. 阅读 feature_list.json（功能状态）
5. 阅读 progress.md（会话上下文）
```

### 识别当前任务

```bash
# 查看当前进行中的功能
cat feature_list.json | jq '.features[] | select(.status == "in-progress")'

# 查看最近进度
cat progress.md | tail -20
```

---

## 📋 工作规则

### 1. 单一功能原则

**一次只处理一个功能**，从 `feature_list.json` 中选择 `in-progress` 状态的功能。

**禁止**: 同时处理多个功能或未经规划的 bug 修复。

### 2. 验证优先

**完成定义**:
- [ ] 实现完成
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 性能测试达标
- [ ] 更新 progress.md
- [ ] 更新 feature_list.json

### 3. 代码规范

**后端**:
- 遵循 `BtDeck/CLAUDE.md`
- API 响应格式统一
- 使用 `app.state.store` 缓存
- 添加类型注解

**前端**:
- 遵循 `BtDeck_fronted/CLAUDE.md`
- Vue 2 Options API 风格
- TypeScript 类型完整
- 定时器必须清理

### 4. Git 提交规范

**前后端分离提交**:
```bash
# 后端
cd BtDeck/
git add . && git commit -m "feat: xxx"

# 前端
cd BtDeck_fronted/
git add . && git commit -m "feat: xxx"
```

**禁止**: 在项目根目录提交。

---

## 📁 必需文件

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `AGENTS.md` | 代理路由层 | 稳定 |
| `feature_list.json` | 功能状态追踪 | 每次会话 |
| `progress.md` | 会话日志 | 每次会话 |
| `PLANS/v1.0.4.md` | 功能规范 | 功能开发时 |
| `CLAUDE.md` | 后端技术约束 | 稳定 |
| `docs/constraints/` | 约束详细规范（见下表） | 稳定 |

### 约束文档清单（`docs/constraints/`）

| 文件 | 约束内容 | 适用场景 |
|------|----------|----------|
| `api-response-format.md` | API 统一响应格式、分页字段名强制规范 | 编写/修改任何 API 接口时 |
| `code-reuse.md` | 代码复用优先原则、扩展判断标准 | 创建新函数/组件前 |
| `database-migration.md` | Alembic 迁移管理、Schema 变更流程 | 修改数据库模型时 |
| `database-consistency.md` | 跨环境数据库一致性保障、版本检查 | 部署/切换环境时 |
| `downloader-connection.md` | 下载器客户端缓存使用规范、禁止新建连接 | 涉及下载器操作的接口 |

---

## ✅ 完成定义

一个功能完成当且仅当：

1. **实现完成**: 代码实现符合 PLANS/v1.0.4.md 规范
2. **测试通过**: 所有验收场景测试通过
3. **性能达标**: 满足性能指标（API < 200ms）
4. **文档更新**: progress.md 记录关键决策
5. **状态更新**: feature_list.json 标记为 done
6. **仓库可重启**: 下个会话可直接继续

---

## 🔄 会话结束清单

在结束会话前，按顺序执行：

```
1. 更新 progress.md
   - 记录完成的工作
   - 记录技术决策
   - 记录已知问题

2. 更新 feature_list.json
   - 更新当前功能状态
   - 添加发现的依赖

3. 验证仓库状态
   - ./init.sh 通过
   - 无未提交的敏感文件
   - 下个会话可继续

4. Git 提交（可选）
   - 按前后端分离提交
   - 提交信息清晰

5. 记录交接信息
   - 当前进度
   - 下一步行动
   - 阻塞问题
```

---

## 🚨 风险与已知问题

### 已有基础设施（v1.0.4 开发前必须了解）

> **重要**: 以下模块已存在。区分"可复用"和"不可复用"，避免重复开发或错误假设。

#### 可复用（必须使用）

1. **下载器客户端缓存** (`app/downloader/initialization.py`)
   - `app.state.store` 提供 `get_snapshot()` 获取缓存的下载器连接
   - 所有下载器操作**必须**通过缓存连接，禁止新建客户端
   - v1.0.4 的速度接口必须通过此缓存调用下载器 API

2. **现有种子列表 API** (`app/api/endpoints/torrent_crud.py`)
   - `POST /torrents/list` 已返回 `download_speed`、`upload_speed` 字段
   - 这是**静态数据**（用户手动刷新时从下载器同步到数据库再返回）
   - v1.0.4 需新增**轻量级动态接口** `GET /torrents/active-torrents`，直接从下载器获取实时速度

3. **应用生命周期** (`app/startup/lifecycle.py`)
   - 已有 `run_dashboard_stats_loop` 后台任务
   - v1.0.4 需考虑与现有定时任务的协调

#### 不可复用（与 v1.0.4 无关）

4. **种子状态统计缓存** (`app/downloader/torrent_stats_cache.py`)
   - 功能：缓存种子的 **status 字段**（downloading/seeding/paused），用于统计计数
   - **不含速度字段**：不存储 `downloadSpeed` / `uploadSpeed`
   - **与 v1.0.4 无直接关系**：v1.0.4 需要的是种子级别的实时速度数据，必须从下载器 API 实时获取

### 当前风险

1. **1秒轮询性能**: 可能导致下载器过载
   - 缓解: 限制并发数量，添加超时

2. **内存泄漏**: 前端定时器未清理
   - 缓解: 严格的 beforeDestroy 清理

3. **数据一致性**: 查询结果与活跃种子不匹配
   - 缓解: 后端应用相同查询条件

### 已知问题

- 无（新功能）

---

## 📚 参考资料

### 架构文档
- `PLANS/README.md` - 版本计划索引
- `PLANS/v1.0.4.md` - 当前功能详细规范

### 技术约束
- `BtDeck/CLAUDE.md` - 后端开发规范
- `BtDeck_fronted/CLAUDE.md` - 前端开发规范
- `BtDeck/docs/constraints/` - 详细约束文档

### API 文档
- 后端: http://localhost:5001/docs
- 前端: http://localhost:8080

---

## 🔍 快速诊断

### 遇到问题时

```bash
# 1. 检查环境
./init.sh

# 2. 查看当前功能状态
cat feature_list.json | jq .

# 3. 查看最近进度
cat progress.md

# 4. 查看后端日志
cd BtDeck && tail -f logs/app.log

# 5. 查看前端日志
cd BtDeck_fronted && npm run serve
```

---

## 📞 支持与反馈

**项目**: https://github.com/your-org/BtDeck
**问题**: 使用 GitHub Issues
**文档**: 见 PLANS/ 目录

---

**最后更新**: 2026-04-22
**维护者**: BTDeck Team
