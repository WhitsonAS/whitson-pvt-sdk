from pydantic import BaseModel, ConfigDict

from whitson_pvt_sdk._oauth import (
    OAuthError,
    TokenGranted,
    TokenRefused,
    oauth_client,
    refreshed_login,
    request_token,
)
from whitson_pvt_sdk._store import ActiveLogin, CredentialStore, InvalidLogin
from whitson_pvt_sdk.credentials import StoredLogin
from whitson_pvt_sdk.errors import LoginError


class Usable(BaseModel):
    model_config = ConfigDict(frozen=True)

    login: StoredLogin


class NoLongerValid(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str
    reason: str


RefreshOutcome = Usable | NoLongerValid


def usable_login(login: StoredLogin, store: CredentialStore) -> RefreshOutcome:
    if not login.expiring():
        return Usable(login=login)
    return replace_access_token(login, store)


def replace_access_token(login: StoredLogin, store: CredentialStore) -> RefreshOutcome:
    with store.transaction() as transaction:
        match transaction.get(login.base_url):
            case None:
                return NoLongerValid(base_url=login.base_url, reason="it was logged out")
            case InvalidLogin(reason=reason):
                return NoLongerValid(base_url=login.base_url, reason=reason)
            case ActiveLogin(login=stored) if (
                stored.access_token != login.access_token and not stored.expiring()
            ):
                return Usable(login=stored)
            case ActiveLogin(login=stored):
                with oauth_client() as http:
                    result = request_token(
                        http,
                        stored.token_endpoint,
                        {
                            "grant_type": "refresh_token",
                            "client_id": stored.client_id,
                            "refresh_token": stored.refresh_token.get_secret_value(),
                        },
                    )
                match result:
                    case TokenGranted(token=token):
                        renewed = refreshed_login(stored, token)
                        transaction.put(renewed)
                        return Usable(login=renewed)
                    case TokenRefused(error=OAuthError(error="invalid_grant") as error):
                        reason = (
                            f"the authorization server refused to renew it ({error.describe()})"
                        )
                        transaction.mark_invalid(stored.base_url, reason)
                        return NoLongerValid(base_url=stored.base_url, reason=reason)
                    case TokenRefused(error=error):
                        raise LoginError(
                            f"Could not renew the login for {stored.base_url}: {error.describe()}."
                        )
