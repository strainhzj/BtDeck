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
 * Seed transfer / change location copy (transfer group, P6-1).
 *
 * Covers TransferDialog, BatchTransferDialog and SetLocationDialog.
 * Terminology per PLANS/bilingual/terminology.md: seed transfer; change location
 * (action label "Set location").
 */
export const transfer = {
  title: 'Transfer Torrent',
  batchTitle: 'Batch Transfer Torrents ({count} selected)',
  currentDownloader: 'Current downloader:',
  currentPath: 'Current path:',
  currentPaths: 'Current paths:',
  selectedTorrents: 'Selected torrents:',
  targetDownloader: 'Target downloader:',
  targetDownloaderPlaceholder: 'Select the target downloader',
  targetPath: 'Target path:',
  targetPathPlaceholder: 'Enter or select the target path',
  pathTypeDefault: 'Default path',
  pathTypeInUse: 'Path in use',
  torrentCount: '({count} torrents)',
  deleteSource: 'Remove source torrent task',
  deleteSourceHint: 'After a successful transfer, remove the torrent task from the source downloader and keep its data files. A second confirmation is required before removal.',
  cancel: 'Cancel',
  submit: 'Confirm',
  submitting: 'Transferring...',
  deleteConfirmTitle: 'Confirm Source Task Removal',
  deleteConfirmDone: 'The torrent was transferred to the target downloader',
  deleteConfirmQuestion: 'Remove the torrent task from the original downloader? Its data files will be kept.',
  deleteConfirmIrreversible: 'This removes the source torrent task only; its data files will remain.',
  deleting: 'Removing...',
  confirmDelete: 'Remove',
  continueConfirm: 'With "Remove source torrent task" checked, a successful transfer will remove the source torrent task and keep its data files. Continue?',
  batchContinueConfirm: 'With "Remove source torrent task" checked, a successful transfer will remove the source torrent tasks and keep their data files. Continue?',
  confirmActionTitle: 'Confirm Action',
  continueButton: 'Continue',
  resultTitle: 'Batch Transfer Finished',
  resultTotal: 'Total: {count}',
  resultSuccess: 'Succeeded: {count}',
  resultFailed: 'Failed: {count}',
  resultFailedList: 'Failed items:',
  unknownError: 'Unknown error',
  close: 'Close',
  validate: {
    selectTargetDownloader: 'Select the target downloader',
    sameAsCurrentDownloader: 'The target downloader must differ from the current one',
    sameAsSelectedDownloader: 'The target downloader must differ from the downloaders of the selected torrents',
    targetPathRequired: 'Enter the target path'
  },
  msg: {
    loadDownloadersFailed: 'Failed to load the downloader list',
    success: 'Torrent transferred',
    successWithDelete: 'Torrent transferred and the source torrent task was removed; data files were kept',
    failed: 'Transfer failed',
    failedWith: 'Transfer failed: {message}',
    failedRetry: 'Transfer failed, please try again later',
    deleteSourceFailed: 'Failed to remove the source torrent task',
    batchDeleteSourceFailed: 'An error occurred while removing source torrent tasks; please check manually',
    noTorrents: 'No torrents selected',
    missingSourceDownloader: 'Cannot determine the source downloader',
    batchFailed: 'Batch transfer failed',
    batchFailedWith: 'Batch transfer failed: {message}',
    deletingSource: 'Removing source torrent tasks...',
    batchSuccessDeleted: 'Batch transfer finished: {count} source torrent tasks removed; data files were kept'
  },
  setLocation: {
    title: 'Change Save Path ({count} selected)',
    moveFiles: 'Move downloaded files',
    moveFilesHint: 'When checked, downloaded files are moved to the new path; otherwise only the save path changes and existing files stay put',
    submitting: 'Submitting...',
    confirmMove: 'Move {count} torrents to the new path?\nThis will move the downloaded files to: {path}',
    confirmChange: 'Change the save path of {count} torrents?\nOnly the path changes; files are not moved.',
    submitted: 'Path change request submitted for {moved} torrents and is running in the background...',
    failed: 'Failed to change the save path'
  }
}
