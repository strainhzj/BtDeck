<template>
  <div class="tracker-test-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1><span class="page-icon">🧪</span>Tracker判断测试工具</h1>
      <p>测试tracker消息的匹配结果，帮助理解判断逻辑</p>
    </div>

    <!-- 测试输入区域 -->
    <el-card class="test-input-card input-card">
      <div slot="header" class="card-header input">
        <span class="card-title">输入测试消息</span>
      </div>
      <el-form ref="testForm" :model="testForm" label-position="top">
        <el-form-item label="Tracker地址" prop="tracker_host" required>
          <el-input
            v-model="testForm.tracker_host"
            placeholder="例如: http://tracker.example.com:8080"
            clearable
            class="form-input"
          />
        </el-form-item>
        <el-form-item label="返回消息" prop="msg" required>
          <el-input
            v-model="testForm.msg"
            type="textarea"
            :rows="5"
            placeholder="请输入tracker返回的消息内容..."
            maxlength="1000"
            show-word-limit
            class="form-textarea"
          />
        </el-form-item>
        <el-form-item>
          <div class="button-group">
            <el-button
              type="primary"
              :loading="testing"
              @click="handleTest"
              class="btn-test"
            >
              <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"></circle>
                <path d="M21 21l-4.35-4.35"></path>
              </svg>
              测试匹配
            </el-button>
            <el-button
              @click="handleClear"
              class="btn-clear"
            >
              <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 6h18"></path>
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
              </svg>
              清空
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 匹配结果区域 -->
    <transition name="result-fade">
      <el-card v-if="testResult" class="test-result-card result-card">
        <div slot="header" class="card-header result">
          <span class="card-title">匹配结果</span>
        </div>

        <!-- 判断结果 -->
        <test-result-summary :result="testResult.result" />

        <!-- 匹配详情 -->
        <div class="match-details">
          <div class="detail-title">匹配详情：</div>

          <!-- 匹配到的关键词 -->
          <div v-if="testResult.matched_keywords && testResult.matched_keywords.length > 0" class="matched-keywords">
            <keyword-card
              v-for="(keyword, index) in testResult.matched_keywords"
              :key="index"
              :keyword="keyword"
            />
          </div>

          <!-- 未匹配原因 -->
          <div v-else class="unmatched-reason">
            <el-alert
              title="未匹配到关键词"
              type="warning"
              :description="testResult.unmatched_reason || '该消息不包含任何成功或失败关键词'"
              :closable="false"
              show-icon
            />
          </div>
        </div>

        <!-- 匹配时间线 -->
        <match-timeline :steps="timelineSteps" />

        <!-- API日志查看器 -->
        <api-log-viewer
          v-model="apiLogExpanded"
          :log-data="apiLogData"
        />

        <!-- 操作按钮 -->
        <div class="result-actions">
          <el-button
            v-if="testResult.result === 'failed' && (!testResult.matched_keywords || testResult.matched_keywords.length === 0)"
            type="danger"
            size="small"
            @click="handleAddToFailureKeywords"
            class="action-btn"
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            添加到失败关键词池
          </el-button>
          <el-button
            v-if="testResult.result === 'success' && (!testResult.matched_keywords || testResult.matched_keywords.length === 0)"
            type="success"
            size="small"
            @click="handleAddToSuccessKeywords"
            class="action-btn"
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            添加到成功关键词池
          </el-button>
          <el-button
            type="info"
            size="small"
            @click="handleCopyResult"
            class="action-btn"
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"></path>
            </svg>
            复制结果
          </el-button>
        </div>
      </el-card>
    </transition>

    <!-- 测试历史 -->
    <el-card class="test-history-card history-card">
      <div slot="header" class="card-header history">
        <span class="card-title">测试历史</span>
        <div class="history-toolbar">
          <el-input
            v-model="historySearchKeyword"
            placeholder="搜索历史记录..."
            prefix-icon="el-icon-search"
            size="small"
            class="history-search"
            clearable
          />
          <el-button
            type="text"
            icon="el-icon-delete"
            @click="handleClearHistory"
            class="clear-history-btn"
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
            </svg>
            清空历史
          </el-button>
        </div>
      </div>

      <el-table
        :data="filteredHistory"
        stripe
        size="small"
        max-height="400"
        class="history-table"
      >
        <el-table-column prop="tracker_host" label="Tracker地址" min-width="200" show-overflow-tooltip />
        <el-table-column prop="msg" label="消息内容" min-width="250" show-overflow-tooltip />
        <el-table-column prop="result" label="结果" width="100" align="center">
          <template slot-scope="scope">
            <el-tag v-if="scope.row.result === 'success'" type="success" size="mini">
              成功
            </el-tag>
            <el-tag v-else type="danger" size="mini">
              失败
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="timestamp" label="测试时间" width="160" align="center" />
        <el-table-column label="操作" width="100" align="center">
          <template slot-scope="scope">
            <el-button
              size="mini"
              type="text"
              @click="handleRetest(scope.row)"
              class="retest-btn"
            >
              <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"></polyline>
                <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"></path>
              </svg>
              重新测试
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页器 -->
      <div v-if="testHistory.length > 0" class="pagination-wrapper">
        <span class="pagination-info">共 {{ testHistory.length }} 条记录</span>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { testMatch, createKeyword } from '@/api/tracker'
