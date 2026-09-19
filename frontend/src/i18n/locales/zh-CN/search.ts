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
 * 高级搜索共享层文案（search 组，P3-1）。
 *
 * 字段/分组标签按稳定字段 code（name/size/tags...）取键，不按中文 label 匹配；
 * 操作符展示名的唯一来源是后端契约（label/labelEn，经 generated.ts），
 * 不在语言包内复制，避免契约与文案双源漂移。
 */
export const search = {
  field: {
    tags: '标签',
    tracker_url: 'Tracker URL',
    tracker_msg: 'Tracker 信息',
    name: '种子名称',
    size: '种子大小',
    save_path: '保存路径',
    status: '状态',
    downloader_name: '下载器',
    category: '分类',
    super_seeding: '超级做种',
    added_date: '添加时间',
    completed_date: '完成时间',
    ratio: '比率',
    ratio_limit: '比率限制'
  },
  section: {
    advanced: '高级信息',
    basic: '基本信息',
    status: '状态信息',
    time: '时间信息',
    ratio: '比率信息'
  },
  operatorGroup: {
    basic: '基本操作'
  },
  value: {
    notSet: '未设置',
    unlimited: '无限制'
  },
  condition: {
    excludeSuffix: '（排除）'
  },
  preview: {
    empty: '暂无搜索条件',
    emptyValid: '暂无有效搜索条件',
    include: '包含',
    exclude: '排除',
    groupFallback: '条件组{index}'
  },
  superSeeding: {
    yes: '是',
    no: '否',
    unsupported: '不支持'
  },
  error: {
    groupNoConditions: '模板条件组{index}没有有效条件',
    unknownField: '模板包含未知字段：{field}',
    invalidFieldType: '模板字段类型无效：{type}',
    operatorNoExclude: '模板操作符“{operator}”不支持排除模式'
  }
}
