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
 * Operation log domain copy (P6-4b: views/logs/audit.vue).
 *
 * Boundaries mirror the zh module header: operation types map by stable
 * value with raw-text fallback (Q02); detail payloads (operation_detail /
 * old_value / new_value / error_message) and user content pass through as
 * original data; endpoint msg is never matched by text — error display goes
 * through the reasonCode contract entries.
 */
export const auditLogs = {
  title: 'Operation Logs',
  subtitle: 'Search key operation records, verify outcomes, and export for archival',
  detail: 'Details',
  filter: {
    panelTitle: 'Filter Logs',
    panelDescription: 'Query by combining name, type, operator, result, and time range',
    countTag: '{count} records in total',
    torrentName: 'Torrent Name',
    torrentNamePlaceholder: 'Supports fuzzy matching',
    operationType: 'Operation Type',
    allTypes: 'All types',
    operator: 'Operator',
    operatorPlaceholder: 'All operators',
    result: 'Result',
    allResults: 'All results',
    all: 'All',
    timeRange: 'Time Range',
    rangeSeparator: 'to',
    startPlaceholder: 'Start time',
    endPlaceholder: 'End time',
    search: 'Search',
    reset: 'Reset'
  },
  operationGroup: {
    seed: 'Torrent Management',
    downloader: 'Downloader Operations',
    task: 'Scheduled Tasks',
    keyword: 'Keyword Rules'
  },
  operationType: {
    add: 'Add torrent',
    transfer: 'Torrent transfer',
    deleteL4: 'Level 4 delete',
    deleteL3: 'Level 3 delete',
    deleteL2: 'Level 2 delete',
    deleteL1: 'Level 1 delete',
    restore: 'Restore torrent',
    downloaderAdd: 'Add downloader',
    downloaderDelete: 'Delete downloader',
    downloaderUpdate: 'Update downloader',
    downloaderTest: 'Test downloader',
    scheduledTaskAdd: 'Add scheduled task',
    scheduledTaskDelete: 'Delete scheduled task',
    scheduledTaskUpdate: 'Update scheduled task',
    scheduledTaskExecute: 'Execute scheduled task',
    scheduledTaskInterrupt: 'Interrupt scheduled task',
    keywordRuleAdd: 'Add keyword rule',
    keywordRuleDelete: 'Delete keyword rule',
    keywordRuleUpdate: 'Update keyword rule'
  },
  operationTypeFull: {
    deleteL4: 'Level 4 delete (pending deletion)',
    deleteL3: 'Level 3 delete (recycle bin)',
    deleteL2: 'Level 2 delete (keep data)',
    deleteL1: 'Level 1 delete (permanent deletion)'
  },
  result: {
    success: 'Success',
    failed: 'Failed',
    partial: 'Partial Success'
  },
  actions: {
    title: 'Log Actions',
    description: 'Export current filter results, or archive historical data',
    export: 'Export',
    exportCsv: 'Export as CSV',
    exportExcel: 'Export as Excel',
    archive: 'Archive History Logs',
    refreshStats: 'Refresh Statistics'
  },
  stats: {
    total: 'Total Logs',
    success: 'Successful Operations',
    failed: 'Failed Operations',
    today: "Today's Operations"
  },
  col: {
    operationType: 'Operation Type',
    operator: 'Operator',
    torrentName: 'Torrent Name',
    downloaderName: 'Downloader',
    time: 'Time',
    result: 'Result',
    ip: 'IP Address',
    action: 'Actions'
  },
  empty: 'No audit logs yet',
  detailDialog: {
    title: 'Audit Log Details',
    basicSection: 'Basic Information',
    debugSection: 'Debug Information',
    operationSection: 'Operation Details',
    oldSection: 'Before Change (Old Value)',
    newSection: 'After Change (New Value)',
    errorSection: 'Error Message',
    operationType: 'Operation type: ',
    operator: 'Operator: ',
    time: 'Time: ',
    result: 'Result: ',
    torrentName: 'Torrent name: ',
    downloaderName: 'Downloader: ',
    ip: 'IP address: ',
    requestId: 'Request ID: ',
    sessionId: 'Session ID: ',
    copyJson: 'Copy JSON'
  },
  archiveDialog: {
    title: 'Archive Audit Logs',
    noticeTitle: 'Archive Notes',
    noticeText: 'Archiving exports audit logs before the specified time to a standalone JSON file and deletes them from the main database. Archived logs no longer appear in the query view, but can be inspected in the archive file.',
    endTime: 'Archive Cutoff Time',
    endTimePlaceholder: 'Select date and time',
    endTimeHint: 'Audit logs before this time will be archived',
    fileName: 'Archive File Name',
    fileNamePlaceholder: 'Leave empty to auto-generate',
    fileNameHint: 'File name only (.json suffix appended automatically); always saved to data/audit_logs_archive/',
    confirm: 'Archive'
  },
  msg: {
    queryFailed: 'Query failed',
    queryException: 'Failed to query audit logs',
    exporting: 'Exporting as {format}...',
    fileNameMissing: 'Export file name missing',
    exportFailed: 'Export failed',
    exportRetry: 'Export failed, please try again later',
    archiveTimeRequired: 'Select an archive cutoff time first',
    archiveConfirm: 'Archiving cannot be undone. Archive the audit logs now?',
    confirmTitle: 'Warning',
    ok: 'OK',
    archiveSuccess: 'Archived {count} logs',
    archiveFailed: 'Archive failed',
    archiveRetry: 'Archive failed, please try again later',
    statsRefreshed: 'Statistics refreshed',
    jsonCopied: 'JSON copied to clipboard',
    copyFailed: 'Copy failed, please select and copy the content manually'
  }
}
