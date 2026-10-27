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

/** Settings M1 scope (2FA / change password / diagnosis; host capability tab is M2). */
export const settings = {
  tabs: {
    twofa: 'Two-Factor Authentication',
    password: 'Change Password',
    mcp: 'MCP Service',
    moviepilot: 'MoviePilot',
    diagnosis: 'Diagnostics'
  },
  twofa: {
    title: 'Two-Factor Authentication',
    statusEnabled: 'enabled',
    enabledDesc: 'Two-factor authentication is currently {status}. Disabling it lowers account security; disable it only when necessary.',
    currentPassword: 'Current password',
    currentPasswordPlaceholder: 'Enter your current password',
    twofaCode: 'Two-factor code',
    twofaCodePlaceholder: 'Enter the 6-digit code from your authenticator',
    locked: 'Locked',
    lockedVerifyDesc: 'Too many failed verification attempts. You are locked out.',
    lockedPasswordDesc: 'Too many failed password attempts. You are locked out.',
    retryAfterSeconds: 'Retry in {seconds} seconds.',
    attemptsWarning: '{failed} failed attempts, {remaining} remaining',
    disable: 'Disable Two-Factor Authentication',
    verifyPasswordStepDesc: 'To protect your account, verify your current password before enabling two-factor authentication.',
    verifyPassword: 'Verify password',
    verifySuccess: 'Password verified',
    verifyFailed: 'Verification failed',
    passwordWrong: 'The password is incorrect',
    lockedFiveMinutes: 'Too many failed password attempts. Locked for 5 minutes.',
    lockedAttemptsFiveMinutes: 'Too many failed verification attempts. Locked for 5 minutes.',
    scanDesc: 'Scan the QR code below with an authenticator app (such as Google Authenticator or Authy), then enter the 6-digit code shown in the app to finish binding.',
    qrGenerating: 'Generating QR code...',
    manualEntryHint: 'QR code generation is unavailable in this environment (missing image dependency). Choose "Enter a setup key manually" in your authenticator app and enter:',
    copySecret: 'Copy key',
    secretCopied: 'Key copied',
    copyFailed: 'Copy failed. Select and copy the key manually.',
    manualEntryMeta: 'Account: {account} · Key type: time-based (TOTP) · Digits: 6 · Refresh: 30 seconds',
    code: 'Verification code',
    codePlaceholder: 'Enter the 6-digit code',
    codeRequired: 'Enter the 6-digit code',
    codeInvalid: 'Invalid verification code. Please try again.',
    userInfoFailed: 'Could not load your profile. Please sign in again.',
    confirmBinding: 'Confirm binding',
    bindSuccess: 'Two-factor authentication enabled',
    bindSuccessDesc: 'Your account is now more secure. A verification code will be required at the next sign-in.',
    bindFailed: 'Binding failed',
    usageTitle: 'How to use:',
    stepDownload: 'Install an authenticator app (such as Google Authenticator or Authy)',
    stepScan: 'Scan the QR code above',
    stepManual: 'Enter the key above manually',
    stepInput: 'Enter the 6-digit code shown in the app',
    stepConfirm: 'Click "Confirm binding" to finish',
    backupSecretTitle: 'Backup key (important!):',
    backupSecretWarning: '⚠️ This key is shown only once. Store it somewhere safe — if you lose access to your authenticator app, you can recover with this key.',
    closeSecretTitle: 'Confirm closing',
    closeSecretConfirm: 'You will not be able to view this key again. Close it anyway?',
    closed: 'Closed',
    disableConfirmTitle: 'Disable two-factor authentication',
    disableConfirm: 'Disabling two-factor authentication lowers account security. Continue?',
    confirmDisable: 'Disable',
    disableSuccess: 'Two-factor authentication disabled',
    fieldsRequired: 'Enter your current password and two-factor code',
    codeMustBeSixDigits: 'The two-factor code must be 6 digits',
    passwordRequired: 'Enter your password'
  },
  password: {
    title: 'Change Password',
    desc: 'Changing your password regularly keeps your account secure. Use a strong password.',
    oldPassword: 'Current password',
    oldPasswordPlaceholder: 'Enter your current password',
    newPassword: 'New password',
    newPasswordPlaceholder: 'Enter the new password',
    confirmPassword: 'Confirm password',
    confirmPasswordPlaceholder: 'Enter the new password again',
    mismatch: 'The two passwords do not match',
    confirm: 'Change password',
    success: 'Password changed. Please sign in again with the new password.',
    failed: 'Failed to change the password',
    userInfoFailed: 'Could not load your profile. Please sign in again.'
  },
  diagnosis: {
    title: 'Diagnostic Dump & Status Analysis',
    desc: 'Generate a diagnostic snapshot and export it as a JSON file for troubleshooting or status analysis. It includes server version and build identity, database/event-loop/sync-task health checks, downloader offline alerts, and process memory samples; it never contains credentials or tokens.',
    generating: 'Generating…',
    export: 'Generate & export diagnostic file',
    exported: 'Diagnostic file exported',
    failed: 'Failed to export the diagnostic file. Please try again later.'
  }
}
