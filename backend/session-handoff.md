# Session Handoff Template

> **用途**: 会话交接模板，确保上下文不丢失

---

## 📋 会话信息

**功能**: v1.0.4 实时速度监控
**会话日期**: 2025-01-22
**上次更新**: 2025-01-22

---

## ✅ 完成的工作

### Harness 构建（100%）

- ✅ 创建 AGENTS.md（代理路由层）
  - 定义启动工作流
  - 定义工作规则
  - 定义完成标准

- ✅ 创建 feature_list.json（功能状态追踪）
  - v1.0.4 功能分解为 6 个任务
  - 定义验收标准
  - 定义性能指标

- ✅ 创建 progress.md（会话日志）
  - 记录技术决策
  - 记录测试场景
  - 记录性能指标

---

## 🚧 进行中的工作

### 当前任务: 后端开发（0%）

**文件**: `BtDeck/app/api/endpoints/torrent_speed.py`

**待实现**:
1. 创建速度接口 `/torrents/active-torrents`
2. 支持查询条件（与静态API一致）
3. 支持分页参数（skip, limit）
4. 并发调用所有下载器
5. 返回符合查询条件的活跃种子

**关键代码**:
```python
@router.get("/active-torrents")
async def get_active_torrents(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    # 查询条件...
):
    # 1. 从数据库获取符合条件的 hash 列表
    # 2. 从下载器 API 获取实时速度
    # 3. 过滤出符合查询条件的活跃种子
    # 4. 分页返回
```

---

## ⏭️ 下一步行动

### 优先级顺序

1. **立即**: 创建 `torrent_speed.py` 文件
2. **然后**: 实现速度接口逻辑
3. **然后**: 注册路由到 `torrents.py`
4. **最后**: 测试后端接口

---

## 🎯 关键上下文

### 技术决策

1. **虚拟分页**: 前端智能合并活跃/非活跃种子
2. **1秒轮询**: 仅查询有速度的种子（>1KB/s）
3. **查询优先**: 复合条件查询优先级高于速度排序

### 权衡与理由

- ❌ 未采用: 后端合并分页（更复杂）
- ✅ 采用: 前端虚拟分页（已有查询逻辑）

### 风险与缓解

- 风险: 1秒轮询导致下载器过载
- 缓解: 限制并发、添加超时、失败跳过

---

## 📊 性能目标

| 指标 | 目标 |
|------|------|
| API 响应时间 | < 200ms |
| 前端轮询间隔 | 1 秒 |
| 内存增长 | < 20MB/h |
| 下载器 CPU | < 30% |

---

## 🧪 待测试场景

1. 有查询 + 有活跃（25活跃，分页20）
2. 有查询 + 无活跃（0活跃）
3. 无查询 + 有活跃（50活跃）
4. 无查询 + 无活跃（0活跃）
5. 活跃 < 每页（15活跃，分页20）
6. 活跃 = 每页（20活跃，分页20）
7. 活跃是倍数（40活跃，分页20）
8. 查询结果为空

---

## 📁 相关文件

### 规范文档
- `PLANS/v1.0.4.md` - 功能详细规范
- `AGENTS.md` - 代理工作流
- `feature_list.json` - 功能状态

### 代码文件
- `BtDeck/app/api/endpoints/torrent_speed.py` - 待创建
- `BtDeck/app/api/endpoints/torrents.py` - 待修改
- `BtDeck_fronted/src/api/torrents.ts` - 待修改
- `BtDeck_fronted/src/views/torrents/index.vue` - 待修改

---

## 🔍 快速恢复命令

```bash
# 查看当前功能状态
cat feature_list.json | jq '.features[] | select(.status == "in-progress")'

# 查看最近进度
tail -50 progress.md

# 验证环境
./init.sh

# 启动后端
cd BtDeck && python -m uvicorn app.main:app --reload --port 5001

# 启动前端
cd BtDeck_fronted && npm run serve
```

---

## ⚠️ 注意事项

### Git 提交规范

**前后端分离**:
```bash
# 后端
cd BtDeck/
git add . && git commit -m "feat: xxx"

# 前端
cd BtDeck_fronted/
git add . && git commit -m "feat: xxx"
```

**禁止**: 在项目根目录提交

### 代码规范

- 后端: 遵循 `BtDeck/CLAUDE.md`
- 前端: 遵循 `BtDeck_fronted/CLAUDE.md`
- Vue 2 Options API 风格

---

**最后更新**: 2025-01-22
