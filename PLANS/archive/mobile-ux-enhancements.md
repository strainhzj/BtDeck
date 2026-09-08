# PLANS: 移动端 UX 增强（mobile-ux-enhancements-2026-08-28）

> **范围**: P0+P1（经 3 子代理独立审查修订），只动 `frontend/src/views/mobile/` + `layout/mobile/` + 桌面 `speedPolling.ts` 增量扩展；后端零改动。
> **状态**: 已实施完成（2026-08-28），验证见文末。

## 背景

移动端实测（iPhone 12 模拟器，17 张截图巡检 + 源码走查）发现的核心缺口：
种子卡片无实时速度、页面无自动刷新、Tab 纯文字、按钮式分页、二级页无返回导航、
通知 50 条封顶、空状态无引导、汉堡触控区 36px 偏小、任务删除按钮紧邻常规操作。

## 审查修订（3 子代理独立审查后的关键决策）

1. **复用而非新建轮询 mixin**：`speedPolling.ts` 增量扩展 `speedPollIntervalMs`（默认 1000，桌面零变化）+ `startSpeedPolling(immediate = true)`；移动端 `immediate=false` 首轮延迟一个周期——同步首拉会击穿 mobile-torrents.spec 的 mock 工厂并打破 dashboard 调用计数断言。
2. **返回按钮弃用 history.back()**：移动导航以 replace 单栈为主，back 会弹回登录页/出站；改固定回退映射（详情→种子列表、下载器设置→下载器、关键词搜索→看板、其余→仪表盘）。
3. **二级页 ← 与汉堡并存**：抽屉是全功能唯一导航面，不能在二级页失联。
4. **速度合并补未命中清零**：active 接口只含速度>0 的种子，停止的种子会从快照消失，行上速度必须清零防冻结。
5. **通知静默刷新与翻页互斥**：已翻页时整表替换会把用户重置回第 1 页，跳过本轮只同步未读角标。
6. **v-infinite-scroll 可用性已验证**：`html/body/#app height:100%` 链条下 `.mobile-content` 是真实滚动容器，Element 指令按 computed overflow 上溯正确挂载。

## 实施清单（6 子任务）

| # | 内容 | 文件 |
|---|------|------|
| 1 | SpeedPollingMixin 增量扩展 | `views/torrents/mixins/speedPolling.ts` + `speed-polling.spec.ts` |
| 2 | 布局壳：Tab 图标/二级页←返回/44px 触控区/未读轮询 hidden 门控 | `layout/mobile/index.vue` + `mobile-shell.spec.ts` |
| 3 | 种子列表：10s 速度轮询合并（复用 buildSpeedSnapshot+traditionalTorrentIdentity）、无限滚动、返回顶部浮标、暂停/恢复乐观状态、空态 CTA（?create=1 直达新增） | `views/mobile/torrents.vue`、`views/mobile/downloader.vue` + 两 spec |
| 4 | 仪表盘 15s / 通知 30s 静默刷新；通知按 id 去重分页追加；下载器空态 CTA；两页移除 m-refresh | `views/mobile/dashboard.vue`、`notifications.vue` + 两 spec |
| 5 | 详情页轮询迁移 mixin（5s+后台暂停，立即首拉语义保留）；任务删除按钮分隔；下拉刷新指示条跳变修复（手势内回顶重置起点） | `torrent-detail.vue`、`tasks.vue`、`mixins/pull-to-refresh.ts` + 两 spec |
| 6 | e2e：查询模板存量失效断言修正 + 二级页返回/Tab 图标用例 | `tests/e2e/mobile/mobile-interactions.spec.ts` |

## 验证（2026-08-28）

- Jest：**84 suites / 1214 tests passed**（基线 1169，净增 45 断言）
- `tsc --noEmit` 通过；`npm run lint`（contract:check + ESLint --max-warnings 0 + vuex action 检查）零错误
- 已知限制：速度行/无限滚动的真机视觉验证需接入真实下载器（本地空库）；e2e 二级页返回用例待 `npm run test:mobile` 环境复核

## 明确不做（后续项）

- ETA 显示（需后端 active-torrents 增字段）
- 详情返回列表的滚动位置/已加载页恢复（keep-alive）
- Android WebViewActivity 补 onPause/onResume + 前端 pagehide 兜底
- 二级页左边缘右滑保持开抽屉（不改返回）
- 其余 7 个移动页的手动刷新/加载更多保留（有意分期）
