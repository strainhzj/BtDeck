<template>
  <div class="maintenance-page">
    <header class="maintenance-header">
      <h1 class="maintenance-title">{{ $t('database.maintenance.title') }}</h1>
      <p class="maintenance-description">{{ $t('database.maintenance.description') }}</p>
    </header>

    <!-- 认证区：未认证 / 维护会话过期时呈现（独立通道，token 仅内存，不弹全局 toast） -->
    <div v-if="!authenticated" class="maintenance-card">
      <h2 class="maintenance-card-title">{{ $t('database.maintenance.auth.title') }}</h2>
      <p class="maintenance-hint">{{ $t('database.maintenance.auth.hint') }}</p>
      <p v-if="sessionExpired" class="maintenance-warn">
        {{ $t('database.maintenance.auth.sessionExpired') }}
      </p>
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        label-position="top"
        class="maintenance-form"
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
        <el-button type="primary" :loading="loginLoading" @click="login">
          {{ loginLoading ? $t('database.maintenance.auth.submitting') : $t('database.maintenance.auth.submit') }}
        </el-button>
      </el-form>
      <p v-if="loginError" class="maintenance-warn">{{ loginError }}</p>
    </div>

    <template v-else>
      <!-- 状态区：粗粒度维护状态徽标 + 锚点（10s 轮询，beforeDestroy 清理） -->
      <div class="maintenance-card">
        <h2 class="maintenance-card-title">{{ $t('database.maintenance.state.title') }}</h2>
        <div class="maintenance-row">
          <el-tag :type="stateTagType" size="small">{{ stateLabel }}</el-tag>
          <span class="maintenance-muted">{{ $t('database.maintenance.state.autoRefresh') }}</span>
        </div>
        <div v-if="attemptIdText" class="maintenance-row">
          <span class="maintenance-label">{{ $t('database.maintenance.state.attemptId') }}</span>
          <code class="maintenance-mono">{{ attemptIdText }}</code>
        </div>
        <div v-if="epochText" class="maintenance-row">
          <span class="maintenance-label">{{ $t('database.maintenance.state.epoch') }}</span>
          <code class="maintenance-mono">{{ epochText }}</code>
        </div>
      </div>

      <!-- 迁移操作区：phase 徽标常显（100% 进度不掩盖未激活）+ 凭据重输 + 只读等待提示 -->
      <div class="maintenance-card">
        <h2 class="maintenance-card-title">{{ $t('database.maintenance.migration.title') }}</h2>

        <template v-if="migration">
          <div class="maintenance-row">
            <span class="maintenance-label">{{ $t('database.maintenance.migration.phase') }}</span>
            <el-tag :type="phaseTagType" size="small">{{ phaseLabel }}</el-tag>
            <el-tag v-if="readiness" :type="readiness.readyToSwitch ? 'success' : 'info'" size="small">
              {{ readiness.readyToSwitch ? $t('database.maintenance.migration.ready') : $t('database.maintenance.migration.notReady') }}
            </el-tag>
          </div>

          <div v-if="progress" class="maintenance-progress">
            <div class="maintenance-row">
              <span class="maintenance-label">{{ $t('database.maintenance.migration.progress') }}</span>
              <span class="maintenance-mono">{{ progressText }}</span>
            </div>
            <el-progress :percentage="progressPercent" :stroke-width="10" />
          </div>

          <!-- READY_TO_SWITCH：本页只读等待（switch 提交在设置面板 / 后续流程执行） -->
          <div v-if="readyToSwitch" class="maintenance-block maintenance-block-info">
            <h3 class="maintenance-block-title">{{ $t('database.maintenance.migration.readyToSwitchTitle') }}</h3>
            <p class="maintenance-hint">{{ $t('database.maintenance.migration.readyToSwitchHint') }}</p>
          </div>

          <!-- NEEDS_CREDENTIALS：凭据重输表单（载荷 snake_case attempt_id/password/target） -->
          <div v-if="needsCredentials" class="maintenance-block maintenance-block-danger">
            <h3 class="maintenance-block-title">{{ $t('database.maintenance.migration.needsCredentialsTitle') }}</h3>
            <p class="maintenance-hint">{{ $t('database.maintenance.migration.needsCredentialsHint') }}</p>
            <p v-if="credSuccess" class="maintenance-ok">
              {{ $t('database.maintenance.migration.credentialsSubmitted') }}
            </p>
            <el-form
              ref="credFormRef"
              :model="credForm"
              :rules="credRules"
              label-position="top"
              class="maintenance-form"
            >
              <div class="maintenance-form-grid">
                <el-form-item :label="$t('database.maintenance.migration.targetHost')" prop="host">
                  <el-input v-model="credForm.host" />
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetPort')" prop="port">
                  <el-input-number
                    v-model="credForm.port"
                    :min="1"
                    :max="65535"
                    controls-position="right"
                    class="maintenance-number"
                  />
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetUser')" prop="user">
                  <el-input v-model="credForm.user" />
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetPassword')" prop="password">
                  <el-input v-model="credForm.password" type="password" show-password />
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetDatabase')" prop="database">
                  <el-input v-model="credForm.database" />
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetSchema')" prop="schema">
                  <el-input
                    v-model="credForm.schema"
                    :placeholder="$t('database.maintenance.migration.targetSchemaPlaceholder')"
                  />
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetSslmode')" prop="sslmode">
                  <el-select v-model="credForm.sslmode" class="maintenance-select">
                    <el-option
                      v-for="mode in sslmodeOptions"
                      :key="mode"
                      :value="mode"
                      :label="mode"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item :label="$t('database.maintenance.migration.targetSslRootCert')" prop="sslRootCert">
                  <el-input
                    v-model="credForm.sslRootCert"
                    :placeholder="$t('database.maintenance.migration.targetSslRootCertPlaceholder')"
                  />
                </el-form-item>
              </div>
              <el-button type="primary" :loading="credSubmitting" @click="submitCredentials">
                {{ credSubmitting
                  ? $t('database.maintenance.migration.submittingCredentials')
                  : $t('database.maintenance.migration.submitCredentials') }}
              </el-button>
            </el-form>
            <p v-if="credError" class="maintenance-warn">{{ credError }}</p>
          </div>
        </template>
        <p v-else class="maintenance-hint">{{ $t('database.maintenance.migration.noAttempt') }}</p>
      </div>

      <!-- 提示区：restartPending → 手动重启提示 -->
      <div v-if="restartPending" class="maintenance-card maintenance-restart">
        <h2 class="maintenance-card-title">{{ $t('database.maintenance.restart.title') }}</h2>
        <p class="maintenance-warn">{{ $t('database.maintenance.restart.message') }}</p>
      </div>

      <div class="maintenance-actions">
        <el-button type="primary" plain @click="goHome">
          {{ $t('database.maintenance.actions.backHome') }}
        </el-button>
        <el-button @click="exitSession">{{ $t('database.maintenance.actions.exitSession') }}</el-button>
      </div>
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
  maintenanceRequest,
  subscribeAuthExpired
} from '@/utils/maintenance-client'
import type {
  CredentialsPayload,
  MigrationStatusData,
  PgFormInput,
  ReadinessData
} from '@/api/database'
import { ApiError } from '@/types/api'

