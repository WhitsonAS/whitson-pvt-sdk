import email.utils
import random
import time

import httpx

from whitson_pvt_sdk.shared.models import RetryConfig


def retry_delay(response: httpx.Response | None, retry_config: RetryConfig, attempt: int) -> float:
    retry_after = response_retry_after(response) if response is not None else None
    if retry_after is not None:
        return retry_after

    delay = min(
        retry_config.backoff_factor * (2 ** (attempt - 1)),
        retry_config.max_backoff,
    )
    return delay * random.uniform(0.8, 1.2)


def response_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after-ms")
    if value is not None:
        try:
            return max(float(value) / 1000, 0)
        except ValueError:
            pass

    value = response.headers.get("retry-after")
    if value is None:
        return rate_limit_reset_after(response)
    try:
        return max(float(value), 0)
    except ValueError:
        try:
            retry_date = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return rate_limit_reset_after(response)
        if retry_date is None:
            return rate_limit_reset_after(response)
        return max(retry_date.timestamp() - time.time(), 0)


def rate_limit_reset_after(response: httpx.Response) -> float | None:
    value = response.headers.get("x-ratelimit-reset")
    if value is None:
        return None
    try:
        return max(float(value) - time.time(), 0)
    except ValueError:
        return None