import { TestMatchRequest, TestMatchResponse } from '@/api/tracker'
import {
  getLanguageLabel,
  extractErrorMessage,
  parseJSON
} from '@/utils/tracker'
import TestResultSummary from './components/TestResultSummary.vue'
import KeywordCard from './components/KeywordCard.vue'
import MatchTimeline from './components/MatchTimeline.vue'
import ApiLogViewer from './components/ApiLogViewer.vue'

/**
 * 测试配置常量
 */
const TEST_CONFIG = {
  MAX_HISTORY: 20,        // 最大历史记录数
  DEFAULT_PRIORITY: 100   // 默认关键词优先级
}

/**
 * 测试历史记录项接口
 */
interface TestHistoryItem {
  tracker_host: string
  msg: string
  result: 'success' | 'failed'
  timestamp: string
  response?: TestMatchResponse
}

@Component({
  name: 'TrackerTest',
  components: {
    TestResultSummary,
    KeywordCard,
    MatchTimeline,
    ApiLogViewer
  }
})
export default class TrackerTest extends Vue {
  // ========== 数据属性 ==========

  /** 测试表单数据 */
  private testForm: TestMatchRequest = {
    tracker_host: '',
    msg: ''
  }

  /** 测试加载状态 */
  private testing = false
  /** 测试结果数据 */
  private testResult: TestMatchResponse | null = null
  /** 测试历史记录 */
  private testHistory: TestHistoryItem[] = []
  /** 历史搜索关键词 */
  private historySearchKeyword = ''
  /** API日志展开状态 */
  private apiLogExpanded = false

  // ========== 计算属性 ==========

  /**
   * 过滤后的历史记录
   */
  get filteredHistory(): TestHistoryItem[] {
    if (!this.historySearchKeyword) {
      return this.testHistory
    }
    const keyword = this.historySearchKeyword.toLowerCase()
    return this.testHistory.filter(item =>
      item.tracker_host.toLowerCase().includes(keyword) ||
      item.msg.toLowerCase().includes(keyword)
    )
  }

  /**
   * 格式化的API日志（带JSON语法高亮）
   */
  get apiLogData(): any {
    if (!this.testResult) return {}

    return {
      request: {
        tracker_host: this.testForm.tracker_host,
        msg: this.testForm.msg
      },
      response: this.testResult
    }
  }

  /**
   * 时间线步骤数据
   */
  get timelineSteps(): Array<{title: string, description: string}> {
    if (!this.testResult) return []

    return [
      {
        title: '接收消息',
        description: `消息长度: <span class="highlight">${this.testForm.msg.length} bytes</span>`
      },
      {
        title: '关键词匹配',
        description: `匹配到 <span class="highlight">${this.testResult.matched_keywords?.length || 0} 个</span>${this.testResult.result === 'success' ? '成功' : '失败'}关键词`
      },
      {
        title: '判定结果',
        description: `最终判定: <span class="highlight">${this.testResult.result === 'success' ? '成功' : '失败'}</span>`
      }
    ]
  }

  // ========== 生命周期 ==========

  /** 组件挂载后加载测试历史 */
  mounted() {
    this.loadTestHistory()
  }

  // ========== 测试方法 ==========

