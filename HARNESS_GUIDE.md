# Harness 实施指南

> **项目**: BtDeck 全栈（backend + frontend + deploy）
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-18

本文件由 backend/HARNESS_GUIDE.md 升级合并而来，覆盖全栈。

---

## 📊 Harness 成熟度评估（五子系统）

基于五子系统框架的评分（2026-06-18 合并后重估）：

| 子系统 | 合并前 | 合并后 | 说明 |
|--------|:---:|:---:|------|
| **Instructions** | 3/5 | 5/5 | 根 AGENTS.md 全栈路由层 + 各端 AGENTS.md 指针 + CLAUDE.md 分层 |
| **State** | 2/5 | 5/5 | 根目录统一 feature_list.json（含 current_dev_version + scope）+ progress.md |
| **Verification** | 2/5 | 4/5 | 根 init.sh 串联两端（--ci/--full 两档） |
| **Scope** | 3/5 | 4/5 | v1.0.5 拆解为 15 任务，覆盖前后端 + 隐藏依赖（User 关系） |
| **Lifecycle** | 2/5 | 4/5 | 根目录统一 session-handoff.md + 3 commit 回滚策略 |

**合并后总体评分**: 4.4/5（优秀）

**合并前主要问题（已解决）**:
- feature_list 前后端分裂且过时（v1.0.4 标 in-progress 实际 done、v1.0.9 标 pending 实际提前完成）
- progress/session-handoff 前后端重复
- 遗漏废弃文件（backend/init.sh、backend/PLANS/、backend/ROADMAP.md）

---

## 📋 Harness 文件清单

### 核心文件（根目录，全栈统一）

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `AGENTS.md` | 全栈代理路由层 | 稳定 |
| `feature_list.json` | 全栈功能状态追踪（schema_version + current_dev_version + scope） | 每次会话 |
| `progress.md` | 全栈会话进度日志（版本分节 + 前后端子段） | 每次会话 |
| `session-handoff.md` | 全栈会话交接模板 | 每次会话结束 |
| `init.sh` | 全栈环境验证入口（--ci/--full） | 稳定 |
| `HARNESS_GUIDE.md` | 本文件 | 按需 |

### 各端文件（端特定，不合并）

| 文件 | 用途 |
|------|------|
| `backend/AGENTS.md`、`frontend/AGENTS.md` | 端规则指针（指向端模块索引 + 约束，不回指根） |
| `backend/CLAUDE.md`、`frontend/CLAUDE.md` | 端技术栈约束（FastAPI / Vue2） |
| `backend/docs/constraints/`、`frontend/docs/constraints/` | 端详细规范（同名不同内容，不合并） |
| `backend/scripts/init.sh`、`frontend/scripts/init.sh` | 端环境验证（被根 init.sh 复用，支持 --ci） |

### 计划文件

| 文件 | 用途 |
|------|------|
| `PLANS/<version>.md` | 各版本详细计划（根目录唯一来源） |

---

## 🚀 使用指南

### 首次使用

```bash
# 1. 运行全栈初始化（完整模式，安装依赖）
./init.sh --full

# 2. 阅读全栈工作流
cat AGENTS.md

# 3. 查看当前版本计划
cat PLANS/v1.0.5.md
```

### 每次会话开始

```bash
# 1. 轻量环境验证（默认，不安装依赖）
./init.sh

# 2. 查看当前开发版本与进行中任务
cat feature_list.json | jq '.current_dev_version'
cat feature_list.json | jq '.features[] | select(.status=="in-progress")'

# 3. 查看最近进度
cat progress.md

# 4. 开始工作（遵循 AGENTS.md 启动工作流）
```

### 会话结束

```bash
# 1. 更新 progress.md
# 2. 更新 feature_list.json（任务 status + evidence）
# 3. 填写 session-handoff.md
# 4. ./init.sh 验证通过
# 5. Git 提交（仅在用户要求时，根目录执行）
```

