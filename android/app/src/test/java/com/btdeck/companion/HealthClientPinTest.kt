package com.btdeck.companion

import com.btdeck.companion.data.HealthClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest

/**
 * HealthClient 指纹钉扎的纯 JVM 契约：
 * hex 指纹（TrustScope 形态）→ OkHttp "sha256/<base64>" pin 的转换正确性、
 * 非法输入拒收、host 解析边界。真实 TLS 握手与不匹配归因在设备/模拟器阶段验证。
 */
class HealthClientPinTest {

    @Test
    fun fingerprintToPin_matchesIndependentSha256Base64() {
        // 独立构造期望值：sha256(字节) → 标准 base64 → "sha256/<b64>"
        // （OkHttp pin 即此格式；CertificatePinner.pin 拒绝非 X509 桩，无法直接对拍）
        val certBytes = ByteArray(128) { it.toByte() }
        val digest = MessageDigest.getInstance("SHA-256").digest(certBytes)
        val hexFingerprint = digest.joinToString(":") { "%02X".format(it) }
        val expected = "sha256/${java.util.Base64.getEncoder().encodeToString(digest)}"

        assertEquals(expected, HealthClient.fingerprintToPin(hexFingerprint))
    }

    @Test
    fun fingerprintToPin_acceptsLowercaseAndNoColonForms() {
        val digest = MessageDigest.getInstance("SHA-256").digest("btdeck".toByteArray())
        val canonical = digest.joinToString(":") { "%02X".format(it) }
        val lowercase = digest.joinToString("") { "%02x".format(it) }

        assertEquals(
            HealthClient.fingerprintToPin(canonical),
            HealthClient.fingerprintToPin(lowercase),
        )
        assertTrue(HealthClient.fingerprintToPin(lowercase)!!.startsWith("sha256/"))
    }

    @Test
    fun fingerprintToPin_rejectsMalformedInput() {
        assertNull(HealthClient.fingerprintToPin("not-a-fingerprint"))
        assertNull(HealthClient.fingerprintToPin("AB:CD"))                          // 长度不足
        assertNull(HealthClient.fingerprintToPin("z".repeat(64)))                   // 非 hex
        assertNull(HealthClient.fingerprintToPin(""))
    }

    @Test
    fun hostOf_extractsHostAndNormalizesIpv6() {
        assertEquals("example.com", HealthClient.hostOf("https://example.com:8443/base"))
        assertEquals("10.0.2.2", HealthClient.hostOf("http://10.0.2.2:5001"))
        assertEquals("::1", HealthClient.hostOf("https://[::1]:5001"))
        assertEquals("", HealthClient.hostOf("::::"))
    }
}
