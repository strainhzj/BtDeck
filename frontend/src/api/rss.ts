import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

/**
 * RSS 订阅 API（feature rss-subscription-2026-09-24 Phase 1）
 *
 * BtDeck 自建订阅引擎：订阅源绑定单一下载器，文章手动推送。
 * 推送参数（保存路径/标签）随请求携带；downloaderId 覆盖为 Phase 2
 * 按类型路由预留。
 */

/** 订阅源 */
export interface RssFeed {
  feedId: string
  downloaderId: string
  name: string
  url: string
  enabled: boolean
  lastFetchAt: string | null
  /** never / ok / failed */
  lastFetchStatus: 'never' | 'ok' | 'failed'
  lastError: string | null
  createdAt: string | null
  /** 待添加文章数（列表接口附带） */
  pendingCount?: number
}

/** 订阅文章 */
export interface RssArticle {
  articleId: string
  feedId: string
  title: string
  link: string
  publishedAt: string | null
  fetchedAt: string | null
  /** pending / added */
  status: 'pending' | 'added'
  addedAt: string | null
  addedDownloaderId: string | null
}

/** 分页信封（list/total/pageSize 固定字段名） */
export interface RssPage<T> {
  list: T[]
  total: number
  pageSize: number
}

export interface RssFeedListParams {
  downloaderId: string
  page?: number
  pageSize?: number
}

export interface RssFeedCreateRequest {
  downloaderId: string
  name: string
  url: string
}

export interface RssFeedUpdateRequest {
  name?: string
  url?: string
  enabled?: boolean
}

export interface RssArticleListParams {
  page?: number
  pageSize?: number
  status?: 'pending' | 'added'
}

export interface RssArticleAddRequest {
  downloaderId?: string
  savePath?: string
  tags?: string
}

export interface RssRefreshResult {
  newCount: number
  articleCount: number
  lastFetchAt: string
}

/** 获取下载器的订阅源列表（分页） */
export function getRssFeeds(params: RssFeedListParams): Promise<ApiEnvelope<RssPage<RssFeed>>> {
  return request<ApiEnvelope<RssPage<RssFeed>>>({
    url: '/rss/feeds',
    method: 'get',
    params
  })
}

/** 新增订阅源 */
export function createRssFeed(data: RssFeedCreateRequest): Promise<ApiEnvelope<{ feed: RssFeed }>> {
  return request<ApiEnvelope<{ feed: RssFeed }>>({
    url: '/rss/feeds',
    method: 'post',
    data
  })
}

/** 更新订阅源（部分更新） */
export function updateRssFeed(feedId: string, data: RssFeedUpdateRequest): Promise<ApiEnvelope<{ feed: RssFeed }>> {
  return request<ApiEnvelope<{ feed: RssFeed }>>({
    url: `/rss/feeds/${feedId}`,
    method: 'put',
    data
  })
}

/** 删除订阅源（文章级联删除） */
export function deleteRssFeed(feedId: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({
    url: `/rss/feeds/${feedId}`,
    method: 'delete'
  })
}

/** 手动刷新订阅源（抓取 + guid 去重入库） */
export function refreshRssFeed(feedId: string): Promise<ApiEnvelope<RssRefreshResult>> {
  return request<ApiEnvelope<RssRefreshResult>>({
    url: `/rss/feeds/${feedId}/refresh`,
    method: 'post'
  })
}

/** 获取订阅源文章列表（分页） */
export function getRssArticles(
  feedId: string,
  params: RssArticleListParams
): Promise<ApiEnvelope<RssPage<RssArticle>>> {
  return request<ApiEnvelope<RssPage<RssArticle>>>({
    url: `/rss/feeds/${feedId}/articles`,
    method: 'get',
    params
  })
}

/** 推送文章到下载器 */
export function addRssArticle(articleId: string, data: RssArticleAddRequest): Promise<ApiEnvelope<{ article: RssArticle, downloaderId: string }>> {
  return request<ApiEnvelope<{ article: RssArticle, downloaderId: string }>>({
    url: `/rss/articles/${articleId}/add`,
    method: 'post',
    data
  })
}
