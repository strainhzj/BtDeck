# Progress Log - BtDeck 全栈项目

## 2026-09-03（续）：W5 批次 E 收口——G0~G10 门禁汇聚 + rc-gate fail-closed DAG（task .9 剩 F）

**代码件**（提交 0807507）：
- release/schemas/gate-fragment.schema.json：标准门禁片段 schema（gate/status/generated_at
  必填、evidence/logs 可选、additionalProperties=false）
- scripts/release/aggregate_gate_report.py：G0~G10 汇聚——片段优先于推导；门映射
  （G0/G2/G3 只认片段，G1/G4/G5 gate-report 值，G6 deb-rpm-windows 生命周期 verdict
  空坏文件=INDETERMINATE，G7 docker，G8 compare 全候选 unexplained==0，G9 扫描+签名
  双面单面缺失不得兜 PASS，G10 verify+manifest 联合且审批完成是检查项）；verdict 三态
  （CERTIFIED 需全 PASS+manifest CERTIFIED+approver）；输出 gate-report-full.json +
  release-summary.md（§14 模板）；坏证据/REJECTED exit 1、INDETERMINATE exit 0
- CI：w0 四探针 job 补 G0 片段写出（windows 纯 pwsh 无 python 依赖、linux python3、
  node-matrix 覆写 working-directory 回仓库根）；rc-gate job——needs 全部 14 门禁 job +
  result 断言（skipped=NOT_RUN fail-closed）、download-artifact pattern w[0-9]-*
  merge-multiple 汇证、regression API（runs?head_sha 查 Full-stack regression conclusion）
  映射 G2/G3 片段、aggregate 汇聚上传

**实证**：
- 本机真实仓库跑 aggregate：提交的空壳 w3 证据（0 字节）被识破为坏证据 → G6
  INDETERMINATE + problems → REJECTED exit 1（fail-closed 演示）
- CI run 33764067820@0807507（dispatch run_windows+run_rc_gate）：w0-windows
  "Write G0 gate fragment" 步骤 success，artifact 片段本机 schema 复验 VALID；
  rc-gate 负向实证——13 个上游门 job skipped 逐个 ::error 阻断红
- 测试 +36（release 275→311）：schema 校验/推导器坏证据语义/片段优先/G2 锁交叉/
  verdict 三态/端到端四链（drill-certified-rejected-tampered）

**修复真 bug 1 个**：derive_g9 首版 `if s` 过滤把缺失扫描面丢掉、仅签名面即可判 PASS
（漏报）——单测暴露后改为显式 NOT_RUN 语义。

**下一步**：批次 F（最后一批）——RC 演练：全门一次 dispatch（run_w2×3+run_w3×3+
run_w4+run_w5_security+run_w5_sign+run_rc_gate+四探针+allow_unsigned_drill）跑完整
DAG 全绿（预期 rc-gate INDETERMINATE：drill 无签名）；六类故障注入各停预期门【旧前端→
G5、qB 漂移→G2、缺契约 JSON→G5、RPM 升级停服→G6、Docker 混装→G8、digest 篡改→G10】；
docs/release/runbook；feature_list/progress/handoff/roadmap 全收口；.9 置 done。

## 2026-09-03：W5 批次 C+D 收口——G9 扫描面+签名面全绿、G10 骨架落地（task .9 in-progress，剩 E/F）

### 批次 C（G9 扫描面，本日另一会话完成）

- CI run 33747568891@b281e85 七目标 SBOM + grype/gitleaks/许可证 verdict=PASS（Critical 19
  全 tracked-no-fix、High 110 全限时例外、0 阻断）
- 政策修订（用户批准）：Critical 无修复可用型（distro 最新+fix=[]+上游已修证据）可登记
  tracked-no-fix 30 天例外；基镜像治理（trixie 线+nginx 1.27）
- 独立欠账：129 条例外 2026-10-03 到期（v1.0.7 依赖升级治理批次消解）；秘密白名单 9 条
  2026-11-02 到期。证据 release/evidence/w5/

### 批次 D（G9 签名面 + G10 骨架，本会话完成）

**代码件**：
- scripts/release/sign_artifacts.py：Windows Authenticode（signtool /fd SHA256 + RFC3161）+
  Docker cosign 双目标；状态机 SIGNED/SIGNING_BLOCKED/SIGN_FAILED/unsigned——正式缺钥
  exit 2 fail-closed（不是跳过）、drill unsigned exit 0 但下游强制 INDETERMINATE、
  SIGN_FAILED exit 3 无演练豁免；签名前后 digest 分片落 signing-digests-<target>.json
  （分片防多 job 覆盖，汲取 index.json 事故教训）；docker digest 三级口径
  RepoDigests>Descriptor.Digest>save-oci（docker save OCI layout index.json 的 manifest
  digest，内容寻址、篡改必变）
- cosign 工具链：ghcr.io/sigstore/cosign 镜像仓库已不存在（NAME_UNKNOWN 实测）→ 改 GitHub
  release 二进制 sha256 固定进 tool-versions.json（digest 取自官方 .sigstore.json 的
  messageDigest，Rekor 链内）；v3 CLI 契约实测：sign-blob 签名材料走 --bundle（无
  --output-signature/--tlog-upload）、verify-blob 只吃 --bundle、keyed 签名 verify 需
  --insecure-ignore-tlog
- scripts/release/build_release_manifest.py：按 schema 生成发布清单——七制品引用签名后
  digest、evidence G0~G10 全索引（批次 E 片段缺失=NOT_RUN 诚实登记）、verdict 生成器只出
  REJECTED/INDETERMINATE（CERTIFIED 属人工审批 + verify 断言链把关）、approver 留空、
  --emit-compose-env 渲染 digest-only compose 输入
- deploy/docker-compose.release.yml：发布组合模板只引 digest（${VAR:?} 必填形式）、无 build
  段（G10 只消费已晋级制品）
- verify_release_bundle.py 扩展：G9 签名面（formal 未完成阻断/签名后篡改现场重算检出）、
  G10 digest 闭环（manifest==现场重算、digest_ref 格式、compose 渲染一致性 digest-only
  负向、CERTIFIED 断言链：approver 空/签名 unsigned/门 NOT_RUN 均拒绝）；gate-report 新增
  G9_signing/G10 键

**本机实证**（release/evidence/w5/sign/）：BLOCKED（exit 2）/drill unsigned（exit 0）/
SIGNED（临时密钥全链+bundle 落盘+内嵌 verify）三态；cosign v3 wiring 冒烟（容器内 keygen→
sign-blob→verify-blob=Verified OK→篡改拒绝）；cp1252 模拟（PYTHONIOENCODING=cp1252）。

**CI 四轮迭代**（w5-sign-windows + w5-sign-docker + allow_unsigned_drill dispatch 输入）：
1. 33755046911：build-info staging 回退链缺 windows-exe → resolve_build_info_path 纯函数+3 回归
2. 33756203828：Windows runner cp1252 双层坑（中文 print 崩 + subprocess locale 解码 docker
   输出崩读线程）→ stdout reconfigure + subprocess UTF-8 强制
3. 33757547345：**G1 拦截真实等价违规**——两次独立前端构建 ~20 个 JS chunk 内容哈希漂移
   （同尺寸不同字节，疑似内嵌构建时间戳；本机双构建复现 index.html/service-worker.js(.map)
   漂移）→ w5-sign-docker 改为消费 w5-sign-windows 上传的唯一前端构建
   （w5-frontend-unique-build artifact）——计划 §8.3 唯一前端 DAG 语义落地；前端构建确定性化
   列为 v1.0.7 候选
4. **33759319494@074377a 终局全绿**：7 制品 verify PASS、manifest INDETERMINATE+approver 空、
   gate-report G1/G2种/G4/G5/G10 PASS+G9_signing INDETERMINATE（drill 正确阻断 CERTIFIED）、
   drill 语义断言 OK；CI artifacts 归档 ci-artifacts/

**测试**：release 180→275（sign 37 / manifest 24 / verify G9G10 34 = 新增 95）；全套
4409 过 0 失败。提交链：fbcf336（批次 D 主体）→ a683366（staging 回退）→ 4e74118+c88dee1
（cp1252）→ 074377a（唯一前端消费）；master workflow 副本同步至 e9b04b7。

**下一步**：批次 E（aggregate_gate_report.py 汇聚 G0~G10 + rc-gate DAG job + w0 探针 job 补
标准 gate 片段 JSON——workflow 小改需 master 双同步）、批次 F（RC 演练：v1.0.5→v1.0.6 一次
全绿 + 六类故障注入各停预期门 + runbook + 全项目收口）。真实签名待用户提供 GH secret
（BTDECK_SIGN_PFX_B64/BTDECK_COSIGN_KEY_B64+PASSWORD）一键启用。

## 2026-09-02：W4 批次 B2 收口——C01~C12 十二场景三制品 CI 全绿，task .8 done（G8 达成）

### 战果

- **CI run 33634391712@dev a59a382 w4-contract 全步骤 success**：同 SHA 构建 deb/rpm/docker →
  三独立实例 FULL(C01~C09/C11/C12) + systemctl/compose restart + C10 --merge-into →
  compare **rpm/docker total_diffs=0 unexplained=0 零豁免**；Mutation drill（G8 退出门）
  M1 前端资源字节变异与 M2 mutate-proxy 响应字段变异双双被精确拦截（演练步骤自身断言"必须红"）。
- 本地实证（release/evidence/w4/b2/）：同镜像双实例 FULL+重启+C10 compare total_diffs=0 且
  FULL 重跑幂等；M1（index.bytes 1984→2004）/M2（live.identity.version）本地复现双红。
- 测试 127→147：test_qb_tr_stub.py 14 例（真实 qbittorrentapi/transmission_rpc 客户端库打
  进程内 stub 验证协议保真）+ runner B2 场景 mock e2e 6 例。

### 代码件

- scripts/release/fixtures/qb_tr_stub.py：纯 stdlib 三角色 stub（qB 18080/18082、TR 18081、
  mutate-proxy），固定数据集零随机、逐请求日志；数据端点 GET/POST 双收（qbittorrentapi
  torrents_info 实测走 POST）。
- contract_runner.py：C05 下载器 CRUD（不可达主机名负向；独立端口 18082 避缓存 host:port
  去重）、C06 种子查询（camelCase 键/分页/筛选/tracker-domains/单种子双 torrents 路径；
  夹具存在即复用保 uuid 稳定）、C10 重启持久化（fail-closed 语义断言防"三制品一致地坏"）、
  C12 路径映射边界；--merge-into/--downloader-stub-host/--c05-qb-port。
- slice_snapshot.py、docker-compose.w4-stub.yml（三监听 stub 服务）、w4_install_wait.sh
  --wait-only、CI job 扩展（stub 双网接入 deb/rpm、重启 C10、变异演练步骤）。

### 副产品：修复遗留同步路径 3 个真缺陷（torrent_sync.py，全新安装首同步必炸）

生产存量库走 update 路径、异步任务走字典批量路径，三缺陷全被掩盖——W4 C06（全新实例
首同步）正是为此设计：
1. qB/TR 构造 torrentInfoModel 缺必填 progress（新种子 INSERT 即 TypeError）；
2. tracker upsert on_conflict_do_update 漏部分索引 index_where=sa_text("dr = 0")（SQLite
   拒绝 → 同事务种子行连带回滚 → 同步"成功"但 0 行）；
3. update 分支 to_dict() 对未设置属性给 None 写 NOT NULL 列 has_tracker_error（二次同步
   IntegrityError；现剔除 None 保留 DB 动态重算现值）。

### 契约实测结论（已入 stub/runner 注释与证据 README，勿再踩）

- 下载器缓存按 host:port 去重且 delete 不清缓存 → C05 用独立端口、C06 夹具复用不重建。
- /downloader/test 是 ICMP/TCP 可达性探测：可达主机的关闭端口仍 success=True，负向必须用
  不可解析主机名。
- /torrents/list 同步全部启用下载器；缓存缺失的下载器返回错误 dict 也被计成 synced。
- getList 行键 camelCase（infoId/savePath/errorReason）；qB add 认证 app_version 属性访问
  恒通过（vacuous）；TR trackerStats 须带 lastAnnounceResult 等完整字段集（无守卫直取）；
  path-mapping add 重复 internal 也 200；C12 内部探测打 app/defaultSavePath+sync/maindata。

### CI 迭代（2 轮）与环境坑

- 首轮 run 33633662656：deb/rpm 两制品 FULL+C10 已全绿，docker 组合 up 步骤被容器名冲突
  挡下（deb/rpm 手起 stub --name w4-stub 撞 compose 服务 container_name）→ 改名
  w4-stub-host + --network-alias w4-stub（DNS 名不变）修复。
- dev 模式 docker build-images 会被 G5 验证器拦 dirty build-info（门禁本职，本地实证改用
  dev 镜像；CI 干净检出用 --release）。
- 本机 Docker Desktop：特权容器上 stub DNS/连通正常（早先"失败"是测试脚本用错容器名）；
  MSYS_NO_PATHCONV=1 必须 export 在同一条命令里。

### 遗留观察（不阻断，待后续处理）

- test_openpyxl_kept_for_excel_export 在 dev 已提交态失败（stash 验证与本批无关）：
  8/27 W2 瘦身后 deploy/requirements-linux-package.txt 丢了 openpyxl——建议单独修复。
- 全新实例启动 tracker_judgment 报 no such table: tracker_keyword_config（后台 ERROR
  日志，未影响场景断言）——疑似 fresh-install 迁移缺口，待排查。
- 全套 pytest：4280 过 / 7 跳过 / 1 失败（即上述 openpyxl 既有项）。

### 遗留观察项清理（同日，B2 收口后）

1. **openpyxl 打包契约失败 → 修复**：`test_openpyxl_kept_for_excel_export` 是 8/27 前后两批
   改造交叠期的旧口径（要求三个 requirements 文件都含 openpyxl），与 8/28 W1/W2 的
   "deploy 平台增量白名单"架构直接矛盾（openpyxl 属公共依赖，由 requirements-lock 带
   哈希供应，白名单仅 pyinstaller/pywebview，复制进平台文件反而违反
   test_dependency_lock 强制）。修复＝陈旧测试对齐现行架构：主清单+锁必须含
   openpyxl（制品实际安装源），平台文件必须不含。
2. **fresh-install 缺 tracker_keyword_config 表 → 修复**：全新实例日志报
   `no such table: tracker_keyword_config`。实锤为**启动顺序竞态**而非迁移缺口——
   基线迁移 e2a02abcf912 无条件建全部 21 表；但 `tracker_judgment.py` 模块级单例
   `judgment_engine = TrackerJudgmentEngine()` 以 auto_load=True 在 **import 期**
   预加载关键词，早于 startup 的 Alembic 迁移；存量库（表已存在）掩盖多年。
   修复＝单例改 `auto_load=False`，首次 judge_status 经 `_ensure_cache_loaded`
   懒加载（双检锁）。回归测试 3 例（reload 时 SessionLocal 一触即爆的 import 期
   禁 DB 契约/源级 auto_load=False 断言/懒加载按需触发）；全新 docker 实例实证
   0 次 no such table + 懒加载成功载入 80 条种子失败关键词。顺手删除该测试文件
   的既有死导入 threading。

### 2026-09-03：.9 开工——批次 C（G9 供应链透明+安全扫描）CI 全绿收口

- **CI run 33747568891@dev b281e85 全步骤 success**：七目标 SBOM（源锁净化 54/前端生产
  过滤 343/PyInstaller onefile 0/deb 2/rpm 2/docker 镜像 3107+1045）+ grype v0.118.0
  漏洞扫描 + gitleaks 全历史秘密扫描 + 许可证禁用清单 → **verdict=PASS 0 阻断**。
- 分级基线：Critical 19 / High 110 / Medium 122；gitleaks 21 命中全为误报模式（白名单
  9 条 rule+文件登记，2026-11-02 到期）。
- **治理决策**（用户批准）：①tracked-no-fix Critical 政策修订——有修复可用硬阻断；
  无修复可用（distro 最新+fix=[]+上游已修证据）可登记 30 天跟踪例外（机器校验三条件，
  upstream_fix 必填）。②基镜像治理：python:3.11-slim 刷 trixie 新 digest、nginx 1.25
  （EOL）→1.27-alpine、两 Dockerfile 运行时加 apk/apt upgrade 层。③129 条例外基线
  （2026-10-03 到期，19 tracked + 110 High，v1.0.7 升级治理批次消解——**独立欠账**）。
- 代码件：generate_sbom.py（五类七目标）/ scan_security.py（策略引擎）/ slice 用纯
  函数单测 28 例（含双变异锚点）；release/tool-versions.json（syft/grype/gitleaks
  digest 固定）；security-exceptions.json / secret-allowlist.json / license-denylist.json；
  CI w5-security job。测试 175→180。
- CI 迭代 7 轮根因：容器 root 写文件宿主无权改写（tmp+os.replace）/ binary 路径假设错
  / docker 目标字面量未插值 / grype `-o json=path` 系 syft 语法（应 `--file`）+ rc=1
  双义性 / grype v0.96.0 DB hydration 缺陷→v0.118.0 / 基镜像 EOL 真实 BLOCKED 命中。
- 提交链 ac0bf68→0a7326e（8 个）全推 origin/dev；master 副本同步 51eaac1。

### 下一步

- .9（W5/W6）进行中：批次 C done（G9 扫描门禁）；剩批次 D（签名/digest 晋级/发布清单）、E（gate-report 汇聚+DAG）、F（RC 演练+runbook+收口）；另有 v1.0.7 依赖升级治理欠账（129 条例外 2026-10-03 到期）。


## 2026-08-28：安全修复与质量门禁可信化人工闭环

- 用户确认 `security-remediation-2026-08` 与 `quality-gate-hardening` 已完成人工闭环。
- `feature_list.json` 中两个父 Feature 状态分别由 `implemented` / `in-progress` 更新为 `done`；现有子任务状态与证据保持不变（安全修复 14/14、质量门禁 2/2）。
- 本次仅调整任务状态与会话记录，未修改业务源码；顶层 `verification` 独立字段保持原值。

## 2026-08-28：MCP 服务与可选能力开放计划（默认关闭 + 强制脱敏）

### 背景与决策

- 用户确认首批 MCP 能力包含：种子高级查询、等级4操作、添加种子、创建高级查询组合、仪表盘读取、定时任务触发；本批只制定计划和实现门禁，不实现 MCP 代码。
- MCP 与 FastAPI 同进程并共享 `app.state.store`、数据库会话工厂和全局 Cron 执行器；工具只调用协议无关 service，不调用 HTTP endpoint，也不创建第二套下载器连接。
- 采用默认拒绝：实例级 MCP 全局开关默认关闭，6 项预置 capability 均独立开关且默认关闭。关闭能力不出现在工具发现结果；客户端缓存旧定义直调时仍由执行门禁拒绝。
- 配置计划复用现有 `configs(key/value)` 表，以 `mcp.runtime.v1` 保存版本化 JSON 和 revision CAS；配置缺失/损坏/未知版本全部 fail-closed。新增最高优先级环境 kill switch `BTDECK_MCP_FORCE_DISABLED`。
- 当前用户模型没有角色字段，控制面按现有模型要求认证用户仍存在、`is_active=True` 且 `must_change_password=False`；不在计划中伪造不存在的 RBAC。首版复用短期访问 JWT，不引入长期 MCP API Key。

### 隐私与安全边界

- MCP 不直接序列化现有 Torrent/Tracker VO 或 ORM。每个工具输出显式 allowlist DTO，并在最终序列化前经过统一 sanitizer 与泄漏扫描器。
- Tracker 只返回规范化域名和 `working/error/unknown` 等安全状态，永不返回原始 URL path/query/fragment、passkey/token 或 announce/scrape 原始消息。
- 绝对保存路径/种子文件路径仅返回脱敏显示值或省略；下载器 host/username/password/cookie/token、审计 IP/UA 永不进入 MCP 响应。首版不提供关闭脱敏选项。
- 高级查询 MCP `pageSize` 最大 200、序列化响应最大 1 MiB；Tracker 输入只接受域名条件。日志同样禁止记录原始工具参数、返回 payload、Tracker URL/消息、上传内容和绝对路径。
- 等级4工具明确语义为添加 `pending_delete` 标签，不删除任务/文件；下载器成功但 DB 失败必须返回 partial。Cron 仅允许显式内置 `task_code`，task_type 0～3 永拒。添加种子首版只接受受控 `.torrent` 内容，不接受磁力、URL 或服务器路径。

### 规划资产

- 新增 `PLANS/mcp-service-capabilities.md`：同进程架构、配置 schema、6 项 capability 目录、统一认证、数据分类/脱敏、查询预算、写操作安全、W0～W4 波次、测试矩阵、完成定义和回滚处置。
- `feature_list.json` 新增 `mcp-service-capabilities-2026-08-28`：status=pending、6 项默认关闭 capability、12 个 blocking implementation gate（MCP-G0～G11）及 9 个 pending 实施任务。
- G1 默认关闭、G2 逐能力门禁、G3 认证、G5 脱敏、G7 写操作安全、G8 Cron/上传安全明确禁止豁免；任一 gate 为 FAIL/NOT_RUN/INDETERMINATE 或缺证据均阻止开放和进入发布制品。
- `PLANS/README.md` 已增加专项计划入口。本批未修改业务源码、数据库结构、依赖或打包配置，未执行 Git 提交。

### 本批验证

- `feature_list.json` PowerShell `ConvertFrom-Json` 解析通过：新 feature 唯一，6 capabilities、12/12 pending gates、9/9 pending tasks，plan_file 存在。
- 结构化不变量验证通过：6 个 capability code/工具名唯一且全部 `default_enabled=false`；12 个 gate ID 唯一且全部 blocking/pending；G1/G2/G3/G5/G7/G8 均为 `waiver=forbidden`；9 个 task ID 唯一且全部 pending；计划索引、progress、handoff 链路可达。
- `git diff --check` 通过；Git Bash 根 `./init.sh --ci` 退出 0，仅保留既有 jq 未安装、虚拟环境未激活和前端 init null-byte 警告。

## 2026-08-28：悬浮玻璃按钮件·回归加固（源码契约 6 例 + 变异验证 24 组）

- 按用户要求为上一批"Tab 栏悬浮圆角玻璃条 + 返回顶部浮标玻璃化"补足回归保护，沿用项目既有加固范式（源码契约切片 + 定点变异验证；jsdom 无法计算 scoped CSS 实际渲染，源码契约是本仓库 CSS 回归的唯一可行层）。
- **mobile-shell.spec +4 例**：① Tab 栏悬浮形态全锁（left/right 12px、bottom calc(8px+安全区)、--radius-xl、--glass-bg/blur/-webkit- 前缀/--glass-border/--shadow-lg、z-index 10，且切片禁 padding-bottom 防安全区双倍避让）；② @supports 降级契约——条件必须字面量 `blur(12px)`（var() 内嵌条件在部分引擎判 unknown 使 not() 恒真、降级实色覆盖支持浏览器，即 Navbar 等桌面端 4 处的既有隐患形态），降级色必须走 --color-bg-primary/--color-border-primary 主题变量；③ 内容区底部留白 calc(80px+安全区)（72px 贴底旧值回归即红）；④ 跨文件几何契约——从两文件切片解析 Tab 高度/Tab 栏底距/浮标 bottom 三值，断言浮标与 Tab 栏顶边净空 ≥ 12px（单侧改动挤压即红，当前 16px）。
- **mobile-torrents.spec +2 例**：⑤ 浮标 --radius-lg 12px 圆角方块 + 玻璃三件套 + --shadow-md + z-index 9（50% 全圆/实色白/硬编码阴影回归即红）；⑥ 浮标 @supports 降级契约（同②）。
- **变异验证 24 组全部精确拦截**（`node .tmp-mobile-run/mutate_glass.mjs`：锚点唯一性预断言 → 内存备份 → 变异 → jest 必红 → 还原 → 字节校验；每源文件 14+10 组）：玻璃底→裸 #fff、删无前缀/-webkit- backdrop-filter、圆角→0/50%、内缩→贴边、bottom→0/72px、@supports 条件内嵌 var()、降级色→裸值 ×4、留白→72px、重加 padding-bottom 双倍安全区、Tab 高 56→64 挤压净空、描边→none ×2、投影→硬编码 ×2。L6/T2 触发双断言双红（直接断言 + 几何契约联动）。还原后 `frontend/src` 零残留（字节校验 + git status 复核）。
- **变异脚本坑**：spawnSync 双 spec 运行遇 ENOBUFS（mobile-torrents 的 Vue 警告噪音超默认 1MB 输出缓冲，status=null 易误判基线未绿）——需 `maxBuffer: 20MB`。
- **验证**：mobile-shell + mobile-torrents 60 tests passed（54+6）；定向 ESLint `--max-warnings 0` 与全量 `npm run lint`（含 contract:check）零错误。feature_list.json mobile-ux.7 补 spec files 与加固 evidence。未执行 Git 提交。

## 2026-08-28：移动端悬浮按钮件质感升级（Tab 栏悬浮圆角玻璃条 + 浮标圆角方块玻璃化）

- **需求与方案**：用户要求移动端按钮框改轻微圆角并加玻璃蒙版。经范围确认（Tab 栏 + 返回顶部浮标两项悬浮件，Tab 栏选悬浮圆角条形态）与子代理独立审查（无 P0；3 条 P1 修订全部采纳）后实施。
- **改动（2 文件纯 CSS）**：`layout/mobile/index.vue` `.mobile-tabbar` 贴底直角实色 → 悬浮圆角条（left/right 12px、bottom 8px+安全区、`--radius-xl` 四角圆角、`--glass-bg`+`backdrop-filter blur(--glass-blur)`+`-webkit-` 前缀、`--glass-border` 描边、`--shadow-lg`）；`.mobile-content` 底部留白 72px → `calc(80px+env(safe-area-inset-bottom))`（首次正确补偿安全区）。`views/mobile/torrents.vue` `.m-backtop` 50% 全圆 → `--radius-lg` 12px 圆角方块，同款玻璃三件套 + `--shadow-md`，bottom 72px → 80px。两处各加 `@supports not (backdrop-filter: blur(12px))` 降级实色（`--color-bg-primary`/`--color-border-primary`）。
- **审查驱动的关键决策**：① `@supports` 条件用字面量 `blur(12px)` 而非照搬 Navbar 的 `var()` 内嵌形式——var() 在部分引擎的条件中判 unknown 会使 `not()` 恒真、降级块在支持的浏览器上也生效（Navbar/Sidebar/layout/index.vue/AdvancedMultiSelect 既有 4 处带 var() 写法存此隐患，登记备忘未在本次处理）；② 降级块用主题变量不用裸 #fff；③ 无前缀检测对 iOS ≤17 误降实色属保守取舍，显式记录（目标环境 Android WebView Chromium 76+ 原生支持）。
- **验证**：`npm run lint` 零错误（含 contract:check）；`npm run build` 通过；mobile-shell + mobile-torrents 54 tests passed（源码切片断言不受影响，@supports 块按审查建议插在 `.mobile-tabbar` 与 `.mobile-tab` 之间避开脆弱区）；复用 `.tmp-mobile-run` 模拟器基建（iPhone 12 视口 CDP 9333）实测截图与计算样式断言：Tab 栏 16px 圆角 + rgba(255,255,255,0.85) + blur(12px) 生效、浮标 12px 圆角 + 后方"删除"按钮虚化透出（蒙版真实生效）、触底末卡距 Tab 栏顶 22px 无遮挡、半透明白描边在 #f5f7fa 页底上边界感可接受（`--shadow-lg` 兜底，无需中性色 hairline）。
- **测试环境假象排查**：自动化点击"回顶"后 scrollY 停滞——探针证实模拟器窗口被桌面遮挡时 Chromium 将 rAF 节流至 1 帧/500ms（visibilityState 仍 visible），rAF 驱动的平滑滚动因此停摆；属环境假象非改动回归（点击处理器正常触发，且本改动纯 CSS 不触 JS）。附带发现：`.mobile-content` 的 `overflow-y:auto` 实际不裁剪（真正滚动容器是 window/document），其 scrollTop 恒 0——既有事实，与本改动无冲突，登记备忘。
- **登记**：feature_list.json `mobile-ux-enhancements-2026-08-28` 追加 mobile-ux.7（done + evidence）；备忘两项（不在本次范围）：index.html 缺 `viewport-fit=cover` 致 safe-area 恒 0（现体系自洽，边到边需求另立任务）；玻璃三件套已 7 处复制，可沉淀 SCSS mixin 回收。未执行 Git 提交。

## 2026-08-28：v1.0.6 交付制品等价性与发布阻断门禁计划

### 背景与裁决

- 对 Windows EXE/Inno Setup、DEB、RPM、Docker backend/frontend 的构建输入、运行入口、依赖、既有制品和 CI 回归完成专项审计。
- 结论：当前不能声明四种交付物核心功能等价或安装生命周期幂等；现有 `dist/btdeck.exe` 可启动，但内嵌前端 SHA256 与当前 `frontend/dist` 不同，已明确不是当前 HEAD 的等价制品。
- 关键阻断：Docker/源码回归使用 `qbittorrent-api~=2025.2.0`，Windows/Linux 包使用 `~=2025.5.0`；CI 仅有 Ubuntu Python 3.12/Node 20 源码回归；Inno、RPM、当前 Docker 组合、重装/升级/卸载和跨制品黑盒比较均未覆盖。
- 用户确认目标候选为 v1.0.6，以正式标签 `v1.0.5@29c6f6f68ab35e25f8cf7237ee187de359c77714` 作为升级基线；平台服务管理和 Nginx/GUI 差异允许登记，但核心 API、数据、迁移和 SPA 必须等价。

### 规划交付

- 新增 `PLANS/release-artifact-equivalence-gate.md`，定义 G0～G10 发布门、C01～C12 黑盒场景、Windows/DEB/RPM/Docker 生命周期矩阵、证据格式、失败/重试/豁免策略和 6 个实施波次。
- 强制原则：同一 SHA、前端只构建一次、公共依赖统一锁定、严格模式缺任一制品即失败、build once/promote same bits、`latest` 不作为发布身份、FAIL/INDETERMINATE/NOT_RUN 全部阻断。
- `feature_list.json` 新增 feature `release-artifact-equivalence-gate-2026-08-28`，拆成 9 个 pending 任务，覆盖基线探针、构建身份、依赖锁、严格构建、Windows/Linux/Docker 生命周期、黑盒等价和安全/晋级/演练。
- `PLANS/README.md` 已增加专项计划入口。本批仅制定计划与门禁，未修改 CI、打包脚本或业务源码，未构建/发布/部署制品。
- 经用户确认删除 2024 年且已与实际完成状态冲突的 `PLANS/v1.0.9.md`；`PLANS/README.md` 移除过期入口，`feature_list.json` 移除失效 `plan_file`，一键部署历史完成证据继续保留在 feature tasks/evidence 与本日志中。

### 首批实施建议

1. W0：验证 Windows Inno/NSSM、Debian/Rocky systemd Runner、低 glibc 构建和 Node 22 兼容性。
2. W1：落地单一 release config、build-info、健康接口构建身份、Python 公共依赖锁及 qB 版本统一。
3. 以负向变异证明版本、SHA 和依赖漂移会触发门禁，再进入安装生命周期改造。

### 计划资产验证

- `feature_list.json` 经 PowerShell `ConvertFrom-Json` 解析通过；新 feature 为 pending，9 个子任务全部 pending。
- 专项计划共 657 行，`PLANS/README.md` 入口存在且目标文件可达；`git diff --check` 通过。
- 使用 Git Bash 执行根 `./init.sh` 退出 0；仅保留既有环境警告（jq 未安装、后端虚拟环境未激活、前端 init 的 null-byte warning）。

## 2026-08-28：移动端 UX 增强（mobile-ux-enhancements，P0+P1）

### 背景

移动端实测（iPhone 12 模拟器 17 张截图巡检 + 源码走查）定位核心缺口：种子卡片无实时速度、页面无自动刷新、Tab 纯文字、按钮式分页、二级页无返回导航、通知 50 条封顶、空状态无引导、汉堡触控区 36px、任务删除紧邻常规操作。计划经 3 子代理独立审查（技术可行性/回归风险/UX 合理性）修订后实施。

### 审查驱动的关键设计决策

- **复用而非新建轮询 mixin**：`speedPolling.ts` 增量扩展（`speedPollIntervalMs` 默认 1000 + `startSpeedPolling(immediate=true)`），桌面零行为变化；移动端 `immediate=false` 延迟首轮——同步首拉会击穿 mobile-torrents.spec mock 工厂（缺 `getActiveTorrents`）并打破 dashboard 调用计数断言。
- **返回按钮弃用 history.back()**：移动导航以 replace 单栈为主，back 会弹回登录页/出站；改固定回退映射（详情→种子列表、下载器设置→下载器、关键词搜索→看板、其余→仪表盘），二级页 ← 与汉堡并存保抽屉全局可达。
- **速度合并补未命中清零**：active 接口只含速度>0 种子，停止种子从快照消失，ready 后未命中行速度清零防冻结。
- **通知静默刷新与翻页互斥**：已翻页跳过本轮只同步未读角标，防重置回第 1 页；追加按 id 去重。
- **v-infinite-scroll 可用性源码级验证**：`html/body/#app height:100%` 下 `.mobile-content` 是真实滚动容器，Element 指令正确挂载。

### 已完成（6 子任务）

1. `speedPolling.ts` 扩展 + speed-polling.spec（9 tests）。
2. 布局壳：Tab 图标（house/hard-drive/download/bell）、二级页 ← 返回（meta.title 标题+空值防护）、44×44 触控区、未读轮询 hidden 门控（mobile-shell 31 tests）。
3. 种子列表：10s 速度轮询合并（buildSpeedSnapshot+traditionalTorrentIdentity 复用）、速度行（>0 渲染+min-width）、v-infinite-scroll+尾部计数、返回顶部浮标、暂停/恢复乐观状态（不 reload 保已加载页）、空态 CTA + downloader.vue `?create=1` 直达新增（mobile-torrents 21 / mobile-downloader 11 tests）。
4. 仪表盘 15s/通知 30s 静默刷新（load(silent) 不闪 loading）、通知分页去重追加、下载器空态 CTA、两页移除 m-refresh（mobile-dashboard 15 / mobile-notifications 17 tests）。
5. 详情页轮询迁移 mixin（5s+后台暂停，立即首拉语义保留）+ 移除底部冗余返回排；tasks 删除按钮分隔；pull-to-refresh 手势内回顶重置起点防指示条跳变（mobile-torrent-detail 7 / pull-to-refresh 9 tests）。
6. e2e：修正查询模板存量失效断言（页面已裁撤）、新增二级页返回映射与 Tab 图标用例。

### 验证

- 前端 Jest 全量：**84 suites / 1214 tests passed**（基线 1169 净增 45）；`tsc --noEmit` 通过；`npm run lint`（contract:check + ESLint --max-warnings 0 + vuex action 检查）零错误。
- 记录同步：feature_list.json 新增 feature `mobile-ux-enhancements-2026-08-28`（6 task + evidence）、PLANS/mobile-ux-enhancements.md、docs/roadmap/README.md 增量行。
- 已知限制：速度行/无限滚动的真机视觉验证需接入真实下载器（本地空库仅单测锚定）；e2e 新用例待 `npm run test:mobile` 环境复核；未执行 Git 提交。

### 提交后验证（同日第二批：891405b 提交后独立验证）

- git 完整性：HEAD 891405b，已跟踪文件零残留；质量门重跑全绿（Jest 1214→1216、tsc、lint）。
- Playwright e2e 双引擎首次跑通：安装 WebKit 二进制后 chromium 19 passed + webkit 19 passed（2 个数据依赖用例空库按条件跳过）；首次 webkit 冷启动一次仪表盘冒烟偶发失败，复跑通过。
- 模拟器 mock 数据视觉验证（page.route 注入 45 条种子 + active 速度）：速度行渲染/无限滚动自动两页加载/45 条满载后计数消失/返回顶部/乐观状态（暂停→已暂停、恢复→下载中）全部通过。
- **验证抓出并修复 2 个真 bug（fix 追加提交）**：
  1. 返回顶部浮标监听了 `.mobile-content` 的 scroll，但该布局实际滚动容器是 window（`.mobile-layout min-height:100vh` 被长列表撑高，`.mobile-content` scrollHeight==clientHeight 不内部滚动；技术审查的"容器内滚动"推演与事实不符）——改为监听 window.scrollY + window.scrollTo。
  2. `onListScroll` 最初写成箭头函数类字段：vue-class-component 装饰组件类时收集 data 会 new 一次类并丢弃，**组件类自身的箭头字段 this 指向被丢弃的收集实例**，`this.showBackTop=true` 静默写到死对象（mixin 基类的箭头字段不受影响，桌面 speedPolling 探针证实正常）——改为 prototype 方法。此坑已写入代码注释与单测（直调 + vm 断言锚定）。

## 2026-08-27：EXE 与 APK 构建脚本生成

### 已完成

- 保留既有 `deploy/build-windows.bat` 行为，新增 `deploy/build-android.bat`：脚本按自身位置解析仓库路径，检查 Gradle/JDK/Android SDK/build-tools，默认构建严格版与 LAN 明文测试版两个 APK。
- Android 每个变体均执行 `:app:testDebugUnitTest` + `:app:assembleDebug`，构建后复制到 `android/dist/`，并执行 `apksigner verify`、`aapt2 dump badging` 与 SHA-256 输出；支持 `--strict-only`/`--lan-only`。
- 新增根目录 `build-packages.bat`：默认统一构建 Windows EXE + Android 双 APK，支持 `--windows`、`--android`、`--android-strict-only`、`--android-lan-only`。
- 工具链解析补充 JDK 主版本校验：全局 `JAVA_HOME` 为 JDK 8 时不会误用，自动选择工作区 JDK 21；其他机器可通过 `BTDECK_GRADLE`、`BTDECK_JAVA_HOME`、`ANDROID_SDK_ROOT` 覆盖。
- README、Android 构建说明、`docs/roadmap/`、`feature_list.json` 与本交接记录已同步；未执行 Git 提交。

### 验证

- `cmd /c deploy\build-android.bat`：严格版与 LAN 版均 `BUILD SUCCESSFUL`；每个变体 13 个 JVM 用例通过，签名校验通过。
- 严格版：`android/dist/btdeck-companion-0.1.0-mvp-strict-debug.apk`，6,281,055 bytes，SHA-256 `036079612252AE55871BA2CC3003E80FD8E67DE1FC8837E71696FB9DB4C4C773`，manifest 指向严格 NSC `@0x7f110000`。
- LAN 版：`android/dist/btdeck-companion-0.1.0-mvp-lan-cleartext-debug.apk`，6,281,023 bytes，SHA-256 `08008D79EAA3EC3C650B6C314D41073BD86499378FB48E3CA0CE5CDBF726D2C8`，manifest 指向 LAN NSC `@0x7f110001`。
- `cmd /c build-packages.bat --android-strict-only`：根入口参数转发与严格版构建通过。
- 既有 `deploy/build-windows.bat` 已在本会话完整跑通：`dist/btdeck.exe` 45,814,476 bytes，SHA-256 `41B586C2A5A8892AFE181EA45E88953B2D68CD9FEAD3C7D4156AC6A6AA07C56F`；ISCC 未安装，Inno Setup 安装器按设计跳过。

## 2026-08-27：种子列表错误提示滚动收起与查询全屏蒙版

### 已完成

- 根因：两种桌面种子视图的错误原因 `el-tooltip` 仅依赖触发元素 hover 生命周期，滚轮及嵌套滚动容器滚动不会触发离开事件；查询 loading 又挂在局部容器上，蒙版随容器范围结束且未锁定页面滚动。
- 实现：新增共享 `errorTooltipDismiss` mixin，在捕获阶段监听页面/列表 `scroll` 与 `wheel` 并调用 tooltip `hide()`，组件销毁时对称解绑；两视图 tooltip 设置 `enterable=false`。两视图查询蒙版统一改为 `v-loading.fullscreen.lock`，沿用现有 `try/finally` 的 `listLoading` 生命周期。
- 测试与路线图：新增 mixin 行为测试（多 tooltip、非冒泡子容器滚动、销毁解绑），扩展双视图源码契约，并同步 `docs/roadmap/` 根索引、前端视图与测试覆盖记录。

### 回归测试加固（同日追加）

- `torrent-error-tooltip-dismiss.spec.ts` 从薄 stub 调用计数扩展为 7 个运行时用例：监听器捕获/被动参数与对称解绑、数组/单例/空 ref、普通 DOM ref 容错、window/非冒泡后代滚动、销毁后重挂载不叠加监听器，以及真实 Element UI Tooltip `show()`→滚轮→`hide()` 的状态闭环。
- 新增 `torrent-loading-mask.spec.ts`，以 Element UI 2.15.13 真实 Loading 指令验证 fullscreen mask 挂载到 body、`el-loading-parent--hidden` 锁定/释放、隐藏状态和加载中销毁清理。
- 新增共享 `loadingDirectiveProbe.ts`，两视图组件测试直接读取 Vue 编译后的 directive binding，验证 `fullscreen`/`lock` modifiers 均为 true，并通过挂起后拒绝的 API 请求验证 `listLoading` 在等待期保持 true、异常 `finally` 后复位 false。

### 验证

- 前端全量 Jest：**84 suites / 1169 tests passed**；相关 5 suites / 70 tests passed。
- `npm run typecheck`、改动文件 ESLint、完整 `npm run lint`、`npm run build` 均通过；构建仅有既有 Sass/CSS 顺序/资源体积/Browserslist 警告。
- `E:\\Git\\bin\\bash.exe -lc './init.sh --ci'` 仓库级校验通过；系统 WSL bash 的 `E_ACCESSDENIED` 以 Git Bash 规避。
- 原修复已提交为 `db6d24b`；本轮回归加固与其分为独立提交，安装包重建记录、未跟踪产物目录及生成契约的无语义行尾状态继续保留在工作区。

## 2026-08-26：伴侣模式用户名/密码记忆与会话恢复（v1.0.6-dual-mode-client.8）

### 已完成

- 桌面端 `ServerProfile` 增加 `username`；新增 `desktop_companion/credentials.py`，Windows 使用当前用户 DPAPI 加密 profile 凭据文件，密码不进入 `companion_servers.json`/管理 API。管理页增加用户名/密码字段、编辑（空密码保留）与显式清除，删除 profile 会同步删除凭据。
- 桌面端远程窗口首屏接入一次性同源登录脚本：按 profile 清理共享 WebView 的旧 token/localStorage，再用保险库凭据调用既有 `/api/v1/auth/login`，成功后写入前端现有 access/refresh cookie；TOTP 只临时 prompt，不落盘。
- Android `ServerProfile` 增加 `username`；新增 `CredentialVault`（Android Keystore AES-GCM + 独立 SharedPreferences，`allowBackup=false`），伴侣列表增加用户名/密码录入、编辑（空密码保留）与清除凭据，忘记服务器同步清除凭据。
- Android `WebViewActivity` 修复 `CookieManager.removeAllCookies` 异步竞态：等待回调后再加载 profile；有凭据时以同源脚本恢复会话，切换不跨服务器复用 token。
- 记录与路线图：`android/README.md`、`docs/roadmap/README.md`、`docs/roadmap/backend/README.md`、`feature_list.json` 已同步；新增 `.8` 子任务并登记待真机/桌面 GUI 验收项。

### 验证

- `python -m pytest backend/tests/desktop_companion -q`：53 passed（含 DPAPI 密文不落明文、改地址清理旧密码回归）。
- `gradle :app:testDebugUnitTest --no-daemon`：13 passed；`:app:assembleDebug` BUILD SUCCESSFUL（首次测试受沙箱网络限制，获准后复跑通过）。
- `:app:lintDebug` 未完成：在线解析 `kotlin-compiler-31.7.3.jar` 超过 120 秒，离线模式因该依赖未缓存退出；不是源码编译错误，待具备完整 Gradle 缓存/网络的 CI 复核。
- 尚未执行 Git stage/commit；保留既有未跟踪 `.tmp-desktop-gui-test/`。

## 2026-08-26：修复 GitHub CI 审计枚举成员数断言

### 结果

- 根因：`AuditOperationType` 已新增 `SCHEDULED_TASK_INTERRUPT`，实际成员数为 48，但枚举测试仍断言 47。
- 修复：补齐 `scheduled_task_interrupt` 的合法值、显示名、分类、构造和字符串行为测试参数；成员数断言更新为 48。
- 文档：路线图同步 `AuditOperationType` 为 48 个成员，`AuditOperationResult` 行号同步为 L257；`feature_list.json` 已补充 CI 修复证据。
- 验证：`python -m pytest tests/enums/test_audit_enums.py -q`，291 passed，4 warnings；审计 API 操作类型回归 4 passed；Flake8、JSON 解析和 `git diff --check` 通过。Black 24.10.0 CLI 在 Windows 上超时，但 Black 纯库格式化接口返回 `NothingChanged`，确认文件已符合 line-length=120 格式。
- 环境限制：根目录 `bash ./init.sh` 仍因当前 Windows 环境缺少可用 WSL 发行版无法执行，与本次 pytest 失败无关。

## 2026-08-25（第二批） - 定时任务停止治理：超时强杀 + interrupt 真取消 + MissingGreenlet 根修

### 背景（生产事故诊断）

用户复现"Tracker 状态同步任务没有正常停止"。日志定位：`cron-7-20260825111000`（task_id=7，cron_run_id 自带时间戳）11:10:00 触发，两个 tr 下载器 6~22s 正常完成 checkpoint 后，qb 下载器 `dabb1e6f` 的 `tracker_enrich_single_torrent` 阶段连续 `qb_fetch_trackers` TimeoutError，11:11:40 后绝对静默；至 20:01 仍每 30s 心跳（elapsed≈8.75h，timeout_exceeded=True 却无终止），持有 heavy_sync（容量 1）连锁堵死 Tracker 汇报轮询/消息记录/路径扫描/种子信息同步 4 个任务（ADMISSION_SKIP）。`正在运行中，跳过本次执行` 0 条（后续触发全被准入层拦截，未到重入检查）；pause/interrupt 成功路径无日志且对运行协程无效（running_tasks 标志仅在下次执行前检查）。

### 实施内容（6 项，双子代理独立审查修订后执行）

1. **cron 层超时强制终止**（`cron_executor.py`）：`_execute_internal_method_observed` 以 `wait_for` 包裹执行体；`timeout_seconds<=0` 归一 None（wait_for(0) 立即取消不合理）；任务体自身 TimeoutError 在执行入口 guard 包装为 `_TaskBodyTimeoutError`——因 Windows ~15.6ms 时钟粒度下 wait_for 可能早于 timeout 触发，elapsed 判定不可靠（实测 15ms<20ms 复现），来源标记法是唯一可靠区分；`TaskExecutionTimeoutError` 经 `_run_python_internal_class` 穿透分支（907 行 except Exception 会吞掉任何穿透异常——审查发现的死代码陷阱）直达 `_execute_task` 落库 outcome=failed。开关 `CRON_TASK_TIMEOUT_ENFORCE` 默认 True。
2. **interrupt 真取消**：`_execute_task` 自登记 `asyncio.current_task()` 句柄（覆盖 APScheduler 调度与 start_task_immediately 两入口）；`interrupt_task` cancel 后 `gather` 等收尾三写完成（消除立即重启并发写 task 行窗口）；`except asyncio.CancelledError` 分支区分用户中断（outcome=cancelled + success=True，对齐 skipped 口径与统计卡片）与调度器关闭（re-raise；CancelledError 是 BaseException，except Exception 捕不到——项目既有教训）。
3. **MissingGreenlet 根修**（`cron_crud_async.py`）：审查查明真因是 `CronTask.update_time` 的 `onupdate=func.now()` postfetch 过期（独立于 expire_on_commit=False），非偶发 greenlet 交错。修复：commit 后 `await db.refresh(task)`。**回归有效性已验证：移除 refresh 两测试即失败（MissingGreenlet 在测试环境复现），恢复即通过。**
4. **观测完善**：`SYNC_TASK_PROGRESS_STALL_WARNING_SECONDS`（默认 300s）心跳停滞提级 WARNING + `progress_stalled=True`（入 EVENT_TASK_LIFECYCLE 白名单，白名单外字段被静默丢弃）；首次触发 `faulthandler.dump_traceback()` 自动留全线程栈现场（每次运行至多一次）——下次卡死不再依赖人工 py-spy；skipped 任务完成日志改打"已跳过+原因"。
5. **认证检查一次性客户端补超时**（`initialization.py` 393/429）：qb `REQUESTS_ARGS={"timeout": 30}`、tr `timeout=30.0`，与缓存客户端对齐；外层 wait_for 只放弃等待不回收线程，缺 requests 超时是线程泄漏根因。
6. **interrupt 审计**：`SCHEDULED_TASK_INTERRUPT` 枚举三处 + 端点接线（显式传 ip/user_agent/request_id/session_id，mypy variance 不接受 **dict 展开）+ 前端 audit.vue 筛选与 typeMap 映射。

### 已知限制（发布说明需含）

- 强杀范围限 task_type=4；脚本(0-3)/清理(5)/审计导出(6)超时不终止（interrupt 取消仍可用）
- thread 模式超时仅放弃等待：孤儿线程继续跑完并持有 downloader_api_runtime per-downloader 令牌，但不再占 heavy_sync
- wait_for 与心跳均依赖事件循环：循环被同步调用阻塞时两者共盲（后备 `faulthandler.dump_traceback_later` 独立线程未实施，列为可选）
- 存量任务 timeout 核查：默认任务 300~7200s 与历史正常运行时长一致（判定 300s 生产每轮正常完成、孤儿类 7200s 有内部预算控制），唯一超时正是不该跑 8.75h 的本案例——无需调整

### 条件项（挂起，待生产取证）

- 预算 0 值语义：`QB_TRACKER_RUN_BUDGET_SECONDS=0=不限时` 是文档化行为且被 2 个测试锚定；若生产取证 `Enriching` 行 budget_seconds=0 则按"参数与 settings 双层收紧 + INFO_SYNC 侧同批"实施，路径 B（挂死）则不做（强杀已兜底）
- `_sync_speed_schedule`（每分钟、全链路同步 HTTP 无超时）为审查发现的同型挂起点，取证后单独立项
- **取证命令包已交用户**：grep QB_TRACKER_ENRICH Enriching/Completed 行、event=downloader_call 计时（queue_wait_ms 高=令牌泄漏 vs remote_call_ms 高=远程慢）、挂死时 `docker exec ... faulthandler.dump_traceback`

### 回归保护批次（同日第三批，+15 用例）

按风险保护价值补齐未被初始测试锚定的改动面：

1. **停滞观测全链路**（TestProgressStallObservation 3 例）：停滞心跳提级 WARNING + progress_stalled=True、faulthandler 线程栈转储整次运行至多一次（节流防日志风暴）、进度持续推进时抑制告警、阈值 0 完全关闭——直接调 `_execute_internal_method_observed` 并 mock `faulthandler.dump_traceback`
2. **重型任务超时锁释放**（生产 8.75h 占锁事故的直接锚点）：真实注册表重型 task_code 超时被杀后 `admission_controller.running` 无残留、令牌可立即重新 acquire
3. **真实链路 interrupt 集成**：不 mock `_run_task_script`，注入真实 fake 任务类经 `_run_python_internal_class` → observed 的 `wait_for` 挂起，interrupt 的 cancel 必须穿透 wait_for（外层 cancel 传播 CancelledError 而非转译 TimeoutError）与两层 `except Exception` 兜底，最终按 cancelled 落库——强杀与中断两个新机制共存性的唯一集成验证
4. **早退路径清理**：读会话失败早退时句柄/中断标记 pop/discard 无残留（防 KeyError）
5. **认证客户端超时构造**（新文件 tests/downloader/test_auth_client_timeout.py 2 例）：qb `REQUESTS_ARGS={"timeout": 30}` / tr `timeout=30.0` 构造断言
6. **interrupt 审计接线 + 统计口径**（API 层 3 例）：成功/失败均落审计（operation_type/operator/task_name/operation_result，隔离 AsyncSessionLocal 防写开发库）；statistics 中 cancelled（success=True）计入成功卡片——若有人把 interrupt 落库改回 success=False，统计契约随之报红
7. **progress_stalled 白名单落盘**（observability 1 例）：EVENT_TASK_LIFECYCLE 专属字段在白名单内输出（白名单外被 format_event_line 静默丢弃，漏登记只提级日志而丢机器可读标记）
8. 现有中断用例补 freshness 断言（last_outcome=cancelled、advance_success=False）；强杀开启时普通异常路径不变、timeout 未配置不强制等负向护栏

结果：相关套件 475 passed（原 461 + 15 新增 - 1 重构合并）；改动文件 black/flake8 全过。注：`black --check tests/` 全目录有 62 个历史文件本就未格式化，属既有状态未触碰。

### 追加：下载器级硬熔断（用户决策，task .8）

用户指出不应依赖 cron 层超时兜底、请求 tracker 时就应主动中断：enrich 内部预算是**协作式检查点**（worker 挂死时永不执行，8.75h 案件形态），必须补强制取消层。在 sync_coordinator tracker 分支对 qb/tr 同步包 `asyncio.wait_for` 硬超时（`TRACKER_SYNC_DOWNLOADER_TIMEOUT_SECONDS` 默认 1800s=半小时，0 关闭）：超时强制取消该下载器（私有 db 会话由 async with 丢弃未提交事务）、记 failed + `DownloaderHardTimeout` 事件 + "已主动中断（不影响其余下载器）"错误文案、放行其余下载器。防御分层完整：per_call 30s → enrich 预算 120s（协作式）→ **下载器级 1800s 硬熔断（强制取消）** → cron 3600s 兜底。测试 TestTrackerDownloaderHardTimeout 4 例（qb 中断/tr 对称/一熔断一成功汇总 partial/配置 0 关闭语义）。

### 追加：真凶根修（task .9，22:38 日志 + 双子代理验证裁决后实施）

22:32 轮（新版本已部署）复现挂起形态，**faulthandler 线程栈转储首次实战立功**；双子代理独立验证裁决：'SSL 握手无限挂'被实验证伪（timeout=30 经 socket.settimeout 完整覆盖 TLS 握手，生产 HTTPS read timeout 警告即证据），真凶为双因——①库层放大器：_clean_host_url 剥 scheme 后 qbittorrentapi 每次 context 重建做 HTTP→HTTPS 双方案探测（先 HTTP 后 HTTPS）× urllib3 Retry(connect=1) × _request_manager 2 轮 × 30s/段 ≈ 单调用 6 分钟（转储时线程在流水线第 252 秒）；②项目层挂死直接原因：producer 哨兵 put 0.5s 超时 break 丢弃全部哨兵（时序重放与生产 4 个 hash 前缀逐条吻合，90% 置信定位 worker queue.get() 永久挂点；且为独立于下载器故障的纯代码缺陷，健康下载器慢消费同样可复现）。

修复四项：enrich 哨兵双保险（producer 30s 总限重试 + worker get 5s 轮询自愈，覆盖全部 4 个调用点）；qb 构造 FORCE_SCHEME_FROM_HOST=True + host 按 is_ssl 补 scheme（消除探测放大）；HTTPADAPTER_ARGS max_retries=0（关双层重试）；requirements qbittorrent-api 对齐实装 2025.2.0。实施中发现并修正自身引入的退化：预算到期场景 producer 白等 30s（重试循环检测 budget_reason 立即放弃，既有 test_budget_expiry_returns_quickly 锚定）。+5 测试例（哨兵确定性回归 + 构造/scheme 断言），相关套件 610 passed。已知残留：熔断救任务不救线程令牌（P2 待立项下载器健康熔断）。

### 生产取证裁决（2026-08-25 22:12 回报）

用户回报 Enriching/错误日志，根因裁决完成：

- **路径 A（预算禁用）排除**：`budget_seconds: 120.0` 默认值在位
- **路径 B 实锤**：`queue_wait_ms=0.0`（无令牌泄漏）+ urllib3 `ReadTimeoutError(192.168.5.51:28180, read timeout=30)`——qb 下载器 dabb1e6f 的 WebUI 对单种子 trackers API 收到请求但 30 秒不返回响应体（requests 超时正常生效）
- **本轮治理全部正常**：4 hash × 30s ÷ 2 worker = 60s enrich（22:09:20→22:10:20 两条超时事件完全吻合），任务 ~120s 结束（心跳 elapsed_ms=120002 印证）；对比 8.75h 旧案是不同容器实例（1-84c6ad0855d6 vs 1-ffc65da65b80，中间重启过），旧案同诱因叠加更深挂点、已被超时强杀兜底
- **task .7 关闭不实施**；行动项移交外部：修复/重启 qb 192.168.5.51:28180（curl 直连其 trackers API 验证；其游标 cursor=None 全失败永不推进，每轮烧 120s 预算重试 4 个 hash，qb 恢复后自愈——另一 qb b58ee7b2 的 791 个种子全部 durable 健康，问题专属该实例）

### 验证

- pytest 相关套件 461 passed（tests/tasks 全目录 + cron_tasks_outcome + tracker_budget + sync_observability）；新增 TestTimeoutEnforcement 4 例、TestInterruptRunningInstance 3 例、freshness 真实会话 2 例（回归保护批次后合计 475）
- mypy 零错、black（24.10.0）已格式化、flake8 通过；前端 eslint（audit.vue）通过
- 配置三件套：config.py 默认值 + .env.example 注释 + docker-compose.yml environment 透传（容器内无 .env，不透传则只能用代码默认值）
- 根 ./init.sh（ci）通过；Git 未提交（待用户指示）

## 2026-08-25 - 主 Logo 品牌资源接入

### 实施结果

- 新增 `frontend/public/img/brand/btdeck-logo.png`（完整 Logo）与 `btdeck-mark.png`（环形图标版），均为透明背景并裁剪了外部留白。
- 新增 `frontend/src/components/common/AppLogo.vue`，统一按 `full`/`mark` 变体加载 public 品牌资源。
- 桌面侧边栏、顶部栏、桌面登录页，以及移动顶部栏/登录页均已接入；登录页使用完整 Logo，导航与小尺寸入口使用 mark。
- 重写 `frontend/scripts/generate-pwa-icons.py`，从 mark 生成 favicon、Apple Touch Icon、Android、maskable 和 Windows 图标；`public/index.html` 增加 SVG/PNG favicon 与 Apple Touch Icon 引用。
- `pwa-manifest.spec.ts` 增加品牌资源契约，路线图已同步通用组件与布局职责。

### 验证

- `npm run typecheck`：通过。
- `npm run test:unit -- pwa-manifest.spec.ts`：6/6 通过。
- Vue lint、Vuex action lint、`npm run build`：通过（构建有既有 Sass/Browserslist 警告）。
- 完整 `npm run lint`：被既有 `advanced-search-contract` 生成契约过期检查拦截，未自动重生成无关契约。
- `bash ./init.sh --ci`：当前 Windows WSL 环境访问被拒绝，未进入全栈验证。

## 2026-08-23 - 前端静态展示 Demo feature 登记

### 计划登记

- 新建 `PLANS/frontend-static-showcase-demo.md`，将上一轮“前端打包为可展示 Demo、后端相关交互改为静态数据”的评估拆为 7 个可验收任务：范围与契约、Demo 入口/认证旁路、集中式静态请求层、本地状态仓库、核心页面、扩展页面/特殊路径、独立打包与回归验收。
- 在 `feature_list.json` 新增 `frontend-static-showcase-demo-2026-08-23`，父 feature 与 7 个子任务均登记为 `pending`，不代表已经实现或完成构建。
- 方案边界：后端源码、数据库和真实下载器不改；生产模式继续使用真实认证/API；Demo 模式只使用脱敏 fixtures 和本地状态模拟。

### 验证与遗留

- `feature_list.json` 已通过 PowerShell JSON 解析；计划文件与 feature 的 `plan_file` 路径一致。
- 本次未增加或修改业务源码，未执行 Git stage/commit/push。
- 根 `./init.sh --ci` 仍受当前 Windows/WSL `E_ACCESSDENIED` 环境问题影响；Demo 构建、前端源码实现和浏览器验收留待后续任务。

## 2026-08-23 - 双模式客户端计划评审修订与 v1.0.6 清单登记

### 结论

- 安卓服务端保留为技术可行但轻量/临时定位，伴侣模式作为可独立先行的 MVP；桌面/NAS/服务器仍是长期运行主力。
- Phase 0 新增 Play/FGS/备份/安全预审和完整 BtDeck import graph 门禁；Phase 1 修正为 TCP 探测、可写路径、打包资源、依赖/工具链矩阵和 Android capability matrix。
- 伴侣 MVP 明确采用远程同源 WebView；内置前端 + runtime baseURL、CORS 和跨服务器凭据隔离不提前混入首版。

### 变更

- 重写 `PLANS/dual-mode-client.md`：补充 `TORRENTS_DIR`、Alembic/frontend dist 打包、HOST/CORS 分离、FGS 类型边界、明文 LAN、自签证书、Keystore/backup、SAF、设备矩阵和真实包体验收。
- `feature_list.json` 新增 `v1.0.6-dual-mode-client` 独立条目，包含 7 个 pending 阶段；原已完成的 `v1.0.6` 孤儿文件任务保持不变。
- 未修改后端、前端或 Android 源码；未创建 wheels 仓库；不代表 Phase 0 已通过。

### 验证与遗留

- `feature_list.json` 通过 PowerShell JSON 解析；新条目为 7 个 pending tasks；`git diff --check` 通过。
- 根 `./init.sh --ci` 的既有 Windows/WSL `E_ACCESSDENIED` 环境问题仍未作为本次计划变更的有效门禁。
- 工作区已有未跟踪 `.release-build-v1.0.5/`；本次业务内容新增/修改为 `PLANS/dual-mode-client.md` 与 `feature_list.json`，`progress.md`/`session-handoff.md` 仅同步记录，均未提交 Git。

## 2026-08-22（六） - v1.0.5 发布前修正 GitHub 仓库地址

### 实施

- 基于已合并的 `origin/master` 创建发布修复分支 `codex/release-v1.0.5-repo-url`，避免把本地 `dev` 尚未推送的提交混入发布基线。
- 将运行时版本检查、定时任务显式调用、`VERSION_HISTORY` 中 v1.0.3/v1.0.4/v1.0.5 的 Release 链接、欢迎通知脚本和根 README 统一改为正式仓库 `strainhzj/BtDeck`。
- 说明：已部署的 v1.0.4 若已将错误仓库地址固化在程序中，无法由 v1.0.5 反向修改；本修复自 v1.0.5 合并并发布后对新部署生效。

### 验证

- `python -m pytest tests/tasks/test_cron_policy_notify.py tests/tasks/test_cron_executor.py tests/tasks/test_cron_executor_admission.py tests/tasks/test_cron_executor_security.py`：42 passed。
- 目标 Python 文件 `compileall` 通过；`git diff --check` 通过；仓库内不再残留错误仓库地址。

### 发布前置

- 该分支仍需合并到 `master`，再以合并后的提交创建并推送 `v1.0.5` tag，最后创建 GitHub Release；Docker 镜像需指向同一发布提交。

## 2026-08-21（第五批） - 按 v1.0.5 更新日志同步根 README.md

### 实施

- 以 `backend/app/version.py` 中 1.0.5 的 `content`（发布日期 2026-08-21）为权威来源更新根 `README.md`：
  - 「核心特性」补入 v1.0.5 新能力三条：高级搜索与查询模板、孤儿文件管理、Tracker 异常识别。
  - 「版本历史」表新增「发布日期」列；v1.0.5 主题对齐 version.py summary（孤儿文件管理 + 查询模板 + 安全加固 + 大量问题修复），状态由「本次发布」改为「已发布」。
  - 新增「v1.0.5 更新亮点」小节：孤儿文件管理 / 查询模板 / 种子列表增强 / 安全加固 / 性能与稳定性 / 安装与部署 / Bug 修复七条精简摘录，附 version.py 与 GitHub Release 链接及数据库自动迁移提示。
- 未改动源码与 docs/roadmap/（纯根 README 文档更新，roadmap 第一层模块路由内容不受影响）。

### 验证

- 纯 Markdown 文档变更，无代码路径影响。按仓库规范，未经用户要求不执行 Git 提交。

## 2026-08-21（第四批） - 后端 mypy 存量报错清零（1617 → 0）+ 8 个休眠 bug 修复

### 排查定性

- 全量 `mypy app/` 基线 **1617 错误 / 117 文件**（历史记录为 203 条 SQLAlchemy Column 报错，实际远超）。错误构成：模型 `Column[...]` 类型污染 ~750、CommonResponse/pydantic `Field(None)` 位置默认值 ~100、隐式 Optional 参数 77、`result` 混合字面量字典窄化 ~80、rowcount/ClauseElement 等零散。

### 实施分层

1. **根因一：ORM 模型全量迁移 `Mapped[] + mapped_column()`**（ast 脚本 + 人工收尾）：21 个模型文件、451 处 Column 声明、3 个 relationship；nullable 语义按 `Optional[X]` 精确对齐（pk/nullable=False → X，其余 → Optional[X]）。`Base = declarative_base()` 改 2.0 类式 `class Base(DeclarativeBase)`。**DDL 快照（33 表/99 索引）迁移前后逐字节一致**，schema 零漂移。
2. **根因二：pydantic 位置默认值**：`Field(None, ...)`/`Field(0, ...)` 等 315 处（27 文件）改 `Field(default=..., ...)`——mypy 的 dataclass_transform 不识别位置默认值，会把可选字段误判为构造必填。
3. **根因三：隐式 Optional 参数**（77 处脚本修复）+ FastAPI `Request` 参数特判：`Optional[Request]` 会破坏 FastAPI 注入（启动即 FastAPIError），改为必填 `Request` 并上移到首个带默认值参数之前。
4. **根因四：SQLAlchemy 2.0.15 typing 缺口**：`rowcount`（19 处 getattr 规避）、`execute()` 变量跨类型复用（tracker 等文件变量改名消除串扰）、`case()`/`in_()`/传输存根 list 不变型（cast 规避）。
5. **长尾逐文件清理**：混合字面量 result 字典补 `Dict[str, Any]`、`min_items/max_items` 改 v2 的 `min_length/max_length`、`Query(examples={...})` dict 改列表形态、安装 types-requests/types-PyYAML/types-croniter 存根（requirements-dev 已登记）。

### 顺带修复的休眠 bug（全部被宽泛 except 吞掉或必抛 TypeError，mypy 揪出）

1. `seed_transfer_service` 降级备份目录 `settings.BASE_DIR` 不存在（AttributeError → 备份从未落盘），改用 `BACKUP_TORRENT_DIR` 统一推导。
2. `advanced_search.delete_torrents_batch` 漏 `await` 协程（读 success_count 必炸），方法改 async + 端点 await。
3. `file_operations` 的 `run_in_executor(None, os.makedirs, path, exist_ok=True)` 不接受 kwargs（必抛 TypeError），改 `functools.partial`。
4. `torrent_location_service` 审计构造传 `torrent_count/move_fields` 不存在字段（必抛 TypeError，位置修改审计从未落库），映射到 `torrent_name/delete_source` 现有列。
5. `tracker_operations` 引用不存在的 `TrackerInfo.id_`（5 处），改 `tracker_id`。
6. `cron_crud/cron_crud_async` 调用不存在的 `DatabaseResult.not_found`（6 处），改 `not_found_result`。
7. `torrent_crud_service` 构造 `TorrentInfo(id_=...)` 属性名错误（2 处）；死函数 `get_trackers_by_status` 引用不存在的 `tracker_status` 列，按 `last_scrape_succeeded` 语义修正。
8. `tracker_messages` 构造/赋值不存在的 `judgment_result` 列（4 处引用移除）；`torrent_deletion` 审计映射引用不存在的 `DeleteOption.LEVEL1-4`（批量删除审计从未落库），按实际枚举成员映射。
9. 删除不可运行的死文件 `app/websocket_main.py`（import 不存在的 `factory.wsapp` 与 `settings.WS_PORT`，全仓无引用）。

### 其它说明

- `TagService` 双模（同步/异步）重构为 `_sync_repository/_async_repository` 双引用 + 取用器，错配时显式报错；`AsyncTorrentTagRepository` 保留（tag_sync 定时任务在用）。
- `torrent_status` 5 个批量操作端点 body 改必填（缺 body 由 500 AttributeError 变 422）。
- SeedTransferAuditLog 的 `*_downloader_id` Integer 列存 UUID 文本（SQLite 类型亲和）以 `type: ignore` 记录，列类型矫正需迁移另行处理。

### 验证

- `mypy app/`：**Success: no issues found in 246 source files**（0 错误）。
- `black --check` / `flake8 app/`：通过（既有 `\s` 转义 SyntaxWarning 为历史存量，非本次引入）。
- `pytest tests/` 全量：**3874 passed / 7 skipped**（多次中间检查点均全绿）。
- DDL 快照终验：与迁移前基线完全一致。

## 2026-08-21（第三批） - 任务日志/孤儿文件统计卡片折叠与持久化

### 实施

- 用户确认在“定时任务-任务日志”和“孤儿文件-孤儿文件”页签中，让统计卡片区域支持收缩/展开，并在刷新后保留偏好。
- 两处均复用全局 `CollapsiblePanel`，不改变统计数据、筛选、表格和分页逻辑；任务日志使用 `btdeck_task_log_stats_collapsed`，孤儿文件使用 `btdeck_orphan_file_stats_collapsed`，两个页签状态相互独立，默认展开。
- 新增 `management-pages-ui.spec.ts` 契约断言，锁定两个页签的面板接入、统计区域保留和 localStorage 键隔离。

### 验证

- `management-pages-ui.spec.ts`：14 passed。
- 任务日志、孤儿文件及契约测试文件 ESLint 通过；前端 `npm run typecheck`、`npm run lint`、`npm run build` 均通过；生产构建保留 58 条既有 Sass/资源体积类 warning，无编译错误。
- 根目录经 Git Bash 执行 `./init.sh --ci` 通过；检测到工作区原有 80 个未提交变更。
- 已提交为 `9647556`（`feat(frontend): persist collapsible management stats`）；工作区既有后端未提交改动保持原样。

## 2026-08-21（第二批） - 列宽拖拽两缺陷修复：名称列手柄 + 传统模式手柄整体失效

### 排查定性

- 用户反馈：①名称列无拖曳手柄；②传统模式所有列无手柄。
- **②根因**：手柄全部样式（`.column-resizer` 定位/命中区/光标/hover 反馈条 + `th:not(.action-column){position:relative}` 定位基准）只写在 `torrent-theme.scss`，而该文件仅被 `index.vue` 以 **scoped** 方式引入；TraditionalView 引入的是 `traditional-view-theme.scss`（无任何手柄规则）→ 传统模式手柄 span 在 DOM 中零样式，不可见不可拖。
- **①性质**：原设计即名称列不登记宽度不渲染手柄（唯一 auto 列吸收全部剩余空间）。是否给手柄涉及布局行为变更，经用户决策选定 **qBittorrent 风格严格列宽**（视口富余时表格右侧留白，不按比例拉伸；备选方案为保持拉伸填充）。
- **顺带发现的隐藏 bug**：`body.column-resizing`（拖拽期间全局光标/禁文本选择）写在 scoped 引入的文件里，编译成 `body[data-v-x]` 从未匹配过 `<body>`——两个模式下都从未生效。

### 实施

- **手柄样式全局化**：抽 `styles/torrent-column-resize.scss`（手柄全套 + th 定位基准 + body 拖拽态 + 传统浅色表头反馈条改 `var(--color-primary)`），在 `styles/index.scss` 全局引入；`torrent-theme.scss` 移除原规则留指引注释。文件头注释写明"必须全局引入"的防回归原因。
- **名称列手柄 + 严格列宽**（两视图）：名称 th 加 `columnWidthStyle('name')` 绑定 + 手柄（sortable th 内 stop/prevent 防误触排序）；`defaultColumnWidths` 登记 `name`（列表 400px / 传统 200px，旧 localStorage 无该键自动落回默认）；`tableMinWidth` optionalKeys 计入 name、去掉 `+200`；表格内联 `width+minWidth` 双绑定列宽总和（覆盖 `.torrent-table/.traditional-table` 的 `width:100%`，该类规则仅弹窗等未定宽场景继续用）；mixin 头注释同步。
- 行为变化：名称列不再随窗口变宽自动填满；所有列严格按设定宽渲染，拖拽全程 1:1；视口比列宽总和宽时表格右侧留白。

### 验证

- 变更文件 eslint 0 错误；全量 npm run lint 通过；`column-resize-mixin.spec` 8 用例与全量 58 suites / **899 passed**；生产 build 通过。

### 三、名称列过长省略号定性 + 跟随列宽修复

- 用户反馈"名称过长显示...，要求前端处理而非后端截断返回"。全链路排查定性：**后端从未截断**（TorrentInfoVO 原样返回、同步写库全量、前端 API 层直传），`...` 是前端 CSS；真正缺陷是 `.torrent-name-text` 硬编码 `max-width: 300px`——名称列可拖宽（默认 400/最大 600px）后文字仍在 300px 处截断，列内留白。
- 修复：列表模式 `.torrent-name` 加 `overflow: hidden`、`.torrent-name-text` 去 `max-width: 300px` 改 `flex: 1 + min-width: 0`，省略号跟随列边界（悬停 title 仍显全名）；传统模式 `.torrent-name-cell` 原先无任何样式（td 的 overflow 兜底只裁剪不出 `...`），补 `overflow: hidden + text-overflow: ellipsis`。
- 验证：eslint 0 错误、traditional-view-component.spec 30 passed、生产 build 通过。

### 四、回归保护 + 提交

- 新增 `column-resize-regression.spec.ts` 5 组源码扫描契约：手柄样式唯一来源全局 partial（两份 scoped 主题不得再携带 .column-resizer/body.column-resizing——传统模式失效根因的防回归锚点）+ 传统表头反馈条主题色；名称列两视图登记宽度 + 手柄绑定；tableMinWidth 计入 name 无 +200；表格 width+minWidth 严格定宽双绑定；名称省略跟随列宽（无 300px 硬编码）。
- 两视图组件 spec 各 +1 运行时用例：表级 `width=minWidth=tableMinWidth`、名称 th 内联宽、手柄 mousedown→body 拖拽态→mousemove 位移更新→mouseup 落盘视图独立存储 key。
- 验证：全量 **59 suites / 906 passed**（+7 用例）、npm run lint 通过；随后按用户指示执行 Git 提交。

## 2026-08-21 - 合并 origin/dev（981 处冲突）+ 种子列表双模式可调列宽

### 一、前置：解决搁置的 git pull 合并冲突（合并提交 afc3c34）

仓库处于未完成的 `git pull`（origin/dev → dev）合并：**181 个文件、981 处冲突标记**（backend/app 514 块、backend/tests 188、frontend 源码+测试、deploy、docs/roadmap、配置文档）。双方各有 30+ 个独有提交，为真正的双开发者分叉。按用户决策逐主题解决：

- **辅种异常排查二选一**：保留远端"表格内嵌筛选版"（`same_content_only` 列表条件 + el-alert + 退出入口），删除本地"弹窗版"6 文件（SameContentInspectionDialog 组件/spec、same_content_inspection 端点/服务/测试/API 文档）并从 api.py 摘除注册。
- **采纳远端**：辅种数量列、Tracker主域名筛选、Tracker异常标签（展示对齐）、双令牌 W6/W8/W9、安全修复 W1-W15、孤儿扫描异步队列重构（前端 orphan-files 视图 50 处 + API/后端服务全链一致取远端）、TorrentDetailCard 共享卡片（取代两视图旧内联面板，含 detail-panel-trad 下线）、部署打包加固、router NavigationFailure 修复。
- **保留本地**：路由 keepAlive meta、Tracker 状态判定回归（已在非冲突区自动合并）、W3/W4 同步观测、高级搜索语义修复、downloader_id String 迁移（b6e1c4d9a2f7）。
- **合并一致性修复 4 处**：①`975dad435c03` 辅种列迁移加 inspect 幂等守卫（远端遗留——版本回拨重放时 duplicate column，远端 08-20 日志已自认存量问题，本次治本）；②`verify_password` 对前缀正确但截断的 bcrypt 哈希先做 60 字符结构校验（新版 bcrypt Rust 实现直接 panic 而非 ValueError）；③`resolve_external_path` 兼容 POSIX 绝对路径（Windows 宿主 `os.path.isabs('/downloads/...')` 为 False，桌面版 Windows 部署受影响）；④删除 `enhanced_python_executor.py` 死代码（远端安全修复已删并清空 BTD301 白名单，本地残留导致架构测试红）。
- 验证：后端全量 pytest **3874 passed / 7 skipped**；前端 tsc、ESLint 0 错误、**891 单测**、契约重新生成、生产 build 通过。修 tasks-sync-freshness.spec 一处行尾脆弱断言（CRLF 检出下多行 toContain 不匹配，读源码后归一化 `\r\n`）。

### 二、新功能：种子列表双模式可调列宽 + localStorage 持久化

- **共享 mixin** `src/views/torrents/mixins/columnResize.ts`（仿 speedPolling 的 vue-class-component 模式）：th 右缘手柄拖拽、宽度夹取 [40,600]px、mouseup 一次性写 localStorage（两视图独立 key `btdeck_torrents_column_widths` / `btdeck_traditional_column_widths`，只认登记列键，新增列自动落回默认）、双击手柄恢复单列、`resetColumnWidths()` 供列设置菜单"重置列宽"、document 监听与 `body.column-resizing` 拖拽态随 mouseup/销毁成对清理。**踩坑记录：类字段箭头函数被 vue-class-component 收进 data 后 this 指向构造期临时实例，拖拽会话失效——改方法 + boundXxx 存储绑定引用**。
- **列表模式 index.vue**：12 列静态内联宽 → `columnWidthStyle()` 绑定 + 手柄（名称列自适应、复选框列可调无手柄、sticky 操作列兼容）；`tableMinWidth` computed 动态 min-width（容器已有横向滚动）。
- **传统模式 TraditionalView.vue**：14 列 th 内联宽覆盖 `.col-*` SCSS 兜底值；静态 `min-width:1435px` 改 computed 动态（SCSS 值留首帧兜底）；虚拟滚动（32px 行高/spacer 行）不受影响。
- **全局样式** torrent-theme.scss：`.torrent-table` 补 `table-layout: fixed`（传统表远端已自带，本次主要影响列表模式）使 th 宽度成为权威列宽；td 溢出省略；`.column-resizer` 手柄（6px 命中区、hover 反馈条、sticky 列贴右缘）。
- 验证：新增 `column-resize-mixin.spec.ts` 8 用例（初始化/存储覆盖/损坏回退/拖拽夹取/落盘时机/双击重置/全部重置/销毁清理）；全量 58 suites / **899 passed**；tsc、lint（含自动格式修复）、生产 build 通过。

## 2026-08-20（第二批） - 展示对齐判定：Tracker 异常可见化与 Announce 状态覆写

### 排查与定性（生产副本实测 + 独立审查）

- 用户报告 `getList?status=error&same_content_only=true` 查出"无错误信息"的种子（锦心似玉组）。桌面生产副本 app.db 实测定性：error 筛选口径为 `status='error' OR has_tracker_error=True`，命中的 953/1348 行是 seeding+has_tracker_error=1（tracker 层失败、`has_tracker_error` 不在 VO 返回、前端零引用）→ UI 显示"做种中"无任何错误标识。
- 深挖发现 Transmission 上报特性：PT 站以 HTTP 200 + bencode failure reason 拒绝时，daemon 记 `lastAnnounceSucceeded=true`（传输层成功）+ result=失败文本；全库 349 行"状态码 2+失败文本"全是策略类拒绝（重复做种/重复汇报/passkey），5793 行状态码 3 全是连接类错误。展示层信了布尔值（✓工作中），判定任务信了消息文本（has_tracker_error=1）——判定是对的，展示错信。
- 实施前两轮独立审查（后端/前端各一）：抓出 3 个测试阻断项（5 个 fixture 缺 tracker_keyword_config 表 / torrent-error-reason-ui.spec 钉死视图内字面量 / 治理测试按 `__name__=="_load_keywords"` 断言 to_thread）、1 个布局缺陷（传统视图 table-layout:fixed 下 90px 状态列裁掉追加标签）、2 个语义边界（not-contacted 残留消息不覆写、duplicates 端点 error 筛选口径不一致），全部吸收进实施。

### 实施内容（后端 6 文件 + 前端 10 文件）

- 后端：
  - 新增 `core/tracker_keyword_map.py`：`load_active_keyword_map()` 加载 failed/success/ignored 三池（first-wins、异常返回空池降级）；判定任务 `_load_keywords` 委托复用（**方法名与 to_thread 调用点是治理测试锚点不可改**），种子级判定与展示覆写共用同一映射保证口径一致。
  - `core/tracker_status_policy.py`：新增 `tracker_message_failed()`（单消息精确命中失败池，守卫非 str/空串）与 `tracker_display_failed()`（覆写裁决：消息命中失败池且非中性码——qb==1/tr∈{0,1} 残留消息不采信，与判定任务语义一致）；`FAILED_DISPLAY_TEXT` 与两套枚举 code=3 文本一致。
  - `torrents/responseVO.py`：TorrentInfoVO 新增 `has_tracker_error`（alias 输出 hasTrackerError）。
  - `api/endpoints/torrent_helpers.py`：`convert_to_vo_with_trackers` 可选参 `tracker_keyword_map`（None 不覆写防 N+1），announce/scrape 文本在消息命中失败池时覆写"工作失败"（L569/L592），VO 透传 has_tracker_error；批量版每次列表转换经共享 loader 加载一次关键词池（L689）。
  - `api/endpoints/duplicate_torrents.py`：同样覆写 + status=error 筛选口径对齐（`OR has_tracker_error`，与 getList/advanced_search 一致——行为变化：duplicates 页筛 error 会多出 tracker 异常种子）。
- 前端：
  - `api/torrents.ts`：Torrent 接口补 `hasTrackerError`/`has_tracker_error`（camel+snake 双字段既有风格）。
  - `utils/torrentBatch.ts`：新增共享 helper `hasTrackerError`（L482）/ `showTrackerErrorTag`（L492，status='error' 不重复打标）/ `getTorrentErrorReason`（L502，errorReason → tracker 消息聚合 → 兜底提示回退链）；两视图逐字节相同的旧 `getTorrentErrorReason` 副本改为薄包装委托。
  - `index.vue` / `TraditionalView.vue`：状态列状态徽标后叠加红色"Tracker异常"小标签（`:title` 显示错误原因）；名称列状态图标/传统视图状态圆点 title 追加"（Tracker异常）"；布局——index 状态列 th 90→130px，TraditionalView `.col-status` 90→145px + 表 min-width 1380→1435px（fixed 布局防裁剪）；样式 `.tracker-error-tag` 分别入 torrent-theme.scss / traditional-view-theme.scss（`var(--color-error)` 系列）。
  - `components/TrackerOperationDialog.vue`：修复既有 bug——announce 状态判断原与 `'True'` 字面量比较，中文状态文本下恒显"异常"，改用共享 `isTrackerAnnounceSuccess`。
  - TrackerDetailCard 零改动即受益（后端覆写"工作失败"→ 前端既有映射自动红 ✗）；`error-reason` prop 同源回退链使 tracker 异常种子详情卡红色告警新增出现（正向行为变化）。

### 测试

- 后端新增 `tests/api/test_tracker_error_display_alignment.py` 24 用例六组（loader 三池过滤/禁用排除；getList 覆写+透传/忽略池保持/成功保持/空池透传解耦/qb+tr 中性码不覆写/scrape 独立/行级互不影响；duplicates error 筛选三态+scrape 覆写；**判定任务 _load_keywords 委托链路+表缺失降级空池**；**判定↔展示一致性契约 8 参数矩阵（展示覆写口径 ⊆ has_tracker_error 判定口径，任何一侧单独改匹配语义即红）**；**advanced_search 同源透传+覆写**）+ `tests/core/test_tracker_status_policy.py` 扩 policy 纯函数用例；5 个既有 fixture 补 `TrackerKeywordConfig.__table__`（test_torrent_list_api / test_duplicate_torrents_api / test_same_content_inspection_api / test_advanced_search_regression / test_advanced_search_batching）；advanced_search_batching 查询计数 6→7（关键词池每请求一次，注释说明）。
- 后端全量 pytest **3884 passed / 7 skipped / 1 failed**——失败项 `test_db_governance_extended::test_upgrade_skips_when_table_and_indexes_exist` 经 **git stash 干净树复现**，为存量问题（auxiliary_seed_count 迁移重复加列，与本次无关）。black/flake8 改动文件全过；mypy 归一化 diff 精确净增 +2，均为 torrent_helpers 两个 VO 构造调用中约 60 个既有字段完全同类的 Column[bool] 旧模型误报。
- 前端全量 57 suites / **891 passed**（torrent-batch +5 helper 用例含 error 状态 tooltip 边界、torrent-error-reason-ui 契约改指向共享 helper 并扩 5 断言组、tracker-detail-card +1 覆写显示用例、**两视图组件级 Tracker异常 标签渲染各 +1**、**新增 tracker-operation-dialog-contract 契约 spec 防回归 'True' 字面量**）；npm run lint 无错误；npm run build 通过；./init.sh 通过。

### 明确不做（及理由）

- 不改 5 处同步落库位点（`last_announce_succeeded` 保留 Transmission 原始归一码，数据保真；展示层覆写不落库、关键词池更新即时生效无滞后）。
- 不用 `judgment_engine.judge_status` 做展示判定（其语义与判定任务相反：子串匹配、ignored=失败——用了会制造"显示失败但 flag=0"的反向新矛盾）。
- 不统一 `tracker_status_sync.py` 关键词加载（AsyncSession 且含 candidate 池，属关键词看板特性语义）。
- 无 DB 迁移、无 error_reason 回填。

### 遗留

- 关键词池编辑后 VO 覆写即时生效，而 has_tracker_error 要等判定任务（约 30 分钟）重算——该滞后窗口为既有语义，方向一致不放大矛盾。
- Git 提交待用户指示。

## 2026-08-18（第四批） - 令牌机制对抗审计修复（10 项：升级500/业务401误踢/跨标签级联/审计下载/清理任务/SECRET_KEY持久化）

### 流程

评估"过期强制退出+提醒/操作实时续期/友好体验"→ 主链路确认成立（三层过期感知/401静默续期重放/三态分流/原子轮换经受双线程实证）→ 两轮对抗审计子代理产出缺口清单 → 修复计划经独立审查子代理对抗审查（裁定"不可按原样执行"：F3 task_profiles 登记是机制误解、F4 护栏须条件化、F7 持久500首载卡死需逃生）→ 按 v2 修订版实施。

### 实施内容（后端 9 文件 + 前端 6 文件）

- 后端：database.py init_config_file 缺失才补 login_status_secret/jwt_secret_key（升级500炸弹+重启杀会话）；config.py _default_secret_key 回退链 env→YAML jwt_secret_key→随机 + _default_config_dir 共享路径解析 + 生产护栏条件化放宽；login.py 改 utils.get_login_secret()（消除直取 KeyError 面）；cuser.py 业务401改码8处（2FA输入错误400、/info兜底500，保留2处真token缺陷401自愈）；auth/token_cleanup.py + refresh_token_cleanup_task.py + 种子（每日04:30保留30天，init_db增量块存量库生效，无Alembic迁移）；auth/utils.py 缓存条件 total_seconds；config.yaml.example jwt_secret_key 仅注释占位。
- 前端：user.ts ExpireSession 不再删共享 access cookie（级联根修，主动登出传播不破坏）+ GetUserInfo 5xx 原样上抛；permission.ts isTransientError 扩5xx + 连续3次瞬时中止逃生回落登出（防持久故障首载卡死/login不可达）+ afterEach 清零；request.ts 网络错误 toast 3秒同文案节流；audit-logs.ts/audit.vue 下载改 axios blob（修前缀/凭证/拦截器三重损坏）；FileManagement.vue el-upload 401 → trySilentRefresh 续期引导。

### 测试

- 后端新增 test_init_config_file（补齐不轮换+端到端+登录签发-校验往返一致）/ test_cuser_business_codes（7处400+兜底500+保留的2处token缺陷401防回退）/ test_token_cleanup（只删超期）/ test_refresh_token_cleanup_task（种子装配防漂移：条目存在+executor字符串动态可导入+保持轻量）/ test_security_config_defaults 扩9用例（回退链6+护栏3）；全量 3826 passed/7 skipped；black/flake8 过、mypy 零新增（存量61为CommonResponse基线）。
- 前端 store-user（ExpireSession 断言反转+5xx上抛）/ permission-guard（5xx中止+逃生回落+计数导航成功清零）/ request-auth（toast节流窗口+redirectToLogin不删共享access cookie）/ session（F6级联防护锚点：被登出标签cookie保留时恢复内存而非误判登出）/ api-contracts（下载blob契约）调整与新增；全量 872 passed/55套件；eslint 过。
- ./init.sh 通过。

### 部署注意

首启过渡（已有 config.yaml 升级后第一次启动 JWT 密钥仍进程随机，再重启一次稳定）；示例文件勿照抄 jwt_secret_key；定时任务种子启动自动补建。详见 PLANS/token-audit-fixes.md。

### 明确本次不修

compose DEV 默认 true；/auth/refresh 无限流；is_admin 硬编码；cookie 非 HttpOnly；审计导出 CWD 相对路径。

### 遗留

Git 提交待用户指示（建议按端拆 fix(backend)/fix(frontend)/docs）。

## 2026-08-18（第三批） - 跨标签令牌续期竞态修复：三态续期 + ExpireSession + 后端原子轮换

### 排查与定性（两轮排查 + 双子代理独立复核/审查）

- 用户报告：令牌过期后无自动续期，操作中突然请求失败。排查确认单标签 401→续期→重放链路完整（8-17 修复后），真正的根因是**多标签竞态**：
  - 后端 `/auth/refresh` 使用即轮换（旧记录置 revoked_at + 签发新记录）；多标签共享同一 refresh cookie、单飞仅限单标签 JS 上下文（模块级变量），无跨标签协调；
  - 任何刷新失败（含竞态败者、网络抖动）都走 `redirectToLogin → ResetToken` 清空**共享** refresh cookie → 一次竞态杀死全浏览器续期能力，此后每个 access 周期（60 分钟）强制登出一次；
  - 次要根因：改密后端撤销全部 refresh token（cuser.py）但前端不清 cookie → "access 活 refresh 死"窗口。
- 复核修正两处初始误判：FileManagement el-upload 是 auto-upload=false 死路径（实际上传走封装请求，不绕过拦截器）；"并发必有一败"精确化为"串行时序必败、极端并发可双成功"。
- 计划独立审查抓出 2 个必改缺陷并采纳：① rejected 路径若清共享 refresh cookie，"败者先读、胜者后写"残余竞态仍可杀全局会话（改为保留）；② 守卫 `next(false)` 后 afterEach 不触发，NProgress 进度条悬挂（必须手动 done）。

### 实施内容（前端 5 文件 + 后端 1 文件）

- `frontend/src/utils/token-refresh.ts`：重写为三态结果 `RefreshOutcome`（renewed/rejected/transient）+ `RefreshDependencies.isDefiniteFailure`（仅后端明确 401 判死）；definite 失败后**重读 cookie** 追他标签轮换新值有限重试（上限 3 次防活锁）；无 refresh token 显式归 rejected（防"不清不跳"僵死）；网络类失败直接 transient 不重试。
- `frontend/src/utils/request.ts`：`refreshDeps.isDefiniteFailure`（ApiError code '401'）；`trySilentRefresh` 返回三态；`handleUnauthorized` 三分支——renewed 重放 / rejected 登出 / transient 不清 token 不跳转、原请求以刷新的网络错误拒绝待自愈；`redirectToLogin` 改用 ExpireSession。
- `frontend/src/store/modules/user.ts`：新增 `ExpireSession` Action（被动登出保留 refresh cookie——死 token 残留无害，重登录时 Login 覆盖）；`ResetToken` 保留主动登出全清语义；GetUserInfo 网络错误（ApiError code '0'）原样上抛供守卫分流。
- `frontend/src/permission.ts`：守卫过期检查三态分流（renewed 放行 / rejected ExpireSession 登出 / transient——roles 已有放行自愈、roles 空 `abortNavigation` 中止导航）；新增 `isTransientNetworkError` + `abortNavigation`（next(false) + Message + 手动 NProgress.done 防悬挂）；GetUserInfo 失败分流——网络错误中止导航保留会话、其余 ExpireSession 登出（原 ResetToken 会清掉 redirectToLogin 刚保留的 refresh cookie，同因改 ExpireSession）。
- `frontend/src/views/settings/index.vue`：改密成功 → ResetToken（主动登出全清，后端已撤销全部 refresh token）+ push('/login') 重登；删除 forceChange query 清理段（整页跳转后无意义）。
- `backend/app/api/endpoints/login.py`：`/auth/refresh` 改条件 UPDATE 原子轮换（`revoked_at IS NULL AND expires_at > now` 才置撤销，rowcount=0 即 401；对齐 cuser.logout 先例），消除并发同值刷新"读-改-写"双成功窗口；record 补空值防御；`request.client` 按 ASGI 规范补 None 防护（mypy 新增错误归零）。

### 明确不做（及理由）

- BroadcastChannel/跨标签锁：cookie 最新值重试 + 保留 cookie 已把竞态后果降为"单标签被踢"，无需锁；
- 服务端 refresh 复用宽限：弱化轮换安全；
- access token 有效期调整（维持 60 分钟）：修复后过期频率无感，调长使登出/改密后旧令牌暴露窗口线性增长。

### 回归加固（应用户要求补测，+5 前端用例 +1 后端用例）

- `store-user.spec.ts` +4：ExpireSession 契约两用例（清 access/userId/roles/mustChangePassword 但 **removeRefreshToken 不被调用**——与 ResetToken 的本质区别直接锚定；W9 标志清除）+ GetUserInfo 上抛契约两用例（网络 ApiError code '0' **原样上抛同一实例**供守卫分流；认证 401 仍包装普通提示防伪装）。
- `request-auth.spec.ts` +1：**transient 自愈闭环**——第一次 401 续期网络失败原请求被拒但会话保留，第二个请求 401 续期成功重放携带新 Bearer（锁住"单飞复位、瞬时失败不卡死续期能力"的设计承诺）。
- `permission-guard.spec.ts`：transient 中止导航用例加 `jest.spyOn(NProgress, 'done')` 断言 ≥1 次——next(false) 后 afterEach 不触发，手动 done 是唯一收尾，缺失即进度条悬挂（审查必改项的回归锚点）。
- `session.spec.ts`：他标签登出触发的统一跳转用例补断言 removeRefreshToken 未被调用（ExpireSession 语义一致性）。
- 后端 `test_auth_refresh.py` +1：`test_rotated_old_token_rejected_without_issuing_new_record`——已轮换旧 token 再刷 401 且**不签发新记录不下发 data**（并发败者的确定性投影，双成功防护）。

### 验证

- 前端全量 55 套件 **866** 用例通过（token-refresh 8、request-auth 14、permission-guard 8、settings-change-password 4、store-user 13、session 12）；`npm run lint`（contract:check + eslint + lint-vuex-action）与 `npm run typecheck` 通过。
- 后端 `pytest tests/api/test_auth_refresh.py`（8 用例：+1 条件更新语义 +1 旧 token 复用投影）+ `test_login_throttle_and_change_password.py`（12）全绿；black/flake8 通过；mypy stash 基线对比 13→13（新增 0）。
- 测试技巧沉淀：api 函数 mock 边界在拦截器**之后**——后端明确拒绝应以拦截器归一化的 ApiError(401) 拒绝形态提供，resolve 401 信封会走"缺 access_token"契约错误分支；beforeEach 先 ResetToken 再 clearAllMocks（防复位期间 cookie mock 调用污染"未被调用"断言）；mockResolvedValueOnce 队列跨用例残留需显式 mockReset。

## 2026-08-18 - 辅种异常排查语义修订：状态/Tracker 改为组内显示筛选（v1.0.6.40）

### 排查背景（生产问题：老男孩查询无结果）

- 用户查询 `same_content_only=true&name_like=老男孩&status=error` 返回 `total=0`（200 成功）。用生产副本库（E:\Users\huangzj\Desktop\app.db，schema 已在 head ab68fe061d5b）+ 真实 `get_torrent_infos` 复现确认。
- 数据事实：老男孩 20 条同名同大小（9033579165）不同 hash，当前仅 1 条 `status='error'`（hash cfcb51db）。旧口径"普通筛选先参与候选判定"使 status=error 过滤后组内只剩 1 hash，`HAVING COUNT(DISTINCT hash)>=2` 不成立 → 整组被丢弃 → 0 条。
- 语义歧义定性（用户确认）：旧口径回答"错误种里哪些构成同内容组"，功能目的是"同内容组里哪几条出错了"。

### 实施内容（用户选定口径：status + tracker 均为显示筛选）

- `torrent_helpers.py`：tracker/tracker_domain/status 三块筛选收进 `_apply_row_display_filters` 闭包（逻辑逐字保留）；普通列表模式在原位置立即应用（行为不变），`same_content_only` 模式延后到分组 join 之后应用——分组候选集只含关键字/下载器/路径/大小/时间/标签/分类/活动种子。
- 新增 2 组 API 用例：status 显示级过滤（单 error 行组不塌、seeding、多选 or）复刻生产场景；tracker_like/tracker_domain 显示级过滤。既有 9 用例无需修改（downloader/category 参与判定的锁定在新口径下仍成立）。
- `docs/api/same-content-inspection.md`：筛选两类口径说明重写。
- feature_list.json 新增 v1.0.6.40 任务及 evidence。

### 验证

- 同内容专用套件 11 passed；普通列表回归 test_torrent_list_api.py 35 passed；flake8/black/py_compile 通过；mypy 58 条与改动前逐条一致（零新增）。
- 生产副本库只读实测：同内容+老男孩+error **0 → 1**（命中 cfcb51db 错误行）；同内容+老男孩仍 20；普通+老男孩+error 仍 1；同内容全局 17748。

### 附带发现（未处理，备查）

- 本仓库存在两份 app.db：`backend/config/app.db`（开发库 22277 种，落后 10 迁移缺 error_reason）与 `data/backend/config/app.db`（docker-compose 挂载部署库，**全空**且 schema 落后 20+ 迁移）。当前代码直连开发库会因 `no such column: error_reason` 全量 500，需先 `alembic upgrade head`。
- `has_tracker_error` 未暴露到 TorrentInfoVO/前端，列表页无法识别"做种中但 tracker 全挂"的种子（本次生产数据中该标志由定时任务动态重算，8/9 快照 2 条 → 8/18 仅 1 条 error）。

## 2026-08-17（第三批） - 问题 A/B 修复：active-torrents 206 根治与 cron 会话收敛（三提交）

### 诊断结论（问题定性，前置三轮调研 + 双子代理独立审查）

- **问题 A**（active-torrents 206「部分下载器速度获取失败，活动快照尚未就绪」）：complete=all() 一票否决。根因①僵尸下载器永久滞留 store 缓存——fail_time 剔除机制是死代码（periodic_check 唯一调用者已注释，fail_time 运行期恒 0），速度接口不读 is_online，每秒轮询对死下载器发起调用必然失败；根因②种子同步窗口（0/15/30/45 分）per-downloader 容量挤占——3s 总预算含 semaphore 排队，超时后底层线程持槽最长 30s。
- **问题 B**（cron 收尾 freshness 落库 greenlet_spawn 错误）：疑因 `_execute_task` 单个 AsyncSession 跨越任务体执行期（重型任务数分钟）与任务体内部 DB 写并发交错；静态证据不足（expire_on_commit=False），定位为卫生性重构+隔离变量，验收依赖 B-1 堆栈。
- **问题 C**（401 连续无效 Token）：已由前一批 3739498 前端修复解决（续期 TypeError/自动登出/重登录生效），本批不涉及。
- 审查关键修正（评审 C-1）：原设想 last_update 距今判离线时长不可行——状态轮询对离线下载器也刷新 last_update（端口不通也算更新成功），必须用新字段 offline_since 表达"首次离线时间"。

### 提交 1（ce5c24c）：A-1+A-3 速度接口

- `_is_freshly_offline`（is_online=False 且 last_update 在 `SPEED_OFFLINE_FRESH_WINDOW`（默认 60s，可配）内才跳过；缺失/过旧保守放行）+ `_process_downloader_speeds` 跳过新鲜离线者（complete=True 空结果，不发起远程调用）+ `_supplement_disappeared` dl_map 同步过滤。
- `_DownloaderSpeedResult.reason` / `_ActiveSpeedGatherResult.failed`（均带默认值，位置参数构造兼容）；206 msg 附加失败明细（>5 截断）+ 结构化日志；failed 仅收 complete=False 者。
- `.env.example`：IO_CONCURRENCY 建议 4 + SPEED_API_TIMEOUT/SPEED_OFFLINE_FRESH_WINDOW 说明。
- +13 用例（跳过三分支/混合归因/边界/补查过滤），70 tests 绿。

### 提交 2（7598184）：A-2 缓存自愈闭环

- `DownloaderCheckVO.offline_since`（首次离线时间戳）；`_set_online_status` 统一维护四个置位点（记录/不覆盖/恢复清空）。
- `CachedDownloaderSyncTask` 步骤 5.5：offline_since 距今 >300s（≈30 次探测失败）剔除；缺失不删防误删；恢复在线经既有 `_check_and_add_new_downloader` 下轮（cron 每 5 分钟）重新入缓存。startup_event 死注释清理。
- 行为变化：长期离线者从仪表盘/getStatusAll 消失（非显示离线）。新建 test_downloader_cache_sync.py（+10 用例）。

### 提交 3（d036d0b）：B-1+B-2+B-3 cron 收敛

- B-1：cron_crud_async 7 处 + cron_executor 2 处错误日志补 exc_info=True。
- B-2：`_execute_task` 三段式（读会话即关 → 任务体无会话 → 收尾短会话三写 duration→log→freshness）；CRUD 签名与 datetime 时间源不变。
- 顺手修存量缺陷：读取失败早退绕过 status=2 复位（任务页永久「运行中」）——移入外层 finally。
- B-3：同步 execute 分支经 `asyncio.to_thread`（封死未来同步任务阻塞事件循环路径）；删全仓无引用的 `execute_with_app`。
- +5 用例（任务体期间活跃会话=0/三写顺序/早退复位/严重异常复位/同步 execute 线程断言）。

### 质量与回归

- 相关批次测试全绿（70 + 10 + 375），black/flake8 全部通过，mypy 每批次与 HEAD 基线对比零新增错误。
- feature_list.json 未动（缺陷修复非 feature 任务）。
- 遗留观察项：greenlet 错误若部署后仍复现，依据 B-1 新增堆栈定向排查（候选：apscheduler 线程池跑同步 `_sync_speed_schedule`、aiosqlite 连接跨 greenlet）。

## 2026-08-17（第二批） - 双密钥会话过期登出与重登录生效修复

### 症状与根因（全部源码实证）

- 症状 1「密钥过期后没有自动退出」：`request.ts` redirectToLogin 用 history 风格 URL 但路由是 hash 模式（pathname 恒为 '/'，redirect 参数退化 + 依赖服务器 SPA 回退）；防抖标志 `isRedirectingToLogin` 置位后永不复位，跳转受挫（bfcache 后退/无回退部署 404）后所有 401 被永久静默吞掉；登出纯被动（只等 API 401，无 JWT exp 主动检查）；`LogOut` 空 token 直接 throw 导致 Navbar 登出也失效。
- 症状 2「重新登录后需刷新才生效」：`FileManagement.vue` uploadHeaders computed 读 cookie（非响应式、Vue2 求值一次永久缓存）且 el-upload 自有 XHR 绕过 axios 拦截器；跨标签页 Vuex token 快照无同步机制（cookie 变化不触发 storage 事件）；Login 缺 refresh_token 时保留已撤销旧 cookie → 续期永远失败。

### 修复（8 文件，全前端）

- 新增 `utils/session.ts`：`getTokenExp`/`isTokenExpired`（JWT exp 纯解析，畸形不误杀）、`buildLoginRedirectTarget`（hash 感知登录 URL）、`syncTokenFromCookie`（cookie→内存快照回同步三分支）、`initSessionWatch`（visibilitychange/focus 监听，他标签登出→统一跳登录；main.ts 接线）。
- `request.ts`：redirectToLogin 改 `/#/login?redirect=<hash内路由>`（不再依赖服务器回退）+ 3 秒防抖窗口自动复位 + 过期 toast；导出 `redirectToLogin` 与 `trySilentRefresh`；handleUnauthorized 改用后者。
- `permission.ts`：守卫 token 分支前置 `isTokenExpired` → `trySilentRefresh`，失败 `ResetToken()` + 跳登录（登录页本身放行避免 redirect 自指循环）。
- `store/modules/user.ts`：LogOut 容忍空 token（跳过后端调用仍完整本地清理 + 补清 mustChangePassword）；Login 缺 refresh_token 时 `removeRefreshToken()`。
- `FileManagement.vue`：uploadHeaders 改响应式 `UserModule.token` + `Authorization: Bearer`（后端 dependencies.py 已兼容，认证契约收敛）。
- 测试：新增 `tests/unit/session.spec.ts`（10 用例）；`store-user.spec.ts` 改写缺 refresh 用例 + 新增 LogOut 4 用例。顺手修复 keyword 三份 spec 的 5 个既有 lint warning（lint 门禁 max-warnings=0 此前已红）。

### 质量与回归

- 前端全量 jest：**51 suites / 817 tests 全绿**；`npm run lint` 0 error 0 warning；`npm run build` 成功（dist 已重建为最新，覆盖 8-16 dist 落后最后一次提交 9d2258d 的问题）；根 `./init.sh`（ci 模式）通过。
- roadmap 同步：frontend/utils-types（+session/token-refresh 条目、request.ts L1-229 实测行号、cookies 双令牌职责、SUCCESS_CODES 补 202）、frontend/entry（main/permission 职责与行号）、frontend/store（user.ts action 清单）、perspectives/test-coverage（前端 spec 清单漂移对齐 33→40 + 登记新增）、根 README 元信息。
- feature_list.json 未动：属缺陷修复非 feature 任务。
- 部署提醒：本机存在 6 周前旧镜像，部署前务必用本次重建的 dist 重打镜像。

### 回归加固（同日第三批：+19 用例，并抓出一个生产级 bug）

- **抓出生产 bug**：新增拦截器集成测试首跑即红——`UserModule.getRefreshTokenValue()` 是 user 模块唯一未装饰普通方法，vuex-module-decorators 的 `getModule` 只代理 @Action/@Mutation/getter，运行时该方法不存在 → 8-16 上线的 401 静默续期在生产从未生效（每次 401 在读取 refresh token 处抛 TypeError，续期/重放/登出全链中断，正是"过期不登出"的最直接根因）。修复：request.ts refreshDeps 直接读 cookie（`getRefreshToken() || ''`），删除死方法。
- 新增 `tests/unit/request-auth.spec.ts`（11 用例）：redirectToLogin hash 跳转与 redirect 参数、3 秒防抖窗口自愈（假时钟）、trySilentRefresh 三态（无 token/成功轮换持久化/失败）、axios adapter 注入的拦截器集成（HTTP 401 error 分支与 HTTP 200 业务码 401 success 分支的续期重放携带新 Bearer、重放仍 401 防循环登出、无 refresh 直接登出、`/auth/refresh` 豁免不递归）。
- 新增 `tests/unit/permission-guard.spec.ts`（5 用例）：真实 router 导航验证守卫五分支（过期+续期成功放行、过期+失败登出保 redirect、目标即 /login 无自指循环、未过期不触发续期、GetUserInfo 失败兜底）。测试技巧：连续 push 同路由会触发 NavigationDuplicated 被吞导致守卫不跑（假绿），beforeEach 统一回 /login + 各用例目标互异 + `pushQuietly` 吞守卫重定向拒绝。
- `session.spec.ts` +2 用例（initSessionWatch 可见/聚焦触发同步与登出，共 12）；`file-management-contract.spec.ts` +1 契约（上传头响应式 UserModule.token + Bearer、禁 x-access-token/getToken 回归锚点）。
- 全量 53 suites / 836 tests 全绿（原 817）；lint 0 warning；build 通过（含两处测试 envelope 的 TS data-null 断言修正）。roadmap test-coverage 同步（43 spec）。

## 2026-08-17 - API 鉴权安全审计 + 附加发现修复 #1/#2

### 审计结论（217 条路由全覆盖，运行时内省 + 源码核对）

- 206/217 路由有鉴权（`require_authenticated_user` 主流 / 旧 `get_current_user` 5 模块）；11 条无鉴权均为合理豁免（login/refresh/health×4/docs(生产已关闭)/SPA fallback）。
- 无业务接口缺失鉴权；3 个子代理深度评估了 4 项附加发现的价值（详见会话记录）。

### 修复 #1：WebSocket 死代码清理（价值评级：高）

- git 考古确认 `websocket_main.py` 是 2026-03-08 提交 `4cf9898`（删除 WebSocket 功能）漏删的遗留物，引用不存在的 `factory.wsapp`，运行必然 ImportError。
- 删除：`backend/app/websocket_main.py`；`config.py` 的 `WS_V1_STR`/`WS_PORT` 两个零引用死配置；`frontend/nginx.conf` 的 `/ws/` 转发块与 `/api/` 块内失效的 Upgrade 头（顺带消除 `Connection ""` 与 `Connection "upgrade"` 重复指令冲突）；`deploy/nginx-tls.conf.example` 的 `/ws/` 块与头部注释。
- roadmap 同步（行号实测）：`docs/roadmap/backend/app-root.md`（文件数 10→9、删 WebSocket 两处条目）；`docs/roadmap/deploy/README.md`（删 WebSocket 3 处，nginx 行号漂移修正 L90→L104 等，补登录接口 L93 条目）。backend/docs 三份历史审计报告按惯例保留原文。

### 修复 #2：鉴权门禁盲区（价值评级：中）

- 盲区实证：`test_architecture_constraints` 比例断言对"完全不带鉴权的新端点"不进分子不进分母；`lint_btdeck.py` 统计正则只认旧 `get_current_user`（主流早已是 `require_authenticated_user`，指标失真）；BTD201 只禁手动解析；逐端点 401 测试是清单非兜底。
- 新增 `tests/api/test_auth_route_coverage.py`：遍历运行时 `app.routes`，非白名单路由的依赖树必须含鉴权函数；白名单双向校验（公开端点必须存在且不得误挂鉴权）；≥100 条受保护路由下限防"路由注册整体失败静默通过"（历史循环 import bug）。变异验证：注入无鉴权路由即报红。
- 统计口径修复：`lint_btdeck.py` 正则同时认两种鉴权依赖，`AuthStats.depends_get_current_user` → `depends_auth_dependency`（lint 输出、`test_architecture_constraints.py`、`diagnose.py` 三处同步）。

### 质量与回归

- 全量 pytest：**3733 passed / 7 skipped / 0 failed**；lint_btdeck.py exit 0（认证统计：Depends=193、占比 100%）。
- flake8 通过；black：改动段落干净（lint_btdeck/diagnose 两脚本存在**既有**格式漂移，HEAD 版本同样不过，非本次引入，未顺手重排）；mypy：config.py 全量运行 0 错误（单文件模式 2 个既有 BaseSettings no-redef）。
- feature_list.json 未动：本次为安全维护修复，非 feature 任务，进度记于本文件。

### 遗留（已评估未实施，待用户决定）

- 附加发现 #3：19 端点迁移 `require_authenticated_user` 并删除旧依赖（成本在 8 个测试文件适配，约 1 天）。
- 附加发现 #4：`.env.example` 的 `ACCESS_TOKEN_EXPIRE_MINUTES=600`（10 小时）建议下调（一行配置）。

## 2026-08-16（第二批） - 进度精度/转移落库/审计 IP 三项修复

### 排查结论（四个问题，问题 4 经拓扑核实为正常）

1. **进度 99.556946664657%**：`_normalize_progress_value` 只夹取不舍入，qB/TR 的 0-1 小数 ×100 原样落库；实测库中 3 条脏值。
2. **转移后无目标记录**：`transfer_seed` 全程不写 `torrent_info`，要等 10 分钟同步任务才出现。
3. **转移/orphan_cleanup/orphan_hardlink_copy_delete 审计无 IP**：调用点未传 ip_address；cleanup/purge 为后台任务链（无 request 上下文）。
4. **IP 全是 192.168.5.60**：docker nginx 反代 + XFF 提取链路正常，.60 为访问端电脑（宿主机为 .51）；已向用户说明（另发现 `extract_audit_info_from_request` 信任 XFF 首值可伪造，遗留待用户决定）。

### 实现（方案经 2 个独立审查代理复核，合入 7 项修订）

- **问题 1**：`torrents_async.py::_normalize_progress_value` 末尾 `round(value_float, 2)`（8 处同步写路径汇聚点）。存量脏值自愈：0.5 阈值保留旧值→保留的是舍入值 + `has_torrent_info_changes` 精确比较判变化 + 全量同步 update 无条件写回；无需数据迁移。
- **问题 2**：`seed_transfer_service.py` 新增 `_upsert_target_torrent_row`（验证成功后按 (downloader_id, hash, dr=0) upsert 目标行；字段对齐 info-only 同步 insert dict，downloader_name=当前昵称保证 bulk_update 主键命中；显式 commit；IntegrityError 竞态转 update；异常吞掉仅 warning）+ `_mark_source_row_transferred`（delete_source 成功时源行 dr=1，与 `_mark_qb_removed_torrents` 同构，不进回收站）+ source==target 服务层兜底防御。
- **问题 3**：
  - 转移：两端点加 `request: Request`，`_log_transfer_audit` 传 ip_address/user_agent（torrent_audit_log 已有列）。
  - 孤儿（用户确认全部补齐）：同步端点 `/hardlink-copies/delete`、`/restore`、`/ignore` 加 request 直接透传；后台任务链 `/cleanup`、`/purge` 经 `orphan_purge_job` 新增 `ip_address` 列（迁移 `ab68fe061d5b`，inspect 守卫 add_column + batch downgrade，串接 ff42d3402df5）持久化，execute_job 读 job 会话内取出传入服务层；5 个服务函数（delete_hardlink_copies/cleanup_orphans/set_ignored/restore_quarantined/purge_quarantine_now）加 ip_address 形参 + 4 处租约递归透传 + 5 处审计调用点传值；4 个提交入口（submit_*/create_*）全加参。
- **测试**：新增 `test_progress_rounding.py`（9 项）；`test_seed_transfer_service_fixes.py` 增 TestTargetRowUpsert 5 项；batch fixes 增审计 IP 断言；`test_orphan_purge_job_service.py` 增 IP 落库+透传 2 项；修复 5 处受影响断言（execute_job/cleanup/purge/ignore 精确 kwargs + w2_3d mock 队列扩展）；`test_db_migration.py`/`test_db_rollback_scenarios.py`/`test_orphan_migration_production_shape.py` 三处 head 版本常量同步为 ab68fe061d5b；`docs/constraints/database-migration.md` HEAD 标注修正（原标 c8d9e0f1a2b3 已过期 5 个版本）。
- **质量**：black/flake8 干净；mypy 新增错误种类 0（16 个新报错全为文件既有 13 类存量模式，ORM 属性赋值等）。

### 回归加固（同日第三批：+20 后端测试）

- **同步流进度舍入**（新文件 `test_progress_rounding_sync.py`，5 项）：qB/TR info-only 真实同步函数 + 伪客户端，锁定 insert 行 progress==99.56、存量脏值 99.556946664657 经"0.5 阈值保留旧值"分支写 99.56（自愈同步侧入口）、修正后稳定行不被重写。
- **转移服务**（`test_seed_transfer_service_fixes.py` +6 项，共 16）：IntegrityError 竞态转 update（rollback→重查→更新→二次 commit）；duplicate/验证超时/添加失败三条早退路径不预插目标行；delete_source 删除失败（partial）源行保持 dr=0 且目标行已存在；`_mark_source_row_transferred` 源行缺失安全 no-op。
- **审计 IP 真实链路**（+8 项）：单转移端点不 patch extract、TestClient 携带 `X-Forwarded-For` 头验证审计行记录首值 203.0.113.9（与 nginx 生产行为一致）；孤儿 5 端点（hardlink-delete/restore/ignore/cleanup/purge）同样走真实头提取并断言服务/提交 kwargs 收到 IP；无代理头回退 `request.client.host`；`execute_job` purge 路径 IP 透传；服务层 `cleanup_orphans` 的 ORPHAN_CLEANUP 审计直接收到 ip_address。
- 合计：本次三项修复的回归保护从 21 项增至 41 项。

### 转移操作日志补种子/下载器名称（同日第四批）

- 需求：转移写入 torrent_audit_log 的操作日志缺种子名称与下载器名称（列表页空列、无法按种子名搜索）。
- 实现：`_log_transfer_audit` 新增 torrent_name/source_downloader_name 参数并放入 operation_detail（AuditLogService 自动提取到 torrent_name/downloader_name 冗余列）；下载器口径统一取来源下载器——downloader_name=源 nickname、downloader_id 同步从目标改为来源（保持 id/name 同源，按下载器筛选才一致）；双向 ID 仍保留在 detail JSON。早退失败路径（源下载器不存在等）名称为空串。
- 测试：TestBatchTransferAudit 三项审计用例补冗余列断言（torrent_name==种子、downloader_name==源、downloader_id==来源 ID、detail JSON 双向 ID 完整）；定向 51 passed。

### 遗留

- `extract_audit_info_from_request` 取 XFF 首值可被客户端伪造（nginx 追加真实 IP 在末尾），待用户决定是否收紧（取尾值/X-Real-IP/直接 client.host）。
- 预插行 status/size/ratio/torrent_file 与目标下载器真实状态短暂不一致（torrent_file 跨类型转移指向源路径），下次同步覆盖，属预期。


## 2026-08-16 - scan_context 统计缓存（孤儿列表二次优化）

### 需求与根因

- 上一轮优化后接口稳定 1.6s；逐阶段基准（45 万行）定位剩余耗时：remaining_count 136ms + ignored_count 205ms + 过滤 total 135ms（三条全量聚合，占 SQL 57%）+ 列表全排序 ~190ms（30%）+ Docker 环境系数。
- 关键事实：remaining/ignored **与过滤条件无关**，只随三类数据变化（is_deleted / is_ignored / 清理任务 active 集）；部署恒单进程（WORKERS=1）→ 进程内缓存无一致性问题；前端每次翻页整包覆盖 scanContext → 后端必须每次返回正确值，用缓存满足，前端零改动。

### 实现（经双子代理独立审查修订）

- 新建 `app/services/orphan_stats_cache.py`：模块单例，键=display_scan.scan_id，值=(remaining_count, remaining_size, ignored_count)，上限 4 条 FIFO 淘汰；**epoch 代际防回写**（get→set 之间有 await，invalidate 夹中间时旧计算直接丢弃）。
- 读路径：`get_orphan_list` / `get_orphan_list_grouped` 缓存优先；**扁平路径无过滤时 total 复用 remaining_count**（显式白名单判定，`status in (None,"")` 等——"pending,deleted" 等组合不满足、grouped 的 total 是组数绝不复用）。
- 失效点（全清 invalidate()，全部 commit 成功后）：`set_ignored`、`_finalize_quarantine`（is_deleted=True 咽喉，覆盖手动/自动清理与异常路径）、`_finalize_restore`、`submit_cleanup_job`（pending 即扣减）、`finish_job`（终态失败回升，**必需**）、`execute_scan` 两处（扫描开始封死 reconcile 分批失败窗口 + 落库后双保险）、`_recover_interrupted_operations` 防御性（purge 经此入口也会全清，接受）。
- 测试：根 conftest autouse 清缓存 fixture（防模块单例跨用例污染）；`test_orphan_query_state.py:212` 改为走真实 claim→finish_job（原直接改 ORM 字段绕过）；新增缓存单测（含 epoch 竞态）+ 7 个集成用例（命中不再聚合、total 复用、status 组合不复用、忽视/清理提交/终态失效、grouped 不复用 total）。

### 性能结果（45 万行 aiosqlite 真实服务路径）

- 冷请求（miss）：310ms → 热请求（命中）：**128ms**；翻页 9 次全命中单页 126ms；失效后重算 282ms。
- 生产估算：无过滤首屏 1.6s → 约 0.6-0.8s，翻页约 0.3s（Docker 系数 1.5x + 请求层）。

### 验证

- 后端全量 pytest：**3507 passed**（较上轮 +19 新用例）；black/flake8 通过；mypy 新模块零错误。
- `./init.sh` 全栈验证全绿（29 ✓）；前端零改动。
- 已记录 feature_list.json（evidence：冷 310ms/热 128ms/翻页 126ms）。

## 2026-08-16 - 孤儿文件列表 5 秒慢查询优化（hardlink_copy_count 快照列）

### 需求与根因

- 用户报告 `GET /orphan-files/list?page=1&page_size=20&hardlink_copies=located` 耗时 5s。
- 实测（10 万行合成库，真实 `_build_orphan_conditions` 构造 SQL）：根因两块——
  1. SQL 侧：located 过滤编译为关联 EXISTS（候选表 join 结果表、CAST inode），count 与 list 各执行一遍，O(2N) 次两跳索引探测，current 模式 count 单条 836ms、合计 1.1s；
  2. 文件系统侧：`_enrich_items` 对当前页 20 文件串行 `os.stat` 取实时 st_nlink-1（NAS/挂载盘上 2-5s）。
- 用户两项决策：副本数必须**扫描发现文件时同步落库**（消除预扫描覆盖时间差导致"有副本显示没副本、删除后副本永远找不到"）；located 筛选改为**「有副本」count>0 语义**。

### 实现

- **模型/迁移**：`orphan_file.hardlink_copy_count`（INTEGER NULL）快照列；新迁移 `d4e5f6a7b8c9` 加列 + 按 current_detail_id 关联预扫描结果分块回填 + 覆盖索引 `ix_orphan_candidate_current_detail_status(current_detail_id, status)`（current 模式 detail_scope 从全表 SCAN 变覆盖索引）。
- **写入链路**：扫描器 `_walk_scan_root` 从既有 stat_info 取 `st_nlink-1`（零额外 IO，在线/降级共用遍历）；lifecycle 新明细创建落库、已有明细"仅变化字段"刷新（None-guard 防抹掉已知值）；每日预扫描 `_refresh_detail_counts` 把 stat 权威值刷回明细列（恢复每日新鲜度，孤儿全量扫描默认每周才跑）。
- **读取去 stat**：`_enrich_items` 删除串行 stat 链路，副本数经 `to_dict()` 直出（弹窗 POST /hardlink-copies 仍实时复核）。
- **筛选重定义**：`_build_orphan_conditions` EXISTS 替换为 `hardlink_copy_count > 0`；顺带修复预存在缺口——`OrphanSelectionFilters`/`resolve_orphan_selection`/`prefix_match_preview`（前后端）透传 located，避免 located 开关下快捷前缀清理放大清理范围。
- **联动**：`delete_hardlink_copies` 成功后按身份批量写回共享 inode 全部明细；`restore_quarantined` 恢复后补 stat 刷新。
- **前端**：筛选 label「已定位副本」→「有硬链接副本」；副本数列 0 也可点击（弹窗实时复核）；NULL 文案「尚未生成快照」；api 类型与单测同步。

### 性能结果（10 万行 current 模式复测）

- located 过滤 count+list：**1107ms → 88ms（12.6×）**，且低于无过滤基线（117ms）；覆盖索引命中 `USING COVERING INDEX`。
- 20 次串行 stat 归零；端到端 5s → 亚秒级。

### 验证

- 后端全量 pytest：3488 passed；迁移链测试 EXPECTED_HEAD/REV_HEAD 同步 d4e5f6a7b8c9；black/flake8 通过；mypy 存量 146 错误零净增。
- 前端：orphan-files.spec.ts 99 passed（含新语义用例）；全量 jest 套件后台验证中；vue-tsc 存量 3012 错误零净增；eslint 存量 5 warnings 非本次引入。
- 测试覆盖：located 快照列语义套件重写（count>0/0/NULL/共享 inode/全选/前缀）；scanner 采集、lifecycle None-guard、预扫描刷新、delete 兄弟写回、restore 补 stat 新增用例；迁移回填与覆盖索引。

### 取舍（用户已确认）

- 副本数 = 扫描时 st_nlink-1 快照（每日预扫描/每次成功扫描刷新），非实时；「已定位路径」仅在弹窗展示。
- 历史 snapshot 批次未回填行显示「未知」（-），由后续扫描覆盖。
- 声明不做（后续项）：scan_context 每页 4-5 条全量聚合按需计算；grouped GROUP BY 表达式排序优化。

## 2026-08-16 - 修复新种子显示 unknown 与传统模式进度条不可见

### 需求与根因

- 用户报告两个问题：1）传统模式下载数据时进度条不随进度变长；2）列表/传统两模式对新添加种子都显示 "unknown"，应显示"下载中"。
- 根因（两问题同源）：qBittorrent 新添加种子处于 `metaDL`/`forcedMetaDL`/`allocating` 等初始态，后端 `QBITTORRENT_STATUS_MAP`（`torrent_status_mapper.py`）缺失这些键导致原样入库；前端 `normalizeTorrentStatus`（`formatters.ts`）只识别 7 个规范值，其余一律归一 `'unknown'` → 状态列显示 "unknown"。
- 传统模式进度条额外踩中样式缺陷：`.progress-bar-fill`（`traditional-view-theme.scss`）无默认背景色、仅按状态类着色，状态为 unknown 时填充条透明 → 宽度在增长但不可见（列表模式 `.progress-fill` 有默认渐变背景故正常）。同一缺陷族还包括 `pausedDL/pausedUP/checkingDL/checkingUP`（后端有意保留的统计变体）与 `completed`（实时轮询完成时写入）此前均无文案/样式。

### 修复内容

- 后端 `torrent_status_mapper.py`：`QBITTORRENT_STATUS_MAP` 补齐 7 个缺失状态——`metaDL/forcedMetaDL/allocating/forcedDL→downloading`、`forcedUP→seeding`、`missingFiles→error`、`checkingResumeData→checkingDL`；`moving`（迁移瞬时态）有意不映射并注释说明。新映射与 `torrent_stats_cache.get_stats` 的统计桶天然兼容（downloading/seeding 桶可正确归类）。
- 前端 `formatters.ts`：`normalizeTorrentStatus` 由 7 分支 switch 重写为 `TORRENT_STATUS_FOLD_MAP` 折叠表（大小写不敏感），覆盖 qB 全量状态词表（含历史入库的 `pausedDL/pausedUP/checkingDL/checkingUP/stalledDL/forcedUP/uploading` 等变体），兜底已入库历史数据展示；未识别仍归 `'unknown'`。
- 前端 `status-config.ts`：`STATUS_TEXT_MAP`/`STATUS_ICON_MAP` 补 `completed: '已完成'/'circle-check-big'` 与 `unknown: '未知'/'help-circle'`（`STATUS_OPTIONS` 六态筛选选项不变）。
- 样式：`traditional-view-theme.scss` `.progress-bar-fill` 加兜底背景 `var(--color-text-tertiary)` + `&.completed`；状态图标圆点与徽章补 `&.completed`/`&.unknown`；`torrent-theme.scss` 列表徽章补 `&.unknown`。
- 存量数据自愈：下一次种子同步会把 DB 中 `metaDL` 等原值重写为规范状态；同步前前端折叠表兜底展示。

### 验证

- 后端：`tests/core/test_torrent_status_mapper.py` 60 passed（映射表完整性/参数化用例同步更新，seeding 来源计数 4→5）；`tests/api/test_transmission_error_sync.py` 32 passed；mypy/black/flake8 通过。`test_path_mapping_validation.py` 直接用原始 state 字符串不走映射器，不受影响（已核）。
- 前端：`shared-utils.spec.ts`（+14 折叠用例）/`status-config.spec.ts`/`traditional-view-component.spec.ts`/`torrent-list-view-component.spec.ts`/`torrent-error-reason-ui.spec.ts` 共 **111 passed**；改动文件 eslint 零问题；`tsc --noEmit` 通过。
- roadmap 同步：`backend/core/README.md` status-mapper 行（L103→L112/L138→L147 漂移修正 + 变更摘要）、`frontend/utils-types/README.md` formatters 行（L571→L589）与 status-config 行。
- 无 schema 变更，无新迁移；未执行 Git 提交（待用户指令）。

## 2026-08-16 - 副本位置弹窗行级删除硬链接副本

### 需求与实现

- 用户要求：在孤儿文件页面的硬链接副本位置弹窗为每个副本行添加删除按钮，直接在页面删除副本（仅移除该路径链接，源文件与数据保留）。
- 交互安全决策（用户确认）：位于活跃种子目录内的副本**严格拒绝**删除（fail-closed，与项目清理门禁一致）。
- 后端 `delete_hardlink_copies`（`orphan_file_service.py:871`）逐路径 fail-closed 门禁链：维护租约 `orphan_maintenance_scope("hardlink_copy_delete")`（busy → `rejected=true` 整体拒绝）→ 明细 `exclude_in_flight` 加载 → 候选 `status=candidate` 且 `operation_state=stable` → 源文件 stat 身份 + 预扫描结果行存在 → **共享 inode 拒绝集**（源路径 + 同 `(device_id, inode)` 全部候选 canonical_path，防在 A 的弹窗删除孤儿 B 本身）→ 种子目录白名单（`collect_torrent_directory_whitelist` 全量下载器 DB 目录级，`asyncio.to_thread`，加载失败整体拒绝）→ 请求路径与返回前端的 copies **原始字符串**成员判定（防任意路径注入）+ 隔离区/回收站标记（settings 口径）+ 符号链接拒绝 → **tombstone 三段式删除**（rename→身份复核→remove，复核失败回滚；`_remove_hardlink_copy` L840）。
- 成功后 setattr payload 同步结果行（copies_json/found_count/copy_count，保留 truncated/scan_note/scanned_at；写竞态由下一轮预扫描自愈）；审计在主事务 commit 后写（restore 模式，注入 `get_audit_service`）；状态类拒绝一律 HTTP 200 + `failed_list[{copy_path, reason}]`（与 set_ignored/restore 形态一致）。新审计枚举 `orphan_hardlink_copy_delete` 三处登记（成员/display/category）。
- 端点 `POST /orphan-files/hardlink-copies/delete`（`orphan_files.py:341`，`{orphan_id, copy_paths≤50}`，Pydantic 失败 422）。同步执行（与 restore 同级先例，单请求 ≤50 个 unlink）。
- 前端：`deleteHardlinkCopy` API；抽取 `fetchHardlinkLocations(orphanIds, keepResult)`；副本行 danger 文字按钮「删除」（`$set/$delete` 维护行级 deleting 态）；`$confirm` type=error 对齐 `handleQuarantinePurge` 惯例；删除成功后就地更新行副本数（located 筛选开启时改走整页刷新）+ 重查弹窗（keepResult 保留旧数据、列表区局部遮罩）；**seq 快照 + 弹窗可见双重校验**防迟到重查覆盖关闭/重开后的新弹窗数据。

### 决策记录（3 个只读子代理独立审查后修订）

- 审计事务冲突：`get_audit_service` 绑定请求主 session 且 `log_operation` 内部 commit，不能在结果行更新 commit 前调用（会把主事务提前提交）→ 统一 restore 模式（commit 后写）。
- 原计划裸 stat-then-unlink 保护低于项目水准 → tombstone 三段式（与 `_purge_single_candidate` 同级）。
- 发现共享 inode 漏洞：copies_json 含共享身份的全部孤儿源路径，仅排除当前源不够 → 同身份候选反查拒绝集。
- Vue2 动态 key 不响应 → `$set/$delete`；弹窗重开竞态 → seq 快照校验；重查失败不得清空弹窗数据 → keepResult。
- mypy 基线实测 1563（非历史记录的 149），stash 对比零新增；ORM 列赋值改 setattr payload（与 `_write_results` 同惯例）。

### 验证

- 后端：`test_orphan_hardlink_detection.py` 33 passed（新增 TestHardlinkCopyDelete 13 用例：happy/共享 inode/非 stored/种子目录/白名单失败/标记/身份不匹配回滚/源不可访问/状态门禁/无预扫描/批量去重/租约 busy/空请求）；`test_orphan_files_api.py` 44 passed（透传/rejected/422 参数化）；`tests/enums` 283 passed（成员计数 45→46）；`tests/services + tests/api` 全量 **1983 passed, 6 skipped**；`tests/core + tests/tasks + tests/enums` **1075 passed**。
- 质量：black/flake8/ruff/lint_btdeck 通过；mypy 全量 1563=基线 1563（stash 实测对比零新增）。
- 前端：`orphan-files.spec.ts` **99 passed**（新增 7 用例）；全量 **44 suites / 754 passed**；typecheck 通过；三个改动文件 `eslint --max-warnings 0` 零问题。
- roadmap 三层更新（根 README 功能域/元信息 + services README orphan 行 + `orphan_file_service.md` 全量行号实测 3809 行 + api README orphan 行）；顺带修正根 README 端点模块计数漂移（38→37 实测）。feature_list.json 新增 feature `orphan-hardlink-copy-delete`（3 tasks）；`./init.sh`（ci）通过。
- 无 schema 变更，无新迁移；未执行 Git 提交（待用户指令）。

## 2026-08-15 - 已定位副本快捷筛选 + 预扫描范围收紧

### 需求与实现

- 用户要求：孤儿页面快捷操作里增加"快速筛选出已找到副本路径的数据"（此前用户无法得知哪些文件的副本已被定位）；同时核查找副本任务是否排除已忽视数据。
- 核查结论：预扫描 `_stat_window` 原过滤 `status != "resolved"`，**未排除已忽视**（忽视是独立布尔列 `is_ignored`，status 保持 `candidate`），且包含 quarantined/purged 候选——其文件已被移动/删除，是部署日志 `stat_failed=101` 的主要来源。经用户确认收紧为 `status == "candidate" AND is_ignored == False`（取消忽视/隔离恢复经 reconcile 重置回 candidate 自动恢复扫描；游标基于 OrphanFile.id 不受影响）。
- 后端筛选：`_build_orphan_conditions` 新增 `hardlink_copies` 参数，`located` 时追加 EXISTS——候选表最近扫描的 `(device_id, inode)`（inode 字符串列 `CAST(inode AS INTEGER)` join 整数 `inode_id`，与 `orphan_purge_job_service` 同口径）命中结果表且 `found_count > 1`（found_count 含源路径自身，>1 即定位到非源副本，与弹框 copies 剔除源路径口径一致；NULL 身份/未扫描不命中，fail-closed）。线程化到 list/grouped/folder_children 三处；`/list`（grouped+flat 两分支）与 `/folders/children` 新增同名 Query 参数；无效取值忽略（与 status/confidence 宽松口径一致）。
- 前端：快捷操作 dropdown 新增"筛选已定位副本"（`toggleLocatedCopies` 在 `handleQuickAction` 先分支处理，切换 `listQuery.hardlinkCopies` 并回第一页重载，不落入前缀对话框流程；激活时显示勾选图标/取消文案）；筛选区新增"已定位副本" `el-checkbox`（tooltip 注明按每日预扫描结果过滤）；`loadOrphanPage`/`buildCurrentFolderParams` 序列化 `hardlink_copies='located'|undefined`；重置清空。
- 无 schema 变更，无需迁移。

### 决策记录

- 独立子代理审查计划后修正三处：前端 spec 对 `listQuery` 的整对象 `toEqual` 精确断言必须同步（否则必挂）；`handleQuickAction` 需先分支处理新命令；`found_count > 1` 在 budget_exceeded 部分遍历的极端情形存在 fail-closed 方向漏报（无误报），经审查确认接受该折中并在 tooltip/注释注明。
- 扫描范围收紧同时排除 quarantined/purged（用户确认）：省出的 stat 预算留给待清理文件，`stat_failed` 将显著下降。

### 验证

- 后端相关三文件 **92 passed**（`tests/api/test_orphan_files_api.py` 两处精确断言更新 + 3 个透传用例；`test_orphan_ignore_and_filters.py` +4 筛选用例；`test_orphan_hardlink_copy_scan.py` +1 排除用例）。
- EXISTS 语句经 SQLite 方言 compile 实测；black/flake8 通过；mypy 与改动前基线一致（149 存量错误，零新增）。
- 前端 `orphan-files.spec.ts` **88 passed**（新增 5 用例）；lint 无新增问题（keyword 相关 spec 5 个警告为 dev 分支存量，与本次无关）。
- roadmap 实测行号同步；发现并顺带修正第三层 `orphan_file_service.md` 在 4da8115 时已漂移（记录 3161 行，实测 3449 行）。

### 回归加固（第三批，+7 后端 / +4 前端，最终 99 / 92 passed）

- located 筛选（`test_orphan_ignore_and_filters.py` 4→8 用例）：截断行（truncated=1）与共享同一 inode 的两个孤儿明细（互为硬链接）均命中；身份列脏数据（`inode='not-a-number'`/device 或 inode 单侧 NULL）安全跳过不抛错不误命中（CAST fail-closed）；`scanned_at` 过期 60 天未清理的行仍可筛出（located 只看 found_count 不看新鲜度）；located 与 confidence=high AND 叠加只返回交集。
- API 宽松契约（`test_orphan_files_api.py`）：未知取值 `bogus` 原样透传到服务层（不做 API 层校验，与 status/confidence 一致）。
- 扫描范围收紧（`test_orphan_hardlink_copy_scan.py` TestScanScopeExclusions +2 用例）：`stat_limit=1` 两轮间 keyset 游标越过被排除候选——若排除失效 ignored 会额外贡献一次成功 stat（`stat_inspected` 断言可分辨），`stat_failed` 只来自在范围内的 gone 文件；被排除候选的既有结果行本轮不被删除/覆盖（scanned_at/found_count 原样），仍交由 30 天保留期任务清理。
- 前端（`orphan-files.spec.ts` 5→9 用例）：快捷操作切换保留既有 path_like/status 筛选一并提交；refreshPageData 刷新保留 located 快照；文件夹视图开启时 group_by_folder 与 hardlink_copies 同时提交；文件夹子项默认关闭时不提交 hardlink_copies。
- 生产代码本轮零改动（纯测试）；black 重排后复跑通过、flake8 干净、mypy 基线不变。

## 2026-08-15 - 两批改动回归加固

### 新增回归保护（本轮对话全部修改）

- 备份补偿（`test_torrent_file_backup_reconcile.py` 3→12 用例）：文件复用双路径不触发复制、`torrent_file` 直连与 `.torrents` 子目录双源解析、复制失败不落库不回填、commit 失败回滚并清理新复制文件、目标筛选（跨下载器/dr/deleted_at/短 hash 排除）与 added_date 倒序批次、路径映射异常回退原路径；仓储字符串过滤/计数、schema 空串拒绝、`get_downloader_from_store` 按 str() 归一匹配 UUID 与整数值；批次配置默认值守护。
- 同步协调器（`test_sync_coordinator.py` 26→29 用例）：full 同步同样触发补偿、tracker-only 不触发、补偿抛异常仅记入 errors/details 不阻断信息同步（outcome 保持 success）。
- 副本预扫描（`test_orphan_hardlink_copy_scan.py` 10→19 用例）：受控时钟中途截止保留已完成根部分结果、截断 note 优先于预算 note、resolved 候选与无候选指针明细跳过、无结果身份优先获得遍历名额且旧结果不被覆盖、budget_exceeded 写入行 scan_note 而权威副本数不丢、任务注册契约（executor 可导入/调度/timeout>预算）、heavy_sync 登记断言、五项护栏默认值守护、execute() 包装器摘要透传。
- 查库契约（`test_orphan_hardlink_detection.py`）：服务与端点双层模块级断言不再引入遍历函数。
- 前端（`orphan-files.spec.ts` 82→83 用例）：预扫描路径截断提示 + 未定位余量展示。

### 验证

- 后端 `tests/services + tests/api + tests/tasks` 全量 **2285 passed, 6 skipped**；black/flake8 通过。
- 前端全量 **738 passed**；typecheck、目标文件严格 ESLint 0 warning 通过。
- 文档同步：feature_list.json 两个 feature 的任务 evidence 追加回归加固记录；roadmap 测试计数更新。

## 2026-08-15 - 副本定位改为定时预扫描落库，前端只读结果

### 需求与实现

- 用户要求：整体查找副本在文件系统过大时耗时不可控，不能放在点击请求里；改为新的定时任务后台执行并存库，前端只查结果，并严格控制性能。
- 新定时任务 `orphan_hardlink_copy_scan`（每日 04:00，`OrphanHardlinkScanService.run_round`）：keyset 游标分批 stat 候选 → 仅 `nlink>1` 的身份进入限时遍历 → 结果按 `(device_id, inode_id)` 唯一落库 → 保留期清理。任务登记 `task_profiles` heavy_sync 互斥。
- 性能护栏（全部可配）：stat 限量 2000/轮（`ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE`）、遍历限量 200 inode/轮（`MAX_TARGETS`）、单调时钟预算 300s 在 `os.walk` 目录间检查（`BUDGET_SECONDS`，超时保留部分结果标记 `budget_exceeded`）、单 inode 路径存储上限 100（`MAX_PATHS_PER_TARGET`，截断标记 `truncated`）、结果保留 30 天清理、写库分批 200 行短事务、遍历单线程串行。
- 新迁移 `c8d9e0f1a2b3`（head 由 `b6e1c4d9a2f7` 推进，单 head）：`orphan_hardlink_copy_result` + 单行游标表 `orphan_hardlink_scan_state`；`device_id` 用 String(32)——Windows `st_dev` 是无符号卷序列号，实测可超 SQLite 有符号 64 位（`Python int too large to convert`），与 `orphan_current_candidate` 同惯例。
- `hardlink-copies` 端点改为纯查库：模块级测试断言服务不再 import 任何遍历函数；保留每文件廉价 stat 复核实时 `st_nlink-1` 总数；未覆盖文件返回 `pending_scan=true`；响应以 `scanned_count/pending_scan_count` 取代 `searched_root_count`。
- 前端弹框：文案改为"由每日定时任务后台整体查找并存储"，新增待预扫描计数/扫描时间/等待提示/截断提示。

### 验证过程中发现并修复的问题

- 同步 helper 内 `await db.flush()` 未 await（协程被丢弃）导致 `current_detail_id` 挂空、stat 窗口恒为空——测试从"永远空窗口"变为真实管线后暴露。
- Windows 下测试真实调用根收集器会把整个 `C:\` 作为扫描根（os.walk 全盘）——测试改为 patch 根收集器限定 tmp 目录；生产环境由 300s 预算兜底（预算内在后台串行遍历，不与交互争抢）。
- Windows `time.monotonic()` 分辨率 15.6ms（GetTickCount64），内存库整轮可能落在同一 tick 使 `budget=0` 测试不确定——改用受控时钟序列。
- 测试与迁移断言适配：SQLite 把表内唯一约束物化为 `sqlite_autoindex_*`（不保留约束名）→ 改断言 autoindex + 重复身份 INSERT 被拒；全量表计数 30→32。

### 验证

- 后端：新增 `test_orphan_hardlink_copy_scan.py`（限时遍历/限量/游标/幂等/清理/预算 10 用例）；`TestHardlinkCopyLocations` 重写为查库契约；迁移 3 文件 34 passed；`tests/services + tests/api` 全量 1930 passed 6 skipped；`tests/tasks` 368 passed（含 task_profiles 漂移守卫驱动更新）；black/flake8 全部通过。
- 前端：orphan-files.spec.ts 82 passed；全量 44 suites / 737 passed；typecheck、变更文件严格 ESLint 0 warning、生产 build 通过。
- 已同步 roadmap（services/infra/tasks/data-models/tests/test-coverage/根元信息，行号实测）、feature_list.json、session-handoff.md；未执行 Git 提交，工作区原有未跟踪产物保持不动。

## 2026-08-15 - 种子文件备份补偿、孤儿副本整体定位与筛选下拉提示语

### 根因与实现

- 用户报告"种子文件管理页面 6 月 7 日后无变动"。取证确认非前端缓存：6 月初同步拆分 info-only 后代码不再执行种子文件备份；本地库 1042 条备份最新停在 2026-05-29，活跃种子 2.1 万+ 无备份记录。
- 同步协调器在 info-only 与 full 路径单下载器完成后调用 `_reconcile_torrent_file_backups`（L1435）：`reconcile_missing_backups`（L151）按 `TORRENT_BACKUP_RECONCILE_BATCH_SIZE`（默认 200）限量增量补齐，支持复用已有备份文件/项目内旧文件、qB 纯 hash 与 Transmission `name.hash.torrent` 源文件名；逻辑删除墓碑视为已处理不自动重建；文件复制在写锁外、DB 记录与 `TorrentInfo.backup_file_path` 同一短事务提交，失败只记错误不阻断信息同步。
- 连带缺陷修复：下载器主键为 UUID 字符串，但备份模型/筛选/导入接口按整数校验；全部改为 String，新增迁移 `b6e1c4d9a2f7`（Integer→String(36)，幂等类型探测 + batch 临时表恢复）。
- 孤儿"查找副本"按用户确认口径从"仅扫已配置映射目录"改为"当前运行环境可访问目录整体查找"：`collect_runtime_accessible_roots`（L311）Linux 读 `/proc/self/mountinfo`、其它平台回退源路径同设备祖先、Windows 枚举盘符；硬链接不跨文件系统，按目标 `st_dev` 严格剪枝并在 `os.walk` 中跳过符号链接与异设备目录，不进入系统/缓存目录所在的其他磁盘。
- 种子页三个筛选下拉提示语从左至右改为"请选择下载器/请选择种子状态/请选择tracker"：`AdvancedMultiSelect` 新增 `placeholder` prop（默认"请选择"保持兼容），仅改提示不改筛选逻辑。

### 验证过程中修复的问题

- 迁移测试抓到 downgrade 数据破坏：SQLite batch 重建经数值亲和力把 `'550e8400-…'` 截断成 `550`；按仓库"受限回滚"惯例改为存在不可无损转整数值时 `raise RuntimeError` 拒绝自动回滚（6132/7b2c9 同款），测试改为断言拒绝执行保持 head + 整数文本可无损降级。
- 前端新测试的 stub 选择器修正：vue-test-utils v1 对驼峰注册名不做 kebab 转换，实际标签为 `advancedmultiselect-stub`。
- 修复 HEAD 既有失败的 `torrent-error-reason-ui.spec.ts` 契约漂移：`title="种子错误原因"`/`:description` 锚点随 5c297b5 迁入 TrackerDetailCard，契约改为扫描卡片源码 + 视图 `:error-reason` 透传断言。

### 验证

- 后端：新增 `test_torrent_file_backup_reconcile.py` 3 passed；`tests/services` 全量 1061 passed 1 skipped；`tests/api + tests/core` 1250 passed 5 skipped（迁移链单 head）；black/flake8 通过；mypy 无新增错误类别（新代码 cast 清理后仅 1 处与全仓库一致的 ORM 直接赋值）。
- 前端：全量 44 suites / 737 passed；`npm run typecheck`、变更文件严格 ESLint 0 warning、生产 build 成功；完整 `npm run lint` 仍被无关 `keywords-board.spec.ts` 5 条既有 warning 拦截（本次文件 0 warning）。
- 按 roadmap-maintain 实测行号同步 services/orphan_file_service.md/infra/frontend/tests/test-coverage 与根 README 元信息；feature_list.json 新增功能条目；未执行 Git 提交，工作区原有未跟踪产物保持不动。

## 2026-08-14 - Tracker 主域名筛选、错误单种排查与卡片统一

### 需求确认与实现

- 按用户确认，Tracker 筛选使用 `tracker_url` 的主机/域名部分：去除 scheme、端口和路径，复用定时 Tracker 同步已写入的 `TrackerInfo.tracker_url/tracker_host`，未新增数据库字段或迁移。
- 已测量获取全部域名的真实耗时：30475 条 Tracker 记录提取 90 个域名，SQLAlchemy 查询+解析 5 次为 231.515–262.118ms，低于 1 秒，因此不增加内存持久化缓存。
- `GET /api/v1/torrents/getList` 新增 `tracker_domain` 和 `single_error_only`：错误单种先判断错误状态，再以全局可见任务的名称+大小是否只有一个任务判定唯一，不按该种子包含多少 Tracker 服务判定。
- 列表/传统模式均新增 Tracker 主域名多选、错误单种快捷操作和退出提示；两种模式的 Tracker 详情现在都由同一个完整弹框组件渲染，标题、关闭按钮、Tracker/文件/Peers 页签、内容区、五列 Tracker 表格和状态语义一致。
- 用户反馈上一版仍存在视觉差异后，将 Tracker 详情弹框骨架完整下沉到 `frontend/src/views/torrents/components/TrackerDetailCard.vue`；两个父页面只传入 `list`/`traditional` 定位属性、数据和事件，旧的两套外层卡片代码与页面级样式已移除，表格字号、间距、状态色、URL 截断和操作列冻结样式继续统一引用 `frontend/src/styles/_tracker-table.scss`。
- 新增/加强 `frontend/tests/unit/tracker-detail-card.spec.ts` 与 `traditional-view-component.spec.ts` 运行时和静态回归，覆盖完整弹框骨架、两种 layout、五列结构、snake/camel 字段兼容、错误提示、中性状态、汇报事件和 loading，防止两种视图再次分叉或恢复旧卡片代码。

### 验证

- 后端 `tests/api/test_torrent_list_api.py`：35 passed。
- 前端目标组件/视图测试：4 suites / 44 passed；`npm run typecheck`、目标 ESLint、生产构建通过；完整 `npm run lint` 仍被 3 个无关关键词测试文件的 5 条既有 warning 阻断；`git diff --check` 通过（仅报告 Windows 换行转换提示）。
- 当前未提交、未推送、未部署；工作区原有未跟踪产物保持不动。

## 2026-08-14 - 超量扫描改为可关闭提醒

### 需求与调整

- 用户确认超量扫描只需提醒，不再要求路径映射/孤儿样本双重核查；提醒可在当前页面手动关闭。
- 前端移除“已完成双重核查”按钮和核查说明输入，超量提示改为 warning 类型并支持关闭；同一页面中同一 scan_id 关闭后不再重复显示，新扫描批次重新显示。
- 后端 `_evaluate_cleanup_snapshot()` 不再把 `cleanup_review_required` 作为清理门禁；手动预览/清理、前缀快捷删除和定时自动清理仍受 completed、最新 scan_id、实时 manifest、路径授权、文件身份等安全校验保护。
- 保留历史复核字段与 `/guardrail-review` 兼容接口，但不再依赖其记录放行清理；超量字段继续用于提醒及后续活跃候选的提醒传递。

### 验证

- 新增后端回归：超量 completed 批次在清理预览、前缀快捷、手动和定时四条入口均不因提醒被拒绝；自动清理拒绝测试覆盖通用安全校验。
- 新增前端回归：超量提醒显示、无双重核查按钮、可关闭且不影响 `cleanupAllowed`；即使历史兼容复核字段已有时间值也不恢复旧门禁。
- 定向回归补强后后端相关套件为 `333 passed, 1 skipped`，前端 orphan/API 套件为 `118 passed`；本轮尚未提交或部署，工作区原有未跟踪文件保持不动。

## 2026-08-14 - 孤儿文件页面视图模式与嵌套表头修复

### 根因与修复

- 主表无条件注册 Element UI `expand` 列，`folderView` 原先只影响请求参数；因此扁平模式仍会为每行生成左侧展开入口。
- 文件夹展开区复用的子表未关闭默认表头，展开后会把子表列头再次渲染成第二个绿色表头；普通文件箭头隐藏规则还被错误嵌套在 `.hardlink-location-summary` 下，生成选择器无法命中实际管理表。
- 现在仅文件夹模式注册展开列，子表显式 `show-header=false`，并将普通行箭头隐藏规则移到 `.orphan-files-page` 的实际作用域；后端聚合、懒加载、分页和选择语义不变。

### 验证

- `orphan-files.spec.ts` 定向回归 `81 passed`；新增扁平/文件夹展开列动态切换、普通文件行展开 class/懒加载事件，以及子表表头、数据行和选择事件回归。
- 前端 `npm run typecheck`、改动文件 ESLint、生产 build 和 `git diff --check` 通过；build 仅报告仓库既有 51 条 Sass/Element UI/Browserslist warning。
- 完整 `npm run lint` 仍被 3 个无关关键词测试文件的既有 5 条 warning 阻断；根 `./init.sh --ci` 在当前主机因缺少 `/bin/bash` 无法启动。未修改后端，未触碰工作区既有未跟踪文件。

## 2026-08-14 - 定时孤儿扫描回接 Cron 生命周期与执行日志

### 根因与修复

- `OrphanScanTask.execute()` 原先只创建 `queued` 扫描并立即返回 `status=success`，实际扫描和定时自动清理由进程内 dispatcher 另起任务完成，导致 APScheduler 的 Cron 执行记录与业务终态脱节。
- `OrphanScanDispatcher` 现在返回扫描、清理及阶段摘要，并提供 `wait_for_completion()`；定时入口等待同一个 dispatcher 任务直到扫描和清理均收口，扫描失败、超时、清理部分失败和超护栏拒绝分别写入明确终态。
- `CronTaskExecutor` 将内部类返回的业务终态透传为 `success/outcome/skip_reason`，并把 OrphanScanTask 的阶段摘要写入现有 `task_logs` 记录；HTTP/手动扫描仍只提交 queued 并由页面轻量轮询，不改变后台 API 语义。
- 超过 50000 条的批次继续沿用 `cleanup_review_required` 门禁；路径映射与孤儿样本核查完成前没有调用清理、隔离或物理删除入口。

### 验证

- 定向孤儿/定时任务回归 `39 passed`；完整 `backend/tests/tasks` `331 passed`；目标 Python 文件 `py_compile` 通过。
- 新增回归覆盖：Cron 等待同一 dispatcher 的扫描+清理结果、超量门禁在 Cron 中收口为 skipped、内部类 failed/partial 终态进入 task_logs、dispatcher 异常不伪造 success。

## 2026-08-14 - 1.02GB 真实孤儿库迁移中断恢复与启动 fail-fast

### 根因与修复

- 对用户复制到 `E:\Users\huangzj\Desktop\app.db` 的 1,020,416,000 字节数据库只读核查：`quick_check=ok`、Alembic 仍为 `4c1d8e7a2b90`，同时残留空的 `_alembic_tmp_orphan_scan_result`。旧迁移逐列 batch 重建大表，中断后下次直接报临时表已存在；移除残留后，`current_detail_id` 回填又被 SQLite 错选 `scan_id` 索引，120 秒仍未完成。
- `7b2c9d4e6f10` 改为原生 `ADD COLUMN`，SQLite 外键列使用受控 `ALTER TABLE ... REFERENCES`；升级/降级入口识别 batch 残留：原表仍在时删除可重建临时副本，原表缺失时拒绝猜测并要求从已验证迁移前备份恢复。
- 回填确保 `ix_orphan_file_canonical_path` 存在并用 `INDEXED BY` 固定查询计划；8 个 downgrade 列在单次 batch 中移除，避免再次重复复制大表。
- 应用内 Alembic 保留现有日志 handler，迁移异常会显示首因；`migrate_database()` 返回显式成功状态并校验最终 head。lifespan、直接运行和桌面入口均在迁移失败时 fail-fast，不再继续 seed、孤儿隔离对账、调度器或下载器任务。

### 真实数据与回归证据

- 仅在工作区副本上完整升级：约 4.97 秒到 `7b2c9d4e6f10`；202669 个候选全部填充 `current_detail_id`，未匹配 0、重复指针组 0；`quick_check=ok`、`foreign_key_check=0`，无 `_alembic_tmp_%` 表。
- 历史 8 个 `total_orphans>50000` 的 completed 批次均为 `cleanup_review_required=1` 且未复核；没有调用清理、隔离或删除入口。桌面原始副本和线上数据库均未写入。
- 迁移链/治理/回滚/startup 专项：`66 passed`，包含 Alembic 无异常但未到 head 的假成功回归。改动 Python 文件 compileall、Flake8 与目标 mypy 通过。Black 已完成 5 个文件重排，但 Windows 进程在退出阶段超时；产物由后续编译、lint 与 pytest 验证。
- 已同步数据库迁移约束、根/后端/测试路线图、feature_list 与 handoff；任务产生的 1GB 级工作区测试副本将在交付前清理，不纳入版本控制。

## 2026-08-13 - 孤儿扫描后台化、稳定明细复用与 12 万级争用治理

### 交付结果

- `POST /orphan-files/scan` 仅创建持久化 `queued` 扫描并立即返回同值的 `scan_id/task_id`；进程内串行调度器领取任务、重启恢复 queued、把残留 running 终结为 failed。页面以 `GET /orphan-files/scans/{scan_id}` 单行只读接口轮询，不再让扫描请求占住 HTTP 连接。
- `orphan_current_candidate.current_detail_id` 绑定稳定当前明细：成功扫描仍重新核查文件系统并推进 `first/last_seen`、次数与 resolved，但已知且未清理的同一路径只复用/按需更新一条 `orphan_file`，不再每轮重复插入 12 万条；清理后同路径重新出现才创建新明细。
- 生命周期发现/更新、明细复用、resolved 和可清理候选均按 `ORPHAN_SCAN_COMMIT_BATCH_SIZE`（默认 200）keyset/分块执行；每批查询、变更、flush/commit 在同一 `db_write_scope`，启动时稳定隔离候选对账也改为分页，避免 SQLite 长写锁和 `BUSY_SNAPSHOT`。
- 文件夹父页仅做 SQL 聚合，初始不加载 children、也不 stat 子项；展开后调用 `/folders/children` 独立分页。实时 `st_nlink - 1` 只覆盖扁平当前页、单文件父页和展开后的当前子页。
- Alembic head `7b2c9d4e6f10` 增加 queued/current 统计、超量复核字段、稳定明细 FK/索引并回填存量。历史及新产生的 `>50000` 成功扫描进入强制清理门禁；必须同时确认路径映射和孤儿样本并记录说明。未复核门禁会向仍有活跃候选的后续小扫描传递，防止以零路径/部分扫描绕过。
- 本轮没有调用清理、隔离或彻底删除入口；现有 120100 条继续锁定，等待真实路径映射与样本核查。

### 验证

- 全部孤儿相关后端测试：`369 passed, 1 skipped`（包含安全门禁传递、迁移/生命周期、存量候选即时绑定稳定明细与真实文件型 12 万争用回归）。
- 12 万回归使用真实临时 SQLite 文件、WAL、`synchronous=NORMAL`、15 秒 busy timeout、NullPool：120100 个已知孤儿以 200 条短事务更新期间并发轮询状态 API；完成后 `orphan_file` 仍为 120100、新扫描明细为 0，接口 P95 `<1s`、最大 `<3s`（运行约 42 秒，阈值 180 秒）。
- 前端 `typecheck`、改动文件 ESLint、`2 suites / 112 tests` 和生产 build 通过；build 仅有仓库既有 51 条 Sass/Browserslist warning。
- 后端涉及文件 Flake8、compileall 通过；新增后台任务/API/startup/task 四个文件 mypy 通过。包含历史 SQLAlchemy 1.x ORM 文件的 mypy 仍报既有 `Column` 类型体系问题（203 条），未作为本功能回归失败处理。
- `alembic heads` 为单 head `7b2c9d4e6f10`；根 `init.sh` 经 Git Bash 通过，前端子 init 仍有既有 null-byte warning；`roadmap-maintain` 已同步模块、迁移与测试覆盖路线图。

## 2026-08-13 - 辅种异常排查改为当前列表分页

### 用户确认口径与交付

- 检查最近提交 `ea5a5f3` 后，将独立 `POST /torrents/same-content-inspection`、646 行共享弹窗及 447 行诊断服务移除。
- 同内容排查改为现有 `GET /torrents/getList?same_content_only=true`：普通筛选先参与候选组判定，按种子行复用现有排序及 `skip/limit` 分页，只为当前页装配 Tracker 数据。
- 列表模式和传统模式均不打开新窗口/弹窗；快捷操作直接切换当前表格数据源，筛选、排序、切页、分页大小和刷新保持列表逻辑，并显示“退出排查”入口。
- `TorrentViewSwitcher` 同步保存 `showingSameContent`，两种视图切换不丢失排查模式；进入重复查询、高级搜索或应用模板时会退出同内容模式。
- 判定仍为名称完全相同、大小相同且规范化 InfoHash 至少两个不同值，并排除逻辑删除、回收站和活动删除占用项；无 Schema/Alembic 变更。

### 验证

- 后端：`test_same_content_inspection_api.py + test_torrent_list_api.py` 共 `40 passed`；专用用例从 4 个扩为 9 个，新增组合筛选、活动删除、活动快照、复合主键稳定排序分页、低 SQLite 变量上限大页及仅当前页 Tracker 预取保护。
- 后端改动文件：Black、Flake8、py_compile 通过。
- 前端：列表视图、传统视图、视图切换共 `3 suites / 36 tests passed`；新增筛选、排序、分页大小、翻页、刷新持续携带 `same_content_only`，以及重复查询、高级搜索、模板切换清理模式的回归保护；TypeScript、改动文件 ESLint、生产 build 通过（仅既有 Sass/Browserslist warning）。
- 根 `init.sh` 经 Git Bash 通过，前端子脚本报告既有 warning；`git diff --check` 通过。
- 全量回归：后端 `3376 passed, 7 skipped`；前端 `43 suites / 719 tests passed`。
- 完整 `npm run lint` 被 3 个无关关键词测试文件的既有 5 条 warning 拦截，无新增 error；后端 mypy 在既有 ORM Column/Pydantic 构造上报告 64 条历史错误。
- 已按 `roadmap-maintain` 用当前源码实测行号同步 API 说明、根/分支路线图与测试覆盖矩阵。

## 2026-08-13 - 同名同大小种子只读异常排查（已由上方列表分页方案替代）

### 用户确认口径与交付

- 在种子列表模式和传统模式的“快捷操作”中新增“辅种异常排查”，两种视图复用同一个只读弹窗。
- 无需选择下载器或填写条件：后端主动按“名称完全相同 + 大小完全相同 + 规范化 InfoHash 至少 2 个不同值”发现候选组；同一下载器内的跨站不同 Hash 任务同样可成组。
- 弹窗支持“完整排查结果”和“仅错误种子”。分页单位是候选组；仅错误模式过滤无错误组，并在组内只返回错误种子，同时保留该组总副本数、不同 Hash 数和错误数作为上下文。
- 功能只读：不连接下载器、不删除、不重汇报、不修改数据库；回收站、逻辑删除和活动删除任务占用项不进入结果。

### 判错与安全边界

- 错误口径联合种子任务 `status=error`、非空 `error_reason`、`has_tracker_error`，以及 Tracker 持久化 `status=error`、announce/scrape 失败/超时状态码 3/4。
- 为避免后台 Tracker 行级状态尚未同步时漏报，最新 announce/scrape 消息还会直接匹配当前启用的 `failed` 关键词池；界面明确展示任务错误、聚合 Tracker 错误或具体 Tracker 消息/状态原因。
- 新 API 只返回 Tracker 主机名，不返回完整 Tracker URL。错误消息中的 URL 会去除 userinfo/path/query/fragment，常见 `passkey/authkey/api-key/token/secret` 参数脱敏，异常响应也不回显内部异常文本。
- 新增 `POST /api/v1/torrents/same-content-inspection`，统一使用 `CommonResponse` 和 `total/page/pageSize/list`；API 口径记录于 `backend/docs/api/same-content-inspection.md`。
- 已按 `roadmap-maintain` 用当前源码实测行号同步根索引、后端 API/服务、前端 API/组件/视图和测试覆盖矩阵；无 Schema/Alembic 变更。

### 验证

- 新 API：`4 passed`；快捷删除、Tracker 共享策略与新功能相关回归：`48 passed`。
- 前端弹窗与两视图入口：`3 suites / 36 tests passed`；`npm run typecheck` 通过。
- 后端新增文件：mypy、Black（single worker + 独立 cache）、Flake8、py_compile 通过；本次前端文件严格 ESLint 0 warning；`git diff --check` 通过。
- 前端生产 build 成功；仅报告仓库既有 Sass/Browserslist/包体积 warning。
- 大型后端回归曾并行运行并因 180/300 秒上限超时，超时前无失败，但未计作完整通过；随后顺序执行直接相关 48 项全部通过。
- 完整 `npm run lint` 在 ESLint 前被任务前已有的高级搜索生成契约漂移拦截；绕过契约后全量 ESLint 仅有 3 个既有关键词测试文件的 5 条 warning，本次文件严格检查为 0 warning。
- 用户已授权提交并推送；提交范围仅包含本功能源码、测试、API/路线图与项目记录，任务前已有的未跟踪技能、工具和计划目录保持不动；未部署。

## 2026-08-13 - 最新提交 Tracker 策略回归加固

### 新增回归保护

- 查看最新提交 `625c1e3d0c423c56ac40a28828a3a96378d061dd`，确认其主题为“完整修复 Tracker Working 空消息判定”，影响共享策略、行级同步服务和种子级状态判断。
- 新增 `backend/tests/core/test_tracker_status_policy.py`，直接覆盖共享纯函数：状态码 2 的 Working 归一化、None/空串/空白消息正常证据、非空 announce/scrape 消息优先、精确/部分匹配模式、未知消息保留、全部失败/任一正常的聚合规则。
- 未修改业务实现；保留工作区原有未跟踪目录不变。

### 验证

- 新增策略回归：`30 passed`。
- 提交直接涉及的行级同步与种子级判断回归：`115 passed`。
- 同步协调器回归：`26 passed`。
- 新测试可编译，代码行长度检查通过，`git diff --check` 通过。
- 根 `init.sh` 仍因当前 Windows WSL `E_ACCESSDENIED` 无法启动；Black 的 `--diff` 检查确认新文件无需格式调整，但 `--check` 在本机运行时超时。
- 用户已授权提交并推送；提交范围仅包含本次测试与配套记录，任务前已有未跟踪目录全部排除。

## 2026-08-12 - Tracker Working 空消息行级残留完整修复

### 根因与修复

- 对用户重新复制的 `E:\Users\huangzj\Desktop\app.db` 只读复核：数据库仍停留在 Alembic
  `de898cb28172`，状态判断 Cron 仍是旧 `0 */5 * * *`；本地修复提交 `196a530` 尚未推送，说明重新部署
  实际未包含上一轮代码/迁移。
- 发现上一轮之外的第二层缺陷：`tracker_status_sync.py` 会直接跳过 announce/scrape 均为空的行，导致
  下载器已同步为 `Working(2)` 时，`tracker_info.status='error'/msg='失败'` 仍永久残留。
- 新增 `app/core/tracker_status_policy.py` 作为行级同步与种子级判断的共享纯函数：非空 announce/scrape
  消息优先按关键词分类；仅消息均为空且原始状态明确 Working 时提供正常证据；成功/忽略/Working
  任一存在即正常、全部失败才错误、未知保留旧值。
- 行级同步把 Working 空消息作为当前 Tracker 行自身的正常证据，不参与 host 全局汇总，避免同 host
  下一个正常种子掩盖其它种子的明确失败消息；保留原有消息型 host 聚合和增量零 DML 机制。
- 种子级 `evaluate_tracker_error_state()` 改为复用共享证据聚合，同时保留下载器类型对应的未联系/
  发送中中性规则及精确关键词语义。独立状态判断 Cron 与 `4c1d8e7a2b90` 错峰迁移保持不变。

### 最新快照证据与验证

- 快照 `quick_check=ok`，大小 `920604672`；zimiao 域名相关 359 个活动 Tracker：201 个明确失败消息、
  152 个 `Working + 空消息 + error/失败`、6 个中性空消息。只读重放后行级只将这 152 行恢复
  `normal/正常`，其余不被跨种子 host 连带覆盖。
- 种子级只读重放会清理 294 个 zimiao 历史 `has_tracker_error=True`；另有 2 个所有 Tracker 均明确
  失败的旧正常标记会被纠正为错误。
- 新增/加固 20 个行级回归实例，含 None/空串/空白、announce/scrape 状态边界、非空失败/未知、
  未知与明确失败同 host 时逐行保留、双消息、顺序、
  幂等、跨种子 host 隔离及 zimiao 359 行快照形态；另加 2 个同步协调器顺序回归，锁定原始 Tracker
  同步成功后才执行行级状态同步、失败时跳过。行级 `40 passed`、种子级 `75 passed`、协调器
  `26 passed`；最终全量已覆盖这些路径。
- 最终后端全量收集 3344 项，`3337 passed, 7 skipped`。目标 mypy、Flake8、Ruff、Black
  （变更源码/行级测试，`--no-cache`）、
  compileall、BtDeck 架构门禁、单 Alembic head `4c1d8e7a2b90`、feature JSON 与 `git diff --check`
  全部通过。根 `init.sh` 仍被 Windows WSL `E_ACCESSDENIED` 阻止，已完成等价分项门禁；样例库全程只读。

## 2026-08-12 - Tracker Working 空消息判定与独立 Cron 错峰修复

### 已完成

- 以 `E:\Users\huangzj\Desktop\app.db` 只读复核 zimiao 样例，确认主要误判不是当前同步状态本身，
  而是 `Working(status=2) + None/空消息` 进入 unknown 后保留了历史 `has_tracker_error=True`。
- 保留状态码与关键词联合判定：未联系/发送中仍为中性；Working 仅在 announce/scrape 两类消息都
  为 `None`、空串或空白时明确正常；存在非空消息时仍按 failed/success/ignored 关键词分类，未知
  消息仍返回 `None` 保留旧值。
- 状态判断继续作为独立 Cron。Tracker 状态同步保持 `10,40 * * * *`，状态判断改为
  `20,50 * * * *`，每 30 分钟在同步任务后 10 分钟执行；任务 profile 与内部建议周期同步为 30 分钟。
- 新增 Alembic `4c1d8e7a2b90` 数据迁移：仅当 task_code、旧 Cron 和系统旧描述全部命中时更新，
  避免覆盖用户自定义计划/描述；downgrade 对称恢复，当前迁移链仍为单 head。
- 新增 36 组 zimiao 双 Tracker 顺序/下载器类型/空消息矩阵，并补齐非空关键词优先、真实 SQLite
  写回、软删除隔离、同步/判断重任务互斥，以及迁移重复升级、自定义值和逻辑删除保护。
- 按 `roadmap-navigation` 定位源码，并由 `roadmap-maintain` 同步 tasks/data-models/infra/测试覆盖索引、
  revision 数量、当前 head 和实测行号；更新数据库迁移约束、后端说明、功能状态与交接记录。

### 样例库重放与验证

- 只读重放 346 个 zimiao 相关种子：新逻辑为 `316 normal / 30 error / 0 unknown`；其中 293 个当前
  错误标记会在下一轮判断中清除，30 个所有 Tracker 均明确失败的种子继续保持错误。
- 判断+迁移定向 `80 passed`；迁移/回滚/任务准入相关 `130 passed`；后端全量收集 3323 项，
  `3316 passed, 7 skipped`。
- 修改范围 mypy、Flake8、Ruff、Black API check、compileall，`scripts/lint_btdeck.py`、
  `alembic heads`（仅 `4c1d8e7a2b90`）及 `git diff --check` 通过。
- 根 `./init.sh` 在当前 Windows 主机仍被 WSL `E_ACCESSDENIED` 阻止；已执行等价分项门禁。样例
  `app.db` 全程只读，未直接迁移或写入；应用升级时由 Alembic 迁移存量任务计划。

## 2026-08-12 - 高级搜索跨字段回归矩阵加固与提交推送

### 新增回归保护

- 第一笔功能修复已独立提交为 `99ccf65 fix: 完善高级搜索全字段查询语义`，随后才开始测试加固，
  保持功能实现与额外回归保护的提交边界清晰。
- 后端新增跨字段全集分区矩阵：名称、比率、完成时间、分类、标签、错误状态、下载器改名、超级
  做种、Tracker URL/消息均断言 include 与 `mode=exclude` 互斥且并集等于全部活动种子；有明确
  反操作符的字段同时断言其结果与 exclude 完全相同。
- 后端对完成时间、比率、比率限制、标签、分类逐字段验证 `is_null`/`is_not_null` 分区；增加
  Tracker URL/消息 `%`、`_` 字面匹配、软删除 Tracker 的否定补集，以及分号标签 token 用例。
- 前端新增五个可空字段与八个非空字段矩阵、九类排除条件正操作符守卫；模板到请求端到端测试
  覆盖数值/日期空值/分类/标签/状态/下载器/超级做种/Tracker，并锁定三个条件组的两个独立连接器。
- 按 `roadmap-maintain` 以当前源码实测更新高级搜索测试行数、覆盖矩阵、功能清单和交接记录；
  无业务代码或数据库 Schema 变更，原有未跟踪备份、镜像、缓存和工具目录仍未触碰。

### 验证

- 后端重点 `162 passed`；全量 `3253 passed, 7 skipped`；新增测试文件 Black/Flake8 通过。
- 前端重点 `2 suites, 111 passed`；全量 `43 suites, 715 passed`；`tsc --noEmit` 通过。
- 全量前端输出仍包含既有 Vue 浅渲染控件告警与 Browserslist 提示，但进程退出码为 0；使用
  `--silent` 复跑取得无截断总数。

## 2026-08-12 - 高级搜索全字段语义审计与修复

### 已完成

- 审计机器契约中的 20 个高级搜索字段，不只修状态：Tracker URL/消息的否定条件改为
  `NOT EXISTS(匹配 Tracker)`，多 Tracker 种子不会因另一条不匹配记录被误纳入；无活动 Tracker
  自然属于正条件的严格补集。
- 文本 contains/starts/ends 对 `%`、`_` 使用字面匹配；标签从任意子串改为逗号/分号分隔的完整
  token 匹配并兼容分隔符空格，避免“辅种”误命中“IYUU自动辅种”。
- 下载器选择仍显示 nickname，但请求保存稳定 `downloader_id`；后端兼容 ID、当前 nickname 与历史
  快照 nickname，下载器改名后旧模板仍可命中。
- 超级做种改为“是/否/不支持”三态；完成时间、比率、比率限制、标签、分类增加字段级
  “未设置/已设置”，不支持空值搜索的字段在请求期拒绝。
- 前端不再把排除模式预先翻成反操作符，而是原样发送正操作符 + `mode=exclude`；后端统一取严格
  补集，NULL/未设置值不再被 SQL 三值逻辑意外漏掉。查询模板和中间请求转换均保留该模式。
- 高级搜索基础集同时排除 `dr != 0`、`deleted_at != NULL` 和活动删除任务，回收站记录不再泄漏。
- 同步更新 v3 机器契约、生成 TypeScript、路线图、功能清单与交接记录；无 Schema/Alembic 变更。

### 回归与验证

- 后端相关全链路：`235 passed`；新增语义重点两文件：`142 passed`。覆盖用户原始 azusa + error
  载荷、Tracker 多行否定、SQL 通配符、标签 token、回收站、下载器改名、超级做种三态、空值
  白名单/空字符串、布尔 false 与 include/exclude 补集。
- 前端：Builder/Input/契约/请求转换 4 suites、`119 passed`；新增重点两套件 `82 passed`。
- 全量回归：后端 `3233 passed, 7 skipped`；前端 `43 suites, 686 passed`。
- 后端 Ruff/Flake8，前端目标 ESLint、`tsc --noEmit`、`contract:check`、生产 build 及
  `git diff --check` 均通过；build 只有既有 Sass/Browserslist/体积提示。
- 用与用户示例同结构的真实 SQLite 请求单独验证，`tracker_url contains azusa` +
  `status in [error]` 返回 `total=1`。
- 根 `./init.sh` 未能在当前 Windows 主机执行：WSL 启动返回 `E_ACCESSDENIED`，提权环境又无
  `/bin/bash`；已拆分执行后端/前端等价校验。完整前端 lint 的 5 条无关既有 warning 仍为基线。

## 2026-08-12 - 种子文件、任务日志、高级搜索与错误原因修复

### 后续修正：高级搜索 UI/组合查询与 Tracker 状态语义

- 高级搜索中“添加条件”改为居中的主按钮，“添加条件组”改为次按钮；组间 AND/OR 控件
  作为 `.condition-groups` 下的独立节点，不再嵌套在任一条件组卡片中。
- 修复用户原始 `tracker_url contains azusa` + `status in [error]` 请求无结果：高级搜索的
  `error` 现在与普通列表一致，同时匹配 `TorrentInfo.status == "error"` 和
  `TorrentInfo.has_tracker_error == True`，并覆盖 eq/ne/in/not_in。
- 确认 Tracker“未联系”误分类来自两处：Transmission 过去把成功布尔值直接写入整型状态列，
  定时判定又只看失败关键词。现在依据 hasAnnounced/hasScraped、成功、超时和活动状态归一为
  0–4 状态码；qB 未联系及 Transmission 未联系/发送中均按中性处理，仅全部明确失败才标错。
- 每项均补回归：Builder 按钮视觉/DOM 层级、原始高级搜索载荷、Transmission announce/scrape
  状态矩阵、定时聚合以及前端“未联系”中性样式。
- 功能修复先独立提交为 `82ceed8`；随后补充 33 项后端、2 项前端回归，覆盖高级搜索
  basic/eq/ne/in/not_in 真值表与软删除排除，Transmission 新旧 RPC 字段优先级、announce/scrape
  独立状态及 legacy/async/manual add/modify 全部写库入口，定时任务真实 SQLite 批量更新，
  三条件组连接器顺序/删除收敛，以及前端发送中、布尔 `false` 的中性边界。

### 后续修正验证

- 后端全量：`3215 passed, 7 skipped`（3222 collected）。
- 前端全量：`43 suites, 676 tests`；`npm.cmd run typecheck`、生产 build 与变更文件严格
  ESLint 通过。
- 完整 `npm.cmd run lint` 的契约检查通过，随后仍被 3 个无关既有关键词测试文件的 5 条
  warning 门禁拦截（0 error）；build 的 51 条 Sass/Browserslist/体积 warning 为既有基线。
- 新增 Python 测试通过 Ruff、Flake8，前端测试通过目标 `--max-warnings 0` ESLint，
  Git Bash 根 `./init.sh --ci` 与 `git diff --check` 通过；Windows Black 目标检查再次超时，
  未自动重排存量文件。
- 路线图按源码实测行号同步；技能包未包含其说明所列 drift 脚本，改以 `rg` 关键符号/末行、
  文件计数和链接回读校验。无新增 Schema/Alembic 变更；功能提交后以独立测试提交交付，
  未 push/deploy。

### 已完成

- 种子文件管理：备份列表对当前页下载器做单次批量查询并返回当前 `downloader_nickname`；
  前端刷新列表即可反映昵称变化，不逐行动态加载，也不再显示 ID；筛选区复用项目
  `management-page` 样式。
- 定时任务：任务日志“导出/清理过期日志”改用项目标准按钮；从任务列表“查看日志”后
  显示当前任务筛选，点击“清空”会清除 `task_id`、全部筛选及日期并立即请求全部日志。
- 高级搜索：共享机器契约将 `status.kind` 改为 `multiSelect`，状态与下载器使用同一
  `AdvancedMultiSelect`（不允许新建）；旧模板标量和 equals/not_equals 兼容归一；组内
  “添加条件”移到“添加条件组”上方。
- 错误原因：`torrent_info` 新增可空 Text `error_reason`，Alembic head 更新为
  `de898cb28172`；Transmission FULL/INFO-ONLY/兼容同步与新增记录均写入 errorString，
  原因变化参与差异检测，warning/正常恢复时清空；API 输出 `errorReason`。
- 列表模式与传统模式均在种子名称 hover tooltip 和 Tracker 卡片展示错误原因。
- 按 `roadmap-maintain` 以 grep 实测行号同步根索引、前后端分支、迁移清单与测试矩阵；
  `feature_list.json`、`session-handoff.md` 同步更新。

### 验证

- 后端全量：`3171 passed, 7 skipped`（3178 collected）；新增字段首次暴露出旧模型字段全集
  断言缺口，补齐后全量复跑通过。相关定向套件先行累计 88 passed。
- 前端全量：`43 suites, 672 tests`；`npm.cmd run typecheck` 与生产 build 通过；修改源码和
  测试的严格 ESLint 通过。
- 本地浏览器实测：文件管理筛选 UI；任务日志按钮；查看任务日志从 2 条经“清空”恢复全部
  6 条；状态多选及“添加条件”在“添加条件组”上方，均符合预期。临时服务与 QA 数据库已清理。
- 后端修改文件 Flake8、`git diff --check` 通过。完整前端 lint 仍仅被 3 个无关既有测试文件
  的 5 条 warning 拦截；目标 mypy 仍报告 142 条既有 SQLAlchemy/Pydantic 类型债；Windows
  Black 26.5.1 对目标文件检查超时，已格式化其中可完成文件且 Flake8 无误。
- Git Bash 根 `./init.sh` 通过；保留既有“虚拟环境未激活”、前端 null-byte warning，且未对
  本地 `backend/config/app.db`（当前 f9a1b2c3d4e5）擅自执行新迁移。

## 2026-08-11 - 按同步阻塞验证报告实施修复

### 已完成

- P0：同步 info/full/legacy 路径只接受 `app.state.store` 缓存客户端；缓存缺失直接失败，
  不再在业务路径构造 qB/TR 客户端；`sync-single` 改为 AsyncSession + 异步 `select`。
- P1：qB Tracker 写入只消费 enrich 成功连续前缀，游标停在最后 durable hash；新增远程失败、
  批大小大于预算回归；qB/TR info 增加稳定 hash cursor、durable progress callback，并在
  有 cursor 时强制完整快照续跑。
- P2：WAL 快照接入 SQLite `wal_checkpoint(PASSIVE)`，提供 `busy_count`/`checkpoint_busy`；
  同步健康查询增加有界超时和 503 reason code。
- W0：新增 [sync-stopgap-runbook.md](backend/docs/operations/sync-stopgap-runbook.md)，覆盖
  暂停、活动运行确认、错峰恢复、升级指标和演练记录模板；同步更新 roadmap 与修复计划。

### 验证

- 定向修复套件：83 passed；coordinator/checkpoint/governance/metadata/legacy：70 passed、5 skipped；
  memory-bound/file contention：18 passed、1 skipped；health：10 passed。
- 后端全量 `python -m pytest -q`：`3142 passed, 7 skipped`（3149 collected）。
- 修复后真实文件型 SQLite 大档：22,000 torrents / 30,000 trackers、30 轮、600 探针，
  0 超时、最终 BUSY=0、SLO 4/4 PASS；结果归档于临时目录
  `C:\Users\huangzj\AppData\Local\Temp\btdeck-sync-fix-20260811`。
- `python -m ruff check`（本次修改文件）通过；`git diff --check` 通过。
- Black 全文件检查在 Windows 环境超时且报告仓库既有格式债，未自动重排；未执行生产 Alembic 迁移、
  未执行生产暂停/恢复演练。

## 2026-08-10 - W0-W4-2 从头实现验证（发现发布门缺口）

### 验证结论

- 独立复跑后端全量 pytest：`3135 passed, 7 skipped`；Windows 包装命令在 pytest 已输出最终摘要后于 300 秒退出码 124，未见测试失败。
- 独立执行真实文件型 SQLite 大档基准（22000 torrents/30000 trackers/30 轮）：600 次探针无超时、最终 BUSY=0、SLO 4/4 PASS。
- W1 短事务、增量 Tracker 状态、W2 准入/交互容量/Worker guard、W4-2 健康接口代码和测试基本有效。
- 发现 P0：canonical info/full 路径在缓存客户端为空时仍可自建 `qbClient`/`trClient`；`sync-single` async handler 内直接执行同步 `db.query`，可能在 SQLite 锁等待时阻塞事件循环。
- 发现 P1：qB Tracker 在 `batch_size > 本轮预算` 时游标可越过未拉取 hash；独立 fake 客户端复现“只调用 h000000/h000001，游标却到 h000004”。info-only 部分运行也没有记录级 cursor。
- 发现 P2：W4-1 `busy_count`/`checkpoint_busy` 仍恒为 `None`；W0 专用生产止血 Runbook/暂停恢复演练证据缺失。
- 本地 `app.db` 为 Alembic `f9a1b2c3d4e5`，仓库 head 为 `f5e6d7c8b9a0`，`alembic check` 报数据库未更新；未在验证中擅自迁移。

### 产物

- 详细报告：`backend/docs/operations/database-blocking-and-sync-verification-2026-08.md`
- 本轮无业务代码修改；待修复 P0/P1/P2 缺口后再更新对应 feature evidence 和发布门状态。

## 2026-08-09 - purge_delay_count 计数列 + 隔离区展示(硬链接延后可观测性)

### 背景
上一批实现了"到期删除遇硬链接副本跳过时延后 purge_after"。本批补充可观测性:新增 `purge_delay_count` 计数列记录每次延后,并在隔离区列表展示(用户决策:展示 + 每次隔离重置,不加通知触发点)。计划经 3 个独立子代理审查后实施。

### 实现
1. **模型**(orphan_file.py):`OrphanCurrentCandidate` 加 `purge_delay_count Integer NOT NULL default=0`,同步 `__init__` 参数与 `to_dict` 键。
2. **迁移**:新 Alembic `f0e1d2c3b4a5_orphan_purge_delay_count.py`(down_revision=f9a1b2c3d4e5),幂等 inspector 守卫 + `server_default="0"`(SQLite ADD COLUMN NOT NULL 硬要求),downgrade 可回滚。
3. **head 同步**:test_db_migration.py `EXPECTED_HEAD` → f0e1d2c3b4a5 + 链注释 + 新增"列存在且 default=0"断言(dflt_value 存储带引号,strip 后比较)。
4. **延后递增**(orphan_file_service.py):改用 **SQL 表达式原子递增**(`purge_delay_count=OrphanCurrentCandidate.purge_delay_count + 1`)并入同一次 UPDATE,避免 commit 后对象过期/StaleData 与 read-modify-write 丢计数;日志记录累计次数。
5. **隔离区展示**:get_quarantine_list 手工 dict 加 `purge_delay_count` 键;前端 `QuarantineItem` 加字段;index.vue 隔离区表格加"延后次数"列(>0 用 warning tag 高亮,0 显示短横线);spec 工厂加字段。
6. **重置语义**:mark_quarantined 白名单加 `purge_delay_count=0`(每次进入隔离态重新计数,re-quarantine 不残留旧计数)。

### 验证
- 迁移测试 11 passed(head 链完整 + 列存在/类型/NOT NULL/默认值断言);孤儿套件 **253 passed / 1 skipped**(基线 251+2);hardlink 专项 23 passed(含 count 递增/跨次累加/无副本不变)。
- black/flake8 通过;mypy 新增行零错误(__init__ 的 `self.purge_delay_count=...` 跟随既有 setattr Column 债模式)。
- 前端 typecheck 零错误;orphan-files.spec.ts **70 passed**(含隔离区渲染)。

### 变更边界
- 加 1 列 + 1 迁移 + 前端展示,不加通知触发点(用户决策);工作区"同步治理"未提交改动保持原样;Git 提交待用户要求。

## 2026-08-09 - 孤儿硬链接功能后续:到期跳过延后 + restore 幂等 + 前端类型检查

### 待办 #1:到期删除遇硬链接副本跳过时延后 purge_after(B 方案)
- config.py 新增 `ORPHAN_HARDLINK_PURGE_DELAY_DAYS=7`:到期删除遇副本跳过后,purge_after 延后 N 天,打破"每日重试循环"(跳过后 purge_after 不变 → 次日再次选中→再次跳过)。
- orphan_file_service.py `except HardlinkCopyError` 块:跳过后 `_commit_candidate_state` 把 purge_after 延后至 `now + N 天`(无上限,副本清除后仍会正常删除)。`except Exception` 保守跳过分支不改(检测异常时无法确认是否真有副本,不延后)。
- 新增 4 测试:默认天数延后、自定义天数延后、延后窗口内不再选中、副本清除+延后到期后正常删除;原 `test_purge_expired_skips_file_with_copies` 补延后断言。

### 待办 #2:restore_quarantined 幂等修复
- 原 L2237-2241 把所有未匹配路径笼统报"候选不存在或非 quarantined 稳定态"。改为三态区分(镜像 purge_quarantine_now 范本):
  - `status=candidate`(已恢复,mark_restored 把候选回滚到 candidate)→ 幂等成功,restored_count+1
  - 状态不符(purged 等)→ 失败原因附实际 status/operation_state
  - 无记录 → "候选不存在"
- 新增 `TestRestoreIdempotency` 4 测试:已恢复幂等成功、混合批次、purged 附实际状态、不存在区分原因。

### 待办 #3:前端类型检查
- `cd frontend && npm run typecheck`(`tsc --noEmit`)通过,零错误。确认 `hardlink_notes?` 可选字段与 `HardlinkNote` interface 无类型问题。node 环境:nvm-windows v22.23.1(`C:\nvm4w\nodejs`,PATH 需手动加入)。

### 验证
- 孤儿套件 **251 passed / 1 skipped**(基线 243 + 新增 8);hardlink+idempotency 专项 21 passed。
- black/flake8 通过;mypy orphan_file_service.py **149 错误 = 基线**(L1938 新增的 `candidate.canonical_path` Column 参数错误已用 `cast(str, ...)` 修复,零新增)。

### 变更边界
- 未新增数据库列/迁移;未加通知触发点;前端仅验证未改代码。
- 工作区"同步治理"未提交改动保持原样;Git 提交待用户要求。

## 2026-08-09 - 孤儿扫描落库分批重构 + 孤儿数护栏(API 卡死治本)

### 背景
8-09 生产事故日志实测:扫描 18:54:02 完成 → 通知 19:05:47 创建,中间 11 分 45 秒为 12 万孤儿落库时间(单大事务 commit 独占 SQLite 写锁),导致 API 卡死。12 万孤儿大部分为真实数据(用户确认),不应阻止入库。

### 实现(落库分批 + 护栏 + 恢复)
1. **配置**:新增 `ORPHAN_SCAN_COMMIT_BATCH_SIZE=200`(落库批次)、`ORPHAN_SCAN_MAX_ORPHANS_WARNING=50000`(护栏阈值)。
2. **`_finalize_successful_scan` 分批重构**(orphan_scanner.py):原单事务(12 万行 OrphanFile insert + reconcile + 状态一次 commit)拆为三步——① `_save_orphan_files` 明细分批(每 200 条独立 session + db_write_scope + commit)② `_reconcile_lifecycle` 候选分批(insert/update 按批 commit)③ completed 状态最后单独 commit。
3. **`reconcile_candidates` 分批支持**(orphan_lifecycle_service.py):新增 `batch_size` 参数,insert/update 按批 commit;resolved 标记依赖完整 seen_paths,留在最后统一处理(计数语义不变)。
4. **`_fail_scan` 补明细清理**:失败时 DELETE 本 scan_id 已提交的 OrphanFile(分批后中途失败的前几批明细不再成为幽灵记录)。
5. **护栏**:孤儿数超阈值时 `orphan_count_warning=True` + 通知正文追加异常提示(不阻断落库,真实大批量孤儿照常入库)。
6. **启动恢复**(startup/lifecycle.py):新增 `recover_interrupted_orphan_scans()`(支持 session_factory 注入),启动时把残留 running 扫描记录标 failed(落库分批后崩溃残留的兜底;running→failed 不改门禁语义,但消除列表空白)。

### 验证
- 新增测试 6 个:reconcile 分批提交计数、分批后 resolved 正确、护栏超阈值/未超阈值标志、running 恢复×2。孤儿套件 **243 passed / 1 skipped**(基线 237+6);任务 7 passed;迁移 11 passed;black/flake8 通过;mypy lifecycle 0 错误、orphan_lifecycle_service 16 个为预存 Column 债(零新增,git diff 证实未触碰 setattr 行)。
- 契约测试 `test_lifecycle_failure_rolls_back_details_and_completed_status` 自动适配新语义(改名为 `test_lifecycle_failure_cleans_up_details_and_marks_failed`):reconcile 失败 → 明细被 `_fail_scan` 清理 → detail_count==0 仍成立,语义从「事务回滚」变为「失败清理」。

### 变更边界
- 未新增数据库列/迁移;未动前端;未动 tr 降级问题(独立,缺运行时日志证据);未清理 12 万真实孤儿(靠下次扫描自然处理)。
- 工作区"同步治理"未提交改动保持原样;未执行 Git 提交。

## 2026-08-09 - 孤儿扫描 API 卡死事故排查与路径映射加固

### 事故现象
部署后启动孤儿文件扫描,API 请求失效卡死。日志显示扫描发现 120,100 个孤儿文件(8-02 那次扫描已落库 120,219 个)。

### 直接原因(API 卡死)
`_finalize_successful_scan`(orphan_scanner.py:736-781)把 12 万行 OrphanFile insert + reconcile_candidates 候选对账 + 状态更新塞进**单个 session,一次 db.commit()**,长时间独占 SQLite 写锁,饿死所有其它 API 写入。三个独立子代理审查确认:这有意为之的"原子写入"设计(L202 注释 + L747 docstring),`_save_orphan_files`(L799)分批函数是死代码未被主流程调用。

### 根因排查过程(严谨记录,含修正)
排查 12 万孤儿的产生源,逐步排除多个假设:
- **tr 下载器(c04cc424)独占 119,097 个孤儿,全是 low confidence**(其余 3 个下载器共 1,122 个,全 high)。low = 扫描时整体降级。
- 假设① inventory 超时:实测直连 tr 拉取 9952 种子+160万文件仅 17 秒,远低于 30s 超时。**排除**。
- 假设② files 解析失败:实测 transmission-rpc 7.x 的 fields["files"] 元素有 name 键,解析正常,0 个空。**排除**。
- 假设③ save_path 取不到:实测 `download_dir` 属性能取到。**排除**。
- 假设④ JSON 全空 external 屏蔽 rules:**基于本地开发库(backend/config/app.db)的误判**——本地库 tr 的 path_mapping JSON external 确实全空。但**生产库(E:\...\Desktop\app.db)tr 的 JSON 有 220 条有效映射 + 仅 1 条空**,rules 也有 13 条。生产库配置健康,此假设对生产事故**不成立**。
- **生产环境 tr 降级的即时原因(运行时 fail_time/缓存/client)只能从生产日志确认**,静态分析与实测已穷尽。

### 本次代码修复(作为健壮性加固,非事故对症药)
修复 `UnifiedPathMappingService` 的真实缺陷:JSON 非空但全部映射无效(external 全空)时,原逻辑锁定 JSON 模式并忽略 path_mapping_rules,导致映射彻底失效。

变更 `backend/app/core/path_mapping.py`:
- `__init__` 新增 `_json_effective` 标志:JSON 有至少一条有效映射(internal+external 均非空)时为 True。
- JSON 全无效时回退到 path_mapping_rules(原 `if/elif` 互斥改为独立加载)。
- JSON 有效时也加载 converter,使 `get_rules()` 不再返回空(供 resolve_external_path 的 rules 来源使用)。
- `internal_to_external` 在 `_json_effective=False` 时优先 converter,避免无效 service 原样返回内部路径。

验证:新增 `tests/core/test_path_mapping_fallback.py` 8 测试全绿(JSON 全空回退/JSON 有效不回退/get_rules 暴露/rules 端到端 resolve);path_mapping 回归 46 passed;孤儿回归 237 passed/1 skipped(基线一致);black/flake8/mypy 干净。生产库配置复测 7/8 路径成功解析。

### 未解决(后续任务)
- **API 卡死根因**:`_finalize_successful_scan` 单大事务分批重构(8 项治本,风险高,需单独审批)。本修复消除"JSON 全空"场景的误报源,但不解决大事务结构本身。
- **生产环境 tr 降级即时原因**:需查生产日志(搜"精筛不可用"/"降级为目录粗筛"含 c04cc424)确认运行时 fail_time/缓存状态。
- **白名单兜底加固**:collect_torrent_directory_whitelist L351-353 在 resolve 失败时用 internal save_path 兜底,commonpath 与 external 扫描根失配——独立加固点,留待后续。

## 2026-08-09 - 前端异步操作条目占用与刷新防重复提交

### 问题与实现

- 种子批量删除和重复种子快捷删除原先只创建进程内任务，业务状态落库前刷新页面仍能查到同一行并再次提交。现由 `DeletionTaskManager.create_task_reserving` 在单锁临界区原子划分 accepted/skipped，并维护线程安全活动 ID 快照；completed/partial/failed 终态释放。
- 普通种子列表/计数、重复种子查询、快捷删除预览和高级搜索统一排除活动删除 ID。提交阶段保留全候选并交给任务管理器原子查重，避免“先查后写”竞态；全部占用返回 `task_id=null`，混合提交只执行 accepted 项。
- 孤儿主动清理和隔离区彻底删除复用既有 `orphan_purge_job`，用 JSON1 子查询把 pending/running 任务中的 orphan ID / canonical path 作为持久化占用；提交锁独立于可关闭的同步写治理开关。列表、分组统计、预览、忽视、隔离列表和恢复入口排除占用项，worker 仍可读取自身快照；终态自然释放。
- 前端 API 类型补齐 nullable task_id 与 requested/accepted/skipped；所有四类异步操作提交后立即刷新，无任务时仅提示并停止轮询，混合提交展示跳过数量。

### 验证

- 后端相关回归：249 passed；py_compile、改动文件 flake8 通过；`deletion_task_manager.py` 与 `orphan_purge_job_service.py` mypy 通过。
- 前端：3 个定向 Jest suites、typecheck、改动文件 ESLint 与生产 build 通过；build 仅有既有 Sass/Browserslist warnings。
- 完整后端收集 3005 项，本次相关用例全部通过；失败来自工作区既有 `test_sqlite_worker_guard.py` mock 返回 `stdout=None` 后执行 `None + str`，未越界修改。完整前端 lint 仍仅被 3 个无关关键词测试文件的 5 条既有 warning 拦截。
- `docs/roadmap/` 已按实测行号同步；未新增数据库 Schema/Alembic 迁移，未执行 Git stage/commit/push。

## 2026-08-08 - Transmission 种子错误状态同步丢失修复

### 问题

Transmission 的种子在出现明显错误（tracker 错误 / 本地错误如磁盘满、数据损坏）时，同步后状态未正确显示为错误。经端到端追踪定位为**双层缺陷**：

1. **字段层**：`TR_BASE_FIELDS`/`TR_DETAIL_FIELDS`（torrents_async.py:2373-2391）未含 `error`，Transmission RPC 按需返回字段时根本不返回错误信息。
2. **映射层**：`convert_transmission_status()` 仅依据 `status` 字符串查表，无通往 `"error"` 的分支；而 Transmission 的 `error` 字段（0=ok/1=tracker警告/2=tracker错误/3=本地错误）独立于 `status`（一个 error=3 的种子 status 仍是 downloading/seeding），被完全忽略。

### 根因验证

- 经 3 个独立子代理交叉审查 + `transmission_rpc` v7.0.11 库源码验证确认。
- 关键陷阱：`Torrent.error` property 实现为 `self.fields["error"]`（方括号索引），字段缺失抛 **KeyError** 而非 AttributeError → `getattr(default=0)` 无效，必须先加字段再用 `isinstance` 守卫。

### 本次实现

- **新增** `TorrentStatusMapper.resolve_transmission_status(tr_status, tr_error)`（torrent_status_mapper.py）：`error>=2` 归入 `"error"`；`isinstance` 守卫规避 KeyError 与测试 MagicMock 陷阱；`checking` 状态优先于 error（校验过程不被 tracker 错误误判）。
- **字段列表**：`TR_BASE_FIELDS`/`TR_DETAIL_FIELDS` 追加 `"error"`。
- **4 个 DB 写入点**改用 resolve：torrents_async.py:1392（FULL sync）、3122（INFO-ONLY sync）、torrent_sync.py:548（LEGACY sync）、torrent_helpers.py:774（种子添加路径）。
- **明确不改**：seed_transfer_service.py:607（迁移成功校验，改了会导致健康做种种子被误判迁移失败并触发源种子删除）、torrent_metadata.py:212（重复检测展示，留待后续评估）。
- **测试**：扩展 `_make_tr_torrent` 工厂加 `error` 默认参数；新增 `TestTransmissionErrorStateMapping`（mapper 单测）+ `test_transmission_error_sync.py`（集成测试，覆盖记录创建、变更检测、恢复链路）。

### 验证

- 新增测试 66 项全通过；回归 test_torrent_crud_status_migration.py（24 passed）、test_sync_db_write.py、test_torrent_sync_review.py 全通过（5 skipped 均为 pre-existing 测试隔离问题，与本次无关）。
- black/flake8 干净；mypy 对本次改动零错误（77 个错误全为预先存在的 Column[arg-type]/rowcount 等，不在改动行）。
- 前端已完全支持 status="error"（status-config.ts 已有 error 标签/图标/红色样式/筛选项），无需改前端。

### 已知限制（发布说明）

1. 首次部署后，历史 DB 中所有 Transmission `error>=2` 的种子会在下次同步刷新为 `status="error"`，UI 错误计数会上升（预期且正确，无自动删除副作用）。
2. 用户仅看到"错误"标签，看不到具体原因（如"磁盘已满"）——errorString 持久化留待后续。
3. dashboard 仪表盘暂无 error 统计桶（error 种子落入 other，downloading/seeding 计数会略降）。

### 变更边界

- 未新增模型列 / 未做 Alembic 迁移；未改前端；未动 has_tracker_error 体系（独立 tracker 判断任务领地）。
- 未执行 Git stage/commit/push。

## 2026-08-08 - 同步任务数据库阻塞详细修复计划

### 本次产物

- 新增 [同步任务数据库阻塞与接口超时修复计划](PLANS/sync-database-blocking-remediation.md)，将评估文档的 P0-01～P0-06、P1-01～P1-07、P2-01～P2-06 全量映射到 W0～W5 交付项和 G0～G5 发布门。
- 计划明确先以 SQLite 为主：W1 先修真实分批提交、Tracker 增量写和旁路 DML，W2 再统一手动/定时同步、保留交互下载器容量、清理 async 阻塞调用并强制单 Worker。
- 后续 W3 增加有界队列、运行预算、持久化 checkpoint 和任务新鲜度，W4 补齐结构化观测、readiness 与真实文件型 SQLite 争用基准，W5 再根据指标决定 Tracker 指纹、DBWriteQueue 和 PostgreSQL 演进。
- 每个工作项均包含根因、目标文件、实施步骤、测试、观测、回滚和 DoD；计划同时定义 CRUD SLO、事件循环 lag、事务时长、WAL、内存和数据新鲜度门槛。
- 更新 PLANS/README.md，增加专项修复计划入口。

### 变更边界

- 本次只新增/更新 Markdown 计划和会话记录，未修改业务源码、数据库 Schema、Alembic 迁移或运行配置。
- 已核对源评估与计划均覆盖同一组 19 个风险编号；计划内相对链接有效，git diff --check 和 ./init.sh --ci 通过。前端 init 保留既有 null-byte warning。
- 未执行 Git stage、commit 或 push；工作区既有 Docker、feature_list 和未跟踪文件保持不动。

## 2026-08-08 - 同步任务数据库阻塞与接口超时 P0/P1/P2 风险登记

### 本次整理

- 新增 `backend/docs/operations/database-blocking-and-sync-issues-2026-08.md`，汇总本次会话发现的 P0/P1/P2 问题、代码证据、实际任务日志、临时止损、分阶段修复、观测指标和文件型 SQLite 压测验收标准。
- 明确当前 `sync-resource-governance` 只能视为部分止血：Tracker 状态全量重写、info-only 大事务、手动/旧版同步旁路、请求端同步下载器调用阻塞事件循环、交互 API 容量未保留以及 SQLite 多 Worker 风险仍未闭环。
- 追加实测边界：本地库约 2.2 万种子/3 万 Tracker；历史 Tracker 任务最长 1161 秒；相关治理测试 75 项通过，但现有 benchmark 未覆盖真实文件型 SQLite 写锁和真实请求并发。

### 变更边界

- 本次仅新增运行评估文档和进度记录，未修改业务源码、数据库 Schema、迁移或运行配置；未执行 Git stage/commit/push。

## 2026-08-08 - 列表模式删除等级入口 Lucide 同步

### 本次实现

- 检查最近 4 次提交，确认 2e2e28a23cd7918483be400be54f18fb0642608f 只覆盖 TraditionalView.vue；列表模式 index.vue 的工具栏批量删除和行内删除仍使用 Element 图标。
- 两组四级删除菜单均迁移为 LucideIcon：tag、trash-2、trash、alert-triangle；保留原有删除命令、等级 1 danger 配色和下拉交互。
- 增加列表模式回归，锁定两组菜单的 SVG、图标名称、menu-icon 与 danger 标识；更新前端视图路线图和 feature_list.json 的 v1.0.6.37 evidence。

### 验证与边界

- npm run test:unit 全量通过；目标两套视图 2 suites / 26 tests 通过；typecheck、改动文件 lint、Vuex action lint、生产 build 通过。
- npm run lint 仅因其他测试文件已有 5 条 ESLint warning 退出；本次改动文件无 warning。build 保留既有 56 条 Sass/资源 warning。
- E:\Git\bin\bash.exe ./init.sh --ci 通过，前端 init 仅有既有 null-byte warning；git diff --check 通过。
- 未执行提交或推送；保留工作区中既有 Docker 远端部署改动及未跟踪文件。

## 2026-08-08 - Docker 远端部署后端健康检查等待修复

### 根因

- 远端 `btdeck-backend` 从 `04:10:24Z` 开始执行孤儿文件隔离状态对账，直到 `04:13:06Z` 才完成 FastAPI 启动前流程，耗时约 162.6 秒。
- 原健康检查仅配置 `start_period=30s`、`interval=30s`、`retries=3`；Compose 在后端最终就绪前将其判定为 unhealthy，随后报 `dependency failed to start`。
- 远端实际 Compose 文件由主机持有，`build-and-export-images.bat` 原先只上传两个镜像 tar，不会同步本地 Compose 配置。

### 本次实现

- 新增 `.btdeck-remote-deploy.sh`：部署时先启动 backend，轮询 `docker inspect` 健康状态最多 300 秒，确认 healthy 后再启动 frontend；同时兼容 `docker compose` 与 `docker-compose`。
- `build-and-export-images.bat` 将该远端部署 helper 与两个镜像 tar 一并上传并调用，保留远端现有 Unraid Compose 的下载目录挂载配置。
- `docker-compose.yml` 后端健康检查 `start_period` 调整为 5 分钟；`backend/Dockerfile` 的镜像健康检查调整为 300 秒。

### 验证与边界

- `.btdeck-remote-deploy.sh` 通过 `sh -n`；`docker compose -f docker-compose.yml config --quiet` 通过；根 `E:\Git\bin\bash.exe ./init.sh --ci` 通过。
- Docker Desktop 本机引擎仍受 Windows 管道权限限制，未进行本地容器构建；本次未执行远端部署、Git stage、commit 或 push。

## 2026-08-03 - 孤儿全选当前筛选、隔离区表头对齐、剪贴板回退与操作日志布局

### 实现内容

- **真全选**：孤儿列表表头复选框不再依赖 Element 自带 selection 列（其数据源被虚拟窗口截成约 15 行），改为维护 `select_all + excluded_orphan_ids + 当前筛选快照` 的独立选择模型；已选计数按服务端 `total` 计算，选中全部时显示“当前筛选全部”标识。清理/忽视提交时前端发送 `select_all + filters + excluded_orphan_ids`，后端 `resolve_orphan_selection` 按与列表完全一致的 `_build_orphan_conditions` 把筛选快照解析为稳定 ID 集。
- **批量查询分块**：全选产生的大规模 ID 快照按 500/批切块，规避 SQLite 绑定变量上限；清理预览对全选大批量截断为前 200 条明细并返回 `items_truncated`（计数与总大小仍覆盖全部）。
- **隔离区表头对齐**：隔离区页签接入共享 `management-table` 表头类，与孤儿页签的表头布局、颜色、间距及固定方式一致，字段与功能不变。
- **剪贴板回退**：新增 `frontend/src/utils/clipboard.ts` 的共享 `copyTextToClipboard`，优先 Clipboard API，非安全上下文/权限拒绝时回退隐藏 textarea + `execCommand`；操作日志详情 JSON 复制与任务详情内容复制统一接入并保留成功/失败提示。
- **操作日志布局**：搜索栏与操作栏拆为独立筛选面板与操作栏，窄视口响应式排列；查询、重置及操作逻辑不变，前端补 `torrent_name` 查询参数对齐后端已有模糊搜索。

### 验证与边界

- 后端孤儿全套：229 passed / 1 skipped（含新增 select_all 快照解析用例）。
- 前端全量 Jest：31 suites / 527 tests（新增 clipboard 用例）；TypeScript typecheck、定向严格 ESLint、生产 build 均通过。
- 变更后端文件 Flake8、`git diff --check` 通过；生产 build 仅保留仓库既有 Sass/Element UI 与资源体积 warning。
- 全量 mypy 仍报告孤儿历史 SQLAlchemy 模块既有 Column 类型债务，新增选择解析辅助代码无新增命中。
- 无数据库 Schema、迁移或依赖变化；已提交并合并远程 `origin/dev`（并行会话 `5725797` 同主题实现，见下条）后推送，工作区原有未跟踪文件保持不动。

## 2026-08-03 - 孤儿列表固定表头、忽视身份与大页性能修复

### 根因与修复

- 表头问题来自滚动放在 `.orphan-table-scroll` 外层，而 Element Table 自身的 overflow 形成了不滚动的 sticky 包含块；现改为给表格 `height="100%"`，监听其内部 body 滚动，表头由组件原生固定。
- 只读核对现场数据库：最新成功扫描剩余 44,499 条中，1,915 条明细的 `downloader_id` 与同路径候选不一致，同时 `canonical_path` 与 `last_seen_scan_id` 一致。旧忽视逻辑用 `(downloader_id, canonical_path)` 查候选，导致这些合法项全部返回“候选不存在”。现统一以候选表主键 `canonical_path` 定位，成功扫描对账及同快照操作同步修正归属元数据；候选状态、operation_state 和扫描批次门禁均保留。
- 忽视服务新增结构化开始/完成日志、失败原因计数与样例、数据库提交异常堆栈；前端区分成功、部分失败和全部失败，并展示后端 `failed_list.reason`。
- 大页保留 20/50/100/500/1000 选项，自定义与 API 单批上限统一为 1000；表格按 48px 定高计算可视窗口并加 8 行 overscan，通过上下占位行保持滚动高度，1000 条数据不再同时创建 1000 个 DOM 行。

### 验证与边界

- 后端孤儿模块全套：226 passed / 1 skipped；其中忽视、生命周期与 API 定向回归 52 passed。
- 前端孤儿页面：24 passed；前端全量：30 suites / 516 tests；TypeScript typecheck、定向严格 ESLint和生产 build 均通过。
- Flake8、`git diff --check` 与 Git Bash 根 `./init.sh --ci` 通过；生产 build 仅保留仓库既有 Browserslist、Sass/Element UI 和资源体积 warning，根验证保留 Windows/npm null-byte 环境 warning。
- 全量 mypy 仍报告孤儿历史 SQLAlchemy 模块的 169 条 Column 类型债务；新增规范路径身份辅助代码无新增命中。当前 Windows Python 的 Black CLI 再次出现格式处理完成后进程不退出，已停止对应验证进程。
- 无数据库 Schema、迁移或依赖变更；已随 `v1.0.6.36` 一并提交，工作区原有未跟踪文件保持不动。

## 2026-08-03 - 孤儿文件列表表头与大分页批量操作修复（并行会话）

### 修正内容

- 孤儿文件与隔离区列表统一为相同的八列表头：选择、文件路径、大小、修改时间、下载器、置信度、状态、操作；隔离区补充后端返回的原文件修改时间。
- 两个页签均使用固定高度滚动容器和吸顶表头；孤儿文件列表改为首尾占位行 + 可视窗口渲染，保留完整数据集合用于全选和批量操作，降低 2000 条及以上分页的 DOM 与重渲染开销。
- 孤儿文件选择改为轻量自维护复选框，避免大分页交给 Element UI 维护 2000 条选择行；全选仍覆盖当前完整分页中的所有可操作记录。
- `set_ignored` 将孤儿明细查询、候选查询和 ORM flush 按 200 条分块，并把原先按候选逐项扫描的 O(n²) 映射改为按明细 ID 直接定位，修复 2000 条批量忽视返回“成功 0、失败 2000”。

### 验证与边界

- 后端孤儿服务/API 定向回归：37 passed；新增 401 条跨批次 flush 的批量忽视回归用例；Flake8 通过。
- 前端孤儿页面回归：20 passed；前端全量 Jest 30 suites / 512 tests passed；TypeScript、全量 Vue ESLint、Vuex action lint 和生产构建通过。
- 完整 `npm run lint` 仍在任务开始前已有的 `advancedSearch.generated.ts` 契约漂移检查处阻断；Black 在当前 Windows Python 环境中命令超时；根 `./init.sh --ci` 仍被 WSL `E_ACCESSDENIED` 阻断，均未修改无关文件。
- 该实现已由并行会话推送到 `origin/dev`（`5725797`）；合并时保留其隔离区 mtime/状态/置信度列等功能点。

## 2026-08-03 - 种子实时进度与孤儿列表交互修复

### 修正内容

- 批量添加种子完成通知正文补充失败文件与具体原因；通知详情读取 `extra_data.failed_list` 结构化展示，前端同步响应也会提示失败明细。
- `/api/v1/torrents/active-torrents` 将活跃及 TTL 补查种子的最新进度按 `(downloader_id, hash)` 复合身份异步写回 `torrent_info`，只写入实际变化，并按 `SYNC_DB_COMMIT_BATCH_SIZE` 分批提交。
- 孤儿文件列表改为固定高度滚动容器，触底按页追加数据；新增高/低置信度筛选，默认排序保证高置信度在前。

### 验证与边界

- 后端相关回归：81 passed（含架构门禁；批量通知、孤儿 API/筛选、active-torrents 及进度写库）。
- 前端全量 Jest：30 suites / 511 tests passed；孤儿页面定向 19 passed；TypeScript typecheck、直接 Vue ESLint、Vuex action lint 和生产构建均通过。
- 完整 `npm run lint` 仍被任务开始前已有的 `advancedSearch.generated.ts` 契约漂移拦截，未修改该无关生成文件；根 `./init.sh --ci` 仍受 Windows/WSL `E_ACCESSDENIED` 阻断。
- Black 在当前 Windows Python 环境中命令超时未退出，未执行格式化写回；Flake8 与 `git diff --check` 通过。
- 未执行 Git stage、commit、push 或部署；保留工作区原有未跟踪目录与工具文件。

## 2026-08-02 - 下载器设置四项运行时问题修复与回归加固

### 修正内容

- 设置弹窗的基本信息表单关闭 `validate-on-rule-change`，避免编辑详情异步回填前触发名称、主机和用户名必填错误；提交时仍保留显式表单校验。
- 抽取连接测试前置判断：编辑已有下载器允许密码为空并交给后端回退已保存密码；新增下载器仍要求密码，端口等边界校验保持不变。
- 将详情回填的 `path_mapping_rules` 从设置弹窗传递到路径映射组件；规则解析抽为纯函数，空 `external` 按最长匹配规则生成并随 `path_mapping` 提交，未匹配路径仍 fail-closed。
- 修复速度规则嵌套 grid 的固有最小宽度，限速数值框/单位选择可收缩，窄视口下下载和上传规则改为单列。

### 回归与交付

- 新增 `frontend/tests/unit/downloader-regressions.spec.ts`，覆盖编辑/新增连接测试 guard、端口边界、最长路径规则、CRLF 规则和未匹配路径。
- 扩展下载器 UI 契约测试及 `backend/tests/api/test_downloader_path_mapping_update.py`，覆盖路径映射缺省保留和显式更新两条后端路径。
- 前端相关回归 3 suites / 37 tests 通过；后端相关回归 58 passed；TypeScript、严格 lint、生产构建通过；`git diff --check` 通过。
- 本次相关文件将单独提交并推送；工作区既有未跟踪临时目录、数据库备份、镜像归档和调试工具保持不动。

## 2026-08-02 - 下载器管理页顶部裁剪与页签左对齐修正

### 修正内容

- 基于最近提交 `5a07e0c` 的下载器控制室重绘，移除管理页顶部“节点控制台”标题、简介和状态指标，只保留“状态链路已建立”工具栏及以下节点列表区域。
- 设置工作台的左侧页签改为明确的弹性左右布局，补齐内容面板、页签面板和子组件的 `width`/`min-width`/左对齐约束，避免卡片宽度变化后内容漂移或溢出。
- 针对设置与新增下载器共用卡片中的页签未跟随重绘的问题，移除旧的水平页签样式，明确 Element UI 左侧导航的 `nav`、`item`、内容面板和 `tab-pane` 盒模型；页签按钮和内容强制从左起布局。
- Chrome 实测发现基本信息/速度页仍受固定 `label-width=140px` 影响，窄认证卡片的输入区被压缩至约 55px；改为卡片内顶部左对齐标签、控件满宽和内容区 `margin-left: 0`，新增与编辑模式共用生效。
- 路径管理二级页签、路径映射、速度设置、路径资产和标签页统一跟随工作台左对齐；移除路径映射组件与父页签重复的内边距。
- 更新下载器控制室 UI 契约测试，锁定顶部裁剪、设置/新增共用页签弹性布局和路径页签左对齐规则。

### 验证

- `npm.cmd run test:unit -- --runTestsByPath tests/unit/downloader-control-room-ui.spec.ts`：22 passed。
- `npm.cmd run test:unit`：29 suites / 498 tests passed。
- `npm.cmd run typecheck`：通过。
- `npm.cmd run lint`：通过（contract check、Vue ESLint、Vuex action lint 均通过）。
- `npm.cmd run build`：通过；保留仓库既有 Browserslist/Sass/Element UI warning。
- 使用 `E:\\Git\\bin\\bash.exe ./init.sh --ci`：全栈环境验证通过；前端子脚本保留当前 Windows/npm 的 null-byte warning，后端虚拟环境未激活为提示。

---

## 2026-08-02 - 下载器控制室 UI 重绘与导航 Lucide 化

### 交付结果

- 下载器管理页重绘为高密度“节点控制室”：非对称标题版式、节点/在线/任务/启用四项摘要、状态链路操作台、名称筛选、在线图例、实时吞吐/任务/延迟遥测卡片，以及可直接进入新增流程的节点卡；保留刷新、轮询、测试、同步、设置、删除和启停能力。
- 新增与编辑流程统一为接近全屏的配置工作区：顶层 Lucide 标识、左侧分区导航、粘性内容导语、Bento 表单分区和固定操作栏；新增模式会锁定需要现有下载器 ID 的速度、路径和标签页，保存后仍走原 API 流程。
- 速度、路径映射、路径资产、标签/分类和模板选择页面同步提高信息密度并统一视觉语法；补齐桌面、平板、390px 移动端以及 `prefers-reduced-motion` 降级。
- 路由侧栏、侧栏折叠、顶栏反馈/通知/用户、主题切换和通知抽屉的应用图标统一迁移到共享 `LucideIcon`；下载器相关模板移除应用自绘 SVG、Element icon 属性和界面表情符号。
- 浏览器验收发现设置弹窗原先位于布局堆叠上下文内，`v-modal` 会覆盖并阻断弹窗；已通过 `append-to-body` 将工作区提升到正确顶层。同步修复下载器启用开关对字符串状态的判断，并补齐新增模式 `plug-zap` 图标注册。

### 验证

- `npm run typecheck`：通过。
- `npm run lint`：通过（contract check、Vue ESLint、Vuex action lint 均通过）。
- 定向回归：2 suites / 110 tests 通过。
- 前端全量 Jest：29 suites / 498 tests 通过。
- `npm run build`：通过；仅保留仓库既有的 48 条 Sass/Element UI 弃用及资源体积 warning。
- Git Bash 根 `./init.sh`：退出 0；前端子脚本仅报告当前 Windows/npm 命令替换的 null-byte 环境 warning。
- 真实浏览器验收：1280x720 桌面与 390x844 移动端均无页面级横向溢出；覆盖管理总览、新增工作区和编辑模式的速度/路径/标签页；临时验收路由与样例数据已删除。
- 未执行 Git stage、commit、push 或部署；会话开始前已有的未跟踪工具目录、数据库备份、镜像归档与脚本保持不动。

---

## 2026-08-01 - 部署后旧 SPA 路由 ChunkLoadError 治理

### 证据链与根因排序

1. **已确认主因：部署前打开的 SPA 仍运行旧 webpack runtime。** 控制台中的 `app.64d1d8fb.js` 请求 `orphan-files.15d0574e.js` / `orphan-files.475718e4.css`；现场当前 `index.html` 已引用 `app.e237e2cd.js`，它映射到 `orphan-files.c9417ee9.js` / `orphan-files.43a2e370.css`，三者均返回 200。旧 runtime 不会重新请求 no-store 的 index，客户端路由跳转时仍会按旧映射取 chunk，旧文件随容器替换消失后即 404。
2. **高风险放大因素：稳定 URL 的 Service Worker 被当作哈希 JS 缓存一年。** `/service-worker.js` 实际返回 `Cache-Control: max-age=31536000, public, immutable`，且 Workbox 预缓存 app shell 和路由 chunk。当前 `main.ts` 未启用注册，因此不能断言本次标签页一定受它控制，但历史注册会显著延长旧版本驻留，不能忽略。
3. **已排除：当前镜像漏文件、宿主 volume 覆盖、多实例混版。** 线上当前入口及其映射资源完整一致；Compose 只有单个固定 `btdeck-frontend` 容器，volume 仅挂载 nginx cache/log，不覆盖 `/usr/share/nginx/html`；Dockerfile 将同一次 builder 的完整 `dist` COPY 到不可变运行镜像。
4. **低概率保留：外部代理/CDN 缓存。** 当前响应头和直连 IP 未显示代理层，index 明确 no-store；若部署拓扑以后增加反向代理，仍需保持稳定入口重验证、哈希资源 immutable 的边界。

### 修复

- 新增 `utils/deployment-recovery.ts`：识别 JS/CSS `ChunkLoadError`，保留 hash 路由并添加 `__btdeck_chunk_retry` 查询标记执行一次整页版本切换；query + sessionStorage 双门禁在 60 秒内禁止二次自动刷新，避免真实服务器故障造成刷新循环。
- `router.onError` 接入恢复；初始异步路由成功后才清除可见查询标记，重复失败时显示手动刷新提示。
- 启动时按根作用域清退旧 Service Worker，并仅删除 `vue-typescript-admin-template-` 前缀的历史 Workbox cache；失败不阻断应用启动。
- nginx 改为只有 `/assets/` 内容哈希资源可缓存一年；`/service-worker.js` 精确 location 使用 no-cache/no-store。稳定文件不再被通用扩展名规则错误标记 immutable；缺失旧 chunk 保持真实 404，交给客户端恢复。

### 验证

- 新增 `deployment-recovery.spec.ts` 11 项：错误识别、路由/query 保留、一次恢复、循环门禁、storage 不可用、query 清理、Service Worker/cache 精确清退和 nginx 缓存契约。
- 前端全量：`28 suites / 418 tests passed`；`typecheck`、严格 `lint`、生产 `build` 通过，build 仅保留既有 48 条 Sass/Element UI warning。
- 使用生产前端镜像执行 `nginx -t` 通过；挂载新 `dist` 的一次性容器实测：index 与 service-worker 均 no-store，当前 app/orphan JS/CSS 为 immutable 200，旧 orphan chunk 为真实 404。
- 根 `bash ./init.sh` 仍被当前 Windows WSL `Bash/Service/CreateInstance/E_ACCESSDENIED` 阻断。
- **未执行 Git 提交、推送或远端部署。**

## 2026-08-01 - 隔离区彻底删除异步化 + ID 空目录治理

### 问题1：为什么同步删除响应慢

- 原 HTTP 端点直接 `await purge_quarantine_now()`，请求会等到全部物理删除和审计落库后才返回。
- 这不是单纯 `os.remove` 慢：每个候选都需要重建实时 torrent manifest，删除 tombstone 前再重建一次，并执行路径授权、size/mtime/inode、租约和 TOCTOU 复核。下载器 API 网络往返与大种子文件列表才是主要耗时，且候选按文件串行处理。

### 异步任务实现

- 新增 `orphan_purge_job` 持久化任务表和 Alembic head `c7d8e9f0a1b2`；状态为 pending/running/completed/partial/failed，升降级可回滚，并对已有表/索引幂等。
- `POST /orphan-files/purge` 仅落库并调度，立即返回任务 ID；新增 `GET /orphan-files/purge-jobs/{task_id}` 查询持久化状态。
- 应用级调度器串行执行任务，原子领取防重；服务重启时将中断的 running 恢复为 pending 并重新调度。
- 终态先落库，再用 `orphan_purge:{task_id}` dedupe key 幂等写入通知中心，含总数/成功/失败数和失败明细；首次通知失败时由既有每小时补偿任务补发。
- 前端不再等待 300 秒；提交后提示任务 ID、清空勾选，完成/失败统一从通知中心查收。

### 问题2：目录不降反增的根因排序与验证

1. **已证实的主因**：原 purge 在已有 UUID 操作目录外再创建一个 tombstone UUID 目录；移走文件后原目录变空，`os.remove(tombstone)` 后新目录也变空，但两者都未 `rmdir`。因此单次彻底删除可从 1 个 ID 目录变为 2 个，净增 1。
2. **已证实的放大因子**：`build_quarantine_path()` 先创建目标目录，journal 预写/租约/移动失败时会留下新空目录；每次重试都可再泄漏一个。restore、到期 purge 和崩溃恢复路径也有同类残留点。
3. **保留的低概率因子**：非空隐藏文件/NFS `.nfs*` 占用、权限或外部并发任务会使 `rmdir` 合理失败；现在记录 warning 并保留目录，不用递归删除掩盖安全问题。

修复仅沿候选记录的 `quarantine_root` 执行 `os.rmdir`：删除已空 UUID 操作目录和已空 scan-id 根，不递归、不删非空目录、不跟随符号链接，且绝不越过记录根删除全局 `.btdeck_quarantine`。启动和每个 purge 任务还会清理历史空 UUID 目录。

### 验证

- 后端全量：`2514 passed, 6 skipped`。含任务持久化/重启恢复/成功与失败通知/补偿幂等、迁移幂等和空目录故障注入回归。
- 前端全量：`27 suites / 407 tests passed`；`typecheck` 和 `lint` 通过；生产 `build` 通过，仅既有 Sass/Element UI 弃用警告。
- 新任务模型+服务 mypy 通过，本次后端实现文件 Black 通过，`flake8 app` 全量通过。全量 `mypy app` 仍有仓库既有 1533 个错误；全量 Black 仍有 9 个未修改旧文件的格式差异。
- 根 `bash ./init.sh` 在当前 Windows 环境被 WSL `Bash/Service/CreateInstance/E_ACCESSDENIED` 阻断，脚本未开始执行；等价的前后端门禁已分别执行。

**未执行 Git 提交、推送或部署。**

---

## 2026-08-01 - 表头渐变确诊 + PageSizeCombobox 自动方向/teleport 彻底解决遮挡

**两个遗留问题收尾**：

### 问题1（表头渐变未生效）—— 确诊为部署问题，代码已正确
深入分析构建产物 `dist/assets/css/app*.css`：
- 我的 `.management-table .el-table__header-wrapper th` 规则是**唯一**带 `!important` 的表头背景规则（Element 默认 `.el-table th.el-table__cell{background-color:#fff}` 无 `!important`），且在产物中出现顺序更后。
- 按 CSS 规则：`!important` 永远赢非 `!important` → **渐变规则在 CSS 层面必赢，代码正确**。
- 结论：用户看到的"未生效"是**远端部署的旧镜像未更新**，不含本次构建。需在远端重新构建并部署前端镜像（`btdeck-frontend`）。

### 问题2（PageSizeCombobox 下拉被遮挡）—— teleport + 自动方向彻底解决
经子代理深入设计，采用"手动 teleport 到 body + position:fixed + 自动方向判断"方案（Element el-select 同路，更轻量无新依赖）：

**`PageSizeCombobox.vue`**：新增 `appendToBody` prop（默认 false，零回归）。开启后：
- `@Watch('expanded')` 展开时把 `<ul>` 用原生 `appendChild` 挪到 `document.body`（手动 portal，Vue2 无 `<teleport>`）；
- `measureAndPlace()` 用 `getBoundingClientRect` 判断下方空间，自动向上/向下展开；`position:fixed` 绕开所有父级 stacking context 与 overflow 裁剪；
- `window scroll`(capture=true，捕获祖先滚动) / `resize` 监听重定位；`beforeDestroy` 把节点挪回原父级再卸载（避免 Vue patch 报错）+ 移除监听 + 取消 RAF（防泄漏）。
- 测量用 `top:-9999px` 移出视口避免定位闪烁。

**`index.scss`**：把 `.page-size-options` 从 `.page-size-combobox` 后代选择器**提升为顶层独立规则**（teleport 后脱离父级，后代选择器失效）；新增 `.page-size-options--floating{position:fixed!important;z-index:var(--z-index-dropdown,1000)}`（1000：高于面板 30、低于 el-loading-mask 2000 与 modal 1050）。

**调用点**：孤儿页/种子列表/TraditionalView 三处 `<PageSizeCombobox>` 加 `append-to-body`。

### 验证
- 前端 lint 无错误；`npm run build` 成功；产物确认含顶层 `.page-size-options` + `.page-size-options--floating{position:fixed!important...}`。
- 孤儿页单元测试 16 passed（组件改动未破坏现有功能）。
- 确认全项目无其它 `.page-size-options` 级联覆盖（回归检查）。

**最后更新**: 2026-08-01

---

### 2026-08-01：隔离区删除失败二次修复与部署包核验

#### 二次根因确认

- 当前源码中的物理删除流程已经不再生成“隔离区路径未授权或身份字段不完整，拒绝删除”这条旧错误；该文案仍存在于工作区的 `btdeck-backend.latest.tar` 二进制镜像中。
- 源码最后修改时间晚于该 tar 的导出时间，说明此前重新部署实际可能加载了旧后端镜像包，不能据此判断本次源码修复未生效。
- 旧版隔离记录还可能缺少 `mtime_ns/device_id/inode`，会被新安全门禁拒绝；已增加仅基于已记录隔离路径的兼容补齐，已有字段不匹配仍 fail-closed。

#### 本轮修复

- `purge_quarantine_now`、自动到期 purge、`purge_pending` 恢复统一只从持久化 `quarantine_path` 取得物理目标，并以 `quarantine_root` 做绝对路径/符号链接/根目录边界校验；不再用下载器路径映射寻找隔离文件。
- 实时 manifest 仅可选地复核原始 `canonical_path` 是否重新被种子引用，不参与隔离路径授权或物理路径解析。
- 失败通知同时展示原路径与实际隔离路径，便于确认删除对象；兼容旧记录补齐身份字段后再执行同样的 size/mtime/inode 复核。
- 新增重复前缀路径和旧身份字段缺失回归测试。

#### 验证与部署边界

- 后端隔离安全：`40 passed, 1 skipped`；隔离安全、manifest、API、异步任务、忽视态和扫描任务选定回归：`126 passed, 1 skipped`。
- 目标后端 Flake8 通过，Black diff 无变更，`git diff --check` 通过。
- 前端 `typecheck`、`lint`、单元测试和生产构建均通过。
- 后端全量本轮为 `2511 passed, 6 skipped, 5 failed`；5 个失败集中在孤儿维护 lease/任务测试的全量顺序污染，相关孤儿服务按独立及选定顺序回归通过，未将其误报为本轮删除逻辑通过。
- 当前 Docker engine 不可用，未重新导出镜像、未提交、未推送、未部署。部署前必须重新构建并导出后端 tar，不能继续加载现有旧 tar；根 `bash ./init.sh` 仍受 Windows WSL `E_ACCESSDENIED` 阻断。

---

### 2026-08-01：隔离区彻底删除路径映射误用修复

#### 根因确认

隔离文件已经从原位置移动到 `.btdeck_quarantine`，但彻底删除前的授权检查仍用原始 `canonical_path` 对当前下载器 manifest 的扫描根做路径授权。下载器内部路径经映射后出现 `/Downloads/ipan/Downloads/...` 重复前缀，或映射配置发生变化时，物理文件其实仍在隔离区，却被误报为“路径未授权或身份字段不完整”。这不是删除动作本身找不到隔离文件，而是把原始下载路径错误地重新用于隔离文件删除授权。

#### 修复

- 自动到期删除、手动异步删除、`purge_pending` 崩溃恢复统一以候选记录的 `quarantine_path` + `quarantine_root` 作为物理删除对象和范围边界。
- 下载器实时 manifest 仅用于确认清单完整、原位置/隔离路径未被重新引用，不再通过下载器路径映射定位隔离文件。
- 保留身份字段（size/mtime/inode）、隔离根逃逸、tombstone、TOCTOU 和维护 lease 等 fail-closed 安全门禁。
- 新增重复前缀回归：原始路径不再被当前 mapping scan root 覆盖，但隔离路径有效时，仍只删除 `.btdeck_quarantine` 中登记的文件。

#### 验证

- 隔离安全回归：35 passed / 1 skipped。
- manifest、孤儿 API、异步任务回归：49 passed。
- 后端全量：2515 passed / 6 skipped。
- 目标代码 Black 行范围与 Flake8 通过；全量 mypy 仍存在既有 SQLAlchemy Column 类型债务。

本轮未提交、未推送、未实际部署；根 `bash ./init.sh` 仍受当前 Windows WSL `E_ACCESSDENIED` 阻断。

---

### 隔离区页签刷新 formatFileSize 报错修复（2026-08-01）

#### 问题定位

- 最近一次提交 `50f4c9b` 仅更新交付记录；实际隔离区前端实现来自 `9891b84`。
- `frontend/src/views/orphan-files/index.vue` 的隔离区大小列调用 `formatFileSize(row.file_size)`，但 Vue 2 class-style 组件实例仅暴露已有的 `formatSize()` 方法，导致隔离区表格渲染时报 `TypeError: e.formatFileSize is not a function`。

#### 修复与验证

- 大小列改为调用组件方法 `formatSize()`，继续复用 `@/utils/formatters` 的实现。
- 新增隔离区刷新/渲染回归测试，覆盖 scoped slot 不再触发渲染异常。
- `npm.cmd run test:unit -- orphan-files.spec.ts`：17 passed。
- 同步提交 `9891b84` 已交付的 cleanup 300000ms 超时契约断言，前端全量 Jest：27 suites / 405 tests passed。
- `npm.cmd run typecheck`、`npm.cmd run lint`、`npm.cmd run build`：通过；生产构建仅保留既有 Sass/Element UI 弃用警告。
- 根 `bash ./init.sh --ci` 受当前 Windows 沙箱 `C:\Windows\System32\bash.exe` 的 `E_ACCESSDENIED` 阻断，脚本未实际开始执行；前端等价验证已完成。

**最后更新**: 2026-08-01

---

## 2026-07-31 - 手动清理放行低置信度孤儿（自动清理仍排除）

**需求**：低置信度（low confidence，离线降级目录粗筛产出）孤儿文件，用户可在前端警告确认后主动手动清理；但自动清理（定时任务）仍排除 low，保留安全限制。

**诊断结论**（对 E:\Users\huangzj\Desktop\app.db 实测）：用户报告的 id 203494/203495/203496 scan_id 匹配、未忽视、未清理，**根因是三者均为 low confidence**（归属 tr 下载器，扫描时离线降级），被 cleanup_preview 的 `confidence=="high"` 硬过滤 → 返回空。

### 改动（前后端协同，保留全部安全底线）

**后端**（`app/services/orphan_file_service.py`）：
- `cleanup_preview`（手动预览）：移除 SQL 的 `confidence == "high"` 过滤，放行 low；响应新增 `low_confidence_count` 供前端警告。
- `cleanup_orphans`（手动清理）：移除循环内 confidence 拒绝（原 `:692-702`）。
- **安全底线全部保留**：实时 manifest 复核（`expected_paths` 文件被引用则拒、`_path_authorized` 下载器授权、`verify_file_identity` 身份复核）、忽视态保护、lease。即 low 文件仍需通过这些复核才能删（下载器离线时仍会被拒，属正确安全行为）。
- **自动清理路径不变**：`get_purgeable_candidates`（`orphan_lifecycle_service.py:173`）仍 `confidence == "high"`，定时任务不删 low。

**前端**：
- `orphan-files.ts`：`CleanupPreviewSuccess` 增 `low_confidence_count?: number`。
- `index.vue`：preview 弹窗当 `low_confidence_count > 0` 时显示红色 error 警告（误判风险提示）；置信度列"低"标签 tooltip 文案改为"手动清理可删，自动清理需等下载器上线精筛"（消除与原"需等上线才可清理"的矛盾）。

**测试**（`tests/services/test_orphan_cleanup_safety.py`）：
- `test_cleanup_rejects_low_confidence_candidate` → 重写为 `test_cleanup_allows_low_confidence_when_manifest_authorizes`：补全候选身份字段 + mock lease，断言 low 在 manifest 授权时被放行清理（success_count=1、无"低置信度"拒绝、文件已隔离）。

### 验证
- 后端 flake8 干净；pytest **52 passed, 1 skipped**（含新的手动放行测试 + 自动清理忽略安全测试，验证自动路径仍正常）。
- `get_purgeable_candidates` 源码确认仍含 `confidence=="high"`（自动清理安全限制保持）。
- 前端 lint 无错误；`npm run build` 成功。

**最后更新**: 2026-07-31

---

## 2026-07-31 - 孤儿文件页面 4 个问题修复（经 3 轮子代理独立审查重订）

**任务**: 修复用户报告的 4 个问题：①表头渐变未生效；②PageSizeCombobox 下拉被列表遮挡；③cleanup-preview 返回空；④cleanup 请求超时。

**过程**：初版计划经 3 份子代理独立审查，**有力推翻了多处核心假设**，重订为更精准、更小改动方案。

### 审查推翻的关键（诚实记录）
- 审查1 推翻"confidence 不一致是 preview 空的根因"——用户报告 code=200（非 500）证明 SQL 正常执行，根因在数据层（low confidence / scan_id 不匹配 / 被忽视），需诊断脚本定位，而非盲改 cleanup SQL（那会破坏 `test_cleanup_rejects_low_confidence_candidate:955` 并丢失逐项诊断能力）。
- 审查2 确认 gather 受 `Semaphore(2)` 钳制，理论加速仅 2x，治本需 manifest 缓存/异步化；并纠正"手动 cleanup per-candidate 反复重建 manifest"实为 purge 路径（`:1159/:1221`），手动 cleanup 只在 `:646` 建 1 次。
- 审查3 推翻"改 overflow+z-index"方案（漏 `.management-table-scroll` 第三道裁剪 + z-index 撞 `el-loading-mask`），改用更优的"下拉向下展开"。

### 改动

**问题1（表头渐变）**：`management-list-page.scss` 表头规则加 `!important`（单层，采纳审查3；放弃双层 tr+th）。

**问题2（下拉遮挡）**：`index.scss` 把 `.page-size-options` 从 `bottom` 改 `top`（向下展开，pagination 是 panel 末尾子元素，下方空白）；`PageSizeCombobox.vue` toggle 图标方向同步反转。

**问题3（preview 空）**：
- 交付只读诊断脚本 `backend/scripts/diagnose_orphan_cleanup.py`（在远端库运行，输出指定 orphan_id 的 scan_id 匹配/confidence/is_deleted/is_ignored/canonical_path 列存在性/alembic 版本，定位 0 行匹配的数据原因）。
- 前端 `handleCleanupPreview`：preview 返回 `total_count===0` 时给出针对性提示（低置信度/已忽视/已清理），不再静默空弹窗。
- **不改** cleanup 的 confidence SQL（保持循环内判断作为正确防御纵深）。

**问题4（cleanup 超时）**：
- 前端 `cleanupOrphans` 单独设 `timeout:120000`（标注临时，解除 20s 硬超时）。
- 后端 `_build_precise_expected`（`orphan_manifest.py`）串行 `for torrent` 改为有界并发 gather（严格按审查2）：worker 只返回纯数据元组不写共享状态、`_seed_degrade` 闭包重构为返回值由主协程串行汇合、`return_exceptions=True` + 显式 `isinstance(result, ManifestBuildError)` 复现降级、operation 统一。顺带修掉既有的 `nonlocal seed_degraded` mypy 错误。

### 验证
- 后端 flake8 干净；`orphan_manifest.py` mypy **Success no issues**（修掉既有 nonlocal 错误）。
- 后端 pytest：manifest+cleanup+ignore+query 共 **62 passed, 1 skipped**（含 manifest 改造的 21 个核心回归全过）。
- 前端 lint 无错误；`npm run build` 成功。
- 诊断脚本本机空库 dry-run 正常输出。

### 诚实边界（治本待办，列后续专项）
- **manifest TTL 缓存**：purge 路径 per-candidate 反复重建（`:1159/:1221`）受益最大，独立架构改动。
- **cleanup 异步化**：复用 `orphan_maintenance_scope` lease（TTL=3600s）+ 前端轮询，彻底摆脱 HTTP timeout。是架构正解。
- **DOWNLOADER_IO_CONCURRENCY 调优**：真正的并发杠杆，但跨 SYNC lane 共享，需独立评估下载器承载。
- 大下载器（数千种子）cleanup 仍可能超时，本次仅 2x 缓解。

**最后更新**: 2026-07-31

---

## 2026-07-31 - 孤儿文件页面 UI 对齐种子列表 + 被忽视沉底排序

**任务 ID**: `orphan-files-management-enhancement`（UI 对齐 + 排序增强）

**需求**:
1. 列表列头颜色/样式与种子列表的列表模式保持一致。
2. 页面大小选择控件复用种子列表的页面大小选择控件。
3. 被忽视的孤儿文件排序优先级到最后，待清理数据排列在前（需后端配合）。

**决策点（已与用户确认）**:
- 列头：完全复刻种子列表列表模式细节（padding/大写/字号/sticky）。
- 样式范围：改共享样式 `management-list-page.scss`，所有管理类页面表头一并统一。
- 分页：完整替换为种子列表同款（PageSizeCombobox + 自定义翻页按钮 + 文字汇总），弃用 el-pagination。

**改动**:

### 后端：排序下推 is_ignored（`backend/app/services/orphan_file_service.py`）
- `get_orphan_list` 的 `list_query.order_by` 原为硬编码 `file_size DESC, id ASC`，完全不感知忽视态。
- 新增 `ignored_rank` 排序键：以 `OrphanFile.canonical_path IN (候选表 is_ignored=True 子查询)` 构造 `case(…, else_=0)`，生成 0（非忽视，靠前）/1（已忽视，沉底）。
- 最终排序：`ignored_rank.asc(), file_size.desc(), id.asc()`。零前端入参侵入（不暴露 sort_by/order 参数）。
- 效果：`status=None`（混合待清理+已忽视）时待清理自然靠前、已忽视沉底；单状态筛选（pending/ignored/deleted）不受影响。

### 前端样式：表头全局统一（`frontend/src/styles/management-list-page.scss`）
- `.management-table` 表头规则对齐 `torrent-theme.scss` 列表模式细节：padding `10px 12px`、`text-transform: uppercase`、`font-size: 12px`、`letter-spacing: 0.5px`。
- 新增 `.el-table__header-wrapper { position: sticky; top:0; z-index:10 }` 列表滚动吸顶。
- 所有复用 `.management-table` 的管理页（回收站/审计日志/定时任务等）一并统一。

### 前端分页：复用 PageSizeCombobox（`frontend/src/views/orphan-files/index.vue`）
- 弃用 `<el-pagination>`，改用 `<nav class="torrent-pagination management-pagination">`：PageSizeCombobox（controlsId=orphan-page-size-options）+ 自定义翻页按钮（LucideIcon chevron-left/right）+ 文字汇总「共 X 条，第 Y/Z 页」。
- 新增状态机 `pageSizeInput/pageSizeDropdownExpanded/pageSizeOptions=[20,50,100]`、计算属性 `totalPages/visiblePages`、方法 `handlePageSizeSelect/Focus/Blur/togglePageSizeDropdown/applyPageSizeSelection/handlePageChange`（参照 `views/torrents/index.vue` 与 `utils/traditionalPagination.ts`）。
- scoped 样式内写自包含分页样式（翻页按钮主题色 hover/active），不污染也不依赖 torrent-theme.scss 全局引入。

**验证**:
- 后端：`pytest tests/services/test_orphan_ignore_and_filters.py` 13 passed（含 2 个新增排序回归：混合态沉底 `test_list_orders_ignored_last_within_mixed_status`、纯 pending 不受干扰 `test_list_orders_pure_pending_unchanged`）；orphan 专项全量 203 passed/1 skipped。
- 后端 flake8 通过；mypy 报告的 86 个错误全部是既有 SQLAlchemy Column 类型债（1541-1574 行），与本次改动（325 行 order_by）无关（git stash 验证前后错误数一致）。
- 前端：`vue-cli-service lint` 无错误；`npm run build` 成功（orphan-files chunk 正常打包）。

**诚实边界（未做）**:
- 未给孤儿列表增加可点击的列头排序（用户未要求，本次仅按"忽视态沉底"固定排序）。
- 后端既有 mypy 类型债未在本任务处理（超出范围）。

**最后更新**: 2026-07-31

---

## 2026-07-31 - 孤儿文件自动清理忽视态边界回归与防御纵深加固

**任务 ID**: `orphan-files-management-enhancement`（回归补丁）
**分支**: dev
**范围**: 为本次孤儿文件增强生成回归测试，重点保证「被忽视的孤儿文件在任何情况下都不被定时自动清理任务删除/隔离」——100% 边界覆盖。

### 关键发现与加固（独立审查暴露的防御纵深缺口）

- 审查发现：`cleanup_orphans`（手动清理）循环内有 `is_ignored` 守卫（`:687`），但 **`auto_cleanup_expired`（定时自动清理）循环内没有**——它完全依赖 `get_purgeable_candidates` 的 SQL `is_ignored==False` 子句。这意味着若 SQL 子句被误删/旁路，被忽视文件会被静默隔离。这是数据安全底线的单点失效。
- **加固**：给 `auto_cleanup_expired` 循环开头加 `is_ignored` 守卫（与手动清理对称），成为第二道防线。
- **变异测试验证有效性**：临时删除该守卫后，`test_injected_ignored_candidate_blocked_in_loop` 立即失败（被忽视候选被隔离）；恢复后通过——证明测试真正守住底线。

### 三层防御纵深回归测试（test_orphan_auto_cleanup_ignore_safety.py，11 用例）

| 层 | 测试 | 断言 |
|---|---|---|
| SQL 过滤层 | `get_purgeable_candidates` 排除/全部忽视/取消忽视后恢复可清理 | is_ignored 候选不入可清理集 |
| 服务 E2E 层 | `auto_cleanup_expired` 端到端：单忽视候选不隔离+文件保留；混合批次只清理非忽视；全忽视走空分支 | quarantined_count==0、文件 exists()、候选 status 不变 |
| 防御纵深层 | 绕过 SQL（直接注入已忽视候选到工作集），循环守卫仍拒绝隔离 | failed_count==1、文件保留、status 不变 |
| 生命周期 | resolved→candidate 重新出现重置 is_ignored（不粘住）；持续孤儿保留忽视标记 | is_ignored 重置为 False / 保留 True |
| purge 任务 | `purge_expired_quarantine` 不误伤已忽视候选（始终 candidate 态，永不 quarantined） | purged_count==0、文件保留 |
| 手动清理 | `cleanup_orphans` 循环守卫拒绝已忽视项（补齐与 preview 对称的 E2E） | failed_list 含「忽视」原因、文件保留 |

### 回归与检查

| 验证项 | 结果 |
|---|---|
| 新增测试（11） | ✅ 全过 |
| 变异测试（删守卫→失败） | ✅ 证明测试有效 |
| 孤儿专项回归 | ✅ 203 passed / 1 skipped（原 192 + 新 11） |
| 全量后端 | ✅ 2472 passed / 6 skipped |
| flake8 + black | ✅ 干净 |

---

## 2026-07-31 - 孤儿文件管理增强（别名/置信度/忽视/多条件搜索）

**任务 ID**: `orphan-files-management-enhancement`
**分支**: dev
**范围**: 孤儿文件列表四项增强——①日志/界面显示下载器所属时使用别名（nickname）；②列表增加置信度显示列；③增加忽视功能（被忽视的孤儿受保护，定时任务不自动删除、手动清理也拒绝，但仍可查询）；④增加路径/下载器/状态多条件搜索与分页。

### 关键设计（经 3 轮子代理独立代码审查修订）

- **status=ignored 联表的阻断性技术问题**：审查发现 `normalize_path`（normcase+normpath+abspath）是 Python 函数无法下推 SQL，原"联表候选 is_ignored"在分页查询层不可表达。修订为给 `orphan_file` 明细表加冗余列 `canonical_path`（落库时已可得，`orphan_scanner._finalize_successful_scan` 直接复用 `_normalize_path(o.file_path)`）+ 索引，使 status=ignored 变成纯 SQL 的 `WHERE canonical_path IN (SELECT ... WHERE is_ignored=1)`。
- **忽视态存储**：存 `OrphanCurrentCandidate`（按 canonical_path 跨扫描持久），不存每次扫描重建的 `OrphanFile` 明细。
- **忽视态跨扫描语义**：`reconcile_candidates` 的 resolved→candidate 分支重置 is_ignored，避免忽视标记永久"粘住"曾被种子引用后又重新成为孤儿的文件。
- **别名**：复用 `BtDownloaders.nickname`（与 recycle-bin/torrents 一致），零下载器表迁移；后端批量 JOIN 注入 `downloader_name`，nickname 为空回退掩码 ID。
- **清理门禁**：忽视=保护态，手动（cleanup_preview/cleanup_orphans）+ 自动（get_purgeable_candidates）双重拒绝已忽视项。
- **前端交互**：采用统一选中矩阵（pending+ignored 均可勾、deleted 禁勾，按选中主导状态动态启停批量按钮，混选禁用），弃用原计划中自相矛盾的"禁勾+预拦截"。

### 落地清单

- 迁移 `a1b2c3d4e5f6`（down_revision `f2a7c91b4d6e`，单 head 无分叉，【可回滚】，纯加列+索引+存量回填）。
- 后端：模型加列（OrphanFile.canonical_path；OrphanCurrentCandidate.is_ignored/ignored_at/ignored_by）；扫描器填 canonical_path；`get_orphan_list` 加 status/path_like 参数 + `_enrich_items`（别名+忽视态批量注入）；`set_ignored`（db_write_scope + 候选 candidate/stable 状态校验 + 独立 session 审计 ORPHAN_IGNORE）；清理三处门禁；`POST /orphan-files/ignore` 端点。
- 前端：类型扩展（OrphanFileItem/OrphanListParams/OrphanScanContext + setIgnored）；视图别名列、置信度列、忽视操作、多条件搜索、已忽视统计卡。

### 回归与检查

| 验证项 | 结果 |
|---|---|
| alembic heads | ✅ 单 head `a1b2c3d4e5f6`（无分叉） |
| 迁移 upgrade/downgrade | ✅ 可逆，空库建 28 表，回填幂等 |
| 新增后端测试（11） | ✅ status 过滤/path_like 转义/别名/置信度/set_ignored/cleanup_preview 拒绝 |
| 孤儿专项回归 | ✅ 192 passed / 1 skipped |
| 全量后端 | ✅ 2461 passed / 6 skipped |
| 后端 black + flake8 | ✅ 干净 |
| 前端 typecheck / eslint / build | ✅ 干净 |
| 前端 Jest（全量） | ✅ 24 suites / 352 tests |
| 前端 orphan-files.spec（新增 4 用例） | ✅ 16 passed |
| 根 init.sh | ✅ 退出 0，无 error/warn |

## 2026-07-30 - 孤儿白名单阶段映射缺失 fail-closed 修复

**任务 ID**: `orphan-scan-path-scope-mapping-fix`（白名单 fail-closed 强化）
**分支**: dev
**范围**: 孤儿白名单构建（`TorrentManifestBuilder.build()`）中种子 `save_path` 缺映射时，由 fail-open（continue + warning，会误判孤儿）改为 fail-closed（整批失败）。作用域按「下载器粒度」限定，既消除误判又不波及作用域外下载器。

### 背景（独立审查发现的关键问题）

- 原始修复计划曾提议全局 fail-closed，经独立子代理审查发现两个严重问题：
  1. **清理路径爆炸半径跨下载器**：`build()` 内层循环遍历全部启用下载器，`required_downloader_ids` 仅校验存在性、不限定遍历。清理下载器 A 的候选时，无关下载器 B 缺映射会拒绝整个清理。
  2. **破坏性变更**：全局 fail-closed 会让依赖「映射缺失跳过」才能完成的用户每次定时扫描都失败。
- 用户决策：①清理路径限定范围（A 不受 B 影响）；②不接受破坏性变更。两者统一为「fail-closed 只作用于本次构建作用域内的下载器」。

### 根因与修复

- 白名单阶段映射缺失 continue → 该种子文件不进白名单；若其文件物理落在其它扫描根子树下 → 误判孤儿 → 可能被清理物理删除。
- 修复：`build()` 内层循环 `resolve_external_path(save_path)` 返回 None 时 `raise ManifestBuildError`，错误消息含 downloader_id / torrent_hash[:8] / save_path 定位信息。
- **作用域限定**（同时满足两个决策）：
  - `build()` 新增 `scoped_configs`：`required_downloader_ids` 非空时只遍历这些下载器；None/空集合时遍历全部（保持扫描全量语义与既有行为不变）。
  - 扫描路径 `_build_torrent_file_map` 传「扫描根涉及的下载器集合」（从 `scan_path_selection.scan_roots` 第二列提取）：仅对正在被扫描的下载器做映射完整性 fail-closed；作用域外下载器（路径不落任何扫描根）不受影响。
  - 清理路径 8 处调用已传候选 `required_downloader_ids` → 改后真正限定遍历，A 的清理不受 B 影响。
- `ManifestSnapshot.warnings` 字段保留：collect 阶段（扫描根缺映射）warning 仍透传，build 成功时 `_build_torrent_file_map` 照常写入 `self._scan_warnings`；失败路径定位信息在 error 消息。
- 不新增数据库结构、不修改路径映射配置；被误判的 `candidate` 在下次完整扫描自动 `resolve` 移出活跃列表（沿用现有生命周期语义）。

### 条件性破坏说明（Release Note）

本次变更为条件性破坏：仅当「扫描根涉及的下载器（其路径已配映射并成为扫描根）的 inventory 中存在另一个未配映射的 save_path」时扫描才失败——这正是要阻断的误判场景，属预期行为。刚添加、未配映射且路径不在任何扫描根下的下载器不受影响。引导用户在扫描根涉及的下载器上补全所有 save_path 映射。

### 回归与检查

| 验证项 | 结果 |
|---|---|
| orphan 专项回归（8 文件） | ✅ 134 passed / 1 skipped |
| mypy（orphan_manifest.py + orphan_scanner.py） | ✅ 通过 |
| flake8（改动文件） | ✅ 通过 |
| Black 基线 | ⚠️ 改动前同文件即 non-compliant（历史遗留），本次未扩大无关格式化范围 |
| 新增测试 | 1 重写（fail_closed）+ 4 新增（作用域隔离/全局fail/warning透传/端到端穿透） |

### 交付边界

- 没有新增数据库表、字段或 Alembic 迁移；不改 API 返回结构（仍为 `data.status=failed + error + warnings`）。
- 不修改任何下载器路径映射配置；映射不完整由 error 消息引导用户在下载器设置中处理。
- 仅改 `orphan_manifest.py` / `orphan_scanner.py` 两个源文件 + 两个测试文件。

---

## 2026-07-30 - 孤儿扫描空 external 映射绕过严格校验修复

**任务 ID**: `orphan-scan-path-scope-mapping-fix`（回归补丁）
**分支**: dev
**范围**: `resolve_external_path` 前缀初筛只认 `internal`/`source`，未要求 `external`/`target` 非空，导致系统自动发现后未回填 external 的映射（tr/tr_lpan/tr_kpan 全空）让下载器内部绝对路径原样通过、被选成扫描根，最终在 `_walk_all_roots` 触发 fail-closed 把整批扫描标为 failed。

### 根因与修复

- `PathMappingService.internal_to_external` 对 `external=""` 的映射逐条跳过 → 无 best_match → 原样返回输入路径（如 `/Downloads/bangumi/`）。
- 旧 `resolve_external_path` 仅校验「前缀命中 + os.path.isabs」：原样返回的内部绝对路径两项都过 → 误判为有效映射 → 选成扫描根。
- 修复：前缀初筛只纳入带有效 `external`/`target` 的显式映射，external 全空时不再命中 → 返回 None → 走既有 `path_mapping_not_found` 软跳过，与上一版「映射缺失」语义对齐；不再误伤 `internal==external` 的合法恒等映射。
- 不新增数据库结构、不修改任何下载器路径映射配置；历史 failed 扫描批次保留不动。

### 回归与检查

| 验证项 | 结果 |
|---|---|
| orphan 专项回归 | ✅ 70 passed |
| Ruff / Flake8 / py_compile | ✅ 通过 |
| `scripts/lint_btdeck.py` | ✅ 无阻塞 |
| 真实 app.db 复跑 | ✅ `/Downloads/bangumi*` 返回 None，`external=/mnt/bangumi` 正例仍解析 |

---

## 2026-07-30 - 孤儿扫描有效路径筛选与严格映射修复

**任务 ID**: `orphan-scan-path-scope-mapping-fix`
**分支**: dev
**范围**: 孤儿扫描根筛选、下载器路径映射、manifest/生命周期安全范围、任务提醒及回归；不新增数据库结构，不修改或自动补全路径映射。

### 根因与修复

- 原扫描根 SQL 只过滤 `torrent_info.dr=0`，没有过滤种子 `enabled/deleted_at`，也没有联结过滤下载器 `enabled/dr`；下载器 `path_mapping` 中每个 external 根还会被无条件加入，导致已删除或停用数据重新进入扫描范围。
- `UnifiedPathMappingService` 未命中规则时会返回原路径；旧扫描器因此可能把下载器内部绝对路径误认为 BtDeck 可访问路径。现在必须命中显式 JSON 映射或规则，并校验转换结果为本机绝对路径。
- 扫描根改为仅来自启用、未删除的种子与下载器，并尊重 `downloader_path_maintenance.is_enabled`；配置中的 external 根不再绕过有效数据筛选。
- 找不到映射时生成 `path_mapping_not_found` 结构化提醒并跳过该路径，不中断其他目录；即使全部路径均未映射，任务仍以 `completed` 返回零扫描根、`total_paths_skipped` 与 `warnings`，提醒用户自行补全映射，本任务不会修复配置。
- manifest 只把成功筛选并映射的目录作为扫描/清理授权根；生命周期对账新增成功扫描根范围，空范围或被跳过目录下的历史候选不会被误标为 `resolved`。
- 扫描触发审计记录保留扫描/跳过数量及 warnings；定时任务结果与完成日志追加映射不完整提醒。

### 回归与检查

| 验证项 | 结果 |
|---|---|
| 全部 orphan 回归 | ✅ 133 passed / 1 skipped |
| 后端全量 pytest | ✅ 2406 passed / 6 skipped |
| Ruff / Flake8 / py_compile / BtDeck 架构检查 | ✅ 通过 |
| 目标 mypy | ✅ `orphan_manifest.py` 与 `orphan_scan_task.py` 通过；组合检查仅剩既有 SQLAlchemy Column 类型债 |
| `git diff --check` / 根 `init.sh --ci` | ✅ 通过 |
| Black 基线对比 | ⚠️ HEAD 与当前版本的同组 9 文件均会被现有 Black 配置重排，未扩大无关格式化范围 |

### 交付边界

- 没有新增数据库表、字段或 Alembic 迁移；warnings 仅进入本次扫描响应、审计详情、定时任务结果和运行日志。
- 不新增、删除或修改任何下载器路径映射；路径映射不完整由提醒引导用户在下载器设置中处理。
- 会话开始前已有的路径映射真实目录验证改动均未覆盖；路线图仅同步本轮孤儿模块条目，工具目录、镜像归档与批处理文件保持不动。

---

## 2026-07-30 - 下载器路径映射真实目录验证修复

**任务 ID**: `v1.0.6.32`
**分支**: dev
**范围**: 下载器路径映射验证 API、缓存客户端探测服务、前端响应类型与回归测试；不修改保存逻辑、数据库 Schema 或 Alembic 迁移。

### 根因与修复

- 旧 `/downloader/{downloader_id}/path-mapping/test` 只做 Pydantic、必填字段、重复 internal 路径和标准化检查，完全没有访问 internal/external 目录，因此格式合法的错误路径必然返回“配置验证通过”。
- 新增逐映射真实目录验证：external 在 BtDeck 运行环境中执行 5 秒有界 `stat`、目录类型和读写权限检查；internal 严格复用 `app.state.store` 缓存客户端，经 `call_downloader_api(INTERACTIVE)` 探测，未创建第二套下载器连接。
- Transmission 使用 `free_space(path)` 验证任意内部目录；qBittorrent 没有等价的任意路径只读探测，改用默认保存路径 + `free_space_on_disk` 或状态可用的现有种子保存路径作为存在性证据，无法取证时 fail-closed。
- 响应新增 `downloader_available`、`internal_paths_valid`、`external_paths_valid` 与逐条 `path_checks`；任一映射任一侧失败即整体失败，错误列表带映射名称、路径侧和原因。前端 API/响应类型同步收紧，既有错误详情区域直接展示这些原因。
- 空映射配置现在失败；internal 冲突在标准化后判断，避免不同分隔符表达绕过重复检查。

### 回归与检查

| 验证项 | 结果 |
|---|---|
| 新增路径映射回归 | ✅ 10 passed；旧实现对同组测试暴露 5 failed |
| 受影响下载器 API 回归 | ✅ 47 passed |
| 后端全量 pytest | ✅ 2403 passed / 6 skipped |
| 前端全量 Jest | ✅ 24 suites / 348 tests |
| Ruff / Flake8 / py_compile / 新增 service/schema 目标 mypy | ✅ 通过；`downloader.py` 的 18 条报告为既有类型债务，未落在修改行 |
| `npm run lint` / typecheck / production build | ✅ 通过；build 保留既有 48 条 Sass/资源体积 warning |
| 根 `init.sh` | ✅ 使用 Git Bash 执行，退出码 0 |
| Black | ✅ 新增 Python 文件已用单 worker 格式化，formatter 复核均为 `NothingChanged`；⚠️ Windows 下 CLI 完成后进程退出仍会挂起 |

### 交付边界

- qBittorrent 对未作为默认路径、且当前没有可用种子引用的目录会返回“无法确认目录存在”，这是 API 能力限制下的保守失败，不会再把未经验证的目录判为成功。
- 本轮按用户要求仅提交本任务文件，未执行 push；会话开始前已有的未跟踪工具目录、镜像归档与批处理文件保持不动。

---

## 2026-07-30 - 孤儿扫描 Transmission Torrent 文件清单解析修复

**任务 ID**: `orphan-transmission-torrent-files-fix`
**分支**: dev
**范围**: 后端解析与回归测试；不修改 API、数据库 Schema、Alembic 迁移或前端。

### 根因与修复

- `transmission-rpc 7.0.11` 的 `Torrent` 是字段容器而不是文件集合：对象本身不可迭代，也没有稳定的 `.files` 属性；原始文件清单位于 `Torrent.fields["files"]`，并可通过 `Torrent.get("files")` 读取。
- 共享 `TorrentManifestBuilder` 先用 `.files` 判断库存是否内嵌文件，因而漏判真实 `Torrent`；详情查询随后返回单个 `Torrent`，旧提取逻辑把该对象当作文件集合执行迭代，最终抛出 `'Torrent' object is not iterable`。
- 新增统一原始文件提取逻辑，按字典、`get("files")`、`fields["files"]`、兼容 `.files` 的顺序识别；库存已携带文件时直接解析，避免不必要的逐种子详情查询，缺失时仍回退 `get_torrent`。
- 文件集合支持列表、元组、生成器和按文件编号映射的字典；字符串、单个 Torrent 或其他不可迭代错误形态改为抛出包含下载器与种子上下文的 `ManifestBuildError`。
- 旧 `OrphanScanner` 的 Transmission 解析入口复用共享提取逻辑，避免两套实现再次漂移。

### 回归与检查

| 验证项 | 结果 |
|---|---|
| manifest + scanner 专项 | ✅ 46 passed |
| 全部 orphan 相关测试 | ✅ 130 passed / 1 skipped |
| 后端全量 pytest | ✅ 2393 passed / 6 skipped |
| Flake8 / Ruff / py_compile / `git diff --check` | ✅ 通过 |
| 目标 mypy | ⚠️ 3 条既有 SQLAlchemy `Column` 类型错误，均不在本次修改行 |
| Black 基线对比 | ⚠️ HEAD 与当前版本的同一批目标文件均会被现有 Black 版本重排；未扩大无关格式化差异 |
| 根 `init.sh` | ⚠️ 当前 Windows 环境启动 WSL 返回 `E_ACCESSDENIED`，未能执行 |

### 交付边界

- 回归测试使用真实 `transmission_rpc.Torrent`，覆盖库存内嵌文件、详情查询回退、单 Torrent 错误库存三条路径；不再依赖会掩盖 SDK 结构差异的 `SimpleNamespace(files=...)`。
- 本轮未执行 Git stage、commit 或 push；会话开始前已有的未跟踪工具目录、镜像归档与批处理文件保持不动。

---

## 2026-07-30 - 孤儿文件扫描、统计与刷新状态一致性修复

**任务 ID**: `orphan-files-state-consistency-fix`
**分支**: dev
**范围**: 前后端与回归测试；不修改数据库结构，不新增 Alembic 迁移。

### 修复结果

- 最近扫描失败时，分页接口同时返回 `latest_attempt` 与最近成功的 `display_scan`；页面只读展示后者的剩余结果和失败原因，预览与清理继续由最新扫描门禁拒绝。
- 最近扫描仍为 `running` 时保持空列表、零统计、`display_scan=null`，不回退旧成功批次，清理不可用。
- 顶部数量和空间改为服务端聚合展示批次中 `is_deleted=false` 的全量剩余值；下载器/大小筛选和分页不改变该聚合，扫描批次原始发现量保持审计快照不变。
- `/orphan-files/list` 的同一响应统一携带分页列表、扫描上下文、剩余统计和清理门禁；前端首次加载、顶部刷新、筛选、翻页、扫描后刷新及清理后刷新均收敛到同一入口。
- 前端刷新复制并冻结查询快照，使用递增请求序号丢弃过期成功/失败响应；仅最新成功响应更新列表、统计和上下文并清空选择，超出末页最多修正一次。
- 清理候选先在 `db_write_scope` 中提交 pending，再执行文件移动、复核 lease，最后将候选稳定化与对应 `OrphanFile` 明细标记放入同一事务；失败显式回滚并由后续恢复流程继续处理。
- 中断恢复一次构建覆盖全部 pending 下载器的 manifest，逐项重新取候选避免 rollback/commit 后 ORM 过期；成功恢复使用 `system:recovery`，resolved/失败路径不误标明细。
- 启动时在调度器之前幂等对账历史 `quarantined/purged + stable` 候选，严格按批次、下载器和规范化路径补齐明细，操作者记录为 `system:reconciliation`。

### 验证

| 验证项 | 结果 |
|---|---|
| 后端专项回归 | ✅ 77 passed / 1 skipped |
| 后端全量 pytest | ✅ 2391 passed / 6 skipped |
| 变更 Python 文件 Black | ✅ 通过 |
| Flake8 app / Ruff 变更范围 / BtDeck 架构检查 | ✅ 通过 |
| Mypy 变更应用文件 | ✅ 89 errors；修改前同口径 90，零新增 |
| Mypy 全量基线 | ⚠️ 1468 errors / 122 files，既有 SQLAlchemy 与历史类型债 |
| 前端专项回归 | ✅ 3 suites / 48 tests |
| 前端全量 Jest | ✅ 24 suites / 348 tests |
| TypeScript / 严格 Vue ESLint / Vuex action lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过 |
| 根 `init.sh` | ✅ 退出 0；Git Bash 子脚本未识别 Node，但指定 Node 18 的全部前端门禁已通过 |

### 已知仓库基线

- 完整 `npm run lint` 仍在任务开始前已存在的 `frontend/src/contracts/advancedSearch.generated.ts` 契约漂移处失败；本任务不涉及高级搜索契约，未混入无关生成文件。其后的 Vue ESLint、TypeScript 与 Vuex 门禁已独立执行并通过。
- 全量 `black --check app/` 命中 10 个本任务未修改文件的既有格式差异；本次所有变更 Python 文件均通过 Black，未为通过门禁而格式化无关文件。
- 本轮没有执行 Git commit/push；既有 6 个未跟踪工具目录保持不动。

---

## 2026-07-27 - 传统保存路径列与列表排序图标

**任务 ID**: `v1.0.6.31`
**分支**: dev
**范围**: 仅前端。为传统模式补保存路径列，为列表模式可排序列增加 Lucide 状态图标，不改 API 与排序参数。

### 实现

- `TraditionalView.vue` 在“分类/标签”与“添加时间”之间新增“保存路径”，兼容 `savePath/save_path`，空值显示 `-`，单元格 `title` 保留完整路径。
- 保存路径加入传统模式独立列设置，默认可见；既有 `visibleTableColumnCount` 自动计入该列，虚拟滚动占位行 colspan 保持正确。
- 传统表格增加 1380px 最小宽度，由现有 `.table-container` 内部滚动承接窄视口，避免新增 180px 路径列压缩名称列。
- `LucideIcon.vue` 静态注册 `arrow-up-down`、`arrow-up`、`arrow-down`，继续只打包实际使用图标。
- 列表模式五个排序表头常驻 13px Lucide 图标：未排序双向、降序向下、升序向上；移除原 ▲/▼ 文本字符。
- 图标沿用 `currentColor`，默认低强调，悬停、焦点和当前排序态提高不透明度；图标保持 `aria-hidden`，表头原有 `aria-sort`、Enter/Space 与可见焦点不变。
- 回归测试覆盖传统列顺序、列设置、蛇形路径兼容与完整路径提示，以及五个表头的图标常驻和三态切换；Lucide 包装器验证三个新图标均能渲染 SVG。
- 独立测试提交追加三项保护：旧版列偏好未包含 `savePath` 时新列仍默认可见；显式隐藏时表头、数据列与 `visibleTableColumnCount` 同步；Space 键切换排序图标且 DOM 不出现 ▲/▼ 字符。

### 验证

| 验证项 | 结果 |
|---|---|
| 目标回归 | ✅ 3 suites / 30 tests |
| 追加回归目标 | ✅ 2 suites / 24 tests |
| 前端全量 Jest | ✅ 23 suites / 330 tests |
| TypeScript `typecheck` | ✅ 通过 |
| 严格 Vue ESLint | ✅ 0 error / 0 warning |
| Vuex action lint | ✅ 通过 |
| 生产构建 | ✅ 通过；48 条既有 Sass/资源体积 warning |
| 根 `init.sh`（Git Bash） | ✅ 退出 0；识别 Node v18.20.8 / npm 10.8.2 |
| `git diff --check` | ✅ 通过 |

### 已知基线与边界

- 完整 `npm run lint` 在首步 `contract:check` 命中任务开始前已存在的 `frontend/src/contracts/advancedSearch.generated.ts` 生成契约漂移；本任务不涉及高级搜索协议，未修改该无关生成文件。其后的 Vue ESLint、TypeScript 与 Vuex 门禁已分别通过。
- 保存路径列按确认范围不参与排序；现有 `sort_by/sort_order` 协议未变。
- 本轮已按功能实现与追加回归保护拆分为两个 Git 提交，均未 push；会话开始前已有的 6 个未跟踪工具目录保持不动。

---

## 2026-07-27 - 种子列表分页组件与列头排序对齐

**任务 ID**: `v1.0.6.30`
**分支**: dev
**范围**: 仅前端。统一种子列表与传统模式的每页数量交互，并为列表模式补齐传统模式中的列头排序，不改后端 API。

### 实现

- 新增共享 `PageSizeCombobox.vue`，两种视图统一使用 20/50/100/500/1000 预设，并继续支持 1–100000 自定义输入；选择预设、Enter 或失焦均归一化应用并回到第 1 页。
- `TraditionalView.vue` 改为复用共享组件，保留原分页状态、虚拟滚动和重复任务行为；组合框样式集中到全局主题样式，避免两个视图出现视觉与交互分叉。
- `views/torrents/index.vue` 移除原 Element `el-select`，接入同一组合框并同步 `limit/skip`。
- 列表模式为名称、大小、状态、比率和添加时间五个列头增加服务端排序入口：首次选择字段默认降序，同字段再次操作切换升/降序。
- 排序列头补齐 `aria-sort`、Enter/Space 键盘操作、可见焦点与当前方向箭头；移动端分页保留每页数量组件，仅隐藏摘要文字。
- 新增列表视图组件测试，并让传统视图组件测试挂载真实共享组合框，锁定分页和排序请求参数。
- 新增 `page-size-combobox.spec.ts` 独立组件回归，锁定五项默认预设、受控输入及全部公共事件、展开/选中 ARIA 状态、箭头状态和 `focusInput()` 聚焦行为。

### 验证

| 验证项 | 结果 |
|---|---|
| 列表视图新增回归 | ✅ 1 suite / 2 tests |
| 分页组件独立回归 | ✅ 1 suite / 4 tests |
| 前端全量 Jest | ✅ 23 suites / 323 tests |
| TypeScript `typecheck` | ✅ 通过 |
| 严格 Vue ESLint | ✅ 0 error / 0 warning |
| Vuex action lint | ✅ 通过 |
| 生产构建 | ✅ 通过；48 条既有 Sass/资源体积 warning |
| 根 `init.sh`（Git Bash） | ✅ 退出 0；识别 Node v18.20.8 / npm 10.8.2 |
| `git diff --check` | ✅ 通过 |

### 已知基线与边界

- 完整 `npm run lint` 在首步 `contract:check` 命中任务开始前已存在的 `frontend/src/contracts/advancedSearch.generated.ts` 生成契约漂移；本次不涉及高级搜索协议，因此未修改该无关文件。其后的 Vue ESLint、TypeScript 与 Vuex 门禁已分别通过。
- 未新增或修改 API，排序继续使用既有 `sort_by/sort_order` 参数。
- 本轮按功能实现与独立回归保护拆分为两个 Git 提交，均未推送；会话开始前已有的 `.agents/`、`.claude/`、`.code-graph/`、`.codex/`、`.spec-workflow/`、`.zcode/` 未跟踪目录保持不动。

---

## 2026-07-27 - 高级搜索视觉密度与多选条件行高修正

**任务 ID**: `advanced-search-ui-revamp.4`
**版本记录**: `v1.0.6.29`
**分支**: dev
**范围**: 仅前端。调整种子列表高级搜索对话框的文字比例、间距和多选控件呈现，不改搜索逻辑与前后端协议。

### 起因与根因

- 用户反馈高级搜索对话框文字比例偏大，标签控件高度显著高于同一条件行，破坏视觉对齐。
- 通过 `docs/roadmap/` 定位调用链：`views/torrents/index.vue` → `AdvancedSearchBuilder.vue` → `ConditionValueInput.vue` → `AdvancedMultiSelect.vue`。
- 根因是 v1.0.6.28 重塑后的 `AdvancedMultiSelect` 把搜索框、已选区、选项列表和快捷操作整块常驻在条件值区域，其他 `size="small"` 控件为 32px，而多选条件会把整行撑到数百像素。

### 实现

- `AdvancedMultiSelect.vue`：默认态改为固定 32px 的紧凑触发器，与 Element UI small 控件等高；完整选择面板收纳进 `el-popover`，点击后浮出。
- 触发器显示首个选项摘要与选中数量，保留主题 token、悬停/焦点反馈，并补 `aria-haspopup`、`aria-expanded`、可见标题；打开面板自动聚焦搜索，Esc 清空搜索并关闭。
- 内层批量粘贴/高级设置 popover 禁止挂载到 body，避免点击嵌套浮层时误关闭外层选择面板。
- 面板字号按 10/11/12/13/14 的层级收紧，缩小搜索框、胶囊、chip、选项、计数和快捷按钮间距；所有选择、创建、虚拟滚动和事件载荷保持不变。
- `AdvancedSearchBuilder.vue`：表单正文统一 13px，Element 控件文字 12px；组、条件和操作区间距收紧，底部动作按钮统一 `size="small"`。
- `views/torrents/index.vue`：高级搜索标题图标 18→16px、标题文字 15px。
- `AdvancedMultiSelect.spec.ts`：新增 2 个回归用例，锁定紧凑触发器默认态及首项/数量摘要。

### 验证

| 验证项 | 结果 |
|---|---|
| 目标组件测试 | ✅ 4 suites / 70 tests |
| 新增紧凑触发器用例 | ✅ 2/2 |
| 全量 Vue ESLint | ✅ 0 error / 0 warning |
| TypeScript `tsc --noEmit` | ✅ 通过 |
| Vuex action lint | ✅ 通过 |
| 生产构建 | ✅ 通过；48 条既有 Sass/资源体积 warning |
| 根 `init.sh`（Git Bash） | ✅ 退出 0；识别 Node v18.20.8 / npm 10.8.2 |
| `git diff --check` | ✅ 通过 |

### 已知基线与边界

- 完整 `npm run lint` 在第一步 `contract:check` 被本次开始前已存在的 `advancedSearch.generated.ts` 漂移拦截；本任务未修改高级搜索协议或生成契约，因此没有把无关生成结果混入 UI 变更。其后的 Vue ESLint、TypeScript 和 Vuex 门禁均已分别通过。
- `npm install --ignore-scripts` 仅按现有 lockfile 补齐缺失的 `lucide` 包，`package.json`/`package-lock.json` 无变更；审计输出的 72 项依赖漏洞为现有依赖树状态，未执行越界的 `npm audit fix`。
- 本轮未执行 Git 提交；会话开始前已有的 `.agents/`、`.claude/`、`.code-graph/`、`.codex/`、`.spec-workflow/`、`.zcode/` 未跟踪目录保持不动。

---

## 2026-07-26 - 高级搜索标签选择器重塑（Lucide + 设计系统对齐）

**任务 ID**: `v1.0.6.28`
**分支**: dev
**范围**: 仅前端。重塑高级搜索通用多选组件 + 接入 Lucide 图标基础设施，不动父级、对话框骨架与后端。

### 起因

用户要求调整高级搜索的"标签选择器"UI，使其更易操作且契合项目风格，约束：统一 Lucide 图标、全程禁止 emoji、对标 Awwwards 级设计品质。

经 3 个独立子代理对抗审查（技术正确性 / 回归测试 / 范围与设计系统），坐实 2 个 BLOCKER 与多个 RISK，全部采纳修正后实施。

### 范围决策（用户确认）

- **改动范围**：仅 `AdvancedMultiSelect.vue`（标签 / 分类 / 下载器三字段共享）+ 对话框标题图标 + Lucide 基础设施 + 2 处配置。父级 `AdvancedSearchBuilder`、`ConditionValueInput`、对话框骨架、后端零改动。
- **基调**：高端 + 与设计系统一致（玻璃拟态 / 渐变高亮 / 分层阴影 / 微交互 / 入场动效）。按职业判断不叠加 WebGL/视差/重动效（会损害多选工具效率与可访问性）。
- **emoji 清理范围**：仅高级搜索对话框渲染树内（`index.vue:571` 的 `🔍` + `AdvancedMultiSelect.vue:27` 的 `el-icon-plus`）。页面级 emoji（`📊 Tracker详情` / `⚙️ 列设置` / `✕✓✗` tracker 状态）**明确列为后续独立任务**，不在本次范围。

### 审查修订（采纳全部 BLOCKER / RISK）

1. **BLOCKER — Lucide 导入方式**：原计划 `render()` 内 `import('lucide')` 动态取图标，经技术审查证伪（返回 Promise 无法同步产 VNode；全命名空间动态导入打包全部 ~2000 图标不可 tree-shake）。改为静态具名导入 9 个图标 + 元组 `[tag, attrs, children]` 递归映射到 Vue2 `h()`，属性合并保留 `viewBox`。
2. **BLOCKER — Jest 不转译 lucide ESM**：回归审查发现 `jest.config.js` 用 `@vue/cli-plugin-unit-jest` preset，默认 `transformIgnorePatterns: ['/node_modules/']` 拒转译 lucide ESM，会让组件测试全红。已加 `transformIgnorePatterns: ['<rootDir>/node_modules/(?!lucide)']`。
3. **RISK — `--color-error-rgb` token 缺失**：`theme-variables.scss` 仅定义 `--color-primary-rgb`。已在 emerald/orange/graphite 三主题块各补 `--color-error-rgb`，排除态 chip 才能真正随主题切换。
4. **RISK — el-dialog 标题 slot 语法**：用仓库既有约定 `<template slot="title">`（非 `#title`），与 NotificationDrawer/BatchOperationDialog 一致。
5. **RISK — `showAdvanced` prop 保留**：父级 `ConditionValueInput.vue:254` 传 `:show-advanced="true"`，删 prop 会触发 Vue2 运行时告警。保留该 prop（高级面板改 popover 入口）。
6. **RISK — 测试钉死项保留**：`.normal-list` class、`搜索选项...` placeholder、`el-input` 元素、data 字段 `filteredOptionsCache`/`lastSearchKeyword`/`searchDebounceTimer`/`customSeparators`/`selectedMode`/`useVirtualScroll`/`highlightedIndex`、`$emit('input', values)` 与 `$emit('change', {values, mode, count})` 载荷形态全部严格不变。
7. **RISK — 颜色变更显式化**：旧版硬编码 Element 蓝（`#409eff`/`#ecf5ff`），改 `var(--color-*)` 是可见行为变更（蓝→翡翠/橙/石墨随主题），作为 intentional change 标注。

### 关键实现

- **LucideIcon.vue（新建，~140 行）**：实测 lucide@1.27.0 IconNode 形状（每个图标是 `[child, ...]`，child = `[tag, attrs]` 或 `[tag, attrs, children]`；`createElement` 内部调 `document.createElementNS` 仅适浏览器 DOM，故不用）。自建轻量包装器：静态具名导入 9 图标（search/plus/sliders-horizontal/check-check/square/list-checks/trash/clipboard-paste/x），`render(h)` 内合并 `defaultAttributes` + 用户 size/strokeWidth，`stroke=currentColor` 跟随主题。webpack 5 + sideEffects tree-shake，仅打包用到图标。
- **AdvancedMultiSelect.vue（核心重构）**：
  - 结构从"堆叠 4 层（tabs + 列表 + 模式切换 + 已选区 + 高级选项）"重塑为"清晰单列视觉流"：顶部搜索框（玻璃拟态，内嵌 Lucide Search + 内联创建按钮）→ 已选区前置（含/排除胶囊 + 渐变计数 + chip 云）→ 选项列表（渐变选中态 + 左侧 accent 条）→ 底部 Lucide 图标快捷操作组 + 批量粘贴 popover + 高级选项 popover。
  - 全程走设计 token（`var(--color-*)` / `var(--glass-bg)` / `var(--shadow-*)` / `var(--radius-xl)` / `var(--transition-base)`），三主题（翡翠/橙/石墨）自然切换。`@supports not (backdrop-filter)` 与 `var(--token, #literal)` 双兜底（仓库既有约定）。
  - 入场动效：选项 `ams-fade-up` 错峰、chip 弹簧感增删（`cubic-bezier(0.34, 1.56, 0.64, 1)`）。
  - 性能/复杂度清理：删除运行时 `console.warn` 性能日志与 `$forceUpdate`，改用响应式 `computed`；保留虚拟滚动分支与防抖机制。
  - API 严格不变（测试覆盖项），仅 `mode-change` event 随 `el-tabs` 移除（无测试、无父级监听，可接受）。
- **index.vue 对话框标题**：`title="🔍 高级搜索"` → `<template slot="title">` 放 `<LucideIcon name="sliders-horizontal" :size="18"/>` + 文案，满足"对话框内零 emoji"约束。
- **theme-variables.scss**：emerald `--color-error-rgb: 239, 68, 68`；orange `220, 38, 38`；graphite `239, 68, 68`。
- **jest.config.js**：加 `transformIgnorePatterns: ['<rootDir>/node_modules/(?!lucide)']`。

### 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/package.json` | +`lucide@^1.27.0` 运行时依赖 |
| `frontend/src/components/common/LucideIcon.vue` | 新建（~140 行 Lucide 包装器） |
| `frontend/src/components/common/__tests__/LucideIcon.spec.ts` | 新建（6 用例） |
| `frontend/src/main.ts` | 全局注册 `<LucideIcon>` |
| `frontend/jest.config.js` | +lucide transformIgnorePatterns |
| `frontend/src/styles/theme-variables.scss` | 三主题块补 `--color-error-rgb` |
| `frontend/src/components/torrents/AdvancedMultiSelect.vue` | 核心重构 |
| `frontend/src/views/torrents/index.vue` | 对话框标题 emoji → Lucide slot |
| `frontend/src/components/torrents/__tests__/AdvancedMultiSelect.spec.ts` | +3 重塑后行为用例 |

### 验证结果

| 验证项 | 结果 |
|---|---|
| TypeScript `tsc --noEmit` | ✅ 0 error |
| 完整 `npm run lint`（contract:check + vue lint --max-warnings 0 + vuex-action） | ✅ 全绿 |
| 全量 Jest | ✅ **21 suites / 315 tests**（基线 306 → 315，+6 LucideIcon +3 重塑行为；零回归） |
| `npm run build` | ✅ 通过（lucide 图标 tree-shake 仅打包用到 9 个，无独立 lucide chunk） |
| AdvancedMultiSelect 公共 API（props/events/data/methods） | ✅ 测试覆盖项全部稳定不变 |

### 明确边界（已记入证据）

- 页面级 emoji 清理（`📊 Tracker详情` / `⚙️ 列设置` / `✕✓✗` tracker 状态等）列为后续独立任务，本次不动。
- `lucide-vue@0.517.0`（冻结的官方 Vue2 包装）评估后不采用：已弃用冻结，自建轻量包装器代码量小且可控。
- Lucide 仅在本次重写范围内接入；全项目"去 emoji / 统一 Lucide"为后续渐进式任务。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地环境完成（CI 已覆盖 lint/typecheck/test/build 全门禁）。

---

## 2026-07-26 - 最近三次提交红队加固实施（v1.0.6.27）

**任务 ID**: `v1.0.6.27`
**分支**: dev
**审查对象**: `0b83ac8`、`b894ca2`、`0b447df`
**状态**: 根因级加固、自动化验证和发布/恢复文档已完成；未提交，未迁移真实本地数据库。

### 红队结论与实施目标

本轮不以代码风格或局部 diff 为判断依据，而是从攻击输入、旧数据、失败恢复、协议漂移和并发写入等运行时场景验证修复是否真正闭环。原实现仍存在三类系统性缺口：

1. `ratio`/`ratio_limit` 虽已改列类型，但不同写入路径对 `-1`、`-2`、缺失值、异常值和 `0` 的语义不一致，可能在后续同步中重新污染数据。
2. 已发布过的 `6132b66d14a7` 不能靠直接改旧迁移覆盖所有环境；备份成功也没有完整性、版本和可恢复性硬门禁。
3. 高级搜索的前后端契约由多份手写常量和兼容 fallback 维持，测试能通过但真实请求仍可能静默改变语义；原 regex 也不是真实、受限的正则执行。

修复方案经 3 个子代理分别从数据迁移/恢复、搜索协议和对抗性发布角度独立审查后收敛并实施。

### 已完成

#### 1. ratio 写入语义与迁移闭环

- 新增统一三态归一化：有效有限非负数、下载器明确空值、暂不可用；暂不可用在更新时保留旧值，在新增时写 `NULL`。
- 覆盖 qBittorrent、Transmission、同步、异步详情、CRUD 和旧迁移写路径；异常按批次聚合记录，避免逐条日志风暴。
- `6132b66d14a7` 改为严格 Python 清洗，非法、非有限和负值统一为 `NULL`；新增 follower 迁移 `8f4c2d1a9b7e`，兼容已经执行过旧版 6132 的数据库。
- ORM、生产完整 schema 和旧 migrator 均加入有限非负约束，避免迁移后再次写入脏值。

#### 2. 备份、诊断与恢复硬门禁

- 迁移前备份必须通过 SQLite 完整性、Alembic 版本和 SHA-256 校验；备份失败在任何环境都中止迁移。
- 新增只读诊断 CLI `backend/scripts/ratio_migration_report.py`，支持 JSON、发现问题时非零退出、单独验证备份文件。
- 红队实跑发现：普通 SQLite 校验可能生成 `-wal`/`-shm`，而原保留策略 glob 会把 sidecar 当成主备份计数。现已改为 `mode=ro&immutable=1`，并只识别带完整时间戳的主备份；sidecar 不计数、不删除。
- 补充两阶段发布、迁移前后诊断、零值对账、备份恢复和不可跨 6132 降级的运维说明。

#### 3. 高级搜索严格协议与安全执行

- 后端 JSON 成为字段、类型和操作符的单一契约，前端文件由脚本生成并在 lint 前校验漂移。
- Pydantic 与服务边界统一拒绝额外字段、未知操作符、非法 value 形状、非有限数、非法本地日期、超限组/条件/regex，统一返回真实 HTTP 422。
- 移除静默操作符和扁平参数 fallback；模板、即时搜索、传统视图和虚拟列表统一使用严格请求构造器。
- SQLite 注册有界 `bt_regexp`，覆盖普通字段与 tracker；单次 regex 匹配和主查询/preview 都有超时预算。
- 前端父组件成为条件结构的唯一状态拥有者，子组件受控更新；单边 `between`、本地日期和精确取反均可逆且不丢条件。

### 验证证据

- 后端全量：`2384 collected / 2378 passed / 6 skipped / 0 failed`。
- 后端重点回归：搜索、迁移和 ratio 共 `341 passed`；备份/诊断 sidecar 回归 `23 passed`。
- 前端全量：`20 suites / 306 tests`；contract check、TypeScript、严格 ESLint、Vuex lint 和生产构建均通过。
- 后端静态门禁：Flake8、BtDeck 架构规则、`git diff --check` 通过；22 个变更 Python 文件通过 Black；6 个新增严格模块通过 mypy。
- 全量 mypy 仍报告仓库既有 `1481` 个 SQLAlchemy/历史类型债务，本轮没有隐藏或降低检查标准。
- 真实 `backend/config/app.db` 只读诊断：`integrity=ok`、revision=`e6d8a20c41f3`、目标=`8f4c2d1a9b7e`、22,277 行仍是旧 VARCHAR schema，工具正确判定为未完成迁移；发现 3 个有效主备份。
- 最新主备份文件只读校验通过：`app.db.pre-migration-20260711-194949-098`，大小 87,363,584 bytes，SHA-256=`9db1a367892825ef296d0717d5fd806048186c1bdbd2fa4133a23a26839b7ae0`，revision=`b075727f7182`。
- 根 `./init.sh` 未能执行：当前 Windows 环境只有不可用的 WSL bash stub；已分别完成其关键后端/前端验证，但没有伪报 init 成功。

### 明确保留的发布边界

- 未擅自迁移或写入真实 `backend/config/app.db`；应按 rollback guide 在受控发布窗口执行诊断、备份、后端迁移和前端发布。
- 历史 `0` 无法仅凭数值区分真实值与旧错误转换值，必须按业务数据源对账，不能自动改写。
- 本轮未创建提交；用户原有未跟踪文件和目录均保持不动。

---

## 2026-07-26 - 高级搜索操作符前后端契约守卫测试（前端 Jest，v1.0.6.26）

**任务 ID**: `v1.0.6.26`
**分支**: dev
**范围**: 前端。补齐 v1.0.6.25 后端 TestOperatorContractGuard 的前端对偶，确保前端输入与后端期望一致。

### 起因

v1.0.6.25 在后端补了 `TestOperatorContractGuard` 冻结契约，但前端侧无对应守卫——前端独立修改 operatorGroups 时不会被后端测试拦住。本次补齐前端 Jest 契约测试。

### 实现

新建 `frontend/tests/unit/operator-contract.spec.ts`（16 用例 4 类），用源码字符串解析范式（与 field-types-consistency.spec.ts 一致，不 mount Vue 组件）：

1. **契约 1 - backendValue 集合**：解析 operatorGroups 全部 backendValue，断言在后端 allowed_operators 集合内（防 422）。**额外读后端源码**（剔除 # 注释后）做双向同步校验，防止 BACKEND_ALLOWED_OPERATORS 常量与后端源码漂移。
2. **契约 2 - value 结构对齐**：between/regex/last_days/date_range 的 value 形态与后端 `_build_between_filter` / `_build_regex_filter` / `_build_date_window_filter` 解构逻辑一致。
3. **契约 3 - formatParamValue 输出类型**：size 带单位串 / date 走 JSON.stringify / number 走 Number() / multiSelect 走数组 / boolean 走 '1'/'0'，与后端 value 字段期望一致。
4. **降级策略 fallback 一致性**：带 fallback 的操作符其 fallback 目标也必须在后端 allowed_operators 内（否则降级后仍 422）。

### 关键技术坑

- ts-jest 转译 module-top-level 的 `/g` 正则字面量时 lastIndex 残留，导致 `[^']+` 连吃尾引号（解析出 `contains'`）。改用**逐行 split + 单行 match（非 /g）**规避。
- 后端 allowed_operators 集合内的中文注释含 `{` `}` 字符（如 `# between={min,max}`），非贪婪正则 `\{([\s\S]*?)\}` 会在注释的 `}` 处提前结束。改用 `indexOf` 定位 `if v not in allowed_operators` 作为结束边界。
- 注释里的字符串字面量（`"days":N`、`{"start","end"}`）会被 `"([^"]+)"` 误读为操作符。剔除 `#` 注释行后再提取。

### 验证

- 前端 `npm run test:unit` 全量 **314 passed**（含新增 16）
- 前端 `npm run lint --max-warnings 0` 通过（修了 3 处 non-null assertion，改三元表达式）

---

## 2026-07-26 - ratio/ratio_limit 列治本（String→Float）+ 4 操作符后端实现（v1.0.6.25）

**任务 ID**: `v1.0.6.25`（v1.0.6 task 25；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 全栈。后端 schema 治本 + 服务层简化 + 4 操作符实现 + 类型契约；前端 numberRange UI + 类型同步。

### 起因：v1.0.5.15 的 cast 修复属「治标不治本」

用户要求"作为红队，严格验证 v1.0.5.15 提交是否治标不治本"。红队审查坐实 3 处同根 bug 未修：
1. **ratio_limit filter**：cast 修复只点名 `field=="ratio"`，遗漏同类型同入口的 ratio_limit
2. **ratio sort**：apply_sorting 直接 order_by(String 列) 走字典序，filter 修了 sort 没修
3. **ratio_limit sort**：同上

且发现 between/regex/last_days/date_range 四个前端暴露的操作符后端 `allowed_operators` 不含，Pydantic 直接 422 拒整个请求。

### 治本方案

**Schema 根因**：ratio/ratio_limit 用 `Column(String)` 存数值是建模错误。改为：
1. **列类型 String→Float** + Alembic batch_alter 迁移（含脏数据 `""`/`-1`/`-2`/`"None"` 清洗、partial unique index 显式 drop+recreate、迁移末尾断言 WHERE 子句保真）
2. **服务层简化**：移除 cast、新增 `NUMERIC_FIELDS = {"ratio","ratio_limit"}` 集中常量、显式 `float(value)` 兜底 Pydantic smart-union
3. **4 操作符后端实现**：between（拆 gte AND lte）、regex（LIKE 兜底）、last_days（datetime 偏移）、date_range（区间）
4. **前端 numberRange UI**：ConditionValueInput 模板 + handler + watcher + formatParamValue number+between 对象分支
5. **写入侧清理 8 处**：torrent_helpers QB+TR 错位修复、torrent_sync QB 哨兵、torrent_crud_service 默认值；新增 `_safe_float` helper 兜底 ValueError 实例
6. **类型契约同步**：VO schema、两份 Torrent 接口、TorrentDetailDialog 0 值修复用 formatRatio

### 红队审查迭代

方案 v1 经 3 子代理独立审查坐实 6 处阻断项（写入侧漏 50%、脏数据漏 `"None"`、batch_alter 范式错误类比、between 是 422 不是静默丢弃、版本号违规、前端 0 值回归），修订为 v2 后用户两次确认范围（4 操作符全纳入、迁移末尾加断言）。

### 验证

- Alembic 迁移 6132b66d14a7 实证：脏数据全部转 NULL、partial index WHERE 保真、upgrade/downgrade 对称
- 后端全量 pytest **2315 passed**（基线 2286 + 新增 29：7 sort + 3 ratio_limit filter + 8 new operators + 1 contract guard + 4 migration + 其他）
- flake8 0；black 通过；mypy 改动区域 0 新增
- 前端 npm run lint + npm run build 通过；vue-tsc type error 2472→2473（基线本身抖动）
- 手动：PRAGMA table_info(torrent_info) ratio 列 FLOAT、idx_torrent_hash_unique 含 WHERE dr=0

### 关键决策

- **哨兵值**：qB -1 / TR None / 历史 "" 全部统一映射 NULL（与 commit message "CAST(NULL AS FLOAT) 不误命中" 一致）
- **TR 赋值错位**：torrent_helpers.py:749 原 `ratio=str(tr_torrent.seed_ratio_limit)`（比率限制误赋给实际比率字段）一并修复
- **batch_alter 断言**：只断言 partial unique index 存在 + WHERE 子句，不强行断言全部 ix_torrent_info_* 索引名（ghost 库用不同索引设计）

---

## 2026-07-26 - 高级搜索完备回归测试 + ratio 字典序 bug 修复 + *_multi 死代码清理

**任务 ID**: `v1.0.5.15`（v1.0.5 高级搜索功能回归保护与缺陷修复；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 全栈。后端 ratio 双路径字典序 bug 修复 + apply_multi_select_conditions 死代码删除 + 完备回归测试；前端同步删除 *_multi 类型声明。

### 现象与根因

用户要求"为高级搜索功能增加完备的回归测试，测试各种组合下的查询是否能达到预期结果"。在用 3 个独立子代理对实施计划做证伪审查时，发现 3 项阻断性问题：

1. **ratio 字符串字典序比较 bug（双路径）**：`TorrentInfo.ratio` 是 String 列，但 `apply_basic_filters:180-184` 用 `TorrentInfo.ratio >= str(value)` 做字符串字典序比较，导致 `ratio_min=2` 让 `ratio="10.0"` 漏匹配（"10.0" < "2"）。同一 bug 在 condition_groups 路径也存在：`_build_condition_filter` 走 `OPERATOR_MAPPING` 的 `gt/gte/lt/lte` 对 ratio 也做字符串比较。
2. **修复计划误改死代码路径**：原计划"修复 tags_multi 整串匹配 bug"目标错误——`apply_multi_select_conditions` 及 `EnhancedAdvancedSearchRequest` 的 4 个 `*_multi` 字段是前端从不调用的死代码路径（前端 `AdvancedSearchBuilder.vue:1093-1098` 明确将 multiSelect 字段走 condition_groups + contains_any）。tags 子串语义已在 v1.0.5.14 通过 condition_groups 的 contains_any 正确修复。
3. **测试设计多处假绿风险**：种子数据日期用非 ISO 格式、NULL 排序盲区、category NULL 三值逻辑污染、xfail 无法对照两路径。

### 关键决策与证据

- **ratio 修复用 `cast(col, Float)`**：经技术正确性子代理实证，`sqlalchemy.cast(TorrentInfo.ratio, Float)` 在 SQLite 生成标准 `CAST(... AS FLOAT)`。NULL→NULL（WHERE 过滤，不误命中）；"" /"abc"→0.0（入库点 `torrents_async.py` 不会写这些异常值）；"2.5"→2.5。比"列改 Float 类型"（破坏性，需 Alembic 迁移）和"Python 层过滤"（性能差）都更优。
- **双路径统一修复**：`apply_basic_filters` 用 cast 替换 str 比较；`_build_condition_filter` 在 size/date 特殊处理块后加 ratio 分支（`column = cast(column, Float)`），保证两路径语义一致。
- **死代码路径整段删除**：删除 `apply_multi_select_conditions` 方法 + `search_torrents` 中的调用 + `MultiSelectCondition` 类 + `EnhancedAdvancedSearchRequest` 的 4 个 `*_multi` 字段 + 前端 `torrents.ts`/`torrent.ts` 的对应类型声明。前端 grep 实证无任何 `.vue` 业务代码赋值这些字段。
- **回归测试用真实内存 SQLite + StaticPool**：复刻 `test_advanced_search_batching.py` 范式，建 3 表（TorrentInfo/TrackerInfo/BtDownloaders），6 颗种子覆盖所有边界（status/category/tags/size/ratio/date/dr/tracker 全维度差异化）。

### 三代理独立审查（证伪优先）

计划经 3 个 general-purpose 子代理审查（技术正确性 / 测试有效性 / 范围回归），**坐实 3 项阻断性问题**，全部采纳修正：
1. 修复 1 漏 condition_groups 路径（三代理一致发现）→ 双路径都修
2. 修复 2 改死代码（范围代理硬证据：前端 `*.vue` 从不赋值 `*_multi`）→ 改为删除死代码
3. 测试设计 3 处假绿风险（种子日期非 ISO / NULL 排序盲区 / category NULL 三值逻辑）→ 修复种子数据 + 精确集合断言

驳回 1 项不成立的初版质疑（xfail NULL 对照），重新设计为独立 characterization test。

### 改动文件

| 文件 | 改动 |
|---|---|
| `backend/app/services/advanced_search.py` | import 加 `cast, Float`；ratio 基础过滤改数值比较；_build_condition_filter 加 ratio cast 分支；删除 apply_multi_select_conditions 方法 + search_torrents 调用 + MultiSelectCondition import；清理 added_date_max 死代码 pass |
| `backend/app/api/models/advanced_search.py` | 删除 MultiSelectCondition 类 + EnhancedAdvancedSearchRequest 的 4 个 *_multi 字段 |
| `backend/tests/services/test_advanced_search.py` | 删除 MultiSelectCondition import + TestApplyMultiSelectConditions 类（4 mock 测试）+ TestMultiValueOperatorsAgainstRealDb 类（7 真实 DB 测试，迁入新文件 B 类）+ 清理未用 PropertyMock import |
| `backend/tests/api/conftest.py` | 扩展 make_torrent 支持 tags/category/ratio/ratio_limit/torrent_id/super_seeding/enabled/save_path 关键字参数 |
| `backend/tests/services/test_advanced_search_regression.py` | **新建**：82 用例 8 类完备回归测试（A 基础过滤 / B 全22操作符 / C 条件组组合 / D *_multi 删除守卫 / E tracker 子查询 / F 排序分页 / G 端到端 / H NULL 边界） |
| `frontend/src/api/torrents.ts` | 删除 4 个 *_multi 字段声明 |
| `frontend/src/types/torrent.ts` | 删除 4 个 *_multi 字段 + MultiSelectField 接口 |

### 回归测试抓到的实现缺陷

TDD 红阶段验证 bug 存在（2 用例失败）→ 修复后转绿（2 用例通过）。关键证据：
- `ratio_min=2` 基础过滤：修复前只命中 t1(2.5)，t3(10.0) 因 "10.0" < "2" 字典序漏匹配；修复后命中 t1+t3
- 条件组 `ratio >= 2`：修复前同样漏 t3；修复后命中 t1+t3
- `ratio_max=999` 不误命中 ratio=NULL 的 t4（CAST(NULL AS FLOAT) <= 999 → NULL → WHERE 排除）

### 验证结果

| 验证项 | 结果 |
|---|---|
| 新增回归测试 `test_advanced_search_regression.py` | ✅ 82/82 通过 |
| advanced_search 全量相关测试（8 文件） | ✅ 188 passed |
| 含 auth_protection 扩展回归 | ✅ 269 passed |
| flake8（5 改动文件） | ✅ 0 error |
| black --check（5 改动文件） | ✅ 通过（新测试文件已 reformat） |
| mypy（2 源文件） | ✅ 与 baseline 一致（29 errors 全在既有 delete_torrents_batch/get_search_statistics 方法，本次 cast/ratio 改动行 0 新增） |
| 前端 typecheck（tsc --noEmit） | ✅ 通过 |
| 前端 lint（eslint --max-warnings 0） | ✅ 0 error |

### 明确不修的边界（已记入 evidence）

- NULL 安全语义差异（顶层 OPERATOR_MAPPING vs `_build_text_filter`）：作用于不同列集合（前者 name/tags/category，后者仅 tracker_url/tracker_msg），是 SQL 实现必需的安全处理而非语义 bug。本任务用 H 类 characterization test 钉死现状，独立技术债任务统一。
- `ratio_limit` 也是 String 列，理论上有同类字典序 bug 但前端无 API 暴露，本次不动。
- search-preview 端点 conditions_json 永远是单 AND 组：既有设计。
- `_build_text_filter` 对非文本操作符 fallback to contains：既有行为，仅测试覆盖。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地环境完成（CI 已覆盖 pytest + flake8 + black + mypy + typecheck + lint 全门禁）。

---

## 2026-07-25 - 高级搜索分类/标签/下载器字段 options 注入补全

**任务 ID**: `v1.0.5.13`（v1.0.5 高级搜索功能的遗漏补丁；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 仅前端。不新增后端端点。

### 现象与根因

用户报告种子列表高级搜索对话框中：① 分类、标签、下载器下拉框没有选项；② 标签用的组件不是下拉框。

经溯源（前端 + 后端源码坐实），两个现象是**同一根因**：`AdvancedSearchBuilder.vue` 对 `category / tags / downloader_name` 三字段只声明了空 `options: []` 占位（注释"将通过API动态获取"），但从未接入数据源——`getFieldOptions()` 对三字段返回 `[]`、`created()` 没调任何接口、顶部 imports 无 `@/api/*`。分类/下载器（原生 `el-select`）下拉因此为空；标签（`AdvancedMultiSelect`，本就允许自由输入）options 为空，只剩"手敲创建"一种交互，让用户感觉"不是下拉框"。

### 关键决策与证据

- **字段口径**（后端源码坐实）：`downloader_name` 匹配 `TorrentInfo.downloader_name` 列，入库点（`torrent_sync.py:1220` 等）全部写 `downloader.nickname`，故前端 value 取 `nickname`（非 `downloader_id`）；`category` 匹配 `TorrentInfo.category`（`==` 精确）；`tags` 匹配 `TorrentInfo.tags`（`LIKE`）。
- **数据源语义**：后端 `tag_management.py:_merge_assigned_filter_names` 已把"配置表 ∪ 种子实际 distinct 值"合并去重，选项必然命中至少一条种子，无"选了搜不到"的语义错配。
- **方案选型**：采用"构建器自拉接口"。经审查验证不违反复用原则——全仓无 options provider/mixin/composable/vuex 模块可复用；`index.vue` 根本没有 category/tag 数据；`ConditionValueInput` 的 `fieldOptions` prop 机制表明数据流设计意图就是"builder 维护 options"。
- **刷新策略**：用户决策为"每次打开对话框重新拉取"。新增公开方法 `refreshFieldOptions()`，由两父视图在打开对话框时经 `$nextTick` + `$refs` 调用（el-dialog 默认 `destroy-on-close=false`，组件常驻，`created()` 只触发一次）。

### 三代理独立审查（证伪优先）

计划经 3 个独立 general-purpose 子代理审查（技术正确性 / 测试有效性 / 根因与方案选型），采纳全部 5 个阻断性修正：
1. `extractErrorMessage` import 来源 `@/utils/formatters`（非 `error-normalize`）；
2. API 返回 `ApiResponse` envelope，必须解 `.data` + 校验 `code === '200'`；
3. spec mock 改为显式列举 exports（不用 `requireActual`，全仓零先例）；
4. 项目无 `flushPromises`，复用 `traditional-view-component.spec.ts` 的 `flushLifecycle` 三段式；
5. B2 用例明确 mount/shallowMount 策略。
驳回 3 个不成立的质疑（响应式需 `$set`、Promise.allSettled 兼容性、构建器自拉违反复用原则——经验证均不成立）。原 B3 源码字符串契约 spec 因过度耦合实现细节、与行为测试 100% 重叠而删除。

### 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/components/torrents/AdvancedSearchBuilder.vue` | 加 import + 三 options 状态字段 + `loadFieldOptions`（`Promise.allSettled` 并发，解 envelope，部分失败静默/全失败告警，销毁防护）+ 公开 `refreshFieldOptions` + `getFieldOptions` switch 三 case |
| `frontend/src/views/torrents/index.vue` | `@click` 改 `openAdvancedSearch`，nextTick 调 `refreshFieldOptions` |
| `frontend/src/views/torrents/TraditionalView.vue` | 同上 |
| `frontend/src/components/torrents/__tests__/AdvancedSearchBuilder.spec.ts` | 扩展：mock 三 api + `flushLifecycle` + 6 用例（首次加载/部分失败/全失败/refresh/value 透传/dialog 复用语义） |
| `frontend/src/components/torrents/__tests__/ConditionValueInput.spec.ts` | 新建：4 用例（select 渲染 el-option / multiSelect options 透传 / 空选项不崩 / emit input+change） |

### 回归测试抓到的实现缺陷

B1「部分失败降级」「全失败」用例失败，暴露真实缺陷：`loadFieldOptions` 失败时未清空旧 options，导致"上次成功 + 本次失败"时残留旧数据误导用户。修正为每次刷新前重置三数组为空，语义更清晰。

### 验证结果

| 验证项 | 结果 |
|---|---|
| ESLint（6 变更文件） | ✅ 通过（自动修复 9 条格式问题后 0 error） |
| `tsc --noEmit` | ✅ 通过 |
| `test:coverage`（全量） | ✅ 18 suites / 283 tests 全绿（含新增 10 用例）；Branches 44.46%（>40% 门禁） |
| `npm run build` | ✅ 通过（仅项目既有 Sass/资源体积 warning） |
| `feature_list.json` JSON 合法性 | ✅ node 解析通过 |

### 明确不修的边界（已记入 evidence）

- 下载器改名导致的历史种子 `downloader_name` 漂移 → 单独立项。
- 抽 `torrentFieldOptions` composable 做跨组件缓存 → 后续优化。
- `category` 的 `==` 精确匹配对大小写/空格敏感 → 后端既有语义，本次不动。
- select 字段 `in/not_in` 操作符当前传单值字符串 → 既有行为，非本次引入，仅注释说明。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地环境完成（CI 已覆盖 lint/typecheck/test/build 全门禁）。

---

## 2026-07-25 - 高级搜索三字段统一多选 + 操作符语义修正（全栈）

**任务 ID**: `v1.0.5.14`（v1.0.5.13 的延续；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 全栈。后端扩操作符白名单 + OPERATOR_MAPPING；前端三表同步 + 两份 formatParamValue 同步 + 操作符按字段过滤 + 旧模板归一化。

### 需求

v1.0.5.13 修复了三字段下拉无选项后，用户进一步要求：标签选择器改用与分类一样的下拉框，且**分类和标签都要支持多选**。经澄清：三字段（category/tags/downloader_name）统一用 AdvancedMultiSelect 多选。

### 第二轮 3 子代理独立审查（证伪优先）

计划经 3 个 general-purpose 子代理审查（技术正确性 / 测试有效性 / 向后兼容），**坐实两个致命缺陷**，推翻了初版"前端零改后端"的前提：

1. **tags 的 in 语义对逗号串列是错的**（代理 C 发现）：`TorrentInfo.tags` 是逗号分隔单字符串列（如 `"movie,4k"`）。`column.in_(['movie'])` 只匹配整串等于 `'movie'`，`tags='movie,4k'` 不命中。→ tags 必须用 `contains_any`（OR(LIKE)），category/downloader_name 单值列才用 in。
2. **后端 Pydantic 白名单拒旧操作符**（代理 A/C 发现）：`validate_operator` 白名单不含 contains_any 等，旧模板请求 422。→ 后端白名单 + OPERATOR_MAPPING 双扩。
3. **遗漏第三份字段表**（代理 A/B 发现）：`torrentBatch.ts:541-561 ADVANCED_FIELD_TYPES` 是模板路径的字段类型表，category 是 select 且缺 downloader_name。→ 三表同步。
4. **两份 formatParamValue 副本**（代理 B 发现）：`AdvancedSearchBuilder.vue` 与 `torrentBatch.ts` 各一份，只改一份会导致即时搜索与模板搜索输出形态矛盾。→ 两份同步数组化。

驳回"前端零改后端"的不成立前提；采纳全部修正。

### 关键设计（字段 × 操作符 × value 矩阵）

| 字段 | 列类型 | 后端操作符 | SQLAlchemy 实现 | 前端 value |
|---|---|---|---|---|
| category | 单值 String | in/not_in | column.in_(list) | string[] |
| downloader_name | 单值 String | in/not_in | column.in_(list) | string[]（nickname） |
| tags | 逗号串 String | contains_any/not_contains_any | or_(*[column.contains(v)]) | string[] |

### 改动

**后端（2 文件 + 1 测试）**：
- `models/advanced_search.py`：`validate_operator` 白名单加 contains_any/all/not_contains_any/not_contains_all
- `services/advanced_search.py`：补 `not_` import；加模块函数 `_normalize_multi_value`（数组/逗号串/单值归一化）；OPERATOR_MAPPING 加 4 个 lambda（or_/and_/not_ 组合 column.contains）
- `tests/services/test_advanced_search.py`：+33 用例（TestNormalizeMultiValue 7 + TestOperatorWhitelistAcceptsMultiValue 6 + TestMultiValueOperatorsAgainstRealDb 7 真实 SQLite 端到端语义验证 + 既有保留）

**前端（3 源文件 + 4 测试）**：
- 三表同步：category/downloader_name 的 type select→multiSelect（AdvancedSearchBuilder.statusFields / ConditionValueInput.fieldTypeMap / torrentBatch.ADVANCED_FIELD_TYPES，后者补 downloader_name 条目）
- `operatorGroups.multiSelect` 重构为含全部 4 操作符；`getOperatorGroups` 按 `matchMode`（exact/substring）过滤——单值列只暴露 in/not_in，逗号串列只暴露 contains_*
- SearchField 接口加 `matchMode?: 'exact' | 'substring'`；category/downloader_name=exact，tags=substring
- 两份 formatParamValue 的 multiSelect 分支：`join(',')` → 返回数组
- `onFieldChange`：multiSelect 字段初始化 value=[]，其它 null
- `applyTemplateGroups`：加载旧模板时归一化（单值列的 contains_* 转 in/not_in；逗号串 value 拆数组）
- `buildSearchParams` 扁平 fallback：multiSelect 字段不生成扁平参数（避免 apply_basic_filters 的 == 误用数组）
- 测试：AdvancedSearchBuilder.spec.ts 重写用例⑤ + 新增 4 用例；ConditionValueInput.spec.ts 用例① 参数化（it.each 三字段）；torrent-batch.spec.ts 更新 tags 断言；新建 field-types-consistency.spec.ts（三表一致性守卫，10 用例）

### 回归测试抓到的语义

后端真实 DB 测试验证（最有价值的回归保护）：
- `tags='movie,4k'` 被 `contains_any(['movie'])` 命中（IN 整串匹配做不到）——证明 tags 必须用 contains_any
- `category in(['电影'])` 精确匹配 `category='电影'`，`in(['电'])` 不命中（单值列 in 是精确非子串）
- `not_contains_any(['movie'])` 对 `tags=NULL` 不命中（SQL NULL 语义：NOT(NULL LIKE) 为 unknown）

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端 pytest（advanced_search 相关） | ✅ 77/77 通过（含新增 33 用例） |
| 后端 mypy | ✅ 与 baseline 一致（29 errors，0 新增） |
| 后端 black/flake8 | ✅ 通过（PropertyMock F401 为既有 baseline，非本次引入） |
| 前端 ESLint（变更文件） | ✅ 0 error 0 warning |
| 前端 tsc --noEmit | ✅ 通过 |
| 前端 test:coverage | ✅ 19 suites / 298 tests 全绿；Branches 44.46%（>40% 门禁） |
| 前端 npm run build | ✅ 通过 |

### 明确不修的边界（已记入 evidence）

- `apply_multi_select_conditions`（*_multi 顶层字段）路径的 tags 整串语义 bug 是既有问题，前端不走该路径，本次不动。
- `contains_all`（AND 语义）UI 不暴露（避免与 in 混淆），后端保留以兼容旧模板。
- PropertyMock F401 是既有 baseline，非本次引入，不越权修。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地完成（CI 全门禁已覆盖）。

---

## 2026-07-22 - 查询模板与孤儿文件页面 UI 对齐

**任务 ID**: `v1.0.6.24`
**分支**: dev
**范围**: 仅调整查询模板与孤儿文件两个前端页面的排布、视觉层级与响应式表现，不修改业务逻辑、API、权限和清理流程。

### 完成内容

- 新增 `management-list-page.scss`，基于项目现有主题变量沉淀管理列表页共用骨架：最大内容宽度、页头、筛选面板、数据面板、表格滚动、分页、统计卡片及移动端断点。
- 查询模板页统一为“标题说明 + 页头操作 + 带标签筛选 + 列表元信息 + 数据表格”的页面结构；刷新与新建模板操作归入页头。
- 孤儿文件页使用与仪表盘/管理页一致的统计卡视觉，扫描与刷新归入页头，清理操作与选中状态归入数据面板，分页收纳到同一面板。
- 两页补充语义化标题、区域标签、明确的空状态；保留原有查询、扫描、清理、创建、编辑、删除等方法与调用链。
- 新增 `management-pages-ui.spec.ts`，以 7 项契约覆盖共用页面骨架、操作分组、统计区、分页归属、响应式样式与全局样式入口。

### 验证结果

- UI 契约测试：1 suite / 7 tests 全部通过。
- `npm run typecheck`：通过。
- 完整 `npm run lint` 与变更文件 ESLint：通过。
- `npm run build`：通过；仅有项目既有 48 条 Sass/资源体积 warning。
- 本地隔离环境浏览器验证：1440×900 桌面视口下两页内容和操作区对齐；390×844 移动视口下文档宽度等于视口宽度，宽表在内部滚动，四张统计卡改单列。
- 根 `./init.sh`：通过；仅保留 Git 工作区、jq、未激活后端虚拟环境及 Git Bash 未发现 Node 的环境提示，前端已通过 Windows Node 独立完成上述门禁。

### 工作区说明

- 本轮未执行 Git 提交。
- 启动的临时前后端验证服务及隔离数据库均已关闭并清理；既有未跟踪工具目录未改动。

---

## 2026-07-19 - 生产环境三连报错根因修复

**任务 ID**: `prod-hotfix-2026-07-19`
**分支**: dev
**范围**: 针对生产环境日志中的三类报错（连接泄漏 SAWarning / 审计日志 AttributeError / transmission-rpc v7 API）做根因分析 + 独立审查 + 修复 + 提交推送。

### 方法

3 个并行子代理对**同一份报错日志**独立做"形成结论 → 证伪/证实原假设"审查，每个假设都附反证排查清单。审查结束后再派 3 个独立 general-purpose 子代理对**我的分析结论**做独立证伪测试，重点寻找被遗漏的反证。

### 三连报错与根因（含审查修正）

**报错 1：`'Client' object has no attribute 'get_session_variables'`（WARNI 循环）**
- 根因：transmission-rpc v7.0 intentional major breaking 移除 `Client.get_session_variables()`，替代为 `client.get_session()` 返回 Session 对象，字段用 snake_case 属性（`session.download_dir`）而非旧版 dict key `"download-dir"`。
- 项目 pin `transmission-rpc~=7.0.11`，`downloader_path_scan.py:680` 是唯一遗留旧 API 调用点（其它 7 处 Transmission 调用均已用新 API）。
- 审查代理运行时验证：`hasattr(Client, 'get_session_variables')==False`、`hasattr(Client, 'get_session')==True`，结论坐实。

**报错 2：`记录审计日志失败: name`（ERROR 偶发）**
- 根因：`torrent_crud.py` 四处种子存在性查询用 `db.query(TorrentInfo.info_id).first()` 返回只含单列的 Row；hash 冲突分支 `db_torrent` 被赋值为该 Row，审计日志构造时访问 `.name/.hash/.size` 触发 SQLAlchemy 2.0 `Row.__getattr__`，`str(AttributeError)` 恰为裸名 `'name'`。
- 偶发原因：仅 hash 冲突分支触发；`.info_id` 因是选中列不报错，`.name` 是首个失败点。
- 独立审查代理用 SQLAlchemy 2.0.47 实测端到端复现：`str(Row.__getattr__('name'))=='name'`，并排除普通 NameError/AttributeError/KeyError（str 格式都不匹配）。

**报错 3：`SAWarning: garbage collector cleaning up non-checked-in connection`（traceback 误指 transmission_rpc/torrent.py:259）**
- 根因：三个 Service 类自建 `SessionLocal/AsyncSessionLocal` 从不 close；`NullPool+aiosqlite` 下连接由 GC 周期性回收，恰好命中 Transmission RPC JSON 解析循环栈帧 → traceback 误指 `super().__init__(fields=fields)`。
- **审查关键修正**：原分析把三个 Service 并列为"本次报错的根因"，但 `recycle_bin_service` 是**同步** `SessionLocal`（同步 sqlite 方言 `is_async=False`），按 `pool/base.py:952` 不进入该 SAWarning 分支；**直接元凶是 `SeedTransferService` 内嵌 `TorrentFileBackupManagerService` 自建的 async session**。`recycle_bin_service` 的同步泄漏是另一类问题（`database is locked` 风险），需单独修。
- **NullPool 不豁免该警告**：审查代理读 `sqlalchemy/pool/base.py:951-952` 源码确认判定只看方言 `is_async`，与 pool 类型无关。

### 修复（7 文件）

| 修复点 | 文件 | 设计 |
|--------|------|------|
| P0-1 `TorrentFileBackupManagerService.aclose()` | `services/torrent_file_backup_manager.py` | `_owns_db`（仅自建才关）+ `_closed`（幂等）双标志 |
| P0-2 `SeedTransferService.aclose()` | `services/seed_transfer_service.py` | 删除死代码 `self.async_db`（无任何方法读取）+ `aclose()` 级联关闭 backup_manager |
| P0-3 seed_transfer 2 端点 try/finally | `api/endpoints/seed_transfer.py` | 调用 `service.aclose()` |
| P0-4 `RecycleBinService.close()` | `services/recycle_bin_service.py` | 同步版双标志 close() |
| P0-5 recycle_bin 4 端点 try/finally | `api/endpoints/recycle_bin.py` | 调用 `service.close()` |
| P1 torrent_crud 4 处 query | `api/endpoints/torrent_crud.py` | `db.query(TorrentInfo.info_id)` → `db.query(TorrentInfo)` |
| P2 transmission-rpc v7 API | `tasks/scheduler/downloader_path_scan.py` | `get_session_variables()+['download-dir']` → `get_session()+.download_dir` |

**为何用 `_owns_db`/`_closed` 标志而非 `self.db = None`**：避免误关闭外部传入的共享 session + 保证幂等；同时 `self.db = None` 会触发 mypy `None → Session` 类型错误（`_closed: bool` 无此问题）。

### 验证结果

| 验证项 | 结果 |
|---|---|
| flake8（7 文件） | ✅ 通过 |
| black（7 文件） | ✅ 通过 |
| mypy（3 service 文件） | ✅ **92 errors，与 baseline 完全一致（0 新增）** |
| 相关 pytest（5 套件 / 55 用例） | ✅ 55 全通过 |
| 全量 pytest（排除 master 同样 hang 的文件） | ✅ **2146 passed, 1 skipped, 0 failed**（189s） |
| `test_torrent_sync_review.py::test_cached_client_exception_handled` | ⚠️ 已 git stash 验证 master baseline 同样 hang，与本次修改无关 |

### Git 状态

- 3 个独立 commit 已推送至 `origin/dev`（`3348016..7c4caee`）：
  - `62404e7` P0 连接泄漏修复（5 文件，+217/-124）
  - `fc04ab8` P1 审计日志 AttributeError（1 文件，+16/-4）
  - `7c4caee` P2 transmission-rpc v7 API 升级（1 文件，+8/-5）
- 本轮文档（progress.md + feature_list.json + .gitignore）将单独成 1 个 commit。

### 副带修复

- `backend/.gitignore` 补 `.pytest-*/` 规则：pytest 中断留下的临时目录（`.pytest-final-all-*` / `.pytest-p1-close-*`）此前未被忽略，且因 Docker Desktop WSL2 挂载锁无法物理删除；通过 gitignore 规则避免污染 git status 与误纳提交。

### 遗留技术债（本次不动）

- 约 92 个 mypy 历史错误（项目预存在，与本次修改无关）。
  - **订正（2026-07-19 code review 后）**：92 是 3 个 service 文件局部口径；实测同口径已降到 **81**，全量 `mypy app` 实为 **1484 错误 / 120 文件**（约 60% 是 SQLAlchemy typed Column 噪声，非真 bug）。后续 hotfix 沿用"修改文件 mypy 数 ≤ baseline"局部守则即可，**不引入**全量 mypy CI 门禁。
- ~~`cron_executor.py:80` 的 `db = SessionLocal()` 是否 finally close 需独立排查~~ **已核实（2026-07-19）**：第 80-107 行有完整 `try/finally: db.close()`，结构安全无泄漏。该审查项是预防性提示，已闭环。
- 真实环境压测（连接泄漏消除验证）需运维监控 SAWarning 在长时间运行后是否复现。

---

## 2026-07-19 - prod-hotfix code review 后续 issue 跟踪清单

**任务 ID**: `prod-hotfix-2026-07-19-followup`
**分支**: dev
**范围**: 3 个独立子代理对 prod-hotfix 完成 code review 后，再派 2 个独立评估代理对剩余 11 项（A-K）做 ROI 分级，挑选值得作为后续 issue 跟踪的项；低成本闭环项立即执行。

### 方法

- **评估代理 1**（代码层）：评估 A-E 五项，实证（grep + 读源码）后给出"建议跟踪 / 不跟踪 / 调研后再定"分级 + 工作量估算
- **评估代理 2**（测试/技术债层）：评估 F-K 六项，实证（实跑 pytest + mypy）后给出同分级
- 两个代理结论高度趋同，未出现矛盾判断

### 立即执行的低成本闭环（本次会话已做）

| 项 | 处理 | commit |
|----|------|--------|
| **C** seed_transfer_service.py:384 变量名遮蔽 | 改名为 `local_backup_manager` | 本次 |
| **B** torrent_backup.py:549 死代码（构造即丢弃） | 删除 | 本次 |
| **I** mypy 历史债务 | progress.md 订正度量口径（92 → 81 局部 / 1484 全量） | 本次 |
| **E/K** cron_executor.py:80 排查 | 实证已正确 close，progress.md 标记闭环 | 本次 |

### 推荐立项跟踪（按优先级）

| 优先级 | Issue 标题 | 工作量 | 价值 |
|--------|-----------|--------|------|
| **P1** | `[test] 启用 test_torrent_sync_review.py 5 个 skip 测试` | 0.5-1 天 | ROI 最高；patch `qbClient/trClient` fallback 路径让 ConnectionError 立即 raise，根治 hang；启用后多 5 个真实回归锚点（fallback 建连异常处理） |
| **P2** | `[torrent-crud] hash 冲突分支审计语义 + 下载器重复调用` | 半天 | 真实业务影响：用户上传已存在 hash 种子时仍调 `add_torrent`（网络/认证开销）+ 审计写 `{"status":"added"}` 但实际可能未新增；运维审计会反复质问 |
| **P2** | `[test] 补 DownloaderPathScanTask.execute() 主流程测试` | 0.5-1 天 | 841 行任务类除 `_get_default_path_from_downloader` 外零覆盖；`_update_path_mapping`/`_sync_default_path` 已接入 `db_write_scope`（sync-resource-governance.2.6）但无锚点；目标：happy path + db_write_scope 行为 + 1-2 个 fallback 分支，不做端到端真实 RPC |
| **P3** | `[backup-manager] aclose 后访问 repository 加防御` | 1-2 小时 | 治理闭环：当前 `aclose()` 关 self.db 但不清 self.repository，close 后访问会触发 SAWarning（SQLAlchemy 自动重开无归属连接）；生产路径不触发但 API 不安全；建议方案 A：`aclose` 中 `self.repository = None` |
| **P3** | `[test] recycle_bin fixture 加真实 Session 守卫` | 0.5 天 | 防御性：当前 `patch("app.database.SessionLocal", return_value=db_session)` 若被改成 MagicMock，9 个测试会"全绿但什么都没测"；加 1 个断言 fixture 注入真实 Session 的守卫测试 |

### 明确不立项（含理由）

| 项 | 不立项理由 |
|----|-----------|
| **B** torrent_backup/torrents_async 12 处统一 close | `torrent_backup.py` 用 `async with AsyncSessionLocal()`（自动关），`torrents_async.py` 4 处 `_owns_db=False`（aclose 本就是 no-op）；**当下不泄漏**，"未来风险"建议转文档约定而非改 12 处代码 |
| **F** torrent_crud /add /add-batch 端点 e2e | 核心 bug 已被 `test_torrent_crud_query.py` 5 用例 + mutation 反向锚定直接覆盖；端点 e2e 需 mock 5 个外部依赖 + 跑 30 秒重试循环，1.5-2 周换不到新回归类型；备注：待 TestClient 基础设施沉淀后再做 |
| **I（治理）** mypy 全量治理 | 1484 错误 60% 是 SQLAlchemy typed Column 噪声非真 bug；消除需 declarative → Mapped 全量重构（数周-数月），收益不抵成本；仅订正 progress.md 口径 |
| **K（排查）** cron_executor.py:80 | 已实证第 80-107 行有完整 `try/finally: db.close()`，无泄漏；审查提示是预防性，已闭环 |

### 评估方法学说明

两个评估代理的关键反证（避免后续审查踩坑）：
- **J 的 skip 数量**：实测 5 个（class 级 skip 覆盖 2 个 method + 3 个 method 级 skip），不是 4 个。
- **I 的 mypy 口径**：progress.md 的"92"是 **3 service 文件局部口径**（实测现 81），全量是 1484——评估时必须区分。
- **K 的代码现状**：第 80 行 `db = SessionLocal()` 配套第 107 行 `finally: db.close()`，结构安全。
- **H 的真实风险**：本次新增 `test_service_close_endpoint.py` 已用 `wraps=` spy 范式绕开脆弱性；残留风险是"fixture 被改成 MagicMock"，加守卫测试即可，无需重写 fixture。

---

## 2026-07-18 - 传统分页预设与展开箭头修正

**任务 ID**: `v1.0.6.22`
**分支**: dev
**范围**: 修复传统模式分页组合框只显示当前值的问题，补充大分页预设并增加展开/收起箭头。

### 完成内容

- 定位到 `el-autocomplete` 聚焦时用当前输入值 `20` 过滤候选，导致下拉只剩一个预设；候选函数改为始终返回完整预设。
- 分页预设调整为 20/50/100/500/1000，继续支持 1–100,000 手动输入、Enter/失焦生效及普通/重复任务数据源保持。
- 组合框右侧增加方向箭头：收起时向下、展开时向上，可用鼠标、Enter 或 Space 切换；聚焦、失焦和选择预设时同步状态。
- 扩展组件桩与回归断言，直接以当前值 `20` 查询并验证五个预设，覆盖箭头展开、收起、再次展开以及选择预设后的分页请求。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标分页/组件/虚拟窗口回归 | ✅ 3 suites / 18 tests |
| 前端全量 Jest | ✅ 14 suites / 253 tests |
| TypeScript / 完整 ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 48 条 Sass/资源体积 warning） |
| 根 `init.sh` | ⚠️ 当前 Windows 无 WSL，系统 `bash.exe` 无法执行 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮修改已随当前任务提交、尚未推送；`dev` 相对 `origin/dev` ahead 5。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页分页组合框与虚拟滚动

**任务 ID**: `v1.0.6.21`
**分支**: dev
**范围**: 合并传统模式的预设/手动分页输入，并将列表锁定为固定视口，超长当前页采用虚拟滚动。

### 完成内容

- 分页栏改为单个 `el-autocomplete`：聚合 10/20/50/100 预设和 1–100,000 自定义输入，选择预设、按 Enter 或失焦均走同一归一化入口。
- 改分页大小后统一回到第 1 页；普通列表和重复任务仍分别使用原有数据源与服务端分页，不自动跨页加载。
- 传统页高度与列表模式对齐为 `calc(100vh - 84px)`；表格容器通过 `flex: 1 1 0`、`height: 0` 锁定剩余可视高度，内容仅在容器内部滚动。
- 新增表格专用虚拟窗口：固定 32px 行高、上下各 8 行缓冲，使用语义化占位行维持完整滚动高度，只切片渲染当前可视窗口。
- 通过 `ResizeObserver` 同步真实视口高度，滚动更新由 `requestAnimationFrame` 合帧；分页、筛选、排序和切换重复任务时重置到列表顶部。
- 新增 4 项纯函数边界回归，并扩展组件测试覆盖单一分页框、预设/自定义输入、100,000 上限、重复任务数据源保持和 1000 条长列表虚拟窗口。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标分页/组件/虚拟窗口回归 | ✅ 3 suites / 18 tests |
| 长列表窗口 | ✅ 1000 条、320px 视口仅渲染 26 条可视/缓冲记录 |
| 前端全量 Jest + coverage | ✅ 14 suites / 253 tests；Statements 52.48%、Branches 44.34%、Functions 44.75%、Lines 51.89% |
| TypeScript / 完整 ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 48 条 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| 根 `init.sh` | ⚠️ 当前 Windows 无 WSL，系统 `bash.exe` 无法执行 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮修改已随当前任务提交、尚未推送；`dev` 相对 `origin/dev` ahead 4。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页回归覆盖补强

**任务 ID**: `v1.0.6.20`
**分支**: dev
**范围**: 对传统种子页近期交互、布局、分页和元数据补全改动补充组件级与后端分支回归。

### 完成内容

- 新增 `TraditionalView` 挂载测试，直接覆盖仅保留“删除”四级下拉、元数据默认 Tracker 且无“常规”页签，以及完整分类/标签映射。
- 覆盖自定义分页 Enter/失焦生效、100,001 钳制到 100,000、应用后回到第 1 页；验证重复任务模式翻页、改页大小和刷新均不会退回普通列表请求。
- 增加悬浮详情层位于分页上方、关闭后不接收指针事件，以及左侧分类/标签区可纵向滚动的布局契约。
- 将 `TraditionalView.vue` 纳入 Jest 覆盖率采集；为兼容 Vue 2 测试模板编译器，将模板中的可选链改为等价显式判空，运行行为不变。
- 后端覆盖 qB hash 归一化、去重及 100 条分批，正常/重试增量详情水合，Transmission 缓存客户端实时元数据，以及缓存快照或下载器 API 失败时返回空结果的降级路径。
- 重复任务 API 新增 Transmission 两下载器同 hash 元数据集成断言；分类/标签聚合新增 `dr=1` 与 `deleted_at` 记录排除回归。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 前端 `TraditionalView` 组件回归 | ✅ 7/7 passed |
| 前端全量 Jest + coverage | ✅ 13 suites / 246 tests；Statements 51.91%、Branches 43.26%、Functions 44.63%、Lines 51.34% |
| 后端重复任务/标签聚合/元数据专项 | ✅ 78/78 passed |
| 后端本次新增可执行行 | ✅ `torrents_async.py` 9/9；`torrent_metadata.py` 157/199（78.9%） |
| 后端 flake8 / 目标 Ruff 格式 | ✅ 通过 |
| TypeScript / 完整 ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮补充已随当前任务提交、尚未推送；`dev` 相对 `origin/dev` ahead 3。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页悬浮元数据与自定义分页大小

**任务 ID**: `v1.0.6.19`
**分支**: dev
**范围**: 纠正传统模式元数据面板位置，并为普通列表与重复任务统一增加最大 100,000 的自定义分页大小。

### 完成内容

- 元数据面板改为表格区域内的绝对定位悬浮层，底边固定在分页栏上方；打开时覆盖列表底部而不改变表格或分页布局，关闭时不占空间且不接收指针事件。
- 分页栏保留 10/20/50/100 预设，新增“每页 [输入框] 条”；按 Enter 或失焦生效，并回到第 1 页。
- 自定义值统一归一化为整数 1–100,000：空值或非数字保持当前值，越界值自动钳制。
- 普通种子列表 `limit` 与重复任务 `pageSize` 的后端上限同步放宽至 100,000，避免前端填写后被接口 422 拒绝。
- 新增前端纯函数边界测试，以及两个后端接口的 100,000/100,001 边界回归。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端普通列表/重复任务/标签聚合/元数据专项 | ✅ 71/71 passed |
| 后端 flake8 / 目标 Ruff 格式 | ✅ 通过 |
| 后端目标 mypy | ✅ 新增重复元数据端点与服务无错误；其他既有端点仍有历史债务 |
| 前端目标分页与状态契约 | ✅ 7/7 passed |
| 前端全量 Jest | ✅ 12 suites / 239 tests |
| TypeScript / ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮未执行提交或推送；分支仍包含此前已提交但未推送的 1 个提交。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页删除、侧栏、重复元数据与下方详情修复

**任务 ID**: `v1.0.6.18`
**分支**: dev
**范围**: 传统模式交互调整，并修复重复任务空元数据的查询兜底与 qB 增量同步根因。

### 完成内容

- 删除传统模式普通批量删除入口；保留四级删除下拉，将“按等级删除”改名为“删除”。
- 左侧过滤区补齐 flex 最小高度和纵向滚动；分类/标签接口同时返回管理项及当前活动种子实际使用值。
- 重复任务接口从同 hash 数据库记录回填名称/大小，并仅通过 `app.state.store` 缓存客户端按下载器补齐缺失的实时元数据，下载器离线时保持数据库结果可用。
- qB `sync/maindata` 增量响应写库前批量获取完整详情，避免缺失字段再次把名称、路径、大小、状态等覆盖为空。
- 传统模式详情面板移至种子列表下方，删除“常规”页签，仅保留 Tracker、文件、Peers，默认显示 Tracker；重复任务模式保持独立分页与刷新状态。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端重复任务/标签聚合/元数据同步专项 | ✅ 40/40 passed |
| 后端目标 flake8 / mypy | ✅ 通过 |
| 后端格式 | ✅ `ruff format --check` 通过；本机 `black` 进程仍会卡住 |
| 前端目标契约测试 | ✅ 3/3 passed |
| TypeScript / ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| 根 `init.sh` | ⚠️ 当前 Windows 无可用 WSL，`bash.exe` 无法执行 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮未执行提交或推送；分支仍包含此前已提交但未推送的 1 个提交。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统模式活动筛选迁移至左侧状态

**任务 ID**: `v1.0.6.17`
**分支**: dev
**范围**: 仅调整种子列表传统模式，将工具栏“活动”入口迁移为左侧状态项；列表模式保持不变。

### 完成内容

- 删除传统模式工具栏顶部的“活动”复选框及其专用样式。
- 左侧“状态”过滤器顺序调整为“全部 → 活动中 → 做种中 → 其余状态”。
- “活动中”使用仅限界面的虚拟状态值，继续映射既有 `showActiveOnly`，请求层仍发送后端 `active_only=true`，未伪装成普通 `status` 参数。
- 左侧状态保持单选语义：选择“活动中”会清空普通状态；选择普通状态或“全部”会关闭活动筛选。
- 提取传统状态过滤纯函数并新增 3 项回归测试，覆盖固定顺序、活动映射和互斥切换。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标回归测试 | ✅ 3/3 passed |
| 前端全量 Jest | ✅ 11 suites / 235 tests |
| TypeScript | ✅ `tsc --noEmit` |
| ESLint / Vuex lint | ✅ 通过 |
| 生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| `git diff --check` | ✅ 通过 |
| 根 `init.sh` | ⚠️ 已尝试；当前 Windows 环境未安装 WSL，系统 `bash.exe` 无法执行 |

---

## 2026-07-17 - 下载器设置端点 mypy 类型债务清理

**任务 ID**: `v1.0.6.16`
**分支**: dev
**范围**: 在不改变下载器设置 API 路径、响应和业务流程的前提下，清理 `downloader_settings.py` 的 11 项 mypy 错误。

### 完成内容

- `verify_downloader_exists` 使用 `scalar_one()` 读取 COUNT 标量，消除 SQLAlchemy Row 的 `count` 方法与 SQL 别名冲突。
- 删除两个未使用的 `Request` 参数；其余三个读取请求体的端点改为 FastAPI 必需 Request 注入，消除 5 项隐式 Optional。
- 为 `response_data` 增加 `dict[str, Any]` 注解。
- 将 INSERT/UPDATE 的执行结果收紧为 `CursorResult[Any]`，合法访问 `lastrowid` 和 `rowcount`。
- qBittorrent 与 Transmission 分别使用 `qb_client`/`tr_client` 局部变量，避免两种 SDK Client 类型互相污染。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标 mypy | ✅ 11 errors → `Success: no issues found` |
| 下载器设置 + 认证专项 | ✅ 33/33 passed |
| 后端全量 pytest | ✅ 2111 passed / 1 skipped |
| 变更文件 flake8 / git diff --check | ✅ 通过 |

### Git 状态

- 限速修复已本地提交：`2e03ce4 fix(fullstack): 修复下载器限速同步应用`。
- `origin/dev` 指向外部 GitHub；即使用户知情确认，当前安全策略仍硬性拒绝网络推送，未尝试绕过。需用户在本机手动执行 `git push origin dev`。

---

## 2026-07-17 - 下载器全局限速同步应用修复

**任务 ID**: `v1.0.6.15`
**分支**: dev
**范围**: 修复下载器管理页保存上传/下载限速后未同步应用的问题，同时覆盖 qBittorrent、Transmission、分时段调度回退与前端状态恢复。

### 根因与修复

- 后端保存接口在解析 `schedule_rules` 时复用了全局 `dl/ul_speed_limit` 与单位变量，导致最后一条规则覆盖 `downloader_settings` 的全局值；现已将全局与规则变量完全隔离，并用 `is None` 保留合法的 0 值。
- SQLite 原始 SQL 对 `SQLEnum(IntEnum)` 可能返回字符串 `"0"/"1"`，SQLAlchemy 历史记录也可能使用枚举名；旧整数映射会把 MB/s 静默当成 KB/s。现由 `SpeedUnitEnum.from_value()` 统一兼容数字、数字字符串、枚举名及 KB/s/MB/s 后再传给两个下载器适配器。
- 定时调度在没有生效规则时计算出全 0 并应用为不限速；现以下载器全局限速为基线，规则只覆盖自身启用且大于 0 的方向，空窗期自动恢复全局值。
- 前端加载设置时丢弃 `enable_schedule`，随后按“存在历史规则”推断为启用；现显式保存并恢复后端开关，缺失字段默认关闭。
- 修正原 15 项调度测试中钉死变量遮蔽错误行为的预期，并补充 qBittorrent/Transmission、单位字符串、调度回退及前端开关契约回归。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 下载器设置 API | ✅ 17/17 passed（含 qBittorrent/Transmission） |
| 最终后端专项回归 | ✅ 48/48 passed（API 17、枚举 16、调度 15） |
| 后端全量 pytest | ✅ 2111 passed / 1 skipped |
| 前端全量 Jest | ✅ 10 suites / 232 tests |
| TypeScript / ESLint / Vuex lint | ✅ 全部通过 |
| 生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 变更文件 flake8 / git diff --check | ✅ 通过 |
| 根 `init.sh` | ✅ 退出 0（Git Bash PATH 无 Node 的既有警告由独立前端门禁覆盖） |

### 已知工具基线

- `black 24.10.0` 在当前 Python 3.13 环境中连 `--version` 都会卡住并超时，故本轮无法执行 black 门禁；不是代码格式错误信号。
- 针对三个后端生产文件运行 mypy 时，仅 `downloader_settings.py` 报 11 项既有类型债务；本次新增枚举与调度服务代码没有 mypy 报错。

---

## 2026-07-17 - 种子同步添加时间显示 1970 回归修复

**任务 ID**: `v1.0.6.14`
**分支**: dev
**范围**: 排查同步种子的添加时间显示为 1970 年，并以失败回归测试驱动最小修复。

### 根因与修复

- 后端同步链路正常：下载器时间写入 `TorrentInfo.added_date`，列表 API 按约定序列化为 ISO 8601 字符串。
- 前端共享 `formatDate` 对所有字符串执行 `parseInt`；`2026-07-17T10:20:30` 被截断为 `2026`，再按 Unix 秒时间戳格式化，因此显示为 `1970-01-01 08:33:46`。
- 新增失败回归用例，修复前为 1 failed / 37 passed，并精确得到上述 1970 年结果。
- 修复后只有完全匹配数字格式的字符串按秒/毫秒时间戳处理；ISO 8601 字符串整体交给 `Date` 解析，纯数字字符串行为保持兼容。
- 回归测试增强后将 ISO 与数值时间戳断言拆分，补充带 `Z`、显式时区偏移、小数秒及毫秒级数值字符串覆盖。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标回归测试 | ✅ Asia/Shanghai、UTC、America/New_York 均为 42/42 passed |
| 全量 Jest + coverage | ✅ 9 suites / 229 tests |
| Statements / Branches | ✅ 50.15% / 42.01% |
| Functions / Lines | ✅ 43.04% / 49.60% |
| TypeScript | ✅ `tsc --noEmit` |
| ESLint / Vuex lint | ✅ 通过 |
| 生产构建 | ✅ 通过（48 条既有 Sass/资源 warning） |

---

## 2026-07-16 - 前端覆盖率与关键契约测试整改

**任务 ID**: `v1.0.6.13`
**分支**: dev
**范围**: 建立可信覆盖率门禁并补高风险回归；不以生成图标、声明文件或纯展示代码抬高数字。

### 完成内容

- Jest `roots` 从 `tests/unit + src/components` 扩展为 `tests/unit + src`，避免新测试在 API、Store、页面目录被静默漏收集。
- 覆盖率口径为全量业务 TypeScript，加已纳入组件回归的 `AdvancedMultiSelect.vue`、`AdvancedSearchBuilder.vue`；排除 `.d.ts`、生成图标和启动入口。
- 新增 `test:coverage`，输出 text-summary、HTML、LCOV；Statements/Branches/Functions/Lines 全局阈值均为 40%。
- 根 CI 改为执行覆盖率门禁，并始终上传 `frontend-coverage` artifact（保留 7 天）。
- 新增 API 请求契约测试：种子、孤儿文件、通知、认证、审计、标签、回收站、定时任务、Tracker、下载器。
- 新增共享工具测试：分页/对象规范化、错误消息、格式化、防抖/节流、状态、下载器类型、校验与主题事件。
- 新增 Vuex 测试：视图模式、筛选面板、侧边栏和设备状态及持久化。
- 新增高级搜索组件测试：条件组生命周期、操作符和值转换、分组/扁平参数、模板深拷贝、事件与保存流程。
- 测试驱动修复两个真实缺陷：`normalizeTorrent` 原对象展开顺序会覆盖规范化状态和空值默认值；`queuedDL` 未进入状态规范化分支。

### 验证结果

| 验证项 | 结果 |
|---|---|
| Jest | ✅ 8 suites / 222 tests（原 4 / 142） |
| Statements | ✅ 50.03%（门禁 40%） |
| Branches | ✅ 42.01%（门禁 40%） |
| Functions | ✅ 43.04%（门禁 40%） |
| Lines | ✅ 49.47%（门禁 40%） |
| TypeScript | ✅ `tsc --noEmit` |
| 目标 ESLint | ✅ 0 error（高级搜索组件 6 条既有 warning） |
| 生产构建 | ✅ 通过（48 条既有 Sass/资源 warning） |

### 边界

- Vue 2 的 Jest 模板编译器无法采集含模板可选链的历史 SFC；本轮先对全量业务 TS 和两个已测试关键 SFC 建立可执行门禁，其余 SFC 随组件测试补齐逐步纳入，避免静默漏采导致虚高。
- 浏览器 E2E 与真实前后端集成测试仍未进入 CI，本轮已在 README 明确标记，不再宣称现有覆盖。

---

## 2026-07-16 - 全栈回归测试质量整改（P0）

**任务 ID**: `v1.0.6.12`
**分支**: dev
**方法**: 分别审查前后端回归质量，按用户要求由子代理复核审查结论与整改方案，再按“数据库隔离 → 活动快照语义 → 前后端接线测试 → Jest/TypeScript → 根 CI”实施。

### 完成内容

- pytest 在导入应用前强制切换到 `.pytest-runtime/process-<pid>/app.db`，执行真实 Alembic；拒绝指向 `backend/config/app.db`，退出时释放 engine 并清理运行目录。
- `OrphanScanner` 支持注入同步/异步 session factory，测试不再隐式使用生产全局 Session。
- 活动种子缓存显式区分 `not_ready/expired/partial/ready_empty/ready`；冷启动、过期或部分下载器失败返回 `206`，权威空集仍返回 `200`。
- `active_only` 只消费完整快照；大集合使用每请求 SQLite TEMP 表联接列表与计数查询，避免绑定参数上限和 OR-IN 膨胀。
- 两个种子视图收到 `206` 时保留现有列表，刷新完整速度快照后受控重试；后端统一返回 `list/total/pageSize` 和快照元数据。
- Jest 恢复 Vue 组件与性能测试收集，修复 `AdvancedMultiSelect` 属性初始化/虚拟滚动边界/搜索行为；TypeScript 请求响应模型补齐。
- 新增根 `.github/workflows/regression.yml`，统一执行后端架构检查、pytest+覆盖率，以及前端 typecheck、完整 Jest 和生产构建。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端全量 pytest + coverage | ✅ 2089 passed, 1 skipped；40.58%（阈值 40%） |
| 活动筛选专项 | ✅ 21 passed（含 600 键低变量限制与 206 握手） |
| 真实业务数据库隔离 | ✅ 两轮全量测试前后 SHA256/mtime 完全不变 |
| 后端格式/静态门禁 | ✅ 变更文件 black/flake8；架构检查；git diff --check |
| 前端 Jest | ✅ 4 suites / 142 tests |
| 前端 TypeScript | ✅ `tsc --noEmit` |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源 warning） |
| 根 init.sh | ✅ Git Bash 下退出 0（其 PATH 无 Node 的警告由独立前端门禁覆盖） |

### 已知基线债务（未扩大本次范围）

- `mypy app` 当前仍有 1534 个跨 123 个既有文件的错误，根 CI 暂未启用该全量门禁。
- 全量 `flake8 app tests` 仍会命中多个既有测试文件；本次修改文件为 0 错误。
- 约 248 个历史 Vue SFC 语义类型错误仍待专项治理；当前严格 `tsc` 覆盖 `.ts/.tsx`，SFC 由 webpack 与 vue-jest 编译/行为测试覆盖。

---

## 2026-07-12 - v1.0.6 孤儿文件清理安全闭环修复

**任务 ID**: `v1.0.6.11`
**方法**: 先补 RED 回归，再修生产链；完成后由 3 个子代理分别复核架构、安全和测试有效性。

### 完成内容

- 共享 `TorrentManifestBuilder` 直接枚举 qBittorrent/Transmission 实时 torrent inventory；任何下载器缺失、不可用或部分响应均 fail-closed，权威空 inventory 保持合法。
- API、前端 preview/confirm、手动与自动清理全部绑定最新 `scan_id`；列表不再回退展示旧 completed 批次。
- 父子扫描根使用全局 expected 集合；单文件 stat 失败整批失败；扫描明细、候选对账和 completed 状态在同一事务提交。
- 手动与自动清理统一进入隔离区；候选必须属于实时授权扫描根，并完整匹配 size/mtime_ns/device/inode。
- 隔离目标使用同文件系统私有 UUID 目录和无覆盖 rename；操作 journal 预写 pending 状态并支持 rename/remove 后崩溃恢复。
- purge 每个文件重新构建 manifest，先原子移动为 tombstone、复核身份后才 unlink；新增每日 purge 任务。
- 统一 `orphan_maintenance` lease 使用独立 session、原子抢占、心跳续租和危险操作前所有权检查。
- 新增通知补偿任务，每小时补发 completed 且缺少 dedupe 通知的扫描结果。
- 前端冻结 previewScanId，确认清理必须使用同一预览批次。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 安全/迁移/生产接线回归 | ✅ 152 passed, 1 skipped |
| 后端全量 pytest | ✅ 2068 passed, 1 skipped |
| 后端 flake8 + git diff --check | ✅ 通过 |
| Alembic upgrade/downgrade/upgrade | ✅ 通过 |
| 前端目标 eslint | ✅ 通过 |
| 前端生产 build | ✅ 通过（48 个既有 Sass/体积 warning） |
| 根 init.sh | ⚠️ 当前 Windows 环境无 Git Bash/WSL，未执行 |

---

## 2026-07-11 - v1.0.6 孤儿文件管理语义重做（严格 TDD 5 阶段）

**任务 ID**: `v1.0.6.7`~`v1.0.6.10`（语义重做，5 阶段严格 TDD）
**分支**: dev
**方法**: 严格遵循「先提交回归测试、确认旧代码失败，再修改生产代码」，每阶段独立 commit

### 语义重做背景

基于代码审查发现的缺陷：旧 v1.0.6 扫描器在下载器清单/路径映射/扫描根不完整时**静默返回 completed**（fail-open），导致真实文件被误报为孤儿；自动清理依据文件 mtime（可被篡改）；无跨进程互斥；无扫描完成通知。

### 5 阶段交付（每阶段独立 commit）

**Phase 1: 失败回归测试（commit c9e048a）**
- 新增 7 文件：conftest.py（async_orphan_db fixture）+ 5 测试文件 + 扩展 scanner 测试
- A/B/C/D/E/F/G/H 共 8 组 53 例，全部在旧代码上失败（34 failed / 34 passed / 1 skipped）
- 失败证据：fail-closed 缺失（5 例）+ 模块不存在（ImportError）+ API 签名不匹配（TypeError）

**Phase 2: 扫描器最小修复（commit e54f616）**
- A/B/C 组 36 测试转绿（19 旧 + 17 新）
- 修复：状态重置 + 绕开 DeleteAdapter + SYNC lane + 逐种子转换 save_path + 规范化路径（normcase+normpath）+ fail-closed（OrphanScanIncompleteError）+ 隔离区排除

**Phase 3: 生命周期 + 迁移（commit 207af69）**
- 迁移 b075727f7182：orphan_current_candidate 表 + orphan_operation_lease 表 + notification.dedupe_key 列
- OrphanLifecycleService：reconcile_candidates（只有 completed 推进）+ get_purgeable_candidates（连续孤儿时间）
- D 组生命周期推进 5 测试转绿；表数 26→28

**Phase 4: 清理安全 + 隔离区 + lease（commit 2243e4c）**
- orphan_lease.py（跨进程 lease，db 参数注入）+ orphan_quarantine.py（隔离区 + verify_file_identity）
- orphan_file_service.py 重构：新鲜度门禁 + 实时 manifest fail-closed + scan_id 参数 + 隔离区工作流
- E/F/H 组 17 测试转绿

**Phase 5: 通知接入 + 全量门禁（commit 本次）**
- orphan_notification.py：notify_scan_completed（dedupe_key 幂等 + 失败不回滚）
- create_notification 双层去重（查询层 + DB 层 IntegrityError）
- 迁移 b075727f7182 notification 表存在守卫（修复 frozen schema 快照旧库）
- G 组 6 测试转绿；test_db_rollback_scenarios.py REV_HEAD 更新

### 最终语义（全部达成）

| 语义 | 实现 |
|------|------|
| 自动清理依据「连续成为孤儿的时间」 | OrphanCurrentCandidate.last_seen_at - first_seen_at >= 30 天 |
| 任一清单不完整整批失败 | OrphanScanIncompleteError → status=failed |
| 自动清理先移隔离区保留 7 天 | quarantine_file → purge_after = now + 7d |
| 手动清理不绕过实时复核 | verify_file_identity + manifest fail-closed |
| 最新扫描 running/failed 禁止清理 | _check_cleanup_allowed |
| 跨进程 lease 保护 | orphan_operation_lease 表 + acquire/release |
| 成功扫描 >0 创建通知 | notify_scan_completed + dedupe_key 幂等 |
| 通知失败不改扫描结果 | try/except 只记 error |

### 验证结果

| 验证项 | 结果 |
|--------|------|
| 全量 pytest tests/ | ✅ **2043 passed, 0 failed, 1 skipped** |
| mypy app/ | ✅ 无新增错误（预存在 ORM 描述符债） |
| black --check app/ tests/ | ✅ 通过 |
| flake8 app/ tests/ | ✅ 通过 |
| ./init.sh | ✅ 通过 |

---

## 2026-07-10 - v1.0.6 孤儿文件管理与路径维护（合并三版本）

**任务 ID**: `v1.0.6`（合并原 v1.0.6 孤儿文件 + v1.0.7 路径扫描增强 + v1.1.0 自动清理）
**分支**: dev
**计划文件**: PLANS/v1.0.6.md（基于代码现状重写，废弃 2024-04-22 旧计划）

### 合并理由

原 v1.0.6 + v1.0.7 + v1.1.0 本质是一个功能集群（孤儿文件发现→路径扩展→自动清理），拆三版本导致接口割裂和重复工作。合并为单一版本一次性交付完整链路。

### 旧计划废弃原因（4 个计划文件全部过时）

1. 前端用 Composition API（`defineComponent`+`setup()`），违反项目强制 Options API 约束
2. v1.1.0 的 AutomationService 与现有 cron_executor（APScheduler + task_profiles）功能完全重叠
3. v1.0.7 引用不存在的 PathMapping/PathMappingRule ORM 模型（实际是 BtDownloaders 表的 Text 字段）
4. 所有计划未考虑 sync-resource-governance 治理体系（db_write_scope + task_profiles 三处同步）

### 关键设计决策（用户确认）

- 扫描路径来源：种子 save_path + 下载器路径映射配置（path_mapping JSON external）
- 清理策略：自动清理超期（物理删除 + 审计日志）+ 手动清理（用户勾选）
- 文件清单来源：实时调下载器 API（复用 get_torrent_files 适配器，经 INTERACTIVE lane）
- 定时任务：每周扫描+清理合一（task_type=4 + task_profiles heavy_sync）
- 一并修复 CleanupTaskExecutor 预存 bug（_query_level3/4_torrents 未定义）

### 交付清单（6 阶段）

**Phase 1: 后端数据模型与迁移**
- `app/models/orphan_file.py` — OrphanScanResult + OrphanFile 两表
- `alembic/versions/c3f1a8b7d902_add_orphan_file_tables.py` — 迁移（含 inspect 守卫）
- `alembic/env.py` — 补模型 import
- `app/core/config.py` — 新增 4 项配置（ORPHAN_AUTO_CLEANUP_DAYS=30 等）

**Phase 2: 后端扫描引擎与服务**
- `app/services/orphan_scanner.py` — OrphanScanner（路径收集+文件清单+inode去重+遍历判定）
  - to_thread 移出文件系统遍历；call_downloader_api(INTERACTIVE) 获取文件清单
  - db_write_scope 串行化 DB commit；复用 UnifiedPathMappingService 路径转换
- `app/services/orphan_file_service.py` — OrphanFileService（查询/预览/手动清理/自动清理）
  - 文件删除参考 recycle_bin_service.py（UNC 兼容 + os.remove + 审计日志）
- `app/torrents/audit_enums.py` — 新增 3 个审计枚举（ORPHAN_SCAN/CLEANUP/AUTO_CLEANUP）

**Phase 3: 后端 API 端点**
- `app/api/endpoints/orphan_files.py` — 5 端点（latest/list/scan/cleanup-preview/cleanup）
- `app/api/api.py` — 路由注册 prefix=/orphan-files

**Phase 4: 定时任务与资源治理**
- `app/tasks/scheduler/orphan_scan_task.py` — OrphanScanTask（每周扫描+清理合一）
- 治理三处同步：default_scheduled_tasks（task_code=orphan_scan_cleanup, cron=0 2 * * 0）+ task_profiles（heavy_sync, wait_timeout=60）+ 任务类
- `app/tasks/cleanup_executor.py` — 修复 _query_level3/4_torrents 未定义 bug

**Phase 5: 前端页面与 API**
- `frontend/src/api/orphan-files.ts` — API 封装（5 函数 + 类型定义）
- `frontend/src/views/orphan-files/index.vue` — 管理页面（class 风格 Options API + 统计卡片 + el-table + el-pagination + 清理两步确认）
- `frontend/src/router.ts` — 路由注册 /orphan-files/index icon=folder

**Phase 6: 测试与验证**
- 3 个新测试文件（扫描器纯函数 19 + API 认证 14 + 任务治理 13 = 46 新测试）
- 更新 4 个现有测试（db_migration head/表数 + db_rollback 版本号 + audit_enums 成员数 39→42 + task_profiles 期望集）
- 全量 pytest **1997 passed, 0 failed**（基线 1937→1997 净增 60）
- black/flake8 通过；./init.sh 通过；前端 eslint 0 error + build 成功

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 新增后端测试（46 个） | ✅ 全 pass |
| 全量 pytest tests/ | ✅ **1997 passed, 0 failed**（基线 1937→1997，净增 60） |
| black（改动文件） | ✅ 通过 |
| flake8（改动文件） | ✅ 通过 |
| ./init.sh（全栈环境验证） | ✅ 通过 |
| 前端 eslint | ✅ 0 error |
| 前端 build（含 tsc） | ✅ 成功（orphan-files chunk 生成） |

---

## 2026-07-10 - SQLite 写锁治理完善（to_thread 止血 + db_write_scope 收尾）

**任务 ID**: `sync-resource-governance`（新增子任务 `sync-resource-governance.2.6`）
**分支**: dev
**类型**: 根因修正 + 治理收尾（4 个重型任务）

### 根因修正

经独立代码审查确认：高强度定时任务期间 WebUI 操作接口超时的根因是 **asyncio 事件循环饥饿**，而非 SQLite 写锁竞争。4 个重型任务的 `execute()` 虽是 `async def`，但任务体内含阻塞式同步 `SessionLocal()` 调用 + 同步 HTTP 调用，直接在共享 uvicorn 循环上跑，冻结整个循环，导致所有 WebUI handler（含读请求）都无法被调度。

修复策略（用户确认）：**to_thread 止血 + db_write_scope 收尾**，范围纳入 4 个重型任务。

### 改动清单（7 项）

1. **torrent_tracker_status_judge.py**（P0）：`execute()` 3 个同步 helper（`_load_keywords`/`_get_all_torrents`）改 `to_thread` 移出循环；`_judge_torrents_batch` 拆为 `_judge_one_batch` 分批（`BATCH_SIZE=1000`，每批 `db_write_scope` + `to_thread` + 单次 commit，单批失败即终止）；**N+1 优化**：逐种子 `db.query` 改两次 IN 查询（本批 TorrentInfo IN + TrackerInfo IN），内存按 `torrent_info_id` 分组。

2. **tracker_message_logger.py**（P0）：`_process_messages_batch_async` 2 处 commit + `_cleanup_old_logs_async` 2 处 commit 各包 `db_write_scope`；死代码同步方法（`_collect_tracker_messages`/`_process_messages_batch`/`_cleanup_old_logs`）加 LEGACY 标记。

3. **tracker_reannounce_task.py**（P0）：读段抽 `_read_downloader_data` 经 `to_thread`（保 `expunge_all`+`close`+不传 `db` 给 `execute_reannounce`）；`execute()` 读 enabled_configs 经 `to_thread`；写段 `batch_update_last_announce_time` 经 `to_thread` + `db_write_scope`（不改该函数本体，保 no-db 签名 + 内部自开 session 回归测试）。

4. **downloader_path_scan.py**（P0）：6 处 commit（`_update_path_mapping`/`_update_external_paths`/`_log_task_execution`/`_sync_default_path`/`_sync_active_path`/`_cleanup_obsolete_paths`）各包 `db_write_scope`；同步 HTTP（`app_default_save_path`/`get_session_variables`）经 `to_thread`；远程获取默认路径移出写 session（`_scan_downloader_paths` 预取 `default_path` 传入 `_sync_to_maintenance_table`）。

5. **database.py + test_database_pragmas.py**（P1）：`busy_timeout` 30000→15000 + sync/async engine `timeout` 30→15 + 4 处注释同步（二级兜底，对齐前端 axios timeout=20s，可独立回退 30s）。

6. **test_heavy_task_db_write_governance.py**（P1）：5 个行为测试取代不可行的 AST 断言（judge db_write_scope 进入 / judge to_thread 读 helper / message_logger db_write_scope 进入 / reannounce 写段 db_write_scope / reannounce 读段 to_thread）。

7. **文档 + DoD**（P2）：重写 `sync-db-write-governance.md` §四（纳入 4 个新任务 + to_thread 止血说明 + busy_timeout 15s 调整说明）；`feature_list.json` 新增 `sync-resource-governance.2.6` 子任务。

### 关键约束保持

- `cron_executor` 已在 `admission_controller.task_scope` 内调 `execute()`（cron_executor.py:417-444）→ 任务文件内只加 `db_write_scope`，不加 `task_scope`。
- `db_write_scope` 在 async caller 侧（loop 线程）获取/释放，同步工作经 `to_thread` 在工作线程跑，scope 不进工作线程（参考 `sync_db_write.py:163-169`）。
- 请求侧 endpoints 绝不动，`test_request_side_endpoints_do_not_use_governance_locks` 保持不变（scheduler 模块不在其扫描白名单）。
- `batch_update_last_announce_time` 不改本体（保 no-db 签名 + 内部自开 session，满足 `test_reannounce_config.py` 回归测试）。

### 明确不做（技术债，本次不纳入）

- `_sync_speed_schedule`（cron_executor.py:54-107）：每分钟持 sync SessionLocal 做 HTTP，P3。
- `tracker_candidate_pool`（被 message_logger 同步触发，未注册 task_profiles）：P3。
- `torrent_sync.py` API 触发路径 / `qb_tr_add_torrents_async` 全量同步：feature_list.json 已记 P3。

### 风险与回退

- `to_thread` 用 asyncio 默认线程池，但 `heavy_sync=Semaphore(1)` 限制重型任务不并发，线程池压力可控。
- `db_write_scope` 串行化若致后台 P95 退化，`SYNC_DB_WRITE_SCOPE_ENABLED=False` 一键回退（config.py:119）。
- `busy_timeout` 若 15s 误触 SQLITE_BUSY，改回 30s（独立改动无耦合）。

---

## 2026-07-05 - sync-resource-governance code review 修复轮

**任务**: 修复 sync-resource-governance code review 发现的 4 项问题 + 验收/文档状态对齐
**分支**: dev
**类型**: code review 修复（治理机制加固）

### 修复前基线核实

`aaa0976`（修复 tag_aggregation 404 循环 import）后全量 pytest 基线已为 **1926 passed, 0 failed**。
本轮修复前基线干净，无预存 fail（与 `sync-resource-governance.3` 旧 evidence 中"16 failed"叙述不符 ——
该 16 failed 是 `aaa0976` 之前的 tag_aggregation 顺序依赖 bug，已根治，本轮在 evidence 中据实更正）。

### 本轮修复（4 项问题 + 文档对齐）

**问题 1：DownloaderApiRuntime 超时后突破真实 per-downloader 并发上限**
- 根因：`async with sem`（asyncio.Semaphore）在 `wait_for` 超时后由 `__aexit__` 释放令牌，但
  `loop.run_in_executor` 提交的同步线程无法取消，仍在跑 → 新调用立即拿到令牌 → 真实远程并发突破上限。
- 修复：`_per_downloader_sems` 从 `asyncio.Semaphore` 改为 `threading.Semaphore`，由 executor 内
  wrapper 线程自身 `acquire/release`（`with sem: func(...)` 包成 wrapper 提交 executor）。
  超时后底层线程仍持有令牌继续运行，新调用阻塞在 `sem.acquire()` 直到旧线程 release。
- 超时 future done callback：归档 success/failure 统计（避免窗口聚合丢数据）。
- 文件：`backend/app/services/downloader_api_runtime.py`
- 测试：改写 `test_timeout_releases_semaphore`（新语义：超时后新调用最终恢复）+ 新增
  `test_timeout_does_not_break_real_concurrency_cap`（mutation 反向验证：修复前 buggy
  asyncio.Semaphore 实现并发达到 5 突破 limit=2）。

**问题 2：实时速度接口绕过 downloader runtime**
- 根因：`torrent_speed.py` 用独立 `_speed_executor` + `run_in_executor` + `wait_for`，
  前端 1 秒轮询绕过 per-downloader 限流，且有同样的超时线程残留风险。
- 修复：删除模块级 `_speed_executor`，`_call_with_timeout` 改为通过 `call_downloader_api`
  走 `DownloadLane.INTERACTIVE` + `timeout=_DOWNLOADER_TIMEOUT`，复用 per-downloader 限流与
  timeout 语义。`_process_downloader` / `_supplement_disappeared` 全部调用点传入 `downloader_id`。
- 文件：`backend/app/api/endpoints/torrent_speed.py`、`backend/app/startup/lifecycle.py`（删 `_speed_executor.shutdown`）
- 测试：新增 `test_uses_interactive_lane_and_timeout`（断言 lane=INTERACTIVE + timeout=_DOWNLOADER_TIMEOUT）+
  `test_speed_endpoint_does_not_bypass_per_downloader_limit`（spy 验证 N 次并发调用全经 runtime）。
  改写 `TestCallWithTimeout` / `test_qb_supplement_called` 适配新签名（patch `call_downloader_api`，
  避免全量 pytest 时 lifespan 关闭全局单例的污染）。

**问题 3：日志/flush 节流未落地**
- 根因：`SYNC_DISK_FLUSH_INTERVAL_SECONDS` 只在 config/docs 存在；`_log_call` 对每次 API 调用打
  info/warning；qB tracker enrich 逐 torrent 调用导致 O(torrent_count) 成功日志 + 失败双重放大。
- 修复：新增 `_CallStatsAggregator`，按 `(lane, method, downloader_id)` 窗口聚合：
  - 成功路径：不逐条 info，窗口到期输出一条结构化聚合日志（success_count/avg_duration/max_duration）。
  - 失败路径：runtime 层降级为 debug（业务侧 `_fetch_single_trackers` 的逐条 error 保留，避免双重放大），
    窗口聚合仍记录 failure_count + last_error_type。
  - `shutdown()` 强制 flush 残留统计。
- 关键：**不动** `SYNC_DB_COMMIT_BATCH_SIZE` 相关的 `bulk_upsert_with_retry` / `db_write_scope`（已落地的 DB 写治理）。
- 文件：`backend/app/services/downloader_api_runtime.py`
- 测试：新增 `TestCallStatsAggregator`（4 测试，spy `logger.extra` 断言，避免全量 pytest 时
  root logger 级别被前序测试抬高导致 caplog 抓不到 INFO 的污染）。

**问题 4：DownloaderApiRuntime.shutdown 未接入生命周期**
- 根因：runtime 有 `shutdown()` 但应用 shutdown 只停 cron 和（已删除的）`_speed_executor`。
- 修复：`lifecycle.py` finally 块在 cron_executor.stop() 之后调用
  `downloader_api_runtime.shutdown()`（关闭三 lane executor + flush 残留日志统计）。
- 文件：`backend/app/startup/lifecycle.py`
- 测试：新增 `test_lifespan_shutdowns_downloader_api_runtime` + `test_lifespan_no_longer_references_speed_executor`
  （AST 扫描 lifespan finally 块，mutation 验证：删 shutdown 调用 / 改回 _speed_executor 报红）+
  `TestShutdown`（行为测试：shutdown 后 executor._shutdown=True + flush 残留统计）。

**问题 5：验收/文档状态对齐**
- `feature_list.json`：父 feature `planned` → `done`；`last_updated` → `2026-07-05`；
  `sync-resource-governance.3` evidence 用真实数字（1937 passed 0 failed）替换"16 failed"旧叙述；
  新增 `sync-resource-governance.4` 子任务记录本轮修复。
- `progress.md`：新增本节。
- `session-handoff.md`：删除残留"阶段 2.5 / 状态: planned"旧块，更新为当前状态。

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 相关测试（runtime + speed + architecture） | ✅ 60 passed |
| 全量 `pytest tests/` | ✅ **1937 passed, 0 failed**（基线 1926→1937，净增 11 测试） |
| black（6 改动文件） | ✅ 通过 |
| flake8（6 改动文件） | ✅ 通过（顺带修了既有 F401 `_ttl_queue` 未用 import + 新增 pytest import） |
| `./init.sh`（全栈环境验证） | ✅ 通过 |
| mutation 反向验证 | ✅ 问题1（buggy 并发达 5）、问题4（删 shutdown AST 报红）均验证测试有效 |

### 关键设计决策

1. **threading.Semaphore 而非 asyncio.Semaphore**（问题1）：核心不变量是"同步线程实际结束前不释放容量"，
   只有让 wrapper 线程自身持有 semaphore 才能保证。asyncio.Semaphore 在协程层释放，与底层线程生命周期解耦。
2. **失败路径 runtime 层降级 debug**（问题3）：业务侧 `_fetch_single_trackers` 已有逐条 error（失败诊断需要），
   runtime 层若再 warning 会双重放大。聚合统计仍记录 failure_count + last_error_type，shutdown/窗口 flush 时输出。
3. **测试用 spy logger 而非 caplog**（问题3测试）：全量 pytest 时某些 API 测试经 TestClient 触发 lifespan，
   root logger 级别可能被抬高，导致 caplog 抓不到 INFO。spy `logger.info/warning` 的 `extra` dict 断言更可靠。
4. **速度测试 patch call_downloader_api**（问题2测试）：全量 pytest 时 lifespan 退出会关闭全局 runtime executor，
   `test_normal_execution` 真实走全局单例会 RuntimeError。统一 patch 避免污染。

### 改动文件清单

- `backend/app/services/downloader_api_runtime.py`（重写：threading.Semaphore + _CallStatsAggregator + future done callback）
- `backend/app/api/endpoints/torrent_speed.py`（删 _speed_executor，接入 INTERACTIVE lane）
- `backend/app/startup/lifecycle.py`（finally 接入 runtime.shutdown，删 _speed_executor 段）
- `backend/tests/services/test_downloader_api_runtime.py`（+8 测试，改写 1 测试）
- `backend/tests/api/test_torrent_speed_regression.py`（改写 4 测试适配新签名，+2 新测试）
- `backend/tests/test_architecture_constraints.py`（+2 AST 测试，+ pytest import）
- `feature_list.json` / `progress.md` / `session-handoff.md`（文档对齐）

---

## 2026-07-05 - 修复 test_tag_aggregation_api.py 全量运行 404（循环 import 根因）

**任务**: 修复 `tests/api/test_tag_aggregation_api.py` 全量 pytest 时 16 个用例全 404（单独跑通过）
**分支**: dev
**类型**: 测试隔离 → 实为业务代码循环 import bug

### 根因（非测试隔离，是业务代码 bug）

`tests/api/test_tag_aggregation_api.py` 全量运行时所有 `/api/v1/tags/*` 路由返回 404，根因是**全局 `app` 未注册业务路由**，触发链：

```
任意测试先 import app.api.api（如 test_recycle_bin_api.py:31 拿 api_router）
  └─ app.api.api 顶层 import 各 endpoint
     └─ app/api/endpoints/seed_transfer.py:25 顶层 `from app.factory import app`  ← 唯一源头
        └─ 触发 app.factory 执行：create_app() + configure_routes_and_static()
           └─ factory.py:62-64 早退检查命中：
              sys.modules["app.api.api"] 存在但无 api_router 属性（半成品）
              → return，跳过 init_routers → 全局 app 仅 4 条默认路由
```

证据（脚本验证）：
- 干净 import → `app.routes` = 191（含 13 个 `/tags/*`）
- 先 `import app.api.api` 再 `from app.main import app` → `app.routes` = **4**（仅默认）

### 为什么前几次修复都没根治

`cfc787b` / `053a390` 都在**测试侧**改（fixture 隔离、并发改串行、Windows 路径），但根因在业务代码（`seed_transfer.py:25` 顶层 import + `factory.py` 早退），测试侧改动无法根治。

### 修复（按子代理审查裁剪到最小根治）

**① `backend/app/api/endpoints/seed_transfer.py`（根因修复）**
- 删除 line 25 顶层 `from app.factory import app`
- 在 `transfer_seed` 和 `batch_transfer_seeds` 两函数 `try:` 块开头加 lazy import
- 与 `downloader.py:93/423/482/1183`、`torrent_location.py:45` 的既有 lazy 模式一致（代码复用优先）
- 加注释说明循环 import 原因，防止回归

**② `backend/app/factory.py`（可观测性增强，零副作用）**
- 早退分支加 WARNING 日志（命中即代表循环 import，便于将来定位）
- 早退逻辑本身保留（防御性），仅观测不改变控制流

### 不动的部分

- ❌ 不动 `test_tag_aggregation_api.py`：lazy 修好后全局 app 路由齐全，16 个用例自然全绿（子代理审查确认测试侧改动非必要）
- ❌ 不动 `main.py`、`api.py`、其他 endpoint

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 最小复现 `pytest test_recycle_bin_api.py test_tag_aggregation_api.py` | ✅ 29 passed（修复前 16 failed） |
| seed_transfer 回归 `pytest test_seed_transfer_api.py` | ✅ 10 passed（lazy 改动未破坏 global_app.state.store 注入） |
| 全量 `pytest tests/` | ✅ **1925 passed, 0 failed**（修复前 16 failed / 1909 passed） |
| 单文件 `pytest test_tag_aggregation_api.py` | ✅ 16 passed |
| black --check（两改动文件） | ✅ 通过 |
| flake8（两改动文件） | ✅ 通过 |
| mypy（两改动文件） | ✅ 无新增错误（基线 10 个历史错误，行号平移，与本次改动无关） |

### 关键设计决策

1. **范围裁剪**：原计划"两边都修"（业务代码 + 测试侧），子代理独立审查后裁剪为"只修业务代码"。理由：lazy 修复消除循环 import 后，全局 app 路由齐全，测试侧自建 FastAPI 实例非必要条件（治本即可）。
2. **factory 早退逻辑保留**：删除会更激进但风险大（行为变更）；保留 + WARNING 是零副作用的可观测性增强。
3. **不引入回归**：seed_transfer lazy 改动有 `test_seed_transfer_api.py` 作为回归基线（子代理提示的关键风险点），已验证通过。

### 改动文件清单

- `backend/app/api/endpoints/seed_transfer.py`（+11/-1）
- `backend/app/factory.py`（+11）

---

## 2026-07-04 - sync-resource-governance 阶段 3 完成（验证与证据归档）

**任务 ID**: `sync-resource-governance`
**阶段**: 3（验证与证据归档）已完成。整个 sync-resource-governance 任务 0/1/2/2.5/3 全部完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（3）**:
- `backend/tests/test_architecture_constraints.py` 扩展（新增 `test_request_side_endpoints_do_not_use_governance_locks`）
- `backend/tests/api/test_sync_governance_integration.py`（3 行为契约测试）
- `backend/scripts/sync_resource_benchmark.py`（6 场景可重复压测脚本）

### 关键设计决策

1. **分层验证**（避开 TestClient 线程安全问题）：架构约束测试（ast 扫描，钉死请求侧不碰治理锁）+ 行为契约测试（纯 asyncio 并发，不走 TestClient）+ 压测脚本（性能验证，运维手动跑）。
2. **TestClient 拓扑限制记录**：计划说的"断言请求侧在可接受时间内返回"在 pytest+TestClient 下无法严谨实现（TestClient 非线程安全，test_tag_aggregation_api.py:402-411 已记录），性能验证划给可重复脚本。
3. **架构约束防回归**：dashboard/torrent_crud/dashboard_service 三个请求探针模块禁止 import/调用 admission_controller/task_scope/db_write_scope/resource_guard，防止未来误在请求路径加锁。

### 验证结果

**新增测试 4 个全 pass**：
- 1 架构约束（ast 扫描三个模块，mutation 加真实 import 报红验证）
- 3 行为契约（heavy_sync 持有时查询完成 / db_write_scope 持有时读不阻塞 / spy acquire 证明不碰锁）

**mock 压测证据**（30 iterations × 6 场景）：

| 场景 | P50 | P95 | P99 | max | 含义 |
|------|-----|-----|-----|-----|------|
| 1_baseline_no_sync | 0ms | 0ms | 0ms | 15ms | 基线 |
| 2_tracker_sync_running | 0ms | 0ms | 16ms | 16ms | tracker 同步中 |
| 3_torrent_info_sync_running | 0ms | 0ms | 0ms | 15ms | 种子信息同步中 |
| 4_both_sync_triggered | 0ms | 0ms | 15ms | 16ms | 同时触发 |
| 5_single_downloader_many_torrents | 0ms | 0ms | 0ms | 16ms | 单下载器大量种子 |
| 6_multi_downloader_concurrent | 0ms | 0ms | 15ms | 16ms | 多下载器并发 |

**结论**：所有场景 P50/P95 <1ms、P99 ≤16ms、max 16ms，证明请求侧（DashboardService 查询）**未被治理锁（heavy_sync/db_write_scope/lane executor）阻塞**，治理目标达成。15-16ms 的偶发抖动是 asyncio 调度噪音，非锁等待。

**全量套件**：16 failed, 1909 passed，**diff 基线为零**（16 个全是预先存在的 tag_aggregation 顺序依赖 bug）。

### sync-resource-governance 整体完成度

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0+1 | TaskAdmissionController（heavy_sync 背压 + 同类去重 + cron_executor 接入） | ✅ |
| 2 | DownloaderApiRuntime（三 lane 隔离 + per-downloader 限流 + qB tracker 并发治理） | ✅ |
| 2.5 | DB 写入治理（变更检测 + 批量 upsert + db_write_scope 串行化） | ✅ |
| 3 | 验证与证据归档（架构约束 + 行为契约 + 压测脚本） | ✅ |

累计：
- 5 个新模块（resource_guard/task_profiles/downloader_api_runtime/sync_db_write/sync_resource_benchmark）
- 7 个配置项
- 1 个 DB 写入治理指南文档
- ~115 个新单测 + 多处 mutation 反向验证
- 6 个 commit（feat + docs 配对）

### 已知技术债（留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 真实生产环境的压测（含真实多下载器 + 真实 qB/TR 实例 + 真实种子规模）需运维用 sync_resource_benchmark.py 跑。

---

## 2026-07-04 - sync-resource-governance 阶段 2.5 完成（DB 写入治理）

**任务 ID**: `sync-resource-governance`
**阶段**: 2.5（DB 写入治理）已完成。经 3 个并行子代理独立审查（技术正确性/范围回归/测试策略）+ 5 项关键发现实证核实后修订计划。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（3）**:
- `backend/app/services/sync_db_write.py` — 变更检测纯函数（has_torrent_info_changes 动态字段对比、has_tracker_changes 6 字段+归一化）+ bulk_upsert_with_retry（db_write_scope+retry base_delay=1.0）
- `backend/tests/services/test_sync_db_write.py`（21 测试）
- `backend/tests/api/test_torrents_async_db_governance.py`（7 真实 SQLite 部分索引集成测试）

**修改文件（4）**:
- `backend/app/api/endpoints/torrents_async.py` — 新增 extract_tracker_rows_from_torrent（纯提取）+ sync_trackers_batch_async（批量 select+变更检测+严格四步顺序+元组语义 mark_removed）；qb/tr_add_torrents_info_only_async 修正 skip 语义 bug+整行变更检测+替换闭包为 bulk_upsert_with_retry；qb/tr_sync_trackers_only_async 主循环改造（累计 rows→batch_size 200→批量 upsert）
- `backend/app/tasks/resource_guard.py` — db_write_scope 加 SYNC_DB_WRITE_SCOPE_ENABLED 开关
- `backend/app/core/config.py` — 新增 SYNC_DB_WRITE_SCOPE_ENABLED=True

### 关键设计决策（含审查调整）

1. **范围补全**（审查2-A2）：qb+tr 两个 sync_trackers_only_async 都改（原计划只改 qb 是漏项）。
2. **mark_removed 元组语义**（审查1-C6 必修2）：禁止扁平化 url 集合，用 `(info_id, url)` 元组 IN 取反，避免跨种子误删。集成测试用"同名 url 跨种子"场景验证。
3. **变更检测字段**（审查2-D10）：has_torrent_info_changes 只对比实际写入 dict 的 key 集（动态适配），不硬编码 29 字段；has_tracker_changes 只对比 6 业务字段（status/msg/seeder 等是死字段）。
4. **归一化契约**（审查3-A2）：None==""/strip 后比较，防远程返回微小差异导致每轮都写。
5. **db_write_scope 开关**（审查2-C9）：SYNC_DB_WRITE_SCOPE_ENABLED=True，3 行代码快速回滚。
6. **测试分层**（审查3-B4/D10）：纯函数 mock + 真实 SQLite 部分索引集成测试（覆盖 mock 测不到的 on_conflict_do_update(index_where dr=0) 语义）。
7. **测试防假通过**（审查3-B6）：db_write_scope 测试用真实 admission_controller + spy _state.db_writer.acquire，mutation 删包裹后报红。

### 验证

- **新单测 28 个全 pass**：21 sync_db_write（纯函数+mock）+ 7 db_governance（真实 SQLite）
- **mutation 反向验证 3 处**：
  - 删 db_write_scope 包裹 → acquire_spy.assert_awaited 报红 ✓
  - mark_removed 扁平化 url → "同名 url 跨种子"测试报红 ✓
  - 变更检测相关 mutation 由 has_*_changes 纯函数测试覆盖 ✓
- **零回归**：全量 16 failed, 1905 passed，**diff 基线为零**（16 个全是预先存在的 tag_aggregation 顺序依赖 bug，已固化基线）
- **stats 守恒断言**：insert+update+skip == 总输入行数

### 已知技术债（显式记录，留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 这两个路径是写锁竞争的未保护源，本轮不根治（范围控制），留 P3 统一改造。

### 不在本轮范围（明确排除）

- 全量同步的 commit 改造（P3）。
- DBWriteQueue（后续独立版本）。
- 前端任何改动。

### 下一步

阶段 3（验证与证据归档）：补充集成验证 + 手动压测矩阵 + 把同步期间请求响应改善、DB commit/写入频率证据写回 harness。

---

## 2026-07-04 - sync-resource-governance 阶段 2 完成（下载器 API 调用隔离）

**任务 ID**: `sync-resource-governance`
**阶段**: 2（方案三：下载器 API 调用隔离与调度层）已完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（2）**:
- `backend/app/services/downloader_api_runtime.py` — DownloaderApiRuntime（三 lane 独立 ThreadPoolExecutor：tracker=5/sync=4/interactive=6 线程）+ per-downloader Semaphore（DOWNLOADER_IO_CONCURRENCY=2）+ call_downloader_api 统一封装 + LaneLogExtra 结构化日志 + 进程级单例 downloader_api_runtime
- `backend/tests/services/test_downloader_api_runtime.py`（14 个新单测）

**修改文件（3）**:
- `backend/app/api/endpoints/torrents_async.py` — 16 处 `asyncio.to_thread` 全量迁移到 `call_downloader_api`（按 sync_lane/tracker_lane/interactive_lane 分类）；`_enrich_qb_torrents_with_trackers` 默认并发 10→3（取 settings.QB_TRACKER_CONCURRENCY）+ 加 downloader_id 参数 + 4 个调用点对齐；`qb_add_torrents_info_only_async`/`tr_add_torrents_info_only_async` 加可选 client 参数 + fallback
- `backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py` — 调用点从 app.state.store 取缓存 client 传入同步函数（复用连接，遵循 downloader-connection 约束）

### 关键设计决策

1. **三 lane 物理隔离**：每个 lane 独立 ThreadPoolExecutor，tracker 批量查询不挤占 sync 主数据同步、不挤占 interactive 用户操作。线程数根据 QB_TRACKER_CONCURRENCY(3) + 余量设为 5/4/6。
2. **per-downloader 跨 lane 总并发**：DOWNLOADER_IO_CONCURRENCY=2 限制同一下载器的所有远程调用总并发，防止单个 qB WebUI 被多任务同时打满。这是 lane 之上的第二层限流。
3. **qB tracker 并发治理**：`_enrich_qb_torrents_with_trackers` 历史默认 10，会打满 qB WebUI；改为取 settings.QB_TRACKER_CONCURRENCY(默认3)，并在 lane executor 之上叠加 asyncio.Semaphore 做批量并发控制。
4. **client 复用渐进式改造**：给 qb/tr_add_torrents_info_only_async 加可选 client 参数，None 时 fallback 新建；TorrentInfoSyncTask 从 store 取后传入。不破坏现有调用方，向后兼容。
5. **异常透传不吞**：call_downloader_api 只记录日志 + 重新抛出，不吞任何异常（调用方原有错误处理逻辑保持不变）。

### 验证

- **新单测 14 个全 pass**：参数透传/超时/超时释放 semaphore/异常透传/异常释放 semaphore/三 lane 物理隔离（线程名前缀断言）/per-downloader 并发上限/不同下载器并行/结构化日志 extra/便捷封装委托
- **mutation 反向验证**：去掉 per-downloader semaphore（换成 Semaphore(10)）→ test_same_downloader_concurrency_capped 报红（max=4 超过 limit=2）✓
- **零回归**：tasks/ + services/ 全量 217 passed；全量套件 16 failed, 1877 passed — 16 个失败全是预先存在的 test_tag_aggregation_api.py 顺序依赖 bug（已三次验证基线）
- **to_thread 清零**：torrents_async.py 的 `asyncio.to_thread` 从 16 处降到 0 处

### 不在本轮范围（明确排除）

- DB 写入治理（db_write_scope 接入 + 批量提交 + 变更检测）— 下一轮（阶段 2.5）
- DBWriteQueue — 后续独立版本候选
- 前端任何改动

### 下一步

阶段 2.5（DB 写入治理）：按 `backend/docs/constraints/sync-db-write-governance.md` 指南，把 qb_add_torrents_info_only_async / qb_sync_trackers_only_async 等同步函数的 commit 点包进 db_write_scope + 批量 upsert + 变更检测。

---

## 2026-07-04 - sync-resource-governance 阶段 0+1 完成（调度器资源背压）

**任务 ID**: `sync-resource-governance`
**阶段**: 0（基线观测）+ 1（方案二：调度器与资源背压）合并实施，已完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（4）**:
- `backend/app/tasks/task_profiles.py` — TaskProfile dataclass + TASK_PROFILES 注册表（6 个重型 task_code）+ get_profile/is_heavy_task 谓词
- `backend/app/tasks/resource_guard.py` — TaskAdmissionController（heavy_sync 全局令牌 + per-task_code 运行/排队登记 + 同类去重跳过 + 等待超时 + task_scope 异常安全 + release 幂等 + db_write_scope 骨架）+ AdmissionResult + 进程级单例 admission_controller
- `backend/docs/constraints/sync-db-write-governance.md` — DB 写入治理指南（变更检测/批量 upsert/db_writer 临界区/日志节流，供阶段 2 改造同步函数 commit 点遵循）
- `backend/tests/tasks/test_task_profiles.py` / `test_resource_guard.py` / `test_cron_executor_admission.py`（3 个测试文件，34 个新单测）

**修改文件（2）**:
- `backend/app/core/config.py` — 新增 7 项配置：SYNC_HEAVY_CONCURRENCY=1、SYNC_HEAVY_QUEUE_LIMIT=1、DOWNLOADER_IO_CONCURRENCY=2、QB_TRACKER_CONCURRENCY=3、DOWNLOADER_API_TIMEOUT_SECONDS=30、SYNC_DB_COMMIT_BATCH_SIZE=200、SYNC_DISK_FLUSH_INTERVAL_SECONDS=5.0
- `backend/app/tasks/cron_executor.py` — `_run_python_internal_class` 签名从 `(executor_code: str)` 改为 `(task: Dict)`；在 importlib 加载类后、调 execute() 前按 task_code 查 profile，重型任务用 `admission_controller.task_scope` 包裹，admitted=False 直接返回 skipped 且不调 execute；轻量任务走原路径不进入背压

### 关键设计决策

1. **接入位置**：cron_executor._run_python_internal_class 是 task_type=4（Python 内部类）的唯一执行入口，所有 6 个重型同步任务都经此进入 execute()。统一在此接入，避免改 6 个任务子类，且新任务自动获得背压保护（只要在 task_profiles 登记）。

2. **同类去重维度**：保留现有 `running_tasks: Dict[int, bool]`（task_id 维度，APScheduler 重入保护）+ 新增 task_code 维度（跨任务类型资源竞争）。两者互补不冲突。

3. **db_writer 骨架不强制接入**：本轮只暴露 `db_write_scope()` 信号量（并发 1）+ 写治理指南，不改造 torrents_async.py 现有 commit 点（留给阶段 2 一起做），避免阶段 1 范围爆炸。

4. **测试隔离**：admission_controller 是进程级单例，每个测试 setup 调 `reset_state()` 重建信号量与登记表，避免状态泄漏。

### 验证

- **新单测 39 个全 pass**：task_profiles（19）+ resource_guard（15）+ cron_executor_admission（5）
- **mutation 反向验证（含审查修订后）**：
  - Mutation A（去掉 acquire 的 running 去重检查）→ 2 个去重测试报红 ✓
  - Mutation B（cron_executor 绕过 admission）→ 2 个接入契约测试报红 ✓
  - Mutation C（删 release idempotency 守卫）→ 修订后的 test_double_release_does_not_overreturn_semaphore 报红 ✓
  - Mutation D（删 _build_log_extra 字段）→ 修订后的 test_admitted_path_extra_contains_all_required_fields 报红 ✓
  - Mutation E（删 acquire 异常分支的 queued 归还）→ 修订后的 test_acquire_exception_releases_queue_slot 报红 ✓
- **零回归**：tests/tasks/ 全量 203 passed（含 test_cron_executor.py 的 coalesce 锚点）
- **全量套件**：16 failed, 1863 passed — 16 个失败全是预先存在的 test_tag_aggregation_api.py 顺序依赖 bug（已用 git stash 验证基线就是 16 failed，与本次改动无关）

### 子代理 code review 修订（2026-07-04）

3 个并行子代理审查（并发正确性 / 测试质量 / 接入回归），逐条实证核实后修订：

- **🔴 假通过 #1（release 幂等性测试）**：原 test_double_release 只断言"能再次 acquire"，溢出后照样能 acquire。重写为跨 task_code 断言溢出后果（两个不同 task_code 同时 admitted=True 破坏互斥）。Mutation C 验证抓到。
- **🔴 假通过 #2（StructuredLog 测试）**：原 spy 断言 AdmissionResult 入参字段，删日志 extra 后仍 PASS。拆出 `_build_log_extra` 纯函数，直接断言 extra dict 的 7 个字段。Mutation D 验证抓到。
- **🔴 skip 与真失败混淆**：原 skip 返回 success=False 与真执行失败结构相同，运维误判故障。改为 success=True + skipped=True 标记 + [ADMISSION_SKIP] 机器可解析前缀。
- **⚠️ 盲区（acquire 异常分支）**：原测试未覆盖 heavy_sync.acquire 抛非 Timeout 异常时的 queued 归还。补 test_acquire_exception_releases_queue_slot。Mutation E 验证抓到。
- **⚠️ 漂移（task_profiles 锚点）**：原 EXPECTED_HEAVY_TASK_CODES 硬编码不与 default_scheduled_tasks.py 交叉验证。补 test_all_profile_codes_exist_in_default_scheduled_tasks + test_profile_codes_subset_of_python_class_tasks。
- **文档化**：task_profiles.py 顶部加"task_code 不可改名 + 配置启动时固化"运维约束；release() docstring 加"禁止体内 await"约束。

### 不在本轮范围（明确排除）

- 阶段 2 `downloader_api_runtime`（tracker/sync/interactive lane、qB tracker 并发治理、to_thread 迁移）— 下一轮
- 现有 torrents_async.py 同步函数的 db_writer/批量提交改造 — 阶段 2 做
- DBWriteQueue — 后续独立版本候选
- 前端任何改动

### 下一步

进入阶段 2（方案三：下载器 API 调用隔离与调度层）：新建 `backend/app/services/downloader_api_runtime.py`，隔离 tracker/sync/interactive lane，控制 qB tracker 明细并发（默认 3），优先复用 app.state.store 客户端，迁移 torrents_async.py 的 `asyncio.to_thread` 散落点到专用 executor。

---

## 2026-07-03 - 下一任务：同步任务资源治理与下载器 API 调度

**任务 ID**: `sync-resource-governance`  
**计划文件**: `PLANS/sync-resource-governance.md`  
**状态**: planned，尚未进入代码实现。  
**用户决策**: 按“方案二 -> 方案三”的顺序修复，即先做调度器/资源背压，再做下载器 API 调用隔离与调度层。

**问题背景**:
- tracker 与种子信息同步期间，请求其它接口经常超时。
- 初步判断瓶颈不是单一 API 慢，而是后台重型任务并发争抢 DB 写入、下载器 WebUI/API、默认线程池与调度资源。
- 已修正一条分析误差：`qb_add_torrents_info_only_async` 当前不调用 `_enrich_qb_torrents_with_trackers`，后续不能把 tracker 富集误归因到 info-only 路径。

**Harness 更新**:
- 新增 `PLANS/sync-resource-governance.md`，作为下一项目任务的详细执行计划。
- `feature_list.json` 的 `current_dev_version` 已更新为 `sync-resource-governance`。
- 新任务拆分为基线观测、方案二资源背压、方案三下载器 API 调度、验证归档四个阶段。

**已确认决策（2026-07-03 补充）**:
- 重型 cron 任务需要引入“队列长度/排队登记”概念：按 `task_code` 判断是否已有同类重型任务运行中或排队中，若存在则跳过本轮。
- `downloader_io` 默认并发使用 2。
- qB tracker 明细并发默认使用 3。
- 允许新增配置项：`SYNC_HEAVY_CONCURRENCY`、`SYNC_HEAVY_QUEUE_LIMIT`、`DOWNLOADER_IO_CONCURRENCY`、`QB_TRACKER_CONCURRENCY`、`DOWNLOADER_API_TIMEOUT_SECONDS`、`SYNC_DB_COMMIT_BATCH_SIZE`、`SYNC_DISK_FLUSH_INTERVAL_SECONDS`。
- 必须关注硬盘写入频率，避免逐条写库、逐条日志落盘、高频 commit/flush 击垮硬盘或造成大规模寿命损耗。
- 暂不实现 `DBWriteQueue`；它作为后续独立版本候选保留在 harness 中，当前任务只做 `db_writer` 短锁、批量提交、变更检测和写入节流。

> **项目**: BtDeck 全栈（backend + frontend）
> **当前分支**: dev
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-25

> 本文件由 backend/progress.md 与 frontend/PROGRESS.md 合并而来（2026-06-18）。按"版本分节 + 每节内前后端子段"组织，技术决策表合并为一表并新增"端"列。

---

## 进行中功能

### v1.0.5 数据库四轨治理（单轨化重构）

**触发问题**: 启动报 `table users already exists`（schema 快照与已有库冲突）
**根因**: 数据库 schema 管理存在四轨冗余：
1. Alembic 迁移链（唯一正道）
2. `Base.metadata.create_all()`（init_db 无条件兜底，无法 ALTER）
3. 生产 schema 快照 `ensure_database_initialized`（写入幽灵版本 9aea25308aff）
4. search_templates 原生 SQL 自建表（独立第四轨）

**治理目标**: 统一为单一 Alembic 轨，存量数十/数百用户升级无感、非破坏性。

**核心决策（经 5 轮子代理审查 + 4 项用户决策）**:
- DEV 默认不变（保持 True），不加新配置项，Docker 默认行为不变（向下兼容）
- seed 保留原生 SQL，仅服务层迁 ORM
- frozen 保留 init_schema_from_production.py 作灾备兜底（仅移除启动调用）
- 幽灵版本（9aea25308aff）用 KNOWN_GHOST_VERSIONS 黑名单救援；未知版本只告警不降级
- 迁移前自动备份（checkpoint+cp，保留 3 份）
- 回滚策略三级（Level1 代码回滚/Level2 备份还原/Level3 alembic downgrade）

**实施（7 阶段，~28 文件）**:
| 阶段 | 内容 | 验证 |
|------|------|------|
| 0 | test_db_migration.py（6 场景） | 6 passed |
| 1a | search_template.py ORM + env.py 补 import | 导入链正常 |
| 1b | search_templates 迁移(95ef8bd8b47a) + ORM 改造 + 清理8处_ensure + downloader裸查询修复 | ORM 测试 9 passed |
| 2 | init_db 删 create_all | — |
| 3 | migrate_database() + _rescue_or_warn_version(黑名单) + _backup + config.py + env.py URL 统一 + .gitignore | 幽灵救援/未知告警/head no-op 全实测通过 |
| 4 | main.py 收敛(删 schema 快照/initialQb/init_db) + 幽灵版本文档清理 | py_compile + import 链通过 |
| 5 | btdeck_startup.sh(删 shell 迁移) + rollback-guide.md + 迁移标注规范 + lint 扩展 + 老迁移标注 | lint 通过 |

**验证结果**:
- pytest: 1536 passed, 2 failed（均为既有 Windows 路径分隔符 bug + flaky 测试，与本次无关）
- lint_btdeck.py: 未发现阻塞性问题
- 手动 A（空库建 25 表+admin+4 模板）/ B（已有库 no-op 不备份）/ C（环境变量路由）/ D（幽灵救援）全通过
- `./init.sh --ci` 全栈环境验证通过

**关键设计文档**: `backend/docs/operations/rollback-guide.md`（回滚操作指南）

**运维影响**:
- 存量用户升级（含幽灵版本库）：自动救援 + 备份，无感
- 后续字段/表变动：alembic 标准流程
- 版本回滚：纯增量走 Level1（代码回滚），破坏性走 Level2（备份还原）


### v1.0.5-audit 契约审计修复（技术债）— fix/contract-audit 分支

**计划文件**: `PLANS/v1.0.5-audit.md`
**审计依据**: `backend/docs/style-and-contract-audit.md`（P1 确定性 bug + P0 契约归一化）
**范围**: P0 + P1。不覆盖 P2（REST 路由迁移）/ P3（前端类型收敛），推迟。

**已完成（5 commit）**:
| 任务 | commit | 验证 |
|------|--------|------|
| P0-3 后端全局异常处理器 | ac324bc | pytest 1524 passed 无回归 |
| P0-1 前端 ApiError 归一化 | 0e55469 | jest 25/25, eslint 0 error |
| P1-A 后端补 4 项端点 | efc6574 | auth+cron 189 passed |
| P1-B 前端修 4 项契约 | 0e8f007 | jest 25/25, eslint 0 error |
| P0-2c 认证基础设施补强 | 9e19822 | auth 125 passed |

**进行中**:
- P0-2a 认证迁移到 `require_authenticated_user`（20+ 文件/~195 处，分批提交）
- P0-2b 认证测试改造（~40 处断言）

**审计交叉验证结论（3 个独立 Explore agent 核实）**:
- 9 项契约不匹配中 8 项属实，`/tags/batch-delete` 误报（后端已有端点）
- tracker statistics 是漏挂装饰器的孤立函数，修复成本极低
- tag_management 的 `{success,message}` 是私有 helper 返回值，非 HTTP 响应，降级不改

---

### v1.0.5 查询模板系统 (done) — dev 分支

**计划文件**: `PLANS/v1.0.5.md`（已标注方向转变）

**目标**: 实现查询模板功能，用户可保存常用查询条件（简单查询 + 高级搜索）并一键应用，含系统预设模板。

**方向转变（重要）**: 探索阶段发现后端与前端已存在完整的 `search_templates` 基础设施（表 + CRUD 端点 + 服务 + 前端 API），仅前端入口 `handleSaveSearchTemplate` 是空函数。改为**补全现有系统**而非从零新建，避免重复造轮子。

**任务完成情况** (12/12 done，见 feature_list.json v1.0.5)：
- 后端：4 个预设模板数据 + init_db 集成 + apply/权限确认（现有代码已满足）+ 16 个认证测试
- 前端：API 便捷方法 + index.vue 接线（handleSaveSearchTemplate + applyQueryTemplate）+ 管理页 + 对话框 + 路由
- 全栈：保存→应用链路代码闭环

**5 个 commit**: 63a4bec / d04af4d / 7f111f8 / 7896a23 / (本条状态更新)

**遗留**: ~~前端 lint/tsc 因环境依赖未完整安装，留待完整环境验证。~~ ✅ **2026-06-27 已补验**（lint 0 error/131 warning、build 成功含 tsc、test:unit 34 passed）。

---

## 已完成功能

### v1.0.4 实时速度监控 (done) — dev 分支

**计划文件**: `PLANS/v1.0.4.md`

**与计划的偏差**:
- 计划: `TorrentStateManager` 动静数据分离(10s/10min刷新) → 实际: 轻量级 `active-torrents` 接口 + 前端1秒轮询
- 计划: `speed-all` API → 实际: `active-torrents` API（仅返回有速度的种子）
- 计划: 前端 `setup()` + Composition API → 实际: **Options API** + 虚拟分页
- 计划: 前端 10秒/10分钟双定时器 → 实际: 1秒单定时器轮询
- 额外完成: 种子完成后自动更新数据库状态、活跃种子进度字段

#### 后端（11 个任务全部 done）

| 任务 | 说明 |
|------|------|
| 活跃种子速度接口 | `torrent_speed.py`, qB用status_filter, tr仅查速度字段 |
| 路由注册 | `/torrents/active-torrents` |
| 线程池泄漏修复 | commit 25c59aa |
| 速度单位转换修复 | commit d79040d |
| Transmission空列表修复 | commit b4ddde2 |
| 活跃种子进度字段 | commit a568aa9, progress字段(0-100百分比) |
| 种子完成后自动更新状态 | commit f8b0185, progress达100%自动更新为completed |
| 性能测试 | 4下载器并发平均543ms |
| 场景测试 | 8个验收场景通过 |

#### 前端（2 个任务 done）

| 任务 | 说明 |
|------|------|
| 前端 API 封装 | `torrents.ts` getActiveTorrents() |
| 前端种子列表改造 | Options API + 虚拟分页 + 1秒轮询 + beforeDestroy清理 |

**关键实现**: `activeSpeedMap` 缓存速度数据；虚拟分页算法（活跃种子优先排列）；防抖 + 版本控制避免重复请求。

**结论**: v1.0.4 前后端开发完成。

---

### v1.0.9 一键部署 (done，提前完成) — dev 分支

**说明**: v1.0.9 早于 v1.0.5~v1.0.8 提前完成落地。

| 任务 | 说明 |
|------|------|
| 全栈 monorepo 整合 | commit c7ce2f4，前后端合并为单一仓库 |
| PyInstaller 打包 | deploy/btdeck.spec，前后端合一单可执行文件 |
| Inno Setup Windows 安装包 | deploy/btdeck.iss |
| fpm Linux 安装包 | deploy/build-linux.sh，.deb/.rpm |
| Docker Compose 全栈部署 | docker-compose.yml |

**部署修复系列**: 5e4baf8 / 6f8e3e0 / 78033bc / fb380b9 / b80a7f6（Inno Setup 语言包、PyInstaller 路径、pandas/numpy/openpyxl hiddenimport、PIL 排除、systemd 目录预创建等）。

---

## 计划外已完成功能

### 通知中心 (done) — dev 分支

**后端**: `notification.py`(模型) + `notification_service.py`(版本检查、未读计数) + `notifications.py`(GET/PUT/DELETE 端点)。单向信箱模式，仅系统写入。
**前端**: `NotificationDrawer/index.vue`(全局右侧抽屉) + `NotificationItem.vue` + `store/modules/notification.ts`(Vuex) + `api/notification.ts`。60秒未读计数轮询。

### Tracker关键词池初始化 (done) — dev 分支

`tracker_keywords_pools.py` 关键词池管理，默认数据自动初始化，集成到 `init_db()` 统一初始化流程。

### 统一初始化重构 (done) — dev 分支

所有初始数据初始化统一到 `init_db()`，集成到后端启动流程。commit 22a89c8。

---

## 待开发功能（按计划顺序）

| 版本 | 名称 | 计划文件 | 状态 |
|------|------|----------|------|
| v1.0.6 | 孤儿文件管理 | PLANS/v1.0.6.md | pending |
| v1.0.7 | 路径扫描增强 | PLANS/v1.0.7.md | pending |
| v1.0.8 | 数据库升级 | PLANS/v1.0.8.md | pending |
| v1.1.0 | 自动化运维 | PLANS/v1.1.0.md | pending |

---

## 技术决策记录

| 日期 | 端 | 决策 | 理由 |
|------|----|------|------|
| 2026-04-22 | backend | 轻量级active-torrents替代动静分离 | 更简单，前端1秒轮询仅查有速度种子 |
| 2026-04-22 | frontend | Options API 而非 Composition API | 项目技术栈约定 |
| 2026-04-22 | frontend | 前端虚拟分页 | 已有查询逻辑，前端合并更灵活 |
| 2026-04-22 | frontend | 防抖+版本控制 | 避免1秒轮询导致重复请求和页面卡顿 |
| 2026-04-22 | backend | 专用线程池 | 避免阻塞默认executor |
| 2026-04-22 | backend | 统一初始化到 init_db() | 集中管理初始数据 |
| 2026-06-18 | fullstack | harness 体系合并到根目录 | 全栈 monorepo 统一状态追踪，消除端级重复 |
| 2026-06-18 | fullstack | v1.0.5 补全 search_templates 而非新建 query_templates | 探索发现已有完整基础设施，避免重复造轮子 |
| 2026-06-18 | fullstack | User 不加 relationship（用 created_by 整数列） | 遵循既有约定（SettingTemplate 同模式），避免触发 User 表迁移 |
| 2026-06-18 | fullstack | query_config 用 source=simple/advanced 双分支 | 1:1 还原两种查询状态（listQuery / condition_groups），应用时按 source 分流 |
| 2026-06-19 | fullstack | 审计修复用独立 feature 块 v1.0.5-audit 而非 v1.0.5.1 | v1.0.5.1 子任务号已被 done 占用，撞号；用 -audit 后缀避开数字子任务号空间 |
| 2026-06-19 | fullstack | 实施顺序 P0-3→P0-1→P1→P0-2c→P0-2a/b | 异常处理器先做兜底；前端归一化在后端 401 之前避免破损窗口；认证基础设施先于迁移避免 user_id 断链 |
| 2026-06-19 | backend | 认证统一用 require_authenticated_user（HTTP 401），login.py 豁免 | login 的 code=401 是密码错误业务语义，非认证失效，前端登录页依赖此分支不跳转 |
| 2026-06-19 | backend | 不把 user_id 加入 verify_access_token required_fields | 避免现有未过期 token 全部失效（强制全员重登），改为 AuthenticatedUserInfo 兜底解析 |
| 2026-06-19 | frontend | ApiError extends Error + 兼容 msg/response getter | 降低约 33 个存量 catch 块的回归（e.msg / e.response.data.msg 链式读取仍可用） |
| 2026-06-19 | frontend | 成功码白名单 {200,206,207} | 206(需确认路径映射)/207(Multi-Status 部分成功) 是业务级成功，不归一化为错误 |
| 2026-06-19 | fullstack | apply 改前端对齐后端 Path 参数 | 后端 Path 更 RESTful，且 override=True 硬编码使 override_local 无效 |
| 2026-06-19 | fullstack | torrents/detail 不补后端端点，删前端死代码 | getTorrentDetail 从未被调用，补后端会引入语义模糊(hash可能重复)的未用功能 |

---

## 当前会话

> **2026-06-28**: 后端回归测试补全（续）——为"纯 DB 操作、业务逻辑零测试覆盖"的接口补充 API 级回归测试，每个接口经"子代理审查 → 实证核实 → 修订 → 反向验证"闭环。共 10 个 commit，+86 个回归测试，全量 tests/api/ 413 passed 无回归。
>
> **本次覆盖的 3 个接口 + 1 个基础设施重构**：
>
> 1. **审计日志查询接口**（commit 545fad4 + 8197567，41 测试）
>    - POST /audit-logs/query（11 维过滤 + 子查询 count + LIKE 模糊 + 分页）
>    - GET /audit-logs/statistics（内存聚合 + unknown 桶）
>    - GET /audit-logs/operation-types（39 枚举展开）
>    - 范式：aiosqlite 异步内存库 + AsyncSession + 覆盖 get_async_db
>    - 子代理审查修订（+7）：排序完整序列断言、count 解耦 offset 验证、msg 排除断言防 service 吞异常假通过、401 body 断言、枚举 value 集合相等、LIKE 通配符已知行为、download-export 约定差异
>
> 2. **仪表盘统计接口**（commit 39e4b97 + 1485986 + 399b68b + 1c05d16，23 测试）
>    - GET /dashboard（裸 SQL 聚合 cron_task/torrent_audit_log + 内存缓存 store/torrent_stats）
>    - 范式：aiosqlite 异步内存库 + SimpleNamespace FakeStore 注入 app.state
>    - 经 **4 轮子代理审查**完全收敛：第1轮发现 1 真 flaky（60秒窗口）+ 1 假通过（dr 方向）；第2-4轮逐轮确认上轮到位 + 补覆盖盲区（dict 计数 vs set、keyword_rule 归一化路径、torrent_stats=None 已知行为）
>    - 关键修复：时间断言用绝对时间/身份标记避免 flaky；降级场景加 msg 断言防假通过
>
> 3. **种子删除 L4 接口**（commit 1e9a10f + 4ac69af，22 测试）
>    - DELETE /torrents/delete-with-level（L4 待删除标签路径）
>    - **设计转折**：原计划 HTTP e2e 经子代理审查发现 3 个 🔴 致命缺陷（同步/异步库不可共享内存库、响应字段缺失、store 未挂载），**重设计为 service 级测试**绕开三缺陷
>    - 范式：同步内存库 + mock request（挂 store）+ mock audit（AsyncMock 记录调用）
>    - 子代理审查修订（+4）：补 delete_batch_by_level 降级编排测试（L3→L4，service 核心复杂度零覆盖）、audit 身份锁定断言、OR 断言收窄、脏数据边界
>
> 4. **测试基础设施去重**（commit c881d69，重构）
>    - 提取 make_torrent 工厂到 tests/api/conftest.py（3 文件去重 → 1 共享工厂，13 业务 kwarg 超集签名）
>    - 设计决策：普通函数（非 fixture，接 db 参数多次调用）；test_torrent_models 的 MagicMock 工厂不合并（不同关注点）
>
> **关键测试质量教训（多轮审查沉淀）**：
> - **flaky 防护**：时间断言用绝对时间/足够裕度/身份标记，不用"恰好当前时间"
> - **防假通过**：降级/空数据场景加 msg 排除断言（防 service 吞异常返回空结构仍 code=200）
> - **身份锁定**：过滤测试断"返回哪条"而非"返回几条"（防方向写反）；audit 断 torrent_info_id
> - **完整序列 + 计数**：排序用完整顺序断言（非首尾比较）；分类用 dict 计数（set 漏计数）
> - **service 级 vs HTTP e2e**：当 endpoint 有同步/异步双 session + 响应字段裁剪时，service 级测试绕开共享库与字段缺失问题，且能测到完整返回字典
>
> **子代理审查的工作流价值**：每轮审查都实证核实（不盲信），发现真问题（flaky/假通过/盲区）也否决误报（如"len==len 恒真"实际能抓到）。4 轮审查收敛性：第1轮发现最多（质量基线），后续轮次确认到位 + 补越来越细的盲区。
>
> ---

> **2026-06-27（续）**: 收尾——v1.0.5-audit 标 done + 前端验证补遗 + 残留分支清理。
>
> **v1.0.5-audit 契约审计收尾** ✅
> - feature_list.json 中 v1.0.5-audit 的 8 个子任务（P0-1~P0-3 / P0-2a-d / P1-A/B）全 done，范围明确（P0+P1 完成，P2/P3 推迟有记录）。feature 顶层 status 从 `in_progress` 标为 `done`
> - **残留分支清理**：原独立分支 `fix/contract-audit` 的所有 commit 已 100% 合并入 dev（`git log dev..fix/contract-audit` 为空，dev 领先 29 commit）。删除本地 + 远端 `fix/contract-audit`（用户决策"删本地+远端"）。远端现仅剩 `origin/dev` + `origin/master`
>   - 注：`git branch -d` 因本地相对上游 `origin/fix/contract-audit` 的保守判断报"未完全合并"，但相对 dev 实际已无独有 commit，改用 `-D` 强制删除（reflog 可恢复）
>
> **前端验证补遗（清除 progress.md 既有遗留）** ✅
> - 既有遗留"前端 lint/tsc 因环境依赖未完整安装"（progress.md:99）现环境就绪，补跑：
>   - `npm run lint`：**0 errors**（131 warnings，全是 no-unused-vars 非阻塞）
>   - `npx vue-cli-service build`：**成功**（含 tsc 类型检查，dist 生成）
>   - `npm run test:unit`：**34 passed**（含契约审计的 ApiError 归一化测试）
> - progress.md:99 遗留标记为已补验
>
> ---

> **2026-06-27**: 高风险 lint 技术债 3 类清理（F811 + E711/E712 + mypy ORM 债评估）——lint 技术债清理第七轮。
>
> **任务 A：F811 高风险残留清理（5→0）** ✅
> - cuser.py：两个 `twofa_verify` 绑不同路由路径（/2faVerifyQrCode/ 与 /2faVerifyCode/），FastAPI 按路径注册故路由正常工作，仅模块级变量被后者覆盖（无调用点）。改名为 `twofa_verify_qrcode`/`twofa_verify_code` 消除 F811（无害变量重定义，**非 bug**）
> - torrents_async.py：`qb/tr_add_torrents_info_only_async` 各定义 3 次。经 **AST 对比 + git 历史追溯（初始 commit 8fe877d）** 确认：tr 三份 IDENTICAL（copy-paste 死代码）；qb 前两份一致（含 tracker 富集），第三份（生效版，Python 后定义覆盖前定义）**从 day 1 起就不含 tracker 富集**（富集只在 tracker-only 同步函数 `qb_sync_trackers_only_async` 里）。三份重复定义自项目诞生即存在，生效版始终是第三份。删除前两组死代码副本（**-678 行**），保留生效版。调用方仅 `torrent_info_sync_task.py`，行为不变
> - **审查教训（子代理发现）**：首版 commit ba8689b 把"第三份去掉富集"误归因到 73df90c。`git log -S "_enrich_..."` 命中 73df90c 是因为它**新增**的 tracker-only 函数含此调用，而非从 info_only **删除**。`git log -S` 只说明该 commit 涉及该字符串，**不能推断增删方向**，必须看 hunk 的 +/- 行（73df90c 的 hunk `@@ -3142,3 +3142,222 @@` 证明只在文件末尾追加、未动 info_only）。已更正文档
> - **门禁收紧**：F811 从 .flake8 extend-ignore 移除，进入全仓门禁。commit ba8689b
>
> **任务 B：E711/E712 全量清理（47→0，最高风险）** ✅
> - **逐个甄别 47 处** == None / == True / == False，区分 ORM 查询（保留语义）与 Python 条件（改 is），**不盲改**避免破坏 SQLAlchemy 查询生成
> - 44 处 ORM `.filter()`/`.where()`/`or_()`/`case()` 内的 `== True/False` → SQLAlchemy 官方推荐的 `.is_(True)`/`.is_(False)`（生成 IS true/false，对 NOT NULL boolean 列与 `==` 语义等价）
> - 3 处 Python 条件：`torrent_sync.py:712 create_time==None→is None`；`torrent_sync.py:1165 downloader.enabled!=True→not downloader.enabled`（已加载实例属性，三态完全等价）
> - 4 处 `downloader.py delay==False`：**0==False 真值陷阱**（ping3.ping 返回值可能是数值/False/None，改 is False 会改变 delay=0 真值）→ **用户决策**加 inline `# noqa: E712` 保留==
> - **子代理 code review（修复者盲点防护）补充修复 3 处**：tracker_messages:90 + cron_crud:418/420 是历史 ORM noqa 顶替（应做 .is_() 而非 noqa），扫描时被默认 noqa 掩盖漏报，一并修正
> - **门禁收紧**：E711/E712 从 .flake8 extend-ignore 移除，进入全仓门禁。commit 7a21718
>
> **任务 C：mypy app/models/ ORM 债评估（133 处，只评估不实施）** ✅
> - 133 errors（117 assignment + 10 return-value + 4 arg-type + 2 var-annotated，9 文件）**100% 归因 ORM 描述符类型推断失败**（`Base=declarative_base()` 1.4 风格），非真实 bug
> - **SQLAlchemy 已是 2.0.47**（无需升级依赖），但未启用 mypy 插件
> - 三方案评估：A 迁移 `DeclarativeBase`+`Mapped[]`（长期最优，17文件146字段，2-3会话）/ B 启用 mypy 插件（短期过渡降噪）/ C 保持现状
> - 评估报告写入 `backend/docs/tech-debt-lint-baseline.md`，**不实施代码改动**，建议作为独立技术债任务单独立项
>
> **验证**：每任务后 pytest（A: 1619 passed；B: 1619 passed）；flake8 全仓 0 错误；F811/E711/E712 isolated 全 0；历史修复全完好。
>
> **lint 技术债清理里程碑**：7 轮清理后，`.flake8` extend-ignore 仅剩 E203/E402/E501/W503/W504/W605 六项（风格/格式类），所有进入豁免的历史 F/E 规则（F401/F541/F811/F821/F824/F841/E711/E712/E722/E741）已全部清零进门禁。剩余仅 mypy ORM 债（架构级，待 SQLAlchemy 2.0 迁移独立立项）。
>
> ---

> **2026-06-26（续4）**: F811 重复 import + E722/E741 风格清理——lint 技术债清理第六轮。
>
> **任务：F811 重复 import（部分）+ E722 + E741** ✅
> - F811：15→5（清 10 处：7 模块级重复 import 删除 + 3 函数内局部 import 加 noqa；剩 5 处是高风险项单独记录）
> - E722：2→0（裸 except 改 except Exception，避免误捕 KeyboardInterrupt）
> - E741：2→0（列表推导式变量 l 改 label）
> - **门禁收紧**：E722/E741 从 `.flake8` extend-ignore 移除（F811 保留豁免，仍有 5 处残留）
>
> **F811 调研发现 2 个真实 bug（高风险，单独记录未修）**：
> - `torrents_async.py`：`qb/tr_add_torrents_info_only_async` 各定义 3 次（copy-paste 残留），需验证内容一致性
> - `cuser.py`：`twofa_verify` 同名函数定义两次绑不同路由。FastAPI 按路径注册故两条路由正常工作，仅模块级变量被后者覆盖（无害），建议改函数名消除 F811（子代理审查修正：非"路由 bug"，是"无害变量重定义"）

> **子代理审查后修正（91140f3）**：
> - 3 处 noqa: F811 的注释从误导性的"与另一函数不冲突"改为准确的"与上方冗余，保留以降低独立 try 块对顶部 import 顺序的耦合"（实为同一函数内冗余 import，功能无害）
> - cuser 判断从"潜在路由 bug"修正为"无害变量重定义"（两函数绑不同路径，路由正常工作）
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；E722/E741 isolated 0；历史修复全完好。
>
> **剩余 lint 债**：F811 高风险 5 处（重复函数/同名 bug）、E711/E712 高风险 47 处（ORM 甄别）、mypy ORM 债 133（SQLAlchemy 2.0 迁移）。
>
> ---

> **2026-06-26（续3）**: P2 F841 未用变量清理（23→0）——lint 技术债清理第五轮。
>
> **任务：F841 局部变量赋值未用全部清理 + 进门禁** ✅
> - 8 文件 23 处：
>   - 16 个 `except ... as e:`（e 未用）→ `except ...:`（保留异常类型去绑定）
>   - 5 个 `torrents = client.xxx()` 连接健康检查 → `client.xxx()`（**保留调用去赋值**，调用是健康检查不能丢）
>   - 1 个 `manager = Service(db)` → `Service(db)`（保留调用）
>   - 1 个 `module = importlib.import_module()` → `importlib.import_module()`（保留导入副作用）
> - **门禁收紧**：F841 从 `.flake8` extend-ignore 移除，进入全仓门禁
>
> **过程中的脚本踩坑（已解决）**：
> - 首版正则 ` as e:\s*$` 的 `\s*$` 吞了行尾换行符，把 except 行和下一行合并成一行（IndentationError）
> - 已 `git checkout HEAD` 回滚，修正为 `line.replace(' as e:', ':')` 只替换子串不碰换行
> - **教训**：处理含换行的文本时，正则的 `$`/`\s*$` 会跨行，应用 `str.replace` 精确替换子串
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541/F821/F824/F401/example= 均无回退；py_compile 全部通过。
>
> ---

> **2026-06-26（续2）**: P5 Pydantic example= 全仓统一（177→0）——lint 技术债清理第四轮。
>
> **任务：Pydantic v1 `example=` → v2 `examples=[]` 全仓清理** ✅
> - 10 文件 166 处（含 app/models/ 之前清的 11 处，共 177→0）：`example=X` → `examples=[X]`
> - 正则方案（字符串/数字/bool/None/空列表 4 类字面量精确匹配），修复后 example= 全清零
> - 补全被 Pydantic v2 静默忽略的 OpenAPI schema 示例值
> - **意外收益**：pytest warnings 865→713（`example=` 的 PydanticDeprecationWarning 消失）
>
> **过程中的脚本踩坑（已解决）**：
> - AST 脚本因 col_offset 是 UTF-8 字节偏移（含中文行与字符索引不一致）导致插入位置错误，损坏 api/responseVO.py
> - 已 `git checkout HEAD` 回滚，改用正则方案（不依赖字节偏移），165 处全清零无误
> - **教训**：Python ast 的 col_offset 对非 ASCII 行是字节偏移，不能直接用于字符串切片
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541/F821/F824/F401 均无回退；schema examples 生成验证通过。
>
> ---

> **2026-06-26（续）**: P3 F541 f-string 清理（74→0）——lint 技术债清理第三轮。
>
> **任务：F541 无占位符 f-string 全部清理 + 进门禁** ✅
> - 26 文件 74 处 `f"无占位符"` → 普通字符串（72 处脚本批量 + 2 处多行拼接手工）
> - 修复前 AST 分析确认 74 处全部是纯字面量、无 `{{}}` 转义，可安全去 `f` 前缀
> - **门禁收紧**：F541 从 `.flake8` extend-ignore 移除，进入全仓门禁
>
> **⚠️ 过程中的工作树污染事故（已恢复）**：
> - 发现本地 dev ref 被某操作重置回 eaf677a（丢失 f867b09 P0 修复），导致在无 P0 修复的旧基础上误跑 F541 脚本
> - 症状诡异：`git diff HEAD` 显示无差异（被 autocrlf=true 掩盖），但工作树文件实际是旧内容
> - 根因定位：`git log` 发现 HEAD 是 eaf677a 而非 f867b09；`origin/dev` 仍有 f867b09
> - 恢复：`git reset --hard origin/dev` 对齐远端，P0 修复完好确认后在干净基础上重跑
> - **教训**：开始工作前必须 `git log` 确认 HEAD 状态，不能假设；`git diff` 在 autocrlf 下可能有假象，用 `git status` + hash 对比更可靠
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541 isolated 0；F821/F824 仍 0（P0 完好）。
>
> **剩余 lint 债**：P2 F841（23）、P4 E711/E712（47，需甄别 ORM 查询）、P5 example=（166）、F811（15）、mypy ORM 债（133）。
>
> ---

> **2026-06-26**: P0 真实 bug 修复（F821/F824，17→0）——lint 技术债清理第二轮。
>
> **任务：F821/F824 真实 bug 全部修复 + 进门禁** ✅
> - 6 文件 17 处 undefined name / global 误用全部修复：
>   - audit_logger.py（5 处）：补模块级 `logger` + `desc` import
>   - torrent_crud.py / torrent_deletion.py（3 处）：函数加 `request: Request` 参数（原 `req.app`/`request` undefined 会 NameError 崩溃）
>   - initialization.py（7 处）：2 个后台任务函数加 `app: FastAPI` 参数（原调用已注释=死代码）+ 删 4 处纯 dict 操作的无用 `global`
>   - tag_service.py（1 处）：删除 except return 后的孤儿死代码（含 undefined `tags`）
>   - security.py（1 处）：删 `_decryption_key_cache.clear()` 的无用 `global`
> - **门禁收紧**：6 文件的 F821/F824 per-file-ignores 全部移除，F821/F824 现进入全仓门禁
> - **教训**：torrent_crud.py 加 `request: Request`（无默认值）放在 `_user=Depends()`（有默认值）之后触发 SyntaxError，导致 180 个测试 setup ERROR；pytest 立即捕获，改为 `request: Request = None` 修复
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F821/F824 isolated 0 残留；init.sh 通过。
>
> **剩余 lint 债**：P2 F841（23）、P3 F541（74）、P4 E711/E712（47，需甄别 ORM 查询）、P5 example=（166）、mypy ORM 债（133，待 SQLAlchemy 2.0 迁移）。

---

> **2026-06-25**: lint 技术债清理（F401 + mypy app/models/ 渐进）——两项独立技术债任务。
>
> **任务 1：F401 未用 import 清理（基线 P1，最大单项收益）** ✅
> - autoflake 保守参数清理：**321 → 9**（清掉 310 个未用 import）
> - **陷阱规避**：autoflake 会误删 `database.py` 的 9 个 ORM 模型注册 import（防御性注册，注释明确意图），手工恢复 + 加 `.flake8` per-file-ignore
> - **附带修复**：`app/models/__init__.py` 的 `__all__` 拼写 bug（`TRANSER_STATUS_SUCCESS` → `TRANSFER_STATUS_SUCCESS`，导致重导出名不副实）
> - **门禁收紧**：F401 从 `.flake8` extend-ignore 移除 → 新增代码未用 import 现已进入门禁
> - black 修复 autoflake 删 import 后的空行副作用（E303/E302）
>
> **任务 2：mypy app/models/ 渐进清理** 🔶（部分完成，剩余归 ORM 债）
> - 修复前 145 errors → 修复后 133 errors（-12）
> - **修了 12 个真实类型 bug**：Pydantic v2 API 误用（`example=` → `examples=[]`，11 个；`ConfigDict(by_alias=)` 死键，1 个）。原 v1 写法被静默忽略导致 OpenAPI schema 无示例值
> - **剩余 133 个 100% 归因 ORM 描述符**：根因 `Base = declarative_base()`（SQLAlchemy 1.4 风格），mypy 不识别 `class X(Base)` 为合法类型。117 assignment + 10 return-value + 4 arg-type + 2 var-annotated。**解法是 SQLAlchemy 2.0 声明式迁移**（`DeclarativeBase` + `Mapped[]`），属独立大任务，不混入 lint 清理
> - **review 发现的遗漏**：全仓另有 166 处同型 v1 `example=` 写法（10 个文件，downloader/torrents/tracker/user/api 等），本次只清了 app/models/ 的 2 个 vo 文件，其余留作 P5 后续项
>
> **验证**：pytest 1589 passed（0 失败，0 回归）；flake8 项目配置 0 错误；mypy app/models/ 145→133；init.sh 全栈验证通过。
>
> **下一步建议**：F401 已彻底闭环。mypy 剩余的 133 个 ORM 债 + 全仓其他模块需等 SQLAlchemy 2.0 迁移（独立任务）。
>
> ---
>
> **2026-06-20**: v1.0.5-audit P0-2 认证统一全部完成——本会话完成 P0-2a（24 文件迁移，分 4 批）+ P0-2b（测试断言改造）+ P0-2d（弃用 verify_token_dependency），共 6 commit。
>
> **调研修正**：交接文档预估 ~21 文件 + ~102 处测试断言。实际调研发现：24 个文件；测试改造仅 32 处 inline 断言（因 test_auth_protection_extended.py 的 62 处走 _is_auth_rejected helper 已兼容 HTTP 401）。这改变了"必须原子配对"的前提，改为按风险分 4 批，每批 commit + 跑针对性 pytest。
>
> **完成清单**：
> - Batch A（10 token-only）+ Batch B（downloader/cron_tasks/tracker/torrent_crud/sync，最大 cron_tasks 20 endpoint）
> - Batch C（3 user_id 文件，advanced_search 旧 token 缺 user_id → HTTP 401 兜底，用户确认对齐 torrent_location 模板）
> - Batch D（4 mixed 部分迁移文件）
> - P0-2b：5 测试文件断言改造（含 tag_management mock_auth 改用 dependency_overrides）
> - P0-2d：verify_token_dependency 加 DeprecationWarning，cron_tasks.verify_token 已删除
>
> **附带修复**：多处预存在的"不安全 try/except 认证"（verify_access_token 失败返回 None 而非抛异常，旧代码 try/except 形同虚设，torrent_sync/tracker_messages/cuser 2FA 端点）。
>
> **验证**：后端 pytest 1523 passed（2 个预存在失败：test_unified_token_expiry 路径分隔符 bug + test_concurrent_requests flaky，均与本次无关）；init.sh 全栈验证通过。
>
> **下一步**：P0-2 全部完成。剩余 P2/P3 均为推迟项（REST 路由迁移、前端 any 治理、OpenAPI schema、分页字段统一、API 对照表 CI）。可选收尾：彻底删除 verify_token_dependency 定义。

---

### 传统模式 bug 修复 + 防回归基础设施 + 功能对齐（2026-06-28）

**目标**：传统模式(TraditionalView.vue)相对列表模式(index.vue)全面对齐——先修 bug，再建防回归基础设施，最后补齐缺失功能。

**方法论**：全程「子代理对抗审查 + 用户决策修订」循环——每个方案先用 Explore 子代理独立审查挑毛病，修正阻断项后再实施。

#### 阶段 1：Bug 修复（8 个，commit 含于防回归提交）
子代理精准审查 + API 签名亲核（deleteTorrents 后端只认 info_id/delete_data/id_recycle；token 存 Cookie 非 localStorage）。
- Bug#4 删除参数错误（hashes→info_id）、Bug#3 速度轮询（原生fetch+错token→getActiveTorrents封装）
- Bug#1 删除计数（字符串长度→逐种子）、Bug#2 文案语义（下载器组数vs种子数）
- Bug#8 选中状态重置、Bug#7 排序键（!!map→速度>0）、Bug#6 单条删除错误收敛、Bug#9 未用import

#### 阶段 2：三层防回归基础设施（commit 52ff81e）
子代理对抗审查修正 3 处阻断：AST selector 静默失效（firstArgument→arguments.0.value 实测）、L3 正则脚本对 index.vue 误报、L2/L3 scope 冲突。
- **L1 ESLint**：no-restricted-syntax 禁原生 fetch/token（esquery 1.7.0 实测 selector），no-unused-vars（warn 避免117历史债阻断CI），FileManagement.vue 文件级豁免
- **L2 纯函数+mixin**：utils/torrentBatch.ts（5纯函数，API依赖注入便于单测）+ mixins/torrentBatch.ts（薄封装），两视图删除~280行重复实现
- **L3 jest 单测**：行为契约断言（不怕等价重写）。反向验证：改回Bug#7原始形态→2测试变红，fetch规则实测拦截

#### 阶段 3：功能对齐（13项，分 P0/P1/P2 三批）
子代理审查修正 4 处阻断：toolbar布局缺失、4等级删除下沉硬伤（上帝mixin）、sort_by跨视图bug、下沉边界偏乐观。

| 批次 | commit | 内容 |
|------|--------|------|
| P0 | c286b7e | 活动开关/刷新/改路径/转移/Tracker操作·汇报·全局替换/详情Tracker增强（9项，对话框全复用） |
| P1 | c82a321 | 高级搜索/查询模板/查找重复 + sort_by统一修复（addedDate→added_date对齐后端ORM字段名） |
| P2 | 5df3ce8 | 4等级删除（纯函数+mixin分层，只做TraditionalView）+ 列设置（10列可隐藏） |

#### 验证
- eslint: 全程 0 error（123 warning 全为历史债，no-unused-vars 降为 warn）
- jest: 53 → 81 passed（净增28行为契约单测）
- mixin/utils 文件 0 TS 错误；两视图 template 噪音是项目既有 vue-tsc 推断问题

#### 关键设计决策
- **下沉边界清晰**：无副作用→utils纯函数（可单测）；Vue实例方法($loading/$message)→mixin；UI接线→视图。不造上帝mixin
- **4等级删除分层**：纯函数(构造/解析)+mixin(入口/轮询/loading+beforeDestroy清理)+视图(dropdown)，解决this.$loading/this.tableData/长轮询生命周期三矛盾
- **列设置独立key**：traditional_columns_visibility 与列表分开（两视图列结构不同）
- **查询模板路由**：traditional模式下index.vue未挂载，apply_template_id必须在本视图处理

#### 诚实边界（未做）
- index.vue 的4等级删除迁移（单独立项，P2只做TraditionalView）
- 详情面板「文件/Peers」占位tab（需后端API，属另一功能）
- showActiveOnly分页失真（标known-issue，对齐列表既有缺陷未根治）
- 主题切换不在对齐范围（传统模式用固定scss主题）

---

**最后更新**: 2026-06-28
---

### 质量门禁可信化（2026-07-10 续）

本轮继续修复前后端 lint/测试“假通过”问题：根 `init.sh --full` 与前后端 `scripts/init.sh --check` 已改为真实传播失败退出码；后端严格入口接入 Black、Flake8、Ruff、Mypy 与自定义架构 lint；前端 `npm run lint` 改为 `vue-cli-service lint --max-warnings 0 && node scripts/lint-vuex-action.js`。

已完成验证：
- 后端自定义架构 lint 的独立负向样例补齐，`pytest backend/tests/test_architecture_constraints.py` 为 21 passed。
- 后端 Black/Flake8/Ruff 基线通过；自定义 lint 已纳入 init/Makefile。
- 前端历史 129 条 ESLint warning 已清零，`npm run lint` 通过，并实际执行 Vuex `@Action({ rawError: true })` 自定义检查。
- Vuex lint 脚本新增可测试导出与正反例单测，`npm run test:unit -- lint-vuex-action.spec.ts` 为 2 passed。

仍保持真实阻断：`mypy app` 存在历史类型债务，严格入口会失败，不做吞错、不做“赋值通过”。后续应作为独立类型治理任务处理。

**最后更新**: 2026-07-10

---

### 传统模式 code review 修复与回归闭环（2026-07-18）

本轮按三个子代理的后端同步、后端分页/元数据和前端传统模式审查结果，修复全部已确认的 P1/P2 问题。

- qB 增量同步改为数据库写入和提交成功后才推进 RID；完整水合为空、部分返回、超时或写库失败时保留旧 RID，并补齐删除路径和首次同步失败回归。
- 元数据补全支持 qB/Transmission 分下载器、分批调用与批次级故障隔离；新增有界正负缓存和轮转游标，避免大数据量在缓存淘汰下长期补不到后续记录。
- 重复任务十万分页改用分页子查询联接，稳定排序加入唯一键；高级搜索和普通列表的 Tracker/下载器数据统一批量预取，并动态遵守 SQLite 变量上限，消除逐行查询。
- 传统模式用 `downloader_id + hash` 作为跨下载器行身份，修复选中、高亮、详情、删除和速度映射串行；活动排序改为线性建索引后排序，覆盖 100000 条数据。
- 普通、重复、高级和模板查询各自保持分页来源，以请求序列丢弃过期响应；分页组合框、过滤按钮及虚拟列表补齐键盘、ARIA、焦点和生命周期回归。

验证结果：后端全量 `pytest tests -q` 为 **2154 passed、1 skipped、0 failed**；前端全量 Jest 为 **16 suites / 265 tests**，TypeScript、严格 ESLint、Vuex lint 和生产构建均通过；变更文件 Flake8、Ruff、Black API 格式校验及 `git diff --check` 通过。根 `init.sh` 因当前 Windows 无可用 WSL 无法执行；Mypy 仍存在项目既有 SQLAlchemy/VO 类型债务，未通过本次任务掩盖或降级。

**最后更新**: 2026-07-18

---

### 孤儿种子删除低置信度超时 —— 初步修复 + 调试日志（2026-08-01）

#### 问题现象
孤儿种子页面删除低置信度种子时出现超时；docker 部署环境下看不到业务日志。

#### 根因定位（经多路子代理深度审查确认）
超时不在删除动作本身，而在删除前的实时 manifest 复核：`_build_realtime_manifest` 对 qBittorrent 需逐种子远程拉取文件清单（`torrents.files`），真实并发被 `DOWNLOADER_IO_CONCURRENCY=2` 钳制，大下载器（数千种子）耗时远超前端 120s。关键放大因素：`16ca426` 放行低置信度后，数量庞大的 low 候选首次进入 `cleanup_orphans`，而它们的 downloader 大概率仍离线——为其拉取整下载器逐种子清单既慢又常被 fail-closed 拒绝（纯浪费）。docker 下看不到现场的原因：超时日志写的是 `logger.debug`（root=INFO 不输出）+ `LOG_LEVEL` 环境变量是死配置（docker-compose 声明了但代码从不读）。

#### 本轮修复（7 文件）
1. **日志可见性彻底修复**：`config.py` 新增 `LOG_LEVEL` 字段（BaseSettings 自动消费环境变量）；`main.py` 接通 LOG_LEVEL + 日志格式加时间戳 + 压制第三方噪声库（sqlalchemy/urllib3/qbittorrentapi 等，避免 DEBUG 时洪水 + cookie 泄露）+ 传 `log_level` 给 uvicorn Config（避免被 uvicorn 默认覆盖）；`btdeck_startup.sh` 的 `--log-level` 改为读环境变量。
2. **超时日志 DEBUG→INFO**：`downloader_api_runtime.py` 的超时/异常日志从 DEBUG 提到 INFO 并加 duration，docker 下即可定位超时事件。
3. **manifest 构建全链路耗时埋点**：`orphan_manifest.py` 的 build()/inventory 拉取/并发 gather 四处加 INFO 耗时日志（种子数/并发度/降级数/耗时）。
4. **三条删除路径耗时埋点**：`orphan_file_service.py` 的 cleanup_orphans / auto_cleanup_expired / purge_expired_quarantine 三处加 INFO 耗时日志；purge 路径特别记录循环内重复构建 manifest 的次数与累计耗时（暴露 1+2N 次构建的性能热点）。
5. **低置信度分流优化（核心治本）**：cleanup_orphans 的 manifest required 集合只放 high 候选所属下载器，low 候选不再触发全量逐种子拉取；新增 `_authorize_low_confidence` 方法——downloader 在线走标准精筛授权（保留恢复后可清理合法路径），仍离线则用 directory_whitelist 做目录级 fail-closed 兜底复核。
6. **前端超时 120s→300s**：`orphan-files.ts` 放宽作为保险（配合分流优化，300s 足以覆盖 high 候选的 manifest）。
7. **并发参数 env 化**：`DOWNLOADER_IO_CONCURRENCY` 保持默认 2（避免 requests.Session 非线程安全风险 + 全局影响其他 lane），补充注释说明可通过环境变量调整。

#### 审查修正的关键问题
- E2（致命）：原计划 LOG_LEVEL 接通不完整（basicConfig 会被 uvicorn 覆盖）→ 改为同时传 uvicorn Config + config.py 加字段。
- E1：DEBUG 会触发第三方库洪水 → 配套压制。
- D1：遗漏 purge_expired_quarantine（循环内重复构建 ~2N 次）→ 三条路径都加埋点。
- B2：被忽视的治本方案（low 候选拉 manifest 是浪费）→ 采纳分流优化。
- 3 处 import 遗漏（main.py 缺 os；manifest/file_service 缺 time）→ 补入。

#### 验证结果
- 后端 black/flake8 通过；mypy 无新增错误（84→85 仅行号偏移，diff 后零新增）；pytest 孤儿套件 **78 passed, 1 skipped**（含新增 `TestAuthorizeLowConfidence` 4 个用例）。
- 前端 `npm run lint` 通过（No lint errors + contract check）。
- 治本（manifest 缓存/异步化）留待日志确认现场后再做。

#### Hotfix：uvicorn --log-level 大写报错（2026-08-01）
重新部署时镜像启动报错 `Invalid value for '--log-level': 'INFO' is not one of 'critical','error','warning','info','debug','trace'`。根因：docker-compose 传入 `LOG_LEVEL=INFO`（大写），而 uvicorn CLI 要求小写；`btdeck_startup.sh` 用 `${LOG_LEVEL:-info}` 原样透传未转小写。修复：改用 bash 参数扩展 `${VAR,,}` 转小写后再传给 `--log-level`。已验证 python:3.11-slim 自带 bash 5.2 支持 `${VAR,,}`，且对 INFO/DEBUG/空值等各种输入均正确输出小写。main.py 的 Config(log_level=...) 路径用 Python `.lower()` 不受此问题影响。

#### 日志可见性二次修复：app logger 独立 handler（2026-08-01）
用户反馈删除成功但 docker logs 仍看不到业务日志（能看到启动 print）。经子代理用 uvicorn 源码复现验证，basicConfig(force=True) 理论上是最终赢家，但为确保彻底脱离 root/basicConfig 的不确定性，改用更稳健方案：给 `app` logger 树装独立 `StreamHandler(sys.stdout)` 并 `propagate=False`，业务日志始终由此 handler 输出到 stdout（与已验证可见的 lifespan print 同流），不受 uvicorn dictConfig/root 状态影响。另加 `[日志] app logger 已就绪` 验证日志，启动即可确认。

同时修复一个并发健壮性问题：本地环境 `LOG_LEVEL=warn` 导致 `Config(log_level='warn')` 触发 uvicorn `KeyError`（uvicorn 只接受 `warning` 不接受缩写）。新增 `_to_uvicorn_level` 规范化函数，兼容 warn/err/crit 等常见缩写，非法值兜底 info，三处（两处 Config + startup.sh）统一使用。

验证：black/flake8 通过；app.main import 成功；规范化函数 13 个用例全过；orphan pytest 25 passed/1 skipped。

#### 待办：隔离区管理功能（2026-08-01）
用户反馈需要处理 .btdeck_quarantine 里的文件。调研确认当前 BtDeck 无恢复/立即删除/隔离区列表功能，只能等定时任务（每天凌晨3点）隔离满7天后物理删除。规划新增：GET /orphan-files/quarantine（列表）、POST /orphan-files/restore（恢复）、POST /orphan-files/purge（立即彻底删除），涉及后端 service 方法 + API 端点 + 审计枚举 + 前端 UI。已完成可行性调研，待实施。

#### 隔离区管理功能实现完成（2026-08-01）
实现隔离区文件的三项管理能力，纯新增不破坏现有流水线：

**后端**：
- 审计枚举新增 ORPHAN_PURGE/ORPHAN_RESTORE（audit_enums.py，含中文映射+资源组）
- lifecycle service 新增 mark_restored（mark_quarantined 逆操作：status→candidate、清空 quarantine 字段）
- orphan_file_service 新增三个方法：get_quarantine_list（只读列表）、restore_quarantined（恢复+lease+审计）、purge_quarantine_now（立即删除+lease+审计，复用 purge_expired_quarantine 全套安全检查只跳时间门禁）
- API 端点：GET /orphan-files/quarantine、POST /orphan-files/restore、POST /orphan-files/purge

**安全底线**：
- 恢复：operation_state=stable 门禁 + quarantine_path 存在 + 原位不存在（防 Windows rename 覆盖）+ 路径逃逸复核 + verify_file_identity 身份复核
- 删除：保留 purge_expired_quarantine 全部检查（manifest 复核/路径授权/身份复核/tombstone），只跳 purge_after 时间门禁
- 两者都走 orphan_maintenance_scope lease 互斥 + 审计日志

**前端**：孤儿文件页面新增"隔离区"Tab，含列表（原位置/大小/隔离时间/预计删除时间/下载器）、恢复选中、彻底删除选中（带不可逆确认弹窗）

**验证**：后端 black/flake8 通过；pytest orphan 套件 83 passed/1 skipped（含 TestQuarantineManagement 5 用例：列表/恢复成功/恢复失败-原位占用/删除成功/删除失败-被引用）；前端 npm run lint 通过。

**最后更新**: 2026-08-01

## 2026-08-01 - 通知时间与主动清理异步化

### 根因与修复

- 通知表保存的是 UTC 的无时区 `DateTime`，`to_dict()` 原样输出后，浏览器按 Asia/Shanghai 本地时间解释，导致通知显示为约 8 小时前。新增统一时间序列化，所有通知 `created_at/read_at` 以及任务状态时间均输出显式 UTC `Z`；既有数据库数据无需迁移。
- 主动清理原先在 `POST /orphan-files/cleanup` 内同步执行 manifest 拉取、实时身份复核和隔离移动。现在复用 `orphan_purge_job` 持久化任务和串行 dispatcher，接口只保存 `scan_id + orphan_ids` 并立即返回 pending；后台仍执行原有安全门禁，终态为 completed/partial/failed，并幂等写入通知中心。
- 新增 `GET /orphan-files/cleanup-jobs/{task_id}`，用于诊断/状态查询；前端提交成功后关闭确认框并提示任务 ID，结果统一由通知中心送达，不再等待长请求或展示伪同步结果。

### 验证

- 后端：主动清理/通知/迁移相关 58 passed；回滚场景 8 passed；目标 Flake8 通过。
- 前端：相关 Jest 48 passed；`npm run typecheck`、严格 `npm run lint`、生产 `npm run build` 通过。构建仅保留既有 Sass/Element UI 弃用及体积警告。
- `git diff --check` 通过；未提交、未推送、未部署。

## 2026-08-02 - 批量添加异步化、路径映射排查与分时段限速修复

### 数据库只读排查

- 使用 `E:/Users/huangzj/Desktop/app.db` 只读查询 nickname=`tr`（Transmission，downloader_id=`c04cc424-b16a-4265-91dc-d22e704988d8`）。221 条 path_mapping 中 182 条 external 为空，且全部集中在 `/Downloads/bangumi`（181 条）和 `/Downloads/movie/`（1 条）。
- `path_mapping_rules` 共 13 条，覆盖 hpan/ipan/jpan/kpan，但没有 `/Downloads/bangumi{#**#}` 或 `/Downloads/movie{#**#}` 前缀规则；因此自动发现映射无法转换 external，留下空值。未修改外部 app.db；建议按实际容器挂载补充 `/Downloads/bangumi -> <外部 bangumi 路径>` 与 `/Downloads/movie -> <外部 movie 路径>`。

### 本次实现

- 批量添加种子移除前后端 10 个数量限制；上传文件流式落临时文件后立即返回 `code=202/task_id`，后台任务复用 `app.state.store` 客户端逐个处理，并在完成后写入通知中心（成功/失败数量及失败文件）。生命周期关闭时会取消未完成任务并清理临时文件。
- 前端请求拦截器已将 `202` 受理码纳入业务成功码，避免异步提交被误判为失败。
- 分时段限速修复：去除 `LIKE` 星期兼容误匹配，严格按当前 0-6 格式/含 7 的旧格式过滤；禁用分时段时恢复全局速度；调度器启动后立即同步并设置 `max_instances=1/coalesce=True`；设置应用接口在启用调度时按当前有效规则应用。

### 验证与环境

- 后端批量/限速/设置定向测试 36 passed；Python compileall 通过。
- 前端 `error-normalize.spec.ts` 34 passed，确认 `202` 异步受理码不会被请求拦截器当作业务错误。
- 前端 `npm.cmd run typecheck`、`npm.cmd run lint`、`npm.cmd run build` 通过；构建仅保留既有 Sass、Browserslist 和资源体积 warning。
- 根 `bash ./init.sh --ci` 在当前 Windows/WSL 环境因 `E_ACCESSDENIED` 无法执行；未执行 Git stage/commit/push/deploy。会话开始前已有未跟踪目录、备份、镜像归档和工具文件均未触碰。

## 2026-08-05 - 孤儿文件筛选交互优化与通知大小格式化

### 背景

用户提出三项调整诉求：1.孤儿种子页面去除"最小大小(字节)"筛选；2.孤儿种子页面下拉框采用种子列表页(列表模式)展示的下拉控件；3.清理/忽略种子通知的"释放空间"采用最接近的单位(如 57286409241 字节→53.35GB，而非 0.05TB 或 5万MB)。

### 决策过程（关键）

- 启动 3 轮子代理独立审查计划：前端深度、后端深度、规范完整性，每轮都实际读代码验证行号与调用点。
- 用户明确选择"筛选下拉换样式"+"改成多选语义"。
- **status 多选陷阱（我替用户做的判断）**：审查发现 status 三态(pending/ignored/deleted)互斥，同时多选会让 SQL `or_()` 退化为恒真条件（pending+ignored→所有未删除文件），这不是用户想要的过滤。用户授权"用最佳判断处理"，故决定 **status 保持单选(规避陷阱)，仅 downloader_id/confidence 改多选**。
- 问题3 采纳审查建议：_format_size 抽公共 utils(format_size.py)而非跨服务依赖私有下划线函数。

### 实现（按 1→3→2 低→高风险顺序）

**问题1 - 去除最小大小筛选**：删除孤儿页面 index.vue 模板/类型/默认值/查询快照/提交转换/重置共6处；删除 api/orphan-files.ts 的 OrphanListParams.min_size 与 OrphanSelectionFilters.min_size 死类型字段；同步 orphan-files.spec.ts。后端 min_size 保留兼容(记 backlog)。

**问题3 - 通知释放空间自适应单位**：新建 `backend/app/utils/format_size.py` 公共 `format_size`(自动选最近单位 B/KB/MB/GB/TB/PB，2位小数)；`orphan_notification._format_size` 改薄封装委托(扫描完成通知连带改善)；`orphan_purge_job_service` 释放空间行调用 format_size(用 int() 修 mypy Column 类型)。新增 test_format_size.py 11个边界测试。

**问题2a - 后端多值过滤**：`_build_orphan_conditions` 对 downloader_id/confidence 支持 split(',')去重→单值==/多值in_(仿 duplicate_torrents 范式)；status 保持单值(三态互斥)；min_size 不动；4 调用点(list/grouped/resolve/prefix_preview)自动受益。更新 orphan_files.py 端点与 OrphanSelectionFilters 的 Query description 声明多值。

**问题2b - 前端 AdvancedMultiSelect**：导出 AdvancedMultiSelect 的 SelectOption 类型；孤儿页面 downloader_id/confidence 的 el-select 换 AdvancedMultiSelect(allow-create=false, show-mode-toggle=false)；listQuery 字段改数组；**修复空数组提交判断 bug**(arr.length ? join : undefined，原 `|| undefined` 对空数组 truthy 失效)；status 保持 el-select；补 confidenceOptions getter(DownloaderOption 死接口删除)；测试同步 Vm 类型与 stub。

### 验证

- 前端：orphan-files.spec.ts 56 passed；npm run build 成功；npm run lint(含 contract:check) 通过；vue-tsc 类型错误数 2735 ≤ 基线 2736(未引入新错误，删除 min_size 字段反而消除 1 个旧错误)。
- 后端：orphan+utils+通知相关 181 passed(含新增 format_size 11个 + 多值过滤 2个)；改动文件 black/flake8 通过；mypy 仅修 1 个自引入错误(281 行 format_size 参数类型，已用 int() 修复)。
- 规范流程：feature_list.json 已登记 `orphan-files-filter-and-notification-polish`(3 task，status=done，含 evidence)；docs/roadmap 行号复测见下。

### 待办与 backlog

- `orphan_purge_job.py:42 total_size: Integer` 应改为 BigInteger(已存在隐患，单任务超 2GB 理论溢出)。
- 后端 `min_size` 死参数长期清理(前端已不传，后端保留兼容)。
- 未执行 Git stage/commit/push/deploy（按规范仅用户要求时提交）。

## 2026-08-05(续) - status 多选 + 路径框样式对齐

### 背景

用户追加两项诉求：1.孤儿状态(status)下拉也采用 AdvancedMultiSelect；2.文件路径模糊搜索框样式对齐 AdvancedMultiSelect 触发器。

### 决策（用户确认）

- **status 多选语义**：用户选"OR 并集 + 前端提示"。三态互斥，pending 与 ignored/deleted 组合时 SQL 退化为"所有未删除文件"，前端在退化时显示 ⚠ 提示文案。
- **路径框样式**：用户选"仅尺寸与圆角对齐"(32px 高/4px 圆角/12px 字号)，颜色仍用 el-input 默认。

### 实现

- **后端** `_build_orphan_conditions`：status 改为支持逗号多值，每个值用 `and_()` 打包(is_deleted + 忽视子查询)再 `or_()` 取并集；补 `and_`/`or_` import；单值仍走原路径(回归保护)。API description 与 OrphanSelectionFilters 同步声明多值。
- **前端**：status el-select → AdvancedMultiSelect；listQuery.status 改数组；提交/重置同步；新增 `statusOptions` getter 与 `statusFilterDegraded` computed(检测 pending+ignored/deleted 组合)，退化时在字段下方显示 ⚠ 提示；新增 `.management-filter__hint` 全局样式。
- **路径框**：path el-input 加 `orphan-path-input` class，scoped 注入 `::v-deep .el-input__inner` 的 32px/4px/12px 样式。
- **类型**：OrphanListParams/OrphanSelectionFilters 的 status/confidence 改为 `string`(接受逗号串)，与 downloader_id 一致(顺带修复上次遗留的 confidence join 类型问题)。

### 验证

- 前端：56 passed；build 成功；lint 通过；vue-tsc 2736 = 基线(未引入新错误)。
- 后端：orphan+utils 相关 158 passed(+1 skipped 预存)；black/flake8 通过；mypy status 分支无新错误(149 个均为预存 Column 误报)。
- 文档：roadmap 行号复测更新(resolve_orphan_selection L184→L199, get_orphan_list L547→L562, 总行数 2776→2791)。

### backlog（无变化，沿用上次）

## 2026-08-08 - Transmission 等级2删除超时：移除全量任务预查询

### 实现与判断

- 已确认现场为后端 `AsyncDeletionExecutor` 的单种子 30 秒超时，目标下载器为 Transmission，且目标种子确实存在。
- Transmission RPC 的 `torrent-remove` 支持直接使用稳定 SHA1 hash 作为 `ids`；等级2删除前的 `get_torrents()` 全量列表查询不是删除正确性的必要条件，反而会在任务较多时增加远程等待。
- `TransmissionDeleteAdapter._delete_torrents_impl` 改为直接使用传入 hash 去重后删除；保留目标任务的 `get_torrent_info()` 查询，用于现有安全告警，不改变告警语义。

### 验证

- 新增 `backend/tests/services/test_transmission_delete_adapter.py`，断言删除路径不调用 `get_torrents()`。
- Transmission 删除适配器 + 等级删除 API + 快捷删除 API：35 passed；目标文件 flake8 通过；新增测试 black check 通过。
- 已同步 `docs/roadmap/backend/services/README.md`；未执行 Git stage/commit/push/deploy。

## 2026-08-08(续) - 孤儿隔离区彻底删除：重跑幂等 + manifest 预构建（TDD）

### 背景

生产库（E:\Users\huangzj\Desktop\app.db）排查发现 2026-08-08 06:05 的删除任务 ea9555f4（20 文件）终态 partial（4 成功/16 失败"候选不存在或非 quarantined 稳定态"）。证据链：16 个候选 updated_at（06:06:40-06:33:50）早于任务 started_at（06:37:53），即第一次执行已删除 16 个后进程中断，重启恢复任务重跑时把已删项误报为失败。另实测每文件 1.5~2 分钟（20 文件约 40 分钟），系 `_purge_single_candidate` 每文件构建 2 次全量实时 manifest。

### 实现（TDD：先写 6 个失败测试 → 实现 → 全绿）

- 新增 `backend/tests/services/test_orphan_purge_idempotency.py`（6 测试）：
  - 幂等：已 purged 候选 → purged_count 计入、无失败；混合批次（已删+隔离中）→ 全部成功；
  - 区分报错：真不存在 → "候选不存在（未找到对应记录）"；已被恢复（status=candidate）→ 附实际状态；
  - manifest：同下载器 2 文件 → 仅构建 1 次（修复前 2N=4 次）；不同下载器 → 各 1 次。
- `purge_quarantine_now`（orphan_file_service.py）：
  - 未匹配路径按候选现状区分：status=purged → 幂等成功（重启重跑不再误报）；其他状态 → 附 status/operation_state；无记录 → 候选不存在；
  - manifest 按 downloader_id 预构建缓存（cast 辅助静态检查），`_purge_single_candidate` 增加 manifest 参数复用（None 时降级逐文件构建兜底）。
- 已知边界：`restore_quarantined` 存在同样的"未匹配→笼统失败"模式，本次未改（同批次处理，建议后续会话按同法修复）。

### 验证

- 新增 6 passed；孤儿全量回归 250 passed（+1 skipped 预存）；tests/services 全量 822 passed。
- black/flake8 通过；mypy 149 个错误全部为预存 Column 误报，本次未新增。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-10 - W4-2 实施：liveness/readiness/同步业务健康接口（PLANS/sync-database-blocking-remediation.md）

### 实现

- 新增 `backend/app/api/endpoints/health.py`：`GET /health/live` 仅证明进程响应，不访问数据库或下载器；`GET /health/ready` 执行严格超时的只读 `SELECT 1`，复用 `startup_guard` 的 SQLite 单 Worker 校验和 W4-1 `EventLoopLagSampler`，失败返回 503 统一响应体及非敏感 `reasonCodes`。readiness 不执行写探针，下载器离线只进入业务健康告警。
- 增加受认证的 `GET /api/v1/health/sync`：按任务返回最近 outcome、freshness、active run/phase、checkpoint age；下载器状态只读取缓存。Coordinator 增加进程内只读活动运行快照，贯穿 admission/backup/sync/tracker_status/done 阶段，不写入业务事实。
- 根路径与 `/api/v1/health/*` 路由均已接线；`backend/Dockerfile` 和 `docker-compose.yml` 的健康检查从 `/docs` 切换为 `/health/ready`，Compose 保留 5 分钟 `start_period` 覆盖启动对账。
- 修正 Windows SQLite Worker 启动测试的 Git Bash 选择顺序，并将 Bash 启动脚本输出显式按 UTF-8 解码，消除 CP936 环境下的测试读取假失败。

### 验证

- `python -m pytest tests/api/test_health.py -q`：9 passed。
- `python -m pytest tests/core/test_sqlite_worker_guard.py -q`：53 passed。
- 同步 Coordinator/观测回归：59 passed；cron/auth 回归：76 passed。
- 后端全量 `python -m pytest -q`：**3135 passed, 7 skipped, 0 failed**（3142 collected）。
- health.py 的 mypy、修改文件 black/flake8、`git diff --check` 通过；`./init.sh --ci` 通过。
- 本阶段无 Schema 变更，不新增 Alembic 迁移；已按源码漂移同步 `docs/roadmap/deploy/README.md` 的健康检查路径；未执行 Git stage/commit/push/deploy。路线图全量收口留给 W5 文档阶段。

## 2026-08-08(续) - W1 分批：同步数据库写事务短事务化（PLANS/sync-database-blocking-remediation.md）

### 背景

实施修复计划第一批 W1（P0 数据库事务修复，G1 门）：消除 info-only / Tracker 状态 / qB removed 三条写路径的单大事务与旁路写者，并建立最小文件型 SQLite 争用回归。修复执行交给 4 个子代理，主代理逐项审查（源码审查 + 亲自复跑测试）后通过。

### W1-1 通用写入改为真实分批提交（app/services/sync_db_write.py）

- `bulk_upsert_with_retry` 重写：每批独立 db_write_scope + DML + commit（批大小默认 `SYNC_DB_COMMIT_BATCH_SIZE=200`），批间 `asyncio.sleep(0)` 让行；新增 `WriteStats`（scanned/changed/committed/batches/retries/elapsed_ms）、`ChunkedWriteError`（携带部分进度统计，`__cause__` 保留异常链）。
- 锁冲突按 SQLite 错误码分类（5/6/261/262/266/517），**禁止消息字符串匹配**；非锁异常（IntegrityError 等）立即失败不重试；退避 = 指数 + `random.uniform` 抖动，单批总睡眠 ≤ `SYNC_DB_RETRY_MAX_BACKOFF_SECONDS=2.0`。
- 新配置：`SYNC_CHUNKED_COMMIT_ENABLED`（False 回退单事务，快速回滚开关）、`SYNC_DB_LOCK_RETRY_COUNT=3`、`SYNC_DB_RETRY_MAX_BACKOFF_SECONDS=2.0`；.env.example 同步。
- 消除对 `torrents_async._retry_on_db_lock` 的反向依赖（该函数保留给旧全量路径调用方）；info-only 两个调用点直接受益、零改动。

### W1-2 Tracker 关键词状态只写变化行（新 app/services/tracker_status_sync.py）

- 判定 + 写回从端点层整体搬迁至服务层 `sync_tracker_status_from_keywords(db)`，**判定规则逐行保持**（精确匹配优先 → 部分匹配 → unknown；全部 failed→error / 有 success|ignored→normal / 其他→unknown）；Step2 追加查询现有 status/msg 用于变化检测（strip 归一化对比）；变化集走 W1-1 统一分批写入；**零变化不进 db_write_scope、不 UPDATE、不 commit**。
- `update_tracker_status_from_keywords`（torrent_sync.py）改为兼容包装：自建会话 → 调服务 → 映射回原 dict 结构并追加 scanned/changed/unchanged/batches/duration_ms；两个调用方（torrent_sync_async / tracker_sync_task）零改动。
- 新配置 `SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED`（False 回退全量写回，判定规则不变）。
- 发现并钉住：重复关键词实际保留**先读取的**值（原注释"保留后读取的"与行为不符）；按"规则逐行保持"约束未改语义。

### W1-3 qB removed 标记纳入统一写治理（app/api/endpoints/torrents_async.py）

- `_mark_qb_removed_torrents` 重写：事务外只读查询待更新 ID → 空变更返回零值 `WriteStats`（不 commit）→ mapping 走 `bulk_upsert_with_retry`（统一批大小 + db_write_scope + 批级重试）；删除路径内自建 commit/retry；失败先 rollback 再原样上抛。
- 实测 TorrentInfo 为 **(info_id, downloader_id, downloader_name) 三列复合主键**，mapping 必须含全部主键列（否则 bulk_update_mappings 静默 0 行更新）。
- 架构测试追加：同步模块（removed 标记 / qB、TR info-only / qB、TR tracker-only 共 5 函数）DML 只能经批准写入口（bulk_upsert_with_retry / sync_trackers_batch_async）。
- 扫描发现的旧全量旁路写者（qb/tr_add_torrents_async 内嵌批处理、sync_add_tracker_async、mark_removed_trackers_*、死代码 _batch_commit_tracker_sync）留给 W2-1 Coordinator 收编，本轮未重构。

### 文件型 SQLite 争用回归（新 tests/integration/test_sqlite_sync_contention.py）

- 真实临时 .db + WAL + 两独立连接（NullPool 每事务独立 sqlite3 连接）；核心用例证明交互写 10 笔在同步 20 批分批写入期间全部成功且单笔 < 5s（远小于 busy_timeout 15s）+ 穿插证明；真实 SQLITE_BUSY 错误码分类（sqlite_errorcode=5）与 `bulk_upsert_with_retry` 真实重试恢复（retries>=1）；短事务提交边界锁释放（纯事件协议、零时间断言）；零变化同步不持锁。
- 22k 行 P99 < 250ms 基准以 `@pytest.mark.performance` + skip 预留（数据校准留给 G1 压测）；探针实测单批 commit P99≈5ms（Windows WAL + synchronous=NORMAL）。

### 验证

- **全量回归：2699 passed, 7 skipped, 0 failed**（162.8s）。
- 新增/改造测试：test_sync_db_write 31、test_tracker_status_sync 21、test_qb_removed_mark_governance 9、争用回归 5（+1 perf skip）、架构约束 22。
- black（10 个改动文件）通过（4 个测试文件先应用 black 格式化后复跑 83 passed）；mypy sync_db_write/tracker_status_sync 无错误；flake8 通过；torrents_async mypy 15 个错误为存量基线（stash 复测 HEAD 同数，未新增）。
- 回滚路径：`SYNC_CHUNKED_COMMIT_ENABLED=false` + `SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED=false` 即回旧写回行为，无 Schema 变更。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-08(续) - W2 分批：统一同步路径与请求响应性（PLANS/sync-database-blocking-remediation.md）

### 背景

实施修复计划第二批 W2（P0 同步路径与请求响应性，G2 门）。共 4 个子任务 + 2 个收尾切片，全部由子代理执行、主代理逐项审查（源码审查 + 亲自复跑测试）后通过。

### W2-1 统一 SyncCoordinator 消除手动同步旁路

- 新建 `app/services/sync_coordinator.py`（756 行）：`SyncRequest`（sync_type/trigger/run_id/deadline/force/dry_run/is_cancelled）+ `SyncResult`（outcome/phase/scanned/committed/skip_reason/errors/duration_ms）；`run_sync` 阶段编排：资源准入（复用 admission_controller，task_code 映射保证手动与定时互斥）→ 备份 hook（预留）→ 下载器解析（只从 app.state.store）→ sync phase（按类型复用 info-only/tracker-only/legacy full）→ tracker_status phase。
- 幂等运行键（downloader_id:sync_type，force 跳过）；取消在阶段/下载器边界检查，已提交批次保留；dry_run 零调用；结构化观测日志。
- `torrent_sync_db_async` 改 legacy adapter（转发 run_sync），`sync_single_downloader` 后台执行体走 Coordinator；`SYNC_CANONICAL_COORDINATOR_ENABLED` 开关应急回退。
- 旧全量写路径收编：qb/tr_add_torrents_async 内嵌 `_bulk_write_with_retry`（自建 500/批）迁移到统一 `bulk_upsert_with_retry`；文件备份段（TorrentFileBackup 逐条 commit）按计划保留为"同步后置短事务"边界并在报告中说明。
- 测试：test_sync_coordinator 20 项（手动/Cron 同源、竞争 already_running、admission 超时、取消 partial/cancelled、离线、dry_run、开关回退、API 兼容）+ 架构断言（手动入口不再调旧全量实现）。

### W2-2 交互下载器 API 容量保留

- `DownloaderApiRuntime` 两级信号量：total（DOWNLOADER_IO_CONCURRENCY=2 不变）+ background（新配置 DOWNLOADER_BACKGROUND_CAPACITY=1）；TRACKER/SYNC lane 为 background（必须同时取两级槽），INTERACTIVE 只取 total 槽 → 后台最多占 1 槽、恒留 1 交互槽；acquire 顺序 background→total、release 反向，无循环等待。
- 删除未生效的 `priority` 参数（grep 确认无调用方）；`queue_wait_ms`/`remote_call_ms` 线程内实测进入日志与窗口统计；timeout 文档化为总预算（含排队）。
- 矛盾组合防护：total=1 且 bg=1 自动降级 bg=0 + 警告（缓存 None 防重复告警）。
- 测试 34 项（交互穿插、多后台不超消费、超时后租约不绕过、异常/取消/shutdown 无泄漏、每下载器隔离、降级组合、timings 字段、priority 已删）。

### W2-3 清除 async 请求端同步下载器调用和漏 await（5 个垂直切片）

- **a. Tracker CRUD**（tracker.py）：修复 **4 处漏 await**（含 AsyncSession.commit 未 await 导致 TR tracker 添加/修改功能静默失效；sync def → async def）；6 处客户端自建改 store 获取；13 处裸同步改 call_downloader_api(INTERACTIVE)；新建 AST 架构测试框架 `tests/architecture/test_async_downloader_calls.py`（规则表 + 白名单 + 自检样例）。
- **b. 种子 CRUD/状态**（torrent_crud.py/torrent_status.py/torrent_helpers.py）：create_torrent 的 TR add/qB add/30 次轮询 3 处 + helper 签名扩展 downloader_id；pause/resume/recheck 6 处；3 处 `get_snapshot_sync()` 改 `await get_snapshot()`；轮询回归测试。
- **c. 标签/下载器**（tag_management.py/downloader.py/downloader_settings.py）：tag 两个 helper 10+2 处；downloader get_status 降级路径 async 化 + store 获取（删除 qbClient/trClient import）；test_downloader_settings **保留自建客户端**（合法测试连接场景，注释说明）+ 调用走 runtime；AST 增强（嵌套属性链检测 + 函数级豁免）。
- **d. 服务层收尾**（reannounce/recycle_bin/seed_transfer_service）：12 处裸同步 → INTERACTIVE lane；删除模块级客户端 import（AST 生效前提）；19 项新测试。
- **e. 删除/位置适配器**（downloader_adapters/ 4 文件）：14 处裸同步 → `asyncio.to_thread`（与同文件惯例一致，adapter 无 downloader_id 且工厂在约束外）；qB 用 lambda 形式保证懒建 `Client()`+`log_in()` 在工作线程求值（专项线程探针测试）；AST adapter 专用规则（to_thread 包裹豁免）。
- 全部保持 HTTP 契约/错误码/超时语义；AST 测试最终 30 项（含负向自检防假通过）。

### W2-4 SQLite 单 Worker 启动约束

- 新建 `app/core/startup_guard.py`（纯函数）：detect_backend（sqlite+aiosqlite 方言）/parse_worker_count/resolve_database_url/validate_worker_count（SQLite+workers≠1 抛可操作错误）/validate_scheduler_scope（PostgreSQL 多 Worker 显式"Leader 未实现"）/log_startup_manifest（database_backend/worker_count/scheduler_enabled/process_id）。
- 接线：main.py 模块加载期校验（外部 WORKERS 环境变量，绕不开）+ btdeck_startup.sh 纯 shell fail-fast（exit 1）+ lifecycle.py scheduler 启动处纵深防御；docker-compose 注释说明。
- 测试 53 项（含子进程验证两个启动入口 fail-fast）；受支持入口全覆盖（裸 uvicorn 不设 WORKERS env 的盲区已在报告中说明）。

### 测试基建修复（主代理）

- 全量回归发现 test_reannounce_service 15 项失败：根因是同一 pytest 进程中 api 目录的 with TestClient 测试触发 lifespan shutdown 关闭全局单例 `downloader_api_runtime` executor（不可逆），W2-3d 迁移后 reannounce 真实调用单例即失败（此前用独立进程跑 api 掩盖了该问题）。按仓库既有约定（test_torrent_speed_regression.py:456 注释同款）给该文件加 autouse fixture patch call_downloader_api 直接执行 func，修复后全量 2959 passed。

### 验证

- **全量回归：2959 passed, 7 skipped, 0 failed**（254.9s）。
- 新增测试：sync_coordinator 20、runtime 34、worker_guard 53、AST 架构 30、各切片端点/服务测试 24+31+19+22。
- black/flake8 通过（tag_management/downloader_settings 的 black 存量债务经 `git show HEAD` 验证为历史遗留，未新增）；mypy sync_coordinator/runtime/startup_guard/tracker_status_sync 无错误。
- G2 门运行观测类验收项（CRUD P95/P99 SLO、event loop lag P99 < 100ms）需真实运行环境数据：代码层阻塞路径已全部消除（架构扫描无未批准调用），量化验收留给 W4（W4-1 lag 采样器、W4-3 争用基准）与发布观察期。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-09(续) - W4-3 实施：真实文件型 SQLite 争用基准与响应性验收（PLANS/sync-database-blocking-remediation.md）

### 背景

实施 W4-3（P1-07：测试覆盖真实文件型 SQLite 争用）。2 个子代理执行 + 主代理逐项审查（源码抽查 + 亲跑验证 + 全量回归）后通过。

### 基准脚本（新 backend/scripts/sync_contention_benchmark.py，1506 行）

- **真实文件型环境**：独立临时目录 + 真实 .db + WAL/synchronous=NORMAL/busy_timeout=15000（与 app/database.py `_apply_sqlite_pragmas` 语义一致）+ NullPool + handle_error 层 SQLITE_BUSY 计数 + WAL 见证连接；最小 ORM 模型 3 张表（bench_torrent / tracker_info / tracker_keyword_config，后两者表名列名对齐生产）。
- **三档数据**：small 2k/3k、mid 10k/15k、large 22k/30k（对应生产规模）；大档生成实测 1.1s；合成数据无任何敏感信息。
- **场景 A/B/C**：A=真实 `bulk_upsert_with_retry`（batch 200）；B=真实 `sync_tracker_status_from_keywords` 两遍（第 1 遍全量写、第 2 遍验证零变化零 DML）；C=批量 UPDATE dr=1 逐批 commit+有界重试。请求探针：只读 count/分页/任务状态 + 单条 INSERT/UPDATE，每探针独立连接。
- **fake 下载器**：slow_func 经 `call_downloader_api` 真实调用（lane executor + 两级 semaphore + wait_for 超时路径，不跳过网络阶段），`--downloader-delay-ms` 控制。
- **故障注入**（--fault）：busy（持锁 300ms×4，断言真实 BUSY 计数>0、重试有界、最终一致）、cancel（中途取消，已提交整批保留无半批）、slow-downloader（2s 调用 1s 超时返回，事件循环零阻塞）。
- **SLO 发布门**（--assert-slo）：大档只读 P95<1s、写 P95<2s、超时率<0.1%、最终 BUSY 失败=0，不满足 exit 1。**本机大档实测全部 PASS：只读 P95=31.76ms、写 P95=33.32ms、超时率 0%、BUSY 失败 0，无需校准系数**。
- **输出**：stdout 表格 + `benchmark_results/sync_contention_<ts>.json`（环境信息/每场景指标/故障注入结果/WAL 增量，无敏感数据）。

### 响应性集成测试（新 backend/tests/integration/test_sync_api_responsiveness.py）

4 用例：info 风格分批写期间只读探针 P95<1.5s（实测 30.6ms）、tracker 风格批量更新期间写探针 P95<2.5s（实测 35.5ms）、2s 慢下载器调用期间事件循环心跳 P99<100ms（实测 16ms）、连续 BUSY 有界重试无雪崩（3 笔总耗时 2.63s）。断言窗口按计划允许放宽防 CI 抖动，实测值记录在报告。

### 故障注入集成回归（扩展 test_sqlite_sync_contention.py）

新增 4 用例：两次连续 BUSY 后成功、300ms 持锁交互写排队成功、慢下载器超时心跳不阻塞（max lag<1s）、取消中途整批保留。集成测试共 13 passed + 1 skipped（22k 性能基准）。

### 运维手册（新 backend/docs/operations/sync-contention-runbook.md）

基准命令、三档数据说明、故障注入说明、验收矩阵表、JSON 对比方法、CI/发布门接入建议（大档 --assert-slo）、环境校准系数方法（"生产门禁仍按绝对阈值"原则）、已知噪音记录（`_attach_done_stats` CancelledError 缺口为 W4-1 收口候选）。

### 审查中修复的问题（主代理）

- **worker_guard bash 定位**：`_find_git_bash` 兜底路径只含 C:/Program Files/Git，本机 Git Bash 在 E:/Git（且当前环境 PATH 无 git 导致推导失败）——补充 E:/Git、D:/Git 常见安装位置后 66 passed。
- **新集成测试的全局单例污染**：两个慢下载器用例调真实全局 runtime 单例，全量顺序下被 api 的 TestClient lifespan shutdown（与 W2 时 test_reannounce_service 同型问题）——两文件加 autouse fixture patch `call_downloader_api` 为"asyncio 默认 executor + wait_for 超时"（保持线程边界与超时语义，不依赖可被关闭的全局单例）。

### 验证

- **全量回归：2967 passed, 7 skipped, 0 failed**（248.1s）。
- 集成测试 14 项（13 passed + 1 perf skip）；基准脚本 small 档 SLO 4/4 PASS、busy 故障注入 3/3 PASS。
- black/flake8 通过；基准脚本与 runbook 无敏感数据。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-09(续) - W3-2 实施：持久化同步检查点（PLANS/sync-database-blocking-remediation.md）

### 背景

实施 W3-2（P1-03：全量同步状态仅在内存，重启后重复工作）。1 个子代理执行 + 主代理逐项审查（源码抽查 + 亲跑验证 + 全量回归）后通过。

### 模型与迁移

- 新建 `app/models/sync_checkpoint.py`（150 行）：`sync_checkpoints` 表 13 列按计划 Schema（downloader_id/sync_type/cursor_value/cycle_started_at/last_full_sync_at/last_success_at/last_attempt_at/outcome/detail_json/version/created_at/updated_at）；`(downloader_id, sync_type)` 唯一约束 + 双索引；`version` 乐观锁；**detail_json 白名单清洗**（sanitize_detail_json 只允许 scanned/changed/committed/batches/retries/duration_ms/version_conflicts 数值，敏感 key 不可能落库）；outcome 六态常量与 W3-4 对齐。
- 新建 Alembic 迁移 `3a4b5c6d7e8f_add_sync_checkpoints.py`（down=d8e9f0a1b2c3，upgrade/downgrade 完整往返）；`alembic/env.py` 注册模型；`test_db_migration.py` 期望值更新（EXPECTED_HEAD/表数 29→30）。

### SyncCoordinator 集成（sync_coordinator.py）

- `SyncCheckpointStore`（独立短事务，不抢 db_write_scope 写锁）：get_or_create（并发创建由唯一约束兜底）、乐观锁推进（UPDATE WHERE version=?，冲突时重读 + 单调合并：last_success_at 取 max、cursor 不覆盖、终态不降级，重试一次仍失败记 version_conflicts）。
- **cursor 不超前于数据**：推进严格滞后于批次 durable commit（重启后重做最后一批幂等安全）；批级推进 API `push_sync_progress` 预留给 W3-1。
- run_sync 集成：sync phase 初始化 checkpoint（cycle_started_at/last_attempt_at）→ 每下载器成功后推进（partial + last_success_at + 聚合统计）→ 终态落 outcome（success/partial/failed/skipped/cancelled，last_success_at 保留）；`_is_run_cancelled` 识别显式取消 → cancelled；dry_run 零读写；SyncResult.checkpoint 填充实际值（不再恒 None）；观测日志 checkpoint_loaded/advanced/finalized。

### 测试

- `tests/core/test_sync_checkpoint_migration.py`（2 项）：空库 upgrade→列/约束/索引核对→downgrade→再 upgrade；旧 head 建库+历史 task_logs 数据→升级→数据完整。
- `tests/services/test_sync_checkpoint.py`（13 项）：CRUD+唯一约束、乐观锁不倒退（cursor 保留/终态不降级/failed 保留 last_success_at）、首次运行创建、**重启续跑**（partial+cursor+二次运行经 get_run_checkpoint 收到续跑上下文）、取消 cancelled、dry_run 零副作用、并发推进不丢游标、detail_json 白名单。
- `tests/services/conftest.py` 新增 autouse `_isolate_checkpoint_store`（每测试独立内存库，防 run_sync 检查点写污染进程级测试库）。

### 审查中修复与确认（主代理）

- **test_db_rollback_scenarios.py 的 REV_HEAD 常量漏更新**（子代理只更新了 test_db_migration.py）：`d8e9f0a1b2c3` → `3a4b5c6d7e8f`，修复后 8 passed。
- **工作区存在并行会话的外部改动**（orphan_files.py 等升级为 submit_cleanup_job API + 前端多处）：orphan cleanup 2 个测试失败（500）经 git stash 二分确认为**外部未完成改动**（端点已换 submit_cleanup_job、测试仍 patch 旧 create_cleanup_job），与 W3-2 无关，未代修（待外部会话同步测试）。

### 验证

- **全量回归：2980 passed, 2 failed（仅 orphan cleanup 2 项，外部并行改动所致，非 W3-2 引入）**。
- W3-2 相关全部通过：checkpoint 迁移 2 + checkpoint 服务 13 + coordinator 20 + rollback 8 + migration 11。
- black/mypy/flake8 通过（模型/迁移/coordinator）。
- 未执行 Git stage/commit/push/deploy。


## 2026-08-09 - 孤儿删除硬链接副本检测与诊断（TDD）

### 背景

用户反馈孤儿删除不总能释放真实存储空间。代码核查确认：扫描阶段识别硬链接（共享 inode 不判孤儿），但删除阶段不检查 nlink——若被删文件存在其它硬链接（种子/媒体库），os.remove 后空间不释放，且用户无感知。

### 实现（TDD：7 测试先 RED 后 GREEN）

- 新增 backend/tests/services/test_orphan_hardlink_detection.py（7 测试）：find_hardlink_copies 单测（找副本/排除自身/限定扫描根）+ 立即删除有副本返回诊断 + 无副本无诊断 + 到期删除遇副本跳过 + 无副本正常删除。
- orphan_quarantine.py 新增 find_hardlink_copies：os.walk 比对 (st_dev, st_ino)，限定候选 downloader 的 scan_roots，排除被删路径，跨平台不依赖 find 命令。
- orphan_file_service.py：HardlinkCopyError 异常 + _detect_hardlink_copies（删除前抓 nlink，>1 才按需构建 manifest 推导 scan_roots 与 is_seed）；_purge_single_candidate 增 mode 参数：purge_now 照删+返回 hardlink_note；purge_expired 抛 HardlinkCopyError 跳过；purge_quarantine_now 收集 hardlink_notes；purge_expired_quarantine 捕获跳过、候选保持 quarantined、返回 skipped_hardlink。
- 模型/迁移：OrphanPurgeJob 加 hardlink_notes_json 列 + property + to_dict；Alembic f9a1b2c3d4e5（ADD COLUMN 可回滚）；finish_job/execute_job 透传；notify_job_result extra_data + 通知正文硬链接提示段。
- 前端：PurgeResult 加 hardlink_notes? + HardlinkNote interface。

### 设计决策（用户确认）

1. 副本枚举仅限候选所属 downloader 的 scan_roots；2. is_seed 用 manifest.expected_paths 判定；3. 到期删除遇副本跳过不删（安全优先），立即删除照删+上报副本位置与种子属性；4. inode 不可靠时立即删除照删（仅缺诊断），到期删除保守跳过。

### 验证

- 新增 7 passed；孤儿+迁移+API 全量 322 passed（+1 skipped 预存）。
- black/flake8 通过；mypy 各文件回到基线（orphan_file_service 149、orphan_purge_job 3 均为预存 Column 误报），新代码零新增错误。
- 迁移链升级/降级往返通过；EXPECTED_HEAD 同步更新为 f9a1b2c3d4e5。
- 前端 vue-tsc 未在当前环境运行（PATH 缺失），类型为纯增量可选字段。
- 未执行 Git stage/commit/push/deploy。


## 2026-08-09(续) - 清理阶段硬链接副本预警（TDD，选 B 方案）

### 背景

硬链接检测原仅覆盖删除阶段（隔离→物理删除）。用户反馈：清理阶段（candidate→隔离）若文件有硬链接副本，应尽早告知，避免反馈延迟（用户以为清理的是孤儿，实际可能与媒体库/种子共享存储）。设计选 B：清理是可恢复操作（7天保留期+可恢复），故清理照常隔离、不阻断，但在结果中返回 hardlink_notes。

### 实现（TDD：3 测试先 RED 后 GREEN）

- 新增 backend/tests/services/test_orphan_cleanup_hardlink_warning.py（3 测试）：手动清理有副本（照常隔离+预警+is_seed判定）+ 无副本（无预警）+ 自动清理有副本（照常隔离+预警）。
- orphan_file_service.py：
  - _detect_hardlink_copies 文档扩展 cleanup_warn 模式（与 purge_now 同走返回路径，永不抛异常，函数体无需改动）；
  - cleanup_orphans 隔离前调用 _detect_hardlink_copies(mode="cleanup_warn")，收集 hardlink_notes，return 加该字段；
  - auto_cleanup_expired 同样在隔离前检测+收集+返回 hardlink_notes。
- 复用既有通知链路：cleanup 任务结果 hardlink_notes 经 execute_job 透传 finish_job，通知正文已有"### 硬链接提示"段（上一次实现），无需额外改动。

### 验证

- 新增 3 passed；孤儿全量 237 passed（+1 skipped 预存）。
- black/flake8 通过；mypy orphan_file_service 仍 149（基线，新代码零新增错误）。
- 未执行 Git commit。

## 2026-08-09(续) - W3-1 实施：qB Tracker 有界队列与单轮预算 + 持久化 cursor 续跑（PLANS/sync-database-blocking-remediation.md）

### 背景

实施 W3-1（P1-01：qB Tracker 同步任务爆炸；P1-04 预算统一）。拆分两部分由子代理执行（完整任务连续 3 次触发子代理模型故障，拆分并限制大文件读取区间后成功）+ 主代理逐项审查通过。期间完成并行会话改动的合并验证（orphan API 已同步 29 passed、迁移链 3a4b5c6d7e8f→f9a1b2c3d4e5→f0e1d2c3b4a5 合并、rollback REV_HEAD 更新至 f0e1d2c3b4a5）。

### W3-1a 有界队列与单轮预算（torrents_async.py + config.py）

- `_enrich_qb_torrents_with_trackers` 重写：有界 `asyncio.Queue(maxsize=worker_count)` + 生产者/消费者（N 个 worker + 哨兵收尾），**禁止全量 create_task**；10k hash 时活跃任务数 ≤ worker_count + 2（实测断言）。
- 新配置：`QB_TRACKER_WORKER_COUNT=2`、`QB_TRACKER_MAX_TORRENTS_PER_RUN=1000`、`QB_TRACKER_RUN_BUDGET_SECONDS=120.0`、`QB_TRACKER_PER_CALL_TIMEOUT=30.0`；`QB_TRACKER_CONCURRENCY` 保留为兼容（不再控制任务数）。
- 预算：数量硬上限（原子计数严格 ≤ 上限）+ 时间软上限（拉取前检查）；`budget_reason: count|time|None`；生产者 put 带 wait_for 防预算到期后永久阻塞；观测字段 queue_depth/workers_active/processed_this_run/remote_error_rate。

### W3-1b 持久化 cursor 续跑 + cycle 语义 + RID 对齐 + 预算接线（torrents_async.py + sync_coordinator.py）

- cursor：JSON `{"last_hash": "..."}` 透明游标存 checkpoint `cursor_value`；hash 字典序稳定排序；跳过 ≤ cursor 的已 durable hash；新游标 = 最后已发起拉取的 hash。
- **仅 durable commit 后推进**：批 `sync_trackers_batch_async` commit 成功后经 `push_sync_progress` 推进；批失败 → 停止本轮、cursor 停在最后成功批（测试验证：第 2 批失败 → cursor=h000004，重试只处理 h00005+）；幂等 upsert 保证重做安全。
- **cycle 语义**：全部处理完（无预算/无失败/无错误）→ `last_full_sync_at` 更新 + cursor 清空（下一轮从头）；空集早退也 cycle_complete（清陈旧 cursor）。
- **RID 对齐确认**：qb 增量两处（L2113、L3031）均为 durable commit 后 `_confirm_qb_sync_rid`，顺序已正确无需调整。
- **Coordinator 接线**：`_sync_one_downloader` 透传 `SyncRequest.deadline/record_budget`；预算到期 → `SyncResult.outcome="partial"` + checkpoint 含 cursor；`finalize` 新增 `clear_cursor`（周期完整强制清空）。
- 测试 12 项（10k 任务数上限/数量/时间预算/续跑无重复无遗漏/批失败停驻/cycle 完整/稳定排序/预算透传）。

### 验证

- **全量回归：3044 passed, 7 skipped, 0 failed**（209.1s）。
- 新增/扩展：test_torrents_async_tracker_budget 12、sync_coordinator 20、sync_checkpoint 13、governance 7。
- black/flake8 通过；mypy 未新增错误（18 个存量基线）。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-09(续) - W3-3 实施：info-only 有界并发与分阶段流水线（PLANS/sync-database-blocking-remediation.md）

### 背景

实施 W3-3（P1-02：info 同时处理多个下载器，内存和 CPU 峰值高）。拆两部分由子代理执行（沿用 W3-1 的拆分 + 大文件读取区间限制经验）+ 主代理逐项审查通过。

### W3-3a 并发配置化 + 分页读取 + 内存/单轮硬上限（torrents_async.py + config.py + task）

- 新配置：`INFO_SYNC_DOWNLOADER_CONCURRENCY=1`（**SQLite 默认串行处理下载器**）、`INFO_SYNC_DB_READ_PAGE_SIZE=500`、`INFO_SYNC_MAX_TORRENTS_PER_RUN=10000`、`INFO_SYNC_RUN_BUDGET_SECONDS=300`、`INFO_SYNC_MAX_BUFFERED_ROWS=2000`。
- `torrent_info_sync_task.py` 的 `max_concurrent` 由硬编码 3 改为读配置。
- info-only 现有记录加载改**分页读取**（hash 排序 + offset 分页，每页后 `asyncio.sleep(0)` 让行）——cache 结构不变（diff 需要内存缓存），峰值内存摊平。
- 单轮预算（数量/时间，`budget_reason: count|time`）+ 缓冲上限（达 2000 行先 flush 再继续，flush 后清空 + 让行）；观测日志 phase_ms/rows_buffered/records_per_second/yield_count。
- 附带发现（未改）：既有变更检测 cache 字段集缺 hash 等键 → 已有行恒判 changed（update 而非 skip）——W2 语义，记录留待后续。

### W3-3b 流水线验证 + RID 完整性 + 内存峰值集成测试（新 tests/integration/test_sync_memory_bound.py，9 用例）

- **fetch 不持 DB 写锁 / write 无下载器调用**：真实文件型 SQLite 时序探针（fetch 全部结束才开始 commit、首个 commit 后零远程调用、commit 次数 = ceil(10k/batch)）。
- **并发符合配置**：真实生产链（TorrentInfoSyncTask.execute → execute_sync_with_concurrency → run_sync 计数探针内跑真实 info-only），4 下载器 × 10k，并发 1 时活跃 ≤1、并发 2 时峰值 ≥2。
- **内存峰值有界**：rows_buffered ≤ MAX_BUFFERED_ROWS + 下载器数×页大小（代理度量，psutil 未安装；真实 RSS 门槛留 G3 发布门基准）。
- **部分失败不阻塞**：第 2 下载器失败 → partial、其余 3 下载器完成。
- **RID 完整性判定：顺序已正确无需改**——`_confirm_qb_sync_rid` 仅在 bulk_upsert_with_retry 全部 durable commit 成功后调用（commit 失败 → 异常 → confirm 不执行）；增量异常回退分页全量仍受单轮预算限制（测试证明）。
- 生产代码零改动（纯验证 + 测试）。

### 验证

- **全量回归：3061 passed, 7 skipped, 0 failed**（208.4s）。
- 新增：test_torrents_async_info_budget 8、test_sync_memory_bound 9；integration 22 passed + 1 skip（既有 22k 基准）。
- black/flake8 通过。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-09(续) - W3-4 实施：任务 outcome/skip/freshness 六态语义（PLANS/sync-database-blocking-remediation.md）

### 背景

实施 W3-4（P1-05：调度成功、跳过和数据新鲜度语义混乱），W3 最后一项。后端/前端并行子代理执行 + 主代理逐项审查通过。

### 后端（cron_executor + 迁移 f5e6d7c8b9a0 + cron_freshness + API）

- **新迁移 `f5e6d7c8b9a0_add_task_outcome_freshness.py`**（down=f0e1d2c3b4a5，纯 ADD COLUMN 全部可空）：task_logs 加 outcome（String 20）/skip_reason（String 50 机器码：resource_busy/already_running/outside_budget/downloader_offline）；cron_task 加 last_success_at/last_attempt_at/last_outcome/last_skip_reason/last_run_id。迁移防护期望更新（EXPECTED_HEAD/REV_HEAD=f5e6d7c8b9a0）。
- **executor 落库六态**：结果 dict 支持 outcome/skipped/skip_reason（skipped 键不再丢弃）；success 布尔保持原语义（执行是否成功），outcome 是业务结果，两者并存；**重入跳过改为记录** TaskLogs（outcome=skipped + [REENTRANT_SKIP]）；准入跳过补 outcome/skip_reason（[ADMISSION_SKIP] 文本与 success=True 保持）。
- **freshness 推进**：每次执行更新 last_attempt_at/last_outcome/last_skip_reason/last_run_id；**last_success_at 仅 success/partial/no_action 推进**（skipped/failed/cancelled 不推进——计划关键语义）。
- **stale 计算**（新 cron_freshness.py）：APScheduler CronTrigger 解析 cron_plan 最短重复间隔（`*/5`→300s、日更→86400s），阈值 = 2 个调度周期，解析失败回退配置 `CRON_STALE_THRESHOLD_SECONDS=7200`；stale = 无 last_success_at 或 freshness > 阈值。
- **API**：CronTaskResponse 加 lastOutcome/lastSuccessfulDataAt/lastAttemptAt/lastSkipReason/lastRunId/freshnessSeconds/stale；TaskLogResponse 加 outcome/skipReason；logs 支持 outcome 过滤；CSV 导出追加两列；statistics 口径不变（success 布尔）。
- 测试：executor 12（六态映射/重入记录/freshness 推进）、admission 5（skip 追加 outcome 断言）、API 10（字段/stale/logs 过滤/NULL 兼容）、迁移往返 3。

### 前端（tasks.ts + tasks/index.vue + 测试）

- `TaskOutcome` 六态字面量联合类型 + `TASK_OUTCOME_META`（el-tag type + 中文文案）+ `getTaskOutcomeMeta`/`isTaskDataStale`/`getStaleTooltipText` 映射工具（无 any）；ScheduledTask/TaskLog 增补可选字段。
- 任务列表"上次执行"列：outcome 六态 el-tag + **数据陈旧 danger 告警 tag**（tooltip 提示成因与最后数据更新时间），旧数据回退仅时间/—；日志表/详情/复制文案六态（无 outcome 回退 success 布尔）。
- 测试：新 tasks-sync-freshness.spec.ts 18 用例（六态映射/stale 三场景/渲染/源码契约守卫）；api-contracts.spec.ts +2；**前端 635 用例全过、typecheck 0 错误、build 成功**。

### 验证

- **后端全量：3085 passed, 7 skipped, 0 failed**（200.9s）。
- 前端：test:unit 635 passed；typecheck exit 0；build 成功；lint 0 errors（5 个存量 warning 与本次无关）。
- black/flake8 通过。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-09(续) - W4-1 实施：阶段级结构化观测与核心指标（PLANS/sync-database-blocking-remediation.md）

### 背景

实施 W4-1（P1-06：缺少阶段级可观测性；P2-05 部分）。拆两部分子代理执行（完整任务与第一部分首跑均触发模型故障，重试后成功）+ 主代理逐项审查（含修复一处测试断言方式）。

### W4-1a 观测工具模块（新 app/services/sync_observability.py）

- **稳定事件名 + 字段字典**：EVENT_SYNC_RUN_START/ADMISSION/BATCH_COMMIT/CHECKPOINT/DOWNLOADER_CALL/LOOP_LAG/WAL_SNAPSHOT + EVENT_FIELDS 白名单（含 W4-1 最小字段集 run_id/phase/batch_rows/commit_ms/lock_wait_ms/lane/queue_wait_ms/wal_bytes 等）；`log_event` 白名单过滤 + key=value 输出 + 脱敏。
- **脱敏**：复用 log_sanitizer.sanitize_ip + 新增敏感 key（password/passkey/cookie/authorization/token）整体遮蔽、URL 保留 scheme+host+path 去 query/userinfo、hash 保留前 8 位。
- **lag 采样器**：loop.call_at 漂移法 + 滑动窗口 p95/p99/max；异常恢复不泄露 task；`SYNC_LAG_SAMPLER_ENABLED/INTERVAL_SECONDS` 配置；False 时 no-op。
- **WAL 快照**：`snapshot_wal_stats`（wal_bytes 文件大小，busy/checkpoint_busy 预留 None），纯只读不 TRUNCATE。
- **`_attach_done_stats` 修复**：cancelled future 先 `fut.cancelled()` 判断 + `except BaseException` 兜底（CancelledError 不再泄漏到 loop handler）。

### W4-1b run_id 贯穿 + 生命周期挂载 + 告警阈值

- **contextvars run_id 贯穿**：`set_run_id/current_run_id/clear_run_id` + log_event 自动附加；run_sync start/finally 设置/清空；sync_coordinator（RUN_START/ADMISSION/CHECKPOINT）、sync_db_write（BATCH_COMMIT + >500ms WARNING 阈值）、downloader_api_runtime（DOWNLOADER_CALL 成功/超时/失败）、tracker_status_sync（TRACKER_STATUS）全部接入 log_event。
- **生命周期**：lifecycle.py startup 启动 lag 采样器、shutdown 停止（与 downloader_api_runtime.shutdown 并列）；WAL 周期快照发射 EVENT_WAL_SNAPSHOT。
- **告警阈值**：单次 lag >500ms / P99 >100ms → WARNING；batch commit >500ms → WARNING（阈值常量在观测模块，初始值记录待两周基线校准）。
- **测试修复（主代理）**：阶段顺序还原测试原用 caplog 断言但 app.* logger 受 alembic fileConfig 级别干扰（records 只捕获 3 条）——改用 spy_log 断言（log() 调用序列），并删除子代理遗留的 DIAG print。

### 验证

- **全量回归：3126 passed, 7 skipped, 0 failed**（249.8s）。
- 新增：test_sync_observability 26（log_event/脱敏/lag 采样器/WAL 快照/_attach_done_stats 修复）+ coordinator 阶段顺序 2。
- black/flake8 通过。
- 未执行 Git stage/commit/push/deploy。

## 2026-08-11 - 孤儿文件硬链接副本数量实时展示

### 提交核查与实现判断

- 检查了近期硬链接相关提交：`d38c2db` 已实现清理/删除阶段的 inode 副本枚举与诊断，`a5e1e5b` 仅补前端 `PurgeResult` 类型，`0597423`/`f9ae521` 处理到期跳过延后与延后次数；主孤儿列表尚未返回或展示副本数量。
- 用户确认“副本数量”口径为 `max(st_nlink - 1, 0)`，不包含当前目录项；这可直接得到全文件系统链接总数，无需为列表逐项遍历扫描根。
- 文件扫描后已消失或 `stat` 失败时返回 `null`，前端显示 `-`，避免把“未知”误报成无副本 `0`。

### 实现

- `orphan_quarantine.py` 新增 `get_hardlink_copy_count()`，复用既有硬链接文件系统模块。
- `OrphanFileService._enrich_items()` 通过 `asyncio.to_thread` 顺序执行本页 `stat`，避免阻塞事件循环或并发打满 NAS；扁平文件行注入 `hardlink_copy_count`。
- 文件夹折叠行在全部子文件可读取时汇总副本数；任一子文件未知时文件夹合计为 `null`。
- 前端 `OrphanFileItem` / `OrphanFolderRow` 增加类型字段，孤儿列表新增“副本数量”列：普通文件明确显示 `0`，有副本显示实际数量，不可访问显示 `-`。
- 无数据库 Schema 变更，无 Alembic 迁移；列表字段为运行时计算。

### 验证

- 后端 TDD：新增测试先因缺少 `get_hardlink_copy_count` 导入失败，实施后 `test_orphan_hardlink_detection.py` 15 passed。
- 后端孤儿相关回归：`345 passed, 1 skipped`；列表/文件夹/API 定向组合 `82 passed`。
- 后端目标 Flake8 通过；`orphan_quarantine.py`、`orphan_file_service.py`、硬链接测试 Black 通过。`orphan_files.py` 当前与 HEAD 均存在同一既有 Black 格式差异，未扩大无关重排。
- 目标 mypy 仍为 `orphan_file_service.py` 既有 149 条 SQLAlchemy Column 类型债，本次新增行零错误。
- 前端 `orphan-files.spec.ts` 72 passed；`npm run typecheck` 通过；本次 3 文件严格 ESLint 通过；生产 build 成功（56 条既有 warning）。
- 全量 `npm run lint` 被关键词相关测试的 5 条既有 warning 门禁拦截，本次文件无 warning。
- Git Bash `./init.sh` 轻量验证通过；系统 WSL `bash` 首次调用的 `E_ACCESSDENIED` 不影响 Git Bash 结果。
- 未执行 Git stage/commit/push/deploy；任务前 13 个未跟踪备份/工具/镜像产物保持不动。

## 2026-08-11 - 孤儿文件硬链接副本位置点击核对

### 已确认交互与边界

- 只有副本数量大于 `0` 时才显示为可点击入口；`0` 和未知值保持普通文本。
- 点击后再按需查询位置，避免列表加载时扫描目录；搜索范围限定为系统已配置且可扫描的下载目录，不遍历整块磁盘。
- 弹框显示完整路径并提供复制按钮；文件夹聚合行按源文件分组，只提交其中副本数量大于 `0` 的子文件。
- `st_nlink - 1` 是文件系统报告的总副本数，而配置目录扫描可能无法覆盖目录外或不可访问的链接，因此界面同时显示总数、已定位数和未定位数，不把未找到误报成不存在。

### 实现

- `orphan_quarantine.find_hardlink_paths()` 支持多个 inode 在一次目录遍历中批量定位，去重重叠扫描根、物理路径和符号链接；既有单文件查询复用该实现。
- `OrphanFileService.get_hardlink_copy_locations()` 批量加载未删除孤儿记录，在线复核源文件 inode/link count，通过 `collect_scan_path_selection()` 获取全部已配置扫描根，并在线程中执行有界文件系统扫描；返回缺失记录、未知源文件、扫描错误和逐文件路径明细。
- 新增受认证保护的 `POST /api/v1/orphan-files/hardlink-copies`，请求最多 `5000` 个孤儿文件 ID，沿用统一 `CommonResponse`。
- 前端新增位置查询类型与 API；数量链接打开懒加载弹框，支持过期响应防护、文件夹子项过滤、完整路径展示和剪贴板复制。
- 已按 `roadmap-maintain` 同步根索引、后端 API/服务、前端 API/视图、测试索引及 `orphan_file_service` 第三层路线图的实测行号与调用链。
- 无数据库 Schema 变更，无 Alembic 迁移。

### 验证

- 后端服务/API 定向：`49 passed`；后端孤儿相关：`350 passed, 1 skipped`。
- 前端全量单测：`39 suites, 640 passed`；`npm run typecheck` 和本次 4 个修改文件严格 ESLint 通过；生产 build 成功（仍为 56 条既有 warning）。
- 后端目标 Flake8、`py_compile`、新增文件/代码区间 Black 检查通过；目标 mypy 仅报告 `orphan_file_service.py` 既有 149 条 SQLAlchemy Column 类型债，本次新增行零错误。
- 全量 `npm run lint` 仅被 5 条无关既有 warning 门禁拦截，本次文件无 warning；`git diff --check` 通过。
- Git Bash `./init.sh` 通过；未执行 Git stage/commit/push/deploy，任务前 13 个未跟踪产物保持不动。

## 2026-08-11 - 硬链接副本位置回归保护加固与提交

### 新增回归保护

- 后端服务新增双文件均有副本场景，明确断言重复孤儿 ID 去重、两个 inode 只调用一次 `find_hardlink_paths()`、源路径被排除且每个副本归入正确源文件。
- 后端新增扫描根不可访问场景，锁定实时 `st_nlink - 1` 总数不丢失、路径不伪造、全部转入 `unlocated_count`，并同时返回汇总和逐文件错误。
- HTTP 端点新增空数组与超过 5000 项的参数化验证，确保无效批次在创建目录扫描前返回 422。
- 前端新增连续点击竞态测试，后返回的旧请求不得覆盖最新弹框；新增扫描失败、源文件不可访问、列表项失效的组合提示测试；新增请求异常后释放 loading 并保持空结果测试。
- 按 `roadmap-maintain` 更新测试分支索引、覆盖矩阵和根路线图元信息；业务实现与第三层源码行号未变化。

### 验证与提交范围

- 后端定向 `53 passed`；后端全量 `3153 passed, 7 skipped`。
- 前端全量 `39 suites, 643 passed`；`npm run typecheck`、目标测试严格 ESLint、生产 build 通过（56 条既有 warning）。
- 后端两个测试文件 Black/Flake8 通过；无 Schema 或 Alembic 变更。
- 用户已验证页面交互并授权提交；提交范围仅包含本功能的 20 个跟踪文件，不包含工作区原有 13 个未跟踪备份、镜像与工具产物，不执行 push/deploy。

## 2026-08-11 - 种子重复查询、任务页与管理界面六项修复

### 已确认交互

- “查找重复任务”是两种种子视图的页面级开关：默认关闭，开启态绿色；开启后查询、筛选、排序、切页、分页大小、刷新和视图切换继续留在重复查询，浏览器刷新恢复关闭。
- 重复结果默认按添加时间倒序；列头排序仍可覆盖主排序。
- 高级搜索对话框左侧显示已保存的高级配置，可选择回填、创建、覆盖保存和删除；系统模板与他人的公开模板只读。

### 实现

- 列表/传统视图用 `el-switch` 替换一次性重复查询按钮，`getList()` 在开关开启时分派到重复端点；`TorrentViewSwitcher` 共享 `showingDuplicates`。重复请求继续携带名称、下载器、状态、分类、标签、活动快照、排序和分页参数。
- `duplicate_torrents.py` 默认 `added_date DESC, info_id DESC`，安全支持五个列排序；活动筛选复用权威速度快照并以连接级 TEMP 表联接，避免大集合触发 SQLite 绑定参数上限。
- `tasks/index.vue` 将 outcome/stale 的模块 helper 通过实例方法暴露给 Vue 模板，修复 `p.getTaskOutcomeMeta is not a function`。
- 回收站搜索区改用孤儿文件页同款 `management-panel` / `management-filter`；查询模板行操作改用 Lucide play/pencil/trash 极简按钮。
- 新增 `AdvancedSearchWorkspace.vue`：左侧管理高级搜索模板，右侧复用 `AdvancedSearchBuilder`；Builder 提供校验后的条件快照。父视图的 reset handler 不再反向重置 Builder，消除同步事件递归。
- 按 `roadmap-maintain` 用源码实测行号同步根索引、前后端分支索引和测试覆盖矩阵；无数据库 Schema 或 Alembic 变更。

### 用户确认后的回归加固

- 重复查询 API 增至 40 项：新增非法排序字段/方向 422、不完整重复组排除、仅单个活跃副本排除，以及权威空活动快照 `ready_empty` 契约。
- 列表与传统视图通过真实 `el-switch` stub 点击验证默认关闭、绿色开启态和查询分派；新增 `torrent-view-switcher.spec.ts`，验证两种视图往返时重复模式、查询、分页和选择状态不丢失。
- 定时任务回归使用 TypeScript AST 确认 `getTaskOutcomeMeta` / stale helpers 是 `TaskManage` 实例方法，直接保护原始运行时错误边界。
- 高级搜索工作区补充名称/描述筛选、单次 reset、保存前校验与并发旧响应隔离；管理页契约细化回收站 Enter/清空/重置和查询模板 ARIA/禁用态。

### 验证

- 后端重复查询定向：`40 passed`；目标 Black（single worker + no-cache）、Flake8、mypy 通过。
- 后端全量：`3163 passed, 7 skipped, 0 failed`。
- 前端高风险相关：`6 suites, 69 tests`；前端全量：`41 suites, 657 tests`。
- `npm run typecheck`、全部变更文件严格 ESLint、生产 build 通过；build 仅有仓库既有 Sass/Browserslist/体积 warning。
- 完整 `npm run lint` 仍仅被 3 个无关关键词测试文件的既有 5 条 warning 门禁拦截，本次文件为 0 warning。
- Git Bash 根 `./init.sh`、`git diff --check`、feature_list JSON 解析与路线图陈旧模式扫描通过；前端 init 仅有既有 null-byte warning。
- 用户已授权提交；提交范围仅包含本次功能、回归和路线图文件，不执行 push/deploy，任务开始前的未跟踪备份、镜像和工具产物保持不动。

## 2026-08-16 - 8 项问题根因分析与修复计划（验证后）

### 需求

- 用户反馈 8 项问题：① active-torrents 任意界面轮询 ② 标签/分类不同步下载器 ③ 新种子添加时间为空 ④ 路径同步误删历史路径 ⑤ 转移假成功/无日志 ⑥ 令牌不续期 ⑦ 删除日志无 IP ⑧ 缺展开/收缩与用户习惯记录。要求先找出最可能根因（深层推导），再生成修复方案。

### 根因分析（4 个子代理独立验证）

- ① 代码无全局轮询（仅 index.vue/TraditionalView，created 启动/beforeDestroy 停止）；部署镜像与源码一致；`/torrents/detail/:hash` 挂载整个列表视图导致详情页也轮询；keepAlive meta 死配置。
- ② create_tag 被"架构调整"注释刻意摘除同步（tag_management.py:448-450）；`_sync_tag_to_downloader` 与 adapter create_tag 均死代码；update_tag 同样缺同步。
- ③ 所有写入路径 added_on 无效即写 NULL（torrents_async.py:3297/3348、torrent_helpers.py:862、torrent_sync.py:824）；首轮 rid=0 maindata 快照不水合；无兜底无回填。子代理修正：info_only 变更检测缓存不含 added_date 列，"有值→None 覆盖"不成立，NULL 只在插入时产生、自愈依赖 delta/12h 全量；生产库 22277 条 0 空值，仅新添加路径命中。
- ④ 子代理修正：斜杠形态不一致假设被驳（存储与比较均原始形态）；真实根因=无宽限期立即禁用 + `_sync_active_path` 永不重新启用（生产库 id 38：2 条活种子、count 持续更新、is_enabled 恒 0）。
- ⑤ qB torrents_add 返回 "Fails." 不抛异常且返回值被忽略（qbittorrentapi 源码级确认）；`_verify_transfer` 按 hash 查旧种子即判成功；批量端点固定 code=200；审计写 seed_transfer_audit_log 无读取 API；端点硬编码 admin。
- ⑥ 后端只签单个 60 分钟 access_token 无 refresh 端点；前端 request.ts 401 直接登出。
- ⑦ 4 个删除端点从不调用 extract_audit_info_from_request；torrent_deletion_service.py:527 硬编码 ip_address=None；by_level 8 处不传 IP；写对 IP 的 _log_deletion_operation_async 死代码。
- ⑧ 无通用折叠面板组件；偏好散落硬编码 localStorage 键；子代理修正：viewMode 实际已持久化（btdeck_view_mode），仅注释误导。

### 交付

- 新建 `PLANS/verified-bugfix-remediation.md`：5 个发布门（G1~G5）、8 项问题→根因→交付项映射、5 个实施 Phase（含文件清单与测试）、验收标准、风险与回滚。
- `PLANS/README.md` 注册专项修复计划。
- 未实施代码改动；待用户确认优先级后按 Phase 交付（建议先做 Phase 3 的转移修复与 Phase 4 的令牌续期）。

### 2026-08-16 决策记录（计划批准）

- 用户确认：8 项问题**全部一次性实施**；令牌续期采用**双令牌 refresh 体系**（access 60 分钟 + refresh 7 天，refresh_tokens 表持久化、使用即轮换、登出撤销），替代初版计划的"滑动续期"。
- 3 个子代理独立审查修正（并入最终计划）：W1-1 路由 name 判断不可用（改用 path 判断）；W4-1 需新增 disabled_by 迁移字段防"重新启用推翻用户手动禁用"（存量 is_enabled=0 保守标 user）；W3-1 水合需宽松模式且仅 info_only 预算路径；W3-3 回填改后台任务；W5-3 前端需经 ApiError.rawResponse 取 400 载荷；W6 需独立 refresh 校验函数（verify_access_token 60 分钟年龄检查会拒 7 天 token）与登出撤销改造；W7 operator 防伪造（请求参数默认 admin 可伪造）。
- 计划文件 `PLANS/verified-bugfix-remediation.md` 已更新为审查修正版并批准；开始按 Phase 1~5 实施。

## 2026-08-16 - 8 项修复实施完成（Phase 1~5）

### 实施（计划 PLANS/verified-bugfix-remediation.md 已批准）

- **Phase 1 轮询**：SpeedPollingMixin（speedPolling.ts）统一两视图轮询 + visibilitychange 后台暂停/恢复；详情死路由跳过轮询；删除 router 13 处 keepAlive 死配置。
- **Phase 2 标签/路径**：create_tag/update_tag 同步下载器（qB 409 幂等、TR no-op、失败 best-effort）；downloader_path_maintenance 新增 disabled_by（迁移 a7b8c9d0e1f2），_sync_active_path 仅恢复 auto、_cleanup_obsolete_paths 宽限期 30 天（PATH_CLEANUP_GRACE_DAYS），服务层 delete/update 标 user；前端路径管理显示"历史路径/手动禁用"标签。
- **Phase 3 添加时间/转移**：首轮 rid=0 快照宽松水合（strict=False）；UI 添加 datetime.now() 兜底；启动后台回填（INFO_SYNC_STARTUP_BACKFILL_ENABLED，默认关）；torrents_add 返回值 "Fails." 检查、目标查重 duplicate、批量 code=400、审计 TRANSFER 并入 torrent_audit_log + 真实用户；前端 BatchTransferDialog 经 ApiError.rawResponse 展示失败明细、部分失败不 emit success。
- **Phase 4 令牌/删除日志**：双令牌体系——refresh_tokens 表（迁移 a8b9c0d1e2f3，SHA-256 哈希、使用即轮换、登出撤销）、/auth/refresh 端点、登录签发 refresh；前端 SetToken action、Login 接 refresh、401 单飞刷新重放（token-refresh.ts 可测编排）、isLoginRequest 豁免 /auth/refresh；4 删除端点提取 audit_info、by_level 8 处 log_operation 补 IP/UA、operator 防伪造（认证用户优先）、recycle_bin manual_cleanup 补 request。
- **Phase 5 折叠面板**：CollapsiblePanel.vue（storageKey 持久化、null 默认展开、aria-expanded/controls），全局注册，接入 audit/recycle-bin/query-templates/orphan-files 四个面板。

### 验证

- 定向测试：后端 267 用例全绿（111 Phase2/3 + 128 Phase4 + 28 W7 新增/回归）；前端 190 用例全绿（speed-polling 6、batch-transfer 4、token-refresh 5、collapsible-panel 7、management-pages-ui 13、error-normalize 35 等）。
- 迁移：25 用例全绿（EXPECTED_HEAD=a8b9c0d1e2f3）；生产库副本实证 disabled_by 迁移（2 条禁用记录保守标 user）。
- 全量回归：后端全量 + 前端全量 + 生产 build 结果见收尾记录。
- 未执行 git 提交（按仓库会话规范，用户未要求）。

---

## 2026-08-16 安全修复（两轮对抗验证驱动，PLANS/security-remediation.md）

### 背景
5 域调查代理 + 9 个对抗验证代理完成两轮安全分析（25 项发现终审），3 个审查代理评审修复计划（修订 15+ 项）。随后按批准计划实施 W1-W15。

### 已实施（后端）
- **W1** serve_frontend resolve+is_relative_to 双校验（覆盖绝对路径注入/`%5c`/未编码穿越）；7 测试
- **W2** cron task_type=4 三层拦截：执行层 `_run_task_script` 闸门（封 0-3 + type4 白名单 `app.tasks.` 前缀 + isclass 校验）、解析层删除 ImportError→exec 回落与两个 exec 方法、API/加载层白名单 + 系统通知；删除 enhanced_python_executor 死代码 + BTD301 白名单清空；41+14 测试
- **W3** 备份导入 filename sanitize + 每请求 uuid 子目录（消除并发 rmtree 竞态）
- **W4** core 层 bencode+info 内容校验（2MB 上限）；端点 .torrent 后缀；seed_transfer info_hash 40/64 hex 闸门；16 测试
- **W5** 归档仅取 basename+强制 .json+固定目录；download-export fullmatch 白名单；前端文案同步；18 测试
- **W6** downloader add 加密落库（ORM 构造点）；encrypt fail-closed raise；core/security encrypt_tracker_info 同修；启动幂等钩子加密存量明文；conftest 补测试 SM4 密钥；9 测试
- **W8** 密码 bcrypt（bcrypt 库，passlib 1.7.4 与新版 bcrypt 不兼容故未用）；verify 双读（$2b$ → bcrypt，否则旧 AES-ECB）；login 条件更新自动升级（防并发竞态）；changePassword 修复（原直调 sm4_decrypt 会 500）→ verify_password + 绑定本人 + 撤销 refresh + 清强制标志；admin seed bcrypt + 存量默认口令检测；alembic 迁移 ff42d3402df5（幂等加列）；7 测试
- **W9** login_throttle 模块（阶梯 5→15m / 10→1h，密码与 TOTP 共用计数，绝不信任 XFF，429 不带剩余时间）；must_change_password 进 token_data；改密撤销 refresh token；10 测试
- **W10** 2FA 四个端点（2faVerifyCode/QrCode/update2faFlg/verifyPasswordFor2FA）绑定本人；TOTP 日志脱敏 4 处；5 测试
- **W11** DEBUG/DB_ECHO 默认 False；DEV 保持 True（frozen 兼容）；desktop_main 移除 DEV=false setdefault（历史必崩入口）；DEV=False 关 docs/openapi；SECRET_KEY 空串归一；compose 透传 DEV/SECRET_KEY/ALLOWED_HOSTS/DEBUG（修复 .env 指引断链）
- **W12** 两个 spec datas 移除 config 目录；btdeck.iss 移除构建机 config 复制；.dockerignore 排除 config.yaml
- **W13** fastapi~=0.115.6 + starlette~=0.41.3（实测解析 fastapi 0.115.14 + starlette 0.41.3，CVE-2024-47874 修复）；nginx login location 1M；升级后 tests/api 895 passed
- **W15** file_operations 删除"取第一个 waiting-delete 文件"兜底（删错文件完整性缺陷）；keywords-search escapeRegExp；MatchTimeline sanitizeDescription 白名单
- **W7** git rm --cached 两个密钥 yaml；.gitignore 补 app/config.yaml；config.yaml.example 更新密钥警告；清理仓库垃圾（畸形目录/nul）；轮换 runbook（顺序契约 + 自救 + filter-repo 手册）

### 前端
- user.ts mustChangePassword 状态；permission.ts 守卫拦截（优先于 redirect）；settings 改密成功清标志 + forceChange 提示；audit.vue 归档文案

### 文档
- PLANS/security-remediation.md（含不修决议）；docs/security/key-rotation-runbook.md；deploy/nginx-tls.conf.example；README 安全加固指引；feature_list.json 新增 feature（14 tasks）

### 遗留（人工）
1. git filter-repo 历史清洗 + force push
2. 生产密钥轮换（顺序：先登录升级 bcrypt 再轮换）
3. 桌面版 verify-package.py 验证

## 2026-08-18 W9 强制改密路由死锁：根因定位、回归重现与完整修复

### 背景

生产事故：部署最新代码后正常使用一段时间，重新登录即被锁死在 /#/settings?forceChange=1，点击任何页面都被弹回且系统设置页无法进入（无法完成改密自救）。

### 根因（四层，已由两端回归测试实证）

1. 触发层：`init_db` 启动自检（database.py）发现 admin 仍用默认口令 "admin"（bcrypt/旧 AES-ECB 双格式命中）→ must_change_password 置 1；
2. 延迟层：标志仅随登录响应下发，存量会话靠 7 天 refresh token 存活——症状推迟到重新登录才爆发；
3. 死锁层：守卫重定向目标/白名单写父路径 /settings（父路由只挂 Layout 无 redirect，真实改密页在 /settings/index）→ 落点内容区 <!----> 白屏、真实路径与侧边栏菜单均被弹回，改密表单代码层面不可达；
4. 首导航缺口（双代理审查发现）：守卫 roles=[] 分支 GetUserInfo 后无条件放行，登录后/F5 后首次导航不受拦截。

### 已实施（修复）

- 前端：router.ts /settings 加 redirect；permission.ts 守卫目标/白名单改子路由 + GetUserInfo 分支补拦截（抽 isForceChangeBlocked/forceChangeRedirect）+ 拦截弹 Message.warning"请先修改密码"（3 秒节流，点其它菜单被弹回时给出反馈；设置页 mounted 旧提示移除避免双弹）；user store GetUserInfo 解析 mustChangePassword（undefined 不写防滚动部署误清）；users.ts 类型；settings/index.vue 改密成功清 forceChange query。
- 后端：cuser.py get_user_info 下发 mustChangePassword（双前缀生效）。
- 发布约束：router redirect 与守卫白名单必须原子交付（单独部署前者会无限重定向循环）。
- 生产解困 runbook（含 SQL 路径、会话残留、SQLite 运维细节）见 PLANS/force-change-deadlock-fix.md 第四节。

### 测试

- 重现（事故时点）：backend test_w9_force_change_reproduction 4 用例 + frontend permission-force-change-deadlock（旧 bug 行为）。
- 修复后锚定：deadlock spec 8 用例（拦截落点可达+提示断言/首导航拦截+提示断言/父路径 redirect/手动直达放行/改密闭环/提示 3 秒节流/对照）；user-store-must-change-password 扩至 9 用例（Login true/显式 false/缺省 + GetUserInfo wrapped/扁平/显式 false 覆盖/字段缺失保持原值）；settings-change-password 新建 4 用例（改密成功双解锁：清 store 标志+清 URL query 保留其他参数；无 query 不多余跳转；失败不提前解锁；前置校验拦截）；后端新增 /users/info 两态 2 用例。
- 验证：后端三套件 97 passed + black/flake8/mypy；前端 jest 相关 6+7+60 passed + eslint + typecheck；./init.sh 通过。

### 遗留（人工/后续）

1. 长会话不刷新的标签页无法实时感知标志（GetUserInfo 唯一调用点是守卫 roles=[] 分支）——彻底消除需挂周期端点，另行评估；
2. 其他父路由（/downloader、/tasks 等）缺 redirect 的手输空白 UX 问题，后续统一补；
3. Git 提交待用户指示。


## 2026-08-19 打包脚本全链路审计与修复（子代理验证 + 人工实施）

### 审计（三并行子代理独立验证 + 主线复核）

- 覆盖四套打包体系：build-and-export-images.bat（Docker+远程部署）、build-images.sh（Docker/Linux）、deploy/build-windows.bat+btdeck-windows.spec+btdeck.iss（桌面/Inno）、deploy/build-linux.sh+btdeck.spec（Linux/fpm）。
- 通过项：全部引用文件存在、bash -n/AST 语法、docker compose config、健康检查链路闭环（health.py:159 /health/ready ↔ Dockerfile ↔ nginx.conf:138 /health ↔ compose 字段级一致）、版本三处一致 v1.0.9、两个镜像 tar 为完整 OCI 归档（digest 全命中）且逐层扫描无 config.yaml/app.db、.dockerignore 对实际敏感文件全覆盖、spec 39 个 app.* hiddenimports 与实码对齐、W12 修复落实。
- 异常（全修复）：①bat 明文 root SSH 密码/hostkey 已随 c603b0d 推送 origin/dev（github.com/strainhzj/BtDeck）②6/21 桌面构建残留内嵌旧密钥（EXE-00.toc 实证）③重试链到不了官方源 PROFILE_1 ④verify-package.py PATH-only 解析致打包校验必失败（临时 venv 实证）⑤打包 requirements 内嵌受 CVE-2024-47874 影响的 starlette 0.38.x ⑥btdeck.iss 卸载留孤儿服务 ⑦--unraid+--compose 参数误解析 ⑧backend/.env.example 真随机 SECRET_KEY 样值。

### 修复（本会话，未提交）

- build-and-export-images.bat：凭据外部化（.btdeck-deploy-credentials.bat，gitignore；模板 .example）；重试链官方源兜底（B_TRIED_OFFICIAL/B_OFFICIAL_TAIL 双标志，高保真仿真验证 2→3→1/3→1/1→2→3 且兜底恰一次——首版实现仿真捕获 1 失败后回环 bug 已修正）；--unraid 第三参数 -- 前缀守卫。
- deploy/verify-package.py + analyze-package-size.py：find_archive_viewer()（sys.executable 同目录优先）；复现场景 not found→found 实证。
- deploy/btdeck.iss：nssm remove 移入 usUninstall。
- deploy/requirements-{windows,linux}-package.txt：fastapi 0.115.6 / starlette 0.41.3 / bcrypt ~=5.0.0 对齐 backend。
- backend/.env.example：SECRET_KEY→占位符；删除 .docker_temp_482561487 + deploy/dist + deploy/build（约 720MB，含密钥残留）。

### 遗留（人工）

1. 【紧急】轮换 192.168.5.51 root 密码（凭据已在 GitHub origin/dev 历史暴露）；改用 SSH key 更佳。
2. git filter-repo 清洗 c603b0d 中的密码/hostkey 后 force push（与既有密钥清洗遗留合并处理）。
3. 打包链近期未实测：Docker 引擎离线未跑 docker build 全流程；桌面打包建议跑一次 deploy/build-windows.bat 验证 Inno 全链（本次修复已解除校验阻断）。
4. 版本号三处维护（build-images.sh 动态 / build-linux.sh + btdeck.iss 硬编码）下次发版需手工同步，建议统一动态解析。


### 2026-08-19 补记：git 历史清洗（已执行）

- 范围：①build-and-export-images.bat 中的 root SSH 密码与 plink hostkey（--replace-text，c603b0d 引入）②backend/config/config.yaml 整路径（8 个历史版本中 7 个含真实 secret_key/login_status_secret，自根提交 8fe877d 起存在于 master+dev，c82f685 起已不再跟踪）。
- 执行：git-filter-repo（--replace-text + --invert-paths --path + --replace-refs delete-no-add）；改写前提交修复 f3db8d6 并创建全量备份 bundle（仓库外 ../BtDeck-pre-history-clean-20260819.bundle，含旧历史，确认无误后可删）；435→434 提交（仅触及 config.yaml 的 e8e7784 变空被剪），根起全部哈希改变。
- 验证：git log --all -S 密码/hostkey 与 config.yaml 路径全部为空；c603b0d/8fe877d 旧对象不可达（gc 已清）；工作树零改动；force push master+dev 后生效。
- 后续注意：①所有既有 clone 需重新 clone（或 fetch+reset --hard origin/<branch>）②GitHub 服务端旧提交在 GC 前仍可能按 SHA 访问，必要时联系 GitHub support 加速回收③**历史清洗不等于未泄露——192.168.5.51 root 密码与历史 secret_key 仍需轮换**④备份 bundle 含泄露内容，仅作回滚用，确认后删除。


## 2026-08-19（二）Windows 桌面发行版打包实测与契约数据缺失修复

### 执行

- 完整跑通 deploy/build-windows.bat：NSSM/npm/python 检查 → .venv-packaging（Python 3.12.4）→ npm ci + build → PyInstaller（btdeck-windows.spec）→ verify-package → analyze。安全对齐实证生效：pip 解析 starlette 0.41.3 + fastapi 0.115.14 + bcrypt 5.0.0。
- Inno Setup 未安装（PATH 与默认目录均无 ISCC）→ setup.exe 安装包步骤按设计跳过；dist/btdeck.exe（64.9MB）产出。注：本仓库安装包格式为 Inno Setup 的 setup.exe，非 MSI。

### 发现与修复（桌面打包真实缺陷）

- 首次运行 exe 启动即崩：app/contracts/advanced_search.py:9 在 import 时读取 advanced_search_contract.json，而 spec datas 未打包该文件（frozen 下 FileNotFoundError 于 _MEIPASS）。修复：两个 spec datas 增加 contracts JSON + production_complete_schema.sql（后者供 init_schema_from_production 运维工具，非启动必需）。重建后归档内两文件确认存在。

### 验证（重点两项均通过）

- **前后端均在包内**：归档 287 个 frontend_dist 条目 + 契约 JSON；运行时 /health/live 返回 200 信封、/ 返回 BtDeck SPA index.html、chunk-vendors.js(1.06MB)/app.css(263KB) 均 200——前端由 exe 内 _MEIPASS/frontend_dist 经 factory._mount_frontend_static 服务，后端 PYZ 完整（API 实测可用），6 秒就绪。
- **前端为独立窗口**：desktop_main.py 以 pywebview 创建 1280×820 原生窗口指向本地 5001；Get-Process 实测 MainWindowTitle="BtDeck"、MainWindowHandle=264442（onefile 双进程中 GUI 进程持窗）。BTDECK_DESKTOP_WINDOW 环境变量可强制有窗/无窗模式。
- 测试后已 taskkill 并清理 dist/ 下首启生成的 config 等目录。

### 遗留

1. setup.exe 安装包：安装 Inno Setup 6 后重跑 bat 第 3 步即可（或给 bat 补默认安装路径探测）。
2. 体积优化：前端 sourcemap（.map）被整体打包（ts.worker.js.map 未压缩 13MB 等），关闭 productionSourceMap 或打包前剔除可显著缩包。
3. spec 修改与本文档未提交（待用户指示）。


## 2026-08-19（三）桌面版 "Redirected when going from ..." 杂音根因与修复

### 现象与根因链（全链实证）

- 用户报告：登录后出现错误 "Redirected when going from \"/login?redirect=%2Fdashboard\" to \"/dashboard\" via a navigation guard."
- 该文本是 vue-router 3.1+ 的 NavigationFailure 内部消息：守卫把导航改道时，原 push 以 rejected promise 结算。触发场景 = 强制改密守卫（admin.must_change_password=1，DB 实证）：登录成功 → push('/dashboard') → 守卫改道 /settings/index。
- 显示链路：login/index.vue:214-220 把 router.push 与登录请求包在同一 try/catch，catch 中 error instanceof Error 为真（NavigationFailure 继承 Error）→ $message.error 原样弹 vue-router 内部英文消息。导航本身正常完成（用户已被送达设置页），纯 UI 杂音。
- 排除项：后端零 30x（代码级）；前端 bundle 不含该渲染字符串（含 sourcemap 全扫，唯一命中是 monaco 源码注释）；运行实例端口/健康正常、系统代理禁用。

### 修复（frontend/src/router.ts，扩展既有实例级补丁）

- 原有补丁只吞 NavigationDuplicated 且未覆盖 replace；现 push/replace 统一用 isNavigationFailure 判定（redirected/aborted/duplicated/cancelled 全覆盖）resolve 之，真实异常仍上抛。守卫控制流不再泄漏为 UI 错误。

### 验证

- 新增回归 spec tests/unit/router-navigation-failure.spec.ts（3 用例：redirected push/replace 静默且落点正确、aborted 静默）；permission-guard/force-change-deadlock/session + 新 spec 共 4 套件 34 用例全绿；tsc --noEmit、npm run lint 通过；前端重建 + PyInstaller 重打包（20:09）+ verify-package 通过。注意：正在运行的旧实例（用户会话）需重启 exe 后生效。

## 2026-08-20 种子信息同步辅种数量

### 用户确认语义

- 辅种匹配键仅为 `name + size`，允许跨下载器、跨同步任务统计；`.torrent` 文件名和下载路径差异不影响同组判断。
- 外部参考库 `E:\Users\huangzj\Desktop\app.db` 只读取证：该名称共 45 条、有效 31 条，`torrent_file` 有 45 个不同值，但有效行缓存分布为 `auxiliary_seed_count=1` 共 31 条；按 `name + size` 刷新后应全部为 31。
- 不在种子列表查询时实时分组；由种子信息同步任务全量计算并写入 `torrent_info.auxiliary_seed_count`。没有有效辅种键或没有辅种数据时显示 1。

### 已实施

- Alembic `975dad435c03` 新增 NOT NULL Integer `auxiliary_seed_count`，历史数据默认 1。
- 同步任务完成后全量校正当前有效行（`dr=0` 且未进入回收站）的辅种数量；列表 API 只读取已持久化字段。
- 等级 1/2/3 删除、种子转移成功删除源行、回收站还原均维护对应分组的缓存数量；下一次同步任务可修复任何异常中断或历史脏数据。
- 普通列表与传统列表均新增“辅种数量”列，并兼容后端 snake_case/camelCase 字段。

### 验证

- 后端回归加固后：辅种服务+种子转移 24 passed；删除等级1/2/3+回收站还原 42 passed；同步任务+列表 API 52 passed（定向合计 118 passed）；数据库迁移/回滚/生产库形状 35 passed。
- 新增边界保护：无效 `name/size` 不生成匹配键；等级3 移动失败不扣减数量；回收站还原将有效分组恢复为新总数；转移场景使用不同 `.torrent` 文件验证只按 `name + size`；同步数量校正失败不覆盖原同步结果；列表响应锁定 `auxiliarySeedCount` camelCase。
- 前端普通/传统列表辅种数量渲染回归加入后，选定单元测试 102 passed；typecheck、lint、生产 build 通过（仅既有 Sass/资源体积警告）。
- `git diff --check` 通过；本轮补测后执行 Git 提交与推送，未部署。


## 2026-08-20 Linux 安装包全链路验证（Docker 容器模拟 Debian 12）与三项修复

### 环境与方法

- node:18.20.1-slim 容器（Bookworm，装 python3.11/venv/binutils/libpython3.11/ruby+fpm），源码快照经 docker cp 传入；镜像源环境变量与 Docker 构建参数对齐（npmmirror/aliyun pypi/apt）。
- 最终完整跑通 deploy/build-linux.sh：venv → npm ci + 前端构建 → PyInstaller（btdeck.spec）→ verify-package 全 PASS → fpm deb/rpm 构建成功；产物 dist/btdeck（ELF x86-64, 73.6MB）、BtDeck-v1.0.9-linux-amd64.deb/.rpm（各 73MB）。

### 发现与修复（本会话 4 项）

1. 【工作区隐患】deploy/build-linux.sh、start.sh、btdeck.service 工作区为陈旧 CRLF 检出（.gitattributes 已 eol=lf 但 git 不重写既有文件；索引本身 LF，Linux 全新 clone 无恙）——本机拷贝到 Linux 即 "$
" 报错。已本地强制重检出修复；同集合共 83 文件（其余为 .py，CRLF 无害），未逐一处理。
2. 【仓库缺陷·已修】verify-package.py/analyze-package-size.py 的 find_archive_viewer 在 Linux 失效：venv bin/python3 是符号链接，Path(sys.executable).resolve() 跳到 /usr/bin。改用 sys.prefix（venv 根，不经软链）优先 + 未 resolve 的同级目录次之 + which 兜底。
3. 【仓库缺陷·已修·关键】ALLOWED_HOSTS 环境变量格式：btdeck.service 的 Environment= 与 postinst 生成的 btdeck.env 均为逗号分隔，而 pydantic-settings 对 List[str] 在校验器之前强制 JSON 解析 → 安装后启动即 SettingsError 崩溃循环（A/B 实证：逗号格式崩溃 / JSON 格式健康）。两处改为 JSON 数组（与 desktop_main.py 一致）。
4. 【脚本健壮性·已修】fpm 拒绝覆盖已存在输出 → 重复构建 fatal；两处 fpm 加 --force。

### 验证结果

- deb 全新容器 dpkg -i：exit 0，postinst 建系统用户 btdeck、/opt/btdeck 五个 ReadWritePaths 目录、600 权限 btdeck.env（SECRET_KEY 随机 + JSON ALLOWED_HOSTS）、chown 正确；systemd 缺失时优雅降级提示。
- 以 btdeck 用户 + env 文件 + DEV=false 启动（Python 干净环境复刻 systemd 传参）：/health/live 200 信封、/ 200 SPA（title BtDeck）。
- systemd 单元内容/行尾核对：LF 干净、硬化段（NoNewPrivileges/ProtectSystem=strict/ReadWritePaths）完整。

### 遗留与注意

1. 二进制为 Bookworm（glibc 2.36）构建：仅适用 Debian 12+/Ubuntu 22.04+ 级别发行版；老系统需对应环境重构建。
2. PyInstaller 每次输出 "Hidden import 'transmissionrpc' not found"（spec 列了 transmission_rpc 旧名，未安装即非致命告警）——建议 spec 删除该旧条目。
3. build-linux.sh 环境前置：binutils/libpython3.11/ruby+fpm 无预检，干净 Debian 需先 apt 安装；建议脚本头部注释说明或加预检。
4. 深层建议：后端 List[str] 环境变量强制 JSON 的语义与 .env.example/compose 文档的逗号指引相悖，可考虑 NoDecode 注解统一兼容（涉及核心配置，另行评估）。


## 2026-08-22 docs/roadmap 全量对账刷新（B 档：计数 + 漏列 + 行号实测 + 行为描述重写）

### 背景与方法

- 触发：roadmap 最后同步于 e6c5036（2026-08-21），其后 04c8ec6（mypy 清零 / ORM Mapped 迁移）改动 143 个后端文件（+1914/−1592），行号大面积漂移且元信息未补记。
- 方法：三路只读核查（后端 10 文件 / 前端 8+deploy+tests / 第三层+perspectives）产出漂移清单 → 用户确认 B 档全量刷新 → 根 README 由主会话修复，其余 24 文件由 5 个并行修复代理按"行号实测"原则逐项重测后写入 → 全局回归校验。
- 全程未改动任何源码；git status 确认变更范围恰为 docs/roadmap/ 下 26 个文件。

### 修复内容（基准 HEAD 348c700）

1. **根 README**：修 4 处计数错误与内部矛盾（endpoints 38→37、api 模块 13→12、store 5→4+1 拆分、tests 145/44→180/59）、alembic 20→28、head 更新；元信息补记 2026-08-22 增量行（含 04c8ec6 批次）。
2. **失效条目清理 7 条**：enhanced_python_executor.py（已删）、QuickDeleteDuplicatesDialog.vue 错路径、deploy/dist 与 deploy/build 错路径、_enrich_hardlink_copy_counts（改名 _enrich_items）、test_same_content_inspection_api.py（已删）、torrent_crud.py:814（行不存在）、R9 构建产物风险（已整改）。
3. **补录漏列 29 项**：后端 10 .py（startup_guard / orphan_folder_grouping / orphan_stats_cache / torrent_added_date_backfill / sync_checkpoint / cron_freshness / login_throttle / datetime_utils / format_size 等）+ 5 个 alembic revision + 前端 9 项（CollapsiblePanel.vue、columnResize/speedPolling mixins、downloader connection/path-mapping-rules、3 内嵌 spec、nginx-tls.conf.example）+ tests 子目录 architecture/integration。
4. **第三层重写**：torrent_crud.md（727 行基准；索引 22 处行号、签名按源码重抄 request 首位/无返回注解、批种添加改写为 202 后台任务 + torrent_batch_add_service、SDK 直调改 call_downloader_api）；orphan_file_service.md（3902 行基准；35 处行号、_enrich_items 快照列语义、补 21 个缺失方法、resolve_orphan_selection 补 hardlink_copies 参数）。
5. **perspectives 4 文件**：architecture.md "5 条"→6 条 + ~40 锚点；conventions/risks/test-coverage 全部计数与锚点实测重校（测试总数 147→180、Jest 44→59、revision 9→28 等）。
6. **实测修正两处估算**：AuditOperationType 成员 39→47（AST 实测）；torrents __tests__ 行数两处矛盾统一为 2637。

### 验证

- 残留旧值 grep（15 类 token）清零；剩余命中均为刻意保留的"已整改/历史状态"描述与 call_downloader_api 新写法。
- 抽查 10 项关键值与源码一致：orphan 3902 / delete_hardlink_copies L856 / torrent_crud 727 / create_torrents_batch L485 / cron_executor 1054 / initialization 2071 / yield L464 / torrents.ts 1335 / router.ts 349 / permission.ts 203 / formatters 606 / alembic 28+head 975dad435c03。
- 未提交 Git（待用户指令）；F2 代理曾因账户限流失败一次，重试后完成。

## 2026-08-22 Docker 后端镜像 Python 3.11 启动语法修复

### 根因

- Docker 使用 Python 3.11；backend/app/tasks/cleanup_executor.py:272 的双引号 f-string 表达式内又使用双引号空字符串，Python 3.11 解析为 SyntaxError: f-string: unmatched '('，导致 Uvicorn 在导入 app.main 前退出。
- 本机 Python 3.12.4 可解析该写法，因此本地普通编译未能复现；问题只在目标 Docker 运行时暴露。

### 修复

- 将表达式内的空字符串改为单引号，保持日志内容和清理逻辑不变。

### 验证

- backend/app/tasks/cleanup_executor.py 编译通过；backend/app 全量 compileall 通过；git diff --check 通过。
- test_orphan_scan_task.py：18 passed；test_cron_executor.py、test_cron_executor_admission.py、test_cron_executor_security.py：38 passed。
- 使用仓库配置的阿里云镜像源构建 btdeck-backend:latest 成功，镜像 digest 为 sha256:c0074bf5c36b78506f7a79fceee5d49f731646cb0f67625d2943659a4b134560。
- 在构建出的 Python 3.11.15 镜像中执行 import app.main 与目标文件 py_compile 均退出 0；临时容器实际启动后状态 running、健康状态 healthy，/health/ready 返回 200。
- docker compose config --quiet 通过；根 bash ./init.sh --ci 仍因当前 Windows WSL E_ACCESSDENIED 无法执行。

### 交付状态

- 未执行 Git stage/commit/push；镜像已构建在本机 Docker 引擎中，待用户按现有部署流程导出/加载并重启目标环境。

## 2026-08-23 安卓适配改造启动（dual-mode-client Phase 0A/0B 脚手架 + Phase 1 主体落地）

### 范围与决策

- 按评审修订版 PLANS/dual-mode-client.md 启动；本轮交付 Phase 0A 决策文档、Phase 0B 独立仓库脚手架、Phase 1 第 1/2(部分)/3/4/5/7 项。Phase 2/3（安卓工程）未启动，Phase 0 闸门未验证（无 CI 实跑）。
- 桌面发行版默认行为不变（HOST 默认值不动）；安卓 loopback 默认属 Phase 3 壳工程注入，契约已冻结在文档。

### 实施（BtDeck 主仓）

1. **统一 TCP probe（Phase 1.1）**：新增 `backend/app/utils/connectivity.py`——loopback 短路（保持 delay=1 历史语义，测试免网络 IO）→ 桌面可选 ICMP（ping3 懒加载，PermissionError/失败全捕获回退）→ TCP connect 计时兜底；安卓环境（sys.getandroidapilevel / BTDECK_PLATFORM=android / TERMUX_VERSION）自动禁 ICMP，不依赖 raw socket 或系统 ping。`downloader.py` get_delay_async/get_delay 与 `initialization.py` _update_downloader_status 三处 ping3 直调全部替换；is_loopback 精确匹配修复历史 `"127.0.0.1" in host` 子串误判（含 host:port 剥离）。顺带修复：延迟探测异常分支局部 delay 未绑定 → 后续日志行 UnboundLocalError → 整个状态更新 return False 的潜伏 bug（原代码同样存在，现异常分支正确置 None 并继续端口检查）。
2. **依赖瘦身（Phase 1.3）**：两个审计服务 Excel 导出改 openpyxl 直写（Workbook/append，列头列序与 pandas 版逐列一致）；pandas/numpy/sympy/common 从 backend/requirements.txt 与 deploy 两份打包 requirements 移除（全仓 app/tests/scripts/alembic 零 import 核实）；两份 PyInstaller spec excludes 显式加 'pandas'/'numpy' 防传递依赖回流，openpyxl hiddenimports 保留。
3. **决策文档（Phase 0A/1.2/1.4/1.7）**：docs/android/ 新增 target-matrix.md（API/ABI/Chaquopy17/Python3.12/FGS specialUse 首选 + dataSync 6h 预算警告 + 备份/Keystore/cleartext 决策）、toolchain-matrix.md（3.11 语法下限 + mypy/black 目标不动 + ABI 依赖分层）、config-and-paths.md（CONFIG_DIR/DATABASE_PATH/TORRENTS_DIR 注入契约 + HOST≠ALLOWED_HOSTS）、host-capability-matrix.md（supported/degraded/unsupported 冻结；自定义脚本/宿主 shell unsupported）。
4. **契约测试（Phase 1.2/1.5）**：tests/core/test_writable_roots.py（6 例：注入优先级/派生根/DATABASE_PATH 覆盖/ALLOWED_HOSTS JSON 强制）、tests/architecture/test_packaging_contract.py（10 例：alembic.ini+迁移链单 head+契约 JSON+schema 快照存在性；双 spec datas 覆盖 alembic/契约/frontend_dist；pandas excludes 防回流；三份 requirements 瘦身防回归）。

### android-wheels 独立仓库（Phase 0B 脚手架）

- 本地 `C:\software\claude_code_full_stack\android-wheels`（git commit ee65481，main 分支）：构建 workflow（四 ABI matrix：cargo-ndk + maturin --abi3 cp312 + NDK clang 链接器 + sdist sha256 固定）、check-wheel-tag.py（文件名 tag + ELF machine 校验）、make-simple-index.py（PEP 503 + sha256 fragment + hashes-SHA256SUMS + BUILD-INFO）、import-matrix.yml（模拟器 API 34/35、full-graph 阶段 2 显式 fail 直到接入真实资源）、最小 Chaquopy17 testapp（versions 固定：pydantic-core 2.41.5/pydantic 2.12.4/fastapi 0.115.6；导入+模型校验+/health/live 三仪表测试）、docs/gate.md 闸门判据与记录模板、versions.env（hash/tag 标注 TBD 首次 CI 回填）。
- **未做（用户操作）**：GitHub 创建远端仓库并推送、开启 Pages、首次 Actions 运行。

### 验证

- 后端：mypy 247 文件零错误、black/flake8 通过、pytest 全量 3927 passed + 7 skipped（含新增 54 例：connectivity 23 + 调用链 8 + Excel 7 + 可写根 6 + 打包契约 10）。
- 根 `./init.sh`（ci 模式）通过（此前记忆中的 WSL E_ACCESSDENIED 已不复现）。
- 未做：Monaco chunk/首屏收益实测（Phase 1 第 6 项，需前端构建产物分析）；GitHub Actions 实跑。

### 遗留（下次会话）

1. 用户创建 android-wheels GitHub 远端并推送 → 首次 CI 回填 versions.env 的 sdist sha256 与 Android platform tag → 跑 import-matrix。
2. Monaco 前端资源审计（构建产物 chunk 体积与首屏数据）。
3. Phase 2 伴侣模式 MVP（可独立先行，不依赖 Phase 0 结果）。
4. LAN 开关受控重绑（Phase 3 壳工程实现，契约已冻结）。
5. Git 提交待用户指示（主仓与 android-wheels 两处）。

## 2026-08-23（第二批）：Phase 1 收口（Monaco 审计）+ Phase 2 伴侣模式 MVP 脚手架

### 用户指令

继续下一步；android-wheels 等"整体打包完成"后再推送（创建远端/Actions 验证全部顺延）。

### Monaco 审计（Phase 1 第 6 项收口，Phase 1 至此七项全完成）

- 方法：审计 2026-08-22 构建产物（前端源此后未变更，数据有效）：index.html 首屏仅引用 app(75KB)+chunk-vendors(1.06MB)；Monaco 全部位于异步 chunk 849(2.94MB，含 monaco 标识 676 处确证)+dist 根按需 worker；tasks 视图为路由级懒加载，其编辑器组件动态 import('monaco-editor')。
- "高级搜索编辑器"不存在：全仓其余 monaco 命中均为 CSS 字体族（Consolas, Monaco, monospace）。
- 唯一改动：删除死组件 frontend/src/components/MonacoEditor.vue（静态 import 版，全仓零消费方、零测试引用），消除未来误用静态导入破坏懒加载的风险。webpack plugin 与组件层均判定不改（无收益改动不列为门禁）。结论文档化 docs/android/monaco-audit.md（含 sourcemap 体积遗留项关联说明）。
- 验证：前端 typecheck 通过；tasks-sync-freshness + tasks-lucide-migration 30 用例通过。

### Phase 2 伴侣模式 MVP（android/ 工程完整脚手架）

- backend/app/api/endpoints/health.py：live/ready（含 503 分支）data 增加 version 字段（常量读取无 I/O，向后兼容）；test_health.py 全等断言更新+双端点 version 断言，10 用例通过；tests/api 全量 1004 passed + 5 skipped；mypy 247 文件零错误、black/flake8 通过。
- android/（Kotlin，AGP 8.5.2，minSdk 24/target 35，package com.btdeck.companion）：向导（模式二选一+可重跑）/服务器列表（添加校验+测试连接+长按忘记）/WebView（同源直连+外链交系统浏览器+20s 超时重试+版本副标题+切换 profile 清 cookie/storage 隔离令牌）/自签证书指纹信任流程（绝不无条件 proceed，作用域=单 profile）/明文 HTTP 双层防线（NSC 默认全禁仅 loopback；应用层 LanHostPolicy 强制私有字面量+显式同意，公网明文拒绝；LAN 明文需 -Pbtdeck.lanCleartext=true 构建变体，平台约束已记录）/HealthClient（live→ready 链式+版本+TLS 可辨识）/LanHostPolicyTest JVM 单测（解析规范化、私有边界 172.32/127.0.0.1.example.com 防误判、策略四分支）。
- 凭据隔离结论：前端令牌在 cookie（frontend/src/utils/cookies.ts，按 origin 隔离），WebView CookieManager 是进程级单例——切换 profile 全量清除 cookie/localStorage 即达成"不跨服务器复用凭据"，MVP 无需前端改动。
- 诚实边界：本机无 Android SDK/JDK17，Gradle 编译与单测未运行（脚手架以正确性审查交付，feature_list 按登记原则标 in-progress 不标 done）；OkHttp 健康检查不消费 WebView 信任指纹（自签 https 显示证书错误）为已知 MVP 边界。

### 验证汇总

- 后端：tests/api 1004 passed；mypy/black/flake8 全绿。
- 前端：typecheck 通过；tasks 相关 30 用例通过。
- 根 ./init.sh 通过。
- roadmap 同步：backend/api README health 行加 version 事实；根 README 模块树+分支表新增 android 分支；元信息两批更新。

### 遗留（下次会话）

1. 【用户决策点】android/ 首次 Gradle 编译验证（JDK17+SDK 环境或 CI）；通过后再考虑 android-wheels 推送（用户指令：整体打包完成后）。
2. Phase 3 安卓服务端壳工程（Chaquopy）等 Phase 0 闸门。
3. 桌面伴侣模式复用 Phase 2 profile/健康检查（计划第 7 节桌面段）。
4. Git 提交待用户指示（本轮新增：health.py、test_health.py、android/ 全目录、docs/android/monaco-audit.md、删除 components/MonacoEditor.vue、roadmap/feature_list/progress/session-handoff 更新）。

## 2026-08-23（第三批）：android/ 首次 Gradle 编译验证（用户指令"开始首次编译验证"）

### 构建环境（本机便携，可整体删除）

- 盘点：本机仅有 JDK 1.8、无 Gradle/Android SDK；本地 C:\software\java\jdk-17 zip 为损坏半截文件（9.6MB）弃用；发现 IntelliJ IDEA 2024.3.1 自带 JBR 21.0.5（AGP 8.7/Gradle 8.9 完整支持）。
- 搭建 C:\software\android-build-env\：Gradle 8.9（腾讯镜像，136MB）+ Android cmdline-tools（dl.google.com，153MB）→ sdkmanager 安装 platform-tools + platforms;android-35 + build-tools;35.0.0（licenses 已接受）。
- android/local.properties 写 sdk.dir（已 gitignore）。

### 首次编译：发现并修复 3 个真实问题

1. AGP 8.5.2 不支持 compileSdk 35 → 升 8.7.3（Gradle 8.9 恰为其最低要求）。
2. ServerListActivity：ListView `apply {}` 块内未限定 `adapter` 解析到 ListView.getAdapter()（Kotlin 平台属性遮蔽外层字段）→ 改显式局部变量。
3. 属性赋值形式 `onItemClickListener = { }` 不做 SAM 推断 → AdapterView.OnItemClickListener SAM 构造器。

### 结果（全部通过）

- `:app:compileDebugKotlin` ✓（全部 Kotlin 源编译通过）
- `:app:testDebugUnitTest`：11 用例全绿（0 failures / 0 errors）
- `:app:assembleDebug`：BUILD SUCCESSFUL；app-debug.apk 6,268,259 字节（~6.0MB）
- apksigner verify：debug 签名有效；badging：com.btdeck.companion 0.1.0-mvp / compileSdk 35 / targetSdk 35 / 权限仅 INTERNET+ACCESS_NETWORK_STATE
- 双 NSC 变体 aapt2 dump xmltree 实证：默认 → @0x7f110000（network_security_config 严格版）；-Pbtdeck.lanCleartext=true → @0x7f110001（network_security_config_lan）——明文构建开关按设计切换
- android/README.md 构建节已更新为"已验证工具链组合 + 流程"；feature_list task .3 evidence 追加验证结论

### 遗留

1. 仪表化测试与真机验收（Phase 5 统一）；安装到真机/模拟器的人工冒烟（BlueStacks 本机存在，未驱动）。
2. android-wheels 推送仍等用户"整体打包完成"指令。
3. Git 提交待用户指示（android/ 含 local.properties 已被 .gitignore 排除，build 产物同）。

## 2026-08-23（第四批）：同步资源占用观测增强

### 结论

针对 `torrent_info_sync_ac608e4d` 多次 `[ADMISSION_SKIP] reason=wait_timeout`，完成一期只读观测增强。保持 `SYNC_HEAVY_CONCURRENCY`、等待超时、调度周期、任务取消语义和数据库写入行为不变；未修改用户提供的 `E:\Users\huangzj\Desktop\app.db`。

### 变更

- `resource_guard.py`：维护 heavy_sync holder 的 task/run/phase/年龄/PID/worker_instance_id；等待超时时输出 blocked_by 诊断，准入/超时/释放发射结构化资源生命周期事件。
- `cron_executor.py`：为 Python 内部类增加 start/heartbeat/timeout_warning/end 观测；`timeout_seconds` 仅用于告警，不调用 `wait_for`、不取消执行；Cron run_id 仅在当前执行上下文关联。
- `sync_coordinator.py`：活动同步快照补充 phase/elapsed/last-progress，发射阶段切换事件并刷新资源 holder 阶段；同步进度不落库。
- `sync_observability.py` / `config.py`：增加 task/resource/sync_phase 事件、进程身份和 `SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS=30` 配置。
- 测试：新增 holder 诊断与生命周期心跳用例。

### 验证

- 观测/同步核心套件：92 passed。
- Cron executor + health 回归：28 passed。
- mypy（5 个后端源文件）：无错误；flake8：通过；Black `--diff`：7 个受影响 Python 文件无需改写。
- 未执行 Git stage/commit；工作区既有 `.release-build-v1.0.5/` 等未跟踪内容保持不动。

### 后续

部署后重点检索 `event=resource_lifecycle`、`event=task_lifecycle`、`event=sync_phase`，确认 `blocked_by_task_code` 是否为 `tracker_sync_598b784c`，并结合 `holder_phase`/`holder_age_ms` 判断实际卡点。

## 2026-08-23（第五批）：孤儿 current_detail_id Schema 漂移重启自愈

### 结论

新快照暴露启动对账查询失败：`orphan_current_candidate.current_detail_id` 在运行库中不存在，但 ORM 对账逻辑已按该字段查询。此前迁移 `975dad435c03` 已可能写入 `alembic_version`，因此单纯 `upgrade head` 会判断“已是最新”并跳过修复。新增 `c1d2e3f4a5b6` Alembic 修复迁移，后端重启时自动处理该版本号/物理 Schema 不一致场景。

### 变更

- `backend/alembic/versions/c1d2e3f4a5b6_repair_orphan_current_detail_id.py`：从 `975dad435c03` 进入新 head；缺列时补 `current_detail_id`，按 `last_seen_scan_id` 优先、canonical path 最新明细兜底回填，并补齐稳定明细唯一索引和扫描状态索引；健康库幂等跳过。
- `backend/tests/core/test_orphan_schema_repair_migration.py`：覆盖“版本号已到旧 head 但缺列”与“健康 Schema”两种重启迁移场景。
- 同步更新迁移 head 测试断言、数据库迁移约束、roadmap、`feature_list.json` 与本交接记录。

### 安全边界

迁移前仍由统一 `migrate_database()` 生成备份；修复失败会在孤儿对账、seed 和调度器启动前 fail-fast。未修改 `E:\Users\huangzj\Desktop\app.db`，未执行任何用户数据清理。`downgrade` 保留该列，避免回滚再次制造已知 Schema 漂移。

### 当前验证

- `python -m pytest tests/core/test_orphan_schema_repair_migration.py -q`：2 passed。
- `python -m pytest tests/core/test_orphan_schema_repair_migration.py tests/core/test_db_migration.py tests/core/test_db_rollback_scenarios.py tests/core/test_orphan_migration_production_shape.py -q`：37 passed。
- `python -m pytest tests/core/test_startup_migration_guard.py tests/tasks/test_orphan_scan_task_lifecycle.py tests/services/test_orphan_query_state.py -q`：17 passed。
- flake8、mypy（新增迁移/测试）、Black `--diff`、`scripts/lint_btdeck.py`、JSON 解析和 `git diff --check` 通过。
- `python -m alembic heads`：仅 `c1d2e3f4a5b6 (head)`。

仓库根 `bash ./init.sh` 在当前 Windows 环境因 WSL `E_ACCESSDENIED` 无法启动，未归因于本次代码变更；其余定向验证已完成。

### 后续

部署包含该 revision 的后端；所有用户重启后会走统一 Alembic 启动迁移。Git stage/commit/push 等待用户明确指示。

## 2026-08-23（第五批）：Phase 4 M1 第一片——移动 UI 壳与四个核心页

用户真机验证伴侣模式通过后继续。Phase 3 被 Phase 0 闸门阻塞（android-wheels 推送等用户指令），Phase 4 不受阻故先行。

- utils/ui-mode.ts（偏好+视口+登录分流）、layout/mobile（底部 Tab 壳+桌面版出口）、views/mobile 四页（login/dashboard/torrents 卡片列表含暂停/恢复/删除/notifications 点击已读）、路由 /m/* 懒加载组、permission.ts 守卫首部模式分流+4 处登录跳转模式化。
- 项目惯例修正：class 组件导入须用 vue-property-decorator（vue-class-component 直用在 Jest 下 Vue 绑定 undefined）。
- 验证：ui-mode 11 + MobileLayout 5 新用例、守卫回归 31、前端全量 704 全绿；tsc/lint/build 通过；m-* 懒加载 chunk 实证。
- 生效提醒：移动版部署到手机需把新 frontend/dist 发布到服务器（重打包/重部署）；本地可 npm run serve 手机访问开发机验证。
- Git 提交待用户指示。

## 2026-08-23（第六批）：tracker_sync 异常边界观测增强

### 结论

针对 `tracker_sync` 中“异常被转成 `errors` 后继续执行、服务日志却缺少 traceback”的排查目标，完成只读观测增强。未改变 tracker 同步的结果映射、批失败处理、游标推进、重试、取消和数据库写入语义，也未修改 `E:\Users\huangzj\Desktop\app.db`。

### 变更

- `sync_observability.py`：新增 `event=sync_error` 及 `stage/operation/error_type/suppressed/continue_after_error` 白名单字段。
- `sync_coordinator.py`：下载器开始/完成、tracker 子结果、tracker 状态阶段开始/跳过/完成均补充观测；下载器粒度异常、同步阶段异常、Tracker 状态阶段异常输出 traceback 并发射 `sync_error`；结果含错误时以 warning 输出 `error_count` 和前 5 条错误。
- `torrents_async.py`：qB/TR tracker-only 的输入校验、单种子远程获取、worker gather、批提交、行提取、检查点读写、qB SDK 标记失败均记录异常类型和是否继续执行；有错误的 tracker-only 汇总提升为 warning。
- `tracker_sync_task.py`：记录有效下载器摘要、Coordinator 结果和最终错误摘要。
- `feature_list.json`、`docs/roadmap/`、`session-handoff.md`：登记本次观测边界与实测行号。

### 验证

- `python -m pytest tests/services/test_sync_observability.py tests/services/test_sync_coordinator.py tests/api/test_torrents_async_tracker_budget.py -q`：82 passed。
- flake8：通过；mypy（4 个后端源文件）：无错误；`git diff --check`：通过。
- Black 对受影响大文件的全量 `--check` 报告既有格式差异且长时间未结束，未执行全文件重排，避免引入无关大范围 diff；本次新增代码未触发 flake8/mypy 问题。

### 部署后观察

按 `run_id` 检索 `event=sync_error`，重点看 `stage`：`tracker_enrich_single_torrent`、`tracker_batch_commit`、`tracker_row_extract`、`tracker_checkpoint_push`、`tracker_status`；再与 `tracker_sync_task coordinator_result`、`sync_coordinator downloader_done` 对照，确认异常是否被抑制、是否继续处理以及最终是否变成 partial/failed。

## 2026-08-24 安卓移动端桌面测试体系搭建 + android/ data 包漏提交修复

### 背景

用户要求继续安卓移动端开发并提供桌面端测试移动端的方案。盘点发现：`C:\software\android-build-env\`（上次便携工具链）与 BlueStacks 均已删除；`android/` 干净检出于 dev HEAD 无法编译——**a2f4e72 提交漏掉 `data/` 包三个文件**（ServerProfile/ServerProfileStore/HealthClient，提交信息与 README 均描述了它们但文件未入库），工作区副本也已丢失。

### 修复与重建

- **data 包重建**：依据调用方（ServerListActivity/WebViewActivity 的 import、构造参数、字段读写）与 android/README.md 契约重建三文件：ServerProfile（data class + HealthState 枚举 + org.json 序列化，UUID id）、ServerProfileStore（SharedPreferences 单键 JSON 数组，loadAll/find/upsert/delete）、HealthClient（OkHttp 挂起函数，live→ready 链式探测，SSL/网络错误分类，Report(state,version,detail)）。
- **工具链重建** `C:\software\android-build-env\`：cmdline-tools（dl.google.com）+ platform-tools + platforms;android-35 + build-tools;35.0.0 + emulator + system-images;android-35;google_apis;x86_64 + Gradle 8.9（腾讯镜像）；JDK 用系统 `C:\Program Files\Java\jdk-17`（17.0.15）。`local.properties` 的 sdk.dir 必须正斜杠写法 `C\:/...`（单反斜杠被 properties 转义吞掉）。
- **构建验证**：`:app:assembleDebug` + `:app:testDebugUnitTest` BUILD SUCCESSFUL（11 单测）；双变体 APK（strict / lan-cleartext `0.1.0-mvp+lan`）产出至 `android/dist/`（不入库）+ WebView 验证截图 evidence。

### AVD 全链路实测（Pixel 6 / API 35，AVD btdeck-test）

- 安装 lan-cleartext 版 → 向导页副标题正确显示"（LAN 明文构建）"。
- 添加服务器 `http://10.0.2.2:5001`（AVD 宿主机回环别名）：URL 输入后**明文风险确认复选框按 LanHostPolicy 自动出现**（http+10.x 私有主机），勾选后保存成功。
- 菜单"测试连接"：**就绪 / v1.0.5**——HealthClient→OkHttp→10.0.2.2:5001→live→ready→data.version 解析全链路正确；store.upsert 持久化（root 读 shared_prefs 实证 JSON 完整）。
- WebView（am start --es profile_id 直达）：加载出 **BtDeck 移动版登录页**（窄视口 auto 分流在 WebView 内生效），副标题"v1.0.5 · 服务就绪"。截图存 android/dist/evidence-webview-mobile-login-2026-08-24.png。

### 前端移动 UI 桌面链路实测（L1）

- 本地起后端（miniconda btpManager 环境 uvicorn 5001）+ 前端 dev server（8080，均 0.0.0.0 监听）。
- Chrome 390×844 设备模拟：`/` 自动分流 `/#/m/login` → 移动登录（admin）→ 强制改密守卫带去桌面设置页（新库默认口令预期行为；API 完成改密 `Btdeck@2026dev` 后需**刷新页面**让 store 重建）→ `/m/dashboard` 统计卡片、`/m/torrents` 筛选+空态、底部 Tab active 态全部正常。
- 测试环境凭据：admin / Btdeck@2026dev（本地开发库）。

### 已知坑（写入 docs/android/desktop-testing.md）

uiautomator dump 在本 AVD 上 ListView 行 bounds 从 y=0 起（与 action bar 重叠、按 dump 坐标点击列表项无效，底部按钮正常）——列表项用真机或 `adb root` + am start --es profile_id 直达；Git Bash 把 `/sdcard` 转成本地路径需写 `//sdcard`；adb input text 不支持中文；login 端点 password 明文直传而 changePassword 端点 base64（行为不一致，测试脚本注意）；`vue.config.js` devServer.allowedHosts 只含域名，其它设备用 IP 访问 dev server 时需补。

### 交付物

- `docs/android/desktop-testing.md`（新）：三层测试体系（L1 浏览器模拟 / L2 AVD / L3 真机）+ 本机环境清单 + 一次性重建步骤 + 8 条已知坑。
- `android/README.md`：data 包重建记录节。
- feature_list.json task .3/.5 evidence 追加；progress.md / session-handoff.md 本批记录。
- 未执行 Git 提交（待用户指示）。M1 余项（种子详情页/更多操作、下拉刷新、通知未读角标、桌面侧栏切换入口）待下一批实现。

### 补记（根因修正）

data 包"漏提交"的真正根因是根 `.gitignore:58` 的 `data/` 规则（Docker 数据目录防误入库）把 `android/app/src/main/java/com/btdeck/companion/data/` Kotlin 源码包也静默忽略——当时 `git add` 根本加不进去。已加 `!android/.../data/` 例外（.gitignore 注释记录此事），重建三文件现在对 git 可见，下次提交即入库。

## 2026-08-24（二）移动布局壳主题色对齐 + 汉堡抽屉完整功能菜单

### 需求与决策（用户确认）

- 移动版主题色与桌面端相同：Tab 激活色原为 Element 默认蓝 #409eff，桌面端主色为 #059669（theme-variables.scss --color-primary 全套变量）。改法：Tab/抽屉激活色统一 `var(--color-primary)`（与桌面同源，无硬编码）；其余中性灰文本与深色头部 #27303f 本就与桌面侧栏一致，Element 组件色已全局绿。
- 完整功能菜单展示形式：11 个功能塞不进底部 Tab（>5 不可用），用户在"4+1 更多面板"与"顶部汉堡抽屉"中选定**顶部汉堡抽屉**。

### 实施（frontend 2 文件）

- `src/layout/mobile/index.vue`：header 左侧汉堡按钮（aria-label，36px 三横线）→ el-drawer（direction ltr / 78% / append-to-body）；抽屉分"移动版"组（仪表盘/种子/通知，当前项标记）与"全部功能（桌面版页面）"组（下载器管理/种子列表桌面/Tracker管理/定时任务/日志管理/回收站/孤儿文件/查询模板/系统设置，父路径均有 redirect）+ 底部"完整桌面版"（与头部出口同款写偏好）。导航语义：移动项 replace 保持单栈；桌面项 **push 保留返回栈且不写 ui_mode 偏好**（返回键/刷新回移动版）。抽屉内容挂 body，样式走第二个非 scoped 块。顺带修掉一个真实 bug：`goMenuItem` 初版从 $router 解构方法会丢 this（真实 VueRouter 会崩），改显式调用。
- `tests/unit/mobile-shell.spec.ts`：5→11 用例（汉堡开抽屉+菜单 12 项、移动项 replace、当前项只关不导航、桌面项 push 且不写偏好、抽屉底部完整桌面版同头部、**主题色静态契约**：`.mobile-tab.is-active` 必须 var(--color-primary) 且全文件禁 #409eff 回归、`.mobile-menu-item.is-active` 同主题变量）；$router mock 补 push；el-drawer 用透传插槽 stub 规避 Element DOM 副作用。

### 验证

- Jest：mobile-shell 11 + ui-mode 11 + permission-guard 回归 11 = 33 passed；tsc、改动文件 ESLint、生产 build 通过。
- 浏览器实测（390×844）：汉堡打开抽屉渲染完整（分组/当前标记/箭头/完整桌面版按钮，dialog 语义）；点"下载器管理"跳 `/#/downloader` 桌面页正常渲染（面包屑/侧栏折叠态）；浏览器返回键回 `/#/m/dashboard` 移动版（push 返回栈设计生效）。注：本会话 IAB 的 Playwright click/CUA 坐标点击不稳定，抽屉交互经 dom_cua 节点点击验证——非产品问题。
- 未执行 Git 提交（待用户指示）。

## 2026-08-24（三）：独立 VitePress Wiki 初始化

- 在 `btdeck-wiki/` 创建独立 Git 仓库，采用 VitePress 1.6.4 + Node 22+。
- 完成深色顶栏、左侧目录、宽内容区、右侧页内目录和本地搜索主题；建立首页、指南、架构、API、部署、维护、路线图和版本页面。
- 增加 Wiki 专用 `AGENTS.md`、`feature_list.json`、`progress.md`、`session-handoff.md` 与 GitLab CI 构建任务。
- `npm run docs:build` 通过；未执行 Git stage/commit/push。

## 2026-08-24（三）移动头部主题色 + 下载器提入底部 Tab 第一梯队（新移动页）

### 需求（用户确认）

1. 头部改为主题色：布局壳头部与抽屉头部背景 #27303f → var(--color-primary)（与桌面端 #059669 同源）；汉堡条/桌面版链接/关闭钮前景改白色系（rgba(255,255,255,.9)/#fff）保证绿底对比度。
2. 初始菜单（权重等级高）：底部 Tab 从三项改四项——仪表盘/下载器/种子/通知；"下载器"提入第一梯队。

### 实施（frontend 5 文件：1 新增 + 4 修改）

- 新增 `src/views/mobile/downloader.vue`：移动下载器监控页（MVP 只读）——卡片（名称/类型/host:port/在线离线徽标，徽标色走 var(--color-primary) 系）+ 每卡"测试连接"（复用桌面 /downloader/testConnection，成功提示并刷新列表同步 connectStatus，失败弹错不刷新）+ 刷新按钮 + 空态；脚注指路抽屉「下载器管理」桌面页做编辑/设置/路径映射。复用 getList({page:1,pageSize:100})。
- `src/router.ts`：/m/downloader 注册（m-downloader 懒加载 chunk，build 产出实证）。
- `src/layout/mobile/index.vue`：tabs/mobileMenuItems 四项（插下载器）；头部+抽屉头部主题色。
- `tests/unit/mobile-shell.spec.ts`：四 Tab 断言、菜单 13 项、桌面组起始索引 at(4)、主题色契约扩展（头部/抽屉头部/Tab 激活三处 var(--color-primary)，源码禁 #409eff 与 #27303f）。
- 新增 `tests/unit/mobile-downloader.spec.ts` 6 用例（列表渲染含在线/离线徽标、空态、接口异常、测试连接成功刷新+失败不刷新、主题色变量）。

### 过程问题（记录防再踩）

- spec 两处坑：①行首 `(xxx as jest.Mock)` 连续语句 ASI 吞分号 → 第二行变首行返回值调用（undefined(...)），改 jest.mocked() 形式；②shallowMount 下 el-button 为 kebab 形态 stub 且不转发 click 事件（findAllComponents({name:'ElButton'}) 匹配不到），按钮交互改为直调组件方法（行为链等价）。
- 本会话 IAB 浏览器交互（Playwright click/CUA 坐标）持续不稳定，Tab 切换浏览器实测未触发（Jest 已覆盖），hash 直达 /m/downloader 验证页面空态渲染正常。

### 验证

Jest 39 passed（shell 11 + downloader 6 + ui-mode 11 + permission-guard 11）；tsc、5 文件 ESLint、生产 build 通过；m-downloader chunk 实证产出。未执行 Git 提交（待用户指示）。

## 2026-08-24（四）：Phase 4 M1 余项四项收口（种子详情/下拉刷新/未读角标/侧栏入口）

### 结论

M1 余项四项全部完成并验证（未提交）：①种子详情页（路由 /m/torrents/detail/:downloaderId/:hash，快照缓存+getList 回查+getActiveTorrents 5s 轮询）；②手写 touch 下拉刷新 mixin 四页接入；③移动布局壳通知未读角标（60s 轮询+已读联动）；④桌面侧栏「移动版」入口（写 mobile 偏好，显式偏好优先视口）。

### 变更（frontend 14 文件：5 新增 + 9 修改）

- 新增：views/mobile/torrent-detail.vue（详情页）、views/mobile/mixins/pull-to-refresh.ts（class 式 mixin）、views/mobile/components/PullIndicator.vue（指示条）、views/mobile/torrent-status.ts（状态映射共享）、views/mobile/torrent-detail-cache.ts（快照缓存）。
- 修改：router.ts（详情子路由）、views/mobile/ 四页（mixin+指示条接入；torrents 卡片点击进详情+@click.stop 保护操作行；notifications 已读后 dispatch FetchUnreadCount）、layout/mobile/index.vue（角标+60s 轮询）、layout/components/Sidebar/index.vue（footer 移动版按钮）、components/common/LucideIcon.vue（注册 smartphone）。
- 测试：新增 pull-to-refresh.spec 6 例、mobile-torrent-detail.spec 6 例、sidebar-mobile-entry.spec 3 例；mobile-shell.spec 扩 4 例（角标三态、fake timers 轮询与销毁停止、mock '@/store/modules/notification'）。

### 关键决策与发现

- **后端单种子端点不可用**：GET /torrents/{info_id}/{downloader_id}/{downloader_name} 直接 return ORM 实体配 response_model=CommonResponse，FastAPI TestClient 实测响应 {"status":null,"msg":null,"code":null,"data":null}（无 from_attributes，实体字段全部丢失），且前端零消费方。详情页改用 getList（downloader_id+name_like，hash 匹配）回查，遵守本批不动后端原则；该端点缺陷已记录待后续修复。
- **mixins 导入坑**：vue-property-decorator 以大写 `Mixins` re-export（`export { Component, Vue, mixins as Mixins }`），小写 mixins 导入不存在。
- **模板函数坑**：.vue 模板只能访问实例成员，模块级 formatTorrentSize/formatRankio 须包装成实例方法/计算属性。
- 下拉刷新滚动容器直接 `closest('.mobile-content')`（自家布局壳类名），比通用 overflow 检测稳（jsdom 可测）。

### 验证

- Jest：相关 7 套件 58 例全绿（pull-to-refresh 6 + torrent-detail 6 + sidebar 3 + shell 15 + downloader 6 + ui-mode 11 + permission-guard 11）；前端全量 65 套件 954 例全绿。
- tsc --noEmit 通过；改动文件 ESLint 零输出；npm run build 通过（m-torrent-detail.6376c386.js + f5abc595.css chunk 实证）。
- 浏览器 390×844 实测（IAB setViewportSize + Playwright locator click 本会话稳定）：自动分流移动登录 → 仪表盘角标 3（API unread=3）→ 列表 20 卡（20/22018）→ 卡片点击进详情全字段 + Tracker 展开「正常」→ 返回列表 → 通知点击已读角标 3→2 实时联动 → 1440 宽视口桌面侧栏点「移动版」→ 移动布局 + 角标 2（偏好优先视口）。截图存 .release-build-v1.0.5/m-torrent-detail-evidence.png。
- 下拉刷新 touch 手势：IAB 无 touch 注入通道，浏览器级手势未验证（已知边界，逻辑单测覆盖 + 指示器挂载/空闲零高度浏览器确认）；真机/Chrome 设备模拟 touch 复核留给后续。
- 本机测试栈（与 desktop-testing.md 的 thoma 路径不同）：后端 C:/software/anaconda3/envs/btpManager/python.exe -m uvicorn（5001），本地开发库 data/backend/config/app.db，admin 已按 SOP 改密 Btdeck@2026dev（默认 admin 触发强制改密标记）。

### 待办

- 本批 14 文件 + 三份记录未提交（待用户指示）。
- 后端单种子端点空 data 缺陷待修复（单独批次）。

## 2026-08-24（五）：M2 五页面收口（上下文恢复 + 4 失败套件修复）

### 背景

上会话（sess_ff0b12a9）完成 M2 全部源码（五页面+路由+抽屉+守卫+specs）后中断，未写交接记录，遗留 4 个失败 Jest 套件。本会话通过 ReadSessionContext 恢复 handoff capsule 并与工作区实测对齐后收口。

### M2 交付内容（上会话源码，本会话验证确认）

- `/m/search`（search.vue）：简单查询（名称/下载器/状态/Tracker 域同桌面快捷筛选→getList）+ 高级搜索（复用桌面 AdvancedSearchBuilder→advancedSearch）；模板应用经 m2-template-cache（take 取走即清）自动回填执行；builder 保存模板→createSearchTemplate。
- `/m/query-templates`（query-templates.vue + m2-template-cache.ts）：客户端名称/来源过滤；系统模板（is_default）只可应用不可删除；「应用」写缓存跳 /m/search；新建/编辑保留桌面。
- `/m/recycle-bin`（recycle-bin.vue）：卡片+名称搜索+下拉刷新；单条恢复/彻底删除（用户拍板不做批量）。
- `/m/logs`（logs.vue）：卡片流+操作类型/结果/名称三筛选+分页；统计/导出保留桌面。
- `/m/downloader/settings/:id`（downloader-settings.vue）：整页复用桌面 DownloaderSettingsDialog，关闭即返回；downloader.vue 升级管理版（新增/编辑/删除/同步/测试/设置入口；发现桌面缺陷 DownloaderDialog submit 只关框不落库、addDownloader 零调用点，移动端显式调用，待反馈桌面端）。
- 路由 5 条 m-* 懒加载 + 抽屉重组（移动组 8/桌面组 6）+ toMobilePath 三映射 + permission.ts 分流扩展。

### 本会话修复（4 套件 6 处，含 1 个真实产品 bug）

1. **search.vue 导入源错误**：buildAdvancedSearchRequest/FromTemplateGroups 实际定义在 views/torrents/utils/torrentBatch（670/713 行），原从 advancedSearchState 导入（只导出 buildAdvancedSearchParams）→ 模块加载即 TypeError，mobile-search 套件 worker 崩溃。
2. **search.vue 模板直调模块级函数（M1 已知坑复发）**：模板 `formatTorrentSize(t.size)` 报 "_vm.formatTorrentSize is not a function"（render error 被 Vue 吞掉导致 DOM 不更新、数据层正常——排查靠临时调试 spec 打印 render 错误）→ formatSize 实例方法包装（同 torrent-detail 约定）。
3. **downloader.vue testOne 真实产品 bug**：后端 /downloader/test 连接失败返回信封 code=200+data.success=false（桌面 handleTest 查 data.success），原实现只查 code 会把连接失败当成功提示并刷新 → 改 `code==='200' && result.success` 双条件，失败提示 data.message 不刷新。
4. mobile-search.spec 补 torrent-detail-cache 的 jest.mock（setCachedTorrent 原是真实函数非 spy）+ 删未用导入。
5. mobile-query-templates.spec：el-button-stub 断言不可行（Jest 无全局 element-ui，unknown 元素不产生 stub）→ 改卡片文本断言删除入口有无。
6. mobile-downloader-settings.spec：shallowMount 把自定义 mock dialog 替换为 `<downloader-settings-dialog-stub>`（mock template 不渲染）→ class 查找改 stub 标签名。另 m2-template-cache.ts member-delimiter lint --fix。

### 验证

- M2 相关 8 套件 67 例全绿；前端全量 70 套件 989 例全绿；tsc 零错误；M2 相关 19 文件 ESLint 通过；生产 build 通过，11 个 m-* chunk 实证（M2 新增 5 个）。
- 浏览器（后端 5001/前端 8080 均存活）：390×844 视口自动分流 /m/login、登录页四元素渲染、Vue data 绑定 evaluate 实证同步、登录 API curl 200、未登录直达 /m/search、/m/recycle-bin、/m/logs 守卫正确重定向带 redirect 回跳——全部实测通过。
- **IAB 交互通道本会话故障**：Playwright click 超时/CUA 坐标点击/dom_cua 节点点击/Enter keypress/截图全部无效（fill/快照/evaluate 正常），较前两会话同类故障更重；页面内交互级验证（登录提交/搜索执行/模板应用）未完成，留待 Chrome 设备模拟或真机复核（docs/android/desktop-testing.md SOP）。

### 待办

- M2 批次 22 文件未提交（11 修改含三份记录 + 11 新增），待用户指示（M1 各批已入库：349bd01/a8c1ac8/2746177）。
- 桌面 DownloaderDialog submit 不落库缺陷待反馈/修复。
- M2 页面浏览器交互级人工复核（Chrome 设备模拟或真机）。
- M2（高级搜索/查询模板/回收站/日志/下载器高级设置移动化）未动。

## 2026-08-24（六）：M2 交互级复核（五页全通过）+ logs 筛选值 bug 修复 + DownloaderDialog 契约文档化

### 结论

本会话 IAB 交互通道恢复（上会话故障为会话级环境问题），390×844 下 M2 五页交互级复核全部实测通过；复核抓到并修复一个真实 bug（logs 结果筛选值）；DownloaderDialog「submit 不落库」定性修正并文档化。

### M2 交互复核结果（全部通过）

- /m/logs：卡片列表（类型/结果/时间/详情/操作人）+ 结果筛选（失败）+ 分页（加载更多 20/451）+ 脚注。
- /m/search：简单查询「老男孩」→结果卡片（名称/状态/下载器/8.4GB/进度）→卡片点击进详情（URL 带 downloaderId/hash）；高级模式桌面 AdvancedSearchBuilder 完整渲染（条件组/分组字段下拉/操作符/包含排除/保存模板/预览），构建「种子名称 包含 老男孩」执行→20 条结果；操作符未选时构建器自身弹「未知搜索操作符」校验提示（行为正确）。
- /m/query-templates：模板卡列表（名称/类型/使用次数/时间/应用+删除）→点应用→跳 /m/search→「已应用模板「测试模板」」提示+自动执行出结果（m2-template-cache 跨页链路实证）。
- /m/recycle-bin：卡片（名称/已删除/大小/下载器/路径/删除时间/恢复+彻底删除）+「彻底删除」确认框正确弹出含警告文案（实际删除未执行，保护数据）。
- /m/downloader：4 卡管理版（全部在线徽标+测试/同步/设置/编辑/删除）+新增按钮；/m/downloader/settings/:id 直达渲染桌面 DownloaderSettingsDialog（标题「下载器设置 • qb」/四页签/基本设置全套表单：名称/端口/主机/类型/HTTPS/认证/配置选项/测试连接/功能开关）。

### 复核发现并修复（真实 bug）

- **mobile logs.vue 筛选值错误**：结果筛选「失败」误传 `failure`，后端 audit_service 契约为 `success/failed/partial`（服务注释与桌面 audit.vue resultMap 双证），导致失败筛选恒空（复核时实证：选失败→空列表）。修复：value 改 `failed` 并补 `partial`（部分成功）选项对齐桌面三值。
- **展示三态折叠**：原 isSuccess 两态把 partial 显示为红色「失败」→ resultText/resultClass 三态（成功绿/部分成功橙 #e6a23c/失败红），error_message 展示条件保留 isSuccess。
- mobile-logs.spec：mock 数据与断言同步改 failed；+1 用例锁三态展示与筛选选项值契约（禁 value="failure" 回归），6 例全绿。

### DownloaderDialog 定性修正（非桌面功能缺陷）

桌面 index.vue 实际绑定的是 DownloaderSettingsDialog（自带 add/up 落库，1151/1189 行），handleSubmit 只关框刷新的注释是对的——**桌面端无功能缺陷**。DownloaderDialog 的问题定性为契约陷阱：emit submit 不做任何落库、除移动端外零消费方，复用方必须显式调 addDownloader/upDownloader（移动端已正确如此）。修复：组件头与 handleSubmit 补契约注释指明责任边界与参考实现。

### 验证

前端全量 70 套件 990 例全绿；tsc/ESLint（3 个改动文件）通过；生产 build 通过，11 个 m-* chunk（m-logs/m-search/m-downloader/m-query-templates/m-recycle-bin 哈希更新实证）。浏览器复核操作备注：IAB click 会话内间歇失灵（playwright click 与 CUA 坐标交替失败、MessageBox 遮罩期点击全部无效），Element 下拉选项对 actionability 判定 hidden——用 dom_cua 节点点击、键盘导航（ArrowDown+Enter 选操作符）、evaluate 只读坐标兜底完成全部链路；均为环境非产品问题。

### 待办

- 本批 4 文件未提交（logs.vue + mobile-logs.spec.ts + DownloaderDialog.vue + 三份记录），待用户指示。
- IAB 点击间歇失灵为跨会话环境问题（三个会话不同表现），交互复核如再受阻优先键盘导航/坐标兜底路径。

## 2026-08-24（七）：修复后端单种子端点空 data 缺陷（M1 遗留最后一项）

### 结论

`GET /api/v1/torrents/torrents/{info_id}/{downloader_id}/{downloader_name}`（torrent_crud.py get_torrent，M1 批次实测响应全 null 的遗留缺陷）已修复并活实例验证。M1 遗留待办清零。

### 根因与修复

- 根因：端点直接 `return torrent`（SQLAlchemy ORM 实体）配 `response_model=CommonResponse`，Pydantic v2 无法从 ORM 属性构造信封（CommonResponse 无 from_attributes），四字段全序列化为 null。
- 修复：复用 torrent_helpers.convert_to_vo（与 getList 同源 ORM→TorrentInfoVO 转换，camelCase 输出）显式包装 `CommonResponse(status="success", code="200", data=vo)`；未找到由 raise HTTPException(404) 改为项目惯例信封 `code="404"` + HTTP 200（与 downloader_settings 等端点一致）；移除失去使用点的 HTTPException import。
- 端点路径说明：端点声明 "/torrents/{...}" 且挂载于 prefix="/torrents"，实际完整路径含双 torrents 段（历史怪癖，保持不变避免破坏契约；前端零消费方）。

### 验证

- 新增 tests/api/test_torrent_single_get_endpoint.py 3 用例：命中返回完整 VO（camelCase 字段断言，核心回归锚点=修复前 data 恒 null）、未找到信封 404、dr=1 软删除行不返回；TestClient + 真实 SQLite ORM。3 passed。
- 相关回归 88 passed（torrent_crud query/add_fallback/review/status_migration + auth_protection）。
- flake8 / black / mypy（torrent_crud.py + 新测试）通过。
- 活实例验证：重启 5001（uvicorn，开发库）后 curl 实测——命中返回 status=success/code=200/data 完整（name「Mushoku.Tensei...S03」/hash/1.45GB/seeding 全真实值）；未找到返回信封 code=404。

### 待办

- 本批 3 文件未提交（torrent_crud.py + 新测试 + 三份记录），待用户指示。
- 移动端详情页目前仍走 getList 回查（M1 绕开方案，可用）；端点修复后如需切换到单种子直查为可选优化（数据一致，非必须）。

## 2026-08-24（八）：移动端 M3（Tracker 关键词看板/搜索 + 定时任务 + 抽屉重组）

### 结论

M3 完成并验证（未提交）。M3 无计划预定义清单——AskUserQuestion 未获回复，按自治指令以推荐范围执行：**Tracker 核心移动化（关键词看板+关键词搜索）+ 定时任务移动化 + 抽屉遗留清理**，全部来自用户列出的候选方向。

### 交付内容（前端 13 文件：6 新增 + 7 修改）

- `/m/tracker/keywords-board`（tracker-keywords.vue）：四池 Tab（候选/忽略/成功/失败，计数走 getPoolStatistics）+ 卡片流（getPoolKeywords 20/页 + 加载更多）；桌面拖拽移池在移动端改为卡片下拉「移动到X池」（moveKeywordToPool 同 API）+ 下拉删除（$confirm）；添加关键词复用桌面 AddKeywordDialog（92% 宽 media query 收缩），候选池禁用添加；搜索入口跳 /m/tracker/keywords-search；下拉刷新。
- `/m/tracker/keywords-search`（tracker-keywords-search.vue）：searchAllPools 全池检索，筛选与桌面同字段集（keyword/pool_types 逗号拼接/time_range/sort_by）；卡片（关键词+池徽标+时间）+ 移动下拉（原地移动禁用）/删除；支持 ?keyword= 初始词；加载更多。
- `/m/tasks`（tasks.vue）：任务卡片流（状态/类型/cron/描述/启用标记/上次执行格式化）；最近结果六态（getTaskOutcomeMeta 同源）+ 数据陈旧（isTaskDataStale/getStaleTooltipText 同源，均实例方法包装——模板不可直调模块级函数）；操作集：立即执行（禁用任务拦截 warning）/启停（PUT /cronTasks/{id} 部分更新 enabled，CronTaskUpdate 全字段可选 + exclude_none 已核实）/中断（仅运行中显示）/删除（$confirm）；新建/编辑/完整日志脚注指路桌面。
- 路由 3 条 m-* 懒加载 + 抽屉重组：移动组 8→10（+Tracker关键词/+定时任务），桌面组 6→4（移除下载器管理——/m/downloader 已全覆盖；移除定时任务——已移动化；Tracker管理 → 「Tracker 汇报/测试（桌面）」直达 /tracker/reannounce-config）。
- 分流策略：/tasks 全前缀拦截（M2 模式，编辑含 Monaco 不适合移动）；/tracker 精确拦截（仅 /tracker、/tracker/keywords-board、/tracker/keywords-search 三路径），汇报配置/测试工具保留移动模式桌面直达。

### 本批发现并修复（桌面缺陷）

- **keywords-board.vue extractErrorMessage 使用未导入**（4 处错误路径：池加载失败/移动失败/删除失败），触发即 ReferenceError——与 keywords-search.vue 同目录同函数（@/utils/tracker，签名 (error, defaultMessage) 匹配），补一行导入修复；eslint/tsc/keyword 相关 33 例通过。

### 本批新增踩坑记录（M3 三连，均模板层）

1. 模板内事件箭头函数不可带 TS 类型标注（`@command="(cmd: string) => ..."` → vue-jest 模板编译失败，报错不指向真因）→ 去 `(cmd)`。
2. 模板不可用 `??`（空值合并，buble/vue-template-es2015-compiler 只到 ES2015）→ 计数兜底收进实例方法 poolCount。
3. 模板不可用 `!` 非空断言 → v-if 守卫 + 函数双调用（桌面 tasks 页同款写法）。

### 验证

- Jest 全量 73 套件 1014 例全绿（+3 套件 +24 例：tracker-keywords 7 / tracker-keywords-search 6 / tasks 9；mobile-shell/ui-mode 契约同步更新）。
- tsc --noEmit 零错误；13 文件 ESLint 通过（含消掉 2 个 no-non-null-assertion warning）；生产 build 通过，14 个 m-* chunk（新增 m-tracker-keywords / m-tracker-keywords-search / m-tasks）。
- 浏览器 390×844（IAB DOM 快照证据；**本会话 click/keyboard/screenshot 通道全断**——playwright click 超时、dom_cua/CUA 坐标点击不达 Vue 处理器、Tab 不移焦点、截图 guest 失败，与交接（五）最重故障模式一致，fill/goto/snapshot/evaluate 正常）：
  - 看板：四池真实计数 112/1/1/81、候选池 20 卡、加载更多 20/112、候选池添加按钮禁用、脚注。
  - 搜索：全池 195 条卡片+池徽标+操作；?keyword=dupe 全新挂载 → 仅 6 条 dupe 命中、无分页按钮（检索过滤链路 e2e；注意 query 变更不重挂载组件，验证须先离开再进入）。
  - 任务：13 张真实任务卡、六态实证（成功/已跳过）、数据陈旧双语义（从未成功数据 + 最后更新过久）含解释文案、中断按钮按运行态正确隐藏。
  - 守卫：/#/tasks/index → /m/tasks 分流；/#/tracker/keywords-board 停留移动页；/#/tracker/reannounce-config 移动模式桌面布局直达（不拦截实证）。
  - 点击类交互（池切换/下拉移动/抽屉菜单/任务操作）浏览器未达，全部有 Jest 直调方法覆盖（switchPool/handleCommand/handleMove/toggleEnabled/confirmDelete 等）。

### 待办

- 本批 13 个前端文件 + 三份记录未提交，待用户指示。
- M3 点击级交互复核留待交互通道恢复的会话或真机（Chrome 设备模拟 docs/android/desktop-testing.md SOP）。
- 后续候选（待用户定）：M4 孤儿文件移动化、系统设置移动化（价值低建议永留桌面）、移动独有优化（PWA/手势）、桌面双模式对齐（task .6，属后端/打包域）。

## 2026-08-24（九）：移动端 M4（孤儿文件双 Tab 移动化）

### 结论

M4 完成并验证（未提交）。AskUserQuestion 获用户确认范围：**孤儿文件移动化 + 隔离区立即清除也做**（单条+强确认）。至此移动抽屉桌面组仅余 3 个有意保留的桌面页（种子列表桌面/Tracker 汇报测试/系统设置），功能页移动化收官。

### 交付（前端 7 文件：2 新增 + 5 修改）

- `/m/orphan-files`（orphan-files.vue）：双 Tab（孤儿文件/隔离区）与桌面同构。
  - **孤儿文件 Tab**：扫描上下文卡（最近扫描时间/待清理数+大小/已忽视数/清理门禁 cleanup_block_reason）；触发扫描（$confirm → triggerScan → 2s/3s 轮询 getScanStatus，完成/失败提示+刷新，beforeDestroy 清理）；筛选状态/置信度/路径；卡片（路径 3 行截断/状态三态/置信度标签/大小/副本徽标/下载器/mtime）；清理走桌面同款两段式（门禁拦截 → cleanupPreview → rejected/空结果分支提示 → $confirm 含条数/大小/低置信度警告 → cleanupOrphans 同载荷 → task_id 提示）；忽视/取消忽视（setIgnored 单条含 scan_id，rejected/全失败/部分成功分支提示）。
  - **隔离区 Tab**：卡片（原路径/大小/置信度/隔离时间/预计清除时间/延迟次数）；单条恢复（restoreQuarantined，rejected 报原因）；单条立即清除（用户拍板纳入：$confirm type=error 含「不可恢复」强文案 → purgeQuarantineNow → already_running/task_id 分支提示）。
  - 留桌面（脚注）：文件夹聚合视图、副本位置弹框、前缀快捷操作、批量操作、守卫复核。
- 路由 m-orphan-files 懒加载 + 抽屉（移动组 11：+孤儿文件；桌面组 3：移除孤儿文件）+ /orphan-files 全前缀拦截（M2 模式）+ toMobilePath 映射。

### 验证

- Jest 全量 74 套件 1025 例全绿（+mobile-orphan-files 10 例：渲染/筛选透传/两段式清理与分支/门禁拦截/忽视分支/扫描轮询 fake timers/隔离区恢复清除与分支/双 Tab 分页；mobile-shell 抽屉 11+3 契约、ui-mode M4 映射同步）。
- tsc 零错误；8 文件 ESLint 通过；build 通过，m-orphan-files chunk 实证（m-* 共 15 个）。
- 浏览器 390×844（IAB DOM 快照）：页面渲染实证——双 Tab/扫描上下文卡空态分支（开发库无扫描记录：「最近扫描：暂无/待清理 0 个/清理暂不可用：无任何扫描记录」门禁文案）/筛选/空态/脚注；守卫 /#/orphan-files/index → /m/orphan-files 分流实证。
- **本回合 IAB 点击通道仍全断**（playwright click 与 dom_cua 节点点击均不达 Vue 处理器，连续第二回合）；Tab 切换/清理/恢复/清除链路由 Jest 直调方法覆盖。开发库无孤儿扫描数据，带数据卡片渲染与扫描链路留待真机或含数据环境复核。

### 待办

- 本批 7 前端文件 + 三份记录未提交，待用户指示。
- 点击级交互与带数据渲染复核留交互通道恢复会话或真机（可选：dev 环境跑一次孤儿扫描生成数据后复测）。
- 功能页移动化收官；后续候选：移动独有优化（PWA/手势）、桌面双模式对齐（task .6）。

## 2026-08-25（一）：移动独有优化（PWA+手势）+ 桌面双模式对齐 task .6 首批

### 结论

用户确认继续两大后续候选（AskUserQuestion 三项范围决策均获确认：桌面伴侣模式=内嵌 webview、手势=Tab 滑动切换+抽屉关闭、PWA=完整启用含更新提示）。本批完成：①前端 PWA 完整启用 + 移动手势；②后端 desktop_companion 桌面双模式对齐（task .6 逻辑层+GUI 全部落地，窗口链路实测留待后续）。未提交。

### 关键调研发现（PWA 前史）

- @vue/cli-plugin-pwa 早已在构建链生效（dist 产物 service-worker.js/manifest 俱在），但 main.ts 从未 import registerServiceWorker——SW 运行时从未注册；manifest/主题色/图标全是模板默认值（"Vue Typescript Admin"/#4DBA87）。
- main.ts 存在 retireLegacyServiceWorkers()：模板时代 SW 曾钉死旧应用壳，项目主动禁用并清理遗留（注销根 scope 注册+删模板前缀缓存）。**重启 PWA 的核心是共存设计**：新 SW 以 `?src=btdeck` 标记注册，retire 改为只注销无标记注册——否则每次启动把自己的 SW 清掉。
- vue-cli-plugin-pwa v5 行为实测：public/manifest.json 是 manifest 源（存在时原样拷贝）；cacheId 默认包名（vue-typescript-admin-template，恰为遗留清理前缀，必须改）；`appleMobileWebAppCapable` 为扁平选项（v4 的 appleMobileWebAppOptions 对象不生效，首构建实证仍是 no 后改扁平修复）；GenerateSW 默认 skipWaiting/clientsClaim 均 false，SW 内 `self.skipWaiting()` 仅在 message 监听器内（grep 上下文实证）。

### 交付（批次 1 前端：PWA+手势）

- **PWA**：registerServiceWorker.ts 重写（标记 URL 注册 + updated() 派发 btdeck-sw-updated 事件）；deployment-recovery.ts 标记感知改造（RetirableServiceWorkerRegistration 增 scriptUrl；只注销无标记根 scope 注册、只删模板前缀缓存）；main.ts 先 retire 再动态 import 注册；vue.config pwa 补全（#059669 主题、capable yes、cacheId 'btdeck'、skipWaiting false + clientsClaim true）；public/manifest.json 品牌化（BtDeck/standalone/zh-CN/maskable）；favicon.svg 统一品牌绿；9 枚图标重生成（scripts/generate-pwa-icons.py，PIL 圆角 BT 字样，maskable 全出血 56% 安全区）；RefreshPrompt.vue 常驻 App.vue（发现新版本→立即刷新→SKIP_WAITING→controllerchange 去抖重载；无容器/无 waiting 直接重载兜底）。
- **手势**：MobileLayout 内容区水平滑动切四个底部 Tab 主页（轴锁 12px/阈值 60px/时长 800ms/切向动画 220ms；**仅精确路径匹配**——startsWith 会误命中 /m/torrents/detail 子页，已排除）；左边缘 24px 右滑优先开抽屉；抽屉内左滑/点遮罩关闭（el-drawer 显式 close-on-click-modal）；下拉刷新 mixin 补横向主导中止（touchstart 记 startX，|dx|>|dy| 且 >12px 归零中止，纵向不受影响）；swipeAnimTimer beforeDestroy 清理。

### 交付（批次 2 后端：desktop_companion，task .6）

- 新包 backend/app/desktop_companion（hosts/lan_policy/profiles/health/launcher），逐模块对齐安卓 com.btdeck.companion 语义：
  - hosts.py：URL 规范化（默认端口归一/IPv6/路径剥离）+ 私有主机字面量判定（127/8、RFC1918、169.254/16、fc00::/7、fe80::/10、*.local、localhost；不做 DNS、fail-closed）。
  - lan_policy.py：明文准入（https 放行；http 须私有+显式确认；公网 http 拒绝），四态 RejectReason 与文案对齐安卓。
  - profiles.py：ServerProfile 键名/五态健康对齐安卓 toJson；Store 原子写+脏数据容错（未知健康态回退 UNKNOWN）；trustedCertFingerprints 为安卓专用不落桌面（已知差异）。
  - health.py：live→ready 链式（data.status/data.version/reasonCodes），TLS 与不可达分类区分；纯 urllib 10s 超时（安卓 5s/10s 分离为已知差异）。
  - launcher.py：desktop_mode.json 持久化（BTDECK_MODE 环境变量 > 记录 > 未决向导）；DesktopLauncher 单次 webview.start() 事件驱动（向导默认高亮服务端/记住选择/管理页增删测试打开/远程窗口关→管理页恢复/重跑向导/退出）；内嵌品牌 HTML 两页 + pywebview js_api 桥；webview 惰性导入（测试环境无依赖可跑逻辑层）。
- desktop_main.py 集成：窗口环境先解析模式（server 直接原路径——历史行为不变；未决/companion 走启动器）；无桌面环境忽略 companion 落回服务端+告警。
- deploy/ 无需改动：desktop_companion 静态导入随 PyInstaller 分析；pywebview 依赖已在 requirements-windows-package.txt。

### 验证

- 前端：Jest 全量 **76 套件 1048 例全绿**（+refresh-prompt 6 例/pwa-manifest 5 例/手势 9 例/互斥 2 例/retire 标记感知改写）；tsc 零错误；13 文件 ESLint 过；build 过。dist 实证：manifest 品牌字段全中、SW setCacheNameDetails prefix btdeck + clientsClaim()、self.skipWaiting() 仅在 message 监听器、index.html theme-color #059669 + apple capable yes、maskable 图标拷贝；nginx.conf 既有 `location = /service-worker.js` no-cache 契约不受 query 标记影响（deployment-recovery.spec 既有断言保持通过）。
- 后端：desktop_companion 新增 **44 pytest 全过**（解析/私有判定/policy 四态/往返与键名对齐/脏数据/健康五态+TLS 分类/模式存储与 env 优先/launcher server 直达/管理 API 增删测试回写）；mypy/black/flake8 全过（7 文件）。
- 后端全量回归：3979 passed / 7 skipped / **1 failed**——tests/integration/test_orphan_scan_120k_regression.py 状态 API 时延 3362ms>3000ms 阈值；**单独重跑通过**（46.6s），判定为满载并发时性能抖动，与本批改动无涉（改动不触孤儿扫描链路）。

### 待办

- 本批前端 13 文件 + 后端 8 文件 + 三份记录未提交，待用户指示。
- 桌面 GUI 窗口链路实测（向导→管理→远程窗口切换、exe 打包 PyInstaller 实跑）留桌面会话；PWA 安装/更新流与手势真机实测留交互会话（逻辑层 Jest 已覆盖）。
- task .6 已置 in-progress；窗口链路实测后可收尾置 done。

## 2026-08-25（二）：移动端模拟器验证（PWA + 手势）

### 结论

按 docs/android/desktop-testing.md SOP 双层验证本次修改（838fc97 前端 PWA+手势）：**全部通过，1 项平台约束记录**。后端 5001（btpManager env）+ 生产 dist 验证；模拟器为 AVD btdeck-test（Pixel 6/API 35），Chrome 访问 http://10.0.2.2:5001。

### L1 浏览器设备模拟（IAB 390×844）——PWA 链路

- 视口分流：390×844 自动进 `/#/m/login?redirect=/m/dashboard` ✓
- 页面 meta：theme-color #059669、apple-mobile-web-app-capable yes、apple-mobile-web-app-title BtDeck、manifest link /manifest.json、apple-touch-icon ✓
- **SW 真实注册实证**：`navigator.serviceWorker.controller.scriptURL === "http://localhost:5001/service-worker.js?src=btdeck"`——带标记注册+已激活接管页面（clientsClaim 生效），与 retireLegacyServiceWorkers 清理共存无冲突 ✓
- 后端服务 PWA 文件：manifest.json 200 application/json（品牌内容）、service-worker.js?src=btdeck 200 text/javascript（MIME 合法）、maskable 图标 200 ✓（factory SPA fallback 服务 dist 根级文件的路径实证）
- IAB click 通道本回合故障（登录按钮 click/dom_cua 均不达，fill/snapshot/evaluate 正常；后端日志确认 login POST 未发出）——与前两会话同症，非产品问题；登录后流程转 L2

### L2 AVD 模拟器——手势（adb input swipe 真触摸 + CDP 状态断言）

登录链路：adb input text 在该 AVD 不可用（WERR_CALL_NOT_IMPLEMENTED，Gboard IME 限制）→ 改走 **Chrome CDP**（adb forward → chrome_devtools_remote → Runtime.evaluate native setter 填表单 + click），登录成功进 /#/m/dashboard；状态断言脚本读 location.hash + Tab 激活态 + 抽屉可见性。

| 手势 | 结果 |
|------|------|
| 内容区左滑 | dashboard→downloader→torrents 链式两步连续切换 ✓（Tab 激活态同步） |
| 内容区右滑 | 切回前一 Tab；第一个 Tab 再右滑不动（边界）✓ |
| 垂直滑动（含顶部下拉） | 不切 Tab（轴锁定让位下拉刷新）✓ |
| 汉堡开抽屉 | CDP click ✓（drawerVisible） |
| 抽屉内左滑 | 关闭 ✓ |
| 点遮罩关抽屉 | 真实触摸 tap ✓（CDP 合成 click 被 Element isTrusted 校验忽略，符合预期） |
| **左边缘右滑开抽屉** | **平台约束**：Android Chrome 保留左边缘右滑为返回导航（实测被 back 出 Chrome），页面收不到该手势；CDP Input.dispatchTouchEvent 协议级注入下 drawerVisible=true——**页面逻辑正确**，真机 Chrome 上该入口不可达属浏览器行为，PWA standalone/其他内嵌 WebView 环境不受影响 |

最终截图视觉确认：种子页卡片流渲染正常、"种子"Tab 绿色激活、布局无错位遮挡。

### 过程记录（后续会话参考）

- AVD Chrome 首启有欢迎页+通知弹窗，uiautomator dump 取 bounds 后 tap 跳过；"No internet connection" 横幅在页面实际加载成功时仍残留（展示性提示）
- 模拟器 back 手势退出 Chrome 后 CDP 目标页会被关闭、剩余 tab 可能网络栈卡 chrome-error——`am force-stop com.android.chrome` 重启恢复
- 验证后模拟器已关、临时脚本清理；后端 5001 保留运行（dev 实例惯例）

### 待办

- 无新增代码改动；本节为验证记录（无文件需提交——progress.md/handoff 更新待用户指示提交）

## 2026-08-25（三）：桌面 GUI 窗口链路实测（task .6 收尾）

### 结论

task .6「桌面双模式对齐」窗口链路全矩阵实测通过并置 done。实测抓到并修复一个 GUI 真实缺陷（向导选模式即进程崩溃），补 2 个回归单测；PyInstaller exe 打包+实跑全链路通过。本批改动：backend/app/desktop_companion/launcher.py（窗口切换顺序修复）、backend/tests/desktop_companion/test_launcher.py（+2 顺序回归；顺带 black 24.10/line-length=120 规范化 + 清理一个原有未用导入）、test_health.py（black 规范化，纯格式）。

### 发现并修复：向导选模式竞态崩溃（打包 exe 同样中招）

- 症状：向导页点击任一模式卡后进程即死（pythonnet `InternalPythonnetException: Failed to create Python type for System.Threading.Tasks.Task'1[[VoidTaskResult]] → NullReferenceException`）。
- 根因：`on_wizard_chosen`/`rerun_wizard` 原顺序「先 destroy 旧窗、再 create 新窗」。pywebview(winforms) 销毁最后一个窗口时在 on_close 里直接 `WinForms.Application.Exit()` 结束 GUI 循环；且运行期 create_window 走「既有窗口实例的 Invoke 通道」（instances 已空则无通道）——新窗建在正在退出的循环上，进程随 interprete 关停竞态崩在 .NET 线程。
- 修复：两处切换均改为「先建新窗、后销毁旧窗」（保持窗口计数不清零）；pywebview 5.4 winforms 源码 on_close/create_window 实读确认语义。回归：webview stub（sys.modules 注入）断言 create-before-destroy 顺序两用例。

### 实测矩阵（btpManager env + pywebview 5.4 + WebView2）

驱动方式：`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<N>` 开 WebView2 调试端口，Node 原生 WebSocket 做 CDP 客户端（Runtime.evaluate 驱动页面内嵌 HTML 的真实 onclick 路径），Win32 PostMessage WM_CLOSE 驱动原生窗口，配置全部走 CONFIG_DIR 临时目录隔离。

1. **首启向导**（无 desktop_mode.json）：向导弹窗；服务端卡带「默认」标签（默认高亮语义）；「记住选择」默认勾选；js_api 桥就绪。选伴侣+记住 → desktop_mode.json 写 mode=companion → 管理页窗口存活渲染（修复后不再崩）。
2. **管理页全链路**：四组校验文案全对（空名/地址无效仅 http/https/公网 http 一律拒/私有未确认拒）；私有 http+确认 → 添加成功，companion_servers.json 键名与值全对（cleartextAllowed=true）；测试连接 → 就绪 + v1.0.5 版本徽标，落盘 READY/serverVersion=1.0.5/lastHealthCheckedAt>0；死端口 → 不可达徽标；删除（window.confirm）→ 列表与落盘同步清空。
3. **打开远程**：新原生窗口「BtDeck - <名称>」连 http://127.0.0.1:5001（dev server 充当远程，loopback 属私有主机），加载远程 SPA 登录页（截图存证）且其 PWA service-worker（?src=btdeck）正常注册；管理页同时隐藏；lastConnectedAt 落盘。**关闭远程 → 管理页恢复显示 + 列表自动刷新**（连接时间从「从未」更新）。
4. **重跑向导**：管理页「重新选择模式」→ desktop_mode.json 删除、向导重现、服务器档案保留；选服务端+记住 → 记录 server → 全新库自动迁移 → uvicorn 5099 → 主窗口加载自家 SPA → 关主窗 → 服务优雅停机（WAL 清理）exit 0。
5. **BTDECK_MODE 优先级**：记录 companion + env server → 全程无向导直达服务端；记录 server + env companion → 全程无向导直达管理页；管理页「退出」按钮 → 全窗销毁进程优雅退出；无记录 + 向导直接关窗 → 落服务端模式且不写记录（主窗口连的是自家 5099 实例，URL 实证）。
6. **PyInstaller exe**：deploy/build-windows.bat 全过（npm ci+build、PyInstaller 43.8MB/1982 条目、verify-package PASS、Inno 跳过=本机未装 ISCC 与前批一致）；exe（含 launcher 修复）实跑与 dev 同构全链路：向导 → 伴侣 → 管理页 → 测试连接就绪 v1.0.5 → 打开/关闭远程 → 重跑向导 → 服务端模式自起 5098 → 关窗优雅退出 exit 0；desktop_main 入口 + webview/WebView2 DLL + pythonnet 随包实证。

### 已知边界与改进登记（未改码）

- **wait_for_server_ready 不校验应答方身份**：目标端口被其他进程占用且应答时，桌面主窗口会连到他人服务（实测残留兜底实例在 5001 被 dev server 占用时开窗连到 dev server）。历史行为（该函数早于双模式存在），建议后续：uvicorn 绑定失败 fail-fast，或就绪探测带本进程实例标识。

### 测试环境备忘（后续会话）

- 用户自己的 Chrome 长期占用 127.0.0.1:9222 调试端口（自动化勿碰，CDP 客户端须按 Browser=Edg/ 过滤并探测双栈——WebView2 调试端口回环栈不固定，127.0.0.1/[::1] 都出现过）。
- Git Bash 后台 `&` 子进程会随工具调用结束被杀——GUI 进程须用 exec 顶替 shell 由后台任务保活；MSYS `$$` 是 MSYS PID 非 Windows PID（winctl 按标题/PID 枚举要用 Windows 侧）。
- btpManager env 无 pytest/mypy（本会话用 anaconda base python 跑质量门）；已向 btpManager 安装 pywebview~=5.4.0（与 deploy/requirements-windows-package.txt 同锚，desktop_main 顶层 import webview 必需）。
- 测试脚本/日志/截图保留于 .tmp-desktop-gui-test/（未跟踪，可整体删除）；dist/btdeck.exe（46.4MB，2026-08-25 15:32 构建）与 .venv-packaging 为本批构建产物。

### 验证

- pytest：tests/desktop_companion 46 例（44+2 新增）+ tests/architecture/test_packaging_contract 10 例共 56 passed。
- mypy（desktop_companion+tests 10 文件零错）/black（~=24.10、line-length=120）/flake8 全过。
- 根 ./init.sh（ci）通过；5001 dev server 全程未受影响（测试实例全部用独立 CONFIG_DIR+PORT）。
- Git 未提交（待用户指示）；本批代码改动 3 文件 + 三份记录。

## 2026-08-26：Tracker 状态同步健壮性回归加固

### 当前结果

- 复查最近 5 次提交，重点覆盖 `b266a4f` 的 qB enrich 哨兵/客户端 scheme 与重试治理，以及 `2c1d990` 的下载器级 Tracker 硬超时治理。
- 新增回归用例：哨兵 producer 在队列满时重试、全部哨兵丢失时 worker 轮询自愈、enrich 取消后的 producer/worker 清理；补充缓存 qB 客户端真实构造路径的 scheme、`FORCE_SCHEME_FROM_HOST`、`max_retries=0` 与请求超时断言。
- 取消回归发现 producer 在外层取消时仍会进入 30 秒哨兵收尾，已修复为跳过取消收尾并统一回收 producer/worker 子任务；相关业务语义保持不变。
- `feature_list.json` 已将两个回归测试文件纳入 task `.9` 的 files/evidence；路线图仅同步测试覆盖矩阵，模块职责未变。

### 验证

- `tests/api/test_torrents_async_tracker_budget.py`、`tests/services/test_sync_coordinator.py`、`tests/downloader/test_auth_client_timeout.py`：56 passed。
- flake8、mypy（`torrents_async.py`）、py_compile、测试文件 Ruff 格式检查及 `git diff --check` 通过；根 `./init.sh --ci` 已通过。
- 未执行 Git stage/commit/push/deploy；保留用户已有的 `.tmp-desktop-gui-test/` 未跟踪目录。

## 2026-08-26：甲板连接 Logo 视觉重绘

### 当前结果

- 按用户确认的方案，将黑色板面替换为绿色 D 形轨道、三条深色甲板线与连接节点；新增标准、反白、微缩及完整横向锁定组合 SVG/PNG。
- `AppLogo` 支持 `full`/`mark`/`micro` 与 `brand`/`inverse`，桌面侧边栏保留唯一品牌锚点，移除顶栏重复 Logo；桌面/移动登录与移动头部尺寸、底色同步调整。
- favicon、Safari pinned tab 与 PWA/Apple/Android 图标统一为绿色底反白 mark，生成脚本改用反白与微缩资源。

### 验证

- 资源生成与 PNG 视觉检查完成；`npm run typecheck` 通过；AppLogo.spec.ts 与 pwa-manifest.spec.ts 共 12 例通过；改动文件 Vue lint 通过；`npm run build` 通过；根 `./init.sh` 通过（仅保留既有 jq/虚拟环境/npm 警告）。
- 全量 `npm run lint` 仍被既有 `advanced-search-contract` 过期检查拦截，与本批 Logo 改动无关。
- 未执行 Git stage/commit/push/deploy；保留用户已有的 `.tmp-desktop-gui-test/` 未跟踪目录。

## 2026-08-26：手机端 Playwright E2E 测试工具搭建与全路由冒烟

### 当前结果

- 安装 Playwright 浏览器二进制：`chromium-1208`（含 headless shell）与 `webkit-2248`；`@playwright/test@1.58.2` 依赖此前已声明，唯浏览器缺失。
- 新增 `frontend/playwright.config.ts`：双引擎项目（`mobile-webkit` iPhone 12 设备默认 WebKit 模拟 iOS Safari；`mobile-chromium` 同 390×844 视口走 Chromium 快速回归），workers=1 串行、失败自动留 trace/截图。
- 新增 `frontend/tests/e2e/mobile/`：`helpers/auth.ts`（UI 真实登录链路 helper，凭据可经 `E2E_USERNAME`/`E2E_PASSWORD` 覆盖）、`login.spec.ts`（渲染/错误凭据/正确凭据 3 例）、`mobile-routes.spec.ts`（Phase 4 M1-M4 全部 12 条静态 /m/ 路由表驱动冒烟，断言根组件挂载 + 布局壳 + 无 pageerror）、`mobile-interactions.spec.ts`（底部 Tab 切换、抽屉菜单、种子卡片→详情、下载器→设置两条动态参数路由，空数据环境条件跳过）。
- `package.json` 新增 `test:mobile` script；`.gitignore` 增加 `test-results/`、`playwright-report/`；Jest roots 不含 `tests/e2e`（listTests 验证 0 误抓），tsc/tsconfig include 覆盖 e2e 目录类型检查。
- 测试基线环境：后端 5001（anaconda btpManager）+ 前端 8080 dev server（/api 代理 5001）。

### 验证

- 全套 38/38 通过（19 用例 × 双引擎，1.5 分钟）：登录 3、交互 4、静态路由 12。
- `npm run typecheck` 通过；`npx eslint tests/e2e playwright.config.ts` 0 error 0 warning。
- 未执行 Git stage/commit/push；既有未提交的 Logo/M3 批次文件保持原样未动。

## 2026-08-26：BtDeck 效果图 Logo 收口与 App 微型图标

### 当前结果

- 将横版 SVG/PNG 从“03 EXPERIMENTAL / 甲板连接 / 说明文字”收敛为效果图中的 D 形 mark + `BtDeck` 字标，`Bt` 使用品牌绿、`Deck` 使用深色，反白版统一纯白。
- 桌面侧边栏与桌面/移动登录页继续复用完整 `AppLogo`；移动布局头部由标准 `mark` 改为 22px 反白 `micro` 光学版。
- `generate-pwa-icons.py` 新增横版 PNG 生成，并将 Android Chrome、maskable、Apple Touch、Windows tile、PNG favicon 与 ICO 的生成源全部统一为反白微型 mark；SVG favicon/Safari pinned tab 同步加粗微缩笔画。
- 桌面登录页与 390×844 移动登录页已通过应用内浏览器视觉复核，Logo 比例、留白和清晰度正常；PNG 与 192/32px 图标另做原图检查。
- 路线图按 `roadmap-maintain` 同步根增量、AppLogo/登录职责及测试覆盖条目；`feature_list.json` task `brand-logo-2026-08.2` 已更新范围与证据。

### 验证

- `AppLogo.spec.ts`、`pwa-manifest.spec.ts`、`mobile-shell.spec.ts`：3 suites / 37 tests 全绿。
- `npm run typecheck`、改动文件 ESLint、`python -m py_compile scripts/generate-pwa-icons.py`、`npm run build`、`git diff --check`、根 `./init.sh --ci` 通过；生产构建仅保留既有 Sass/包体积/顺序警告。
- 完整 `npm run lint` 仍被既有 `advanced-search-contract` 过期检查拦截，与本批 Logo 改动无关，未擅自重生成契约。
- 已按用户后续指令提交本批改动（`feat(frontend): align logo display and app icons`），未执行 push/deploy；并行任务的 Playwright E2E 工作区变动未纳入本批，`.release-build-v1.0.5/` 与 `data/` 保持原样。

## 2026-08-26：移动端仪表盘全 0 显示修复

### 当前结果

- 用户报告重新部署环境后，移动端 /m/dashboard 数据全显示 0（Network 有正常请求）。实测本机 5001 后端 /api/v1/dashboard 返回完整数据（4 下载器在线、20677 活跃种子、实时速度），排除环境与后端因素。
- 根因：`views/mobile/dashboard.vue`（Phase 4 M1 引入）模板误读 `torrent_stats`/`downloader_stats`/`system_stats`，而契约键为 `torrents`/`downloaders`/`system`（types/dashboard.ts 与 dashboard_service.py 双向核实），`?? 0` 兜底致全 0；速度/页脚因 `formatSpeedValue(undefined)` 显 '-'。该组件此前无任何测试导入，错误从未被 vue-jest 编译暴露。
- 连带两缺陷同修：① 下载器列表 computed 返回 `downloaders` 统计对象（无 length，`v-if` 恒假，区块永不渲染）→ 改 `downloaderList` 取 `downloader_list`；② `formatSpeedValue` 把 bytes/s 当 KB/s（错 1024 倍）→ 删除，新增 `formatSpeedDisplay` 复用桌面 `formatSpeed`（bytes/s，null→'--'、0→'0 B/s'）。
- 实现要点：vue-jest 模板走 buble 不支持 `?.`/`??`（M3 三坑再次实证，修复过程中首次编译即触发 buble 解析错误），字段兜底全部收敛到 `torrentStats`/`downloaderStats`/`systemStats`/`downloaderList` computed，模板仅普通属性访问；桌面端/移动壳/API 层零改动。
- 新增 `tests/unit/mobile-dashboard.spec.ts` 5 用例：卡片按位置精确断言（2/100/3、3/4）、速度换算（286720 B/s→280.00 KB/s，断言不出现 280.00 MB/s）、下载器列表与页脚渲染、源码契约双锁定（禁旧字段名 + 模板块禁 `?.`/`??`）、接口失败走 `$message.error` 留空态。
- feature_list.json `v1.0.6-dual-mode-client.5` evidence 已追加本批记录；docs/roadmap 无 views/mobile 引用，无需同步。

### 验证

- `npm run test:unit -- mobile-dashboard.spec.ts`：5/5 通过。
- `npm run lint` 通过：前置 `contract:check` 曾被行尾差异拦为 stale（工作区遗留，与本次改动无关），`npm run contract:generate` 重写后内容与 HEAD 零差异（仅行尾）；`vue-cli-service lint --fix` 顺手修复 `PullIndicator.vue` 的 `:style` 空格风格（遗留项，与本批无关但保留）。
- `npm run typecheck`（tsc --noEmit）零错误；`npm run build` 生产构建通过。
- 后端 paused 恒为 0 是 dashboard_stats 任务已知限制（暂不统计），不在本批范围；未执行 Git 提交。

### 回归测试加固（2026-08-26 同日追加）

- `mobile-dashboard.spec.ts` 5→10 用例，新增五类保护：① 旧错误契约负例——响应只含 `torrent_stats`/`downloader_stats`/`system_stats` 旧键时卡片必须显示 0、页脚不得出现旧键携带值（对原始 bug 的直接锁死）；② 信封契约——code=500 与 code=200+data:null 均停留空态、不渲染 0 假数据、不误报 `$message.error`；③ 刷新链路——`.m-refresh` 按钮 click 与下拉刷新 `onPullRefresh` 均重新拉取并渲染新值（1.50 MB/s）；④ `formatSpeedDisplay` 方法契约（`--`/`0 B/s`/`1.00 KB/s`/`280.00 KB/s`/`1.50 MB/s`）；⑤ computed 兜底（data 空时 `downloaderList=[]`、统计归零、`version`/`uptime_display='-'`）。
- 变异验证实证保护有效：临时把 `torrentStats` 改回读 `torrent_stats` → 3 用例红；把 `downloaderList` 改回 `downloaders` 统计对象 → 列表用例红；还原后 10/10 全绿。
- 验证：单套件 10/10、lint 通过、tsc 零错误；未执行 Git 提交。

## 2026-08-26：移动通知内容渲染与 Web 端一致

### 当前结果

- 用户要求：移动端通知页对通知内容的文本渲染需与 Web 端一致。此前移动页 `{{ n.content }}` 原样输出（Markdown 记号裸露、无详情视图），而桌面是"列表纯文本摘要（三行截断）+ 点击详情弹窗按 Markdown-lite 渲染（含失败明细与 Release 链接）"。
- 渲染逻辑抽共享：`NotificationDrawer/index.vue` `detailHtml` getter 的转换逻辑（#/##/### 标题、`---` 分隔线、`- ` 列表、段落分块，输入先 HTML 转义，结构化输出上替换 `**粗体**`/`` `行内代码` ``）与失败明细目标回退链，逐行搬移至新文件 `utils/notification-markdown.ts`（`renderNotificationContent`/`notificationFailureTarget`）；桌面详情弹窗改为委托调用，行为零变化，两端从此单一渲染源（代码复用约束，杜绝复制粘贴漂移）。
- `views/mobile/notifications.vue` 升级：列表摘要改纯文本三行截断（`-webkit-line-clamp:3`，对齐桌面 `NotificationItem`）；新增详情弹层（el-dialog `append-to-body` 92% 宽，`m-notification-detail-dialog`）——标题+关闭头、类型标签+时间 meta、`v-html` 同源渲染、失败明细（`extra_data.failed_list`）、Release 外链（`extra_data.release_url`）；点击卡片打开详情并保留"查看即已读 + 角标联动"语义（与桌面 `handleView` 一致）；v-html 产物无 scoped 标记，弹层样式非 scoped 且按类名收口，排版参数对齐桌面 `.notification-detail-dialog`。
- roadmap：`docs/roadmap/frontend/components-layout/README.md` 通知抽屉行补共享 util 与移动端共用事实（roadmap 未覆盖 views/mobile，无其他漂移）。

### 验证

- 新增 `tests/unit/notification-markdown.spec.ts` 13 例全过（分块结构、转义防注入、内联替换、列表闭合、失败目标回退链）。
- 相关回归 `mobile-shell.spec.ts` + `api-contracts.spec.ts` 61 例全绿；`tsc --noEmit` 零错误；改动 4 文件 ESLint（`--max-warnings 0`）通过；`npm run build` 生产构建通过。
- feature_list.json `v1.0.6-dual-mode-client.5` evidence 已追加本批记录；未执行 Git 提交（遵循仅用户要求时提交）。

### 回归测试加固（2026-08-26 通知渲染批次追加）

- 按用户要求为"移动通知内容渲染与 Web 端一致"修改补三层回归保护：
  - **util 层**：`notification-markdown.spec.ts` 13→22 例——CRLF 行尾、`&` 转义（防实体注入）、纯空白行、标题/空行打断列表不复用同一 ul、内联替换覆盖列表项与标题节点、未配对 `**`/`` ` `` 字面量、连续 hr。
  - **移动组件层**：新增 `mobile-notifications.spec.ts` 12 例——列表契约、摘要纯文本（渲染只发生在详情）、点击未读（markAsRead + FetchUnreadCount 角标联动 + 就地置已读）、已读不重复标记、详情同源渲染（h3/li/strong/code/hr 无记号残留）、失败明细回退链、Release 外链、类型标签、markAsRead 失败路径、信封契约、双刷新链路、源码契约（共享渲染函数必须引用、禁 v-html 直塞原始 content、禁私有实现回流、三行截断存在、弹层类名收口、模板禁 ?./??）。
  - **Web 委托层**：新增 `notification-drawer-detail.spec.ts` 7 例——handleView 未读自动已读、已读不重复、失败明细/外链、关闭清空、源码契约（委托调用必须存在 + 抽取前内联转换三重禁入）、未读数 60s 轮询启停（fake timers）。
- **变异验证**三组全部精确拦截：移动回退裸文本→同源渲染用例红；删三行截断→源码契约红；Web 绕过共享 util→渲染用例+源码契约双红；还原后三套件 39 例全绿。
- 全量复验：**81 套件 1108 例全绿**；tsc 零错误；三 spec ESLint `--max-warnings 0` 通过（过程修正：多行类型分隔符须分号、去 `!` 非空断言）。
- test-coverage 矩阵修复历史漂移：unit 表 48→69 行补齐（mobile-* 14 个等历史缺失 + 本批 2 个新增），行数与目录实测对齐；未执行 Git 提交。

## 2026-08-26：移动简单搜索迁入种子页与高级搜索模板同源显示

### 当前结果

- 用户报告两项：①希望把移动端高级搜索里的简单搜索迁移到种子页面；②移动端高级搜索没有显示 Web 端保存的高级搜索模板。
- **简单搜索迁移**：`views/mobile/search.vue` 删除「简单查询/高级搜索」双模式（变纯高级搜索页）；`views/mobile/torrents.vue` 新增可折叠筛选面板——名称关键词、下载器多选、状态多选、Tracker 域多选（allow-create），与桌面 torrents 快捷筛选同字段集，四字段透传 `name_like/downloader_id/status/tracker_domain` 到 getList；原单一状态下拉被状态多选取代；空态区分「暂无种子/没有匹配的种子」；下拉刷新带当前筛选重载。修复过程中发现并纠正自身引入的缺陷：mounted 去掉默认 reload 后无模板时列表不加载，已改为 applyPendingTemplate 无 pending 时兜底 reload。
- **模板同源显示**：search.vue 由直接嵌 `AdvancedSearchBuilder` 升级为复用桌面 `AdvancedSearchWorkspace`——左侧「已保存搜索」列表与 Web 端同源（`getSearchTemplates({is_public:true})` 过滤 source=advanced），选择回填、新建、保存更改、删除全量对齐桌面；组件自带 ≤900px 媒体查询在 390px 视口自动上下堆叠；页面删除自身重复的 save-template/createSearchTemplate 接线（工作区内部完成）；下拉刷新改为未搜索时 `refreshFieldOptions`（刷新字段候选+模板列表）、已搜索经 `workspace.onSearch` 重放。
- **模板应用分流**：`query-templates.vue`「应用」按 `conditions.source` 分流——简单模板跳 `/m/torrents`（回填筛选+执行），高级模板跳 `/m/search`（回填工作区+FromTemplateGroups 构建+执行）；两执行页 mounted 遇来源不符的模板交回 m2 缓存并互转对端页，防缓存被错误消费。查询模板页脚注同步（高级模板可在移动高级搜索页新建/编辑）。
- roadmap：test-coverage.md unit 表 69→70 并更新 mobile-search/mobile-query-templates 描述、新增 mobile-torrents 行（roadmap 不覆盖 views/mobile 本体，无其他漂移）。

### 验证

- `mobile-search.spec.ts` 重写 8 用例（工作区 search 事件→POST、空态、详情跳转、advanced 模板回填执行、simple 模板转种子页、下拉刷新两态、源码契约禁简单搜索回流）；新增 `mobile-torrents.spec.ts` 10 用例（初始加载、选项加载、面板展开、四字段透传、重置、双向模板分流、空态区分、下拉刷新带条件、加载更多 skip 递增、源码契约）；`mobile-query-templates.spec.ts` 应用断言改双分流。三套件 24 用例全绿。
- 前端全量 **82 套件 1119 passed**；`tsc --noEmit` 零错误；改动文件 ESLint `--max-warnings 0` 通过；`npm run lint`（含 advanced-search 契约检查）通过；`npm run build` 生产构建通过；根 `./init.sh` 通过。
- Chrome 390×844 浏览器实测（dev server + 本机 5001 后端）：种子页筛选面板展开与关键词「Grand.Blue」过滤 20/22 全命中；/m/search 侧栏显示系统「大文件」模板及临时创建的个人高级模板；查询模板页应用高级模板自动跳 /m/search、构建器回填「种子名称/包含/Grand.Blue」并执行出 22 条结果；应用简单模板跳 /m/torrents 并显示「已应用模板」提示（临时模板已删除清理）。
- 浏览器会话备注：IAB 标签页长时间使用后出现点击派发失灵（fill/快照正常但 el-button 点击无效），换新标签页后全部恢复正常——判断为宿主环境状态问题而非代码缺陷（同页面同按钮新标签页可点）。
- feature_list.json `v1.0.6-dual-mode-client.5` evidence 已追加本批记录；未执行 Git 提交（遵循仅用户要求时提交）。

## 2026-08-26：移动种子页多选筛选不生效根因修复（数组参数序列化契约断裂）

### 根因分析（按用户要求做多假设深挖验证）

- 现象：种子页筛选面板中名称关键词生效，但下载器/状态/Tracker 域三个多选筛选全部"不生效"（结果不变）。
- 假设排序与验证过程：
  - H1 选择后未点搜索按钮（交互落差）——被降级：即使点了搜索，参数也到不了后端（见 H3）；名称有回车即搜路径与现象吻合是巧合，非根因。
  - H2 el-select 弹层被遮挡/选不上——排除：用户报告口径是"没生效"而非"选不上"；本会话 IAB 浏览器弹层 hidden 判定为环境输入派发噪音（同环境按钮/卡片多次点击失灵，换标签页恢复），无代码层证据。
  - H3 **数组参数序列化契约断裂（根因，实锤）**：后端 `/torrents/getList` 的 `downloader_id/status/tracker_domain` 均为 `Optional[str]`（逗号分隔字符串契约，torrent_crud.py:609-629）；前端 request.ts 无自定义 paramsSerializer，axios 默认把数组序列化为 `key[]=v` 形式——参数名带方括号与后端完全不匹配，被 FastAPI 静默忽略。桌面端 index.vue 在调用前有专门的 `join(',')` 归一化（index.vue:1205-1218）所以一直正常；旧移动 search.vue 简单查询与迁移后的 torrents.vue 都直接传数组——**该 bug 自 Phase 4 M2 旧简单查询页即存在，迁移时原样继承**。上一批浏览器实测只验证了名称关键词（纯字符串路径），恰好绕过数组路径——实测盲区。单测同样 mock 了 api 模块只断言参数对象形态，覆盖不到序列化层。
  - H4 状态枚举值错配（项目有大小写先例）——排除：TORRENT_STATUS_OPTIONS 值与后端一致，且错配症状应为"结果变空"而非"结果不变"。
  - H5 v-model 响应式断裂——排除：标准 data 声明，选择值正常进入 filters（curl 实验也证明问题在序列化层而非取值层）。
- **curl 决定性实证**（本机 5001 后端，22396 基线）：`status=paused` → total=60（过滤生效）；`status[]=paused` → total=22396（被忽略，精确复现用户现象）；`downloader_id=<uuid>` → 886 vs 方括号 → 22396；`tracker_domain=1ptba.com` → 171 vs 方括号 → 22396。

### 修复

- 契约收敛在 API 层：`api/torrents.ts` 新增 `normalizeTorrentListArrayParams`——`getTorrentList` 内把 `downloader_id/status/tracker_domain` 数组归一化为 `join(',')` 字符串、空数组剔除该键，与 `TorrentListParams` 类型 `string | string[]` 的既有声明承诺对齐；桌面 index.vue 已有 join 成为无害冗余（未动，最小变更）。一次修复覆盖当前与未来所有调用方（移动种子页/详情回查/传统视图等）。
- 回归：`api-contracts.spec.ts` 新增 2 用例（多选数组 join 逗号契约 + 空数组剔除/字符串原样透传），锁死序列化层防回流。
- 前端全量 82 套件 **1121 passed**（+2）；tsc 零错误；ESLint 与 `npm run lint`（含契约检查）、`npm run build` 通过。

### 遗留与备注

- feature_list.json `v1.0.6-dual-mode-client.5` evidence 已追加本批记录；未执行 Git 提交。
- 备忘：el-select 下拉在 ZCode IAB 环境存在输入派发不稳定（弹层 double-toggle 假象），移动端 UI 交互验证建议优先真机/Chrome 设备模拟手动复核。

### 回归测试加固（2026-08-26 移动筛选批次追加）

- 按用户要求为本次对话全部修改（简单搜索迁移 + workspace 模板同源 + m2 分流 + 数组序列化根因修复）补足三层回归，四套件 55→76 用例：
  - **mobile-torrents.spec 10→18**：新增 8 例——筛选选项加载失败静默（不弹错不阻塞列表）、getList 网络异常（$message.error + 空态 + loading 复位）、getList 信封非 200（不渲染假数据不误报）、筛选生效后加载更多（二次请求仍带条件 + skip 按过滤后列表递增）、工具栏筛选计数徽标（四类计数与重置清零）、advanced 模板转发不触发本页 getList、simple 模板 trackerDomains 恒空（防串味）、严格索引访问修正。
  - **mobile-search.spec 8→13**：新增 5 例——advancedSearch 信封非 200（提示后端 msg、searched/searching 状态不受污染）、网络异常（提示 + searching 复位）、工作区 reset 清空结果态、advanced 模板无效条件组（空 conditions 触发 buildAdvancedSearchRequestFromTemplateGroups 校验链，提示「模板条件组1没有条件」且不发起 POST）、rerunAdvanced 无 workspace ref 静默防御。
  - **api-contracts.spec +3**：数组归一化不修改调用方传入对象（浅拷贝契约，保护桌面 listQuery 拷贝与移动 filters 不感知形态变化）、无参调用 params undefined 不抛错、（此前已有 join 逗号契约与空数组剔除）。
- **变异验证四组全部精确拦截**：①删 normalize 直传数组 → 2 红（join 契约 + 空数组剔除）；②归一化去浅拷贝直接 mutate → 1 红（不可变用例）；③torrents.vue 移除 tracker_domain 透传 → 2 红（四字段透传 + 源码契约）；④advanced 转发分支误触发 reload → 1 红（不误刷用例）；⑤search.vue simple 模板不转发 → 1 红；⑥query-templates 分流回退统一跳搜索页 → 1 红。还原后全绿。
- 过程事故与处置：变异脚本 str.replace 全局替换误伤 torrents.ts 另外三处 `params: params`（enabled 参数/search-templates/backup list），导致套件编译失败；按 url 上下文精确还原并经 git diff 核对差异恰好只剩预期归一化函数后重做变异（改用唯一锚点断言 count==1），后续变异脚本均带唯一性断言。
- 全量复验：**82 套件 1135 例全绿**（较上批 +14）；tsc 零错误；三 spec ESLint `--max-warnings 0` 通过；`npm run lint`、`npm run build` 通过；未执行 Git 提交。

## 2026-08-27：移动通知列表预览裸露 Markdown 记号修复

### 根因

- 用户报告：移动端通知页面在未打开详情前，列表预览摘要仍显示 `##` 等渲染字符。
- 定位：`views/mobile/notifications.vue` 列表摘要 `{{ n.content }}` 纯文本直出原始 Markdown（2026-08-26 cb6890d 批次只对齐了详情弹层渲染，摘要按"纯文本+三行截断"设计保留，记号裸露成为遗留缺口）；桌面 `NotificationDrawer/NotificationItem.vue` 摘要同病（`{{ notification.content }}`）。
- 方案（AskUserQuestion 确认）：摘要剥离 Markdown 记号为纯文本（不渲染 HTML，保留三行截断与纯文本插值的安全面）；范围移动+桌面一起修，共享 util 单一实现。

### 修复

- `utils/notification-markdown.ts` 新增 `plainNotificationContent`：块级记号逐行剥离（`#`/`##`/`###` 标题前缀、`- ` 列表标记；空行与 `---` 分隔线整行丢弃），片段单空格合并后内联去 `**粗体**` 与 `` `行内代码` `` 记号；不做 HTML 转义（摘要走纯文本插值，转义由框架负责，与 renderNotificationContent 职责边界明确）。语法集合与渲染函数保持一致。
- `views/mobile/notifications.vue`：新增 `summaryText(n)` 方法委托共享函数，摘要插值与 v-if 判空均用剥离后文本；样式注释同步。
- `NotificationDrawer/NotificationItem.vue`：新增 `plainContent` computed 委托共享函数，摘要插值与 v-if 判空同改——两端列表摘要从此同源。

### 验证

- 测试三层 51 例全绿：util `notification-markdown.spec` 22→31 例（标题/列表剥离、分隔线与空行丢弃、内联记号覆盖全部片段、输出不含 HTML 转义职责、CRLF、未配对记号字面量、trim/缩进）；`mobile-notifications.spec` 摘要契约反转（原"记号原样可见"用例改为"记号剥离正文保留"）+ 源码契约禁 `{{ n.content }}` 直塞；`notification-drawer-detail.spec` 7→10 例，新增 NotificationItem describe（摘要剥离断言、剥离后空不渲染摘要块、源码契约禁模板直塞原始 content）。
- `tsc --noEmit` 零错误；改动 6 文件 ESLint 通过；前端全量 **82 套件 1147 例全绿**（较上批 +12，恰为本批新增用例数）；`npm run lint`（含 contract:check/vuex-action 检查）通过（contract stale 为已知行尾假警报：generator 重写后与 HEAD 内容零差异，已恢复）；`npm run build` 生产构建通过；根 `./init.sh`（ci 模式）通过。
- 过程踩坑：spec 块注释中书写 `（##/- **/`/---）` 时 `**/` 恰构成 `*/` 提前终止块注释，后续反引号被解析为模板字符串边界导致整个套件 TS2304——块注释内避免 `**/` 序列（已改中文顿号措辞）。
- roadmap 同步：`docs/roadmap/frontend/components-layout/README.md` 通知项行补摘要纯文本化；`docs/roadmap/perspectives/test-coverage.md` 三行描述更新（notification-drawer-detail/notification-markdown ✨2026-08-27）。
- feature_list.json `v1.0.6-dual-mode-client.5` evidence 已追加本批记录；未执行 Git 提交（遵循仅用户要求时提交）。

### 回归测试加固（2026-08-27 通知摘要批次追加）

- 按用户要求为"通知列表摘要剥离 Markdown 记号"修改补足回归保护，三套件 51→62 例：
  - **util 层** `notification-markdown.spec` 31→37：新增语法严格性（`#`/`##`/`###`/`-` 后无空格不视为块级记号原样保留）、语法集交叉契约（renderNotificationContent 可识别的每种块级前缀在摘要中不残留记号字符，逐前缀精确值锁定）、完整版本更新通知端到端快照（摘要全文精确匹配）、跨行配对内联记号合并语义（行级剥离→单空格连接→内联替换，`**第一行\n第二行**`→`第一行 第二行`）、连续分隔线与空行交错全部丢弃且片段间恒单空格。
  - **移动组件层** `mobile-notifications.spec` 12→15：新增摘要与详情双层分离契约（同一条通知摘要精确全文 `'v1.0.6 更新 新增：查询模板管理 优化 docker compose 部署 详情见 Release'` + 点击后详情完整 h3/strong/code 渲染，锁死两层各走各的共享函数）；剥离后无可见文本的通知（content 仅分隔线/空行）不渲染摘要块（v-if 判空路径）；summaryText 纯函数契约（不修改通知原始 content，详情渲染源不被摘要污染）。
  - **桌面组件层** `notification-drawer-detail.spec` 10→13：新增摘要全文精确匹配、content 空串不渲染摘要块、notification prop 更新时摘要响应式重算（setProps 后 computed 依赖跟踪）。
- **变异验证四组全部精确拦截**（备份-变异-恢复方式，本批源码未提交不可 git checkout 还原；变异脚本锚点带唯一性断言）：①移动 summaryText 回退 `return n.content` → 5 红；②桌面 plainContent 回退 `return this.notification.content` → 5 红；③util 删分隔线丢弃分支 → 三层 7 红（含两端空摘要块用例，跨层拦截实证）；④util 删粗体内联替换 → 8 红。还原后 62 例全绿。
- 变异过程踩坑：锚点含行尾 `\n` 时因源文件 CRLF 行尾匹配失败（ANCHOR NOT UNIQUE 防线拦截），改用不含行尾的行内锚点重试——后续变异脚本锚点避免跨行尾。
- 还原完整性复核：源码 3 文件 git status 与变异前一致；tsc 零错误；三 spec ESLint 通过。
- 全量复验：**82 套件 1158 例全绿**（较加固前 +11）；feature_list.json evidence 与 session-handoff.md 已追加加固记录；roadmap test-coverage util 行补语法严格性要点。未执行 Git 提交。

## 2026-08-27：移动端搜索收敛与系统设置移动化（三项调整）

- 用户要求移动端三项调整：①高级搜索与查询模板仅保留高级搜索；②高级搜索条件组做移动端适配；③系统设置增加移动页适配。
- **①裁撤移动查询模板页**：`/m/search` 已整页复用桌面 `AdvancedSearchWorkspace`（左侧已保存搜索与 Web 端同源，新建/保存更改/删除全量对齐），独立模板页成冗余——删除 `views/mobile/query-templates.vue` 与 `m2-template-cache.ts`（唯一写入方消失后跨页缓存链路成死代码），种子页/搜索页 `applyPendingTemplate` 回填逻辑移除；`/m/query-templates` 路由保留深链 redirect 至 `/m/search`，`toMobilePath('/query-templates')` 同步改落 `/m/search`，抽屉菜单移除「查询模板」项；构建产物 `m-query-templates` chunk 消失、`m-search` 保留实证。
- **②条件组移动适配**（共享组件，桌面零回归）：`AdvancedSearchBuilder.vue` 内联定宽全部类化（组名输入 120px/组内逻辑 100px/字段 140px/操作符 120px/组间逻辑 100px，桌面值不变），768px 断点强化——选择器铺满整行（原断点只把容器拉满、内联宽度穿透导致 140px 小控件残留）、组头换行、组内逻辑说明折行下移、AND/OR 悬浮标签经 `:not(:first-child)` padding-top 避让铺满后的字段选择器、组间逻辑卡片通栏、操作按钮纵向铺满；预览/保存模板对话框（append-to-body）加 `advanced-search-dialog` 全局块窄屏 94% 压宽（内联 width 须 !important 覆盖）；`ConditionValueInput.vue` 日期范围 2×180px 类化为 `range-date-picker`，窄屏 flex:1 弹性对分（修 375px 视口横向溢出，桌面 180px 不变）。
- **③新增 `/m/settings`**：`views/mobile/settings.vue` 整页复用桌面 `views/settings/index.vue`（参照 downloader-settings 先例，2FA 全状态机 + 改密零重复实现），`::v-deep` 剥离桌面外层留白；桌面设置页改密成功跳转 `loginPathForMode()`（桌面行为不变，移动回 `/m/login`）；守卫 `forceChangeTargetPath()` 按模式选落点（移动 `/m/settings`/桌面 `/settings/index`）+ `forceChangeAllowedPaths` 增补 `/m/settings`（防重定向循环）；`uiModeRedirectPath` 移动分支收编 `/settings`、桌面分支补 `/m/settings→/settings`；`toMobilePath` 增 `/settings` 映射；抽屉移动组加「系统设置」（11 项）、桌面组移除（余 2 项）。
- 测试：删 `mobile-query-templates.spec`（-5 例）；`mobile-search.spec` 13→10（移除模板应用例，源码契约加 m2 禁回流）；`mobile-torrents.spec` 移除 4 模板例 + 契约禁回流；`mobile-shell.spec` 菜单 14→13 项断言；`ui-mode.spec` +1（settings 映射 + 兜底改写）；`permission-force-change-deadlock.spec` 7→8（新增移动模式真实路由拦截落 `/m/settings` 用例，需 stub `layout/mobile` 与 `mobile/dashboard` 防 jsdom API 副作用）；新增 `mobile-settings.spec` 3 例；e2e `mobile-routes.spec` 路由全集换入 settings。
- 验证：全量 **82 套件 1151 例全绿**（首跑 1 套件 worker 偶发崩溃，复跑两轮均全绿）；`tsc --noEmit` 零错误；`npm run lint`（契约检查+ESLint+vuex 门）通过——契约 stale 为已知行尾假警报，重生成后与 HEAD 内容零差异仅 LF 归一化（保留生成版本使 check 通过）；`npm run build` 通过（m-settings chunk 实证）；根 `./init.sh`（ci）通过。
- roadmap 同步：entry 分支路由表/守卫行号全量重测（原表漂移至 349 行旧版，现 452 行），components-layout 分支 Builder/Workspace/ConditionValueInput 条目更新，根 README 元信息加 2026-08-27 增量行。feature_list.json `.5` evidence 追加；未执行 Git 提交。

## 2026-08-27：Tracker 域名筛选命中可视化（matched_domain 标记 + 高亮 + 观察日志）

- **根因（双独立子代理验证）**：`torrent_domain` 筛选是 EXISTS/ANY 语义——种子任一 tracker 命中所选域名即整行返回（辅种一籽挂多站 tracker 属常态），而返回行 `tracker_info` 携带全部 tracker 且无命中标记，Tracker 详情平铺造成「搜出与所选域名不同」的观感；SQL 锚定本身严格（子串/子域误匹配经内存库动态实验排除）。
- **后端**：`trackerVO.py` TrackerInfoVO 新增 `matched_domain`（default None，duplicate/advanced_search 复用路径零改动兼容）；`torrent_helpers.py` 域名归一前移到 `get_torrent_infos` 入口（过滤闭包与 VO 标记共用一份，防口径漂移），新增 `tracker_row_matches_domains` Python 谓词与 SQL 8 条件同口径（注释互指 + 回归测试锁定），`convert_to_vo(s)_with_trackers` 新增可选参数 `requested_tracker_domains` 计算 matched；同批修复 tracker_like 空结果静默返回全部（改 `filter(false())` 返回空）与 like 未转义（`_escape_like_literal` + `escape="\\"`，`_`/`%` 字面量化，语义收紧属预期）。
- **观察日志**：后端 `logger.debug` 四锚点——`[tracker-domain-filter]` 原始输入/归一域名、本页命中行数/标记数汇总，`[tracker-filter]` 关键字命中 tracker 行数，`[torrent-list]` total/本页/筛选参数；`LOG_LEVEL=DEBUG` 开启（默认 INFO）。前端两视图 `getList` 成功后 `console.debug('[tracker-filter] total/本页/命中标记行')`，统计走共享纯函数 `countMatchedTrackerRows`（torrentBatch.ts）。
- **前端**：`torrents.ts` TrackerInfo 加 `matchedDomain/matched_domain` 双读字段；`TrackerDetailCard.vue` 命中行 `tracker-row-matched` 高亮 + 名称旁「命中筛选」标签（tooltip 显示命中域名），样式进共享 `_tracker-table.scss`（sticky 操作列同色跟随、hover 让位）；查询模板缺口修复——`QueryTemplateConditions['listQuery']` 加 `tracker_domain?: string[]`、`QueryTemplateDialog` simple 表单加 AdvancedMultiSelect 域名多选（options 懒加载 getTrackerDomains、编辑回填、buildConditions 写入）、`saveSimpleQueryAsTemplate` 同步透传；还原端两视图本就兼容未动。
- **测试**：后端 `test_torrent_list_api.py` 40 passed（新增 ANY+标记/多选标记/未筛选不标记/下划线字面量 4 例；改写 tracker_like 空结果 1 例为新语义）；关联面 duplicates+advanced_search 50 passed；全量 4052 passed / 7 skipped。前端 tracker-detail-card +1、torrent-batch +2、api-contracts +1；全量 82 suites / 1155 passed。
- **质量门**：black（改动文件）/flake8/mypy 通过（app/ 存量未格式化 `tracker_sync_task.py` 非本次引入未动）；`tsc --noEmit` 零错误；`npm run lint` 通过；根 `./init.sh`（ci）通过。roadmap 同步 torrent_crud 三层 md 与前端 views/components 分支条目。未执行 Git 提交。

## 2026-08-27：移动端回收站 info_id 契约修复（自查缺陷，双子代理独立审查修订后执行）

- **缺陷（两串联确定性缺陷，诊断实证）**：移动端回收站恢复/彻底删除把 `item.torrent_id`（40 位 InfoHash）当批量接口 ID 传，后端服务层（recycle_bin_service.py L207/L641）实际按 `TorrentInfo.info_id`（UUID 主键）查询，查不到即 failed `reason: "种子不存在"`；前端又误读 `failed_list[0].error`（后端键恒为 `reason`）致「未知原因」兜底。桌面端一直正确传 `info_id`。请求字段名 `torrent_ids` 与循环变量同名的命名歧义是系统性成因（后端 42 处/9 文件，含 advanced_search 批删等语义不一，更名属破坏性变更另行立项）。
- **双子代理独立审查推翻原方案三处硬伤**：①spec 用例 6（无 torrent_id 直接返回）在守卫改 `!item.info_id` 后必红（item2 `info_id:'i2'` 为 truthy 守卫放行）——须连锁改造该用例；②后端 cleanup 成功用例审计坑——真实 AuditLogService 在测试同步 Session 上 `await commit()` 抛 TypeError 被服务层外层吞成假失败「清理异常」，须 `dependency_overrides[get_audit_service] = lambda: None`；③feature_list.json 语法修复是两处（L94 残留 `}` + L93 尾逗号，只删 L94 仍非法），且损坏源于工作区未提交的 brand-logo-2026-08.3 删除残留。审查另确认：failed 键全后端统一 `reason` 无 `error`、移动端列表数据含 `info_id` 无缺口、其他移动端视图无同类混淆。
- **前端修复（子代理 A，3 文件）**：`mobile/recycle-bin.vue` 恢复/彻底删除守卫与载荷统一改 `item.info_id`（`as string` 断言随之消失），失败提示恢复/删除两分支均展示 `failed_list[0].reason`（审查采纳扩项，与删除对称），彻底删除按钮禁用去掉 `|| !item.torrent_id`（同根缺陷：manual_cleanup 全程不用 torrent_id，无 InfoHash 记录此前被永久禁止彻底删除）；`api/recycle-bin.ts` failed_list 项类型改 `{torrent_id; torrent_name?; reason}`（「种子不存在/清理异常」条目无 torrent_name 故可选）、success_list 项 `name→torrent_name`（后端恒提供，全仓零消费方）；`mobile-recycle-bin.spec` 7→9 例——载荷断言 `['t1']→['i1']`（fixture info_id/torrent_id 值可区分构成契约锁）、用例 6 改「无 info_id 直接返回」语义、新增删除/恢复失败 reason 展示 2 例。
- **后端契约测试（子代理 B，源码零改动）**：`test_recycle_bin_api.py` 新增 `TestBatchPayloadRequiresInfoId` 2 例（HTTP 级，`make_torrent` 造 `info_id="i1"/torrent_id="t1"` 两列不同行）——restore/cleanup 传 torrent_id 值 → `failed_count==1` + `reason=="种子不存在"` 且无 `error` 键；cleanup 传 info_id → `success_count==1`（get_audit_service 依赖 override None 规避审计假失败，try/finally 清理）。info_id 成功路径由既有 service 级测试覆盖（docstring 注明）。
- **验证**：前端 `npm run test:unit -- tests/unit/mobile-recycle-bin.spec.ts` 9/9 全绿；定向 ESLint `--no-fix --max-warnings 0` 通过；`tsc --noEmit` 零错误；grep 确认回收站 failed_list 无 `.error` 残留。后端 `pytest tests/api/test_recycle_bin_api.py` 16 passed（14 旧 + 2 新）；black(24.10.0)/flake8 通过。根 `./init.sh`（ci）通过。
- **已知错位登记（待后续 UI 语义决策）**：恢复按钮禁用与 L37 文案按 torrent_id 有无判定，与后端 `can_restore`（备份文件存在性）判据错位——torrent_id 在但备份丢→可点击但失败（修复后会显示真实 reason）；torrent_id 缺但备份在→误显「无法恢复」。`/restore-manual`（现 501 stub）未来实现时应接受 info_id 且 UI 自动带出。
- 顺带修复 feature_list.json L93/L94 语法错误（完成 brand-logo-2026-08.3 删除意图，json.tool 校验合法）；`.5` evidence 追加本批并补 files；roadmap test-coverage mobile-recycle-bin 行更新。未执行 Git 提交。

## 2026-08-27：移动端回收站 info_id 契约修复·回归加固（三层 + 变异验证）

- 按用户要求为上一批修复补足回归保护，前端 9→13 例 + api-contracts 新增 describe，后端 2→4 例，变异验证 10 组全部精确拦截。
- **前端组件层**（`mobile-recycle-bin.spec`）：fixture 改造堵变异盲区——item2 改为 `torrent_id:'t2'` 且无 info_id（原两 ID 皆缺，守卫改回 `!item.torrent_id` 不会红）、新增 item3（info_id 在/torrent_id 缺）专测按钮态；新增按钮禁用态契约（缺 torrent_id 仅禁恢复并显「无法恢复」、彻底删除可用——锁 L43 修复；busyKey 期间双禁用+复位）、reason 缺失兜底「未知原因」、destroy reject 走 extractErrorMessage 且 busyKey 复位、源码契约用例（两处 `[item.info_id]` 载荷/两处 `!item.info_id` 守卫/两处 `.reason`/按行级 disabled 表达式区分两按钮——恢复含 `|| !item.torrent_id` 是有意保留的现有语义）。
- **前端类型契约层**（`api-contracts.spec` 新增 describe）：readFileSync 锁 `api/recycle-bin.ts` failed_list 项 `reason: string`+`torrent_name?: string`、禁 `error`/`name` 回流；success_list 项 `torrent_name: string`；请求字段 `torrent_ids` 不变式。
- **后端契约层**（`TestBatchPayloadRequiresInfoId` 2→4 例）：失败项键集升级精确相等 `{torrent_id, reason}`；新增 cleanup 成功项契约（`success_list` 键集 `{torrent_id, torrent_name}` 且 torrent_name 值锁）与混合批量 `['i1','t1']` 逐项独立判定 + failed 回显收到的值。
- **变异验证 10 组全部拦截**（python 定点变异，锚点唯一性预断言、不含行尾，备份-变异-红-还原-cmp 字节校验）：前端 M1 恢复载荷回退→载荷用例+源码契约红；M2 删除载荷回退→同上；M3 `.reason`→`.error`→删除 reason 用例+源码契约红；M4 恢复提示去 reason 尾段→恢复 reason 用例红；M5 彻底删除禁用加回 `|| !item.torrent_id`→按钮态+源码契约红；M6 守卫改回 `!item.torrent_id`→item2 穿透守卫用例红；M7 类型 `reason`→`error`→api-contracts 用例红。后端 M8 restore 查询 `info_id`→`torrent_id`→契约用例+既有 service 级用例双红；M9 cleanup 查询同样变异→cleanup 三用例红；M10 L211 `reason` 键→`error`→精确键集断言红。还原后 `backend/app/` 与前端源码零残留（git diff + cmp 双核实）。
- **验证**：前端定向 57 例 + 全量 **84 套件 1178 例全绿**、`tsc --noEmit` 零错误、两 spec 定向 ESLint `--max-warnings 0` 通过；后端 `pytest tests/api/test_recycle_bin_api.py` **18 passed**、black/flake8 通过；根 `./init.sh`（ci）通过。未执行 Git 提交。

## 2026-08-27：等级3删除文件缺失容错（无可操作文件 → 提醒+跳过文件操作+直接入回收站）

- **需求**：种子列表等级3（回收站）删除时，若没有可操作的文件，提醒用户并跳过文件操作，直接把种子数据加入回收站。
- **根因链**：文件缺失时 `_move_torrent_files_for_recycle` 单/多文件分支均 `return success=False`（「单文件不存在」/「原文件夹不存在」）→ `_delete_level3` 回滚数据库软删除 + 删标记文件 → 整体失败，种子永远进不了回收站。且两分支的幂等检测（already_moved）写在「原路径存在」检查之后，属不可达死代码——上次已移动过的重试同样必失败。
- **后端（torrent_deletion_by_level.py）**：`_move_torrent_files_for_recycle` 原路径不存在时先查 `.pending_delete` 目标——存在 → 幂等跳过（`already_moved=True`，顺带修复不可达缺陷，多文件智能合并块同步清理）；不存在 → `file_missing=True` 跳过（单/多文件两分支对称，返回均带 `skipped/already_moved/file_missing`）。`_delete_level3` 对 file_missing 记 warning 日志、审计 `operation_detail` 落 `torrent_moved=False/file_missing=True/skip_reason=file_missing`、返回 `file_missing/torrent_name` 与提醒 message（「未找到种子文件，已跳过文件操作，仅将种子移入回收站」）；辅种数量照常扣减。`delete_batch_by_level` 收集 `level3_file_missing: [{torrent_id, torrent_name}]`。
- **API（torrent_deletion.py）**：同步 `delete-with-level` 成功/部分失败两分支 data 透出 `level3_file_missing`，msg 拼接「N个种子未找到文件，已跳过文件操作直接移入回收站」。异步链路 `results` 已含每种子 result（file_missing 字段随 `success_items` 自然透出），无需改动。
- **前端**：`utils/torrentBatch.ts` 两解析器新增 `fileMissingDetail`——`parseSyncDeleteResponse` 读 `level3_file_missing`、`parseDeleteTaskResult` 从异步 `results` 提取 `result.file_missing`（新增 `extractFileMissingFromResults`/`buildFileMissingDetail` 纯函数，前5名+「等N个」截断与既有 failedDetail 同风格）；主 message 追加「其中 N 个未找到文件，已跳过文件操作」。`mixins/torrentBatch.ts` 单删与批量轮询两处对 `fileMissingDetail` 发 `$notify.warning('文件缺失提醒')`。
- **生命周期兼容性核实**：回收站还原时 `.pending_delete` 重命名失败本就 warning 降级继续重新添加种子；彻底清理按 `original_file_list`/文件存在性逐项处理——跳过移动的记录还原/清理均无阻断。真实移动失败（目标冲突、数据不一致、部分文件失败）仍走原回滚失败路径，语义不变。
- **测试**：后端新增 7 例（移动函数四分支真实临时目录验证 + level3 file_missing 集成 + 幂等集成 + batch 收集），`test_torrent_deletion_by_level_api.py` 35 passed；deletion/recycle/file_operations 关联面 143 passed。前端 torrent-batch.spec 新增 7 例，87 passed；全量构建/lint/tsc 通过。
- 质量门：后端 black(24.10.0)/flake8/mypy 改动文件全过；前端 `npm run lint`、`tsc --noEmit`、`npm run build` 通过。feature_list.json 追加 `level3-delete-file-missing-skip-2026-08-27`。未执行 Git 提交。

## 2026-08-27：等级3删除文件缺失容错·回归加固（三层保护 + 变异验证）

- 按用户要求为上一批修复补足回归保护并提交：后端 7→23 新增用例（35→44 passed）、前端 7→13 新增（86→93 passed），变异验证 12 组全部精确拦截。
- **后端正常路径回归**（`TestMoveTorrentFilesForRecycleFileMissing` 扩充，真实临时目录）：单文件正常重命名（skipped=False + 文件落位）、多文件整体搬移（moved_count=2 + 子目录结构 + 原文件夹留空目录的既有语义）、单文件目标冲突真实失败（文件系统零改动——锁"容错只作用于原路径不存在场景，不得吞目标冲突"）、智能合并子集残留清理重移、空 .pending_delete 残留清理、内容不相交数据损坏失败 + inconsistent_state 不自动处置（保护清理智能合并死代码时的行为不变）。
- **后端 HTTP 级契约**（`TestDeleteWithLevelFileMissingPayload` 3 例，monkeypatch delete_batch_by_level）：成功/部分失败分支 data.level3_file_missing 精确值锁 + msg 含「N个种子未找到文件，已跳过文件操作直接移入回收站」（部分失败分支同样要提醒）；无缺失时 msg 干净不含「未找到文件」。前端 fileMissingDetail 依赖 data 字段，丢字段即静默失去提醒——HTTP 级透出是最后一道锁。
- **前端并存场景 + 源码接线契约**（6 例）：降级与文件缺失并存（downgradeDetail 与 fileMissingDetail 同时输出——锁降级分支 return 透传）、部分失败与缺失并存、异步 partial+results 提取并存；源码契约锁 utils 读 `data?.level3_file_missing`/`result?.file_missing` 契约字段名、两接口 `fileMissingDetail: string | null` 声明计数（3=两接口+局部变量）、mixin 单删与轮询两处 `if (parsed.fileMissingDetail)` + `title: '文件缺失提醒'` 计数各 2——行为测试锁纯函数，源码契约拦"解析了但没展示/字段名对不上"的静默失效。
- **变异验证 12 组全部拦截**（python 定点变异，锚点唯一性预断言、备份-变异-红-还原-cmp 字节校验，还原后 git status 零残留）：后端 M1 单文件 file_missing 反转、M2 多文件幂等 already_moved 反转、M3 `_delete_level3` 标志传递断开、M4 batch 收集条件失效、M5 endpoint msg 拼接移除（两处）、M6 endpoint data 透出移除（两处）、M7 单文件目标冲突被吞（success False→True）、M8 审计 skip_reason 键改名；前端 M9 异步提取 return false、M10 同步字段名错位（level3_file_missing→_x）、M11 mixin 轮询处通知移除（缩进锚点定位 10 空格块）、M12 提醒文案丢失。
- **验证**：后端全量 **4075 passed / 7 skipped**；`test_torrent_deletion_by_level_api.py` 44 passed；改动文件 black(24.10.0)/flake8/mypy 通过。前端全量 **84 套件 1191 passed**；定向 ESLint `--no-fix --max-warnings 0` 与 `tsc --noEmit` 零错误。feature_list.json evidence 已更新加固记录。

## 2026-08-28：移动端高级搜索条件组 UI 辨识度优化（行标签 + 内容行主题强调 + 触控放大）

- **需求**：移动端 /m/search 条件组堆叠后四个控件（字段/操作/值/方式）同为灰底圆角框且无标签，用户难以分辨哪一格是内容输入框。
- **改动**（全部限于 ≤768px 断点，桌面零变化；`AdvancedSearchBuilder.vue` + `ConditionValueInput.vue`）：
  - 条件四行加行标签「字段/操作/内容/方式」（`condition-row-label`，桌面 `display:none` 基准隐藏，模板标签+类名锁内容行）；
  - 「内容」行主题强调卡片：`--color-primary-lightest` 底 + `rgba(--color-primary-rgb,0.35)` 边框（随绿/橙主题联动，不写死色相），标签主题色加粗；`width:100%` 必须显式——基础 `.condition-content{align-items:center}` 多一层 `.conditions` 特异性更高会压掉媒体查询的 stretch（截图实测暴露后修复）；
  - 触控目标：条件行内输入/选择控件 32→40px（含 `.el-input__icon` 行高同步；`.ams__search-box` 玻璃搜索框豁免保持自绘 32px）；包含/排除单选组 flex 等宽拉伸、padding 12px；删除圆钮 `align-self:flex-end` 不再拉伸通栏；
  - ConditionValueInput 移动端 `.size-number-input` 100→130px：14px 字号下「0.00」末位被步进按钮裁切（截图实测暴露后修复）。
- **验证**：定向 65 例（AdvancedSearchBuilder/ConditionValueInput/field-types-consistency/mobile-search 四套件）全绿；`npm run lint`（含 contract:check）与 `tsc --noEmit` 零错误；Playwright 双栈实测（iPhone 12 视口登录 → /m/search）：390px 断点标签 block/内容行主题底/输入 40px/删除钮 flex-end、1280px 桌面标签 none/无底色/32px 全部断言 PASS，sizeRange 与多选两复杂变体截图复核无溢出无裁切。未执行 Git 提交。

## 2026-08-28：移动端条件组辨识度改造·回归加固（源码契约 + DOM 断言 + 变异验证）

- 按用户要求为上一批移动端 /m/search 条件组 UI 改造补足回归保护，新增 11 例（Builder 9 + ConditionValueInput 2），变异验证 14 组全部精确拦截。
- **DOM 层**（AdvancedSearchBuilder.spec 新增 1 例）：每条件渲染「字段/操作/内容/方式」四个 `condition-row-label` 且文案顺序锁定、「内容」行带 `--value` 修饰类（模板 class 契约）。
- **源码契约层**（AdvancedSearchBuilder.spec 新增 describe 8 例，范式同 field-types-consistency：jsdom 不级联媒体查询，锁源码字符串）：以首个 `@media (max-width: 768px)` 切分 baseBlock/mediaBlock 分区断言——①断点边界 768px 精确 ×2（scoped 主样式 + 对话框压宽块，防误改破坏桌面或移动覆盖）；②行标签桌面 `display:none` 基准 / 断点内 `display:block`；③`&--value` 主题色 + 加粗 600；④内容行强调卡三件套：显式 `width:100%`（防 `.condition-content{align-items:center}` 多层 `.conditions` 特异性压掉 stretch 的收缩回归，即上轮截图实测踩过的坑）+ `--color-primary-lightest` 底 + `rgba(--color-primary-rgb)` 边框（主题联动不写死色相）；⑤触控 40px（height+line-height 成对）与 `.ams__search-box` 玻璃框 32px 豁免；⑥单选组 flex/width:100%、按钮 flex:1、内边距 12px；⑦删除钮 `align-self:flex-end`；⑧桌面零变化锁：断点外 `.condition-value` 仍 `flex:1 + min-width:200px`。
- **ConditionValueInput.spec 新增 describe 2 例**：断点内 `.size-range-input .size-input-wrapper .size-number-input, .size-with-unit-input .size-number-input` 逗号选择器整对加宽 130px（缺一即红，锁 14px 字号防裁切）；桌面基准 100px/120px 不变。
- **变异验证 14/14 全拦截**（python 字节级定点变异，锚点唯一性预断言、备份-变异-红-还原-cmp 校验；M11 断点边界锚点计数 2 仅替换 scoped 块首处）：M1 --value 修饰类移除、M2 桌面基准 none→block、M3 移动端标签 block→none、M4 主题色→中性灰、M5 width:100%→auto、M6 主题浅底→透明、M7 触控 40→39px、M8 ams 豁免 32→40px、M9 内边距 12→6px、M10 右对齐→auto、M11 断点 768→900、M12 加粗 600→400、M13 数字框 130→100px、M14 逗号选择器截断。还原后 `git status` 零残留（两 .vue diff 与上批 UI 增量逐字节一致）。
- **验证**：定向四套件 **76 例全绿**（原 65 + 新 11）；`npm run lint`（含 contract:check）与 `tsc --noEmit` 零错误。未执行 Git 提交。

## 2026-08-28（晚）：Phase 0 风险闸门判据 1-4 达成（android-wheels 远端首建+导入矩阵全绿）

- **批次 B 收口**（用户确认"严格等 B"后的第一批）：gh CLI 未装，经 Git 凭据管理器 token + GitHub API 创建公开远端 `strainhzj/android-wheels` 并推送本地脚手架（ee65481）。
- **16 轮 CI 迭代**（每轮失败均归因并登记 gate.md/commit message）：cargo-ndk 只在 crates.io（pip 装不到）→maturin 无 `--abi3` 参数且 pydantic-core 无 abi3 feature（改 `-i 3.12`+`pyo3/extension-module`）→交叉链接要 `-lpython3.12`（空动态库 stub+patchelf 显式补 DT_NEEDED，lld --as-needed 会丢弃无符号解析的 NEEDED）→maturin 1.8 android repair 试图 vendor 系统库 libdl（`--skip-auditwheel`）→PEP 503 索引路径归一化必须连字符→ELF e_machine 在 offset 18（脚本原按 16 读 8 字节必错）→DT_STRTAB 虚拟地址须经 PT_LOAD 翻译→RECORD 重写键必须按旧路径匹配（zip/RECORD 一致性，Chaquopy pip_install int('') 崩溃归因）→Chaquopy 无 extraIndexUrls DSL（`options("--extra-index-url",…)`）→py3.12 弃 32 位 ABI（abiFilters 收敛）→useAndroidX→androidTest asMap 泛型→`Python.start(AndroidPlatform)`→emulator-runner 拆坏多行 script 分组（收敛仓库内脚本）→boot-timeout 1800（无 KVM 软件模拟冷启动 8-11 分钟）。
- **结果**：判据 1/2/3（两 ABI wheel 构建+形态校验+Pages PEP 503 索引 https://strainhzj.github.io/android-wheels/simple/pydantic-core/）与判据 4（import-matrix run 33180505344 全绿：索引装 wheel→模拟器→pydantic-core 原生导入→FastAPI /health/live 4/4）达成；`versions.env` 已回填 sdist sha256 与 wheel tag 并强校验。
- **重大口径修正**：Chaquopy 15.0.1 起 Python 3.12+ 不支持 armeabi-v7a/x86（changelog+官方仓库 wheel 文件名+Chaquopy 构建报错三重实证）——Phase 0 目标矩阵四 ABI→两 ABI；ABI 敏感依赖自建面收窄至 pydantic-core 一项（bcrypt/regex/pillow/pycryptodomex 官方仓库已有；gmssl 纯 Python）。
- **环境限制登记**：GitHub runner 软件模拟下 android-35 镜像 droid.bluetooth SIGABRT 系统级崩溃（default/google_atd 双镜像复现、应用零痕迹、API34 同 wheel 全绿对照）——API35+16KB 转判据 6 专项（google_apis_ps16k 镜像+本地 AVD）。
- **闸门状态**：判据 5（完整 import graph 阶段 2）/6（16KB/冷启动/升级）与 arm64 真机导入未完成，**Phase 3 维持封锁**；`.1` 保持 in-progress。
- 验证：build run 33164701409 起持续绿；import-matrix run 33180505344 success；本地干跑 retag/check-wheel-tag/索引脚本（合成 wheel + 真实 wheel 双向验证）；主仓 `./init.sh --ci` 通过；desktop_companion 53 passed 复验。

## 2026-08-28（晚·批次 A）：Phase 1（task .2）收口置 done

- 用户确认关闭口径：七项已全部收口（evidence 追加 2026-08-23 第二批），LAN 受控重绑维持 Phase 3 登记。
- 本批验证：定向后端测试组 109 passed（connectivity/delay-probe/writable-roots/packaging-contract/audit-excel/desktop_companion 六组）；首轮核查 ping3 零直调、requirements 瘦身、docs/android 文档矩阵齐全。
- `.2` → done；未执行 Git 提交（遵循仅用户要求时提交）。

## 2026-08-28（夜）：v1.0.6 制品等价门禁 W0 本地探针批次（release-artifact-equivalence-gate task .1）

- **范围**：只读核查后的第一批实施——基线固化 + 4 项本地 Docker 探针 + release-gate.yml 编写；不改任何构建脚本与业务源码。
- **基线**：`release/release-config.json` + `release/evidence/w0/baseline.json`；v1.0.5 标签=29c6f6f（与计划一致）；GitHub Release API 对 v1.0.5 实测 404（无正式发布制品）；`./init.sh --ci` 通过。
- **v1.0.5 夹具升级**：本地 `.release-build-v1.0.5/assets/` 发现完整制品集（DEB/RPM/portable EXE+ZIP）；与 `git archive v1.0.5` 对账 971 文件仅 4 差异（cleanup_executor.py 第272行 py3.11 f-string 热修=feature_list 记录在案的 R9 事故修复 + feature_list/progress/session-handoff 三个记录文件）→ 夹具策略从"纯重建"升级为 local-release-build（仍按 reconstructed 语义标注；SHA256 全归档于 w0-environment-report.md §2）。
- **R10 定案（耗时约 3+69 秒两段实验）**：现有 Debian 12 构建二进制在 rockylinux:9 失败——内嵌 libpython3.11.so.1.0 需 GLIBC_2.35 > 2.34（exit 255）；python:3.11-bullseye 容器重建后同一 spec 单二进制在 Debian 12 + Rocky 9 双发行版均 `Application startup complete` → **单二进制方案成立，Linux 构建基线定格 python:3.11-bullseye（glibc 2.31），不拆发行版制品**。证据：w0-glibc-{rocky9,debian12}-{existing,bullseye}.log + w0-bullseye-build.log。
- **Node 22**：node:22-bookworm-slim（v22.23.2+npm10.9.8）npm ci → contract:check → typecheck → Jest 84 套件 1233 测试（39s）→ build（46s）全绿 → **前端构建统一锁 22 线**；contract:check 通过同时证明工作区 advancedSearch.generated.ts 为合法再生产物（历史会话判定为行尾假警报，内容与后端契约同步）。证据：w0-node22-frontend*.log。
- **systemd 拓扑**：官方 rockylinux:9/debian:12 基础镜像均不含 systemd；自建镜像（官方基+仓库装 systemd，debian 必须补 /sbin/init 符号链接）以 `--privileged --cgroupns=host` 运行，双发行版单元生命周期（daemon-reload/enable --now/active/stop/inactive）全通；is-system-running=degraded 属容器正常态。证据：w0-systemd-smoke.log。
- **CI 编排**：`.github/workflows/release-gate.yml` 落地 4 个 W0 探针 job（w0-windows-runner：choco innosetup 6.3.3+ISCC 编译/静默装卸+NSSM 生命周期；w0-linux-systemd；w0-node-matrix；w0-glibc-bullseye），workflow_dispatch、fail-closed、报告 artifact if-no-files-found: error；Python yaml 校验通过。**未推送（未获授权）→ CI 侧全部 NOT_RUN，Windows Inno+NSSM 能力结论待 CI。**
- **收尾**：探针容器与 w0out 卷已清理；dist/ 遗留制品、.release-build-v1.0.5/、data/ 未触碰；PLANS 追加 §18、feature_list task .1 evidence（保持 pending，CI 未跑）、session-handoff 已更新；复验 `./init.sh --ci` 通过。
- **批次耗时**：约 70 分钟（含 Docker Desktop 启动 15s、4 镜像拉取、双探针并行）。

## 2026-08-28（晚·追加）：OkHttp 健康检查接入信任指纹（Phase 2 已知边界闭环）

- 用户拍板"纳入"：HealthClient 增 trustedFingerprints 参数，全信 SSLContext+CertificatePinner 精确钉扎组合（trust-any+pin=trust-only-these），hex→base64 pin 转换，指纹不匹配归 TLS_ERROR 提示重新确认；两调用点传入 profile 指纹。
- 新增 HealthClientPinTest 4 例；:app:testDebugUnitTest 17/17 全绿（--rerun-tasks 复核）。真实 TLS 握手待设备验证。
- SDK 下载完成：emulator + android-35 google_apis x86_64 + google_apis_ps16k（16KB）镜像就位（C:/software/android-build-env/sdk），AVD 创建与 16KB/冷启动验证留待下批。

## 2026-08-28（晚二）：判据 6 之 16KB page-size——缺陷发现、修复与双页验证

- ps16k AVD 实测抓出旧 wheel p_align=4096 在 16KB 页 dlopen 即崩（linker LoadSegments SEGV_ACCERR，tombstone 实锤；CI 4096 镜像盲区）；"gradle 全量部分通过"系 runner 进程重启假象，solo 复测纠正。
- 修复：`-Wl,-z,max-page-size=16384` + check-wheel-tag p_align≥16384 断言（对旧 wheel 验证拦截）。
- 验证：16KB AVD 6/6、常规 4096 AVD 6/6 全绿；install -r 升级安装覆盖。
- 附带：深导入需大栈线程（16MB）——Phase 3 app.main 导入的前置技法。
- 下一批主任务：判据 5 阶段 2 实装（backend/alembic/契约/frontend dist 注入 testapp + 全量依赖可解析性梳理）。

## 2026-08-29：判据 5 达成——BtDeck 完整 import graph 在 Android 全通（Phase 0 闸门仅剩判据 6 收尾）

- **实装**：android-wheels 仓 fullgraph 阶段 2（staging 脚本/bootstrap 运行体/Kotlin 测试/gradle 属性接线），backend+alembic+frontend dist 注入 testapp，路径锚定零后端改动。
- **验证**：4096 x86_64 AVD **9/9 全绿**——完整导入/迁移（空库→head+幂等）/uvicorn loopback 服务（lifespan 完整初始化：调度器+三 lane runtime+仪表盘任务；/health/live 200；静态 SPA 首页 200）。
- **自建 bcrypt 5.0.0**：官方 3.2.2 在 Android15 16K 镜像 dlopen 失败（老 NDK 形态）——走 setuptools-rust 原生后端（maturin 会误取 Cargo 元数据）；retag 泛化为"错误 libpython3.X 移除+目标补记"（abi3 链接形态）。bencodepy 入 extra-wheels（sdist-only+distutils）。tzdata 补充（Android 无系统 tz 库，调度器 GMT 报错实证）。
- **新坑登记**：Chaquopy 源集丢孤儿 .py（.pymig+物化解）；包化目录会遮蔽同名库（PEP 420 语义）；testapp 需 INTERNET 权限否则 bind EPERM；uvicorn 拒绑 port 0；gradle 不追踪 -r 文件变化。
- **16KB 限制**：官方仓库存量 C 扩展 wheel（bcrypt/regex 已证，pillow/pycryptodomex/greenlet 大概率同类）在 16K 镜像系统性不可载——判据 6 收尾=全依赖面 16KB 化，Phase 3 前必须解决。
- `.1` 保持 in-progress（判据 6 未收）；wheels 仓已推 a9caf91。

## 2026-08-29：种子实时终态收敛与部分快照容错

- **根因**：`active-torrents` 原先只返回有速度任务，且 qB/Transmission 实时数据没有状态字段；任务完成后速度归零即从响应消失，TTL 补查固定取前 20 条并重复请求，数据库同步只依据进度 100 合成状态，前端还会丢弃 206 部分快照，导致列表继续显示 downloading 或进度冻结。
- **后端**：新增运行态归一化（状态映射、进度 0–100 钳制、`downloadComplete` 完成证据）；显式未完成标记优先于状态推断，且完成时间/完成状态/100% 一旦落库后不会被异步旧快照回退；TTL 按下载器独立轮转并设置 2 秒补查退避，确认完成后移除；终态在速度接口返回前同步进度/状态/完成时间，普通进度仍按批次异步写入；新增 `POST /torrents/runtime-state/reconcile`，批量核验最多 100 个复合键并返回 `list/missing`。
- **前端**：`buildSpeedSnapshot` 接受 206 并返回可合并增量；列表、传统、移动三视图按 `downloader_id + hash` 精确更新速度/状态/进度，完整快照连续两次未命中时低频调用终态核验；完成证据强制进度 100，状态筛选场景核验后刷新列表。
- **回归与记录**：后端定向 94 passed；前端速度工具 98 passed、列表/传统/移动组件 75 passed（合计 173）；`tsc --noEmit`、`npm run lint`、mypy、flake8、py_compile、前端生产 build 通过。Black 24.10 在当前 Windows 对该文件按项目 `line-length=120` 检查会挂起，改用 `line-length=117` 快速检查确认无格式差异。`./init.sh --ci` 在当前 Windows/WSL 环境仍受既有 E_ACCESSDENIED/null-byte 输出限制；未执行 Git 提交。

## 2026-08-29：种子实时终态修复回归加固与目的验证

- **目的验证闭环**：新增端点级两轮场景，第一轮 qB 任务以 4096 B/s、99.37%、`downloading` 进入 TTL；第二轮活动接口不再返回该任务，TTL 按复合键补查到零速 `seeding` 且原始进度仍为 99.37%，响应最终稳定为 `progress=100`、`downloadComplete=true`、非下载中状态，终态在响应前同步并从 TTL 移除。另验证其它下载器失败导致 206 时，健康下载器已确认的终态仍会交付和同步。
- **新增 36 个回归执行项**：后端 16 项覆盖 qB 6 种上传终态、Transmission 2 种做种终态、100%/显式 false 优先级、终态错误保留、TTL 退避/恢复、两轮闭环、206 终态，以及完成时间/完成状态/100% 三种落库证据独立防回退；前端 20 项覆盖旧服务端终态矩阵、异常数值、显式 false 与 100% 优先级、同 hash 复合键隔离、核验排除集/100 项上限、API 载荷和列表/传统/移动三视图行为。
- **测试结果**：后端定向三文件 **110 passed**；前端定向 5 suites / **237 passed**，前端全量 84 suites / **1258 passed**。后端全量 4145 collected，结果 **4136 passed / 7 skipped / 2 failed**；两项失败分别对应本任务开始前已存在的未暂存 `backend/app/api/endpoints/health.py` 新增 build 字段但旧断言未更新，以及 `deploy/requirements-linux-package.txt` 改为引用 lock 后旧测试仍要求本文件直接出现 openpyxl，均与本批 8 个测试文件无重叠。
- **质量门禁**：前端 `npm run typecheck`、`npm run lint`、`npm run build` 通过；后端目标 mypy、flake8、py_compile、`scripts/lint_btdeck.py` 通过。Ruff format 120 对两个 API 测试通过，`test_active_only_filter.py` 只报告本批未触及的既有 L177 字符串拼接；Black 24.10 在当前 Windows 对测试文件按项目 120 线宽仍无输出挂起并已中止。根 `bash ./init.sh --ci` 仍在 WSL 创建阶段报 `Bash/Service/CreateInstance/E_ACCESSDENIED`。
- **记录状态**：`feature_list.json`、`docs/roadmap/tests/README.md`、`docs/roadmap/perspectives/test-coverage.md` 与 `session-handoff.md` 已同步。本轮仅新增/扩展测试和证据，业务源码无需再改；回归加固尚未 Git 提交，保留工作区其它发布构建相关未提交内容。

## 2026-08-29（晚）：判据 6 达成——完整后端 16KB 页 Android 全通，Phase 0 闸门全过（task .1 置 done）

- **16KB ps16k AVD 全新安装 9/9 全绿**（完整导入/迁移/uvicorn 服务/静态首页+阶段1）；判据 1-6 全部达成，Phase 3 解锁（正式放行待用户确认 arm64 真机项）。
- **16KB 全依赖面攻坚（~20 轮 CI）**：greenlet/regex/pycryptodomex/bcrypt 自建全绿。关键沉淀：CC/CXX wrapper 剥宿主 sysconfig 注入（-I/usr/include 连体+分体、-m64、--fix-cortex）+ -nostdinc 显式 NDK isystem 根治 + .so 自动 -shared + c-ext 必须补 DT_NEEDED libpython + NEEDED 改名表（libz.so.1→libz.so 等）。pillow 挂其自家后端深处（登记 ANDROID-DROP）。
- **主仓后端小改**：cuser.py 的 qrcode/PIL 顶层导入改函数内延迟（桌面零差异，cuser 10 测试全绿）——完整启动链不再触碰 PIL。
- wheels 仓推至 917bb89；索引常驻五包自建 wheel + bencodepy。

## 2026-08-29：桌面折叠侧栏多子菜单 Lucide 图标修复

- **根因闭环**：种子管理与 Tracker 管理有多个可见子路由，因此 `SidebarItem` 进入 `el-submenu` 分支；桌面折叠样式原用 `> span { visibility: hidden; }` 隐藏标题。该规则早于 Lucide 迁移，迁移后 `LucideIcon` 的根节点也是 `span`，主图标遂与标题、箭头一起被隐藏。单子路由进入 `el-menu-item` 分支，不命中这条规则，形成表面上的“仅多子菜单图标异常”。
- **修复**：在子菜单标题文字上增加 `.submenu-label`，折叠态仅隐藏 `.submenu-label` 与 `.submenu-chevron`，并显式保持 `.menu-icon` 可见；展开态及单子项渲染路径不变。
- **回归**：新增 `frontend/tests/unit/sidebar-collapse-lucide.spec.ts`，真实挂载 `SidebarItem + Element UI + LucideIcon` 并编译组件实际 SCSS，5 项覆盖种子管理、Tracker 管理折叠态，展开态，单子项，以及禁止重新引入广泛 `> span` 选择器。
- **验证**：相关 4 suites / 122 tests、前端全量 85 suites / 1263 tests、`npm run typecheck`、严格 `npm run lint`、`npm run build` 全部通过；构建仅保留 58 条既有 Sass/资源/CSS 顺序 warning。根 `bash ./init.sh --ci` 仍受当前 Windows/WSL `E_ACCESSDENIED` 环境限制；未执行 Git 提交，工作区其它既有修改均保留。

## 2026-08-29（深夜）：Phase 3 安卓本地服务端壳工程落地（task .4 → in-progress）

- **批次 A（Python 侧）**：`android/tools/stage-server.py`（移植 wheels staging：backend/app + alembic(.pymig) + alembic.ini + frontend/dist → gitignored 源集，requirements 生成含 pillow ANDROID-DROP）与 `android/server-python/btdeck_server.py`（start/stop/status JSON 契约：异步启动+状态轮询、Alembic fail-fast、16MB 大栈线程、uvicorn 预取端口、优雅停机）。桌面冒烟 SMOKE PASS（4s running / live+ready 200 v1.0.6 / SPA 首页 / 停机干净 / 重启 2s）。
- **三个实证修复**：① 迁移必须前置于 `from app import main`（导入链有模块级 DB 查询，空库时刷"no such table"依赖 lifespan 补救）；② 健康自检 httpx 必须 `trust_env=False`——Windows 注册表系统代理会把 127.0.0.1 探测转发成代理 503（`proxy-connection: close` 响应头实锤，BtDeck/uvicorn 无辜）；③ 端口复用探测 socket 需 `SO_REUSEADDR`（重启时 TIME_WAIT 端口被拒，AVD 实证 expected≠actual）。
- **批次 B（壳工程）**：Chaquopy 17.0.0 接线（Python 3.12、extra-index-url 指向 android-wheels 索引、-r staged requirements、`-Pbtdeck.server=off` 可跳过）。**Chaquopy pip 空配置坑（本仓新实证）**：pip 块内无任何 `install()` 时整个 pip 配置（含 options()）被判空跳过 → requirements-*.imy 仅 22 字节空头；tzdata 的 install() 兼任生效锚点。abiFilters 收敛 arm64-v8a/x86_64；FGS specialUse manifest（权限+subtype+START_STICKY）；ServerService（通知+停止 action+轮询状态镜像+绑定变化完整重启+数据锚定 filesDir/btdeck-server）；ServerStates/LocalServerProfile/LocalServerState 纯 JVM 契约层；LanHostPolicy 回环豁免（Hosts.isLoopbackHost：127/8+::1+localhost 免明文确认，LAN 主机仍需确认）。JVM 单测 28 绿（testImplementation org.json:json 修 not-mocked）。
- **批次 C（向导集成）**：ABI 检测 → 通知权限请求（13+）→ 确认对话框（LAN 开关默认关+威胁模型）→ 启动进度 → running 自动写本机 profile（固定 id+动态端口）复用 WebViewActivity 全链 → 错误按阶段归因；ServerList 本机 profile 未运行引导。
- **批次 D（双 AVD 实证）**：btdeck-a35（4096）connectedDebugAndroidTest 1/1 绿（start→迁移→健康握手→SPA→停机→重启端口复用）+ 手动全流程铁证（uiautomator/dumpsys）：向导→权限 Allow→确认框→15s running→WebView 自动开→SPA 登录页渲染→标题"本机服务端 v1.0.6 · 服务就绪"→常驻通知带端口+停止 action→FGS types=0x40000000→ACTION_STOP 销毁→重启→am crash 后 pid 3816→4301 START_STICKY 重建+端口 36519 复原。btdeck-16k（ps16k 16KB）connectedDebugAndroidTest 绿+启动链抽验（10s WebView、通知 41241）。LAN 变体构建 0.2.0-server+lan 通过。APK debug 90.4MB。
- **后端零源码改动**。遗留（登记 feature_list task .4）：arm64 真机/升级安装演练/OEM 电池与 Doze 设备矩阵属 Phase 5；pillow ANDROID-DROP 致 2FA 二维码暂不可用；release+bundletool 精算 Phase 5。未执行 Git 提交。

## 2026-08-29（深夜二）：Phase 4 capability 矩阵 API/UI 一致降级接线（task .5 追加）

- **后端**：`app/core/platform_capabilities.py`（14 项能力矩阵单一真相源，`BTDECK_PLATFORM` 判定 desktop/android-server，非法值 fail-safe 回落 desktop，键集有单测锁定——新增能力必须先登记矩阵文档）；`GET /api/v1/platform/capabilities` 认证端点；cron 自定义脚本拦截升级（android-server 形态 403"当前主机形态不支持"，形态判定优先于安全开关，desktop 语义不变）；btdeck_server 注入 `BTDECK_PLATFORM=android-server`。
- **前端**：api 层单例缓存（失败按 supported/desktop 兜底）；settings 新增"主机能力"tab（表格/卡片双布局，移动端经包装自动同源）；桌面任务创建对话框 0-3 类型置灰+说明+提交兜底；移动任务列表 android-server 显示省电延迟提示条。
- **验证**：后端定向 70+156 passed（mypy/black/flake8 过）；前端定向 22 例+全量 89 suites/1285 tests、tsc 零错、lint 过；AVD（btdeck-a35）端到端实证——服务 10s 就绪、`/platform/capabilities` 返回 android-server 14 项 5 降级/3 不支持（与冻结矩阵逐项一致）、cron add task_type=0 被拒并给出主机形态文案。
- 过程修复一处测试自身问题（api spec 漏 mock 清理导致调用计数跨用例累积，mockReset 根治）。未执行 Git 提交。

## 2026-08-30：.3/.5/.8 设备级验证批次 + Phase 4 提交

- **提交**：`b326378`（Phase 4 capability 矩阵 API/UI 一致降级，20 文件 +1181）。
- **.5 矩阵 UI 设备级目验**：Playwright 直连 AVD forward 的 android-server 后端自带前端（与 App WebView 同源等价），settings-capability.spec.ts 4/4——主机能力 tab、14 卡片、"Android 服务端"形态、降级 5/不支持 3 统计、danger/warning 徽标。
- **.8 Keystore 设备级**：CredentialVaultAndroidTest 仪表化 6/6——加解密往返、密文落盘（无明文）、覆盖保存改密、删除、约束；connectedDebugAndroidTest 合计 7/7（含 LocalServerAndroidTest 回归）。
- **.3 认证路径**：AVD 后端复跑 login.spec 3/3（错误凭据 error message 停留登录页、正确凭据进仪表盘）；强制改密全流程与登录限流（429→服务重启清零）实证。
- **过程坑**：adb UI 表单自动化脆弱（对话框外点即关/键盘位移/仪表化测试清数据卸 APK）——原生 UI 项转 Playwright+仪表化覆盖；E2E 全新库需先完成强制改密（forceChange 跳设置页，改密表单在"修改密码" tab 非 2FA tab）。
- 遗留人工项：.3 离线 toast/自签证书弹窗/多 profile 原生切换肉眼验收；.8 桌面 GUI 侧与自动登录 UI 流程。未执行 Git 提交（验证产物待用户指示后一并提交）。

## 2026-08-30（二）：Phase 5 发布验收首批（task .7 → in-progress）

- **批次 A**：release keystore（gitignored+local.properties 凭据，缺失退化不阻断）+ signingConfig 接线；assembleRelease 87.7MB / AAB 67.7MB；apksigner 验签；bundletool 精算（universal 85.6MB、native 拆分各 12.2MB、单设备 ≈73MB、8 so/ABI 清单）；minify 关闭决策登记。
- **批次 B 设备矩阵**：API 24（新建 btdeck-a24）——release 全链路 10s WebView（Python 3.12 on minSdk 24 跑通）、FGS+health 200、旋转存活、LAN 绑定变化（*:0.0.0.0 端口复用）、kill -9 崩溃恢复；**修复两个 API 24 真 bug**：NotificationChannel 无版本守卫（ClassNotFoundException 崩溃）、java.util.Base64 lint NewApi（改自包含 Base64，单测/设备一致）。API 34（新建 btdeck-a34）——链路+capabilities android-server 5/3。Doze deep idle 模拟器不可强制（登记真机）。
- **批次 C**：docs/android/play-release.md（Play 申报材料全家桶+包体实测）；:app:lintDebug 绿（修复后）；单测 32 绿。
- 遗留边界（登记 task .7）：Play 上传、arm64 真机、跨版本升级演练（v1.0.7）、Doze 真机。

## 2026-08-30（三）：种子列表成员自愈补充修复

- **问题判定**：批量添加接口返回 202 后，父列表原有 `@confirm` 只立即调用一次 `getList()`；后台任务稍后才写数据库，因此会出现“实际已入库、页面仍没有该行”。实时速度更新又只修改当前 `list` 中已存在的行，无法让缺失行凭空出现，所以此前的终态收敛修复不能完整覆盖这一竞态。
- **运行态自愈**：`torrentBatch.ts` 新增 `RuntimeListMembershipTracker`。首个 200 完整活动快照只建立分页外任务基线，后续新出现且当前列表未展示的 `downloader_id + hash` 才触发一次串行权威列表刷新；206 仅增量合并。刷新后立即重放同轮速度，列表、传统、移动三视图均能让新行直接显示当前进度与速度。
- **后台完成兜底**：`TorrentAddDialog.vue` 在 202 后保留 `task_id`，每 2 秒查询既有系统通知的 `torrent_batch_add_completed` 事件；完成后发出 `batch-complete`，桌面列表/传统视图再次拉取权威列表并补一次速度。该路径覆盖新增种子零速度、暂停或瞬间完成、不出现在活动快照中的情况；10 分钟超时仍执行一次最终刷新，组件销毁会清理计时器。
- **回归保护**：新增 12 个执行项，覆盖首次完整快照基线、206 增量、同 hash 跨下载器、重建基线、并发刷新单飞，三视图“已入库但未展示”闭环，桌面双视图完成信号刷新，以及添加对话框通知匹配与销毁清理。相关 5 suites / 204 passed；全量 90 suites / 1297 passed。
- **质量门禁**：`npm run typecheck`、`npm run lint`、`npm run build` 全部通过；构建仅有既有 Browserslist/Sass 警告。根 `bash ./init.sh --ci` 仍受当前 Windows/WSL `Bash/Service/CreateInstance/E_ACCESSDENIED` 环境限制。`feature_list.json`、`docs/roadmap/` 与 `session-handoff.md` 已同步；本批尚未 Git 提交，工作区其它 Android/发布构建修改保持不动。

## 2026-08-29：v1.0.6 制品等价门禁 W0-CI 收口 + W1 全批次（release-artifact-equivalence-gate task .1/.2/.3 → done）

- **W0 CI 收口**：workflow 推送 dev（master 注册 b357e07，dispatch ref=dev）；run 33236313405 Node22/bullseye/systemd 三绿；Windows 探针两轮修复后 run 33237024759 @621e7a5 全绿（ISCC 编译/静默装卸/NSSM 生命周期三 PASS，报告归档 w0/w0-windows-runner.json）。失败本身验证了 fail-closed（报告缺失即 job 红）。修复点：runner 预装 Inno 6.7.1 与钉死 6.3.3 冲突→预装探测跳过 choco；pwsh7 无 Set-Content -Append→Add-Content。task .1 → done。
- **W1 版本单一源（task .2 → done）**：release-config candidate.product_version=1.0.6 为唯一输入；六处声明（version.py/package.json/feature_list/btdeck.iss/build-linux.sh/release-config）统一并被 --check-versions + 13 例测试（5 变异）强制；package.json 增 engines+packageManager。build-info/release-manifest 双 schema；generate_build_info.py（SHA/alembic 单 head/frontend+source manifest）真实仓库端到端冒烟通过；backend/app/core/build_info.py 运行时读取（MEIPASS/仓库/BTDECK_BUILD_INFO，dev 不伪造身份，畸形即 BuildInfoError）；健康接口 live/ready 增 build 字段（外壳/旧字段不变，身份非法 ready 503+build_identity_invalid）；旧全等断言按新契约更新。回归 50/50（release 40 + health 10）+ 变异（version 漂移/packaging 白名单外 qB/锁内 qB 漂移）全拦截 + black/flake8/mypy 全过。
- **W1 依赖与工具链（task .3 → done）**：backend/requirements-lock.txt（pip-compile --generate-hashes，Py3.11，51 包）落库，**qB 分叉关闭（==2025.2.0）**；deploy 两 packaging 文件重构为 -r 锁+白名单增量，passlib/email-validator 零使用项移除；干净容器 --require-hashes dry-run OK；regression.yml 切 Python 3.11 + Node 22.23.2；两 Dockerfile digest 固定（python:3.11-slim@1042b614/node:22-bookworm-slim@83f487e0/nginx:1.25-alpine@516475cc）+ OCI label ARG 骨架 + trixie deb822 镜像 sed 修复 + runtime 离线 pins 安装（sdist wheel 哈希误杀规避）+ pip check。
- **镜像级验证**：btdeck-backend:w1-smoke 构建成功，真实环境 pip freeze 与锁归一化比对 50/50 全一致（FREEZE_MATCHES_LOCK，G2 制品导出首例）；btdeck-frontend:w1-smoke 构建成功，配对网络冒烟（frontend healthy 200 / backend /health/live 携带 build 身份块 dev 模式）。
- **坑位沉淀**：PyPI 直连限速 40KB/s、tuna 403、aliyun 可用（锁生成/镜像构建均走 aliyun，哈希为内容哈希不受镜像影响，已去除锁内 --index-url 行）；Docker Desktop 引擎间歇掉线两次（重启即恢复）；`tee|tail` 吞退出码。
- 未提交（遵循仅用户要求时提交）；feature 整体保持 pending（.4~.9 待做，下一批 W2 唯一前端构建与严格制品构建）。

## 2026-08-30：v1.0.6 制品等价门禁 W2 批次（task .4 → done：唯一前端构建/严格制品构建/静态等价 E2E 全绿）

- **唯一前端构建链**：scripts/release/build_frontend.py（Node 版本线校验+纯规范 manifest+meta）；check_prebuilt_frontend.py 在所有制品构建消费前强制 canonical 一致——本地以 node:22 容器产出唯一构建（357 文件，v22.23.2），Linux/Docker 制品均消费该构建，零二次前端构建。
- **严格模式**：三构建入口（build-linux.sh/build-windows.bat/build-images.sh）--release 均为 fail-closed：预构建前端必需、fpm/ISCC 必需且失败即败、干净工作区强制、双 spec 嵌 build-info/双 manifest（staging 缺失即败）、Windows EXE VSVersionInfo 版本资源（完整 SHA 备注）、OCI label 构建后强校验、frontend/Dockerfile.release 消费唯一前端（独立上下文绕开 .dockerignore）。
- **本地 E2E 全绿**（临时干净 clone @37bbccd + bullseye/fpm/rpmbuild 构建容器 + 镜像源加速）：Linux 严格构建 exit 0（PyInstaller→verify-package 内容级 PASS→fpm DEB+RPM）；docker 严格构建 exit 0（label 校验+镜像内 build-info 断言）；**verify_release_bundle 6 制品一致 PASS（G1/G4/G5）**——同一 SHA、manifest 逐字节一致、DEB/RPM 解包二进制==中间二进制、checksums+镜像 ID 归档（release/evidence/w2/）。
- **E2E 拦下的真实缺陷（fail-closed 七连实证）**：①严格模式正确拒绝脏工作区×2；②锁内 --hash 激活 pip 哈希模式与未哈希平台增量冲突→两段式安装；③CRLF 锁文件被 pip 视为续行→gitattributes 强制 LF+CR 剥离；④Windows python/docker CLI 不识别 /c/... 路径→统一 cd+相对路径；⑤python 补丁把 '\r' 写成字面 CR 字节、MSYS 吞裸 CR 参数→字节级修复；⑥并发严格构建互相覆盖镜像标签（竞态）→串行纪律；⑦Linux/docker 制品跨 SHA 不一致被 bundle 验证器拦截→对齐重建。
- **测试**：tests/release/ 78 例全绿（新增 verify-package 五变异 8 例、构建脚本源码契约 19 例、bundle 纯函数 11 例）。
- **CI**：release-gate.yml 增 w2-strict-{linux,windows,docker} job（workflow_dispatch，含制品上传与 EXE 版本资源断言）；尚未推送执行。
- 工程修复沉淀：generator/build_frontend 统一 LF 写出（跨平台字节一致）、manifest 纯规范形态、bundle 验证器 frontend-build 仅参与 manifest 比对。
- 未提交部分见下一提交；feature 整体 pending（W3 生命周期批次待做）。

## 2026-08-30（四）：下载器手动种子同步异步生命周期修复

- **根因**：下载器页同步按钮仍能调用 `POST /torrents/sync-single`，后端也仍经 `SyncCoordinator(sync_type=full, trigger=manual)` 执行并复用 `app.state.store` 缓存客户端；但桌面/移动端把“后台任务已受理”立即提示为“执行成功/同步完成”并释放 loading。后端另有三个生命周期缺口：结构化 `{status: failed}` 正常返回会被标成 SUCCESS；重复检查仅看 RUNNING 且先查后建非原子；fire-and-forget runner 未保留强引用。
- **后端修复**：`BackgroundTaskManager` 新增 `create_task_if_idle()`，在同一把锁下占用 pending/running 任务；`start_task_runner()` 保留 asyncio.Task 且在 done callback 统一释放/消费异常；`execute_task()` 按结果 status/outcome 映射 SUCCESS/FAILED/CANCELLED。sync-single 只将下载器数据与审计上下文的纯数据快照传入后台执行体，并在重复请求上返回 409 + 同一 task_id。
- **前端修复**：`api/downloader.ts` 补齐任务提交/状态类型与 `getSyncTaskStatus()`；新建共享 `views/downloader/sync-task.ts`，1s 轮询既有 sync-status，支持终态分类、销毁取消、10 分钟超时及连续查询错误上限。桌面与移动页均仅在真实后台终态后释放按钮，并区分 success/partial/failed/cancelled。
- **真实页面验证**：本地启动 FastAPI + Vue 后使用开发登录账号进入“下载器管理”，点击 qb 的“同步”。界面先显示“同步任务已启动: qb”；由于当前 192.168.5.51 下载器未进入 `app.state.store`，协调器返回 failed，页面随后展示“不在 store 缓存中（可能离线或未启用）”的真实原因，没有再误报同步成功。
- **回归与门禁**：后端同步专项 78 passed / 5 skipped；前端相关 4 suites / 87 tests，全量 91 suites / 1302 tests；`npm run typecheck`、严格 `npm run lint`、`npm run build`、目标 mypy/flake8 全通过。Git Bash 根 `./init.sh --ci`、feature_list JSON 解析与 `git diff --check` 通过。新增测试经 Black formatter API 校验通过；其余已修改的后端存量文件在 HEAD 上已不符合当前 Black 版本，本批不做全文无关重排。生产构建仅有已有 Browserslist/Sass 弃用警告。未新增 API 端点、数据表或 Alembic 迁移。
- **交付记录**：`feature_list.json` 新增 `downloader-control-room-ui-redesign.4` 并置 done；`docs/roadmap/` 已按路线图维护规则同步入口、方法行号和当前实测测试文件计数。本批未执行 Git 提交，已有 Android/发布制品与 `advancedSearch.generated.ts` 工作保持不动。

## 2026-08-31：v1.0.6 制品等价门禁 W3 批次（task .5/.6/.7 部分完成，CI 收口待下轮）

- **R11 修复**（deploy/package-scripts/）：maintainer scripts 从 build-linux.sh 抽为可测试文件；prerm 按 DEB 字面/RPM 数字参数智能分支（升级只 stop 不 disable），DEB postrm purge 清数据；fpm 布线 DEB 三 scriptlet / RPM 两 scriptlet。
- **生产缺陷修复（E2E 实测拦截）**：①btdeck.service 补 PrivateTmp=true——ProtectSystem=strict 下 /tmp 只读致 PyInstaller onefile 无法解压（restart 循环）；②postinst SECRET_KEY 兜底链改 coreutils（最小系统无 openssl/python3 时 exit 127）；③postinst 守卫接受容器 degraded 态。
- **生命周期驱动**：deb.sh/rpm.sh（fresh: 首装+重装+重启×2+remove 数据保留+purge；upgrade: v1.0.5→v1.0.6 R11 断言+secret 保留+head 推进）；docker.sh（v1.0.5 夹具上线→幂等 up→force-recreate→升级→同组合不 recreate→down-up）；windows.ps1（EXE 隔离双启+Setup 静默全周期）；make_v105_baseline.sh（CI 侧 tag 重建）；run_deb_rpm.sh（编排器）。
- **CI**：release-gate.yml 增 w3-lifecycle-{linux,docker,windows} 三 job（全 checkout fetch-depth 0）。六轮 CI 迭代发现并修复：w1_pinned.node 值带注记→build_frontend 校验失败；bat if 块 echo ASCII 括号→cmd 解析崩溃 exit 255；make_v105 容器内缺 safe.directory；锁缺 colorama（click 的 Windows 传递依赖）；rocky curl-minimal 冲突；Windows --require-hashes 平台标记不兼容。
- **本地 E2E**（Debian 12 容器）：**deb-fresh reinstall/restart/remove/purge 全 PASS；deb-upgrade v105_to_v106_upgrade PASS + alembic_head_advanced PASS + remove_after_upgrade PASS**——R11 核心链路实证绿。deb-fresh 首装 fail 因 v1.0.6 包在 CI 构建含旧 scriptlets（本地重建的包已修复）。
- **测试**：tests/release/ 100/100（lifecycle_scripts 22 例：prerm 参数语义 mock systemctl/postrm purge/源码契约）。
- **CI 现状**：第六轮修复已推送（356c89d），Docker v105 夹具容器启动后挂住（仅 banner 无后续——v1.0.5 Docker 镜像 btdeck_startup.sh 兼容性问题，非 v1.0.6 缺陷）；Linux/Windows CI 可能存在日志缓存未反映最新代码。
- **遗留**：CI 三 job 全绿需下一轮干净 dispatch；Docker v105 夹具挂住需诊断 btdeck_startup.sh 在 compose 环境的行为；任务 .5/.6/.7 保持 pending 直到 CI 全绿。

### 2026-08-31（续二）：W3 CI 第七~九轮——五根因修复、deb/docker 首全绿、RPM scriptlet 时序深层缺陷

- **诊断纠偏**：27e1135/469a854 推送后从未触发 CI（最新 run 停在 356c89d）——"日志缓存"实为从未跑过；27e1135 相对 356c89d 只改文档无代码修复，上轮三 job 失败根因全部仍在。356c89d 轮日志归档 release/evidence/w3/ci-v7/。
- **第七轮四根因（194e5d0）**：①锁补 tzdata==2026.3（tzlocal 的 `platform_system=="Windows"` 传递依赖；锁内嵌 --hash 自动激活哈希模式，与 colorama 同型，PyPI 哈希+本地下载实证）+requirements.txt 声明；②run_deb_rpm.sh SKIP_MIRROR 分支 debian 夹具漏装 python3（build_info_field 静默回退 'ERR'，镜像分支有而官方源分支无）；③build-linux.sh 包内 build-info 按包型 retag（计划 §158 枚举不含 linux-binary；就地单字段改写防 generator 重算 build_id 漂移；DEB/RPM 链式 retag 白名单）④v1.0.5 健康谓词改 alive——**v1.0.5 响应无 version 字段**（version 是 v1.0.6 W1 引入），四驱动等 `"version":"1.0.5"` 必然超时（deb 容器实证：服务 5 秒就绪、alive HIT、version ABSENT）；windows.ps1 另修匹配串带空格（紧凑 JSON 不命中）。
- **第八轮两缺陷（f1d2b87 + 548c56f）**：①w2-strict-linux builder 装 rpm-build（RHEL 系包名，bullseye 无）→对齐 W3 job 已实证的 rpm+rpm2cpio（w2 三 job 首跑暴露的存量缺陷；workflow 双同步 master 5975aa1）；②verify-package 归档条目名规范化——PyInstaller 在 Windows 用 os.path.join 组装 datas 目标路径，目录型条目进 CArchive 为反斜杠名（本地 6.19 实证 'app\contracts\x.json'），dest='.' 三件套可读而子目录条目全误报缺失；+stdout cp1252 兜底（中文失败信息 UnicodeEncodeError 掩盖真因）。
- **第八轮 run（33398652029@194e5d0）战果**：**docker compose job 首次全 PASS**（v105 alive 谓词实证生效）；deb-fresh/deb-upgrade 全 PASS（v105_baseline_install 首过）；rpm-fresh 挂 reinstall（dnf reinstall 对本地包立即报错）、rpm-upgrade 挂升级后健康（3 分钟无响应）。
- **第九轮 RPM scriptlet 时序深层缺陷（97ac103）**：**RPM 升级时序 %post(新)→%preun(旧) 与 DEB（prerm(旧)→postinst(新)）相反**。①v1.0.5 冻结包 prerm 无条件 stop+disable，在新 postinst 之后执行→停掉刚拉起的服务（rpm-upgrade 失败根因；不可改冻结制品→rpm.sh 升级段加 enable+restart 夹具补偿，与 deb.sh 基线适配同类；**真实生产 v1.0.5→v1.0.6 RPM 升级需手动 `systemctl enable --now btdeck`，登记 runbook**）；②R11 自身缺陷：v1.0.6 prerm 的 RPM 升级分支（$1=1/2）stop 同样停掉服务→改 **no-op**（服务全权交新 postinst）；③postinst"未运行才启动"在 RPM 时序下升级不生效（旧进程持旧 inode 继续 serving v1.0.5）→运行态改 **restart**（DEB 升级时 prerm 已 stop→仍走 start，行为不变）；④reinstall 改 `rpm -Uvh --force`（本地文件强制重装标准形态，时序同升级→依赖①②修复）。测试 110/110（prerm DEB/RPM 分支拆分断言+postinst restart 契约）；artifact path 补 *.journal.log；master 双同步 b033727。
- **九轮累计**：每轮 CI 均暴露真实缺陷并实证修复（本轮新增 Docker 首绿+deb 全绿+RPM 三处 scriptlet 语义修正）；测试 100→107→109→110；run 33400673991@97ac103 待全绿。
- **第十轮 Windows 桌面分支卡死（1232fd6）**：第九轮 run 33400673991 战果——**w2-strict-linux 首绿 + w3-DEB+RPM 全绿（RPM 时序三修复实证）+ w3-Docker 连续两轮全绿**；Windows 场景 A 起即挂（隔离 EXE 240s 无健康响应、w3-iso 仅有 config 目录无 btdeck.env）。根因：**desktop_main 的 should_start_desktop_window 在 CI runner 用户态会话返回真→EXE 误入桌面伴侣 GUI 启动器等待交互→无头环境卡死**；NSSM 服务进程 SESSIONNAME 非必 "services" 同样中招（B1 listeners=0 同源）。修复：btdeck.iss 的 NSSM 服务注入 AppEnvironmentExtra=BTDECK_DESKTOP_WINDOW=0（服务形态产品级强制服务端模式）+windows.ps1 场景 A 进程级同设+EXE 输出重定向诊断兜底；契约测试 111/111。master regression（b033727）全绿。run 33404186612@1232fd6 仅重跑 Windows。
- **第十一轮 Windows cp1252 启动崩溃（36b6554）**：第十轮 EXE 输出重定向诊断兜底抓到真凶——`yamlConfig.load` 首启无 config.yaml 的正常路径 print 中文警告，西文/CI 控制台（cp1252）UnicodeEncodeError 崩溃启动链（except 分支的中文 print 二次崩上抛）。**真实生产缺陷：西文 Windows 用户 EXE 直接启动崩溃**。三层修复：yamlConfig print→logging；desktop_main 入口 reconfigure stdout/stderr 为 utf-8/replace（必须先于 app.* 导入——导入链触发 yamlConfig.load）；ps1 设 PYTHONIOENCODING=utf-8 兜底 v1.0.5 冻结夹具（其代码不可改）。新增 cp1252 子进程行为级回归（复现 CI 形态）+入口顺序契约；core 523 绿 + release 114 绿。run 33407536772@36b6554 重跑 Windows。
- **第十二轮 Windows 残留进程与诊断增强（bf1056c）**：第十一轮战果——**场景 A 首断言 PASS（cp1252 修复实证，EXE 成功启动返回身份）**；失败顺移：stop_port_freed FAIL（onefile bootloader 与 Python 子进程双 PID，单杀主 PID 留子进程占 5001→连锁二次启动/夹具失败）+ B1 NSSM 服务仍不监听（无服务侧日志）。修复：场景 A/B3 改按进程名全杀+端口释放 30s 轮询；iss 的 NSSM 服务输出落盘（AppStdout/AppStderr/RotateFiles+logs 目录 users-modify）+B1 失败 dump 服务日志与 nssm status；B3 夹具 stderr 重定向；ps1 加 BOM（本机 PS5.1 对无 BOM UTF-8 按 ANSI 误判——CI pwsh7 不受影响，语法经 ParseFile 双验证）。114/114。run 33409939531@bf1056c。
- **第十三轮 Windows B2/B3 收口（4653844）**：第十二轮战果——start_identity/stop_port_freed/**setup_silent_install（NSSM 服务）三 PASS**；剩 B2（服务态时序假阴性：重装后 Start-Sleep 5 秒即查 Status）、B3（v1.0.5 夹具 stderr 实测仍 cp1252 崩 lifespan:280 中文 print——**CI 上 PowerShell $env: 继承对该进程未生效**，本机同构实验继承正常，差异未解明故弃解释改硬保证）。修复：B3 经 cmd /c "set PYTHONIOENCODING=utf-8&& exe" shell 层注入（本机实证子进程 ENV/ENC 均 utf-8，不依赖继承链）；B2 先 Wait-Health 再判服务态+失败 nssm start 兜底；B3 停止后端口释放等待防夹具残留阻塞 B4 升级。114/114。run 33412326917@4653844。
- **第十四轮 Windows secret 文件与 B3 三路防护（33913e1）**：第十三轮战果——B1 PASS 稳定；B2 **四条件全真却 FAIL**（services=1 status=Running secretStable=True health=True）——真相：**Windows EXE 形态密钥在 config.yaml（security 段），btdeck.env 是 deb/rpm postinst 概念在 Windows 下不存在**→secretB1/B2 双 null 假 stable，`$null -ne $secretB1` 断言挂（场景 A 的 restart_secret_stable 同因）。B3 cmd 注入未解明仍 cp1252。修复：全部 secret 指纹改 hash(config\config.yaml)（frozen 路径实证 EXE 同级）；B3 去 stderr 重定向——**windowed EXE 无句柄时 sys.stdout/stderr=None，CPython print 对 None 流静默返回不崩**（十二轮加的重定向反而制造 cp1252 崩溃流）+PYTHONUTF8=1/PYTHONIOENCODING 双保险+失败诊断改列目录/进程。111/111。run 33414373967@33913e1。
- **第十五轮 Windows 诊断强化（265cc6b）**：第十四轮战果——**B1/B2/B4 升级/B5 卸载四 PASS**（secret 文件修正实证：B2 四条件全真→PASS）；剩 A 二次启动（十四轮零输出，最强假设：**首启写出的 config.yaml 在二次加载路径触发崩溃=真实用户重启场景**）与 B3 夹具（config.yaml 已写出=print 静默实证，但进程退出无输出）。强化：A 二次启动加输出重定向；B3 改 wrapper.bat（同 cmd 实例内 set，无跨进程传递环节——区别于 Start-Process 参数式 /c set 在 CI 实测未生效）+2> 保留 stderr。111/111。run 33416266061@265cc6b。
- **第十六轮 v1.0.5 夹具编码垫片（f1a7905）**：第十五轮战果——**7/8 phase PASS（A 首启/停止/二次启动 secret 稳定 + B1/B2/B4 升级/B5 卸载全绿）**，仅剩 v105_fixture_seeded。stderr 铁证：wrapper.bat 内 set PYTHONUTF8=1+PYTHONIOENCODING=utf-8 仍 cp1252 崩——**PyInstaller bootloader 对 frozen app 隔离 PYTHON* 环境变量**（十二~十五轮 env 注入全路线实证无效：PS 继承/参数式 /c set/bat 内 set）。修复：CI 夹具构建步骤注入 desktop_main 启动编码垫片（等价 v1.0.6 reconfigure 修复；与 Linux 夹具 R9 热修同型 reconstructed 语义，YAML here-string 顶格 + anchor 行经 ParseFile/YAML 双验证）。master 双同步 eeea267。run @f1a7905。
- **第十七~十八轮 B4 升级卡点与 print 静默（3095d61→193ffd4）**：第十六轮战果——**夹具垫片生效，v105_fixture_seeded PASS（7/8）**；第十七轮 B4 诊断实证：服务 SERVICE_RUNNING、stderr 推进到"成功加载 13 个定时任务"后无 Uvicorn running（卡 lifespan 后段），stdout.log 全空。真相分层：**logging 走 C 层 fd2（stderr.log 有内容）而 print 走 Python 层 sys.stdout——windowed 打包下 PyInstaller 不传 stdout 句柄，sys.stdout=None，print 全部静默丢弃**（服务可观测性产品级缺陷）。修复：desktop_main 入口 stdout 接力到 stderr（stderr 句柄存在时）+夹具垫片同步；下轮 B4 卡点在 stderr 可见。master 双同步 b3885d5。run @193ffd4。
- **第十九~二十一轮 B4 端口占用根因闭环（72ff3e2→930a352→e8ec9ed）**：十九轮 DIAG 转义 bug（\" 字面量使 ForEach-Object 崩+ErrorActionPreference=Stop 终止脚本）；二十轮修复后**归档日志铁证**：服务 Application startup complete 后 **bind 5001 Errno 10048 → NSSM 反复重启循环**（4 对轮转归档）。根因：**v1.0.5 夹具经 wrapper.bat（十五轮引入）启动后进程名为 btdeck-v105-fixture.exe，Stop-BtDeckProcesses 的精确名 btdeck 匹配杀不掉**→夹具残留 serving v1.0.5 契约（无 version）→B4 的 version 谓词永不满足+新服务 bind 失败。B4 曾在十六轮前偶过=无 wrapper 直启（进程名 btdeck.exe 可被杀）。修复：Get-Process btdeck* 通配。run @e8ec9ed。

### 2026-09-01：W3 收口达成——三平台生命周期门禁全部 CI 全绿（.5/.6/.7 → done）

- **终局战报**：w3-lifecycle-linux（run 33400673991@97ac103，DEB/RPM 四场景全 PASS）+ w3-lifecycle-docker（同 run 9 phase 全 PASS，194e5d0 起连续多轮绿）+ **w3-lifecycle-windows（run 33504251419@e8ec9ed，8/8 phase 全 PASS）**；附加 w2-strict-linux 同批次首绿。第二十一轮通配修复后 Windows 一次通过。
- **.5/.6/.7 置 done**（feature_list evidence 已填：各自 CI run、phase 清单、全部根因修复清单）。
- **W3 累计（第七~二十一轮，14 个 commit 194e5d0→e8ec9ed）**：修复 6 类平台缺陷/16 个独立根因，其中真实生产缺陷 7 个——西文 Windows EXE 启动崩溃（cp1252 print）、NSSM 服务误入桌面 GUI、Windows 服务启动日志缺失一半（stdout None 静默）、RPM 升级 scriptlet 时序（%post(新)先于%preun(旧)与 DEB 相反）三连、v1.0.5→v1.0.6 RPM 升级停摆（旧 prerm 无条件 stop+disable，runbook 记手动 enable --now）、PyInstaller Windows datas 反斜杠归档名、锁缺 tzdata。测试 100→114（+四组契约/行为回归：Windows 传递依赖入锁、v1.0.5 谓词、sysd python3、retag 链式、反斜杠规范化、cp1252 子进程、NSSM 服务模式）。
- **关键方法论沉淀**：①CI 失败要逐层剥洋葱（本轮从"以为是缓存"剥到 16 个真根因，每轮诊断输出重定向都换回下一层真相）；②frozen app 的 PYTHON* env 被 PyInstaller bootloader 隔离（env 注入三路线全败实证，修复必须走代码垫片）；③DEB/RPM 升级 scriptlet 时序相反是包管理器的经典陷阱；④windowed 打包的 stdout=None print 静默是可观测性黑洞（logging 走 fd2 有输出、print 全丢——诊断时两者要分开看）。
- **master 同步**：workflow 注册副本三轮双同步（5975aa1/b033727/b3885d5），master regression 全绿。
- **下一步**：W4 黑盒契约（task .8）按批次纪律先出方案；.9（W5/W6）最后。

### 2026-09-01（续）：W4 批次 A 落地——黑盒契约测试器 + 跨制品 CI 接入

- **contract_runner.py**（scripts/release/）：纯 stdlib、禁 import app.*（铁律静态测试强制）；C01 健康 Identity 精确值（G1 等价对象，artifactKind 排除——包型身份天然不同）+C02 OpenAPI 指纹（DEV 形态 /api/v1/openapi.json，生产形态按 W11 安全设计关闭→unavailable 降级仍可比）+C03 认证全链路（错误码/登录/info/refresh/logout/token 失效）+C04 改密持久化（oldPassword/newPassword base64+userId 必填占位）；快照只留结构+身份字段（滤 token/secret/user_id 实例特定值）。
- **compare_snapshots.py**：逐路径 diff（missing/mismatch/extra）+exceptions 白名单强制（禁 */吞段规则、expires 过期即红、stale 规则报告防腐化）；release/equivalence-exceptions.json schema（当前空集=完全等价）。
- **测试 14 例**：铁律（禁 import app.*）、规范化纯函数、内嵌 mock server 端到端（含 token 唯一性状态机）、变异检出（version 改动→diff 报红）、compare 规则负向（宽泛/过期拒绝）；release 套件 125/125。
- **本地实证**：隔离双实例（各自全新 CONFIG_DIR/DB/secret 的同源码服务）C01~C04 快照 compare **total_diffs=0**——规范化设计正确性实证；真实实例冒烟修正两契约细节（openapi 路径、userId 必填）。证据 release/evidence/w4/。
- **CI 接入**：release-gate.yml 增 w4-contract job（run_w4_contract 输入）——同 SHA 构建 deb/rpm/docker→debian/rocky systemd 容器+compose 三独立实例各跑 runner→deb 基准 compare（fail-closed）+artifact 归档；bash -n+YAML 双校验；master 双同步 8ad4c7c。提交链 c1d022b（批次 A 代码）→8d2ea28（CI 接入）。
- **批次 B 待做**：C05~C12（受控 qB/TR stub、查询模板、定时任务、通知审计、迁移重启、SPA、路径边界）+变异注入演练（G8 退出门）。

### 2026-09-01（续三）：W4 批次 B1 全绿——八场景跨制品黑盒契约等价（task .8 in-progress）

- **终局**：w4-contract job 三轮迭代全绿（最后一轮）——**八场景（C01~C04+C07/C08/C09/C11）**三制品快照 compare **rpm/docker 双候选 total_diffs=0、零豁免**。
- **B1 新场景**：C07 查询模板全生命周期（create/update/delete/list，真实前缀 /api/v1/advanced-search + 列表 data 直接数组契约）、C08 定时任务 13 种子任务名集合、C09 通知审计分页形状+操作类型枚举、C11 SPA（index/资源 manifest/fallback）。真实契约探测修正三处 data_of 首元素语义与直接数组端点的冲突；_auth_token 区分不可达与认证失败。
- **C11 部署形态语义**：deb/rpm 二进制内嵌前端（backend 直出 SPA），docker 部署由独立 frontend nginx 提供——runner 增 --spa-base-url（docker 指向 w3-life-frontend），比对同一唯一前端构建；期间发现 nginx 本有 try_files fallback、index 已匹配仅 fallback 请求残打 base_url（替换被 black 折行吞掉未 assert——**批量 replace 必须 assert 教训第三次**）。
- **本地实证**：真实双实例 B1 total_diffs=0（清掉手动 probe 残留后）；mock 扩 B1 路由（模板状态机+PUT/DELETE+SPA+通知审计）16 测试全绿；release 127/127。
- evidence：release/evidence/w4/（B1 三制品快照+报告+三轮 CI 日志+本地双实例快照）。**B2 待做**：C05/C06（qB/TR stub）、C10（重启编排）、C12（路径边界）+制品级变异注入演练。
