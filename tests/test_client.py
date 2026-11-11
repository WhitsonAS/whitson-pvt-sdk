import pytest

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.errors import AuthError
from whitson_pvt_sdk.shared.models import RetryConfig


def test_passes_retry_config(base_url):
    retry_config = RetryConfig(max_attempts=1)
    client = WhitsonPVTClient(token="t", base_url=base_url, retry_config=retry_config)
    assert client._transport._retry_config is retry_config


def test_passes_timeout_config(base_url):
    client = WhitsonPVTClient(token="t", base_url=base_url, timeout=12.5, file_timeout=19.5)
    assert client._transport._http.timeout.read == 12.5
    assert client._transport._file_timeout == 19.5


TOKEN = "whitson_pvt_abcdefghijkl_" + "a" * 43 + "_abcdef"
ENV_TOKEN = "whitson_pvt_from_env"


@pytest.mark.parametrize(
    ("explicit", "env", "expected"),
    [
        (TOKEN, None, TOKEN),
        (None, ENV_TOKEN, ENV_TOKEN),
        (TOKEN, ENV_TOKEN, TOKEN),
    ],
    ids=["token", "env", "token-over-env"],
)
def test_token_is_sent_as_the_bearer(base_url, httpx_mock, monkeypatch, explicit, env, expected):
    if env is not None:
        monkeypatch.setenv("PVT_TOKEN", env)
    httpx_mock.add_response(
        url=f"{base_url}/external/v2/regions",
        json={"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}},
    )
    WhitsonPVTClient(token=explicit, base_url=base_url).regions.list()
    requests = httpx_mock.get_requests()
    assert [r.url.path for r in requests] == ["/external/v2/regions"]
    assert requests[0].headers["Authorization"] == f"Bearer {expected}"


@pytest.mark.parametrize(
    ("explicit", "env"),
    [(None, None), ("", None), (None, ""), (None, "  "), ("", ENV_TOKEN)],
    ids=["none", "empty-token", "empty-env", "blank-env", "empty-token-over-env"],
)
def test_unusable_authentication_is_rejected(base_url, monkeypatch, explicit, env):
    if env is not None:
        monkeypatch.setenv("PVT_TOKEN", env)
    with pytest.raises(AuthError):
        WhitsonPVTClient(token=explicit, base_url=base_url)
