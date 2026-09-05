package com.btdeck.companion

import android.content.Intent
import android.webkit.CookieManager
import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import org.hamcrest.Matchers.anything
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.btdeck.companion.ui.ServerListActivity
import com.btdeck.companion.ui.WebViewActivity
import org.junit.After
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicReference

/**
 * task .3/.8 设备级验收——多 Profile 切换的 cookie/storage/凭据隔离与自动登录：
 * - 打开保存了凭据的服务器 A：WebView 自动登录（POST /api/v1/auth/login 带 A 凭据，
 *   token 写入 cookie）；
 * - 切换到服务器 B：A 的 cookie 被清除、B 不携带 A 的登录请求（凭据按 profile 隔离）；
 * - 回到 A：首次访问写入的 localStorage 标记已被全局清除（WebStorage.deleteAllData），
 *   页面重读为 none——若隔离失效则会读到旧值 A。
 */
@RunWith(AndroidJUnit4::class)
class CompanionProfileIsolationUiTest {

    private lateinit var serverA: TinyLoopbackServer
    private lateinit var serverB: TinyLoopbackServer

    @Before
    fun startServers() {
        CompanionTestState.resetAll()
        serverA = TinyLoopbackServer.startPlain("A")
        serverB = TinyLoopbackServer.startPlain("B")
    }

    @After
    fun stopServers() {
        serverA.stop()
        serverB.stop()
    }

    /** CookieManager 读取固定走主线程（WebView 进程级单例）。 */
    private fun cookieOf(url: String): String? {
        val holder = AtomicReference<String?>()
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            holder.set(CookieManager.getInstance().getCookie(url))
        }
        return holder.get()
    }

    @Test
    fun switchingProfilesClearsCookiesAndCredentialsStayScoped() {
        val profileA = CompanionTestState.seedProfile(
            "服务器A", serverA.baseUrl(), username = "admin", password = "secret-A",
        )
        CompanionTestState.seedProfile("服务器B", serverB.baseUrl())

        ActivityScenario.launch(ServerListActivity::class.java).use {
            // ---- 打开 A：自动登录 + cookie 标记 ----
            onData(anything()).inAdapterView(withId(R.id.server_list)).atPosition(0).perform(click())
            val loginSeen = CompanionTestState.awaitTrue(20_000) {
                serverA.requestsFor("/api/v1/auth/login").isNotEmpty()
            }
            assertTrue("保存凭据的 A 应触发自动登录", loginSeen)
            val loginBody = serverA.requestsFor("/api/v1/auth/login").first().body.orEmpty()
            assertTrue(
                "登录请求必须携带 A profile 的凭据",
                loginBody.contains("\"username\":\"admin\"") && loginBody.contains("\"password\":\"secret-A\""),
            )
            assertTrue(
                "自动登录后应写入 access token cookie",
                CompanionTestState.awaitTrue { cookieOf(serverA.baseUrl())?.contains("vue_typescript_admin_access_token=") == true },
            )
            assertTrue(
                "A 页面 Set-Cookie 标记应可见",
                CompanionTestState.awaitTrue { cookieOf(serverA.baseUrl())?.contains("srv=A") == true },
            )

            // ---- 切换 B：cookie 清除 + 凭据不越界 ----
            pressBack()
            println("ISO-DIAG: beforeB cookieA='${cookieOf(serverA.baseUrl())}'")
            onData(anything()).inAdapterView(withId(R.id.server_list)).atPosition(1).perform(click())
            val bLoaded = CompanionTestState.awaitTrue(20_000) {
                serverB.requestsFor("/").isNotEmpty()
            }
            assertTrue("B 页面应完成加载", bLoaded)
            assertTrue(
                "B 不得收到登录请求（凭据按 profile 隔离）",
                serverB.requestsFor("/api/v1/auth/login").isEmpty(),
            )
            // WebView cookie 不分端口（RFC 6265）：B 的同域 srv=B 可出现在 A 的 URL 上，
            // 但 A 会话残留（srv=A / access token）必须已被 removeAllCookies 清除
            val cookieAResidueGone = CompanionTestState.awaitTrue {
                val cookieA = cookieOf(serverA.baseUrl())
                cookieA == null ||
                    (!cookieA.contains("srv=A") && !cookieA.contains("vue_typescript_admin_access_token="))
            }
            println("ISO-DIAG: afterB cookieA='${cookieOf(serverA.baseUrl())}' cookieB='${cookieOf(serverB.baseUrl())}'")
            assertTrue("切换后 A 的会话 cookie 残留应被清除", cookieAResidueGone)
        }
    }

    @Test
    fun switchingProfilesClearsWebStorageAcrossOrigins() {
        val profileA = CompanionTestState.seedProfile("服务器A", serverA.baseUrl())
        CompanionTestState.seedProfile("服务器B", serverB.baseUrl())

        fun openAndReadMarker(profileId: String, server: TinyLoopbackServer): String {
            val marker = AtomicReference<String?>()
            ActivityScenario.launch<WebViewActivity>(
                Intent(InstrumentationRegistry.getInstrumentation().targetContext, WebViewActivity::class.java)
                    .putExtra(WebViewActivity.EXTRA_PROFILE_ID, profileId),
            ).use { scenario ->
                assertTrue(
                    "页面应完成加载",
                    CompanionTestState.awaitTrue(20_000) { server.requestsFor("/").isNotEmpty() },
                )
                assertTrue(
                    "页面应渲染出 marker 结果",
                    CompanionTestState.awaitTrue(20_000) {
                        scenario.onActivity { activity ->
                            activity.findViewById<WebView>(R.id.web_view).evaluateJavascript(
                                "(function(){var el=document.getElementById('out');return el?el.textContent:'';})()",
                            ) { value -> marker.set(value) }
                        }
                        marker.get() != null
                    },
                )
            }
            return marker.get() ?: ""
        }

        // 首访 A：写入 localStorage 标记（existing 为空）
        val firstVisit = openAndReadMarker(profileA.id, serverA)
        assertTrue("首访 A 应读到 marker=none，实际: $firstVisit", firstVisit.contains("marker=none"))

        // 中间访问 B（触发 WebViewActivity 的 cookie/storage 全清）
        val profileB = CompanionTestState.store().loadAll().first { it.displayName == "服务器B" }
        val visitB = openAndReadMarker(profileB.id, serverB)
        assertTrue("B 页面应读到 marker 结果，实际: $visitB", visitB.contains("marker="))

        // B 会话后、回到 A 之前：A 的会话 cookie 残留应已清除（B 同域标记可出现）
        val cookieAAfterB = cookieOf(serverA.baseUrl())
        assertTrue(
            "B 会话后 A 的会话 cookie 残留应被清除，实际: '$cookieAAfterB'",
            cookieAAfterB == null ||
                (!cookieAAfterB.contains("srv=A") && !cookieAAfterB.contains("vue_typescript_admin_access_token=")),
        )

        // 回到 A：localStorage 已被清除 → 再次读到 none；若隔离失效会读到旧值 A
        val revisitA = openAndReadMarker(profileA.id, serverA)
        assertTrue(
            "切换 profile 后 A 的 localStorage 应被清除（读到 none），实际: $revisitA",
            revisitA.contains("marker=none") && !revisitA.contains("marker=A"),
        )
    }
}