/** sslmode 全档（后端 pg_params_from_mapping 契约；技术字面量不翻译） */
type SslMode = 'disable' | 'allow' | 'prefer' | 'require' | 'verify-ca' | 'verify-full'

/** 需要校验 CA 证书路径（ssl_root_cert）的 verify 档位 */
const SSL_VERIFY_MODES: readonly SslMode[] = ['verify-ca', 'verify-full']

/** el-tag 档位（空串 = 主题默认色） */
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

/** 粗粒度维护状态 → 人类可读文案键 */
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

/** 迁移 phase（后端小写字面量）→ 文案键（phase 徽标常显，进度 100% 不掩盖未激活） */
const PHASE_LABEL_KEYS: Readonly<Record<string, string>> = {
  idle: 'database.maintenance.migration.phaseIdle',
  preparing: 'database.maintenance.migration.phasePreparing',
  draining: 'database.maintenance.migration.phaseDraining',
  frozen: 'database.maintenance.migration.phaseFrozen',
  importing: 'database.maintenance.migration.phaseImporting',
  verifying: 'database.maintenance.migration.phaseVerifying',
  ready_to_switch: 'database.maintenance.migration.phaseReadyToSwitch',
  needs_credentials: 'database.maintenance.migration.phaseNeedsCredentials',
  cancelling: 'database.maintenance.migration.phaseCancelling',
  cancelled: 'database.maintenance.migration.phaseCancelled',
  failed: 'database.maintenance.migration.phaseFailed',
  held: 'database.maintenance.migration.phaseHeld',
  committed: 'database.maintenance.migration.phaseCommitted'
}

