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
 * Database settings domain (database-migration-ui W4-2; "Database" tab in settings).
 * Effective summaries / hosting hints / handoff plan steps are server-passthrough
 * copy (E03 semantics, same as the MCP catalog) and are not maintained here;
 * sslmode levels are technical literals and stay untranslated.
 */
export const database = {
  panel: {
    description: 'Shows the currently effective database configuration (application reality wins; environment variables act as the source only when no managed config exists). The SQLite → PostgreSQL migration can be started and committed right on this page in one stop.',
    loading: 'Loading...',
    loadFailed: 'Failed to load database status.',
    retry: 'Retry'
  },
  status: {
    title: 'Effective Database',
    source: 'Config source',
    sourceActive: 'Managed (app-managed)',
    sourceEnv: 'Environment variables',
    dialect: 'Dialect',
    sqlitePath: 'SQLite path',
    pgTarget: 'PostgreSQL target',
    sslmode: 'TLS mode (sslmode)',
    pool: 'Connection pool',
    poolInfo: 'pool {size} · overflow {overflow} · timeout {timeout}s',
    generation: 'Managed control generation',
    restartPending: 'Commit effect',
    restartPendingYes: 'Restart pending',
    restartPendingNo: 'Effective',
    hosting: 'Hosting',
    autoRestart: 'Auto restart capable',
    noAutoRestart: 'Manual restart required',
    hostingHints: {
      MANAGED_RESTART_MANUAL: 'Unknown hosting or managed restart not opted in (BTD_MIGRATION_MANAGED_RESTART=1): restart manually after the switch is committed'
    }
  },
  form: {
    title: 'PostgreSQL Migration Target',
    description: 'Target database parameters for starting a migration (auto-filled from the deployment environment when available); use "test connection" to probe the target before starting. The password lives in component memory only and is never saved.',
    host: 'Host',
    port: 'Port',
    user: 'User',
    password: 'Password',
    passwordEnvHint: 'Password loaded from the deployment environment (DB_PASSWORD); the eye icon only reveals the mask placeholder — the real password never leaves the server. Type to override.',
    passwordRestoreEnv: 'Restore environment password',
    database: 'Database',
    schema: 'Schema',
    schemaPlaceholder: 'Defaults to public',
    sslmode: 'TLS mode (sslmode)',
    sslRootCert: 'CA certificate path',
    sslRootCertPlaceholder: 'Required for verify-ca / verify-full',
    sslRootCertRequired: 'A CA certificate path is required for verify-ca / verify-full',
    poolSize: 'Pool size',
    maxOverflow: 'Max overflow',
    poolTimeout: 'Acquire timeout (s)',
    testConnection: 'Test connection',
    testFailed: 'Failed to test the connection. Please try again later.',
    requiredField: 'Required field',
    resultReachableLabel: 'Reachability',
    resultReachableOk: 'Reachable',
    resultReachableBad: 'Unreachable',
    resultVersionLabel: 'Version requirement (PG ≥ 16)',
    resultVersionOk: 'Satisfied',
    resultVersionBad: 'Not satisfied',
    resultVersionInfo: 'Server version: {version}',
    resultSslInfo: 'Negotiated TLS: {mode}',
    resultTargetLabel: 'Target database',
    resultTargetEmpty: 'Empty (migratable)',
    resultTargetNotEmpty: 'Not empty (migration requires an empty target)'
  },
  entry: {
    title: 'Database Switch Entries (A / B)',
    nameB: 'B · App-managed configuration',
    descB: 'Start the migration right here in one stop: tasks pause automatically and the maintenance window opens after confirmation; complete the maintenance authentication to track progress and commit the switch on this page (the commit is persistent and irreversible). This is the recommended way.',
    nameA: 'A · env handoff',
    descA: 'Hand the current managed configuration back to host environment variables (same database only). The button below only generates a plan preview and never executes anything.',
    startMigration: 'Start migration',
    startDisabledRestart: 'A committed switch is waiting for restart; a new migration cannot start until the restart completes',
    startDisabledAttempt: 'A migration is already in progress',
    startConfirmTitle: 'Start migration?',
    startConfirmText: 'All tasks will be paused automatically and business APIs frozen (normal pages return 503 until the migration completes or is cancelled); do not refresh the page during the import. Start the SQLite → PostgreSQL migration?',
    startLaunched: 'Migration started and tasks paused. Complete the maintenance authentication below to continue tracking.',
    startFailed: 'Failed to start the migration.',
    startWrongDialect: 'The current database is already PostgreSQL; migrating back to SQLite requires the reverse migration (API/upcoming release).',
    startNoSourcePath: 'Cannot determine the current SQLite database path; migration start is blocked.',
    followTitle: 'Migration tracking',
    followAuthHint: 'The migration window is open. Complete the maintenance authentication (independent of your login session; in-memory token, 15 minutes) to track progress and perform the commit.',
    followCancel: 'Cancel migration',
    followCancelConfirmTitle: 'Cancel this migration?',
    followCancelConfirmText: 'The import will be cooperatively stopped and the source unfrozen; the state stays "cancelling" until the worker acknowledges.',
    followCancelFailed: 'Failed to cancel the migration.',
    followLeave: 'Abandon migration',
    followLeaving: 'Abandoning…',
    followLeaveConfirmTitle: 'Abandon this migration?',
    followLeaveConfirmText: 'Abandon this migration and fall back to the source (only when safely stopped and not committed; irreversible, the epoch advances).',
    followLeaveFailed: 'Failed to abandon the migration.',
    followAutoRefresh: 'Tracking status refreshes every 10 seconds.',
    followDoneFallback: 'The migration window is closed.',
    envHandoff: 'env handoff (preview only)',
    handoffTitle: 'env Handoff Plan Preview (not executed)',
    handoffSteps: 'Handoff steps',
    handoffConfirmToken: 'Confirm token',
    handoffConfirmTokenNote: 'The confirmToken is used only when the handoff is actually executed in the maintenance flow',
    handoffAck: 'Got it: preview only',
    handoffAckNote: 'The preview executes nothing; the actual handoff requires a second confirmation with the confirm token in the maintenance flow.',
    handoffAckDone: 'Preview only; nothing was handed off'
  },
  msg: {
    handoffFailed: 'Failed to generate the handoff plan. Please try again later.',
    handoffConflict: 'The current state does not allow a same-database handoff (no managed config, or env points to a different database). Use a new migration or offline recovery instead.'
  },
  /**
   * Platform gating notices (database-migration-ui W4-4; the page layer of
   * the three-layer rejection). Matrix / demo / Android WebView are separate
   * keys and stack when hit together.
   */
  platformGuard: {
    unsupported: 'The current platform does not support database migration: the target form and switch entries are disabled; status stays viewable.',
    demo: 'Demo mode shows sample data without a real database: the migration target and switch entries are unavailable.',
    androidLocal: 'PostgreSQL data sources are not supported on the Android device itself'
  },
  /**
   * Read-only mobile maintenance entry (database-migration-ui W4-4; /m/maintenance).
   * Auth/state/restart copy reuses the maintenance.* sub-domain; only
   * mobile-specific guidance lives here.
   */
  mobile: {
    title: 'Maintenance',
    description: 'Read-only mobile entry under maintenance mode: view the maintenance status and restart hints after authenticating. Credential re-entry and migration actions are not performed here.',
    guidanceTitle: 'Read-only guidance',
    readOnlyHint: 'Mobile is view-only. Complete credential re-entry, migration start and commit on the desktop maintenance page (/maintenance).'
  },
  /**
   * Maintenance recovery page (database-migration-ui W4-3): the standalone
   * page under the maintenance barrier (/maintenance). Maintenance token is
   * memory-only, coarse state badges, NEEDS_CREDENTIALS re-entry, read-only
   * READY_TO_SWITCH waiting, and the restartPending manual-restart hint.
   */
  maintenance: {
    title: 'Maintenance Mode',
    description: 'Business APIs are under maintenance. This page provides an independent maintenance session, migration status and credential re-entry. The maintenance token lives only in page memory and is lost on refresh.',
    auth: {
      title: 'Maintenance Authentication',
      hint: 'The maintenance session is fully independent from normal login: authentication only unlocks maintenance APIs on this page, touches no other session and is never written to browser storage.',
      username: 'Username',
      password: 'Password',
      twofa: '2FA code (optional)',
      submit: 'Authenticate',
      submitting: 'Authenticating...',
      failed: 'Maintenance authentication failed. Check the account and password, then try again.',
      sessionExpired: 'The maintenance session has expired. Please authenticate again.',
      notMaintenance: 'No migration is currently running; start one from "Settings → Database" first.'
    },
    state: {
      title: 'Maintenance Status',
      unknown: 'Unknown state ({code})',
      preparing: 'Preparing',
      draining: 'Draining',
      frozen: 'Frozen',
      importing: 'Importing',
      verifying: 'Verifying',
      readyToSwitch: 'Ready to switch',
      needsCredentials: 'Awaiting credentials',
      committedPendingRestart: 'Committed, restart pending',
      attemptId: 'Attempt ID',
      epoch: 'Epoch',
      autoRefresh: 'Auto refresh every 10s'
    },
    migration: {
      title: 'Migration Progress',
      noAttempt: 'No migration is currently in progress.',
      phase: 'Phase',
      phaseUnknown: 'Unknown phase ({phase})',
      phaseIdle: 'Idle',
      phasePreparing: 'Preparing',
      phaseDraining: 'Draining',
      phaseFrozen: 'Frozen',
      phaseImporting: 'Importing',
      phaseVerifying: 'Verifying',
      phaseReadyToSwitch: 'Ready to switch',
      phaseNeedsCredentials: 'Awaiting credentials',
      phaseCancelling: 'Cancelling',
      phaseCancelled: 'Cancelled',
      phaseFailed: 'Failed',
      phaseHeld: 'Held',
      phaseCommitted: 'Committed',
      progress: 'Progress',
      progressCount: '{done} / {total}',
      readiness: 'Target readiness',
      ready: 'Ready',
      notReady: 'Not ready',
      readyToSwitchTitle: 'Waiting to commit / waiting for restart',
      readyToSwitchHint: 'The target database is ready. You can submit the switch below (the commit is persistent and irreversible); the service will then restart per the managed/manual restart policy.',
      needsCredentialsTitle: 'Credential re-entry required',
      needsCredentialsHint: 'The maintenance flow cannot decrypt the stored target credentials after restart. Re-enter the originally bound target information to continue (temporarily switching targets is not supported).',
      targetHost: 'Target host',
      targetPort: 'Target port',
      targetUser: 'Target user',
      targetPassword: 'Target password',
      targetDatabase: 'Target database',
      targetSchema: 'Target schema',
      targetSchemaPlaceholder: 'Defaults to public',
      targetSslmode: 'TLS mode (sslmode)',
      targetSslRootCert: 'CA certificate path',
      targetSslRootCertPlaceholder: 'Required for verify-ca / verify-full',
      targetSslRootCertRequired: 'A CA certificate path is required for verify-ca / verify-full',
      requiredField: 'Required field',
      submitCredentials: 'Submit credentials',
      submittingCredentials: 'Submitting...',
      credentialsFailed: 'Failed to submit credentials. Please try again later.',
      credentialsSubmitted: 'Credentials accepted. Status will update on the next poll.',
      switchSubmit: 'Submit switch',
      switchSubmitting: 'Submitting…',
      switchConfirmTitle: 'Confirm switch commit?',
      switchConfirmText: 'The commit is persistent and irreversible: the managed config will be published and the service enters the pending-restart state, then restarts to complete activation. Commit with the current attempt?',
      switchSubmitted: 'Switch committed. The service is now pending restart.',
      switchFailed: 'Failed to submit the switch. Please try again later.'
    },
    restart: {
      title: 'Restart Pending',
      message: 'The configuration has been committed. A manual service restart is required for it to take effect.'
    },
    actions: {
      backHome: 'Back to home',
      exitSession: 'Exit maintenance session'
    }
  }
}
