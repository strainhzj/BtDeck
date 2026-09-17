package com.btdeck.companion.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.net.URI
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLException
import javax.net.ssl.SSLPeerUnverifiedException
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * 服务端健康检查（计划 Phase 2）：`/health/live` → `/health/ready` 链式探测。
 *
 * - live 探测连通性与进程存活；ready 探测业务就绪并读取 `data.version`；
 * - 传入 [trustedFingerprints]（WebView 指纹确认流程记录的 SHA-256）时，
 *   OkHttp 以"全信 SSLSocketFactory + 握手后手动 SPKI 钉扎"组合
 *   只信任这些指纹（trust-any + pin = trust-only-these），主机名校验由钉扎
 *   承担；指纹不匹配按 TLS_ERROR 归类并提示重新确认；
 * - 未传指纹时走系统信任链，自签证书必然 TLS_ERROR——提示用户走 WebView 的
 *   指纹信任流程（README 已登记的 MVP 边界现已通过本参数闭环）；
 * - 根路径 `/health` 系列端点（live/ready）可能被反向代理吞掉（静态健康块
 *   返回纯文本、SPA 兜底返回 HTML），后端在 `/api/v1` 下挂有同 handler 的
 *   免认证别名——主路径探测到"HTTP 错误或响应不是 JSON 信封"时回退别名再探
 *   一次（见 [probeWithFallback]），旧部署无需更新网关配置也能读到真实存活与版本。
 */
