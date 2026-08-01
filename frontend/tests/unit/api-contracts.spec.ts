import request from '@/utils/request'
import {
  deleteBatchAsync,
  deleteTorrents,
  getActiveTorrents,
  getBatchDeleteStatus,
  getTorrentList,
  pauseTorrents,
  resumeTorrents
} from '@/api/torrents'
import {
  cleanupOrphans,
  cleanupPreview as previewOrphanCleanup,
  getLatestScan,
  getOrphanList,
  triggerScan
} from '@/api/orphan-files'
import {
  deleteNotification,
  getNotificationList,
  getUnreadCount,
  markAllAsRead,
  markAsRead,
  markAsUnread
} from '@/api/notification'
import { changePassword, getUserInfo, login, logout } from '@/api/users'
import { getDashboardData } from '@/api/dashboard'
import {
  archiveAuditLogs,
  downloadExportFile,
  exportAuditLogs,
  getAuditLogStatistics,
  getOperationTypes,
  queryAuditLogs
} from '@/api/audit-logs'
import {
  batchDeleteTags,
  checkCategorySupport,
  createTag,
  deleteTag,
  getAllCategories,
  getAllTags,
  getAllTagsDetailed,
  getTagList,
  updateTag
} from '@/api/tag-management'
import {
  cleanupPreview as previewRecycleCleanup,
  getRecycleBinList,
  manualCleanup,
  restoreTorrents
} from '@/api/recycle-bin'
import {
  cleanupTaskLogs,
  deleteTaskLogs,
  executeTask,
  exportTaskLogs,
  getTaskDetail,
  getTaskList,
  getTaskLogs,
  getTaskLogStatistics,
  getTaskTypeConfig,
  interruptTask,
  pauseTask,
  resumeTask,
  validateCronExpression,
  validatePythonClass,
  validateScriptSyntax
} from '@/api/tasks'
import {
  deleteKeyword,
  deleteMessageLog,
  getKeywordDetail,
  getKeywordList,
  getMessageLogDetail,
  getMessageLogList,
  getMessageStatistics
} from '@/api/tracker'
import {
  applyDownloaderSettings,
  deleteDownloader,
  getDetail as getDownloaderDetail,
  getDownloaderCapabilities,
  getDownloaderSettings,
  getStatus as getDownloaderStatus,
  getStatusAll,
  syncDownloader,
  testConnection
} from '@/api/downloader'

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: jest.fn()
}))

type RequestConfig = Parameters<typeof request>[0]
const mockRequest = request as jest.MockedFunction<typeof request>

function expectRequest(invoke: () => unknown, expected: RequestConfig): void {
  invoke()
  expect(mockRequest).toHaveBeenCalledTimes(1)
  expect(mockRequest).toHaveBeenCalledWith(expected)
}

