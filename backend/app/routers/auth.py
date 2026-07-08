import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import (
    create_access_token,
    get_current_user,
    login_throttle,
    token_version_store,
    verify_password,
)
from app.schemas import LoginRequest, TokenResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    # Apply the accumulated progressive delay first, so sustained bursts of
    # attempts are slowed as well, then evaluate the password.
    await asyncio.sleep(login_throttle.current_delay())
    if not verify_password(body.password):
        login_throttle.record_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    login_throttle.record_success()
    token = create_access_token()
    return TokenResponse(token=token)


@router.post("/logout")
def logout(_: str = Depends(get_current_user)):
    """Revoke all outstanding tokens by bumping the server-side token version.

    Requires a valid token, so an anonymous caller cannot force logouts.
    """
    token_version_store.bump()
    return {"message": "Logged out"}
