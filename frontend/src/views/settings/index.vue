<template>
  <div class="settings-container">
    <el-tabs v-model="activeTab" type="card" class="settings-tabs">
      <!-- 双因素认证标签页 -->
      <el-tab-pane :label="$t('settings.tabs.twofa')" name="2fa">
        <div class="settings-content">
          <div class="settings-card">
            <h3 class="settings-card-title">{{ $t('settings.twofa.title') }}</h3>

            <!-- 已启用2FA：显示停用界面 -->
            <div v-if="isEnabled2FA" class="step-container">
              <p class="settings-description">
                {{ $t('settings.twofa.enabledDesc', {status: $t('settings.twofa.statusEnabled')}) }}
              </p>

              <el-form :model="disable2FAForm" class="verify-form" label-position="top">
                <el-form-item :label="$t('settings.twofa.currentPassword')">
                  <el-input
                    v-model="disable2FAForm.password"
                    type="password"
                    show-password
                    :placeholder="$t('settings.twofa.currentPasswordPlaceholder')"
                    :disabled="isLocked"
                  />
                </el-form-item>

                <el-form-item :label="$t('settings.twofa.twofaCode')">
                  <el-input
                    v-model="disable2FAForm.twoFactorCode"
                    maxlength="6"
                    :placeholder="$t('settings.twofa.twofaCodePlaceholder')"
                    :disabled="isLocked"
                  >
                    <template #prefix>
                      <i class="el-icon-key" />
                    </template>
                  </el-input>
                </el-form-item>

                <!-- 锁定提示 -->
                <el-alert
                  v-if="isLocked"
                  :title="$t('settings.twofa.locked')"
                  type="error"
                  :closable="false"
                  show-icon
                  class="lock-alert"
                >
                  <template>
                    {{ $t('settings.twofa.lockedVerifyDesc') }}
                    <br />
                    {{ $t('settings.twofa.retryAfterSeconds', {seconds: lockCountdown}) }}
                  </template>
                </el-alert>

                <!-- 错误提示 -->
                <el-alert
                  v-if="errorMessage && !isLocked"
                  :title="errorMessage"
                  type="error"
                  :closable="false"
                  show-icon
                  class="error-alert"
                />

                <!-- 失败次数提示 -->
                <div v-if="failedAttempts > 0 && !isLocked" class="attempts-warning">
                  <i class="el-icon-warning" />
                  {{ $t('settings.twofa.attemptsWarning', {failed: failedAttempts, remaining: 5 - failedAttempts}) }}
                </div>

                <div class="form-actions">
                  <el-button
                    type="danger"
                    :loading="disableLoading"
                    :disabled="isLocked || !disable2FAForm.password || !disable2FAForm.twoFactorCode"
                    @click="confirmDisable2FA"
                  >
                    {{ $t('settings.twofa.disable') }}
                  </el-button>
                </div>
              </el-form>
            </div>

            <!-- 未启用2FA：显示绑定流程 -->
            <div v-else>
              <!-- 步骤1：验证密码 -->
              <div v-if="currentStep === 1" class="step-container">
              <p class="settings-description">
                {{ $t('settings.twofa.verifyPasswordStepDesc') }}
              </p>

              <el-form :model="passwordForm" class="verify-form" label-position="top">
                <el-form-item :label="$t('settings.twofa.currentPassword')">
                  <el-input
                    v-model="passwordForm.password"
                    type="password"
                    show-password
                    :placeholder="$t('settings.twofa.currentPasswordPlaceholder')"
                    :disabled="isLocked"
                    @keyup.enter.native="verifyPassword"
                  />
                </el-form-item>

                <!-- 锁定提示 -->
                <el-alert
                  v-if="isLocked"
                  :title="$t('settings.twofa.locked')"
                  type="error"
                  :closable="false"
                  show-icon
                  class="lock-alert"
                >
                  <template>
                    {{ $t('settings.twofa.lockedPasswordDesc') }}
                    <br />
                    {{ $t('settings.twofa.retryAfterSeconds', {seconds: lockCountdown}) }}
                  </template>
                </el-alert>

                <!-- 错误提示 -->
                <el-alert
                  v-if="errorMessage && !isLocked"
                  :title="errorMessage"
                  type="error"
                  :closable="false"
                  show-icon
                  class="error-alert"
                />

                <!-- 失败次数提示 -->
                <div v-if="failedAttempts > 0 && !isLocked" class="attempts-warning">
                  <i class="el-icon-warning" />
                  {{ $t('settings.twofa.attemptsWarning', {failed: failedAttempts, remaining: 5 - failedAttempts}) }}
                </div>

                <div class="form-actions">
                  <el-button
                    type="primary"
                    :loading="verifyLoading"
                    :disabled="isLocked || !passwordForm.password"
                    @click="verifyPassword"
                  >
                    {{ $t('settings.twofa.verifyPassword') }}
                  </el-button>
                </div>
              </el-form>
            </div>

            <!-- 步骤2：扫描二维码并验证 -->
            <div v-if="currentStep === 2" class="step-container">
              <p class="settings-description">
                {{ $t('settings.twofa.scanDesc') }}
              </p>

              <div
                v-loading="qrLoading"
                class="qr-code"
                :class="{'qr-code-manual': !qrCodeData && !qrLoading}"
              >
                <img v-if="qrCodeData" :src="qrCodeData" alt="2FA QR Code" />
                <span v-else-if="qrLoading">{{ $t('settings.twofa.qrGenerating') }}</span>
                <div v-else class="manual-secret-entry">
                  <p class="manual-entry-hint">
                    {{ $t('settings.twofa.manualEntryHint') }}
                  </p>
                  <div class="manual-secret-row">
                    <el-input :value="manualEntrySecret" readonly class="manual-secret-input" />
                    <el-button size="small" type="primary" plain @click="copyManualSecret">{{ $t('settings.twofa.copySecret') }}</el-button>
                  </div>
                  <p class="manual-entry-meta">
                    {{ $t('settings.twofa.manualEntryMeta', {account: manualEntryAccount}) }}
                  </p>
                </div>
              </div>

              <el-form :model="totpForm" class="verify-form" label-position="top">
                <el-form-item :label="$t('settings.twofa.code')">
                  <el-input
                    v-model="totpForm.twoFactorCode"
                    maxlength="6"
                    :placeholder="$t('settings.twofa.codePlaceholder')"
                    @keyup.enter.native="confirmBinding"
                  >
                    <template #prefix>
                      <i class="el-icon-key" />
                    </template>
                  </el-input>
                </el-form-item>

                <!-- 绑定错误提示 -->
                <el-alert
                  v-if="bindingError"
                  :title="bindingError"
                  type="error"
                  :closable="false"
                  show-icon
                  class="error-alert"
                />

                <div class="form-actions">
                  <el-button @click="resetFlow">{{ $t('common.cancel') }}</el-button>
                  <el-button
                    type="primary"
                    :loading="bindingLoading"
                    :disabled="!totpForm.twoFactorCode || totpForm.twoFactorCode.length !== 6"
                    @click="confirmBinding"
                  >
                    {{ $t('settings.twofa.confirmBinding') }}
                  </el-button>
                </div>
              </el-form>

              <div class="qr-instructions">
                <p><strong>{{ $t('settings.twofa.usageTitle') }}</strong></p>
                <ol>
                  <li>{{ $t('settings.twofa.stepDownload') }}</li>
                  <li v-if="qrCodeData">{{ $t('settings.twofa.stepScan') }}</li>
                  <li v-else>{{ $t('settings.twofa.stepManual') }}</li>
                  <li>{{ $t('settings.twofa.stepInput') }}</li>
                  <li>{{ $t('settings.twofa.stepConfirm') }}</li>
                </ol>
              </div>
            </div>

            <!-- 步骤3：绑定成功 -->
            <div v-if="currentStep === 3" class="step-container success-step">
              <el-result
                icon="success"
                :title="$t('settings.twofa.bindSuccess')"
                :sub-title="$t('settings.twofa.bindSuccessDesc')"
              >
                <template #extra>
                  <div class="backup-secret">
                    <p><strong>{{ $t('settings.twofa.backupSecretTitle') }}</strong></p>
                    <el-input
                      :value="backupSecret"
                      readonly
                      type="textarea"
                      :rows="2"
                    />
                    <p class="secret-warning">
                      {{ $t('settings.twofa.backupSecretWarning') }}
                    </p>
                  </div>
                  <el-button type="primary" @click="closeAndRefresh">
                    {{ $t('common.close') }}
                  </el-button>
                </template>
              </el-result>
            </div>
            </div> <!-- 闭合 v-else 的div -->
          </div> <!-- 闭合 settings-card 的div -->
        </div> <!-- 闭合 settings-content 的div -->
      </el-tab-pane>

      <!-- 修改密码标签页 -->
      <el-tab-pane :label="$t('settings.tabs.password')" name="password">
        <div class="settings-content">
          <div class="settings-card">
            <h3 class="settings-card-title">{{ $t('settings.password.title') }}</h3>
            <p class="settings-description">
              {{ $t('settings.password.desc') }}
            </p>
            <el-form :model="passwordFormChange" class="change-password-form" label-position="top">
              <el-form-item :label="$t('settings.password.oldPassword')">
                <el-input
                  v-model="passwordFormChange.old_password"
                  type="password"
                  show-password
                  :placeholder="$t('settings.password.oldPasswordPlaceholder')"
                />
              </el-form-item>
              <el-form-item :label="$t('settings.password.newPassword')">
                <el-input
                  v-model="passwordFormChange.new_password"
                  type="password"
                  show-password
                  :placeholder="$t('settings.password.newPasswordPlaceholder')"
                />
              </el-form-item>
              <el-form-item :label="$t('settings.password.confirmPassword')">
                <el-input
                  v-model="confirmPass"
                  type="password"
                  show-password
                  :placeholder="$t('settings.password.confirmPasswordPlaceholder')"
                />
              </el-form-item>
              <div class="form-actions">
                <el-button @click="cancelPasswordChange">{{ $t('common.cancel') }}</el-button>
                <el-button type="primary" @click="changePassword">{{ $t('settings.password.confirm') }}</el-button>
              </div>
            </el-form>
          </div>
        </div>
      </el-tab-pane>

      <!-- MCP 服务（mcp-service-capabilities W1：全局/能力开关 + 风险说明；移动端经包装自动同源）
           （v1.0.7 新功能面，中文硬编码待双语化另立项；见 PLANS/merge-dev107-into-dev.md） -->
      <el-tab-pane label="MCP 服务" name="mcp">
        <div class="settings-content">
          <mcp-settings-panel />
        </div>
      </el-tab-pane>

      <!-- MoviePilot 集成（moviepilot-integration：全局开关/实例与下载器映射/关联反查；移动端经包装自动同源） -->
      <el-tab-pane label="MoviePilot" name="moviepilot">
        <div class="settings-content">
          <movie-pilot-panel />
        </div>
      </el-tab-pane>

      <!-- 状态诊断：故障转储/排查/状态分析导出（原后端 /health/sync 业务健康视图改造） -->
      <el-tab-pane :label="$t('settings.tabs.diagnosis')" name="diagnosis">
        <div class="settings-content">
          <div class="settings-card">
            <h3 class="settings-card-title">{{ $t('settings.diagnosis.title') }}</h3>
            <p class="settings-description">
              {{ $t('settings.diagnosis.desc') }}
            </p>
            <div class="form-actions">
              <el-button
                type="primary"
                :loading="diagnosisLoading"
                @click="handleExportDiagnosis"
              >
                {{ diagnosisLoading ? $t('settings.diagnosis.generating') : $t('settings.diagnosis.export') }}
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { UserModule } from '@/store/modules/user'
import { changePassword } from '@/api/users'
import { exportDiagnosisFile } from '@/api/health'
import { isDemoMode } from '@/demo/config'
import McpSettingsPanel from './components/McpSettingsPanel.vue'
import MoviePilotPanel from './components/MoviePilotPanel.vue'
import { loginPathForMode } from '@/utils/ui-mode'
import { apiErrorMessage } from '@/i18n'
import { copyTextToClipboard } from '@/utils/clipboard'
import request from '@/utils/request'

