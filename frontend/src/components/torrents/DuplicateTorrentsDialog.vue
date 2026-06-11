<template>
  <!-- 重复种子查询对话框 -->
  <div
    class="modal-overlay"
    :class="{active: visible}"
    @click.self="handleClose"
  >
    <div class="modal-dialog duplicate-torrents-dialog">
      <!-- 标题栏 -->
      <div class="modal-header">
        <h3 class="modal-title">🔍 重复种子查询</h3>
        <button class="modal-close" @click="handleClose">✕</button>
      </div>

      <!-- 内容区域 -->
      <div class="modal-body">
        <!-- 加载状态 -->
        <div v-if="loading" class="loading-container">
          <el-progress
            :percentage="100"
            :status="null"
            :stroke-width="12"
            :indeterminate="true"
          />
          <p class="loading-text">正在查询重复种子...</p>
        </div>

        <!-- 错误提示 -->
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
          show-icon
        />

        <!-- 结果列表 -->
        <div v-if="!loading && !error && torrentList.length > 0" class="table-container">
          <table class="result-table">
            <thead>
              <tr>
                <th>Hash值</th>
                <th>任务名称</th>
                <th>大小</th>
                <th>所在下载器</th>
                <th>状态</th>
                <th>保存路径</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(torrent, index) in torrentList" :key="index">
                <td class="hash-cell">
                  <code class="hash-code">{{ torrent.hash }}</code>
                </td>
                <td>{{ torrent.name }}</td>
                <td>{{ formatSize(torrent.size) }}</td>
                <td>
                  <span class="downloader-tag">
                    {{ torrent.downloaderName }}
                  </span>
                </td>
                <td>
                  <span :class="getStatusClass(torrent.status)">
                    {{ torrent.status }}
                  </span>
                </td>
                <td class="path-cell" :title="torrent.savePath">
                  {{ truncatePath(torrent.savePath) }}
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 统计信息 -->
          <div class="statistics-footer">
            <span>共找到 <strong>{{ duplicateCount }}</strong> 组重复种子</span>
            <span>总计 <strong>{{ torrentList.length }}</strong> 个任务</span>
          </div>
        </div>

        <!-- 空状态提示 -->
        <div v-if="!loading && !error && torrentList.length === 0" class="empty-state">
          <div class="empty-icon">✅</div>
          <div class="empty-text">未发现重复种子</div>
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="modal-footer">
        <div class="modal-footer-left"></div>
        <div class="modal-footer-right">
          <button class="btn-secondary" @click="handleClose">关闭</button>
          <button class="btn-primary" @click="handleRefresh">
            刷新
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { getDuplicateTorrents } from '@/api/torrents'

@Component({
  name: 'DuplicateTorrentsDialog'
})
export default class DuplicateTorrentsDialog extends Vue {
  @Prop({ type: Boolean, default: false }) readonly visible!: boolean

  // 状态管理
  private loading = false
  private error = ''
  private torrentList: any[] = []
  private duplicateCount = 0

  @Watch('visible')
  onVisibleChange(val: boolean) {
    if (val) {
      this.fetchDuplicates()
    }
  }

  /**
   * 查询重复种子
   */
  private async fetchDuplicates() {
    try {
      this.loading = true
      this.error = ''

      const response = await getDuplicateTorrents({})

      if (response.code === '200') {
        this.torrentList = response.data.list || []
        // total是重复组数,list是所有重复种子
        this.duplicateCount = response.data.total || 0
      } else {
        this.error = response.msg || '查询失败'
        this.torrentList = []
        this.duplicateCount = 0
      }
    } catch (error: any) {
      const errorMessage = error?.response?.data?.msg ?? error?.message ?? '查询失败'
      this.error = errorMessage
      this.torrentList = []
      this.duplicateCount = 0
    } finally {
      this.loading = false
    }
  }

  /**
   * 刷新数据
   */
  private handleRefresh() {
    this.fetchDuplicates()
  }

  /**
   * 关闭对话框
   */
  private handleClose() {
    this.$emit('close')
  }

