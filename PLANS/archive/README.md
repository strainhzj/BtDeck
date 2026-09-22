# 已归档计划索引

> **归档时间**: 2026-09-08（计划盘点，见 progress.md 当日记录）
> **归档原则**: 对应 feature 已 done，或计划整体过时不再具有开发价值。文件内容保持归档时原样，仅路径移入本目录。
> 活跃计划见 [../README.md](../README.md)。

## 已完成归档（feature 已 done）

| 计划 | 主题 | 对应 feature（状态） |
|------|------|----------------------|
| [v1.0.4.md](./v1.0.4.md) | 实时速度监控 | `v1.0.4`（done） |
| [v1.0.5.md](./v1.0.5.md) | 查询模板系统 | `v1.0.5`（done） |
| [v1.0.5-audit.md](./v1.0.5-audit.md) | 契约审计修复 | `v1.0.5-audit`（done） |
| [v1.0.6.md](./v1.0.6.md) | 孤儿文件管理 | `v1.0.6`（done）；双模式客户端后续见活跃计划 [dual-mode-client.md](../dual-mode-client.md) |
| [verified-bugfix-remediation.md](./verified-bugfix-remediation.md) | 8 项已验证问题修复 | `verified-bugfix-2026-08`（done） |
| [force-change-deadlock-fix.md](./force-change-deadlock-fix.md) | W9 强制改密路由死锁修复 | `force-change-deadlock-fix-2026-08-18`（done） |
| [mobile-ux-enhancements.md](./mobile-ux-enhancements.md) | 移动端 UX 增强 | `mobile-ux-enhancements-2026-08-28`（done） |
| [token-audit-fixes.md](./token-audit-fixes.md) | 令牌审计修复 | `token-refresh-race-fix-2026-08-18`（done） |
| [security-remediation.md](./security-remediation.md) | 安全修复（两轮对抗验证驱动） | `security-remediation-2026-08`（done） |
| [sync-resource-governance.md](./sync-resource-governance.md) | 同步任务资源治理与下载器 API 调度 | `sync-resource-governance`（done） |
| [release-artifact-equivalence-gate.md](./release-artifact-equivalence-gate.md) | v1.0.6 交付制品等价性与发布阻断门禁 | `release-artifact-equivalence-gate-2026-08-28`（done） |
| [sync-database-blocking-remediation.md](./sync-database-blocking-remediation.md) | 同步任务数据库阻塞与接口超时修复 | W1～W4 共九个 feature（全部 done）；G5 残余事项见下文 |

## 过时归档（不再具有开发价值）

| 计划 | 原主题 | 过时原因 |
|------|--------|----------|
| [v1.0.7.md](./v1.0.7.md) | 路径扫描增强 | 伪代码引用的 `app/services/path_mapping_service.py` 与 `PathMapping`/`PathMappingRule`/`PathTransferHistory` 模型均不存在（真实实现在 `app/core/path_mapping.py`，且 path_mapping 为每下载器 JSON 字段）；"rules 转换路径"来源与现有 `downloader_path_scan` 已有能力重复 |
| [v1.1.0.md](./v1.1.0.md) | 自动化运维 | 核心交付已被 `app/data/default_scheduled_tasks.py`（14 个默认任务全部默认启用，含自动孤儿清理/路径扫描/标签同步）+ `cron_executor` + 任务页事实性覆盖；计划内 AutomationService 与现有基建重复；前端示例使用 Vue 3 Composition API，违反仓库 Vue 2 Options API 强制约束 |

## 遗留事项（重启相关方向时从这里捡起）

- **v1.0.7 可回收价值（收窄后约半天～1 天）**：给 `app/tasks/scheduler/downloader_path_scan.py` 增加 `seed_transfer_audit_log.target_path` 作为路径发现来源，补"种子转移到新路径后、该路径尚无种子被同步进 `torrent_info`"的发现盲区；可顺带把 path_mapping 已知 external 路径并入去重集合。注意与孤儿扫描（orphan_files）的文件系统层范围边界。
- **sync 计划 G5 未关项**（开发部分已全部落地，以下为决策/运维残留）：
  - W5-1 Tracker 变化指纹：按数据决定实施或明确不实施；
  - W5-2 DBWriteQueue ADR：默认不做，需 7 天 WAL/指标数据支撑结论；
  - W5-3 PostgreSQL 演进计划重写：并入 [../v1.0.8.md](../v1.0.8.md) 重启时处理（2026-09-08 决策：数据库源变动暂缓）；
  - W5-4 feature_list/progress/handoff/constraints/roadmap 状态收口；
  - 生产 app.db 迁移、暂停/恢复演练与 30 轮基线归档待运维执行（见 `backend/docs/operations/sync-stopgap-runbook.md`）。