@Component({
  name: 'Settings',
  components: { McpSettingsPanel, MoviePilotPanel }
})
export default class extends Vue {
  // 当前激活的标签页
  private activeTab = '2fa'

  // 2FA相关状态
  private currentStep = 1 // 1:验证密码 2:扫描二维码 3:绑定成功
  private isEnabled2FA = false // 是否已启用2FA
  private passwordForm = {
    userId: 1,
    password: ''
  }
  private totpForm = {
    userId: 1,
    twofaFlag: '1',
    twoFactorCode: ''
  }

  // 停用2FA表单
  private disable2FAForm = {
    password: '',
    twoFactorCode: ''
  }
  private showDisableConfirm = false // 停用确认对话框
  private disableLoading = false // 停用按钮加载状态

  // 加载状态
  private verifyLoading = false
  private qrLoading = false
  private bindingLoading = false

  // 数据
  private qrCodeData = ''
  private backupSecret = ''
  // Pillow 缺失（Android 服务端形态）降级：手动录入密钥
  private manualEntrySecret = ''
  private manualEntryAccount = ''

  // 错误提示
  private errorMessage = ''
  private bindingError = ''

  // 失败锁定机制
  private failedAttempts = 0
  private isLocked = false
  private lockEndTime: number | null = null
  private lockCountdown = 0
  private lockTimer: number | null = null

