package com.btdeck.companion.server

import org.json.JSONObject

/**
 * 本机服务端状态契约（纯 JVM，供单元测试锁定）。
 *
 * 状态真相源在 Python btdeck_server（start/stop/status 返回 JSON），
 * Kotlin 侧只做镜像；本类负责 JSON 解析与"状态 → 通知/界面文案"的确定性映射。
 *
 * JSON 契约（android/server-python/btdeck_server.py）：
 * status → {"ok", "state", "port", "version", "error", "errorPhase", "startedAtMs"}
 */
object ServerStates {

    const val STATE_STOPPED = "stopped"
    const val STATE_STARTING = "starting"
    const val STATE_RUNNING = "running"
    const val STATE_ERROR = "error"

    data class Snapshot(
        val state: String,
        val port: Int?,
        val version: String?,
        val error: String?,
        val errorPhase: String?,
        val startedAtMs: Long,
    ) {
        val isRunning: Boolean get() = state == STATE_RUNNING
        val isTerminal: Boolean get() = state == STATE_RUNNING || state == STATE_ERROR
    }

    /** status() JSON → Snapshot；坏 JSON 返回 null（调用方按未知处理，不伪造状态）。 */
    fun parseStatus(raw: String): Snapshot? = runCatching {
        val json = JSONObject(raw)
        Snapshot(
            state = json.optString("state", STATE_STOPPED),
            port = if (json.isNull("port")) null else json.optInt("port"),
            version = if (json.isNull("version")) null else json.optString("version").takeIf { it.isNotEmpty() },
            error = if (json.isNull("error")) null else json.optString("error").takeIf { it.isNotEmpty() },
            errorPhase = if (json.isNull("errorPhase")) null else json.optString("errorPhase").takeIf { it.isNotEmpty() },
            startedAtMs = json.optLong("startedAtMs", 0L),
        )
    }.getOrNull()

    fun stateLabel(state: String): String = when (state) {
        STATE_STOPPED -> "已停止"
        STATE_STARTING -> "启动中…"
        STATE_RUNNING -> "运行中"
        STATE_ERROR -> "启动失败"
        else -> "未知（$state）"
    }

    /** 常驻通知正文。lanEnabled 时附 LAN 提示（无加密，见威胁模型文案）。 */
    fun notificationText(snapshot: Snapshot, lanEnabled: Boolean): String {
        val base = when (snapshot.state) {
            STATE_STARTING -> "首次启动含数据库迁移，最长约 1-2 分钟"
            STATE_RUNNING -> {
                val version = snapshot.version?.let { "v$it · " } ?: ""
                "${version}本机 http://127.0.0.1:${snapshot.port ?: 0}"
            }
            STATE_ERROR -> snapshot.error ?: "未知错误"
            else -> stateLabel(snapshot.state)
        }
        return if (lanEnabled && snapshot.state != STATE_ERROR) "$base · 局域网已开放（明文）" else base
    }

    /** 启动失败的阶段中文名（errorPhase 归因，向导错误界面直接展示）。 */
    fun phaseLabel(phase: String?): String = when (phase) {
        "env" -> "目录准备"
        "migration" -> "数据库迁移"
        "import" -> "服务装配"
        "bind" -> "端口绑定"
        "health" -> "健康自检"
        else -> "启动"
    }
}
