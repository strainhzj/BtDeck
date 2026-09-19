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
 * Query template management page copy (queryTemplate group, en;
 * key set identical to zh-CN, pinned by parity gate).
 */
export const queryTemplate = {
  list: {
    title: 'Query Templates',
    subtitle: 'Centrally manage and reuse common simple queries and advanced search conditions',
    create: 'New Template',
    filterAria: 'Query template filters',
    nameLabel: 'Template name',
    namePlaceholder: 'Enter template name',
    sourceLabel: 'Template type',
    sourcePlaceholder: 'All types',
    sourceAll: 'All',
    simple: 'Simple query',
    advanced: 'Advanced search',
    search: 'Search',
    listTitle: 'Template List',
    listDesc: 'Built-in templates can only be applied; personal templates can be edited or deleted',
    countTag: '{count} templates',
    empty: 'No query templates',
    colName: 'Template Name',
    colDesc: 'Description',
    colType: 'Type',
    colSource: 'Source',
    colUsage: 'Usage',
    colCreated: 'Created At',
    colActions: 'Actions',
    tagSystem: 'Built-in',
    tagPublic: 'Public',
    tagPrivate: 'Private',
    applyTip: 'Apply template',
    editTip: 'Edit template',
    editDisabled: 'Built-in templates cannot be edited',
    deleteTip: 'Delete template',
    deleteDisabled: 'Built-in templates cannot be deleted',
    loadFailed: 'Failed to load templates',
    loadFailedWith: 'Failed to load templates: {message}',
    confirmDelete: 'Delete template "{name}"?',
    confirmTitle: 'Confirm',
    confirmOk: 'OK',
    deleteOk: 'Deleted successfully',
    deleteFailed: 'Delete failed',
    deleteFailedWith: 'Delete failed: {message}'
  },
  dialog: {
    editTitle: 'Edit Query Template',
    createTitle: 'New Query Template',
    nameLabel: 'Template name',
    namePlaceholder: 'Enter a template name',
    descLabel: 'Description',
    descPlaceholder: 'Optional, briefly describe the purpose of this template',
    typeLabel: 'Template type',
    simple: 'Simple query',
    advanced: 'Advanced search',
    statusFilter: 'Status filter',
    statusPlaceholder: 'Select torrent statuses (multiple allowed)',
    nameLike: 'Name keyword',
    nameLikePlaceholder: 'Fuzzy match on torrent name (optional)',
    categoryLike: 'Category keyword',
    categoryLikePlaceholder: 'Fuzzy match on category (optional)',
    tagsLike: 'Tag keyword',
    tagsLikePlaceholder: 'Fuzzy match on tags (optional)',
    trackerDomain: 'Tracker domain',
    trackerDomainPlaceholder: 'Select tracker domains (multiple allowed)',
    sortBy: 'Sort field',
    sortAddedDate: 'Added date',
    sortName: 'Name',
    sortSize: 'Size',
    sortDesc: 'Descending',
    sortAsc: 'Ascending',
    advancedHint:
      'Advanced search templates must be configured in the Torrents page via the advanced search panel, then saved',
    isPublic: 'Public',
    publicHint: 'Public templates are visible to all users',
    createBtn: 'Create',
    saveBtn: 'Save',
    rules: {
      nameRequired: 'Please enter a template name',
      lengthRange: 'Length must be 1 to 100 characters'
    },
    advancedFromTorrents:
      'Advanced search templates must be saved via the advanced search panel in the Torrents page',
    updated: 'Updated successfully',
    updateFailed: 'Update failed',
    created: 'Created successfully',
    createFailed: 'Create failed',
    saveFailedWith: 'Save failed: {message}'
  }
}
