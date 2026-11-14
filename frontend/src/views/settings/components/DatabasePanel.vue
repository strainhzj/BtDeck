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
            <el-input
              v-model="pgForm.password"
              type="password"
              show-password
              @focus="onPasswordFocus"
              @input="onPasswordInput"
            />
            <!-- A2 环境密码：掩码哨兵占位（眼睛可见的仅是占位符本体，真实密码不出服务端）；
                 手动输入即覆盖，可一键还原 -->
            <div v-if="envPasswordAvailable" class="db-password-env">
              <span v-if="envPasswordMode" class="db-muted">{{ $t('database.form.passwordEnvHint') }}</span>
              <el-button
                v-else
                type="text"
                size="mini"
                class="db-password-restore"
                @click="restoreEnvPassword"
              >
                {{ $t('database.form.passwordRestoreEnv') }}
              </el-button>
            </div>
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

    <!-- A/B 双入口卡（移动壳整卡隐藏：迁移动作面仅桌面提供）：B=一站式发起；A=env 交接（仅预览） -->
    <div v-if="!isMobileShell" class="db-card">
      <h3 class="db-card-title">{{ $t('database.entry.title') }}</h3>

      <div v-if="!isMobileShell" class="db-entry">
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
            :loading="startSubmitting"
            :disabled="restartPending || attemptActive || followMode"
            @click="onStartMigration"
          >
            {{ $t('database.entry.startMigration') }}
          </el-button>
        </div>
        <p v-if="startError" class="db-entry-note">{{ startError }}</p>
        <p v-if="restartPending" class="db-entry-note">{{ $t('database.entry.startDisabledRestart') }}</p>
        <p v-if="attemptActive && !followMode" class="db-entry-note">{{ $t('database.entry.startDisabledAttempt') }}</p>
      </div>

      <div v-if="!isMobileShell" class="db-entry">
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

    <!-- 一站式迁移跟踪卡（2026-11-08）：start 后内嵌维护认证 + 进度 + 提交；移动壳隐藏 -->
    <div v-if="followMode && !isMobileShell" class="db-card">
      <h3 class="db-card-title">{{ $t('database.entry.followTitle') }}</h3>

      <!-- 免认证只读进度（2026-11-14）：发起推进 epoch 即作废旧 token，进度查看
           不再依赖重输凭据——进度条始终自动刷新，操作类动作才需要认证 -->
      <template v-if="followDisplay">
        <div class="db-status-row">
          <span class="db-label">{{ $t('database.maintenance.migration.phase') }}</span>
          <el-tag size="small" :type="followPhaseTagType">{{ followPhaseLabel }}</el-tag>
        </div>
        <div v-if="followProgress" class="db-hint">
          <el-progress :percentage="followProgressPercent" :stroke-width="10" />
          <span>{{ followProgressText }}</span>
        </div>
      </template>

      <!-- 维护认证：窗口开启后才能签发（独立于登录会话，令牌仅内存 15min）；进度无需认证 -->
      <div v-if="!maintenanceAuthenticated" class="db-entry">
        <p class="db-description">{{ $t('database.entry.followReadonlyHint') }}</p>
        <el-form :model="authForm" label-position="top" @submit.native.prevent>
          <el-form-item :label="$t('database.maintenance.auth.username')">
            <el-input v-model="authForm.username" />
          </el-form-item>
          <el-form-item :label="$t('database.maintenance.auth.password')">
            <el-input v-model="authForm.password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="$t('database.maintenance.auth.twofa')">
            <el-input v-model="authForm.twofa" />
          </el-form-item>
          <div class="db-actions">
            <el-button
              type="primary"
              size="small"
              :loading="maintenanceSubmitting"
              @click="loginMaintenance"
            >
              {{ maintenanceSubmitting
                ? $t('database.maintenance.auth.submitting')
                : $t('database.maintenance.auth.submit') }}
            </el-button>
          </div>
          <p v-if="maintenanceAuthError" class="db-entry-note">{{ maintenanceAuthError }}</p>
        </el-form>
      </div>

      <template v-else>
        <div class="db-status-row">
          <span class="db-label">{{ $t('database.maintenance.migration.phase') }}</span>
          <el-tag size="small" :type="followPhaseTagType">{{ followPhaseLabel }}</el-tag>
          <el-tag v-if="followReadiness" :type="followReadiness.readyToSwitch ? 'success' : 'info'" size="small">
            {{ followReadiness.readyToSwitch
              ? $t('database.maintenance.migration.ready')
              : $t('database.maintenance.migration.notReady') }}
          </el-tag>
        </div>
        <div v-if="followProgress" class="db-hint">
          <el-progress :percentage="followProgressPercent" :stroke-width="10" />
          <span>{{ followProgressText }}</span>
        </div>

        <p v-if="switchOk" class="db-ok">{{ $t('database.maintenance.migration.switchSubmitted') }}</p>

        <!-- 提交切换（READY；提交即持久不可撤销，后端就绪门 409 兑底）。
             协作取消不放此处：READY 后 worker 已收尾，取消永远等不到 ACK
             （后端 409 fail-fast）——留在 READY 会造成永久 cancelling 死锁 -->
        <div v-if="followReadyToSwitch" class="db-actions">
          <el-button
            type="danger"
            size="small"
            :loading="switchSubmitting"
            :disabled="followRestartPending"
            @click="commitFollowSwitch"
          >
            {{ switchSubmitting
              ? $t('database.maintenance.migration.switchSubmitting')
              : $t('database.maintenance.migration.switchSubmit') }}
          </el-button>
        </div>
        <p v-if="switchError" class="db-entry-note">{{ switchError }}</p>

        <!-- 协作取消（worker 活跃/即将启动阶段；READY 后不可取消） -->
        <div v-if="followCancellable && !followRestartPending" class="db-actions">
          <el-button size="small" plain :loading="cancelSubmitting" @click="requestFollowCancel">
            {{ $t('database.entry.followCancel') }}
          </el-button>
        </div>

        <!-- 已安全停止（取消/失败/挂起）：可放弃回源 -->
        <div v-if="followLeavable" class="db-actions">
          <el-button
            size="small"
            type="warning"
            plain
            :loading="leaveSubmitting"
            @click="requestFollowLeave"
          >
            {{ leaveSubmitting
              ? $t('database.entry.followLeaving')
              : $t('database.entry.followLeave') }}
          </el-button>
        </div>
        <p v-if="cancelError" class="db-entry-note">{{ cancelError }}</p>
        <p v-if="leaveError" class="db-entry-note">{{ leaveError }}</p>

        <!-- NEEDS_CREDENTIALS：复用上方 PG 表单（已回填）提交绑定凭据 -->
        <div v-if="followNeedsCredentials" class="db-actions">
          <el-button
            type="primary"
            size="small"
            :loading="credFollowSubmitting"
            @click="submitFollowCredentials"
          >
            {{ credFollowSubmitting
              ? $t('database.maintenance.migration.submittingCredentials')
              : $t('database.maintenance.migration.submitCredentials') }}
          </el-button>
        </div>
        <p v-if="credFollowError" class="db-entry-note">{{ credFollowError }}</p>

        <p v-if="followRestartPending" class="db-entry-note">{{ $t('database.maintenance.restart.message') }}</p>
        <p class="db-hint">{{ $t('database.entry.followAutoRefresh') }}</p>
      </template>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import {
  DatabaseControlSummary,
  DeploymentTargetData,
  EffectiveSummary,
  HostingCapabilityData,
  CredentialsPayload,
  MigrationCasPayload,
  MigrationStartPayload,
  MigrationStatusData,
  PgFormInput,
  PgMasked,
  ReadinessData,
  SwitchCommitData,
  SwitchPayload,
  TestConnectionData,
  TestConnectionPayload,
  clearActivation,
  getDatabaseStatus,
  getDeploymentTarget,
  getMigrationStatus,
  probeControlReady,
  startMigration,
  testConnection
} from '@/api/database'
import { isCapabilityAvailable } from '@/api/platform-capabilities'
import { isDemoMode } from '@/demo/config'
import { isCompanionAppWebView } from '@/utils/ui-mode'
import {
  clearMaintenanceToken,
  getMaintenanceProgress,
  MaintenanceProgressData,
  maintenanceLogin,
  maintenanceRequest,
  subscribeAuthExpired
} from '@/utils/maintenance-client'
import { ApiError } from '@/types/api'