  /**
   * 执行tracker消息匹配测试
   * 验证输入后调用API进行匹配判断
   */
  private async handleTest() {
    if (!this.testForm.tracker_host) {
      this.$message.warning('请输入tracker地址')
      return
    }
    if (!this.testForm.msg) {
      this.$message.warning('请输入消息内容')
      return
    }

    this.testing = true
    try {
      const res = await testMatch(this.testForm)
      if (res.code === '200') {
        this.testResult = res.data
        this.apiLogExpanded = false // 重置日志折叠状态
        this.addToHistory(res.data)
        this.$message.success('测试完成')
      } else {
        this.$message.error(res.msg || '测试失败')
      }
    } catch (error: any) {
      console.error('测试失败:', error)
      const errorMsg = extractErrorMessage(error, '测试失败')
      this.$message.error(errorMsg)
    } finally {
      this.testing = false
    }
  }

  /**
   * 清空测试表单和结果
   */
  private handleClear() {
    this.testForm = {
      tracker_host: '',
      msg: ''
    }
    this.testResult = null
    this.apiLogExpanded = false
  }

  // ========== 历史记录管理 ==========

  /**
   * 添加测试结果到历史记录
   * @param response - API响应数据
   */
  private addToHistory(response: TestMatchResponse) {
    const item: TestHistoryItem = {
      tracker_host: this.testForm.tracker_host,
      msg: this.testForm.msg,
      result: response.result,
      timestamp: new Date().toLocaleString('zh-CN'),
      response: response
    }

    this.testHistory.unshift(item)
    // 限制历史记录数量
    if (this.testHistory.length > TEST_CONFIG.MAX_HISTORY) {
      this.testHistory = this.testHistory.slice(0, TEST_CONFIG.MAX_HISTORY)
    }

    this.saveTestHistory()
  }

  /**
   * 保存测试历史到本地存储
   */
  private saveTestHistory() {
    try {
      const json = JSON.stringify(this.testHistory)
      localStorage.setItem('tracker_test_history', json)
    } catch (error: any) {
      console.error('保存历史记录失败:', error)
    }
  }

  /**
   * 从本地存储加载测试历史
   */
  private loadTestHistory() {
    try {
      const saved = localStorage.getItem('tracker_test_history')
      if (saved) {
        this.testHistory = parseJSON<TestHistoryItem[]>(saved)
      }
    } catch (error: any) {
      console.error('加载历史记录失败:', error)
    }
  }

  /**
   * 清空测试历史记录
   */
  private async handleClearHistory() {
    try {
      await this.$confirm('确定要清空测试历史吗?', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
      this.testHistory = []
      this.historySearchKeyword = ''
      localStorage.removeItem('tracker_test_history')
      this.$message.success('已清空历史记录')
    } catch (error) {}
  }

  /**
   * 使用历史记录重新测试
   * @param item - 历史记录项
   */
  private handleRetest(item: TestHistoryItem) {
    this.testForm = {
      tracker_host: item.tracker_host,
      msg: item.msg
    }
    this.handleTest()
  }

  // ========== 关键词操作方法 ==========

  /**
   * 添加到失败关键词池
   * 通过prompt输入框获取关键词说明
   */
  private async handleAddToFailureKeywords() {
    try {
      const { value } = await this.$prompt('请输入关键词说明（可选）', '添加到失败关键词池', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '例如: 超时错误'
      })
      this.addKeyword('failure', value)
    } catch (error) {}
  }

  /**
   * 添加到成功关键词池
   * 通过prompt输入框获取关键词说明
   */
  private async handleAddToSuccessKeywords() {
    try {
      const { value } = await this.$prompt('请输入关键词说明（可选）', '添加到成功关键词池', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '例如: 下载成功'
      })
      this.addKeyword('success', value)
    } catch (error) {}
  }

  /**
   * 添加关键词到关键词池
   * @param keywordType - 关键词类型 ('success' | 'failure')
   * @param description - 关键词说明（可选）
   */
  private async addKeyword(keywordType: 'success' | 'failure', description?: string) {
    try {
      const res = await createKeyword({
        keyword_type: keywordType,
        keyword: this.testForm.msg,
        priority: TEST_CONFIG.DEFAULT_PRIORITY,
        enabled: true,
        description: description || undefined
      })

      if (res.code === '200') {
        this.$message.success('添加成功')
      } else {
        this.$message.error(res.msg || '添加失败')
      }
    } catch (error: any) {
      console.error('添加关键词失败:', error)
      const errorMsg = extractErrorMessage(error, '添加失败')
      this.$message.error(errorMsg)
    }
  }

  // ========== 工具方法 ==========

  /**
   * 复制测试结果到剪贴板
   */
  private handleCopyResult() {
    if (!this.testResult) return

    const text = `判断结果: ${this.testResult.result === 'success' ? '成功' : '失败'}
匹配关键词: ${this.testResult.matched_keywords?.map(k => k.keyword).join(', ') || '无'}
未匹配原因: ${this.testResult.unmatched_reason || '无'}`

    navigator.clipboard.writeText(text).then(() => {
      this.$message.success('已复制到剪贴板')
    }).catch(() => {
      this.$message.error('复制失败')
    })
  }
}
</script>