  // 修改密码相关
  private confirmPass = ''
  private passwordFormChange = {
    name: '',
    userId: '',
    new_password: '',
    old_password: ''
  }

  // 状态诊断导出
  private diagnosisLoading = false

  get name() {
    return UserModule.name
  }

  // 获取用户2FA状态
  get twoFactorFlag() {
    // 从UserModule获取，如果UserModule没有则默认为'0'
    return (UserModule as any).twoFactorFlag || '0'
  }

  mounted() {
    // 从localStorage恢复失败次数
    this.restoreFailedAttempts()

    // 初始化2FA状态
    this.isEnabled2FA = this.twoFactorFlag === '1'

    // 强制改密引导提示（安全修复 W9）由路由守卫统一弹出（permission.ts
    // 的 forceChangeRedirect）：拦截重定向回本页不会重新挂载，mounted
    // 提示无法覆盖"点击其它菜单被弹回"的场景，且会与守卫提示双弹
  }

  beforeDestroy() {
    // 清理定时器
    if (this.lockTimer) {
      clearInterval(this.lockTimer)
    }
  }

  // 生成并导出故障诊断快照 JSON（demo 模式生成前端本地快照）
  private async handleExportDiagnosis() {
    if (this.diagnosisLoading) return
    this.diagnosisLoading = true
    try {
      const blob = isDemoMode() ? this.buildDemoDiagnosisBlob() : await exportDiagnosisFile()
      const fileName = `btdeck-diagnosis-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.json`
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      this.$message.success(this.$t('settings.diagnosis.exported'))
    } catch (error) {
      console.error('导出诊断文件失败:', error)
      this.$message.error(this.$t('settings.diagnosis.failed'))
    } finally {
      this.diagnosisLoading = false
    }
  }

