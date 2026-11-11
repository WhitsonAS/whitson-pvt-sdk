import stat

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.errors import ConfigurationError
from whitson_pvt_sdk.login import logout

EMPTY_PAGE = {"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}}


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


def test_keyring_holds_the_tokens_when_it_is_usable(base_url, httpx_mock, store, store_login):
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    store_login(base_url, access="keyring-access", refresh="keyring-refresh")
    httpx_mock.add_response(url=f"{base_url}/external/v2/regions", json=EMPTY_PAGE)

    WhitsonPVTClient(base_url=base_url).regions.list()

    assert httpx_mock.get_requests()[0].headers["Authorization"] == "Bearer keyring-access"
    content = store.path.read_text()
    assert "keyring-access" not in content
    assert "keyring-refresh" not in content
    assert sorted(backend.passwords.values()) == ["keyring-access", "keyring-refresh"]

    httpx_mock.add_response(
        url="https://login.example.com/.well-known/openid-configuration", status_code=503
    )
    logout(base_url)
    assert backend.passwords == {}
