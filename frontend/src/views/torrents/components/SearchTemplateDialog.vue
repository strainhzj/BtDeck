<template>
  <el-dialog
    :title="$t('search.templateDialog.title')"
    :visible.sync="visible"
    width="700px"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="$t('search.templateDialog.applyTab')" name="apply">
        <el-empty v-if="templates.length === 0" :description="$t('search.templateDialog.empty')" />
        <el-list v-else>
          <el-list-item v-for="template in templates" :key="template.id">
            <div class="template-item">
              <div class="template-name">{{ template.name }}</div>
              <div class="template-desc">{{ template.description }}</div>
              <el-button size="small" type="primary" @click="handleApply(template)">{{ $t('search.templateDialog.apply') }}</el-button>
            </div>
          </el-list-item>
        </el-list>
      </el-tab-pane>

      <el-tab-pane :label="$t('search.templateDialog.saveTab')" name="save">
        <el-form :model="form" label-width="100px">
          <el-form-item :label="$t('search.templateDialog.nameLabel')">
            <el-input v-model="form.name" :placeholder="$t('search.templateDialog.namePlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('search.templateDialog.descLabel')">
            <el-input v-model="form.description" type="textarea" :placeholder="$t('search.templateDialog.descPlaceholder')" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <span slot="footer" class="dialog-footer">
      <el-button @click="$emit('update:visible', false)">{{ $t('common.cancel') }}</el-button>
      <el-button v-if="activeTab === 'save'" type="primary" @click="handleSave">{{ $t('search.templateDialog.save') }}</el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

interface SearchTemplate {
  id?: string
  name: string
  description: string
  conditions: any
}

@Component
export default class SearchTemplateDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Array) templates!: SearchTemplate[]

  private activeTab = 'apply'
  private form = {
    name: '',
    description: ''
  }

  handleApply(template: SearchTemplate) {
    this.$emit('apply', template)
  }

  handleSave() {
    if (!this.form.name) {
      this.$message.warning(this.$t('search.templateDialog.nameRequired').toString())
      return
    }
    this.$emit('save', this.form)
    this.form = { name: '', description: '' }
  }
}
</script>

<style scoped>
.template-item {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.template-name {
  font-weight: bold;
}

.template-desc {
  flex: 1;
  color: #999;
  font-size: 12px;
}
</style>