  /**
   * 格式化文件大小
   */
  private formatSize(bytes: number | null | undefined): string {
    if (bytes === null || bytes === undefined || bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
  }

  /**
   * 截断路径显示
   */
  private truncatePath(path: string): string {
    if (!path) return ''
    const maxLength = 40
    return path.length > maxLength ? path.substring(0, maxLength) + '...' : path
  }

  /**
   * 获取状态样式类
   */
  private getStatusClass(status: string): string {
    const statusMap: Record<string, string> = {
      seeding: 'status-seeding',
      downloading: 'status-downloading',
      paused: 'status-paused',
      error: 'status-error'
    }
    return statusMap[status] || 'status-default'
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/torrent-theme.scss';

.duplicate-torrents-dialog {
  max-width: 1200px;
}

// 加载状态
.loading-container {
  padding: 40px 20px;
  text-align: center;

  .loading-text {
    margin-top: 16px;
    font-size: 14px;
    color: var(--color-text-secondary);
  }
}

// 表格容器
.table-container {
  margin-top: 20px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.result-table {
  width: 100%;
  border-collapse: collapse;

  thead {
    background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
    color: white;

    th {
      padding: 12px 16px;
      text-align: left;
      font-weight: var(--font-weight-semibold);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
  }

  tbody tr {
    border-bottom: 1px solid var(--color-border-primary);
    transition: background-color var(--transition-base) ease;

    &:hover {
      background: var(--color-bg-hover);
    }

    &:last-child {
      border-bottom: none;
    }

    td {
      padding: 12px 16px;
      font-size: 14px;
      color: var(--color-text-primary);
    }
  }

  .hash-cell {
    font-family: 'Courier New', monospace;
  }

  .hash-code {
    background: var(--color-bg-tertiary);
    padding: 4px 8px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--color-text-secondary);
  }

  .downloader-tag {
    display: inline-block;
    padding: 4px 10px;
    background: rgba(var(--theme-primary-rgb), 0.1);
    color: var(--color-primary);
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: var(--font-weight-medium);
  }

  .path-cell {
    max-width: 300px;
    font-size: 12px;
    color: var(--color-text-secondary);
  }

  // 状态样式
  .status-seeding {
    color: var(--theme-success);
    font-weight: var(--font-weight-medium);
  }

  .status-downloading {
    color: var(--theme-primary);
    font-weight: var(--font-weight-medium);
  }

  .status-paused {
    color: var(--theme-warning);
    font-weight: var(--font-weight-medium);
  }

  .status-error {
    color: var(--theme-error);
    font-weight: var(--font-weight-medium);
  }

  .status-default {
    color: var(--color-text-secondary);
  }
}

// 统计信息
.statistics-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-primary);
  font-size: 14px;
  color: var(--color-text-secondary);

  strong {
    color: var(--color-primary);
    font-weight: var(--font-weight-semibold);
  }
}

// 空状态
.empty-state {
  text-align: center;
  padding: 60px 20px;

  .empty-icon {
    font-size: 64px;
    margin-bottom: 16px;
  }

  .empty-text {
    font-size: 18px;
    color: var(--color-text-secondary);
    font-weight: var(--font-weight-medium);
  }
}

// 响应式设计
@media screen and (max-width: 1280px) {
  .result-table {
    .path-cell {
      max-width: 200px;
    }
  }
}

@media screen and (max-width: 768px) {
  .result-table {
    thead {
      display: none;
    }

    tbody {
      display: block;

      tr {
        display: block;
        margin-bottom: 16px;
        border: 1px solid var(--color-border-primary);
        border-radius: var(--radius-md);
        padding: 16px;

        td {
          display: block;
          padding: 8px 0;
          border: none;

          &::before {
            content: attr(data-label);
            font-weight: var(--font-weight-semibold);
            color: var(--color-text-secondary);
            display: inline-block;
            width: 100px;
            margin-right: 12px;
          }
        }
      }
    }
  }

  .statistics-footer {
    flex-direction: column;
    gap: 8px;
    text-align: center;
  }
}
</style>
