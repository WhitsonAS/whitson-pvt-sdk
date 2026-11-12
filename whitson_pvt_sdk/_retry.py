import email.utils
import math
import random
import time

import httpx2

from whitson_pvt_sdk.shared.models import HTTPMethod, RetryConfig

MAX_SERVER_DELAY_SECONDS = 60.0


def retry_delay(
    config: RetryConfig,
    method: HTTPMethod,
    attempt: int,
    outcome: httpx2.Response | httpx2.TransportError,
) -> float | None:
    if attempt >= config.max_attempts:
        return None
    match outcome:
        case httpx2.Response(status_code=status) if status in config.statuses and (
            status == 429 or method in config.methods
        ):
            server_delay = retry_after(outcome)
            if server_delay is None:
                return _backoff(config, attempt)
            return min(server_delay, MAX_SERVER_DELAY_SECONDS)
        case httpx2.TransportError() if method in config.methods:
            return _backoff(config, attempt)
        case _:
            return None


def _backoff(config: RetryConfig, attempt: int) -> float:
    delay = min(config.backoff_factor * (2 ** (attempt - 1)), config.max_backoff)
    return delay * random.uniform(0.8, 1.2)


def retry_after(response: httpx2.Response) -> float | None:
    milliseconds = _seconds(response.headers.get("retry-after-ms"))
    if milliseconds is not None:
        return milliseconds / 1000

    value = response.headers.get("retry-after")
    if value is None:
        return _rate_limit_reset_after(response)
    seconds = _seconds(value)
    if seconds is not None:
        return seconds
    try:
        retry_date = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return _rate_limit_reset_after(response)
    if retry_date is None:
        return _rate_limit_reset_after(response)
    return max(retry_date.timestamp() - time.time(), 0)


def _rate_limit_reset_after(response: httpx2.Response) -> float | None:
    reset = _seconds(response.headers.get("x-ratelimit-reset"))
    if reset is None or response.status_code != 429:
        return None
    return max(reset - time.time(), 0)


def _seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None
