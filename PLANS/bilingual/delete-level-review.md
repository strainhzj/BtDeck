# 四级删除与回收站危险操作双语审校清单（P5，R01～R05）

> 状态：**待用户逐条签认**（M1 门禁要求：危险操作英文表达经业务负责人人工签认后才算通过）。
> 依据：terminology.md §3 危险操作红线——等级数字 + 影响对象 + 不可恢复性三要素齐备；取消零副作用。
> zh 文案全部冻结（与原内联中文逐字节一致，零回归原则）；本清单审校的是 **en 表达是否准确传达危险语义**。
> 落键位置：`torrent.deleteLevel.*` 与 `recycleBin.*`（zh-CN/en 成对，parity 门禁钉住）。

## 一、四级删除确认框（R01～R04）

| ID | 等级 | 场景 | zh（冻结） | en（待签认） | 三要素核对 |
|---|---|---|---|---|---|
| C-L1-S | 等级1 | 单个 | 警告：此操作将完全删除，是否继续？ | Level 1 - Permanently delete this torrent and its data files? This cannot be undone. | ✅号/✅对象+数据文件/✅不可逆 |
| C-L1-B | 等级1 | 批量 | 确定要将选中的 {count} 个种子完全删除吗？ | Level 1 - Permanently delete {count} selected torrents and their data files? This cannot be undone. | ✅号/✅对象+数量/✅不可逆 |
| C-L2-S | 等级2 | 单个 | 确定要将种子删除任务（保留数据）吗？ | Level 2 - Remove this torrent from the downloader? Its data files will be kept. | ✅号/✅任务移除+✅数据保留 |
| C-L2-B | 等级2 | 批量 | 确定要将选中的 {count} 个种子删除任务（保留数据）吗？ | Level 2 - Remove {count} selected torrents from the downloader? Their data files will be kept. | ✅号/✅对象+数量/✅数据保留 |
| C-L3-S | 等级3 | 单个 | 警告：此操作将移至回收站，是否继续？ | Level 3 - Move this torrent to the recycle bin? It can be restored from there later. | ✅号/✅可恢复路径明示 |
| C-L3-B | 等级3 | 批量 | 确定要将选中的 {count} 个种子移至回收站吗？ | Level 3 - Move {count} selected torrents to the recycle bin? They can be restored from there later. | ✅号/✅对象+数量/✅可恢复 |
| C-L4-S | 等级4 | 单个 | 确定要将种子标记为待删除吗？ | Level 4 - Mark this torrent as pending deletion? Nothing is removed yet. | ✅号/✅仅标记不删除 |
| C-L4-B | 等级4 | 批量 | 确定要将选中的 {count} 个种子标记为待删除吗？ | Level 4 - Mark {count} selected torrents as pending deletion? Nothing is removed yet. | ✅号/✅对象+数量/✅仅标记 |

**审校重点**：
1. 等级1 的 "and its data files" + "cannot be undone" 是否足够醒目（是否需要更强警告词，如 "⚠ DANGER"）；
2. 等级2 的 "Remove ... from the downloader" 是否会被误解为卸载下载器（备选："Remove the torrent task from the downloader"）；
3. 等级3 的 "It can be restored from there later"——实际存在**备份失败降级**路径（见 D-GR），降级后不可恢复；确认句是否需要弱化为 "It can usually be restored later"；
4. zh 文案本身未含等级号与不可逆提示（历史冻结），如需对齐 en 三要素请单独拍板（属 zh 文案变更，非本批范围）。

