import pytest

from companion.infrastructure.windows_credentials import (
    CREDENTIAL_TARGET,
    CredentialStoreError,
    WindowsCredentialStore,
)


SECRET = "credential-fixture-not-for-plaintext-storage"


class FakeCredentialApi:
    def __init__(self):
        self.values = {}
        self.calls = []
        self.error_on = None

    def read(self, target):
        self.calls.append(("read", target))
        if self.error_on == "read":
            raise RuntimeError(f"native detail leaked {SECRET}")
        return self.values.get(target)

    def write(self, target, secret):
        self.calls.append(("write", target))
        if self.error_on == "write":
            raise RuntimeError(f"native detail leaked {SECRET}")
        self.values[target] = secret

    def delete(self, target):
        self.calls.append(("delete", target))
        if self.error_on == "delete":
            raise RuntimeError(f"native detail leaked {SECRET}")
        self.values.pop(target, None)


def test_missing_credential_returns_none_without_plaintext_fallback(tmp_path):
    api = FakeCredentialApi()
    store = WindowsCredentialStore(api=api, platform_name="win32")
    assert store.get() is None
    assert api.calls == [("read", CREDENTIAL_TARGET)]
    assert list(tmp_path.iterdir()) == []


def test_store_reads_replaces_and_deletes_only_the_product_target():
    api = FakeCredentialApi()
    api.values["OtherProduct/key"] = "keep-me"
    store = WindowsCredentialStore(api=api, platform_name="win32")
    store.set("first-key")
    assert store.get() == "first-key"
    store.set("second-key")
    assert store.get() == "second-key"
    store.delete()
    assert store.get() is None
    assert api.values == {"OtherProduct/key": "keep-me"}
    assert all(target == CREDENTIAL_TARGET for _, target in api.calls)


def test_unsupported_platform_fails_without_calling_injected_backend():
    api = FakeCredentialApi()
    store = WindowsCredentialStore(api=api, platform_name="linux")
    with pytest.raises(CredentialStoreError):
        store.get()
    with pytest.raises(CredentialStoreError):
        store.set("key")
    with pytest.raises(CredentialStoreError):
        store.delete()
    assert api.calls == []


@pytest.mark.parametrize("operation", ["read", "write", "delete"])
def test_native_errors_are_sanitized_and_do_not_fall_back(operation):
    api = FakeCredentialApi()
    api.error_on = operation
    store = WindowsCredentialStore(api=api, platform_name="win32")
    with pytest.raises(CredentialStoreError) as error:
        if operation == "read":
            store.get()
        elif operation == "write":
            store.set(SECRET)
        else:
            store.delete()
    assert SECRET not in str(error.value)
    assert "native detail" not in str(error.value)
    assert CREDENTIAL_TARGET not in str(error.value)


@pytest.mark.parametrize("secret", ["", "  ", "has\x00nul", "x" * 3000])
def test_invalid_secret_is_rejected_before_native_write(secret):
    api = FakeCredentialApi()
    store = WindowsCredentialStore(api=api, platform_name="win32")
    with pytest.raises(CredentialStoreError):
        store.set(secret)
    assert api.calls == []


def test_target_name_is_product_scoped_and_never_contains_secret():
    assert CREDENTIAL_TARGET.startswith("AICompanion/")
    assert SECRET not in CREDENTIAL_TARGET
