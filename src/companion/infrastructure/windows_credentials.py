from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import Protocol


CREDENTIAL_TARGET = "AICompanion/Provider/OpenAICompatible"
MAX_CREDENTIAL_BYTES = 2500
_ERROR_NOT_FOUND = 1168
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


class CredentialStoreError(RuntimeError):
    """Safe failure from the current user's Windows Credential Manager."""

    def __init__(self) -> None:
        super().__init__("Windows Credential Manager is unavailable.")


class CredentialApi(Protocol):
    def read(self, target: str) -> str | None: ...
    def write(self, target: str, secret: str) -> None: ...
    def delete(self, target: str) -> None: ...


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class _NativeWindowsCredentialApi:
    """Minimal ctypes wrapper around generic Credential Manager entries."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise CredentialStoreError()
        try:
            self._advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
            self._advapi.CredReadW.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
            ]
            self._advapi.CredReadW.restype = wintypes.BOOL
            self._advapi.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
            self._advapi.CredWriteW.restype = wintypes.BOOL
            self._advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self._advapi.CredDeleteW.restype = wintypes.BOOL
            self._advapi.CredFree.argtypes = [ctypes.c_void_p]
            self._advapi.CredFree.restype = None
        except Exception:
            raise CredentialStoreError() from None

    def read(self, target: str) -> str | None:
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not self._advapi.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            code = ctypes.get_last_error()
            if code == _ERROR_NOT_FOUND:
                return None
            raise CredentialStoreError()
        try:
            credential = pointer.contents
            size = int(credential.CredentialBlobSize)
            if size > MAX_CREDENTIAL_BYTES:
                raise CredentialStoreError()
            value = ctypes.string_at(credential.CredentialBlob, size).decode("utf-8")
            if not value:
                return None
            return value
        except CredentialStoreError:
            raise
        except Exception:
            raise CredentialStoreError() from None
        finally:
            self._advapi.CredFree(pointer)

    def write(self, target: str, secret: str) -> None:
        try:
            encoded = secret.encode("utf-8")
            buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
            credential = _CREDENTIALW()
            credential.Type = _CRED_TYPE_GENERIC
            credential.TargetName = target
            credential.CredentialBlobSize = len(encoded)
            credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
            credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
            credential.AttributeCount = 0
            credential.Attributes = None
            credential.UserName = "AI Companion"
            if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
                raise CredentialStoreError()
        except CredentialStoreError:
            raise
        except Exception:
            raise CredentialStoreError() from None

    def delete(self, target: str) -> None:
        if not self._advapi.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
            if ctypes.get_last_error() != _ERROR_NOT_FOUND:
                raise CredentialStoreError()


class WindowsCredentialStore:
    """Store only the provider key in the current user's Credential Manager."""

    def __init__(self, api: CredentialApi | None = None, *, platform_name: str | None = None) -> None:
        self._api = api
        self._platform_name = platform_name or sys.platform

    def _backend(self) -> CredentialApi:
        if self._platform_name != "win32":
            raise CredentialStoreError()
        if self._api is None:
            self._api = _NativeWindowsCredentialApi()
        return self._api

    def get(self) -> str | None:
        try:
            value = self._backend().read(CREDENTIAL_TARGET)
            if value is not None and not isinstance(value, str):
                raise CredentialStoreError()
            return value
        except CredentialStoreError:
            raise
        except Exception:
            raise CredentialStoreError() from None

    def set(self, secret: str) -> None:
        if not isinstance(secret, str):
            raise CredentialStoreError()
        normalized = secret.strip()
        try:
            encoded_size = len(normalized.encode("utf-8"))
        except UnicodeError:
            raise CredentialStoreError() from None
        if not normalized or "\x00" in normalized or encoded_size > MAX_CREDENTIAL_BYTES:
            raise CredentialStoreError()
        try:
            self._backend().write(CREDENTIAL_TARGET, normalized)
        except CredentialStoreError:
            raise
        except Exception:
            raise CredentialStoreError() from None

    def delete(self) -> None:
        try:
            self._backend().delete(CREDENTIAL_TARGET)
        except CredentialStoreError:
            raise
        except Exception:
            raise CredentialStoreError() from None
