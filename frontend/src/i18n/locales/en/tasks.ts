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
 * Scheduled-tasks domain copy (P6-4a; paired with zh-CN/tasks.ts).
 *
 * Boundaries mirror the zh module header: backend Chinese status/type names
 * are data semantics (display maps by stable code); Cron template names and
 * categories are data identity (display maps by template key); the Python
 * class list is driven by backend type-config (descriptions pass through
 * as original data, Q02).
 */
export const tasks = {
  tabs: {
    management: 'Task Management',
    logs: 'Task Logs'
  },
  list: {
    title: 'Task List',
    filter: {
      taskName: 'Task name',
      taskNamePlaceholder: 'Enter a task name',
      taskCode: 'Task code',
      taskCodePlaceholder: 'Enter a task code',
      enabled: 'Enabled',
      selectPlaceholder: 'Select',
      enabledOption: 'Enabled',
      disabledOption: 'Disabled',
      taskType: 'Task type'
    },
    query: 'Search',
    reset: 'Reset',
    toolbar: {
      enable: 'Enable',
      pause: 'Pause',
      delete: 'Delete',
      recheck: 'Recheck',
      refresh: 'Refresh',
      create: 'New Task'
    },
    col: {
      taskName: 'Task Name',
      taskCode: 'Task Code',
      taskType: 'Task Type',
      status: 'Status',
      enabled: 'Enabled',
      cron: 'Cron Expression',
      lastExecute: 'Last Run',
      actions: 'Actions'
    },
    platformDisabled: 'Platform disabled',
    enabledTag: 'Enabled',
    disabledTag: 'Disabled',
    dataStale: 'Stale data',
    menu: {
      actions: 'Actions',
      execute: 'Run now',
      edit: 'Edit',
      logs: 'View logs',
      interrupt: 'Interrupt',
      delete: 'Delete'
    },
    tip: {
      executeUnsupported: 'The current host capability does not support this task; it will not run',
      executeDisabled: 'Task is disabled. Enable it first'
    },
    pagination: {
      prefix: 'Total ',
      middle: ', page ',
      suffix: '',
      perPageSuffix: ' / page'
    }
  },
  /** Task types (mapped by stable code; two distinct fallbacks, do not merge) */
  type: {
    shell: 'Shell script',
    cmd: 'CMD script',
    powershell: 'PowerShell script',
    python: 'Python script',
    pythonClass: 'Python built-in class',
    cleanup: 'Recycle bin cleanup',
    unknownShort: 'Unknown',
    unknownType: 'Unknown type',
    executorFallback: 'Execution content',
    executorShell: 'Shell script',
    executorCmd: 'CMD script',
    executorPowershell: 'PowerShell script',
    executorPython: 'Python script'
  },
  /** Task status (backend taskStatus codes 0/1/2; Chinese names are data matching only) */
  status: {
    waiting: 'Waiting',
    running: 'Running',
    idle: 'Idle',
    unknown: 'Unknown status'
  },
  /** Six outcome states (api/tasks.ts getTaskOutcomeMeta single source of truth) */
  outcome: {
    success: 'Success',
    partial: 'Partial success',
    skipped: 'Skipped',
    failed: 'Failed',
    noAction: 'No change',
    cancelled: 'Cancelled'
  },
  /** Stale-data tooltips (api/tasks.ts getStaleTooltipText) */
  stale: {
    attemptOnly: 'Execution attempts exist since {time}, but no successful data update yet (stale data)',
    lastSuccess: 'Stale data: last data update was at {time}',
    generic: 'Stale data: the last data update was too long ago'
  },
  logs: {
    title: 'Task Logs',
    statsTitle: 'Log Statistics',
    stat: {
      total: 'Total logs',
      success: 'Successful logs',
      failed: 'Failed logs',
      today: 'Today'
    },
    activeFilter: 'Current task filter',
    filter: {
      taskName: 'Task name',
      taskNamePlaceholder: 'Search task names',
      content: 'Log content',
      contentPlaceholder: 'Search log content',
      result: 'Result',
      success: 'Success',
      failed: 'Failure',
      search: 'Search',
      clear: 'Clear',
      timeRange: 'Time range',
      rangeSep: 'to',
      startPlaceholder: 'Start time',
      endPlaceholder: 'End time'
    },
    toolbar: {
      batchDelete: 'Batch delete',
      export: 'Export',
      exportCsv: 'Export as CSV',
      exportJson: 'Export as JSON',
      exportTxt: 'Export as TXT',
      cleanup: 'Clean up expired logs'
    },
    col: {
      taskName: 'Task Name',
      taskType: 'Task Type',
      startTime: 'Start Time',
      endTime: 'End Time',
      duration: 'Duration',
      result: 'Result',
      detail: 'Details'
    },
    viewDetail: 'View details',
    successTag: 'Success',
    failedTag: 'Failure'
  },
  form: {
    createTitle: 'New Task',
    editTitle: 'Edit Task',
    taskName: 'Task name',
    taskNamePlaceholder: 'Enter a task name',
    taskCode: 'Task code',
    taskCodePlaceholder: 'Enter a task code',
    taskType: 'Task type',
    taskTypePlaceholder: 'Select a task type',
    typeUnsupportedHint: ' (not supported on the current host profile)',
    executorClass: 'Execution class',
    cleanup: {
      label: 'Cleanup config',
      level3: 'Cleanup level 3',
      level4: 'Cleanup level 4',
      on: 'On',
      off: 'Off',
      level3Desc: 'Clean up torrents deleted at level 3',
      level3Unsupported: 'The current host does not support level-3 file operations',
      level4Desc: 'Clean up torrents deleted at level 4',
      daysLabel: 'Days threshold',
      daysPlaceholder: 'Days',
      daysDesc: 'Clean up torrents deleted more than N days ago (1-365)',
      previewBtn: 'Preview cleanup'
    },
    cronLabel: 'Schedule',
    cronError: 'Cron expression error: {message}',
    advancedCollapse: 'Collapse',
    advancedExpand: 'Expand',
    advancedSuffix: ' advanced settings',
    timeout: {
      label: 'Timeout',
      placeholder: 'seconds',
      desc: 'Task execution timeout in seconds; default 1 hour'
    },
    retry: {
      maxLabel: 'Max retries',
      placeholder: 'times',
      maxDesc: 'Maximum retries after failure; default no retry',
      intervalLabel: 'Retry interval',
      intervalPlaceholder: 'seconds',
      intervalDesc: 'Retry interval in seconds; default 5 minutes'
    },
    descLabel: 'Description',
    descPlaceholder: 'Task description (optional)',
    enabledOn: 'Enabled',
    enabledOff: 'Disabled',
    enabledOnDesc: 'Enabled: the task will run on schedule',
    enabledOffDesc: 'Disabled: the task will not run',
    cancel: 'Cancel',
    saving: 'Saving...',
    confirm: 'OK'
  },
  syntax: {
    lineError: 'Line {line}: {message}',
    viewAll: 'View all {count} errors',
    detailLine: 'Line {line}, column {col}:',
    passTitle: 'Syntax check passed',
    passDesc: 'The code syntax is correct and can be executed'
  },
  logDetail: {
    title: 'Task Execution Details',
    taskName: 'Task name: ',
    executeTime: 'Execution time: ',
    result: 'Result: ',
    duration: 'Duration: ',
    success: 'Success',
    failed: 'Failure',
    contentTitle: 'Execution details:',
    empty: 'No details available',
    close: 'Close',
    copy: 'Copy content',
    copyEmpty: 'Nothing to copy',
    copyDone: 'Content copied to clipboard',
    copyFailed: 'Copy failed, please copy manually',
    copyTaskName: 'Task name: ',
    copyStart: 'Start time: ',
    copyEnd: 'End time: ',
    copyResult: 'Result: ',
    copyDuration: 'Duration: ',
    copyDetail: 'Details: '
  },
  preview: {
    title: 'Cleanup Preview',
    level3: 'Level-3 torrents',
    level4: 'Level-4 torrents',
    total: 'Total',
    freed: 'Space freed',
    countSuffix: '',
    level3Detail: 'Level-3 torrent details (up to 20 shown)',
    level4Detail: 'Level-4 torrent details (up to 20 shown)',
    colName: 'Name',
    colSize: 'Size (GB)',
    colDeletedAt: 'Deleted at',
    colTags: 'Tags',
    close: 'Close'
  },
  cleanupDialog: {
    title: 'Clean Up Expired Logs',
    keepDays: 'Keep last N days',
    keepDaysHint: 'Logs older than this will be cleaned up',
    keepSuccess: 'Keep success logs',
    keepError: 'Keep failure logs',
    cancel: 'Cancel',
    confirm: 'Clean up'
  },
  msg: {
    fetchListFailed: 'Failed to load the task list',
    cleanupConfigParseFailed: 'Failed to parse the cleanup config; using defaults',
    noTaskId: 'Cannot resolve the task ID',
    logTaskFallback: 'Task {id}',
    switchedLogs: 'Switched to logs of task "{name}"',
    viewLogsFailed: 'Failed to view logs, please try again later',
    capabilityUnsupported: 'The current host capability does not support this task; not executed',
    taskDisabled: 'Task "{name}" is disabled and cannot be started. Enable it first.',
    executeSuccess: 'Task executed successfully',
    executeFailed: 'Failed to execute the task',
    deleteConfirm: 'Delete this task?',
    deleteSuccess: 'Deleted successfully',
    deleteFailed: 'Failed to delete the task',
    selectToEnable: 'Select tasks to enable',
    batchEnableConfirm: 'Enable the {count} selected tasks?',
    batchEnableTitle: 'Batch enable',
    batchEnableSuccess: 'Enabled {count} tasks',
    batchEnableFailed: 'Batch enable failed',
    selectToDisable: 'Select tasks to disable',
    batchDisableConfirm: 'Disable the {count} selected tasks?',
    batchDisableTitle: 'Batch disable',
    batchDisableSuccess: 'Disabled {count} tasks',
    batchDisableFailed: 'Batch disable failed',
    selectToDelete: 'Select tasks to delete',
    batchDeleteConfirm: 'Delete the {count} selected tasks? This cannot be undone!',
    batchDeleteTitle: 'Batch delete',
    batchDeleteSuccess: 'Deleted {count} tasks',
    batchDeleteFailed: 'Batch delete failed',
    batchDeleteFailedCount: 'Failed to delete {count} tasks',
    customScriptUnsupported: 'The current host profile does not support custom script tasks',
    level3Unsupported: 'The current host does not support level-3 file operations; disable level 3 before creating the task',
    updateSuccess: 'Updated successfully',
    createSuccess: 'Created successfully',
    taskCodeFormat: 'Invalid task code format',
    executorRequired: 'Enter the execution content',
    saveFailed: 'Failed to save the task',
    interruptSuccess: 'Task interrupted successfully',
    interruptFailed: 'Failed to interrupt the task',
    editorFallback: 'Failed to load the code editor; switched to basic mode',
    loadLogsFailed: 'Failed to load log data',
    fetchLogsFailed: 'Failed to load the log list',
    exportSuccess: 'Exported successfully',
    exportFailed: 'Export failed, please try again later',
    exportFilenamePrefix: 'task_logs_',
    cleanupDone: 'Log cleanup finished',
    cleanupFailed: 'Cleanup failed',
    cleanupRetry: 'Cleanup failed, please try again later',
    selectLogsToDelete: 'Select logs to delete',
    logDeleteConfirm: 'Delete the {count} selected logs?',
    logDeleteCancelled: 'Deletion cancelled',
    logDeleteSuccess: 'Deleted {count} logs',
    logDeleteFailed: 'Delete failed',
    logDeleteRetry: 'Delete failed, please try again later',
    previewFailed: 'Preview failed, please try again later',
    networkError: 'Network error, please check the connection',
    previewFailedWithReason: 'Preview failed: {message}'
  },
  dialog: {
    notice: 'Notice',
    confirm: 'OK',
    cancel: 'Cancel'
  },
  /** Cron expression editor (components/tasks/CronEditor.vue) */
  cronEditor: {
    tabs: {
      template: 'Templates',
      custom: 'Custom expression'
    },
    templateTitle: 'Choose a preset template',
    filterPlaceholder: 'Filter category',
    /** Filter values stay as Chinese data values (template category matching); only labels localize */
    category: {
      all: 'All',
      basic: 'Basic',
      hourly: 'Hourly',
      daily: 'Daily',
      workday: 'Workdays',
      weekend: 'Weekends'
    },
    customSection: 'Custom templates',
    addCustom: 'Add custom template',
    expressionLabel: 'Cron expression',
    validateBtn: 'Validate',
    formatHint: 'Format: minute hour day month weekday (0-59 0-23 1-31 1-12 0-6)',
    visualTitle: 'Visual builder',
    field: {
      minute: 'Minute',
      hour: 'Hour',
      day: 'Day',
      month: 'Month',
      weekday: 'Weekday',
      minuteShort: 'Min',
      hourShort: 'Hour',
      dayShort: 'Day',
      monthShort: 'Month',
      weekdaySun: 'Sun',
      weekdayMon: 'Mon',
      weekdayTue: 'Tue',
      weekdayWed: 'Wed',
      weekdayThu: 'Thu',
      weekdayFri: 'Fri',
      weekdaySat: 'Sat',
      tooltipMinute: 'Minute (0-59)',
      tooltipHour: 'Hour (0-23)',
      tooltipDay: 'Day (1-31, L=last day)',
      tooltipMonth: 'Month (1-12)',
      tooltipSun: 'Sunday',
      tooltipMon: 'Monday',
      tooltipTue: 'Tuesday',
      tooltipWed: 'Wednesday',
      tooltipThu: 'Thursday',
      tooltipFri: 'Friday',
      tooltipSat: 'Saturday',
      placeholderMinute: '0-59 or */5',
      placeholderHour: '0-23 or */2',
      placeholderDay: '1-31 or 1,15,L',
      placeholderMonth: '1-12 or 1,6,12'
    },
    preview: {
      title: 'Next execution preview',
      refresh: 'Refresh',
      nextExecute: 'Next run',
      empty: 'No upcoming executions'
    },
    validation: {
      validTitle: 'Expression is valid',
      invalidTitle: 'Expression is invalid',
      suggestion: 'Suggestions:'
    },
    addDialog: {
      title: 'Add Custom Template',
      nameLabel: 'Template name',
      namePlaceholder: 'e.g. Hourly backup',
      expressionLabel: 'Cron expression',
      descLabel: 'Description',
      descPlaceholder: 'What this template is for',
      cancel: 'Cancel',
      save: 'Save'
    },
    msg: {
      expressionEmpty: 'Cron expression cannot be empty',
      validateFailed: 'Validation failed, please check the expression format',
      validateUnavailable: 'Validation service unavailable',
      formatInvalid: 'Invalid cron expression format',
      customAdded: 'Custom template added'
    },
    time: {
      tomorrow: 'Tomorrow {time}',
      daysLater: 'in {count} days',
      hoursLater: 'in {count} hours',
      minutesLater: 'in {count} minutes',
      soon: 'soon'
    },
    rules: {
      expressionRequired: 'Enter a cron expression',
      expressionEmpty: 'Enter a cron expression',
      expressionFiveFields: 'The cron expression must contain 5 fields: minute hour day month weekday',
      fieldEmpty: 'Field {index} cannot be empty',
      fieldInvalid: 'Field {index} has an invalid format: {part}',
      syntaxErrorCount: 'Found {count} syntax errors',
      descLength: 'Description cannot exceed 200 characters',
      nameRequired: 'Enter a template name',
      nameLength: 'Template name must be 2-50 characters'
    },
    /** Built-in template display (name/description mapped by template key; identity matching still uses the stored name) */
    templates: {
      everyMinute: { name: 'Every minute', desc: 'Run once per minute' },
      every5Minutes: { name: 'Every 5 minutes', desc: 'Run once every 5 minutes' },
      every15Minutes: { name: 'Every 15 minutes', desc: 'Run once every 15 minutes' },
      every30Minutes: { name: 'Every 30 minutes', desc: 'Run once every 30 minutes' },
      hourly: { name: 'Hourly', desc: 'Run at minute 0 of every hour' },
      every2Hours: { name: 'Every 2 hours', desc: 'Run once every 2 hours' },
      daily: { name: 'Daily', desc: 'Run at 00:00 every day' },
      daily9am: { name: 'Daily at 9', desc: 'Run at 09:00 every day' },
      weekly: { name: 'Weekly', desc: 'Run at 00:00 every Sunday' },
      monthly: { name: 'Monthly', desc: 'Run at 00:00 on day 1 of every month' },
      workday: { name: 'Workdays', desc: 'Run at 09:00 Monday to Friday' },
      workdayAm: { name: 'Workday mornings', desc: 'Run at 09:00 and 17:00 on workdays' },
      weekend: { name: 'Weekends', desc: 'Run at 10:00 on Saturdays and Sundays' }
    }
  },
  /** Monaco code editor (components/tasks/MonacoEditor.vue) */
  monaco: {
    fallbackTitle: 'Editor failed to load',
    fallbackDesc: 'Switched to basic mode. You can continue with the plain text editor',
    retry: 'Retry loading',
    printQuoteHint: 'The print statement may be missing quotes'
  },
  /** Python class selector (components/tasks/PythonClassSelector.vue) */
  pythonSelector: {
    tabs: {
      preset: 'Preset classes',
      manual: 'Manual input'
    },
    presetTitle: 'Choose a system preset Python task class',
    searchPlaceholder: 'Search class name or description...',
    categoryFallback: 'Class',
    viewDetailTip: 'View class details',
    selectTip: 'Select this class',
    selectedTitle: 'Selected class',
    classPathLabel: 'Class path: ',
    descLabel: 'Description: ',
    noDesc: 'No description',
    paramsLabel: 'Parameters: ',
    manual: {
      classPathLabel: 'Class path',
      placeholder: 'e.g. app.tasks.custom.MyCustomTask',
      tooltip: 'Full module path.ClassName',
      formatHint: 'Format: module.path.ClassName, e.g. app.tasks.backup.BackupTask',
      templatesTitle: 'Common path templates',
      historyLabel: 'History',
      validationLabel: 'Validation status',
      validTitle: 'Class path is valid',
      invalidTitle: 'Class path is invalid',
      importable: 'Class exists and is importable',
      modulePath: 'Module path: ',
      classInfo: 'Class info: ',
      waitingTitle: 'Waiting for validation',
      waitingDesc: 'Click the validate button to check the class path',
      validateBtn: 'Validate class path',
      clearBtn: 'Clear'
    },
    detail: {
      title: 'Python Class Details',
      basic: 'Basic Info',
      path: 'Class path',
      module: 'Module',
      category: 'Type',
      status: 'Status',
      available: 'Available',
      unavailable: 'Unavailable',
      descTitle: 'Description',
      noDesc: 'No description',
      paramsTitle: 'Parameter Configuration',
      colName: 'Parameter',
      colType: 'Type',
      colRequired: 'Required',
      colDesc: 'Description',
      colDefault: 'Default',
      requiredYes: 'Yes',
      requiredNo: 'No',
      defaultRequired: 'Required',
      defaultOptional: 'Optional',
      methodsTitle: 'Available Methods',
      close: 'Close',
      select: 'Select this class'
    },
    msg: {
      validateFailed: 'Validation failed, please check the network connection',
      notAllowed: 'The class path is outside the allowed module scope',
      notAllowedClassInfo: 'Module outside the allowed scope',
      formatOkWaiting: 'Class path format is correct; awaiting runtime validation',
      needRuntimeCheck: 'Class existence needs to be verified at runtime',
      emptyPath: 'Class path cannot be empty'
    },
    rules: {
      classPathRequired: 'Enter a class path',
      classPathFormat: 'Invalid class path format; use dot-separated identifiers, e.g. app.tasks.MyTask'
    },
    validation: {
      formatInvalid: 'Invalid class path format; use dot-separated identifiers, e.g. app.tasks.MyTask',
      missingParts: 'The class path must contain at least one module name and a class name',
      classNameCase: 'The class name should start with an uppercase letter followed by letters or digits',
      formatOk: 'Format is correct'
    }
  }
}