  // demo 模式诊断快照：结构与后端 /health/diagnosis 响应对齐，并标注 demo: true
  private buildDemoDiagnosisBlob(): Blob {
    const dump = {
      generatedAt: new Date().toISOString(),
      demo: true,
      version: 'demo',
      build: { status: 'demo' },
      checks: {
        database: { status: 'ok' },
        worker: { status: 'ok' },
        eventLoopLag: { status: 'ok', sampleCount: 0, p99Ms: null, maxMs: null }
      },
      readinessFailureTotal: {},
      sync: {
        tasks: [],
        downloaders: { status: 'unknown', total: 0, offlineCount: 0, warnings: [] },
        process: { rssMb: null }
      }
    }
    return new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' })
  }

  // 从localStorage恢复失败次数
  private restoreFailedAttempts() {
    const stored = localStorage.getItem('2fa_failed_attempts')
    if (stored) {
      const data = JSON.parse(stored)
      const now = Date.now()

      // 检查是否还在锁定期
      if (data.lockEndTime && now < data.lockEndTime) {
        this.failedAttempts = data.failedAttempts
        this.lockEndTime = data.lockEndTime
        this.startLockTimer()
      } else {
        // 锁定期已过，重置
        this.clearFailedAttempts()
      }
    }
  }

  // 保存失败次数到localStorage
  private saveFailedAttempts() {
    localStorage.setItem('2fa_failed_attempts', JSON.stringify({
      failedAttempts: this.failedAttempts,
      lockEndTime: this.lockEndTime
    }))
  }

