# -*- coding: utf-8 -*-
"""伴侣模式凭据保险库。

profile 文件只保存可展示的账号名，不保存密码或 token。Windows 桌面端使用
当前用户 DPAPI 加密凭据文件；测试和非 Windows 开发环境可以显式注入内存保险库。
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CredentialRecord:
    """与一个 profile 绑定的登录信息。

    access/refresh token 预留给后续会话续期；当前实现只持久化账号和密码，
    token 仍由远端前端 cookie 管理，避免把短期 token 写入 profile 文件。
    """

    username: str
    password: str


class CredentialVault(Protocol):
    def get(self, profile_id: str) -> CredentialRecord | None: ...

    def put(self, profile_id: str, record: CredentialRecord) -> None: ...

    def delete(self, profile_id: str) -> None: ...

    def has(self, profile_id: str) -> bool: ...


class MemoryCredentialVault:
    """测试用保险库；不会写磁盘。"""

    def __init__(self) -> None:
        self._records: dict[str, CredentialRecord] = {}

    def get(self, profile_id: str) -> CredentialRecord | None:
        return self._records.get(profile_id)

    def put(self, profile_id: str, record: CredentialRecord) -> None:
        self._records[profile_id] = record

    def delete(self, profile_id: str) -> None:
        self._records.pop(profile_id, None)

    def has(self, profile_id: str) -> bool:
        record = self.get(profile_id)
        return bool(record and record.username and record.password)


if os.name == "nt":

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class WindowsCredentialVault:
    """使用 Windows 当前用户 DPAPI 保存 profile 凭据。

    DPAPI 密文文件本身不包含可读密码；解密需要同一 Windows 用户上下文。
    文件采用临时文件 + replace 写入，避免应用中断留下半截密文。
    """

    def __init__(self, directory: Path):
        if os.name != "nt":
            raise OSError("WindowsCredentialVault 仅支持 Windows")
        self._directory = directory
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32
        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_wchar_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptProtectData.restype = ctypes.c_int
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptUnprotectData.restype = ctypes.c_int
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    def _path(self, profile_id: str) -> Path:
        # UUID/hex profile ids are expected; replacing separators also protects
        # older/corrupt profile data from escaping the vault directory.
        safe_id = "".join(ch for ch in profile_id if ch.isalnum() or ch in "-_")
        if not safe_id:
            raise ValueError("无效的 profile id")
        return self._directory / f"{safe_id}.dpapi"

    def _protect(self, payload: bytes) -> bytes:
        source = ctypes.create_string_buffer(payload)
        source_blob = _DataBlob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
        target_blob = _DataBlob()
        if not self._crypt32.CryptProtectData(
            ctypes.byref(source_blob),
            "BtDeck companion credential",
            None,
            None,
            None,
            0,
            ctypes.byref(target_blob),
        ):
            raise OSError(ctypes.get_last_error(), "CryptProtectData 失败")
        try:
            return ctypes.string_at(target_blob.pbData, target_blob.cbData)
        finally:
            self._kernel32.LocalFree(target_blob.pbData)

    def _unprotect(self, payload: bytes) -> bytes:
        source = ctypes.create_string_buffer(payload)
        source_blob = _DataBlob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
        target_blob = _DataBlob()
        description = ctypes.c_wchar_p()
        if not self._crypt32.CryptUnprotectData(
            ctypes.byref(source_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            0,
            ctypes.byref(target_blob),
        ):
            raise OSError(ctypes.get_last_error(), "CryptUnprotectData 失败")
        try:
            return ctypes.string_at(target_blob.pbData, target_blob.cbData)
        finally:
            self._kernel32.LocalFree(target_blob.pbData)
            if description:
                self._kernel32.LocalFree(description)

    def get(self, profile_id: str) -> CredentialRecord | None:
        path = self._path(profile_id)
        try:
            encrypted = path.read_bytes()
            raw = json.loads(self._unprotect(encrypted).decode("utf-8"))
            if not isinstance(raw, dict):
                return None
            username = raw.get("username")
            password = raw.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                return None
            return CredentialRecord(username=username, password=password)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("读取伴侣凭据失败（%s）：%s", path, exc)
            return None

    def put(self, profile_id: str, record: CredentialRecord) -> None:
        path = self._path(profile_id)
        self._directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"username": record.username, "password": record.password},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = self._protect(payload)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def delete(self, profile_id: str) -> None:
        try:
            self._path(profile_id).unlink()
        except FileNotFoundError:
            pass

    def has(self, profile_id: str) -> bool:
        record = self.get(profile_id)
        return bool(record and record.username and record.password)


def build_auto_login_script(profile_id: str, username: str, password: str) -> str:
    """生成一次性同源登录脚本，密码只在 WebView 运行时短暂出现。

    脚本不通过原生 JS bridge 暴露凭据；成功后只写入前端现有 token cookie，
    账号密码不会写入 localStorage/profile JSON。TOTP 仅通过临时 prompt 获取。
    """

    profile_literal = json.dumps(profile_id, ensure_ascii=False)
    username_literal = json.dumps(username, ensure_ascii=False)
    password_literal = json.dumps(password, ensure_ascii=False)
    return f"""
(function() {{
  if (window.__btdeckAutoLoginRunning) return;
  window.__btdeckAutoLoginRunning = true;
  var profileId = {profile_literal};
  var username = {username_literal};
  var password = {password_literal};
  var accessKey = 'vue_typescript_admin_access_token';
  var refreshKey = 'vue_typescript_admin_refresh_token';
  function hasAccessCookie() {{ return document.cookie.split(';').some(function(item) {{ return item.trim().indexOf(accessKey + '=') === 0; }}); }}
  function clearCookie(name) {{ document.cookie = name + '=; Max-Age=0; path=/'; }}
  function setCookie(name, value) {{ document.cookie = name + '=' + encodeURIComponent(value) + '; Max-Age=604800; path=/'; }}
  var slot = 'btdeck_companion_profile_id';
  try {{
    if (localStorage.getItem(slot) !== profileId) {{
      localStorage.clear();
      clearCookie(accessKey);
      clearCookie(refreshKey);
      localStorage.setItem(slot, profileId);
    }}
  }} catch (_) {{}}
  if (hasAccessCookie()) return;
  function login(twofa) {{
    var body = {{username: username, password: password}};
    if (twofa) body.twofa_code = twofa;
    return fetch(new URL('/api/v1/auth/login', window.location.origin).toString(), {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)
    }}).then(function(response) {{ return response.json(); }}).then(function(payload) {{
      var message = String(payload && payload.msg || '');
      if (payload && payload.code === '400' && message.indexOf('验证码') >= 0) {{
        var code = window.prompt('请输入两步验证码');
        return code ? login(code) : null;
      }}
      if (!payload || payload.code !== '200' || !payload.data || !payload.data[0]) return null;
      var token = payload.data[0];
      if (!token.access_token) return null;
      setCookie(accessKey, token.access_token);
      if (token.refresh_token) setCookie(refreshKey, token.refresh_token);
      window.location.reload();
      return true;
    }}).catch(function() {{ return null; }});
  }}
  login(null);
}})();
"""


def default_credential_vault(config_path: Path) -> CredentialVault:
    """按平台选择默认保险库；非 Windows 不做持久化明文回退。"""

    if os.name == "nt":
        return WindowsCredentialVault(config_path / "companion_credentials")
    logger.warning("当前平台没有系统凭据保险库，伴侣凭据仅在本次进程内可用")
    return MemoryCredentialVault()
