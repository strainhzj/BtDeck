package com.btdeck.companion.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * 服务器 profile 持久化（计划 Phase 2）：SharedPreferences 单键存 JSON 数组。
 *
 * - manifest 已 allowBackup=false，本存储不进入系统备份/云迁移；
 * - 删除 profile 即连同其信任的证书指纹一起消失（指纹只存在 profile 内）；
 * - loadAll 按 displayName 字典序输出，列表展示顺序稳定。
 */
class ServerProfileStore(context: Context) {

    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun loadAll(): List<ServerProfile> {
        val raw = prefs.getString(KEY_PROFILES, null) ?: return emptyList()
        val array = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        return (0 until array.length())
            .mapNotNull { i ->
                runCatching { ServerProfile.fromJson(array.optJSONObject(i) ?: return@mapNotNull null) }
                    .getOrNull()
            }
            .sortedBy { it.displayName }
    }

    fun find(id: String): ServerProfile? = loadAll().firstOrNull { it.id == id }

    fun upsert(profile: ServerProfile) {
        val current = loadAll().filterNot { it.id == profile.id } + profile
        persist(current)
    }

    fun delete(id: String) {
        persist(loadAll().filterNot { it.id == id })
    }

    private fun persist(profiles: List<ServerProfile>) {
        val array = JSONArray()
        profiles.forEach { array.put(it.toJson()) }
        prefs.edit().putString(KEY_PROFILES, array.toString()).apply()
    }

    companion object {
        private const val PREFS_NAME = "btdeck_companion"
        private const val KEY_PROFILES = "server_profiles"
    }
}
