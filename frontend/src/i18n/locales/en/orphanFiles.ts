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
 * Orphan file domain copy (P6-4b: views/orphan-files/index.vue).
 *
 * Boundaries mirror the zh module header: statuses/confidence map by
 * stable codes with raw-text fallback (Q02); scan-context service values
 * pass through as original data ({reason} slots or console, E01); endpoint
 * msg is never matched by text — error display goes through the reasonCode
 * contract entries; destructive flows keep the three-element semantics
 * (target + count/size + irreversibility).
 */
export const orphanFiles = {
  title: 'Orphan Files',
  subtitle: 'Scan files not referenced by any torrent and review them safely before cleanup',
  scanNow: 'Scan Now',
  tabs: {
    orphans: 'Orphan Files',
    quarantine: 'Quarantine'
  },
  stats: {
    title: 'Scan Statistics',
    summaryAria: 'Summary of the most recent orphan file scan',
    pendingCount: 'Files Pending Cleanup',
    pendingSize: 'Space Pending Cleanup',
    ignoredCount: 'Ignored Files',
    pathCount: 'Paths Scanned',
    lastScan: 'Last Successful Scan',
    noScan: 'No successful scan yet'
  },
  scanState: {
    failedTitle: 'Last Scan Failed',
    queuedTitle: 'Orphan File Scan Waiting to Run',
    runningTitle: 'Orphan File Scan in Progress',
    largeTitle: 'Large Scan Reminder',
    largeText: 'This scan found a large number of orphan files. Check the downloader path mappings and orphan detection; this reminder does not block cleanup.',
    queuedDesc: 'The scan task is queued in the background; the page only polls a lightweight status, so the list and cleanup are temporarily unavailable.',
    runningDesc: 'A scan is in progress. The list and statistics stay empty until it finishes, and cleanup is temporarily unavailable.',
    failedWithDisplay: 'Failure reason: {reason}. The remaining results of the last successful scan are shown read-only; cleanup stays unavailable until a new scan succeeds.',
    failedNoDisplay: 'Failure reason: {reason}. There are no successful scan results to display yet.',
    unknownError: 'Unknown error'
  },
  filter: {
    aria: 'Orphan file filter conditions',
    pathLike: 'File Path',
    pathPlaceholder: 'Fuzzy-match path keyword',
    downloader: 'Downloader',
    status: 'Status',
    statusDegradedTip: 'Selecting "Pending cleanup" together with "Ignored/Cleaned" widens the filter to all non-deleted files',
    warnAria: 'Filter combination hint',
    confidence: 'Confidence',
    located: 'Copy Filter',
    locatedTip: 'Filter by the hard-link copy count captured at scan time; copy locations are re-verified live in the dialog',
    hasCopies: 'Has hard-link copies',
    search: 'Search',
    reset: 'Reset'
  },
  confidence: {
    high: 'High confidence',
    low: 'Low confidence'
  },
  status: {
    pending: 'Pending cleanup',
    ignored: 'Ignored',
    deleted: 'Cleaned',
    mixed: 'Mixed'
  },
  confidenceTag: {
    high: 'High',
    low: 'Low',
    mixed: 'Mixed',
    folderLowTip: 'The folder contains low-confidence items from the offline degraded-directory coarse check, which may misjudge',
    folderHighTip: 'All files in the folder passed the online precise check and are confirmed unreferenced by any torrent',
    lowTip: 'Judged by the offline degraded-directory coarse check and may be misjudged; manual cleanup can delete it, while automatic cleanup waits for the downloader to come online for a precise check',
    highTip: 'Judged by the online precise check and confirmed unreferenced by any torrent'
  },
  list: {
    title: 'File List',
    description: 'Showing remaining results of the successful scan at {time}',
    descriptionEmpty: 'Results will appear here after the first successful scan',
    selected: '{count} selected',
    cleanupSelected: 'Clean Up Selected',
    ignoreSelected: 'Ignore Selected',
    unignoreSelected: 'Unignore',
    folderView: 'Group by Folder',
    folderViewTip: 'When enabled, multiple files in the same directory collapse into one folder row (display only; deletion still works per file)',
    quickAction: 'Quick Actions',
    quickCleanup: 'Quick Delete (by Prefix)',
    quickIgnore: 'Quick Ignore (by Prefix)',
    quickIgnoreTitle: 'Batch-ignore pending files by path prefix',
    clearLocated: 'Clear Copy Filter',
    filterLocated: 'Filter Files with Copies',
    locatedOn: 'Show only files with hard-link copies (counted at scan time)',
    locatedOff: 'Clear the copy filter to restore the full list',
    empty: 'No orphan files yet. Click "Scan Now" to start detection',
    col: {
      path: 'File Path',
      size: 'Size',
      copies: 'Copies',
      mtime: 'Modified',
      downloader: 'Downloader',
      confidence: 'Confidence',
      status: 'Status',
      action: 'Actions'
    },
    filesCount: '{count} files',
    multipleDownloaders: 'Multiple',
    ignore: 'Ignore',
    unignore: 'Unignore',
    paginationAria: 'Orphan file pagination',
    selectAllAria: 'Select all orphan files on the current page',
    totalPrefix: '',
    totalSuffix: ' items in total'
  },
  quarantine: {
    title: 'Quarantined Files',
    subtitle: 'Cleaned files are held here (retention: {days} days); restore them to their original locations or permanently delete them now',
    selected: '{count} selected',
    restore: 'Restore Selected',
    purge: 'Delete Selected Permanently',
    col: {
      path: 'Original Location (Canonical Path)',
      size: 'Size',
      quarantinedAt: 'Quarantined At',
      purgeAfter: 'Scheduled Deletion',
      delayCount: 'Delays',
      downloader: 'Downloader'
    },
    total: '{count} items in total',
    paginationAria: 'Quarantine pagination'
  },
  hardlink: {
    title: 'Hard-Link Copy Locations',
    titleWithCount: 'Hard-Link Copy Locations ({count} files)',
    notice: 'Copy locations are looked up and stored in bulk by a daily scheduled task; this dialog shows the most recent round directly.',
    realtime: 'Live copies',
    located: 'Located',
    pending: 'Pending pre-scan',
    unlocatedTitle: '{count} copies were not located in the latest pre-scan round',
    unlocatedDesc: 'These copies may sit in directories without permission or not mounted, or may not be covered by the pre-scan yet; the total copy count is a live statistic.',
    unknownTitle: '{count} source files are currently inaccessible, so their locations cannot be verified',
    invalidTitle: '{count} list items are stale; refresh the page and try again',
    copyTag: '{count} copies',
    pendingTag: 'Pending pre-scan',
    locatedTag: '{count} located',
    scannedAt: 'Scanned at {time}',
    inaccessible: 'Source file inaccessible; copy locations cannot be re-verified',
    copyPath: 'Copy Path',
    remove: 'Delete',
    truncated: 'The number of paths exceeds the storage limit; only the first {count} are shown.',
    emptyPending: 'Waiting for the daily scheduled pre-scan to locate copy paths; reopen later to check.',
    emptyUnlocated: 'The latest pre-scan round did not locate any copy paths.',
    emptyNone: 'This file currently has no other hard-link copies.',
    unlocatedCount: '{count} copy locations of this file remain unlocated.',
    countFolderTitle: 'After expanding, only the copy-count snapshots of currently visible files are tallied',
    countUnknownTitle: 'No copy-count snapshot yet (waiting for scan)',
    countZeroTitle: 'No other hard-link copies (click to re-verify live)',
    countNTitle: 'Click to view the locations of {count} hard-link copies',
    deleteConfirm: 'Delete this hard-link copy?\n{path}\nThis cannot be undone: only the link at this path is removed and the data stays with the source file; copies inside torrent directories are rejected for deletion.',
    deleteTitle: 'Delete Copy Confirmation',
    confirmDelete: 'Delete',
    rejected: 'Deletion rejected',
    deleted: 'Copy deleted: {path}'
  },
  cleanup: {
    title: 'Cleanup Confirmation',
    confirmTitle: 'Clean up the following orphan files? This cannot be undone!',
    fileCount: 'File count: ',
    totalSize: 'Total size: ',
    lowTitle: '{count} of them are low-confidence (offline degraded-directory coarse check)',
    lowText: 'Low-confidence files may be misjudged (they might not be true orphans). Verify the paths before confirming cleanup to avoid deleting user data by mistake.',
    confirm: 'Clean Up'
  },
  quickAction: {
    cleanupTitle: 'Quick Delete (by Prefix)',
    ignoreTitle: 'Quick Ignore (by Prefix)',
    noticeTitle: 'Left-match pending files by path prefix',
    noticeLead: 'Enter a path prefix (the start of an absolute path); it matches all',
    noticeFileStrong: 'file paths',
    noticeMid: ' starting with it that are',
    noticePendingStrong: 'pending cleanup',
    noticeTail: ' (excluding ignored/cleaned).',
    cleanupNote: 'Deletion moves files into quarantine and is recoverable.',
    prefixLabel: 'Path Prefix',
    prefixPlaceholder: 'e.g. D:\\downloads\\to-clean\\ or /data/leak/',
    ok: 'OK'
  },
  batchTitle: {
    cleanupSelectFirst: 'Select pending files first',
    cleanupMixed: 'Do not mix statuses; only "pending cleanup" items can be cleaned up',
    ignoreSelectFirst: 'Select pending files first',
    ignoreMixed: 'Do not mix statuses; only "pending cleanup" items can be ignored',
    unignoreSelectFirst: 'Select ignored files first',
    unignoreMixed: 'Do not mix statuses; only "ignored" items can be unignored'
  },
  msg: {
    tipTitle: 'Notice',
    actionIgnore: 'Ignore',
    actionUnignore: 'Unignore',
    skippedCount: ', skipped {count} in progress',
    networkFallback: 'Network error',
    loadQuarantineFailed: 'Failed to load the quarantine list: ',
    restoreConfirm: 'Restore the selected files to their original locations?',
    restoreTitle: 'Restore Confirmation',
    restoreRejected: 'Restore rejected',
    restoreDone: 'Restore finished: {count} succeeded',
    restoreFailedSuffix: ', {count} failed',
    restoreFailed: 'Restore failed: ',
    purgeConfirm: 'Permanently delete the selected files? This cannot be undone; the files will be deleted forever!',
    purgeTitle: 'Permanent Deletion Confirmation',
    purgeSubmitted: 'Permanent deletion task submitted ({taskId}){skipped}; the result will arrive via Notification Center',
    purgeAllProcessing: 'All selected quarantined files are already being processed by a deletion task',
    purgeFailed: 'Deletion failed: ',
    folderChildrenFailed: 'Failed to load folder children',
    folderChildrenFailedWith: 'Failed to load folder children: ',
    hardlinkQueryFailed: 'Failed to query hard-link copy locations',
    hardlinkQueryFailedWith: 'Failed to query hard-link copy locations: ',
    hardlinkRefreshFailed: 'Failed to refresh copy locations; the current view shows pre-deletion results: ',
    hardlinkDeleteFailed: 'Failed to delete the hard-link copy',
    hardlinkDeleteFailedWith: 'Failed to delete the hard-link copy: ',
    hardlinkDeletePartial: 'Some copies failed to delete; see the console log for details',
    pathCopied: 'Path copied',
    copyPathFailed: 'Copy failed: ',
    clipboardUnsupported: 'The current browser does not support the clipboard',
    blockReasonDefault: 'The current scan snapshot does not allow cleanup',
    blockReasonInitial: 'No successful scan is cleanable yet',
    pageSizeAdjusted: 'At most {count} items can be loaded at once; the value was adjusted automatically',
    listFailed: 'Failed to load the list',
    listFailedWith: 'Failed to load the orphan file list: ',
    scanConfirm: 'Scan for orphan files now? The scan may take a while.',
    scanSubmitted: 'Scan task submitted to the background',
    scanExisting: 'A scan task already exists; continuing to track its status',
    scanFailed: 'Scan failed',
    scanFailedWith: 'Scan failed: ',
    scanDone: 'Scan finished: {total} orphans, {added} new details, {known} reused',
    scanFailedRecord: 'Scan failed: {reason}',
    cleanupSelectFirst: 'Select files to clean up first',
    cleanupEmptySelection: 'None of the selected files are cleanable: they may be low-confidence (waiting for the downloader to come online for a precise check), ignored (unignore first), or already cleaned.',
    previewRejected: 'The current scan snapshot does not allow cleanup; refresh and try again',
    previewFailed: 'Preview failed',
    previewFailedWith: 'Preview failed: ',
    scanStale: 'The scan batch is stale; refresh and try again',
    cleanupSubmitted: 'Cleanup task submitted ({taskId}){skipped}; the result will arrive via Notification Center',
    cleanupAllProcessing: 'All selected orphan files are already being processed by a cleanup task',
    cleanupFailed: 'Cleanup failed',
    cleanupFailedWith: 'Cleanup failed: ',
    cleanupSubmitFailed: 'Failed to submit the cleanup task',
    ignoreSelectPending: 'Select pending files to ignore',
    ignoreSelectIgnored: 'Select ignored files to unignore',
    ignoreConfirm: '{action} the {count} selected orphan files?',
    ignoreFailedCount: '{action} failed: {count} files left unprocessed',
    ignorePartial: '{action} partially finished: {success} succeeded, {failed} failed',
    ignoreDone: '{action} finished: {count} succeeded',
    ignoreFailed: '{action} failed',
    prefixRequired: 'Enter a path prefix',
    noScanBatch: 'No successful scan batch is available; prefix actions are unavailable',
    snapshotNotAllowed: 'The current scan snapshot does not allow this action',
    prefixPreviewFailed: 'Prefix match preview failed',
    prefixPreviewFailedWith: 'Prefix match preview failed: ',
    noMatch: 'No matching pending files',
    affectCount: 'This will affect {count} pending files',
    sizeSuffix: ' ({size} in total)',
    lowWarn: '⚠️ {count} of them are low-confidence and may be misjudged; verify the paths',
    moveToQuarantine: '\n\nMove them into quarantine (recoverable)?',
    setIgnored: '\n\nMark them as ignored (protected from automatic/manual cleanup)?',
    matchAllProcessing: 'All matched files are already being processed by a cleanup task'
  }
}
