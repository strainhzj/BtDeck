# backend/app/desktop_companion — 桌面伴侣

> 2026-08-26 源码实测。桌面伴侣沿用 Android profile/健康检查语义，密码不进入
> `companion_servers.json`；Windows 发行版使用当前用户 DPAPI 保护凭据文件。

## 文件与职责

| 文件 | 关键入口（当前行号） | 职责 |
|------|----------------------|------|
| `profiles.py` | `ServerProfile:44`、`ServerProfileStore:90` | profile 元数据/`username`、健康状态与原子 JSON 持久化；旧数据缺 username 时按空值读取 |
| `credentials.py` | `MemoryCredentialVault:44`、`WindowsCredentialVault:70`、`build_auto_login_script:206` | 测试内存保险库；Windows DPAPI 密文文件；同源登录脚本（含一次性 TOTP prompt） |
| `launcher.py` | `_ManagerApi:115`、`add_server:131`、`update_server:164`、`DesktopLauncher:252`、`open_remote_window:316` | 伴侣管理页桥接、凭据录入/清除、profile 切换、pywebview 远程窗口与首屏会话恢复 |
| `health.py` | `HealthClient` | `/health/live` → `/health/ready` 探测与 TLS/不可达分类 |
| `lan_policy.py` / `hosts.py` | `check` / `parse_url` | http/https、私有 LAN 与显式明文同意校验 |

## 安全与切换约束

- `ServerProfile.to_json()` 只输出 username；密码由 `CredentialVault` 保存，`list_servers()` 仅返回 `hasSavedCredential` 布尔值。
- 删除 profile 或显式清除凭据必须调用 vault `delete`；编辑时空密码表示保留旧密码，显式 `clear_credentials` 才清除；更换 URL 会清理旧服务器凭据。
- pywebview 远程窗口首屏用 profile id 清理共享 localStorage/cookie，再调用既有 `/api/v1/auth/login` 写入前端 token cookie；不使用 `addJavascriptInterface` 暴露密码。
- TOTP 只在后端返回验证码挑战时通过临时 prompt 传递，不写入 profile/保险库；自动登录不循环重试，避免触发登录限流。

## 回归入口

- `backend/tests/desktop_companion/test_desktop_companion.py`：profile JSON/旧数据兼容。
- `backend/tests/desktop_companion/test_launcher.py`：管理 API、密码不回显、保留/清除语义。
- `backend/tests/desktop_companion/test_credentials.py`：内存保险库、DPAPI 密文不落明文、自动登录脚本安全锚点。
