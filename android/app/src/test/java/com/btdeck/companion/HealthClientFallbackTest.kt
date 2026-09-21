package com.btdeck.companion

import com.btdeck.companion.data.HealthClient
import com.btdeck.companion.data.ServerProfile
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/**
 * HealthClient 反代兜底回退（根路径 /health 系列端点 → /api/v1 别名）的 JVM 契约：
 * 注入假 HttpCall 按 URL 分发响应（不依赖 mockwebserver/真网络），覆盖
 * 「纯文本健康块吞掉主路径→回退成功」「HTTP 404→回退」「双路径全败保留主路径
 * 归因」「网络错误不回退」「主路径正常零回退」五类路径。
 */
class HealthClientFallbackTest {

    private class FakeCall(private val responder: (String) -> Response) : HealthClient.HttpCall {
        val urls = mutableListOf<String>()

        override fun execute(request: Request, client: OkHttpClient): Response {
            val url = request.url.toString()
            urls.add(url)
            return responder(url)
        }
    }

    private val jsonType = "application/json".toMediaType()

    private fun respond(url: String, code: Int, body: String): Response =
        Response.Builder()
            .request(Request.Builder().url(url).get().build())
            .protocol(Protocol.HTTP_1_1)
            .code(code)
            .message("test")
            .body(body.toResponseBody(jsonType))
            .build()

    private val liveBody =
        """{"status":"success","code":"200","data":{"status":"alive","version":"1.0.6"}}"""
    private val readyBody =
        """{"status":"success","code":"200","data":{"status":"ready","version":"1.0.6"}}"""

    @Test
    fun textHealthBlock_fallsBackToApiAlias_andReachesReady() = runBlocking {
        // 网关静态健康块：/health/* 返回 200 纯文本（非法 JSON 信封）——正是
        // 「版本未知 · 服务存活检查失败」的线上形态；别名路径返回真实信封。
        val call = FakeCall { url ->
            when {
                url.endsWith("/api/v1/health/live") -> respond(url, 200, liveBody)
                url.endsWith("/api/v1/health/ready") -> respond(url, 200, readyBody)
                else -> respond(url, 200, "healthy\n")
            }
        }
        val report = HealthClient(call).check("http://10.0.0.8:8080")

        assertEquals(ServerProfile.HealthState.READY, report.state)
        assertEquals("1.0.6", report.version)
        assertEquals("服务就绪", report.detail)
        assertEquals(
            listOf(
                "http://10.0.0.8:8080/health/live",
                "http://10.0.0.8:8080/api/v1/health/live",
                "http://10.0.0.8:8080/health/ready",
                "http://10.0.0.8:8080/api/v1/health/ready",
            ),
            call.urls,
        )
    }

    @Test
    fun httpError404_fallsBackToApiAlias() = runBlocking {
        // 网关对根路径 /health/* 返回 404（无代理规则），别名经 /api/ 代理可达。
        val call = FakeCall { url ->
            when {
                url.endsWith("/api/v1/health/live") -> respond(url, 200, liveBody)
                url.endsWith("/api/v1/health/ready") -> respond(url, 200, readyBody)
                else -> respond(url, 404, """{"status":"error"}""")
            }
        }
        val report = HealthClient(call).check("http://example.com")

        assertEquals(ServerProfile.HealthState.READY, report.state)
        assertEquals("1.0.6", report.version)
    }

    @Test
    fun bothPathsFail_keepsPrimaryAttribution() = runBlocking {
        val call = FakeCall { url ->
            if (url.endsWith("/health/live")) {
                respond(url, 502, """{"status":"error"}""")
            } else {
                throw IOException("connection reset")
            }
        }
        val report = HealthClient(call).check("http://example.com")

        // 回退路径仍失败时保留主路径结果：HTTP 502 归因不失真。
        assertEquals(ServerProfile.HealthState.UNREACHABLE, report.state)
        assertEquals("服务存活检查失败：HTTP 502", report.detail)
        assertEquals(2, call.urls.size)
    }

    @Test
    fun networkError_doesNotFallback() = runBlocking {
        val call = FakeCall { throw IOException("unreachable") }
        val report = HealthClient(call).check("http://example.com")

        // 网络/TLS 错误不换路径重试（同主机同结果）。
        assertEquals(ServerProfile.HealthState.UNREACHABLE, report.state)
        assertEquals("无法连接服务器", report.detail)
        assertEquals(1, call.urls.size)
    }

    @Test
    fun primaryHealthy_neverTouchesAlias() = runBlocking {
        val call = FakeCall { url ->
            when {
                url.endsWith("/health/live") -> respond(url, 200, liveBody)
                url.endsWith("/health/ready") -> respond(url, 200, readyBody)
                else -> throw IOException("alias should not be probed")
            }
        }
        val report = HealthClient(call).check("http://example.com")

        assertEquals(ServerProfile.HealthState.READY, report.state)
        assertEquals("1.0.6", report.version)
        assertEquals(
            listOf("http://example.com/health/live", "http://example.com/health/ready"),
            call.urls,
        )
        assertTrue(call.urls.none { it.contains("/api/v1") })
    }
}
