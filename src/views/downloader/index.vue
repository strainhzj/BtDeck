<template>
  <div class="downloader-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>下载器管理</h1>
      <div class="header-actions">
        <!-- 搜索框 -->
        <el-input
          v-model="searchKeyword"
          placeholder="搜索下载器别名"
          prefix-icon="el-icon-search"
          clearable
          :style="{width: '280px'}"
          @input="handleSearchInput"
          @clear="handleSearchClear"
        />
        <!-- 搜索结果提示 -->
        <span v-if="isSearching" class="search-result-tip">
          找到 {{ filteredDownloaderList.length }} 个下载器
        </span>
        <el-button
          :icon="listLoading ? 'el-icon-loading' : 'el-icon-refresh'"
          :loading="listLoading"
          @click="handleRefresh"
        >
          刷新
        </el-button>
        <el-button type="primary" icon="el-icon-plus" @click="handleAdd">
          新增下载器
        </el-button>
      </div>
    </div>

    <!-- 无搜索结果提示 -->
    <div v-if="isSearching && filteredDownloaderList.length === 0 && !listLoading" class="empty-search-result">
      <div class="empty-icon">🔍</div>
      <div class="empty-text">无搜索结果</div>
      <div class="empty-tip">请尝试其他关键词</div>
    </div>

    <!-- 下载器卡片网格 -->
    <div v-show="!isSearching || filteredDownloaderList.length > 0" v-loading="listLoading" class="downloader-grid">
      <!-- 下载器卡片 -->
      <downloader-card
        v-for="item in filteredDownloaderList"
        :key="safeGetId(item.info)"
        :info="item.info"
        :status="item.status"
        :is-testing="testingIds.includes(safeGetId(item.info))"
        :is-syncing="syncingIds.includes(safeGetId(item.info))"
        @settings="handleSettings"
        @test="handleTest"
        @sync="handleSync"
        @delete="handleDelete"
        @toggle-enable="handleToggleEnable"
      />

      <!-- 添加下载器卡片 -->
      <div class="downloader-card-add" @click="handleAdd">
        <div class="add-icon">➕</div>
        <div class="add-text">添加新下载器</div>
      </div>
    </div>

    <!-- 新增/编辑/设置弹框 -->
    <downloader-settings-dialog
      :visible.sync="dialogVisible"
      :downloader="currentDownloader"
      @submit="handleSubmit"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { Message, MessageBox } from 'element-ui'
import { Route } from 'vue-router'
import DownloaderCard from './components/DownloaderCard.vue'
import DownloaderSettingsDialog from './components/DownloaderSettingsDialog.vue'
import {
  getList,
  getStatus,
  getStatusAll,
  addDownloader,
  upDownloader,
  deleteDownloader,
  testConnection,
  syncDownloader
} from '@/api/downloader'
import {
  Downloader,
  DownloaderStatus,
  DownloaderFormData,
  DownloaderCardData,
  OnlineStatus
} from './types'

@Component({
  name: 'DownloaderManager',
  components: {
    DownloaderCard,
    DownloaderSettingsDialog
  }
})
export default class DownloaderManager extends Vue {
  // 数据列表
  private downloaderList: DownloaderCardData[] = []
  private listLoading = true
  private listRequesting = false // 防抖标志：防止getList重复调用
  private requestSequence = 0 // 请求序列号：用于识别最新请求，避免过期响应覆盖

  // ✅ 使用 Map 存储下载器对象，避免因 downloaderList 重新赋值导致引用失效
  private downloaderMap: Map<string, DownloaderCardData> = new Map()

  // 搜索相关
  private searchKeyword = ''
  private isSearching = false
  private searchDebounceTimer: number | null = null

  // 弹框相关
  private dialogVisible = false
  private currentDownloader: Downloader | null = null

  // 测试连接状态
  private testingIds: string[] = []

  // 同步状态
  private syncingIds: string[] = []

  // 状态轮询相关（批量轮询）
  private continueGetStatus = true
  private statusPollingTimer: number | null = null
  private pollInterval = 5000 // 固定5秒轮询间隔

  // 计算属性：过滤后的下载器列表
  get filteredDownloaderList(): DownloaderCardData[] {
    if (!this.isSearching || !this.searchKeyword.trim()) {
      return this.downloaderList
    }
    const keyword = this.searchKeyword.trim().toLowerCase()
    return this.downloaderList.filter(item =>
      item.info.nickname?.toLowerCase().includes(keyword)
    )
  }

