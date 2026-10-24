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
 * 种子转移 / 修改路径域文案（transfer 组，P6-1）。
 *
 * 覆盖 TransferDialog（单个转移）、BatchTransferDialog（批量转移结果）、
 * SetLocationDialog（修改保存路径）。术语依据 PLANS/bilingual/terminology.md：
 * 种子转移 = seed transfer；修改路径 = change location（动作 Set location）。
 * zh 值与原内联中文逐字节一致。
 */
export const transfer = {
  title: '转移种子',
  batchTitle: '批量转移种子（已选择{count}个）',
  currentDownloader: '当前下载器:',
  currentPath: '当前路径:',
  currentPaths: '当前路径：',
  selectedTorrents: '已选择的种子：',
  targetDownloader: '目标下载器:',
  targetDownloaderPlaceholder: '请选择目标下载器',
  targetPath: '目标路径:',
  targetPathPlaceholder: '请输入或选择目标路径',
  pathTypeDefault: '默认路径',
  pathTypeInUse: '在用路径',
  torrentCount: '({count}个种子)',
  deleteSource: '移除原下载器中的种子任务',
  deleteSourceHint: '勾选后，转移成功将移除原下载器中的种子任务，保留数据文件；移除前需再次确认。',
  cancel: '取消',
  submit: '确定',
  submitting: '转移中...',
  deleteConfirmTitle: '确认移除原种子任务',
  deleteConfirmDone: '种子已成功转移到目标下载器',
  deleteConfirmQuestion: '是否移除原下载器中的种子任务？数据文件将保留。',
  deleteConfirmIrreversible: '此操作只会移除原种子任务，数据文件仍会保留。',
  deleting: '移除中...',
  confirmDelete: '确认移除',
  continueConfirm: '勾选“移除原下载器中的种子任务”后，转移成功会移除源种子任务并保留数据文件。是否继续？',
  batchContinueConfirm: '勾选“移除原下载器中的种子任务”后，转移成功会移除源种子任务并保留数据文件。是否继续？',
  confirmActionTitle: '确认操作',
  continueButton: '继续',
  resultTitle: '批量转移完成',
  resultTotal: '总数: {count}个',
  resultSuccess: '成功: {count}个',
  resultFailed: '失败: {count}个',
  resultFailedList: '失败列表：',
  unknownError: '未知错误',
  close: '关闭',
  validate: {
    selectTargetDownloader: '请选择目标下载器',
    sameAsCurrentDownloader: '目标下载器不能与当前下载器相同',
    sameAsSelectedDownloader: '目标下载器不能与选中种子的下载器相同',
    targetPathRequired: '请输入目标路径'
  },
  msg: {
    loadDownloadersFailed: '加载下载器列表失败',
    success: '种子转移成功',
    successWithDelete: '种子转移成功，原种子任务已移除，数据文件已保留',
    failed: '种子转移失败',
    failedWith: '种子转移失败: {message}',
    failedRetry: '种子转移失败，请稍后重试',
    deleteSourceFailed: '移除原种子任务失败',
    batchDeleteSourceFailed: '移除原种子任务时发生错误，请手动检查',
    noTorrents: '未选择任何种子',
    missingSourceDownloader: '无法获取源下载器信息',
    batchFailed: '批量转移失败',
    batchFailedWith: '批量转移失败: {message}',
    deletingSource: '正在移除原种子任务...',
    batchSuccessDeleted: '批量转移完成，已成功移除 {count} 个原种子任务，数据文件已保留'
  },
  setLocation: {
    title: '修改保存路径（已选择{count}个种子）',
    moveFiles: '移动已下载的文件',
    moveFilesHint: '勾选后会将已下载的文件移动到新路径，否则仅修改保存路径不影响现有文件',
    submitting: '提交中...',
    confirmMove: '确认将 {count} 个种子移动到新路径？\n这将移动已下载的文件到: {path}',
    confirmChange: '确认修改 {count} 个种子的保存路径？\n仅修改路径，不移动文件。',
    submitted: '成功提交{moved}个种子路径修改请求，正在后台处理...',
    failed: '修改路径失败'
  }
}