/** 迁移 phase → 徽标色 */
const PHASE_TAG_TYPES: Readonly<Record<string, TagType>> = {
  idle: 'info',
  preparing: 'info',
  draining: 'info',
  frozen: 'warning',
  importing: '',
  verifying: '',
  ready_to_switch: 'success',
  needs_credentials: 'danger',
  cancelling: 'warning',
  cancelled: 'warning',
  failed: 'danger',
  held: 'warning',
  committed: 'success'
}

/** 认证表单草稿（twofa 可选，提交时为空则不传） */
interface LoginForm {
  username: string
  password: string
  twofa: string
}

/** 凭据重输表单草稿（提交时映射 snake_case PgFormInput + 顶层 password） */
interface CredFormDraft {
  host: string
  port: number
  user: string
  password: string
  database: string
  schema: string
  sslmode: SslMode
  sslRootCert: string
}

/**
 * 维护恢复页（database-migration-ui W4-3）。
 *
 * - 独立可达（/maintenance，路由守卫白名单豁免）：业务 API 503 洪泛时的恢复面，
 *   页面自身绝不走 utils/request 普通通道；
 * - 认证区：maintenanceLogin 建立内存态维护 token；401 过期经
 *   subscribeAuthExpired 回调回到登录区（不弹 toast、不清其它会话）；
 * - 状态区：getMaintenanceStatus 粗粒度状态徽标，10s 轮询，
 *   beforeDestroy 清理定时器并退订；
 * - 迁移操作区：迁移状态/就绪面经 maintenanceRequest 直调
 *   /database/migration/status 与 /target-readiness（普通 request 通道在维护态
 *   会被 401/503 拦截，这里手动映射信封 data 为 @/api/database 类型）；
 *   NEEDS_CREDENTIALS 显示凭据重输表单（snake_case attempt_id/password/target）；
 *   READY_TO_SWITCH 只读等待提示（switch 提交不在本页执行）；
 * - 提示区：restartPending → 手动重启文案。
 */
@Component({ name: 'MaintenancePage' })
export default class extends Vue {
  // ---- 认证区（token 由 maintenance-client 模块级内存持有，本组件仅记布尔） ----
  private authenticated = false
  private sessionExpired = false
  private loginForm: LoginForm = { username: '', password: '', twofa: '' }
  private loginLoading = false
  private loginError: string | null = null

  // ---- 状态区（/maintenance/status 粗粒度） ----
  private status: MaintenanceStatusData | null = null

  // ---- 迁移操作区（维护通道直调 database 端点，信封 data 手动映射复用类型） ----
  private migration: MigrationStatusData | null = null
  private readiness: ReadinessData | null = null

  private credForm: CredFormDraft = {
    host: '',
    port: 5432,
    user: '',
    password: '',
    database: '',
    schema: 'public',
    sslmode: 'prefer',
    sslRootCert: ''
  }
  private credSubmitting = false
  private credError: string | null = null
  private credSuccess = false

  private readonly sslmodeOptions: readonly SslMode[] = [
    'disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'
  ]

  // ---- 10s 轮询 + 订阅退订（beforeDestroy 统一清理） ----
  private pollTimer: number | null = null
  private readonly pollIntervalMs = 10000
  private unsubscribeAuth: (() => void) | null = null

  get loginFormRef(): ElForm {
    return this.$refs.loginFormRef as ElForm
  }

