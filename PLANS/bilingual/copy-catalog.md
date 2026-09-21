# 文案去重目录与工作量重估（P0）

> 生成：2026-09-18；明细数据：[copy-catalog.json](./copy-catalog.json)（机器可读，P1+ 落键的底账）。
> 复现：`cd PLANS/bilingual && python3 p0_extract.py`

## 1. 口径与限制

- 范围：`frontend/src` 的 `.vue/.ts/.js`，**排除** `views/mobile`、`demo`、`__tests__`、`tests`、`*.spec.*`、icons；整行注释不计。
- **限制（重要）**：
  1. 行内尾注释无法与代码剥离——少量注释片段混入（如 `速度轮询]`），P1 落键时逐条人工剔除，JSON 保留原始数据不删。
  2. 模板插值句子被拆成片段（`共 {{total}} 项` → `共`/`项`/`个种子`）——**片段数高估真实键数**；真实键数以 P1 按"整句 + 插值参数"重组为准。
  3. 去重按字符串字面聚合；同形异义（如「删除」在不同危险等级确认框）在落键时按语义拆键（主计划 §3.1：危险操作不用模糊通用文案）。
- 后端中文（msg/通知/预设）不在本 JSON，见 error-contract.md 与 system-content.md。

## 2. 规模总览

| 口径 | 唯一文案 | 原始命中 |
|---|---:|---:|
| 桌面全量 | **3088** | 5138 |
| M1 core（文件级） | **987** | 1955 |
| M1 partial（部分范围） | **588** | 936 |
| M2 批次 | 1491 | 2213 |
| 生成文件（不直译） | 22 | 34 |

M1 core+partial 合计 1575 唯一 / 2891 命中；去除 partial 中 M2 域标签（types/store 中任务、日志枚举）与注释噪声，**P1 实际需落键约 1300～1450 条**（含插值重组后的整句键）。

### 分组分布（唯一 / 命中）

| 组 | 全量 | M1 core+partial |
|---|---|---|
| torrent | 832 / 1603 | 663 |
| tasks | 523 / 865 | 67（types 枚举为主） |
| downloader | 473 / 708 | 181 |
| tracker | 231 / 308 | 0 |
| orphanFiles | 212 / 301 | 0 |
| settings | 196 / 239 | 196 |
| common | 169 / 278 | 134 |
| logs | 96 / 148 | 0 |
| errors | 86 / 249 | 86 |
| navigation | 71 / 139 | 71 |
| recycleBin | 66 / 92 | 66 |
| search | 47 / 66 | 47 |
| dashboard | 29 / 63 | 29 |
| auth | 18 / 19 | 18 |
| notifications | 17 / 26 | 17 |
| other | 22 / 34 | 0 |

高频 M1 样例（count / 组 / 文案）：45 个 · 45 确定 · 30 删除 · 26 拖拽调整列宽，双击恢复默认 · 22 操作 · 21 删除失败 · 18 下载器 · 17 添加时间 · 16 条件组 · 15 吗？ · 14 网络错误 · 13 暂停 · 11 操作失败 · 10 连接失败……

### 文件热点（命中数，M1 加粗）

`views/tasks/index.vue` 391（M2）· `views/orphan-files/index.vue` 337（M2）· **`views/torrents/index.vue` 310** · `TraditionalView.vue` 200（M2）· `CronEditor.vue` 155（M2）· `audit.vue` 146（M2）· `PythonClassSelector.vue` 143（M2）· **`DownloaderSettingsDialog.vue` 125** · **`recycle-bin/index.vue` 123** · **`settings/index.vue` 121** · `reannounce-config.vue` 103（M2）· `MoviePilotPanel.vue` 101（M2）· **`CompactTable.vue` 98** · **`utils/torrentBatch.ts` 97** · `PathMappingTab.vue` 90（M2）

## 3. 键命名与组织方案（P1 固化输入）

- 目录：`frontend/src/i18n/`，按 `locales/zh-CN/*.ts` + `locales/en/*.ts` 同构分组（组名即上表：common/auth/navigation/dashboard/downloader/torrent/search/tracker/recycleBin/orphanFiles/tasks/logs/settings/notifications/errors），语言入口 `index.ts`。
- 键：语义点路径，如 `torrent.delete.level3.confirm`、`downloader.test.failed.auth`；**禁止**中文原句/行号/动态拼键；中英键集合与插值参数一致（自动化检查项，主计划 §7）。
- 插值：Element/Vue 模板内 `{{ }}` 改 `$t('key', { n, size })`；复数用 vue-i18n 的 pluralization（0/1/多）。
- 类型：键名联合类型由 zh 根对象 `keyof typeof` 推导，杜绝魔法串（禁 any 约束不变）。
- 非组件层（router meta、formatters、request 拦截器、store）统一从 i18n 模块取同源 `t()`，禁止各自引库。

## 4. 特殊对象

1. **`router.ts` meta.title（71 条 navigation）**：改为 `titleKey`（或按 `name` 映射表），面包屑/侧栏/document.title 统一走 `$te + $t`；`/m/*` 移动标题键**保留中文现值不动**（移动英文化另行立项）。
2. **`contracts/advancedSearch.generated.ts`（22 条）**：生成产物禁直改；中文标签源在 `backend/app/contracts/advanced_search_contract.json`（39 处中文）与 `components/torrents/advancedSearchFields.ts`，改动走「源 → `frontend/scripts/generate-advanced-search-contract.js` 再生成」（详见 system-content.md §5）。
3. **types/ 标签枚举（169 条）**：`TASK_TYPE_LABELS` 等常量映射改为按当前语言取值，保持键（英文枚举值）不变，消费端渐进迁移。
4. **utils/formatters.ts**：相对时间「刚刚/X分钟前/X小时前/X天前」、时长 d/h/m/s、大小 1024 换算——换算与语义不变，仅措辞走 i18n；日期集中格式化（主计划 §3.2）。

## 5. 工作量重估（对主计划 §8 的数据修订）

| 项 | 原估（M1） | 重估（M1） | 依据 |
|---|---|---|---|
| 翻译与术语审校 | 4～6 | 4～7 | 约 1300～1450 实键（片段重组后），插值句占比中等 |
| 代码改造 | 13～20 | 12～19 | 热点集中（前 10 文件占 M1 命中 45%+），机械提取可脚本辅助 |
| 测试与视觉验收 | 6～10 | 6～10 | 不变（依赖矩阵而非文案量） |
| **合计** | 23～36 | **22～36** | 区间上限微降、下限微降；置信度仍「中等」 |

M2 增量文案约 1500 唯一（含 tasks/orphan/logs/tracker 四大块），原 M2 追加 10～16 人日估计维持。**本重估为静态数据推算，非实际工时**；P1 完成落键后再次校准。
