package com.btdeck.companion

import com.btdeck.companion.net.LanHostPolicy
import com.btdeck.companion.util.Hosts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 计划 Phase 2 红线的行为锁定：
 * - 只允许 http/https URL；
 * - 明文 HTTP 仅按用户选择的私有 LAN 主机放行（公网明文即使已同意也拒绝）；
 * - 私有明文必须记录用户同意；
 * - URL 规范化（默认端口折叠、IPv6、路径剥离）。
 */
class LanHostPolicyTest {

    // ============ URL 解析与规范化 ============

    @Test
    fun parse_rejectsNonHttpSchemes() {
        assertNull(Hosts.parse("ftp://192.168.1.5"))
        assertNull(Hosts.parse("file:///etc/passwd"))
        assertNull(Hosts.parse("javascript:alert(1)"))
        assertNull(Hosts.parse("not-a-url"))
        assertNull(Hosts.parse("http://"))
    }

    @Test
    fun parse_normalizesDefaultPortsAndStripsPath() {
        assertEquals("https://example.com", Hosts.parse("https://example.com/a/b?x=1")?.baseUrl)
        assertEquals("http://192.168.1.5:5001", Hosts.parse("http://192.168.1.5:5001/")?.baseUrl)
        // 默认端口折叠
        assertEquals("http://10.0.0.2", Hosts.parse("http://10.0.0.2:80")?.baseUrl)
        assertEquals("https://nas.local", Hosts.parse("https://NAS.local:443")?.baseUrl)
    }

    @Test
    fun parse_ipv6Literal() {
        val parsed = Hosts.parse("http://[::1]:5001")
        assertNotNull(parsed)
        assertEquals("::1", parsed!!.host)
        assertEquals(5001, parsed.port)
        assertEquals("http://[::1]:5001", parsed.baseUrl)
    }

    @Test
    fun parse_rejectsInvalidPort() {
        assertNull(Hosts.parse("http://192.168.1.5:99999"))
        assertNull(Hosts.parse("http://192.168.1.5:abc"))
    }

    // ============ 私有主机判定 ============

    @Test
    fun privateLanHost_literals() {
        assertTrue(Hosts.isPrivateLanHost("127.0.0.1"))
        assertTrue(Hosts.isPrivateLanHost("localhost"))
        assertTrue(Hosts.isPrivateLanHost("10.1.2.3"))
        assertTrue(Hosts.isPrivateLanHost("172.16.0.1"))
        assertTrue(Hosts.isPrivateLanHost("172.31.255.255"))
        assertTrue(Hosts.isPrivateLanHost("192.168.5.51"))
        assertTrue(Hosts.isPrivateLanHost("169.254.1.1"))
        assertTrue(Hosts.isPrivateLanHost("nas.local"))
        assertTrue(Hosts.isPrivateLanHost("::1"))
        assertTrue(Hosts.isPrivateLanHost("fc00::1"))
        assertTrue(Hosts.isPrivateLanHost("fe80::1"))
    }

    @Test
    fun privateLanHost_publicAndEdgeCases() {
        assertFalse(Hosts.isPrivateLanHost("example.com"))
        assertFalse(Hosts.isPrivateLanHost("8.8.8.8"))
        // 172.32 是公网段（172.16-31 才私有）
        assertFalse(Hosts.isPrivateLanHost("172.32.0.1"))
        // 含 127 的普通域名不得误判（历史后端同名坑）
        assertFalse(Hosts.isPrivateLanHost("127.0.0.1.example.com"))
        assertFalse(Hosts.isPrivateLanHost("192.168.1.5.evil.com"))
    }

    // ============ 策略 ============

    @Test
    fun httpsAlwaysOk() {
        assertEquals(true, LanHostPolicy.check("https://example.com", false).isOk)
        assertEquals(true, LanHostPolicy.check("https://192.168.1.5:5001", false).isOk)
    }

    @Test
    fun httpPrivateHostRequiresConsent() {
        val url = "http://192.168.5.51:5001"
        val without = LanHostPolicy.check(url, cleartextConsent = false)
        assertTrue(without is LanHostPolicy.Verdict.Reject)
        assertEquals(
            LanHostPolicy.Reason.HTTP_LAN_WITHOUT_CONSENT,
            (without as LanHostPolicy.Verdict.Reject).reason,
        )
        assertTrue(LanHostPolicy.check(url, cleartextConsent = true).isOk)
    }

    @Test
    fun httpPublicHostRejectedEvenWithConsent() {
        val url = "http://example.com"
        val verdict = LanHostPolicy.check(url, cleartextConsent = true)
        assertTrue(verdict is LanHostPolicy.Verdict.Reject)
        assertEquals(LanHostPolicy.Reason.HTTP_PUBLIC_HOST, (verdict as LanHostPolicy.Verdict.Reject).reason)
    }

    @Test
    fun malformedUrlRejected() {
        val verdict = LanHostPolicy.check("随便写的", cleartextConsent = true)
        assertTrue(verdict is LanHostPolicy.Verdict.Reject)
        assertEquals(LanHostPolicy.Reason.MALFORMED_URL, (verdict as LanHostPolicy.Verdict.Reject).reason)
    }

    @Test
    fun needsCleartextConsentOnlyForHttpPrivate() {
        assertTrue(LanHostPolicy.needsCleartextConsent("http://10.0.0.2:5001"))
        assertFalse(LanHostPolicy.needsCleartextConsent("https://10.0.0.2:5001"))
        assertFalse(LanHostPolicy.needsCleartextConsent("http://example.com"))
    }

    // ============ 回环豁免（Phase 3 本机服务端） ============

    @Test
    fun loopbackHostDetection() {
        assertTrue(Hosts.isLoopbackHost("127.0.0.1"))
        assertTrue(Hosts.isLoopbackHost("127.3.4.5")) // 整个 127/8
        assertTrue(Hosts.isLoopbackHost("LOCALHOST"))
        assertTrue(Hosts.isLoopbackHost("::1"))
        assertFalse(Hosts.isLoopbackHost("192.168.1.5"))
        assertFalse(Hosts.isLoopbackHost("10.0.0.2"))
        // 非 127 开头的 127 字样不得误判
        assertFalse(Hosts.isLoopbackHost("127.0.0.1.example.com"))
        // 残缺 IPv4 形态
        assertFalse(Hosts.isLoopbackHost("127.0"))
    }

    @Test
    fun httpLoopbackExemptFromConsent() {
        // 本机服务端固定形态：无需明文确认记录
        assertTrue(LanHostPolicy.check("http://127.0.0.1:36603", cleartextConsent = false).isOk)
        assertTrue(LanHostPolicy.check("http://localhost:8300", cleartextConsent = false).isOk)
        assertTrue(LanHostPolicy.check("http://[::1]:8300", cleartextConsent = false).isOk)
    }

    @Test
    fun loopbackExemptDoesNotLeakToLan() {
        // 豁免只覆盖回环；LAN 私有主机仍要求确认
        val verdict = LanHostPolicy.check("http://192.168.5.51:5001", cleartextConsent = false)
        assertTrue(verdict is LanHostPolicy.Verdict.Reject)
        assertEquals(
            LanHostPolicy.Reason.HTTP_LAN_WITHOUT_CONSENT,
            (verdict as LanHostPolicy.Verdict.Reject).reason,
        )
        // loopback 不触发确认 UI
        assertFalse(LanHostPolicy.needsCleartextConsent("http://127.0.0.1:8300"))
        assertFalse(LanHostPolicy.needsCleartextConsent("http://localhost:8300"))
    }
}
