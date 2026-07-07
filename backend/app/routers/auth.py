import asyncio

from fastapi import APIRouter, HTTPException, status

from app.auth import create_access_token, login_throttle, verify_password
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
