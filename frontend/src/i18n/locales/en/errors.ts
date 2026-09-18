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
 * Error contract copy (errors group, M1 subset in the P2 batch).
 * byCode keys are the camelCase form of backend data.reasonCode; unknown codes fall back to generic.
 * Matching by Chinese msg is forbidden (master plan §3.3).
 */
export const errors = {
  generic: 'Operation failed',
  network: {
    unavailable: 'Network connection failed. Please check your network.',
    generic: 'Network error'
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
    downloaderDbQueryFailed: 'Database query failed. Please try again later.'
  }
}