  created() {
    this.getList()
    // 监听路由变化（移除 immediate: true，避免竞态条件）
    this.$watch('$route', (to: Route, from: Route) => {
      this.handleRouteChange(to, from)
    })
  }

  destroyed() {
    // 组件销毁时清理轮询定时器
    this.continueGetStatus = false
    this.clearPollingTimer()
  }

  // ==================== 数据获取 ====================

  private async getList() {
    // 生成当前请求的序列号
    const currentSeq = ++this.requestSequence

    // 防抖检查：如果已经在请求中，直接返回
    if (this.listRequesting) {
      return
    }

    this.listRequesting = true
    this.listLoading = true

    try {
      const response = await getList({})

      // 检查是否是最新的请求（避免过期响应覆盖）
      if (currentSeq !== this.requestSequence) {
        return
      }

      const { data } = response

      // ✅ 同时更新 downloaderList 和 downloaderMap
      this.downloaderList = data.map((item: Downloader) => ({
        info: item,
        status: this.initDownloaderStatus()
      }))

      // 更新 Map，确保轮询函数能找到最新的下载器对象
      this.downloaderMap.clear()
      this.downloaderList.forEach(item => {
        const id = this.safeGetId(item.info)
        if (id) {
          this.downloaderMap.set(id, item)
        }
      })

      // 启动状态轮询（仅在非搜索状态）
      if (this.isCurrentDownloaderPage() && !this.isSearching) {
        // 在启动新轮询前清理旧轮询
        this.continueGetStatus = false
        this.clearPollingTimer()

        // 启动新轮询
        this.continueGetStatus = true
        this.startBatchPolling()
      }
    } catch (error) {
      // 只处理最新的请求错误
      if (currentSeq === this.requestSequence) {
        console.error('获取下载器列表失败:', error)
        Message.error('获取下载器列表失败')
      }
      // 失败后不重启轮询，保持清理状态
    } finally {
      // 只在当前请求完成后清除标志（避免清除最新请求的标志）
      if (currentSeq === this.requestSequence) {
        this.listLoading = false
        this.listRequesting = false
      }
    }
  }

  // ==================== 搜索功能 ====================

  // 搜索输入处理（防抖300ms）
  private handleSearchInput(value: string) {
    // 清除之前的防抖定时器
    if (this.searchDebounceTimer) {
      clearTimeout(this.searchDebounceTimer)
    }

    if (value.trim()) {
      // 输入有内容，开始搜索
      this.searchDebounceTimer = setTimeout(() => {
        this.performSearch(value.trim())
      }, 300) as unknown as number
    } else {
      // 输入为空，清除搜索状态
      this.clearSearch()
    }
  }

  // 执行搜索
  private performSearch(keyword: string) {
    this.isSearching = true
    this.searchKeyword = keyword

    // 搜索时暂停轮询
    this.continueGetStatus = false
    this.clearPollingTimer()
  }

  // 清除搜索
  private handleSearchClear() {
    this.clearSearch()
  }

  // 清除搜索状态
  private clearSearch() {
    this.isSearching = false
    this.searchKeyword = ''

    // 恢复轮询
    if (this.isCurrentDownloaderPage()) {
      this.continueGetStatus = true
      this.startBatchPolling()
    }
  }

  // 初始化下载器状态（空数据降级逻辑）
  private initDownloaderStatus(): DownloaderStatus {
    return {
      online: undefined,  // 未检测
      delay: undefined,
      upload_speed: undefined,
      download_speed: undefined,
      downloading_count: undefined,  // 后端未实现，显示 '-'
      seeding_count: undefined,      // 后端未实现，显示 '-'
      last_online: undefined,        // 后端未实现，显示 '-'
      connection_status: undefined,
      connection_msg: undefined
    }
  }

  // 字段名映射：后端驼峰 → 前端蛇形
  private mapApiStatusToFrontend(apiStatus: any): DownloaderStatus {
    return {
      online: true,
      delay: apiStatus.delay,
      upload_speed: apiStatus.uploadSpeed, // 直接使用后端返回的带单位字符串
      download_speed: apiStatus.downloadSpeed, // 直接使用后端返回的带单位字符串
      downloading_count: apiStatus.downloadingCount,
      seeding_count: apiStatus.seedingCount,
      connection_status: apiStatus.connectStatus === 'connected' ? 'success' : 'error',
      connection_msg: apiStatus.connectStatus === 'connected' ? '连接成功' : '连接失败',
      last_online: undefined
    }
  }

