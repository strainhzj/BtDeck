import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

/**
 * RSS 订阅 API（feature rss-subscription-2026-09-24 Phase 1）
 *
 * Phase 1：BtDeck 引擎（订阅源绑定单一下载器，文章手动推送）。
 * Phase 2（feature rss-subscription-phase2-2026-09-24）：模式切换 +
 * 引擎自动下载规则 + qB 原生 RSS 代理（源/规则/偏好/文章透传）。
 */

/** 订阅源 */
export interface RssFeed {
  feedId: string
  downloaderId: string
  name: string
  url: string
  enabled: boolean
  /** 每源刷新间隔覆盖（分钟，null=跟全局调度节奏；Phase 2） */
  refreshIntervalMinutes: number | null
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
  /** 自动规则命中事实（手动推送为 null；Phase 2） */
  addedRuleId?: string | null
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
  /** 刷新间隔覆盖（分钟；显式 null=恢复全局节奏） */
  refreshIntervalMinutes?: number | null
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

// ==============================================================================
// Phase 2（feature rss-subscription-phase2-2026-09-24）：模式 + 自动规则 + qB 原生代理
// ==============================================================================

/** RSS 模式（按下载器二选一；qb_native 仅 qB） */
export type RssModeValue = 'btdeck' | 'qb_native'

export interface RssModeView {
  mode: RssModeValue
  qbNativeAvailable: boolean
}

/** 获取下载器 RSS 模式（缺省 btdeck） */
export function getRssMode(downloaderId: string): Promise<ApiEnvelope<RssModeView>> {
  return request<ApiEnvelope<RssModeView>>({
    url: '/rss/mode',
    method: 'get',
    params: { downloaderId }
  })
}

/** 切换下载器 RSS 模式（qb_native 仅 qB 且需能力） */
export function updateRssMode(downloaderId: string, mode: RssModeValue): Promise<ApiEnvelope<{ mode: RssModeValue, frozenHint: boolean }>> {
  return request<ApiEnvelope<{ mode: RssModeValue, frozenHint: boolean }>>({
    url: '/rss/mode',
    method: 'put',
    data: { downloaderId, mode }
  })
}

/** 引擎自动下载规则 */
export interface RssRule {
  ruleId: string
  downloaderId: string
  name: string
  enabled: boolean
  includeKeywords: string
  excludeKeywords: string | null
  useRegex: boolean
  targetDownloaderId: string | null
  savePath: string | null
  tags: string | null
  feedIds: string[]
  matchCount: number
  lastMatchedAt: string | null
  createdAt: string | null
}

export interface RssRuleListParams {
  downloaderId: string
  page?: number
  pageSize?: number
}

/** 规则创建/更新请求（更新时全部字段可选；显式 null 有语义字段见后端契约） */
export interface RssRuleSaveRequest {
  name?: string
  includeKeywords?: string
  excludeKeywords?: string | null
  useRegex?: boolean
  targetDownloaderId?: string | null
  savePath?: string | null
  tags?: string | null
  feedIds?: string[]
  enabled?: boolean
}

/** 回填计数（创建/更新后立即匹配推送的结果） */
export interface RssRuleBackfill {
  matched: number
  pushed: number
  failed: number
  skippedMode: number
}

/** 匹配预览文章（引擎侧，含源名） */
export interface RssRulePreviewArticle extends RssArticle {
  feedName: string | null
}

/** 获取规则列表（分页） */
export function getRssRules(params: RssRuleListParams): Promise<ApiEnvelope<RssPage<RssRule>>> {
  return request<ApiEnvelope<RssPage<RssRule>>>({
    url: '/rss/rules',
    method: 'get',
    params
  })
}

/** 创建规则（创建后立即回填匹配推送） */
export function createRssRule(downloaderId: string, data: RssRuleSaveRequest): Promise<ApiEnvelope<{ rule: RssRule, backfill: RssRuleBackfill }>> {
  return request<ApiEnvelope<{ rule: RssRule, backfill: RssRuleBackfill }>>({
    url: '/rss/rules',
    method: 'post',
    data: { downloaderId, ...data }
  })
}

/** 更新规则（更新后立即回填匹配推送） */
export function updateRssRule(ruleId: string, data: RssRuleSaveRequest): Promise<ApiEnvelope<{ rule: RssRule, backfill: RssRuleBackfill }>> {
  return request<ApiEnvelope<{ rule: RssRule, backfill: RssRuleBackfill }>>({
    url: `/rss/rules/${ruleId}`,
    method: 'put',
    data
  })
}

/** 删除规则 */
export function deleteRssRule(ruleId: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `/rss/rules/${ruleId}`, method: 'delete' })
}

/** 规则匹配预览（只读，不推送） */
export function previewRssRule(ruleId: string): Promise<ApiEnvelope<{ list: RssRulePreviewArticle[], total: number, pageSize: number, truncated: boolean }>> {
  return request<ApiEnvelope<{ list: RssRulePreviewArticle[], total: number, pageSize: number, truncated: boolean }>>({
    url: `/rss/rules/${ruleId}/match-preview`,
    method: 'post'
  })
}

// ------------------------------------------------------------------------------
// qB 原生 RSS 代理（qB 为事实源，透传不落库）
// ------------------------------------------------------------------------------

