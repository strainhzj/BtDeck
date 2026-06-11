<template>
  <div class="tracker-detail-card">
    <div class="tracker-detail-header">
      <div class="header-left">
        <i class="el-icon-location"></i>
        <span>Tracker详情</span>
      </div>
    </div>
    <div class="tracker-detail-content">
      <!-- Tracker列表表格 -->
      <el-table
        v-loading="loading"
        :data="trackerTableData"
        border
        fit
        stripe
        style="width: 100%"
        :show-header="true"
        :empty-text="'暂无Tracker数据'"
      >
        <el-table-column
          label="Tracker名称"
          min-width="120"
          show-overflow-tooltip
        >
          <template slot-scope="{row}">
            <span>{{ row.trackerName || '未知' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          label="Tracker地址"
          min-width="200"
          show-overflow-tooltip
        >
          <template slot-scope="{row}">
            <span :title="row.trackerUrl">{{ row.trackerUrl || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          label="Announce状态"
          width="100"
          align="center"
        >
          <template slot-scope="{row}">
            <el-tag
              :type="getTrackerTagType(row.lastAnnounceSucceeded)"
              size="mini"
            >
              {{ getTrackerStatusText(row.lastAnnounceSucceeded) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          label="Announce信息"
          min-width="150"
          show-overflow-tooltip
        >
          <template slot-scope="{row}">
            <span :title="row.lastAnnounceMsg">{{ row.lastAnnounceMsg || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          label="Tracker状态"
          width="100"
          align="center"
        >
          <template slot-scope="{row}">
            <el-tag
              :type="getTrackerStatusTagType(row.trackerStatus)"
              size="mini"
            >
              {{ getTrackerStatusDisplayText(row.trackerStatus) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          label="Scrape状态"
          width="100"
          align="center"
        >
          <template slot-scope="{row}">
            <el-tag
              :type="getTrackerTagType(row.lastScrapeSucceeded)"
              size="mini"
            >
              {{ getTrackerStatusText(row.lastScrapeSucceeded) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          label="Scrape信息"
          min-width="150"
          show-overflow-tooltip
        >
          <template slot-scope="{row}">
            <span :title="row.lastScrapeMsg">{{ row.lastScrapeMsg || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 浮动关闭按钮 -->
    <div class="floating-close-button" @click="handleClose" title="关闭">
      <i class="el-icon-close"></i>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import { TrackerInfo } from '@/api/torrents'

@Component({
  name: 'TrackerDetailCard'
})
export default class TrackerDetailCard extends Vue {
  @Prop({ type: Array, default: () => [] }) trackerInfo!: TrackerInfo[]
  @Prop({ type: Boolean, default: false }) loading!: boolean

  // 计算属性：转换数据格式为表格所需格式
  get trackerTableData() {
    if (!this.trackerInfo) {
      return []
    }

    // 如果已经是数组，直接使用
    if (Array.isArray(this.trackerInfo)) {
      return this.trackerInfo.map(tracker => this.normalizeTrackerData(tracker))
    }

    // 如果是对象，转换为数组
    if (typeof this.trackerInfo === 'object') {
      return [this.trackerInfo].map(tracker => this.normalizeTrackerData(tracker))
    }

    return []
  }

  // 标准化tracker数据字段
  private normalizeTrackerData(tracker: any) {
    return {
      trackerName: tracker.trackerName || tracker.tracker_name || '未知',
      trackerUrl: tracker.trackerUrl || tracker.tracker_url || '',
      // 原有announce/scrape状态（保持不变，不被tracker状态覆盖）
      lastAnnounceSucceeded: tracker.lastAnnounceSucceeded || tracker.last_announce_succeeded || '',
      lastAnnounceMsg: tracker.lastAnnounceMsg || tracker.last_announce_msg || '',
      lastScrapeSucceeded: tracker.lastScrapeSucceeded || tracker.last_scrape_succeeded || '',
      lastScrapeMsg: tracker.lastScrapeMsg || tracker.last_scrape_msg || '',
      // 新增：tracker状态（根据关键词看板判断，独立于announce/scrape状态）
      trackerStatus: tracker.trackerStatus || tracker.tracker_status || 'unknown',
      // 新增字段
      trackerHost: tracker.trackerHost || tracker.tracker_host || '',
      seederCount: tracker.seederCount ?? tracker.seeder_count ?? null,
      leecherCount: tracker.leecherCount ?? tracker.leecher_count ?? null,
      downloadCount: tracker.downloadCount ?? tracker.download_count ?? null
    }
  }

  /**
   * 根据tracker状态返回Element UI的tag类型
   *
   * 状态分类（基于 tracker_status.py 枚举的中文值）：
   * - 成功状态：工作中 → success（绿色✓）
   * - 失败状态：工作失败、已禁用、超时、已清除 → danger（红色✗）
   * - 中性状态：未联系、发送中 → info（灰色，无特殊标记）
   *
   * @param status tracker状态中文文本
   * @returns Element UI的tag类型
   */
  getTrackerTagType(status: string | number): string {
    // 空值处理
    if (status === null || status === undefined || status === '') {
      return 'info'
    }

    // 转换为字符串
    const statusStr = String(status)

    // 成功状态：工作中
    if (statusStr === '工作中') {
      return 'success'
    }

    // 失败状态：工作失败、已禁用、超时、已清除
    if (['工作失败', '已禁用', '超时', '已清除'].includes(statusStr)) {
      return 'danger'
    }

    // 中性状态：未联系、发送中 → 无特殊标记
    return 'info'
  }

  /**
   * 根据tracker状态返回可读文本
   * 后端已返回中文枚举，直接显示即可
   *
   * @param status tracker状态中文文本
   * @returns 可读文本
   */
  getTrackerStatusText(status: string | number): string {
    // 空值处理
    if (status === null || status === undefined || status === '') {
      return '未知'
    }

    // 直接返回后端传来的中文状态
    return String(status)
  }

  /**
   * 根据tracker状态（关键词看板判断）返回Element UI的tag类型
   * 状态值: normal/error/unknown
   */
  getTrackerStatusTagType(status: string): string {
    if (!status || status === 'unknown') {
      return 'info'
    }

    // 记录意外的状态值（开发环境）
    if (process.env.NODE_ENV === 'development') {
      if (!['normal', 'error', 'unknown'].includes(status)) {
        console.warn(`意外的tracker状态值: ${status}`)
      }
    }

    switch (status) {
      case 'normal':
        return 'success'
      case 'error':
        return 'danger'
      default:
        return 'info'
    }
  }

  /**
   * 根据tracker状态（关键词看板判断）返回可读文本
   * 状态值: normal/error/unknown
   */
  getTrackerStatusDisplayText(status: string): string {
    if (!status) {
      return '未知'
    }

    switch (status) {
      case 'normal':
        return '正常'
      case 'error':
        return '失败'
      case 'unknown':
      default:
        return '未知'
    }
  }

  // 关闭卡片
  handleClose() {
    this.$emit('close')
  }
}
</script>

<style scoped>
.tracker-detail-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  margin: 10px 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: relative;
}

.tracker-detail-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
  color: #303133;
  font-weight: 600;
  border-radius: 6px 6px 0 0;
}

.tracker-detail-header i {
  margin-right: 8px;
  font-size: 16px;
  color: #409eff;
}

.tracker-detail-content {
  padding: 16px;
  max-height: 284px; /* 最大高度300px - header(16px) - padding */
  overflow-y: auto;
}

/* 浮动关闭按钮 */
.floating-close-button {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 24px;
  height: 24px;
  background: #f56c6c;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(245, 108, 108, 0.3);
}

.floating-close-button:hover {
  background: #f78989;
  transform: scale(1.1);
  box-shadow: 0 4px 8px rgba(245, 108, 108, 0.4);
}

.floating-close-button i {
  font-size: 12px;
  margin: 0;
}

/* Element UI表格样式适配 */
.tracker-detail-content .el-table {
  border-radius: 4px;
  overflow: hidden;
}

.tracker-detail-content .el-table th {
  background: #fafafa;
  color: #606266;
  font-weight: 600;
  border-bottom: 1px solid #ebeef5;
}

.tracker-detail-content .el-table td {
  border-bottom: 1px solid #ebeef5;
}

.tracker-detail-content .el-table--border::after,
.tracker-detail-content .el-table--group::after,
.tracker-detail-content .el-table::before {
  background-color: #ebeef5;
}

/* 状态标签样式 */
.tracker-detail-content .el-tag--mini {
  font-size: 11px;
  padding: 1px 6px;
  height: 18px;
  line-height: 16px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .tracker-detail-content .el-table {
    font-size: 12px;
  }

  .floating-close-button {
    width: 28px;
    height: 28px;
    top: 8px;
    right: 8px;
  }

  .floating-close-button i {
    font-size: 14px;
  }
}

/* 空数据状态样式 */
.tracker-detail-content .el-table__empty-block {
  min-height: 120px;
}

.tracker-detail-content .el-table__empty-text {
  color: #909399;
  font-size: 14px;
}

/* Loading状态优化 */
.tracker-detail-content .el-loading-mask {
  border-radius: 4px;
}
</style>