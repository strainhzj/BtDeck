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

/** 高级搜索共享层文案（search 组，en；键集与 zh-CN 完全一致，parity 门禁钉住）。 */
export const search = {
  field: {
    tags: 'Tags',
    tracker_url: 'Tracker URL',
    tracker_msg: 'Tracker message',
    name: 'Torrent name',
    size: 'Torrent size',
    save_path: 'Save path',
    status: 'Status',
    downloader_name: 'Downloader',
    category: 'Category',
    super_seeding: 'Super seeding',
    added_date: 'Added date',
    completed_date: 'Completed date',
    ratio: 'Ratio',
    ratio_limit: 'Ratio limit'
  },
  section: {
    advanced: 'Advanced',
    basic: 'Basic',
    status: 'Status',
    time: 'Time',
    ratio: 'Ratio'
  },
  operatorGroup: {
    basic: 'Basic operators'
  },
  value: {
    notSet: 'Not set',
    unlimited: 'Unlimited'
  },
  condition: {
    excludeSuffix: ' (excluded)'
  },
  preview: {
    empty: 'No search conditions',
    emptyValid: 'No valid search conditions',
    include: 'Include',
    exclude: 'Exclude',
    groupFallback: 'Group {index}'
  },
  superSeeding: {
    yes: 'Yes',
    no: 'No',
    unsupported: 'Unsupported'
  },
  error: {
    groupNoConditions: 'Template group {index} has no valid conditions',
    unknownField: 'Template contains unknown field: {field}',
    invalidFieldType: 'Template field type is invalid: {type}',
    operatorNoExclude: 'Template operator "{operator}" does not support exclude mode'
  },
  /** AdvancedSearchBuilder dialog shell (condition groups / buttons / preview / save, P3-2) */
  builder: {
    groupNamePlaceholder: 'Group name',
    groupFallbackName: 'Group {index}',
    renameGroup: 'Rename group',
    more: 'More',
    deleteGroup: 'Delete group',
    copyGroup: 'Duplicate group',
    clearConditions: 'Clear conditions',
    logicAnd: 'AND',
    logicOr: 'OR',
    rowLabelField: 'Field',
    rowLabelOperator: 'Operator',
    rowLabelValue: 'Value',
    rowLabelMode: 'Mode',
    selectFieldPlaceholder: 'Select field',
    selectOperatorPlaceholder: 'Select operator',
    include: 'Include',
    exclude: 'Exclude',
    addCondition: 'Add condition',
    addGroup: 'Add condition group',
    executeSearch: 'Search',
    saveAsTemplate: 'Save as template',
    resetConditions: 'Reset conditions',
    previewQuery: 'Preview query',
    previewTitle: 'Search condition preview',
    copyQuery: 'Copy query',
    copied: 'Query copied to clipboard',
    copyFailed: 'Copy failed',
    saveTemplateTitle: 'Save search template',
    templateNameLabel: 'Template name',
    templateNamePlaceholder: 'Enter template name',
    setAsDefault: 'Set as default',
    descriptionLabel: 'Description',
    descriptionPlaceholder: 'Optional: describe the purpose of this template',
    save: 'Save',
    groupLogicAndDesc: 'All conditions must be satisfied',
    groupLogicOrDesc: 'Any one condition is enough',
    betweenLogicAndDesc: 'AND with the next group',
    betweenLogicOrDesc: 'OR with the next group',
    copySuffix: ' (copy)',
    loadOptionsFailed: 'Failed to load search field options',
    nameRequired: 'Please enter a template name'
  },
  /** AdvancedSearchWorkspace sidebar and feedback (P3-2) */
  workspace: {
    sidebarAria: 'Saved advanced searches',
    savedTitle: 'Saved searches',
    newConfig: 'New search configuration',
    refreshSaved: 'Refresh saved searches',
    filterPlaceholder: 'Filter saved searches',
    tagSystem: 'Built-in',
    tagPublic: 'Public',
    tagPrivate: 'Personal',
    usageCount: 'Used {count} times',
    emptyNoMatch: 'No matching saved searches',
    emptyNone: 'No saved advanced searches yet',
    saveChanges: 'Save changes',
    delete: 'Delete',
    builderAria: 'Advanced search condition builder',
    editHintSelect: 'Select a personal search configuration first',
    editHintSystem: 'Built-in search configurations cannot be modified',
    editHintPublic: 'Only the creator can modify a public search configuration',
    editHintOk: 'Overwrite the selected search configuration with current conditions',
    deleteHintSelect: 'Select a personal search configuration first',
    deleteHintSystem: 'Built-in search configurations cannot be deleted',
    deleteHintPublic: 'Only the creator can delete a public search configuration',
    deleteHintOk: 'Delete the selected search configuration',
    loadFailed: 'Failed to load saved searches',
    applyInvalid: 'This search configuration has no valid advanced search conditions',
    loadConfigFailed: 'Failed to load search configuration',
    templateSaveFailed: 'Failed to save template',
    templateSaved: 'Template saved successfully',
    conditionsInvalid: 'Current search conditions are invalid',
    saveChangesFailed: 'Failed to save changes',
    configUpdated: 'Search configuration updated',
    confirmDelete: 'Delete search configuration "{name}"?',
    confirmDeleteTitle: 'Delete search configuration',
    confirmDeleteBtn: 'Delete',
    deleteFailed: 'Failed to delete search configuration',
    configDeleted: 'Search configuration deleted'
  },
  /** ConditionValueInput (P3-2) */
  valueInput: {
    noValueNeeded: 'No value needed',
    daysSuffix: 'days',
    yes: 'Yes',
    no: 'No',
    statusPaused: 'Paused',
    startPlaceholder: 'Start time',
    endPlaceholder: 'End time',
    rangeSeparator: 'to',
    minLabel: 'Min:',
    maxLabel: 'Max:',
    minPlaceholder: 'Minimum',
    maxPlaceholder: 'Maximum',
    unitPlaceholder: 'Unit',
    regexCaseSensitive: 'Case sensitive',
    regexCaseInsensitive: 'Ignore case',
    placeholder: {
      text: 'Enter text',
      number: 'Enter a number',
      datetime: 'Select date and time',
      select: 'Please select',
      tags: 'Select or enter tags',
      days: 'Enter days',
      dateRange: 'Select date range',
      sizeRange: 'Select size range',
      size: 'Enter size',
      regex: 'Enter regular expression',
      default: 'Please enter a value'
    },
    parentMissingSizeRange: 'Parent did not provide torrent size range state',
    parentMissingNumberRange: 'Parent did not provide number range state',
    parentMissingSize: 'Parent did not provide torrent size state'
  },
  /** SizeRangeFilter quick presets (P3-2) */
  sizeRange: {
    minLabel: 'Min:',
    maxLabel: 'Max:',
    numberPlaceholder: 'Enter a number',
    presetsLabel: 'Quick presets:',
    preset: {
      small: 'Small files (<100MB)',
      medium: 'Medium files (100MB-1GB)',
      large: 'Large files (1GB-10GB)',
      xlarge: 'Huge files (>10GB)',
      movie: 'HD movies (4GB-20GB)'
    },
    applied: 'Applied: {label}'
  },
  /** SearchTemplateDialog (torrents page search template dialog, P3-2) */
  templateDialog: {
    title: 'Search templates',
    applyTab: 'Apply template',
    saveTab: 'Save current search',
    empty: 'No saved templates',
    apply: 'Apply',
    nameLabel: 'Template name',
    namePlaceholder: 'Enter template name',
    descLabel: 'Description',
    descPlaceholder: 'Enter description',
    save: 'Save',
    nameRequired: 'Please enter a template name'
  },
  /** advancedSearchState.ts validation messages (translate(), P3-2) */
  validation: {
    mustBeFinite: '{label} must be a finite non-negative number',
    invalidUnit: 'The unit of {label} is invalid',
    mustBeLocalDate: '{label} must be a local date string',
    invalidFormat: '{label} has an invalid format',
    invalidDate: '{label} is not a valid date',
    tplValueStructure: 'Condition value structure in template is invalid',
    tplNumber: 'Number in template is invalid',
    tplMultiSelect: 'Multi-select value in template is invalid',
    tplSuperSeeding: 'Super seeding state in template is invalid',
    tplBoolean: 'Boolean value in template is invalid',
    tplText: 'Text value in template is invalid',
    tplUnknownOperator: 'Template contains an unknown operator: {operator}',
    notSelected: 'not selected',
    unknownOperator: 'Unknown search operator: {operator}',
    operatorNoExclude: 'Operator "{operator}" does not support exclude mode',
    sizeRangeStructure: 'Torrent size range structure is invalid',
    labelMinSize: 'minimum size',
    labelMaxSize: 'maximum size',
    sizeRangeOneBound: 'At least one bound of the size range is required',
    sizeRangeMinMax: 'Size range minimum cannot be greater than maximum',
    sizeStructure: 'Torrent size structure is invalid',
    labelTorrentSize: 'torrent size',
    regexStructure: 'Regex condition structure is invalid',
    regexEmpty: 'Regular expression cannot be empty',
    regexTooLong: 'Regular expression cannot exceed {max} characters',
    regexSyntax: 'Regular expression syntax is invalid',
    regexTooMany: 'At most {max} regex conditions are allowed',
    lastDaysStructure: 'Last-days structure is invalid',
    lastDaysRange: 'Last days must be an integer between 1 and 36500',
    dateRangeStructure: 'Date range structure is invalid',
    labelStartDate: 'start date',
    labelEndDate: 'end date',
    dateRangeOneBound: 'At least one bound of the date range is required',
    dateRangeOrder: 'Start date cannot be later than end date',
    numberRangeStructure: 'Number range structure is invalid',
    labelMinValue: 'minimum value',
    labelMaxValue: 'maximum value',
    numberRangeOneBound: 'At least one bound of the number range is required',
    numberRangeMinMax: 'Minimum value cannot be greater than maximum',
    labelNumber: 'number',
    labelDate: 'date',
    multiSelectOneValue: 'Multi-select condition requires at least one valid value',
    boolRequired: 'Boolean condition must explicitly choose yes or no',
    valueRequired: 'Condition value cannot be empty',
    groupsRequired: 'At least one condition group is required',
    groupLogicInvalid: 'Group logic of condition group {index} is invalid',
    groupNoConditions: 'Condition group {index} requires at least one condition',
    condNoField: 'Item {cond} of condition group {group} has no valid field selected',
    condNoExclude: 'Operator "{operator}" does not support exclude mode',
    fieldNoOperator: 'Field "{field}" does not support operator "{operator}"',
    missingBetweenLogic: 'Condition group {index} is missing valid group logic'
  },
  /** Built-in presets display (mapped by preset_key, Q01) */
  presets: {
    activeTorrents: {
      name: 'Active torrents',
      description: 'Torrents being downloaded or seeded'
    },
    errorStatus: {
      name: 'Error status',
      description: 'Torrents in error state (including tracker issues)'
    },
    paused: {
      name: 'Paused',
      description: 'All paused torrents'
    },
    largeFiles: {
      name: 'Large files',
      description: 'Torrents larger than 10 GB (advanced search)',
      groupName: 'Large files'
    }
  }
}
