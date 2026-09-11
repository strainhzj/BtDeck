package com.btdeck.companion.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.CheckBox
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.btdeck.companion.BuildConfig
import com.btdeck.companion.R
import com.btdeck.companion.data.ServerProfileStore
import com.btdeck.companion.server.LocalServerProfile
import com.btdeck.companion.server.LocalServerState
import com.btdeck.companion.server.ServerService
import com.btdeck.companion.server.ServerStates
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * 首启向导（计划 Phase 2/3）：模式二选一，支持重新选择。
 * - 伴侣模式：连接已有服务器；
 * - 服务端模式：本机 Python 服务端（Phase 3 交付）——ABI 检测 → 通知权限 →
 *   确认对话框（LAN 开关默认关 + 威胁模型）→ ServerService 启动 → 状态监听 →
 *   就绪后写入本机 profile 并进 WebView；错误按阶段归因展示。
 */
class WizardActivity : AppCompatActivity() {

    private var stateListener: ((ServerStates.Snapshot) -> Unit)? = null
    private var pendingDialog: AlertDialog? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_wizard)

        // 构建标识：明文 LAN 需专用构建变体，误装严格版会遇到
        // ERR_CLEARTEXT_NOT_PERMITTED——在向导页直接可见当前构建能力
        findViewById<TextView>(R.id.wizard_subtitle).text =
            if (BuildConfig.LAN_CLEARTEXT_BUILD) {
                getString(R.string.wizard_subtitle) + "（LAN 明文构建）"
            } else {
                getString(R.string.wizard_subtitle) + "（严格 HTTPS/回环构建：局域网 http 需 LAN 明文构建版）"
            }

        findViewById<android.view.View>(R.id.card_companion).setOnClickListener {
            startActivity(Intent(this, ServerListActivity::class.java))
        }

        findViewById<android.view.View>(R.id.card_local).setOnClickListener { showLocalServerDialog() }
    }

    override fun onDestroy() {
        stateListener?.let { LocalServerState.removeListener(it) }
        super.onDestroy()
    }

    // ============ 本机服务端入口（Phase 3） ============

    private fun showLocalServerDialog() {
        if (!ServerService.isAbiSupported()) {
            MaterialAlertDialogBuilder(this)
                .setTitle(R.string.wizard_local_title)
                .setMessage(R.string.local_server_unsupported_abi)
                .setPositiveButton(android.R.string.ok, null)
                .show()
            return
        }
        maybeRequestNotificationPermission()
        val snapshot = LocalServerState.snapshot
        if (snapshot.isRunning) {
            showRunningDialog(snapshot)
        } else {
            showStartDialog()
        }
    }

    /** 首次/停止态：确认启动（LAN 默认关，勾选前展示威胁模型）。 */
    private fun showStartDialog() {
        val view = layoutInflater.inflate(R.layout.dialog_local_config, null)
        val lanSwitch = bindLanToggle(view)

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.wizard_local_title)
            .setView(view)
            .setPositiveButton(R.string.local_server_start) { _, _ ->
                startLocalServer(lanSwitch.isChecked)
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** 运行态：打开界面 / 切换 LAN（重启服务）/ 停止。 */
    private fun showRunningDialog(snapshot: ServerStates.Snapshot) {
        val view = layoutInflater.inflate(R.layout.dialog_local_config, null)
        view.findViewById<TextView>(R.id.text_status).apply {
            text = getString(
                R.string.local_server_running_status,
                ServerStates.stateLabel(snapshot.state),
                snapshot.version ?: "-",
                snapshot.port ?: 0,
            )
            visibility = View.VISIBLE
        }
        view.findViewById<TextView>(R.id.text_start_hint).visibility = View.GONE
        val lanSwitch = bindLanToggle(view)

        pendingDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.wizard_local_title)
            .setView(view)
            .setPositiveButton(R.string.local_server_open) { _, _ ->
                if (lanSwitch.isChecked != LocalServerState.lanEnabled) {
                    restartLocalServer(lanSwitch.isChecked) // 绑定变化：重启后再打开
                } else {
                    openLocalWebView()
                }
            }
            .setNeutralButton(R.string.local_server_stop) { _, _ ->
                stopService(Intent(this, ServerService::class.java).setAction(ServerService.ACTION_STOP))
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** LAN 开关联动威胁模型文案（dialog_local_config 布局内两控件）。
     *  初始勾选态从持久化偏好恢复（旧程序化版本同语义）。 */
    private fun bindLanToggle(view: View): CheckBox {
        val lanSwitch = view.findViewById<CheckBox>(R.id.check_lan)
        lanSwitch.isChecked = LocalServerState.lanEnabled
        val lanThreat = view.findViewById<TextView>(R.id.text_lan_threat)
        lanThreat.visibility = if (lanSwitch.isChecked) View.VISIBLE else View.GONE
        lanSwitch.setOnCheckedChangeListener { _, checked ->
            lanThreat.visibility = if (checked) View.VISIBLE else View.GONE
        }
        return lanSwitch
    }

    /** 启动服务并挂状态监听：就绪进 WebView，失败按阶段归因。 */
    private fun startLocalServer(lanEnabled: Boolean) {
        watchLocalState(requireTransition = false)
        ContextCompat.startForegroundService(
            this,
            Intent(this, ServerService::class.java)
                .setAction(ServerService.ACTION_START)
                .putExtra(ServerService.EXTRA_LAN, lanEnabled),
        )
        pendingDialog = buildProgressDialog(R.string.local_server_starting_progress)
    }

    /** LAN 绑定变化：先按新绑定重启（服务内部完整重启），随后走监听流程打开。 */
    private fun restartLocalServer(lanEnabled: Boolean) {
        // 立即回放会先看到旧的 RUNNING——要求先观察到状态离开 RUNNING（重启启动中）再武装
        watchLocalState(requireTransition = true)
        ContextCompat.startForegroundService(
            this,
            Intent(this, ServerService::class.java)
                .setAction(ServerService.ACTION_START)
                .putExtra(ServerService.EXTRA_LAN, lanEnabled),
        )
        pendingDialog = buildProgressDialog(R.string.local_server_restarting_progress)
    }

    /** 启动/重启进度对话框（不可取消，取消动作=停止服务）。 */
    private fun buildProgressDialog(messageRes: Int): AlertDialog {
        val view = layoutInflater.inflate(R.layout.dialog_progress, null)
        view.findViewById<TextView>(R.id.text_progress).text = getString(messageRes)
        return MaterialAlertDialogBuilder(this)
            .setTitle(R.string.wizard_local_title)
            .setView(view)
            .setNegativeButton(android.R.string.cancel) { _, _ ->
                stopService(Intent(this, ServerService::class.java).setAction(ServerService.ACTION_STOP))
            }
            .setCancelable(false)
            .show()
    }

    private fun watchLocalState(requireTransition: Boolean) {
        stateListener?.let { LocalServerState.removeListener(it) }
        var armed = !requireTransition
        val listener: (ServerStates.Snapshot) -> Unit = listener@{ snapshot ->
            if (!armed) {
                if (snapshot.state != ServerStates.STATE_RUNNING) armed = true
                return@listener // 等待重启真正开始（状态离开 RUNNING）后再处理
            }
            when (snapshot.state) {
                ServerStates.STATE_RUNNING -> {
                    pendingDialog?.dismiss()
                    pendingDialog = null
                    openLocalWebView()
                }
                ServerStates.STATE_ERROR -> {
                    pendingDialog?.dismiss()
                    pendingDialog = null
                    showErrorDialog(snapshot)
                }
                else -> Unit // starting 轮询中
            }
        }
        stateListener = listener
        LocalServerState.addListener(listener)
    }

    private fun openLocalWebView() {
        val snapshot = LocalServerState.snapshot
        val port = snapshot.port ?: return
        val store = ServerProfileStore(this)
        val existing = store.find(LocalServerProfile.PROFILE_ID)
        store.upsert(LocalServerProfile.buildProfile(port, existing))
        stateListener?.let { LocalServerState.removeListener(it) }
        stateListener = null
        startActivity(
            Intent(this, WebViewActivity::class.java)
                .putExtra(WebViewActivity.EXTRA_PROFILE_ID, LocalServerProfile.PROFILE_ID)
        )
    }

    private fun showErrorDialog(snapshot: ServerStates.Snapshot) {
        stateListener?.let { LocalServerState.removeListener(it) }
        stateListener = null
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.local_server_error_title)
            .setMessage(
                getString(R.string.local_server_error_body,
                    ServerStates.phaseLabel(snapshot.errorPhase), snapshot.error ?: "")
            )
            .setPositiveButton(R.string.retry) { _, _ -> showStartDialog() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Android 13+ 通知权限：拒绝不阻断（FGS 照常，仅通知不可见）。 */
    private fun maybeRequestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_POST_NOTIFICATIONS,
            )
        }
    }

    companion object {
        private const val REQ_POST_NOTIFICATIONS = 10
    }
}
