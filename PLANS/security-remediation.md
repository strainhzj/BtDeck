# 安全修复计划（对抗验证驱动）

> **状态**：实施完成，待全量验证收尾
> **创建日期**：2026-08-16
> **问题来源**：两轮对抗验证安全分析（5 域调查代理 + 5+4 对抗验证代理），25 项发现经终审
> **验证基线**：`make lint` + 全量 pytest + 前端 lint/build（见文末验证记录）
> **预计工作量**：14 个工作项（W1-W15）
> **计划边界**：响应格式一律 CommonResponse（HTTP 200 + 字符串 code）；schema 变更走 Alembic（单 head，docstring 标注可回滚）；前端 Vue 2 Options API 无 any；审计走 AuditLogService

## 1. 目标与成功标准

1.1 目标
- P0：消除未认证任意文件读取（serve_frontend 穿越）、认证后 RCE（cron task_type=4）、任意文件写入/读取（备份导入/归档/导出/备份源）
- P1：密码存储迁移 bcrypt 单向哈希（双读自动升级）；git 停止跟踪真实密钥并给出轮换手册；下载器密码全链路加密（add 明文入库 + encrypt fail-open 修复）；登录限流 + 首登强制改密；2FA 端点绑定本人；生产配置加固（DEBUG/DEV/docs/compose 断链）；发行包不再打包 config 目录；starlette CVE 升级

1.2 非目标
- 双轨认证依赖统一（发现21：verify_secret 恒不轮换，实害≈0，不修，记录决议）
- recycle 链 realpath 包含校验（发现23：上游 libtorrent 已清洗路径，当前不可利用，登记延后下版本）
- git 历史 filter-repo 清洗：破坏性操作，写为人工手册（docs/security/key-rotation-runbook.md）

1.3 关键不变量
- 所有 API 拒绝响应保持 CommonResponse 格式（前端 request.ts 按字符串 code 判定）
- Alembic 单 head（ff42d3402df5），test_db_migration EXPECTED_HEAD 已同步
- 登录/2FA 限流键为 username+client.host，绝不信任 X-Forwarded-For（uvicorn 未开 proxy-headers）
- decrypt 的非 sm4: 前缀透传保留（存量明文兼容，load-bearing）
- bcrypt 仅用于 users 表；下载器密码必须可逆（SM4）不得 bcrypt

## 2. 问题 → 根因（已验证）→ 交付项映射

| 工作项 | 发现（终审） | 根因 | 交付 |
|--------|-------------|------|------|
| W1 | serve_frontend 未认证穿越 Critical | `frontend_path / path` 无 resolve/包含校验，pathlib 锚点替换可注入绝对路径 | resolve+is_relative_to 双校验，越界回退 index.html |
| W2 | cron task_type=4 RCE High | 类路径解析失败回落 exec()，开关只封 0-3 类型 | 三层拦截：执行层 `_run_task_script` 闸门（封 0-3 + type4 白名单）/解析层删 exec 回落 + isclass 校验/API+加载层白名单；删 enhanced_python_executor |
| W3 | 备份导入任意写 High | `temp_dir / file.filename` 未消毒 | sanitize + 每请求 uuid 子目录 |
| W4 | source_file_path 任意读 High | copy2 无源校验；seed_transfer info_hash 未限 hex | core 层 bencode+info 内容校验（2MB 上限）；端点 .torrent 后缀；info_hash 40/64 hex |
| W5 | 归档任意写+审计销毁、导出穿越 | open(用户路径,"w")；Path 拼接 | 归档仅取 basename+强制 .json+固定目录；导出 fullmatch 白名单；前端文案 |
| W6 | 下载器密码明文入库 High + encrypt fail-open | add 明文直写；encrypt 失败返回原文 | ORM 构造点加密；encrypt fail-closed raise；core/security 同修；启动幂等钩子加密存量 |
| W7 | git 真实密钥 Critical | config.yaml 被跟踪且保留真实值 | git rm --cached + gitignore + 模板警告 + 轮换手册 |
| W8 | 密码可逆存储 Critical | AES-ECB 冒充哈希 | bcrypt（bcrypt 库直接实现，passlib 1.7.4 与新版 bcrypt 不兼容）；verify 双读；login 条件更新自动升级；changePassword 修复（原直调 sm4_decrypt 会 500） |
| W9 | admin/admin 无改密 + 无限速 High | 无强制机制；无失败计数 | 内存限流（阶梯 5/15m、10/1h，密码与 TOTP 共用）；must_change_password 列+守卫拦截+改密撤销 refresh |
| W10 | 2FA secret 裸读 | 端点仅要求登录态 | 4 端点绑定本人；TOTP 日志脱敏 |
| W11 | DEBUG traceback/DEV 断链/docs 开放 | 默认值 + compose 不透传 | DEBUG/DB_ECHO 默认 False；DEV 保持 True（frozen 兼容）；desktop_main 移除 DEV=false setdefault；DEV=False 关 docs；compose 透传 4 变量；SECRET_KEY 空串归一 |
| W12 | 发行包内嵌 config 目录 | spec datas + iss 复制 | 两 spec 移除 datas；iss 移除复制；.dockerignore 排除 config.yaml |
| W13 | starlette CVE-2024-47874 未认证 DoS | multipart 解析先于认证；版本锁死 | fastapi~=0.115.6 + starlette~=0.41.3；nginx login location 1M |
| W15 | 删错文件兜底/前端两处 | file_operations 取首个匹配；正则未转义；裸 v-html | 仅精确匹配；escapeRegExp；sanitizeDescription 白名单 |

