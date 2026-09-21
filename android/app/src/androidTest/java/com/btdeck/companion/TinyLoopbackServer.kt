package com.btdeck.companion

import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.InetAddress
import java.net.ServerSocket
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.util.Collections
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext

/**
 * 仪表化测试专用回环 HTTP(S) 服务器（设备 127.0.0.1 上自持，不依赖宿主机/adb reverse）。
 *
 * - 协议面按 BtDeck 前端/健康检查消费的最小契约实现：/health/live、/health/ready、
 *   POST /api/v1/auth/login（响应可注入）、/（带 Set-Cookie 标记与 localStorage 探针页）；
 * - TLS 形态从 androidTest assets 装载 PKCS12 自签证书（test_cert_a/b.p12），
 *   用于 WebView SslError 信任弹窗与 OkHttp 指纹钉扎的设备级验证；
 * - Connection: close 短连接，OkHttp/WebView 均可正常消费。
 */
class TinyLoopbackServer private constructor(
    private val serverSocket: ServerSocket,
    private val marker: String,
) {
    class RecordedRequest(val method: String, val path: String, val body: String?) {
        override fun toString(): String = "$method $path${body?.let { " body=${it.take(80)}" } ?: ""}"
    }

    val port: Int = serverSocket.localPort
    val requests: MutableList<RecordedRequest> = Collections.synchronizedList(mutableListOf())

    /** POST /api/v1/auth/login 的响应体（默认成功 token，可注入失败信封）。 */
    @Volatile
    var loginResponseBody: String =
        """{"code":"200","status":"success","msg":"登录成功","data":[{"access_token":"tok-$marker","refresh_token":"refresh-$marker"}]}"""

    private val running = AtomicBoolean(true)

    fun baseUrl(): String = "http://127.0.0.1:$port"

    fun tlsBaseUrl(): String = "https://127.0.0.1:$port"

    fun stop() {
        running.set(false)
        runCatching { serverSocket.close() }
    }

    fun requestsFor(path: String): List<RecordedRequest> = requests.filter { it.path == path }

    private fun startAcceptLoop() {
        Thread({
            while (running.get()) {
                val socket = runCatching { serverSocket.accept() }.getOrNull() ?: break
                Thread({ handle(socket) }, "tiny-loopback-conn").start()
            }
        }, "tiny-loopback-accept").apply { isDaemon = true }.start()
    }

    private fun handle(socket: java.net.Socket) {
        // 自签证书未信任/换签阶段客户端会以 TLS alert 中断连接——预期噪声，
        // 服务线程吞掉，避免测试运行器把未捕获异常记为用例失败
        runCatching { handleOnce(socket) }
    }

    private fun handleOnce(socket: java.net.Socket) {
        socket.use { s ->
            s.soTimeout = 10_000
            val reader = BufferedReader(InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8))
            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return
            val method = parts[0]
            var path = parts[1]
            var contentLength = 0
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) break
                val colon = line.indexOf(':')
                if (colon > 0 && line.substring(0, colon).trim().equals("Content-Length", ignoreCase = true)) {
                    contentLength = line.substring(colon + 1).trim().toIntOrNull() ?: 0
                }
            }
            val body = if (contentLength > 0) {
                val chars = CharArray(contentLength)
                var read = 0
                while (read < contentLength) {
                    val n = reader.read(chars, read, contentLength - read)
                    if (n < 0) break
                    read += n
                }
                String(chars, 0, read)
            } else null
            val queryIndex = path.indexOf('?')
            if (queryIndex >= 0) path = path.substring(0, queryIndex)
            requests.add(RecordedRequest(method, path, body))

            val (payload, contentType, extraHeaders) = when {
                path == "/health/live" ->
                    Triple(
                        """{"code":"200","status":"success","msg":"","data":{"status":"alive"}}""",
                        "application/json",
                        "",
                    )
                path == "/health/ready" ->
                    Triple(
                        """{"code":"200","status":"success","msg":"","data":{"status":"ready","version":"9.9.9-$marker"}}""",
                        "application/json",
                        "",
                    )
                path == "/api/v1/auth/login" && method == "POST" ->
                    Triple(loginResponseBody, "application/json", "")
                path == "/" ->
                    Triple(
                        """<!doctype html><html><head><script>
try {
  var existing = localStorage.getItem('btdeck_srv_marker');
  if (!existing) localStorage.setItem('btdeck_srv_marker', '$marker');
  document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('out').textContent =
      'marker=' + (existing || 'none');
  });
} catch (e) {}
</script></head><body><div id="out">loading</div>SERVER $marker</body></html>""",
                        "text/html; charset=utf-8",
                        "Set-Cookie: srv=$marker; Path=/\r\n",
                    )
                else -> Triple("{\"code\":\"404\"}", "application/json", "")
            }
            val bytes = payload.toByteArray(StandardCharsets.UTF_8)
            val head = buildString {
                append("HTTP/1.1 200 OK\r\n")
                append("Content-Type: $contentType\r\n")
                append("Content-Length: ${bytes.size}\r\n")
                append(extraHeaders)
                append("Connection: close\r\n\r\n")
            }
            s.getOutputStream().apply {
                write(head.toByteArray(StandardCharsets.UTF_8))
                write(bytes)
                flush()
            }
        }
    }

    companion object {
        private fun bind(socket: ServerSocket, port: Int): ServerSocket {
            // SO_REUSEADDR 必须在 bind 前设置：证书换签演练需要在同端口重启服务器
            socket.reuseAddress = true
            socket.bind(java.net.InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 10)
            return socket
        }

        fun startPlain(marker: String, port: Int = 0): TinyLoopbackServer {
            val socket = bind(ServerSocket(), port)
            return TinyLoopbackServer(socket, marker).apply { startAcceptLoop() }
        }

        /** 从 androidTest assets 装载 PKCS12 自签证书并启动 HTTPS 形态。 */
        fun startTls(
            marker: String,
            keystoreBytes: ByteArray,
            keystorePassword: CharArray,
            port: Int = 0,
        ): TinyLoopbackServer {
            val keyStore = KeyStore.getInstance("PKCS12")
            keystoreBytes.inputStream().use { keyStore.load(it, keystorePassword) }
            val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
            kmf.init(keyStore, keystorePassword)
            val context = SSLContext.getInstance("TLS").apply {
                init(kmf.keyManagers, null, null)
            }
            val factory = context.serverSocketFactory
            val socket = bind(factory.createServerSocket() as ServerSocket, port)
            return TinyLoopbackServer(socket, marker).apply { startAcceptLoop() }
        }
    }
}