  // 清除失败次数
  private clearFailedAttempts() {
    this.failedAttempts = 0
    this.lockEndTime = null
    this.isLocked = false
    this.lockCountdown = 0
    if (this.lockTimer) {
      clearInterval(this.lockTimer)
      this.lockTimer = null
    }
    localStorage.removeItem('2fa_failed_attempts')
  }

  // 启动锁定定时器
  private startLockTimer() {
    this.isLocked = true

    this.lockTimer = window.setInterval(() => {
      const now = Date.now()
      if (this.lockEndTime && now < this.lockEndTime) {
        this.lockCountdown = Math.ceil((this.lockEndTime - now) / 1000)
      } else {
        // 锁定期结束
        this.clearFailedAttempts()
      }
    }, 1000)
  }

  // 验证密码
  private async verifyPassword() {
    if (!this.passwordForm.password) {
      this.errorMessage = this.$t('settings.twofa.passwordRequired')
      return
    }
    // 检查 userId 是否存在
    if (!UserModule.userId) {
      this.errorMessage = this.$t('settings.twofa.userInfoFailed')
      return
    }

    this.verifyLoading = true
    this.errorMessage = ''

    try {
      const response = await request.post('/user/verifyPasswordFor2FA', {
        userId: UserModule.userId,
        password: this.passwordForm.password
      })

      if (response.code === '200') {
        // 验证成功
        this.clearFailedAttempts()
        this.qrCodeData = response.data.qr_code_base64 || ''
        this.backupSecret = response.data.secret
        this.manualEntrySecret = response.data.secret || ''
        this.manualEntryAccount = UserModule.name || ''
        this.currentStep = 2
        this.$message({
          type: 'success',
          message: this.$t('settings.twofa.verifySuccess')
        })
      } else {
        throw new Error(response.msg || this.$t('settings.twofa.verifyFailed'))
      }
    } catch (error: any) {
      // 验证失败：reasonCode 命中错误契约时本地化，否则保留原始信息
      this.failedAttempts++

      this.errorMessage = apiErrorMessage(error, this.$t('settings.twofa.passwordWrong'))

      // 检查是否需要锁定
      if (this.failedAttempts >= 5) {
        this.lockEndTime = Date.now() + 5 * 60 * 1000 // 5分钟后
        this.saveFailedAttempts()
        this.startLockTimer()
        this.$message({
          type: 'error',
          message: this.$t('settings.twofa.lockedFiveMinutes')
        })
      } else {
        this.saveFailedAttempts()
      }
    } finally {
      this.verifyLoading = false
    }
  }

  // 确认绑定
  private async confirmBinding() {
    if (!this.totpForm.twoFactorCode || this.totpForm.twoFactorCode.length !== 6) {
      this.bindingError = this.$t('settings.twofa.codeRequired')
      return
    }
    // 检查 userId 是否存在
    if (!UserModule.userId) {
      this.bindingError = this.$t('settings.twofa.userInfoFailed')
      return
    }

    this.bindingLoading = true
    this.bindingError = ''

    try {
      const response = await request.post(`/user/update2faFlg/${UserModule.userId}`, {
        userId: UserModule.userId,
        twofaFlag: '1',
        twoFactorCode: this.totpForm.twoFactorCode
      })

      if (response.code === '200') {
        this.currentStep = 3
        this.$message({
          type: 'success',
          message: this.$t('settings.twofa.bindSuccess')
        })
      } else {
        throw new Error(response.msg || this.$t('settings.twofa.bindFailed'))
      }
    } catch (error: any) {
      this.bindingError = apiErrorMessage(error, this.$t('settings.twofa.codeInvalid'))
    } finally {
      this.bindingLoading = false
    }
  }

