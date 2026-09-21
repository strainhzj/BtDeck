<template>
  <div class="tracker-test-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1><span class="page-icon">🧪</span>{{ $t('tracker.testTool.title') }}</h1>
      <p>{{ $t('tracker.testTool.description') }}</p>
    </div>

    <!-- 测试输入区域 -->
    <el-card class="test-input-card input-card">
      <div slot="header" class="card-header input">
        <span class="card-title">{{ $t('tracker.testTool.inputCardTitle') }}</span>
      </div>
      <el-form ref="testForm" :model="testForm" label-position="top">
        <el-form-item :label="$t('tracker.testTool.trackerAddr')" prop="tracker_host" required>
          <el-input
            v-model="testForm.tracker_host"
            :placeholder="$t('tracker.testTool.trackerAddrPlaceholder')"
            clearable
            class="form-input"
          />
        </el-form-item>
        <el-form-item :label="$t('tracker.testTool.msgLabel')" prop="msg" required>
          <el-input
            v-model="testForm.msg"
            type="textarea"
            :rows="5"
            :placeholder="$t('tracker.testTool.msgPlaceholder')"
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
              {{ $t('tracker.testTool.testButton') }}
            </el-button>
            <el-button
              @click="handleClear"
              class="btn-clear"
            >
              <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 6h18"></path>
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
              </svg>
              {{ $t('tracker.testTool.clearButton') }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 匹配结果区域 -->
    <transition name="result-fade">
      <el-card v-if="testResult" class="test-result-card result-card">
        <div slot="header" class="card-header result">
          <span class="card-title">{{ $t('tracker.testTool.resultCardTitle') }}</span>
        </div>

        <!-- 判断结果 -->
        <test-result-summary :result="testResult.result" />

        <!-- 匹配详情 -->
        <div class="match-details">
          <div class="detail-title">{{ $t('tracker.testTool.detailTitle') }}</div>

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
              :title="$t('tracker.testTool.unmatchedTitle')"
              type="warning"
              :description="testResult.unmatched_reason || $t('tracker.testTool.unmatchedFallback')"
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
            {{ $t('tracker.testTool.addToFailedPool') }}
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
            {{ $t('tracker.testTool.addToSuccessPool') }}
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
            {{ $t('tracker.testTool.copyResult') }}
          </el-button>
        </div>
      </el-card>
    </transition>

    <!-- 测试历史 -->
    <el-card class="test-history-card history-card">
      <div slot="header" class="card-header history">
        <span class="card-title">{{ $t('tracker.testTool.historyCardTitle') }}</span>
        <div class="history-toolbar">
          <el-input
            v-model="historySearchKeyword"
            :placeholder="$t('tracker.testTool.historySearch')"
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
            {{ $t('tracker.testTool.clearHistory') }}
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
        <el-table-column prop="tracker_host" :label="$t('tracker.testTool.colTracker')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="msg" :label="$t('tracker.testTool.colMsg')" min-width="250" show-overflow-tooltip />
        <el-table-column prop="result" :label="$t('tracker.testTool.colResult')" width="100" align="center">
          <template slot-scope="scope">
            <el-tag v-if="scope.row.result === 'success'" type="success" size="mini">
              {{ $t('tracker.testTool.resultSuccess') }}
            </el-tag>
            <el-tag v-else type="danger" size="mini">
              {{ $t('tracker.testTool.resultFailed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="timestamp" :label="$t('tracker.testTool.colTime')" width="160" align="center" />
        <el-table-column :label="$t('tracker.testTool.colActions')" width="100" align="center">
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
              {{ $t('tracker.testTool.retest') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页器 -->
      <div v-if="testHistory.length > 0" class="pagination-wrapper">
        <span class="pagination-info">{{ $t('tracker.testTool.totalRecords', {count: testHistory.length}) }}</span>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { testMatch, createKeyword } from '@/api/tracker'
import { TestMatchRequest, TestMatchResponse } from '@/api/tracker'
import {
  extractErrorMessage,
  parseJSON
} from '@/utils/tracker'
import { getLocale } from '@/i18n'
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

    const resultWord = this.testResult.result === 'success'
      ? this.$t('tracker.testTool.resultSuccess')
      : this.$t('tracker.testTool.resultFailed')
    return [
      {
        title: this.$t('tracker.testTool.timeline.step1Title'),
        description: this.$t('tracker.testTool.timeline.step1Desc', { length: this.testForm.msg.length })
      },
      {
        title: this.$t('tracker.testTool.timeline.step2Title'),
        description: this.$t('tracker.testTool.timeline.step2Desc', {
          count: this.testResult.matched_keywords?.length || 0,
          type: resultWord
        })
      },
      {
        title: this.$t('tracker.testTool.timeline.step3Title'),
        description: this.$t('tracker.testTool.timeline.step3Desc', { result: resultWord })
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
      this.$message.warning(this.$t('tracker.testTool.requireTracker'))
      return
    }
    if (!this.testForm.msg) {
      this.$message.warning(this.$t('tracker.testTool.requireMsg'))
      return
    }

    this.testing = true
    try {
      const res = await testMatch(this.testForm)
      if (res.code === '200') {
        this.testResult = res.data
        this.apiLogExpanded = false // 重置日志折叠状态
        this.addToHistory(res.data)
        this.$message.success(this.$t('tracker.testTool.testDone'))
      } else {
        this.$message.error(apiResponseMessage(res, this.$t('tracker.testTool.testFailed')))
      }
    } catch (error: any) {
      console.error('测试失败:', error)
      const errorMsg = extractErrorMessage(error, this.$t('tracker.testTool.testFailed'))
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
      // 双语 P6-3：历史时间列随界面语言本地化（原硬编码 zh-CN）
      timestamp: new Date().toLocaleString(getLocale() === 'en' ? 'en-US' : 'zh-CN', { hour12: false }),
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
      await this.$confirm(this.$t('tracker.testTool.clearHistoryConfirm'), this.$t('tracker.pools.dialog.notice'), {
        confirmButtonText: this.$t('tracker.pools.dialog.confirm'),
        cancelButtonText: this.$t('tracker.pools.dialog.cancel'),
        type: 'warning'
      })
      this.testHistory = []
      this.historySearchKeyword = ''
      localStorage.removeItem('tracker_test_history')
      this.$message.success(this.$t('tracker.testTool.clearedHistory'))
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
      const { value } = await this.$prompt(this.$t('tracker.testTool.promptDesc'), this.$t('tracker.testTool.promptFailedTitle'), {
        confirmButtonText: this.$t('tracker.pools.dialog.confirm'),
        cancelButtonText: this.$t('tracker.pools.dialog.cancel'),
        inputPlaceholder: this.$t('tracker.testTool.promptPlaceholderFailed')
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
      const { value } = await this.$prompt(this.$t('tracker.testTool.promptDesc'), this.$t('tracker.testTool.promptSuccessTitle'), {
        confirmButtonText: this.$t('tracker.pools.dialog.confirm'),
        cancelButtonText: this.$t('tracker.pools.dialog.cancel'),
        inputPlaceholder: this.$t('tracker.testTool.promptPlaceholderSuccess')
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
        this.$message.success(this.$t('tracker.testTool.addSuccess'))
      } else {
        this.$message.error(apiResponseMessage(res, this.$t('tracker.testTool.addFailed')))
      }
    } catch (error: any) {
      console.error('添加关键词失败:', error)
      const errorMsg = extractErrorMessage(error, this.$t('tracker.testTool.addFailed'))
      this.$message.error(errorMsg)
    }
  }

  // ========== 工具方法 ==========

  /**
   * 复制测试结果到剪贴板
   */
  private handleCopyResult() {
    if (!this.testResult) return

    const resultWord = this.testResult.result === 'success'
      ? this.$t('tracker.testTool.resultSuccess')
      : this.$t('tracker.testTool.resultFailed')
    const keywords = this.testResult.matched_keywords?.map(k => k.keyword).join(', ') || this.$t('tracker.testTool.none')
    const reason = this.testResult.unmatched_reason || this.$t('tracker.testTool.none')
    const text = [
      this.$t('tracker.testTool.copyResultLine', { result: resultWord }),
      this.$t('tracker.testTool.copyKeywordsLine', { keywords }),
      this.$t('tracker.testTool.copyReasonLine', { reason })
    ].join('\n')

    navigator.clipboard.writeText(text).then(() => {
      this.$message.success(this.$t('tracker.testTool.copied'))
    }).catch(() => {
      this.$message.error(this.$t('tracker.testTool.copyFailed'))
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
