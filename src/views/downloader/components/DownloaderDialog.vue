<template>
  <el-dialog
    :title="dialogTitle"
    :visible.sync="visible"
    width="60%"
    :before-close="handleClose"
    :close-on-click-modal="false"
    custom-class="downloader-dialog"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="105px"
      label-position="left"
      v-loading="loading"
    >
      <!-- 表单三列布局（6个字段 = 3列 x 2行） -->
      <!-- label-width 设置为 105px 以容纳"验证用户密码"等较长标签而不换行 -->
      <div class="form-grid">
        <el-form-item label="下载器名称" prop="nickname">
          <el-input
            v-model="formData.nickname"
            placeholder="请输入下载器名称"
          />
        </el-form-item>

        <el-form-item label="主机地址" prop="host">
          <el-input
            v-model="formData.host"
            placeholder="例如: 192.168.1.100"
          />
        </el-form-item>

        <el-form-item label="验证用户名" prop="username">
          <el-input
            v-model="formData.username"
            placeholder="请输入用户名"
          />
        </el-form-item>

        <el-form-item label="验证用户密码" prop="password">
          <el-input
            v-model="formData.password"
            type="password"
            show-password
            placeholder="请输入密码"
          />
        </el-form-item>

        <el-form-item label="端口" prop="port">
          <el-input
            v-model.number="formData.port"
            type="number"
            placeholder="请输入端口号"
          />
        </el-form-item>

        <el-form-item label="下载器类型" prop="downloader_type">
          <el-select
            v-model="formData.downloader_type"
            placeholder="请选择下载器类型"
            style="width: 100%"
          >
            <el-option label="qBittorrent" :value="0" />
            <el-option label="Transmission" :value="1" />
          </el-select>
        </el-form-item>
      </div>

      <!-- 开关行布局 -->
      <div class="switch-row">
        <div class="switch-item">
          <span class="switch-title">启用SSL加密连接</span>
          <el-switch
            v-model="formData.is_ssl"
            active-value="1"
            inactive-value="0"
          />
        </div>

        <div class="switch-item">
          <span class="switch-title">启用搜索功能</span>
          <el-switch
            v-model="formData.is_search"
            active-value="1"
            inactive-value="0"
          />
        </div>

        <div class="switch-item">
          <span class="switch-title">启用下载器</span>
          <el-switch
            v-model="formData.enabled"
            active-value="1"
            inactive-value="0"
          />
        </div>
      </div>
    </el-form>

    <span slot="footer" class="dialog-footer">
      <el-button class="btn-cancel" @click="handleClose">取消</el-button>
      <el-button class="btn-confirm" type="primary" @click="handleSubmit">
        {{ isEdit ? '保存修改' : '确认新增' }}
      </el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import {
  Downloader,
  DownloaderFormData,
  OnlineStatus
} from '../types'
import { downloaderTypeToString } from '@/utils/downloaderType'

@Component({
  name: 'DownloaderDialog'
})
export default class DownloaderDialog extends Vue {
  @Prop({ default: false }) visible!: boolean
  @Prop({ default: null }) downloader!: Downloader | null

  private loading = false
  private formData: DownloaderFormData = {
    nickname: '',
    host: '',
    port: 8080,
    username: '',
    password: '',
    is_ssl: '0',
    is_search: '1',
    downloader_type: 0,
    enabled: '1'
  }

  // 表单验证规则
  private formRules = {
    nickname: [
      { required: true, message: '请输入下载器名称', trigger: 'blur' }
    ],
    host: [
      { required: true, message: '请输入主机地址', trigger: 'blur' }
    ],
    username: [
      { required: true, message: '请输入用户名', trigger: 'blur' }
    ],
    password: [
      { required: true, message: '请输入密码', trigger: 'blur' }
    ],
    port: [
      { required: true, message: '请输入端口号', trigger: 'blur' },
      { type: 'number', min: 1, max: 65535, message: '端口范围为1-65535', trigger: 'blur' }
    ],
    downloader_type: [
      { required: true, message: '请选择下载器类型', trigger: 'change' }
    ]
  }

  // 计算属性：是否为编辑模式
  get isEdit(): boolean {
    return this.downloader !== null
  }

  // 计算属性：弹框标题
  get dialogTitle(): string {
    return this.isEdit ? '修改下载器' : '新增下载器'
  }

  // 获取表单引用
  get formRef(): ElForm {
    return this.$refs.formRef as ElForm
  }

  // 监听弹框显示状态，重置表单或加载数据
  @Watch('visible')
  onVisibleChange(val: boolean) {
    if (val) {
      if (this.isEdit && this.downloader) {
        // 编辑模式：加载下载器数据
        this.loading = true

        // 转换下载器类型：数字 → 字符串
        const downloaderTypeStr = this.downloader.downloader_type_name
          ? this.downloader.downloader_type_name
          : downloaderTypeToString(this.downloader.downloader_type)

        Object.assign(this.formData, {
          id: this.downloader.id,
          nickname: this.downloader.nickname,
          host: this.downloader.host,
          port: this.downloader.port,
          username: this.downloader.username,
          password: this.downloader.password,
          is_ssl: this.downloader.is_ssl,
          is_search: this.downloader.is_search,
          downloader_type: downloaderTypeStr,
          enabled: this.downloader.enabled
        })
        this.loading = false
      } else {
        // 新增模式：重置表单
        this.resetForm()
      }
    }
  }

  // 重置表单
  private resetForm() {
    this.formData = {
      nickname: '',
      host: '',
      port: 8080,
      username: '',
      password: '',
      is_ssl: '0',
      is_search: '1',
      downloader_type: 0,
      enabled: '1'
    }
    this.$nextTick(() => {
      this.formRef?.clearValidate()
    })
  }

  // 关闭弹框
  private handleClose() {
    this.$emit('update:visible', false)
    this.resetForm()
  }

  // 提交表单
  private async handleSubmit() {
    try {
      await this.formRef.validate()
      this.$emit('submit', this.formData)
    } catch (error) {
      // 验证失败
      console.log('表单验证失败:', error)
    }
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

// 弹框靠左布局
::v-deep .downloader-dialog {
  // 距离左边缘 20px
  left: 20px !important;

  // 移除默认的居中变换
  transform: none !important;

  // 最大宽度限制
  max-width: 1200px;

  // 确保圆角和阴影效果
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
}

// 表单三列布局
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

::v-deep .el-form-item {
  margin-bottom: 0;
}

// 强制标签文字不换行
::v-deep .el-form-item__label {
  white-space: nowrap;
}

// 开关行布局
.switch-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--color-border-primary);
}

.switch-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
}

.switch-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  text-align: center;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);

  // 取消按钮 - 灰色背景
  .btn-cancel {
    background: var(--color-bg-tertiary);
    color: var(--color-text-primary);
    border: 1px solid transparent;

    &:hover {
      background: var(--color-bg-active);
      color: var(--color-text-primary);
    }
  }

  // 确认按钮 - 使用Element UI的primary颜色，确保主题一致性
  .btn-confirm {
    background: var(--color-primary);
    border-color: var(--color-primary);

    &:hover {
      background: var(--color-primary-hover);
      border-color: var(--color-primary-hover);
    }
  }
}
</style>
