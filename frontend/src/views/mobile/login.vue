<template>
  <div class="m-login">
    <div class="m-login-title">
      <AppLogo variant="full" class="m-login-logo" />
    </div>
    <div class="m-login-card">
      <el-button v-if="demoMode" type="text" class="m-login-demo" @click="enterDemoMode">
        进入演示模式
      </el-button>
      <el-input v-model="username" placeholder="用户名" autocomplete="username" class="m-login-input" />
      <el-input
        v-model="password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        show-password
        class="m-login-input"
        @keyup.enter.native="submit"
      />
      <el-button type="primary" class="m-login-button" :loading="loading" @click="submit">登录</el-button>
    </div>
    <el-button type="text" size="mini" class="m-login-desktop" @click="switchToDesktop">使用桌面版</el-button>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { UserModule } from '@/store/modules/user'
import { isDemoMode } from '@/demo/config'
import { extractErrorMessage } from '@/utils/formatters'
import { setStoredUiMode } from '@/utils/ui-mode'
import AppLogo from '@/components/common/AppLogo.vue'

/** 移动登录页（Phase 4 M1）：复用 user store Login action 与既有 token/守卫链路 */
@Component({
  name: 'MobileLogin',
  components: {
    AppLogo
  }
})
export default class MobileLogin extends Vue {
  private username = ''
  private password = ''
  private loading = false

  get demoMode(): boolean {
    return isDemoMode()
  }

  private enterDemoMode(): void {
    UserModule.InitializeDemoSession()
    this.$message.success('已进入演示模式')
    const redirect = this.$route.query.redirect
    const target = typeof redirect === 'string' && redirect.startsWith('/m/')
      ? redirect
      : '/m/dashboard'
    this.$router.replace(target).catch(() => undefined)
  }

  private async submit(): Promise<void> {
    if (!this.username || !this.password) {
      this.$message.warning('请输入用户名与密码')
      return
    }
    this.loading = true
    try {
      await UserModule.Login({ username: this.username, password: this.password })
      this.$message.success('登录成功')
      const redirect = this.$route.query.redirect
      const target = typeof redirect === 'string' && redirect.startsWith('/m/')
        ? redirect
        : '/m/dashboard'
      this.$router.replace(target).catch(() => undefined)
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private switchToDesktop(): void {
    setStoredUiMode('desktop')
    this.$router.replace('/login').catch(() => undefined)
  }
}
</script>

<style scoped>
.m-login {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-secondary, #F9FAFB);
  padding: 24px;
}

.m-login-title {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  margin-bottom: 24px;
}

.m-login-logo {
  width: 280px;
  height: 69px;
  max-width: 100%;
}

.m-login-card {
  width: 100%;
  max-width: 360px;
  background: #fff;
  border-radius: 10px;
  padding: 24px 16px;
}

.m-login-input {
  margin-bottom: 12px;
}

.m-login-button {
  width: 100%;
  margin-top: 4px;
}

.m-login-demo {
  display: block;
  width: 100%;
  margin-top: 8px;
}

.m-login-desktop {
  color: var(--color-text-secondary, #6B7280);
  margin-top: 16px;
}
</style>
