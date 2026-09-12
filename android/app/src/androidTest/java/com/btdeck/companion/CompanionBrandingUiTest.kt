package com.btdeck.companion

import android.Manifest
import android.content.Context
import android.os.Build
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.openContextualActionModeOverflowMenu
import androidx.test.espresso.matcher.RootMatchers
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers
import androidx.test.espresso.matcher.ViewMatchers.Visibility
import androidx.test.espresso.matcher.ViewMatchers.isChecked
import androidx.test.espresso.matcher.ViewMatchers.isNotChecked
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withEffectiveVisibility
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.btdeck.companion.server.LocalServerState
import com.btdeck.companion.ui.WizardActivity
import com.btdeck.companion.ui.ServerListActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputLayout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 品牌化 UI 回归（android-native-ui-branding）：翡翠绿 Material 改造的行为契约。
 * - 主题 colorPrimary 必须解析为 #059669（token/主题被误删或漂移即失败）；
 * - 向导品牌头部 + 双模式卡片存在，伴侣卡片进入服务器列表（MaterialButton 主操作）；
 * - 添加服务器表单：四个 OutlinedBox 输入框标签、http 私有地址联动机明文确认、
 *   https 撤回、空名称提交展示 TextInputLayout 错误且不关对话框、合法输入保存成行；
 * - 健康语义色：关闭端口 → 文案「不可达」+ 圆点/文案 error 红 #EF4444；
 * - 本机服务确认对话框：LAN 开关联动威胁模型文案（初始态从持久化恢复）。
 */
@RunWith(AndroidJUnit4::class)
class CompanionBrandingUiTest {

