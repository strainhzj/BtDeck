# mobile-ux-fixes-2026-09 — 手机端七问题修复批次

> **挂靠**: v1.0.6（feature_list 任务组 `mobile-ux-fixes-2026-09`） | **状态**: ✅ 已完成（2026-09-10）
> **性质**: 用户验收反馈修复（非新功能规划）；计划经独立子代理对抗性审查（APPROVE_WITH_AMENDMENTS，5 MAJOR/6 MINOR 全部修订吸收）

---

## 📌 用户问题与根因（全部经代码实证）

| # | 用户反馈 | 根因 |
|---|---------|------|
| 1 | 确认弹框未做手机适配 | 全部走 Element `$confirm`（MessageBox 420px 定宽主题类规则），零移动适配 |
| 2 | 高负载时伴侣模式请求失败（症状=页面红色 toast） | 瞬态失败（网络错误/网关 5xx）直接弹 toast，无自动重试。**本批为对症缓解**，负载根源（单 Worker SQLite 串行 + 容器 1C/1G）另行治理 |
| 3 | 种子页面响应慢 | mount 即拉 `/torrents/tracker-domains`（TrackerInfo 全表扫描）；长列表卡片无渲染减负；每行携带完整 tracker_info 数组 |
| 4 | 缺少查找重复任务、快捷操作高级功能 | 桌面已有全套（`POST /torrents/duplicates` + `same_content_only`/`single_error_only` + 快捷删重弹窗），手机页零入口 |
| 5 | app 不需要显示桌面版 | 移动壳 5 处可点入口 + 6 处文案（用户确认全部移除） |
| 6 | 伴侣模式连接后「版本未知·服务存活检查失败」 | `frontend/nginx.conf` `location /health` 前缀匹配静态返回纯文本 `"healthy\n"` 吞掉 `/health/live` → 安卓 HealthClient JSON 解析 null → 恰好渲染该文案（无 HTTP 码后缀，症状吻合）；TLS 示例配置回落 index.html 同症状 |
| 7 | 下载器新增/编辑未适配且无页签 | 手机页用旧 `DownloaderDialog`（60% 宽 6 字段无页签）；桌面已统一 `DownloaderSettingsDialog`（新增模式 downloader=null） |

## 🔧 实施记录

### F. 问题6 双端双修
- `frontend/nginx.conf`：`location /health` → `location = /health`（compose 健康检查 `wget /health` 精确命中不变）+ 新增 `location /health/` 代理后端；`deploy/nginx-tls.conf.example` 同款。
- 安卓 `HealthClient.kt`：`probeWithFallback`（主路径 HttpError 或 2xx 非 JSON 信封 → 回退 `/api/v1/health/*` 免认证别名；网络/TLS 错误不回退；回退失败保留主路径归因）；新增可注入 `HttpCall` 探测点（不新增 mockwebserver）。
- `backend/app/desktop_companion/health.py`：`_probe_endpoint_with_fallback` 同语义（与安卓端对齐）。
- **效果**：新部署 nginx 直通根路径；旧部署不更新 nginx 也靠客户端回退修好。

### A. 问题1 确认弹框
- `styles/index.scss` 全局 `@media (max-width:768px)`：`.el-message-box` 宽 `92vw !important`（覆盖 Element 主题类规则）+ 双钮等宽全宽 ≥40px 触控。一处覆盖全部 `$confirm` 调用点。

### B. 问题2 瞬态重试（缓解）
- `utils/request.ts`：幂等 GET 网络错误/502/503/504 静默重试 1 次（800ms，落响应拦截器内，首次失败不弹 toast）；超时（ECONNABORTED，20s 已过长）与写操作不重试；与 401 刷新重放（`_retried`）触发集不相交（`_transientRetried` 防循环）。

