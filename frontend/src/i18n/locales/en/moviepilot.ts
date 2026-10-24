/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * MoviePilot integration domain (settings panel + torrent detail "Media Library"
 * tab + association reverse lookup; bilingual batch after the v1.0.7 merge).
 * The shared subtree holds display values used by both the panel's reverse-lookup
 * card and the TrackerDetailCard media tab.
 */
export const moviepilot = {
  panel: {
    title: 'MoviePilot Integration',
    description: 'The MoviePilot plugin BtDeckBridge syncs its transfer history as a read-only mirror and links "media library file ↔ transfer source file ↔ BT task". This feature never writes to production tasks or to the MoviePilot side; if history disappears in MoviePilot, nothing is cleaned up locally.',
    loading: 'Loading...',
    loadFailed: 'Failed to load MoviePilot integration configuration.',
    retry: 'Retry',
    globalSwitch: 'Integration switch',
    stateOn: 'On',
    stateOff: 'Off',
    offHint: 'While off, plugin handshakes and syncs are rejected (403); already synced mirror data is kept. On the plugin side, configure the BtDeck address and a dedicated integration account (create a separate account and do not enable two-factor authentication on it).',
    neverSaved: 'Configuration has never been saved',
    revisionInfo: 'Current revision {revision} · {time}{by}',
    bySuffix: ' ({by})',
    discard: 'Discard changes',
    save: 'Save configuration',
    instancesTitle: 'Registered instances',
    refresh: 'Refresh',
    instancesDesc: 'The MoviePilot plugin registers automatically after its first handshake. Only after mapping "MoviePilot downloader → BtDeck downloader" can synced history be linked to tasks by (downloader, hash); mapping names must match the downloader names on the MoviePilot side.',
    noInstance: 'No instances yet. Once the BtDeckBridge plugin is installed in MoviePilot and completes a handshake, the instance appears here.',
    instanceEnabled: 'Enabled',
    instanceDisabled: 'Disabled',
    allowSync: 'Allow sync',
    deleteInstance: 'Delete instance',
    instanceIds: 'Instance {instanceId} · bound account {username}',
    moviepilotVersionSuffix: '· MoviePilot {version}',
    pluginVersionSuffix: '· plugin {version}',
    lastErrorPrefix: 'Last error: {error}',
    syncedCount: '{count} records synced',
    notSyncedYet: 'Never synced',
    mapping: {
      title: 'Downloader mapping',
      edit: 'Edit mapping',
      cancel: 'Cancel',
      save: 'Save mapping',
      mpPlaceholder: 'MoviePilot downloader name',
      btPlaceholder: 'BtDeck downloader',
      remove: 'Delete',
      add: '+ Add mapping',
      reparseNotice: 'After saving, all history of this instance is immediately re-resolved against the new mapping.',
      notConfigured: 'No mapping configured yet (history will be marked as unmapped).',
      saved: 'Mapping saved; association status of history re-resolved',
      saveFailed: 'Failed to save mapping',
      rowInvalid: 'Each mapping row needs both a MoviePilot downloader name and a BtDeck downloader',
      duplicateName: 'Duplicate MoviePilot downloader names are not allowed'
    },
    msg: {
      saved: 'MoviePilot integration configuration saved',
      conflict: 'The configuration was modified in another session; the latest configuration has been reloaded — review it and retry',
      saveFailed: 'Save failed; please try again later',
      instanceEnabled: 'Instance enabled',
      instanceDisabled: 'Instance disabled (handshake/sync will be rejected)',
      instanceUpdateFailed: 'Failed to update instance',
      deleteTitle: 'Delete instance',
      deleteConfirm: 'Deleting instance "{name}" also deletes its {count} synced history records, and this cannot be undone. Delete it?',
      deleteConfirmButton: 'Delete',
      instanceDeleted: 'Instance deleted',
      instanceDeleteFailed: 'Failed to delete instance'
    }
  },
  reverse: {
    title: 'Association reverse lookup',
    description: 'Enter a media library file/directory or a source file path to look up associated transfer history and BT tasks. Directories match contained files by prefix; history without a hash is marked as unassociated.',
    placeholder: 'e.g. /data/media/movies or /data/downloads/xxx.mkv',
    modeAll: 'All paths',
    modeSrc: 'Source only',
    modeDest: 'Library only',
    query: 'Search',
    pathRequired: 'Enter a path to look up',
    notFound: 'No matching transfer history found.',
    failed: 'Reverse lookup failed; please try again later',
    colTitle: 'Media title',
    colSeason: 'Season / Ep',
    colMode: 'Transfer mode',
    colDest: 'Library path',
    colSrc: 'Source path',
    colTask: 'Linked task'
  },
  shared: {
    transferMode: {
      copy: 'Copy',
      move: 'Move',
      link: 'Symlink',
      hardlink: 'Hardlink'
    },
    association: {
      linked: 'Linked',
      unmapped: 'Unmapped',
      unassociated: 'Unassociated'
    },
    unknownTitle: 'Unknown title'
  },
  media: {
    tab: 'Media Library',
    loading: 'Loading media library associations...',
    loadFailed: 'Failed to load media library associations',
    empty: 'No MoviePilot transfer records found (requires sync to have run and a downloader mapping configured)',
    count: '{count} transfer records in total',
    refresh: 'Refresh',
    stale: 'Update failed; showing last data',
    failedTag: 'Transfer failed',
    loadFailedFallback: 'Failed to load media library associations',
    colTitle: 'Media title',
    colSeason: 'Season / Ep',
    colMode: 'Transfer mode',
    colDest: 'Library path',
    colSrc: 'Source path',
    colInstance: 'Instance'
  }
}
