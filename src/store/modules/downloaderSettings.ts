/**
 * 下载器设置管理 - Vuex 状态管理模块
 */
import { Module } from 'vuex'
import {
  DownloaderSettings,
  DownloaderCapabilities,
  SettingTemplate,
  SpeedScheduleRule
} from '@/views/downloader/types'
import {
  getDownloaderSettings,
  updateDownloaderSettings,
  getDownloaderCapabilities,
  testDownloaderSettings,
  getTemplateList,
  getTemplateDetail,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  applyTemplate
} from '@/api/downloader'

interface DownloaderSettingsState {
  // 设置数据
  settings: Record<string, DownloaderSettings>

  // 能力信息
  capabilities: Record<string, DownloaderCapabilities>

  // 模板数据
  templates: SettingTemplate[]

  // 加载状态
  loading: boolean
  capabilitiesLoading: boolean
  templatesLoading: boolean

  // 错误状态
  error: string | null
}

const downloaderSettingsModule: Module<DownloaderSettingsState, any> = {
  namespaced: true,

  state: {
    settings: {},
    capabilities: {},
    templates: [],
    loading: false,
    capabilitiesLoading: false,
    templatesLoading: false,
    error: null
  },

  mutations: {
    // 更新设置
    SET_SETTINGS(state, payload: { downloaderId: string, settings: DownloaderSettings }) {
      state.settings = {
        ...state.settings,
        [payload.downloaderId]: payload.settings
      }
    },

    // 更新能力信息
    SET_CAPABILITIES(state, payload: { downloaderId: string, capabilities: DownloaderCapabilities }) {
      state.capabilities = {
        ...state.capabilities,
        [payload.downloaderId]: payload.capabilities
      }
    },

    // 更新模板列表
    SET_TEMPLATES(state, templates: SettingTemplate[]) {
      state.templates = templates
    },

    // 添加模板
    ADD_TEMPLATE(state, template: SettingTemplate) {
      state.templates.push(template)
    },

    // 更新模板
    UPDATE_TEMPLATE(state, template: SettingTemplate) {
      const index = state.templates.findIndex(t => t.id === template.id)
      if (index !== -1) {
        state.templates.splice(index, 1, template)
      }
    },

    // 删除模板
    DELETE_TEMPLATE(state, templateId: string) {
      const index = state.templates.findIndex(t => t.id === templateId)
      if (index !== -1) {
        state.templates.splice(index, 1)
      }
    },

    // 设置加载状态
    SET_LOADING(state, loading: boolean) {
      state.loading = loading
    },

    SET_CAPABILITIES_LOADING(state, loading: boolean) {
      state.capabilitiesLoading = loading
    },

    SET_TEMPLATES_LOADING(state, loading: boolean) {
      state.templatesLoading = loading
    },

    // 设置错误状态
    SET_ERROR(state, error: string | null) {
      state.error = error
    }
  },

  actions: {
    // 获取下载器设置
    async fetchSettings({ commit }, downloaderId: string) {
      commit('SET_LOADING', true)
      commit('SET_ERROR', null)

      try {
        const response = await getDownloaderSettings(downloaderId)
        if (response.code === '200') {
          commit('SET_SETTINGS', {
            downloaderId,
            settings: response.data
          })
          return response.data
        } else {
          throw new Error(response.msg || '获取设置失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '获取设置失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_LOADING', false)
      }
    },

    // 更新下载器设置
    async updateSettings({ commit }, payload: { downloaderId: string, settings: Partial<DownloaderSettings> }) {
      commit('SET_LOADING', true)
      commit('SET_ERROR', null)

      try {
        const response = await updateDownloaderSettings(payload.downloaderId, payload.settings)
        if (response.code === '200') {
          commit('SET_SETTINGS', {
            downloaderId: payload.downloaderId,
            settings: response.data
          })
          return response.data
        } else {
          throw new Error(response.msg || '更新设置失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '更新设置失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_LOADING', false)
      }
    },

    // 获取下载器能力信息
    async fetchCapabilities({ commit }, downloaderId: string) {
      commit('SET_CAPABILITIES_LOADING', true)

      try {
        const response = await getDownloaderCapabilities(downloaderId)
        if (response.code === '200') {
          commit('SET_CAPABILITIES', {
            downloaderId,
            capabilities: response.data
          })
          return response.data
        } else {
          throw new Error(response.msg || '获取能力信息失败')
        }
      } catch (error: any) {
        console.error('获取下载器能力失败:', error)
        // 能力信息获取失败不影响主流程，返回默认值
        const defaultCapabilities: DownloaderCapabilities = {
          downloader_id: downloaderId,
          downloader_type: 0,
          supports_speed_scheduling: false,
          supports_connection_limits: true,
          supports_queue_management: true,
          supports_path_mapping: false,
          supports_advanced_options: true
        }
        commit('SET_CAPABILITIES', {
          downloaderId,
          capabilities: defaultCapabilities
        })
        return defaultCapabilities
      } finally {
        commit('SET_CAPABILITIES_LOADING', false)
      }
    },

    // 测试下载器设置连接
    async testSettings({ commit }, downloaderId: string) {
      try {
        const response = await testDownloaderSettings(downloaderId)
        return response
      } catch (error) {
        throw error
      }
    },

    // 获取模板列表
    async fetchTemplates({ commit }, params?: any) {
      commit('SET_TEMPLATES_LOADING', true)

      try {
        const response = await getTemplateList(params || { page: 1, pageSize: 100 })
        if (response.code === '200') {
          commit('SET_TEMPLATES', response.data.list)
          return response.data.list
        } else {
          throw new Error(response.msg || '获取模板列表失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '获取模板列表失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_TEMPLATES_LOADING', false)
      }
    },

    // 获取模板详情
    async fetchTemplateDetail({ commit }, templateId: string) {
      try {
        const response = await getTemplateDetail(templateId)
        if (response.code === '200') {
          return response.data
        } else {
          throw new Error(response.msg || '获取模板详情失败')
        }
      } catch (error) {
        throw error
      }
    },

    // 创建模板
    async createTemplate({ commit }, template: Partial<SettingTemplate>) {
      commit('SET_LOADING', true)

      try {
        const response = await createTemplate(template)
        if (response.code === '200') {
          commit('ADD_TEMPLATE', response.data)
          return response.data
        } else {
          throw new Error(response.msg || '创建模板失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '创建模板失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_LOADING', false)
      }
    },

    // 更新模板
    async updateTemplate({ commit }, template: SettingTemplate) {
      commit('SET_LOADING', true)

      try {
        const response = await updateTemplate(template.id, template)
        if (response.code === '200') {
          commit('UPDATE_TEMPLATE', response.data)
          return response.data
        } else {
          throw new Error(response.msg || '更新模板失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '更新模板失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_LOADING', false)
      }
    },

    // 删除模板
    async deleteTemplate({ commit }, templateId: string) {
      commit('SET_LOADING', true)

      try {
        const response = await deleteTemplate(templateId)
        if (response.code === '200') {
          commit('DELETE_TEMPLATE', templateId)
          return true
        } else {
          throw new Error(response.msg || '删除模板失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '删除模板失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_LOADING', false)
      }
    },

    // 应用模板到下载器
    async applyTemplate({ commit }, payload: { templateId: string, downloaderId: string, overrideLocal?: boolean }) {
      commit('SET_LOADING', true)

      try {
        const response = await applyTemplate(payload.templateId, {
          template_id: payload.templateId,
          downloader_id: payload.downloaderId,
          override_local: payload.overrideLocal ?? true
        })
        if (response.code === '200') {
          // 同时更新设置
          commit('SET_SETTINGS', {
            downloaderId: payload.downloaderId,
            settings: response.data
          })
          return response.data
        } else {
          throw new Error(response.msg || '应用模板失败')
        }
      } catch (error: any) {
        const errorMsg = error?.response?.data?.msg || error?.message || '应用模板失败'
        commit('SET_ERROR', errorMsg)
        throw error
      } finally {
        commit('SET_LOADING', false)
      }
    }
  },

  getters: {
    // 获取下载器设置
    getSettingsById: (state) => (downloaderId: string) => {
      return state.settings[downloaderId]
    },

    // 获取下载器能力信息
    getCapabilitiesById: (state) => (downloaderId: string) => {
      return state.capabilities[downloaderId]
    },

    // 根据类型过滤模板
    getTemplatesByType: (state) => (downloaderType: 'qbittorrent' | 'transmission') => {
      return state.templates.filter(template => {
        return (
          template.downloader_type === downloaderType ||
          template.downloader_type === 'both'
        )
      })
    },

    // 获取系统默认模板
    getSystemTemplates: (state) => {
      return state.templates.filter(template => template.is_system_default)
    },

    // 获取用户模板
    getUserTemplates: (state) => {
      return state.templates.filter(template => !template.is_system_default)
    },

    // 检查是否正在加载
    isLoading: (state) => {
      return state.loading || state.capabilitiesLoading || state.templatesLoading
    },

    // 获取错误信息
    getError: (state) => {
      return state.error
    }
  }
}

export default downloaderSettingsModule