### C. 问题3 提速
- 后端 `/torrents/tracker-domains` 60s 进程内 TTL 缓存（单 Worker 安全；`reset_tracker_domains_cache` 测试钩子；新域名最多延迟 60s 出现）。
- 前端 tracker 域名候选懒加载（首展筛选面板才拉，失败下次展开重试）；下载器列表保留 mount（空态判断）。
- `getList` 新增 `with_trackers` Query（`torrent_helpers` `include_trackers` 跳过 tracker 批量预取+关键词池）；移动列表携带 false；详情页 `refreshBase` 全量回查补 tracker 明细。
- 卡片 `content-visibility:auto` + `contain-intrinsic-size: auto 148px`（长列表渲染减负）。

### D. 问题4 快捷操作
- 移动种子页「快捷」下拉（与桌面同语义）：查找重复任务（toggle，`getDuplicateTorrents`，skip/limit→1-based page/pageSize 换算，模式横幅+退出+空态口径）、辅种异常排查（`same_content_only`）、错误单种排查（`single_error_only`）、快捷删除重复种子（复用自包含 QuickDeleteDuplicatesDialog）。`reload()/fetchPage` 按模式分发（pull-refresh/终态刷新等一切 reload 路径自动走对）。
- QuickDeleteDuplicatesDialog 手机适配（custom-class + `@media ≤768 width:94% !important`，分组双列纵排，底部按钮全宽）；AdvancedMultiSelect 嵌套 popover（320/280px）按视口钳制（主弹层已有 max-width）。

### E. 问题5 桌面版入口全移除
- 顶栏「桌面版」、抽屉「完整桌面版」、抽屉「全部功能（桌面版页面）」分组、登录页「使用桌面版」、种子空态「去桌面版添加」全部删除；6 处脚注改「暂未在移动端提供」。
- **已知取舍（用户确认）**：「Tracker 汇报/测试」配置页自此移动端无导航入口（仅桌面浏览器 ≥768px 或 localStorage 桌面模式可达）；桌面侧栏切移动入口保留。
- ui-mode 偏好机制不变：≥768px 设备默认桌面版不受影响。

### G. 问题7 下载器新增/编辑
- 移动下载器页「新增」→ `/m/downloader/settings/new`、「设置」→ `/m/downloader/settings/:id`（编辑与设置合一）；`downloader-settings.vue` 支持 `id=new`（downloader=null 新增模式，速度/路径页签锁定与桌面一致）；种子页空态 CTA 直达 settings/new；`?create=1` 兼容落点保留。
- `DownloaderSettingsDialog` `:tab-position` 响应式（≤780 顶部横向滚动页签带图标+文字，宽屏左列不变，matchMedia 监听）；旧 `DownloaderDialog.vue` 确认零消费方后**删除**。

## ✅ 验证

- 后端：mypy/black/flake8 绿；`tests/api/test_torrent_list_api.py` 42 passed（TTL 缓存 2 例 + with_trackers 1 例新增）+ `tests/desktop_companion` 66 passed（health 21 例含回退 5 例，mock 改按 URL 分发）。
- 前端：lint 绿、typecheck 0 error、build 绿；全量 1495 passed（新增/改写：request-transient-retry 6、mobile-torrents 43、mobile-shell 34、mobile-downloader 11、mobile-downloader-settings 6、downloader-control-room-ui 27 改锚）。
- 安卓：`:app:testDebugUnitTest` HealthClientFallbackTest（5 例）+ HealthClientPinTest 全绿；未重出 APK。
- `./init.sh` 通过。

## ⚠️ 存量测试债（非本批引入，HEAD 即红）

`permission-guard` / `permission-force-change-deadlock` / `torrent-list-view-component` / `traditional-view-component` / `mobile-delete-level-dialog` 五套件在本批次前后均为 **12 failed / 88 passed 完全一致**（受控 stash 基线对照验证）；疑似环境/时序相关（Node 22），建议独立批次排查。

## 🚀 部署提示

- nginx 变更需重建 frontend 镜像才生效（`docker compose up -d --build`）；不重建时安卓/桌面伴侣客户端回退 `/api/v1` 别名同样修复。
- 安卓端改动需重出 APK 才携带 HealthClient 回退。
