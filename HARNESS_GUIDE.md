# Harness 实施指南

> **BTDeck 项目** - v1.0.4 实时速度监控
> **日期**: 2026-04-22

---

## 📊 Harness 成熟度评估

基于五子系统框架的当前评分：

| 子系统 | 评分 | 说明 |
|--------|------|------|
| **Instructions** | 4/5 | AGENTS.md + CLAUDE.md + PLANS/ 完整 |
| **State** | 4/5 | feature_list.json + progress.md 完整 |
| **Verification** | 2/5 | init.sh 存在，缺少自动化测试 |
| **Scope** | 4/5 | 定义清晰，单一功能原则 |
| **Lifecycle** | 3/5 | 启动流程完整，交接流程需验证 |

**总体评分**: 3.4/5（良好）

**瓶颈**: Verification（验证子系统）

---

## 🎯 改进建议

### 短期（1-2天）

1. **完善 Verification**
   - 添加后端单元测试
   - 添加前端组件测试
   - 添加性能基准测试

2. **完善 Lifecycle**
   - 测试 session-handoff.md 模板
   - 添加会话恢复检查清单

### 中期（1周）

1. **自动化验证**
   - CI/CD 集成
   - 自动化测试运行

2. **监控与告警**
   - 性能监控
   - 错误追踪

---

## 📋 Harness 文件清单

### 核心文件（必需）

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `AGENTS.md` | 代理路由层 | 稳定 |
| `feature_list.json` | 功能状态追踪 | 每次会话 |
| `progress.md` | 会话日志 | 每次会话 |
| `init.sh` | 环境验证 | 稳定 |
| `session-handoff.md` | 交接模板 | 每次会话 |

### 支持文件（推荐）

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `HARNESS_GUIDE.md` | 本文件 | 按需 |
| `PLANS/v1.0.4.md` | 功能规范 | 功能开发时 |

---

## 🚀 使用指南

### 首次使用

```bash
# 1. 克隆项目
git clone <repo-url>
cd BtDeck

# 2. 运行初始化
./init.sh

# 3. 阅读指南
cat AGENTS.md
cat PLANS/v1.0.4.md
cat progress.md
```

### 每次会话开始

```bash
# 1. 查看当前状态
cat feature_list.json | jq '.features[] | select(.status == "in-progress")'

# 2. 查看最近进度
tail -50 progress.md

# 3. 验证环境
./init.sh

# 4. 开始工作
# (阅读 AGENTS.md 中的启动工作流)
```

### 会话结束

```bash
# 1. 更新进度
# (编辑 progress.md)

# 2. 更新功能状态
# (编辑 feature_list.json)

# 3. 准备交接
# (复制 session-handoff.md 模板，填写当前状态)

# 4. Git 提交（可选）
cd BtDeck/
git add . && git commit -m "feat: xxx"
```

---

## 🧪 验证流程

### 手动验证（当前）

```bash
# 1. 环境验证
./init.sh

# 2. 后端启动测试
cd BtDeck
python -m uvicorn app.main:app --reload --port 5001

# 3. 前端启动测试
cd BtDeck_fronted
npm run serve

# 4. 功能测试
# (手动测试 8 个验收场景)
```

### 自动化验证（待实现）

```bash
# TODO: 添加自动化测试脚本
./scripts/test.sh
```

---

## 📊 效果测量

### 基线（无 Harness）

| 指标 | 值 |
|------|-----|
| 会话恢复时间 | ~15 分钟 |
| 上下文丢失率 | ~30% |
| 重复工作率 | ~20% |

### 目标（有 Harness）

| 指标 | 值 | 改进 |
|------|-----|------|
| 会话恢复时间 | < 5 分钟 | 67% ↓ |
| 上下文丢失率 | < 5% | 83% ↓ |
| 重复工作率 | < 5% | 75% ↓ |

### 测量方法

1. **会话恢复时间**: 从开始阅读 AGENTS.md 到理解当前状态
2. **上下文丢失率**: 需要重新询问的问题数量 / 总问题数
3. **重复工作率**: 重做的代码量 / 总代码量

---

## ⚠️ 陷阱与预防

### 常见陷阱

1. **忘记更新 feature_list.json**
   - 预防: 会话结束前检查清单

2. **progress.md 记录不详**
   - 预防: 使用结构化模板

3. **跳过 init.sh 验证**
   - 预防: AGENTS.md 启动工作流强制要求

4. **Git 提交到错误目录**
   - 预防: 提交前检查 pwd

### 预防措施

- ✅ 会话结束检查清单（session-handoff.md）
- ✅ 结构化日志模板（progress.md）
- ✅ 启动工作流（AGENTS.md）
- ✅ 前后端分离提醒（AGENTS.md）

---

## 🔄 持续改进

### 每周回顾

- [ ] Harness 文件是否完整？
- [ ] 会话交接是否顺利？
- [ ] 是否有新的陷阱发现？
- [ ] 验证流程是否有效？

### 每月评估

- [ ] 重新评分五子系统
- [ ] 更新改进建议
- [ ] 调整文件结构

---

## 📞 支持与反馈

**问题**: GitHub Issues
**讨论**: 项目 Wiki
**文档**: 见 PLANS/ 目录

---

**最后更新**: 2026-04-22
**维护者**: BTDeck Team
