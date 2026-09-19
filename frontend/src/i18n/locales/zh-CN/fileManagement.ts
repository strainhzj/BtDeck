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
 * 种子文件管理页文案（fileManagement 组，P6-1）。
 *
 * 覆盖 FileManagement.vue（备份列表/详情弹窗/批量导入/下载删除链路）。
 * zh 值与原内联中文逐字节一致。
 */
export const fileManagement = {
  title: '种子文件管理',
  subtitle: '管理种子文件备份，支持去重、导出、导入操作',
  filter: {
    aria: '种子文件筛选条件',
    searchLabel: '任务名称 / Info Hash',
    searchPlaceholder: '搜索任务名称或Info Hash...',
    downloaderLabel: '下载器',
    downloaderPlaceholder: '全部下载器',
    dateLabel: '创建时间',
    dateSeparator: '至',
    dateStart: '开始日期',
    dateEnd: '结束日期',
    search: '搜索',
    reset: '重置'
  },
  toolbar: {
    dedupe: '去重',
    export: '导出',
    import: '导入'
  },
  table: {
    loading: '加载中...',
    name: '任务名称',
    downloader: '下载器',
    uploadedAt: '上传时间',
    updatedAt: '最后更新',
    actions: '操作',
    detail: '详情',
    download: '下载',
    delete: '删除'
  },
  detailDialog: {
    title: '种子文件详情',
    name: '任务名称',
    downloader: '下载器',
    filePath: '文件路径',
    uploadedAt: '上传时间',
    updatedAt: '最后更新',
    uploadedBy: '上传用户',
    close: '关闭',
    download: '下载文件'
  },
  importDialog: {
    title: '批量导入种子文件',
    downloaderLabel: '目标下载器',
    downloaderPlaceholder: '请选择下载器',
    fileLabel: '种子文件',
    dropPrefix: '将文件拖到此处，或',
    dropAction: '点击上传',
    tip: '只能上传 .torrent 文件，支持批量上传',
    cancel: '取消',
    confirm: '确定导入'
  },
  msg: {
    operationSuccess: '操作成功',
    dedupeFailed: '去重失败',
    selectExport: '请先选择要导出的种子文件',
    exportSuccess: '导出成功',
    selectDownloader: '请选择目标下载器',
    selectImportFiles: '请选择要导入的种子文件',
    invalidFile: '请选择有效文件',
    importPartialFailed: '部分文件导入失败:\n{list}',
    importFailed: '导入失败',
    sessionRenewed: '登录已续期，请重新上传',
    uploadFailedRetry: '上传失败，请稍后重试',
    uploadFailed: '上传失败',
    downloadSuccess: '下载成功',
    authFailed: '认证失败，请重新登录',
    fileNotFound: '种子文件不存在',
    downloadFailedWithStatus: '下载失败: {status}',
    networkError: '网络错误，请检查网络连接',
    downloadFailedRetry: '下载失败，请稍后重试',
    deleteConfirm: '确认删除该种子文件备份吗？',
    confirmTitle: '提示',
    confirmButton: '确定',
    cancelButton: '取消',
    deleteSuccess: '删除成功',
    deleteFailed: '删除失败'
  }
}
