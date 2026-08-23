# 主机能力矩阵与 Android 降级（Phase 1.7 基线）

> 对应计划: `PLANS/dual-mode-client.md` 第 2 节"主机能力"行与第 4 节条目 7。
> 支持级别是**产品决策基线**；API/UI 的"一致降级"（同一能力在 API 响应、
> 设置页、任务列表三处显示相同状态）在 Phase 4 移动 UI 中落地，
> 本文先行冻结级别定义与判定来源。

## 1. 支持级别定义

| 级别 | 含义 | UI 要求 |
|---|---|---|
| `supported` | 全功能可用 | 正常展示 |
| `degraded` | 受限可用（列出限制） | 展示限制说明 |
| `unsupported` | 该主机形态不提供 | 入口隐藏/置灰 + 说明，禁止报错式暴露 |

## 2. 能力矩阵

| 能力 | 桌面/NAS/服务器 | Android 服务端模式 | 判定来源（代码事实） |
|---|---|---|---|
| 下载器管理/增删改/连接测试 | supported | supported | TCP probe 统一后无 ICMP 依赖（Phase 1.1） |
| 种子 CRUD/同步/删除/回收站 | supported | supported | — |
| Tracker 管理/关键词/重宣告 | supported | supported | — |
| 高级搜索/查询模板 | supported | supported | — |
| 审计日志 CSV/Excel 导出 | supported | supported（Excel 已 openpyxl 直写，Phase 1.3 去除 pandas/numpy） | — |
| **自定义脚本执行（cron task_type=4）** | supported（`BTDECK_ALLOW_CUSTOM_SCRIPTS` 默认 False） | **unsupported** | W2 已删除 exec 引擎，枚举层拦截；Android 壳不启用开关 |
| **宿主文件系统任意路径**（路径维护/孤儿清理根） | supported | **degraded**：仅 app-private + SAF 授权目录 | 路径注入见 `config-and-paths.md`；扫描根来自种子 save_path |
| SAF 文件选择（下载/上传 .torrent） | supported（原生文件对话框） | degraded：仅 SAF 授权 URI 可访问 | Phase 2/3 壳工程实现 |
| 种子文件下载/上传 | supported | degraded（仅授权目录） | 同上 |
| 系统通知 | 前端轮询/站内通知 | degraded：FGS 通知 + 站内通知；系统推送不在范围 | Phase 3 |
| **shell 依赖能力**（bash/PowerShell/cmd 脚本） | supported | **unsupported** | Android 无宿主 shell 契约；矩阵冻结时点后端已无 shell 调用（ping 子进程已随 Phase 1.1 移除） |
| 定时任务（cron_executor 调度） | supported | degraded：Doze 下不保证准点；任务列表显示"可能延迟" | Phase 5 设备验收校验 |
| 本地服务端（uvicorn） | supported | supported（临时定位，FGS 生命周期约束） | Phase 3 |
| 常驻 7×24 服务端 | supported（推荐部署形态） | **unsupported**（产品边界，见计划第 1 节） | 定位声明，非技术判定 |

## 3. 判定与暴露方式（设计冻结，Phase 4 实现）

1. 能力判定以**主机形态**为轴（desktop / android-server / companion），
   不按 UA 猜测（计划第 5 节明确"不以 UA 自动识别作为唯一模式依据"）。
2. 后端在启动时按注入的环境（`BTDECK_PLATFORM` 等）生成 capability 集合，
   经设置/任务列表 API 一并下发；前端三处展示同一来源，避免各自判断漂移。
3. `unsupported` 能力的 API 返回业务错误码（而非 500），消息中说明
   "当前主机形态不支持该能力"。
4. 任何新增后台能力必须在本文登记级别后才允许进入移动 UI。

## 4. 变更记录

- 2026-08-23：初版（Phase 1.7 基线冻结）。API/UI 一致降级与前端组件改造
  登记在 `feature_list.json` v1.0.6-dual-mode-client.5（Phase 4）。
