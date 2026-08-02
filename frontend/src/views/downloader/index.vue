<template>
  <main
    class="downloader-control-room"
    aria-label="下载器管理"
    @pointermove="handlePointerMove"
    @pointerleave="resetPointerGlow"
  >
    <div class="control-room-atmosphere" aria-hidden="true">
      <div class="control-grid" />
      <div class="control-glow control-glow--primary" />
      <div class="control-glow control-glow--secondary" />
      <div class="control-orbit control-orbit--one" />
      <div class="control-orbit control-orbit--two" />
    </div>

    <section class="command-deck" aria-label="下载器筛选与操作">
      <div class="command-deck__signal">
        <span class="signal-beacon" aria-hidden="true" />
        <div>
          <strong>状态链路已建立</strong>
          <span>每 5 秒同步一次节点遥测</span>
        </div>
      </div>

      <div class="command-deck__actions">
        <el-input
          v-model="searchKeyword"
          class="control-search"
          placeholder="按别名筛选节点"
          aria-label="按下载器别名筛选"
          @input="handleSearchInput"
        >
          <template slot="prefix">
            <LucideIcon name="search" :size="16" :stroke-width="1.8" />
          </template>
          <template v-if="searchKeyword" slot="suffix">
            <button
              type="button"
              class="control-search__clear"
              aria-label="清空搜索"
              @mousedown.prevent
              @click="handleSearchClear"
            >
              <LucideIcon name="x" :size="14" :stroke-width="2" />
            </button>
          </template>
        </el-input>

        <span v-if="isSearching" class="search-result-tip" aria-live="polite">
          {{ filteredDownloaderList.length }} / {{ downloaderList.length }} 节点
        </span>

        <el-button
          class="control-action control-action--secondary"
          :disabled="listLoading"
          @click="handleRefresh"
        >
          <LucideIcon
            name="refresh-cw"
            :size="16"
            :stroke-width="1.8"
            :class="{'is-spinning': listLoading}"
          />
          <span>刷新</span>
        </el-button>
        <el-button class="control-action control-action--primary" type="primary" @click="handleAdd">
          <LucideIcon name="plus" :size="17" :stroke-width="2" />
          <span>接入节点</span>
        </el-button>
      </div>
    </section>

    <section class="nodes-section" aria-labelledby="downloader-node-heading">
      <div class="nodes-section__header">
        <div>
          <div class="section-index">01 / NODE MATRIX</div>
          <h2 id="downloader-node-heading">下载器节点</h2>
        </div>
        <div class="nodes-section__legend" aria-label="状态图例">
          <span><i class="legend-dot legend-dot--online" />在线 {{ onlineDownloaderCount }}</span>
          <span><i class="legend-dot legend-dot--offline" />离线 {{ offlineDownloaderCount }}</span>
          <span><i class="legend-dot legend-dot--pending" />待响应 {{ pendingDownloaderCount }}</span>
        </div>
      </div>

      <div v-if="listLoading && downloaderList.length === 0" class="node-skeleton-grid" aria-label="正在加载下载器">
        <div v-for="index in 3" :key="index" class="node-skeleton" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>

      <div
        v-else-if="isSearching && filteredDownloaderList.length === 0"
        class="empty-search-result"
        role="status"
      >
        <div class="empty-search-result__icon">
          <LucideIcon name="search-x" :size="30" :stroke-width="1.5" />
        </div>
        <div>
          <strong>没有匹配的节点</strong>
          <span>更换关键词，或清空筛选查看全部下载器。</span>
        </div>
        <button type="button" @click="handleSearchClear">
          清空筛选
          <LucideIcon name="x" :size="14" :stroke-width="2" />
        </button>
      </div>

      <transition-group v-else name="node-list" tag="div" class="downloader-grid">
        <downloader-card
          v-for="(item, index) in filteredDownloaderList"
          :key="safeGetId(item.info)"
          :index="index"
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

        <button key="add-downloader" type="button" class="downloader-card-add" @click="handleAdd">
          <span class="downloader-card-add__index">NEXT / NODE</span>
          <span class="downloader-card-add__icon">
            <LucideIcon name="plus" :size="24" :stroke-width="1.7" />
          </span>
          <span class="downloader-card-add__title">接入新的下载器</span>
          <span class="downloader-card-add__copy">配置连接、认证、路径与速率策略</span>
          <span class="downloader-card-add__action">
            开始配置
            <LucideIcon name="chevron-right" :size="15" :stroke-width="2" />
          </span>
        </button>
      </transition-group>
    </section>

    <downloader-settings-dialog
      :visible.sync="dialogVisible"
      :downloader="currentDownloader"
      @submit="handleSubmit"
    />
  </main>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { Message, MessageBox } from 'element-ui'
