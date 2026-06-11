/**
 * 标签管理 API
 * @Time: 2026-02-12
 */

import request from '@/utils/request'

// ==================== 类型定义 ====================

/**
 * 标签类型
 */
export enum TagType {
  CATEGORY = 'category',
  TAG = 'tag'
}

/**
 * 标签数据结构
 */
export interface TorrentTag {
  tag_id: string
  downloader_id: string
  tag_name: string
  tag_type: 'category' | 'tag'
  color: string | null
  created_at: string
  updated_at: string
  dr: number
}

/**
 * 创建标签请求
 */
export interface CreateTagRequest {
  downloader_id: string
  tag_name: string
  tag_type: 'category' | 'tag'
  color?: string
}

/**
 * 更新标签请求
 */
export interface UpdateTagRequest {
  tag_name?: string
  color?: string
}

/**
 * 标签列表查询参数
 */
export interface DeleteTagRequest {
  target_category?: string  // 目标分类名称（空字符串表示未分类）
}

export interface TagListParams {
  downloader_id: string
  tag_type?: 'category' | 'tag'
  search?: string
  sort_by?: 'created_at' | 'tag_name'
  sort_order?: 'asc' | 'desc'
}

// ==================== API 接口 ====================

/**
 * 获取标签列表
 * @param params 查询参数
 */
export function getTagList(params: TagListParams) {
  return request({
    url: `/tags/list/${params.downloader_id}`,
    method: 'get',
    params: {
      tag_type: params.tag_type,
      search: params.search,
      sort_by: params.sort_by || 'created_at',
      sort_order: params.sort_order || 'desc'
    }
  })
}

/**
 * 创建标签
 * @param data 创建数据
 */
export function createTag(data: CreateTagRequest) {
  return request({
    url: '/tags/create',
    method: 'post',
    data
  })
}

/**
 * 更新标签
 * @param tagId 标签ID
 * @param data 更新数据
 */
export function updateTag(tagId: string, data: UpdateTagRequest) {
  return request({
    url: `/tags/update/${tagId}`,
    method: 'put',
    data
  })
}

/**
 * 删除标签
 * @param tagId 标签ID
 */
export function deleteTag(tagId: string, data?: DeleteTagRequest) {
  return request({
    url: `/tags/delete/${tagId}`,
    method: 'delete',
    data
  })
}

/**
 * 批量删除标签
 * @param tagIds 标签ID列表
 */
export function batchDeleteTags(tagIds: string[]) {
  return request({
    url: '/tags/batch-delete',
    method: 'post',
    data: { tag_ids: tagIds }
  })
}

/**
 * 检查下载器是否支持分类功能
 * @param downloaderId 下载器ID
 */
export function checkCategorySupport(downloaderId: string) {
  return request({
    url: `/tags/downloader/${downloaderId}/category-support`,
    method: 'get'
  })
}
