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
 * 英文相对时间文案（复数「单|复」两态；choice=n 时 n>=2 走复数支）。
 * 口径与中文版档位一一对应，换算语义不变（F01）。
 */

export const time = {
  justNow: 'just now',
  minutesAgo: '{n} minute ago|{n} minutes ago',
  hoursAgo: '{n} hour ago|{n} hours ago',
  daysAgo: '{n} day ago|{n} days ago',
  weeksAgo: '{n} week ago|{n} weeks ago',
  monthsAgo: '{n} month ago|{n} months ago',
  yearsAgo: '{n} year ago|{n} years ago'
}
