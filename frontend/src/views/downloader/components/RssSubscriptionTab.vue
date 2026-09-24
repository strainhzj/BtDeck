<template>
  <div class="rss-subscription-tab">
    <!-- 新增模式提示 -->
    <div v-if="!downloader" class="empty-state">
      <LucideIcon class="empty-icon" name="lock-keyhole" :size="42" :stroke-width="1.4" />
      <h3>{{ $t('downloader.tabs.needBasicTitle') }}</h3>
      <p>{{ $t('downloader.tabs.needBasicRss') }}</p>
    </div>

    <!-- 订阅管理内容 -->
    <div v-else class="rss-content">
      <!-- 工具栏 -->
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button size="small" :disabled="loading" @click="loadFeeds">
            <LucideIcon name="rotate-ccw" :size="13" />
            {{ $t('downloader.rss.refreshList') }}
          </el-button>
        </div>
        <div class="toolbar-right">
          <el-button type="primary" size="small" @click="openCreateDialog">
            <LucideIcon name="plus" :size="14" />
            {{ $t('downloader.rss.addFeed') }}
          </el-button>
        </div>
      </div>

      <!-- 订阅源表格 -->
      <div v-loading="loading" class="feed-table" :element-loading-text="$t('downloader.rss.loading')">
        <template v-if="feeds.length > 0">
          <el-table :data="feeds" size="small" style="width: 100%;">
            <el-table-column :label="$t('downloader.rss.feedName')" min-width="140">
              <template slot-scope="{row}">
                <div class="feed-name-cell">
                  <LucideIcon name="rss" :size="13" class="feed-icon" />
                  <span class="feed-name" :title="row.name">{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.feedUrl')" min-width="200" show-overflow-tooltip>
              <template slot-scope="{row}">
                <span class="feed-url">{{ row.url }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.enabled')" width="70" align="center">
              <template slot-scope="{row}">
                <el-switch
                  :value="row.enabled"
                  @change="value => handleToggleEnabled(row, value)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.fetchStatus')" width="90" align="center">
              <template slot-scope="{row}">
                <el-tag v-if="row.lastFetchStatus === 'ok'" size="mini" type="success">
                  {{ $t('downloader.rss.statusOk') }}
                </el-tag>
                <el-tag v-else-if="row.lastFetchStatus === 'failed'" size="mini" type="danger" :title="row.lastError || ''">
                  {{ $t('downloader.rss.statusFailed') }}
                </el-tag>
                <el-tag v-else size="mini" type="info">{{ $t('downloader.rss.statusNever') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.lastFetchAt')" width="150">
              <template slot-scope="{row}">
                <span>{{ row.lastFetchAt || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.pendingCount')" width="80" align="center">
              <template slot-scope="{row}">
                <span :class="['pending-badge', {active: (row.pendingCount || 0) > 0}]">{{ row.pendingCount || 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.actions')" width="220" align="center">
              <template slot-scope="{row}">
                <el-button size="mini" type="text" @click="openArticlesDrawer(row)">
                  <LucideIcon name="list" :size="12" />
                  {{ $t('downloader.rss.viewArticles') }}
                </el-button>
                <el-button size="mini" type="text" :loading="refreshingFeedId === row.feedId" @click="handleRefreshFeed(row)">
                  {{ $t('downloader.rss.refreshFeed') }}
                </el-button>
                <el-button size="mini" type="text" @click="openEditDialog(row)">{{ $t('downloader.rss.editFeed') }}</el-button>
                <el-button size="mini" type="text" class="danger-action" @click="handleDeleteFeed(row)">
                  {{ $t('downloader.rss.deleteFeed') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="feedTotal > feedPageSize"
            class="feed-pagination"
            layout="total, prev, pager, next"
            :current-page.sync="feedPage"
            :page-size="feedPageSize"
            :total="feedTotal"
            @current-change="loadFeeds"
          />
        </template>
        <div v-else-if="!loading" class="table-empty">
          <LucideIcon name="rss" :size="36" :stroke-width="1.4" class="empty-icon" />
          <h3>{{ $t('downloader.rss.emptyFeeds') }}</h3>
          <p>{{ $t('downloader.rss.emptyFeedsDesc') }}</p>
        </div>
      </div>
    </div>

    <!-- 新增/编辑订阅源弹窗 -->
    <el-dialog
      :title="editingFeed ? $t('downloader.rss.editFeed') : $t('downloader.rss.addFeed')"
      :visible.sync="feedDialogVisible"
      width="480px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form ref="feedForm" :model="feedForm" :rules="feedFormRules" label-width="90px" size="small">
        <el-form-item :label="$t('downloader.rss.feedName')" prop="name">
          <el-input v-model="feedForm.name" :placeholder="$t('downloader.rss.feedNamePlaceholder')" maxlength="200" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.feedUrl')" prop="url">
          <el-input v-model="feedForm.url" :placeholder="$t('downloader.rss.feedUrlPlaceholder')" maxlength="1000" />
        </el-form-item>
      </el-form>
      <template slot="footer">
        <el-button size="small" @click="feedDialogVisible = false">{{ $t('downloader.rss.cancel') }}</el-button>
        <el-button type="primary" size="small" :loading="submitting" @click="handleSubmitFeed">
          {{ editingFeed ? $t('common.confirm') : $t('downloader.rss.addFeed') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 文章抽屉 -->
    <el-drawer
      :visible.sync="articlesDrawerVisible"
      :title="articlesDrawerTitle"
      size="620px"
      direction="rtl"
      append-to-body
      :wrapper-closable="true"
    >
      <div class="articles-drawer-body">
        <div class="articles-filter">
          <el-radio-group v-model="articleStatusFilter" size="small" @change="handleArticleFilterChange">
            <el-radio-button label="all">{{ $t('downloader.rss.allArticles') }}</el-radio-button>
            <el-radio-button label="pending">{{ $t('downloader.rss.statusPending') }}</el-radio-button>
            <el-radio-button label="added">{{ $t('downloader.rss.statusAdded') }}</el-radio-button>
          </el-radio-group>
          <el-button size="small" :loading="refreshingFeedId === activeFeedId" @click="handleRefreshActiveFeed">
            <LucideIcon name="rotate-ccw" :size="13" />
            {{ $t('downloader.rss.refreshFeed') }}
          </el-button>
        </div>

        <div v-loading="articlesLoading" class="article-list" :element-loading-text="$t('downloader.rss.loading')">
          <template v-if="articles.length > 0">
            <div v-for="article in articles" :key="article.articleId" :class="['article-card', {added: article.status === 'added'}]">
              <div class="article-main">
                <div class="article-title" :title="article.title">{{ article.title }}</div>
                <div class="article-meta">
                  <span class="article-time">{{ article.publishedAt || article.fetchedAt || '—' }}</span>
                  <a
                    v-if="article.link"
                    :href="article.link"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="article-link"
                  >
                    <LucideIcon name="external-link" :size="12" />
                  </a>
                </div>
              </div>
              <div class="article-side">
                <el-tag v-if="article.status === 'added'" size="mini" type="success">
                  {{ $t('downloader.rss.statusAdded') }}
                </el-tag>
                <el-button v-else size="mini" type="primary" plain @click="openPushDialog(article)">
                  {{ $t('downloader.rss.addToDownloader') }}
                </el-button>
              </div>
            </div>
            <el-pagination
              v-if="articleTotal > articlePageSize"
              class="article-pagination"
              layout="total, prev, pager, next"
              :current-page.sync="articlePage"
              :page-size="articlePageSize"
              :total="articleTotal"
              @current-change="loadArticles"
            />
          </template>
          <div v-else-if="!articlesLoading" class="table-empty">
            <LucideIcon name="inbox" :size="36" :stroke-width="1.4" class="empty-icon" />
            <h3>{{ $t('downloader.rss.emptyArticles') }}</h3>
            <p>{{ $t('downloader.rss.emptyArticlesDesc') }}</p>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 推送参数弹窗 -->
    <el-dialog
      :title="$t('downloader.rss.pushParams')"
      :visible.sync="pushDialogVisible"
      width="480px"
      :close-on-click-modal="false"
      append-to-body
    >
      <div v-if="pushingArticle" class="push-article-title" :title="pushingArticle.title">
        <LucideIcon name="rss" :size="13" />
        {{ pushingArticle.title }}
      </div>
      <el-form label-width="90px" size="small">
        <el-form-item :label="$t('downloader.rss.targetDownloader')">
          <el-select v-model="pushForm.downloaderId" style="width: 100%;">
            <el-option
              v-for="item in downloaderOptions"
              :key="item.downloaderId"
              :label="item.nickname"
              :value="item.downloaderId"
            />
          </el-select>
          <div class="form-tip">{{ $t('downloader.rss.targetDownloaderDefault') }}</div>
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.savePath')">
          <el-input v-model="pushForm.savePath" :placeholder="$t('downloader.rss.savePathPlaceholder')" maxlength="500" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.tagsLabel')">
          <el-input v-model="pushForm.tags" :placeholder="$t('downloader.rss.tagsPlaceholder')" maxlength="500" />
        </el-form-item>
      </el-form>
      <template slot="footer">
        <el-button size="small" @click="pushDialogVisible = false">{{ $t('downloader.rss.cancel') }}</el-button>
        <el-button type="primary" size="small" :loading="pushing" @click="handlePushArticle">
          {{ $t('downloader.rss.pushConfirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import { Message, MessageBox } from 'element-ui'
import { Downloader } from '../types'
import {
  getRssFeeds,
  createRssFeed,
  updateRssFeed,
  deleteRssFeed,
  refreshRssFeed,
  getRssArticles,
  addRssArticle,
  RssFeed,
  RssArticle
} from '@/api/rss'
import { getList } from '@/api/downloader'
import { extractErrorMessage } from '@/utils/formatters'

interface FeedFormState {
  name: string
  url: string
}

@Component({
  name: 'RssSubscriptionTab'
})
export default class RssSubscriptionTab extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null

  // ==================== 订阅源列表 ====================

  private feeds: RssFeed[] = []
  private loading = false
  private feedPage = 1
  private feedPageSize = 20
  private feedTotal = 0

  // ==================== 新增/编辑弹窗 ====================

  private feedDialogVisible = false
  private submitting = false
  private editingFeed: RssFeed | null = null
  private feedForm: FeedFormState = { name: '', url: '' }

  private get feedFormRules(): Record<string, unknown[]> {
    return {
      name: [
        { required: true, message: this.$t('downloader.rss.feedName').toString(), trigger: 'blur' }
      ],
      url: [
        { required: true, message: this.$t('downloader.rss.feedUrl').toString(), trigger: 'blur' },
        {
          validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
            if (value && !/^https?:\/\/.+/i.test(value.trim())) {
              callback(new Error(this.$t('downloader.rss.feedUrlPlaceholder').toString()))
              return
            }
            callback()
          },
          trigger: 'blur'
        }
      ]
    }
  }

  // ==================== 文章抽屉 ====================

  private articlesDrawerVisible = false
  private articles: RssArticle[] = []
  private articlesLoading = false
  private articlePage = 1
  private articlePageSize = 20
  private articleTotal = 0
  private articleStatusFilter: 'all' | 'pending' | 'added' = 'all'
  private activeFeed: RssFeed | null = null

  private get activeFeedId(): string {
    return this.activeFeed ? this.activeFeed.feedId : ''
  }

  private get articlesDrawerTitle(): string {
    return this.activeFeed
      ? `${this.$t('downloader.rss.articles')} · ${this.activeFeed.name}`
      : this.$t('downloader.rss.articles').toString()
  }

  // ==================== 推送弹窗 ====================

  private pushDialogVisible = false
  private pushing = false
  private pushingArticle: RssArticle | null = null
  private downloaderOptions: Downloader[] = []
  private pushForm = {
    downloaderId: '',
    savePath: '',
    tags: ''
  }

  // ==================== 刷新状态 ====================

  private refreshingFeedId = ''

  // ==================== 生命周期 ====================

  mounted() {
    if (this.downloader) {
      this.loadFeeds()
    }
  }

  @Watch('downloader')
  onDownloaderChanged(value: Downloader | null) {
    if (value) {
      this.feedPage = 1
      this.loadFeeds()
    } else {
      this.feeds = []
      this.feedTotal = 0
    }
  }

  // ==================== 订阅源操作 ====================

  private async loadFeeds(): Promise<void> {
    if (!this.downloader) return
    this.loading = true
    try {
      const response = await getRssFeeds({
        downloaderId: this.downloader.downloaderId,
        page: this.feedPage,
        pageSize: this.feedPageSize
      })
      this.feeds = response.data.list
      this.feedTotal = response.data.total
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.loading = false
    }
  }

  private openCreateDialog() {
    this.editingFeed = null
    this.feedForm = { name: '', url: '' }
    this.feedDialogVisible = true
    this.$nextTick(() => {
      const form = this.$refs.feedForm as ElForm | undefined
      form?.clearValidate()
    })
  }

  private openEditDialog(feed: RssFeed) {
    this.editingFeed = feed
    this.feedForm = { name: feed.name, url: feed.url }
    this.feedDialogVisible = true
    this.$nextTick(() => {
      const form = this.$refs.feedForm as ElForm | undefined
      form?.clearValidate()
    })
  }

  private async handleSubmitFeed(): Promise<void> {
    const form = this.$refs.feedForm as ElForm | undefined
    if (form) {
      const valid = await form.validate().catch(() => false)
      if (!valid) return
    }
    if (!this.downloader) return
    this.submitting = true
    try {
      const payload = { name: this.feedForm.name.trim(), url: this.feedForm.url.trim() }
      if (this.editingFeed) {
        await updateRssFeed(this.editingFeed.feedId, payload)
        Message.success(this.$t('downloader.rss.updateSuccess').toString())
      } else {
        await createRssFeed({ downloaderId: this.downloader.downloaderId, ...payload })
        Message.success(this.$t('downloader.rss.createSuccess').toString())
      }
      this.feedDialogVisible = false
      this.loadFeeds()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.submitting = false
    }
  }

  private async handleToggleEnabled(feed: RssFeed, value: boolean): Promise<void> {
    try {
      await updateRssFeed(feed.feedId, { enabled: value })
      feed.enabled = value
    } catch (error) {
      Message.error(extractErrorMessage(error))
    }
  }

  private handleDeleteFeed(feed: RssFeed) {
    MessageBox.confirm(
      this.$t('downloader.rss.deleteConfirmMsg', { name: feed.name }).toString(),
      this.$t('downloader.rss.deleteConfirmTitle').toString(),
      { type: 'warning', confirmButtonText: this.$t('common.confirm').toString(), cancelButtonText: this.$t('downloader.rss.cancel').toString() }
    )
      .then(async() => {
        try {
          await deleteRssFeed(feed.feedId)
          Message.success(this.$t('downloader.rss.deleteSuccess').toString())
          if (this.activeFeedId === feed.feedId) {
            this.articlesDrawerVisible = false
            this.activeFeed = null
          }
          this.loadFeeds()
        } catch (error) {
          Message.error(extractErrorMessage(error))
        }
      })
      .catch(() => undefined)
  }

  private async handleRefreshFeed(feed: RssFeed): Promise<void> {
    this.refreshingFeedId = feed.feedId
    try {
      const response = await refreshRssFeed(feed.feedId)
      Message.success(
        this.$t('downloader.rss.refreshSuccess', {
          newCount: response.data.newCount,
          articleCount: response.data.articleCount
        }).toString()
      )
      this.loadFeeds()
      if (this.activeFeedId === feed.feedId) {
        this.loadArticles()
      }
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.refreshingFeedId = ''
    }
  }

  private handleRefreshActiveFeed() {
    if (this.activeFeed) {
      this.handleRefreshFeed(this.activeFeed)
    }
  }

  // ==================== 文章抽屉 ====================

  private openArticlesDrawer(feed: RssFeed) {
    this.activeFeed = feed
    this.articlePage = 1
    this.articleStatusFilter = 'all'
    this.articlesDrawerVisible = true
    this.loadArticles()
  }

  private handleArticleFilterChange() {
    this.articlePage = 1
    this.loadArticles()
  }

  private async loadArticles(): Promise<void> {
    if (!this.activeFeed) return
    this.articlesLoading = true
    try {
      const response = await getRssArticles(this.activeFeed.feedId, {
        page: this.articlePage,
        pageSize: this.articlePageSize,
        status: this.articleStatusFilter === 'all' ? undefined : this.articleStatusFilter
      })
      this.articles = response.data.list
      this.articleTotal = response.data.total
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.articlesLoading = false
    }
  }

  // ==================== 推送 ====================

  private async openPushDialog(article: RssArticle): Promise<void> {
    this.pushingArticle = article
    this.pushForm = { downloaderId: '', savePath: '', tags: '' }
    this.pushDialogVisible = true
    if (this.downloaderOptions.length === 0) {
      try {
        const response = await getList({})
        this.downloaderOptions = (response.data as Downloader[]).filter(
          (item: Downloader) => item.downloaderType === 0 || item.downloaderType === 1
        )
      } catch {
        // 目标列表加载失败不阻塞推送（可用默认绑定下载器）
        this.downloaderOptions = []
      }
    }
  }

  private async handlePushArticle(): Promise<void> {
    if (!this.pushingArticle) return
    this.pushing = true
    try {
      await addRssArticle(this.pushingArticle.articleId, {
        downloaderId: this.pushForm.downloaderId || undefined,
        savePath: this.pushForm.savePath.trim() || undefined,
        tags: this.pushForm.tags.trim() || undefined
      })
      Message.success(this.$t('downloader.rss.pushSuccess').toString())
      this.pushDialogVisible = false
      this.loadArticles()
      this.loadFeeds()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.pushing = false
    }
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.rss-subscription-tab {
  width: 100%;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;

  .empty-icon {
    color: var(--color-text-secondary, #909399);
    margin-bottom: 12px;
  }

  h3 {
    margin: 0 0 8px;
    font-size: 16px;
    font-weight: 600;
  }

  p {
    margin: 0;
    font-size: 13px;
    color: var(--color-text-secondary, #909399);
  }
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 8px;
  flex-wrap: wrap;
}

.feed-table {
  min-height: 160px;

  .table-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 48px 20px;

    .empty-icon {
      color: var(--color-text-secondary, #909399);
      margin-bottom: 10px;
    }

    h3 {
      margin: 0 0 6px;
      font-size: 15px;
    }

    p {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary, #909399);
    }
  }
}

.feed-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;

  .feed-icon {
    color: var(--color-primary, #409eff);
    flex-shrink: 0;
  }

  .feed-name {
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.feed-url {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  word-break: break-all;
}

.pending-badge {
  font-weight: 600;
  color: var(--color-text-secondary, #909399);

  &.active {
    color: var(--color-primary, #409eff);
  }
}

.danger-action {
  color: var(--color-danger, #f56c6c) !important;
}

.feed-pagination {
  margin-top: 12px;
  text-align: right;
}

.articles-drawer-body {
  display: flex;
  flex-direction: column;
  padding: 0 16px 16px;
  height: 100%;
  box-sizing: border-box;
}

.articles-filter {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.article-list {
  flex: 1;
  min-height: 200px;
  overflow-y: auto;

  .table-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 48px 20px;

    .empty-icon {
      color: var(--color-text-secondary, #909399);
      margin-bottom: 10px;
    }

    h3 {
      margin: 0 0 6px;
      font-size: 15px;
    }

    p {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary, #909399);
    }
  }
}

.article-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--color-border-lighter, #ebeef5);
  border-radius: 6px;
  margin-bottom: 8px;

  &.added {
    background: var(--color-success-bg, #f0f9eb);
  }

  .article-main {
    flex: 1;
    min-width: 0;

    .article-title {
      font-size: 13px;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .article-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 4px;

      .article-time {
        font-size: 12px;
        color: var(--color-text-secondary, #909399);
      }

      .article-link {
        color: var(--color-text-secondary, #909399);
        display: inline-flex;

        &:hover {
          color: var(--color-primary, #409eff);
        }
      }
    }
  }

  .article-side {
    flex-shrink: 0;
  }
}

.article-pagination {
  margin-top: 12px;
  text-align: right;
}

.push-article-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: var(--color-bg-page, #f5f7fa);
  border-radius: 4px;
  word-break: break-all;
}

.form-tip {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  line-height: 1.5;
  margin-top: 4px;
}

/* ≤780 移动适配：抽屉全宽、表格横向滚动、工具栏纵向堆叠 */
@media (max-width: 780px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;

    .toolbar-left,
    .toolbar-right {
      width: 100%;

      ::v-deep .el-button {
        width: 100%;
      }
    }
  }
}
</style>

<style lang="scss">
/* 抽屉内内容区高度修正（element-ui drawer body 默认无高度约束） */
.el-drawer__body {
  .articles-drawer-body {
    height: 100%;
  }
}

/* 移动端抽屉全宽 */
@media (max-width: 780px) {
  .el-drawer.rtl {
    width: 100% !important;
  }
}
</style>
