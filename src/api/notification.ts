/* eslint-disable camelcase */
import request from '@/utils/request'

/** 通知项 */
export interface NotificationItem {
  id: number
  type: string              // version_update / system
  title: string
  content: string | null
  priority: string          // info / warning / error
  is_read: boolean
  extra_data: {
    version?: string
    current_version?: string
    release_url?: string
    published_at?: string
  } | null
  created_at: string
  read_at: string | null
}

/** 分页响应 */
export interface NotificationListData {
  total: number
  page: number
  pageSize: number
  list: NotificationItem[]
}

/** 通用 API 响应 */
export interface ApiResponse<T = unknown> {
  status: string
  msg: string
  code: string
  data: T
}

/**
 * 获取通知列表
 */
export function getNotificationList(params?: {
  page?: number
  pageSize?: number
  type?: string
  is_read?: boolean
}): Promise<ApiResponse<NotificationListData>> {
  return request({
    url: '/notifications',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<NotificationListData>>
}

/**
 * 获取未读通知数量
 */
export function getUnreadCount(): Promise<ApiResponse<{ count: number }>> {
  return request({
    url: '/notifications/unread-count',
    method: 'get'
  }) as unknown as Promise<ApiResponse<{ count: number }>>
}

/**
 * 标记通知为已读
 */
export function markAsRead(id: number): Promise<ApiResponse<null>> {
  return request({
    url: '/notifications/mark-read',
    method: 'put',
    params: { notification_id: id }
  }) as unknown as Promise<ApiResponse<null>>
}

/**
 * 标记通知为未读
 */
export function markAsUnread(id: number): Promise<ApiResponse<null>> {
  return request({
    url: '/notifications/mark-unread',
    method: 'put',
    params: { notification_id: id }
  }) as unknown as Promise<ApiResponse<null>>
}

/**
 * 全部标记为已读
 */
export function markAllAsRead(): Promise<ApiResponse<{ count: number }>> {
  return request({
    url: '/notifications/read-all',
    method: 'put'
  }) as unknown as Promise<ApiResponse<{ count: number }>>
}

/**
 * 删除通知
 */
export function deleteNotification(id: number): Promise<ApiResponse<null>> {
  return request({
    url: `/notifications/${id}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<null>>
}