  // 重置流程
  private resetFlow() {
    this.currentStep = 1
    this.passwordForm.password = ''
    this.totpForm.twoFactorCode = ''
    this.qrCodeData = ''
    this.backupSecret = ''
    this.manualEntrySecret = ''
    this.manualEntryAccount = ''
    this.errorMessage = ''
    this.bindingError = ''
  }

  // 手动录入模式：复制密钥到剪贴板（Pillow 缺失降级）
  private async copyManualSecret() {
    try {
      await copyTextToClipboard(this.manualEntrySecret)
      this.$message({ type: 'success', message: this.$t('settings.twofa.secretCopied') })
    } catch (error) {
      this.$message({ type: 'error', message: this.$t('settings.twofa.copyFailed') })
    }
  }

  // 确认停用2FA（显示确认对话框）
  private confirmDisable2FA() {
    if (!this.disable2FAForm.password || !this.disable2FAForm.twoFactorCode) {
      this.errorMessage = this.$t('settings.twofa.fieldsRequired')
      return
    }

    if (this.disable2FAForm.twoFactorCode.length !== 6) {
      this.errorMessage = this.$t('settings.twofa.codeMustBeSixDigits')
      return
    }

    // 显示确认对话框
    this.$confirm(this.$t('settings.twofa.disableConfirm'), this.$t('settings.twofa.disableConfirmTitle'), {
      confirmButtonText: this.$t('settings.twofa.confirmDisable'),
      cancelButtonText: this.$t('common.cancel'),
      type: 'warning'
    }).then(() => {
      // 用户点击确认，执行停用
      this.disable2FA()
    }).catch(() => {
      // 用户点击取消
    })
  }

  // 停用2FA
  private async disable2FA() {
    if (!UserModule.userId) {
      this.errorMessage = this.$t('settings.twofa.userInfoFailed')
      return
    }

    this.disableLoading = true
    this.errorMessage = ''

    try {
      const response = await request.post(`/user/update2faFlg/${UserModule.userId}`, {
        userId: UserModule.userId,
        twofaFlag: '0',
        twoFactorCode: this.disable2FAForm.twoFactorCode,
        password: this.disable2FAForm.password
      })

      if (response.code === '200') {
        // 停用成功
        this.clearFailedAttempts()

        // 使用$nextTick确保DOM更新完成后再显示消息
        // 避免：v-if条件变化导致DOM销毁时，$message调用竞态条件
        this.$nextTick(() => {
          this.isEnabled2FA = false // 更新状态，可能触发v-if的DOM销毁

          // 清空表单
          this.disable2FAForm.password = ''
          this.disable2FAForm.twoFactorCode = ''

          // 在下一个tick调用$message，此时DOM已稳定
          this.$message({
            type: 'success',
            message: this.$t('settings.twofa.disableSuccess')
          })

          // 更新UserModule中的状态（通过 Action，不绕过 mutation）
          UserModule.SetTwoFactorFlag('0')
        })
      } else {
        throw new Error(response.msg || this.$t('settings.twofa.verifyFailed'))
      }
    } catch (error: any) {
      // 验证失败：reasonCode 命中错误契约时本地化，否则保留原始信息
      this.failedAttempts++

      this.errorMessage = apiErrorMessage(error, this.$t('settings.twofa.verifyFailed'))

      // 检查是否需要锁定
      if (this.failedAttempts >= 5) {
        this.lockEndTime = Date.now() + 5 * 60 * 1000 // 5分钟后
        this.saveFailedAttempts()
        this.startLockTimer()
        this.$message({
          type: 'error',
          message: this.$t('settings.twofa.lockedAttemptsFiveMinutes')
        })
      } else {
        this.saveFailedAttempts()
      }
    } finally {
      this.disableLoading = false
    }
  }

