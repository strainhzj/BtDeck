# 密钥轮换与历史泄露处置手册（安全修复 W7）

> 对应发现：git 仓库历史中提交了真实 `security.secret_key` / `login_status_secret`
> （`backend/config/config.yaml` 与 `backend/app/config.yaml`，提交 `e8e7784` 曾把
> 占位值改回真实值）。该密钥是 **用户密码（AES-ECB 可逆存储）与下载器密码
> （SM4-ECB）的加密主密钥**——任何获得「仓库 + 一份 app.db」的人可离线还原
> 全部凭据明文。

## 一、为什么必须按顺序操作（顺序契约，违反会锁死）

`users.password`（旧格式）与 `bt_downloaders.password` 共用 yaml `secret_key`：

1. **先部署代码**（含 bcrypt 双读迁移 W8）并**登录一次**——旧格式密码自动升级为
   bcrypt（此后不再依赖 secret_key）；
2. **再轮换 secret_key**——此时只剩下载器密码 SM4 密文依赖旧密钥。

**如果先轮换密钥再登录**：旧格式密码密文无法解密 → 无法登录 → 需要手工恢复
（见第三节自救步骤）。

## 二、轮换步骤

```bash
# 1. 确认代码已部署到 W8（bcrypt 双读）版本
# 2. 管理员登录一次（触发旧格式密码自动升级为 bcrypt）
# 3. 停止服务，生成新密钥
python -c "import secrets; print(secrets.token_hex(16))"   # secret_key
python -c "import secrets; print(secrets.token_hex(16))"   # login_status_secret

# 4. 编辑 <CONFIG_PATH>/config.yaml（开发/桌面版: backend/config/config.yaml；
#    Docker: ./data/backend/config/config.yaml），替换 security 下两字段
# 5. 启动服务
# 6. 验证：登录正常；下载器若连接失败，在下载器管理中重录密码
#    （新明文由启动钩子 encrypt_plaintext_downloader_passwords 自动加密，自愈闭环）
```

> 轮换 `login_status_secret` 会使所有已签发 JWT 失效（全员重新登录，符合预期）。

## 三、锁死自救（先轮换后升级导致无法登录）

```bash
# 1. 停止服务
# 2. 备份数据库后删除 admin 用户行（LoginLog 无 FK 约束，安全）
sqlite3 <CONFIG_PATH>/app.db "DELETE FROM users WHERE username='admin';"
# 3. 启动服务 → init_db 重建 admin（bcrypt("admin") + 强制改密标志）
# 4. 用 admin/admin 登录 → 被强制改密
```

## 四、git 历史清洗（破坏性，需人工执行）

代码已 `git rm --cached` 两个 yaml 文件并补 .gitignore；但**历史提交仍含两组
真实密钥**（`[REDACTED-SECRET]` 与更早轮换前的值），且 `backend/app/config.yaml` 的
`fb889bae...` 从初始提交即被跟踪。若仓库为公开/半公开，必须清洗历史：

```bash
# 1. 与所有协作者确认后（force push 会使他人 clone 失效）
git clone --bare <remote> repo.git && cd repo.git
git filter-repo --path backend/config/config.yaml --path backend/app/config.yaml --invert-paths
git push --force --mirror origin
# 2. 所有协作者重新 clone（旧 clone 视为已泄露）
# 3. 即使清洗完成，上述两把密钥 + fb889bae... 一律视为已泄露，按第二节轮换
```

工具：`git filter-repo`（pip install git-filter-repo）。

## 五、已泄露密钥的影响面

| 密钥 | 来源 | 能解密什么 |
|------|------|-----------|
| `[REDACTED-SECRET]` | git HEAD 的 backend/config/config.yaml | 用该文件初始化部署的 users.password（AES-ECB 旧格式）、下载器密码（SM4） |
| `[REDACTED-SECRET]` | backend/app/config.yaml（无代码消费，死文件） | 无运行时作用（仅模板误导风险） |
| `[REDACTED-SECRET]` | auth/utils.py 旧兜底常量（已改为随机值） | 配置丢失场景的登录密钥比对值（不参与签名，低危） |

> 注意：`bt_downloaders.password` 在旧版本中大量**明文**存储（add 端点缺陷，
> 已修复 + 启动钩子加密），无需密钥即可读取——数据库泄露即凭据泄露，轮换
> 密钥后仍建议为下载器统一重录密码一次。
