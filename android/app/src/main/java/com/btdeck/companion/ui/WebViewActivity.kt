package com.btdeck.companion.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.net.http.SslError
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebStorage
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.btdeck.companion.R
import com.btdeck.companion.data.CredentialVault
import com.btdeck.companion.data.HealthClient
import com.btdeck.companion.data.ServerProfile
import com.btdeck.companion.data.ServerProfileStore
import com.btdeck.companion.data.buildAutoLoginScript
import com.btdeck.companion.net.LanHostPolicy
import com.btdeck.companion.net.TrustScope
import com.btdeck.companion.util.Hosts
import kotlinx.coroutines.launch

/**
 * 远程同源 WebView（计划 Phase 2）：
 * - 直接加载服务器自带前端，不把前端 API/store 复制进 APK；
 * - 切换 profile 时清除全部 cookie/localStorage（CookieManager 进程级单例，
 *   无法按 profile 分区——清除即隔离，access/refresh token 不跨服务器复用）；
 * - 自签证书必须用户显式信任并把指纹记录在该 profile（禁止无条件 proceed）；
 * - 加载超时/失败可重试返回；副标题展示服务端版本提示（/health/ready）。
 */
class WebViewActivity : AppCompatActivity() {

    private lateinit var store: ServerProfileStore
    private lateinit var credentials: CredentialVault
    private lateinit var profile: ServerProfile
    private lateinit var webView: WebView
    private lateinit var errorOverlay: LinearLayout
    private lateinit var errorText: TextView

