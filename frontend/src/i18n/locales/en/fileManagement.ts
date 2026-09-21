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
 * Torrent file management page copy (fileManagement group, P6-1).
 *
 * Covers FileManagement.vue: backup list, detail dialog, batch import,
 * download and delete chains.
 */
export const fileManagement = {
  title: 'Torrent File Management',
  subtitle: 'Manage torrent file backups: deduplicate, export and import',
  filter: {
    aria: 'Torrent file filters',
    searchLabel: 'Task name / Info Hash',
    searchPlaceholder: 'Search by task name or Info Hash...',
    downloaderLabel: 'Downloader',
    downloaderPlaceholder: 'All downloaders',
    dateLabel: 'Created at',
    dateSeparator: 'to',
    dateStart: 'Start date',
    dateEnd: 'End date',
    search: 'Search',
    reset: 'Reset'
  },
  toolbar: {
    dedupe: 'Deduplicate',
    export: 'Export',
    import: 'Import'
  },
  table: {
    loading: 'Loading...',
    name: 'Task name',
    downloader: 'Downloader',
    uploadedAt: 'Uploaded at',
    updatedAt: 'Last updated',
    actions: 'Actions',
    detail: 'Details',
    download: 'Download',
    delete: 'Delete'
  },
  detailDialog: {
    title: 'Torrent File Details',
    name: 'Task name',
    downloader: 'Downloader',
    filePath: 'File path',
    uploadedAt: 'Uploaded at',
    updatedAt: 'Last updated',
    uploadedBy: 'Uploaded by',
    close: 'Close',
    download: 'Download file'
  },
  importDialog: {
    title: 'Batch Import Torrent Files',
    downloaderLabel: 'Target downloader',
    downloaderPlaceholder: 'Select a downloader',
    fileLabel: 'Torrent files',
    dropPrefix: 'Drop files here, or ',
    dropAction: 'click to upload',
    tip: 'Only .torrent files are allowed; batch upload is supported',
    cancel: 'Cancel',
    confirm: 'Import'
  },
  msg: {
    operationSuccess: 'Done',
    dedupeFailed: 'Deduplication failed',
    selectExport: 'Select the torrent files to export first',
    exportSuccess: 'Exported',
    selectDownloader: 'Select a target downloader',
    selectImportFiles: 'Select the torrent files to import',
    invalidFile: 'Select a valid file',
    importPartialFailed: 'Some files failed to import:\n{list}',
    importFailed: 'Import failed',
    sessionRenewed: 'Your session was renewed. Please upload again.',
    uploadFailedRetry: 'Upload failed, please try again later',
    uploadFailed: 'Upload failed',
    downloadSuccess: 'Downloaded',
    authFailed: 'Authentication failed. Please sign in again.',
    fileNotFound: 'The torrent file does not exist',
    downloadFailedWithStatus: 'Download failed: {status}',
    networkError: 'Network error. Please check your network connection.',
    downloadFailedRetry: 'Download failed, please try again later',
    deleteConfirm: 'Delete this torrent file backup?',
    confirmTitle: 'Notice',
    confirmButton: 'Confirm',
    cancelButton: 'Cancel',
    deleteSuccess: 'Deleted',
    deleteFailed: 'Delete failed'
  }
}