/** qB 源树节点 */
export interface RssQbNode {
  type: 'folder' | 'feed'
  name: string
  path: string
  articleCount?: number
  unreadCount?: number
  children?: RssQbNode[]
}

/** qB 文章 */
export interface RssQbArticle {
  articleId: string
  title: string
  link: string
  published: string | null
  isRead: boolean
}

/** qB 规则定义（透传 qB ruleDef，常见字段强类型） */
export interface RssQbRuleDef {
  enabled?: boolean
  mustContain?: string
  mustNotContain?: string
  affectedFeeds?: string[]
  savePath?: string
  assignedCategory?: string
  addPaused?: boolean
  [key: string]: unknown
}

export interface RssQbRule extends RssQbRuleDef {
  name: string
}

/** qB RSS 偏好（白名单四键） */
export interface RssQbPreferences {
  rssProcessingEnabled: boolean
  rssAutoDownloadingEnabled: boolean
  rssRefreshInterval: number
  rssMaxArticlesPerFeed: number
}

const QB_BASE = '/rss/qb'

/** 获取 qB 源树（含未读数） */
export function getQbRssFeeds(downloaderId: string): Promise<ApiEnvelope<{ list: RssQbNode[] }>> {
  return request<ApiEnvelope<{ list: RssQbNode[] }>>({ url: `${QB_BASE}/${downloaderId}/feeds`, method: 'get' })
}

/** 添加 qB 订阅源 */
export function addQbRssFeed(downloaderId: string, path: string, url: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/feeds`, method: 'post', data: { path, url } })
}

/** 添加 qB 文件夹 */
export function addQbRssFolder(downloaderId: string, path: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/folders`, method: 'post', data: { path } })
}

/** 修改 qB 订阅源地址 */
export function updateQbRssFeedUrl(downloaderId: string, path: string, url: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/feeds/url`, method: 'put', params: { path }, data: { url } })
}

/** 删除 qB RSS 项（源或文件夹） */
export function deleteQbRssItem(downloaderId: string, path: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/items`, method: 'delete', params: { path } })
}

/** 移动 qB RSS 项 */
export function moveQbRssItem(downloaderId: string, originPath: string, destPath: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/items/move`, method: 'post', data: { originPath, destPath } })
}

/** 刷新 qB RSS 项（path 为空 = 全部） */
export function refreshQbRssItem(downloaderId: string, path: string | null): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/items/refresh`, method: 'post', data: { path } })
}

/** 标记 qB 已读（articleId 为空 = 整源） */
export function markQbRssRead(downloaderId: string, path: string, articleId: string | null): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/items/mark-read`, method: 'post', data: { path, articleId } })
}

/** 获取 qB 源文章列表 */
export function getQbRssArticles(downloaderId: string, path: string, onlyUnread = false): Promise<ApiEnvelope<{ list: RssQbArticle[], total: number, unreadCount: number }>> {
  return request<ApiEnvelope<{ list: RssQbArticle[], total: number, unreadCount: number }>>({
    url: `${QB_BASE}/${downloaderId}/articles`,
    method: 'get',
    params: { path, onlyUnread }
  })
}

/** 获取 qB 下载规则列表 */
export function getQbRssRules(downloaderId: string): Promise<ApiEnvelope<{ list: RssQbRule[], total: number }>> {
  return request<ApiEnvelope<{ list: RssQbRule[], total: number }>>({ url: `${QB_BASE}/${downloaderId}/rules`, method: 'get' })
}

/** 设置 qB 下载规则 */
export function setQbRssRule(downloaderId: string, name: string, ruleDef: RssQbRuleDef): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/rules`, method: 'post', data: { name, ruleDef } })
}

/** 重命名 qB 下载规则 */
export function renameQbRssRule(downloaderId: string, name: string, newName: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/rules/rename`, method: 'put', params: { name }, data: { newName } })
}

/** 删除 qB 下载规则 */
export function deleteQbRssRule(downloaderId: string, name: string): Promise<ApiEnvelope<Record<string, never>>> {
  return request<ApiEnvelope<Record<string, never>>>({ url: `${QB_BASE}/${downloaderId}/rules`, method: 'delete', params: { name } })
}

/** qB 规则命中文章预览 */
export function getQbRssMatching(downloaderId: string, name: string): Promise<ApiEnvelope<{ feeds: Array<{ feedPath: string, articles: RssQbArticle[] }> }>> {
  return request<ApiEnvelope<{ feeds: Array<{ feedPath: string, articles: RssQbArticle[] }> }>>({ url: `${QB_BASE}/${downloaderId}/rules/matching`, method: 'get', params: { name } })
}

/** 获取 qB RSS 偏好（白名单四键） */
export function getQbRssPreferences(downloaderId: string): Promise<ApiEnvelope<{ preferences: RssQbPreferences }>> {
  return request<ApiEnvelope<{ preferences: RssQbPreferences }>>({ url: `${QB_BASE}/${downloaderId}/preferences`, method: 'get' })
}

/** 更新 qB RSS 偏好（白名单四键） */
export function updateQbRssPreferences(downloaderId: string, data: Partial<RssQbPreferences>): Promise<ApiEnvelope<{ preferences: RssQbPreferences }>> {
  return request<ApiEnvelope<{ preferences: RssQbPreferences }>>({ url: `${QB_BASE}/${downloaderId}/preferences`, method: 'put', data })
}
