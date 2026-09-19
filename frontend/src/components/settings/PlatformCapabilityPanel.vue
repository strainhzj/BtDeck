<template>
  <div class="platform-capability-panel">
    <div class="settings-card">
      <h3 class="settings-card-title">{{ $t('settings.capability.title') }}</h3>
      <p class="settings-description">
        {{ $t('settings.capability.platformLabel') }}<strong>{{ platformLabel }}</strong>
        <template v-if="data">
          {{ $t('settings.capability.degradedCount', {degraded: data.degradedCount, unsupported: data.unsupportedCount}) }}
        </template>
        {{ $t('settings.capability.hint') }}
      </p>

      <div v-if="loading" class="capability-hint">{{ $t('settings.capability.loading') }}</div>
      <div v-else-if="!data" class="capability-hint">
        {{ $t('settings.capability.unavailable') }}
      </div>
      <template v-else>
        <!-- 桌面 ≥768px：表格 -->
        <el-table
          v-if="!isNarrow"
          :data="rows"
          size="small"
          class="capability-table"
        >
          <el-table-column prop="label" :label="$t('settings.capability.colCapability')" min-width="240" show-overflow-tooltip />
          <el-table-column :label="$t('settings.capability.colLevel')" width="120">
            <template slot-scope="{row}">
              <el-tag :type="levelTagType(row.level)" size="mini" :effect="row.level === 'supported' ? 'light' : 'plain'">
                {{ levelText(row.level) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('settings.capability.colNote')" min-width="280">
            <template slot-scope="{row}">
              <span v-if="row.note">{{ row.note }}</span>
              <span v-else class="capability-muted">—</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 移动 <768px：卡片列表 -->
        <div v-else class="capability-cards">
          <div v-for="row in rows" :key="row.key" class="capability-card">
            <div class="capability-card-head">
              <span class="capability-card-label">{{ row.label }}</span>
              <el-tag :type="levelTagType(row.level)" size="mini" :effect="row.level === 'supported' ? 'light' : 'plain'">
                {{ levelText(row.level) }}
              </el-tag>
            </div>
            <div v-if="row.note" class="capability-card-note">{{ row.note }}</div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  loadPlatformCapabilities,
  PlatformCapabilitiesData,
  PlatformCapabilityEntry
} from '@/api/platform-capabilities'

interface CapabilityRow {
  key: string
  label: string
  level: PlatformCapabilityEntry['level']
  note?: string
}

/**
 * 主机能力矩阵面板（dual-mode-client Phase 4）：桌面/移动设置页共用
 * （移动 settings.vue 包装桌面页，本 tab 自动同源）。级别与文案全部来自
 * 服务端 /platform/capabilities（单一真相源，不在前端复制矩阵）。
 */
@Component({
  name: 'PlatformCapabilityPanel'
})
export default class extends Vue {
  private data: PlatformCapabilitiesData | null = null
  private loading = true
  private isNarrow = typeof window !== 'undefined' && window.innerWidth < 768

  private get platformLabel(): string {
    // 遗留补译：形态名走 i18n（row.label/row.note 为服务端原文，按契约透传 E03 语义）
    if (!this.data) return this.$t('settings.capability.platformUnknown').toString()
    return this.data.platform === 'android-server'
      ? this.$t('settings.capability.platformAndroidServer').toString()
      : this.$t('settings.capability.platformDesktop').toString()
  }

  private get rows(): CapabilityRow[] {
    if (!this.data) return []
    return Object.entries(this.data.capabilities).map(([key, entry]) => ({
      key,
      label: entry.label,
      level: entry.level,
      note: entry.note
    }))
  }

  private levelTagType(level: PlatformCapabilityEntry['level']): string {
    if (level === 'unsupported') return 'danger'
    if (level === 'degraded') return 'warning'
    return 'success'
  }

  private levelText(level: PlatformCapabilityEntry['level']): string {
    if (level === 'unsupported') return this.$t('settings.capability.levelUnsupported').toString()
    if (level === 'degraded') return this.$t('settings.capability.levelDegraded').toString()
    return this.$t('settings.capability.levelSupported').toString()
  }

  private mounted(): void {
    loadPlatformCapabilities()
      .then(data => {
        this.data = data
      })
      .finally(() => {
        this.loading = false
      })
  }
}
</script>

<style scoped>
.platform-capability-panel {
  width: 100%;
}

.capability-table {
  width: 100%;
}

.capability-muted {
  color: var(--el-text-color-secondary, #909399);
}

.capability-hint {
  color: var(--el-text-color-secondary, #909399);
  padding: 12px 0;
}

.capability-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.capability-card {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 6px;
  padding: 10px 12px;
}

.capability-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.capability-card-label {
  font-size: 13px;
}

.capability-card-note {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
</style>
