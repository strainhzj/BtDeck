package com.btdeck.companion.server

import com.btdeck.companion.data.ServerProfile

/**
 * 本机服务端 profile（纯 JVM 逻辑，供单元测试）。
 *
 * 固定 id 复用 WebViewActivity 全链路（健康提示/会话隔离/自动登录）；
 * baseUrl 随动态端口在服务就绪后刷新。cleartextAllowed 恒 true——
 * 127.0.0.1 是回环私有字面量且 NSC 只对 loopback 放行明文
 * （LanHostPolicy 已对回环豁免确认记录，此字段仅为旧数据兼容保留 true）。
 */
object LocalServerProfile {

    const val PROFILE_ID = "local-server"
    const val DISPLAY_NAME = "本机服务端"

    fun baseUrl(port: Int): String = "http://127.0.0.1:$port"

    /**
     * 服务就绪后写入 profile store 的形态；复用既有 profile 保留用户名与
     * 健康历史（url 变化不影响凭据——同源回环，id 不变）。
     */
    fun buildProfile(port: Int, existing: ServerProfile?): ServerProfile {
        val profile = existing ?: ServerProfile(
            id = PROFILE_ID,
            displayName = DISPLAY_NAME,
            baseUrl = baseUrl(port),
            cleartextAllowed = true,
        )
        profile.displayName = DISPLAY_NAME
        profile.baseUrl = baseUrl(port)
        profile.cleartextAllowed = true
        return profile
    }

    /** 是否本机服务端 profile。 */
    fun isLocal(profile: ServerProfile): Boolean = profile.id == PROFILE_ID
}

/** 服务端口与 LAN 偏好的持久化接口（ServerService 用 SharedPreferences 实现）。 */
interface ServerPrefs {
    /** 上次成功端口：下次启动优先复用（LAN 场景其它设备免追端口）。 */
    var lastPort: Int
    /** LAN 开关（默认关；打开前 UI 必须展示威胁模型）。 */
    var lanEnabled: Boolean
}
