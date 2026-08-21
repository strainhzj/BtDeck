# W9 强制改密路由死锁修复

> **性质**: 生产事故修复（verified-bugfix）
> **日期**: 2026-08-18
> **范围**: 前端路由/守卫 + 后端 /user/info 契约补全
> **状态**: 已实施，回归全绿

## 一、事故回顾（根因链，已由两端回归测试实证）

1. **触发层（后端）**: 部署含 W9 安全修复的版本后，`init_db`（`backend/app/database.py:185-192`）启动自检发现 admin 仍在用默认口令 "admin"（bcrypt 或旧 AES-ECB 格式均命中）→ `users.must_change_password` 置 1。
2. **延迟层（会话）**: 标志仅随登录响应下发（`login.py` token_data），存量会话靠 refresh token 存活最长 7 天——"部署后正常使用一段时间"的假象由会话寿命造成，重新登录那一刻症状爆发。
3. **死锁层（前端路由）**: 守卫（`permission.ts`）重定向目标与白名单均为父路径 `/settings`，而路由表中该父路由只挂 Layout 无 redirect，真实改密页挂在子路由 `/settings/index`：
   - 拦截落点 `/settings` 只渲染布局框架，内容区为 Vue 空占位 `<!---->`（白屏）；
   - 手动输入真实路径 `/settings/index`、点侧边栏菜单（生成完整子路径）都被白名单弹回；
   - 改密表单从代码层面不可达 → 标志无法清除 → 用户永久锁死。
4. **首导航缺口（双代理审查发现）**: 守卫 `roles.length === 0` 分支（登录后/F5 后首次导航）`await GetUserInfo()` 后无条件 `next()` 放行，不检查标志——强制改密用户首次导航会先落到业务页一次。

复现测试（事故时点）: `frontend/tests/unit/permission-force-change-deadlock.spec.ts`（断言旧 bug 行为 5 用例）、`backend/tests/api/test_w9_force_change_reproduction.py`（init_db 置位 4 用例）。

## 二、修复改动（6 处）

| # | 文件 | 改动 |
|---|------|------|
| 1 | `frontend/src/router.ts` | `/settings` 父路由加 `redirect: '/settings/index'`（对齐 `/torrents`、`/logs` 模式） |
| 2 | `frontend/src/permission.ts` | 重定向目标/白名单改用 `/settings/index`（白名单防御性保留 `/settings`）；**GetUserInfo 分支成功后同样检查标志拦截**（闭合首导航缺口）；拦截逻辑抽 `isForceChangeBlocked`/`forceChangeRedirect` 复用 |
| 3 | `backend/app/api/endpoints/cuser.py` | `get_user_info` 响应 `user.mustChangePassword` 实时下发（防御式读法与 login.py 一致，双前缀 `/user`+`/users` 同时生效） |
| 4 | `frontend/src/api/users.ts` | `UserInfoData` 加可选 `mustChangePassword?: boolean` |
| 5 | `frontend/src/store/modules/user.ts` | `GetUserInfo` 双分支解析 `mustChangePassword` 同步 store；**仅当字段非 undefined 才写**（滚动部署新前端+旧后端时不误清登录时置位的标志） |
| 6 | `frontend/src/views/settings/index.vue` | 改密成功后清除 URL 上的 `forceChange` query，防 F5 重弹过期警告；mounted 的旧引导提示移除（由守卫统一弹出，避免双弹） |
| 7 | `frontend/src/permission.ts`（同日补充） | 拦截时弹 `Message.warning("请先修改密码：完成修改前仅可访问系统设置页")`（3 秒节流）——拦截重定向回同一路径时设置页不重新挂载，用户点其它菜单被弹回原本无任何反馈 |

### 发布原子性约束（重要）

改动 1 与 2 **必须同一版本原子交付**：单独部署改动 1（父路由 redirect）而守卫白名单仍是父路径 `/settings` 时，`/settings` ↔ `/settings/index` 之间形成无限重定向循环（vue-router 3 无环检测，已实证）。

## 三、修复后行为（回归测试锚定）