  // 取消修改密码
  private cancelPasswordChange() {
    this.passwordFormChange.old_password = ''
    this.passwordFormChange.new_password = ''
    this.confirmPass = ''
  }

  // 确认修改密码
  private async changePassword() {
    if (this.confirmPass !== this.passwordFormChange.new_password) {
      this.$message({
        message: this.$t('settings.password.mismatch'),
        type: 'warning',
        duration: 3000
      })
      return
    }

    // 检查 userId 是否存在
    if (!UserModule.userId) {
      this.$message({
        message: this.$t('settings.password.userInfoFailed'),
        type: 'error',
        duration: 3000
      })
      return
    }

    try {
      await changePassword({
        userId: String(UserModule.userId), // 确保userId是字符串类型
        new_password: window.btoa(this.passwordFormChange.new_password),
        old_password: window.btoa(this.passwordFormChange.old_password)
      })

      this.$message({
        message: this.$t('settings.password.success'),
        type: 'success',
        duration: 3000
      })

      // 改密会话终结（跨标签续期修复）：后端 change_password 已撤销该用户
      // 全部 refresh token（W9），本地会话不可再续期——主动登出语义全清
      // （ResetToken 含强制改密标志清除），跳登录页用新密码重登。
      // forceChange query 清理随整页跳转自然失效，无需单独处理；
      // 登录页按 UI 模式分流（本组件被 /m/settings 整页复用，移动模式回 /m/login）
      UserModule.ResetToken()
      this.$router.push(loginPathForMode()).catch(() => undefined)
    } catch (error) {
      this.$message({
        // 原密码错等失败路径经错误契约本地化（USER_ORIG_PASSWORD_INVALID 等）
        message: apiErrorMessage(error, this.$t('settings.password.failed')),
        type: 'error',
        duration: 3000
      })
    }
  }
  // 关闭绑定成功界面并切换到解绑界面
  private closeAndRefresh() {
    this.$confirm(this.$t('settings.twofa.closeSecretConfirm'), this.$t('settings.twofa.closeSecretTitle'), {
      confirmButtonText: this.$t('settings.twofa.closeSecretTitle'),
      cancelButtonText: this.$t('common.cancel'),
      type: 'warning'
    }).then(() => {
      // 用户确认关闭
      // 切换到已启用状态，显示解绑界面
      this.isEnabled2FA = true
      // 重置步骤到初始状态
      this.currentStep = 1
      // 清除密钥，防止再次查看
      this.backupSecret = ''
      // 清空其他表单数据
      this.passwordForm.password = ''
      this.totpForm.twoFactorCode = ''
      this.qrCodeData = ''
      this.manualEntrySecret = ''
      this.manualEntryAccount = ''
      this.errorMessage = ''
      this.bindingError = ''
      this.$message({
        type: 'success',
        message: this.$t('settings.twofa.closed')
      })
    }).catch(() => {
      // 用户取消
    })
  }
}
</script>

<style lang="scss" scoped>
.settings-container {
  max-width: 1920px;
  margin: 0 auto;
  padding: var(--spacing-xl);
}

.settings-tabs {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);

  ::v-deep .el-tabs__header {
    margin: 0;
    padding: var(--spacing-lg) var(--spacing-xl) 0;
    background: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border-primary);
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }

  ::v-deep .el-tabs__nav {
    border: none;
  }

  ::v-deep .el-tabs__item {
    border: 1px solid var(--color-border-primary);
    border-bottom: none;
    border-radius: var(--radius-md) var(--radius-md) 0 0;
    margin-right: var(--spacing-md);
    padding: 0 var(--spacing-xl);
    height: 48px;
    line-height: 48px;
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-secondary);
    background: var(--color-bg-tertiary);
    transition: all var(--transition-base);

    &:hover {
      color: var(--color-primary);
      background: var(--color-bg-secondary);
    }

    &.is-active {
      color: var(--color-primary);
      background: var(--color-bg-primary);
      border-bottom: 1px solid var(--color-bg-primary);
      margin-bottom: -1px;
    }
  }

  ::v-deep .el-tabs__content {
    padding: var(--spacing-xl);
  }
}

