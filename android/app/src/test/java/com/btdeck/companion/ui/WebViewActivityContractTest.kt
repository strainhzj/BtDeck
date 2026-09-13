package com.btdeck.companion.ui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * WebView 文件选择器接线契约（mobile-ux-pending-fixes 回归保护）：
 * 真机验证通过的行为无法在 JVM 端到端复现（Intent/ClipData 实例化是
 * not-mocked stub、仓内无 Robolectric），沿用前端仓「源码契约」模式直读
 * 实现文件钉死关键结构——变异数字对应的都是真机踩过的坑：
 * - webChromeClient 缺失 → `<input type="file">` 点击被静默忽略（首验根因）；
 * - 回调漏投/双投 → WebView 永久拒绝后续选择器（锁死）；
 * - createIntent 的 acceptTypes 处理 → ".torrent" 被 SAF 当 MIME 过滤空列表；
 * - versionCode 不递增 → 真机装没装上新包无法分辨（复验批根因）。
 */
class WebViewActivityContractTest {

    private fun source(relative: String): String {
        val file = File("src/main/java/com/btdeck/companion/$relative")
        assumeTrue("源文件不可见（非模块工作目录）：$file", file.isFile)
        return file.readText()
    }

    @Test
    fun webChromeClientIsWiredWithFileChooser() {
        val s = source("ui/WebViewActivity.kt")
        assertTrue("webChromeClient 必须挂载（缺它文件选择点击被静默忽略）", s.contains("webChromeClient ="))
        assertTrue(s.contains("override fun onShowFileChooser"))
        // 结果通道走 ActivityResultLauncher（onCreate 前注册的属性初始化器）
        assertTrue(s.contains("ActivityResultContracts.StartActivityForResult"))
        assertTrue(s.contains("fileChooserLauncher.launch"))
    }

    @Test
    fun callbackDeliveredExactlyOnceOnAllFourPaths() {
        val s = source("ui/WebViewActivity.kt")
        // launcher 回调：取出即清空（同一次结果不会二次投递）
        assertTrue(
            "launcher 回调必须先取引用再清空再投递",
            Regex("val callback = pendingFileChooser\\s*\\n\\s*pendingFileChooser = null\\s*\\n\\s*callback\\?\\.onReceiveValue")
                .containsMatchIn(s),
        )
        // 「恰好一次」的四条路径都以 onReceiveValue(null) 收尾：新请求作废旧
        // 回调 / onDestroy 补投 / ActivityNotFoundException / SecurityException
        val deliverNull = Regex("onReceiveValue\\(null\\)").findAll(s).count()
        assertTrue("onReceiveValue(null) 应恰 4 处（四条取消/失败路径），实际 $deliverNull", deliverNull == 4)
    }

    @Test
    fun userAgentInjectsCompanionMarkerForAppOnlyMobileUi() {
        val s = source("ui/WebViewActivity.kt")
        // UA 标记是前端「App WebView 恒移动端」的判定输入（ui-mode 的
        // isCompanionAppWebView / wide-viewport mixin 据此压制桌面版出口
        // 与 desktop 偏好）；丢了它平板/横屏 ≥768px 会重新渲染桌面版出口
        assertTrue(
            "WebView UA 必须追加 BtDeckCompanion 标记（前端据此恒移动端）",
            s.contains("userAgentString = \"\$userAgentString BtDeckCompanion\""),
        )
    }

    @Test
    fun pickerIntentAvoidsMimeTrapAndKeepsMultiple() {
        val s = source("ui/FileChooser.kt")
        // 禁回退 createIntent（acceptTypes 原样当 MIME → SAF 空列表）
        assertFalse(
            "禁止调用 FileChooserParams.createIntent（MIME 陷阱）",
            Regex("\\.createIntent\\(").containsMatchIn(s),
        )
        assertTrue("多选须补 EXTRA_ALLOW_MULTIPLE", s.contains("Intent.EXTRA_ALLOW_MULTIPLE"))
        // 类型只走决策值（不透传页面 acceptTypes）
        assertTrue(s.contains("type = params.mimeType"))
    }

