<template>
  <div class="database-panel">
    <!-- 状态卡：展示有效库实况（§9：active 优先，不把 env 当实况） -->
    <div class="db-card">
      <h3 class="db-card-title">{{ $t('database.status.title') }}</h3>
      <p class="db-description">
        {{ $t('database.panel.description') }}
      </p>

      <div v-if="loading" class="db-hint">{{ $t('database.panel.loading') }}</div>
      <div v-else-if="!loaded" class="db-hint">
        {{ $t('database.panel.loadFailed') }}
        <el-button size="mini" @click="load">{{ $t('database.panel.retry') }}</el-button>
      </div>

      <template v-else>
        <div class="db-status-row">
          <span class="db-label">{{ $t('database.status.source') }}</span>
          <el-tag :type="sourceTagType" size="small">{{ sourceLabel }}</el-tag>
        </div>
        <div class="db-status-row">
          <span class="db-label">{{ $t('database.status.dialect') }}</span>
          <span class="db-value">{{ dialectLabel }}</span>
        </div>

        <!-- SQLite 路径 / PG 脱敏摘要（无凭据字段；密码永不下发） -->
        <div v-if="sqlitePathText" class="db-status-row">
          <span class="db-label">{{ $t('database.status.sqlitePath') }}</span>
          <code class="db-value db-mono">{{ sqlitePathText }}</code>
        </div>
        <template v-else-if="pgMasked">
          <div class="db-status-row">
            <span class="db-label">{{ $t('database.status.pgTarget') }}</span>
            <code class="db-value db-mono">{{ pgTargetText }}</code>
          </div>
          <div class="db-status-row">
            <span class="db-label">{{ $t('database.status.sslmode') }}</span>
            <code class="db-value db-mono">{{ pgMasked.sslmode }}</code>
          </div>
          <div class="db-status-row">
            <span class="db-label">{{ $t('database.status.pool') }}</span>
            <span class="db-value">{{ poolText }}</span>
          </div>
        </template>

        <!-- 控制锚点：generation / restartPending（无受管控制时锚点整体缺省） -->
        <div v-if="control" class="db-status-row">
          <span class="db-label">{{ $t('database.status.generation') }}</span>
          <code class="db-value db-mono">{{ control.generation || '—' }}</code>
        </div>
        <div class="db-status-row">
          <span class="db-label">{{ $t('database.status.restartPending') }}</span>
          <el-tag :type="restartPending ? 'warning' : 'info'" size="small">
            {{ restartPending ? $t('database.status.restartPendingYes') : $t('database.status.restartPendingNo') }}
          </el-tag>
        </div>

        <!-- 托管重启能力（restart_adapter.hosting_capability() 下发） -->
        <div class="db-status-row">
          <span class="db-label">{{ $t('database.status.hosting') }}</span>
          <code class="db-value db-mono">{{ hosting.hosting }}</code>
          <el-tag :type="hosting.autoRestartCapable ? 'success' : 'warning'" size="small">
            {{ hosting.autoRestartCapable ? $t('database.status.autoRestart') : $t('database.status.noAutoRestart') }}
          </el-tag>
        </div>
        <p v-if="hostingHint" class="db-description db-hosting-hint">{{ hostingHint }}</p>
      </template>
    </div>

    <!-- PG 目标表单卡（仅迁移入口用；本页只做只读探测，不保存密码、不提交迁移）
         平台门控（W4-4）：矩阵 db_migration 非 supported / demo / Android WebView
         任一命中 → 表单整体只读化（el-form disabled 传播至全部内嵌控件） -->
    <div class="db-card">
      <h3 class="db-card-title">{{ $t('database.form.title') }}</h3>
      <p class="db-description">
        {{ $t('database.form.description') }}
      </p>
      <p v-for="note in guardNotes" :key="note" class="db-guard-note">{{ note }}</p>

      <el-form
        ref="pgFormRef"
        :model="pgForm"
        :rules="pgRules"
        :disabled="migrationEntriesLocked"
        label-position="top"
        class="db-form"
      >
        <div class="db-form-grid">
          <el-form-item :label="$t('database.form.host')" prop="host">
            <el-input v-model="pgForm.host" />
          </el-form-item>
          <el-form-item :label="$t('database.form.port')" prop="port">
            <el-input-number
              v-model="pgForm.port"
              :min="1"
              :max="65535"
              controls-position="right"
              class="db-number"
            />
          </el-form-item>
          <el-form-item :label="$t('database.form.user')" prop="user">
            <el-input v-model="pgForm.user" />
          </el-form-item>
          <el-form-item :label="$t('database.form.password')" prop="password">
            <el-input v-model="pgForm.password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="$t('database.form.database')" prop="database">
            <el-input v-model="pgForm.database" />
          </el-form-item>
          <el-form-item :label="$t('database.form.schema')" prop="schema">
            <el-input v-model="pgForm.schema" :placeholder="$t('database.form.schemaPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('database.form.sslmode')" prop="sslmode">
            <el-select v-model="pgForm.sslmode" class="db-select">
              <el-option
                v-for="mode in sslmodeOptions"
                :key="mode"
                :value="mode"
                :label="mode"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('database.form.sslRootCert')" prop="sslRootCert">
            <el-input
              v-model="pgForm.sslRootCert"
              :placeholder="$t('database.form.sslRootCertPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="$t('database.form.poolSize')" prop="poolSize">
            <el-input-number v-model="pgForm.poolSize" :min="1" controls-position="right" class="db-number" />
          </el-form-item>
          <el-form-item :label="$t('database.form.maxOverflow')" prop="maxOverflow">
            <el-input-number v-model="pgForm.maxOverflow" :min="0" controls-position="right" class="db-number" />
          </el-form-item>
          <el-form-item :label="$t('database.form.poolTimeout')" prop="poolTimeout">
            <el-input-number v-model="pgForm.poolTimeout" :min="1" controls-position="right" class="db-number" />
          </el-form-item>
        </div>

        <div class="db-actions">
          <el-button
            size="small"
            type="primary"
            plain
            :loading="testing"
            :disabled="migrationEntriesLocked"
            @click="runTestConnection"
          >
            {{ $t('database.form.testConnection') }}
          </el-button>
        </div>

        <!-- 探测三态：reachable / versionOk / targetEmpty（PG 另附版本与协商 TLS） -->
        <div v-if="testResult" class="db-test-result">
          <div class="db-status-row">
            <span class="db-label">{{ $t('database.form.resultReachableLabel') }}</span>
            <span :class="testResult.reachable ? 'db-ok' : 'db-bad'">
              {{ testResult.reachable ? $t('database.form.resultReachableOk') : $t('database.form.resultReachableBad') }}
            </span>
          </div>
          <template v-if="testResult.reachable">
            <div class="db-status-row">
              <span class="db-label">{{ $t('database.form.resultVersionLabel') }}</span>
              <span :class="testResult.versionOk ? 'db-ok' : 'db-bad'">
                {{ testResult.versionOk ? $t('database.form.resultVersionOk') : $t('database.form.resultVersionBad') }}
              </span>
              <span v-if="testResult.serverVersion" class="db-muted">
                {{ $t('database.form.resultVersionInfo', {version: testResult.serverVersion}) }}
              </span>
            </div>
            <div class="db-status-row">
              <span class="db-label">{{ $t('database.form.resultTargetLabel') }}</span>
              <span :class="testResult.targetEmpty ? 'db-ok' : 'db-bad'">
                {{ testResult.targetEmpty ? $t('database.form.resultTargetEmpty') : $t('database.form.resultTargetNotEmpty') }}
              </span>
            </div>
            <div v-if="testResult.sslmode" class="db-status-row">
              <span class="db-label">{{ $t('database.status.sslmode') }}</span>
              <span class="db-muted">{{ $t('database.form.resultSslInfo', {mode: testResult.sslmode}) }}</span>
            </div>
          </template>
        </div>
      </el-form>
    </div>

    <!-- A/B 双入口卡：B=受管迁移说明 + start 入口（普通态仅指引）；A=env 交接（仅预览） -->
    <div class="db-card">
      <h3 class="db-card-title">{{ $t('database.entry.title') }}</h3>

      <div class="db-entry">
        <div class="db-entry-head">
          <span class="db-entry-badge db-entry-badge-b">B</span>
          <span class="db-entry-name">{{ $t('database.entry.nameB') }}</span>
        </div>
        <p class="db-description">
          {{ $t('database.entry.descB') }}
        </p>
        <div class="db-actions">
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="restartPending || attemptActive"
            @click="onStartMigration"
          >
            {{ $t('database.entry.startMigration') }}
          </el-button>
        </div>
        <p v-if="restartPending" class="db-entry-note">{{ $t('database.entry.startDisabledRestart') }}</p>
        <p v-if="attemptActive" class="db-entry-note">{{ $t('database.entry.startDisabledAttempt') }}</p>
      </div>

      <div class="db-entry">
        <div class="db-entry-head">
          <span class="db-entry-badge db-entry-badge-a">A</span>
          <span class="db-entry-name">{{ $t('database.entry.nameA') }}</span>
        </div>
        <p class="db-description">
          {{ $t('database.entry.descA') }}
        </p>
        <p v-for="note in guardNotes" :key="note" class="db-guard-note">{{ note }}</p>
        <div class="db-actions">
          <el-button
            size="small"
            :loading="handoffLoading"
            :disabled="migrationEntriesLocked"
            @click="previewHandoff"
          >
            {{ $t('database.entry.envHandoff') }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import {
  DatabaseControlSummary,
  EffectiveSummary,
  HostingCapabilityData,
  MigrationCasPayload,
  MigrationStatusData,
  PgFormInput,
  PgMasked,
  TestConnectionData,
  TestConnectionPayload,
  clearActivation,
  getDatabaseStatus,
  getMigrationStatus,
  testConnection
} from '@/api/database'
import { isCapabilityAvailable } from '@/api/platform-capabilities'
import { isDemoMode } from '@/demo/config'
import { isCompanionAppWebView } from '@/utils/ui-mode'
import { ApiError } from '@/types/api'

/** sslmode 全档（后端 pg_params_from_mapping 契约；技术字面量不翻译） */
type SslMode = 'disable' | 'allow' | 'prefer' | 'require' | 'verify-ca' | 'verify-full'

/** 需要校验 CA 证书路径（ssl_root_cert）的 verify 档位 */
const SSL_VERIFY_MODES: readonly SslMode[] = ['verify-ca', 'verify-full']

/** 视为「迁移进行中」的阶段（idle/cancelled/failed/committed 之外全部占住单飞行） */
const ACTIVE_PHASES: readonly string[] = [
  'preparing', 'draining', 'frozen', 'importing', 'verifying',
  'ready_to_switch', 'cancelling', 'held'
]

/** PG 目标表单草稿（组件内 camelCase；提交时映射为后端 snake_case PgFormInput） */
interface PgTargetDraft {
  host: string
  port: number
  user: string
  password: string
  database: string
  schema: string
  sslmode: SslMode
  sslRootCert: string
  poolSize: number
  maxOverflow: number
  poolTimeout: number
}

/**
 * 数据库设置面板（database-migration-ui W4-2）。
 *
 * - 状态卡展示「有效」库实况（§9：active 优先，env 仅在无受管配置时作为来源），
 *   摘要来自后端脱敏视图（无凭据字段，密码永不下发/不落任何持久层）；
 * - PG 目标表单仅迁移入口用：本页只经 testConnection 做只读探测（三态结果），
 *   不保存密码、不提交迁移；sslmode 全档下拉，verify-ca/full 时 CA 路径必填；
 * - A/B 双入口均保留：B 受管迁移说明（start 按钮仅入口暴露——disabled 当
 *   restartPending 或 attempt 进行中，普通态点击只提示去维护流程）；A env 交接
 *   仅调 clearActivation 生成计划预览（steps/confirmToken 确认弹窗展示，不执行）；
 * - 平台门控（W4-4）：矩阵 db_migration 非 supported、demo 模式、Android 伴侣
 *   WebView 三门独立只读化 PG 表单/测试连接/A 入口（提示叠加展示）；方法层
 *   同步拦截（直调 runTestConnection/previewHandoff 不发请求）；状态卡不受门控影响；
 * - 生命周期：mounted 拉状态；restartPending 时 10s 轮询，beforeDestroy 清理。
 *
 * 迁移/切换的实际执行面在维护页（维护 token 通道），本组件不接入维护客户端。
 */
@Component({ name: 'DatabasePanel' })
export default class extends Vue {
  private loading = false
  private loaded = false

  // 状态卡数据（getDatabaseStatus 下发）
  private effective: EffectiveSummary | null = null
  private control: DatabaseControlSummary | null = null
  private hosting: HostingCapabilityData = {
    hosting: 'unknown',
    optIn: false,
    pid1Self: false,
    autoRestartCapable: false,
    hintCode: null,
    hint: null
  }

  /** 托管提示：优先按 hintCode 本地化（P7 V01-F01），未识别码回退后端原文 */
  private get hostingHint(): string | null {
    if (this.hosting.hintCode) {
      return this.$t(`database.status.hostingHints.${this.hosting.hintCode}`) as string
    }
    return this.hosting.hint
  }

  // 迁移状态（仅用于 start 入口的 attempt 进行中判定；503/失败按未知处理）
  private migrationStatus: MigrationStatusData | null = null

  // PG 目标草稿（密码仅存组件内存）
  private pgForm: PgTargetDraft = {
    host: '',
    port: 5432,
    user: '',
    password: '',
    database: '',
    schema: 'public',
    sslmode: 'prefer',
    sslRootCert: '',
    poolSize: 10,
    maxOverflow: 20,
    poolTimeout: 30
  }

  private readonly sslmodeOptions: readonly SslMode[] = [
    'disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'
  ]
  private testing = false
  private testResult: TestConnectionData | null = null

  // A 入口：交接计划预览加载态
  private handoffLoading = false

  // restartPending 轮询（10s；beforeDestroy 清理）
  private pollTimer: number | null = null
  private readonly pollIntervalMs = 10000

  get pgMasked(): PgMasked | null {
    return this.effective?.postgresql ?? null
  }

  get restartPending(): boolean {
    return this.control?.restartPending ?? false
  }

  /** attempt 占住单飞行（start 入口禁用条件之一；状态未知时保守放行入口） */
  get attemptActive(): boolean {
    const status = this.migrationStatus
    if (!status || !status.attemptId) return false
    return ACTIVE_PHASES.indexOf(status.phase) >= 0
  }

  // ====== 平台门控（W4-4；§9 三层拒的页面层：PG 表单/测试连接/A 入口只读化） ======

  /** 平台矩阵未把 db_migration 标记为 supported（消费方式同 pathMappingAvailable；
   * 缓存为响应式，由路由守卫统一 loadPlatformCapabilities，本组件纯只读消费） */
  get platformBlocked(): boolean {
    return !isCapabilityAvailable('db_migration')
  }

  /** demo 模式不接真实目标：同样只读 + 样例数据提示 */
  get demoBlocked(): boolean {
    return isDemoMode()
  }

  /** Android 伴侣 WebView（UA 注入 BtDeckCompanion 标记）：本机不提供 PG 数据源，叠加禁用 */
  get androidLocalBlocked(): boolean {
    return isCompanionAppWebView()
  }

  get migrationEntriesLocked(): boolean {
    return this.platformBlocked || this.demoBlocked || this.androidLocalBlocked
  }

  /** 门控提示文案（三个门独立成键，命中时叠加展示；状态卡不受影响） */
  get guardNotes(): string[] {
    const notes: string[] = []
    if (this.platformBlocked) {
      notes.push(this.$t('database.platformGuard.unsupported').toString())
    }
    if (this.demoBlocked) {
      notes.push(this.$t('database.platformGuard.demo').toString())
    }
    if (this.androidLocalBlocked) {
      notes.push(this.$t('database.platformGuard.androidLocal').toString())
    }
    return notes
  }

  get sourceLabel(): string {
    return this.effective?.source === 'active'
      ? this.$t('database.status.sourceActive').toString()
      : this.$t('database.status.sourceEnv').toString()
  }

  get sourceTagType(): string {
    return this.effective?.source === 'active' ? 'success' : 'info'
  }

  /** 方言为产品名，原样展示（sqlite / postgresql） */
  get dialectLabel(): string {
    return this.effective?.dialect || '—'
  }

  get sqlitePathText(): string {
    return this.effective?.sqlitePath || ''
  }

  /** PG 脱敏摘要：host:port/database（无凭据；密码字段后端永不下发） */
  get pgTargetText(): string {
    const pg = this.pgMasked
    return pg ? `${pg.host}:${pg.port}/${pg.database}` : ''
  }

  get poolText(): string {
    const pg = this.pgMasked
    if (!pg) return ''
    return this.$t('database.status.poolInfo', {
      size: pg.poolSize,
      overflow: pg.maxOverflow,
      timeout: pg.poolTimeout
    }).toString()
  }

  get pgFormRef(): ElForm {
    return this.$refs.pgFormRef as ElForm
  }

  /** verify 档位：CA 路径（ssl_root_cert）必填 */
  get verifySslMode(): boolean {
    return SSL_VERIFY_MODES.indexOf(this.pgForm.sslmode) >= 0
  }

  /** 表单规则（computed：CA 路径必填随 sslmode 档位联动） */
  get pgRules(): Record<string, Array<Record<string, unknown>>> {
    const requiredBlur = (): Record<string, unknown> => ({
      required: true,
      message: this.$t('database.form.requiredField').toString(),
      trigger: 'blur'
    })
    return {
      host: [requiredBlur()],
      port: [{ ...requiredBlur(), trigger: 'change' }],
      user: [requiredBlur()],
      password: [requiredBlur()],
      database: [requiredBlur()],
      sslmode: [{ ...requiredBlur(), trigger: 'change' }],
      // verify 档位必填（is-required 标记与错误文案同源）；非 verify 档不要求
      sslRootCert: this.verifySslMode
        ? [{
            required: true,
            message: this.$t('database.form.sslRootCertRequired').toString(),
            trigger: 'blur'
          }]
        : []
    }
  }

  mounted(): void {
    this.load()
    this.loadMigrationStatus()
  }

  beforeDestroy(): void {
    this.clearPollTimer()
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getDatabaseStatus()
      this.effective = res.data.effective
      this.control = res.data.control
      this.hosting = res.data.hosting
      this.loaded = true
      this.syncPolling()
    } catch (error) {
      // 失败保持 !loaded 占位（重试按钮），不弹全局错误（请求层已节流提示）
      this.loaded = false
      console.error('加载数据库状态失败:', error)
    } finally {
      this.loading = false
    }
  }

  /** restartPending 轮询回调：失败保持旧态（不翻转为 false、轮询继续），不打扰用户 */
  private async refreshStatus(): Promise<void> {
    try {
      const res = await getDatabaseStatus()
      this.effective = res.data.effective
      this.control = res.data.control
      this.hosting = res.data.hosting
      this.loaded = true
      this.syncPolling()
    } catch (error) {
      console.error('轮询数据库状态失败:', error)
    }
  }

  /** 迁移状态仅服务 start 入口判定；管理器未接线（503）时按未知处理，不阻塞面板 */
  private async loadMigrationStatus(): Promise<void> {
    try {
      const res = await getMigrationStatus()
      this.migrationStatus = res.data
    } catch (error) {
      console.error('加载迁移状态失败:', error)
    }
  }

  private syncPolling(): void {
    if (this.restartPending) {
      if (this.pollTimer === null) {
        this.pollTimer = window.setInterval(() => {
          void this.refreshStatus()
        }, this.pollIntervalMs)
      }
    } else {
      this.clearPollTimer()
    }
  }

  private clearPollTimer(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer)
      this.pollTimer = null
    }
  }

  /** 草稿 → 后端 PgFormInput（snake_case 契约；缺省项由后端补全） */
  private buildPgInput(): PgFormInput {
    return {
      host: this.pgForm.host.trim(),
      port: this.pgForm.port,
      user: this.pgForm.user.trim(),
      password: this.pgForm.password,
      database: this.pgForm.database.trim(),
      schema: this.pgForm.schema.trim() || 'public',
      sslmode: this.pgForm.sslmode,
      ssl_root_cert: this.verifySslMode ? this.pgForm.sslRootCert.trim() : null,
      pool_size: this.pgForm.poolSize,
      max_overflow: this.pgForm.maxOverflow,
      pool_timeout: this.pgForm.poolTimeout
    }
  }

  private async runTestConnection(): Promise<void> {
    if (this.testing || this.migrationEntriesLocked) return
    let valid = false
    try {
      valid = await this.pgFormRef.validate()
    } catch {
      valid = false
    }
    if (!valid) return
    this.testing = true
    this.testResult = null
    try {
      const payload: TestConnectionPayload = {
        dialect: 'postgresql',
        postgresql: this.buildPgInput()
      }
      const res = await testConnection(payload)
      this.testResult = res.data
    } catch (error) {
      console.error('测试连接失败:', error)
      this.$message.error(this.$t('database.form.testFailed').toString())
    } finally {
      this.testing = false
    }
  }

  /** start 仅入口暴露：维护态才可 start，普通态提示去维护流程（不实际提交） */
  private onStartMigration(): void {
    this.$message.info(this.$t('database.entry.goMaintenanceHint').toString())
  }

  /**
   * A 入口：env 交接计划预览（§7.3）。
   * 预览载荷填当前控制锚点（后端 plan_handoff_same_db 只读生成计划、不校验 CAS
   * 值）；实际交接的 CAS/确认令牌消费在维护流程执行，本页不自动执行任何动作。
   */
  private async previewHandoff(): Promise<void> {
    if (this.handoffLoading || this.migrationEntriesLocked) return
    this.handoffLoading = true
    try {
      const payload: MigrationCasPayload = {
        attempt_id: this.effective?.receiptAttemptId || 'handoff-preview',
        epoch: this.control?.generation || 'preview',
        state_version: 1
      }
      const res = await clearActivation(payload)
      this.showHandoffPlan(res.data)
    } catch (error) {
      if (error instanceof ApiError && error.code === '409') {
        // 无受管 active / env 指向异库：后端 409，提示改走迁移或离线恢复
        this.$message.warning(this.$t('database.msg.handoffConflict').toString())
      } else {
        console.error('生成 env 交接计划失败:', error)
        this.$message.error(this.$t('database.msg.handoffFailed').toString())
      }
    } finally {
      this.handoffLoading = false
    }
  }

  /** 计划预览确认弹窗：steps + confirmToken（仅展示；确认不触发任何执行） */
  private showHandoffPlan(plan: Record<string, unknown>): void {
    const kind = typeof plan.kind === 'string' ? plan.kind : ''
    const steps = Array.isArray(plan.steps) ? plan.steps.map(step => String(step)) : []
    const confirmToken = typeof plan.confirmToken === 'string' ? plan.confirmToken : ''

    const h = this.$createElement
    const message = h('div', { class: 'db-handoff-preview' }, [
      h('p', { class: 'db-handoff-kind' }, kind),
      h('p', { class: 'db-handoff-token' }, [
        `${this.$t('database.entry.handoffConfirmToken')}：${confirmToken}`,
        h('span', { class: 'db-handoff-token-note' }, this.$t('database.entry.handoffConfirmTokenNote').toString())
      ]),
      h('p', { class: 'db-handoff-steps-title' }, this.$t('database.entry.handoffSteps').toString()),
      h('ol', { class: 'db-handoff-steps' }, steps.map(step => h('li', { class: 'db-handoff-step' }, step))),
      h('p', { class: 'db-handoff-note' }, this.$t('database.entry.handoffAckNote').toString())
    ])
    // 仅确认弹窗：确认后只回执「未执行」，交接动作永远不在此触发
    this.$msgbox({
      title: this.$t('database.entry.handoffTitle').toString(),
      message,
      confirmButtonText: this.$t('database.entry.handoffAck').toString(),
      showCancelButton: false,
      type: 'info',
      customClass: 'db-handoff-msgbox'
    })
      .then(() => {
        this.$message.info(this.$t('database.entry.handoffAckDone').toString())
      })
      .catch(() => undefined)
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/settings-panel';

// 多卡片列间距统一交由父层 .settings-content 的 gap 控制
.database-panel {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

// 卡片壳/标题/描述：统一继承系统设置页签规范（960px 宽 + 渐变竖条标题 + 14px 描述）
.db-card {
  @extend %settings-card;
}

.db-card-title {
  @extend %settings-card-title;
}

.db-description {
  @extend %settings-card-description;
}

.db-hint {
  color: var(--color-text-secondary, #909399);
  padding: 12px 0;
}

// 状态卡行：标签 + 值（码值等宽字体）
.db-status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 0;
  flex-wrap: wrap;
}

.db-label {
  font-size: 13px;
  font-weight: 600;
  min-width: 160px;
}

.db-value {
  font-size: 13px;
  color: var(--color-text-primary);
  word-break: break-all;
}

.db-mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.db-muted {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
}

.db-ok {
  color: var(--color-success, #67c23a);
}

.db-bad {
  color: var(--color-danger, #f56c6c);
}

.db-hosting-hint {
  margin-bottom: 0;
}

// 平台门控提示（W4-4）：warning 色文案，随禁用面一同出现
.db-guard-note {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-warning-dark);
  margin: 0 0 8px;
}

// PG 目标表单：双列栅格，窄屏单列（数值输入固定宽防拉伸）
.db-form {
  margin-top: var(--spacing-sm);
}

.db-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: var(--spacing-lg);
}

.db-select,
.db-number {
  width: 100%;
}

.db-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: var(--spacing-sm);
}

.db-test-result {
  border: 1px solid var(--color-border-primary, #ebeef5);
  border-radius: 6px;
  padding: 8px 12px;
  margin-top: var(--spacing-md);
}

// A/B 入口块
.db-entry {
  padding: var(--spacing-sm) 0;

  & + .db-entry {
    border-top: 1px solid var(--color-border-primary, #ebeef5);
    margin-top: var(--spacing-sm);
    padding-top: var(--spacing-md);
  }
}

.db-entry-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.db-entry-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.db-entry-badge-b {
  background: var(--color-primary);
}

.db-entry-badge-a {
  background: var(--color-text-secondary, #909399);
}

.db-entry-name {
  font-size: 14px;
  font-weight: 600;
}

.db-entry-note {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin: var(--spacing-xs) 0 0;
  line-height: 1.5;
}

// 响应式：窄屏（≤768px，含移动端整页复用）单列表单
@media (max-width: 768px) {
  .db-form-grid {
    grid-template-columns: 1fr;
  }

  .db-label {
    min-width: 120px;
  }
}
</style>

<style lang="scss">
// 交接计划预览弹窗：MessageBox 渲染在 body 下（组件外），scoped 样式不可达，
// 经 customClass=db-handoff-msgbox 以全局块定制（同仓 MessageBox 定制先例）
.db-handoff-msgbox .db-handoff-preview {
  text-align: left;
  max-height: 50vh;
  overflow-y: auto;
}

.db-handoff-msgbox .db-handoff-kind,
.db-handoff-msgbox .db-handoff-steps-title {
  font-weight: 600;
  margin: 0 0 6px;
}

.db-handoff-msgbox .db-handoff-token {
  margin: 0 0 8px;
  word-break: break-all;
}

.db-handoff-msgbox .db-handoff-token-note {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin-top: 2px;
}

.db-handoff-msgbox .db-handoff-steps {
  margin: 0 0 8px;
  padding-left: 18px;
}

.db-handoff-msgbox .db-handoff-step {
  font-size: 13px;
  line-height: 1.7;
}

.db-handoff-msgbox .db-handoff-note {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  margin: 0;
}
</style>
