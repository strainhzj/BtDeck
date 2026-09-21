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
 * Tracker 域文案（tracker 组，P3-2：详情卡片三页签 + Tracker 操作弹窗 + 列表异常标签；
 * P6-3：关键词看板/搜索、汇报配置、判断测试工具 + 9 组件 + utils 共享工具）。
 *
 * 边界：
 * - 后端返回的 announce/scrape 原始诊断文本（如「工作失败/未联系」）属用户可见原始
 *   数据，保留原文不译（T03：原始详情保留）；
 * - TRACKER_SUCCESS_VALUES / TRACKER_FAIL_VALUES 的中文值集合是数据语义匹配，
 *   不是文案，禁止翻译；
 * - 汇报按钮文案在本组；列表页汇报操作的 toast 反馈在 torrent 组（P3-1 已落）。
 */
export const tracker = {
  detail: {
    collapse: '收起详情',
    title: 'Tracker详情 - {name}',
    errorTitle: '种子错误原因',
    table: {
      name: 'Tracker名称',
      announce: 'Announce信息',
      actions: '操作'
    },
    status: {
      working: '✓ 工作',
      failedPrefix: '✗ {reason}',
      failedFallback: '失败'
    },
    matched: '命中筛选',
    matchedTitle: '命中当前 Tracker 域名筛选：{domain}',
    unknownTracker: '未知',
    reannounce: '汇报',
    files: {
      tab: '文件',
      loading: '文件列表加载中...',
      loadFailed: '文件列表加载失败',
      empty: '暂无文件数据',
      searchPlaceholder: '搜索文件名',
      stale: '更新失败，显示上次数据',
      noMatch: '未找到匹配 "{keyword}" 的文件',
      colName: '文件名',
      colSize: '大小',
      colProgress: '进度',
      countTotal: '共 {total} 个文件',
      countMatched: '命中 {matched} / {total} 个文件',
      countTruncatedPrefixMatched: '命中 {total} 个文件',
      truncateSuffix: '，仅显示前 {max} 个'
    },
    peers: {
      loading: 'Peers 列表加载中...',
      loadFailed: 'Peers 列表加载失败',
      empty: '暂无 Peers 数据',
      countWithRefresh: '共 {total} 个 Peers（每 5 秒自动刷新）',
      countTotal: '共 {total} 个 Peers',
      colAddress: '地址',
      colClient: '客户端',
      colProgress: '进度',
      colDownSpeed: '↓速度',
      colUpSpeed: '↑速度'
    }
  },
  operation: {
    addTab: '添加Tracker',
    modifyTab: '修改Tracker',
    scopeLabel: '操作范围',
    selectedTorrents: '选中的种子',
    trackerUrls: 'Tracker地址',
    addPlaceholder: '多个tracker地址用分号;分隔\n例如:\nhttps://tracker1.com/announce\nhttps://tracker2.com/announce',
    addHint: '支持添加多个tracker地址，每个地址一行或用分号分隔',
    currentList: '当前Tracker列表',
    status: '状态',
    normal: '正常',
    abnormal: '异常',
    newList: '新Tracker列表',
    modifyPlaceholder:
      '多个tracker地址用分号;分隔，将完全替换当前的tracker列表\n例如:\nhttps://tracker1.com/announce;https://tracker2.com/announce',
    noticeLabel: '注意：',
    noticeReplace: '修改操作将完全替换当前tracker列表，请谨慎操作',
    rules: {
      requiredUrl: '请输入tracker地址',
      requiredNewList: '请输入新的tracker列表'
    },
    validate: {
      invalidUrl: '请输入有效的tracker地址',
      badUrls: '以下tracker地址格式不正确: {urls}'
    },
    scopeAllTorrents: '下载器「{name}」全部种子',
    scopeTotalSuffix: '（共 {total} 个）',
    addSubmitScoped: '添加到该下载器全部种子',
    addSubmitBatch: '批量添加 ({count}个种子)',
    addSubmitSingle: '添加Tracker',
    modifySubmitScoped: '替换该下载器全部种子Tracker',
    modifySubmitBatch: '批量修改 ({count}个种子)',
    modifySubmitSingle: '修改Tracker',
    titleScoped: 'Tracker操作（按下载器） - {name}',
    titleBatch: '批量Tracker操作 - 已选{count}个种子',
    titleSingle: 'Tracker操作 - {name}',
    torrentFallbackName: '种子',
    resultSuffix: '（成功 {ok}）',
    resultSuffixWithFail: '（成功 {ok}，失败 {fail}）',
    formNotReady: '表单未初始化，请稍后重试',
    addSuccess: '添加Tracker成功',
    addFailed: '添加Tracker失败',
    modifySuccess: '修改Tracker成功',
    modifyFailed: '修改Tracker失败',
    noTorrentId: '未获取到种子ID，请重新选择种子'
  },
  /** 全局替换 Tracker 弹窗（P6-1；R06 相邻的危险操作语义：不可撤销明示） */
  replace: {
    title: '全局替换Tracker',
    helpTitle: '操作说明',
    warning: '此功能将全局替换所有种子中匹配的tracker地址，操作不可撤销！',
    warningHint: '请确保您输入的tracker地址正确无误。',
    oldLabel: '被替换的Tracker',
    oldPlaceholder: '输入要被替换的tracker地址，例如: https://tracker.old.com/announce',
    oldHint: '将被完全匹配替换的tracker地址',
    newLabel: '新Tracker地址',
    newPlaceholder: '输入新的tracker地址，例如: https://tracker.new.com/announce',
    newHint: '将用于替换的新tracker地址',
    submit: '执行替换',
    exampleTitle: '操作示例',
    exampleStep1: '输入旧tracker',
    exampleStep2: '输入新tracker',
    exampleStep3: '全局替换',
    exampleStep3Desc: '所有种子自动更新',
    validate: {
      oldRequired: '请输入被替换的tracker地址',
      newRequired: '请输入新的tracker地址',
      invalidUrl: '请输入有效的tracker地址格式'
    }
  },
  errorReason: {
    withMessage: 'Tracker 宣告失败：{message}',
    fallback: 'Tracker 宣告失败，详见 Tracker 标签页'
  },
  /**
   * P6-3 Tracker 管理域（关键词看板/搜索、汇报配置、判断测试工具 + 9 组件）。
   *
   * 边界：
   * - 后端关键词/汇报/测试域端点的中文 msg 属原始数据原文透传（E03），不在本组；
   * - pools.candidate 等为「池子名称」；keywordCard.typeSuccess 等为关键词类型标签，
   *   两组词不同（候选池 vs 候选），禁止互相复用；
   * - pools.dialog.confirm/cancel 为 $confirm 按钮文案，与 common.confirm（「确认」）措辞不同，
   *   保持原页面措辞零回归。
   */
  pools: {
    candidate: '候选池',
    ignored: '忽略池',
    success: '成功池',
    failed: '失败池',
    poolFallback: '池子',
    unknownTime: '未知时间',
    viewAll: '查看全部 →',
    moveTo: '移动到',
    moveToPool: '移动到池子',
    moveToOtherPool: '移动到其它池',
    batchMoveTo: '批量移动到',
    quickActionTip: '快捷操作（按前缀左匹配）',
    addKeyword: '添加关键词',
    importKeywords: '导入关键词',
    exportKeywords: '导出关键词',
    dialog: {
      confirm: '确定',
      cancel: '取消',
      notice: '提示',
      confirmDelete: '确认删除',
      close: '关 闭'
    }
  },
  board: {
    title: 'Tracker关键词管理',
    search: '搜索',
    refresh: '刷新',
    loadAllFailed: '加载池数据失败',
    loadFailed: '加载失败',
    loadPoolFailed: '加载{pool}数据失败',
    moveSuccess: '关键词 "{keyword}" 已移动到 {pool}',
    moveFailed: '移动失败',
    deleteConfirm: '确定要删除关键词 "{keyword}" 吗？',
    deleteSuccess: '删除成功',
    deleteFailed: '删除失败',
    candidateAddDenied: '候选池不支持手动添加关键词,请将关键词拖拽到其他池子',
    candidateImportDenied: '候选池不支持导入关键词,请将关键词拖拽到其他池子',
    exportWip: '导出功能开发中 - {pool}'
  },
  search: {
    backToBoard: '返回看板',
    title: '搜索关键词',
    foundPrefix: '共找到 ',
    foundSuffix: ' 个关键词',
    inputPlaceholder: '输入关键词搜索...',
    searchButton: '搜索',
    poolPlaceholder: '选择池子',
    timeRange: '时间范围',
    all: '全部',
    today: '今天',
    week: '本周',
    month: '本月',
    sortPlaceholder: '排序方式',
    sortTimeDesc: '添加时间 ↓',
    sortTimeAsc: '添加时间 ↑',
    sortNameAsc: '关键词 A-Z',
    colIndex: '序号',
    colKeyword: '关键词',
    colPool: '所在池子',
    colTime: '添加时间',
    colActions: '操作',
    viewDetail: '查看详情',
    delete: '删除',
    empty: '暂无搜索结果，请尝试调整搜索条件或关键词',
    searchFailed: '搜索失败',
    moveSuccess: '关键词已移动到 {pool}',
    moveFailed: '移动失败',
    deleteConfirm: '确定要删除关键词 "{keyword}" 吗？',
    deleteSuccess: '删除成功',
    deleteFailed: '删除失败'
  },
  reannounce: {
    title: 'Tracker汇报配置',
    description: '配置站点的Tracker汇报间隔，支持域名通配符匹配',
    searchDomain: '搜索域名名称...',
    enabledStatus: '启用状态',
    enabled: '已启用',
    disabled: '已禁用',
    search: '搜索',
    reset: '重置',
    getListFailed: '获取配置列表失败',
    createConfig: '新增配置',
    autoDetect: '自动检测域名',
    batchSetup: '批量设置',
    batchModeInfo: '批量编辑模式 - 已选择 {count} 条记录',
    exitBatch: '退出批量编辑',
    modifiedCount: '已修改 {count} 条记录',
    undoChanges: '撤销更改',
    saveChanges: '保存更改',
    loadingText: '加载中...',
    colDisplayName: '域名显示名称',
    colPattern: '域名模式',
    colInterval: '间隔分钟',
    colEnabled: '启用开关',
    colActions: '操作',
    displayNamePlaceholder: '域名显示名称',
    patternPlaceholder: '%.tracker.com',
    minutesPlaceholder: '分钟',
    edited: '已编辑',
    notEdited: '未编辑',
    edit: '编辑',
    delete: '删除',
    createTitle: '新增配置',
    editTitle: '编辑配置',
    formPattern: '域名模式',
    formDisplayName: '域名显示名称',
    formInterval: '汇报间隔（分钟）',
    formEnabled: '启用配置',
    patternRequired: '请输入域名模式',
    intervalRequired: '请输入汇报间隔',
    intervalRange: '汇报间隔必须在 1-1440 分钟之间',
    patternHint: '💡 支持使用 % 作为通配符匹配多个子域名',
    displayNameDialogPlaceholder: 'Tracker站点',
    enabledHint: '开启后将按设定间隔自动汇报Tracker',
    updateSuccess: '配置更新成功',
    updateFailed: '配置更新失败',
    createSuccess: '配置创建成功',
    createFailed: '配置创建失败',
    toggleEnabled: '配置已启用',
    toggleDisabled: '配置已禁用',
    toggleFailed: '配置状态更新失败',
    deleteConfirm: '确定要删除配置「{name}」吗？',
    deleteSuccess: '配置删除成功',
    deleteFailed: '配置删除失败',
    detectResult: '检测到 {detected} 个域名，新增 {created} 个配置',
    detectFailed: '自动检测失败',
    exitBatchConfirm: '退出批量编辑将丢失未保存的更改，确定要退出吗？',
    undoConfirm: '确定要撤销所有更改吗？',
    nothingToSave: '没有需要保存的更改',
    batchPartial: '批量更新完成，成功 {success} 条，失败 {failed} 条',
    batchSuccess: '批量更新成功，已保存 {count} 条记录',
    batchFailed: '批量更新失败'
  },
  testTool: {
    title: 'Tracker判断测试工具',
    description: '测试tracker消息的匹配结果，帮助理解判断逻辑',
    inputCardTitle: '输入测试消息',
    trackerAddr: 'Tracker地址',
    trackerAddrPlaceholder: '例如: http://tracker.example.com:8080',
    msgLabel: '返回消息',
    msgPlaceholder: '请输入tracker返回的消息内容...',
    testButton: '测试匹配',
    clearButton: '清空',
    resultCardTitle: '匹配结果',
    detailTitle: '匹配详情：',
    unmatchedTitle: '未匹配到关键词',
    unmatchedFallback: '该消息不包含任何成功或失败关键词',
    addToFailedPool: '添加到失败关键词池',
    addToSuccessPool: '添加到成功关键词池',
    copyResult: '复制结果',
    historyCardTitle: '测试历史',
    historySearch: '搜索历史记录...',
    clearHistory: '清空历史',
    colTracker: 'Tracker地址',
    colMsg: '消息内容',
    colResult: '结果',
    colTime: '测试时间',
    colActions: '操作',
    resultSuccess: '成功',
    resultFailed: '失败',
    retest: '重新测试',
    totalRecords: '共 {count} 条记录',
    timeline: {
      step1Title: '接收消息',
      step1Desc: '消息长度: <span class="highlight">{length} bytes</span>',
      step2Title: '关键词匹配',
      step2Desc: '匹配到 <span class="highlight">{count} 个</span>{type}关键词',
      step3Title: '判定结果',
      step3Desc: '最终判定: <span class="highlight">{result}</span>'
    },
    requireTracker: '请输入tracker地址',
    requireMsg: '请输入消息内容',
    testDone: '测试完成',
    testFailed: '测试失败',
    clearHistoryConfirm: '确定要清空测试历史吗?',
    clearedHistory: '已清空历史记录',
    promptDesc: '请输入关键词说明（可选）',
    promptFailedTitle: '添加到失败关键词池',
    promptSuccessTitle: '添加到成功关键词池',
    promptPlaceholderFailed: '例如: 超时错误',
    promptPlaceholderSuccess: '例如: 下载成功',
    addSuccess: '添加成功',
    addFailed: '添加失败',
    copyResultLine: '判断结果: {result}',
    copyKeywordsLine: '匹配关键词: {keywords}',
    copyReasonLine: '未匹配原因: {reason}',
    none: '无',
    copied: '已复制到剪贴板',
    copyFailed: '复制失败'
  },
  addDialog: {
    title: '添加关键词到 {pool}',
    contentLabel: '关键词内容 *',
    placeholder: '请输入关键词',
    adding: '添加中...',
    confirmAdd: '确定添加',
    required: '关键词不能为空',
    tooLong: '关键词长度不能超过100个字符',
    addSuccess: '已添加关键词 "{keyword}" 到 {pool}',
    addFailed: '添加关键词失败',
    addFailedRetry: '添加关键词失败,请稍后重试'
  },
  importDialog: {
    title: '导入关键词到 {pool}',
    uploadText: '点击或拖拽TXT文件到此处',
    uploadHint: '仅支持.txt文件,每行一个关键词',
    manualLabel: '或手动输入关键词',
    textareaPlaceholder: '每行一个关键词,按回车分隔',
    previewPrefix: '将导入 ',
    previewSuffix: ' 个关键词',
    importing: '导入中...',
    cancel: '取消',
    startImport: '开始导入',
    cancelImport: '取消导入',
    onlyTxt: '仅支持.txt文件',
    readSuccess: '已读取 {count} 个关键词',
    readFailed: '文件读取失败',
    requireKeywords: '请先输入或上传关键词',
    cancelled: '导入已取消',
    cancelledWithStats: '导入已取消,成功 {success} 个,失败 {fail} 个',
    progress: '正在导入 {percent}% ({done}/{total})',
    done: '导入完成',
    successBox: '成功导入 {success} 个关键词,失败 {fail} 个',
    toastSuccess: '成功导入 {success} 个关键词',
    toastFailSuffix: ',失败 {fail} 个',
    allFailed: '导入失败,请稍后重试',
    processError: '导入过程出错,请稍后重试',
    cancelling: '正在取消导入...',
    addFailedFallback: '添加失败'
  },
  listModal: {
    searchPlaceholder: '搜索关键词...',
    titleSuffix: '{pool}详情',
    selectedPrefix: '已选 ',
    selectedSuffix: ' 项',
    batchDelete: '批量删除',
    empty: '暂无数据',
    loadFailed: '加载数据失败',
    moveSuccess: '关键词已移动到 {pool}',
    moveFailed: '移动失败',
    deleteConfirm: '确定要删除关键词 "{keyword}" 吗？',
    deleteSuccess: '删除成功',
    deleteFailed: '删除失败',
    batchMoveSuccess: '已将 {count} 个关键词移动到 {pool}',
    batchMoveFailed: '批量移动失败',
    batchDeleteConfirm: '确定要删除选中的 {count} 个关键词吗？',
    batchDeleteSuccess: '已删除 {count} 个关键词',
    batchDeleteFailed: '批量删除失败'
  },
  quickAction: {
    deleteMode: '删除',
    moveMode: '移动到其它池',
    alertTitle: '按关键词文本前缀左匹配本池关键词',
    alertBody: '输入前缀，将匹配所有<strong>{pool}</strong>中<strong>关键词文本</strong>以此开头的词（排除已删除）。',
    deleteHint: '删除后关键词进入逻辑删除状态。',
    moveHint: '移动后关键词进入目标池，并按前缀批量迁移。',
    prefixLabel: '关键词前缀',
    prefixPlaceholder: '例如：success- 或 50%',
    targetLabel: '移动到池子',
    deleteTitle: '快捷删除',
    moveTitle: '快捷移动',
    titleSuffix: '（按前缀）',
    requirePrefix: '请输入关键词前缀',
    emptyPool: '该池没有关键词',
    sameTarget: '不能移动到原池子',
    previewFailed: '预览失败',
    noMatch: '没有匹配的关键词',
    sampleLine: '\n匹配样本：{sample}{more}',
    sampleMore: ' …',
    confirmDeleteText: '将删除 {count} 个匹配的关键词。{sample}\n\n确认删除？',
    confirmMoveText: '将移动 {count} 个关键词到{pool}。{sample}\n\n确认移动？',
    deleted: '已删除 {count} 个关键词',
    moved: '已移动 {count} 个关键词到{pool}'
  },
  keywordCard: {
    priority: '优先级',
    language: '语言',
    description: '说明',
    typeSuccess: '成功',
    typeFailed: '失败',
    typeCandidate: '候选',
    typeIgnored: '忽略'
  },
  timeline: {
    title: '匹配过程时间线'
  },
  resultSummary: {
    resultLabel: '判断结果: {result}',
    success: '成功',
    failed: '失败',
    successDesc: '该消息判定为成功状态',
    failedDesc: '该消息判定为失败状态（失败优先）'
  },
  apiLog: {
    title: 'API日志',
    collapse: '收起',
    expand: '展开'
  },
  /** 语言显示名（getLanguageLabel；未登记语言码原文回退 Q02） */
  lang: {
    zh_CN: '中文',
    en_US: '英文',
    ru_RU: '俄语',
    ja_JP: '日语',
    generic: '通用'
  },
  /** utils/tracker.ts extractErrorMessage 共享兜底 */
  errors: {
    operationFailed: '操作失败',
    validationFailed: '参数验证失败: {message}'
  }
}
