/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * 数据库设置域（database-migration-ui W4-2；设置页「数据库」页签）。
 * 状态摘要/托管 hint/交接计划步骤为后端下发原文透传（E03 语义，同 MCP 目录），
 * 不在本包维护；sslmode 档位值为技术字面量，不翻译。
 */
export const database = {
  panel: {
    description: '展示当前实际生效的数据库配置（以应用实况为准；环境变量仅在无受管配置时作为来源）。数据库切换须经维护流程完成迁移与提交。',
    loading: '加载中…',
    loadFailed: '数据库状态加载失败。',
    retry: '重试'
  },
  status: {
    title: '当前生效数据库',
    source: '配置来源',
    sourceActive: '受管（应用管理）',
    sourceEnv: '环境变量',
    dialect: '数据库方言',
    sqlitePath: 'SQLite 路径',
    pgTarget: 'PostgreSQL 目标',
    sslmode: 'TLS 模式（sslmode）',
    pool: '连接池',
    poolInfo: '池 {size} · 溢出 {overflow} · 获取超时 {timeout} 秒',
    generation: '受管控制代次',
    restartPending: '提交生效状态',
    restartPendingYes: '待重启生效',
    restartPendingNo: '已生效',
    hosting: '托管环境',
    autoRestart: '支持托管重启',
    noAutoRestart: '需手动重启',
    hostingHints: {
      // zh 与后端 restart_adapter.hint 字面量逐字节一致（P7 V01-F01：后端
      // 自由文本改 hintCode 后由前端本地化；capable 时无 hint）
      MANAGED_RESTART_MANUAL: '未知托管或未显式 opt-in（BTD_MIGRATION_MANAGED_RESTART=1）：切换提交后需手动重启'
    }
  },
  form: {
    title: 'PostgreSQL 迁移目标',
    description: '供维护流程发起迁移时使用的目标库参数；本页仅提供只读探测（测试连接），不保存密码、不提交迁移。',
    host: '主机',
    port: '端口',
    user: '用户名',
    password: '密码',
    database: '数据库',
    schema: 'Schema',
    schemaPlaceholder: '默认 public',
    sslmode: 'TLS 模式（sslmode）',
    sslRootCert: 'CA 证书路径',
    sslRootCertPlaceholder: 'verify-ca / verify-full 时必填',
    sslRootCertRequired: 'verify-ca / verify-full 模式必须填写 CA 证书路径',
    poolSize: '池大小',
    maxOverflow: '最大溢出',
    poolTimeout: '获取超时（秒）',
    testConnection: '测试连接',
    testFailed: '测试连接失败，请稍后重试',
    requiredField: '必填项',
    resultReachableLabel: '连通性',
    resultReachableOk: '可连通',
    resultReachableBad: '不可连通',
    resultVersionLabel: '版本要求（PG ≥ 16）',
    resultVersionOk: '满足',
    resultVersionBad: '不满足',
    resultVersionInfo: '服务器版本：{version}',
    resultSslInfo: '协商 TLS：{mode}',
    resultTargetLabel: '目标库状态',
    resultTargetEmpty: '空库（可迁移）',
    resultTargetNotEmpty: '非空库（迁移要求空库）'
  },
  entry: {
    title: '数据库切换入口（A / B）',
    nameB: 'B · 配置由应用管理',
    descB: '经维护流程发起迁移并提交切换：应用发布受管配置，托管环境支持时自动重启。这是推荐的切换方式。',
    nameA: 'A · env 交接',
    descA: '把当前受管配置交还给宿主环境变量管理（仅限同一数据库）。下方按钮只生成交接计划预览，不会执行任何变更。',
    startMigration: '发起迁移（入口指引）',
    startDisabledRestart: '存在待重启生效的提交，重启完成前不可发起新迁移',
    startDisabledAttempt: '已有迁移在进行中',
    goMaintenanceHint: '迁移在维护模式下发起与提交，普通设置页不直接提交；请按维护流程进入维护页操作。',
    envHandoff: 'env 交接（仅预览）',
    handoffTitle: 'env 交接计划预览（不执行）',
    handoffSteps: '交接步骤',
    handoffConfirmToken: '确认令牌',
    handoffConfirmTokenNote: 'confirmToken 仅在维护流程实际交接时使用',
    handoffAck: '我已知晓：本次仅为预览',
    handoffAckNote: '预览未执行任何变更；实际交接需在维护流程中携带确认令牌二次确认。',
    handoffAckDone: '本次仅为预览，未执行交接'
  },
  msg: {
    handoffFailed: '生成交接计划失败，请稍后重试',
    handoffConflict: '当前状态不满足同库交接条件（无受管配置或 env 指向不同数据库），请改走迁移或离线恢复'
  },
  /**
   * 平台门控提示（database-migration-ui W4-4；§9 三层拒的页面层）。
   * 平台矩阵 / demo 模式 / Android WebView 三个门独立成键，命中时叠加展示。
   */
  platformGuard: {
    unsupported: '当前平台不支持数据库迁移：目标表单与切换入口已禁用，仅可查看状态。',
    demo: '演示模式展示样例数据，不连接真实数据库：迁移目标与切换入口不可用。',
    androidLocal: 'Android 本机不支持 PostgreSQL 数据源'
  },
  /**
   * 移动维护只读入口（database-migration-ui W4-4；/m/maintenance）。
   * 认证/状态/重启文案复用 maintenance.* 子域；此处仅维护移动专属指引。
   */
  mobile: {
    title: '维护',
    description: '维护模式的移动只读入口：认证后可查看维护状态与重启提示；不承载凭据补交或迁移操作。',
    guidanceTitle: '只读指引',
    readOnlyHint: '移动端仅提供只读查看。凭据重输、迁移发起与提交请在桌面端维护页（/maintenance）完成。'
  },
  /**
   * 维护恢复页（database-migration-ui W4-3）：维护屏障下的独立可达页
   * （/maintenance）。维护 token 仅内存、状态粗粒度徽标、NEEDS_CREDENTIALS
   * 凭据重输、READY_TO_SWITCH 只读等待、restartPending 手动重启提示。
   */
  maintenance: {
    title: '维护模式',
    description: '业务接口处于维护模式。本页提供独立的维护会话认证、迁移状态查看与凭据补交；维护令牌仅保存在页面内存中，刷新后需重新认证。',
    auth: {
      title: '维护认证',
      hint: '维护会话与普通登录相互独立：认证仅解锁本页的维护接口，不影响其它会话，也不写入浏览器存储。',
      username: '用户名',
      password: '密码',
      twofa: '两步验证码（可选）',
      submit: '认证',
      submitting: '认证中…',
      failed: '维护认证失败，请检查账户与密码后重试。',
      sessionExpired: '维护会话已过期，请重新认证。'
    },
    state: {
      title: '维护状态',
      unknown: '未知状态（{code}）',
      preparing: '准备中',
      draining: '排空中',
      frozen: '已冻结',
      importing: '导入中',
      verifying: '校验中',
      readyToSwitch: '可提交切换',
      needsCredentials: '等待补交凭据',
      committedPendingRestart: '已提交，待重启',
      attemptId: '迁移单号',
      epoch: '纪元（epoch）',
      autoRefresh: '每 10 秒自动刷新'
    },
    migration: {
      title: '迁移进度',
      noAttempt: '当前没有进行中的迁移。',
      phase: '阶段',
      phaseUnknown: '未知阶段（{phase}）',
      phaseIdle: '空闲',
      phasePreparing: '准备中',
      phaseDraining: '排空中',
      phaseFrozen: '已冻结',
      phaseImporting: '导入中',
      phaseVerifying: '校验中',
      phaseReadyToSwitch: '可提交切换',
      phaseNeedsCredentials: '等待补交凭据',
      phaseCancelling: '取消中',
      phaseCancelled: '已取消',
      phaseFailed: '已失败',
      phaseHeld: '已挂起',
      phaseCommitted: '已提交',
      progress: '进度',
      progressCount: '{done} / {total}',
      readiness: '目标就绪',
      ready: '就绪',
      notReady: '未就绪',
      readyToSwitchTitle: '等待提交 / 等待重启',
      readyToSwitchHint: '目标库已就绪。切换提交不在本页执行：请在设置面板或后续维护流程完成提交，并按提示重启服务。',
      needsCredentialsTitle: '需要重新输入凭据',
      needsCredentialsHint: '维护流程重启后无法解密已落盘的目标凭据，请重新输入原绑定目标库信息以继续（不支持临时更换目标）。',
      targetHost: '目标主机',
      targetPort: '目标端口',
      targetUser: '目标用户名',
      targetPassword: '目标密码',
      targetDatabase: '目标数据库',
      targetSchema: '目标 Schema',
      targetSchemaPlaceholder: '默认 public',
      targetSslmode: 'TLS 模式（sslmode）',
      targetSslRootCert: 'CA 证书路径',
      targetSslRootCertPlaceholder: 'verify-ca / verify-full 时必填',
      targetSslRootCertRequired: 'verify-ca / verify-full 模式必须填写 CA 证书路径',
      requiredField: '必填项',
      submitCredentials: '提交凭据',
      submittingCredentials: '提交中…',
      credentialsFailed: '提交凭据失败，请稍后重试。',
      credentialsSubmitted: '凭据已受理，状态将随轮询更新。'
    },
    restart: {
      title: '待重启生效',
      message: '配置已提交，需手动重启服务后生效。'
    },
    actions: {
      backHome: '返回主界面',
      exitSession: '退出维护会话'
    }
  }
}
