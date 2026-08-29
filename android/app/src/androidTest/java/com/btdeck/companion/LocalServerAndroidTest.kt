package com.btdeck.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Phase 3 本机服务端 AVD 实测（dual-mode-client task .4）：
 * 直接驱动 Python btdeck_server（start/status/stop 契约）——
 * 启动 → 迁移 → 健康握手（/health/live）→ 静态 SPA 首页 → 优雅停机 → 重启。
 *
 * FGS/通知/向导 UI 流程另行手动实录（证据入 feature_list.json task .4）。
 */
@RunWith(AndroidJUnit4::class)
class LocalServerAndroidTest {

    companion object {
        @BeforeClass
        @JvmStatic
        fun startPython() {
            if (!Python.isStarted()) {
                Python.start(
                    AndroidPlatform(InstrumentationRegistry.getInstrumentation().targetContext)
                )
            }
        }
    }

    private fun call(fn: String, vararg args: Any?): JSONObject = JSONObject(
        Python.getInstance().getModule("btdeck_server").callAttr(fn, *args).toString()
    )

    private fun awaitRunning(timeoutS: Long = 180): JSONObject {
        var last = JSONObject()
        val deadline = System.currentTimeMillis() + timeoutS * 1000
        while (System.currentTimeMillis() < deadline) {
            last = call("status")
            when (last.optString("state")) {
                "running" -> return last
                "error" -> throw AssertionError("启动失败: ${last.optString("error")}")
            }
            Thread.sleep(1000)
        }
        throw AssertionError("等待 running 超时（${timeoutS}s），最后状态: $last")
    }

    @Test
    fun startHealthStopRestart() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        // 测试数据目录与 ServerService 生产目录分离（btdeck-test）
        val dataRoot = File(ctx.filesDir, "btdeck-test").absolutePath

        val start = call("start", dataRoot, "127.0.0.1", 0)
        assertTrue(start.getBoolean("ok"))
        assertEquals("starting", start.optString("state"))

        val running = awaitRunning()
        val port = running.getInt("port")
        assertTrue("端口缺失", port in 1..65535)
        assertTrue("版本缺失", running.optString("version").isNotEmpty())

        // 健康握手 + 静态 SPA 首页（trust_env 语义由 OkHttp 天然满足：不读环境代理）
        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()
        client.newCall(Request.Builder().url("http://127.0.0.1:$port/health/live").build())
            .execute().use { resp ->
                assertEquals("health/live 非 200", 200, resp.code)
                val body = JSONObject(resp.body!!.string())
                assertEquals("alive", body.getJSONObject("data").optString("status"))
            }
        client.newCall(Request.Builder().url("http://127.0.0.1:$port/").build())
            .execute().use { resp ->
                assertEquals("静态首页非 200", 200, resp.code)
                val html = resp.body!!.string()
                assertTrue("首页不是 SPA index.html", html.contains("<div id=\"app\""))
            }

        // 优雅停机 → 幂等重启
        val stop = call("stop")
        assertTrue(stop.getBoolean("ok"))
        assertEquals("stopped", call("status").optString("state"))

        val restart = call("start", dataRoot, "127.0.0.1", port) // preferred=上次端口
        assertTrue(restart.getBoolean("ok"))
        val rerun = awaitRunning()
        assertEquals("重启未复用上次端口（LAN 便利性契约）", port, rerun.getInt("port"))

        call("stop")
        assertEquals("stopped", call("status").optString("state"))
    }
}
