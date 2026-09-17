package com.btdeck.companion.ui

import androidx.annotation.ColorRes
import com.btdeck.companion.R
import com.btdeck.companion.data.ServerProfile

/** 健康状态 → 展示文案 + 语义色资源（同前端 emerald 语义色；纯 JVM 可测）。
 *  从 ServerListActivity 抽出：文案被 androidTest Espresso 依赖，色值映射是
 *  品牌化回归保护的落点。 */
object HealthUi {

    fun label(state: ServerProfile.HealthState): String = when (state) {
        ServerProfile.HealthState.UNKNOWN -> "未测试"
        ServerProfile.HealthState.READY -> "就绪"
        ServerProfile.HealthState.NOT_READY -> "未就绪"
        ServerProfile.HealthState.UNREACHABLE -> "不可达"
        ServerProfile.HealthState.TLS_ERROR -> "证书错误"
    }

    @ColorRes
    fun colorRes(state: ServerProfile.HealthState): Int = when (state) {
        ServerProfile.HealthState.UNKNOWN -> R.color.btdeck_text_tertiary
        ServerProfile.HealthState.READY -> R.color.btdeck_success
        ServerProfile.HealthState.NOT_READY -> R.color.btdeck_warning
        ServerProfile.HealthState.UNREACHABLE,
        ServerProfile.HealthState.TLS_ERROR -> R.color.btdeck_error
    }
}
