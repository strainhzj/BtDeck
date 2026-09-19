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
 * Error contract copy (errors group: P2 M1 subset + P4 batch extension).
 * byCode keys are the camelCase form of backend data.reasonCode; unknown codes fall back to generic.
 * Matching by Chinese msg is forbidden (master plan §3.3).
 */
export const errors = {
  generic: 'Operation failed',
  unknown: 'Unknown error',
  /** Operation context composition (formatters.showErrorToast) */
  contextFailed: '{context} failed: {message}',
  network: {
    unavailable: 'Network connection failed. Please check your network.',
    checkSettings: 'Network connection failed. Please check your network settings.',
    generic: 'Network error'
  },
  /** HTTP status fallbacks (formatters.extractErrorMessage, leftover fix) */
  http: {
    '400': 'Bad request',
    '401': 'Unauthorized. Please sign in again.',
    '403': 'Access denied',
    '404': 'The requested resource does not exist',
    '422': 'Validation failed',
    '500': 'Internal server error',
    '502': 'Bad gateway',
    '503': 'Service unavailable'
  },
  httpFallback: 'Request failed ({status})',
  /** E17: 422 field validation mapped by pydantic type (field is the last loc segment identifier) */
  validation: {
    missing: 'Missing required field: {field}',
    tooShort: 'Not enough items: {field}',
    tooLong: 'Too many items: {field}',
    stringType: 'Invalid type: {field} must be text',
    intParsing: 'Invalid type: {field} must be an integer',
    boolParsing: 'Invalid type: {field} must be a boolean',
    greaterThan: 'Value too small: {field}',
    lessThan: 'Value too large: {field}',
    valueError: 'Invalid value: {field}',
    generic: 'Request validation failed ({field})'
  },
  byCode: {
    authRateLimited: 'Too many attempts. Please try again later.',
    authInvalidCredentials: 'Incorrect username or password.',
    authTotpRequired: 'Enter your two-factor code.',
    authTotpInvalid: 'Invalid verification code. Please try again.',
    authInternal: 'Something went wrong on the server. Please try again later.',
    authRefreshInvalid: 'Your session has expired. Please sign in again.',
    userNotFound: 'User not found.',
    userOrigPasswordInvalid: 'The current password is incorrect.',
    userPasswordUpdateFailed: 'Failed to change the password. Please try again later.',
    twofaForbidden: 'You are not allowed to manage another user\'s 2FA settings.',
    twofaInvalidOperation: 'Invalid 2FA operation.',
    twofaAlreadyEnabled: 'Two-factor authentication is already enabled for this account.',
    twofaPasswordRequired: 'Your current password is required to disable two-factor authentication.',
    twofaPasswordInvalid: 'The current password is incorrect.',
    twofaTotpRequired: 'A two-factor code is required to disable two-factor authentication.',
    twofaTotpInvalid: 'The two-factor code is incorrect.',
    downloaderAuthFailed: 'The downloader rejected the username or password.',
    downloaderNotFound: 'This downloader no longer exists.',
    downloaderOrigPasswordRequired: 'The original password is required when changing the username or password.',
    downloaderOrigPasswordInvalid: 'The original password is incorrect.',
    downloaderOrigPasswordUnverified: 'Could not verify the original password. Please try again later.',
    downloaderTestFailed: 'Connection test failed.',
    downloaderDbQueryFailed: 'Database query failed. Please try again later.',
    /* ↓ bilingual P4 extension: torrent ops / tracker / query templates / add chain */
    downloaderCacheUnavailable: 'The downloader cache service is unavailable. Please try again later.',
    downloaderOffline: 'The downloader is offline. Check its status and try again.',
    downloaderConnectionMissing: 'The downloader connection is unavailable. Please try again later.',
    downloaderNoTorrents: 'No torrents under this downloader.',
    torrentHashesRequired: 'Select at least one torrent to operate on.',
    torrentRecordsNotFound: 'No matching torrent records were found.',
    torrentOperationFailed: 'The torrent operation failed. Please try again later.',
    torrentOperationInternal: 'Something went wrong. Please try again later.',
    torrentFileRequired: 'Choose a .torrent file.',
    torrentFileInvalid: 'The torrent file is invalid or corrupted.',
    torrentInfoTimeout: 'Timed out fetching torrent info. Check the downloader connection.',
    torrentInfoUnavailable: 'The torrent was submitted, but its info is not yet available from the downloader.',
    torrentAddFailed: 'Failed to add the torrent. Please try again later.',
    torrentFilesRequired: 'Choose at least one .torrent file.',
    torrentStageFailed: 'Failed to upload the torrent files. Please try again.',
    torrentBatchSubmitFailed: 'Failed to submit the batch task. Please try again later.',
    torrentSyncFailed: 'Sync failed. Please try again later.',
    trackerUrlRequired: 'Enter at least one tracker URL.',
    trackerNotFound: 'No tracker matched the replace request.',
    trackerOperationInternal: 'The tracker operation failed. Please try again later.',
    searchTemplateNotFound: 'This query template does not exist.',
    searchTemplateForbidden: 'You are not allowed to modify this template.',
    searchTemplateInvalidConditions: 'The query conditions are invalid. Please check and try again.',
    searchTemplateCreateFailed: 'Failed to create the template. Please try again later.',
    searchTemplateListFailed: 'Failed to load templates. Please try again later.',
    searchTemplateUpdateFailed: 'Failed to update the template. Please try again later.',
    searchTemplateDeleteFailed: 'Failed to delete the template. Please try again later.',
    searchTemplateApplyFailed: 'Failed to apply the template. Please try again later.',
    internalError: 'Internal server error. Please try again later.',
    dbOperationFailed: 'Database operation failed. Please try again later.',
    /* Bilingual P5: deletion chain / recycle bin */
    torrentDeleteAccepted: 'Batch deletion task submitted and running in the background',
    torrentDeleteAlreadyProcessed: 'All selected torrents are already being handled by a deletion task',
    torrentDeleteTaskNotFound: 'The deletion task does not exist or has expired',
    torrentDeleteSubmitFailed: 'Failed to submit the deletion task. Please try again later.',
    torrentDeleteStatusQueryFailed: 'Failed to query the deletion task status. Please try again later.',
    torrentDeleteFailed: 'Failed to delete the torrents. Please try again later.',
    torrentDeleteInvalidParams: 'Invalid request parameters. Please check and retry.',
    downloaderUnsupportedType: 'Unsupported downloader type',
    downloaderAdapterInitFailed: 'Failed to initialize the downloader adapter. Please try again later.',
    recycleBinQueryFailed: 'Failed to query the recycle bin. Please try again later.',
    recycleRestoreFailed: 'Failed to restore the torrents. Please try again later.',
    recyclePreviewFailed: 'Failed to preview the cleanup. Please try again later.',
    recycleCleanupFailed: 'Failed to clean up the recycle bin. Please try again later.',
    notImplemented: 'This feature is not available yet'
  }
}
