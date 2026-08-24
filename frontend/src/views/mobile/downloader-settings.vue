<template>
  <div class="m-dl-settings">
    <div v-if="!downloader && !loadFailed" class="m-hint">加载下载器信息…</div>
    <div v-else-if="!downloader" class="m-detail-empty">
      <div class="m-hint">未找到下载器（可能已被删除）</div>
      <el-button size="small" @click="back">返回</el-button>
    </div>
    <!--
      复用桌面 DownloaderSettingsDialog（visible + downloader 契约，append-to-body
      width 94% top 0，天然贴近全屏）：内部自带 basic/speed/pathManagement/
      tagManagement 页签的取数、归一化与保存编排，移动端零重复实现。
    -->
    <downloader-settings-dialog
      v-if="downloader"
      :visible="dialogVisible"
      :downloader="downloader"
      @update:visible="onDialogVisibleChange"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { getList } from '@/api/downloader'
import DownloaderSettingsDialog from '@/views/downloader/components/DownloaderSettingsDialog.vue'
import { extractErrorMessage } from '@/utils/formatters'
import { Downloader } from '@/views/downloader/types'

/**
 * 移动下载器设置页（Phase 4 M2）：整页复用桌面设置对话框（fullscreen 近似形态），
 * 覆盖基本设置/速度设置(含分时段调度)/路径维护/标签管理全部能力；
 * 关闭对话框即返回移动下载器页。
 */
@Component({
  name: 'MobileDownloaderSettings',
  components: { 'downloader-settings-dialog': DownloaderSettingsDialog }
})
export default class MobileDownloaderSettings extends Vue {
  private downloader: Downloader | null = null
  private dialogVisible = true
  private loadFailed = false

  mounted(): void {
    this.load()
  }

  private async load(): Promise<void> {
    try {
      const res = await getList({ page: 1, pageSize: 100 })
      if (res.code === '200' && Array.isArray(res.data)) {
        const id = String(this.$route.params.id || '')
        this.downloader = res.data.find(
          (d: Downloader) => String(d.id) === id || String(d.downloaderId) === id
        ) ?? null
        if (!this.downloader) this.loadFailed = true
      }
    } catch (e) {
      this.loadFailed = true
      this.$message.error(extractErrorMessage(e))
    }
  }

  private onDialogVisibleChange(visible: boolean): void {
    if (!visible) this.back()
  }

  private back(): void {
    this.$router.replace('/m/downloader').catch(() => undefined)
  }
}
</script>

<style scoped>
.m-dl-settings {
  min-height: 60vh;
}

.m-detail-empty {
  text-align: center;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>

<!-- 设置对话框挂 body（append-to-body），窄视口下压缩内边距提升可用性 -->
<style>
@media (max-width: 768px) {
  .downloader-settings-dialog {
    width: 100% !important;
  }

  .downloader-settings-dialog .el-dialog__body {
    padding: 10px 8px;
  }
}
</style>
