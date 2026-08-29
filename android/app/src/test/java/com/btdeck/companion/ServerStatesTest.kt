package com.btdeck.companion

import com.btdeck.companion.server.ServerStates
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 本机服务端状态契约锁定（Phase 3）：
 * - btdeck_server status() JSON 的解析形状（键名/空值语义）；
 * - 状态 → 通知文案映射（含 LAN 提示与错误归因）；
 * - 坏 JSON 不伪造状态。
 */
class ServerStatesTest {

    private fun runningJson(port: Int = 36603): String = JSONObject().apply {
        put("ok", true)
        put("state", "running")
        put("port", port)
        put("version", "1.0.6")
        put("error", JSONObject.NULL)
        put("errorPhase", JSONObject.NULL)
        put("startedAtMs", 1788014120058L)
    }.toString()

    @Test
    fun parseStatus_fullContract() {
        val snapshot = ServerStates.parseStatus(runningJson())
        assertNotNull(snapshot)
        assertEquals(ServerStates.STATE_RUNNING, snapshot!!.state)
        assertEquals(36603, snapshot.port)
        assertEquals("1.0.6", snapshot.version)
        assertNull(snapshot.error)
        assertNull(snapshot.errorPhase)
        assertEquals(1788014120058L, snapshot.startedAtMs)
        assertTrue(snapshot.isRunning)
        assertTrue(snapshot.isTerminal)
    }

    @Test
    fun parseStatus_errorCarriesPhase() {
        val raw = JSONObject().apply {
            put("ok", true)
            put("state", "error")
            put("port", JSONObject.NULL)
            put("version", JSONObject.NULL)
            put("error", "[migration] migrate_database() 返回 False")
            put("errorPhase", "migration")
            put("startedAtMs", 1L)
        }.toString()
        val snapshot = ServerStates.parseStatus(raw)!!
        assertEquals(ServerStates.STATE_ERROR, snapshot.state)
        assertEquals("migration", snapshot.errorPhase)
        assertTrue(snapshot.error!!.contains("migrate_database"))
        assertTrue(snapshot.isTerminal)
        assertFalse(snapshot.isRunning)
    }

    @Test
    fun parseStatus_startingWithPort() {
        // bind 后 starting 态即可见端口（提前握手/诊断契约）
        val raw = JSONObject().apply {
            put("ok", true); put("state", "starting"); put("port", 40001)
            put("version", JSONObject.NULL); put("error", JSONObject.NULL)
            put("errorPhase", JSONObject.NULL); put("startedAtMs", 5L)
        }.toString()
        val snapshot = ServerStates.parseStatus(raw)!!
        assertEquals(ServerStates.STATE_STARTING, snapshot.state)
        assertEquals(40001, snapshot.port)
        assertFalse(snapshot.isTerminal)
    }

    @Test
    fun parseStatus_badJsonReturnsNull() {
        assertNull(ServerStates.parseStatus("not json"))
        assertNull(ServerStates.parseStatus(""))
    }

    @Test
    fun notificationText_mapping() {
        val running = ServerStates.parseStatus(runningJson())!!
        assertEquals("v1.0.6 · 本机 http://127.0.0.1:36603", ServerStates.notificationText(running, lanEnabled = false))
        assertTrue(
            ServerStates.notificationText(running, lanEnabled = true).endsWith("局域网已开放（明文）")
        )

        val starting = ServerStates.Snapshot(ServerStates.STATE_STARTING, null, null, null, null, 0)
        assertTrue(ServerStates.notificationText(starting, false).contains("迁移"))

        val errored = ServerStates.Snapshot(ServerStates.STATE_ERROR, null, null, "[bind] 端口占用", "bind", 0)
        assertEquals("[bind] 端口占用", ServerStates.notificationText(errored, false))
    }

    @Test
    fun phaseLabel_mapping() {
        assertEquals("数据库迁移", ServerStates.phaseLabel("migration"))
        assertEquals("健康自检", ServerStates.phaseLabel("health"))
        assertEquals("启动", ServerStates.phaseLabel(null))
        assertEquals("启动", ServerStates.phaseLabel("unknown-phase"))
    }
}
