/**
 * 移动端四级删除共享文案（2026-09-05 移动验收补齐）：
 * 列表页与详情页执行 deleteTorrentsWithLevel 后的成功提示单源维护。
 * 等级语义与后端 /torrents/delete-with-level 对齐（1=完全删除, 2=删任务保数据,
 * 3=回收站, 4=待删除标签）。
 */
export const DELETE_LEVEL_SUCCESS_TEXT: Record<number, string> = {
  4: '已标记为待删除',
  3: '已移至回收站，可从回收站恢复',
  2: '已删除任务（数据已保留）',
  1: '已完全删除'
}
