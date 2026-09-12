package com.btdeck.companion.ui

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.webkit.WebChromeClient.FileChooserParams

/**
 * WebView 文件选择器（`<input type="file">`，添加种子 .torrent 入口）：
 * 意图构造参数决策与结果解析的纯逻辑单元，Activity 侧保持薄装配。
 *
 * - 不用 [FileChooserParams.createIntent]：它把 acceptTypes 原样塞进
 *   `setType`——前端 `accept=".torrent"` 的扩展名会被 SAF 当 MIME 过滤，
 *   选择器空列表（".torrent" 不是合法 MIME）。统一 ACTION_GET_CONTENT +
 *   `*&#47;*`（MimeTypeMap 也不认识 .torrent 扩展名，application/x-bittorrent
 *   同样会过滤成空），扩展名校验由前端 TorrentAddDialog 完成；
 * - [parseResult] 规则与 `FileChooserParams.parseResult` 同口径，但独立
 *   实现：android.webkit 在 JVM 单测是 not-mocked stub（仓内 HealthClient
 *   同因手写 base64）。取消必须收敛为 null——空数组与双重投递都会让
 *   WebView 永久拒绝后续 onShowFileChooser；
 * - [urisFromIntent] 与 [buildPickerIntent] 的 Intent/ClipData 状态存取
 *   同样无法 JVM 化（无 Robolectric），方法体保持无分支直译，行为由
 *   设备级验收兜底。
 */
object FileChooser {

    /** SAF MIME 陷阱对策：恒放宽为 `*&#47;*`，见类注释。 */
    const val PICKER_MIME_TYPE = "*/*"

    /** 选择器意图参数（纯数据，JVM 可测）：装配见 [buildPickerIntent]。 */
    data class PickerParams(
        val mimeType: String,
        /** 多选须显式补 EXTRA_ALLOW_MULTIPLE（ACTION_GET_CONTENT 默认单选）。 */
        val allowMultiple: Boolean,
    )

    /** 由 WebView 的 openMode 决策选择器参数（mode 是 compile-time 常量）。 */
    fun pickerParams(mode: Int): PickerParams =
        PickerParams(PICKER_MIME_TYPE, mode == FileChooserParams.MODE_OPEN_MULTIPLE)

    /** 装配 ACTION_GET_CONTENT 意图（CATEGORY_OPENABLE 与 createIntent 同内核）。 */
    fun buildPickerIntent(params: PickerParams): Intent =
        Intent(Intent.ACTION_GET_CONTENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = params.mimeType
            if (params.allowMultiple) putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        }

    /**
     * 提取选择结果：MULTIPLE 时 clipData 展开（去 null item），否则单 data；
     * 取消/无选中返回空列表。Intent 存取无分支直译，由调用方传给 [parseResult]。
     */
    fun urisFromIntent(data: Intent?): List<Uri> {
        if (data == null) return emptyList()
        val clip = data.clipData ?: return listOfNotNull(data.data)
        return (0 until clip.itemCount).mapNotNull { clip.getItemAt(it)?.uri }
    }

    /** RESULT_OK 且至少一个 uri → 数组透传；否则 null（取消/清空语义）。 */
    fun parseResult(resultCode: Int, uris: List<Uri>): Array<Uri>? =
        if (isSelectionComplete(resultCode, uris.size)) uris.toTypedArray() else null

    /** 选择有效性决策（纯，JVM 可测；RESULT_OK=-1/RESULT_CANCELED=0）。 */
    internal fun isSelectionComplete(resultCode: Int, uriCount: Int): Boolean =
        resultCode == Activity.RESULT_OK && uriCount > 0
}
