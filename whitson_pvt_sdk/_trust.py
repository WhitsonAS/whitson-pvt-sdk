import ipaddress
from collections.abc import Callable, Sequence
from typing import Annotated

import httpx2
from pydantic import AfterValidator, BaseModel, ConfigDict

from whitson_pvt_sdk.credentials import host_name, normalise_url, origin, same_origin
from whitson_pvt_sdk.errors import ConfigurationError, LoginError


class HostAllowlist(BaseModel):
    model_config = ConfigDict(frozen=True)

    https_parent_domains: tuple[str, ...]
    loopback_names: tuple[str, ...]
    loopback_addresses: frozenset[str]

    def is_loopback(self, host: str) -> bool:
        return host in self.loopback_addresses or any(
            host == name or _strictly_under(host, name) for name in self.loopback_names
        )

    def is_deployment(self, host: str) -> bool:
        return any(_strictly_under(host, domain) for domain in self.https_parent_domains)


ALLOWLIST = HostAllowlist(
    https_parent_domains=("pvt.whitson.com",),
    loopback_names=("localhost",),
    loopback_addresses=frozenset({"127.0.0.1", "::1"}),
)


class KnownIssuers(BaseModel):
    model_config = ConfigDict(frozen=True)

    hosts: frozenset[str]

    def includes(self, issuer: str) -> bool:
        try:
            url = httpx2.URL(normalise_url(issuer))
        except ValueError:
            return False
        return url.scheme == "https" and url.port is None and host_name(url) in self.hosts


# A new login domain needs an SDK release before deployments switch to it.
KNOWN_ISSUERS = KnownIssuers(hosts=frozenset({"whitson.eu.auth0.com"}))


def _strictly_under(host: str, domain: str) -> bool:
    # Match on a label boundary only: "evilpvt.whitson.com" and the apex itself are not under it.
    return host.endswith(f".{domain}")


