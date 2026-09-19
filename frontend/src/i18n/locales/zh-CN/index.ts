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
 * zh-CN 消息根：navigation / time / el（Element UI 内置文案）。
 * el 子树来自 element-ui 语言包，经 ElementLocale.i18n 接管后随界面语言切换。
 */

import elementZhCN from 'element-ui/lib/locale/lang/zh-CN'
import { MessageTree } from '../../types'
import { auth } from './auth'
import { common } from './common'
import { dashboard } from './dashboard'
import { downloader } from './downloader'
import { errors } from './errors'
import { navigation } from './navigation'
import { search } from './search'
import { settings } from './settings'
import { time } from './time'
import { torrent } from './torrent'

const messages: MessageTree = {
  auth,
  common,
  dashboard,
  downloader,
  errors,
  navigation,
  search,
  settings,
  time,
  torrent,
  el: elementZhCN.el
}

export default messages
