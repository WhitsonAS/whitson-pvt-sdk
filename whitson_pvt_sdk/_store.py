import logging
import os
import secrets
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer, SecretStr
from pydantic import ValidationError as PydanticValidationError

from whitson_pvt_sdk._oauth import HTTP_TIMEOUT_SECONDS
from whitson_pvt_sdk._trust import Remembered
from whitson_pvt_sdk.credentials import DeploymentUrl, StoredLogin, normalise_url
from whitson_pvt_sdk.errors import ConfigurationError, CredentialStoreBusyError

if TYPE_CHECKING:
    from keyring.backend import KeyringBackend

APP_DIRECTORY = "whitson-pvt"
KEYRING_SERVICE = "whitson-pvt"
# Outlasts a token refresh held under the lock: connect, write and read can each take
# HTTP_TIMEOUT_SECONDS.
LOCK_TIMEOUT_SECONDS = 4 * HTTP_TIMEOUT_SECONDS
_REPLACE_ATTEMPTS = 10
_REPLACE_RETRY_SECONDS = 0.03

logger = logging.getLogger("whitson_pvt_sdk")

_BINARY = getattr(os, "O_BINARY", 0)
_TOKEN_FIELDS = {"access_token", "refresh_token"}
_FACT_FIELDS = set(StoredLogin.model_fields) - _TOKEN_FIELDS


class ActiveLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    login: StoredLogin


class InvalidLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    login: StoredLogin
    reason: str
    since: AwareDatetime


StoreEntry = ActiveLogin | InvalidLogin


KeyringCleanup = Literal["not_used", "deleted", "not_deleted"]


class RemovedLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str
    login: StoredLogin | None
    keyring: KeyringCleanup


_Secret = Annotated[
    SecretStr,
    PlainSerializer(lambda value: value.get_secret_value(), return_type=str, when_used="json"),
]


class _FileSecrets(BaseModel):
    storage: Literal["file"] = "file"
    access_token: _Secret
    refresh_token: _Secret


class _KeyringSecrets(BaseModel):
    storage: Literal["keyring"] = "keyring"


class _Active(BaseModel):
    state: Literal["active"] = "active"


class _Invalid(BaseModel):
    state: Literal["invalid"] = "invalid"
    reason: str
    since: AwareDatetime


class _Profile(BaseModel):
    base_url: DeploymentUrl
    issuer: str
    client_id: str
    audience: str
    scopes: tuple[str, ...]
    token_endpoint: str
    expires_at: AwareDatetime
    secrets: Annotated[_FileSecrets | _KeyringSecrets, Field(discriminator="storage")]
    status: Annotated[_Active | _Invalid, Field(discriminator="state")] = _Active()


class _Document(BaseModel):
    version: Literal[1] = 1
    default: DeploymentUrl | None = None
    profiles: dict[DeploymentUrl, _Profile] = Field(default_factory=dict)


def config_directory() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return base / APP_DIRECTORY


class StoreTransaction:
    def __init__(self, document: _Document) -> None:
        self._document = document
        self._written: dict[str, StoredLogin] = {}

    def get(self, base_url: str) -> StoreEntry | None:
        key = normalise_url(base_url)
        written = self._written.get(key)
        profile = self._document.profiles.get(key)
        if profile is None:
            return None
        if written is not None:
            return _entry(profile, written.access_token, written.refresh_token)
        return _load_entry(profile)

    def urls(self) -> list[str]:
        return list(self._document.profiles)

    def put(self, login: StoredLogin) -> None:
        self._document.profiles[login.base_url] = _Profile(
            **login.model_dump(include=_FACT_FIELDS), secrets=_file_secrets(login)
        )
        self._written[login.base_url] = login

    def set_default(self, base_url: str) -> None:
        key = normalise_url(base_url)
        if key not in self._document.profiles:
            raise ConfigurationError(f"No stored login for {key}.")
        self._document.default = key

    def mark_invalid(self, base_url: str, reason: str) -> None:
        profile = self._document.profiles[normalise_url(base_url)]
        profile.status = _Invalid(reason=reason, since=datetime.now(UTC))

    def remove(self, base_url: str) -> RemovedLogin | None:
        key = normalise_url(base_url)
        try:
            entry = self.get(key)
        except ConfigurationError:
            entry = None
        profile = self._document.profiles.pop(key, None)
        if profile is None:
            return None
        self._written.pop(key, None)
        if self._document.default == key:
            self._document.default = None
        return RemovedLogin(
            base_url=key,
            login=None if entry is None else entry.login,
            keyring=_delete_secrets(profile),
        )


class CredentialStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "credentials.json"
        self._directory = directory
        self._lock_path = directory / "credentials.lock"

    @classmethod
    def from_environment(cls) -> Self:
        return cls(config_directory())

    def get(self, base_url: str) -> StoreEntry | None:
        profile = self._read().profiles.get(normalise_url(base_url))
        return None if profile is None else _load_entry(profile)

    def remembered(self, base_url: str) -> Remembered | None:
        profile = self._read().profiles.get(normalise_url(base_url))
        if profile is None:
            return None
        return Remembered(issuer=profile.issuer, audience=profile.audience)

    def default_url(self) -> str | None:
        return self._read().default

    @contextmanager
    def transaction(self) -> Iterator[StoreTransaction]:
        with self._locked():
            document = self._read()
            unchanged = document.model_dump_json()
            transaction = StoreTransaction(document)
            yield transaction
            if transaction._written or document.model_dump_json() != unchanged:
                self._commit(transaction)

    def _read(self) -> _Document:
        try:
            fd = os.open(self.path, os.O_RDONLY | _BINARY)
        except FileNotFoundError:
            return _Document()
        with os.fdopen(fd, "rb") as file:
            _check_private(self.path, os.fstat(file.fileno()))
            content = file.read()
        try:
            return _Document.model_validate_json(content)
        except PydanticValidationError:
            raise ConfigurationError(
                f"{self.path} is not a valid whitson PVT credentials file. "
                "Remove it and run `wpvt auth login`."
            ) from None

    def _commit(self, transaction: StoreTransaction) -> None:
        document = transaction._document
        backend = _keyring()
        for key, login in transaction._written.items():
            document.profiles[key].secrets = _secrets(backend, login)
        self._write(document)

    def _write(self, document: _Document) -> None:
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self._directory / f".credentials.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(document.model_dump_json(indent=2).encode())
                file.flush()
                os.fsync(file.fileno())
            _replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while not _try_lock(fd):
                if time.monotonic() > deadline:
                    raise CredentialStoreBusyError(
                        f"Another process held the credential store lock {self._lock_path} for "
                        f"{LOCK_TIMEOUT_SECONDS:.0f} s, probably while renewing a login; "
                        "try again."
                    )
                time.sleep(0.05)
            try:
                yield
            finally:
                _unlock(fd)
        finally:
            os.close(fd)


def _replace(source: Path, target: Path) -> None:
    # Windows refuses to replace a file another process has open (reads take no lock).
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            if attempt == _REPLACE_ATTEMPTS:
                raise ConfigurationError(
                    f"Could not save {target} ({exc.strerror}); another program may have it "
                    "open. Close it and try again."
                ) from None
            time.sleep(_REPLACE_RETRY_SECONDS)


def _check_private(path: Path, status: os.stat_result) -> None:
    if sys.platform == "win32":
        return
    if status.st_uid != os.getuid():
        raise ConfigurationError(
            f"{path} belongs to another user. Remove it and run `wpvt auth login`."
        )
    if status.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigurationError(
            f"{path} can be read by other users (mode {stat.filemode(status.st_mode)}). "
            f"Run `chmod 600 {path}` and try again."
        )


