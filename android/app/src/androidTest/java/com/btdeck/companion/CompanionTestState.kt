package com.btdeck.companion

import android.content.Context
import androidx.test.platform.app.InstrumentationRegistry
import com.btdeck.companion.data.CredentialRecord
import com.btdeck.companion.data.CredentialVault
import com.btdeck.companion.data.ServerProfile
import com.btdeck.companion.data.ServerProfileStore

/** 仪表化测试共享夹具：profile/凭据持久层清理、种子与轮询工具。 */
object CompanionTestState {

    /** 栈顶 Activity（WebViewActivity 断言用）；resetAll 时幂等安装跟踪器。 */
    @Volatile
    var currentActivity: android.app.Activity? = null
        private set

    private var trackerInstalled = false

    private fun installActivityTracker() {
        if (trackerInstalled) return
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync {
            val app = instrumentation.targetContext.applicationContext as android.app.Application
            app.registerActivityLifecycleCallbacks(object : android.app.Application.ActivityLifecycleCallbacks {
                override fun onActivityStarted(activity: android.app.Activity) {
                    currentActivity = activity
                }

                override fun onActivityDestroyed(activity: android.app.Activity) {
                    if (currentActivity === activity) currentActivity = null
                }

                override fun onActivityCreated(activity: android.app.Activity, savedInstanceState: android.os.Bundle?) {}

                override fun onActivityResumed(activity: android.app.Activity) {
                    currentActivity = activity
                }
                override fun onActivityPaused(activity: android.app.Activity) {}
                override fun onActivityStopped(activity: android.app.Activity) {}
                override fun onActivitySaveInstanceState(activity: android.app.Activity, outState: android.os.Bundle) {}
            })
        }
        trackerInstalled = true
    }

    fun context(): Context = InstrumentationRegistry.getInstrumentation().targetContext

    fun store(): ServerProfileStore = ServerProfileStore(context())

    fun vault(): CredentialVault = CredentialVault(context())

    /** 清空两个 SharedPreferences 存储与已记录指纹/凭据（每个用例独立起点）。 */
    fun resetAll() {
        installActivityTracker()
        val ctx = context()
        ctx.getSharedPreferences("btdeck_companion", Context.MODE_PRIVATE).edit().clear().commit()
        ctx.getSharedPreferences("btdeck_companion_credentials", Context.MODE_PRIVATE).edit().clear().commit()
    }

    fun seedProfile(
        displayName: String,
        baseUrl: String,
        username: String = "",
        password: String? = null,
    ): ServerProfile {
        val profile = ServerProfile(displayName = displayName, baseUrl = baseUrl, username = username)
        store().upsert(profile)
        password?.let { vault().save(profile.id, CredentialRecord(username, it)) }
        return profile
    }

    /** 读取栈顶 WebViewActivity 失败覆盖层文案（无则空串）。 */
    fun webViewOverlayText(): String {
        val holder = arrayOf("")
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            holder[0] = (currentActivity as? com.btdeck.companion.ui.WebViewActivity)
                ?.findViewById<android.widget.TextView>(com.btdeck.companion.R.id.error_text)
                ?.text?.toString() ?: ""
        }
        return holder[0]
    }

    fun awaitTrue(timeoutMs: Long = 20_000, intervalMs: Long = 250, condition: () -> Boolean): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (runCatching(condition).getOrDefault(false)) return true
            Thread.sleep(intervalMs)
        }
        return runCatching(condition).getOrDefault(false)
    }

    /** Espresso 断言轮询：视图/对话框异步出现时用（最终态不满足时返回 false）。 */
    fun eventually(timeoutMs: Long = 20_000, intervalMs: Long = 250, assertion: () -> Unit): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        var lastError: Throwable? = null
        while (System.currentTimeMillis() < deadline) {
            try {
                assertion()
                return true
            } catch (e: Throwable) {
                lastError = e
                Thread.sleep(intervalMs)
            }
        }
        return try {
            assertion()
            true
        } catch (e: Throwable) {
            println("eventually failed: $e")
            false
        }
    }
}