    @Before
    fun resetState() {
        CompanionTestState.resetAll()
        // LAN 偏好在独立 prefs（btdeck_server）+ 进程级镜像，测试内直接复位可控初态
        CompanionTestState.context()
            .getSharedPreferences("btdeck_server", Context.MODE_PRIVATE).edit().clear().commit()
        LocalServerState.lanEnabled = false
        // Android 13+：预授权通知权限，避免系统弹窗拦截向导本机服务入口
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            runCatching {
                InstrumentationRegistry.getInstrumentation().uiAutomation
                    .grantRuntimePermission(TARGET_PACKAGE, Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    @Test
    fun themeCarriesEmeraldPrimaryColor() {
        ActivityScenario.launch(WizardActivity::class.java).use { scenario ->
            val holder = arrayOf(0)
            scenario.onActivity { activity ->
                val ta = activity.obtainStyledAttributes(intArrayOf(android.R.attr.colorPrimary))
                holder[0] = ta.getColor(0, 0)
                ta.recycle()
            }
            assertEquals("colorPrimary 必须解析为翡翠绿 #059669", 0xFF059669.toInt(), holder[0])
        }
    }

    @Test
    fun wizardShowsBrandMarkAndBothModeCards() {
        ActivityScenario.launch(WizardActivity::class.java).use {
            onView(withId(R.id.brand_mark)).check(matches(isDisplayed()))
            onView(withId(R.id.card_companion)).check(matches(isDisplayed()))
            onView(withId(R.id.card_local)).check(matches(isDisplayed()))
            onView(withText(R.string.wizard_companion_title)).check(matches(isDisplayed()))
            onView(withText(R.string.wizard_local_title)).check(matches(isDisplayed()))
        }
    }

    @Test
    fun companionCardOpensServerListWithMaterialButton() {
        ActivityScenario.launch(WizardActivity::class.java).use {
            onView(withId(R.id.card_companion)).perform(click())
            val shown = CompanionTestState.eventually {
                onView(withId(R.id.btn_add_server))
                    .check(matches(ViewMatchers.isAssignableFrom(MaterialButton::class.java)))
                    .check(matches(isDisplayed()))
            }
            assertTrue("伴侣卡片应进入服务器列表且主操作为 MaterialButton", shown)
        }
    }

    @Test
    fun addDialogValidatesAndTogglesCleartextConsent() {
        ActivityScenario.launch(ServerListActivity::class.java).use {
            onView(withId(R.id.btn_add_server)).perform(click())

            // 四个输入框均包在 TextInputLayout（OutlinedBox 浮动标签）中
            assertFloatingHint(R.id.input_name, R.string.add_server_name)
            assertFloatingHint(R.id.input_url, R.string.add_server_url)
            assertFloatingHint(R.id.input_username, R.string.add_server_username)
            assertFloatingHint(R.id.input_password, R.string.add_server_password)

            // http 私有地址 → 明文风险确认出现；换 https → 撤回
            onView(withId(R.id.input_url)).perform(replaceText("http://192.168.1.10:8080"))
            onView(withId(R.id.check_consent)).check(matches(isDisplayed()))
            onView(withId(R.id.input_url)).perform(replaceText("https://example.com"))
            onView(withId(R.id.check_consent)).check(matches(withEffectiveVisibility(Visibility.GONE)))

            // 空名称提交 → TextInputLayout 错误展示 + 对话框不关闭
            onView(withText(android.R.string.ok)).inRoot(RootMatchers.isDialog()).perform(click())
            onView(withText("请输入显示名称")).check(matches(isDisplayed()))
            onView(withId(R.id.input_url)).check(matches(isDisplayed()))

            // 补全合法数据 → 保存、对话框关闭、列表出现新行
            onView(withId(R.id.input_name)).perform(replaceText("NAS"))
            onView(withText(android.R.string.ok)).inRoot(RootMatchers.isDialog()).perform(click())
            val saved = CompanionTestState.eventually {
                onView(withText("NAS")).check(matches(isDisplayed()))
                onView(withText("https://example.com")).check(matches(isDisplayed()))
            }
            assertTrue("合法输入应保存并出现在列表", saved)
        }
    }

    @Test
    fun unreachableProfileTintsHealthDotAndLabelErrorRed() {
        CompanionTestState.seedProfile("离线服务器", "http://127.0.0.1:9")
        ActivityScenario.launch(ServerListActivity::class.java).use {
            openContextualActionModeOverflowMenu()
            onView(withText("测试连接")).perform(click())

            val shown = CompanionTestState.eventually {
                onView(withId(R.id.row_health)).check(matches(withText("不可达")))
            }
            assertTrue("关闭端口应标记不可达", shown)

            val expectedError = 0xFFEF4444.toInt()
            onView(withId(R.id.row_health)).check { view, noView ->
                if (noView != null) throw noView
                assertEquals(
                    "健康文案应为 error 红",
                    expectedError,
                    (view as TextView).textColors.defaultColor,
                )
            }
            onView(withId(R.id.row_health_dot)).check { view, noView ->
                if (noView != null) throw noView
                assertEquals(
                    "健康圆点应为 error 红",
                    expectedError,
                    view.backgroundTintList?.defaultColor ?: 0,
                )
            }
        }
    }

    @Test
    fun localServerStartDialogTogglesThreatTextWithLan() {
        ActivityScenario.launch(WizardActivity::class.java).use {
            onView(withId(R.id.card_local)).perform(click())

            onView(withId(R.id.check_lan))
                .check(matches(isDisplayed()))
                .check(matches(isNotChecked()))
            onView(withId(R.id.text_start_hint)).check(matches(isDisplayed()))
            onView(withId(R.id.text_lan_threat))
                .check(matches(withEffectiveVisibility(Visibility.GONE)))

            onView(withId(R.id.check_lan)).perform(click())
            onView(withId(R.id.check_lan)).check(matches(isChecked()))
            onView(withId(R.id.text_lan_threat)).check(matches(isDisplayed()))
        }
    }

    /** 输入框必须包在 TextInputLayout 中且浮动标签文案未漂移（标识 OutlinedBox 表单结构）。
     *  EditText 直接父容器是 TIL 内部的 inputFrame（FrameLayout），需沿祖先链查找。 */
    private fun assertFloatingHint(inputId: Int, hintRes: Int) {
        val expected = CompanionTestState.context().getString(hintRes)
        onView(withId(inputId)).check { view, noView ->
            if (noView != null) throw noView
            var parent = view.parent
            var layout: TextInputLayout? = null
            while (parent is android.view.ViewGroup) {
                if (parent is TextInputLayout) {
                    layout = parent
                    break
                }
                parent = parent.parent
            }
            assertEquals(
                "输入框 ${view.context.resources.getResourceEntryName(inputId)} 未包在 TextInputLayout 中",
                true,
                layout != null,
            )
            assertEquals(
                "输入框 ${view.context.resources.getResourceEntryName(inputId)} 浮动标签漂移",
                expected,
                layout!!.hint.toString(),
            )
        }
    }

    companion object {
        private const val TARGET_PACKAGE = "com.btdeck.companion"
    }
}
