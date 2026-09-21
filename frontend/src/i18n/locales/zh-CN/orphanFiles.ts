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
 * 孤儿文件域文案（P6-4b：views/orphan-files/index.vue）。
 *
 * 边界：
 * - 状态/置信度按稳定码位（pending/ignored/deleted、high/low）映射 status.*，
 *   与筛选选项同源；未知值回退原文（Q02）；
 * - 后端扫描上下文 cleanup_block_reason / error_message / failed_list[].reason
 *   属服务层数据（B03 原文透传）：包装文案走键，数据值以 {reason} 槽位或
 *   console 承接（E01：诊断明细不进用户提示，见回收站 P5 先例）；
 * - 后端 orphan-files 端点 msg 属原始数据原文透传（E03），错误展示走
 *   apiResponseMessage/apiErrorMessage（reasonCode 优先），禁止中文 msg 匹配；
 * - 危险链路（彻底删除/快捷删除/删除副本/清理确认）保持三要素语义：
 *   对象 + 数量/大小 + 不可恢复性；
 * - 「确定/取消/提示」与 common.confirm（「确认」）措辞不同，保持原页面措辞零回归。
 */
export const orphanFiles = {
  title: '孤儿文件',
  subtitle: '扫描未被种子引用的文件，并在清理前进行安全复核',
  scanNow: '立即扫描',
  tabs: {
    orphans: '孤儿文件',
    quarantine: '隔离区'
  },
  stats: {
    title: '扫描统计',
    summaryAria: '最近一次孤儿文件扫描摘要',
    pendingCount: '待清理文件数',
    pendingSize: '待清理空间',
    ignoredCount: '已忽视文件数',
    pathCount: '扫描路径数',
    lastScan: '最近成功扫描',
    noScan: '尚无成功扫描'
  },
  scanState: {
    failedTitle: '最近一次扫描失败',
    queuedTitle: '孤儿文件扫描等待执行',
    runningTitle: '孤儿文件扫描进行中',
    largeTitle: '超量扫描提醒',
    largeText: '本次扫描发现的孤儿文件数量较多，请留意下载器路径映射和孤儿判定；此提醒不影响清理。',
    queuedDesc: '扫描任务已进入后台队列；页面仅轮询轻量状态，列表与清理暂不可用。',
    runningDesc: '扫描正在进行中，完成前列表与统计保持为空，清理功能暂不可用。',
    failedWithDisplay: '失败原因：{reason}。当前只读展示最近一次成功扫描的剩余结果，重新扫描成功前不可清理。',
    failedNoDisplay: '失败原因：{reason}。当前尚无可展示的成功扫描结果。',
    unknownError: '未知错误'
  },
  filter: {
    aria: '孤儿文件筛选条件',
    pathLike: '文件路径',
    pathPlaceholder: '路径关键字模糊匹配',
    downloader: '下载器',
    status: '状态',
    statusDegradedTip: '同时选“待清理”与“已忽视/已清理”会扩大为全部未删除文件',
    warnAria: '筛选组合提示',
    confidence: '置信度',
    located: '副本筛选',
    locatedTip: '按扫描时统计的硬链接副本数过滤；副本位置详情由弹窗实时复核',
    hasCopies: '有硬链接副本',
    search: '搜索',
    reset: '重置'
  },
  confidence: {
    high: '高置信度',
    low: '低置信度'
  },
  /** 状态标签与筛选选项同源（值为后端稳定码位）；mixed 仅用于聚合展示 */
  status: {
    pending: '待清理',
    ignored: '已忽视',
    deleted: '已清理',
    mixed: '混合'
  },
  confidenceTag: {
    high: '高',
    low: '低',
    mixed: '混合',
    folderLowTip: '文件夹内含离线降级目录粗筛判定的低置信度项，有误判风险',
    folderHighTip: '文件夹内全部为在线精筛判定，确认未被任何种子引用',
    lowTip: '离线降级目录粗筛判定，有误判风险；手动清理可删，自动清理需等下载器上线精筛',
    highTip: '在线精筛判定，确认未被任何种子引用'
  },
  list: {
    title: '文件列表',
    description: '展示成功扫描 {time} 的剩余结果',
    descriptionEmpty: '完成首次成功扫描后将在此显示结果',
    selected: '已选择 {count} 项',
    cleanupSelected: '清理选中',
    ignoreSelected: '忽视选中',
    unignoreSelected: '取消忽视',
    folderView: '按文件夹展示',
    folderViewTip: '开启后同目录下多个文件折叠为文件夹一行（仅影响展示，删除仍按文件）',
    quickAction: '快捷操作',
    quickCleanup: '快捷删除（按前缀）',
    quickIgnore: '快捷忽视（按前缀）',
    quickIgnoreTitle: '按路径前缀批量忽视待清理文件',
    clearLocated: '取消有副本筛选',
    filterLocated: '筛选有副本文件',
    locatedOn: '仅显示有硬链接副本的文件（扫描时统计）',
    locatedOff: '取消副本筛选，恢复完整列表',
    empty: '暂无孤儿文件，点击“立即扫描”开始检测',
    col: {
      path: '文件路径',
      size: '大小',
      copies: '副本数量',
      mtime: '修改时间',
      downloader: '下载器',
      confidence: '置信度',
      status: '状态',
      action: '操作'
    },
    filesCount: '{count} 个文件',
    multipleDownloaders: '多个',
    ignore: '忽视',
    unignore: '取消忽视',
    paginationAria: '孤儿文件分页',
    selectAllAria: '选择当前页的全部孤儿文件',
    totalPrefix: '共 ',
    totalSuffix: ' 条'
  },
  quarantine: {
    title: '隔离区文件',
    subtitle: '已清理文件暂存于此（保留期 {days} 天），可恢复到原位置或立即彻底删除',
    selected: '已选择 {count} 项',
    restore: '恢复选中',
    purge: '彻底删除选中',
    col: {
      path: '原位置（规范化路径）',
      size: '大小',
      quarantinedAt: '隔离时间',
      purgeAfter: '预计删除',
      delayCount: '延后次数',
      downloader: '下载器'
    },
    total: '共 {count} 条',
    paginationAria: '隔离区分页'
  },
  hardlink: {
    title: '硬链接副本位置',
    titleWithCount: '硬链接副本位置（{count} 个文件）',
    notice: '副本位置由每日定时任务在后台整体查找并存储，此处直接显示最近一轮结果。',
    realtime: '实时副本',
    located: '已定位',
    pending: '待预扫描',
    unlocatedTitle: '还有 {count} 个副本未在最近一轮预扫描中定位',
    unlocatedDesc: '这些副本可能位于无权限或未挂载目录，也可能尚未被预扫描覆盖；副本总数为实时统计。',
    unknownTitle: '{count} 个源文件当前不可访问，无法核对位置',
    invalidTitle: '{count} 个列表项已失效，请刷新页面后重试',
    copyTag: '副本 {count}',
    pendingTag: '待预扫描',
    locatedTag: '已定位 {count}',
    scannedAt: '扫描于 {time}',
    inaccessible: '源文件不可访问，无法重新核对副本位置',
    copyPath: '复制路径',
    remove: '删除',
    truncated: '路径数超过存储上限，仅显示前 {count} 条。',
    emptyPending: '等待每日定时任务预扫描定位副本路径，可稍后重新打开查看。',
    emptyUnlocated: '最近一轮预扫描未定位到副本路径。',
    emptyNone: '该文件当前已无其它硬链接副本。',
    unlocatedCount: '该文件还有 {count} 个副本位置未定位。',
    countFolderTitle: '展开后仅统计当前可见文件的副本数量快照',
    countUnknownTitle: '副本数量尚未生成快照（等待扫描）',
    countZeroTitle: '暂无其它硬链接副本（点击可实时复核）',
    countNTitle: '点击查看 {count} 个硬链接副本的位置',
    deleteConfirm: '确认删除硬链接副本？\n{path}\n此操作不可恢复：仅移除该路径链接，数据仍由源文件保留；位于种子目录内的副本会被拒绝删除。',
    deleteTitle: '删除副本确认',
    confirmDelete: '确认删除',
    rejected: '删除被拒绝',
    deleted: '已删除副本：{path}'
  },
  cleanup: {
    title: '清理确认',
    confirmTitle: '确认清理以下孤儿文件？此操作不可恢复！',
    fileCount: '文件数量: ',
    totalSize: '总大小: ',
    lowTitle: '其中 {count} 个为低置信度（离线降级目录粗筛判定）',
    lowText: '低置信度文件有误判风险（可能并非真正的孤儿）。确认清理前请核对路径，避免误删用户数据。',
    confirm: '确认清理'
  },
  quickAction: {
    cleanupTitle: '快捷删除（按前缀）',
    ignoreTitle: '快捷忽视（按前缀）',
    noticeTitle: '按路径前缀左匹配待清理文件',
    noticeLead: '输入路径前缀（绝对路径开头），将匹配所有',
    noticeFileStrong: '文件路径',
    noticeMid: ' 以此开头的',
    noticePendingStrong: '待清理',
    noticeTail: '文件（排除已忽视/已清理）。',
    cleanupNote: '删除即移入隔离区，可恢复。',
    prefixLabel: '路径前缀',
    prefixPlaceholder: '例如：D:\\downloads\\待清理目录\\ 或 /data/leak/',
    ok: '确定'
  },
  /** 批量按钮 title（禁用原因提示） */
  batchTitle: {
    cleanupSelectFirst: '请先选择待清理文件',
    cleanupMixed: '请勿混选不同状态，仅支持清理"待清理"项',
    ignoreSelectFirst: '请先选择待清理文件',
    ignoreMixed: '请勿混选不同状态，仅支持忽视"待清理"项',
    unignoreSelectFirst: '请先选择已忽视文件',
    unignoreMixed: '请勿混选不同状态，仅支持取消"已忽视"项'
  },
  msg: {
    tipTitle: '提示',
    actionIgnore: '忽视',
    actionUnignore: '取消忽视',
    skippedCount: '，跳过处理中 {count} 个',
    networkFallback: '网络错误',
    loadQuarantineFailed: '加载隔离区列表失败：',
    restoreConfirm: '确认恢复选中的文件到原位置？',
    restoreTitle: '恢复确认',
    restoreRejected: '恢复被拒绝',
    restoreDone: '恢复完成：成功 {count} 个',
    restoreFailedSuffix: '，失败 {count} 个',
    restoreFailed: '恢复失败：',
    purgeConfirm: '确认彻底删除选中的文件？此操作不可恢复，文件将被永久删除！',
    purgeTitle: '彻底删除确认',
    purgeSubmitted: '彻底删除任务已提交（{taskId}）{skipped}，完成或失败后将在通知中心提醒',
    purgeAllProcessing: '所选隔离文件均已在彻底删除任务中处理',
    purgeFailed: '删除失败：',
    folderChildrenFailed: '加载文件夹子项失败',
    folderChildrenFailedWith: '加载文件夹子项失败：',
    hardlinkQueryFailed: '查询硬链接副本位置失败',
    hardlinkQueryFailedWith: '查询硬链接副本位置失败：',
    hardlinkRefreshFailed: '刷新副本位置失败，当前展示为删除前结果：',
    hardlinkDeleteFailed: '删除硬链接副本失败',
    hardlinkDeleteFailedWith: '删除硬链接副本失败：',
    hardlinkDeletePartial: '部分副本删除失败，明细详见控制台日志',
    pathCopied: '路径已复制',
    copyPathFailed: '复制失败：',
    clipboardUnsupported: '当前浏览器不支持剪贴板',
    blockReasonDefault: '当前扫描快照不允许清理',
    blockReasonInitial: '尚无可清理的成功扫描',
    pageSizeAdjusted: '单次最多加载 {count} 条，已自动调整',
    listFailed: '获取列表失败',
    listFailedWith: '获取孤儿文件列表失败：',
    scanConfirm: '确认立即扫描孤儿文件？扫描可能需要较长时间。',
    scanSubmitted: '扫描任务已提交到后台',
    scanExisting: '已有扫描任务，继续跟踪其状态',
    scanFailed: '扫描失败',
    scanFailedWith: '扫描失败：',
    scanDone: '扫描完成：孤儿 {total}，新增明细 {added}，复用 {known}',
    scanFailedRecord: '扫描失败：{reason}',
    cleanupSelectFirst: '请先选择要清理的文件',
    cleanupEmptySelection: '所选文件均无可清理项：可能是低置信度（需等下载器上线精筛）、已忽视（需先取消忽视）或已清理。',
    previewRejected: '当前扫描快照不允许清理，请刷新后重试',
    previewFailed: '预览失败',
    previewFailedWith: '预览失败：',
    scanStale: '扫描批次已失效，请刷新后重试',
    cleanupSubmitted: '主动清理任务已提交（{taskId}）{skipped}，完成或失败后将在通知中心提醒',
    cleanupAllProcessing: '所选孤儿文件均已在主动清理任务中处理',
    cleanupFailed: '清理失败',
    cleanupFailedWith: '清理失败：',
    cleanupSubmitFailed: '清理任务提交失败',
    ignoreSelectPending: '请选择待清理的文件',
    ignoreSelectIgnored: '请选择已忽视的文件',
    ignoreConfirm: '确认{action}选中的 {count} 个孤儿文件？',
    ignoreFailedCount: '{action}失败：{count} 个文件未处理',
    ignorePartial: '{action}部分完成：成功 {success} 个，失败 {failed} 个',
    ignoreDone: '{action}完成：成功 {count} 个',
    ignoreFailed: '{action}失败',
    prefixRequired: '请输入路径前缀',
    noScanBatch: '当前无可用的成功扫描批次，无法按前缀操作',
    snapshotNotAllowed: '当前扫描快照不允许操作',
    prefixPreviewFailed: '前缀匹配预览失败',
    prefixPreviewFailedWith: '前缀匹配预览失败：',
    noMatch: '没有匹配的待清理文件',
    affectCount: '将影响 {count} 个待清理文件',
    sizeSuffix: '（共 {size}）',
    lowWarn: '⚠️ 其中 {count} 个为低置信度，有误判风险，请核对路径',
    moveToQuarantine: '\n\n确认将它们移入隔离区（可恢复）？',
    setIgnored: '\n\n确认将它们设为忽视（受保护，不再被自动/手动清理）？',
    matchAllProcessing: '匹配文件均已在主动清理任务中处理'
  }
}
