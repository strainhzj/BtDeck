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
 * 定时任务域文案（P6-4a：任务页 + Cron/Monaco/Python 类选择三组件 + api/tasks 共享展示层）。
 *
 * 边界：
 * - 后端 taskStatusName/taskTypeName/taskTypeName(日志) 中文值属数据语义匹配
 *   （isTaskExecutable/getStatusTag/getTemplateTagType 等），展示按稳定码位
 *   （taskStatus/taskType/outcome）映射本组键，未知值回退原文（Q02）；
 * - CronEditor 内置模板 name/category 为数据身份（选择匹配/过滤/CSS 类），
 *   展示按模板 key 映射 templates.*，自定义模板（用户数据）原文直出（Q02）；
 * - PythonClassSelector 预定义类列表由后端 type-config pythonClasses 驱动，
 *   后端中文描述按 Q02 原始数据透传，不落键；
 * - 后端 cronTasks 端点 msg 属原始数据原文透传（E03），不在本组；
 * - 「确定/取消/提示」与 common.confirm（「确认」）措辞不同，保持原页面措辞零回归。
 */
export const tasks = {
  tabs: {
    management: '任务管理',
    logs: '任务日志'
  },
  list: {
    title: '任务列表',
    filter: {
      taskName: '任务名称',
      taskNamePlaceholder: '请输入任务名称',
      taskCode: '任务编码',
      taskCodePlaceholder: '请输入任务编码',
      enabled: '是否启用',
      selectPlaceholder: '请选择',
      enabledOption: '启用',
      disabledOption: '禁用',
      taskType: '任务类型'
    },
    query: '查询',
    reset: '重置',
    toolbar: {
      enable: '启用',
      pause: '暂停',
      delete: '删除',
      recheck: '重检',
      refresh: '刷新',
      create: '新增任务'
    },
    col: {
      taskName: '任务名称',
      taskCode: '任务编码',
      taskType: '任务类型',
      status: '状态',
      enabled: '启用状态',
      cron: 'Cron表达式',
      lastExecute: '上次执行',
      actions: '操作'
    },
    platformDisabled: '平台禁用',
    enabledTag: '已启用',
    disabledTag: '已禁用',
    dataStale: '数据陈旧',
    menu: {
      actions: '操作',
      execute: '立即执行',
      edit: '编辑',
      logs: '查看日志',
      interrupt: '中断',
      delete: '删除'
    },
    tip: {
      executeUnsupported: '当前主机能力不支持，任务不会执行',
      executeDisabled: '任务已禁用，请先启用'
    },
    pagination: {
      prefix: '共 ',
      middle: ' 条，第 ',
      suffix: ' 页',
      perPageSuffix: ' 条/页'
    }
  },
  /** 任务类型（按稳定码位映射；两处兜底措辞不同，勿合并） */
  type: {
    shell: 'shell脚本',
    cmd: 'cmd脚本',
    powershell: 'powershell脚本',
    python: 'python脚本',
    pythonClass: 'python内部类',
    cleanup: '清理回收站',
    unknownShort: '未知',
    unknownType: '未知类型',
    /** getExecutorLabel 的兜底（执行内容表单项标签） */
    executorFallback: '执行内容',
    executorShell: 'Shell脚本',
    executorCmd: 'Cmd脚本',
    executorPowershell: 'PowerShell脚本',
    executorPython: 'Python脚本'
  },
  /** 任务状态（后端 taskStatus 码 0/1/2；taskStatusName 中文值仅作数据匹配） */
  status: {
    waiting: '等待运行',
    running: '运行中',
    idle: '空闲',
    unknown: '未知状态'
  },
  /** 执行结果六态（api/tasks.ts getTaskOutcomeMeta 唯一事实来源） */
  outcome: {
    success: '成功',
    partial: '部分成功',
    skipped: '已跳过',
    failed: '失败',
    noAction: '无变化',
    cancelled: '已取消'
  },
  /** 数据陈旧 tooltip（api/tasks.ts getStaleTooltipText） */
  stale: {
    attemptOnly: '任务自 {time} 起已有执行尝试，但尚无成功数据更新（数据陈旧）',
    lastSuccess: '数据陈旧：最后数据更新时间为 {time}',
    generic: '数据陈旧：最近一次数据更新距今过久'
  },
  logs: {
    title: '任务日志',
    statsTitle: '日志统计',
    stat: {
      total: '总日志数',
      success: '成功日志',
      failed: '失败日志',
      today: '今日日志'
    },
    activeFilter: '当前任务筛选',
    filter: {
      taskName: '任务名称',
      taskNamePlaceholder: '搜索任务名称',
      content: '日志内容',
      contentPlaceholder: '搜索日志内容',
      result: '执行结果',
      success: '成功',
      failed: '失败',
      search: '搜索',
      clear: '清空',
      timeRange: '时间范围',
      rangeSep: '至',
      startPlaceholder: '开始时间',
      endPlaceholder: '结束时间'
    },
    toolbar: {
      batchDelete: '批量删除',
      export: '导出',
      exportCsv: '导出为 CSV',
      exportJson: '导出为 JSON',
      exportTxt: '导出为 TXT',
      cleanup: '清理过期日志'
    },
    col: {
      taskName: '任务名称',
      taskType: '任务类型',
      startTime: '开始时间',
      endTime: '结束时间',
      duration: '耗时',
      result: '执行结果',
      detail: '执行详情'
    },
    viewDetail: '查看详情',
    successTag: '成功',
    failedTag: '失败'
  },
  form: {
    createTitle: '新增任务',
    editTitle: '编辑任务',
    taskName: '任务名称',
    taskNamePlaceholder: '请输入任务名称',
    taskCode: '任务编码',
    taskCodePlaceholder: '请输入任务编码',
    taskType: '任务类型',
    taskTypePlaceholder: '请选择任务类型',
    typeUnsupportedHint: '（当前主机形态不支持）',
    executorClass: '执行类',
    cleanup: {
      label: '清理配置',
      level3: '清理等级3',
      level4: '清理等级4',
      on: '启用',
      off: '禁用',
      level3Desc: '清理等级为3的种子',
      level3Unsupported: '当前主机不支持等级3文件操作',
      level4Desc: '清理等级为4的种子',
      daysLabel: '天数阈值',
      daysPlaceholder: '天数',
      daysDesc: '清理多少天前的种子（1-365天）',
      previewBtn: '预览清理'
    },
    cronLabel: '执行计划',
    cronError: 'Cron表达式错误: {message}',
    advancedCollapse: '收起',
    advancedExpand: '展开',
    advancedSuffix: '高级配置',
    timeout: {
      label: '超时时间',
      placeholder: '秒',
      desc: '任务执行超时时间(秒), 默认1小时'
    },
    retry: {
      maxLabel: '最大重试次数',
      placeholder: '次数',
      maxDesc: '失败后最大重试次数, 默认不重试',
      intervalLabel: '重试间隔',
      intervalPlaceholder: '秒',
      intervalDesc: '重试间隔时间(秒), 默认5分钟'
    },
    descLabel: '任务描述',
    descPlaceholder: '任务描述（可选）',
    enabledOn: '启用',
    enabledOff: '禁用',
    enabledOnDesc: '启用状态：任务将按计划执行',
    enabledOffDesc: '禁用状态：任务不会执行',
    cancel: '取消',
    saving: '保存中...',
    confirm: '确定'
  },
  syntax: {
    lineError: '第{line}行：{message}',
    viewAll: '查看全部 {count} 个错误',
    detailLine: '第{line}行, 第{col}列:',
    passTitle: '语法检查通过',
    passDesc: '代码语法正确, 可以正常执行'
  },
  logDetail: {
    title: '任务执行详情',
    taskName: '任务名称：',
    executeTime: '执行时间：',
    result: '执行结果：',
    duration: '执行耗时：',
    success: '成功',
    failed: '失败',
    contentTitle: '执行详情内容：',
    empty: '暂无详情信息',
    close: '关闭',
    copy: '复制内容',
    copyEmpty: '暂无内容可复制',
    copyDone: '内容已复制到剪贴板',
    copyFailed: '复制失败，请手动复制内容',
    copyTaskName: '任务名称：',
    copyStart: '开始时间：',
    copyEnd: '结束时间：',
    copyResult: '执行结果：',
    copyDuration: '执行耗时：',
    copyDetail: '执行详情：'
  },
  preview: {
    title: '清理预览',
    level3: '等级3种子',
    level4: '等级4种子',
    total: '总计',
    freed: '释放空间',
    countSuffix: ' 个',
    level3Detail: '等级3种子详情（最多显示20条）',
    level4Detail: '等级4种子详情（最多显示20条）',
    colName: '名称',
    colSize: '大小(GB)',
    colDeletedAt: '删除时间',
    colTags: '标签',
    close: '关闭'
  },
  cleanupDialog: {
    title: '清理过期日志',
    keepDays: '保留最近天数',
    keepDaysHint: '清理此天数之前的日志',
    keepSuccess: '保留成功日志',
    keepError: '保留失败日志',
    cancel: '取消',
    confirm: '确定清理'
  },
  msg: {
    fetchListFailed: '获取任务列表失败',
    cleanupConfigParseFailed: '清理任务配置解析失败，使用默认配置',
    noTaskId: '无法获取任务ID',
    logTaskFallback: '任务 {id}',
    switchedLogs: '已切换到任务"{name}"的日志',
    viewLogsFailed: '查看日志失败，请稍后重试',
    capabilityUnsupported: '当前主机能力不支持该任务，未执行',
    taskDisabled: '任务 "{name}" 已禁用，无法启动。请先启用该任务。',
    executeSuccess: '任务执行成功',
    executeFailed: '执行任务失败',
    deleteConfirm: '确定要删除这个任务吗?',
    deleteSuccess: '删除成功',
    deleteFailed: '删除任务失败',
    selectToEnable: '请选择要启用的任务',
    batchEnableConfirm: '确定要启用选中的 {count} 个任务吗？',
    batchEnableTitle: '批量启用',
    batchEnableSuccess: '成功启用 {count} 个任务',
    batchEnableFailed: '批量启用失败',
    selectToDisable: '请选择要禁用的任务',
    batchDisableConfirm: '确定要禁用选中的 {count} 个任务吗？',
    batchDisableTitle: '批量禁用',
    batchDisableSuccess: '成功禁用 {count} 个任务',
    batchDisableFailed: '批量禁用失败',
    selectToDelete: '请选择要删除的任务',
    batchDeleteConfirm: '确定要删除选中的 {count} 个任务吗？此操作不可恢复！',
    batchDeleteTitle: '批量删除',
    batchDeleteSuccess: '成功删除 {count} 个任务',
    batchDeleteFailed: '批量删除失败',
    batchDeleteFailedCount: '{count}个任务删除失败',
    customScriptUnsupported: '当前主机形态不支持自定义脚本任务',
    level3Unsupported: '当前主机不支持等级3文件操作，请关闭等级3后再创建任务',
    updateSuccess: '更新成功',
    createSuccess: '创建成功',
    taskCodeFormat: '任务编码格式不正确',
    executorRequired: '请输入执行内容',
    saveFailed: '保存任务失败',
    interruptSuccess: '任务中断成功',
    interruptFailed: '中断任务失败',
    editorFallback: '代码编辑器加载失败，已切换到基础模式',
    loadLogsFailed: '加载日志数据失败',
    fetchLogsFailed: '获取日志列表失败',
    exportSuccess: '导出成功',
    exportFailed: '导出失败，请稍后重试',
    exportFilenamePrefix: '任务日志_',
    cleanupDone: '日志清理完成',
    cleanupFailed: '清理失败',
    cleanupRetry: '清理失败，请稍后重试',
    selectLogsToDelete: '请选择要删除的日志',
    logDeleteConfirm: '确定要删除选中的 {count} 条日志吗？',
    logDeleteCancelled: '已取消删除',
    logDeleteSuccess: '成功删除 {count} 条日志',
    logDeleteFailed: '删除失败',
    logDeleteRetry: '删除失败，请稍后重试',
    previewFailed: '预览失败，请稍后重试',
    networkError: '网络异常，请检查连接',
    previewFailedWithReason: '预览失败：{message}'
  },
  dialog: {
    notice: '提示',
    confirm: '确定',
    cancel: '取消'
  },
  /** Cron 表达式编辑器（components/tasks/CronEditor.vue） */
  cronEditor: {
    tabs: {
      template: '模板选择',
      custom: '自定义表达式'
    },
    templateTitle: '选择预设模板',
    filterPlaceholder: '筛选分类',
    /** 筛选 value 保持中文数据值（模板 category 匹配），仅 label 本地化 */
    category: {
      all: '全部',
      basic: '基础',
      hourly: '小时',
      daily: '日常',
      workday: '工作日',
      weekend: '周末'
    },
    customSection: '自定义模板',
    addCustom: '添加自定义模板',
    expressionLabel: 'Cron表达式',
    validateBtn: '验证',
    formatHint: '格式：分 时 日 月 周 (0-59 0-23 1-31 1-12 0-6)',
    visualTitle: '可视化配置',
    field: {
      minute: '分钟',
      hour: '小时',
      day: '日期',
      month: '月份',
      weekday: '星期',
      minuteShort: '分',
      hourShort: '时',
      dayShort: '日',
      monthShort: '月',
      weekdaySun: '日',
      weekdayMon: '一',
      weekdayTue: '二',
      weekdayWed: '三',
      weekdayThu: '四',
      weekdayFri: '五',
      weekdaySat: '六',
      tooltipMinute: '分 (0-59)',
      tooltipHour: '时 (0-23)',
      tooltipDay: '日 (1-31, L=最后一天)',
      tooltipMonth: '月 (1-12)',
      tooltipSun: '星期日',
      tooltipMon: '星期一',
      tooltipTue: '星期二',
      tooltipWed: '星期三',
      tooltipThu: '星期四',
      tooltipFri: '星期五',
      tooltipSat: '星期六',
      placeholderMinute: '0-59 或 */5',
      placeholderHour: '0-23 或 */2',
      placeholderDay: '1-31 或 1,15,L',
      placeholderMonth: '1-12 或 1,6,12'
    },
    preview: {
      title: '下次执行时间预览',
      refresh: '刷新',
      nextExecute: '下次执行',
      empty: '暂无执行时间'
    },
    validation: {
      validTitle: '表达式有效',
      invalidTitle: '表达式有误',
      suggestion: '建议：'
    },
    addDialog: {
      title: '添加自定义模板',
      nameLabel: '模板名称',
      namePlaceholder: '例如：每小时备份',
      expressionLabel: 'Cron表达式',
      descLabel: '描述',
      descPlaceholder: '模板用途说明',
      cancel: '取消',
      save: '保存'
    },
    msg: {
      expressionEmpty: 'Cron表达式不能为空',
      validateFailed: '验证失败，请检查表达式格式',
      validateUnavailable: '验证服务不可用',
      formatInvalid: 'Cron表达式格式不正确',
      customAdded: '自定义模板添加成功'
    },
    time: {
      tomorrow: '明天 {time}',
      daysLater: '{count}天后',
      hoursLater: '{count}小时后',
      minutesLater: '{count}分钟后',
      soon: '即将执行'
    },
    rules: {
      expressionRequired: '请输入Cron表达式',
      expressionEmpty: '请输入Cron表达式',
      expressionFiveFields: 'Cron表达式必须包含5个字段：分 时 日 月 周',
      fieldEmpty: '第{index}个字段不能为空',
      fieldInvalid: '第{index}个字段格式不正确: {part}',
      syntaxErrorCount: '发现 {count} 个语法错误',
      nameRequired: '请输入模板名称',
      nameLength: '模板名称长度在2-50个字符',
      descLength: '描述不能超过200个字符'
    },
    /** 内置模板展示（name/description 按模板 key 映射；身份匹配仍用中文 name） */
    templates: {
      everyMinute: { name: '每分钟', desc: '每分钟执行一次' },
      every5Minutes: { name: '每5分钟', desc: '每5分钟执行一次' },
      every15Minutes: { name: '每15分钟', desc: '每15分钟执行一次' },
      every30Minutes: { name: '每30分钟', desc: '每30分钟执行一次' },
      hourly: { name: '每小时', desc: '每小时的第0分钟执行' },
      every2Hours: { name: '每2小时', desc: '每2小时执行一次' },
      daily: { name: '每天', desc: '每天0点执行' },
      daily9am: { name: '每天9点', desc: '每天上午9点执行' },
      weekly: { name: '每周', desc: '每周日0点执行' },
      monthly: { name: '每月', desc: '每月1日0点执行' },
      workday: { name: '工作日', desc: '周一到周五9点执行' },
      workdayAm: { name: '工作日上午', desc: '工作日9点和17点执行' },
      weekend: { name: '周末', desc: '周六和周日10点执行' }
    }
  },
  /** Monaco 代码编辑器（components/tasks/MonacoEditor.vue） */
  monaco: {
    fallbackTitle: '编辑器加载失败',
    fallbackDesc: '已切换到基础模式，您可以继续使用文本编辑器',
    retry: '重试加载',
    printQuoteHint: 'print语句可能缺少引号'
  },
  /** Python 类选择器（components/tasks/PythonClassSelector.vue） */
  pythonSelector: {
    tabs: {
      preset: '预定义类',
      manual: '手动输入'
    },
    presetTitle: '选择系统预定义的Python任务类',
    searchPlaceholder: '搜索类名或描述...',
    categoryFallback: '类',
    viewDetailTip: '查看类详情',
    selectTip: '选择此类',
    selectedTitle: '当前选择的类',
    classPathLabel: '类路径：',
    descLabel: '描述：',
    noDesc: '无描述',
    paramsLabel: '参数：',
    manual: {
      classPathLabel: '类路径',
      placeholder: '例如: app.tasks.custom.MyCustomTask',
      tooltip: '完整模块路径.类名',
      formatHint: '格式：模块路径.类名，例如：app.tasks.backup.BackupTask',
      templatesTitle: '常用路径模板',
      historyLabel: '历史记录',
      validationLabel: '验证状态',
      validTitle: '类路径有效',
      invalidTitle: '类路径有误',
      importable: '类存在且可导入',
      modulePath: '模块路径: ',
      classInfo: '类信息: ',
      waitingTitle: '等待验证',
      waitingDesc: '请点击验证按钮检查类路径',
      validateBtn: '验证类路径',
      clearBtn: '清空'
    },
    detail: {
      title: 'Python类详情',
      basic: '基本信息',
      path: '类路径',
      module: '模块',
      category: '类型',
      status: '状态',
      available: '可用',
      unavailable: '不可用',
      descTitle: '描述',
      noDesc: '暂无描述',
      paramsTitle: '参数配置',
      colName: '参数名',
      colType: '类型',
      colRequired: '必填',
      colDesc: '说明',
      colDefault: '默认值',
      requiredYes: '是',
      requiredNo: '否',
      defaultRequired: '必填',
      defaultOptional: '可选',
      methodsTitle: '可用方法',
      close: '关闭',
      select: '选择此类'
    },
    msg: {
      validateFailed: '验证失败，请检查网络连接',
      notAllowed: '类路径不在允许的模块范围内',
      notAllowedClassInfo: '模块不在允许范围内',
      formatOkWaiting: '类路径格式正确，等待运行时验证',
      needRuntimeCheck: '需要在运行时验证类的存在性',
      emptyPath: '类路径不能为空'
    },
    rules: {
      classPathRequired: '请输入类路径',
      classPathFormat: '类路径格式错误，应使用点号分隔的标识符，如：app.tasks.MyTask'
    },
    validation: {
      formatInvalid: '类路径格式错误，应使用点号分隔的标识符，如：app.tasks.MyTask',
      missingParts: '类路径应包含至少一个模块名和类名',
      classNameCase: '类名应以大写字母开头，后跟字母或数字',
      formatOk: '格式正确'
    }
  }
}
