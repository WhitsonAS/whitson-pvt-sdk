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
        monkeypatch.setenv("WHITSON_PVT_TOKEN", env)
    httpx_mock.add_response(
        url=f"{base_url}/external/v2/regions",
        json={"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}},
    )
    WhitsonPVTClient(token=explicit, base_url=base_url).regions.list()
    requests = httpx_mock.get_requests()
    assert [r.url.path for r in requests] == ["/external/v2/regions"]
    assert requests[0].headers["Authorization"] == f"Bearer {expected}"


@pytest.mark.parametrize(
    ("explicit", "env", "source"),
    [
        (None, None, "No credentials configured"),
        ("", None, "token= argument is empty"),
        (None, "", "WHITSON_PVT_TOKEN is set but empty"),
        (None, "  ", "WHITSON_PVT_TOKEN is set but empty"),
        ("", ENV_TOKEN, "token= argument is empty"),
    ],
    ids=["none", "empty-token", "empty-env", "blank-env", "empty-token-over-env"],
)
def test_unusable_authentication_is_rejected(base_url, monkeypatch, explicit, env, source):
    if env is not None:
        monkeypatch.setenv("WHITSON_PVT_TOKEN", env)
    with pytest.raises(ConfigurationError, match=source):
        WhitsonPVTClient(token=explicit, base_url=base_url)


def test_leaving_the_with_block_closes_the_client(base_url):
    with WhitsonPVTClient(token="t", base_url=base_url) as client:
        pass
    with pytest.raises(RuntimeError, match="closed"):
        client.regions.list()
