import os
import stat
import threading

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import fail
from keyring.errors import KeyringLocked, PasswordDeleteError

from tests.conftest import EMPTY_PAGE, active_login, make_login
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.errors import ConfigurationError, CredentialStoreBusyError
from whitson_pvt_sdk.login import logout


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.passwords.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


def _logged_out(base_url: str) -> dict[str, object] | None:
    result = logout(base_url)
    return None if result is None else result.model_dump()


class LockedKeyring(KeyringBackend):
    priority = 1

    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringLocked("Failed to unlock the collection")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked("Failed to unlock the collection")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringLocked("Failed to unlock the collection")


def test_credentials_file_is_private_to_the_user(base_url, store, store_login):
    store_login(base_url)

    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize("mode", [0o640, 0o604], ids=["group", "world"])
def test_credentials_file_readable_by_others_is_refused(base_url, store, store_login, mode):
    store_login(base_url)
    store.path.chmod(mode)

    with pytest.raises(ConfigurationError, match=f"chmod 600 {store.path}"):
        WhitsonPVTClient(base_url=base_url)


def test_keyring_holds_the_tokens_when_it_is_usable(base_url, httpx2_mock, store, store_login):
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    store_login(base_url, access="keyring-access", refresh="keyring-refresh")
    httpx2_mock.add_response(url=f"{base_url}/external/v2/regions", json=EMPTY_PAGE)

    WhitsonPVTClient(base_url=base_url).regions.list()

    assert httpx2_mock.get_requests()[0].headers["Authorization"] == "Bearer keyring-access"
    content = store.path.read_text()
    assert "keyring-access" not in content
    assert "keyring-refresh" not in content
    assert sorted(backend.passwords.values()) == ["keyring-access", "keyring-refresh"]

    httpx2_mock.add_response(
        url="https://whitson.eu.auth0.com/.well-known/openid-configuration", status_code=503
    )
    assert _logged_out(base_url) == {"url": base_url, "revocation": "failed", "keyring": "deleted"}
    assert backend.passwords == {}


def test_unreadable_keyring_is_a_configuration_error_and_logout_still_removes_the_login(
    base_url, store, store_login
):
    keyring.set_keyring(MemoryKeyring())
    store_login(base_url)
    keyring.set_keyring(LockedKeyring())

    with pytest.raises(ConfigurationError, match="KeyringLocked") as refusal:
        WhitsonPVTClient(base_url=base_url)
    assert "nlock" in refusal.value.message
    assert f"wpvt auth login --url {base_url}" in refusal.value.message

    assert _logged_out(base_url) == {
        "url": base_url,
        "revocation": "skipped",
        "keyring": "not_deleted",
    }
    assert store.get(base_url) is None


def test_logout_without_a_keyring_says_its_entries_were_not_deleted(base_url, store, store_login):
    keyring.set_keyring(MemoryKeyring())
    store_login(base_url)
    keyring.set_keyring(fail.Keyring())

    assert _logged_out(base_url) == {
        "url": base_url,
        "revocation": "skipped",
        "keyring": "not_deleted",
    }
    assert store.get(base_url) is None


@pytest.mark.parametrize("failures", [2, None], ids=["transient", "persistent"])
def test_replacing_the_credentials_file_is_retried_while_it_is_open(
    base_url, monkeypatch, store, store_login, failures
):
    store_login(base_url, access="first")
    replace = os.replace
    attempts = []

    def replace_while_open(source, target):
        attempts.append(target)
        if failures is None or len(attempts) <= failures:
            raise PermissionError(13, "The process cannot access the file")
        replace(source, target)

    monkeypatch.setattr(os, "replace", replace_while_open)

    def save() -> None:
        with store.transaction() as transaction:
            transaction.put(make_login(base_url, access="second"))

    if failures is None:
        with pytest.raises(ConfigurationError, match="try again"):
            save()
        expected = "first"
    else:
        save()
        expected = "second"

    assert active_login(store, base_url).access_token.get_secret_value() == expected
    assert [path.name for path in store.path.parent.iterdir() if path.suffix == ".tmp"] == []


def test_waiting_for_the_lock_outlasts_a_token_refresh(monkeypatch, store):
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with store.transaction():
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(10)
    now = [1000.0]
    monkeypatch.setattr("whitson_pvt_sdk._store.time.monotonic", lambda: now[0])

    def sleep(seconds: float) -> None:
        now[0] += seconds

    monkeypatch.setattr("whitson_pvt_sdk._store.time.sleep", sleep)
    try:
        with pytest.raises(CredentialStoreBusyError, match="try again"), store.transaction():
            pass
    finally:
        release.set()
        holder.join()

    assert now[0] - 1000.0 > 90
