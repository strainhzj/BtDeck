package com.btdeck.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.btdeck.companion.data.CredentialRecord
import com.btdeck.companion.data.CredentialVault
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 凭据保险库设备级验证（dual-mode-client task .8）：
 * Android Keystore AES-GCM 真实加解密往返、密文落盘（无明文）、
 * 覆盖保存（改密语义）、删除、hasPassword、用户名约束。
 * AVD 实测 = Keystore 硬件级路径（JVM 单测不可替代）。
 */
@RunWith(AndroidJUnit4::class)
class CredentialVaultAndroidTest {

    private fun vault(): CredentialVault {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        return CredentialVault(context)
    }

    @Test
    fun saveGetRoundTrip() {
        val vault = vault()
        val id = "cred_test_roundtrip"
        vault.delete(id)
        vault.save(id, CredentialRecord("admin", "S3cret密码!"))
        val loaded = vault.get(id)
        assertNotNull(loaded)
        assertEquals("admin", loaded!!.username)
        assertEquals("S3cret密码!", loaded.password)
        vault.delete(id)
    }

    @Test
    fun storedValueIsCiphertextNotPlaintext() {
        val vault = vault()
        val id = "cred_test_cipher"
        vault.delete(id)
        vault.save(id, CredentialRecord("admin", "PLAINTEXT_MARKER_9f8e"))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val raw = context
            .getSharedPreferences("btdeck_companion_credentials", android.content.Context.MODE_PRIVATE)
            .getString(id, null)
        assertNotNull(raw)
        assertFalse("凭据明文泄漏到 SharedPreferences", raw!!.contains("PLAINTEXT_MARKER_9f8e"))
        assertTrue("密文应为 Base64 形态", raw.length > 40)
        vault.delete(id)
    }

    @Test
    fun overwriteSaveReplacesPassword() {
        val vault = vault()
        val id = "cred_test_overwrite"
        vault.delete(id)
        vault.save(id, CredentialRecord("admin", "old-pass"))
        vault.save(id, CredentialRecord("admin", "new-pass"))
        assertEquals("new-pass", vault.get(id)!!.password)
        vault.delete(id)
    }

    @Test
    fun deleteRemovesRecord() {
        val vault = vault()
        val id = "cred_test_delete"
        vault.save(id, CredentialRecord("admin", "x"))
        vault.delete(id)
        assertNull(vault.get(id))
        assertFalse(vault.hasPassword(id))
    }

    @Test
    fun hasPasswordSemantics() {
        val vault = vault()
        val id = "cred_test_haspw"
        vault.delete(id)
        assertFalse(vault.hasPassword(id))
        vault.save(id, CredentialRecord("admin", "pw"))
        assertTrue(vault.hasPassword(id))
        vault.delete(id)
    }

    @Test
    fun passwordRequiresUsername() {
        val vault = vault()
        val id = "cred_test_require"
        vault.delete(id)
        var rejected = false
        try {
            vault.save(id, CredentialRecord("", "pw"))
        } catch (expected: IllegalArgumentException) {
            rejected = true
        }
        assertTrue(rejected)
        assertNull(vault.get(id))
        vault.delete(id)
    }
}
