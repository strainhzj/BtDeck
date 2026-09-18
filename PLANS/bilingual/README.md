# 桌面双语 P0 盘点产出（desktop-bilingual-20260918.p0）

> 生成：2026-09-18（P0 静态盘点批）
> 上游计划：[PLANS/desktop-bilingual.md](../desktop-bilingual.md)
> 授权边界：本轮仅文档与静态脚本产出，不改业务代码、不安装依赖、不提交 Git。

## 文件索引

| 文件 | 内容 |
|---|---|
| [routes-inventory.md](./routes-inventory.md) | 全部桌面路由 / 页面 / 弹窗 / 状态清单 + M1 可达范围划定 |
| [p1-i18n-decision.md](./p1-i18n-decision.md) | P1 依赖选型与维护风险记录（vue-i18n@8.28.2）+ 落地范围与验证 |
| [copy-catalog.md](./copy-catalog.md) | 文案去重规模、分组分布、键命名方案、工作量重估（明细数据在 copy-catalog.json） |
| [copy-catalog.json](./copy-catalog.json) | 机器可读全量文案目录（zh / count / group / m1 / locations） |
| [error-contract.md](./error-contract.md) | 错误契约清单：现有架构、M1 失败路径样例、reasonCode 提案 |
| [system-content.md](./system-content.md) | 系统内容清单：查询/设置预设身份与迁移方案、通知事件、时间约定、生成契约链 |
| [terminology.md](./terminology.md) | 术语表（含「辅种」等经用户确认的定名） |
| [p0_extract.py](./p0_extract.py) | 文案提取脚本（可重跑，口径见文件头注释） |

## 维护约定

- 文案明细以 `copy-catalog.json` 为准，P1+ 落键时逐条标记（proposed_key / review 状态），不回填本目录以外的临时表格。
- M1 归属（core / partial / m2 / generated）为文件级判定；页面内部分范围的（如 settings 的 MCP/MoviePilot 页签）标 partial，精确到页签的划分由对应任务（P6）补齐。
- 本目录文档与源码漂移时，以源码为准并回改本文档；路线图（docs/roadmap）仅在 P1+ 改动源码后按 roadmap-maintain 流程同步。
