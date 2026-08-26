# -*- coding: utf-8 -*-

import os

import pytest

from app.desktop_companion.credentials import (
    CredentialRecord,
    MemoryCredentialVault,
    WindowsCredentialVault,
    build_auto_login_script,
)


def test_memory_vault_roundtrip_and_delete():
    vault = MemoryCredentialVault()
    record = CredentialRecord("alice", "secret")
    vault.put("profile-1", record)
    assert vault.get("profile-1") == record
    assert vault.has("profile-1") is True
    vault.delete("profile-1")
    assert vault.get("profile-1") is None
    assert vault.has("profile-1") is False


def test_auto_login_script_uses_profile_slot_and_totp_prompt():
    script = build_auto_login_script("profile-1", "alice", "secret")
    assert "btdeck_companion_profile_id" in script
    assert "/api/v1/auth/login" in script
    assert "window.prompt" in script
    assert "addJavascriptInterface" not in script


@pytest.mark.skipif(os.name != "nt", reason="DPAPI 仅在 Windows 可用")
def test_windows_dpapi_vault_does_not_write_plaintext(tmp_path):
    vault = WindowsCredentialVault(tmp_path)
    vault.put("profile-1", CredentialRecord("alice", "secret"))
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert b"secret" not in files[0].read_bytes()
    assert vault.get("profile-1") == CredentialRecord("alice", "secret")
    vault.delete("profile-1")
    assert vault.get("profile-1") is None
