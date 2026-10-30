"""
Shared objects that routes ask for with `Depends(...)`.

- get_db                → a database session for this HTTP request
- get_current_user      → the signed-in user (401 if not signed in)
- get_optional_user     → the signed-in user, or None for anonymous visitors
- require_roles(...)    → only allows the listed roles (403 otherwise)
"""

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import get_db
from ..errors import ApiError
from ..models import User
from ..repositories import users as users_repo
from ..security import TokenError, decode_access_token

# auto_error=False → we produce our own consistent 401 error instead of FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from /api/auth/login")

__all__ = ["get_db", "get_app_settings", "get_current_user", "get_optional_user", "require_roles"]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def _unauthorized(message: str) -> ApiError:
    return ApiError(401, "not_authenticated", message, headers={"WWW-Authenticate": "Bearer"})


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials, secret=request.app.state.jwt_secret)
    except TokenError as exc:
        raise _unauthorized(str(exc)) from exc
    user = users_repo.get_by_id(db, payload["sub"])
    # Load the user fresh each time, so a disabled account or changed role takes effect immediately.
    if user is None or not user.is_active:
        raise _unauthorized("Your account is not available. Please sign in again.")
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise _unauthorized("Please sign in to do this.")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "You don't have permission to do this.")
        return user

    return checker
