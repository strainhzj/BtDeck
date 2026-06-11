<template>
  <div class="settings-container">
    <el-tabs v-model="activeTab" type="card" class="settings-tabs">
      <!-- 双因素认证标签页 -->
      <el-tab-pane label="双因素认证" name="2fa">
        <div class="settings-content">
          <div class="settings-card">
            <h3 class="settings-card-title">双因素认证</h3>

            <!-- 已启用2FA：显示停用界面 -->
            <div v-if="isEnabled2FA" class="step-container">
              <p class="settings-description">
                您的双因素认证当前处于 <strong style="color: var(--color-success)">已启用</strong> 状态。
                停用后账户安全性将降低，建议仅在必要时停用。
              </p>

              <el-form :model="disable2FAForm" class="verify-form" label-position="top">
                <el-form-item label="当前密码">
                  <el-input
                    v-model="disable2FAForm.password"
                    type="password"
                    show-password
                    placeholder="请输入当前密码"
                    :disabled="isLocked"
                  />
                </el-form-item>

                <el-form-item label="双因素验证码">
                  <el-input
                    v-model="disable2FAForm.twoFactorCode"
                    maxlength="6"
                    placeholder="请输入认证器中的6位验证码"
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
                  title="已锁定"
                  type="error"
                  :closable="false"
                  show-icon
                  class="lock-alert"
                >
                  <template>
                    验证失败次数过多，已被锁定。
                    <br />
                    请在 <strong>{{ lockCountdown }}</strong> 秒后重试。
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
                  已失败 {{ failedAttempts }} 次，还剩 {{ 5 - failedAttempts }} 次机会
                </div>

                <div class="form-actions">
                  <el-button
                    type="danger"
                    :loading="disableLoading"
                    :disabled="isLocked || !disable2FAForm.password || !disable2FAForm.twoFactorCode"
                    @click="confirmDisable2FA"
                  >
                    停用双因素认证
                  </el-button>
                </div>
              </el-form>
            </div>

            <!-- 未启用2FA：显示绑定流程 -->
            <div v-else>
              <!-- 步骤1：验证密码 -->
              <div v-if="currentStep === 1" class="step-container">
              <p class="settings-description">
                为保护账户安全，开启双因素认证前需先验证当前密码。
              </p>

              <el-form :model="passwordForm" class="verify-form" label-position="top">
                <el-form-item label="当前密码">
                  <el-input
                    v-model="passwordForm.password"
                    type="password"
                    show-password
                    placeholder="请输入当前密码"
                    :disabled="isLocked"
                    @keyup.enter.native="verifyPassword"
                  />
                </el-form-item>

                <!-- 锁定提示 -->
                <el-alert
                  v-if="isLocked"
                  title="已锁定"
                  type="error"
                  :closable="false"
                  show-icon
                  class="lock-alert"
                >
                  <template>
                    密码验证失败次数过多，已被锁定。
                    <br />
                    请在 <strong>{{ lockCountdown }}</strong> 秒后重试。
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
                  已失败 {{ failedAttempts }} 次，还剩 {{ 5 - failedAttempts }} 次机会
                </div>

                <div class="form-actions">
                  <el-button
                    type="primary"
                    :loading="verifyLoading"
                    :disabled="isLocked || !passwordForm.password"
                    @click="verifyPassword"
                  >
                    验证密码
                  </el-button>
                </div>
              </el-form>
            </div>

            <!-- 步骤2：扫描二维码并验证 -->
            <div v-if="currentStep === 2" class="step-container">
              <p class="settings-description">
                请使用认证器应用（如 Google Authenticator、Authy）扫描下方二维码，然后输入应用中显示的6位验证码以完成绑定。
              </p>

              <div v-loading="qrLoading" class="qr-code">
                <img v-if="qrCodeData" :src="qrCodeData" alt="2FA QR Code" />
                <span v-else>生成二维码中...</span>
              </div>

              <el-form :model="totpForm" class="verify-form" label-position="top">
                <el-form-item label="验证码">
                  <el-input
                    v-model="totpForm.twoFactorCode"
                    maxlength="6"
                    placeholder="请输入6位验证码"
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
                  <el-button @click="resetFlow">取消</el-button>
                  <el-button
                    type="primary"
                    :loading="bindingLoading"
                    :disabled="!totpForm.twoFactorCode || totpForm.twoFactorCode.length !== 6"
                    @click="confirmBinding"
                  >
                    确认绑定
                  </el-button>
                </div>
              </el-form>

              <div class="qr-instructions">
                <p><strong>使用步骤：</strong></p>
                <ol>
                  <li>下载认证器应用（如 Google Authenticator、Authy）</li>
                  <li>扫描上方二维码</li>
                  <li>输入应用中显示的6位验证码</li>
                  <li>点击"确认绑定"完成设置</li>
                </ol>
              </div>
            </div>

            <!-- 步骤3：绑定成功 -->
            <div v-if="currentStep === 3" class="step-container success-step">
              <el-result
                icon="success"
                title="双因素认证启用成功"
                sub-title="您的账户现在更安全了，下次登录时需要输入验证码。"
              >
                <template #extra>
                  <div class="backup-secret">
                    <p><strong>备份密钥（重要！）：</strong></p>
                    <el-input
                      :value="backupSecret"
                      readonly
                      type="textarea"
                      :rows="2"
                    />
                    <p class="secret-warning">
                      ⚠️ 密钥只会显示一次，请将此密钥保存在安全的地方，如果丢失认证器应用，可以使用此密钥恢复。
                    </p>
                  </div>
                  <el-button type="primary" @click="closeAndRefresh">
                    关闭
                  </el-button>
                </template>
              </el-result>
            </div>
            </div> <!-- 闭合 v-else 的div -->
          </div> <!-- 闭合 settings-card 的div -->
        </div> <!-- 闭合 settings-content 的div -->
      </el-tab-pane>

      <!-- 修改密码标签页 -->
      <el-tab-pane label="修改密码" name="password">
        <div class="settings-content">
          <div class="settings-card">
            <h3 class="settings-card-title">修改密码</h3>
            <p class="settings-description">
              定期修改密码可以保护账户安全，建议使用强密码。
            </p>
            <el-form :model="passwordFormChange" class="change-password-form" label-position="top">
              <el-form-item label="旧密码">
                <el-input
                  v-model="passwordFormChange.old_password"
                  type="password"
                  show-password
                  placeholder="请输入旧密码"
                />
              </el-form-item>
              <el-form-item label="新密码">
                <el-input
                  v-model="passwordFormChange.new_password"
                  type="password"
                  show-password
                  placeholder="请输入新密码"
                />
              </el-form-item>
              <el-form-item label="确认密码">
                <el-input
                  v-model="confirmPass"
                  type="password"
                  show-password
                  placeholder="请再次输入新密码"
                />
              </el-form-item>
              <div class="form-actions">
                <el-button @click="cancelPasswordChange">取消</el-button>
                <el-button type="primary" @click="changePassword">确认修改</el-button>
              </div>
            </el-form>
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
import request from '@/utils/request'

