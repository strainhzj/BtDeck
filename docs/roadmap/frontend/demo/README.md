# frontend/demo — 静态展示 Demo

> 仅在 `VUE_APP_DEMO_MODE=true` 时由请求入口启用；真实构建继续走 Axios。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/demo/README.md`。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 类型与路由矩阵 | `src/demo/types.ts`（403 行；`DemoRouteDefinition` L11、`DEMO_ROUTE_MATRIX` L378） | Demo API 信封、分页、领域 fixture 类型、核心/扩展/只读/禁用路由矩阵和脱敏占位常量 |
| 脱敏 fixture | `src/demo/fixtures/index.ts`（790 行；`DEMO_FIXTURE_BUNDLE` L770） | 固定演示用户、下载器、种子、Tracker、任务、日志、回收站、孤儿文件和模板数据；主机使用 `.example.invalid`，路径使用 `/demo/*` |
| fixture 说明 | `src/demo/fixtures/README.md` | 字段分组、安全边界、重置和演示脚本说明 |
| 内存状态仓库 | `src/demo/demo-store.ts`（802 行；`DemoStore` L176、singleton L802） | 提供分页/筛选、有限 CRUD、种子状态、通知、模板、任务、关键词池和孤儿文件本地状态突变，禁止持久化真实业务数据 |
| 请求分流 | `src/demo/demo-request.ts`（1002 行；`handleDemoRequest` L348、`demoRequest` L992） | 按 method + path 集中返回 API 信封、Blob、降级响应和特殊页面契约，不发真实网络 |
| Demo 配置 | `src/demo/config.ts`（21 行） | Demo 开关、固定本地会话和重置事件 |
| Demo 构建入口 | `package.json` / `.env.demo` / `Dockerfile.demo` / `nginx.demo.conf` | 一键生成静态 `dist`，可用 zip 或不依赖后端 upstream 的 Nginx 容器交付 |

## 关键约定

- 分页统一返回 `list` / `total` / `pageSize`，外层统一为 `{ status, msg, code, data }`。
- Demo 请求不回退到 Axios；未覆盖路径返回可读降级结果，业务错误/Blob 仍保持调用方语义。
- 业务数据只在内存中突变；页面刷新或 Demo 顶部“重置数据”恢复 fixture，不写 Cookie/localStorage 中的真实凭据。
- 所有外部主机、文件路径和导出路径均为保留占位值；文件系统、脚本、Cron、Tracker 网络和真实认证不执行。
