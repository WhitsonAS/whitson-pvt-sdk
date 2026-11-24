from pydantic import BaseModel, ConfigDict

from whitson_pvt_sdk._oauth import OAuthError, TokenResponse, oauth_client, post_oauth
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


def replace_access_token(login: StoredLogin, store: CredentialStore) -> RefreshOutcome:
    with store.transaction() as transaction:
        match transaction.get(login.base_url):
            case None:
                return NoLongerValid(base_url=login.base_url, reason="it was logged out")
            case ActiveLogin(login=stored) | InvalidLogin(login=stored) if not stored.same_client(
                login
            ):
                return NoLongerValid(
                    base_url=login.base_url,
                    reason="a login with another issuer or client replaced it",
                )
            case InvalidLogin(reason=reason):
                return NoLongerValid(base_url=login.base_url, reason=reason)
            case ActiveLogin(login=stored) if (
                stored.access_token != login.access_token and not stored.expiring()
            ):
                return Usable(login=stored)
            case ActiveLogin(login=stored):
                with oauth_client() as http:
                    result = post_oauth(
                        http,
                        stored.token_endpoint,
                        {
                            "grant_type": "refresh_token",
                            "client_id": stored.client_id,
                            "refresh_token": stored.refresh_token.get_secret_value(),
                        },
                        TokenResponse,
                    )
                match result:
                    case TokenResponse() as token:
                        renewed = stored.model_copy(
                            update={
                                "access_token": token.access_token,
                                "refresh_token": token.refresh_token or stored.refresh_token,
                                "expires_at": token.expires_at(),
                            }
                        )
                        transaction.put(renewed)
                        return Usable(login=renewed)
                    case OAuthError(error="invalid_grant") as error:
                        reason = (
                            f"the authorization server refused to renew it ({error.describe()})"
                        )
                        transaction.mark_invalid(stored.base_url, reason)
                        return NoLongerValid(base_url=stored.base_url, reason=reason)
                    case OAuthError() as error:
                        raise LoginError(
                            f"Could not renew the login for {stored.base_url}: {error.describe()}."
                        )
