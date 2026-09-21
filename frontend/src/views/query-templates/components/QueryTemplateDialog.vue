<template>
  <el-dialog
    :visible.sync="dialogVisible"
    :title="isEdit ? $t('queryTemplate.dialog.editTitle') : $t('queryTemplate.dialog.createTitle')"
    width="560px"
    :before-close="handleClose"
  >
    <el-form ref="templateFormRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item :label="$t('queryTemplate.dialog.nameLabel')" prop="name">
        <el-input v-model="form.name" :placeholder="$t('queryTemplate.dialog.namePlaceholder')" maxlength="100" show-word-limit />
      </el-form-item>
      <el-form-item :label="$t('queryTemplate.dialog.descLabel')" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          :placeholder="$t('queryTemplate.dialog.descPlaceholder')"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
      <el-form-item :label="$t('queryTemplate.dialog.typeLabel')" prop="source">
        <el-radio-group v-model="form.source" :disabled="isEdit">
          <el-radio label="simple">{{ $t('queryTemplate.dialog.simple') }}</el-radio>
          <el-radio label="advanced">{{ $t('queryTemplate.dialog.advanced') }}</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 简单查询条件 -->
      <div v-if="form.source === 'simple'">
        <el-form-item :label="$t('queryTemplate.dialog.statusFilter')">
          <el-select v-model="simpleForm.status" multiple :placeholder="$t('queryTemplate.dialog.statusPlaceholder')" style="width: 100%">
            <el-option :label="$t('torrent.status.seeding')" value="seeding" />
            <el-option :label="$t('torrent.status.downloading')" value="downloading" />
            <el-option :label="$t('torrent.status.paused')" value="paused" />
            <el-option :label="$t('torrent.status.error')" value="error" />
            <el-option :label="$t('torrent.status.checking')" value="checking" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('queryTemplate.dialog.nameLike')">
          <el-input v-model="simpleForm.name_like" :placeholder="$t('queryTemplate.dialog.nameLikePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('queryTemplate.dialog.categoryLike')">
          <el-input v-model="simpleForm.category_like" :placeholder="$t('queryTemplate.dialog.categoryLikePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('queryTemplate.dialog.tagsLike')">
          <el-input v-model="simpleForm.tags_like" :placeholder="$t('queryTemplate.dialog.tagsLikePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('queryTemplate.dialog.trackerDomain')">
          <AdvancedMultiSelect
            v-model="simpleForm.tracker_domain"
            :placeholder="$t('queryTemplate.dialog.trackerDomainPlaceholder')"
            :options="trackerDomainOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :virtual-scroll-threshold="100"
            :list-height="240"
            style="width: 100%;"
          />
        </el-form-item>
        <el-form-item :label="$t('queryTemplate.dialog.sortBy')">
          <el-select v-model="simpleForm.sort_by" style="width: 60%">
            <el-option :label="$t('queryTemplate.dialog.sortAddedDate')" value="added_date" />
            <el-option :label="$t('queryTemplate.dialog.sortName')" value="name" />
            <el-option :label="$t('queryTemplate.dialog.sortSize')" value="size" />
          </el-select>
          <el-select v-model="simpleForm.sort_order" style="width: 35%; margin-left: 5%">
            <el-option :label="$t('queryTemplate.dialog.sortDesc')" value="desc" />
            <el-option :label="$t('queryTemplate.dialog.sortAsc')" value="asc" />
          </el-select>
        </el-form-item>
      </div>

      <!-- 高级搜索提示 -->
      <el-form-item v-else label="">
        <el-alert
          :title="$t('queryTemplate.dialog.advancedHint')"
          type="info"
          :closable="false"
          show-icon
        />
      </el-form-item>

      <el-form-item :label="$t('queryTemplate.dialog.isPublic')">
        <el-switch v-model="form.is_public" />
        <span style="margin-left: 10px; color: #909399; font-size: 12px">
          {{ $t('queryTemplate.dialog.publicHint') }}
        </span>
      </el-form-item>
    </el-form>

    <span slot="footer">
      <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? $t('queryTemplate.dialog.saveBtn') : $t('queryTemplate.dialog.createBtn') }}
      </el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import AdvancedMultiSelect from '@/components/torrents/AdvancedMultiSelect.vue'
import { apiErrorMessage, apiResponseMessage } from '@/i18n'
import type { SelectOption } from '@/components/torrents/AdvancedMultiSelect.vue'
import {
  createSearchTemplate,
  updateSearchTemplate,
  getTrackerDomains,
  SearchTemplate,
  QueryTemplateConditions
} from '@/api/torrents'

@Component({
  name: 'QueryTemplateDialog',
  components: {
    AdvancedMultiSelect
  }
})
export default class QueryTemplateDialog extends Vue {
  @Prop({ type: Boolean, default: false }) visible!: boolean
  @Prop({ type: Object, default: null }) template!: SearchTemplate | null

  private dialogVisible = false
  private submitting = false

  private form = {
    name: '',
    description: '',
    source: 'simple' as 'simple' | 'advanced',
    is_public: false
  }

  private simpleForm = {
    status: [] as string[],
    name_like: '',
    category_like: '',
    tags_like: '',
    tracker_domain: [] as string[],
    showActiveOnly: false,  // 活动种子开关（H2修复：编辑保存不覆写，保持存取对称）
    sort_by: 'added_date',
    sort_order: 'desc' as 'asc' | 'desc'
  }

