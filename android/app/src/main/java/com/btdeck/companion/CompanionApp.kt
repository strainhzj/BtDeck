package com.btdeck.companion

import android.app.Application
import android.webkit.CookieManager
import com.btdeck.companion.server.ServerPrefsImpl
import com.btdeck.companion.server.ServerPrewarm
import com.btdeck.companion.server.ServerService

class CompanionApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // WebView cookie 全局就绪；伴侣模式的凭据隔离依赖切换 profile 时
        // 全量清除（CookieManager 是进程级单例，无法按 profile 分区）
        CookieManager.getInstance().setAcceptCookie(true)
        // 本机服务端预热（启动等待优化 2026-09-13）：仅曾用过的设备
        // （lastPort>0，上次 running 时由 ServerService 落盘）——纯伴侣
        // 用户不为此平白加载 Python 后端（百 MB 级内存代价）。首次使用
        // 者由向导"本机服务端"卡片入口预热（WizardActivity）。
        if (ServerService.isAbiSupported() && ServerPrefsImpl(this).lastPort > 0) {
            ServerPrewarm.prewarmAsync(this)
        }
    }
}
