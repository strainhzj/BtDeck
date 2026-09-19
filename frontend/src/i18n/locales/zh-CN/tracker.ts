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
 * Tracker 域文案（tracker 组，P3-2：详情卡片三页签 + Tracker 操作弹窗 + 列表异常标签）。
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
  errorReason: {
    withMessage: 'Tracker 宣告失败：{message}',
    fallback: 'Tracker 宣告失败，详见 Tracker 标签页'
  }
}
