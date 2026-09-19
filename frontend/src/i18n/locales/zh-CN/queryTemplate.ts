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
 * 查询模板管理页文案（queryTemplate 组，P3-2：列表/筛选/新建/编辑/删除）。
 *
 * 注意：系统预设行的名称/描述按后端 preset_key 走 search.presets.* 展示映射
 * （Q01）；用户模板与未识别行保留原文（Q02）。状态筛选选项复用 torrent.status.*。
 */
export const queryTemplate = {
  list: {
    title: '查询模板',
    subtitle: '集中管理并复用常用的简单查询与高级搜索条件',
    create: '新建模板',
    filterAria: '查询模板筛选条件',
    nameLabel: '模板名称',
    namePlaceholder: '输入模板名称',
    sourceLabel: '模板类型',
    sourcePlaceholder: '全部类型',
    sourceAll: '全部',
    simple: '简单查询',
    advanced: '高级搜索',
    search: '搜索',
    listTitle: '模板列表',
    listDesc: '系统模板仅可应用，个人模板可以编辑或删除',
    countTag: '共 {count} 个模板',
    empty: '暂无查询模板',
    colName: '模板名称',
    colDesc: '描述',
    colType: '类型',
    colSource: '来源',
    colUsage: '使用次数',
    colCreated: '创建时间',
    colActions: '操作',
    tagSystem: '系统',
    tagPublic: '公开',
    tagPrivate: '私有',
    applyTip: '应用模板',
    editTip: '编辑模板',
    editDisabled: '系统模板不可编辑',
    deleteTip: '删除模板',
    deleteDisabled: '系统模板不可删除',
    loadFailed: '获取模板列表失败',
    loadFailedWith: '获取模板列表失败：{message}',
    confirmDelete: '确认删除模板 "{name}" 吗？',
    confirmTitle: '提示',
    confirmOk: '确定',
    deleteOk: '删除成功',
    deleteFailed: '删除失败',
    deleteFailedWith: '删除失败：{message}'
  },
  dialog: {
    editTitle: '编辑查询模板',
    createTitle: '新建查询模板',
    nameLabel: '模板名称',
    namePlaceholder: '请输入模板名称',
    descLabel: '模板描述',
    descPlaceholder: '可选，简要描述模板用途',
    typeLabel: '模板类型',
    simple: '简单查询',
    advanced: '高级搜索',
    statusFilter: '状态筛选',
    statusPlaceholder: '选择种子状态（可多选）',
    nameLike: '名称关键词',
    nameLikePlaceholder: '种子名称模糊匹配（可选）',
    categoryLike: '分类关键词',
    categoryLikePlaceholder: '分类模糊匹配（可选）',
    tagsLike: '标签关键词',
    tagsLikePlaceholder: '标签模糊匹配（可选）',
    trackerDomain: 'Tracker域名',
    trackerDomainPlaceholder: '选择tracker域名（可多选）',
    sortBy: '排序字段',
    sortAddedDate: '添加时间',
    sortName: '名称',
    sortSize: '大小',
    sortDesc: '降序',
    sortAsc: '升序',
    advancedHint: '高级搜索模板请在「种子管理」页面通过高级搜索面板配置条件后保存',
    isPublic: '是否公开',
    publicHint: '公开模板所有用户可见',
    createBtn: '创建',
    saveBtn: '保存',
    rules: {
      nameRequired: '请输入模板名称',
      lengthRange: '长度在 1 到 100 个字符'
    },
    advancedFromTorrents: '高级搜索模板请在「种子管理」页面通过高级搜索面板保存',
    updated: '更新成功',
    updateFailed: '更新失败',
    created: '创建成功',
    createFailed: '创建失败',
    saveFailedWith: '保存失败：{message}',
    saveFailed: '保存失败，请稍后重试'
  }
}
