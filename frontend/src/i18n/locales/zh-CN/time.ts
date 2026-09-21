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
 * 中文相对时间文案（F01：formatRelativeTime 七档）。
 * 复数格式「单|复」：中文两态一致，仅保持与英文同构以便参数校验。
 */

export const time = {
  justNow: '刚刚',
  minutesAgo: '{n}分钟前|{n}分钟前',
  hoursAgo: '{n}小时前|{n}小时前',
  daysAgo: '{n}天前|{n}天前',
  weeksAgo: '{n}周前|{n}周前',
  monthsAgo: '{n}个月前|{n}个月前',
  yearsAgo: '{n}年前|{n}年前'
}
