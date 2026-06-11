<template>
  <div class="basic-settings-tab">
    <!-- 下载器信息 -->
    <div class="form-section">
      <div class="form-section-title">下载器信息</div>
      <el-form :model="formData" :rules="formRules" ref="formRef" label-width="120px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="下载器名称" prop="nickname">
              <el-input v-model="formData.nickname" disabled class="readonly-input" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="下载器类型" prop="downloader_type">
              <el-input v-model="downloaderTypeLabel" disabled class="readonly-input" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 认证设置 -->
    <div class="form-section">
      <div class="form-section-title">认证设置</div>
      <el-form :model="formData" :rules="formRules" ref="authFormRef" label-width="120px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username" required>
              <el-input
                v-model="formData.username"
                placeholder="请输入用户名"
                clearable
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="formData.password"
                type="password"
                placeholder="不修改密码请留空"
                show-password
                clearable
              />
            </el-form-item>
          </el-col>
        </el-row>
        <!-- 原密码字段：仅在用户名改变或密码有输入时显示 -->
        <el-row v-if="showOldPassword" :gutter="16">
          <el-col :span="12">
            <el-form-item label="原密码" prop="old_password" :rules="[{required: true, message: '请输入原密码', trigger: 'blur'}]">
              <el-input
                v-model="formData.old_password"
                type="password"
                placeholder="请输入原密码以验证身份"
                show-password
                clearable
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <div class="old-password-hint">
              <svg class="hint-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span>修改用户名或密码时需要验证原密码</span>
            </div>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 配置选项 -->
    <div class="form-section">
      <div class="form-section-title">配置选项</div>
      <div class="switch-item">
        <span class="switch-label">覆盖下载器本地配置</span>
        <el-switch
          v-model="formData.override_local"
          active-color="#059669"
          inactive-color="#d1d5db"
        />
      </div>
      <p class="form-hint">
        <svg class="hint-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        启用后，将覆盖下载器本地配置。建议谨慎使用，确保了解各配置项的作用。
      </p>
    </div>

    <!-- 连接测试 -->
    <div class="form-section">
      <div class="form-section-title">连接测试</div>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-button
            type="info"
            :loading="testing"
            @click="handleTestConnection"
            style="width: 100%;"
          >
            <svg v-if="!testing" class="button-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
            </svg>
            {{ testing ? '测试中...' : '测试连接' }}
          </el-button>
        </el-col>
        <el-col :span="12">
          <!-- 测试结果显示 -->
          <div v-if="testResult" :class="['test-result', testResult.success ? 'success' : 'error']">
            <svg v-if="testResult.success" class="result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
            <svg v-else class="result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="15" y1="9" x2="9" y2="15"></line>
              <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
            <span>{{ testResult.message }}</span>
          </div>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import { Downloader, DownloaderSettings } from '../types'
import { testDownloaderSettings } from '@/api/downloader'

@Component({
  name: 'BasicSettingsTab'
})
export default class BasicSettingsTab extends Vue {
  @Prop({ required: true }) downloader!: Downloader
  @Prop({ required: true }) settings!: DownloaderSettings

  // 表单数据
  private formData = {
    nickname: '',
    downloader_type: 0 as 0 | 1,
    username: '',
    password: '',
    old_password: '',  // 原密码字段
    override_local: false
  }

  // 保存原始用户名，用于判断是否发生变化
  private originalUsername = ''

  // 表单验证规则
  private formRules = {
    username: [
      { required: true, message: '请输入用户名', trigger: 'blur' }
    ],
    password: [
      { required: false, message: '请输入密码', trigger: 'blur' }  // 编辑模式下密码非必填
    ],
    old_password: [
      { required: false, message: '请输入原密码', trigger: 'blur' }  // 动态验证
    ]
  }

  // 测试连接状态
  private testing = false
  private testResult: { success: boolean, message: string } | null = null

  // 获取表单引用
  get formRef(): ElForm {
    return this.$refs.formRef as ElForm
  }

  get authFormRef(): ElForm {
    return this.$refs.authFormRef as ElForm
  }

  // 计算属性：下载器类型标签
  get downloaderTypeLabel(): string {
    // 使用驼峰命名的字段
    if (this.downloader.downloaderTypeName === 'qbittorrent') return 'qBittorrent'
    if (this.downloader.downloaderTypeName === 'transmission') return 'Transmission'

    const type = this.downloader.downloaderType
    if (type === 0) return 'qBittorrent'
    if (type === 1) return 'Transmission'

    return '未知类型'
  }

