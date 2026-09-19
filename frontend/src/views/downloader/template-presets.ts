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
 * 下载器设置模板：系统预设展示映射（双语 P6-2，P0 方案 system-content.md §2）。
 *
 * 契约：
 * - 系统预设身份 = `preset_key`（qb_standard / qb_highperf / tr_standard /
 *   tr_highperf / night_unlimited，P0 冻结）；展示层按 key 取本地化名称/描述；
 * - **不改用户可见的存储值**：API 仍返回数据库中的名称/描述（旧库中文名保留），
 *   仅展示映射（Q02）；
 * - 未登记 key 或用户自定义模板 → 原样返回 name/description（不猜、不覆盖）；
 * - 描述中的数值来自后端 preset 配置（app/data/default_templates.py），
 *   本地化文案与其保持一致（键值见 locales 下 downloader.template.presets 子树）。
 */
import i18n, { translate } from '@/i18n'

/** 设置模板展示所需的最小结构（兼容 camel/snake 与可选 preset_key）。 */
export interface TemplatePresetLike {
  name?: string | null
  description?: string | null
  preset_key?: string | null
  presetKey?: string | null
}

/** 读取 preset_key（snake 优先、camel 兼容）。 */
export function getTemplatePresetKey(template: TemplatePresetLike | null | undefined): string {
  if (!template) return ''
  const key = template.preset_key ?? template.presetKey
  return typeof key === 'string' ? key.trim() : ''
}

function presetKeyOf(template: TemplatePresetLike | null | undefined, field: 'name' | 'description'): string {
  const key = getTemplatePresetKey(template)
  if (!key) return ''
  const path = `downloader.template.presets.${key}.${field}`
  return i18n.te(path) || i18n.te(path, 'en') ? path : ''
}

/** 展示名称：系统预设按 preset_key 本地化，未登记/用户模板保留存储值（Q02）。 */
export function templateDisplayName(template: TemplatePresetLike | null | undefined): string {
  const path = presetKeyOf(template, 'name')
  if (path) return translate(path)
  return template?.name ?? ''
}

/** 展示描述：语义同 templateDisplayName（无描述回退空串）。 */
export function templateDisplayDescription(template: TemplatePresetLike | null | undefined): string {
  const path = presetKeyOf(template, 'description')
  if (path) return translate(path)
  return template?.description ?? ''
}