  get credFormRef(): ElForm {
    return this.$refs.credFormRef as ElForm
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

  /** verify 档位：CA 路径（ssl_root_cert）必填 */
  get verifySslMode(): boolean {
    return SSL_VERIFY_MODES.indexOf(this.credForm.sslmode) >= 0
  }

  get credRules(): Record<string, Array<Record<string, unknown>>> {
    const requiredBlur = (): Record<string, unknown> => ({
      required: true,
      message: this.$t('database.maintenance.migration.requiredField').toString(),
      trigger: 'blur'
    })
    return {
      host: [requiredBlur()],
      port: [{ ...requiredBlur(), trigger: 'change' }],
      user: [requiredBlur()],
      password: [requiredBlur()],
      database: [requiredBlur()],
      sslmode: [{ ...requiredBlur(), trigger: 'change' }],
      // verify 档位必填；非 verify 档不要求
      sslRootCert: this.verifySslMode
        ? [{
            required: true,
            message: this.$t('database.maintenance.migration.targetSslRootCertRequired').toString(),
            trigger: 'blur'
          }]
        : []
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
    return this.status?.attemptId || this.migration?.attemptId || ''
  }

  get epochText(): string {
    return this.status?.epoch || this.migration?.epoch || ''
  }

  get phaseCode(): string {
    return this.migration ? this.migration.phase : ''
  }

  get phaseLabel(): string {
    const key = PHASE_LABEL_KEYS[this.phaseCode]
    if (key) {
      return this.$t(key).toString()
    }
    return this.$t('database.maintenance.migration.phaseUnknown', {
      phase: this.phaseCode || '—'
    }).toString()
  }

  get phaseTagType(): TagType {
    return PHASE_TAG_TYPES[this.phaseCode] ?? 'info'
  }

  /** 进度（detail.progress {done,total}）；无效/缺失时为 null（不渲染进度条） */
  get progress(): { done: number, total: number } | null {
    const detail = this.migration ? this.migration.detail : undefined
    const p = detail ? detail.progress : undefined
    if (!p || typeof p.done !== 'number' || typeof p.total !== 'number' || p.total <= 0) {
      return null
    }
    return { done: p.done, total: p.total }
  }

  get progressPercent(): number {
    const p = this.progress
    if (!p) return 0
    return Math.min(100, Math.floor((p.done / p.total) * 100))
  }

  get progressText(): string {
    const p = this.progress
    if (!p) return ''
    return this.$t('database.maintenance.migration.progressCount', {
      done: p.done,
      total: p.total
    }).toString()
  }

  /** NEEDS_CREDENTIALS：迁移状态 / 就绪面 / 粗粒度状态任一命中即呈现凭据重输 */
  get needsCredentials(): boolean {
    if (this.migration && this.migration.needsCredentials) return true
    if (this.readiness && this.readiness.needsCredentials) return true
    return this.stateCode === 'NEEDS_CREDENTIALS'
  }

  /** READY_TO_SWITCH：只读等待提示（本页不执行 switch 提交） */
  get readyToSwitch(): boolean {
    if (this.readiness && this.readiness.readyToSwitch) return true
    return this.phaseCode === 'ready_to_switch' || this.stateCode === 'READY_TO_SWITCH'
  }

  get restartPending(): boolean {
    if (this.migration) return this.migration.restartPending === true
    return this.stateCode === 'COMMITTED_PENDING_RESTART'
  }

  mounted(): void {
    this.unsubscribeAuth = subscribeAuthExpired(this.handleAuthExpired)
    // 同页重挂载（如布局重排）时内存 token 仍有效：直接进入已认证视图
    if (getMaintenanceToken()) {
      this.authenticated = true
      void this.refreshAll()
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

  /** 维护会话认证：成功进入状态视图并立即拉取（失败展示行内错误，不弹 toast） */
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
      void this.refreshAll()
      this.syncPolling()
    } catch (error) {
      this.loginError = error instanceof ApiError && error.message
        ? error.message
        : this.$t('database.maintenance.auth.failed').toString()
    } finally {
      this.loginLoading = false
    }
  }

  /** 401 订阅回调：维护 token 过期 → 回登录区（不弹 toast、不触碰其它会话） */
  private handleAuthExpired(): void {
    this.resetToLoginArea(true)
  }

  /** 退出维护会话（手动）：同样只清维护 token，不动普通会话 */
  private exitSession(): void {
    this.resetToLoginArea(false)
  }

  private resetToLoginArea(expired: boolean): void {
    clearMaintenanceToken()
    this.authenticated = false
    this.sessionExpired = expired
    this.loginError = null
    this.loginForm.password = ''
    this.loginForm.twofa = ''
    this.status = null
    this.migration = null
    this.readiness = null
    this.credError = null
    this.credSuccess = false
    this.credForm.password = ''
    this.clearPollTimer()
  }

  /** 登录后从本页返回入口（普通导航由路由守卫接管：无业务会话时会落登录页） */
  private goHome(): void {
    void this.$router.push('/')
  }

  /** 全量刷新：维护状态 + 迁移状态/就绪面（错误静默保持旧值；401 已由通道派发） */
  private async refreshAll(): Promise<void> {
    await Promise.all([this.fetchMaintenanceStatus(), this.fetchMigrationFaces()])
  }

  private async fetchMaintenanceStatus(): Promise<void> {
    try {
      this.status = await getMaintenanceStatus()
    } catch {
      // 静默保持旧值：503/网络抖动不打扰用户；401 已由通道派发 auth expired
    }
  }

  private async fetchMigrationFaces(): Promise<void> {
    try {
      this.migration = await maintenanceRequest<MigrationStatusData>(
        'get',
        '/database/migration/status'
      )
    } catch {
      // 静默保持旧值（维护通道无重试/无 toast）
    }
    try {
      this.readiness = await maintenanceRequest<ReadinessData>(
        'get',
        '/database/target-readiness'
      )
    } catch {
      // 静默保持旧值
    }
  }

  /** NEEDS_CREDENTIALS 恢复：重输绑定目标凭据（snake_case attempt_id/password/target） */
  private async submitCredentials(): Promise<void> {
    if (this.credSubmitting) return
    const attemptId = this.migration?.attemptId || ''
    if (!attemptId) {
      this.credError = this.$t('database.maintenance.migration.noAttempt').toString()
      return
    }
    let valid = false
    try {
      valid = await this.credFormRef.validate()
    } catch {
      valid = false
    }
    if (!valid) return
    this.credSubmitting = true
    this.credError = null
    this.credSuccess = false
    try {
      const payload: CredentialsPayload = {
        attempt_id: attemptId,
        password: this.credForm.password,
        target: this.buildCredTarget()
      }
      this.migration = await maintenanceRequest<MigrationStatusData>(
        'post',
        '/database/migration/credentials',
        payload
      )
      this.credSuccess = true
      this.credForm.password = ''
      void this.refreshAll()
    } catch (error) {
      this.credError = error instanceof ApiError && error.message
        ? error.message
        : this.$t('database.maintenance.migration.credentialsFailed').toString()
    } finally {
      this.credSubmitting = false
    }
  }

  /** 凭据草稿 → 后端 PgFormInput（snake_case 契约；缺省项由后端补全） */
  private buildCredTarget(): PgFormInput {
    return {
      host: this.credForm.host.trim(),
      port: this.credForm.port,
      user: this.credForm.user.trim(),
      password: this.credForm.password,
      database: this.credForm.database.trim(),
      schema: this.credForm.schema.trim() || 'public',
      sslmode: this.credForm.sslmode,
      ssl_root_cert: this.verifySslMode ? this.credForm.sslRootCert.trim() : null
    }
  }

  private syncPolling(): void {
    if (this.authenticated && this.pollTimer === null) {
      this.pollTimer = window.setInterval(() => {
        void this.refreshAll()
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

<style lang="scss" scoped>
// 独立整页（不挂桌面 Layout）：居中窄栏卡片流，复用全局主题变量
.maintenance-page {
  min-height: 100vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 16px;
  background: var(--color-bg-secondary);
}

.maintenance-header {
  max-width: 640px;
  width: 100%;
  margin-bottom: 24px;
}

.maintenance-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 8px;
}

.maintenance-description {
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin: 0;
}

.maintenance-card {
  max-width: 640px;
  width: 100%;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 16px;
  box-sizing: border-box;
}

.maintenance-card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 12px;
}

.maintenance-restart {
  border-color: var(--color-warning);
}

.maintenance-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 0;
  flex-wrap: wrap;
}

.maintenance-label {
  font-size: 13px;
  font-weight: 600;
  min-width: 140px;
}

.maintenance-muted {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.maintenance-mono {
  font-size: 13px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  word-break: break-all;
}

.maintenance-hint {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin: 0 0 12px;
}

.maintenance-warn {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-warning-dark);
  margin: 0 0 8px;
}

.maintenance-ok {
  font-size: 13px;
  color: var(--color-success-dark);
  margin: 0 0 8px;
}

.maintenance-progress {
  padding: 8px 0;
}

.maintenance-block {
  border: 1px solid var(--color-border-primary);
  border-radius: 6px;
  padding: 12px 16px;
  margin-top: 12px;
}

.maintenance-block-info {
  border-color: var(--color-success);
}

.maintenance-block-danger {
  border-color: var(--color-danger);
}

.maintenance-block-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 6px;
}

.maintenance-form {
  margin-top: 8px;
}

.maintenance-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.maintenance-select,
.maintenance-number {
  width: 100%;
}

.maintenance-actions {
  max-width: 640px;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
}

@media (max-width: 768px) {
  .maintenance-form-grid {
    grid-template-columns: 1fr;
  }

  .maintenance-label {
    min-width: 110px;
  }
}
</style>
