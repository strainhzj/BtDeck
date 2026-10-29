<template>
  <div class="m-maintenance">
    <h1 class="m-maintenance-title">{{ $t('database.mobile.title') }}</h1>
    <p class="m-maintenance-desc">{{ $t('database.mobile.description') }}</p>

    <!-- 认证区：维护会话独立认证（token 仅内存；与桌面维护页同一通道） -->
    <div v-if="!authenticated" class="m-card">
      <h2 class="m-card-title">{{ $t('database.maintenance.auth.title') }}</h2>
      <p class="m-hint">{{ $t('database.maintenance.auth.hint') }}</p>
      <p v-if="sessionExpired" class="m-warn">
        {{ $t('database.maintenance.auth.sessionExpired') }}
      </p>
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        label-position="top"
        @submit.native.prevent="login"
      >
        <el-form-item :label="$t('database.maintenance.auth.username')" prop="username">
          <el-input v-model="loginForm.username" :disabled="loginLoading" />
        </el-form-item>
        <el-form-item :label="$t('database.maintenance.auth.password')" prop="password">
          <el-input v-model="loginForm.password" type="password" show-password :disabled="loginLoading" />
        </el-form-item>
        <el-form-item :label="$t('database.maintenance.auth.twofa')" prop="twofa">
          <el-input v-model="loginForm.twofa" :disabled="loginLoading" />
        </el-form-item>
        <el-button type="primary" size="small" :loading="loginLoading" @click="login">
          {{ loginLoading ? $t('database.maintenance.auth.submitting') : $t('database.maintenance.auth.submit') }}
        </el-button>
      </el-form>
      <p v-if="loginError" class="m-warn">{{ loginError }}</p>
    </div>

    <template v-else>
      <!-- 状态区：粗粒度维护状态徽标 + 锚点（10s 轮询，beforeDestroy 清理） -->
      <div class="m-card">
        <h2 class="m-card-title">{{ $t('database.maintenance.state.title') }}</h2>
        <div class="m-row">
          <el-tag :type="stateTagType" size="small">{{ stateLabel }}</el-tag>
          <span class="m-muted">{{ $t('database.maintenance.state.autoRefresh') }}</span>
        </div>
        <div v-if="attemptIdText" class="m-row">
          <span class="m-label">{{ $t('database.maintenance.state.attemptId') }}</span>
          <code class="m-mono">{{ attemptIdText }}</code>
        </div>
        <div v-if="epochText" class="m-row">
          <span class="m-label">{{ $t('database.maintenance.state.epoch') }}</span>
          <code class="m-mono">{{ epochText }}</code>
        </div>
      </div>

      <!-- restartPending → 手动重启提示 -->
      <div v-if="restartPending" class="m-card m-card--warn">
        <h2 class="m-card-title">{{ $t('database.maintenance.restart.title') }}</h2>
        <p class="m-warn">{{ $t('database.maintenance.restart.message') }}</p>
      </div>

      <!-- 只读指引：移动端不承载凭据重输/迁移操作（桌面维护页承载） -->
      <div class="m-card">
        <h2 class="m-card-title">{{ $t('database.mobile.guidanceTitle') }}</h2>
        <p class="m-hint">{{ $t('database.mobile.readOnlyHint') }}</p>
      </div>

      <el-button size="small" class="m-exit" @click="exitSession">
        {{ $t('database.maintenance.actions.exitSession') }}
      </el-button>
    </template>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import {
  MaintenanceStatusData,
  clearMaintenanceToken,
  getMaintenanceStatus,
  getMaintenanceToken,
  maintenanceLogin,
  subscribeAuthExpired
} from '@/utils/maintenance-client'

/** el-tag 档位（空串 = 主题默认色；与桌面维护页同口径） */
type TagType = 'success' | 'info' | 'warning' | 'danger' | ''

/** 粗粒度维护状态（/maintenance/status 的 state，W4-1 契约大写码）→ 徽标色 */
const STATE_TAG_TYPES: Readonly<Record<string, TagType>> = {
  PREPARING: 'info',
  DRAINING: 'info',
  FROZEN: 'warning',
  IMPORTING: '',
  VERIFYING: '',
  READY_TO_SWITCH: 'success',
  NEEDS_CREDENTIALS: 'danger',
  COMMITTED_PENDING_RESTART: 'warning'
}

/** 粗粒度维护状态 → 人类可读文案键（复用桌面维护页 i18n 子域） */
const STATE_LABEL_KEYS: Readonly<Record<string, string>> = {
  PREPARING: 'database.maintenance.state.preparing',
  DRAINING: 'database.maintenance.state.draining',
  FROZEN: 'database.maintenance.state.frozen',
  IMPORTING: 'database.maintenance.state.importing',
  VERIFYING: 'database.maintenance.state.verifying',
  READY_TO_SWITCH: 'database.maintenance.state.readyToSwitch',
  NEEDS_CREDENTIALS: 'database.maintenance.state.needsCredentials',
  COMMITTED_PENDING_RESTART: 'database.maintenance.state.committedPendingRestart'
}

/** 认证表单草稿（twofa 可选，提交时为空则不传；与桌面维护页同契约） */
interface LoginForm {
  username: string
  password: string
  twofa: string
}