  // ==================== 状态轮询 ====================

  // 路由变化处理
  private handleRouteChange(to: Route, from?: Route) {
    const currentPath = to?.path || this.$route.path
    const previousPath = from?.path || 'unknown'

    const isDownloaderPage = currentPath === '/downloader/index'
    const wasDownloaderPage = previousPath === '/downloader/index'

    if (!wasDownloaderPage && isDownloaderPage) {
      // 进入下载器页面
      this.continueGetStatus = true

      // ✅ 只有在列表已加载时才启动轮询（避免在 getList 完成前启动）
      if (this.downloaderList && this.downloaderList.length > 0) {
        this.startBatchPolling()
      }
      // 否则等待 getList 完成后自动启动
    } else if (wasDownloaderPage && !isDownloaderPage) {
      // 离开下载器页面，停止轮询
      this.continueGetStatus = false
      this.clearPollingTimer()
    }
  }

  // ==================== 工具函数 ====================

  /**
   * 安全获取下载器ID（避免undefined访问错误）
   * 兼容 id 和 downloaderId 两种字段名
   * @param info 下载器信息对象
   * @returns 下载器ID字符串，如果获取失败返回空字符串
   */
  private safeGetId(info: any): string {
    if (!info) {
      return ''
    }
    const id = info.id || info.downloaderId
    return id ? String(id) : ''
  }

  /**
   * 安全获取下载器info对象（避免undefined访问错误）
   * @param item 下载器卡片数据
   * @returns 下载器info对象，如果不存在返回空对象
   */
  private safeGetInfo(item: any): any {
    return item?.info || {}
  }

  // 检查当前是否在下载器页面
  private isCurrentDownloaderPage(): boolean {
    return this.$route.path === '/downloader/index'
  }

  // ==================== 状态轮询（批量优化版） ====================

  /**
   * 启动批量轮询（单一定时器）
   * 相比旧版的多个独立定时器，大幅降低请求次数和服务器负载
   */
  private startBatchPolling() {
    // ✅ 防御性检查：如果列表为空，不启动轮询
    if (!this.downloaderList || this.downloaderList.length === 0) {
      return
    }

    // 立即执行一次
    this.pollAllDownloaders()

    // 设置定时轮询
    this.statusPollingTimer = setTimeout(() => {
      if (this.continueGetStatus && this.isCurrentDownloaderPage()) {
        this.pollAllDownloaders()
      }
    }, this.pollInterval) as unknown as number
  }

  /**
   * 批量轮询所有下载器状态
   * 一次API调用获取所有在线下载器的状态
   */
  private async pollAllDownloaders() {
    if (!this.continueGetStatus || !this.isCurrentDownloaderPage()) {
      return
    }

    // P1-2修复：添加Map初始化检查，防止未定义时调用.get()方法
    if (!this.downloaderMap) {
      console.warn('下载器Map未初始化，跳过本轮轮询')
      return
    }

    try {
      // 调用批量接口
      const response = await getStatusAll()

      // 检查响应有效性
      const hasValidData = response && response.data && Array.isArray(response.data)

      if (!hasValidData) {
        console.warn('批量状态响应格式异常:', response)
        // 标记所有下载器为离线
        this.markAllDownloadersOffline()
        return
      }

      // 构建在线下载器ID集合
      const onlineIds = new Set<string>()

      // 遍历返回的状态数据
      for (const apiStatus of response.data) {
        const downloaderId = apiStatus.id
        if (!downloaderId) continue

        onlineIds.add(downloaderId)

        // 从 Map 中获取对应的下载器对象
        const downloader = this.downloaderMap.get(downloaderId)

        if (downloader) {
          // 字段名映射：后端驼峰 → 前端蛇形
          const mappedStatus = this.mapApiStatusToFrontend(apiStatus)

          // ✅ 完全替换 status 对象，确保触发 Vue 2 响应式更新
          downloader.status = {
            ...mappedStatus,
            online: apiStatus.connectStatus === 'connected',
            connection_status: apiStatus.connectStatus === 'connected' ? 'success' : 'error',
            connection_msg: apiStatus.connectStatus === 'connected' ? '连接成功' : '连接失败',
            // 保留其他可能未定义的字段
            last_online: downloader.status.last_online
          }
        }
      }

      // 标记未在返回列表中的下载器为离线
      this.markOfflineDownloaders(onlineIds)

    } catch (error) {
      console.warn('批量获取下载器状态失败:', error)

      // 失败时标记所有下载器为离线
      this.markAllDownloadersOffline()
    }

    // 清理之前的定时器
    if (this.statusPollingTimer) {
      clearTimeout(this.statusPollingTimer)
    }

    // 设置下一次轮询（固定5秒间隔）
    if (this.continueGetStatus && this.isCurrentDownloaderPage()) {
      this.statusPollingTimer = setTimeout(() => {
        this.pollAllDownloaders()
      }, this.pollInterval) as unknown as number
    }
  }

