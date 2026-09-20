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
 * 操作日志域文案（P6-4b：views/logs/audit.vue）。
 *
 * 边界：
 * - 操作类型按稳定 value（add/delete_l4/...）映射 operationType.*，
 *   未知值回退原文（Q02）；筛选下拉的删除四级带等级语义后缀（operationTypeFull）；
 * - 详情弹窗的 operation_detail/old_value/new_value/error_message 为历史审计
 *   原文数据（B03），不翻译；操作人与种子名称为用户内容原文展示；
 * - 后端 audit-logs 端点 msg 属原始数据原文透传（E03），错误展示走
 *   apiResponseMessage/apiErrorMessage（reasonCode 优先），不在本组做中文匹配；
 * - 「确定/取消」与 common.confirm（「确认」）措辞不同，保持原页面措辞零回归。
 */
export const auditLogs = {
  title: '操作日志',
  subtitle: '检索关键操作记录，核对执行结果并导出留档',
  detail: '详情',
  filter: {
    panelTitle: '筛选日志',
    panelDescription: '可组合名称、类型、操作人、结果与时间范围进行查询',
    countTag: '共 {count} 条',
    torrentName: '种子名称',
    torrentNamePlaceholder: '支持模糊搜索',
    operationType: '操作类型',
    allTypes: '全部类型',
    operator: '操作人',
    operatorPlaceholder: '全部操作人',
    result: '操作结果',
    allResults: '全部结果',
    all: '全部',
    timeRange: '操作时间',
    rangeSeparator: '至',
    startPlaceholder: '开始时间',
    endPlaceholder: '结束时间',
    search: '搜索',
    reset: '重置'
  },
  operationGroup: {
    seed: '种子管理',
    downloader: '下载器操作',
    task: '定时任务',
    keyword: '关键词规则'
  },
  /** 操作类型短标签（表格/详情）；value→键映射见组件内 OPERATION_TYPE_KEYS */
  operationType: {
    add: '新增种子',
    transfer: '种子转移',
    deleteL4: '等级4删除',
    deleteL3: '等级3删除',
    deleteL2: '等级2删除',
    deleteL1: '等级1删除',
    restore: '还原种子',
    downloaderAdd: '添加下载器',
    downloaderDelete: '删除下载器',
    downloaderUpdate: '修改下载器',
    downloaderTest: '测试下载器',
    scheduledTaskAdd: '添加定时任务',
    scheduledTaskDelete: '删除定时任务',
    scheduledTaskUpdate: '修改定时任务',
    scheduledTaskExecute: '执行定时任务',
    scheduledTaskInterrupt: '中断定时任务',
    keywordRuleAdd: '添加关键词规则',
    keywordRuleDelete: '删除关键词规则',
    keywordRuleUpdate: '修改关键词规则'
  },
  /** 筛选下拉中删除四级的完整标签（含等级语义后缀）；其余类型复用 operationType */
  operationTypeFull: {
    deleteL4: '等级4删除（待删除）',
    deleteL3: '等级3删除（回收站）',
    deleteL2: '等级2删除（保留数据）',
    deleteL1: '等级1删除（完全删除）'
  },
  result: {
    success: '成功',
    failed: '失败',
    partial: '部分成功'
  },
  actions: {
    title: '日志操作',
    description: '导出当前筛选结果，或归档历史数据',
    export: '导出',
    exportCsv: '导出为 CSV',
    exportExcel: '导出为 Excel',
    archive: '归档历史日志',
    refreshStats: '刷新统计'
  },
  stats: {
    total: '总日志数',
    success: '成功操作',
    failed: '失败操作',
    today: '今日操作'
  },
  col: {
    operationType: '操作类型',
    operator: '操作人',
    torrentName: '种子名称',
    downloaderName: '下载器名称',
    time: '操作时间',
    result: '结果',
    ip: 'IP地址',
    action: '操作'
  },
  empty: '暂无审计日志',
  detailDialog: {
    title: '审计日志详情',
    basicSection: '基本信息',
    debugSection: '调试信息',
    operationSection: '操作详情',
    oldSection: '修改前（旧值）',
    newSection: '修改后（新值）',
    errorSection: '错误信息',
    operationType: '操作类型：',
    operator: '操作人：',
    time: '操作时间：',
    result: '操作结果：',
    torrentName: '种子名称：',
    downloaderName: '下载器名称：',
    ip: 'IP地址：',
    requestId: '请求ID：',
    sessionId: '会话ID：',
    copyJson: '复制 JSON'
  },
  archiveDialog: {
    title: '归档审计日志',
    noticeTitle: '归档说明',
    noticeText: '归档功能会将指定时间之前的审计日志导出到独立的JSON文件，并从主数据库中删除这些日志。归档后的日志将无法在查询界面中显示，但可以通过归档文件查看。',
    endTime: '归档截止时间',
    endTimePlaceholder: '选择日期时间',
    endTimeHint: '此时间之前的审计日志将被归档',
    fileName: '归档文件名',
    fileNamePlaceholder: '留空则自动生成',
    fileNameHint: '仅接受文件名（自动追加 .json 后缀），固定保存到：data/audit_logs_archive/',
    confirm: '确认归档'
  },
  msg: {
    queryFailed: '查询失败',
    queryException: '查询审计日志失败',
    exporting: '正在导出为 {format}...',
    fileNameMissing: '导出文件名缺失',
    exportFailed: '导出失败',
    exportRetry: '导出失败，请稍后重试',
    archiveTimeRequired: '请选择归档截止时间',
    archiveConfirm: '归档操作不可恢复，确定要归档审计日志吗？',
    confirmTitle: '警告',
    ok: '确定',
    archiveSuccess: '归档成功，已归档 {count} 条日志',
    archiveFailed: '归档失败',
    archiveRetry: '归档失败，请稍后重试',
    statsRefreshed: '统计已刷新',
    jsonCopied: 'JSON 已复制到剪贴板',
    copyFailed: '复制失败，请手动选择内容复制'
  }
}