def _file_secrets(login: StoredLogin) -> _FileSecrets:
    return _FileSecrets(access_token=login.access_token, refresh_token=login.refresh_token)


def _load_entry(profile: _Profile) -> StoreEntry:
    match profile.secrets:
        case _FileSecrets(access_token=access_token, refresh_token=refresh_token):
            return _entry(profile, access_token, refresh_token)
        case _KeyringSecrets():
            access_token, refresh_token = _read_keyring(profile.base_url)
            return _entry(profile, access_token, refresh_token)


def _entry(profile: _Profile, access_token: SecretStr, refresh_token: SecretStr) -> StoreEntry:
    login = StoredLogin(
        **profile.model_dump(include=_FACT_FIELDS),
        access_token=access_token,
        refresh_token=refresh_token,
    )
    match profile.status:
        case _Active():
            return ActiveLogin(login=login)
        case _Invalid(reason=reason, since=since):
            return InvalidLogin(login=login, reason=reason, since=since)


def _keyring() -> "KeyringBackend | None":
    try:
        import keyring
        from keyring.backends import fail, null
    except ImportError:
        return None
    backend = keyring.get_keyring()
    if isinstance(backend, (fail.Keyring, null.Keyring)):
        return None
    return backend


def _keyring_names(base_url: str) -> tuple[str, str]:
    return f"{base_url} access_token", f"{base_url} refresh_token"


def _read_keyring(base_url: str) -> tuple[SecretStr, SecretStr]:
    backend = _keyring()
    if backend is None:
        raise ConfigurationError(
            f"The login for {base_url} is stored in the OS keyring, which is not available here. "
            f'Install the keyring package (pip install "whitson-pvt-sdk[cli]") or run '
            f"`wpvt auth login --url {base_url}` again."
        )
    access_name, refresh_name = _keyring_names(base_url)
    try:
        access_token = backend.get_password(KEYRING_SERVICE, access_name)
        refresh_token = backend.get_password(KEYRING_SERVICE, refresh_name)
    except Exception as exc:
        raise ConfigurationError(
            f"Could not read the login for {base_url} from the OS keyring "
            f"({type(exc).__name__}). Unlock the keyring and try again, or run "
            f"`wpvt auth login --url {base_url}` again, which stores the login in the "
            "credentials file when the keyring cannot be used."
        ) from None
    if not access_token or not refresh_token:
        raise ConfigurationError(
            f"The OS keyring has no tokens for the login to {base_url}. "
            f"Run `wpvt auth login --url {base_url}`."
        )
    return SecretStr(access_token), SecretStr(refresh_token)


def _secrets(
    backend: "KeyringBackend | None", login: StoredLogin
) -> _FileSecrets | _KeyringSecrets:
    if backend is None:
        return _file_secrets(login)
    access_name, refresh_name = _keyring_names(login.base_url)
    try:
        backend.set_password(KEYRING_SERVICE, access_name, login.access_token.get_secret_value())
        backend.set_password(KEYRING_SERVICE, refresh_name, login.refresh_token.get_secret_value())
    except Exception as exc:
        logger.warning(
            "Could not store the login for %s in the OS keyring (%s); storing it in the "
            "credentials file instead",
            login.base_url,
            type(exc).__name__,
        )
        return _file_secrets(login)
    return _KeyringSecrets()


def _delete_secrets(profile: _Profile) -> KeyringCleanup:
    if isinstance(profile.secrets, _FileSecrets):
        return "not_used"
    backend = _keyring()
    if backend is None:
        return "not_deleted"
    from keyring.errors import PasswordDeleteError

    deleted = True
    for name in _keyring_names(profile.base_url):
        try:
            backend.delete_password(KEYRING_SERVICE, name)
        except PasswordDeleteError:
            pass
        except Exception:
            logger.warning("Could not delete %s from the OS keyring", name)
            deleted = False
    return "deleted" if deleted else "not_deleted"


if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
