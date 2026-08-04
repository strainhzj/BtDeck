# perspectives — 跨切专题索引

> 跨分支的横向主题：调用链、约定、风险、测试覆盖。本目录**只放索引与摘要**，完整论述链接到已有文档，避免双份真相。
> 定位方式：`Grep -i <功能词> docs/roadmap/perspectives/README.md`，命中行即含专题文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 架构调用链 architecture | [architecture.md](./architecture.md) | 5 条关键业务流程的调用链索引（入口 → 数据层） |
| 约定 conventions | [conventions.md](./conventions.md) | 代码约定索引（链接到 backend/frontend docs/constraints/，不复制条款） |
| 风险技术债 risks | [risks.md](./risks.md) | 孤儿文件、入口分散、双 SPA fallback、文档/代码漂移等 |
| 测试覆盖 test-coverage | [test-coverage.md](./test-coverage.md) | 源文件 ↔ 测试文件覆盖矩阵 |

## 单一真相原则

本目录遵循提示词"避免双份真相"原则：

- **架构论述**（配置双轨、迁移双轨、定时任务隔离三方案）已在 `backend/docs/architecture-deep-dive.md`（901 行）完整论述 → 本目录只放调用链索引 + 链接
- **代码约定**（API 响应格式、数据库迁移、下载器连接等）已在 `backend/docs/constraints/`（6 文件）和 `frontend/docs/constraints/`（6 文件）完整定义 → 本目录只放索引表
- **技术债**：已在 `backend/docs/tech-debt-lint-baseline.md`、`backend/docs/style-and-contract-audit.md` 等论述的，本目录只补充路线图视角的发现（如孤儿文件清单）

## 相关文档

- 架构深度分析：[../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md)
- 架构独立审查：[../../backend/docs/architecture-review.md](../../backend/docs/architecture-review.md)
- 后端约束集：[../../backend/docs/constraints/](../../backend/docs/constraints/)
- 前端约束集：[../../frontend/docs/constraints/](../../frontend/docs/constraints/)
- 技术债基线：[../../backend/docs/tech-debt-lint-baseline.md](../../backend/docs/tech-debt-lint-baseline.md)
