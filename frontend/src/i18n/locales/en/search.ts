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
  }
}