  /**
   * 标记未在在线列表中的下载器为离线
   * @param onlineIds 在线下载器ID集合
   */
  private markOfflineDownloaders(onlineIds: Set<string>) {
    // P1-2修复：添加Map初始化检查
    if (!this.downloaderMap) {
      console.warn('下载器Map未初始化，跳过离线标记')
      return
    }

    // 遍历所有下载器，未在在线列表中的标记为离线
    this.downloaderList.forEach(item => {
      const id = this.safeGetId(item.info)
      if (!id) return

      // 如果ID不在在线集合中，标记为离线
      if (!onlineIds.has(id)) {
        const downloader = this.downloaderMap.get(id)
        if (downloader) {
          downloader.status = {
            ...downloader.status,
            online: false,
            connection_status: 'offline',
            connection_msg: '离线',
            delay: undefined
          }
        }
      }
    })
  }

  /**
   * 标记所有下载器为离线（异常降级）
   */
  private markAllDownloadersOffline() {
    // P1-2修复：添加Map初始化检查
    if (!this.downloaderMap) {
      console.warn('下载器Map未初始化，跳过离线标记')
      return
    }

    this.downloaderList.forEach(item => {
      const id = this.safeGetId(item.info)
      if (!id) return

      const downloader = this.downloaderMap.get(id)
      if (downloader) {
        downloader.status = {
          ...downloader.status,
          online: false,
          connection_status: 'offline',
          connection_msg: '离线',
          delay: undefined
        }
      }
    })
  }

  /**
   * 清理批量轮询定时器
   */
  private clearPollingTimer() {
    if (this.statusPollingTimer) {
      clearTimeout(this.statusPollingTimer)
      this.statusPollingTimer = null
    }
  }

  // ==================== 操作处理 ====================

  // 刷新列表
  private handleRefresh() {
    this.getList()
  }

  // 新增下载器
  private handleAdd() {
    this.currentDownloader = null
    this.dialogVisible = true
  }

  // 设置下载器（复用同一个对话框）
  private handleSettings(downloader: Downloader) {
    this.currentDownloader = downloader
    this.dialogVisible = true
  }

  // 提交表单（新增/编辑）
  // DownloaderSettingsDialog 内部已处理提交逻辑，这里只需要关闭对话框和刷新列表
  private async handleSubmit() {
    this.dialogVisible = false
    await this.getList()
  }

