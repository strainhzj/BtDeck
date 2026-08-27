<template>
  <el-dialog
    :visible.sync="dialogVisible"
    :title="isEdit ? '编辑查询模板' : '新建查询模板'"
    width="560px"
    :before-close="handleClose"
  >
    <el-form ref="templateFormRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="模板名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入模板名称" maxlength="100" show-word-limit />
      </el-form-item>
      <el-form-item label="模板描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          placeholder="可选，简要描述模板用途"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="模板类型" prop="source">
        <el-radio-group v-model="form.source" :disabled="isEdit">
          <el-radio label="simple">简单查询</el-radio>
          <el-radio label="advanced">高级搜索</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 简单查询条件 -->
      <div v-if="form.source === 'simple'">
        <el-form-item label="状态筛选">
          <el-select v-model="simpleForm.status" multiple placeholder="选择种子状态（可多选）" style="width: 100%">
            <el-option label="做种中" value="seeding" />
            <el-option label="下载中" value="downloading" />
            <el-option label="已暂停" value="paused" />
            <el-option label="错误" value="error" />
            <el-option label="检查中" value="checking" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称关键词">
          <el-input v-model="simpleForm.name_like" placeholder="种子名称模糊匹配（可选）" />
        </el-form-item>
        <el-form-item label="分类关键词">
          <el-input v-model="simpleForm.category_like" placeholder="分类模糊匹配（可选）" />
        </el-form-item>
        <el-form-item label="标签关键词">
          <el-input v-model="simpleForm.tags_like" placeholder="标签模糊匹配（可选）" />
        </el-form-item>
        <el-form-item label="Tracker域名">
          <AdvancedMultiSelect
            v-model="simpleForm.tracker_domain"
            placeholder="选择tracker域名（可多选）"
            :options="trackerDomainOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :virtual-scroll-threshold="100"
            :list-height="240"
            style="width: 100%;"
          />
        </el-form-item>
        <el-form-item label="排序字段">
          <el-select v-model="simpleForm.sort_by" style="width: 60%">
            <el-option label="添加时间" value="added_date" />
            <el-option label="名称" value="name" />
            <el-option label="大小" value="size" />
          </el-select>
          <el-select v-model="simpleForm.sort_order" style="width: 35%; margin-left: 5%">
            <el-option label="降序" value="desc" />
            <el-option label="升序" value="asc" />
          </el-select>
        </el-form-item>
      </div>

      <!-- 高级搜索提示 -->
      <el-form-item v-else label="">
        <el-alert
          title="高级搜索模板请在「种子管理」页面通过高级搜索面板配置条件后保存"
          type="info"
          :closable="false"
          show-icon
        />
      </el-form-item>

      <el-form-item label="是否公开">
        <el-switch v-model="form.is_public" />
        <span style="margin-left: 10px; color: #909399; font-size: 12px">
          公开模板所有用户可见
        </span>
      </el-form-item>
    </el-form>

    <span slot="footer">
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import AdvancedMultiSelect from '@/components/torrents/AdvancedMultiSelect.vue'
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
        { required: true, message: '请输入模板名称', trigger: 'blur' },
        { min: 1, max: 100, message: '长度在 1 到 100 个字符', trigger: 'blur' }
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
      this.$message.warning('高级搜索模板请在「种子管理」页面通过高级搜索面板保存')
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
          this.$message.success('更新成功')
          this.$emit('success')
        } else {
          this.$message.error(response.msg || '更新失败')
        }
      } else {
        const response = await createSearchTemplate({
          name: this.form.name,
          description: this.form.description,
          conditions,
          is_public: this.form.is_public
        })
        if (response.code === '200') {
          this.$message.success('创建成功')
          this.$emit('success')
        } else {
          this.$message.error(response.msg || '创建失败')
        }
      }
    } catch (error) {
      this.$message.error('保存失败：' + (error as Error).message)
    } finally {
      this.submitting = false
    }
  }
}
</script>
