import hmac
import threading
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import settings

security = HTTPBearer(auto_error=False)


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
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {"sub": "admin", "exp": expire}
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
        return sub
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
