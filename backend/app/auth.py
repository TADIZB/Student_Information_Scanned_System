from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Session as SessionModel, User, UserIdentity

# ─── Cấu hình ────────────────────────────────────────────────────────────────

SESSION_EXPIRE_HOURS = 24
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    """Dùng khi tạo tài khoản mới."""
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _create_session(user: User, response: Response, db: DBSession) -> str:
    """Tạo session mới cho user, set cookie HttpOnly, trả về session_id."""
    session_id = uuid.uuid4().hex
    expires = datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS)
    db.add(SessionModel(session_id=session_id, user_id=user.id, expires_at=expires))
    db.commit()

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,        # Đổi True khi triển khai HTTPS
        samesite="lax",
        max_age=SESSION_EXPIRE_HOURS * 3600,
        path="/",
    )
    return session_id


def _user_to_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
    }


# ─── Login (local: username hoặc email + password) ───────────────────────────

def login_user(
    identifier: str,
    password: str,
    response: Response,
    db: DBSession,
) -> dict:
    """
    `identifier` có thể là username HOẶC email.
    Nếu khớp + password đúng → tạo session, set cookie.
    """
    ident = identifier.strip()
    user = (
        db.query(User)
        .filter((User.username == ident) | (User.email == ident.lower()))
        .first()
    )
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu.")

    _create_session(user, response, db)
    return {"message": "Đăng nhập thành công.", **_user_to_dict(user)}


# ─── Google OAuth helpers ────────────────────────────────────────────────────

def _fetch_google_userinfo(access_token: str) -> dict:
    """Gọi Google UserInfo endpoint để lấy {sub, email, name, picture}."""
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
    """
    Trả về User dựa trên thông tin Google.
    - create_if_missing=True (luồng "Đăng ký"): chưa có thì tạo mới; đã có thì vẫn cho đăng nhập.
    - create_if_missing=False (luồng "Đăng nhập"): chưa có thì báo lỗi 404.
    """
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

    # Thử link theo email
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
    """Luồng 'Đăng nhập bằng Google': chỉ cho phép user đã từng đăng ký."""
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
    _create_session(user, response, db)
    return {"message": "Đăng nhập Google thành công.", **_user_to_dict(user)}


def google_register(access_token: str, response: Response, db: DBSession) -> dict:
    """Luồng 'Đăng ký bằng Google': tạo user nếu chưa có; đã có thì vẫn đăng nhập."""
    info = _fetch_google_userinfo(access_token)
    sub = info.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Google response thiếu 'sub'.")
    email = (info.get("email") or "").lower() or None

    # Đã có identity → coi như đăng nhập, báo cho FE biết
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
    _create_session(user, response, db)
    return {
        "message": "Đăng nhập Google thành công." if already_existed else "Đăng ký Google thành công.",
        "already_existed": already_existed,
        **_user_to_dict(user),
    }


# ─── Dependency xác thực ─────────────────────────────────────────────────────

def get_current_user(
    session_id: str | None = Cookie(default=None),
    db: DBSession = Depends(get_db),
) -> User:
    """Bắt buộc đăng nhập. Ném 401 nếu không có session hợp lệ."""
    if not session_id:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập.")

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.session_id == session_id,
            SessionModel.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập hết hạn hoặc không hợp lệ.")

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại.")

    return user


def get_optional_user(
    session_id: str | None = Cookie(default=None),
    db: DBSession = Depends(get_db),
) -> User | None:
    """Không bắt buộc đăng nhập. Trả về User nếu có session hợp lệ, None nếu không."""
    if not session_id:
        return None
    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.session_id == session_id,
            SessionModel.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not session:
        return None
    return db.query(User).filter(User.id == session.user_id).first()
