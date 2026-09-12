package com.btdeck.companion.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** 品牌主题回归（android-native-ui-branding）——直接读源码资源文件做静态断言：
 *  1) colors.xml token 值与前端 emerald 主题（theme-variables.scss）同源；
 *  2) values/themes.xml 与 values-v35/themes.xml 的颜色项保持同步
 *     （v35 整体覆盖同名 style，漏改一项即静默漂移，AndroidManifest 层面无提示）；
 *  3) 主题基底为 Light（前端无暗色主题，DayNight 会让自绘浅色值在系统暗色下断裂）；
 *  4) 对话框走 Material 主题覆盖、colorAccent 兜底（WebViewActivity 存量 appcompat
 *     对话框的绿色按钮依赖它）。
 *
 *  资源文件以文件路径读取（unit test 工作目录=app 模块目录），前端文件按仓库根
 *  相对定位——独立分发的 android 子目录下自动跳过（assume），不阻断构建。 */
class BrandThemeSyncTest {

    // ============ 期望 token：与 frontend/src/styles/theme-variables.scss [data-theme="emerald"] 同源 ============

    private val emeraldTokens = mapOf(
        "btdeck_primary" to "#059669",
        "btdeck_primary_dark" to "#047857",
        "btdeck_primary_deep" to "#065F46",
        "btdeck_primary_light" to "#10B981",
        "btdeck_primary_lightest" to "#D1FAE5",
        "btdeck_success" to "#10B981",
        "btdeck_warning" to "#F59E0B",
        "btdeck_error" to "#EF4444",
        "btdeck_text_primary" to "#1F2937",
        "btdeck_text_secondary" to "#6B7280",
        "btdeck_text_tertiary" to "#9CA3AF",
        "btdeck_bg_secondary" to "#F9FAFB",
        "btdeck_border" to "#E5E7EB",
    )

    // android color 名 → 前端 CSS 变量名（emerald 块）
    private val frontendVariableOf = mapOf(
        "btdeck_primary" to "--color-primary",
        "btdeck_primary_dark" to "--color-primary-hover",
        "btdeck_primary_light" to "--color-primary-light",
        "btdeck_success" to "--color-success",
        "btdeck_warning" to "--color-warning",
        "btdeck_error" to "--color-error",
        "btdeck_text_primary" to "--color-text-primary",
        "btdeck_text_secondary" to "--color-text-secondary",
        "btdeck_text_tertiary" to "--color-text-tertiary",
        "btdeck_bg_secondary" to "--color-bg-secondary",
        "btdeck_border" to "--color-border-primary",
    )

    @Test
    fun colorsXmlKeepsEmeraldTokenValues() {
        val colors = parseColors(resFile("values/colors.xml"))
        emeraldTokens.forEach { (name, hex) ->
            assertEquals("colors.xml token $name 漂移", hex, colors[name])
        }
    }

    @Test
    fun v35ThemeKeepsColorItemsInSyncWithBaseTheme() {
        val base = themeItemNames(resFile("values/themes.xml"))
        val v35 = themeItemNames(resFile("values-v35/themes.xml"))
        val missing = base - v35
        assertTrue(
            "values-v35/themes.xml 缺少基础主题的 item（v35 覆盖式继承，漏项=静默漂移）: $missing",
            missing.isEmpty(),
        )
    }

    @Test
    fun themeIsLightBasedWithMaterialDialogOverlay() {
        val base = resFile("values/themes.xml").readText()
        val parent = Regex("""<style name="Theme\.BtDeckCompanion"\s+parent="([^"]+)"""")
            .find(base)?.groupValues?.get(1)
        assertFalse(
            "主题基底必须保持 Light（前端无暗色主题，DayNight 会与自绘浅色值断裂），实际 parent=$parent",
            parent?.contains("DayNight") ?: true,
        )
        assertEquals(
            "colorPrimary 必须绑定翡翠绿 token",
            "@color/btdeck_primary",
            Regex("""<item name="colorPrimary">([^<]+)</item>""").find(base)?.groupValues?.get(1),
        )
        assertNotNull("必须保留 materialAlertDialogTheme 覆盖", Regex("""<item name="materialAlertDialogTheme">@style/ThemeOverlay\.BtDeck\.MaterialAlertDialog</item>""").find(base))
        assertNotNull("必须保留 colorAccent 兜底（存量 appcompat 对话框按钮色）", Regex("""<item name="colorAccent">@color/btdeck_primary</item>""").find(base))
    }

    @Test
    fun androidTokensMatchFrontendEmeraldTheme() {
        val scss = repoRoot().let { root ->
            if (root == null) null
            else File(root, "frontend/src/styles/theme-variables.scss").takeIf { it.isFile }
        }
        assumeTrue("仓库根不可见（独立分发的 android 子目录），跳过前端同源比对", scss != null)
        val frontend = parseEmeraldBlock(scss!!)
        val android = parseColors(resFile("values/colors.xml"))
        frontendVariableOf.forEach { (androidName, cssVar) ->
            assertEquals(
                "android token $androidName 与前端 $cssVar 失同步",
                frontend[cssVar],
                android[androidName],
            )
        }
    }

    // ============ 解析辅助 ============

    private fun resFile(relative: String): File {
        var dir: File? = File(".").absoluteFile.parentFile // 模块目录（unit test 工作目录=app 模块）
        repeat(6) {
            if (dir == null) return@repeat
            val candidate = File(dir, "src/main/res/$relative")
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        throw IllegalStateException("未找到 src/main/res/$relative（工作目录=${File(".").absolutePath}）")
    }

    private fun repoRoot(): File? {
        var dir: File? = File(".").absoluteFile.parentFile
        repeat(8) {
            if (dir == null) return@repeat
            if (File(dir, "android").isDirectory && File(dir, "frontend").isDirectory) return dir
            dir = dir.parentFile
        }
        return null
    }

    private fun parseColors(file: File): Map<String, String> =
        Regex("""<color name="([^"]+)">\s*(#[0-9A-Fa-f]{6,8})\s*</color>""")
            .findAll(file.readText())
            .associate { it.groupValues[1] to it.groupValues[2].uppercase() }

    /** 提取 Theme.BtDeckCompanion 样式块的 item name 集合（含 android: 前缀属性名）。 */
    private fun themeItemNames(file: File): Set<String> {
        val text = file.readText()
        val start = text.indexOf("<style name=\"Theme.BtDeckCompanion\"")
        assertTrue("${file.path} 缺少 Theme.BtDeckCompanion", start >= 0)
        val end = text.indexOf("</style>", start)
        val block = text.substring(start, end)
        return Regex("""<item name="([^"]+)">""").findAll(block).map { it.groupValues[1] }.toSet()
    }

    /** 提取前端 emerald 主题块的 CSS 变量（#hex 值统一大写）。 */
    private fun parseEmeraldBlock(scss: File): Map<String, String> {
        val text = scss.readText()
        val start = text.indexOf("[data-theme=\"emerald\"]")
        assertTrue("theme-variables.scss 缺少 emerald 块", start >= 0)
        val end = text.indexOf("[data-theme=\"orange\"]", start).let { if (it < 0) text.length else it }
        return Regex("""(--color-[a-z-]+):\s*(#[0-9A-Fa-f]{6,8})\s*;""")
            .findAll(text.substring(start, end))
            .associate { it.groupValues[1] to it.groupValues[2].uppercase() }
    }
}
