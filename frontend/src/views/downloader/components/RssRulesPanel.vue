<template>
  <div class="rss-rules-panel">
    <!-- 工具栏 -->
    <div class="rules-toolbar">
      <div class="rules-toolbar__title">
        <LucideIcon name="wand-sparkles" :size="14" />
        <span>{{ $t('downloader.rss.rulesSectionTitle') }}</span>
      </div>
      <div class="rules-toolbar__actions">
        <span class="rules-toolbar__desc">{{ $t('downloader.rss.rulesSectionDesc') }}</span>
        <el-button size="mini" :disabled="loading" @click="loadRules">
          <LucideIcon name="rotate-ccw" :size="12" />
        </el-button>
        <el-button type="primary" size="mini" @click="openCreateDialog">
          <LucideIcon name="plus" :size="13" />
          {{ $t('downloader.rss.addRule') }}
        </el-button>
      </div>
    </div>

    <!-- 规则表格 -->
    <div v-loading="loading" class="rules-table">
      <template v-if="rules.length > 0">
        <el-table :data="rules" size="mini" style="width: 100%;">
          <el-table-column :label="$t('downloader.rss.ruleName')" min-width="130">
            <template slot-scope="{row}">
              <span class="rule-name" :title="row.name">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.includeKeywords')" min-width="170">
            <template slot-scope="{row}">
              <div class="keyword-tags">
                <el-tag v-for="kw in splitKeywords(row.includeKeywords)" :key="'i-' + kw" size="mini" class="kw-tag kw-tag--include">{{ kw }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.excludeKeywords')" min-width="130">
            <template slot-scope="{row}">
              <div v-if="splitKeywords(row.excludeKeywords).length" class="keyword-tags">
                <el-tag v-for="kw in splitKeywords(row.excludeKeywords)" :key="'e-' + kw" size="mini" type="danger" class="kw-tag">{{ kw }}</el-tag>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.ruleFeeds')" min-width="120">
            <template slot-scope="{row}">
              <span v-if="!row.feedIds.length" class="scope-all">{{ $t('downloader.rss.ruleFeedsAll') }}</span>
              <span v-else :title="feedNamesOf(row.feedIds)">{{ feedNamesOf(row.feedIds) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.ruleTarget')" min-width="110">
            <template slot-scope="{row}">
              <span>{{ targetLabel(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.enabled')" width="60" align="center">
            <template slot-scope="{row}">
              <el-switch :value="row.enabled" @change="value => handleToggleEnabled(row, value)" />
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.matchCount')" width="75" align="center">
            <template slot-scope="{row}">
              <span class="match-count">{{ row.matchCount || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('downloader.rss.actions')" width="170" align="center">
            <template slot-scope="{row}">
              <el-button size="mini" type="text" @click="openPreview(row)">
                <LucideIcon name="search" :size="12" />
                {{ $t('downloader.rss.previewRule') }}
              </el-button>
              <el-button size="mini" type="text" @click="openEditDialog(row)">{{ $t('downloader.rss.editRule') }}</el-button>
              <el-button size="mini" type="text" class="danger-action" @click="handleDeleteRule(row)">
                {{ $t('downloader.rss.deleteFeed') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="total > pageSize"
          class="rules-pagination"
          layout="total, prev, pager, next"
          :current-page.sync="page"
          :page-size="pageSize"
          :total="total"
          @current-change="loadRules"
        />
      </template>
      <div v-else-if="!loading" class="rules-empty">
        <LucideIcon name="wand-sparkles" :size="32" :stroke-width="1.4" class="empty-icon" />
        <h4>{{ $t('downloader.rss.emptyRules') }}</h4>
        <p>{{ $t('downloader.rss.emptyRulesDesc') }}</p>
      </div>
    </div>

    <!-- 新增/编辑规则弹窗 -->
    <el-dialog
      :title="editingRule ? $t('downloader.rss.editRule') : $t('downloader.rss.addRule')"
      :visible.sync="dialogVisible"
      width="560px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form ref="ruleForm" :model="form" :rules="formRules" label-width="110px" size="small">
        <el-form-item :label="$t('downloader.rss.ruleName')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('downloader.rss.ruleNamePlaceholder')" maxlength="200" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.includeKeywords')" prop="includeKeywords">
          <el-input v-model="form.includeKeywords" :placeholder="$t('downloader.rss.includeKeywordsPlaceholder')" />
          <div v-if="form.useRegex" class="form-hint">{{ $t('downloader.rss.useRegex') }} · re.search / i</div>
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.excludeKeywords')">
          <el-input v-model="form.excludeKeywords" :placeholder="$t('downloader.rss.excludeKeywordsPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.useRegex')">
          <el-switch v-model="form.useRegex" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.ruleFeeds')">
          <el-select
            v-model="form.feedIds"
            multiple
            collapse-tags
            clearable
            filterable
            :placeholder="$t('downloader.rss.ruleFeedsPlaceholder')"
            style="width: 100%;"
          >
            <el-option v-for="feed in feeds" :key="feed.feedId" :label="feed.name" :value="feed.feedId" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.ruleTarget')">
          <el-select v-model="form.targetDownloaderId" clearable style="width: 100%;" :placeholder="$t('downloader.rss.ruleTargetDefault')">
            <el-option
              v-for="item in downloaderOptions"
              :key="item.downloaderId"
              :label="optionLabel(item)"
              :value="item.downloaderId"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.savePath')">
          <el-input v-model="form.savePath" :placeholder="$t('downloader.rss.savePathPlaceholder')" maxlength="500" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.tagsLabel')">
          <el-input v-model="form.tags" :placeholder="$t('downloader.rss.tagsPlaceholder')" maxlength="200" />
        </el-form-item>
        <el-form-item :label="$t('downloader.rss.enabled')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="dialogVisible = false">{{ $t('downloader.rss.cancel') }}</el-button>
        <el-button type="primary" size="small" :loading="submitting" @click="handleSubmit">{{ $t('common.confirm') }}</el-button>
      </div>
    </el-dialog>

    <!-- 匹配预览抽屉 -->
    <el-drawer
      :title="`${$t('downloader.rss.rulePreviewTitle')} · ${previewRule ? previewRule.name : ''}`"
      :visible.sync="previewVisible"
      size="480px"
      :with-header="true"
      append-to-body
    >
      <div v-loading="previewLoading" class="preview-body">
        <template v-if="previewArticles.length > 0">
          <div v-if="previewTruncated" class="preview-truncated">{{ $t('downloader.rss.rulePreviewTruncated') }}</div>
          <div v-for="item in previewArticles" :key="item.articleId" class="preview-item">
            <div class="preview-item__title" :title="item.title">{{ item.title }}</div>
            <div class="preview-item__meta">
              <span>{{ item.feedName || '—' }}</span>
              <span>{{ item.publishedAt || item.fetchedAt || '' }}</span>
            </div>
          </div>
        </template>
        <div v-else-if="!previewLoading" class="preview-empty">
          <p>{{ $t('downloader.rss.rulePreviewEmpty') }}</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script lang="ts">
import { ElForm } from 'element-ui'
import { Message, MessageBox } from 'element-ui'
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'
import { extractErrorMessage } from '@/utils/formatters'
import { getList } from '@/api/downloader'
import {
  RssFeed,
  RssRule,
  RssRulePreviewArticle,
  createRssRule,
  deleteRssRule,
  getRssFeeds,
  getRssRules,
  previewRssRule,
  updateRssRule
} from '@/api/rss'
import { Downloader } from '@/views/downloader/types'

interface RuleFormState {
  name: string
  includeKeywords: string
  excludeKeywords: string
  useRegex: boolean
  feedIds: string[]
  targetDownloaderId: string
  savePath: string
  tags: string
  enabled: boolean
}

@Component({
  name: 'RssRulesPanel',
  components: { LucideIcon }
})
export default class RssRulesPanel extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null

  private rules: RssRule[] = []
  private loading = false
  private page = 1
  private pageSize = 20
  private total = 0

  private feeds: RssFeed[] = []
  private downloaderOptions: Downloader[] = []

  private dialogVisible = false
  private submitting = false
  private editingRule: RssRule | null = null
  private form: RuleFormState = {
    name: '',
    includeKeywords: '',
    excludeKeywords: '',
    useRegex: false,
    feedIds: [],
    targetDownloaderId: '',
    savePath: '',
    tags: '',
    enabled: true
  }

  private previewVisible = false
  private previewLoading = false
  private previewRule: RssRule | null = null
  private previewArticles: RssRulePreviewArticle[] = []
  private previewTruncated = false

  private get formRules(): Record<string, unknown[]> {
    return {
      name: [{ required: true, message: this.$t('downloader.rss.ruleName').toString(), trigger: 'blur' }],
      includeKeywords: [
        { required: true, message: this.$t('downloader.rss.includeKeywords').toString(), trigger: 'blur' }
      ]
    }
  }

  mounted() {
    if (this.downloader) {
      this.loadRules()
    }
  }

  @Watch('downloader')
  onDownloaderChanged(value: Downloader | null) {
    if (value) {
      this.page = 1
      this.loadRules()
    } else {
      this.rules = []
      this.total = 0
    }
  }

  private async loadRules(): Promise<void> {
    if (!this.downloader) return
    this.loading = true
    try {
      const response = await getRssRules({
        downloaderId: this.downloader.downloaderId,
        page: this.page,
        pageSize: this.pageSize
      })
      this.rules = response.data.list
      this.total = response.data.total
      if (this.feeds.length === 0) {
        await this.loadFeeds()
      }
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.loading = false
    }
  }

  private async loadFeeds(): Promise<void> {
    if (!this.downloader) return
    try {
      const response = await getRssFeeds({ downloaderId: this.downloader.downloaderId, page: 1, pageSize: 100 })
      this.feeds = response.data.list
    } catch {
      this.feeds = []
    }
  }

  private async ensureDownloaderOptions(): Promise<void> {
    if (this.downloaderOptions.length > 0) return
    try {
      const response = await getList({})
      this.downloaderOptions = (response.data as Downloader[]).filter(
        (item: Downloader) => item.downloaderType === 0 || item.downloaderType === 1
      )
    } catch {
      this.downloaderOptions = []
    }
  }

  private splitKeywords(raw: string | null): string[] {
    return (raw || '')
      .split(',')
      .map(part => part.trim())
      .filter(part => part.length > 0)
      .slice(0, 5)
  }

  private feedNamesOf(feedIds: string[]): string {
    const names = feedIds
      .map(id => (this.feeds.find(feed => feed.feedId === id) || {}).name)
      .filter((name): name is string => Boolean(name))
    return names.length ? names.join(', ') : '—'
  }

  private targetLabel(rule: RssRule): string {
    if (!rule.targetDownloaderId) {
      return this.$t('downloader.rss.ruleTargetDefault').toString()
    }
    const target = this.downloaderOptions.find(item => item.downloaderId === rule.targetDownloaderId)
    return target ? this.optionLabel(target) : rule.targetDownloaderId
  }

  private optionLabel(item: Downloader): string {
    return `${item.nickname} (${item.downloaderTypeName || ''})`
  }

  private openCreateDialog() {
    this.editingRule = null
    this.form = {
      name: '',
      includeKeywords: '',
      excludeKeywords: '',
      useRegex: false,
      feedIds: [],
      targetDownloaderId: '',
      savePath: '',
      tags: '',
      enabled: true
    }
    this.dialogVisible = true
    this.ensureDownloaderOptions()
    this.$nextTick(() => {
      const form = this.$refs.ruleForm as ElForm | undefined
      form?.clearValidate()
    })
  }

  private openEditDialog(rule: RssRule) {
    this.editingRule = rule
    this.form = {
      name: rule.name,
      includeKeywords: rule.includeKeywords,
      excludeKeywords: rule.excludeKeywords || '',
      useRegex: rule.useRegex,
      feedIds: [...rule.feedIds],
      targetDownloaderId: rule.targetDownloaderId || '',
      savePath: rule.savePath || '',
      tags: rule.tags || '',
      enabled: rule.enabled
    }
    this.dialogVisible = true
    this.ensureDownloaderOptions()
    this.$nextTick(() => {
      const form = this.$refs.ruleForm as ElForm | undefined
      form?.clearValidate()
    })
  }

  private async handleSubmit(): Promise<void> {
    const form = this.$refs.ruleForm as ElForm | undefined
    if (form) {
      const valid = await form.validate().catch(() => false)
      if (!valid) return
    }
    if (!this.downloader) return
    this.submitting = true
    try {
      const payload = {
        name: this.form.name.trim(),
        includeKeywords: this.form.includeKeywords.trim(),
        excludeKeywords: this.form.excludeKeywords.trim() || null,
        useRegex: this.form.useRegex,
        feedIds: [...this.form.feedIds],
        targetDownloaderId: this.form.targetDownloaderId || null,
        savePath: this.form.savePath.trim() || null,
        tags: this.form.tags.trim() || null,
        enabled: this.form.enabled
      }
      const response = this.editingRule
        ? await updateRssRule(this.editingRule.ruleId, payload)
        : await createRssRule(this.downloader.downloaderId, payload)
      const backfill = response.data.backfill
      const parts: string[] = []
      if (backfill.pushed > 0) {
        parts.push(this.$t('downloader.rss.backfillPushed', { count: backfill.pushed }).toString())
      }
      if (backfill.skippedMode > 0) {
        parts.push(this.$t('downloader.rss.backfillSkipped', { count: backfill.skippedMode }).toString())
      }
      if (backfill.failed > 0) {
        parts.push(this.$t('downloader.rss.backfillFailed', { count: backfill.failed }).toString())
      }
      Message.success(
        `${this.$t(this.editingRule ? 'downloader.rss.ruleUpdateSuccess' : 'downloader.rss.ruleCreateSuccess').toString()}${parts.length ? ' · ' + parts.join('，') : ''}`
      )
      this.dialogVisible = false
      this.loadRules()
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.submitting = false
    }
  }

  private async handleToggleEnabled(rule: RssRule, value: boolean): Promise<void> {
    try {
      await updateRssRule(rule.ruleId, { enabled: value })
      rule.enabled = value
    } catch (error) {
      Message.error(extractErrorMessage(error))
    }
  }

  private handleDeleteRule(rule: RssRule) {
    MessageBox.confirm(
      this.$t('downloader.rss.ruleDeleteConfirmMsg', { name: rule.name }).toString(),
      this.$t('downloader.rss.ruleDeleteConfirmTitle').toString(),
      { type: 'warning', confirmButtonText: this.$t('common.confirm').toString(), cancelButtonText: this.$t('downloader.rss.cancel').toString() }
    )
      .then(async() => {
        try {
          await deleteRssRule(rule.ruleId)
          Message.success(this.$t('downloader.rss.ruleDeleteSuccess').toString())
          this.loadRules()
        } catch (error) {
          Message.error(extractErrorMessage(error))
        }
      })
      .catch(() => undefined)
  }

  private async openPreview(rule: RssRule): Promise<void> {
    this.previewRule = rule
    this.previewVisible = true
    this.previewLoading = true
    this.previewArticles = []
    this.previewTruncated = false
    try {
      const response = await previewRssRule(rule.ruleId)
      this.previewArticles = response.data.list
      this.previewTruncated = response.data.truncated
    } catch (error) {
      Message.error(extractErrorMessage(error))
    } finally {
      this.previewLoading = false
    }
  }
}
</script>

<style lang="scss" scoped>
.rss-rules-panel {
  margin-top: 18px;
}

.rules-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;

  &__title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    font-size: 14px;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  &__desc {
    font-size: 12px;
    opacity: 0.65;
  }
}

.rules-table {
  min-height: 80px;
}

.rule-name {
  font-weight: 500;
}

.keyword-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.kw-tag {
  &--include {
    background: rgba(64, 158, 255, 0.12);
    border-color: rgba(64, 158, 255, 0.3);
    color: #409eff;
  }
}

.scope-all {
  font-style: italic;
  opacity: 0.7;
}

.muted {
  opacity: 0.5;
}

.match-count {
  font-variant-numeric: tabular-nums;
}

.danger-action {
  color: #f56c6c;
}

.rules-pagination {
  margin-top: 10px;
  text-align: right;
}

.rules-empty {
  text-align: center;
  padding: 26px 12px;
  border: 1px dashed rgba(128, 128, 128, 0.25);
  border-radius: 8px;

  h4 {
    margin: 8px 0 4px;
    font-size: 14px;
  }

  p {
    margin: 0;
    font-size: 12px;
    opacity: 0.65;
  }
}

.form-hint {
  font-size: 12px;
  opacity: 0.6;
  line-height: 1.4;
  margin-top: 2px;
}

.preview-body {
  padding: 0 18px 18px;
}

.preview-truncated {
  font-size: 12px;
  color: #e6a23c;
  margin-bottom: 10px;
}

.preview-item {
  padding: 8px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.15);

  &__title {
    font-size: 13px;
    line-height: 1.4;
    word-break: break-all;
  }

  &__meta {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-top: 3px;
    font-size: 12px;
    opacity: 0.6;
  }
}

.preview-empty {
  text-align: center;
  padding: 40px 0;
  opacity: 0.65;
}

@media (max-width: 780px) {
  .rules-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