class TrustedDeployment(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str


class TrustedLoopback(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str


class TrustedByOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str


TrustedHost = TrustedDeployment | TrustedLoopback | TrustedByOverride


Resolver = Callable[[str], Sequence[str]]


def host_trust(base_url: str, *, trust_host: bool, resolve: Resolver) -> TrustedHost:
    try:
        url = normalise_url(base_url)
    except ValueError:
        raise ConfigurationError(
            "The login URL is not a deployment URL such as "
            "https://example.pvt.whitson.com: it needs http(s) and a host name, and no user "
            "name, password, query or fragment."
        ) from None
    parsed = httpx2.URL(url)
    host = host_name(parsed)
    if not base_url.isascii() or any(label.startswith("xn--") for label in host.split(".")):
        raise ConfigurationError(
            f"{base_url.strip()!r} has a non-ASCII (internationalised) host name; "
            "logins are only started for plain ASCII host names."
        )
    if ALLOWLIST.is_loopback(host):
        _require_loopback_resolution(host, resolve)
        return TrustedLoopback(url=url)
    if parsed.scheme != "https":
        raise ConfigurationError(f"Refusing to log in over plain HTTP to {url}; use https://.")
    if ALLOWLIST.is_deployment(host):
        return TrustedDeployment(url=url)
    if trust_host:
        return TrustedByOverride(url=url)
    raise ConfigurationError(
        f"{host} is not a known whitson PVT deployment. Logins are only started for "
        "HTTPS hosts under pvt.whitson.com and for this machine (localhost), so that a link "
        "to another host cannot send you to a login page it controls. If you trust "
        f"{host} and meant to log in to it, run the login again with --trust-host "
        "(trust_host=True in Python)."
    )


def _require_loopback_resolution(host: str, resolve: Resolver) -> None:
    if host in ALLOWLIST.loopback_addresses or host in ALLOWLIST.loopback_names:
        return
    addresses = sorted(set(resolve(host)))
    if not addresses:
        raise ConfigurationError(
            f"{host} does not resolve to an address on this machine, so the login was not "
            "started. Use http://localhost:<port> or check the name."
        )
    elsewhere = [address for address in addresses if not _is_loopback_address(address)]
    if elsewhere:
        raise ConfigurationError(
            f"{host} resolves to {', '.join(elsewhere)}, which is not this machine, so the "
            "login was not started. Names under localhost are only trusted where they resolve "
            "to loopback addresses only; use http://localhost:<port> instead."
        )


def _is_loopback_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


class Proceed(BaseModel):
    model_config = ConfigDict(frozen=True)


def _audience_note(deployment_host: str, foreign_audience: str | None) -> str:
    if foreign_audience is None:
        return ""
    return (
        f" {deployment_host} also asks for access to {foreign_audience!r}, which is not "
        f"{deployment_host} itself."
    )


class FirstUse(BaseModel):
    model_config = ConfigDict(frozen=True)

    deployment_host: str
    issuer_host: str
    foreign_audience: str | None

    def describe(self) -> str:
        return (
            f"First login to {self.deployment_host} from this machine. You will sign in at "
            f"{self.issuer_host}, the login server that {self.deployment_host} names."
            f"{_audience_note(self.deployment_host, self.foreign_audience)} Continue only if "
            "you trust both hosts."
        )


class IssuerChanged(BaseModel):
    model_config = ConfigDict(frozen=True)

    deployment_host: str
    issuer_host: str
    previous_issuer_host: str
    foreign_audience: str | None

    def describe(self) -> str:
        return (
            f"The login server of {self.deployment_host} changed from "
            f"{self.previous_issuer_host} to {self.issuer_host} since the last login. You will "
            f"sign in at {self.issuer_host}."
            f"{_audience_note(self.deployment_host, self.foreign_audience)} Continue only if "
            "you expected this change."
        )


Confirmation = FirstUse | IssuerChanged


def login_decision(
    host: TrustedHost, issuer: str, audience: str, previous_issuer: str | None
) -> Proceed | Confirmation:
    pinned = KNOWN_ISSUERS.includes(issuer)
    own_audience = _is_own_audience(host.url, audience)
    match host:
        case TrustedDeployment(url=url):
            deployment_host = host_name(url)
            if not pinned:
                raise LoginError(
                    f"{deployment_host} named an unexpected login server, {origin(issuer)}, so "
                    "the login was stopped before contacting it. Please report this to whitson."
                )
            if not own_audience:
                raise LoginError(
                    f"{deployment_host} asked for access to a different service, {audience!r}, "
                    f"instead of {deployment_host} itself, so the login was stopped before "
                    "contacting the login server. Please report this to whitson."
                )
            return Proceed()
        case TrustedLoopback() if pinned and own_audience:
            return Proceed()
        case TrustedLoopback(url=url) | TrustedByOverride(url=url):
            deployment_host = host_name(url)
            foreign_audience = None if own_audience else audience
            if previous_issuer is None:
                return FirstUse(
                    deployment_host=deployment_host,
                    issuer_host=host_name(issuer),
                    foreign_audience=foreign_audience,
                )
            if previous_issuer.rstrip("/") != issuer.rstrip("/"):
                return IssuerChanged(
                    deployment_host=deployment_host,
                    issuer_host=host_name(issuer),
                    previous_issuer_host=host_name(previous_issuer),
                    foreign_audience=foreign_audience,
                )
            return Proceed()


def _is_own_audience(url: str, audience: str) -> bool:
    # Every deployment's user-token audience is its own MCP resource URL, https://<host>/mcp.
    try:
        audience_origin = normalise_url(audience)
        path = httpx2.URL(audience.strip()).raw_path
    except ValueError:
        return False
    return same_origin(audience_origin, url) and path == b"/mcp"


class InsecureUrlError(ValueError):
    pass


def _secure_url(value: str) -> str:
    try:
        url = httpx2.URL(value)
    except httpx2.InvalidURL:
        raise ValueError("must be a URL") from None
    if url.scheme == "https" and url.host:
        return value
    if url.scheme == "http" and ALLOWLIST.is_loopback(host_name(url)):
        return value
    raise InsecureUrlError("must be an https URL (http only on this machine)")


SecureUrl = Annotated[str, AfterValidator(_secure_url)]