describe('API 请求契约', () => {
  beforeEach(() => {
    mockRequest.mockReset()
  })

  describe('种子关键链路', () => {
    it('活动筛选参数原样传入列表接口', () => {
      const params = {
        active_only: true,
        skip: 20,
        limit: 20,
        sort_by: 'added_date',
        sort_order: 'desc'
      }
      expectRequest(
        () => getTorrentList(params),
        { url: '/torrents/getList', method: 'get', params }
      )
    })

    it('速度快照使用轻量活动接口', () => {
      expectRequest(
        () => getActiveTorrents(),
        { url: '/torrents/active-torrents', method: 'get' }
      )
    })

    it('单种子删除保持后端要求的四个查询参数', () => {
      const params = {
        info_id: 'info-1',
        downloader_id: 'dl-1',
        delete_data: 1,
        id_recycle: 0
      }
      expectRequest(
        () => deleteTorrents(params),
        { url: '/torrents/delete', method: 'delete', params }
      )
    })

    it('异步批量删除提交 JSON 并通过任务 ID 查询状态', () => {
      const data = { torrent_info_ids: ['a', 'b'], delete_level: 3, operator: 'tester' }
      expectRequest(
        () => deleteBatchAsync(data),
        { url: '/torrents/delete-batch-async', method: 'post', data }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getBatchDeleteStatus('task-1'),
        { url: '/torrents/delete-batch-status/task-1', method: 'get' }
      )
    })

    it.each([
      ['pause', pauseTorrents, '/torrents/pause'],
      ['resume', resumeTorrents, '/torrents/resume']
    ] as const)('%s 操作使用下载器和哈希数组作为请求体', (_name, operation, url) => {
      const data = { downloader_id: 'dl-1', hashes: ['hash-1', 'hash-2'] }
      expectRequest(() => operation(data), { url, method: 'post', data })
    })
  })

  describe('孤儿文件安全链路', () => {
    it('查询最新批次和分页列表', () => {
      expectRequest(
        () => getLatestScan(),
        { url: '/orphan-files/latest', method: 'get' }
      )

      mockRequest.mockReset()
      const params = { page: 2, page_size: 50, downloader_id: 'dl-1', min_size: 1024 }
      expectRequest(
        () => getOrphanList(params),
        { url: '/orphan-files/list', method: 'get', params }
      )
    })

    it('手动扫描使用 POST 且不发送伪造请求体', () => {
      expectRequest(
        () => triggerScan(),
        { url: '/orphan-files/scan', method: 'post' }
      )
    })

    it('预览和执行清理绑定同一 scan_id 与候选 ID', () => {
      const data = { scan_id: 'scan-1', orphan_ids: [1, 2] }
      expectRequest(
        () => previewOrphanCleanup(data),
        { url: '/orphan-files/cleanup-preview', method: 'post', data }
      )

      mockRequest.mockReset()
      expectRequest(
        () => cleanupOrphans(data),
        { url: '/orphan-files/cleanup', method: 'post', data, timeout: 120000 }
      )
    })
  })

  describe('通知接口', () => {
    it('分页查询保留 pageSize 驼峰契约', () => {
      const params = { page: 3, pageSize: 20, type: 'system', is_read: false }
      expectRequest(
        () => getNotificationList(params),
        { url: '/notifications', method: 'get', params }
      )
    })

    it('查询未读数并切换单条已读状态', () => {
      expectRequest(
        () => getUnreadCount(),
        { url: '/notifications/unread-count', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => markAsRead(7),
        { url: '/notifications/mark-read', method: 'put', params: { notification_id: 7 } }
      )

      mockRequest.mockReset()
      expectRequest(
        () => markAsUnread(7),
        { url: '/notifications/mark-unread', method: 'put', params: { notification_id: 7 } }
      )
    })

    it('全部已读和删除使用各自固定端点', () => {
      expectRequest(
        () => markAllAsRead(),
        { url: '/notifications/read-all', method: 'put' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => deleteNotification(9),
        { url: '/notifications/9', method: 'delete' }
      )
    })
  })

  describe('认证与仪表盘接口', () => {
    it('登录、用户信息、改密和退出保持认证端点契约', () => {
      const loginData = { username: 'admin', password: 'secret', twofa_code: '123456' }
      expectRequest(
        () => login(loginData),
        { url: '/auth/login', method: 'post', data: loginData }
      )

      mockRequest.mockReset()
      const infoData = { token: 'token-1' }
      expectRequest(
        () => getUserInfo(infoData),
        { url: '/users/info', method: 'post', data: infoData }
      )

      mockRequest.mockReset()
      const passwordData = { oldPassword: 'old', newPassword: 'new' }
      expectRequest(
        () => changePassword(passwordData),
        { url: '/user/changePassword', method: 'post', data: passwordData }
      )

      mockRequest.mockReset()
      expectRequest(
        () => logout(),
        { url: '/users/logout', method: 'post' }
      )
    })

    it('仪表盘使用只读端点', () => {
      expectRequest(
        () => getDashboardData(),
        { url: '/dashboard', method: 'get' }
      )
    })
  })

  describe('审计与标签接口', () => {
    it('审计查询、统计、导出和归档使用正确载荷位置', () => {
      const query = { operator: 'admin', page: 1, page_size: 20 }
      expectRequest(
        () => queryAuditLogs(query),
        { url: '/audit-logs/query', method: 'post', data: query }
      )

      mockRequest.mockReset()
      const statisticsParams = { start_time: '2026-07-01', end_time: '2026-07-16' }
      expectRequest(
        () => getAuditLogStatistics(statisticsParams),
        { url: '/audit-logs/statistics', method: 'get', params: statisticsParams }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getOperationTypes(),
        { url: '/audit-logs/operation-types', method: 'get' }
      )

      mockRequest.mockReset()
      const exportData = { export_format: 'csv' as const, max_rows: 1000 }
      expectRequest(
        () => exportAuditLogs(exportData),
        { url: '/audit-logs/export', method: 'post', data: exportData }
      )

      mockRequest.mockReset()
      const archiveData = { end_time: '2026-06-01', archive_path: '/archive' }
      expectRequest(
        () => archiveAuditLogs(archiveData),
        { url: '/audit-logs/archive', method: 'post', data: archiveData }
      )
    })

    it('导出文件 URL 编码规则不经过 Axios 包装', () => {
      expect(downloadExportFile('audit.csv')).toBe('/api/audit-logs/download-export/audit.csv')
      expect(mockRequest).not.toHaveBeenCalled()
    })

    it('聚合标签端点区分分类、标签和详细列表', () => {
      expectRequest(
        () => getAllCategories(),
        { url: '/tags/categories', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getAllTags(),
        { url: '/tags/tags', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getAllTagsDetailed('category'),
        { url: '/tags/all', method: 'get', params: { tag_type: 'category' } }
      )
    })

    it('标签 CRUD 与能力检查保持路径参数和请求体契约', () => {
      const listParams = {
        downloader_id: 'dl-1',
        tag_type: 'tag' as const,
        search: 'media'
      }
      expectRequest(
        () => getTagList(listParams),
        {
          url: '/tags/list/dl-1',
          method: 'get',
          params: {
            tag_type: 'tag',
            search: 'media',
            sort_by: 'created_at',
            sort_order: 'desc'
          }
        }
      )

      mockRequest.mockReset()
      const createData = { downloader_id: 'dl-1', tag_name: 'media', tag_type: 'tag' as const }
      expectRequest(
        () => createTag(createData),
        { url: '/tags/create', method: 'post', data: createData }
      )

      mockRequest.mockReset()
      const updateData = { tag_name: 'video', color: '#fff' }
      expectRequest(
        () => updateTag('tag-1', updateData),
        { url: '/tags/update/tag-1', method: 'put', data: updateData }
      )

      mockRequest.mockReset()
      const deleteData = { target_category: '' }
      expectRequest(
        () => deleteTag('tag-1', deleteData),
        { url: '/tags/delete/tag-1', method: 'delete', data: deleteData }
      )

      mockRequest.mockReset()
      expectRequest(
        () => batchDeleteTags(['tag-1', 'tag-2']),
        { url: '/tags/batch-delete', method: 'post', data: { tag_ids: ['tag-1', 'tag-2'] } }
      )

      mockRequest.mockReset()
      expectRequest(
        () => checkCategorySupport('dl-1'),
        { url: '/tags/downloader/dl-1/category-support', method: 'get' }
      )
    })
  })

  describe('回收站接口', () => {
    it('列表、还原、预览和清理保持分页与请求体契约', () => {
      const listParams = { page: 1, page_size: 25, search: 'ubuntu' }
      expectRequest(
        () => getRecycleBinList(listParams),
        { url: '/recycle/bin', method: 'get', params: listParams }
      )

      mockRequest.mockReset()
      const restoreData = { torrent_ids: ['torrent-1', 'torrent-2'] }
      expectRequest(
        () => restoreTorrents(restoreData),
        { url: '/recycle/restore', method: 'post', data: restoreData }
      )

      mockRequest.mockReset()
      const previewData = { days: 30 }
      expectRequest(
        () => previewRecycleCleanup(previewData),
        { url: '/recycle/cleanup-preview', method: 'post', data: previewData }
      )

      mockRequest.mockReset()
      const cleanupData = { torrent_ids: ['torrent-1'] }
      expectRequest(
        () => manualCleanup(cleanupData),
        { url: '/recycle/cleanup', method: 'post', data: cleanupData }
      )
    })
  })

  describe('定时任务接口', () => {
    it('任务查询、详情、执行和日志查询使用固定路径', () => {
      const listParams = { page: 2, limit: 20, enabled: true }
      expectRequest(
        () => getTaskList(listParams),
        { url: '/cronTasks/list', method: 'get', params: listParams }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getTaskDetail(7),
        { url: '/cronTasks/7', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => executeTask({ id: 7 }),
        { url: '/cronTasks/7/start', method: 'post' }
      )

      mockRequest.mockReset()
      const logParams = { task_id: 7, success: false, skip: 10, limit: 10 }
      expectRequest(
        () => getTaskLogs(logParams),
        { url: '/cronTasks/logs', method: 'get', params: logParams }
      )
    })

    it('日志删除、导出、统计和清理区分 params、blob 与 data', () => {
      const deleteParams = { task_id: 7, log_ids: [1, 2] }
      expectRequest(
        () => deleteTaskLogs(deleteParams),
        { url: '/cronTasks/logs/delete', method: 'delete', params: deleteParams }
      )

      mockRequest.mockReset()
      const exportParams = { task_id: 7, format: 'csv' as const }
      expectRequest(
        () => exportTaskLogs(exportParams),
        { url: '/cronTasks/logs/export', method: 'get', params: exportParams, responseType: 'blob' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getTaskLogStatistics(),
        { url: '/cronTasks/logs/statistics', method: 'get' }
      )

      mockRequest.mockReset()
      const cleanupParams = { days: 30, keep_error: true }
      expectRequest(
        () => cleanupTaskLogs(cleanupParams),
        { url: '/cronTasks/logs/cleanup', method: 'post', data: cleanupParams }
      )
    })

    it.each([
      ['pause', pauseTask, '/cronTasks/7/pause'],
      ['resume', resumeTask, '/cronTasks/7/resume'],
      ['interrupt', interruptTask, '/cronTasks/7/interrupt']
    ] as const)('%s 任务控制请求使用 POST', (_name, operation, url) => {
      expectRequest(() => operation(7), { url, method: 'post' })
    })

    it('脚本、Cron、Python 类和任务类型配置走独立验证端点', () => {
      const scriptData = { content: 'print(1)', script_type: 3 }
      expectRequest(
        () => validateScriptSyntax(scriptData),
        { url: '/cronTasks/validation/script', method: 'post', data: scriptData }
      )

      mockRequest.mockReset()
      const cronData = { expression: '0 2 * * *' }
      expectRequest(
        () => validateCronExpression(cronData),
        { url: '/cronTasks/validation/cron', method: 'post', data: cronData }
      )

      mockRequest.mockReset()
      const pythonData = { class_path: 'app.tasks.ExampleTask' }
      expectRequest(
        () => validatePythonClass(pythonData),
        { url: '/cronTasks/validation/python-class', method: 'post', data: pythonData }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getTaskTypeConfig(),
        { url: '/cronTasks/config/task-types', method: 'get' }
      )
    })
  })

  describe('Tracker 消息与关键词接口', () => {
    it('关键词列表、详情和删除保持 ID 路径契约', () => {
      const params = { keyword_type: 'success' as const, page: 1, pageSize: 20 }
      expectRequest(
        () => getKeywordList(params),
        { url: '/tracker-keywords', method: 'get', params }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getKeywordDetail('keyword-1'),
        { url: '/tracker-keywords/keyword-1', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => deleteKeyword('keyword-1'),
        { url: '/tracker-keywords/keyword-1', method: 'delete' }
      )
    })

    it('消息列表、详情、删除和统计保持路径契约', () => {
      const params = { tracker_host: 'tracker.example.com', is_processed: false, pageSize: 50 }
      expectRequest(
        () => getMessageLogList(params),
        { url: '/tracker-messages', method: 'get', params }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getMessageLogDetail('log-1'),
        { url: '/tracker-messages/log-1', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => deleteMessageLog('log-1'),
        { url: '/tracker-messages/log-1', method: 'delete' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getMessageStatistics(),
        { url: '/tracker-messages/statistics', method: 'get' }
      )
    })
  })

  describe('下载器连接与设置接口', () => {
    it('详情、状态、删除和连接测试使用下载器 ID 路径', () => {
      expectRequest(
        () => getDownloaderDetail('dl-1'),
        { url: '/downloader/detail/dl-1', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getDownloaderStatus('dl-1'),
        { url: '/downloader/getStatus/dl-1', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getStatusAll(),
        { url: '/downloader/getStatusAll', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => deleteDownloader('dl-1'),
        { url: '/downloader/delete/dl-1', method: 'delete' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => testConnection('dl-1'),
        { url: '/downloader/test/dl-1', method: 'post' }
      )
    })

    it('同步、设置、应用和能力接口不混用路径前缀', () => {
      expectRequest(
        () => syncDownloader('dl-1'),
        { url: '/torrents/sync-single', method: 'post', data: { downloader_id: 'dl-1' } }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getDownloaderSettings('dl-1'),
        { url: '/downloaders/dl-1/settings', method: 'get' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => applyDownloaderSettings('dl-1'),
        { url: '/downloaders/dl-1/settings/apply', method: 'post' }
      )

      mockRequest.mockReset()
      expectRequest(
        () => getDownloaderCapabilities('dl-1'),
        { url: '/downloaders/dl-1/capabilities', method: 'get' }
      )
    })
  })
})