  // 测试连接
  private async handleTest(id: string) {
    // 添加到测试列表
    this.testingIds.push(id)

    try {
      const response = await testConnection(id)

      // 验证响应数据结构
      if (!response?.data) {
        throw new Error('响应数据格式异常')
      }

      const { data } = response

      // ✅ 从 Map 中获取下载器对象
      const downloader = this.downloaderMap.get(id)
      if (downloader) {
        // 更新状态（测试结果）
        if (data.success) {
          downloader.status = {
            ...downloader.status,
            online: true,
            delay: data.delay,
            connection_status: 'success',
            connection_msg: '连接成功'
          }
          Message.success(`连接成功，延迟 ${data.delay || 0}ms`)
        } else {
          downloader.status = {
            ...downloader.status,
            online: false,
            connection_status: 'error',
            connection_msg: data.message || '连接失败'
          }
          Message.error(data.message || '连接失败')
        }
      }
    } catch (error: any) {
      console.error('测试连接失败:', error)

      // 提供更详细的错误信息
      const errorMsg = error?.response?.data?.msg || error?.message || '测试连接失败'
      Message.error(errorMsg)
    } finally {
      // 从测试列表移除
      const index = this.testingIds.indexOf(id)
      if (index > -1) {
        this.testingIds.splice(index, 1)
      }
    }
  }
    // 同步下载器种子
  private async handleSync(id: string) {
    // 参数验证
    if (!id || typeof id !== "string" || id.trim() === "") {
      Message.error("下载器ID无效")
      return
    }

    const validId = id.trim()

    // 防止重复调用（竞态条件保护）
    if (this.syncingIds.includes(validId)) {
      console.warn(`下载器 ${validId} 正在同步中，忽略重复请求`)
      return
    }

    // 添加到同步列表
    this.syncingIds.push(validId)

    try {
      const response = await syncDownloader(validId)

      // 验证响应数据结构
      if (!response?.data) {
        throw new Error('响应数据格式异常')
      }

      const { data, msg, code } = response

      if (code === '200') {
        Message.success('执行成功')

        // 同步成功后，批量轮询会自动更新状态（无需手动触发）
      } else {
        Message.error('执行失败')
      }
    } catch (error: unknown) {
      console.error('同步下载器失败:', error)

      // 提供更详细的错误信息（类型守卫）
      let errorMsg = '同步失败'
      if (error && typeof error === 'object') {
        if ('response' in error) {
          const err = error as { response?: { data?: { msg?: string } } }
          if (err.response?.data?.msg) {
            errorMsg = String(err.response.data.msg)
          }
        } else if ('message' in error) {
          const err = error as { message?: string }
          if (err.message) {
            errorMsg = String(err.message)
          }
        }
      } else if (error && typeof error === 'string') {
        errorMsg = error
      }
      Message.error(errorMsg)
    } finally {
      // 从同步列表移除
      const index = this.syncingIds.indexOf(validId)
      if (index > -1) {
        this.syncingIds.splice(index, 1)
      }
    }
  }



  // 切换启用/停用状态
  private async handleToggleEnable(downloader: Downloader) {
    // 保存原始状态（用于失败回滚）
    const originalEnabled = downloader.enabled
    const newEnabled = downloader.enabled === '1' ? '0' : '1'

    // 立即更新UI状态
    downloader.enabled = newEnabled

    try {
      await upDownloader({ ...downloader, enabled: newEnabled })
      Message.success(newEnabled === '1' ? '已启用' : '已停用')
    } catch (error) {
      console.error('更新状态失败:', error)
      // 失败回滚
      downloader.enabled = originalEnabled
      Message.error('操作失败，已恢复原状态')
    }
  }

  // 删除下载器
  private handleDelete(downloader: Downloader) {
    MessageBox.confirm(
      `确定要删除下载器"${downloader.nickname}"吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    ).then(async() => {
      try {
        await deleteDownloader(downloader.id)
        Message.success('删除成功')

        // getList 会重新初始化轮询，无需手动清理
        await this.getList()
      } catch (error) {
        console.error('删除失败:', error)
        Message.error('删除失败')
      }
    }).catch(() => {
      // 取消删除
    })
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.downloader-container {
  max-width: 1600px;
  margin: 0 auto;
}

// 页面头部
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);

  h1 {
    font-size: 28px;
    font-weight: var(--font-weight-bold);
    color: var(--color-text-primary);
    margin: 0;
  }

  .header-actions {
    display: flex;
    gap: var(--spacing-sm);
    align-items: center;

    .search-result-tip {
      font-size: var(--font-size-sm);
      color: var(--color-text-secondary);
      margin-left: var(--spacing-sm);
      white-space: nowrap;
    }
  }
}

// 空搜索结果
.empty-search-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl) 0;
  min-height: 400px;

  .empty-icon {
    font-size: 64px;
    margin-bottom: var(--spacing-lg);
    opacity: 0.5;
  }

  .empty-text {
    font-size: var(--font-size-lg);
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-secondary);
    margin-bottom: var(--spacing-xs);
  }

  .empty-tip {
    font-size: var(--font-size-sm);
    color: var(--color-text-tertiary);
  }
}

// 下载器卡片网格 - 正方形布局
.downloader-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: var(--spacing-lg);
}

// 添加下载器卡片
.downloader-card-add {
  aspect-ratio: 1 / 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--color-border-primary);
  background: linear-gradient(135deg, var(--color-bg-secondary), var(--color-bg-tertiary));
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--transition-base);

  &:hover {
    border-color: var(--color-primary);
    background: var(--color-bg-secondary);
    transform: translateY(-4px);
    box-shadow: var(--shadow-md);
  }
}

.add-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-sm);
  color: var(--color-primary);
}

.add-text {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}
</style>