import { Route } from 'vue-router'
import DownloaderCard from './components/DownloaderCard.vue'
import DownloaderSettingsDialog from './components/DownloaderSettingsDialog.vue'
import {
  getList,
  getStatusAll,
  upDownloader,
  deleteDownloader,
  testConnection,
  syncDownloader
} from '@/api/downloader'
import {
  Downloader,
  DownloaderStatus,
  DownloaderCardData
} from './types'

interface DownloaderApiStatus {
  id?: string
  delay?: number
  uploadSpeed?: string
  downloadSpeed?: string
  downloadingCount?: number
  seedingCount?: number
  connectStatus?: string
}

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
  private pointerFrame: number | null = null
  private pointerClientX = 0
  private pointerClientY = 0

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

  get onlineDownloaderCount(): number {
    return this.downloaderList.filter(item => item.status.online === true).length
  }

  get offlineDownloaderCount(): number {
    return this.downloaderList.filter(item => item.status.online === false).length
  }

  get pendingDownloaderCount(): number {
    return this.downloaderList.filter(item => item.status.online === undefined).length
  }

  created() {
    this.getList()
    // 监听路由变化（移除 immediate: true，避免竞态条件）
    this.$watch('$route', (to: Route, from: Route) => {
      this.handleRouteChange(to, from)
    })
  }

  beforeDestroy() {
    // 组件销毁时清理轮询定时器
    this.continueGetStatus = false
    this.clearPollingTimer()
    if (this.searchDebounceTimer !== null) {
      clearTimeout(this.searchDebounceTimer)
      this.searchDebounceTimer = null
    }
    if (this.pointerFrame !== null) {
      cancelAnimationFrame(this.pointerFrame)
      this.pointerFrame = null
    }
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
  private mapApiStatusToFrontend(apiStatus: DownloaderApiStatus): DownloaderStatus {
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
  private safeGetId(info: Downloader | null | undefined): string {
    if (!info) {
      return ''
    }
    const id = info.id || info.downloaderId
    return id ? String(id) : ''
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

  private handlePointerMove(event: PointerEvent) {
    this.pointerClientX = event.clientX
    this.pointerClientY = event.clientY

    if (this.pointerFrame !== null) return

    this.pointerFrame = requestAnimationFrame(() => {
      this.pointerFrame = null
      const root = this.$el as HTMLElement
      const bounds = root.getBoundingClientRect()
      root.style.setProperty('--pointer-x', `${this.pointerClientX - bounds.left}px`)
      root.style.setProperty('--pointer-y', `${this.pointerClientY - bounds.top}px`)
    })
  }

  private resetPointerGlow() {
    const root = this.$el as HTMLElement
    root.style.setProperty('--pointer-x', '68%')
    root.style.setProperty('--pointer-y', '12%')
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

      const { code } = response

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

.downloader-control-room {
  --pointer-x: 68%;
  --pointer-y: 12%;
  --page-downloader-panel: rgba(255, 255, 255, 0.78);
  --page-downloader-line: rgba(var(--color-primary-rgb), 0.14);
  position: relative;
  isolation: isolate;
  min-height: calc(100vh - var(--navbar-height, 64px) - 48px);
  max-width: 1760px;
  margin: 0 auto;
  padding: clamp(22px, 2.6vw, 42px);
  overflow: hidden;
  border: 1px solid rgba(var(--color-primary-rgb), 0.12);
  border-radius: clamp(18px, 2vw, 30px);
  color: var(--color-text-primary);
  background:
    radial-gradient(circle at var(--pointer-x) var(--pointer-y), rgba(var(--color-primary-rgb), 0.13), transparent 24%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.94), rgba(var(--color-primary-rgb), 0.035) 52%, rgba(255, 255, 255, 0.86));
  box-shadow: 0 24px 90px rgba(15, 23, 42, 0.08);
}

.control-room-atmosphere,
.control-grid,
.control-glow,
.control-orbit {
  position: absolute;
  pointer-events: none;
}

.control-room-atmosphere {
  inset: 0;
  z-index: -1;
  overflow: hidden;
}

.control-grid {
  inset: 0;
  opacity: 0.48;
  background-image:
    linear-gradient(var(--page-downloader-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--page-downloader-line) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: linear-gradient(to bottom, black, transparent 82%);
}

.control-glow {
  width: 360px;
  height: 360px;
  border-radius: 50%;
  filter: blur(4px);

  &--primary {
    top: -210px;
    right: 8%;
    background: radial-gradient(circle, rgba(var(--color-primary-rgb), 0.2), transparent 68%);
  }

  &--secondary {
    bottom: -250px;
    left: 7%;
    background: radial-gradient(circle, rgba(59, 130, 246, 0.13), transparent 68%);
  }
}

.control-orbit {
  border: 1px solid rgba(var(--color-primary-rgb), 0.14);
  border-radius: 50%;

  &::before {
    content: '';
    position: absolute;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--color-primary);
    box-shadow: 0 0 18px rgba(var(--color-primary-rgb), 0.7);
  }

  &--one {
    top: -185px;
    right: -75px;
    width: 390px;
    height: 390px;
    animation: control-orbit 24s linear infinite;

    &::before {
      top: 47px;
      left: 58px;
    }
  }

  &--two {
    top: -112px;
    right: 18px;
    width: 240px;
    height: 240px;
    animation: control-orbit 18s linear reverse infinite;

    &::before {
      right: 21px;
      bottom: 57px;
    }
  }
}

.section-index {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.command-deck {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 30px;
  padding: 10px 12px 10px 16px;
  border: 1px solid rgba(var(--color-primary-rgb), 0.16);
  border-radius: 16px;
  background: var(--page-downloader-panel);
  box-shadow: 0 10px 35px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(18px);

  &__signal,
  &__actions {
    display: flex;
    align-items: center;
  }

  &__signal {
    min-width: 210px;
    gap: 11px;

    > div {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    strong {
      font-size: 12px;
      font-weight: 650;
    }

    span:not(.signal-beacon) {
      color: var(--color-text-tertiary);
      font-size: 10px;
    }
  }

  &__actions {
    min-width: 0;
    gap: 8px;
  }
}

.signal-beacon {
  position: relative;
  width: 10px;
  height: 10px;
  border: 2px solid var(--color-bg-primary);
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 0 4px var(--color-success-light);
}

.control-search {
  width: min(300px, 26vw);

  ::v-deep .el-input__inner {
    height: 36px;
    padding-left: 38px;
    padding-right: 34px;
    border-color: transparent;
    border-radius: 10px;
    background: var(--color-bg-secondary);
    font-size: 12px;

    &:focus {
      border-color: var(--color-primary);
      box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.1);
    }
  }

  ::v-deep .el-input__prefix,
  ::v-deep .el-input__suffix {
    display: flex;
    align-items: center;
    color: var(--color-text-tertiary);
  }

  &__clear {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    padding: 0;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--color-text-tertiary);
    cursor: pointer;

    &:hover,
    &:focus-visible {
      background: var(--color-bg-active);
      color: var(--color-text-primary);
      outline: none;
    }
  }
}

.search-result-tip {
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  font-size: 10px;
  white-space: nowrap;
}

.control-action {
  ::v-deep span {
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }

  &--secondary,
  &--primary {
    height: 36px;
    padding: 0 14px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
  }

  &--secondary {
    border-color: var(--color-border-primary);
    background: var(--color-bg-primary);
    color: var(--color-text-secondary);
  }

  &--primary {
    border-color: var(--color-primary);
    background: var(--color-primary);
    box-shadow: 0 9px 22px rgba(var(--color-primary-rgb), 0.22);
  }
}

.is-spinning {
  animation: spin 0.8s linear infinite;
}

.nodes-section {
  position: relative;
}

.nodes-section__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 14px;
  padding: 0 3px;

  h2 {
    margin: 5px 0 0;
    font-size: clamp(20px, 2vw, 28px);
    letter-spacing: -0.035em;
  }
}

.section-index {
  color: var(--color-primary);
}

.nodes-section__legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 14px;
  color: var(--color-text-tertiary);
  font-size: 10px;

  span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
}

.legend-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-quaternary);

  &--online {
    background: var(--color-success);
  }

  &--offline {
    background: var(--color-error);
  }

  &--pending {
    background: var(--color-warning);
  }
}

