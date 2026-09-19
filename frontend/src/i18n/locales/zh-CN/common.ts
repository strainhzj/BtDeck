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

/** 跨页面共享文案（common 组，P2 首次使用闭环；P3-1 增 multiSelect/pageSize 共享组件组）。 */
export const common = {
  adminName: '管理员',
  cancel: '取消',
  /** 名称列表拼接分隔符（删除失败/降级/文件缺失详情等） */
  listSeparator: '、',
  close: '关闭',
  confirm: '确认',
  refresh: '刷新',
  loadMore: '加载更多',
  copy: '复制',
  sessionExpired: '登录状态已过期，请重新登录',
  forceChangeHint: '请先修改密码：完成修改前仅可访问系统设置页',
  partialSuccess: '部分操作成功',
  serviceUnavailable: '服务暂时不可用，请稍后重试',
  capabilityUnknown: '无法确认当前服务端能力，已暂时禁用该功能，请检查连接后重试',
  capabilityBlocked: '当前 Android 主服务端无法访问下载器主机文件系统，该功能不可用',
  notFound: {
    title: '页面未找到',
    desc: '抱歉，您访问的页面不存在或已被删除。',
    hint: '请检查URL或返回首页继续浏览。',
    back: '返回上一页',
    home: '返回首页',
    helpTitle: '需要帮助？',
    contactSupport: '联系支持团队'
  },
  notifications: {
    title: '通知中心',
    closeLabel: '关闭通知中心',
    closeDetail: '关闭通知详情',
    empty: '暂无通知',
    markUnread: '标记未读',
    markRead: '标记已读',
    markAllRead: '全部已读',
    remove: '删除',
    failedDetail: '失败明细',
    viewRelease: '在 GitHub 上查看完整 Release',
    filterAll: '全部',
    filterUnread: '未读',
    filterUpdate: '更新',
    filterSystem: '系统',
    typeVersionUpdate: '版本更新',
    typeSystem: '系统通知',
    /** 事件本地化（双语 P4 / E03）：按 extra_data.event 映射，未登记事件原文展示 */
    events: {
      batchAdd: {
        title: '批量添加种子完成',
        content: '批量添加种子任务完成：共 {total} 个，成功 {success} 个，失败 {failed} 个。'
      },
      orphanScan: {
        title: '孤儿文件扫描完成',
        content: '本次扫描发现 {count} 个孤儿文件，共 {size}，请前往孤儿文件管理页面查看。',
        warning: '（注意：孤儿数量超过护栏阈值，可能是真实的大批量数据，也可能是路径映射失效导致的误判，请前往孤儿文件管理页面核查。）'
      },
      versionUpdate: {
        title: 'BtDeck {version} 版本更新'
      },
      welcome: {
        title: '欢迎使用 BtDeck',
        content: '感谢您使用 BtDeck！这是您的第一条系统通知。通知中心会在这里显示版本更新和系统消息。'
      }
    }
  },
  /** AdvancedMultiSelect 共享多选下拉（列表筛选/高级搜索/移动端同源消费） */
  multiSelect: {
    searchPlaceholder: '搜索选项...',
    createOption: '创建 "{keyword}"',
    include: '包含',
    exclude: '排除',
    selectedLabel: '项已选',
    clear: '清空',
    removeItem: '移除 {label}',
    emptyHint: '从下方选项中选择，或直接搜索创建',
    noMatch: '无匹配选项',
    selectVisible: '选择当前可见项',
    deselectVisible: '取消当前可见项',
    selectAll: '选择全部选项',
    clearAll: '清空所有选择',
    pasteTitle: '批量粘贴',
    parsedCount: '解析 {count} 项',
    apply: '应用',
    virtualScroll: '启用虚拟滚动',
    showCount: '显示选项数量',
    customSeparators: '自定义分隔符',
    useSeparators: '使用{separators}分隔多个值',
    separatorJoin: '、',
    spaceSeparator: '空格',
    multiSelected: '{first} 等 {count} 项',
    ariaSelect: '选择多个条件值',
    ariaClear: '清空已选条件值'
  },
  /** PageSizeCombobox 分页大小选择器 */
  pageSize: {
    ariaLabel: '每页数量',
    inputHint: '选择预设值或输入 1 至 100000，按 Enter 或失焦生效',
    expand: '展开分页大小选项',
    collapse: '收起分页大小选项',
    options: '分页大小预设'
  }
}
