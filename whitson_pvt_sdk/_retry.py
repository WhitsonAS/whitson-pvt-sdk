import email.utils
import random
import time

import httpx

from whitson_pvt_sdk.shared.models import HTTPMethod, RetryConfig


def retry_delay(
    config: RetryConfig,
    method: HTTPMethod,
    attempt: int,
    outcome: httpx.Response | httpx.TransportError,
) -> float | None:
    if attempt >= config.max_attempts:
        return None
    match outcome:
        case httpx.Response(status_code=status) if status in config.statuses and (
            status == 429 or method in config.methods
        ):
            server_delay = retry_after(outcome)
            return _backoff(config, attempt) if server_delay is None else server_delay
        case httpx.TransportError() if method in config.methods:
            return _backoff(config, attempt)
        case _:
            return None


def _backoff(config: RetryConfig, attempt: int) -> float:
    delay = min(config.backoff_factor * (2 ** (attempt - 1)), config.max_backoff)
    return delay * random.uniform(0.8, 1.2)


def retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after-ms")
    if value is not None:
        try:
            return max(float(value) / 1000, 0)
        except ValueError:
            pass

    value = response.headers.get("retry-after")
    if value is None:
        return _rate_limit_reset_after(response)
    try:
        return max(float(value), 0)
    except ValueError:
        try:
            retry_date = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return _rate_limit_reset_after(response)
        if retry_date is None:
            return _rate_limit_reset_after(response)
        return max(retry_date.timestamp() - time.time(), 0)


def _rate_limit_reset_after(response: httpx.Response) -> float | None:
    value = response.headers.get("x-ratelimit-reset")
    if value is None:
        return None
    try:
        return max(float(value) - time.time(), 0)
    except ValueError:
        return None