/** sslmode 全档（后端 pg_params_from_mapping 契约；技术字面量不翻译） */
type SslMode = 'disable' | 'allow' | 'prefer' | 'require' | 'verify-ca' | 'verify-full'

/** 需要校验 CA 证书路径（ssl_root_cert）的 verify 档位 */
const SSL_VERIFY_MODES: readonly SslMode[] = ['verify-ca', 'verify-full']

/** 环境密码掩码哨兵（A2：仅作展示占位；提交时以 use_env_password 开关替代） */
const ENV_PASSWORD_SENTINEL = '********'

/** 视为「迁移进行中」的阶段（idle/cancelled/failed/committed 之外全部占住单飞行） */
const ACTIVE_PHASES: readonly string[] = [
  'preparing', 'draining', 'frozen', 'importing', 'verifying',
  'ready_to_switch', 'cancelling', 'held'
]

/** 跟踪卡 phase 徽标文案键（复用维护页 i18n 键，避免双份翻译漂移） */
const FOLLOW_PHASE_LABEL_KEYS: Readonly<Record<string, string>> = {
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

/** 跟踪卡 phase 徽标色（同维护页口径） */
const FOLLOW_PHASE_TAG_TYPES: Readonly<Record<string, string>> = {
  preparing: 'info',
  draining: 'info',
  frozen: 'warning',
  importing: '',
  verifying: '',
  ready_to_switch: 'success',
  needs_credentials: 'warning',
  cancelling: 'warning',
  cancelled: 'info',
  failed: 'danger',
  held: 'warning',
  committed: 'success'
}

/** 已安全停止、可放弃回源（leave）的 phase（COMMITTED 后绝不允许 leave） */
const FOLLOW_LEAVABLE_PHASES: readonly string[] = ['cancelled', 'failed', 'held']

/** 协作取消可用阶段（worker 活跃或即将启动；READY 后 worker 已收尾不可取消，
 * 后端 fail-fast 409——按钮留在 READY 会造成永久 cancelling 死锁） */
const FOLLOW_CANCELLABLE_PHASES: readonly string[] = [
  'preparing', 'draining', 'frozen', 'importing', 'verifying'
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

  // A2 部署环境目标回填：非敏感字段 + hasEnvPassword（密码本体不出服务端）
  private deploymentTarget: DeploymentTargetData | null = null
  /** 环境密码模式：true=提交走 use_env_password；手动输入即切回 */
  private envPasswordMode = false

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

  // ====== 一站式迁移流（2026-11-08）：start → 内嵌维护认证 → 跟踪 → 提交 ======
  // followMode=true 后普通通道 /database/* 调用全部停止（普通令牌在维护窗口内
  // 必 401，全局拦截器会刷新+跳登录）；一切迁移操作走 maintenanceRequest 通道。
  private followMode = false
  private maintenanceAuthenticated = false
  private maintenanceSubmitting = false
  private maintenanceAuthError: string | null = null
  private authForm = { username: '', password: '', twofa: '' }
  private followStatus: MigrationStatusData | null = null
  /** 免认证进度面：令牌失效/未认证时仍驱动只读进度显示（2026-11-14） */
  private followProgress: MaintenanceProgressData | null = null
  private followReadiness: ReadinessData | null = null
  private followTimer: number | null = null
  private followPollInFlight = false
  private unsubAuthExpired: (() => void) | null = null
  private startSubmitting = false
  private startError: string | null = null
  private switchSubmitting = false
  private switchOk = false
  private switchError: string | null = null
  private cancelSubmitting = false
  private cancelError: string | null = null
  private leaveSubmitting = false
  private leaveError: string | null = null
  private credFollowSubmitting = false
  private credFollowError: string | null = null

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

  /** 移动壳（/m/*）复用桌面设置页：迁移发起/认证/提交动作面仅桌面提供 */
  get isMobileShell(): boolean {
    const path = (this.$route && this.$route.path) || ''
    return path.indexOf('/m/') === 0
  }

  /** 只读显示源：认证态用完整 /migration/status；令牌失效/未认证回退免认证进度面
   * （2026-11-14：发起推进 epoch 即作废旧 token，进度查看不得依赖重输凭据） */
  get followDisplay(): MigrationStatusData | null {
    if (this.followStatus) return this.followStatus
    const p = this.followProgress
    if (!p || !p.phase) return null
    return {
      attemptId: p.attemptId ?? null,
      phase: p.phase,
      epoch: p.epoch ?? '',
      stateVersion: p.stateVersion ?? 0,
      commitPhase: p.commitPhase ?? null,
      workerGeneration: 0,
      needsCredentials: p.needsCredentials === true,
      restartPending: p.restartPending === true,
      detail: p.detail ? { progress: p.detail.progress, target: p.detail.target } : undefined
    }
  }

  get followNeedsCredentials(): boolean {
    const s = this.followDisplay
    if (!s) return false
    return s.needsCredentials === true || s.phase === 'needs_credentials'
  }

  get followReadyToSwitch(): boolean {
    return this.followDisplay?.phase === 'ready_to_switch'
  }

  get followRestartPending(): boolean {
    return this.followDisplay?.restartPending === true
  }

  get followLeavable(): boolean {
    const s = this.followDisplay
    if (!s) return false
    return FOLLOW_LEAVABLE_PHASES.indexOf(s.phase) >= 0
  }

  /** 协作取消仅在 worker 活跃/即将启动阶段可用（后端同口径 fail-fast） */
  get followCancellable(): boolean {
    const phase = this.followDisplay?.phase
    if (!phase) return false
    return FOLLOW_CANCELLABLE_PHASES.indexOf(phase) >= 0
  }

  get followPhaseLabel(): string {
    const s = this.followDisplay
    if (!s) return '—'
    const key = FOLLOW_PHASE_LABEL_KEYS[s.phase]
    if (!key) {
      return this.$t('database.maintenance.migration.phaseUnknown', { phase: s.phase }).toString()
    }
    return this.$t(key).toString()
  }

  get followPhaseTagType(): string {
    return FOLLOW_PHASE_TAG_TYPES[this.followDisplay?.phase || ''] ?? 'info'
  }

  get followProgress(): { done: number, total: number } | null {
    const p = this.followDisplay?.detail?.progress
    if (!p || typeof p.done !== 'number' || typeof p.total !== 'number') return null
    return { done: p.done, total: p.total }
  }

  get followProgressPercent(): number {
    const p = this.followProgress
    if (!p || p.total <= 0) return 0
    return Math.min(100, Math.round((p.done / p.total) * 100))
  }

  get followProgressText(): string {
    const p = this.followProgress
    if (!p) return ''
    return this.$t('database.maintenance.migration.progressCount', { done: p.done, total: p.total }).toString()
  }

  /** 跟踪通道 CAS 快照（/migration/status 为权威；epoch/state_version 后端当前不消费但保持契约完整） */
  get followAttemptPayload(): MigrationCasPayload | null {
    const s = this.followStatus
    if (!s || !s.attemptId) return null
    return { attempt_id: s.attemptId, epoch: s.epoch, state_version: s.stateVersion }
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

  /** 部署环境密码可用（available 且服务端有 DB_PASSWORD；门控锁定时表单整体禁用不回填交互） */
  get envPasswordAvailable(): boolean {
    const t = this.deploymentTarget
    return !!t && t.available === true && t.hasEnvPassword
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
      // 环境密码模式：服务端自取 DB_PASSWORD，密码框哨兵占位不校验
      password: this.envPasswordMode ? [] : [requiredBlur()],
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
    void this.loadDeploymentTarget()
    // 维护令牌过期（15min）统一分流：窗口仍在→重认证表单；窗口已关→回退普通通道
    this.unsubAuthExpired = subscribeAuthExpired(() => {
      if (!this.followMode) return
      this.maintenanceAuthenticated = false
      // 令牌失效不中断进度可见：立即降级免认证进度通道并保持轮询
      this.syncFollowPolling()
      void this.probeMaintenanceWindow().then(maintenance => {
        if (!maintenance) void this.fallbackToNormalMode()
      })
    })
  }

  beforeDestroy(): void {
    this.clearPollTimer()
    this.clearFollowTimer()
    if (this.unsubAuthExpired) {
      this.unsubAuthExpired()
      this.unsubAuthExpired = null
    }
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getDatabaseStatus({ skipAuthFallback: true })
      this.effective = res.data.effective
      this.control = res.data.control
      this.hosting = res.data.hosting
      this.loaded = true
      this.syncPolling()
    } catch (error) {
      // 401=可能处于迁移维护窗口：探测后进入一站式跟踪（skipAuthFallback 已阻断全局跳登录）
      if (await this.maybeEnterFollowMode(error)) return
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
      const res = await getDatabaseStatus({ skipAuthFallback: true })
      this.effective = res.data.effective
      this.control = res.data.control
      this.hosting = res.data.hosting
      this.loaded = true
      this.syncPolling()
    } catch (error) {
      if (await this.maybeEnterFollowMode(error)) return
      console.error('轮询数据库状态失败:', error)
    }
  }

  /** 迁移状态仅服务 start 入口判定；管理器未接线（503）时按未知处理，不阻塞面板 */
  private async loadMigrationStatus(): Promise<void> {
    try {
      const res = await getMigrationStatus({ skipAuthFallback: true })
      this.migrationStatus = res.data
    } catch (error) {
      if (await this.maybeEnterFollowMode(error)) return
      console.error('加载迁移状态失败:', error)
    }
  }

  /** 普通通道 401 = 可能处于迁移维护窗口（普通令牌被拒）：探测确认后进入一站式跟踪。
   * 返回 true=已进入 followMode（调用方不再按普通错误处理） */
  private async maybeEnterFollowMode(error: unknown): Promise<boolean> {
    if (!(error instanceof ApiError) || error.code !== '401') return false
    if (!(await this.probeMaintenanceWindow())) return false
    this.followMode = true
    this.maintenanceAuthenticated = false
    return true
  }

  /** 维护窗口探测（/health/control-ready 公开端点；maintenance=true 即窗口开启） */
  private async probeMaintenanceWindow(): Promise<boolean> {
    try {
      const res = await probeControlReady()
      return res.data?.maintenance === true
    } catch {
      return false
    }
  }

  /** A2 部署环境目标回填：失败静默退回手动填写（同维护页 fetchMigrationFaces 策略，
   * 也不新增基线外 lint 噪声）；表单仍可全量手输 */
  private async loadDeploymentTarget(): Promise<void> {
    try {
      const res = await getDeploymentTarget()
      this.deploymentTarget = res.data
      this.applyDeploymentTarget()
    } catch {
      // 静默：回填不可用（503/维护态/旧镜像）时退回手动填写，不打扰用户
    }
  }

  /** 非敏感字段入草稿（schema 保留默认 public）；有环境密码时进入掩码哨兵态 */
  private applyDeploymentTarget(): void {
    const target = this.deploymentTarget?.target
    if (!this.deploymentTarget?.available || !target) return
    this.pgForm.host = target.host
    this.pgForm.port = target.port
    this.pgForm.user = target.user
    this.pgForm.database = target.database
    const mode = target.sslmode as SslMode
    if (this.sslmodeOptions.indexOf(mode) >= 0) this.pgForm.sslmode = mode
    this.pgForm.sslRootCert = target.sslRootCert || ''
    this.pgForm.poolSize = target.poolSize
    this.pgForm.maxOverflow = target.maxOverflow
    this.pgForm.poolTimeout = target.poolTimeout
    if (this.deploymentTarget.hasEnvPassword) this.restoreEnvPassword()
  }

  /** 还原环境密码：掩码哨兵占位 + 提交走 use_env_password */
  private restoreEnvPassword(): void {
    this.envPasswordMode = true
    this.pgForm.password = ENV_PASSWORD_SENTINEL
  }

  /** 环境密码态聚焦即清空输入框（保持模式；未输入则提交仍走环境密码） */
  private onPasswordFocus(): void {
    if (this.envPasswordMode) this.pgForm.password = ''
  }

  /** 实际输入即切回手动密码模式（哨兵值不会混入真实密码） */
  private onPasswordInput(): void {
    if (this.envPasswordMode) this.envPasswordMode = false
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

  /** 草稿 → 后端 PgFormInput（snake_case 契约；缺省项由后端补全）。
   * 环境密码模式不外发哨兵值（密码留空 + 请求级 use_env_password 开关） */
  private buildPgInput(): PgFormInput {
    return {
      host: this.pgForm.host.trim(),
      port: this.pgForm.port,
      user: this.pgForm.user.trim(),
      password: this.envPasswordMode ? '' : this.pgForm.password,
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
      if (this.envPasswordMode) payload.use_env_password = true
      const res = await testConnection(payload)
      this.testResult = res.data
    } catch (error) {
      console.error('测试连接失败:', error)
      this.$message.error(this.$t('database.form.testFailed').toString())
    } finally {
      this.testing = false
    }
  }

  /** 一站式发起：确认后 POST start（普通通道），后端自动关准入→排空→冻结（暂停所有任务）；
   * 窗口打开后本面板停止普通通道调用，改走内嵌维护认证 + maintenanceRequest 通道 */
  private async onStartMigration(): Promise<void> {
    if (this.startSubmitting || this.migrationEntriesLocked) return
    if (this.followMode || this.attemptActive) return
    if ((this.effective?.dialect || '') !== 'sqlite') {
      this.$message.warning(this.$t('database.entry.startWrongDialect').toString())
      return
    }
    const sqlitePath = this.effective?.sqlitePath || ''
    if (!sqlitePath) {
      this.$message.warning(this.$t('database.entry.startNoSourcePath').toString())
      return
    }
    let valid = false
    try {
      valid = await this.pgFormRef.validate()
    } catch {
      valid = false
    }
    if (!valid) return
    try {
      await this.$confirm(
        this.$t('database.entry.startConfirmText').toString(),
        this.$t('database.entry.startConfirmTitle').toString(),
        { type: 'warning' }
      )
    } catch {
      return
    }
    this.startSubmitting = true
    this.startError = null
    // 先停普通通道轮询再发请求：窗口打开后普通令牌必 401（skipAuthFallback 兑底在途请求）
    this.clearPollTimer()
    this.followMode = true
    try {
      const payload: MigrationStartPayload = {
        direction: 'sqlite-to-pg',
        target: this.buildPgInput(),
        source: { dialect: 'sqlite', path: sqlitePath }
      }
      if (this.envPasswordMode) payload.use_env_password = true
      else payload.password = this.pgForm.password
      const res = await startMigration(payload)
      this.followStatus = res.data
      this.maintenanceAuthenticated = false
      this.$message.success(this.$t('database.entry.startLaunched').toString())
    } catch (error) {
      // 超时/网络错误后结果不确定（后端排空最长 30s）：探测窗口——已开=启动实际成功
      if (await this.probeMaintenanceWindow()) {
        this.$message.success(this.$t('database.entry.startLaunched').toString())
      } else {
        this.followMode = false
        this.startError = error instanceof ApiError && error.message
          ? error.message
          : this.$t('database.entry.startFailed').toString()
        void this.loadMigrationStatus()
        this.syncPolling()
      }
    } finally {
      this.startSubmitting = false
    }
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

  // ====== 一站式迁移跟踪（维护通道；窗口关闭自动回退普通通道） ======

  /** 内嵌维护认证：窗口开启后才能签发；409 NOT_MAINTENANCE=窗口已关，回退普通通道 */
  private async loginMaintenance(): Promise<void> {
    if (this.maintenanceSubmitting) return
    this.maintenanceSubmitting = true
    this.maintenanceAuthError = null
    try {
      await maintenanceLogin(
        this.authForm.username.trim(),
        this.authForm.password,
        this.authForm.twofa.trim() || undefined
      )
      this.authForm.password = ''
      this.authForm.twofa = ''
      this.maintenanceAuthenticated = true
      void this.refreshFollowState()
      this.syncFollowPolling()
    } catch (error) {
      // 后端固定文案（maintenance.py）：仅凭 message 匹配（契约常量）
      if (error instanceof ApiError && error.message === 'not in maintenance mode') {
        this.$message.info(this.$t('database.entry.followDoneFallback').toString())
        await this.fallbackToNormalMode()
      } else {
        this.maintenanceAuthError = error instanceof ApiError && error.message
          ? error.message
          : this.$t('database.maintenance.auth.failed').toString()
      }
    } finally {
      this.maintenanceSubmitting = false
    }
  }

  /** 维护窗口已关（重启激活完成/迁移取消）：清维护态、回普通通道并刷新实况 */
  private async fallbackToNormalMode(): Promise<void> {
    this.followMode = false
    this.maintenanceAuthenticated = false
    this.followStatus = null
    this.followProgress = null
    this.followReadiness = null
    clearMaintenanceToken()
    this.clearFollowTimer()
    await this.loadMigrationStatus()
    await this.load()
  }

  private syncFollowPolling(): void {
    // 只需 followMode：未认证/令牌失效时走免认证进度通道（进度自动可见），
    // 认证后自动升格为完整通道（就绪面/操作数据）
    if (this.followMode && this.followTimer === null) {
      this.followTimer = window.setInterval(() => {
        void this.refreshFollowState()
      }, this.pollIntervalMs)
    } else if (!this.followMode) {
      this.clearFollowTimer()
    }
  }

  private clearFollowTimer(): void {
    if (this.followTimer !== null) {
      clearInterval(this.followTimer)
      this.followTimer = null
    }
  }

  /** 跟踪轮询：单飞行（无重叠）；失败保持旧值；401 过期经 subscribeAuthExpired 分流。
   * 双通道（2026-11-14）：认证态走完整 /migration/status；未认证/令牌失效回退
   * 免认证 /maintenance/progress（进度自动可见），窗口关闭（409）回退普通通道。 */
  private async refreshFollowState(): Promise<void> {
    if (!this.followMode || this.followPollInFlight) return
    this.followPollInFlight = true
    try {
      if (this.maintenanceAuthenticated) {
        this.followStatus = await maintenanceRequest<MigrationStatusData>('get', '/database/migration/status')
        this.followReadiness = await maintenanceRequest<ReadinessData>('get', '/database/target-readiness')
      } else {
        this.followProgress = await getMaintenanceProgress()
      }
      this.syncFollowPolling()
    } catch (error) {
      if (
        !this.maintenanceAuthenticated &&
        error instanceof ApiError &&
        error.message === 'not in maintenance mode'
      ) {
        // 免认证进度 409=窗口已关（放弃/完成/撤销）→ 回普通通道
        await this.fallbackToNormalMode()
      } else {
        console.error('跟踪迁移状态失败:', error)
      }
    } finally {
      this.followPollInFlight = false
    }
  }

  /** NEEDS_CREDENTIALS：复用上方 PG 表单（已回填）提交绑定凭据（不临时换目标） */
  private async submitFollowCredentials(): Promise<void> {
    if (this.credFollowSubmitting || !this.maintenanceAuthenticated) return
    const snapshot = this.followAttemptPayload
    if (!snapshot) {
      this.credFollowError = this.$t('database.maintenance.migration.noAttempt').toString()
      return
    }
    this.credFollowSubmitting = true
    this.credFollowError = null
    try {
      const payload: CredentialsPayload = {
        attempt_id: snapshot.attempt_id,
        target: this.buildPgInput()
      }
      if (this.envPasswordMode) payload.use_env_password = true
      else payload.password = this.pgForm.password
      this.followStatus = await maintenanceRequest<MigrationStatusData>(
        'post',
        '/database/migration/credentials',
        payload
      )
      this.$message.success(this.$t('database.maintenance.migration.credentialsSubmitted').toString())
    } catch (error) {
      this.credFollowError = error instanceof ApiError && error.message
        ? error.message
        : this.$t('database.maintenance.migration.credentialsFailed').toString()
    } finally {
      this.credFollowSubmitting = false
    }
  }

  /** 提交切换（READY；提交即持久不可撤销，后端就绪门 409 兑底；mode 固定 B） */
  private async commitFollowSwitch(): Promise<void> {
    if (this.switchSubmitting) return
    const snapshot = this.followAttemptPayload
    if (!snapshot) {
      this.switchError = this.$t('database.maintenance.migration.noAttempt').toString()
      return
    }
    this.switchSubmitting = true
    try {
      // 二次确认单独 await：取消（reject）直接返回，不落错误分支
      try {
        await this.$confirm(
          this.$t('database.maintenance.migration.switchConfirmText').toString(),
          this.$t('database.maintenance.migration.switchConfirmTitle').toString(),
          { type: 'warning' }
        )
      } catch {
        return
      }
      this.switchOk = false
      this.switchError = null
      const payload: SwitchPayload = { ...snapshot, mode: 'B' }
      await maintenanceRequest<SwitchCommitData>('post', '/database/migration/switch', payload)
      this.switchOk = true
      // 本地乐观置位：重启后刷新可能静默失败，按钮随 phase 变 committed 消失
      if (this.followStatus) this.followStatus.phase = 'committed'
      void this.refreshFollowState()
    } catch (error) {
      this.switchError = error instanceof ApiError && error.message
        ? error.message
        : this.$t('database.maintenance.migration.switchFailed').toString()
    } finally {
      this.switchSubmitting = false
    }
  }

  /** 协作取消（可逆；worker ACK 前状态为取消中，期间按钮随 phase 消失） */
  private async requestFollowCancel(): Promise<void> {
    if (this.cancelSubmitting) return
    const snapshot = this.followAttemptPayload
    if (!snapshot) return
    this.cancelSubmitting = true
    this.cancelError = null
    try {
      try {
        await this.$confirm(
          this.$t('database.entry.followCancelConfirmText').toString(),
          this.$t('database.entry.followCancelConfirmTitle').toString(),
          { type: 'warning' }
        )
      } catch {
        return
      }
      this.followStatus = await maintenanceRequest<MigrationStatusData>(
        'post',
        '/database/migration/cancel',
        snapshot
      )
    } catch (error) {
      this.cancelError = error instanceof ApiError && error.message
        ? error.message
        : this.$t('database.entry.followCancelFailed').toString()
    } finally {
      this.cancelSubmitting = false
    }
  }

  /** 放弃回源（仅已安全停止且未 COMMITTED；不可逆，epoch 推进） */
  private async requestFollowLeave(): Promise<void> {
    if (this.leaveSubmitting) return
    const snapshot = this.followAttemptPayload
    if (!snapshot) return
    this.leaveSubmitting = true
    this.leaveError = null
    try {
      try {
        await this.$confirm(
          this.$t('database.entry.followLeaveConfirmText').toString(),
          this.$t('database.entry.followLeaveConfirmTitle').toString(),
          { type: 'warning' }
        )
      } catch {
        return
      }
      this.followStatus = await maintenanceRequest<MigrationStatusData>(
        'post',
        '/database/migration/leave',
        snapshot
      )
      this.$message.success(this.$t('database.entry.followDoneFallback').toString())
      await this.fallbackToNormalMode()
    } catch (error) {
      this.leaveError = error instanceof ApiError && error.message
        ? error.message
        : this.$t('database.entry.followLeaveFailed').toString()
    } finally {
      this.leaveSubmitting = false
    }
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

// A2 环境密码：占位提示 / 还原操作行（settings-card 样式不穿透，本组件自带）
.db-password-env {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  line-height: 1.4;
}

.db-password-restore {
  padding: 0;
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