.settings-content {
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

.settings-card {
  width: 100%;
  max-width: 600px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-md);
}

.settings-card-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);

  &::before {
    content: '';
    width: 4px;
    height: 20px;
    background: linear-gradient(180deg, var(--color-primary), var(--color-primary-light));
    border-radius: var(--radius-sm);
  }
}

.settings-description {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-lg);
  line-height: 1.6;
}

.step-container {
  animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.verify-form {
  margin-top: var(--spacing-lg);
}

.lock-alert,
.error-alert {
  margin-bottom: var(--spacing-md);
}

.attempts-warning {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  color: var(--color-warning-text);
  font-size: 13px;
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);

  i {
    font-size: 16px;
  }
}

.qr-code {
  width: 200px;
  height: 200px;
  background: linear-gradient(135deg, var(--color-bg-primary), var(--color-bg-tertiary));
  border-radius: var(--radius-lg);
  margin: 0 auto var(--spacing-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  font-size: 14px;
  font-weight: 500;
  border: 2px dashed var(--color-border-primary);
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
}

// Pillow 缺失降级：手动录入密钥块（自适应高度替代固定 200×200 二维码位）
.qr-code.qr-code-manual {
  width: 100%;
  max-width: 420px;
  height: auto;
  min-height: 200px;
  padding: var(--spacing-lg);
  flex-direction: column;
  align-items: stretch;
  text-align: left;

  .manual-entry-hint {
    margin: 0 0 var(--spacing-md);
    font-size: 13px;
    font-weight: 400;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  .manual-secret-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm, 8px);

    .manual-secret-input {
      flex: 1;

      ::v-deep .el-input__inner {
        font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
        letter-spacing: 0.5px;
      }
    }
  }

  .manual-entry-meta {
    margin: var(--spacing-md) 0 0;
    font-size: 12px;
    font-weight: 400;
    color: var(--color-text-tertiary);
  }
}

.qr-instructions {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  margin-top: var(--spacing-lg);

  p {
    margin: 0 0 var(--spacing-sm);
    color: var(--color-text-primary);
    font-size: 14px;
  }

  strong {
    color: var(--color-primary);
  }

  ol {
    margin: 0;
    padding-left: var(--spacing-lg);
    color: var(--color-text-secondary);
    font-size: 13px;
    line-height: 1.8;

    li {
      margin-bottom: var(--spacing-xs);
    }
  }
}

.success-step {
  text-align: center;

  ::v-deep .el-result {
    padding: var(--spacing-xl) 0;
  }
}

.backup-secret {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  margin: var(--spacing-lg) 0;
  text-align: left;

  p {
    margin: 0 0 var(--spacing-sm);
    color: var(--color-text-primary);
    font-size: 14px;
  }

  strong {
    color: var(--color-primary);
  }

  .secret-warning {
    margin: var(--spacing-md) 0 0;
    padding: var(--spacing-sm);
    background: var(--color-warning-bg);
    border-left: 3px solid var(--color-warning);
    color: var(--color-warning-text);
    font-size: 12px;
    border-radius: var(--radius-sm);
  }
}

.change-password-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
  justify-content: flex-end;
}

// 响应式
@media (max-width: 768px) {
  .settings-container {
    padding: var(--spacing-md);
  }

  .settings-tabs {
    ::v-deep .el-tabs__header {
      padding: var(--spacing-md) var(--spacing-md) 0;
    }

    ::v-deep .el-tabs__content {
      padding: var(--spacing-md);
    }
  }

  .settings-card {
    max-width: 100%;
    padding: var(--spacing-lg);
  }

  .qr-code {
    width: 160px;
    height: 160px;
  }
}
</style>
