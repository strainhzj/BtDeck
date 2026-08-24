package com.btdeck.companion.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException

/**
 * 服务端健康检查（计划 Phase 2）：`/health/live` → `/health/ready` 链式探测。
 *
 * - live 探测连通性与进程存活；ready 探测业务就绪并读取 `data.version`；
 * - TLS 错误（自签证书不被 OkHttp 信任）单独归类 TLS_ERROR——与网络不可达
 *   区分开，提示用户走 WebView 的指纹信任流程；
 * - OkHttp 不消费 WebView 记录的信任指纹，自签 https 在此必然报 TLS_ERROR，
 *   属已知 MVP 边界（README 已登记）：版本提示退化为"证书错误"。
 */
class HealthClient {

    data class Report(
        val state: ServerProfile.HealthState,
        /** /health/ready 返回的服务端版本；非 READY 或响应缺失时为 null。 */
        val version: String?,
        /** 人类可读结果（Toast / 副标题直接展示）。 */
        val detail: String,
    )

    private val client = OkHttpClient.Builder()
        .connectTimeout(CONNECT_TIMEOUT_S, TimeUnit.SECONDS)
        .readTimeout(READ_TIMEOUT_S, TimeUnit.SECONDS)
        .build()

    suspend fun check(baseUrl: String): Report = withContext(Dispatchers.IO) {
        when (val live = probe("$baseUrl/health/live")) {
            is ProbeResult.NetworkError -> live.toReport()
            is ProbeResult.HttpError ->
                Report(ServerProfile.HealthState.UNREACHABLE, live.version, "服务存活检查失败：HTTP ${live.code}")
            is ProbeResult.Ok -> {
                if (live.body?.optString("status") != "alive") {
                    return@withContext Report(ServerProfile.HealthState.UNREACHABLE, null, "服务存活检查失败")
                }
                when (val ready = probe("$baseUrl/health/ready")) {
                    is ProbeResult.NetworkError -> ready.toReport()
                    is ProbeResult.HttpError ->
                        Report(ServerProfile.HealthState.NOT_READY, ready.version, "服务未就绪：${ready.reason}")
                    is ProbeResult.Ok ->
                        if (ready.body?.optString("status") == "ready") {
                            Report(ServerProfile.HealthState.READY, ready.version, "服务就绪")
                        } else {
                            Report(ServerProfile.HealthState.NOT_READY, ready.version, "服务未就绪")
                        }
                }
            }
        }
    }

    // ============ 内部：单端点探测与错误分类 ============

    private sealed class ProbeResult {
        /** HTTP 响应可达：body 为 data 对象（可能为 null），version 提取自 data.version。 */
        class Ok(val body: JSONObject?, val version: String?) : ProbeResult()
        class HttpError(val code: Int, val reason: String, val version: String?) : ProbeResult()
        class NetworkError(val cause: IOException) : ProbeResult()
    }

    private fun ProbeResult.NetworkError.toReport(): Report = when (cause) {
        is SSLException ->
            Report(ServerProfile.HealthState.TLS_ERROR, null, "证书错误（自签证书请在页面内确认信任）")
        else ->
            Report(ServerProfile.HealthState.UNREACHABLE, null, "无法连接服务器")
    }

    private fun probe(url: String): ProbeResult {
        val request = Request.Builder().url(url).get().build()
        return try {
            client.newCall(request).execute().use { response ->
                val data = runCatching {
                    response.body?.string()?.let { JSONObject(it).optJSONObject("data") }
                }.getOrNull()
                val version = data?.optString("version")?.takeIf { it.isNotEmpty() }
                when {
                    response.isSuccessful && data != null -> ProbeResult.Ok(data, version)
                    response.isSuccessful -> ProbeResult.Ok(null, version)
                    else -> ProbeResult.HttpError(
                        response.code,
                        data?.optJSONArray("reasonCodes")?.join("、") ?: response.message,
                        version,
                    )
                }
            }
        } catch (e: IOException) {
            ProbeResult.NetworkError(e)
        }
    }

    companion object {
        private const val CONNECT_TIMEOUT_S = 5L
        private const val READ_TIMEOUT_S = 10L
    }
}
