package com.btdeck.companion

import android.app.Application
import android.webkit.CookieManager

class CompanionApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // WebView cookie 全局就绪；伴侣模式的凭据隔离依赖切换 profile 时
        // 全量清除（CookieManager 是进程级单例，无法按 profile 分区）
        CookieManager.getInstance().setAcceptCookie(true)
    }
}
