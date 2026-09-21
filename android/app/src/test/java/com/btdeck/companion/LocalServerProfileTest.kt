package com.btdeck.companion

import com.btdeck.companion.data.ServerProfile
import com.btdeck.companion.net.LanHostPolicy
import com.btdeck.companion.server.LocalServerProfile
import com.btdeck.companion.server.ServerPrefs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 本机服务端 profile 契约锁定（Phase 3）：
 * - 固定 id / baseUrl 形态 / cleartextAllowed 语义；
 * - 既有 profile 复用（保留用户名与健康历史）；
 * - 本机 URL 通过 LanHostPolicy（回环豁免）——WebView 打开前的兜底校验闭环。
 */
class LocalServerProfileTest {

    @Test
    fun baseUrl_forms() {
        assertEquals("http://127.0.0.1:8300", LocalServerProfile.baseUrl(8300))
        assertEquals("http://127.0.0.1:65535", LocalServerProfile.baseUrl(65535))
    }

    @Test
    fun buildProfile_fresh() {
        val profile = LocalServerProfile.buildProfile(40001, existing = null)
        assertEquals(LocalServerProfile.PROFILE_ID, profile.id)
        assertEquals(LocalServerProfile.DISPLAY_NAME, profile.displayName)
        assertEquals("http://127.0.0.1:40001", profile.baseUrl)
        assertTrue(profile.cleartextAllowed)
    }

    @Test
    fun buildProfile_reusesExistingIdentityAndUsername() {
        val existing = ServerProfile(
            id = LocalServerProfile.PROFILE_ID,
            displayName = "随便改过的名字",
            baseUrl = "http://127.0.0.1:39999",
            username = "admin",
            cleartextAllowed = false,
            serverVersion = "1.0.6",
        )
        val profile = LocalServerProfile.buildProfile(41234, existing)
        assertEquals(LocalServerProfile.PROFILE_ID, profile.id) // id 不变：凭据/信任沿用
        assertEquals(LocalServerProfile.DISPLAY_NAME, profile.displayName) // 显示名归位
        assertEquals("http://127.0.0.1:41234", profile.baseUrl) // 端口刷新
        assertEquals("admin", profile.username) // 用户名保留
        assertTrue(profile.cleartextAllowed)
        assertEquals("1.0.6", profile.serverVersion)
    }

    @Test
    fun localUrlPassesPolicyLoopbackExempt() {
        // WebViewActivity 打开前的 LanHostPolicy 兜底对回环必须放行
        val url = LocalServerProfile.baseUrl(40001)
        assertTrue(LanHostPolicy.check(url, cleartextConsent = false).isOk)
    }

    @Test
    fun isLocal_recognizesOnlyFixedId() {
        assertTrue(LocalServerProfile.isLocal(
            ServerProfile(id = LocalServerProfile.PROFILE_ID, displayName = "x", baseUrl = "http://127.0.0.1:1")
        ))
        assertFalse(LocalServerProfile.isLocal(
            ServerProfile(id = "other", displayName = "x", baseUrl = "http://127.0.0.1:1")
        ))
    }

    /** ServerPrefs 实现的最小行为（端口/LAN 偏好默认值）。 */
    private class FakePrefs : ServerPrefs {
        override var lastPort: Int = 0
        override var lanEnabled: Boolean = false
    }

    @Test
    fun prefsDefaults() {
        val prefs = FakePrefs()
        assertEquals(0, prefs.lastPort) // 0 → Python 侧动态分配
        assertFalse(prefs.lanEnabled)  // LAN 默认关
    }
}