.downloader-grid,
.node-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.node-skeleton {
  min-height: 236px;
  padding: 24px;
  border: 1px solid var(--color-border-primary);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.7);
  overflow: hidden;

  span {
    display: block;
    height: 14px;
    margin-bottom: 18px;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--color-bg-tertiary), rgba(255, 255, 255, 0.9), var(--color-bg-tertiary));
    background-size: 220% 100%;
    animation: skeleton-shift 1.5s ease infinite;

    &:nth-child(1) {
      width: 42%;
      height: 22px;
    }

    &:nth-child(2) {
      width: 88%;
    }

    &:nth-child(3) {
      width: 68%;
    }
  }
}

.empty-search-result {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 15px;
  align-items: center;
  min-height: 150px;
  padding: 24px;
  border: 1px dashed rgba(var(--color-primary-rgb), 0.26);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.62);

  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 54px;
    height: 54px;
    border-radius: 15px;
    background: var(--color-bg-secondary);
    color: var(--color-primary);
  }

  > div:nth-child(2) {
    display: flex;
    flex-direction: column;
    gap: 4px;

    strong {
      font-size: 15px;
    }

    span {
      color: var(--color-text-tertiary);
      font-size: 12px;
    }
  }

  button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 11px;
    border: 0;
    border-radius: 9px;
    background: var(--color-bg-tertiary);
    color: var(--color-text-secondary);
    font-size: 11px;
    cursor: pointer;
  }
}

