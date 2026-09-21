/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * 回收站域文案（recycleBin 组，双语 P5）。
 *
 * zh 值与原内联中文逐字节一致（零回归）；R03～R05 危险语义（可恢复/降级/不可撤销）
 * 审校清单见 PLANS/bilingual/delete-level-review.md。
 */
export const recycleBin = {
  title: '回收站',
  subtitle: '管理已删除的种子，支持还原或永久删除',
  filter: {
    title: '筛选条件',
    description: '按名称搜索回收站中的种子',
    nameLabel: '种子名称',
    searchPlaceholder: '搜索种子名称...',
    search: '搜索',
    reset: '重置'
  },
  toolbar: {
    restore: '还原',
    delete: '删除',
    cleanupPreview: '清理预览',
    refresh: '刷新列表',
    clearAll: '清空回收站',
    manualUpload: '手动上传还原'
  },
  table: {
    name: '种子名称',
    status: '状态',
    size: '大小',
    deletedAt: '删除时间',
    downloader: '所属下载器',
    path: '原路径',
    actions: '操作',
    restore: '还原',
    delete: '删除',
    restorable: '可还原',
    notRestorable: '不可还原',
    loading: '加载中...'
  },
  empty: {
    text: '回收站为空',
    hint: '删除的种子会显示在这里'
  },
  previewDialog: {
    title: '清理预览',
    cleanBefore: '清理',
    daysUnit: '天前的种子',
    preview: '预览',
    countLabel: '种子数量：',
    sizeLabel: '总大小：',
    colName: '种子名称',
    colSize: '大小',
    colDeletedAt: '删除时间',
    colPath: '原路径',
    cancel: '取消',
    confirm: '确认清理'
  },
  manualDialog: {
    title: '手动上传种子文件还原',
    torrentIdLabel: '种子ID',
    torrentIdPlaceholder: '请输入要还原的种子ID',
    fileLabel: '种子文件',
    chooseFile: '选择种子文件',
    fileTip: '只能上传.torrent文件，且不超过10MB',
    noticeTitle: '提示',
    notice: '当种子文件备份不存在时，可以手动上传种子文件进行还原',
    cancel: '取消',
    confirm: '开始还原'
  },
  confirmDialog: {
    danger: '⚠️ 危险操作',
    cancel: '取消',
    confirm: '确认',
    batchRestoreTitle: '批量还原',
    batchRestoreMessage: '确定要还原选中的 {count} 个种子吗？',
    batchRestoreDetail: '还原操作将重新添加种子到下载器，并清除删除标记。',
    batchDeleteTitle: '批量删除',
    batchDeleteMessage: '确定要永久删除选中的 {count} 个种子吗？',
    batchDeleteDetail: '此操作不可撤销，种子将被永久删除！',
    cleanupTitle: '确认清理',
    cleanupMessage: '确定要清理 {count} 个种子吗？',
    cleanupDetail: '释放空间：{size}',
    restoreTitle: '还原种子',
    restoreMessage: '确定要还原 "{name}" 吗？',
    restoreDetail: '种子将被重新添加到下载器。',
    deleteTitle: '删除种子',
    deleteMessage: '确定要永久删除 "{name}" 吗？',
    deleteDetail: '此操作不可撤销，种子将被永久删除！',
    clearAllTitle: '清空回收站',
    clearAllMessage: '确定要清空回收站吗？',
    clearAllDetail: '此操作将永久删除回收站中的所有 {count} 个种子，不可撤销！'
  },
  msg: {
    getListFailed: '获取回收站列表失败',
    previewFailed: '获取预览失败',
    noCleanable: '没有可清理的种子',
    cleanupSuccess: '清理成功',
    cleanupFailed: '清理失败',
    refreshSuccess: '刷新成功',
    binEmpty: '回收站为空',
    clearAllFailed: '清空回收站失败',
    enterTorrentId: '请输入种子ID',
    chooseFile: '请选择种子文件',
    invalidFile: '种子文件对象无效',
    restoreSuccess: '还原成功',
    restoreFailed: '还原失败',
    manualPartial: '部分成功：成功{success}个，失败{failed}个',
    manualRestoreFailed: '手动还原失败',
    restoreSuccessCount: '还原成功：共{count}个种子',
    restoreFailedCount: '还原失败：共{count}个种子',
    restorePartial: '还原部分成功：成功{success}个，失败{failed}个',
    deleteSuccessCount: '删除成功：共{count}个种子',
    deleteFailedCount: '删除失败：共{count}个种子',
    deletePartial: '删除部分成功：成功{success}个，失败{failed}个',
    deleteFailed: '删除失败'
  }
}
