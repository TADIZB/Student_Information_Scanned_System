from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Session as SessionModel, User

# ─── Cấu hình ────────────────────────────────────────────────────────────────

SESSION_EXPIRE_HOURS = 24


# ─── Helpers ─────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    """Dùng khi tạo tài khoản mới."""
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


# ─── Login ───────────────────────────────────────────────────────────────────

def login_user(
    username: str,
    password: str,
    response: Response,
    db: DBSession,
) -> dict:
    """
    Kiểm tra username/password trong bảng users.
    Nếu đúng → tạo session_id (UUID hex), lưu vào bảng sessions,
    trả về qua Set-Cookie HttpOnly.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu.")

    # Tạo session mới
    session_id = uuid.uuid4().hex
    expires = datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS)
    session = SessionModel(session_id=session_id, user_id=user.id, expires_at=expires)
    db.add(session)
    db.commit()

    # Gắn cookie HttpOnly vào response – trình duyệt tự gửi lại mọi request
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,        # Đổi thành True khi triển khai HTTPS
        samesite="lax",
        max_age=SESSION_EXPIRE_HOURS * 3600,
        path="/",
    )
    return {"message": "Đăng nhập thành công.", "username": user.username}


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
