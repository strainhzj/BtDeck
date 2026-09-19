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
 * 高级搜索共享层文案（search 组，P3-1；P3-2 扩 builder/workspace/valueInput/
 * sizeRange/templateDialog/validation/presets 子树）。
 *
 * 字段/分组标签按稳定字段 code（name/size/tags...）取键，不按中文 label 匹配；
 * 操作符展示名的唯一来源是后端契约（label/labelEn，经 generated.ts），
 * 不在语言包内复制，避免契约与文案双源漂移。
 *
 * presets：系统预设名称/描述/内置组名按后端 preset_key 展示映射（Q01），
 * zh 值与后端 DEFAULT_SEARCH_TEMPLATES 存储值逐字节一致；未识别行保留原文（Q02）。
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
  },
  /** AdvancedSearchBuilder 弹窗外壳（条件组/按钮/预览/保存模板，P3-2） */
  builder: {
    groupNamePlaceholder: '组名称',
    groupFallbackName: '条件组 {index}',
    renameGroup: '重命名条件组',
    more: '更多',
    deleteGroup: '删除组',
    copyGroup: '复制组',
    clearConditions: '清空条件',
    logicAnd: 'AND (并且)',
    logicOr: 'OR (或者)',
    rowLabelField: '字段',
    rowLabelOperator: '操作',
    rowLabelValue: '内容',
    rowLabelMode: '方式',
    selectFieldPlaceholder: '选择字段',
    selectOperatorPlaceholder: '选择操作',
    include: '包含',
    exclude: '排除',
    addCondition: '添加条件',
    addGroup: '添加条件组',
    executeSearch: '执行搜索',
    saveAsTemplate: '保存为模板',
    resetConditions: '重置条件',
    previewQuery: '预览查询',
    previewTitle: '搜索条件预览',
    copyQuery: '复制查询',
    copied: '查询已复制到剪贴板',
    copyFailed: '复制失败',
    saveTemplateTitle: '保存搜索模板',
    templateNameLabel: '模板名称',
    templateNamePlaceholder: '输入模板名称',
    setAsDefault: '设为默认',
    descriptionLabel: '描述',
    descriptionPlaceholder: '可选：描述此模板的用途',
    save: '保存',
    groupLogicAndDesc: '所有条件都必须满足',
    groupLogicOrDesc: '任意一个条件满足即可',
    betweenLogicAndDesc: '并且与下一个条件组',
    betweenLogicOrDesc: '或者与下一个条件组',
    copySuffix: ' (副本)',
    loadOptionsFailed: '加载搜索字段选项失败',
    nameRequired: '请输入模板名称'
  },
  /** AdvancedSearchWorkspace 侧栏与操作反馈（P3-2） */
  workspace: {
    sidebarAria: '已保存高级搜索',
    savedTitle: '已保存搜索',
    newConfig: '新建搜索配置',
    refreshSaved: '刷新已保存搜索',
    filterPlaceholder: '筛选已保存搜索',
    tagSystem: '系统',
    tagPublic: '公开',
    tagPrivate: '个人',
    usageCount: '使用 {count} 次',
    emptyNoMatch: '没有匹配的已保存搜索',
    emptyNone: '暂无已保存高级搜索',
    saveChanges: '保存更改',
    delete: '删除',
    builderAria: '高级搜索条件配置',
    editHintSelect: '请先选择一个个人搜索配置',
    editHintSystem: '系统搜索配置不可修改',
    editHintPublic: '公开搜索配置仅创建者可修改',
    editHintOk: '用当前条件覆盖已选择的搜索配置',
    deleteHintSelect: '请先选择一个个人搜索配置',
    deleteHintSystem: '系统搜索配置不可删除',
    deleteHintPublic: '公开搜索配置仅创建者可删除',
    deleteHintOk: '删除已选择的搜索配置',
    loadFailed: '获取已保存搜索失败',
    applyInvalid: '该搜索配置没有有效的高级搜索条件',
    loadConfigFailed: '加载搜索配置失败',
    templateSaveFailed: '模板保存失败',
    templateSaved: '模板保存成功',
    conditionsInvalid: '当前搜索条件无效',
    saveChangesFailed: '保存更改失败',
    configUpdated: '搜索配置已更新',
    confirmDelete: '确认删除搜索配置“{name}”吗？',
    confirmDeleteTitle: '删除搜索配置',
    confirmDeleteBtn: '删除',
    deleteFailed: '删除搜索配置失败',
    configDeleted: '搜索配置已删除'
  },
  /** ConditionValueInput 条件值输入器（P3-2） */
  valueInput: {
    noValueNeeded: '无需填写',
    daysSuffix: '天内',
    yes: '是',
    no: '否',
    statusPaused: '暂停',
    startPlaceholder: '开始时间',
    endPlaceholder: '结束时间',
    rangeSeparator: '至',
    minLabel: '最小:',
    maxLabel: '最大:',
    minPlaceholder: '最小值',
    maxPlaceholder: '最大值',
    unitPlaceholder: '单位',
    regexCaseSensitive: '区分大小写',
    regexCaseInsensitive: '不区分',
    placeholder: {
      text: '输入文本内容',
      number: '输入数字',
      datetime: '选择日期时间',
      select: '请选择',
      tags: '选择或输入标签',
      days: '输入天数',
      dateRange: '选择日期范围',
      sizeRange: '选择大小范围',
      size: '输入大小值',
      regex: '输入正则表达式',
      default: '请输入值'
    },
    parentMissingSizeRange: '父组件未提供种子大小范围状态',
    parentMissingNumberRange: '父组件未提供数值范围状态',
    parentMissingSize: '父组件未提供种子大小状态'
  },
  /** SizeRangeFilter 大小快捷预设（P3-2） */
  sizeRange: {
    minLabel: '最小值:',
    maxLabel: '最大值:',
    numberPlaceholder: '输入数字',
    presetsLabel: '快捷选择:',
    preset: {
      small: '小文件 (<100MB)',
      medium: '中文件 (100MB-1GB)',
      large: '大文件 (1GB-10GB)',
      xlarge: '超大文件 (>10GB)',
      movie: '高清电影 (4GB-20GB)'
    },
    applied: '已应用: {label}'
  },
  /** SearchTemplateDialog（种子页搜索模板弹窗，P3-2） */
  templateDialog: {
    title: '搜索模板',
    applyTab: '应用模板',
    saveTab: '保存当前搜索',
    empty: '暂无保存的模板',
    apply: '应用',
    nameLabel: '模板名称',
    namePlaceholder: '输入模板名称',
    descLabel: '描述',
    descPlaceholder: '输入描述',
    save: '保存',
    nameRequired: '请输入模板名称'
  },
  /** advancedSearchState.ts 校验消息（translate 消费，P3-2；zh 输出与原内联逐字节一致） */
  validation: {
    mustBeFinite: '{label}必须是有限的非负数',
    invalidUnit: '{label}的单位无效',
    mustBeLocalDate: '{label}必须是本地日期字符串',
    invalidFormat: '{label}格式无效',
    invalidDate: '{label}不是有效日期',
    tplValueStructure: '模板中的条件值结构无效',
    tplNumber: '模板中的数值无效',
    tplMultiSelect: '模板中的多选值无效',
    tplSuperSeeding: '模板中的超级做种状态无效',
    tplBoolean: '模板中的布尔值无效',
    tplText: '模板中的文本值无效',
    tplUnknownOperator: '模板包含未知操作符：{operator}',
    notSelected: '未选择',
    unknownOperator: '未知搜索操作符：{operator}',
    operatorNoExclude: '操作符“{operator}”不支持排除模式',
    sizeRangeStructure: '种子大小范围结构无效',
    labelMinSize: '最小大小',
    labelMaxSize: '最大大小',
    sizeRangeOneBound: '大小范围至少填写一个边界',
    sizeRangeMinMax: '大小范围最小值不能大于最大值',
    sizeStructure: '种子大小结构无效',
    labelTorrentSize: '种子大小',
    regexStructure: '正则条件结构无效',
    regexEmpty: '正则表达式不能为空',
    regexTooLong: '正则表达式不能超过{max}个字符',
    regexSyntax: '正则表达式语法无效',
    regexTooMany: '正则条件最多允许{max}个',
    lastDaysStructure: '最近天数结构无效',
    lastDaysRange: '最近天数必须是1到36500的整数',
    dateRangeStructure: '日期范围结构无效',
    labelStartDate: '开始日期',
    labelEndDate: '结束日期',
    dateRangeOneBound: '日期范围至少填写一个边界',
    dateRangeOrder: '开始日期不能晚于结束日期',
    numberRangeStructure: '数值范围结构无效',
    labelMinValue: '最小值',
    labelMaxValue: '最大值',
    numberRangeOneBound: '数值范围至少填写一个边界',
    numberRangeMinMax: '最小值不能大于最大值',
    labelNumber: '数值',
    labelDate: '日期',
    multiSelectOneValue: '多选条件至少选择一个有效值',
    boolRequired: '布尔条件必须明确选择是或否',
    valueRequired: '条件值不能为空',
    groupsRequired: '至少需要一个条件组',
    groupLogicInvalid: '条件组{index}的组内逻辑无效',
    groupNoConditions: '条件组{index}至少需要一个条件',
    condNoField: '条件组{group}第{cond}项未选择有效字段',
    condNoExclude: '操作符“{operator}”不支持排除模式',
    fieldNoOperator: '字段“{field}”不支持操作符“{operator}”',
    missingBetweenLogic: '条件组{index}缺少有效的组间逻辑'
  },
  /** 系统预设展示（按 preset_key 映射，Q01；zh 与后端存储值逐字节一致） */
  presets: {
    activeTorrents: {
      name: '活跃种子',
      description: '正在下载或做种的种子'
    },
    errorStatus: {
      name: '错误状态',
      description: '处于错误状态的种子（含 tracker 异常）'
    },
    paused: {
      name: '已暂停',
      description: '所有已暂停的种子'
    },
    largeFiles: {
      name: '大文件',
      description: '大于 10GB 的种子（高级搜索）',
      groupName: '大文件'
    }
  }
}
