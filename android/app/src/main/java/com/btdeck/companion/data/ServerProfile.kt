package com.btdeck.companion.data

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * 服务器 profile 模型（计划 Phase 2）。
 *
 * 持久化由 [ServerProfileStore] 以 JSON 编码写入 SharedPreferences；
 * 序列化实现放在伴生对象，模型本体保持可变字段——列表页健康检查、
 * WebView 版本提示、自签证书信任追加都直接改写后 upsert 回存。
 */
data class ServerProfile(
    val id: String = UUID.randomUUID().toString(),
    var displayName: String,
    var baseUrl: String,
    /** 用户已为该地址显式确认明文风险（仅私有 LAN 主机可生效，见 LanHostPolicy）。 */
    var cleartextAllowed: Boolean = false,
    var healthState: HealthState = HealthState.UNKNOWN,
    /** /health/ready 返回的服务端版本（如 "1.0.5"），未探测到为 null。 */
    var serverVersion: String? = null,
    var lastHealthCheckedAt: Long = 0L,
    var lastConnectedAt: Long = 0L,
    /** 用户已确认信任的自签证书 SHA-256 指纹（作用域 = 本 profile）。 */
    val trustedCertFingerprints: MutableSet<String> = linkedSetOf(),
) {

    enum class HealthState {
        UNKNOWN,
        READY,
        NOT_READY,
        UNREACHABLE,
        TLS_ERROR,
    }

    fun toJson(): JSONObject = JSONObject().apply {
        put(KEY_ID, id)
        put(KEY_DISPLAY_NAME, displayName)
        put(KEY_BASE_URL, baseUrl)
        put(KEY_CLEARTEXT_ALLOWED, cleartextAllowed)
        put(KEY_HEALTH_STATE, healthState.name)
        put(KEY_SERVER_VERSION, serverVersion ?: JSONObject.NULL)
        put(KEY_LAST_HEALTH_CHECKED_AT, lastHealthCheckedAt)
        put(KEY_LAST_CONNECTED_AT, lastConnectedAt)
        put(KEY_TRUSTED_FINGERPRINTS, JSONArray(trustedCertFingerprints))
    }

    companion object {
        private const val KEY_ID = "id"
        private const val KEY_DISPLAY_NAME = "displayName"
        private const val KEY_BASE_URL = "baseUrl"
        private const val KEY_CLEARTEXT_ALLOWED = "cleartextAllowed"
        private const val KEY_HEALTH_STATE = "healthState"
        private const val KEY_SERVER_VERSION = "serverVersion"
        private const val KEY_LAST_HEALTH_CHECKED_AT = "lastHealthCheckedAt"
        private const val KEY_LAST_CONNECTED_AT = "lastConnectedAt"
        private const val KEY_TRUSTED_FINGERPRINTS = "trustedCertFingerprints"

        /** 未知枚举名回退 UNKNOWN：向前兼容旧数据被新版本状态值污染的场景。 */
        fun fromJson(json: JSONObject): ServerProfile = ServerProfile(
            id = json.optString(KEY_ID, UUID.randomUUID().toString()),
            displayName = json.optString(KEY_DISPLAY_NAME, ""),
            baseUrl = json.optString(KEY_BASE_URL, ""),
            cleartextAllowed = json.optBoolean(KEY_CLEARTEXT_ALLOWED, false),
            healthState = json.optString(KEY_HEALTH_STATE)
                .let { name -> HealthState.entries.firstOrNull { it.name == name } } ?: HealthState.UNKNOWN,
            serverVersion = if (json.isNull(KEY_SERVER_VERSION)) null else json.optString(KEY_SERVER_VERSION),
            lastHealthCheckedAt = json.optLong(KEY_LAST_HEALTH_CHECKED_AT, 0L),
            lastConnectedAt = json.optLong(KEY_LAST_CONNECTED_AT, 0L),
            trustedCertFingerprints = json.optJSONArray(KEY_TRUSTED_FINGERPRINTS)
                ?.let { array -> (0 until array.length()).mapTo(linkedSetOf()) { array.optString(it) } }
                ?: linkedSetOf(),
        )
    }
}