class HealthClient(private val httpCall: HttpCall = HttpCall { request, client ->
    client.newCall(request).execute()
}) {

    /** 单次 HTTP 执行点：默认真实 OkHttp；JVM 单测注入按 URL 分发的假实现。 */
    fun interface HttpCall {
        /** 与 OkHttp Call.execute 同契约：同步返回 Response，调用方负责 close。 */
        @Throws(IOException::class)
        fun execute(request: Request, client: OkHttpClient): Response
    }


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

    /** 握手中捕获对端证书链的 TrustManager（钉扎校验的数据源）。 */
    private class CapturingTrustManager : X509TrustManager {
        @Volatile
        var lastServerChain: Array<X509Certificate>? = null

        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit

        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            lastServerChain = chain
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }

    private class PinnedClient(val okHttp: OkHttpClient, val trustManager: CapturingTrustManager)

    /** 指纹钉扎客户端缓存：同一指纹集合复用（OkHttpClient 实例应共享连接池）。 */
    private val pinnedClients = HashMap<Int, PinnedClient>()

    suspend fun check(
        baseUrl: String,
        trustedFingerprints: Set<String> = emptySet(),
    ): Report = withContext(Dispatchers.IO) {
        val pins = trustedFingerprints.mapNotNull { fingerprintToPin(it) }
        val pinned = if (pins.isNotEmpty() && baseUrl.startsWith("https://", ignoreCase = true)) {
            pinnedClient(pins)
        } else {
            null
        }
        val target = pinned?.okHttp ?: client
        when (val live = probeWithFallback("/health/live", baseUrl, target, pins) { pinned?.trustManager?.lastServerChain }) {
            is ProbeResult.NetworkError -> live.toReport(pins.isNotEmpty())
            is ProbeResult.HttpError ->
                Report(ServerProfile.HealthState.UNREACHABLE, live.version, "服务存活检查失败：HTTP ${live.code}")
            is ProbeResult.Ok -> {
                if (live.body?.optString("status") != "alive") {
                    return@withContext Report(ServerProfile.HealthState.UNREACHABLE, null, "服务存活检查失败")
                }
                when (val ready = probeWithFallback("/health/ready", baseUrl, target, pins) { pinned?.trustManager?.lastServerChain }) {
                    is ProbeResult.NetworkError -> ready.toReport(pins.isNotEmpty())
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

    /**
     * 主路径探测的反代兜底：根路径 `/health` 系列端点被网关静态健康块（纯文本
     * 200）或 SPA 兜底（HTML 200）吞掉时，改探后端 `/api/v1` 下的免认证别名
     * （同 handler）。仅在主路径 HTTP 错误、或 2xx 但响应不是 JSON 信封
     * （body=null）时回退；网络/TLS 错误不换路径重试（同主机同结果，徒增等待）。
     * 回退仍未得到可解析信封则保留主路径结果，错误归因不失真。
     */
    private fun probeWithFallback(
        path: String,
        baseUrl: String,
        target: OkHttpClient,
        pins: List<String>,
        peerChainProvider: () -> Array<X509Certificate>?,
    ): ProbeResult {
        val primary = probe("$baseUrl$path", target, pins, peerChainProvider)
        val needsFallback = primary is ProbeResult.HttpError ||
            (primary is ProbeResult.Ok && primary.body == null)
        if (!needsFallback) return primary
        val alias = probe("$baseUrl$API_ALIAS_PREFIX$path", target, pins, peerChainProvider)
        return if (alias is ProbeResult.Ok && alias.body != null) alias else primary
    }

    private sealed class ProbeResult {
        /** HTTP 响应可达：body 为 data 对象（可能为 null），version 提取自 data.version。 */
        class Ok(val body: JSONObject?, val version: String?) : ProbeResult()
        class HttpError(val code: Int, val reason: String, val version: String?) : ProbeResult()
        class NetworkError(val cause: IOException) : ProbeResult()
    }

    private fun ProbeResult.NetworkError.toReport(pinned: Boolean): Report = when (cause) {
        is SSLPeerUnverifiedException ->
            Report(ServerProfile.HealthState.TLS_ERROR, null, PIN_MISMATCH_DETAIL)
        is SSLException ->
            Report(
                ServerProfile.HealthState.TLS_ERROR, null,
                if (pinned) PIN_MISMATCH_DETAIL else "证书错误（自签证书请在页面内确认信任）",
            )
        else ->
            Report(ServerProfile.HealthState.UNREACHABLE, null, "无法连接服务器")
    }

    private fun probe(
        url: String,
        target: OkHttpClient,
        pins: List<String>,
        peerChainProvider: () -> Array<X509Certificate>?,
    ): ProbeResult {
        val request = Request.Builder().url(url).get().build()
        return try {
            httpCall.execute(request, target).use { response ->
                // 手动钉扎（OkHttp CertificatePinner 与自定义 SSLSocketFactory 不兼容：
                // 信任链经空 TrustManager 清洗后 peer chain 为空，pin 校验必然失败——
                // 设备级实测 Certificate pinning failure）。在握手成功的响应上比对
                // 对端证书 SPKI 哈希，不匹配按 TLS_ERROR 归类提示重新确认。
                if (pins.isNotEmpty()) {
                    // 自定义 SSLSocketFactory 下 OkHttp Handshake/conscrypt 会话取不到对端
                    // 证书（peerCount=0 实测），改从 TrustManager 捕获的链取叶证书比对
                    val peerCert = peerChainProvider()?.firstOrNull()
                    val actualPin = peerCert?.let { spkiPinOf(it) }
                    if (actualPin == null || actualPin !in pins) {
                        throw SSLPeerUnverifiedException("btdeck pin mismatch")
                    }
                }
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

    /** 全信 TrustManager + 握手中捕获证书链手动 SPKI 钉扎：放行完全由 pin 集合决定。 */
    private fun pinnedClient(pins: List<String>): PinnedClient {
        val key = pins.hashCode()
        return synchronized(pinnedClients) {
            pinnedClients.getOrPut(key) {
                val trustManager = CapturingTrustManager()
                val sslContext = SSLContext.getInstance("TLS").apply {
                    init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
                }
                PinnedClient(
                    OkHttpClient.Builder()
                        .sslSocketFactory(sslContext.socketFactory, trustManager)
                        .hostnameVerifier { _, _ -> true } // 身份由指纹钉扎承担
                        .connectTimeout(CONNECT_TIMEOUT_S, TimeUnit.SECONDS)
                        .readTimeout(READ_TIMEOUT_S, TimeUnit.SECONDS)
                        .build(),
                    trustManager,
                )
            }
        }
    }

    /** 与 fingerprintToPin 同口径：对端证书 SPKI 的 sha256/<base64> pin。 */
    private fun spkiPinOf(cert: X509Certificate): String =
        "sha256/" + base64NoWrap(
            java.security.MessageDigest.getInstance("SHA-256").digest(cert.publicKey.encoded)
        )

    companion object {
        private const val CONNECT_TIMEOUT_S = 5L
        private const val READ_TIMEOUT_S = 10L

        /** 后端在 API 前缀下挂载的同 handler 健康检查别名（免认证）。 */
        private const val API_ALIAS_PREFIX = "/api/v1"
        private const val PIN_MISMATCH_DETAIL =
            "证书指纹不匹配（服务器证书已变更，请在页面内重新确认信任）"

        /** URI.host（IPv6 字面量去方括号）；解析失败返回空串（钉扎退化为系统信任）。 */
        @JvmStatic
        internal fun hostOf(baseUrl: String): String = runCatching {
            URI(baseUrl).host?.removeSurrounding("[", "]") ?: ""
        }.getOrDefault("")

        /**
         * TrustScope 的指纹是"冒号分隔大写 hex"；OkHttp pin 是 "sha256/<base64>"。
         * 容忍大小写与冒号差异；非法 hex 返回 null（该指纹跳过）。
         * Base64 自包含实现：java.util 是 API 26+（lint NewApi），android.util
         * 在 JVM 单测是 not-mocked stub——手写编码让设备与测试行为一致。
         */
        @JvmStatic
        internal fun fingerprintToPin(fingerprint: String): String? = runCatching {
            val hex = fingerprint.replace(":", "").trim()
            require(hex.length == SHA256_HEX_LEN && hex.all { it.isDigit() || it in 'a'..'f' || it in 'A'..'F' })
            val bytes = ByteArray(hex.length / 2) { i ->
                ((Character.digit(hex[i * 2], 16) shl 4) or Character.digit(hex[i * 2 + 1], 16)).toByte()
            }
            "sha256/${base64NoWrap(bytes)}"
        }.getOrNull()

        /** 标准 Base64（无换行，等价 NO_WRAP）；SHA-256 产物为 44 字符一个 '='。 */
        private fun base64NoWrap(bytes: ByteArray): String {
            val table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            val out = StringBuilder((bytes.size * 4 / 3) + 4)
            var i = 0
            while (i + 2 < bytes.size) {
                val n = ((bytes[i].toInt() and 0xFF) shl 16) or
                    ((bytes[i + 1].toInt() and 0xFF) shl 8) or
                    (bytes[i + 2].toInt() and 0xFF)
                out.append(table[(n ushr 18) and 0x3F]).append(table[(n ushr 12) and 0x3F])
                    .append(table[(n ushr 6) and 0x3F]).append(table[n and 0x3F])
                i += 3
            }
            when (bytes.size - i) {
                1 -> {
                    val n = (bytes[i].toInt() and 0xFF) shl 16
                    out.append(table[(n ushr 18) and 0x3F]).append(table[(n ushr 12) and 0x3F]).append("==")
                }
                2 -> {
                    val n = ((bytes[i].toInt() and 0xFF) shl 16) or ((bytes[i + 1].toInt() and 0xFF) shl 8)
                    out.append(table[(n ushr 18) and 0x3F]).append(table[(n ushr 12) and 0x3F])
                        .append(table[(n ushr 6) and 0x3F]).append('=')
                }
            }
            return out.toString()
        }

        private const val SHA256_HEX_LEN = 64
    }
}
