"""
Registration and login.

- POST /api/auth/register  → creates a CUSTOMER account (the role can't be chosen) and signs them in
- POST /api/auth/login     → returns an access token
- GET  /api/auth/me        → the signed-in user
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...config import Settings
from ...errors import ApiError
from ...models import User
from ...repositories import users as users_repo
from ...schemas import ErrorResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut
from ...security import create_access_token, hash_password, verify_password
from ..dependencies import get_app_settings, get_current_user, get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])

INVALID_LOGIN = "Incorrect email or password."


def _token_response(request: Request, settings: Settings, user: User) -> TokenResponse:
    token = create_access_token(
        user_id=user.id,
        role=user.role,
        secret=request.app.state.jwt_secret,
        minutes=settings.access_token_minutes,
    )
    return TokenResponse(access_token=token, expires_in=settings.access_token_minutes * 60, user=UserOut.model_validate(user, from_attributes=True))


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
    summary="Create a customer account",
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}, 422: {"model": ErrorResponse}},
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    if users_repo.get_by_email(db, payload.email):
        raise ApiError(409, "email_taken", "An account with this email already exists. Try signing in instead.")
    try:
        user = users_repo.create(
            db,
            email=payload.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role="customer",
        )
    except IntegrityError as exc:  # two sign-ups with the same email at the same moment
        db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists. Try signing in instead.") from exc
    return _token_response(request, settings, user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in and get an access token",
    responses={
        401: {"model": ErrorResponse, "description": "Wrong email or password"},
        403: {"model": ErrorResponse, "description": "Account disabled"},
        429: {"model": ErrorResponse, "description": "Too many failed attempts"},
    },
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    limiter = request.app.state.login_limiter
    key = users_repo.normalize_email(payload.email)
    if limiter.is_limited(key):
        raise ApiError(
            429,
            "too_many_attempts",
            "Too many failed sign-in attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": str(limiter.retry_after(key))},
        )

    user = users_repo.get_by_email(db, payload.email)
    # verify_password runs even for unknown emails, so both cases take the same time.
    if not verify_password(payload.password, user.password_hash if user else None) or user is None:
        limiter.hit(key)
        raise ApiError(401, "invalid_credentials", INVALID_LOGIN)
    if not user.is_active:
        raise ApiError(403, "account_disabled", "This account has been disabled. Please contact support.")

    limiter.reset(key)
    return _token_response(request, settings, user)


@router.get("/me", response_model=UserOut, summary="Get the signed-in user", responses={401: {"model": ErrorResponse}})
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)