- `frontend/tests/unit/permission-force-change-deadlock.spec.ts`（8 用例）: 拦截落点 `/settings/index?forceChange=1` 且改密页渲染可达 + 拦截弹"请先修改密码"提示；首导航（GetUserInfo 分支）同样拦截；手输父路径被 redirect 解析且内容非空；手动直达真实路径放行；改密成功（标志清除）后业务页恢复；提示 3 秒节流（窗口内多次拦截只弹一次、窗口过后恢复）；flag=false 对照组正常且无提示。
- `frontend/tests/unit/user-store-must-change-password.spec.ts`（9 用例）: Login 解析（true / 显式 false / 缺省）、改密清标志、ResetToken 清标志、GetUserInfo 四态（wrapped true / 扁平 true / 显式 false 覆盖 / 字段缺失保持原值）。
- `frontend/tests/unit/settings-change-password.spec.ts`（4 用例，组件级）: 改密成功双解锁（清 store 标志 + 清 URL forceChange query 且保留其他参数）、无 query 不做多余跳转、API 失败不提前解锁、两次输入不一致前置校验拦截。
- `backend/tests/api/test_login_throttle_and_change_password.py`（12 用例）: 新增 `/users/info` 携带 mustChangePassword true/false 两态。
- `backend/tests/api/test_w9_force_change_reproduction.py`（4 用例）: init_db 置位链路（默认口令 bcrypt/旧 AES、自定义口令不置位、改密后幂等）——W9 安全行为保留不动。

## 四、生产解困 runbook

- **首选**：部署本修复版（前后端原子交付）。被困用户登录后自动落到 `/settings/index?forceChange=1` 真实改密页 → 完成改密即解锁（后端清库标志 + 前端清 store 标志 + 清 URL query）。部署后需刷新页面或重新登录一次（守卫在 roles 为空时经 GetUserInfo 取实时标志）。
- **无法立即部署时**（按序执行）：
  1. 建议先停后端容器再执行 SQL（SQLite WAL 单写者，运行中的后端写 LoginLog 等可能 `database is locked`）。
  2. 口令已自定义：`UPDATE users SET must_change_password = 0 WHERE username = 'admin';` —— 重启安全（启动自检 `verify_password("admin")` 不通过，不再置位）。
  3. 口令仍为默认 "admin"：仅清标志会在下次重启被重新置位；应直接写入新口令哈希并清标志：
     ```bash
     python -c "from app.auth.security import get_password_hash; print(get_password_hash('新口令'))"
     # UPDATE users SET password='<上面输出的哈希>', must_change_password=0 WHERE username='admin';
     ```
     禁止手工造非 bcrypt 格式（`verify_password` 只认 `$2b$` 前缀或旧 AES-ECB）；直写后该用户不再被强制改密，需线下告知新口令。
  4. **任何 SQL 路径后必须重新登录或清浏览器 cookie**：旧会话 Vuex 内存中的标志仍在（死锁时布局框架仍渲染，Navbar 登出入口可达）。
  5. 库文件定位：`DATABASE_PATH` 环境变量 / deploy 卷 `./data/backend/data/`。

## 五、遗留清单（本次明确不做）

1. **不刷新的长会话标签页无法实时感知标志**：`GetUserInfo` 全仓唯一调用点是守卫 roles=[] 分支，活动标签页（roles 已填充）不会再拉取。F5/新会话/重新登录均已覆盖；如需彻底消除须把标志挂到周期性轮询端点，改动面大，另行评估。
2. **其他父路由缺 redirect 的系统性 UX 问题**（`/downloader`、`/tasks`、`/recycle-bin`、`/orphan-files`、`/query-templates` 等）：手输父路径内容区空白，但均不在守卫白名单内、无死锁风险（菜单链接均为完整子路径）。后续可统一补 redirect。
3. **后端 `init_db` 启动置位逻辑不动**：W9 安全意图（默认口令强制改密）保留，幂等性已有测试锁定。
4. Git 提交仅在用户明确要求时执行。

## 六、验证记录（2026-08-18）

- 后端：`tests/api/test_login_throttle_and_change_password.py` + `test_w9_force_change_reproduction.py` + `test_auth_protection_extended.py` 共 97 passed；改动文件 black/flake8/mypy 通过。
- 前端：deadlock spec 6/6、user-store spec 7/7、permission-guard/store-user/api-contracts/request-auth 回归 60 passed；改动文件 eslint 通过；`npm run typecheck` 通过。
- 仓库根 `./init.sh` 通过。