    private val timeoutHandler = Handler(Looper.getMainLooper())
    private var loadFinished = false
    private var autoLoginStarted = false
    private val healthClient = HealthClient()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_web)

        store = ServerProfileStore(this)
        credentials = CredentialVault(this)
        val profileId = intent.getStringExtra(EXTRA_PROFILE_ID)
        profile = profileId?.let { store.find(it) } ?: run {
            finish()
            return
        }
        supportActionBar?.title = profile.displayName
        supportActionBar?.subtitle = profile.baseUrl

        webView = findViewById(R.id.web_view)
        errorOverlay = findViewById(R.id.error_overlay)
        errorText = findViewById(R.id.error_text)
        findViewById<Button>(R.id.btn_retry).setOnClickListener { load() }

        webView.settings.apply {
            javaScriptEnabled = true          // SPA 前端必需
            domStorageEnabled = true          // localStorage 会话状态
            // 桌面管理页兜底（原生移动 UI 是 Phase 4 交付）：按页面设计视口
            // 布局 + 首屏按屏宽缩放 + 捏合缩放，保证宽表格基本可用
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
            allowFileAccess = false           // 禁本地文件面
            allowContentAccess = false
            cacheMode = WebSettings.LOAD_DEFAULT
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false)
        webView.webViewClient = CompanionWebViewClient()

        onBackPressedDispatcher.addCallback(this, object : androidx.activity.OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })

        // 策略兜底：NSC 构建变体或数据被改动后仍拒绝违规明文地址
        when (val verdict = LanHostPolicy.check(profile.baseUrl, profile.cleartextAllowed)) {
            is LanHostPolicy.Verdict.Reject -> {
                showError(rejectText(verdict))
                return
            }
            is LanHostPolicy.Verdict.Ok -> Unit
        }

        prepareSession {
            refreshVersionHint()
            load()
        }
    }

    override fun onDestroy() {
        timeoutHandler.removeCallbacksAndMessages(null)
        webView.destroy()
        super.onDestroy()
    }

    private fun load() {
        loadFinished = false
        autoLoginStarted = false
        hideError()
        timeoutHandler.postDelayed({
            if (!loadFinished && !isDestroyed) showError(getString(R.string.load_timeout))
        }, LOAD_TIMEOUT_MS)
        webView.loadUrl(profile.baseUrl)
    }

    /** profile 切换即清除凭据：cookie + localStorage 全量清（进程级单例的隔离手段）。 */
    private fun prepareSession(onReady: () -> Unit) {
        if (lastLoadedProfileId == profile.id) {
            onReady()
            return
        }
        val cookieManager = CookieManager.getInstance()
        // removeAllCookies 是异步 API；必须等待回调后再加载新 profile，避免旧 token
        // 与新页面竞态复用。WebStorage 没有回调，调用后再继续即可。
        cookieManager.removeAllCookies {
            runOnUiThread {
                cookieManager.flush()
                WebStorage.getInstance().deleteAllData()
                lastLoadedProfileId = profile.id
                onReady()
            }
        }
    }

    /** 服务端版本提示：后台健康检查，副标题展示 v{version} · 状态。 */
    private fun refreshVersionHint() {
        lifecycleScope.launch {
            val report = healthClient.check(profile.baseUrl, profile.trustedCertFingerprints.toSet())
            profile.healthState = report.state
            profile.serverVersion = report.version ?: profile.serverVersion
            profile.lastHealthCheckedAt = System.currentTimeMillis()
            store.upsert(profile)
            if (!isDestroyed) {
                val version = report.version?.let { "v$it" } ?: "版本未知"
                supportActionBar?.subtitle = "$version · ${report.detail}"
            }
        }
    }

    private fun showError(message: String) {
        errorText.text = message
        errorOverlay.visibility = View.VISIBLE
    }

    private fun hideError() {
        errorOverlay.visibility = View.GONE
    }

    private fun rejectText(verdict: LanHostPolicy.Verdict.Reject): String = when (verdict.reason) {
        LanHostPolicy.Reason.MALFORMED_URL -> "服务器地址无效"
        LanHostPolicy.Reason.SCHEME_NOT_ALLOWED -> "仅支持 http/https 地址"
        LanHostPolicy.Reason.HTTP_PUBLIC_HOST -> "明文 HTTP 仅允许私有局域网地址，公网地址请使用 HTTPS"
        LanHostPolicy.Reason.HTTP_LAN_WITHOUT_CONSENT -> "该服务器未记录明文风险确认，请在服务器列表重新添加"
    }

    // ============ WebViewClient ============

    private inner class CompanionWebViewClient : WebViewClient() {

        override fun onPageFinished(view: WebView?, url: String?) {
            loadFinished = true
            timeoutHandler.removeCallbacksAndMessages(null)
            maybeAutoLogin(view, url)
            if (url != null && isSameOrigin(url)) {
                profile.lastConnectedAt = System.currentTimeMillis()
                store.upsert(profile)
            }
            hideError()
        }

        private fun maybeAutoLogin(view: WebView?, url: String?) {
            if (view == null || url == null || !isSameOrigin(url) || autoLoginStarted) return
            val record = credentials.get(profile.id) ?: return
            if (profile.username.isBlank() || record.password.isEmpty()) return
            val cookie = CookieManager.getInstance().getCookie(profile.baseUrl).orEmpty()
            if (cookie.contains("vue_typescript_admin_access_token=")) return
            autoLoginStarted = true
            view.evaluateJavascript(buildAutoLoginScript(profile.id, profile.username, record.password), null)
        }

        /** 主框架错误 → 覆盖层提示（可重试/返回）。 */
        override fun onReceivedError(
            view: WebView?,
            request: WebResourceRequest?,
            error: WebResourceError?,
        ) {
            if (request?.isForMainFrame == true) {
                loadFinished = true
                timeoutHandler.removeCallbacksAndMessages(null)
                showError("加载失败：${error?.description ?: "未知错误"}")
            }
        }

        /** 站内同源继续加载；外部 http(s) 链接交给系统浏览器；其它 scheme 拦截。 */
        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
            val url = request?.url?.toString() ?: return false
            val scheme = request.url.scheme?.lowercase() ?: return false
            if (scheme != "http" && scheme != "https") return true
            return if (isSameOrigin(url)) false else {
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                true
            }
        }

        /**
         * 自签证书处理（计划红线：禁止无条件 proceed）：
         * 1. 指纹已在 profile 中 → proceed（作用域=本 profile）；
         * 2. 否则弹窗说明风险 → 用户确认后记录指纹再 proceed；拒绝则 cancel。
         */
        override fun onReceivedSslError(
            view: WebView?,
            handler: SslErrorHandler?,
            error: SslError?,
        ) {
            val certificate = error?.certificate
            if (handler == null || certificate == null) {
                handler?.cancel()
                showError("证书错误且无法读取证书信息，已拒绝连接")
                return
            }
            val fingerprint = TrustScope.sha256Fingerprint(certificate)
            if (fingerprint != null && fingerprint in profile.trustedCertFingerprints) {
                handler.proceed()
                return
            }
            val host = Hosts.parse(profile.baseUrl)?.host ?: profile.baseUrl
            AlertDialog.Builder(this@WebViewActivity)
                .setTitle("不受信任的证书")
                .setMessage(
                    "服务器 ${host} 使用自签证书。\n\n" +
                        "指纹（SHA-256）：\n${fingerprint ?: "（无法计算）"}\n\n" +
                        "信任后将记录在本服务器的配置中；证书更换后需重新确认。中间人攻击同样会呈现该提示，请核对指纹来源。"
                )
                .setPositiveButton("信任该证书") { _, _ ->
                    if (fingerprint != null) {
                        profile.trustedCertFingerprints.add(fingerprint)
                        store.upsert(profile)
                        handler.proceed()
                    } else {
                        handler.cancel()
                        showError("无法计算证书指纹，已拒绝连接")
                    }
                }
                .setNegativeButton(android.R.string.cancel) { _, _ -> handler.cancel() }
                .setOnCancelListener { handler.cancel() }
                .show()
        }

        private fun isSameOrigin(url: String): Boolean {
            val target = Hosts.parse(url) ?: return false
            val base = Hosts.parse(profile.baseUrl) ?: return false
            return target.scheme == base.scheme && target.host == base.host && target.port == base.port
        }
    }

    companion object {
        const val EXTRA_PROFILE_ID = "profile_id"
        private const val LOAD_TIMEOUT_MS = 20_000L

        /** 上一个加载的 profile：切换时先异步清 cookie/storage，再加载新会话。 */
        private var lastLoadedProfileId: String? = null
    }
}
