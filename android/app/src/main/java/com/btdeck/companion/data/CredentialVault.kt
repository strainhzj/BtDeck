package com.btdeck.companion.data

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties

/**
 * 每个 profile 一条凭据记录，密码使用 Android Keystore 生成的 AES-GCM 密钥加密后
 * 才写入 SharedPreferences。profile JSON 只保留 username，不保存 password。
 */
data class CredentialRecord(val username: String, val password: String)

class CredentialVault(context: Context) {

    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun get(profileId: String): CredentialRecord? {
        val encoded = prefs.getString(profileId, null) ?: return null
        return runCatching {
            val packed = Base64.decode(encoded, Base64.NO_WRAP)
            require(packed.size > IV_LENGTH)
            val iv = packed.copyOfRange(0, IV_LENGTH)
            val encrypted = packed.copyOfRange(IV_LENGTH, packed.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(TAG_BITS, iv))
            val json = JSONObject(String(cipher.doFinal(encrypted), StandardCharsets.UTF_8))
            val username = json.optString(KEY_USERNAME, "")
            val password = json.optString(KEY_PASSWORD, "")
            CredentialRecord(username, password)
        }.getOrNull()
    }

    fun save(profileId: String, record: CredentialRecord) {
        require(record.username.isNotBlank() || record.password.isBlank()) {
            "填写密码时必须输入用户名"
        }
        val json = JSONObject()
            .put(KEY_USERNAME, record.username)
            .put(KEY_PASSWORD, record.password)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(json.toString().toByteArray(StandardCharsets.UTF_8))
        val packed = cipher.iv + encrypted
        prefs.edit().putString(profileId, Base64.encodeToString(packed, Base64.NO_WRAP)).apply()
    }

    fun delete(profileId: String) {
        prefs.edit().remove(profileId).apply()
    }

    fun hasPassword(profileId: String): Boolean {
        val record = get(profileId)
        return record != null && record.username.isNotBlank() && record.password.isNotEmpty()
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setUserAuthenticationRequired(false)
                .build(),
        )
        return generator.generateKey()
    }

    companion object {
        private const val PREFS_NAME = "btdeck_companion_credentials"
        private const val KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "btdeck_companion_credentials_v1"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val TAG_BITS = 128
        private const val IV_LENGTH = 12
        private const val KEY_USERNAME = "username"
        private const val KEY_PASSWORD = "password"
    }
}

/** 同源一次性登录，不创建暴露密码的 addJavascriptInterface。 */
fun buildAutoLoginScript(profileId: String, username: String, password: String): String {
    val profile = JSONObject.quote(profileId)
    val user = JSONObject.quote(username)
    val secret = JSONObject.quote(password)
    return """
        (function() {
          if (window.__btdeckAutoLoginRunning) return;
          window.__btdeckAutoLoginRunning = true;
          var profileId = $profile;
          var username = $user;
          var password = $secret;
          var accessKey = 'vue_typescript_admin_access_token';
          var refreshKey = 'vue_typescript_admin_refresh_token';
          function hasAccess() { return document.cookie.split(';').some(function(v) { return v.trim().indexOf(accessKey + '=') === 0; }); }
          function clearCookie(name) { document.cookie = name + '=; Max-Age=0; path=/'; }
          function setCookie(name, value) { document.cookie = name + '=' + encodeURIComponent(value) + '; Max-Age=604800; path=/'; }
          try {
            var slot = 'btdeck_companion_profile_id';
            if (localStorage.getItem(slot) !== profileId) {
              localStorage.clear(); clearCookie(accessKey); clearCookie(refreshKey); localStorage.setItem(slot, profileId);
            }
          } catch (_) {}
          if (hasAccess()) return;
          function login(twofa) {
            var body = {username: username, password: password};
            if (twofa) body.twofa_code = twofa;
            return fetch(new URL('/api/v1/auth/login', window.location.origin).toString(), {
              method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
            }).then(function(r) { return r.json(); }).then(function(payload) {
              var message = String(payload && payload.msg || '');
              if (payload && payload.code === '400' && message.indexOf('验证码') >= 0) {
                var code = window.prompt('请输入两步验证码');
                return code ? login(code) : null;
              }
              if (!payload || payload.code !== '200' || !payload.data || !payload.data[0]) return null;
              var token = payload.data[0];
              if (!token.access_token) return null;
              setCookie(accessKey, token.access_token);
              if (token.refresh_token) setCookie(refreshKey, token.refresh_token);
              window.location.reload();
              return true;
            }).catch(function() { return null; });
          }
          login(null);
        })();
    """.trimIndent()
}
