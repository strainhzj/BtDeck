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
 * en 消息根：结构必须与 zh-CN/index.ts 完全一致（parity 测试钉住）。
 */

import elementEn from 'element-ui/lib/locale/lang/en'
import { MessageTree } from '../../types'
import { auditLogs } from './auditLogs'
import { auth } from './auth'
import { common } from './common'
import { dashboard } from './dashboard'
import { downloader } from './downloader'
import { errors } from './errors'
import { fileManagement } from './fileManagement'
import { mcp } from './mcp'
import { moviepilot } from './moviepilot'
import { navigation } from './navigation'
import { orphanFiles } from './orphanFiles'
import { queryTemplate } from './queryTemplate'
import { recycleBin } from './recycleBin'
import { search } from './search'
import { statistics } from './statistics'
import { tasks } from './tasks'
import { settings } from './settings'
import { time } from './time'
import { transfer } from './transfer'
import { torrent } from './torrent'
import { tracker } from './tracker'

const messages: MessageTree = {
  auditLogs,
  auth,
  common,
  dashboard,
  downloader,
  errors,
  fileManagement,
  mcp,
  moviepilot,
  navigation,
  orphanFiles,
  queryTemplate,
  recycleBin,
  search,
  statistics,
  tasks,
  settings,
  time,
  torrent,
  transfer,
  tracker,
  el: elementEn.el
}

export default messages
