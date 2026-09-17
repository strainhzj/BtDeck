package com.btdeck.companion.ui

import android.webkit.WebChromeClient.FileChooserParams
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 文件选择器纯逻辑回归（App 添加种子的 .torrent 入口，mobile-file-chooser）：
 * - MIME 陷阱钉死：选择器恒 `*&#47;*`——禁止回退 FileChooserParams.createIntent
 *   的「扩展名当 MIME」（accept=".torrent" → SAF 过滤空列表）；
 * - 多选决策：MODE_OPEN_MULTIPLE → EXTRA_ALLOW_MULTIPLE（装配层直译）；
 * - 取消语义：非 RESULT_OK 或零 uri 必须判无效（null），空数组/不投递都会
 *   让 WebView 永久锁死后续选择。
 * Intent/ClipData 状态存取在 JVM 下是 not-mocked stub（仓内无 Robolectric），
 * buildPickerIntent/urisFromIntent 装配行为由真机验收兜底。
 */
class FileChooserTest {

    @Test
    fun pickerMimeIsWildcardNotTorrentExtension() {
        // ".torrent" 不是合法 MIME，SAF 按它过滤必空列表
        assertEquals("*/*", FileChooser.PICKER_MIME_TYPE)
    }

    @Test
    fun multipleModeOptsIntoAllowMultiple() {
        val multiple = FileChooser.pickerParams(FileChooserParams.MODE_OPEN_MULTIPLE)
        assertTrue(multiple.allowMultiple)
        assertEquals("*/*", multiple.mimeType)

        val single = FileChooser.pickerParams(FileChooserParams.MODE_OPEN)
        assertFalse(single.allowMultiple)
        assertEquals("*/*", single.mimeType)
    }

    @Test
    fun selectionCompleteRequiresOkAndNonEmpty() {
        // Activity.RESULT_OK = -1 / RESULT_CANCELED = 0（compile-time 常量内联值）
        assertTrue(FileChooser.isSelectionComplete(-1, 1))   // 单选确认
        assertTrue(FileChooser.isSelectionComplete(-1, 3))   // 多选透传
        assertFalse(FileChooser.isSelectionComplete(-1, 0))  // OK 但零选中（全清后确认）
        assertFalse(FileChooser.isSelectionComplete(0, 1))   // 取消：即使带数据也判无效
        assertFalse(FileChooser.isSelectionComplete(0, 0))
    }

    @Test
    fun onlyMultipleModeOptsIn() {
        // 多选是显式 opt-in：打开/保存/未知 mode 一律单选（EXTRA_ALLOW_MULTIPLE
        // 误开会改变选择器交互形态）
        assertFalse(FileChooser.pickerParams(FileChooserParams.MODE_OPEN).allowMultiple)
        assertFalse(FileChooser.pickerParams(FileChooserParams.MODE_SAVE).allowMultiple)
        assertFalse(FileChooser.pickerParams(-1).allowMultiple)
        assertFalse(FileChooser.pickerParams(Int.MAX_VALUE).allowMultiple)
    }
}
