<template>
  <el-dialog
    title="搜索模板"
    :visible.sync="visible"
    width="700px"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="应用模板" name="apply">
        <el-empty v-if="templates.length === 0" description="暂无保存的模板" />
        <el-list v-else>
          <el-list-item v-for="template in templates" :key="template.id">
            <div class="template-item">
              <div class="template-name">{{ template.name }}</div>
              <div class="template-desc">{{ template.description }}</div>
              <el-button size="small" type="primary" @click="handleApply(template)">应用</el-button>
            </div>
          </el-list-item>
        </el-list>
      </el-tab-pane>

      <el-tab-pane label="保存当前搜索" name="save">
        <el-form :model="form" label-width="100px">
          <el-form-item label="模板名称">
            <el-input v-model="form.name" placeholder="输入模板名称" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" placeholder="输入描述" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <span slot="footer" class="dialog-footer">
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button v-if="activeTab === 'save'" type="primary" @click="handleSave">保存</el-button>
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
      this.$message.warning('请输入模板名称')
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
