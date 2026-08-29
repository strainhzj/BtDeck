package com.btdeck.companion.server

import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * 本机服务端进程级状态镜像（UI 查询入口）。
 *
 * 真相源在 Python btdeck_server；ServerService 轮询后写入本单例并回调
 * 监听器（主线程）。Service 未运行时保持 stopped 快照——向导据此决定
 * "启动服务"还是"直接打开"。
 */
object LocalServerState {

    @Volatile
    var snapshot: ServerStates.Snapshot = stoppedSnapshot()
        private set

    @Volatile
    var lanEnabled: Boolean = false

    private val mainHandler = Handler(Looper.getMainLooper())
    private val listeners = mutableListOf<(ServerStates.Snapshot) -> Unit>()

    fun stoppedSnapshot(): ServerStates.Snapshot =
        ServerStates.Snapshot(ServerStates.STATE_STOPPED, null, null, null, null, 0L)

    fun addListener(listener: (ServerStates.Snapshot) -> Unit) {
        synchronized(listeners) { listeners.add(listener) }
        listener(snapshot) // 立即回放当前状态
    }

    fun removeListener(listener: (ServerStates.Snapshot) -> Unit) {
        synchronized(listeners) { listeners.remove(listener) }
    }

    fun update(next: ServerStates.Snapshot) {
        snapshot = next
        val toNotify = synchronized(listeners) { listeners.toList() }
        mainHandler.post { toNotify.forEach { it(next) } }
    }
}

/** [ServerPrefs] 的 SharedPreferences 实现（进程内，allowBackup=false 由 manifest 保证）。 */
class ServerPrefsImpl(context: Context) : ServerPrefs {
    private val sp = context.getSharedPreferences("btdeck_server", Context.MODE_PRIVATE)

    override var lastPort: Int
        get() = sp.getInt(KEY_LAST_PORT, 0)
        set(value) = sp.edit().putInt(KEY_LAST_PORT, value).apply()

    override var lanEnabled: Boolean
        get() = sp.getBoolean(KEY_LAN_ENABLED, false)
        set(value) = sp.edit().putBoolean(KEY_LAN_ENABLED, value).apply()

    companion object {
        private const val KEY_LAST_PORT = "last_port"
        private const val KEY_LAN_ENABLED = "lan_enabled"
    }
}
