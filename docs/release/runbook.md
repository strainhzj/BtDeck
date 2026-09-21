# BtDeck 发布 Runbook（v1.0.6 起，release-artifact-equivalence-gate 落地后生效）

> 适用范围：v1.0.6 及之后的正式发布（Windows EXE/Setup、DEB/RPM、Docker 双镜像）。
> 门禁体系：G0 候选冻结 / G1 版本溯源 / G2 工具链依赖 / G3 源码回归 / G4 制品完整 /
> G5 静态等价 / G6 安装生命周期 / G7 运行迁移 / G8 黑盒契约 / G9 安全供应链 / G10 证据闭环。
> 原则：**fail-closed**——任何门红灯即阻断，不允许跳过；CERTIFIED 只能由人工审批写入
> release manifest（审批对象是清单，不是文件名）。

## 0. 角色与前置

| 角色 | 职责 |
|---|---|
| 发布负责人 | 打受保护标签、dispatch 门禁、审批 manifest（填 approver/approved_at + verdict=CERTIFIED） |
| 值班工程师 | 处置红灯、按 §5 排查、必要时按 §3 申请限时豁免 |
| 密钥管理员 | 维护 GH secrets（签名证书/cosign key，见 §4） |

前置条件：
- 发布分支 dev 干净、`Full-stack regression` 对目标 SHA 绿（rc-gate 的 G2/G3 片段来源）
- 签名 secrets 已配置（未配置只能走 `allow_unsigned_drill` 演练，永不能 CERTIFIED）
- `release/release-config.json` 的 candidate 指向本次版本

## 1. 发布流程（RC → CERTIFIED → 晋级）

### 1.1 触发完整门禁

GitHub → Actions → **Release Gate** → Run workflow（branch: dev），勾选全部输入：
`run_windows / run_linux_systemd / run_node_matrix / run_glibc / run_w2_linux / run_w2_windows /
run_w2_docker / run_w3_lifecycle_linux / run_w3_lifecycle_docker / run_w3_lifecycle_windows /
run_w4_contract / run_w5_security / run_w5_sign / run_rc_gate`。

- 正式路径：**不勾** `allow_unsigned_drill`（缺签名 secret → w5-sign-windows 直接
  SIGNING_BLOCKED exit 2 → job 红 → rc-gate 跳过，CERTIFIED 不可能）
- 演练路径：勾 `allow_unsigned_drill`（签名记录 unsigned，manifest/汇聚均 INDETERMINATE）

全链约 2~2.5 小时。rc-gate 末尾产出 `gate-report-full.json` + `release-summary.md`
（artifact `rc-gate`），并断言全部 14 个上游 job success（任一 skipped/failure 即红）。

### 1.2 门禁语义速查（红灯了先看这里）

| 门 | 数据源 | 红的常见根因 |
|---|---|---|
| G0 | w0 探针片段 | 探针环境变化（Inno/NSSM/systemd 容器/glibc） |
| G1 | gate-report.json | 跨制品 build-info 不一致、dirty 构建、SHA/版本漂移 |
| G2 | regression 映射片段 + check_dependencies | qB 等公共依赖锁漂移、打包文件白名单外增量 |
| G3 | regression 映射片段 | 主回归任意测试红（看 §5 先查时序类） |
| G4 | gate-report.json | 六认证对象缺一（构建链断） |
| G5 | verify_release_bundle / verify-package | 前端 manifest 字节漂移（**旧前端混入**）、缺契约 JSON、deb/rpm 内二进制与中间产物不一致 |
| G6 | w3 lifecycle 报告 verdict | 首装/重装/升级/重启/卸载失败（升级停服类） |
| G7 | docker lifecycle 报告 | 健康检查/迁移 head/重启稳定性 |
| G8 | w4 compare 报告 unexplained | 跨制品响应/资源差异（**Docker 混装**、字段漂移） |
| G9 | security-report + signing 记录 | Critical/High 超政策、秘密、许可证、签名 BLOCKED/FAILED |
| G10 | manifest + 终验 | digest 漂移/篡改、compose 模板不一致、CERTIFIED 断言链 |

### 1.3 审批与晋级（G10 闭环）

1. 从 artifact `w5-sign-docker` 取 `release/build/release-manifest.json`，人工核对
   artifacts 七项 digest、evidence 全 PASS、verdict=INDETERMINATE
2. 发布负责人填写 `approver` / `approved_at`，并将 `verdict` 改为 `CERTIFIED`
   （此动作即"审批对象是 manifest"）；重跑 `verify_release_bundle.py --require-manifest`
   ——CERTIFIED 断言链会复核 approver 非空 + 全门 PASS + 签名全 signed
3. 晋级只复制已验证 digest：`deploy/compose-release.env` 已由 manifest 渲染
   （backend/frontend digest），发布侧 `docker compose -f deploy/docker-compose.release.yml
   --env-file deploy/compose-release.env up -d`；**禁止 rebuild、禁止改用可变 tag**
4. Docker 推送后在 registry 侧核对 RepoDigests 与 manifest 一致（本地 save-oci 口径
   与 registry digest 可能因媒体类型转换不同，以 RepoDigests 为准）

## 2. 回滚

- **Docker**：`docker compose -f deploy/docker-compose.release.yml --env-file <上一版本
  compose-release.env> up -d`（digest 引用不可变，回滚=换回旧 env）；数据卷不动
- **DEB**：`apt install btdeck=<旧版本>`（数据目录 /opt/btdeck/config 与 SQLite 保留；
  跨版本回滚先确认 alembic downgrade 需求——当前策略不支持自动降迁移，需 DB 备份恢复）