---

## 🧪 验证流程

### 全栈验证

```bash
# 轻量验证（日常，不安装依赖）
./init.sh

# 完整验证（CI / 首次，安装依赖 + lint）
./init.sh --full
```

### 单端验证

```bash
# 后端
cd backend && ./scripts/init.sh          # 默认：安装依赖 + 验证
cd backend && ./scripts/init.sh --ci     # 仅验证（不安装）

# 前端
cd frontend && ./scripts/init.sh
cd frontend && ./scripts/init.sh --ci
```

### init.sh 参数语义（统一约定）

| 调用方式 | 行为 | 适用场景 |
|----------|------|----------|
| `./scripts/init.sh` | 安装依赖 + 环境验证 | 端内首次开发、手动装依赖 |
| `./scripts/init.sh --ci` | 仅环境验证（不安装） | 被 root init.sh 调用、CI 快速检查 |
| `./scripts/init.sh --check` | （废弃，由 --full 替代） | — |
| 根 `./init.sh` | 串联两端 `--ci` | 全栈日常验证 |
| 根 `./init.sh --full` | 串联两端默认模式 | 全栈完整验证 |

---

## 📊 效果测量

### 合并前基线（端分裂）

| 指标 | 值 |
|------|-----|
| 状态文件份数 | 4 份（backend + frontend 各 feature_list/progress） |
| 状态不一致风险 | 高（v1.0.4/v1.0.9 状态已脱节） |
| 全栈上下文恢复 | 需读 4+ 文件 |
| 废弃文件干扰 | 存在（backend/init.sh、backend/PLANS 等） |

### 合并后目标

| 指标 | 值 | 改进 |
|------|-----|------|
| 状态文件份数 | 1 份（根 feature_list.json + progress.md） | 75% ↓ |
| 状态不一致风险 | 低（单源真相） | — |
| 全栈上下文恢复 | 读 2 文件 + ./init.sh | 50% ↓ |
| 废弃文件干扰 | 0（已清理 17 文件） | 100% ↓ |

---

## ⚠️ 陷阱与预防

### 常见陷阱

1. **忘记更新 feature_list.json**
   - 预防: 会话结束清单强制检查
2. **task 的 file 字段未覆盖全部改动文件**
   - 预防: 完成定义要求"覆盖声明的所有 file"
3. **fullstack 任务无单一 file**
   - 预防: scope=fullstack，file 填主文件或留空（见 feature_list.json merge_note）
4. **跨端变更只在一端测试**
   - 预防: 完成定义要求前后端各自验证
5. **跳过 init.sh 验证**
   - 预防: AGENTS.md 启动工作流强制要求

### 三轮独立审查沉淀的经验

本次 harness 合并经三轮子代理独立审查（62→78→82 分），沉淀以下关键教训：

1. **合并前必须实际读取所有源文件**：设计者曾误判"前端无 feature_list.json"，实际存在。
2. **废弃文件要全仓库搜索**：backend/init.sh、backend/PLANS/、backend/ROADMAP.md 均为陈旧重复，易遗漏。
3. **旧路径批量替换要全仓库覆盖**：BtDeck_fronted 实际散落 17 处，逐文件列举易漏。
4. **隐藏依赖要从代码反查**：QueryTemplate 的 back_populates 暴露 User 模型改造需求。
5. **改默认行为会破坏肌肉记忆**：init.sh 用 --ci 新参数而非改默认更稳妥。

---

## 🔄 持续改进

### 每周回顾

- [ ] harness 文件是否完整？
- [ ] feature_list.json 状态是否准确？
- [ ] 会话交接是否顺利？
- [ ] 是否有新的废弃文件产生？

### 每月评估

- [ ] 重新评分五子系统
- [ ] 检查 PLANS/ 与 feature_list 一致性
- [ ] 清理陈旧文档

---

**最后更新**: 2026-06-18
**维护者**: BtDeck 开发团队
