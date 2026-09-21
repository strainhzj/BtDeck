# 孤儿文件危险操作双语审校清单（P6，R06）

> 状态：**待用户逐条签认**（M2 门禁要求：危险操作英文表达经业务负责人人工签认后才算通过；R01～R05 清单见 delete-level-review.md）。
> 依据：主计划 §6 R06 红线——**发现/隔离/恢复/清理不得混译成同一个 Delete**；硬链接等特殊影响必须按后端实际语义解释，禁止臆测。
> zh 文案全部冻结（与 P6-4b 落键逐字节一致，零回归原则）；本清单审校的是 **en 表达是否准确传达危险语义**。
> 落键位置：`orphanFiles.*`（zh-CN/en 成对，parity 门禁钉住）。
> 后端契约：audit_logs/orphan_files 全端点 reasonCode（P6-4b，E14 rejected 双形态）；动态诊断只进日志。

## 术语对照（R06 红线：三个「删除」必须区分）

| 中文 | en | 后端语义（禁止混译） |
|---|---|---|
| 清理（孤儿文件） | **clean up / cleanup** | 把孤儿文件移入隔离区（quarantine），**可恢复** |
| 彻底删除（隔离区） | **permanently delete** | 从隔离区物理删除文件，**不可恢复** |
| 删除（硬链接副本） | **delete (the hard-link copy)** | 仅移除一个路径链接，数据仍由源文件 inode 保留 |
| 忽视 / 取消忽视 | **ignore / unignore** | 标记不再参与清理，不动文件 |
| 恢复 | **restore** | 从隔离区移回原位置 |
| 隔离区 | **quarantine** | 清理动作的落脚点，非回收站（recycle bin 是种子域） |

## 一、清理链路（发现 → 清理，R06 主场景）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| OF-C-T | 清理确认框标题 | 确认清理以下孤儿文件？此操作不可恢复！ | Clean up the following orphan files? This cannot be undone! |
| OF-C-B | 确认按钮 | 确认清理 | Clean Up |
| OF-C-LOW | 低置信度 alert 正文 | 低置信度文件有误判风险（可能并非真正的孤儿）。确认清理前请核对路径，避免误删用户数据。 | Low-confidence files may be misjudged (they might not be true orphans). Verify the paths before confirming cleanup to avoid deleting user data by mistake. |
| OF-C-LOWT | 低置信度计数标题 | 其中 {count} 个为低置信度（离线降级目录粗筛判定） | {count} of them are low-confidence (offline degraded-directory coarse check) |
| OF-C-WARN | 确认框内低置信度行 | ⚠️ 其中 {count} 个为低置信度，有误判风险，请核对路径 | ⚠️ {count} of them are low-confidence and may be misjudged; verify the paths |
| OF-C-SUB | 提交受理（异步，不报完成） | 主动清理任务已提交（{taskId}）{skipped}，完成或失败后将在通知中心提醒 | Cleanup task submitted ({taskId}){skipped}; the result will arrive via Notification Center |
| OF-C-EMPTY | 选中但无可清理项 | 所选文件均无可清理项：可能是低置信度（需等下载器上线精筛）、已忽视（需先取消忽视）或已清理。 | None of the selected files are cleanable: they may be low-confidence (waiting for the downloader to come online for a precise check), ignored (unignore first), or already cleaned. |
| OF-C-BUSY | 全部处理中 | 所选孤儿文件均已在主动清理任务中处理 | All selected orphan files are already being processed by a cleanup task |

**审校重点**：①OF-C-T 的 zh「此操作不可恢复」与术语表「清理=可恢复」**表面矛盾**——实际语义是「清理动作本身不可撤销（无法一键还原），文件进隔离区后可另行恢复」；en 用 "cannot be undone" 表达动作不可撤销，是否需要补 "(files go to quarantine)" 消歧待拍板；②OF-C-LOW/OF-C-WARN 的「误判风险」译 may be misjudged 是否达意。

## 二、置信度体系（R06：按后端实际判定方式解释，禁止臆测）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| OF-CONF-H/L | 置信度标签 | 高置信度 / 低置信度 | High confidence / Low confidence |
| OF-CONF-TAG | 标签短形态 | 高 / 低 / 混合 | High / Low / Mixed |
| OF-CONF-HT | 高置信度 tooltip | 在线精筛判定，确认未被任何种子引用 | Judged by the online precise check and confirmed unreferenced by any torrent |
| OF-CONF-LT | 低置信度 tooltip | 离线降级目录粗筛判定，有误判风险；手动清理可删，自动清理需等下载器上线精筛 | Judged by the offline degraded-directory coarse check and may be misjudged; manual cleanup can delete it, while automatic cleanup waits for the downloader to come online for a precise check |
| OF-CONF-FH/FL | 文件夹级 tooltip | 文件夹内全部为在线精筛判定… / 文件夹内含…低置信度项，有误判风险 | All files in the folder passed the online precise check… / The folder contains low-confidence items…which may misjudge |

**审校重点**：①「在线精筛 / 离线降级目录粗筛」译 online precise check / offline degraded-directory coarse check——"degraded-directory" 是直译，备选 "offline fallback directory scan"；②「未被任何种子引用」unreferenced by any torrent 是否需要更口语（not used by any torrent）。

## 三、忽视 / 取消忽视（不动文件的标记操作）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| OF-I-C | 确认框 | 确认{action}选中的 {count} 个孤儿文件？ | {action} the {count} selected orphan files? |
| OF-I-A | 动作词 | 忽视 / 取消忽视 | Ignore / Unignore |
| OF-I-DONE/PART/FAIL | 结果三态 | {action}完成：成功 {count} 个 / {action}部分完成：成功 {success} 个，失败 {failed} 个 / {action}失败：{count} 个文件未处理 | {action} finished: {count} succeeded / {action} partially finished: {success} succeeded, {failed} failed / {action} failed: {count} files left unprocessed |

