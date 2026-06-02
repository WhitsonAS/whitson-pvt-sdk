from ...http import HTTPTransport
from ...models.v2 import (
    TokenData,
)


def external_auth_get_token_auth_token_post(transport: HTTPTransport) -> TokenData:
    body = transport.post("/auth/token")
    return TokenData.model_validate(body)
