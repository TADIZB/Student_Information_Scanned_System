from __future__ import annotations

import hashlib
import json
import os
import secrets
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta

import bcrypt as _bcrypt
import jwt as _jwt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import RefreshToken, User, UserIdentity

# ─── Cấu hình ────────────────────────────────────────────────────────────────

ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=30)
JWT_ALGORITHM = "HS256"

# Secret để ký JWT — BẮT BUỘC set qua biến môi trường JWT_SECRET ở production
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    # Fallback dev: sinh secret tạm thời cho mỗi lần boot (mọi user sẽ phải re-login khi server restart)
    JWT_SECRET = secrets.token_urlsafe(48)
    print("⚠️  JWT_SECRET chưa được set — dùng secret tạm. Hãy set biến môi trường JWT_SECRET ở production.")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

# Cookie config
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = "lax"


# ─── Mật khẩu ────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


# ─── Token primitives ────────────────────────────────────────────────────────

def _encode_access_token(user_id: uuid.UUID) -> str:
    """JWT chứa user_id + exp. Hạn ngắn (ACCESS_TOKEN_TTL)."""
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
        "type": "access",
    }
    return _jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return uuid.UUID(payload["sub"])
    except (_jwt.PyJWTError, KeyError, ValueError):
        return None


def _hash_refresh(token: str) -> str:
    """SHA-256 hex của refresh token (chỉ hash lưu DB)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _create_refresh_token(user: User, db: DBSession) -> str:
    """Sinh refresh token opaque, lưu hash vào DB, trả về raw token cho cookie."""
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=_hash_refresh(raw),
        expires_at=datetime.utcnow() + REFRESH_TOKEN_TTL,
    ))
    db.commit()
    return raw


def _lookup_refresh(token: str, db: DBSession) -> RefreshToken | None:
    """Tìm RefreshToken hợp lệ (chưa hết hạn, chưa revoke) theo raw token."""
    rec = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash_refresh(token)).first()
    if not rec or rec.revoked_at is not None or rec.expires_at <= datetime.utcnow():
        return None
    return rec


def _revoke_refresh(rec: RefreshToken, db: DBSession) -> None:
    rec.revoked_at = datetime.utcnow()
    db.commit()


# ─── Cookies ─────────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    # Xoá cookie cũ từ scheme session opaque (nếu còn)
    response.delete_cookie("session_id", path="/")


def _issue_tokens(user: User, response: Response, db: DBSession) -> None:
    """Cấp cặp access + refresh mới cho user và set cookies."""
    access = _encode_access_token(user.id)
    refresh = _create_refresh_token(user, db)
    _set_auth_cookies(response, access, refresh)


# ─── User helpers ────────────────────────────────────────────────────────────

def _user_to_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
    }


# ─── Login (local) ───────────────────────────────────────────────────────────

def login_user(identifier: str, password: str, response: Response, db: DBSession) -> dict:
    ident = identifier.strip()
    user = (
        db.query(User)
        .filter((User.username == ident) | (User.email == ident.lower()))
        .first()
    )
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu.")

    _issue_tokens(user, response, db)
    return {"message": "Đăng nhập thành công.", **_user_to_dict(user)}


# ─── Google OAuth ────────────────────────────────────────────────────────────

def _fetch_google_userinfo(access_token: str) -> dict:
    req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=401, detail=f"Google token không hợp lệ ({exc.code}).")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không gọi được Google: {exc}")


def _login_or_register_google(
    sub: str,
    email: str | None,
    full_name: str | None,
    avatar_url: str | None,
    *,
    create_if_missing: bool,
    db: DBSession,
) -> User:
    identity = (
        db.query(UserIdentity)
        .filter(UserIdentity.provider == "google", UserIdentity.provider_uid == sub)
        .first()
    )
    if identity:
        user = db.query(User).filter(User.id == identity.user_id).first()
        if not user:
            raise HTTPException(status_code=500, detail="Identity trỏ tới user không tồn tại.")
        return user

    user = db.query(User).filter(User.email == email).first() if email else None

    if not user:
        if not create_if_missing:
            raise HTTPException(
                status_code=404,
                detail="Tài khoản Google này chưa được đăng ký. Vui lòng dùng 'Đăng ký bằng Google'.",
            )
        user = User(
            username=None,
            password_hash=None,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
        )
        db.add(user)
        db.flush()
    else:
        if not user.full_name and full_name:
            user.full_name = full_name
        if not user.avatar_url and avatar_url:
            user.avatar_url = avatar_url

    db.add(UserIdentity(
        user_id=user.id,
        provider="google",
        provider_uid=sub,
        email=email,
    ))
    db.commit()
    db.refresh(user)
    return user


def google_login(access_token: str, response: Response, db: DBSession) -> dict:
    info = _fetch_google_userinfo(access_token)
    sub = info.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Google response thiếu 'sub'.")
    email = (info.get("email") or "").lower() or None

    user = _login_or_register_google(
        sub=sub,
        email=email,
        full_name=info.get("name"),
        avatar_url=info.get("picture"),
        create_if_missing=False,
        db=db,
    )
    _issue_tokens(user, response, db)
    return {"message": "Đăng nhập Google thành công.", **_user_to_dict(user)}


def google_register(access_token: str, response: Response, db: DBSession) -> dict:
    info = _fetch_google_userinfo(access_token)
    sub = info.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Google response thiếu 'sub'.")
    email = (info.get("email") or "").lower() or None

    existing = (
        db.query(UserIdentity)
        .filter(UserIdentity.provider == "google", UserIdentity.provider_uid == sub)
        .first()
    )
    already_existed = existing is not None

    user = _login_or_register_google(
        sub=sub,
        email=email,
        full_name=info.get("name"),
        avatar_url=info.get("picture"),
        create_if_missing=True,
        db=db,
    )
    _issue_tokens(user, response, db)
    return {
        "message": "Đăng nhập Google thành công." if already_existed else "Đăng ký Google thành công.",
        "already_existed": already_existed,
        **_user_to_dict(user),
    }


# ─── Refresh + Logout ────────────────────────────────────────────────────────

def refresh_tokens(refresh_token: str | None, response: Response, db: DBSession) -> dict:
    """
    Đổi refresh token lấy cặp access + refresh mới (rotate).
    Token cũ bị revoke; nếu refresh đã hết hạn / không tồn tại → 401.
    """
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Thiếu refresh token.")

    rec = _lookup_refresh(refresh_token, db)
    if not rec:
        # Xoá cookies cũ luôn để FE biết đường mà dừng retry
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token không hợp lệ hoặc hết hạn.")

    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại.")

    # Rotate: revoke token cũ, cấp token mới
    _revoke_refresh(rec, db)
    _issue_tokens(user, response, db)
    return {"message": "Đã làm mới phiên đăng nhập.", **_user_to_dict(user)}


def logout_user(refresh_token: str | None, response: Response, db: DBSession) -> dict:
    """Revoke refresh token (nếu có) + xoá cookies."""
    if refresh_token:
        rec = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash_refresh(refresh_token)).first()
        if rec and rec.revoked_at is None:
            _revoke_refresh(rec, db)
    _clear_auth_cookies(response)
    return {"message": "Đã đăng xuất."}


# ─── Dependency xác thực ─────────────────────────────────────────────────────

def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: DBSession = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập.")
    user_id = _decode_access_token(access_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập hết hạn hoặc không hợp lệ.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại.")
    return user


def get_optional_user(
    access_token: str | None = Cookie(default=None),
    db: DBSession = Depends(get_db),
) -> User | None:
    if not access_token:
        return None
    user_id = _decode_access_token(access_token)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()
