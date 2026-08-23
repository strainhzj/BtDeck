package com.btdeck.companion.util

/**
 * URL 解析与主机分类（纯 JVM，供单元测试）。
 *
 * 设计约束：
 * - 只允许 http/https（计划 Phase 2：服务器地址仅接受 http/https URL）；
 * - 私有主机判定不做 DNS 解析（避免主线程网络 IO 与不可判定行为），
 *   只认字面量：loopback、RFC1918 三段、169.254/16、fc00::/7、fe80::/10、
 *   *.local 与 "localhost"。真实域名指向内网主机的场景按公网处理
 *   （fail-closed：明文一律拒绝，HTTPS 不受影响）。
 */
object Hosts {

    data class ParsedUrl(
        val scheme: String,
        val host: String,
        val port: Int,
        val baseUrl: String,
    )

    /** 解析并规范化 baseUrl（scheme://host[:port]，无路径无 query）。非法返回 null。 */
    fun parse(raw: String): ParsedUrl? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val schemeSeparator = trimmed.indexOf("://")
        if (schemeSeparator <= 0) return null
        val scheme = trimmed.substring(0, schemeSeparator).lowercase()
        if (scheme != "http" && scheme != "https") return null

        var rest = trimmed.substring(schemeSeparator + 3)
        // 去掉路径与 query（服务器根地址语义）
        rest = rest.substringBefore('/').substringBefore('?').substringBefore('#')
        if (rest.isEmpty()) return null

        val host: String
        val port: Int
        if (rest.startsWith("[")) {
            // IPv6 字面量 [::1]:8080
            val close = rest.indexOf(']')
            if (close <= 1) return null
            host = rest.substring(1, close).lowercase()
            val after = rest.substring(close + 1)
            port = when {
                after.isEmpty() -> if (scheme == "https") 443 else 80
                after.startsWith(":") -> after.substring(1).toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
                else -> return null
            }
        } else {
            val colon = rest.lastIndexOf(':')
            if (colon > 0 && rest.indexOf(':') == colon) {
                host = rest.substring(0, colon).lowercase()
                port = rest.substring(colon + 1).toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
            } else {
                host = rest.lowercase()
                port = if (scheme == "https") 443 else 80
            }
        }
        if (host.isEmpty()) return null
        val hostPart = if (host.contains(':')) "[$host]" else host
        val baseUrl = "$scheme://$hostPart" + if (isDefaultPort(scheme, port)) "" else ":$port"
        return ParsedUrl(scheme, host, port, baseUrl)
    }

    private fun isDefaultPort(scheme: String, port: Int): Boolean =
        (scheme == "https" && port == 443) || (scheme == "http" && port == 80)

    /** 是否私有/本地主机（按字面量判定，不做 DNS）。 */
    fun isPrivateLanHost(host: String): Boolean {
        val h = host.lowercase().removeSuffix(".")
        if (h == "localhost") return true
        if (h.endsWith(".local")) return true
        if (h.contains(':')) return isPrivateIpv6(h)

        val parts = h.split('.')
        if (parts.size != 4) return false
        val octets = IntArray(4)
        for (i in 0..3) {
            val part = parts[i]
            if (part.isEmpty() || part.length > 3 || !part.all { ch -> ch.isDigit() }) return false
            octets[i] = part.toInt()
            if (octets[i] !in 0..255) return false
        }
        val o = octets
        return when {
            o[0] == 127 -> true // loopback 127.0.0.0/8
            o[0] == 10 -> true // RFC1918
            o[0] == 172 && o[1] in 16..31 -> true
            o[0] == 192 && o[1] == 168 -> true
            o[0] == 169 && o[1] == 254 -> true // link-local
            else -> false
        }
    }

    private fun isPrivateIpv6(h: String): Boolean {
        // 仅字面量判定：::1 / fc00::/7（ULA）/ fe80::/10（link-local）
        if (h == "::1" || h == "::") return true
        val firstGroup = h.substringBefore(':')
        if (firstGroup.isEmpty()) return h.startsWith("f") || h.startsWith("fe8")
        val first = firstGroup.toIntOrNull(16) ?: return false
        return (first and 0xFE00) == 0xFC00 || (first and 0xFFC0) == 0xFE80
    }
}
