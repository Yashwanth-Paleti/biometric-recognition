"""
Security & Cryptographic Utilities.

Provides secure password hashing (bcrypt), JWT token issuance,
verification, and OAuth2 security dependencies for administrative API endpoints.
Enforces zero credential leakage, token expiration, and secure environment configuration.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config.settings import settings
from app.utils.logging import logger

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with a randomized salt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception as e:
        logger.error(f"Error during password verification: {e}")
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Issues a signed JWT access token with an expiration timestamp.
    Tokens are signed with HMAC-SHA256 (or settings.jwt_algorithm).
    """
    to_encode = data.copy()
    now_utc = datetime.now(timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode.update({
        "exp": expire,
        "iat": now_utc,
    })

    secret = settings.jwt_secret_key
    algorithm = settings.jwt_algorithm

    encoded_jwt = jwt.encode(to_encode, secret, algorithm=algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes and cryptographically validates a JWT access token.
    
    Raises:
        HTTPException(401): If token is expired, invalid, or malformed.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Access token rejected: Signature has expired.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please authenticate again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Access token rejected: Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_admin(
    token: Optional[str] = Depends(oauth2_scheme),
) -> dict[str, Any]:
    """
    FastAPI dependency validating administrative access token.
    Ensures administrative endpoints are restricted to authenticated callers.
    """
    if not token:
        logger.warning("Access denied to protected endpoint: Missing Bearer token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    username: Optional[str] = payload.get("sub")
    role: Optional[str] = payload.get("role", "admin")

    if username is None or role != "admin":
        logger.warning(f"Access denied: Insufficient privileges for user '{username}'.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Administrator privilege required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "username": username,
        "role": role,
        "claims": payload,
    }
