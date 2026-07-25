# tests — 测试

> 后端 pytest（96 个 test_*.py，按子目录组织；另有 conftest.py/__init__.py 等支持文件 16 个，全 .py 共 112）+ 前端 jest unit。测试覆盖矩阵见 [../perspectives/test-coverage.md](../perspectives/test-coverage.md)。

## backend/tests/（96 个 test_*.py + 16 个支持文件）

### 顶层

| 文件 | 用途 |
|------|------|
| `__init__.py` | 包标识 |
| `conftest.py` | pytest 全局 fixture（DB session、测试客户端、种子数据等） |
| `panic_fixes_verification.py` | panic 修复验证脚本 |
| `test_architecture_constraints.py` | 架构约束测试（如禁止某些反模式） |

### 子目录（按源码分支镜像）

| 子目录 | 对应源码分支 | 说明 |
|--------|-------------|------|
| `api/` | `app/api/` | API 层测试 |
| `auth/` | `app/auth/` | 认证测试 |
| `core/` | `app/core/` | 基础设施测试 |
| `downloader/` | `app/downloader/` | 下载器测试 |
| `endpoints/` | `app/api/endpoints/` | 端点集成测试 |
| `enums/` | `app/enums/` | 枚举测试 |
| `models/` | `app/models/` | ORM 模型测试 |
| `repositories/` | `app/repositories/` | 仓储测试 |
| `services/` | `app/services/` | 服务层测试 |
| `services/tag_adapters/` | `app/services/tag_adapters/` | 标签适配器测试 |
| `tasks/` | `app/tasks/` | 定时任务测试 |
| `utils/` | `app/utils/` | 工具测试 |

### 运行命令

```bash
cd backend && pytest                          # 全量
cd backend && pytest tests/services/ -v       # 按目录
cd backend && pytest tests/api/               # API 层（34 个测试）
```

## frontend/tests/

| 子目录 | 说明 |
|--------|------|
| `unit/` | jest 单元测试 |

### 组件内嵌测试

部分组件有内嵌 `__tests__/`：
- `frontend/src/components/torrents/__tests__/`（4 个 spec，1484 行）
  - `AdvancedMultiSelect.performance.spec.ts`（466 行，性能测试）
  - `AdvancedMultiSelect.spec.ts`（348 行）
  - `AdvancedSearchBuilder.spec.ts`（506 行）
  - `ConditionValueInput.spec.ts`（164 行）

### 运行命令

```bash
cd frontend && npm run test:unit    # jest
```

---

## 测试覆盖观察

- **后端测试组织良好**：112 个测试文件按源码分支镜像组织（api/auth/core/downloader/endpoints/...），与路线图分支划分一致
- **前端测试集中在核心组件**：`components/torrents/` 的搜索/多选组件有完整单测（含性能测试），其他组件测试覆盖较薄
- **架构约束测试**：`test_architecture_constraints.py` 是防退化机制（自动检测反模式）
- 详细覆盖矩阵（源文件 ↔ 测试文件对应）见 [../perspectives/test-coverage.md](../perspectives/test-coverage.md)

## 第三层详情

- 测试分支通常不需要第三层方法签名详情；如需要，可对 `conftest.py`（fixture 体系）做专项分析。
