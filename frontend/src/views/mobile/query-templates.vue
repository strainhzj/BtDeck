<template>
  <div class="m-templates">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div class="m-toolbar">
      <el-input
        v-model="nameFilter"
        size="small"
        placeholder="筛选模板名称"
        clearable
        prefix-icon="el-icon-search"
      />
      <el-select v-model="sourceFilter" size="small" placeholder="全部类型" clearable>
        <el-option label="简单查询" value="simple" />
        <el-option label="高级搜索" value="advanced" />
      </el-select>
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="load">刷新</el-button>
    </div>

    <div v-if="!loading && filteredList.length === 0" class="m-hint">
      {{ list.length === 0 ? '暂无查询模板' : '没有匹配的模板' }}
    </div>

    <div v-for="tpl in filteredList" :key="tpl.id" class="m-tpl-card">
      <div class="m-tpl-head">
        <span class="m-tpl-name" :title="tpl.name">{{ tpl.name }}</span>
        <el-tag v-if="tpl.is_default" size="mini" type="warning">系统</el-tag>
        <el-tag v-else-if="tpl.is_public" size="mini" type="info">公开</el-tag>
      </div>
      <div class="m-tpl-tags">
        <el-tag size="mini" :type="sourceOf(tpl) === 'advanced' ? 'primary' : 'success'" effect="plain">
          {{ sourceOf(tpl) === 'advanced' ? '高级搜索' : '简单查询' }}
        </el-tag>
        <span class="m-tpl-meta-text">使用 {{ tpl.usage_count }} 次</span>
        <span class="m-tpl-meta-text">{{ formatTime(tpl.updated_time || tpl.created_time) }}</span>
      </div>
      <div v-if="tpl.description" class="m-tpl-desc">{{ tpl.description }}</div>
      <div class="m-tpl-actions">
        <el-button size="mini" type="primary" plain :loading="applyingId === tpl.id" @click="apply(tpl)">
          应用
        </el-button>
        <el-button
          v-if="!tpl.is_default"
          size="mini"
          type="danger"
          plain
          :disabled="applyingId === tpl.id"
          @click="remove(tpl)"
        >
          删除
        </el-button>
      </div>
    </div>

    <div class="m-tpl-footnote">
      高级模板的新建与编辑可在「高级搜索」页已保存搜索中操作；简单模板请回种子页筛选后在桌面版保存
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getSearchTemplates,
  deleteSearchTemplate,
  SearchTemplate
} from '@/api/torrents'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { setAppliedTemplateConditions } from '@/views/mobile/m2-template-cache'

/**
 * 移动查询模板（Phase 4 M2）：复用 /advanced-search/search-templates API；
 * 与桌面页一致做客户端名称/类型过滤。「应用」把 conditions 交给执行页
 * （简单模板→种子页筛选回填，高级模板→高级搜索页回填构建器）；
 * 系统模板（is_default）只可应用不可删除，与桌面判定一致。
 */
@Component({
  name: 'MobileQueryTemplates',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileQueryTemplates extends Mixins(PullToRefresh) {
  private list: SearchTemplate[] = []
  private loading = false
  private applyingId = ''
  private nameFilter = ''
  private sourceFilter = ''

  mounted(): void {
    this.load()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.load()
  }

  private get filteredList(): SearchTemplate[] {
    return this.list.filter((tpl) => {
      if (this.nameFilter && !tpl.name.includes(this.nameFilter)) return false
      if (this.sourceFilter && this.sourceOf(tpl) !== this.sourceFilter) return false
      return true
    })
  }

  private sourceOf(tpl: SearchTemplate): string {
    return tpl.conditions?.source ?? 'simple'
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getSearchTemplates()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.list = res.data
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private apply(tpl: SearchTemplate): void {
    if (!tpl.conditions) {
      this.$message.error('模板条件缺失，无法应用')
      return
    }
    this.applyingId = tpl.id
    setAppliedTemplateConditions(tpl.conditions, tpl.name)
    // 简单模板回种子页筛选执行（简单搜索已迁入 /m/torrents），高级模板进高级搜索页
    const target = (tpl.conditions.source ?? 'simple') === 'advanced' ? '/m/search' : '/m/torrents'
    this.$router.push(target).catch(() => undefined)
  }

  private remove(tpl: SearchTemplate): void {
    this.$confirm(`删除模板「${tpl.name}」？该操作不可恢复。`, '删除确认', { type: 'warning' })
      .then(async() => {
        try {
          const res = await deleteSearchTemplate(tpl.id)
          if (res.code === '200') {
            this.$message.success('模板已删除')
            await this.load()
          }
        } catch (e) {
          this.$message.error(extractErrorMessage(e))
        }
      })
      .catch(() => undefined)
  }

  private formatTime(value: string | null): string {
    if (!value) return '-'
    return value.replace('T', ' ').slice(0, 16)
  }
}
</script>

<style scoped>
.m-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.m-toolbar .el-input {
  flex: 1;
}

.m-toolbar .el-select {
  width: 108px;
  flex-shrink: 0;
}

.m-tpl-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-tpl-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.m-tpl-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-tpl-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.m-tpl-meta-text {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.m-tpl-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.m-tpl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.m-tpl-actions .el-button {
  margin-left: 0;
  padding: 5px 12px;
}

.m-tpl-footnote {
  margin-top: 14px;
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
