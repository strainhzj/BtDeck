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

/** 种子域文案（torrent 组，en；术语依据 PLANS/bilingual/terminology.md：cross-seed / recheck / reannounce / recycle bin）。 */
export const torrent = {
  status: {
    seeding: 'Seeding',
    downloading: 'Downloading',
    completed: 'Completed',
    paused: 'Paused',
    queuedDL: 'Queued',
    error: 'Error',
    checking: 'Checking',
    unknown: 'Unknown'
  },
  list: {
    searchPlaceholder: 'Search torrent name...',
    /** Traditional view only (P6-1): filter panel / selection counter / status bar */
    filters: {
      toggle: 'Toggle filter panel',
      title: 'Filters',
      collapse: 'Collapse',
      all: 'All',
      downloader: 'Downloader',
      trackerDomain: 'Tracker domain',
      category: 'Category',
      tags: 'Tags',
      /** Traditional-view virtual status filter items (P6-5 leftover fix: traditionalStatusFilter prepends) */
      activeStatus: 'Active'
    },
    selectedPrefix: 'Selected',
    selectedSuffix: '',
    connected: 'Connected',
    activeLabel: 'Active:',
    downloaderPlaceholder: 'Select downloaders',
    statusPlaceholder: 'Select torrent status',
    trackerPlaceholder: 'Select trackers',
    activeOnly: 'Active torrents only',
    search: 'Search',
    advancedSearch: 'Advanced search',
    duplicateSwitch: 'Find duplicates',
    clear: 'Clear',
    refresh: 'Refresh',
    alert: {
      sameContent: 'Cross-seed inspection: the list only shows torrents with the same name and size but different InfoHash',
      singleError: 'Unique error inspection: the list only shows the only errored copy of each content',
      exit: 'Exit inspection and return to normal list'
    },
    toolbar: {
      start: 'Start',
      pause: 'Pause',
      delete: 'Delete',
      recheck: 'Recheck',
      trackerOps: 'Tracker operations',
      reannounce: 'Reannounce',
      globalReplace: 'Global replace',
      transfer: 'Transfer',
      setLocation: 'Set location',
      quickActions: 'Quick actions',
      add: 'Add torrents',
      columns: 'Column settings',
      addShort: 'Add'
    },
    deleteMenu: {
      level4: 'Level 4: Mark for deletion (recommended)',
      level3: 'Level 3: Move to recycle bin',
      level2: 'Level 2: Remove torrent (keep data)',
      level1: 'Level 1: Delete completely'
    },
    quickMenu: {
      sameContent: 'Cross-seed inspection',
      singleError: 'Unique error inspection',
      deleteDuplicates: 'Quick delete duplicates'
    },
    column: {
      name: 'Name',
      nameShort: 'Name',
      downloaderShort: 'Downloader',
      downloadShort: '↓ Download',
      uploadShort: '↑ Upload',
      downloadSpeed: 'Down speed',
      uploadSpeed: 'Up speed',
      size: 'Size',
      auxiliarySeedCount: 'Cross-seeds',
      progress: 'Progress',
      status: 'Status',
      downloader: 'Downloader',
      ratio: 'Ratio',
      category: 'Category/Tags',
      savePath: 'Save path',
      addedDate: 'Added',
      actions: 'Actions'
    },
    sortTitle: {
      name: 'Sort by name',
      size: 'Sort by size',
      status: 'Sort by status',
      ratio: 'Sort by ratio',
      addedDate: 'Sort by added date'
    },
    resizeHint: 'Drag to resize the column, double-click to reset',
    loading: 'Loading...',
    trackerError: 'Tracker error',
    trackerErrorTitle: '{status} (tracker error)',
    action: {
      recheck: 'Force recheck',
      setLocation: 'Set save location'
    },
    view: {
      list: 'List view',
      traditional: 'Traditional view'
    },
    pagination: {
      summary: '{total} items, page {page} of {pages}',
      /** Traditional view pagination fragments (keeps the numeric <strong> markup) */
      prefix: 'Total',
      middle: 'items, page',
      suffix: ''
    },
    columnSettings: {
      title: 'Column settings',
      reset: 'Reset',
      resetWidths: 'Reset widths',
      apply: 'Apply',
      saved: 'Column settings saved',
      widthsReset: 'Column widths reset to default'
    }
  },
  msg: {
    getListFailed: 'Failed to load the torrent list',
    applyTemplateFailed: 'Failed to apply the template',
    applyTemplateFailedWith: 'Failed to apply the template: {message}',
    inspectSameContentDone: 'Inspection finished, {count} torrents with the same content found',
    inspectSingleErrorDone: 'Inspection finished, {count} unique errored torrents found',
    duplicatesFound: 'Search finished, {count} duplicate torrents found',
    duplicateFetchFailed: 'Search failed',
    duplicateFetchFailedRetry: 'Search failed, please try again later',
    reannounceSuccess: 'Tracker reannounce succeeded',
    reannounceFailed: 'Tracker reannounce failed',
    reannounceIncomplete: 'Torrent information is incomplete, cannot reannounce',
    reannouncePartial: 'Tracker reannounce partially completed: {succeeded} downloaders succeeded, {failed} failed ({total} torrents total)',
    reannounceBatchSuccess: 'Tracker reannounce succeeded ({total} torrents, {downloaderCount} downloaders)',
    reannounceBatchFailed: 'Tracker reannounce failed, see console for details',
    startSuccess: 'Started successfully',
    pauseSuccess: 'Paused successfully',
    recheckSuccess: 'Recheck started',
    opFailed: 'Operation failed, please try again later',
    recheckFailed: 'Recheck failed, please try again later',
    advancedDone: 'Advanced search finished, {count} results found',
    searchFailed: 'Search failed',
    advancedFailed: 'Advanced search failed, please check the search conditions',
    invalidSearchParams: 'Invalid search condition format',
    templateInvalid: 'Invalid template condition format',
    templateApplied: 'Query template applied',
    advancedTemplateApplied: 'Advanced search template applied',
    unsupportedTemplate: 'Unsupported template type',
    conditionsReset: 'Search conditions have been reset',
    trackerOpSuccess: 'Tracker operation succeeded',
    globalReplaceSuccess: 'Global tracker replacement succeeded',
    selectFirstAction: 'Select torrents first',
    selectFirstTransfer: 'Select torrents to transfer first',
    selectFirst: 'Select torrents first',
    missingDownloader: 'Selected torrents are missing downloader information, please refresh and retry',
    missingDownloaderShort: 'The torrent is missing downloader information',
    startTaskSuccess: 'Task started',
    pauseTaskSuccess: 'Task paused',
    recheckSubmitted: 'Recheck task submitted',
    selectFirstReannounce: 'Select torrents to reannounce first',
    globalReplaceFailed: 'Global tracker replacement failed',
    transferSingleDownloaderOnly: 'Batch transfer only supports torrents on the same downloader, please reselect',
    setLocationSingleDownloaderOnly: 'Selected torrents must belong to the same downloader',
    transferDone: 'Batch transfer completed'
  },
  addDialog: {
    title: 'Add Torrents',
    fileLabel: 'Torrent files',
    filePlaceholder: 'Click to select .torrent files (no limit)',
    filesSelected: '{count} files selected',
    fileHint: 'Only .torrent files are supported; they are processed asynchronously in the background',
    downloaderLabel: 'Downloader',
    downloaderPlaceholder: 'Select a downloader',
    pathLabel: 'Save path',
    pathPlaceholder: 'Enter or select a save path',
    pathTypeDefault: 'Default path',
    pathTypeInUse: 'In use',
    pathCount: '{count} torrents',
    checkPolicy: 'Verification policy',
    skipCheck: 'Skip recheck (seed directly when data is complete)',
    skipCheckHint: 'Tick this when the save path already contains complete data (cross-seed / re-seed): it skips the qBittorrent local recheck and avoids CheckingDL. Do not tick for fresh downloads (they would be treated as completed and never download). Applies to qBittorrent only.',
    category: 'Category',
    categoryPlaceholder: 'Select category (optional)',
    tags: 'Tags',
    tagsPlaceholder: 'Select tags (optional)',
    confirm: 'Confirm',
    adding: 'Adding...',
    error: {
      chooseFile: 'Please select torrent files',
      chooseDownloader: 'Please select a downloader',
      enterPath: 'Please enter a save path',
      onlyTorrent: 'Only .torrent files can be selected'
    },
    msg: {
      submitted: 'Submitted {count} torrents for background processing',
      success: 'Successfully added {count} torrents',
      failed: 'Failed to add torrents',
      failedWith: 'Failed to add torrents: {detail}',
      partial: 'Partially successful: {success} added, {failed} failed',
      failureItem: '{name}: {error}',
      unknownError: 'Unknown error',
      moreFailures: '; see the notification center for the other {count} failures',
      retry: 'Failed to add torrents, please try again later'
    }
  },
  batchDialog: {
    title: {
      delete: 'Batch delete confirmation',
      pause: 'Batch pause confirmation',
      resume: 'Batch resume confirmation',
      start: 'Batch start confirmation',
      fallback: 'Batch operation confirmation'
    },
    op: {
      delete: 'Delete',
      pause: 'Pause',
      resume: 'Resume',
      start: 'Start',
      fallback: 'Action'
    },
    message: {
      delete: 'Are you sure you want to delete these torrents? This action cannot be undone!',
      pause: 'Are you sure you want to pause these torrents?',
      resume: 'Are you sure you want to resume these torrents?',
      start: 'Are you sure you want to start these torrents?',
      fallback: 'Are you sure you want to perform this action?'
    },
    opType: 'Operation: ',
    affectCount: 'Affected: ',
    countTorrents: '{count} torrents',
    affected: 'Affected torrents:',
    confirmAction: 'Confirm {op}'
  },
  batch: {
    action: {
      start: 'start',
      pause: 'pause',
      recheck: 'recheck'
    },
    partial: 'Batch {action} partially completed: {succeeded} downloaders succeeded, {failed} failed ({total} torrents total)',
    success: 'Batch {action} succeeded ({total} torrents, {downloaderCount} downloaders)',
    failed: {
      start: 'Batch start failed, see console for details',
      pause: 'Batch pause failed, see console for details',
      recheck: 'Batch recheck failed, see console for details'
    }
  },
  /** Four-level deletion chain (P5; per-level keys per R01-R04 red line: level number + affected object + irreversibility) */
  deleteLevel: {
    confirm: {
      titleSingle: 'Confirm Deletion',
      titleBatch: 'Confirm Batch Deletion',
      confirmButton: 'Confirm',
      cancelButton: 'Cancel',
      level1: {
        single: 'Level 1 - Permanently delete this torrent and its data files? This cannot be undone.',
        batch: 'Level 1 - Permanently delete {count} selected torrents and their data files? This cannot be undone.'
      },
      level2: {
        single: 'Level 2 - Remove this torrent from the downloader? Its data files will be kept.',
        batch: 'Level 2 - Remove {count} selected torrents from the downloader? Their data files will be kept.'
      },
      level3: {
        single: 'Level 3 - Move this torrent to the recycle bin? It can be restored from there later.',
        batch: 'Level 3 - Move {count} selected torrents to the recycle bin? They can be restored from there later.'
      },
      level4: {
        single: 'Level 4 - Mark this torrent as pending deletion? Nothing is removed yet.',
        batch: 'Level 4 - Mark {count} selected torrents as pending deletion? Nothing is removed yet.'
      },
      generic: {
        single: 'Are you sure you want to delete this torrent?',
        batch: 'Are you sure you want to delete {count} selected torrents?'
      }
    },
    msg: {
      selectFirst: 'Select torrents to delete first',
      submitFailed: 'Failed to submit the deletion task',
      alreadyProcessed: 'All selected torrents are already being handled by a deletion task',
      skipped: 'Skipped {count} torrents that are already being processed',
      deleteFailed: 'Deletion failed',
      batchDeleteFailed: 'Batch deletion failed',
      statusQueryFailed: 'Failed to query the task status',
      retryLater: 'Deletion failed, please try again later'
    },
    progress: {
      loading: 'Deleting torrents, please wait...',
      running: 'Deleting... ({done}/{total})',
      timeout: 'The deletion task is taking unusually long; check its status later'
    },
    notify: {
      downgradeTitle: 'Downgrade details',
      fileMissingTitle: 'Missing files notice',
      failedTitle: 'Deletion failure details'
    },
    result: {
      taskCompleted: 'Batch deletion finished: {count} torrents deleted',
      taskCompletedWithMissing: 'Batch deletion finished: {count} torrents deleted ({missing} had no files on disk; file operations were skipped)',
      taskFailed: 'Batch deletion failed: {error}',
      taskPartial: 'Batch deletion partially finished: {success} succeeded, {failed} failed',
      failedDetail: 'The following torrents failed to delete: {names}',
      failedDetailMore: 'The following torrents failed to delete: {names} and {count} more',
      fileMissingDetail: 'No files were found for the following torrents; file operations were skipped and they were moved to the recycle bin directly: {names}',
      fileMissingDetailMore: 'No files were found for the following torrents; file operations were skipped and they were moved to the recycle bin directly: {names} and {count} more',
      downgraded: '{count} torrents were downgraded to Level 4 deletion (backup failed)',
      downgradeDetail: 'Backup failed for the following torrents; they were downgraded to Level 4: {names}',
      downgradeDetailMore: 'Backup failed for the following torrents; they were downgraded to Level 4: {names} and {count} more',
      syncPartialFailed: 'Deletion finished: {count} failed',
      level3Success: 'Level 3 deletion succeeded for {count} torrents',
      level3SuccessWithMissing: 'Level 3 deletion succeeded for {count} torrents ({missing} had no files on disk; file operations were skipped)',
      levelDone: 'Level {level} deletion finished: {count} torrents succeeded',
      deleteDone: 'Deletion finished: {count} torrents succeeded'
    }
  },
  /** Torrent detail dialog (TorrentDetailDialog, P3-2; transfer dialog body is P6, not translated) */
  detail: {
    title: 'Torrent Details',
    nameLabel: 'Torrent name',
    status: 'Status',
    size: 'Size',
    progress: 'Progress',
    downloadSpeed: 'Download speed',
    uploadSpeed: 'Upload speed',
    addedDate: 'Added at',
    completedDate: 'Completed at',
    ratio: 'Share ratio',
    savePath: 'Save path',
    tags: 'Tags',
    notCompleted: 'Not completed',
    trackerSection: 'Tracker Info',
    trackerColName: 'Name',
    trackerColStatus: 'Status',
    statusNormal: 'Normal',
    statusAbnormal: 'Error',
    transfer: 'Transfer'
  },
  duplicates: {
    quick: {
      title: 'Quick Delete Duplicates',
      detectLabel: 'Downloaders to scan',
      detectHint: 'Select 2 or more downloaders to find duplicate torrents among them',
      keepLabel: 'Keep downloaders',
      keepHint: 'Duplicates in these downloaders are kept; duplicates in the other scanned downloaders are removed (torrents only, data files are not deleted)',
      autoHint: 'The duplicate preview refreshes automatically once scan and keep downloaders are selected',
      analyzing: 'Analyzing duplicate torrents...',
      groupsPrefix: '',
      groupsSuffix: ' duplicate groups',
      deletePrefix: 'Will delete',
      deleteSuffix: 'torrents',
      skippedNote: '⚠ {count} more groups skipped (no kept copy)',
      skippedTooltip: 'These duplicates exist only among the to-delete downloaders with no kept copy; they are skipped so the last remaining copy is never lost',
      empty: 'No removable duplicate torrents found among the selected downloaders',
      noName: '(no name)',
      skippedBadge: 'Skipped',
      skippedBody: 'These copies exist only among the to-delete downloaders with no kept copy; they are skipped so the last remaining copy is never lost (they will not be deleted)',
      colDelete: 'Will be deleted',
      colKeep: 'Kept copies',
      confirmDelete: 'Confirm delete',
      confirmDeleteCount: 'Confirm delete ({count})',
      msg: {
        queryFailed: 'Query failed',
        submitFailed: 'Failed to submit the delete task',
        noDeletable: 'No removable duplicate torrents found',
        submitted: 'Delete task submitted ({total} torrents, {skipped} in progress skipped)',
        submittedPlain: 'Delete task submitted ({total} torrents)',
        taskDone: 'Delete task completed: {success} succeeded, {failed} failed',
        taskPartial: 'Delete task partially completed: {success} succeeded, {failed} failed',
        taskFailed: 'Delete task failed: {success} succeeded, {failed} failed',
        stillRunning: 'The delete task is still running in the background; check the notification center later for the result'
      }
    },
    scan: {
      title: 'Duplicate Torrents',
      loading: 'Searching duplicate torrents...',
      col: {
        hash: 'Hash',
        name: 'Name',
        size: 'Size',
        downloader: 'Downloader',
        status: 'Status',
        path: 'Save path'
      },
      groupsPrefix: '',
      groupsSuffix: ' duplicate groups found',
      tasksPrefix: '',
      tasksSuffix: ' torrents in total',
      empty: 'No duplicate torrents found',
      queryFailed: 'Query failed'
    }
  }
}