  private trackerDomainList: string[] = []

  get isEdit(): boolean {
    return this.template !== null
  }

  get rules() {
    return {
      name: [
        { required: true, message: this.$t('queryTemplate.dialog.rules.nameRequired'), trigger: 'blur' },
        { min: 1, max: 100, message: this.$t('queryTemplate.dialog.rules.lengthRange'), trigger: 'blur' }
      ]
    }
  }

  get trackerDomainOptions(): SelectOption[] {
    return this.trackerDomainList.map(domain => ({
      label: domain,
      value: domain
    }))
  }

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.resetForm()
      this.loadTrackerDomainOptions()
    }
  }

  @Watch('dialogVisible')
  onDialogVisibleChange(val: boolean) {
    this.$emit('update:visible', val)
  }

  private resetForm() {
    if (this.template) {
      // 编辑模式：回填
      this.form.name = this.template.name
      this.form.description = this.template.description || ''
      this.form.is_public = this.template.is_public
      const conditions = this.template.conditions as QueryTemplateConditions
      this.form.source = conditions?.source || 'simple'
      if (conditions?.source === 'simple' && conditions.listQuery) {
        this.simpleForm.status = conditions.listQuery.status ? [...conditions.listQuery.status] : []
        this.simpleForm.name_like = conditions.listQuery.name_like || ''
        this.simpleForm.category_like = conditions.listQuery.category_like || ''
        this.simpleForm.tags_like = conditions.listQuery.tags_like || ''
        this.simpleForm.tracker_domain = conditions.listQuery.tracker_domain
          ? [...conditions.listQuery.tracker_domain]
          : []
        // H2修复：回填活动种子开关，避免编辑保存时被 buildConditions 覆写为 false
        this.simpleForm.showActiveOnly = conditions.listQuery.showActiveOnly ?? false
        this.simpleForm.sort_by = conditions.listQuery.sort_by || 'added_date'
        this.simpleForm.sort_order = conditions.listQuery.sort_order || 'desc'
      }
    } else {
      // 创建模式：默认值
      this.form = {
        name: '',
        description: '',
        source: 'simple',
        is_public: false
      }
      this.simpleForm = {
        status: [],
        name_like: '',
        category_like: '',
        tags_like: '',
        tracker_domain: [],
        showActiveOnly: false,
        sort_by: 'added_date',
        sort_order: 'desc'
      }
    }
  }

  private async loadTrackerDomainOptions() {
    if (this.trackerDomainList.length > 0) return
    try {
      const response = await getTrackerDomains()
      if (response.code === '200' && Array.isArray(response.data)) {
        this.trackerDomainList = response.data
      }
    } catch (error) {
      console.error('获取 Tracker 主域名失败:', error)
    }
  }

  private buildConditions(): QueryTemplateConditions {
    if (this.form.source === 'simple') {
      return {
        source: 'simple',
        version: 1,
        listQuery: {
          name_like: this.simpleForm.name_like,
          category_like: this.simpleForm.category_like,
          tags_like: this.simpleForm.tags_like,
          downloader_id: [],
          status: [...this.simpleForm.status],
          tracker_domain: [...this.simpleForm.tracker_domain],
          showActiveOnly: this.simpleForm.showActiveOnly,
          sort_by: this.simpleForm.sort_by,
          sort_order: this.simpleForm.sort_order
        }
      }
    }
    // advanced：编辑时不允许改类型，新建时返回空骨架（实际条件从种子页保存）
    return {
      source: 'advanced',
      version: 1,
      condition_groups: []
    }
  }

  private handleClose() {
    this.dialogVisible = false
  }

  private async handleSubmit() {
    const formRef = this.$refs.templateFormRef as ElForm
    if (!formRef) return

    try {
      await formRef.validate()
    } catch {
      return // 校验失败
    }

    // 高级搜索新建不允许（需从种子页保存）
    if (!this.isEdit && this.form.source === 'advanced') {
      this.$message.warning(this.$t('queryTemplate.dialog.advancedFromTorrents'))
      return
    }

    this.submitting = true
    try {
      const conditions = this.buildConditions()
      if (this.isEdit && this.template) {
        const response = await updateSearchTemplate(this.template.id, {
          name: this.form.name,
          description: this.form.description,
          conditions,
          is_public: this.form.is_public
        })
        if (response.code === '200') {
          this.$message.success(this.$t('queryTemplate.dialog.updated'))
          this.$emit('success')
        } else {
          // 双语 P4 错误契约：优先 reasonCode 本地化
          this.$message.error(apiResponseMessage(response, this.$t('queryTemplate.dialog.updateFailed') as string))
        }
      } else {
        const response = await createSearchTemplate({
          name: this.form.name,
          description: this.form.description,
          conditions,
          is_public: this.form.is_public
        })
        if (response.code === '200') {
          this.$message.success(this.$t('queryTemplate.dialog.created'))
          this.$emit('success')
        } else {
          // 双语 P4 错误契约：优先 reasonCode 本地化
          this.$message.error(apiResponseMessage(response, this.$t('queryTemplate.dialog.createFailed') as string))
        }
      }
    } catch (error) {
      // 双语 P4 错误契约：优先 reasonCode 本地化，未契约化路径回退原始 msg
      this.$message.error(apiErrorMessage(error, this.$t('queryTemplate.dialog.saveFailed') as string))
    } finally {
      this.submitting = false
    }
  }
}
</script>
