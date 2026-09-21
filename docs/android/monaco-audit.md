# Monaco 前端资源审计（Phase 1.6）

> 对应计划: `PLANS/dual-mode-client.md` 第 2 节"Monaco"行与第 4 节条目 6。
> 原则：以真实构建产物与首屏引用为依据，不预设"高级搜索编辑器"存在，
> 不把没有收益的改动列为门禁。

## 1. 审计数据（2026-08-22 构建产物，前端源码此后未变更）

首屏（`dist/index.html` 实际引用，仅两个 chunk）：

| chunk | 体积（未压缩） | 说明 |
|---|---|---|
| `assets/js/chunk-vendors.<hash>.js` | 1,060,068 B (~1.06 MB) | 第三方依赖合集 |
| `assets/js/app.<hash>.js` | 75,059 B (~75 KB) | 应用入口 |

Monaco 实际落点：

| 资源 | 体积 | 加载时机 |
|---|---|---|
| `assets/js/849.<hash>.js`（含 "monaco" 标识 676 处，确证为 monaco 主 chunk） | 2,940,642 B (~2.94 MB) | **异步**：仅任务页编辑器初始化时经动态 `import('monaco-editor')` 拉取 |
| `dist/{editor,ts,json,css,html}.worker.js`（dist 根目录） | 按需 | monaco worker，编辑器实例化时才加载 |

结论：**Monaco 零首屏成本**。index.html 不引用任何 monaco 产物；
`views/tasks/index.vue` 是路由级懒加载 chunk（`tasks.<hash>.js` 106 KB，也不在首屏），
其内部 `components/tasks/MonacoEditor.vue` 对 `monaco-editor` 采用
`await import(...)` 动态导入（L106），monaco 主体被隔离进独立异步 chunk。

## 2. "高级搜索编辑器"核查

全仓 `monaco` 命中逐项核对：除任务页编辑器外，其余全部是 CSS 字体族
（`font-family: Consolas, Monaco, monospace` 等，分布于 torrents/orphan-files/
recycle-bin/ConditionValueInput/SizeRangeFilter/AdvancedSearchBuilder）。
**不存在使用 Monaco 的高级搜索编辑器**——计划提醒正确，无需为其做任何处理。

## 3. 本次唯一改动：删除死组件

`frontend/src/components/MonacoEditor.vue`（顶部 `import * as monaco from
'monaco-editor'` 静态导入版）**全仓零消费方、零测试引用**（唯一活跃实现是
`components/tasks/MonacoEditor.vue` 懒加载版）。已删除：
- 收益：消除未来误 import 静态版导致 monaco 进入首屏/共享 chunk 的风险；
- 无风险：无引用即无构建影响，typecheck/lint 不涉及未引用文件。

## 4. 决策：webpack plugin 与组件层均不再改动

`vue.config.js` 的 `MonacoWebpackPlugin`（languages: javascript/typescript/
css/html/json/python）维持现状：

1. 当前懒加载已经达成"首屏零成本 + 按需 worker"的目标，plugin 改动无新增收益；
2. 语言清单（6 种）与编辑器功能匹配，裁剪语言只影响 849 chunk 体积，
   不影响首屏——除非未来任务编辑器体积成为移动端可感知问题（M2 复评），
   否则不动。

## 5. 关联遗留（非本审计决策范围）

- dist 体积 54 MB 主要来自 sourcemap（如 `ts.worker.js.map` 未压缩 ~13 MB 级），
  属桌面打包体积遗留项（2026-08-19 已登记）：关 `productionSourceMap` 或
  打包前剔除 `.map` 可显著缩小 exe；与安卓伴侣模式无关（伴侣加载服务端
  dist，不进 APK）。
