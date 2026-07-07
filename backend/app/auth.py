import hmac
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import settings

security = HTTPBearer(auto_error=False)

# Filename (stored next to the database) holding the current token version.
_TOKEN_VERSION_FILENAME = ".auth_token_version"


class TokenVersionStore:
    """Server-side token version used to revoke all outstanding JWTs.

    Every issued token carries the current version as a "tv" claim. Bumping the
    version (e.g. on logout) invalidates every previously-issued token. The
    value is persisted in a file beside the database and cached in memory, so
    validation costs no per-request I/O. Revocation is per-process, which is
    correct for the default single-process deployment.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version: int | None = None

    def _path(self) -> Path:
        return settings.db_file_path.parent / _TOKEN_VERSION_FILENAME

    def _read_disk(self) -> int:
        try:
            return int(self._path().read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def get(self) -> int:
        with self._lock:
            if self._version is None:
                self._version = self._read_disk()
            return self._version

    def bump(self) -> int:
        """Increment the version and persist it. Returns the new value."""
        with self._lock:
            current = self._version if self._version is not None else self._read_disk()
            new_version = current + 1
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(new_version))
            self._version = new_version
            return new_version


token_version_store = TokenVersionStore()


class LoginThrottle:
    """Global progressive-delay throttle for failed login attempts.

    A single shared counter of consecutive failures (not per-IP). Each failure
    increases the delay applied to subsequent attempts, up to a cap, slowing
    brute-force without ever permanently locking out the legitimate operator.
    A successful login resets the counter.
    """

    BASE_DELAY = 0.5   # seconds, applied after the first failure
    MAX_DELAY = 5.0    # upper bound on the delay

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures = 0

    def current_delay(self) -> float:
        """Delay (seconds) to apply before the next attempt, from prior failures."""
        with self._lock:
            failures = self._failures
        if failures <= 0:
            return 0.0
        return min(self.BASE_DELAY * (2 ** (failures - 1)), self.MAX_DELAY)

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0


login_throttle = LoginThrottle()


def create_access_token() -> str:
    """Create a JWT access token stamped with the current token version."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {"sub": "admin", "exp": expire, "tv": token_version_store.get()}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_password(password: str) -> bool:
    """Check the provided password against the configured password.

    Uses a constant-time comparison so response timing does not leak how much
    of the password matched.
    """
    return hmac.compare_digest(
        password.encode("utf-8"), settings.AUTH_PASSWORD.encode("utf-8")
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """FastAPI dependency – validates the JWT and returns the subject."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        sub: str | None = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        # Reject tokens whose version does not match the current server value
        # (missing claim on pre-upgrade tokens, or revoked via logout).
        if payload.get("tv") != token_version_store.get():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return sub
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
