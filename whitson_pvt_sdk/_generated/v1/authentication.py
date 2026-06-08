from ...http import HTTPTransport
from ...v1.models import (
    TokenData,
)


def get_token(transport: HTTPTransport) -> TokenData:
    body = transport.post("/auth/token")
    return TokenData.model_validate(body)
