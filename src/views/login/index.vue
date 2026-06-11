<template>
  <div class="login-container">
    <!-- 背景装饰 -->
    <div class="login-background">
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
      <div class="bg-circle bg-circle-3"></div>
    </div>

    <!-- 主题切换器 -->
    <div class="theme-selector">
      <theme-switcher />
    </div>

    <!-- 登录卡片 -->
    <div class="login-card">
      <!-- Logo和标题 -->
      <div class="login-header">
        <div class="logo-container">
          <svg-icon name="dashboard" class="logo-icon" />
        </div>
        <h1 class="login-title">BtDeck</h1>
        <p class="login-subtitle">统一管理您的下载器</p>
      </div>

      <!-- 登录表单 -->
      <el-form
        ref="loginForm"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        autocomplete="on"
        @submit.native.prevent="handleLogin"
      >
        <!-- 用户名输入 -->
        <el-form-item prop="username">
          <el-input
            ref="username"
            v-model="loginForm.username"
            placeholder="用户名"
            name="username"
            type="text"
            autocomplete="username"
            prefix-icon="el-icon-user"
            size="large"
          />
        </el-form-item>

        <!-- 密码输入 -->
        <el-form-item prop="password">
          <el-input
            :key="passwordType"
            ref="password"
            v-model="loginForm.password"
            :type="passwordType"
            placeholder="密码"
            name="password"
            autocomplete="current-password"
            prefix-icon="el-icon-lock"
            size="large"
            @keyup.enter.native="handleLogin"
          >
            <i
              slot="suffix"
              class="el-input__icon el-icon-view"
              :class="{'show-pwd': passwordType === 'text'}"
              @click="showPwd"
            />
          </el-input>
        </el-form-item>

        <!-- TOTP验证码 -->
        <el-form-item prop="twofa_code">
          <el-input
            ref="twofa"
            v-model="loginForm.twofa_code"
            placeholder="双因素验证码（如有设置必须填写）"
            name="twofa_code"
            type="text"
            maxlength="6"
            prefix-icon="el-icon-key"
            size="large"
            @keyup.enter.native="handleLogin"
          />
        </el-form-item>

        <!-- 记住我 & 忘记密码 -->
        <div class="login-options">
          <el-checkbox v-model="rememberMe">记住我</el-checkbox>
          <el-link type="primary" :underline="false">忘记密码？</el-link>
        </div>

        <!-- 登录按钮 -->
        <el-button
          :loading="loading"
          type="primary"
          size="large"
          class="login-button"
          native-type="submit"
        >
          {{ loading ? '登录中...' : '登录' }}
        </el-button>
      </el-form>

      <!-- 底部链接 -->
      <div class="login-footer">
        <p class="footer-text">
          还没有账号？
          <el-link type="primary" :underline="false">立即注册</el-link>
        </p>
      </div>
    </div>

    <!-- 版权信息 -->
    <div class="copyright">
      <p>© 2025 BtDeck. All rights reserved.</p>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Watch } from 'vue-property-decorator'
import { Route } from 'vue-router'
import { Dictionary } from 'vue-router/types/router'
import { Form as ElForm, Input } from 'element-ui'
import { UserModule } from '@/store/modules/user'
import { isValidUsername } from '@/utils/validate'
import ThemeSwitcher from '@/components/ThemeSwitcher/index.vue'

@Component({
  name: 'Login',
  components: {
    ThemeSwitcher
  }
})
export default class extends Vue {
  private loginForm = {
    username: '',
    password: '',
    twofa_code: ''
  }

  private loginRules = {
    username: [{ validator: this.validateUsername, trigger: 'blur' }],
    password: [{ validator: this.validatePassword, trigger: 'blur' }],
    twofa_code: [{ validator: this.validateTwofaCode, trigger: 'blur' }]
  }

  private passwordType = 'password'
  private loading = false
  private rememberMe = false
  private redirect?: string
  private isLoggingIn = false  // 防止重复提交的标志
  private isDestroyed = false  // 组件销毁标志，防止状态更新错误

  private validateTwofaCode = (rule: any, value: string, callback: Function) => {
    // 2FA验证码为可选，如果填写了必须是6位数字
    if (!value) {
      callback()
      return
    }
    if (!/^\d{6}$/.test(value)) {
      callback(new Error('双因素验证码必须是6位数字'))
      return
    }
    callback()
  }

  private validateUsername = (rule: any, value: string, callback: Function) => {
    if (!isValidUsername(value)) {
      callback(new Error('请输入正确的用户名'))
    } else {
      callback()
    }
  }

  private validatePassword = (rule: any, value: string, callback: Function) => {
    if (value.length < 5) {
      callback(new Error('密码长度不能少于5位'))
    } else {
      callback()
    }
  }

  private showPwd() {
    if (this.passwordType === 'password') {
      this.passwordType = 'text'
    } else {
      this.passwordType = 'password'
    }
    this.$nextTick(() => {
      (this.$refs.password as Input).focus()
    })
  }

