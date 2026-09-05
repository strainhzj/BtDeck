package com.btdeck.companion

import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.openContextualActionModeOverflowMenu
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.btdeck.companion.ui.ServerListActivity
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matchers.anything
import org.hamcrest.Matchers.containsString
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.X509Certificate

/**
 * task .3 设备级验收——自签证书信任与证书变更：
 * 1. 自签 HTTPS 首访必须弹「不受信任的证书」确认框（禁止无条件 proceed）；
 * 2. 用户确认后指纹按 profile 作用域落库（与 keystore 证书实算值一致）；
 * 3. 指纹钉扎让健康检查转「就绪」（OkHttp trust-any + CertificatePinner）；
 * 4. 服务器证书更换后必须重新确认：WebView 再次弹框、健康检查转「证书错误」。
 */
@RunWith(AndroidJUnit4::class)
class CompanionSelfSignedCertUiTest {

    private lateinit var server: TinyLoopbackServer
    private val keystorePassword = "btdeck-test".toCharArray()

    @Before
    fun startCertA() {
        CompanionTestState.resetAll()
        server = TinyLoopbackServer.startTls("certA", keystoreBytes("test_cert_a.p12"), keystorePassword)
    }

    @After
    fun stopServer() {
        server.stop()
    }

    private fun keystoreBytes(asset: String): ByteArray =
        InstrumentationRegistry.getInstrumentation().context.assets.open(asset).use { it.readBytes() }

    /** 与 TrustScope 同格式（SPKI 的 SHA-256，大写 hex 冒号分隔）实算 keystore 证书指纹。 */
    private fun expectedFingerprint(asset: String): String {
        val ks = KeyStore.getInstance("PKCS12")
        keystoreBytes(asset).inputStream().use { ks.load(it, keystorePassword) }
        val cert = ks.getCertificate("cert") as X509Certificate
        return MessageDigest.getInstance("SHA-256").digest(cert.publicKey.encoded)
            .joinToString(":") { byte -> "%02X".format(byte) }
    }

    /** WebView 会话可能有页面历史，一次 back 只退页面——循环退栈直到回到列表。 */
    private fun backToListFromWebView() {
        repeat(4) {
            if (CompanionTestState.currentActivity !is com.btdeck.companion.ui.WebViewActivity) {
                return
            }
            pressBack()
            // 等 resumed 状态稳定，避免在 destroy/resume 空窗期重复按 back 误杀 app
            CompanionTestState.awaitTrue(2_000) {
                CompanionTestState.currentActivity is com.btdeck.companion.ui.ServerListActivity
            }
        }
    }

    @Test
    fun trustDialogScopesFingerprintAndCertChangeRequiresReconfirmation() {
        val profile = CompanionTestState.seedProfile("自签服务器", server.tlsBaseUrl())

        // 单一列表场景贯穿全流程：行点击 → WebView 会话 → back 回列表 → 菜单 → 换证书重开
        ActivityScenario.launch(ServerListActivity::class.java).use {
            // ---- 1. 首访弹信任框，文案含指纹与重确认提示 ----
            onData(anything()).inAdapterView(withId(R.id.server_list)).atPosition(0).perform(click())

            val dialogShown = CompanionTestState.eventually {
                onView(withText("不受信任的证书")).inRoot(isDialog()).check(matches(isDisplayed()))
            }
            assertTrue("自签证书首访必须弹出『不受信任的证书』确认框", dialogShown)
            onView(allOf(withText(containsString("指纹（SHA-256）")), isDisplayed()))
                .inRoot(isDialog())
                .check(matches(isDisplayed()))
            onView(allOf(withText(containsString("证书更换后需重新确认")), isDisplayed()))
                .inRoot(isDialog())
                .check(matches(isDisplayed()))

            // ---- 2. 确认信任 → 页面完成加载 ----
            onView(withText("信任该证书")).inRoot(isDialog()).perform(click())
            val loaded = CompanionTestState.awaitTrue {
                CompanionTestState.store().find(profile.id)?.lastConnectedAt ?: 0L > 0L
            }
            assertTrue("信任后页面应完成同源加载（lastConnectedAt 落库）", loaded)

            // ---- 3. 指纹按 profile 作用域记录，与证书实算值一致 ----
            val stored = CompanionTestState.store().find(profile.id)
            assertEquals(
                listOf(expectedFingerprint("test_cert_a.p12")),
                stored?.trustedCertFingerprints?.toList(),
            )

            // ---- 4. 回列表：钉扎健康检查转「就绪」 ----
            backToListFromWebView()
            openContextualActionModeOverflowMenu()
            onView(withText("测试连接")).perform(click())
            val ready = CompanionTestState.eventually(25_000) {
                onView(withId(R.id.row_health)).check(matches(withText("就绪")))
            }
            assertTrue("信任指纹后健康检查应为『就绪』", ready)

            // ---- 5. 服务器换证书（B 替 A，同端口）→ 必须重新确认 ----
            val port = server.port
            server.stop()
            server = TinyLoopbackServer.startTls("certB", keystoreBytes("test_cert_b.p12"), keystorePassword, port)

            onData(anything()).inAdapterView(withId(R.id.server_list)).atPosition(0).perform(click())
            val reconfirmShown = CompanionTestState.eventually {
                onView(withText("不受信任的证书")).inRoot(isDialog()).check(matches(isDisplayed()))
            }
            assertTrue("证书变更后必须再次弹出信任确认框", reconfirmShown)
            // 拒绝新证书：不得静默放行
            onView(withText(android.R.string.cancel)).inRoot(isDialog()).perform(click())

            // 健康钉扎语义（同一 HealthClient 产品路径）：WebViewActivity 打开时的
            // 后台健康检查对换签后的服务器报 TLS_ERROR 并落库
            val tlsErrorRecorded = CompanionTestState.awaitTrue(20_000) {
                CompanionTestState.store().find(profile.id)?.healthState ==
                    com.btdeck.companion.data.ServerProfile.HealthState.TLS_ERROR
            }
            assertTrue("证书变更后健康检查应为『证书错误』（钉扎不匹配）", tlsErrorRecorded)
        }
    }
}
