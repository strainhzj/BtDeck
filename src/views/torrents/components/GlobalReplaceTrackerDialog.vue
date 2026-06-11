<template>
  <el-dialog
    title="全局替换Tracker"
    :visible.sync="dialogVisible"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-alert
      title="操作说明"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 20px;"
    >
      <template>
        <div>此功能将全局替换所有种子中匹配的tracker地址，操作不可撤销！</div>
        <div style="margin-top: 5px;">请确保您输入的tracker地址正确无误。</div>
      </template>
    </el-alert>

    <el-form :model="form" :rules="rules" ref="form" label-width="140px">
      <el-form-item label="被替换的Tracker" prop="oldTrackerUrl">
        <el-input
          v-model="form.oldTrackerUrl"
          placeholder="输入要被替换的tracker地址，例如: https://tracker.old.com/announce"
          clearable
        />
        <div class="form-tip">
          <i class="el-icon-info"></i>
          将被完全匹配替换的tracker地址
        </div>
      </el-form-item>

      <el-form-item label="新Tracker地址" prop="newTrackerUrl">
        <el-input
          v-model="form.newTrackerUrl"
          placeholder="输入新的tracker地址，例如: https://tracker.new.com/announce"
          clearable
        />
        <div class="form-tip">
          <i class="el-icon-info"></i>
          将用于替换的新tracker地址
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="handleSubmit" :loading="submitting" icon="el-icon-refresh">
          执行替换
        </el-button>
        <el-button @click="handleClose">取消</el-button>
      </el-form-item>
    </el-form>

    <!-- 操作示例 -->
    <el-divider>操作示例</el-divider>
    <div class="example-section">
      <el-steps :active="exampleStep" process-status="success" align-center>
        <el-step title="输入旧tracker" description="https://tracker.old.com/announce"></el-step>
        <el-step title="输入新tracker" description="https://tracker.new.com/announce"></el-step>
        <el-step title="全局替换" description="所有种子自动更新"></el-step>
      </el-steps>
    </div>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { replaceTracker } from '@/api/torrents'

/**
 * 全局替换Tracker对话框组件
 * @description 不需要选择种子，直接根据tracker URL进行全局替换
 */
@Component({
  name: 'GlobalReplaceTrackerDialog'
})
export default class GlobalReplaceTrackerDialog extends Vue {
  @Prop(Boolean) visible!: boolean

  // 对话框显示状态
  private dialogVisible = false
  private submitting = false
  private exampleStep = 0

  // 表单数据
  private form = {
    oldTrackerUrl: '',
    newTrackerUrl: ''
  }

  // URL格式校验正则
  private readonly TRACKER_URL_PATTERN = /^(https?|udp):\/\/[^\s\/$.?#].[^\s]*$/

  /**
   * 表单验证规则
   */
  private get rules() {
    return {
      oldTrackerUrl: [
        { required: true, message: '请输入被替换的tracker地址', trigger: 'blur' },
        {
          validator: (rule: any, value: string, callback: Function) => {
            if (!value || value.trim() === '') {
              callback(new Error('请输入被替换的tracker地址'))
              return
            }
            if (!this.TRACKER_URL_PATTERN.test(value)) {
              callback(new Error('请输入有效的tracker地址格式'))
            } else {
              callback()
            }
          },
          trigger: 'blur'
        }
      ],
      newTrackerUrl: [
        { required: true, message: '请输入新的tracker地址', trigger: 'blur' },
        {
          validator: (rule: any, value: string, callback: Function) => {
            if (!value || value.trim() === '') {
              callback(new Error('请输入新的tracker地址'))
              return
            }
            if (!this.TRACKER_URL_PATTERN.test(value)) {
              callback(new Error('请输入有效的tracker地址格式'))
            } else {
              callback()
            }
          },
          trigger: 'blur'
        }
      ]
    }
  }

  /**
   * 监听visible属性变化
   */
  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.resetForm()
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
   * 重置表单
   */
  private resetForm() {
    this.form.oldTrackerUrl = ''
    this.form.newTrackerUrl = ''
    this.exampleStep = 0
    this.submitting = false

    // 清空表单验证
    this.$nextTick(() => {
      (this.$refs.form as any)?.clearValidate()
    })
  }

  /**
   * 提交替换操作
   */
  private async handleSubmit() {
    const form = this.$refs.form as any

    try {
      await form.validate()
    } catch (error) {
      console.log('表单验证失败:', error)
      return
    }

    this.submitting = true
    this.exampleStep = 1

    try {
      // 注意：后端API参数命名不准确
      // torrentInfoIds实际是被替换的tracker URL
      // trackers实际是目标tracker URL
      const response = await replaceTracker({
        torrentInfoIds: this.form.oldTrackerUrl,
        trackers: this.form.newTrackerUrl
      })

      if (response.code === '200') {
        this.exampleStep = 2
        this.$message.success('全局替换Tracker成功')
        this.$emit('success')
        setTimeout(() => {
          this.handleClose()
        }, 1500)
      } else {
        this.$message.error(response.msg || '全局替换Tracker失败')
        this.exampleStep = 0
      }
    } catch (error: any) {
      console.error('全局替换Tracker失败:', error)
      if (error !== 'cancel') {
        // 修复：显示实际的错误消息，而不是硬编码
        this.$message.error(error.message || '全局替换Tracker失败')
      }
      this.exampleStep = 0
    } finally {
      this.submitting = false
    }
  }

  /**
   * 关闭对话框
   */
  private handleClose() {
    this.resetForm()
    this.dialogVisible = false
  }
}
</script>

<style lang="scss" scoped>
.form-tip {
  margin-top: 5px;
  font-size: 12px;
  color: #909399;

  i {
    margin-right: 4px;
  }
}

.example-section {
  margin-top: 20px;
  padding: 20px;
  background-color: #f5f7fa;
  border-radius: 4px;

  ::v-deep .el-step__title {
    font-size: 14px;
  }

  ::v-deep .el-step__description {
    font-size: 12px;
  }
}
</style>