@Component({
  name: 'Settings'
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
  }

  beforeDestroy() {
    // 清理定时器
    if (this.lockTimer) {
      clearInterval(this.lockTimer)
    }
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
      this.errorMessage = '请输入密码'
      return
    }
    // 检查 userId 是否存在
    if (!UserModule.userId) {
      this.errorMessage = '用户信息获取失败，请重新登录'
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
        this.qrCodeData = response.data.qr_code_base64
        this.backupSecret = response.data.secret
        this.currentStep = 2
        this.$message({
          type: 'success',
          message: '密码验证成功'
        })
      } else {
        throw new Error(response.msg || '验证失败')
      }
    } catch (error: any) {
      // 验证失败
      this.failedAttempts++

      if (error.response?.data?.msg) {
        this.errorMessage = error.response.data.msg
      } else if (error.message) {
        this.errorMessage = error.message
      } else {
        this.errorMessage = '密码错误'
      }

      // 检查是否需要锁定
      if (this.failedAttempts >= 5) {
        this.lockEndTime = Date.now() + 5 * 60 * 1000 // 5分钟后
        this.saveFailedAttempts()
        this.startLockTimer()
        this.$message({
          type: 'error',
          message: '密码错误次数过多，已被锁定5分钟'
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
      this.bindingError = '请输入6位验证码'
      return
    }
    // 检查 userId 是否存在
    if (!UserModule.userId) {
      this.bindingError = '用户信息获取失败，请重新登录'
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
          message: '双因素认证启用成功'
        })
      } else {
        throw new Error(response.msg || '绑定失败')
      }
    } catch (error: any) {
      if (error.response?.data?.msg) {
        this.bindingError = error.response.data.msg
      } else if (error.message) {
        this.bindingError = error.message
      } else {
        this.bindingError = '验证码错误，请重试'
      }
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
    this.errorMessage = ''
    this.bindingError = ''
  }

  // 确认停用2FA（显示确认对话框）
  private confirmDisable2FA() {
    if (!this.disable2FAForm.password || !this.disable2FAForm.twoFactorCode) {
      this.errorMessage = '请填写当前密码和双因素验证码'
      return
    }

    if (this.disable2FAForm.twoFactorCode.length !== 6) {
      this.errorMessage = '双因素验证码必须是6位数字'
      return
    }

    // 显示确认对话框
    this.$confirm('停用双因素认证后，账户安全性将降低。是否继续停用？', '确认停用双因素认证', {
      confirmButtonText: '确认停用',
      cancelButtonText: '取消',
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
      this.errorMessage = '用户信息获取失败，请重新登录'
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
            message: '双因素认证已停用'
          })

          // 更新UserModule中的状态
          (UserModule as any).twoFactorFlag = '0'
        })
      } else {
        throw new Error(response.msg || '验证失败')
      }
    } catch (error: any) {
      // 验证失败
      this.failedAttempts++

      if (error.response?.data?.msg) {
        this.errorMessage = error.response.data.msg
      } else if (error.message) {
        this.errorMessage = error.message
      } else {
        this.errorMessage = '验证失败'
      }

      // 检查是否需要锁定
      if (this.failedAttempts >= 5) {
        this.lockEndTime = Date.now() + 5 * 60 * 1000 // 5分钟后
        this.saveFailedAttempts()
        this.startLockTimer()
        this.$message({
          type: 'error',
          message: '验证失败次数过多，已被锁定5分钟'
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
        message: '两次输入的密码不一致',
        type: 'warning',
        duration: 3000
      })
      return
    }

    // 检查 userId 是否存在
    if (!UserModule.userId) {
      this.$message({
        message: '用户信息获取失败，请重新登录',
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
        message: '密码修改成功',
        type: 'success',
        duration: 3000
      })

      this.cancelPasswordChange()
    } catch (error) {
      this.$message({
        message: '密码修改失败',
        type: 'error',
        duration: 3000
      })
    }
  }
  // 关闭绑定成功界面并切换到解绑界面
  private closeAndRefresh() {
    this.$confirm('关闭后将无法再次查看此密钥，是否确认关闭？', '确认关闭', {
      confirmButtonText: '确认关闭',
      cancelButtonText: '取消',
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
      this.errorMessage = ''
      this.bindingError = ''
      this.$message({
        type: 'success',
        message: '已关闭'
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
