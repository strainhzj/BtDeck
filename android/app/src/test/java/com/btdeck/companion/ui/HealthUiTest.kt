package com.btdeck.companion.ui

import com.btdeck.companion.R
import com.btdeck.companion.data.ServerProfile
import org.junit.Assert.assertEquals
import org.junit.Test

/** 健康状态文案/语义色映射回归（android-native-ui-branding）：
 *  - 文案被 androidTest Espresso 直接依赖（未测试/就绪/未就绪/不可达/证书错误）；
 *  - 语义色对应前端 emerald 语义（success/warning/error），防误换/误删 token。 */
class HealthUiTest {

    @Test
    fun labelsCoverAllStates() {
        assertEquals("未测试", HealthUi.label(ServerProfile.HealthState.UNKNOWN))
        assertEquals("就绪", HealthUi.label(ServerProfile.HealthState.READY))
        assertEquals("未就绪", HealthUi.label(ServerProfile.HealthState.NOT_READY))
        assertEquals("不可达", HealthUi.label(ServerProfile.HealthState.UNREACHABLE))
        assertEquals("证书错误", HealthUi.label(ServerProfile.HealthState.TLS_ERROR))
    }

    @Test
    fun colorsFollowEmeraldSemantics() {
        assertEquals(R.color.btdeck_text_tertiary, HealthUi.colorRes(ServerProfile.HealthState.UNKNOWN))
        assertEquals(R.color.btdeck_success, HealthUi.colorRes(ServerProfile.HealthState.READY))
        assertEquals(R.color.btdeck_warning, HealthUi.colorRes(ServerProfile.HealthState.NOT_READY))
        assertEquals(R.color.btdeck_error, HealthUi.colorRes(ServerProfile.HealthState.UNREACHABLE))
        assertEquals(R.color.btdeck_error, HealthUi.colorRes(ServerProfile.HealthState.TLS_ERROR))
    }

    @Test
    fun fourSemanticGroupsAreDistinct() {
        val distinct = ServerProfile.HealthState.values()
            .map(HealthUi::colorRes)
            .toSet()
        // 灰/绿/橙/红 四组互不相同（UNREACHABLE 与 TLS_ERROR 同为 error）
        assertEquals(4, distinct.size)
    }
}