.downloader-card-add {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: auto auto auto;
  column-gap: 16px;
  align-items: center;
  min-height: 236px;
  padding: 24px;
  overflow: hidden;
  border: 1px dashed rgba(var(--color-primary-rgb), 0.34);
  border-radius: 18px;
  background: rgba(var(--color-primary-rgb), 0.025);
  color: var(--color-text-primary);
  text-align: left;
  cursor: pointer;
  transition: transform 420ms cubic-bezier(0.22, 1, 0.36, 1), border-color 250ms ease, background 250ms ease;

  &::after {
    content: '';
    position: absolute;
    right: -52px;
    bottom: -72px;
    width: 190px;
    height: 190px;
    border: 1px solid rgba(var(--color-primary-rgb), 0.14);
    border-radius: 50%;
    box-shadow: 0 0 0 28px rgba(var(--color-primary-rgb), 0.035), 0 0 0 58px rgba(var(--color-primary-rgb), 0.02);
  }

  &:hover,
  &:focus-visible {
    border-color: var(--color-primary);
    background: rgba(var(--color-primary-rgb), 0.06);
    transform: translateY(-3px);
    outline: none;
  }

  &__index {
    grid-column: 1 / -1;
    align-self: start;
    color: var(--color-primary);
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.15em;
  }

  &__icon {
    grid-row: 2 / 4;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 52px;
    height: 52px;
    border: 1px solid rgba(var(--color-primary-rgb), 0.24);
    border-radius: 15px;
    background: var(--color-bg-primary);
    color: var(--color-primary);
    box-shadow: 0 12px 30px rgba(var(--color-primary-rgb), 0.12);
  }

  &__title {
    align-self: end;
    font-size: 18px;
    font-weight: 650;
    letter-spacing: -0.025em;
  }

  &__copy {
    align-self: start;
    color: var(--color-text-tertiary);
    font-size: 11px;
  }

  &__action {
    z-index: 1;
    grid-column: 3;
    grid-row: 2 / 4;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--color-primary);
    font-size: 11px;
    font-weight: 650;
  }
}

.node-list-enter-active,
.node-list-leave-active {
  transition: opacity 320ms ease, transform 420ms cubic-bezier(0.22, 1, 0.36, 1);
}

.node-list-enter,
.node-list-leave-to {
  opacity: 0;
  transform: translateY(18px) scale(0.985);
}

@keyframes control-orbit {
  to { transform: rotate(360deg); }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes skeleton-shift {
  to { background-position: -120% 0; }
}

@media (max-width: 1180px) {
  .command-deck {
    align-items: stretch;
    flex-direction: column;

    &__actions {
      width: 100%;
    }
  }

  .control-search {
    flex: 1;
    width: auto;
  }
}

@media (max-width: 900px) {
  .downloader-grid,
  .node-skeleton-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .downloader-control-room {
    min-height: calc(100vh - var(--navbar-height, 64px) - 24px);
    margin: -12px;
    padding: 22px 14px;
    border-radius: 0;
  }

  .command-deck__actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .control-search {
    grid-column: 1 / -1;
  }

  .search-result-tip {
    display: none;
  }

  .control-action {
    width: 100%;
  }

  .nodes-section__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .nodes-section__legend {
    justify-content: flex-start;
  }

  .empty-search-result {
    grid-template-columns: auto 1fr;

    button {
      grid-column: 1 / -1;
      justify-self: start;
    }
  }

  .downloader-card-add {
    grid-template-columns: auto 1fr;

    &__action {
      grid-column: 2;
      grid-row: 4;
      margin-top: 14px;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .control-orbit,
  .control-kicker__pulse,
  .is-spinning,
  .node-skeleton span {
    animation: none !important;
  }

  .downloader-card-add,
  .node-list-enter-active,
  .node-list-leave-active {
    transition-duration: 0.01ms !important;
  }
}
</style>