/**
 * 移动维护只读入口（database-migration-ui W4-4；/m/maintenance）。
 *
 * - 桌面维护页（/maintenance）的移动精简版：复用 maintenance-client 同一认证
 *   通道（maintenance token 仅内存）与 /maintenance/status 粗粒度状态；
 * - 只读定位：状态徽标 + attemptId/epoch 锚点 + restartPending 手动重启提示；
 *   不渲染凭据重输表单、不发起任何迁移操作（NEEDS_CREDENTIALS 等状态同样
 *   只给只读指引，操作面在桌面维护页）；
 * - 不做平台能力门控：维护/恢复面必须全平台可达（§9 门控只作用于设置面板
 *   的 PG 表单与切换入口）；
 * - 生命周期：认证后 10s 轮询，beforeDestroy 清理定时器并退订 auth expired。
 */
@Component({ name: 'MobileMaintenance' })
export default class extends Vue {
  private authenticated = false
  private sessionExpired = false
  private loginForm: LoginForm = { username: '', password: '', twofa: '' }
  private loginLoading = false
  private loginError: string | null = null

  private status: MaintenanceStatusData | null = null

  private pollTimer: number | null = null
  private readonly pollIntervalMs = 10000
  private unsubscribeAuth: (() => void) | null = null

  get loginFormRef(): ElForm {
    return this.$refs.loginFormRef as ElForm
  }

  get loginRules(): Record<string, Array<Record<string, unknown>>> {
    const requiredBlur = (): Record<string, unknown> => ({
      required: true,
      message: this.$t('database.maintenance.auth.failed').toString(),
      trigger: 'blur'
    })
    return {
      username: [requiredBlur()],
      password: [requiredBlur()]
      // twofa 可选：无校验规则
    }
  }

  /** 粗粒度维护状态码（大写；未知/未取到时 UNKNOWN） */
  get stateCode(): string {
    if (!this.status || !this.status.state) return 'UNKNOWN'
    return this.status.state.toUpperCase()
  }

  get stateLabel(): string {
    const key = STATE_LABEL_KEYS[this.stateCode]
    if (key) {
      return this.$t(key).toString()
    }
    return this.$t('database.maintenance.state.unknown', { code: this.stateCode }).toString()
  }

  get stateTagType(): TagType {
    return STATE_TAG_TYPES[this.stateCode] ?? 'info'
  }

  get attemptIdText(): string {
    return this.status?.attemptId || ''
  }

  get epochText(): string {
    return this.status?.epoch || ''
  }

  get restartPending(): boolean {
    return this.stateCode === 'COMMITTED_PENDING_RESTART'
  }

  mounted(): void {
    this.unsubscribeAuth = subscribeAuthExpired(this.handleAuthExpired)
    // 同页重挂载时内存 token 仍有效：直接进入已认证视图
    if (getMaintenanceToken()) {
      this.authenticated = true
      void this.fetchStatus()
    }
    this.syncPolling()
  }

  beforeDestroy(): void {
    this.clearPollTimer()
    if (this.unsubscribeAuth) {
      this.unsubscribeAuth()
      this.unsubscribeAuth = null
    }
  }

  /** 维护会话认证：成功进入状态视图并立即拉取（失败行内提示，不弹 toast） */
  private async login(): Promise<void> {
    if (this.loginLoading) return
    let valid = false
    try {
      valid = await this.loginFormRef.validate()
    } catch {
      valid = false
    }
    if (!valid) return
    this.loginLoading = true
    this.loginError = null
    try {
      await maintenanceLogin(
        this.loginForm.username.trim(),
        this.loginForm.password,
        this.loginForm.twofa.trim() || undefined
      )
      this.loginForm.password = ''
      this.loginForm.twofa = ''
      this.authenticated = true
      this.sessionExpired = false
      void this.fetchStatus()
      this.syncPolling()
    } catch (error) {
      this.loginError = error instanceof Error && error.message
        ? error.message
        : this.$t('database.maintenance.auth.failed').toString()
    } finally {
      this.loginLoading = false
    }
  }

  /** 401 订阅回调：维护 token 过期 → 回认证区（不弹 toast、不触碰普通会话） */
  private handleAuthExpired(): void {
    this.resetToAuthArea(true)
  }

  /** 退出维护会话（手动）：只清维护 token，不动普通会话 */
  private exitSession(): void {
    this.resetToAuthArea(false)
  }

  private resetToAuthArea(expired: boolean): void {
    clearMaintenanceToken()
    this.authenticated = false
    this.sessionExpired = expired
    this.loginError = null
    this.loginForm.password = ''
    this.loginForm.twofa = ''
    this.status = null
    this.clearPollTimer()
  }

  /** 粗粒度状态拉取（错误静默保持旧值；401 已由通道派发 auth expired） */
  private async fetchStatus(): Promise<void> {
    try {
      this.status = await getMaintenanceStatus()
    } catch {
      // 静默保持旧值：503/网络抖动不打扰用户
    }
  }

  private syncPolling(): void {
    if (this.authenticated && this.pollTimer === null) {
      this.pollTimer = window.setInterval(() => {
        void this.fetchStatus()
      }, this.pollIntervalMs)
    } else if (!this.authenticated) {
      this.clearPollTimer()
    }
  }

  private clearPollTimer(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer)
      this.pollTimer = null
    }
  }
}
</script>

<style scoped>
.m-maintenance-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 4px 0 6px;
}

.m-maintenance-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin: 0 0 12px;
}

.m-card {
  background: #fff;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 10px;
}

.m-card--warn {
  border: 1px solid var(--color-warning);
}

.m-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 8px;
}

.m-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  flex-wrap: wrap;
}

.m-label {
  font-size: 13px;
  font-weight: 600;
}

.m-muted {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.m-mono {
  font-size: 13px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  word-break: break-all;
}

.m-hint {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin: 0 0 10px;
}

.m-warn {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-warning-dark);
  margin: 0 0 8px;
}

.m-exit {
  display: flex;
  margin: 4px auto 0;
}
</style>