- **RPM**：`dnf downgrade btdeck-<旧版本>`；注意旧包 prerm 会 stop 服务，升级/降级后需
  `systemctl enable --now btdeck`（v1.0.5 历史包 scriptlet 已知行为，见 §5.6）
- **Windows**：控制面板卸载新版本 → 安装旧 Setup（NSSM 服务随卸载移除，数据在
  %PROGRAMDATA%\BtDeck 保留）
- 回滚前置：`release/build/backup/`（应用自身备份任务产物）与 DB 快照任一可用

## 3. 豁免（限时例外，默认不可豁免项见下）

**不可人工放行**：Git SHA/版本/digest 不一致、公共依赖漂移、制品缺装启、数据丢失或
secret 重置、Critical 漏洞（有修复可用）、真实秘密、签名/digest 校验失败、跨制品核心
API/数据库不一致。

可申请（≤30 天到期，到期自动阻断）：
- High 漏洞：需不可利用证明 + 责任人 + 补救任务 + 补救版本 + 到期日
- Critical 无修复可用型（distro 最新 + fix=[] + 上游已修证据）：tracked-no-fix 例外
- 非核心响应头差异（equivalence-exceptions.json 逐字段登记，禁宽泛规则）

登记文件：`release/security-exceptions.json`（漏洞）、`release/equivalence-exceptions.json`
（等价差异）、`release/secret-allowlist.json`（秘密误报，逐条 rule_id+file）。
**当前基线**：129 条安全例外 2026-10-03 到期（v1.0.7 依赖升级治理批次消解）；
秘密白名单 9 条 2026-11-02 到期。到期未续即 w5-security 红。

## 4. 签名证书轮换

secrets（仓库 Settings → Secrets → Actions）：
- `BTDECK_SIGN_PFX_B64` + `BTDECK_SIGN_PFX_PASSWORD`：Authenticode pfx（base64）
- `BTDECK_COSIGN_KEY_B64` + `BTDECK_COSIGN_PASSWORD`：cosign 静态 key（base64）

轮换步骤：
1. 新证书/key 就绪（cosign：`cosign generate-key-pair`，密码进 secret）
2. 更新 GH secrets（旧值先备份到密钥库再覆盖）
3. dispatch 一次 w5-sign（不带 drill）验证 SIGNED；签名材料落
   `release/build/signatures/`
4. Authenticode 时间戳保证旧证书过期后签名仍可验；轮换本身不改变制品 digest 语义
   （签名后 digest 以 signing-digests post_sha256 为准）
5. 密钥疑似泄漏：立即轮换 + 该密钥签过的 RC 作废重出（digest 链从签名步重走）

## 5. 故障排查（红灯处置，附六类注入演练实证）

通用：先看 rc-gate 汇总 `release-summary.md` 定位门 → 再看对应 job 日志与
`gate-report-full.json` 的 problems。本地复现优先用
`scripts/release/fault_injection_drills.py`（六类注入的可复现驱动）。

1. **旧前端混入（G5）**：`frontend-asset-manifest 与基准不一致`。根因：某 job 自建
   前端而非消费唯一构建（前端双构建必然漂移——SW/index.html 非确定）。处置：检查
   该 job 是否下载 `w5-frontend-unique-build` artifact；禁止任何 job 重复跑
   `build_frontend.py`
2. **qB 依赖漂移（G2）**：`check_dependencies.py` 报锁与声明不一致。处置：以
   `backend/requirements.txt` 为准修锁（手工双哈希，动 W1 哈希链须全链重验）
3. **缺契约 JSON（G5）**：verify-package 报必需条目缺失。根因：打包 datas 配置或
   CArchive 反斜杠条目名（Windows 打包坑）。处置：核对 `deploy/btdeck.spec` datas 与
   verify-package 的 POSIX 名归一
4. **RPM 升级停服（G6）**：lifecycle-rpm-upgrade verdict=FAIL。已知历史：v1.0.5 旧包
   prerm 无条件 stop+disable（不可修），升级后必须 `systemctl enable --now btdeck`；
   新包 scriptlet 已按 DEB/RPM 参数分支。排查：w3 job 的 journal.log/container.log
5. **Docker 混装（G8）**：compare unexplained>0（常见 C11 SPA 资源差异）。根因：前后端
   镜像出自不同 SHA/不同前端构建。处置：确认两镜像来自同一 dispatch run；compose
   发布模板只允许 digest 配对（`w5-sign-docker` 的 compose-release.env）
6. **digest 篡改（G10）**：`manifest digest 与实际文件不一致`。这是最严重红灯：制品
   在签名/清单之后被改动。处置：全链重走（禁止手改 manifest 对齐）；同时审计制品
   传递路径（artifact 下载、晋级复制）
7. **签名 BLOCKED（G9）**：w5-sign job 红、退出码 2=SIGNING_BLOCKED（secrets 缺）、
   3=SIGN_FAILED（工具/证书问题）。处置：§4 轮换/配置；BLOCKED 是设计内状态不是故障
8. **rc-gate 断言红**：`upstream gate job <name> -> skipped/failure`——上游门没在同
   一 dispatch 里全跑或真的红了。处置：同一 run 重 dispatch 全输入；仍红按 1~7 排查

## 6. 版本与标签

- 版本唯一入口 `release/release-config.json`；六处版本声明一致性由
  `generate_build_info.py --check-versions` 强制
- RC 必须来自受保护标签（如 v1.0.6）的干净检出；工作树 dirty 会被 G1 拦截
- 发布后：`session-handoff.md` 与本 runbook 同步新增已知事项