## 3. 不修决议（记录原因，防复审反复）

1. **双轨认证依赖**（get_current_user 19 端点不校验 verify_secret）：`login_status_secret`
   轮换代码被注释、从不轮换，两依赖实际行为差异≈0；真缺口（改密不撤销 refresh token）
   已由 W9 覆盖。
2. **recycle 链路径校验**：original_file_list 唯一来源是下载器 API 返回值，libtorrent
   （CVE-2009-1760 起）与 Transmission（CVE-2010-0012 起）均强制清洗 `..`，当前不可利用；
   作为纵深防御登记延后（下版本与 `_sanitize_path` 升级一并做）。
3. **axios CVE-2023-45857**：项目认证走 Authorization Bearer，无 XSRF cookie 机制，
   触发前提不成立；列入依赖升级清单不单独立项。

## 4. 验证记录

- `tests/api/test_factory_serve_frontend.py`：7 用例（穿越/绝对路径/反斜杠拒绝，正常资源放行）
- `tests/api/test_cron_security_api.py`：41 用例（含新增 executor 白名单组）
- `tests/tasks/test_cron_executor_security.py`：14 用例（标记目录法验证恶意 payload 不执行）
- `tests/api/test_audit_path_security.py`：18 用例（归档约束 + 导出白名单）
- `tests/services/test_backup_source_validation.py`：16 用例（bencode 内容校验）
- `tests/utils/test_downloader_password_encryption.py`：9 用例（fail-closed + 启动钩子）
- `tests/auth/test_bcrypt_dual_read.py`：7 用例（双读 + 旧格式兼容）
- `tests/api/test_twofa_ownership.py`：5 用例（4 端点本人绑定）
- `tests/api/test_login_throttle_and_change_password.py`：10 用例（限流/强制改密/撤销 refresh）
- 升级 starlette 0.41.3 后 `tests/api/` 全量 895 passed（TestClient 行为无回归）
- 迁移链 upgrade→downgrade→upgrade 对称验证通过；EXPECTED_HEAD 更新为 ff42d3402df5

## 5. 遗留事项（人工执行）

1. git filter-repo 历史清洗 + force push（手册：docs/security/key-rotation-runbook.md 第四节）
2. 生产部署密钥轮换（手册第二节，顺序契约：先登录升级 bcrypt 再轮换）
3. 桌面版发布前跑 `deploy/verify-package.py` 确认不再打包 config
