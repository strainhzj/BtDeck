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
 * Tracker domain copy (tracker group, en; key set identical to zh-CN, pinned by parity gate).
 */
export const tracker = {
  detail: {
    collapse: 'Collapse details',
    title: 'Tracker details - {name}',
    errorTitle: 'Torrent error reason',
    table: {
      name: 'Tracker name',
      announce: 'Announce info',
      actions: 'Actions'
    },
    status: {
      working: '✓ Working',
      failedPrefix: '✗ {reason}',
      failedFallback: 'Failed'
    },
    matched: 'Filter match',
    matchedTitle: 'Matches the current tracker domain filter: {domain}',
    unknownTracker: 'Unknown',
    reannounce: 'Reannounce',
    files: {
      tab: 'Files',
      loading: 'Loading file list...',
      loadFailed: 'Failed to load file list',
      empty: 'No file data',
      searchPlaceholder: 'Search file name',
      stale: 'Update failed, showing last data',
      noMatch: 'No files matching "{keyword}"',
      colName: 'File name',
      colSize: 'Size',
      colProgress: 'Progress',
      countTotal: '{total} files',
      countMatched: '{matched} / {total} files matched',
      countTruncatedPrefixMatched: '{total} files matched',
      truncateSuffix: ', showing first {max} only'
    },
    peers: {
      loading: 'Loading Peers list...',
      loadFailed: 'Failed to load Peers list',
      empty: 'No Peers data',
      countWithRefresh: '{total} Peers (auto-refreshes every 5 seconds)',
      countTotal: '{total} Peers',
      colAddress: 'Address',
      colClient: 'Client',
      colProgress: 'Progress',
      colDownSpeed: '↓ Speed',
      colUpSpeed: '↑ Speed'
    }
  },
  operation: {
    addTab: 'Add Trackers',
    modifyTab: 'Modify Trackers',
    scopeLabel: 'Scope',
    selectedTorrents: 'Selected torrents',
    trackerUrls: 'Tracker URLs',
    addPlaceholder:
      'Separate multiple tracker URLs with semicolons;\nFor example:\nhttps://tracker1.com/announce\nhttps://tracker2.com/announce',
    addHint: 'Multiple tracker URLs are supported, one per line or separated by semicolons',
    currentList: 'Current tracker list',
    status: 'Status',
    normal: 'Normal',
    abnormal: 'Error',
    newList: 'New tracker list',
    modifyPlaceholder:
      'Separate multiple tracker URLs with semicolons; this will fully replace the current tracker list\nFor example:\nhttps://tracker1.com/announce;https://tracker2.com/announce',
    noticeLabel: 'Note: ',
    noticeReplace: 'The modify operation fully replaces the current tracker list. Proceed with care',
    rules: {
      requiredUrl: 'Please enter tracker URLs',
      requiredNewList: 'Please enter the new tracker list'
    },
    validate: {
      invalidUrl: 'Please enter valid tracker URLs',
      badUrls: 'Invalid tracker URL format: {urls}'
    },
    scopeAllTorrents: 'All torrents of downloader "{name}"',
    scopeTotalSuffix: ' ({total} total)',
    addSubmitScoped: 'Add to all torrents of this downloader',
    addSubmitBatch: 'Batch add ({count} torrents)',
    addSubmitSingle: 'Add Trackers',
    modifySubmitScoped: 'Replace trackers of all torrents in this downloader',
    modifySubmitBatch: 'Batch modify ({count} torrents)',
    modifySubmitSingle: 'Modify Trackers',
    titleScoped: 'Tracker operation (by downloader) - {name}',
    titleBatch: 'Batch tracker operation - {count} torrents selected',
    titleSingle: 'Tracker operation - {name}',
    torrentFallbackName: 'torrent',
    resultSuffix: ' ({ok} succeeded)',
    resultSuffixWithFail: ' ({ok} succeeded, {fail} failed)',
    formNotReady: 'The form is not initialized yet, please retry shortly',
    addSuccess: 'Trackers added successfully',
    addFailed: 'Failed to add trackers',
    modifySuccess: 'Trackers modified successfully',
    modifyFailed: 'Failed to modify trackers',
    noTorrentId: 'No torrent ID obtained, please reselect torrents'
  },
  errorReason: {
    withMessage: 'Tracker announce failed: {message}',
    fallback: 'Tracker announce failed, see the Tracker tab for details'
  }
}
