package com.btdeck.companion

import com.btdeck.companion.data.ServerProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerProfileTest {
    @Test
    fun usernameIsProfileMetadata() {
        val profile = ServerProfile(
            displayName = "NAS",
            baseUrl = "http://192.168.1.5:5001",
            username = "alice",
        )
        assertEquals("alice", profile.username)
    }

    @Test
    fun usernameDefaultsToEmptyForLegacyConstructor() {
        val profile = ServerProfile(displayName = "Legacy", baseUrl = "https://example.com")
        assertTrue(profile.username.isEmpty())
    }
}