## 二、删除结果链路（R02/R04/R05）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| D-DONE | 批量完成 | 批量删除完成，成功删除 {count} 个种子 | Batch deletion finished: {count} torrents deleted |
| D-DONE-M | 批量完成（部分文件缺失） | 批量删除完成，成功删除 {count} 个种子（其中 {missing} 个未找到文件，已跳过文件操作） | Batch deletion finished: {count} torrents deleted ({missing} had no files on disk; file operations were skipped) |
| D-PART | 部分成功 | 批量删除部分完成：成功 {success} 个，失败 {failed} 个 | Batch deletion partially finished: {success} succeeded, {failed} failed |
| D-FAIL | 全部失败 | 批量删除失败：{error} | Batch deletion failed: {error} |
| D-FAIL-D | 失败详情 | 以下种子删除失败：{names}（>5 个时：… 等{count}个） | The following torrents failed to delete: {names}（>5 个时：… and {count} more） |
| D-SYNC-N | 等级 N 同步完成 | 等级{level}删除完成，成功 {count} 个 | Level {level} deletion finished: {count} torrents succeeded |
| D-SYNC-PART | 同步部分失败 | 删除完成：失败 {count} 个 | Deletion finished: {count} failed |
| D-GR | 等级3 备份失败降级为等级4 | 已将 {count} 个种子降级为等级4删除（备份失败）+ 详情 | {count} torrents were downgraded to Level 4 deletion (backup failed) + Backup failed for the following torrents; they were downgraded to Level 4: {names} |
| D-FM | 等级3 文件缺失直接入回收站 | 以下种子未找到文件，已跳过文件操作直接移入回收站：{names} | No files were found for the following torrents; file operations were skipped and they were moved to the recycle bin directly: {names} |
| D-SKIP | 跳过处理中种子 | 已跳过 {count} 个正在处理的种子 | Skipped {count} torrents that are already being processed |
| D-ALREADY | 全部已在处理 | 所选种子均已在删除任务中处理 | All selected torrents are already being handled by a deletion task |
| D-ACCEPT | 提交受理（E14，不报已完成） | 批量删除任务已提交，正在后台执行 | Batch deletion task submitted and running in the background |

**审校重点（R05：202 不报完成）**：D-ACCEPT 文案必须保持「已提交/后台执行」语义，禁止出现 finished/deleted 字样——现行 en ✓；D-PART/D-SYNC-PART 必须明示失败计数，不允许只报成功——现行 en ✓。

## 三、回收站（R03～R05）

| ID | 场景 | zh（冻结） | en（待签认） |
|---|---|---|---|
| RB-RESTORE | 批量还原确认 | 确定要还原选中的 {count} 个种子吗？+ 还原操作将重新添加种子到下载器，并清除删除标记。 | Restore the {count} selected torrents? + Restoring will re-add the torrents to their downloaders and clear the deletion marker. |
| RB-DEL | 批量永久删除确认 | 确定要永久删除选中的 {count} 个种子吗？+ 此操作不可撤销，种子将被永久删除！ | Permanently delete the {count} selected torrents? + This cannot be undone. The torrents will be deleted permanently! |
| RB-DEL-1 | 单条永久删除 | 确定要永久删除 "{name}" 吗？+ 同上 | Permanently delete "{name}"? + This cannot be undone. The torrent will be deleted permanently! |
| RB-CLEANUP | 按天数清理确认 | 确定要清理 {count} 个种子吗？+ 释放空间：{size} | Clean up {count} torrents? + Space to free: {size} |
| RB-CLEAR | 清空回收站（v-if=false 当前隐藏） | 确定要清空回收站吗？+ 此操作将永久删除回收站中的所有 {count} 个种子，不可撤销！ | Empty the recycle bin? + This will permanently delete all {count} torrents in the recycle bin. This cannot be undone! |
| RB-STATUS | 可还原/不可还原徽标 | 可还原 / 不可还原 | Restorable / Not restorable |
| RB-RESULT | 还原/清理结果三态 | 还原成功：共{count}个种子 / 还原失败：共{count}个 / 还原部分成功：成功{success}个，失败{failed}个 | Restore finished: {count} torrents restored / Restore failed: {count} torrents / Restore partially finished: {success} succeeded, {failed} failed |
| RB-STUB | 手动还原未开放（E16） | 功能开发中，请稍后再试（501 + NOT_IMPLEMENTED） | This feature is not available yet |

**审校重点（R03/R04）**：RB-DEL 系列的 "deleted permanently" + "cannot be undone" 双重明示；RB-CLEANUP 的 {size} 让用户知道释放多少空间；RB-STATUS 中 dr=1 的「不可还原」语义（备份已不存在，restore 会失败）用 Not restorable 是否达意。

## 四、签认记录

| 项 | 状态 |
|---|---|
| C-L1-S ～ C-L4-B（8 条确认框） | ⬜ 待签认 |
| D-DONE ～ D-ACCEPT（12 条结果链路） | ⬜ 待签认 |
| RB-RESTORE ～ RB-STUB（8 条回收站） | ⬜ 待签认 |
| 审校重点 4+2+3 条议题 | ⬜ 待拍板 |

> 签认方式：逐条确认或整体确认（可附修改意见，修改后重走 parity 门禁与相关单测）。
> 浏览器人工验收（R01～R05 实操 + V02 视觉）在签认后随 P5 收口批执行。
