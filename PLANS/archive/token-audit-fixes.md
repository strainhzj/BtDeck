# 令牌机制对抗审计修复（v1.0.6.41）

> 日期：2026-08-18
> 背景：对登录令牌机制做"过期强制退出+提醒 / 操作实时续期 / 友好体验"评估后，
> 经两轮对抗审计（前端链路 / 后端链路子代理）+ 一轮修复计划独立审查，
> 确认主链路（三层过期感知、401 静默续期重放、三态分流、原子轮换）成立，
> 但边界存在 10 项真实缺陷。本计划按审查修订后版本（v2）实施完毕。

## 修复清单（F1–F10）

### 后端

| # | 问题 | 修复 |
|---|------|------|
| F1 | 旧版升级 config.yaml 永不补 `login_status_secret`，登录端点直取 KeyError → **登录 500 炸弹** | `database.py` init_config_file 已存在分支"缺失才补"该键 + `jwt_secret_key`；`login.py` 改用 `utils.get_login_secret()`（与 refresh 端点对齐，缓存+fail-safe） |
| F2 | cuser.py 业务 401 滥用（10 处）：2FA 输错密码/验证码 → 前端当认证失败（续期→重放→登出），**输错密码即被误踢** | 7 处改 400（L236/242/248/254/275/282/333），/info 兜底 L105 改 500；保留 L77/L119（真 token 缺陷，refresh 重建字段自愈） |
| F3 | refresh_tokens 无任何清理路径，登录/续期各 +1 行**无限增长** | 新增 `auth/token_cleanup.py` + 定时任务 `refresh_token_cleanup_task.py`（每日 04:30，保留 30 天）；种子走 init_db 增量块对存量库生效；不登记 task_profiles（未注册=轻量是设计语义）；无需 Alembic 迁移 |
| F4 | compose 默认 SECRET_KEY 空 → 每进程随机 → **每次重启杀全部会话** | init_config_file 写 `security.jwt_secret_key`（缺失才补）；`config.py` `_default_secret_key` 回退链 env→YAML→随机；CONFIG_PATH 与引导期共用 `_default_config_dir()`；生产护栏条件化放宽（仅 env 与 YAML 均无才拒启，护栏不拆）；config.yaml.example 只留注释占位（缺失才补语义下示例值会被永久沿用为公开已知签名密钥） |
| F5 | `get_login_secret` 缓存条件 `.seconds` 按 86400 取模 | 改 `.total_seconds()`（卫生修复，实际影响可忽略） |

### 前端

| # | 问题 | 修复 |
|---|------|------|
| F6 | ExpireSession 删共享 **access cookie** → 他标签 focus 时 syncTokenFromCookie 判 logged-out → **跨标签级联误杀** | user.ts ExpireSession 不再 removeToken（共享 cookie 全保留：refresh 防轮换竞态、access 防级联）；主动登出传播不破坏（LogOut/ResetToken 仍全清）；误判标签硬刷新可自愈回工作页 |
| F7 | /info 兜底 401 使 **DB 抖动误踢**（配合 F2 改 500 后需要分流） | user.ts GetUserInfo 原样上抛条件扩为 `code==='0' \|\| /^5/`；permission.ts `isTransientError` 同步扩 + abortNavigation 提示改「服务暂时不可用」；**逃生机制**：连续 3 次瞬时中止回落登出（防持久 5xx 下首导航永久卡死且 /login 不可达），afterEach 导航成功清零 |
| F8 | 审计日志下载 `window.open` **三重损坏**（前缀缺 /api/v1、不带 Authorization、绕过拦截器） | api/audit-logs.ts downloadExportFile 改 axios blob（`responseType:'blob'` + encodeURIComponent）；audit.vue 用 createObjectURL+a.click 模式（同 tasks/index.vue 先例）；blob 401 正常走续期重放 |
| F9 | 断网 + 1 秒速度轮询 → 拦截器每失败请求弹独立 Message **toast 洪泛** | request.ts 网络分支 3 秒同文案节流（窗口到期复位，长故障仍周期提醒） |
| F10 | el-upload 自有 XHR 绕过拦截器，上传 401 只弹「上传失败」 | FileManagement.vue handleUploadError 识别 err.status===401（element-ui ajax getError 挂 status）→ trySilentRefresh：renewed 提示重传（headers computed 响应式）、rejected 走 redirectToLogin、transient 保留现场 |

## 明确"本次不修"（防范围漂移）

- compose `DEV` 默认 true（生产护栏默认不生效）
- `/auth/refresh` 无限流、失败不落审计
- `is_admin` 硬编码 "1"（单管理员设计）
- 令牌存 JS 可读 cookie（非 HttpOnly，XSS 可读）
- 审计导出目录 `data/audit_logs_export` 为 CWD 相对路径

## 测试

- 后端新增：`tests/core/test_init_config_file.py`（补齐不轮换/新文件/端到端 get_login_secret 可读/登录签发-校验往返一致）、`tests/api/test_cuser_business_codes.py`（2FA 7 处 400 + /info 兜底 500 + **保留的 2 处 token 缺陷 401 语义防回退**）、`tests/auth/test_token_cleanup.py`（只删超期、保留期内/活跃不动）、`tests/tasks/test_refresh_token_cleanup_task.py`（**种子装配防漂移**：条目存在/executor 字符串可动态导入/保持轻量不登记 task_profiles）、`test_security_config_defaults.py` 扩 SECRET_KEY 回退链 6 用例 + 生产护栏条件化 3 用例
- 前端调整/新增：store-user.spec（ExpireSession 断言反转：共享 cookie 全保留；GetUserInfo 5xx 原样上抛）、permission-guard.spec（5xx 中止保留会话 + 连续中止逃生回落登出 + **计数在导航成功后清零**）、request-auth.spec（网络 toast 3 秒节流窗口语义 + **redirectToLogin 不删共享 access cookie**）、session.spec（**F6 级联防护锚点：被登出标签 cookie 保留时恢复内存而非误判登出**）、api-contracts.spec（下载改 axios blob 契约 + 文件名编码）
- 验证：后端全量 pytest **3826 passed / 7 skipped**；black/flake8 通过，mypy 零新增错误（存量 61 个为 CommonResponse/Result 基线）；前端全量 jest **872 passed**（55 套件）+ eslint 通过；./init.sh 通过

## 部署注意

1. **首启过渡**：已有 config.yaml 的部署升级后第一次启动补入 `jwt_secret_key`，但 settings 在 import 期先于补齐实例化——该次启动 JWT 密钥仍为进程随机，**再重启一次后稳定**（首启无存量会话需保留，无实际影响）
2. **手动维护的 config.yaml**：若手工从 example 复制，切勿照抄任何 jwt_secret_key 示例值（缺失才补语义下会被永久沿用）
3. 定时任务种子在下次启动经 init_db 增量块自动补建（无需手工 SQL）

## 审查记录

- 第一轮（双代理对抗验证主链路结论）：A–H / A–G 全部 CONFIRMED，产出缺口清单
- 第二轮（修复计划独立审查）：F3 删除 task_profiles 登记步骤；F4 生产护栏条件化；F7 补逃生机制（P1：持久 500 首载卡死）；F2 计数更正 10 处；F6 论证修正（整页跳转后内存从 cookie 重建）
