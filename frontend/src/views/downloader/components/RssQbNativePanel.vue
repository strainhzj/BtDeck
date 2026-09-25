<template>
  <div class="rss-qb-native-panel">
    <!-- 面板头 -->
    <div class="qb-header">
      <div class="qb-header__text">
        <h4>
          <LucideIcon name="rss" :size="14" />
          {{ $t('downloader.rss.qb.sectionTitle') }}
        </h4>
        <p>{{ $t('downloader.rss.qb.sectionDesc') }}</p>
      </div>
      <div class="qb-header__actions">
        <el-button size="mini" :loading="treeLoading" @click="loadFeeds">{{ $t('downloader.rss.refreshList') }}</el-button>
        <el-button size="mini" :loading="refreshingAll" @click="handleRefreshAll">
          <LucideIcon name="rotate-ccw" :size="12" />
          {{ $t('downloader.rss.qb.refreshAll') }}
        </el-button>
        <el-button size="mini" @click="folderDialogVisible = true">{{ $t('downloader.rss.qb.addFolder') }}</el-button>
        <el-button type="primary" size="mini" @click="feedDialogVisible = true">{{ $t('downloader.rss.qb.addFeed') }}</el-button>
      </div>
    </div>

    <!-- 源树 -->
    <div v-loading="treeLoading" class="qb-tree" :element-loading-text="$t('downloader.rss.qb.loadingTree')">
      <template v-if="treeData.length > 0">
        <el-tree
          :data="treeData"
          node-key="path"
          default-expand-all
          :expand-on-click-node="false"
        >
          <span slot-scope="{data}" class="qb-tree-node">
            <span class="qb-tree-node__name">
              <LucideIcon :name="data.type === 'folder' ? 'folder' : 'rss'" :size="13" :class="{'is-folder': data.type === 'folder'}" />
              <span class="qb-tree-node__label" :title="data.path">{{ data.name }}</span>
              <span v-if="data.type === 'feed' && (data.unreadCount || 0) > 0" class="unread-badge">{{ data.unreadCount }}</span>
            </span>
            <span v-if="data.type === 'feed'" class="qb-tree-node__actions">
              <el-button size="mini" type="text" @click="openArticles(data)">
                <LucideIcon name="list" :size="12" />
                {{ $t('downloader.rss.viewArticles') }}
              </el-button>
              <el-button size="mini" type="text" :loading="busyPath === data.path" @click="handleRefreshItem(data)">
                {{ $t('downloader.rss.refreshFeed') }}
              </el-button>
              <el-button size="mini" type="text" @click="handleChangeUrl(data)">{{ $t('downloader.rss.qb.changeUrl') }}</el-button>
              <el-button size="mini" type="text" @click="handleMarkRead(data, null)">{{ $t('downloader.rss.qb.markAllRead') }}</el-button>
              <el-button size="mini" type="text" class="danger-action" @click="handleDeleteItem(data)">
                {{ $t('downloader.rss.deleteFeed') }}
              </el-button>
            </span>
            <span v-else class="qb-tree-node__actions">
              <el-button size="mini" type="text" class="danger-action" @click="handleDeleteItem(data)">
                {{ $t('downloader.rss.deleteFeed') }}
              </el-button>
            </span>
          </span>
        </el-tree>
      </template>
      <div v-else-if="!treeLoading" class="qb-empty">
        <LucideIcon name="rss" :size="34" :stroke-width="1.4" class="empty-icon" />
        <h4>{{ $t('downloader.rss.qb.emptyFeeds') }}</h4>
        <p>{{ $t('downloader.rss.qb.emptyFeedsDesc') }}</p>
      </div>
    </div>

    <!-- qB 规则 -->
    <div class="qb-section">
      <div class="qb-section__head">
        <h4>
          <LucideIcon name="wand-sparkles" :size="14" />
          {{ $t('downloader.rss.qb.rulesTitle') }}
        </h4>
        <el-button type="primary" size="mini" @click="openRuleDialog(null)">
          <LucideIcon name="plus" :size="13" />
          {{ $t('downloader.rss.qb.addRule') }}
        </el-button>
      </div>
      <div v-loading="rulesLoading" class="qb-rules-table">
        <template v-if="rules.length > 0">
          <el-table :data="rules" size="mini" style="width: 100%;">
            <el-table-column :label="$t('downloader.rss.qb.ruleName')" min-width="130">
              <template slot-scope="{row}">
                <span class="rule-name" :title="row.name">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.qb.mustContain')" min-width="130">
              <template slot-scope="{row}">
                <span>{{ row.mustContain || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.qb.mustNotContain')" min-width="120">
              <template slot-scope="{row}">
                <span>{{ row.mustNotContain || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.qb.affectedFeeds')" min-width="140">
              <template slot-scope="{row}">
                <span :title="affectedFeedsText(row)">{{ affectedFeedsText(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.enabled')" width="60" align="center">
              <template slot-scope="{row}">
                <span>{{ row.enabled ? '✓' : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('downloader.rss.actions')" width="190" align="center">
              <template slot-scope="{row}">
                <el-button size="mini" type="text" @click="openMatching(row)">{{ $t('downloader.rss.qb.matchingPreview') }}</el-button>
                <el-button size="mini" type="text" @click="openRuleDialog(row)">{{ $t('downloader.rss.qb.editRule') }}</el-button>
                <el-button size="mini" type="text" class="danger-action" @click="handleDeleteRule(row)">
                  {{ $t('downloader.rss.deleteFeed') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
        <div v-else-if="!rulesLoading" class="qb-empty qb-empty--compact">
          <p>{{ $t('downloader.rss.emptyRulesDesc') }}</p>
        </div>
      </div>
    </div>

    <!-- qB 偏好 -->
    <div class="qb-section">
      <div class="qb-section__head">
        <h4>
          <LucideIcon name="settings-2" :size="14" />
          {{ $t('downloader.rss.qb.prefsTitle') }}
        </h4>
      </div>
      <div v-loading="prefsLoading" class="qb-prefs">
        <el-form label-width="150px" size="small" class="qb-prefs__form">
          <el-form-item :label="$t('downloader.rss.qb.prefProcessing')">
            <el-switch v-model="prefsForm.rssProcessingEnabled" />
          </el-form-item>
          <el-form-item :label="$t('downloader.rss.qb.prefAutoDownload')">
            <el-switch v-model="prefsForm.rssAutoDownloadingEnabled" />
          </el-form-item>
          <el-form-item :label="$t('downloader.rss.qb.prefRefreshInterval')">
            <el-input-number v-model="prefsForm.rssRefreshInterval" :min="1" :max="9999" controls-position="right" style="width: 140px;" />
          </el-form-item>
          <el-form-item :label="$t('downloader.rss.qb.prefMaxArticles')">
            <el-input-number v-model="prefsForm.rssMaxArticlesPerFeed" :min="1" :max="5000" controls-position="right" style="width: 140px;" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="small" :loading="prefsSaving" @click="handleSavePrefs">
              {{ $t('common.confirm') }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 添加源弹窗 -->
    <el-dialog :title="$t('downloader.rss.qb.addFeed')" :visible.sync="feedDialogVisible" width="480px" append-to-body>
      <el-form label-width="80px" size="small">
        <el-form-item :label="$t('downloader.rss.qb.path')">
          <el-input v-model="feedDialogForm.path" :placeholder="$t('downloader.rss.qb.pathPlaceholder')" maxlength="500" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.feedUrl')">
          <el-input v-model="feedDialogForm.url" :placeholder="$t('downloader.rss.feedUrlPlaceholder')" maxlength="1000" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="feedDialogVisible = false">{{ $t('downloader.rss.cancel') }}</el-button>
        <el-button type="primary" size="small" :loading="dialogSubmitting" @click="handleAddFeed">{{ $t('common.confirm') }}</el-button>
      </div>
    </el-dialog>

    <!-- 添加文件夹弹窗 -->
    <el-dialog :title="$t('downloader.rss.qb.addFolder')" :visible.sync="folderDialogVisible" width="480px" append-to-body>
      <el-form label-width="80px" size="small">
        <el-form-item :label="$t('downloader.rss.qb.path')">
          <el-input v-model="folderForm.path" :placeholder="$t('downloader.rss.qb.pathPlaceholder')" maxlength="500" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="folderDialogVisible = false">{{ $t('downloader.rss.cancel') }}</el-button>
        <el-button type="primary" size="small" :loading="dialogSubmitting" @click="handleAddFolder">{{ $t('common.confirm') }}</el-button>
      </div>
    </el-dialog>

    <!-- 规则编辑弹窗 -->
    <el-dialog
      :title="editingRuleName ? $t('downloader.rss.qb.editRule') : $t('downloader.rss.qb.addRule')"
      :visible.sync="ruleDialogVisible"
      width="560px"
      append-to-body
    >
      <el-form label-width="110px" size="small">
        <el-form-item :label="$t('downloader.rss.qb.ruleName')">
          <el-input v-model="ruleForm.name" maxlength="200" :disabled="Boolean(editingRuleName)" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.qb.mustContain')">
          <el-input v-model="ruleForm.mustContain" :placeholder="$t('downloader.rss.includeKeywordsPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.qb.mustNotContain')">
          <el-input v-model="ruleForm.mustNotContain" :placeholder="$t('downloader.rss.excludeKeywordsPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.qb.affectedFeeds')">
          <el-input v-model="ruleForm.affectedFeeds" :placeholder="$t('downloader.rss.qb.affectedFeedsPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.qb.savePath')">
          <el-input v-model="ruleForm.savePath" :placeholder="$t('downloader.rss.savePathPlaceholder')" maxlength="500" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.qb.category')">
          <el-input v-model="ruleForm.assignedCategory" maxlength="100" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.qb.addPaused')">
          <el-switch v-model="ruleForm.addPaused" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.enabled')">
          <el-switch v-model="ruleForm.enabled" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="ruleDialogVisible = false">{{ $t('downloader.rss.cancel') }}</el-button>
        <el-button type="primary" size="small" :loading="dialogSubmitting" @click="handleSaveRule">{{ $t('common.confirm') }}</el-button>
      </div>
    </el-dialog>

    <!-- 命中预览弹窗 -->
    <el-dialog :title="matchingRuleName" :visible.sync="matchingVisible" width="560px" append-to-body>
      <div v-loading="matchingLoading" class="matching-body">
        <template v-if="matchingFeeds.length > 0">
          <div v-for="group in matchingFeeds" :key="group.feedPath" class="matching-group">
            <div class="matching-group__path">{{ group.feedPath }}</div>
            <div v-for="article in group.articles" :key="article.articleId" class="matching-item">
              <span class="matching-item__title" :title="article.title">{{ article.title }}</span>
              <span class="matching-item__time">{{ article.published || '' }}</span>
            </div>
          </div>
        </template>
        <div v-else-if="!matchingLoading" class="preview-empty">
          <p>{{ $t('downloader.rss.rulePreviewEmpty') }}</p>
        </div>
      </div>
    </el-dialog>

    <!-- 文章抽屉 -->
    <el-drawer
      :title="`${$t('downloader.rss.qb.articlesTitle')} · ${articlesFeed ? articlesFeed.name : ''}`"
      :visible.sync="articlesVisible"
      size="480px"
      append-to-body
    >
      <div class="articles-body">
        <div class="articles-toolbar">
          <el-checkbox v-model="onlyUnread" size="mini" @change="loadArticles">{{ $t('downloader.rss.qb.unreadOnly') }}</el-checkbox>
          <el-button v-if="articlesFeed" size="mini" :loading="markingRead" @click="handleMarkRead(articlesFeed, null)">
            {{ $t('downloader.rss.qb.markAllRead') }}
          </el-button>
        </div>
        <div v-loading="articlesLoading" class="articles-list">
          <template v-if="articles.length > 0">
            <div v-for="article in articles" :key="article.articleId" :class="['qb-article', {'is-read': article.isRead}]">
              <div class="qb-article__main">
                <div class="qb-article__title" :title="article.title">{{ article.title }}</div>
                <div class="qb-article__meta">
                  <span>{{ article.published || '' }}</span>
                  <a v-if="article.link" :href="article.link" target="_blank" rel="noopener noreferrer" class="qb-article__link">
                    <LucideIcon name="external-link" :size="12" />
                  </a>
                </div>
              </div>
              <el-button v-if="!article.isRead" size="mini" type="text" @click="handleMarkRead(articlesFeed, article.articleId)">
                {{ $t('downloader.rss.qb.markRead') }}
              </el-button>
            </div>
          </template>
          <div v-else-if="!articlesLoading" class="preview-empty">
            <p>{{ $t('downloader.rss.qb.emptyArticles') }}</p>
            <p class="empty-desc">{{ $t('downloader.rss.qb.emptyArticlesDesc') }}</p>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script lang="ts">
import { Message, MessageBox } from 'element-ui'
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'
import { extractErrorMessage } from '@/utils/formatters'
import {
  RssQbArticle,
  RssQbNode,
  RssQbPreferences,
  RssQbRule,
  RssQbRuleDef,
  addQbRssFeed,
  addQbRssFolder,
  deleteQbRssItem,
  deleteQbRssRule,
  getQbRssArticles,
  getQbRssFeeds,
  getQbRssMatching,
  getQbRssPreferences,
  getQbRssRules,
  markQbRssRead,
  refreshQbRssItem,
  setQbRssRule,
  updateQbRssFeedUrl,
  updateQbRssPreferences
} from '@/api/rss'
import { Downloader } from '@/views/downloader/types'

@Component({
  name: 'RssQbNativePanel',
  components: { LucideIcon }
})
export default class RssQbNativePanel extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null

  // ==================== 源树 ====================
  private treeData: RssQbNode[] = []
  private treeLoading = false
  private refreshingAll = false
  private busyPath = ''

  // ==================== 规则 ====================
  private rules: RssQbRule[] = []
  private rulesLoading = false
  private ruleDialogVisible = false
  private editingRuleName = ''
  private ruleForm = {
    name: '',
    mustContain: '',
    mustNotContain: '',
    affectedFeeds: '',
    savePath: '',
    assignedCategory: '',
    addPaused: false,
    enabled: true
  }

  // ==================== 偏好 ====================
  private prefsLoading = false
  private prefsSaving = false
  private prefsForm: RssQbPreferences = {
    rssProcessingEnabled: false,
    rssAutoDownloadingEnabled: false,
    rssRefreshInterval: 30,
    rssMaxArticlesPerFeed: 50
  }

  // ==================== 弹窗通用 ====================
  private dialogSubmitting = false
  private feedDialogVisible = false
  private feedDialogForm = { path: '', url: '' }
  private folderDialogVisible = false
  private folderForm = { path: '' }

  // ==================== 命中预览 ====================
  private matchingVisible = false
  private matchingLoading = false
  private matchingRuleName = ''
  private matchingFeeds: Array<{ feedPath: string, articles: RssQbArticle[] }> = []

  // ==================== 文章抽屉 ====================
  private articlesVisible = false
  private articlesLoading = false
  private articlesFeed: RssQbNode | null = null
  private articles: RssQbArticle[] = []
  private onlyUnread = false
  private markingRead = false

  mounted() {
    if (this.downloader) {
      this.loadAll()
    }
  }

  @Watch('downloader')
  onDownloaderChanged(value: Downloader | null) {
    if (value) {
      this.loadAll()
    } else {
      this.treeData = []
      this.rules = []
    }
  }

  private loadAll(): void {
    this.loadFeeds()
    this.loadRules()
    this.loadPrefs()
  }

  // ==================== 源树操作 ====================

  private async loadFeeds(): Promise<void> {
    if (!this.downloader) return
    this.treeLoading = true
    try {
      const response = await getQbRssFeeds(this.downloader.downloaderId)
      this.treeData = response.data.list
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.treeLoading = false
    }
  }

  private async handleRefreshAll(): Promise<void> {
    if (!this.downloader) return
    this.refreshingAll = true
    try {
      await refreshQbRssItem(this.downloader.downloaderId, null)
      Message.success(this.$t('downloader.rss.qb.refreshAll').toString())
      this.loadFeeds()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.refreshingAll = false
    }
  }

  private async handleRefreshItem(node: RssQbNode): Promise<void> {
    if (!this.downloader) return
    this.busyPath = node.path
    try {
      await refreshQbRssItem(this.downloader.downloaderId, node.path)
      this.loadFeeds()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.busyPath = ''
    }
  }

  private async handleAddFeed(): Promise<void> {
    if (!this.downloader) return
    this.dialogSubmitting = true
    try {
      await addQbRssFeed(this.downloader.downloaderId, this.feedDialogForm.path.trim(), this.feedDialogForm.url.trim())
      Message.success(this.$t('downloader.rss.createSuccess').toString())
      this.feedDialogVisible = false
      this.feedDialogForm = { path: '', url: '' }
      this.loadFeeds()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.dialogSubmitting = false
    }
  }

  private async handleAddFolder(): Promise<void> {
    if (!this.downloader) return
    this.dialogSubmitting = true
    try {
      await addQbRssFolder(this.downloader.downloaderId, this.folderForm.path.trim())
      Message.success(this.$t('downloader.rss.createSuccess').toString())
      this.folderDialogVisible = false
      this.folderForm.path = ''
      this.loadFeeds()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.dialogSubmitting = false
    }
  }

  private handleChangeUrl(node: RssQbNode): void {
    if (!this.downloader) return
    MessageBox.prompt(this.$t('downloader.rss.feedUrlPlaceholder').toString(), this.$t('downloader.rss.qb.changeUrl').toString(), {
      inputPattern: /^https?:\/\/.+/i,
      inputErrorMessage: this.$t('downloader.rss.feedUrlPlaceholder').toString(),
      confirmButtonText: this.$t('common.confirm').toString(),
      cancelButtonText: this.$t('downloader.rss.cancel').toString()
    })
      .then(async({ value }) => {
        const downloader = this.downloader
        if (!downloader) return
        try {
          await updateQbRssFeedUrl(downloader.downloaderId, node.path, value.trim())
          Message.success(this.$t('downloader.rss.updateSuccess').toString())
        } catch (error) {
          Message.error(extractErrorMessage(error))
        }
      })
      .catch(() => undefined)
  }

  private handleDeleteItem(node: RssQbNode): void {
    if (!this.downloader) return
    MessageBox.confirm(
      this.$t('downloader.rss.qb.deleteItemConfirmMsg', { name: node.path }).toString(),
      this.$t('downloader.rss.qb.deleteItemConfirmTitle').toString(),
      { type: 'warning', confirmButtonText: this.$t('common.confirm').toString(), cancelButtonText: this.$t('downloader.rss.cancel').toString() }
    )
      .then(async() => {
        const downloader = this.downloader
        if (!downloader) return
        try {
          await deleteQbRssItem(downloader.downloaderId, node.path)
          Message.success(this.$t('downloader.rss.deleteSuccess').toString())
          this.loadFeeds()
        } catch (error) {
          Message.error(extractErrorMessage(error))
        }
      })
      .catch(() => undefined)
  }

  private async handleMarkRead(node: RssQbNode | null, articleId: string | null): Promise<void> {
    if (!this.downloader || !node) return
    this.markingRead = true
    try {
      await markQbRssRead(this.downloader.downloaderId, node.path, articleId)
      if (articleId) {
        this.loadArticles()
      } else {
        this.loadFeeds()
        if (this.articlesVisible) {
          this.loadArticles()
        }
      }
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.markingRead = false
    }
  }

  // ==================== 文章抽屉 ====================

  private openArticles(node: RssQbNode): void {
    this.articlesFeed = node
    this.onlyUnread = false
    this.articlesVisible = true
    this.loadArticles()
  }

  private async loadArticles(): Promise<void> {
    if (!this.downloader || !this.articlesFeed) return
    this.articlesLoading = true
    try {
      const response = await getQbRssArticles(
        this.downloader.downloaderId,
        this.articlesFeed.path,
        this.onlyUnread
      )
      this.articles = response.data.list
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.articlesLoading = false
    }
  }

  // ==================== 规则操作 ====================

  private async loadRules(): Promise<void> {
    if (!this.downloader) return
    this.rulesLoading = true
    try {
      const response = await getQbRssRules(this.downloader.downloaderId)
      this.rules = response.data.list
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.rulesLoading = false
    }
  }

  private affectedFeedsText(rule: RssQbRule): string {
    const feeds = rule.affectedFeeds || []
    return feeds.length ? feeds.join(', ') : this.$t('downloader.rss.ruleFeedsAll').toString()
  }

  private openRuleDialog(rule: RssQbRule | null): void {
    this.editingRuleName = rule ? rule.name : ''
    this.ruleForm = {
      name: rule ? rule.name : '',
      mustContain: (rule && rule.mustContain) || '',
      mustNotContain: (rule && rule.mustNotContain) || '',
      affectedFeeds: (rule && rule.affectedFeeds && rule.affectedFeeds.join(', ')) || '',
      savePath: (rule && rule.savePath) || '',
      assignedCategory: (rule && rule.assignedCategory) || '',
      addPaused: Boolean(rule && rule.addPaused),
      enabled: rule ? Boolean(rule.enabled) : true
    }
    this.ruleDialogVisible = true
  }

  private async handleSaveRule(): Promise<void> {
    if (!this.downloader) return
    const name = this.ruleForm.name.trim()
    if (!name) {
      Message.warning(this.$t('downloader.rss.qb.ruleName').toString())
      return
    }
    this.dialogSubmitting = true
    try {
      const affectedFeeds = this.ruleForm.affectedFeeds
        .split(',')
        .map(part => part.trim())
        .filter(part => part.length > 0)
      const ruleDef: RssQbRuleDef = {
        enabled: this.ruleForm.enabled,
        mustContain: this.ruleForm.mustContain.trim(),
        mustNotContain: this.ruleForm.mustNotContain.trim(),
        affectedFeeds,
        savePath: this.ruleForm.savePath.trim(),
        assignedCategory: this.ruleForm.assignedCategory.trim(),
        addPaused: this.ruleForm.addPaused
      }
      await setQbRssRule(this.downloader.downloaderId, name, ruleDef)
      Message.success(this.$t('downloader.rss.ruleCreateSuccess').toString())
      this.ruleDialogVisible = false
      this.loadRules()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.dialogSubmitting = false
    }
  }

  private handleDeleteRule(rule: RssQbRule): void {
    if (!this.downloader) return
    MessageBox.confirm(
      this.$t('downloader.rss.qb.ruleDeleteConfirmMsg', { name: rule.name }).toString(),
      this.$t('downloader.rss.qb.ruleDeleteConfirmTitle').toString(),
      { type: 'warning', confirmButtonText: this.$t('common.confirm').toString(), cancelButtonText: this.$t('downloader.rss.cancel').toString() }
    )
      .then(async() => {
        const downloader = this.downloader
        if (!downloader) return
        try {
          await deleteQbRssRule(downloader.downloaderId, rule.name)
          Message.success(this.$t('downloader.rss.ruleDeleteSuccess').toString())
          this.loadRules()
        } catch (error) {
          Message.error(extractErrorMessage(error))
        }
      })
      .catch(() => undefined)
  }

  private async openMatching(rule: RssQbRule): Promise<void> {
    if (!this.downloader) return
    this.matchingRuleName = `${this.$t('downloader.rss.qb.matchingPreview')} · ${rule.name}`
    this.matchingVisible = true
    this.matchingLoading = true
    this.matchingFeeds = []
    try {
      const response = await getQbRssMatching(this.downloader.downloaderId, rule.name)
      this.matchingFeeds = response.data.feeds
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.matchingLoading = false
    }
  }

  // ==================== 偏好 ====================

  private async loadPrefs(): Promise<void> {
    if (!this.downloader) return
    this.prefsLoading = true
    try {
      const response = await getQbRssPreferences(this.downloader.downloaderId)
      this.prefsForm = { ...response.data.preferences }
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.prefsLoading = false
    }
  }

  private async handleSavePrefs(): Promise<void> {
    if (!this.downloader) return
    this.prefsSaving = true
    try {
      const response = await updateQbRssPreferences(this.downloader.downloaderId, { ...this.prefsForm })
      this.prefsForm = { ...response.data.preferences }
      Message.success(this.$t('downloader.rss.qb.prefsSaved').toString())
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.prefsSaving = false
    }
  }
}
</script>

<style lang="scss" scoped>
.rss-qb-native-panel {
  .qb-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 12px;

    &__text {
      h4 {
        display: flex;
        align-items: center;
        gap: 6px;
        margin: 0 0 4px;
        font-size: 14px;
      }

      p {
        margin: 0;
        font-size: 12px;
        opacity: 0.65;
      }
    }

    &__actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
  }
}

.qb-tree {
  min-height: 80px;
  border: 1px solid rgba(128, 128, 128, 0.18);
  border-radius: 8px;
  padding: 6px 10px;

  ::v-deep .el-tree-node__content {
    height: 32px;
  }
}

.qb-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  padding-right: 6px;
  overflow: hidden;

  &__name {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    overflow: hidden;

    .is-folder {
      opacity: 0.7;
    }
  }

  &__label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }
}

.unread-badge {
  background: rgba(245, 108, 108, 0.15);
  color: #f56c6c;
  border-radius: 9px;
  font-size: 11px;
  padding: 0 6px;
  line-height: 16px;
  font-variant-numeric: tabular-nums;
}

.qb-section {
  margin-top: 18px;

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;

    h4 {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 0;
      font-size: 14px;
    }
  }
}

.qb-rules-table {
  min-height: 60px;
}

.rule-name {
  font-weight: 500;
}

.danger-action {
  color: #f56c6c;
}

.qb-prefs__form {
  max-width: 480px;
}

.qb-empty {
  text-align: center;
  padding: 28px 12px;

  h4 {
    margin: 8px 0 4px;
    font-size: 14px;
  }

  p {
    margin: 0;
    font-size: 12px;
    opacity: 0.65;
  }

  &--compact {
    padding: 14px 8px;
  }
}

.matching-body {
  max-height: 420px;
  overflow-y: auto;
}

.matching-group {
  margin-bottom: 12px;

  &__path {
    font-size: 12px;
    font-weight: 600;
    opacity: 0.75;
    margin-bottom: 4px;
    word-break: break-all;
  }
}

.matching-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 0 5px 10px;
  font-size: 13px;
  border-bottom: 1px dashed rgba(128, 128, 128, 0.15);

  &__title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__time {
    flex-shrink: 0;
    font-size: 12px;
    opacity: 0.6;
  }
}

.preview-empty {
  text-align: center;
  padding: 36px 0;
  opacity: 0.65;

  p {
    margin: 0;
  }

  .empty-desc {
    font-size: 12px;
  }
}

.articles-body {
  padding: 0 18px 18px;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.articles-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.15);
  margin-bottom: 8px;
}

.articles-list {
  flex: 1;
  overflow-y: auto;
}

.qb-article {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.12);

  &.is-read {
    opacity: 0.55;
  }

  &__main {
    min-width: 0;
    flex: 1;
  }

  &__title {
    font-size: 13px;
    line-height: 1.4;
    word-break: break-all;
  }

  &__meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 3px;
    font-size: 12px;
    opacity: 0.6;
  }

  &__link {
    color: inherit;
    display: inline-flex;
    align-items: center;
  }
}

@media (max-width: 780px) {
  .qb-header {
    flex-direction: column;
    align-items: stretch;
  }

  .qb-tree-node {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;

    &__actions {
      flex-wrap: wrap;
    }
  }
}
</style>
