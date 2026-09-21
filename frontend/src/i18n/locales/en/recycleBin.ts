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
 * Recycle bin copy (recycleBin group, bilingual P5).
 *
 * R03-R05 hazardous semantics (restorable / downgrade / irreversibility):
 * per-level wording review checklist lives in PLANS/bilingual/delete-level-review.md.
 */
export const recycleBin = {
  title: 'Recycle Bin',
  subtitle: 'Manage deleted torrents: restore them or delete them permanently',
  filter: {
    title: 'Filters',
    description: 'Search recycle bin torrents by name',
    nameLabel: 'Torrent name',
    searchPlaceholder: 'Search torrent name...',
    search: 'Search',
    reset: 'Reset'
  },
  toolbar: {
    restore: 'Restore',
    delete: 'Delete',
    cleanupPreview: 'Cleanup preview',
    refresh: 'Refresh list',
    clearAll: 'Empty recycle bin',
    manualUpload: 'Manual upload restore'
  },
  table: {
    name: 'Torrent name',
    status: 'Status',
    size: 'Size',
    deletedAt: 'Deleted at',
    downloader: 'Downloader',
    path: 'Original path',
    actions: 'Actions',
    restore: 'Restore',
    delete: 'Delete',
    restorable: 'Restorable',
    notRestorable: 'Not restorable',
    loading: 'Loading...'
  },
  empty: {
    text: 'The recycle bin is empty',
    hint: 'Deleted torrents will appear here'
  },
  previewDialog: {
    title: 'Cleanup Preview',
    cleanBefore: 'Clean up torrents deleted more than',
    daysUnit: 'days ago',
    preview: 'Preview',
    countLabel: 'Torrent count: ',
    sizeLabel: 'Total size: ',
    colName: 'Torrent name',
    colSize: 'Size',
    colDeletedAt: 'Deleted at',
    colPath: 'Original path',
    cancel: 'Cancel',
    confirm: 'Clean up'
  },
  manualDialog: {
    title: 'Restore with Uploaded Torrent File',
    torrentIdLabel: 'Torrent ID',
    torrentIdPlaceholder: 'Enter the torrent ID to restore',
    fileLabel: 'Torrent file',
    chooseFile: 'Choose torrent file',
    fileTip: 'Only .torrent files up to 10MB are allowed',
    noticeTitle: 'Notice',
    notice: 'When the torrent file backup is missing, you can upload the torrent file manually to restore it',
    cancel: 'Cancel',
    confirm: 'Start restore'
  },
  confirmDialog: {
    danger: '⚠️ Dangerous operation',
    cancel: 'Cancel',
    confirm: 'Confirm',
    batchRestoreTitle: 'Batch Restore',
    batchRestoreMessage: 'Restore the {count} selected torrents?',
    batchRestoreDetail: 'Restoring will re-add the torrents to their downloaders and clear the deletion marker.',
    batchDeleteTitle: 'Batch Delete',
    batchDeleteMessage: 'Permanently delete the {count} selected torrents?',
    batchDeleteDetail: 'This cannot be undone. The torrents will be deleted permanently!',
    cleanupTitle: 'Confirm Cleanup',
    cleanupMessage: 'Clean up {count} torrents?',
    cleanupDetail: 'Space to free: {size}',
    restoreTitle: 'Restore Torrent',
    restoreMessage: 'Restore "{name}"?',
    restoreDetail: 'The torrent will be re-added to its downloader.',
    deleteTitle: 'Delete Torrent',
    deleteMessage: 'Permanently delete "{name}"?',
    deleteDetail: 'This cannot be undone. The torrent will be deleted permanently!',
    clearAllTitle: 'Empty Recycle Bin',
    clearAllMessage: 'Empty the recycle bin?',
    clearAllDetail: 'This will permanently delete all {count} torrents in the recycle bin. This cannot be undone!'
  },
  msg: {
    getListFailed: 'Failed to load the recycle bin list',
    previewFailed: 'Failed to load the preview',
    noCleanable: 'Nothing to clean up',
    cleanupSuccess: 'Cleanup finished',
    cleanupFailed: 'Cleanup failed',
    refreshSuccess: 'Refreshed',
    binEmpty: 'The recycle bin is empty',
    clearAllFailed: 'Failed to empty the recycle bin',
    enterTorrentId: 'Enter a torrent ID',
    chooseFile: 'Choose a torrent file',
    invalidFile: 'Invalid torrent file',
    restoreSuccess: 'Restored successfully',
    restoreFailed: 'Restore failed',
    manualPartial: 'Partially succeeded: {success} succeeded, {failed} failed',
    manualRestoreFailed: 'Manual restore failed',
    restoreSuccessCount: 'Restore finished: {count} torrents restored',
    restoreFailedCount: 'Restore failed: {count} torrents',
    restorePartial: 'Restore partially finished: {success} succeeded, {failed} failed',
    deleteSuccessCount: 'Deletion finished: {count} torrents deleted',
    deleteFailedCount: 'Deletion failed: {count} torrents',
    deletePartial: 'Deletion partially finished: {success} succeeded, {failed} failed',
    deleteFailed: 'Deletion failed'
  }
}
