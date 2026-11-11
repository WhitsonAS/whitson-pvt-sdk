import pytest

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.errors import APIError, ConfigurationError
from whitson_pvt_sdk.shared.models import RetryConfig


def test_passes_retry_config(base_url, httpx_mock):
    client = WhitsonPVTClient(
        token="t", base_url=base_url, retry_config=RetryConfig(max_attempts=1)
    )
    httpx_mock.add_response(status_code=503, json={"message": "Unavailable"})
    with pytest.raises(APIError):
        client.regions.list()
    assert len(httpx_mock.get_requests()) == 1


def test_passes_timeout_config(base_url, httpx_mock):
    client = WhitsonPVTClient(token="t", base_url=base_url, timeout=12.5, file_timeout=19.5)
    httpx_mock.add_response(
        url=f"{base_url}/external/v2/regions",
        json={"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}},
    )
    httpx_mock.add_response(url=f"{base_url}/external/v2/reports/1/export", content=b"zip")
    client.regions.list()
    client.reports.export(report_id=1)
    assert [r.extensions["timeout"]["read"] for r in httpx_mock.get_requests()] == [12.5, 19.5]


TOKEN = "whitson_pvt_abcdefghijkl_" + "a" * 43 + "_abcdef"
ENV_TOKEN = "whitson_pvt_from_env"
STORED_TOKEN = "stored-access-token"
OTHER_URL = "https://other.pvt.whitson.com"
EMPTY_PAGE = {"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}}


@pytest.mark.parametrize(
    ("explicit", "env", "stored", "expected"),
    [
        (TOKEN, None, False, TOKEN),
        (None, ENV_TOKEN, False, ENV_TOKEN),
        (TOKEN, ENV_TOKEN, False, TOKEN),
        (None, None, True, STORED_TOKEN),
        (None, ENV_TOKEN, True, ENV_TOKEN),
        (TOKEN, None, True, TOKEN),
    ],
    ids=["token", "env", "token-over-env", "stored", "env-over-stored", "token-over-stored"],
)
def test_token_is_sent_as_the_bearer(
    base_url, httpx_mock, monkeypatch, store_login, explicit, env, stored, expected
):
    if env is not None:
        monkeypatch.setenv("WHITSON_PVT_TOKEN", env)
    if stored:
        store_login(base_url, access=STORED_TOKEN)
    httpx_mock.add_response(url=f"{base_url}/external/v2/regions", json=EMPTY_PAGE)
    WhitsonPVTClient(token=explicit, base_url=base_url).regions.list()
    requests = httpx_mock.get_requests()
    assert [r.url.path for r in requests] == ["/external/v2/regions"]
    assert requests[0].headers["Authorization"] == f"Bearer {expected}"


@pytest.mark.parametrize(
    ("explicit", "env", "stored_for", "source"),
    [
        (None, None, None, "No credentials configured for https://dev.pvt.whitson.com"),
        ("", None, None, "token= argument is empty"),
        (None, "", None, "WHITSON_PVT_TOKEN is set but empty"),
        (None, "  ", None, "WHITSON_PVT_TOKEN is set but empty"),
        ("", ENV_TOKEN, None, "token= argument is empty"),
        (None, None, OTHER_URL, "No credentials configured for https://dev.pvt.whitson.com"),
        ("", None, "https://dev.pvt.whitson.com", "token= argument is empty"),
        (None, "", "https://dev.pvt.whitson.com", "WHITSON_PVT_TOKEN is set but empty"),
    ],
    ids=[
        "none",
        "empty-token",
        "empty-env",
        "blank-env",
        "empty-token-over-env",
        "login-for-another-url",
        "empty-token-over-stored",
        "empty-env-over-stored",
    ],
)
def test_unusable_authentication_is_rejected(
    base_url, monkeypatch, store_login, explicit, env, stored_for, source
):
    if env is not None:
        monkeypatch.setenv("WHITSON_PVT_TOKEN", env)
    if stored_for is not None:
        store_login(stored_for)
    with pytest.raises(ConfigurationError, match=source) as exc:
        WhitsonPVTClient(token=explicit, base_url=base_url)
    if explicit is None and env is None:
        assert "wpvt auth login --url https://dev.pvt.whitson.com" in exc.value.message


@pytest.mark.parametrize(
    ("argument", "env_url", "default", "expected"),
    [
        ("https://Arg.pvt.whitson.com/", OTHER_URL, OTHER_URL, "https://arg.pvt.whitson.com"),
        (None, "https://env.pvt.whitson.com", OTHER_URL, "https://env.pvt.whitson.com"),
        (None, None, OTHER_URL, OTHER_URL),
    ],
    ids=["argument", "env-over-default", "default-login"],
)
def test_deployment_url_is_resolved(
    httpx_mock, monkeypatch, store_login, argument, env_url, default, expected
):
    if env_url is not None:
        monkeypatch.setenv("WHITSON_PVT_URL", env_url)
    store_login(default)
    httpx_mock.add_response(url=f"{expected}/external/v2/regions", json=EMPTY_PAGE)
    WhitsonPVTClient(base_url=argument, token="t").regions.list()
    assert [str(r.url) for r in httpx_mock.get_requests()] == [f"{expected}/external/v2/regions"]


@pytest.mark.parametrize(
    ("env_url", "message"),
    [
        (None, "No deployment URL configured.*WHITSON_PVT_URL.*wpvt auth login --url"),
        ("", "WHITSON_PVT_URL is set but empty"),
        ("ftp://example.com", "WHITSON_PVT_URL must be an http"),
    ],
    ids=["none", "empty-env", "not-http"],
)
def test_unusable_deployment_url_is_rejected(monkeypatch, env_url, message):
    if env_url is not None:
        monkeypatch.setenv("WHITSON_PVT_URL", env_url)
    with pytest.raises(ConfigurationError, match=message):
        WhitsonPVTClient(token="t")


def test_leaving_the_with_block_closes_the_client(base_url):
    with WhitsonPVTClient(token="t", base_url=base_url) as client:
        pass
    with pytest.raises(RuntimeError, match="closed"):
        client.regions.list()