    /**
     * 返回来源页双入口接线契约（2026-09-13 真机反馈）：
     * WebView 内此前无主动返回（系统返回键被 WebView 历史优先占用），
     * 用户困在仪表盘回不到模式/服务器选择页。变体对应真机踩过的坑：
     * - 丢 setDisplayHomeAsUpEnabled → 左上角无返回箭头；
     * - onSupportNavigateUp 走 super → 默认落到 onBackPressed，先被
     *   WebView 历史（SPA 路由）耗掉，箭头点了只翻页不退出；
     * - 副标题仍写 supportActionBar?.subtitle → 原生 subtitle 已随
     *   setDisplayShowTitleEnabled(false) 隐藏，健康提示静默不可见。
     */
    @Test
    fun actionBarExposesTwoReturnEntriesToSourcePages() {
        val s = source("ui/WebViewActivity.kt")
        assertTrue(
            "action bar 必须开启 home-as-up 返回箭头",
            s.contains("setDisplayHomeAsUpEnabled(true)"),
        )
        assertTrue(
            "onSupportNavigateUp 必须直接 exitToSourcePage 且不调 super（super 默认走 onBackPressed 先耗 WebView 历史）",
            Regex("override fun onSupportNavigateUp\\(\\):\\s*Boolean\\s*\\{\\s*exitToSourcePage\\(\\)\\s*return true\\s*\\}")
                .containsMatchIn(s),
        )
        // 原生 title 无点击 API：名称须由 custom view 承载并整体可点
        assertTrue(
            "标题区必须以 action_bar_web_title custom view 承载（名称可点）",
            s.contains("R.layout.action_bar_web_title"),
        )
        assertTrue(
            "custom view 根节点必须挂点击监听走 exitToSourcePage",
            Regex("setOnClickListener\\s*\\{\\s*exitToSourcePage\\(\\)\\s*\\}").containsMatchIn(s),
        )
        assertFalse(
            "副标题更新必须写 custom view TextView；supportActionBar?.subtitle 已隐藏不可见",
            s.contains("supportActionBar?.subtitle"),
        )
    }

    /** 自定义标题布局契约：根节点可点（clickable+focusable）且两行文本 ID 齐。 */
    @Test
    fun actionBarTitleLayoutIsClickableContainer() {
        val layout = File("src/main/res/layout/action_bar_web_title.xml")
        assumeTrue("布局文件不可见（非模块工作目录）：$layout", layout.isFile)
        val text = layout.readText()
        assertTrue(
            "标题区根节点必须 clickable+focusable（整体点击返回）",
            text.contains("android:clickable=\"true\"") && text.contains("android:focusable=\"true\""),
        )
        assertTrue("标题行 ID 缺失", text.contains("@+id/action_bar_title"))
        assertTrue("副标题行 ID 缺失", text.contains("@+id/action_bar_subtitle"))
        // 名称与地址须可读：显式 colorOnPrimary（custom view 不保证继承覆盖层标题色）
        assertTrue("标题文本必须显式 colorOnPrimary", text.contains("android:textColor=\"?attr/colorOnPrimary\""))
    }

    /** APK 交付版本纪律锚点：发版递增 versionCode 并同步 bat 产物名（发版时抬升）。 */
    @Test
    fun apkVersionKeepsAscendingAndAligned() {
        val gradle = File("build.gradle.kts").takeIf { it.isFile }
        assumeTrue("build.gradle.kts 不可见（非模块工作目录），跳过", gradle != null)
        val text = gradle!!.readText()
        val codeMatch = Regex("versionCode = (\\d+)").find(text)
            ?: error("versionCode 未找到")
        val code = codeMatch.groupValues[1].toInt()
        // 3 是文件选择器批次的锚点值：曾因新旧包同为 2，真机验收无法分辨装没装新包
        assertTrue("versionCode 应 ≥3 且每次 APK 交付递增（锚点随发版抬升）", code >= 3)
        val nameMatch = Regex("else \"(\\d+\\.\\d+\\.\\d+)-server\"").find(text)
            ?: error("versionName 未找到")
        val name = nameMatch.groupValues[1]
        val bat = repoBat()
        assumeTrue("deploy bat 不可见（独立分发的 android 子目录），跳过产物名比对", bat != null)
        // bat 产物名版本与包内 versionName 曾脱钩（0.1.0-mvp vs 0.2.0-server）
        assertTrue(
            "bat BTDECK_APK_VERSION 应与 versionName 同源（$name）",
            bat!!.readText().contains("BTDECK_APK_VERSION=$name\""),
        )
    }

    /** 从模块目录向上找仓库根的 deploy/build-android.bat（CI 工作目录差异兜底）。 */
    private fun repoBat(): File? {
        var dir: File? = File(".").absoluteFile.parentFile
        while (dir != null) {
            val candidate = File(dir, "deploy/build-android.bat")
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        return null
    }
}
