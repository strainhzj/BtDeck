<template>
  <el-dialog
    :title="dialogTitle"
    :visible.sync="dialogVisible"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-tabs v-model="activeTab" type="border-card" @tab-click="handleTabChange">

      <!-- Tab 1: 添加Tracker -->
      <el-tab-pane label="添加Tracker" name="add">
        <el-form :model="addForm" :rules="addRules" ref="addForm" label-width="120px">
          <el-form-item label="选中的种子">
            <div v-if="isBatchOperation" class="torrent-list">
              <el-tag
                v-for="torrent in selectedTorrents"
                :key="torrent.info_id"
                type="info"
                size="small"
                style="margin: 5px;"
              >
                {{ torrent.name }}
              </el-tag>
            </div>
            <el-tag v-else type="info">{{ selectedTorrents[0]?.name || '-' }}</el-tag>
          </el-form-item>

          <el-form-item label="Tracker地址" prop="trackers">
            <el-input
              type="textarea"
              :rows="5"
              v-model="addForm.trackers"
              placeholder="多个tracker地址用分号;分隔&#10;例如:&#10;https://tracker1.com/announce&#10;https://tracker2.com/announce"
            />
            <div class="form-tip">
              <i class="el-icon-info"></i>
              支持添加多个tracker地址，每个地址一行或用分号分隔
            </div>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="handleAddSubmit" :loading="submitting">
              {{ isBatchOperation ? `批量添加 (${selectedTorrents.length}个种子)` : '添加Tracker' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- Tab 2: 修改Tracker -->
      <el-tab-pane label="修改Tracker" name="modify">
        <el-form :model="modifyForm" :rules="modifyRules" ref="modifyForm" label-width="120px">
          <el-form-item label="选中的种子">
            <div v-if="isBatchOperation" class="torrent-list">
              <el-tag
                v-for="torrent in selectedTorrents"
                :key="torrent.info_id"
                type="info"
                size="small"
                style="margin: 5px;"
              >
                {{ torrent.name }}
              </el-tag>
            </div>
            <el-tag v-else type="info">{{ selectedTorrents[0]?.name || '-' }}</el-tag>
          </el-form-item>

          <el-form-item label="当前Tracker列表" v-if="currentTrackers.length > 0">
            <el-table :data="currentTrackers" size="small" max-height="200" border>
              <el-table-column prop="tracker_url" label="URL" show-overflow-tooltip min-width="300" />
              <el-table-column label="状态" width="80" align="center">
                <template slot-scope="scope">
                  <el-tag :type="scope.row.last_announce_succeeded === 'True' ? 'success' : 'danger'" size="mini">
                    {{ scope.row.last_announce_succeeded === 'True' ? '正常' : '异常' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-form-item>

          <el-form-item label="新Tracker列表" prop="trackers">
            <el-input
              type="textarea"
              :rows="5"
              v-model="modifyForm.trackers"
              placeholder="多个tracker地址用分号;分隔，将完全替换当前的tracker列表&#10;例如:&#10;https://tracker1.com/announce;https://tracker2.com/announce"
            />
            <div class="form-tip">
              <i class="el-icon-warning"></i>
              <strong>注意：</strong>修改操作将完全替换当前tracker列表，请谨慎操作
            </div>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="handleModifySubmit" :loading="submitting">
              {{ isBatchOperation ? `批量修改 (${selectedTorrents.length}个种子)` : '修改Tracker' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

    </el-tabs>

    <span slot="footer" class="dialog-footer">
      <el-button @click="handleClose">关闭</el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { addTracker, modifyTracker } from '@/api/torrents'
import { Torrent, TrackerInfo } from '@/api/torrents'

/**
 * Tracker操作对话框组件
 * @description 提供tracker的添加、修改功能，支持单种子和批量操作
 */
@Component({
  name: 'TrackerOperationDialog'
})
export default class TrackerOperationDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Array) selectedTorrents!: Torrent[]
  @Prop(String) operationType!: 'add' | 'modify' | ''

  // 对话框显示状态
  private dialogVisible = false
  private activeTab = 'add'
  private submitting = false

  // 当前tracker列表
  private currentTrackers: TrackerInfo[] = []

  // 表单数据
  private addForm = {
    trackers: ''
  }

  private modifyForm = {
    trackers: ''
  }

  // URL格式校验正则
  private readonly TRACKER_URL_PATTERN = /^(https?|udp):\/\/[^\s\/$.?#].[^\s]*$/

  /**
   * 表单验证规则 - 添加Tracker
   */
  private get addRules() {
    return {
      trackers: [
        { required: true, message: '请输入tracker地址', trigger: 'blur' },
        {
          validator: this.validateTrackerUrls,
          trigger: 'blur'
        }
      ]
    }
  }

  /**
   * 表单验证规则 - 修改Tracker
   */
  private get modifyRules() {
    return {
      trackers: [
        { required: true, message: '请输入新的tracker列表', trigger: 'blur' },
        {
          validator: this.validateTrackerUrls,
          trigger: 'blur'
        }
      ]
    }
  }

  /**
   * 是否为批量操作
   */
  get isBatchOperation(): boolean {
    return this.selectedTorrents.length > 1
  }

  /**
   * 对话框标题
   */
  get dialogTitle(): string {
    if (this.isBatchOperation) {
      return `批量Tracker操作 - 已选${this.selectedTorrents.length}个种子`
    } else {
      const torrentName = this.selectedTorrents[0]?.name || '种子'
      return `Tracker操作 - ${torrentName}`
    }
  }

  /**
   * 监听visible属性变化
   */
  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.initializeDialog()
    }
  }

  /**
   * 监听dialogVisible变化
   */
  @Watch('dialogVisible')
  onDialogVisibleChange(val: boolean) {
    this.$emit('update:visible', val)
  }

  /**
   * 初始化对话框
   */
  private initializeDialog() {
    // 设置操作类型对应的Tab
    if (this.operationType) {
      this.activeTab = this.operationType
    }

    // 加载当前tracker列表（仅单种子操作）
    if (!this.isBatchOperation && this.selectedTorrents.length > 0) {
      this.loadCurrentTrackers()
    } else {
      this.currentTrackers = []
    }

    // 重置表单
    this.resetForms()
  }

  /**
   * 加载当前tracker列表
   */
  private loadCurrentTrackers() {
    const torrent = this.selectedTorrents[0]
    if (torrent && torrent.trackerInfo) {
      this.currentTrackers = torrent.trackerInfo
    } else {
      this.currentTrackers = []
    }
  }

  /**
   * 重置所有表单
   * @description 安全地重置表单数据和验证状态，处理el-tabs导致的ref渲染延迟问题
   */
  private resetForms() {
    this.addForm.trackers = ''
    this.modifyForm.trackers = ''

    // 清空表单验证 - 增加安全检查以避免el-tabs渲染延迟导致的ref未定义问题
    this.$nextTick(() => {
      // 检查ref是否存在且是Element UI表单组件
      if (this.$refs.addForm && typeof (this.$refs.addForm as any).clearValidate === 'function') {
        (this.$refs.addForm as any).clearValidate()
      }

      if (this.$refs.modifyForm && typeof (this.$refs.modifyForm as any).clearValidate === 'function') {
        (this.$refs.modifyForm as any).clearValidate()
      }
    })
  }

  /**
   * Tab切换处理
   */
  private handleTabChange(tab: any) {
    console.log('切换到Tab:', tab.name)
  }

  /**
   * Tracker URL格式校验
   */
  private validateTrackerUrls(rule: any, value: string, callback: Function) {
    if (!value || value.trim() === '') {
      callback(new Error('请输入tracker地址'))
      return
    }

    // 支持多个URL，用分号或换行分隔
    const urls = value
      .split(/[;\n]/)
      .map(u => u.trim())
      .filter(u => u.length > 0)

    if (urls.length === 0) {
      callback(new Error('请输入有效的tracker地址'))
      return
    }

    // 验证每个URL格式
    const invalidUrls = urls.filter(url => !this.TRACKER_URL_PATTERN.test(url))
    if (invalidUrls.length > 0) {
      callback(new Error(`以下tracker地址格式不正确: ${invalidUrls.join(', ')}`))
      return
    }

    callback()
  }

  /**
   * 提交添加Tracker
   */
  private async handleAddSubmit() {
    const form = this.$refs.addForm as any
    if (!form) {
      this.$message.error('表单未初始化，请稍后重试')
      return
    }
    
    await form.validate()

    this.submitting = true
    try {
      // 调试：检查selectedTorrents内容和属性
      console.log("=== 添加Tracker调试 ===")
      console.log("selectedTorrents:", this.selectedTorrents)
      console.log("selectedTorrents长度:", this.selectedTorrents.length)
      if (this.selectedTorrents.length > 0) {
        console.log("第一个种子:", this.selectedTorrents[0])
        console.log("所有属性:", Object.keys(this.selectedTorrents[0]))
        console.log("info_id值:", this.selectedTorrents[0].info_id)
        console.log("infoId值:", this.selectedTorrents[0].infoId)
      }
      
      // 兼容两种命名：info_id 和 infoId
      const torrentInfoIds = this.selectedTorrents
        .map(t => t.info_id || t.infoId || "")
        .filter(id => id)
        .join(",")
      console.log("最终torrentInfoIds:", torrentInfoIds)
      
      if (!torrentInfoIds) {
        this.$message.error("未获取到种子ID，请重新选择种子")
        this.submitting = false
        return
      }
      const response = await addTracker({
        torrentInfoIds,
        trackers: this.addForm.trackers
      })

      if (response.code === '200') {
        this.$message.success('添加Tracker成功')
        this.$emit('success')
        this.handleClose()
      } else {
        this.$message.error(response.msg || '添加Tracker失败')
      }
    } catch (error: any) {
      console.error('添加Tracker失败:', error)
      if (error !== 'cancel') {
        // 修复：显示实际的错误消息，而不是硬编码
        this.$message.error(error.message || '添加Tracker失败')
      }
    } finally {
      this.submitting = false
    }
  }

  /**
   * 提交修改Tracker
   */
  private async handleModifySubmit() {
    const form = this.$refs.modifyForm as any
    if (!form) {
      this.$message.error('表单未初始化，请稍后重试')
      return
    }
    
    await form.validate()

    this.submitting = true
    try {
      // 调试：检查selectedTorrents内容和属性
      console.log("=== 修改Tracker调试 ===")
      console.log("selectedTorrents:", this.selectedTorrents)
      console.log("selectedTorrents长度:", this.selectedTorrents.length)
      if (this.selectedTorrents.length > 0) {
        console.log("第一个种子:", this.selectedTorrents[0])
        console.log("所有属性:", Object.keys(this.selectedTorrents[0]))
        console.log("info_id值:", this.selectedTorrents[0].info_id)
        console.log("infoId值:", this.selectedTorrents[0].infoId)
      }
      
      // 兼容两种命名：info_id 和 infoId
      const torrentInfoIds = this.selectedTorrents
        .map(t => t.info_id || t.infoId || "")
        .filter(id => id)
        .join(",")
      console.log("最终torrentInfoIds:", torrentInfoIds)
      
      if (!torrentInfoIds) {
        this.$message.error("未获取到种子ID，请重新选择种子")
        this.submitting = false
        return
      }
      const response = await modifyTracker({
        torrentInfoIds,
        trackers: this.modifyForm.trackers
      })

      if (response.code === '200') {
        this.$message.success('修改Tracker成功')
        this.$emit('success')
        this.handleClose()
      } else {
        this.$message.error(response.msg || '修改Tracker失败')
      }
    } catch (error: any) {
      console.error('修改Tracker失败:', error)
      if (error !== 'cancel') {
        // 修复：显示实际的错误消息，而不是硬编码
        this.$message.error(error.message || '修改Tracker失败')
      }
    } finally {
      this.submitting = false
    }
  }

  /**
   * 关闭对话框
   */
  private handleClose() {
    this.resetForms()
    this.dialogVisible = false
  }
}
</script>

<style lang="scss" scoped>
.torrent-list {
  max-height: 100px;
  overflow-y: auto;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.form-tip {
  margin-top: 5px;
  font-size: 12px;
  color: #909399;

  i {
    margin-right: 4px;
  }

  strong {
    color: #f56c6c;
  }
}
</style>
