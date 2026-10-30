"""
Password hashing and login tokens.

Passwords:  hashed with Argon2 (via pwdlib). The plain password is never stored or logged.
Tokens:     signed JWTs (HS256) containing only the user ID and role, valid for a limited time.
            The signing secret comes from MENDORA_JWT_SECRET.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from .config import Settings

log = logging.getLogger("mendora.security")

_hasher = PasswordHash.recommended()  # Argon2id with sensible defaults

# Used to make "unknown email" take as long as "wrong password", so attackers
# can't discover which emails have accounts by timing the login.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    try:
        return _hasher.verify(password, password_hash)
    except Exception:  # malformed hash in the database → treat as a failed login
        return False


class TokenError(Exception):
    pass


def resolve_jwt_secret(settings: Settings) -> str:
    """
    Use MENDORA_JWT_SECRET. In development/test, if it's missing, create a random
    temporary secret (everyone is logged out when the server restarts) and warn loudly.
    Production refuses to start without it (see config.py).
    """
    if settings.usable_jwt_secret:
        return settings.usable_jwt_secret
    log.warning(
        "MENDORA_JWT_SECRET is not set (or is still the .env.example placeholder). Using a temporary random secret: all logins will end when the server restarts. "
        "Set MENDORA_JWT_SECRET in backend/.env to keep users signed in."
    )
    return secrets.token_urlsafe(64)


def create_access_token(*, user_id: str, role: str, secret: str, minutes: int, algorithm: str = "HS256") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str = "HS256") -> dict:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],  # fixed list: never trust the algorithm named inside the token
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Your session has expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid authentication token.") from exc
    if payload.get("type") != "access":
        raise TokenError("Invalid authentication token.")
    return payload