<style lang="scss" scoped>
.tracker-test-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;

  // 页面标题
  .page-header {
    margin-bottom: 24px;

    h1 {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 8px 0;
      font-size: 24px;
      font-weight: 600;
      color: #303133;

      .page-icon {
        font-size: 28px;
      }
    }

    p {
      margin: 0;
      font-size: 14px;
      color: #909399;
    }
  }

  // 卡片通用样式
  .el-card {
    margin-bottom: 24px;
    border-radius: 8px;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
    overflow: hidden;
    transition: box-shadow 0.3s ease;

    &:hover {
      box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.12);
    }

    ::v-deep .el-card__header {
      padding: 16px 24px;
      border-bottom: 1px solid #ebeef5;
      background: linear-gradient(to bottom, #fafafa, #ffffff);
    }

    ::v-deep .el-card__body {
      padding: 24px;
    }
  }

  // 卡片标题样式
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .card-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 600;
      color: #303133;

      &::before {
        content: '📝';
        font-size: 18px;
      }
    }

    &.input .card-title::before {
      content: '📝';
    }

    &.result .card-title::before {
      content: '📊';
    }

    &.history .card-title::before {
      content: '📖';
    }
  }

  // 输入卡片
  .input-card {
    .button-group {
      display: flex;
      gap: 8px;

      .btn-test,
      .btn-clear {
        display: inline-flex;
        align-items: center;
        gap: 6px;

        .btn-icon {
          width: 16px;
          height: 16px;
        }
      }
    }

    // 表单项样式优化
    ::v-deep .el-form-item__label {
      font-weight: 500;
      color: #606266;

      &::before {
        color: #f56c6c;
        margin-right: 4px;
      }
    }

    ::v-deep .el-input__inner {
      border-radius: 4px;
      transition: all 0.3s ease;

      &:focus {
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
      }
    }

    ::v-deep .el-textarea__inner {
      border-radius: 4px;
      transition: all 0.3s ease;

      &:focus {
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
      }
    }
  }

  // 结果卡片动画
  .result-fade-enter-active {
    animation: fadeInUp 0.3s ease-out;
  }

  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  // 结果卡片
  .result-card {
    // 匹配详情
    .match-details {
      margin-bottom: 24px;

      .detail-title {
        font-size: 15px;
        font-weight: 600;
        color: #303133;
        margin-bottom: 16px;
      }

      .matched-keywords {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .unmatched-reason {
        padding: 16px;
      }
    }

    // 操作按钮
    .result-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding-top: 16px;
      border-top: 1px solid #ebeef5;

      .action-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;

        .btn-icon {
          width: 14px;
          height: 14px;
        }
      }
    }
  }

  // 历史记录卡片
  .history-card {
    .history-toolbar {
      display: flex;
      align-items: center;
      gap: 12px;

      .history-search {
        width: 250px;
      }

      .clear-history-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 14px;

        .btn-icon {
          width: 14px;
          height: 14px;
        }
      }
    }

    .pagination-wrapper {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      padding: 16px 0;

      .pagination-info {
        font-size: 14px;
        color: #909399;
      }
    }

    // 表格样式优化
    ::v-deep .history-table {
      border-radius: 4px;

      .el-table__header-wrapper {
        th {
          background: #f5f7fa;
          font-weight: 600;
          color: #606266;
        }
      }

      .retest-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;

        .btn-icon {
          width: 14px;
          height: 14px;
        }
      }
    }
  }

  // 表格样式覆盖
  ::v-deep .el-table {
    border-radius: 4px;

    &.el-table--striped .el-table__body tr.el-table__row--striped td {
      background: #fafafa;
    }

    th {
      background: #f5f7fa;
      font-weight: 600;
      color: #606266;
    }
  }
}
</style>
