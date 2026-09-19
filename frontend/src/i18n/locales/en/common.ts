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

/** Cross-page shared copy (common group, P2 first-use loop; P3-1 adds multiSelect/pageSize shared components). */
export const common = {
  adminName: 'Administrator',
  cancel: 'Cancel',
  close: 'Close',
  confirm: 'Confirm',
  refresh: 'Refresh',
  loadMore: 'Load more',
  copy: 'Copy',
  sessionExpired: 'Your session has expired. Please sign in again.',
  forceChangeHint: 'Please change your password first — only the settings page is available until then.',
  partialSuccess: 'Some operations succeeded',
  serviceUnavailable: 'The service is temporarily unavailable. Please try again later.',
  capabilityUnknown: 'Cannot verify server capabilities. This feature is temporarily disabled — check the connection and try again.',
  capabilityBlocked: 'The Android host server cannot access the downloader host file system, so this feature is unavailable.',
  notFound: {
    title: 'Page not found',
    desc: 'Sorry, the page you are looking for does not exist or has been removed.',
    hint: 'Check the URL or go back to the home page.',
    back: 'Go back',
    home: 'Home',
    helpTitle: 'Need help?',
    contactSupport: 'Contact support'
  },
  notifications: {
    title: 'Notifications',
    closeLabel: 'Close notifications',
    closeDetail: 'Close notification detail',
    empty: 'No notifications',
    markUnread: 'Mark as unread',
    markRead: 'Mark as read',
    remove: 'Delete',
    failedDetail: 'Failure details',
    viewRelease: 'View the full release on GitHub',
    filterAll: 'All',
    filterUnread: 'Unread',
    filterUpdate: 'Updates',
    filterSystem: 'System'
  },
  /** AdvancedMultiSelect shared multi-select (list filters / advanced search / mobile, same source) */
  multiSelect: {
    searchPlaceholder: 'Search options...',
    createOption: 'Create "{keyword}"',
    include: 'Include',
    exclude: 'Exclude',
    selectedLabel: 'selected',
    clear: 'Clear',
    removeItem: 'Remove {label}',
    emptyHint: 'Pick from the options below, or search to create',
    noMatch: 'No matching options',
    selectVisible: 'Select visible',
    deselectVisible: 'Deselect visible',
    selectAll: 'Select all options',
    clearAll: 'Clear all selections',
    pasteTitle: 'Bulk paste',
    parsedCount: 'Parsed {count} items',
    apply: 'Apply',
    virtualScroll: 'Virtual scrolling',
    showCount: 'Visible option limit',
    customSeparators: 'Custom separators',
    useSeparators: 'Separate multiple values with {separators}',
    separatorJoin: ', ',
    spaceSeparator: 'space',
    multiSelected: '{first} + {count} more',
    ariaSelect: 'Select multiple values',
    ariaClear: 'Clear selected values'
  },
  /** PageSizeCombobox */
  pageSize: {
    ariaLabel: 'Items per page',
    inputHint: 'Choose a preset or type 1-100000; press Enter or click away to apply',
    expand: 'Expand page size options',
    collapse: 'Collapse page size options',
    options: 'Page size presets'
  }
}