  private handleLogin() {
    // 防止重复提交
    if (this.isLoggingIn) {
      return
    }

    (this.$refs.loginForm as ElForm).validate(async(valid: boolean) => {
      if (valid) {
        this.isLoggingIn = true
        this.loading = true
        try {
          await UserModule.Login(this.loginForm)
          // 先显示成功消息，确保用户能看到反馈
          // 检查组件是否已销毁，避免在销毁的组件上更新状态
          if (!this.isDestroyed) {
            this.$message.success('登录成功')
          }
          // 登录成功后主动触发路由导航，让路由守卫处理重定向逻辑
          // 路由守卫会检测到token存在，并自动跳转到redirect参数或首页
          await this.$router.push(this.redirect || '/')
        } catch (error) {
          // 显示后端返回的错误消息
          const errorMessage = error instanceof Error ? error.message : '登录失败，请重试'
          if (!this.isDestroyed) {
            this.$message.error(errorMessage)
          }
          console.error('登录失败:', error)
        } finally {
          // 检查组件是否已销毁再重置状态
          if (!this.isDestroyed) {
            this.loading = false
            this.isLoggingIn = false
          }
        }
      }
    })
  }

  @Watch('$route', { immediate: true })
  private onRouteChange(route: Route) {
    const query = route.query as Dictionary<string>
    if (query.redirect) {
      this.redirect = query.redirect
    }
  }

  // 组件销毁前设置标志，防止异步操作更新已销毁的组件
  private beforeDestroy() {
    this.isDestroyed = true
  }
}
</script>

<style lang="scss" scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: var(--color-bg-primary);
}

// 背景装饰
.login-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  overflow: hidden;
}

.bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.1;
  background: var(--color-primary);
  filter: blur(60px);
  animation: float 20s infinite ease-in-out;
}

.bg-circle-1 {
  width: 400px;
  height: 400px;
  top: -100px;
  right: -100px;
  animation-delay: 0s;
}

.bg-circle-2 {
  width: 300px;
  height: 300px;
  bottom: -50px;
  left: -50px;
  animation-delay: 5s;
}

.bg-circle-3 {
  width: 200px;
  height: 200px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation-delay: 10s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(30px, -30px) scale(1.1);
  }
  66% {
    transform: translate(-20px, 20px) scale(0.9);
  }
}

// 主题切换器
.theme-selector {
  position: absolute;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  z-index: 10;
}

// 登录卡片
.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 420px;
  padding: var(--spacing-2xl);
  background: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  border: 1px solid var(--color-border-primary);
  animation: slideUp 0.6s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// 登录头部
.login-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
}

.logo-container {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-md);
  box-shadow: var(--shadow-lg);
}

.logo-icon {
  width: 36px;
  height: 36px;
  color: white;
}

.login-title {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-sm);
}

.login-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

// 登录表单
.login-form {
  margin-top: var(--spacing-xl);
}

::v-deep .el-form-item {
  margin-bottom: var(--spacing-lg);
}

::v-deep .el-input__inner {
  height: 48px;
  line-height: 48px;
  padding-left: 48px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  font-size: var(--font-size-md);
  transition: all var(--transition-base);

  &:focus {
    border-color: var(--color-primary);
    background: var(--color-bg-primary);
  }

  &::placeholder {
    color: var(--color-text-tertiary);
  }
}

::v-deep .el-input__prefix {
  left: 12px;
}

::v-deep .el-input__suffix {
  right: 12px;
}

::v-deep .el-input__icon {
  font-size: var(--font-size-lg);
  color: var(--color-text-tertiary);
}

.show-pwd {
  cursor: pointer;
  color: var(--color-primary) !important;
}

// 登录选项
.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

::v-deep .el-checkbox__label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

// 登录按钮
.login-button {
  width: 100%;
  height: 48px;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
  border: none;
  box-shadow: var(--shadow-md);
  transition: all var(--transition-base);

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
  }

  &:active {
    transform: translateY(0);
  }
}

// 底部
.login-footer {
  margin-top: var(--spacing-xl);
  text-align: center;
}

.footer-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

// 版权信息
.copyright {
  position: absolute;
  bottom: var(--spacing-lg);
  left: 0;
  right: 0;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  z-index: 1;
}

.copyright p {
  margin: 0;
}

// 响应式设计
@media (max-width: 768px) {
  .login-card {
    max-width: 100%;
    margin: var(--spacing-md);
    padding: var(--spacing-xl);
  }

  .login-title {
    font-size: var(--font-size-2xl);
  }

  .login-subtitle {
    font-size: var(--font-size-xs);
  }

  .logo-container {
    width: 56px;
    height: 56px;
  }

  .logo-icon {
    width: 32px;
    height: 32px;
  }

  .action-buttons {
    flex-direction: column;
  }

  .back-button,
  .home-button {
    width: 100%;
  }
}
</style>
