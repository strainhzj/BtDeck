package com.btdeck.companion.server

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.btdeck.companion.R
import com.btdeck.companion.ui.WizardActivity
import com.chaquo.python.PyException
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * 本机服务端 Foreground Service（计划 Phase 3，specialUse 类型）。
 *
 * - 仅经用户操作启动（向导入口 startForegroundService）；
 * - 生命周期：onStartCommand 立即 startForeground（Android 12+ 5s 约束）→
 *   后台线程 Chaquopy callAttr 启动 Python btdeck_server → 每秒轮询 status
 *   镜像到 [LocalServerState] 并刷新常驻通知（状态 + 停止按钮）；
 * - 进程被杀：START_STICKY，系统重建时 intent=null → 按默认（记住的 LAN
 *   偏好）自动重启服务；
 * - LAN 开关：Intent extra 传入；绑定变化（loopback ↔ 0.0.0.0）时完整重启
 *   Python 服务端。默认 127.0.0.1，LAN 明文风险由向导威胁模型弹窗把关。
 */
class ServerService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var pollJob: Job? = null
    private lateinit var prefs: ServerPrefsImpl
    private var lanEnabled = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = ServerPrefsImpl(this)
        lanEnabled = prefs.lanEnabled
        LocalServerState.lanEnabled = lanEnabled
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                scope.launch { stopServer() }
                return START_NOT_STICKY
            }
            else -> {
                // START_STICKY 重建时 intent=null → 按记住的偏好自动重启
                val lan = intent?.getBooleanExtra(EXTRA_LAN, lanEnabled) ?: lanEnabled
                val current = LocalServerState.snapshot.state
                startInForeground()
                when {
                    current == ServerStates.STATE_RUNNING && lan != lanEnabled ->
                        scope.launch { restartWith(lan) } // 绑定变化：完整重启
                    current == ServerStates.STATE_RUNNING ->
                        updateNotification() // 已运行：幂等，仅刷新通知
                    else ->
                        scope.launch { startServer(lan) }
                }
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    // ============ 启动 / 停止 ============

    private suspend fun startServer(lan: Boolean) {
        lanEnabled = lan
        prefs.lanEnabled = lan
        LocalServerState.lanEnabled = lan
        LocalServerState.update(
            ServerStates.Snapshot(ServerStates.STATE_STARTING, null, null, null, null, 0L)
        )
        updateNotification()
        try {
            val dataRoot = withContext(Dispatchers.IO) {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(this@ServerService))
                }
                File(filesDir, DATA_DIR).absolutePath
            }
            callServer("start", dataRoot, if (lan) HOST_LAN else HOST_LOOPBACK, prefs.lastPort)
        } catch (e: PyException) {
            LocalServerState.update(
                ServerStates.Snapshot(ServerStates.STATE_ERROR, null, null, e.message, null, 0L)
            )
            updateNotification()
            return
        }
        pollStatus()
    }

    private suspend fun restartWith(lan: Boolean) {
        pollJob?.cancel()
        callServerQuietly("stop")
        LocalServerState.update(
            ServerStates.Snapshot(ServerStates.STATE_STARTING, null, null, null, null, 0L)
        )
        updateNotification()
        startServer(lan)
    }

    private suspend fun stopServer() {
        pollJob?.cancel()
        callServerQuietly("stop")
        LocalServerState.update(LocalServerState.stoppedSnapshot())
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /** 每秒轮询 Python status → 状态镜像 + 通知；running/error 停止轮询。 */
    private fun pollStatus() {
        pollJob?.cancel()
        pollJob = scope.launch {
            while (isActive) {
                val snapshot = runCatching {
                    ServerStates.parseStatus(callServer("status"))
                }.getOrNull()
                if (snapshot != null) {
                    LocalServerState.update(snapshot)
                    updateNotification()
                    if (snapshot.isTerminal) {
                        if (snapshot.isRunning && snapshot.port != null) {
                            prefs.lastPort = snapshot.port
                        }
                        return@launch
                    }
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    private suspend fun callServer(fn: String, vararg args: Any?): String =
        withContext(Dispatchers.IO) {
            Python.getInstance().getModule(MODULE).callAttr(fn, *args).toString()
        }

    private suspend fun callServerQuietly(fn: String) {
        runCatching { callServer(fn) }
            .onFailure { it.printStackTrace() } // logcat 归因；停止路径不让异常外溢
    }

    // ============ 通知 ============

    private fun startInForeground() {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID, notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun updateNotification() {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIFICATION_ID, buildNotification())
    }

    private fun buildNotification(): Notification {
        val stopIntent = PendingIntent.getService(
            this, REQ_STOP,
            Intent(this, ServerService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val contentIntent = PendingIntent.getActivity(
            this, REQ_OPEN,
            Intent(this, WizardActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
            .setContentTitle(getString(R.string.local_server_notification_title))
            .setContentText(ServerStates.notificationText(LocalServerState.snapshot, lanEnabled))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(contentIntent)
            .addAction(0, getString(R.string.local_server_stop), stopIntent)
            .build()
    }

    private fun createChannel() {
        // NotificationChannel 是 API 26+ 的类：低版本直接引用类会
        // ClassNotFoundException（API 24 实测崩溃）。26 以下 startForeground
        // 用无 channel 的普通通知，NotificationCompat 自动兼容。
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                getString(R.string.local_server_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.local_server_channel_desc)
            }
        )
    }

    companion object {
        const val ACTION_START = "com.btdeck.companion.server.START"
        const val ACTION_STOP = "com.btdeck.companion.server.STOP"
        const val EXTRA_LAN = "lan_enabled"

        const val MODULE = "btdeck_server"
        private const val CHANNEL_ID = "btdeck_server"
        private const val NOTIFICATION_ID = 1001
        private const val REQ_STOP = 1
        private const val REQ_OPEN = 2
        private const val DATA_DIR = "btdeck-server"
        private const val HOST_LOOPBACK = "127.0.0.1"
        private const val HOST_LAN = "0.0.0.0"
        private const val POLL_INTERVAL_MS = 1000L

        /** 当前设备是否支持本机服务端（Chaquopy Python 3.12 仅 64 位 ABI）。 */
        fun isAbiSupported(): Boolean =
            Build.SUPPORTED_ABIS.any { it == "arm64-v8a" || it == "x86_64" }
    }
}
