package com.btdeck.companion

import android.app.Activity
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.openContextualActionModeOverflowMenu
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.btdeck.companion.ui.ServerListActivity
import com.btdeck.companion.ui.WebViewActivity
import org.hamcrest.Matchers.anything
import org.hamcrest.Matchers.containsString
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * task .3 设备级验收——离线状态提示：
 * - 服务器不可达时 WebView 必须给出可读的失败覆盖层（可重试/返回），不得白屏；
 * - 服务器列表「测试连接」必须把关闭端口归类为「不可达」。
 */
@RunWith(AndroidJUnit4::class)
class CompanionOfflineUiTest {

    @Before
    fun resetState() {
        CompanionTestState.resetAll()
    }

    @Test
    fun webViewShowsOfflineOverlayForUnreachableServer() {
        CompanionTestState.seedProfile("离线服务器", "http://127.0.0.1:9")

        ActivityScenario.launch(ServerListActivity::class.java).use {
            onData(anything()).inAdapterView(withId(R.id.server_list)).atPosition(0).perform(click())

            val overlayText = awaitWebViewOverlayText()
            assertTrue(
                "不可达服务器应显示『加载失败』覆盖层，实际: '$overlayText'",
                overlayText.contains("加载失败"),
            )
        }
    }

    @Test
    fun healthCheckMarksClosedPortUnreachable() {
        CompanionTestState.seedProfile("离线服务器", "http://127.0.0.1:9")

        ActivityScenario.launch(ServerListActivity::class.java).use {
            openContextualActionModeOverflowMenu()
            onView(withText("测试连接")).perform(click())

            val shown = CompanionTestState.eventually {
                onView(withId(R.id.row_health)).check(matches(withText("不可达")))
            }
            assertTrue("健康检查应把关闭端口标记为『不可达』", shown)
        }
    }

    /** 读取栈顶 WebViewActivity 的失败覆盖层文案（轮询至非空或超时）。 */
    private fun awaitWebViewOverlayText(timeoutMs: Long = 25_000): String {
        var text = ""
        CompanionTestState.awaitTrue(timeoutMs) {
            text = CompanionTestState.webViewOverlayText()
            text.isNotEmpty()
        }
        return text
    }
}
