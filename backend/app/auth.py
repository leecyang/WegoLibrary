import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.database import (
    AuthSession,
    User,
    create_auth_session,
    engine,
    get_auth_session_by_token_hash,
    update_auth_session,
)

# 配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-keep-it-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "3000"))
AUTH_SESSION_COOKIE_NAME = os.getenv("AUTH_SESSION_COOKIE_NAME", "wegolibrary_session")
AUTH_SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(30 * 24 * 60 * 60)))
AUTH_SESSION_SAMESITE = os.getenv("AUTH_SESSION_SAMESITE", "lax").lower()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def get_session():
    with Session(engine) as session:
        yield session


def verify_password(plain_password, hashed_password):
    if isinstance(plain_password, str):
        plain_password = plain_password.encode("utf-8")
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode("utf-8")
    return bcrypt.checkpw(plain_password, hashed_password)


def get_password_hash(password):
    if isinstance(password, str):
        password = password.encode("utf-8")
    return bcrypt.hashpw(password, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _build_credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _build_auth_session_expiry(now: Optional[datetime] = None) -> datetime:
    return (now or datetime.now()) + timedelta(seconds=AUTH_SESSION_TTL_SECONDS)


def hash_auth_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_auth_session_cookie(response: Response, token: str, request: Request):
    response.set_cookie(
        key=AUTH_SESSION_COOKIE_NAME,
        value=token,
        max_age=AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        secure=_request_is_secure(request),
        samesite=AUTH_SESSION_SAMESITE,
        path="/",
    )


def clear_auth_session_cookie(response: Response):
    response.delete_cookie(
        key=AUTH_SESSION_COOKIE_NAME,
        path="/",
        samesite=AUTH_SESSION_SAMESITE,
    )


def create_persistent_auth_session(session: Session, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    create_auth_session(
        session,
        user_id=user_id,
        token_hash=hash_auth_session_token(raw_token),
        expires_at=_build_auth_session_expiry(),
    )
    return raw_token


def revoke_auth_session_token(session: Session, raw_token: Optional[str]) -> bool:
    if not raw_token:
        return False

    auth_session = get_auth_session_by_token_hash(session, hash_auth_session_token(raw_token))
    if not auth_session or auth_session.revoked_at is not None:
        return False

    auth_session.revoked_at = datetime.now()
    update_auth_session(session, auth_session)
    return True


def _get_user_from_bearer_token(session: Session, token: str) -> Optional[User]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if not username:
            return None
    except JWTError:
        return None

    return session.exec(select(User).where(User.username == username)).first()


def _get_user_from_auth_session(
    session: Session,
    raw_token: str,
) -> tuple[Optional[User], Optional[AuthSession]]:
    auth_session = get_auth_session_by_token_hash(session, hash_auth_session_token(raw_token))
    if not auth_session:
        return None, None

    now = datetime.now()
    if auth_session.revoked_at is not None or auth_session.expires_at <= now:
        if auth_session.revoked_at is None:
            auth_session.revoked_at = now
            update_auth_session(session, auth_session)
        return None, auth_session

    user = session.get(User, auth_session.user_id)
    if not user:
        auth_session.revoked_at = now
        update_auth_session(session, auth_session)
        return None, auth_session

    return user, auth_session


def _refresh_auth_session(
    session: Session,
    auth_session: AuthSession,
    response: Response,
    request: Request,
    raw_token: str,
):
    now = datetime.now()
    auth_session.last_used_at = now
    auth_session.expires_at = _build_auth_session_expiry(now)
    update_auth_session(session, auth_session)
    set_auth_session_cookie(response, raw_token, request)


async def get_current_user(
    request: Request,
    response: Response,
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    credentials_exception = _build_credentials_exception()

    if token:
        user = _get_user_from_bearer_token(session, token)
        if user is not None:
            return user

    session_token = request.cookies.get(AUTH_SESSION_COOKIE_NAME)
    if session_token:
        user, auth_session = _get_user_from_auth_session(session, session_token)
        if user is not None and auth_session is not None:
            _refresh_auth_session(session, auth_session, response, request, session_token)
            return user
        clear_auth_session_cookie(response)

    raise credentials_exception


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )
    return current_user