## 四、快捷操作（按路径前缀，strong 分片五键）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| OF-Q-T | 两模式标题 | 快捷删除（按前缀）/ 快捷忽视（按前缀） | Quick Clean-up (by prefix) / Quick Ignore (by prefix) |
| OF-Q-N | 说明行（五分片） | 输入路径前缀（绝对路径开头），将匹配所有**文件路径** 以此开头的**待清理**文件（排除已忽视/已清理）。 | Enter a path prefix (the start of an absolute path); it matches all **file paths** starting with it that are **pending cleanup** (excluding ignored/cleaned). |
| OF-Q-NOTE | 删除语义注 | 删除即移入隔离区，可恢复。 | Deletion moves files into quarantine and is recoverable. |
| OF-Q-PH | 前缀占位符 | 例如：D:\downloads\待清理目录\ 或 /data/leak/ | e.g. D:\downloads\to-clean\ or /data/leak/ |

**审校重点**：OF-Q-NOTE 的 zh「删除」承接入口按钮「快捷删除」，en 入口为 Quick Clean-up 但注解写 "Deletion"——是否统一为 "Clean-up moves files into quarantine and is recoverable." 待拍板。

## 五、隔离区（恢复 / 彻底删除，R06 高危）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| OF-QR-TAB | 页签名 | 隔离区 | Quarantine |
| OF-QR-RC | 恢复确认 | 确认恢复选中的文件到原位置？ | Restore the selected files to their original locations? |
| OF-QR-RD | 恢复结果 | 恢复完成：成功 {count} 个（失败追加 ，失败 {count} 个） | Restore finished: {count} succeeded (, {count} failed) |
| OF-QR-RR | 恢复被拒绝（E14 双形态） | 恢复被拒绝 | Restore rejected |
| OF-QR-PC | 彻底删除确认 | 确认彻底删除选中的文件？此操作不可恢复，文件将被永久删除！ | Permanently delete the selected files? This cannot be undone; the files will be deleted forever! |
| OF-QR-PT | 确认框标题 | 彻底删除确认 | Permanent Deletion Confirmation |
| OF-QR-PS | 提交受理（异步） | 彻底删除任务已提交（{taskId}）{skipped}，完成或失败后将在通知中心提醒 | Permanent deletion task submitted ({taskId}){skipped}; the result will arrive via Notification Center |
| OF-QR-PB | 全部处理中 | 所选隔离文件均已在彻底删除任务中处理 | All selected quarantined files are already being processed by a deletion task |
| OF-QR-PA | 「预计删除」列 | 预计删除 | Scheduled Deletion |

**审校重点**：①OF-QR-PC 双重明示（cannot be undone + deleted forever）✓；②「预计删除」列名 Scheduled Deletion 表达的是「保留期到期后自动物理删除」，是否改为 "Auto-delete At"/"Deletion Due" 待拍板。

## 六、硬链接副本（R06：按 inode 语义解释，禁止臆测）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| OF-HL-DC | 删除副本确认（三行） | 确认删除硬链接副本？\n{path}\n此操作不可恢复：仅移除该路径链接，数据仍由源文件保留；位于种子目录内的副本会被拒绝删除。 | Delete this hard-link copy?\n{path}\nThis cannot be undone: only the link at this path is removed and the data stays with the source file; copies inside torrent directories are rejected. |
| OF-HL-DT | 确认框标题 | 删除副本确认 | Delete Copy Confirmation |
| OF-HL-DD | 成功 | 已删除副本：{path} | Copy deleted: {path} |
| OF-HL-PART | 部分失败（E01） | 部分副本删除失败，明细详见控制台日志 | Some copies failed to delete; see the console log for details |

**审校重点**：OF-HL-DC 的「此操作不可恢复」指**该路径链接的移除不可撤销**（数据不动）——en 用 "This cannot be undone: only the link … is removed and the data stays with the source file" 已先行限定；「位于种子目录内的副本会被拒绝删除」对应后端 guardrail（安全护栏主动拒绝），en 用被动 "are rejected" 是否需要点名动作方（the server rejects…）待拍板。

## 七、状态标签（稳定码位）

| ID | zh（冻结） | en（待签认） |
|---|---|---|
| 状态四态 | 待清理 / 已忽视 / 已清理 / 混合 | Pending cleanup / Ignored / Cleaned / Mixed |

## 八、签认记录

| 项 | 状态 |
|---|---|
| OF-C-T ～ OF-C-BUSY（清理链路 8 条） | ⬜ 待签认 |
| OF-CONF-*（置信度 6 条） | ⬜ 待签认 |
| OF-I-*（忽视 5 条） | ⬜ 待签认 |
| OF-Q-*（快捷操作 4 条） | ⬜ 待签认 |
| OF-QR-*（隔离区 9 条） | ⬜ 待签认 |
| OF-HL-*（硬链接 4 条） | ⬜ 待签认 |
| 状态标签 1 条 | ⬜ 待签认 |
| 审校重点议题（6 条） | ⬜ 待拍板 |

> 签认方式：逐条确认或整体确认（可附修改意见，修改后重走 parity 门禁与相关单测）。
> 浏览器人工验收（R06 实操：发现/隔离/恢复/清理/彻底删除/副本删除）随 P7 收口批执行；**仅使用隔离测试目录/数据**。