  // 计算属性：是否需要显示原密码字段
  get showOldPassword(): boolean {
    // 用户名发生变化，或密码字段有输入时，显示原密码字段
    const usernameChanged = this.formData.username !== this.originalUsername
    const passwordHasInput = this.formData.password && this.formData.password.trim() !== ''
    return usernameChanged || passwordHasInput
  }

  // 监听下载器变化
  @Watch('downloader', { immediate: true, deep: true })
  onDownloaderChange(val: Downloader) {
    if (val) {
      this.formData.nickname = val.nickname
      // 使用驼峰命名的字段
      this.formData.downloader_type = val.downloaderType as 0 | 1
      this.formData.username = val.username || ''
      // 保存原始用户名，用于判断是否发生变化
      this.originalUsername = val.username || ''
      // 后端不返回密码，密码字段初始化为空
      this.formData.password = ''
      // 原密码字段初始化为空
      this.formData.old_password = ''
    }
  }

  // 监听设置变化
  @Watch('settings', { immediate: true, deep: true })
  onSettingsChange(val: DownloaderSettings) {
    if (val) {
      this.formData.override_local = val.override_local || false
    }
  }

  // 测试连接
  private async handleTestConnection() {
    // ✅ 构建测试参数（使用表单数据，不使用缓存）
    const testParams = {
      host: this.downloader.host,
      port: this.downloader.port,
      username: this.formData.username,  // 使用表单中的用户名（可能已修改）
      password: this.formData.password,  // 使用表单中的密码（非空时使用前端密码，空则后端查询数据库）
      downloader_type: this.downloader.downloaderType as 0 | 1,
      is_ssl: this.downloader.is_ssl
    }

    this.testing = true
    this.testResult = null

    try {
      // ✅ 传递测试参数给后端API
      const response = await testDownloaderSettings(this.downloader.id, testParams)

      if (response.code === '200') {
        this.testResult = {
          success: true,
          message: response.data.success
            ? `连接成功 • 延迟 ${response.data.delay || 0}ms`
            : response.data.message || '连接失败'
        }
      } else {
        this.testResult = {
          success: false,
          message: response.msg || '连接失败'
        }
      }
    } catch (error: any) {
      this.testResult = {
        success: false,
        message: error?.response?.data?.msg || error?.message || '连接失败'
      }
    } finally {
      this.testing = false
    }
  }

  // 获取表单数据（供父组件调用）
  public getFormData(): Partial<DownloaderSettings & { old_password?: string }> {
    const data: Partial<DownloaderSettings & { old_password?: string }> = {
      username: this.formData.username,
      override_local: this.formData.override_local
    }

    // 只有在密码字段有输入时才包含密码
    if (this.formData.password && this.formData.password.trim() !== '') {
      data.password = this.formData.password
    }

    // 只有在显示原密码字段时才包含原密码
    if (this.showOldPassword && this.formData.old_password) {
      data.old_password = this.formData.old_password
    }

    return data
  }

  // 验证表单
  public async validateForm(): Promise<boolean> {
    try {
      await Promise.all([
        this.formRef.validate(),
        this.authFormRef.validate()
      ])
      return true
    } catch (error) {
      return false
    }
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.basic-settings-tab {
  padding: var(--spacing-md) 0;
}

.form-section {
  margin-bottom: var(--spacing-xl);
}

.form-section-title {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);

  &::before {
    content: '';
    width: 4px;
    height: 16px;
    background: var(--color-primary);
    border-radius: 2px;
  }
}

::v-deep .readonly-input input {
  background: var(--color-bg-tertiary) !important;
  color: var(--color-text-secondary) !important;
  cursor: not-allowed;
}

.switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-sm);
}

.switch-label {
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.form-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0;
}

.hint-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.old-password-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-info-light);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-info);
  line-height: 1.5;
  height: 40px;
}

.button-icon {
  display: inline;
  vertical-align: middle;
  margin-right: 6px;
  width: 16px;
  height: 16px;
}

// 测试结果样式
.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  height: 40px;

  &.success {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  &.error {
    background: var(--color-error-light);
    color: var(--color-error);
  }
}

.result-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
</style>
