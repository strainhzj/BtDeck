# 术语表（P0）

> 状态：初版。审校模式：**代理初译 + 用户审校**（2026-09-18 用户确认默认模式）；标 ✅ 的为已确认定名，标 ⏳ 的为待用户复核。
> 规则：术语一经定名，P1～P7 全程一致；英文键与 UI 用词都以此表为准；与 qBittorrent / Transmission 官方英文 UI 冲突时**优先向客户端官方用语看齐**（英语用户的心智模型来自下载器本身）。

## 1. 已确认（用户 2026-09-18 确认业务含义）

| 中文 | 英文 | 说明 |
|---|---|---|
| 辅种 | cross-seed（动词 cross-seeding）✅ | 业务含义经确认：同一份数据在多个站点/Tracker 上做种。「辅种 N」→ `Cross-seeds: N`；不译作 auxiliary seed（易误读为辅助节点） |

## 2. 核心域名词（⏳ 待复核）

| 中文 | 提案英文 | 说明 |
|---|---|---|
| 种子 | torrent | 全站统一；「任务」另译（下条） |
| 任务（下载器中的种子条目，qB 语境） | torrent | qBittorrent 官方用 torrent；仅在「批量添加任务」等歧义处用 `transfer` 说明 |
| 任务（BtDeck 定时任务） | scheduled task | 与下载器任务严格区分；定时任务页 M2 |
| 数据文件 | data files | 四级删除语义中「下载数据」 |
| 下载器 | downloader | BtDeck 自有概念 |
| 做种 | seeding | |
| 下载中 | downloading | |
| 校验 / 强制校验 | recheck / force recheck | qB 官方 force recheck；TR 官方 verify |
| 汇报 / 重新汇报 | reannounce / force reannounce | qB 官方 reannounce；「汇报配置」`Reannounce settings` |
| 回收站 | recycle bin | BtDeck 自有概念 |
| 隔离区（孤儿文件） | quarantine | 孤儿文件域 M2，但术语先定 |
| 彻底删除 / 永久删除 | purge / permanently delete | 四级删除 L4 与回收站操作区分场景；动作按钮统一 `Delete permanently`，名词 purge 用于工程语境 |
| 孤儿文件 | orphan file(s) | |
| 路径映射 | path mapping | |
| 种子转移 | seed transfer | BtDeck 自有功能名（转移下载器） |
| 修改路径 | change location | qB 官方「Set location」→ 动作用 `Set location` 更贴近客户端习惯，⏳ 倾向后者 |
| 标签 / 分类 | tag / category | qB 官方同词 |
| Tracker 异常 | tracker error / tracker issue | 列表标签；原始诊断保留原文 |
| 关键词看板 | keyword board | Tracker 管理域 M2 |
| 查询模板 | query template / saved search | ⏳ 倾向 saved search（英语生态惯用），按钮 `Save search` |
| 高级搜索 | advanced search | |
| 系统预设 | built-in preset | 区别于用户自建 |
| 能力 | capability | 平台能力门控语境，不译 feature（避免与功能混淆） |
| 双因素认证 | two-factor authentication (2FA) | |
| 强制改密 | forced password change / must change password | 守卫语境 `must change password` |
| 操作日志 | audit log | |
| 演示模式 | demo mode | |
| 伴侣模式（App） | companion mode | 移动壳语境，仅说明文案使用 |

## 3. 动词与危险操作规范（⏳ 待复核）

| 中文场景 | 规范 | 理由 |
|---|---|---|
| 删除（从下载器移除种子） | remove | qB 官方 DeleteTorrents 实为移除语义；按钮 `Remove`，避免与文件删除混淆 |
| 删除（磁盘数据一起删） | delete (with data files) | 确认框明示 `...and permanently delete its data files` |
| 移除（列表项/标签/文件行） | remove | 非破坏性 |
| 删除（下载器/模板/规则等记录） | delete | |
| 恢复（回收站） | restore | |
| 清空 / 清理 | empty (recycle bin) / clean up | 隔离区清理用 `purge`⏳ |
| 忽视（孤儿文件） | ignore | |
| 暂停 / 恢复（种子） | pause / resume | qB/TR 官方 |
| 开始 / 强制开始 | start / force start | |
| 测试（连接） | test connection | |
| 确认 / 取消 | Confirm / Cancel | 危险确认框必须完整句，不用裸 OK |

**危险操作红线（主计划 §3.1）**：四级删除各等级必须语义独立成键，禁止共用模糊文案（R01～R04）；等级数字 + 影响对象 + 不可恢复性三要素齐备；取消零副作用。

## 4. 「辅种」跨端一致性

`auxiliarySeedCount`（后端字段）/「辅种 N」（移动端卡片）/「辅种数量」——英文统一 `cross-seeds`；字段名不改（API 语义冻结），仅展示层映射。移动端当前无英文化计划，但字段消费逻辑共用，避免两套译名。

## 5. 维护

- 新术语先入本表再进键值；PR 涉及新概念时在对应任务 evidence 里回链本文件。
- 英文最终审校责任：用户（关键危险操作 R01～R06 逐条人工签认后才过 M1/M2 门禁）。
