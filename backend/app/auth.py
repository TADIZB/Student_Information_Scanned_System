"""Auth tối giản: 2 cách đăng ký (email @hust.edu.vn hoặc username) + cookie user_id.

Không JWT, không refresh token, không sessions DB, không Google OAuth, không pepper.
Mật khẩu: bcrypt thuần + check độ dài tối thiểu + chặn mật khẩu phổ biến.
"""
from __future__ import annotations

import re
import secrets
import uuid

import bcrypt as _bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import User

# ─── Cấu hình ────────────────────────────────────────────────────────────────

HUST_EMAIL_DOMAIN = "@sis.hust.edu.vn"
_HUST_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@sis\.hust\.edu\.vn$", re.IGNORECASE)

# Email thường (dùng cho tài khoản thường + quên mật khẩu): định dạng email hợp lệ chung.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# Username: 3-50 ký tự, chỉ chữ/số/._-
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")

COOKIE_NAME = "user_id"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 ngày


def is_hust_email(s: str) -> bool:
    return bool(_HUST_EMAIL_RE.match(s.strip()))


def is_valid_username(s: str) -> bool:
    return bool(_USERNAME_RE.match(s.strip()))


def is_valid_email(s: str) -> bool:
    return bool(_EMAIL_RE.match(s.strip()))


# ─── Mật khẩu ────────────────────────────────────────────────────────────────

_COMMON_PASSWORDS = {
    "123456", "password", "12345678", "qwerty", "abc123", "111111", "123123",
    "admin", "letmein", "welcome", "password1", "iloveyou", "000000", "matkhau",
    "123456789", "1234567890", "12345", "1q2w3e4r", "p@ssw0rd",
}


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode())
    except (ValueError, TypeError):
        return False


def is_common_password(plain: str) -> bool:
    return plain.lower() in _COMMON_PASSWORDS


def validate_password_strength(plain: str) -> None:
    if len(plain) < 6:
        raise HTTPException(status_code=422, detail="Mật khẩu phải có ít nhất 6 ký tự.")
    if is_common_password(plain):
        raise HTTPException(
            status_code=422,
            detail="Mật khẩu quá phổ biến, dễ bị đoán. Vui lòng chọn mật khẩu khác.",
        )


# ─── Cookie helpers ──────────────────────────────────────────────────────────

def _set_user_cookie(response: Response, user_id: uuid.UUID) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=str(user_id),
        httponly=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


def _clear_user_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _user_to_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "birth_date": user.birth_date,
    }


# Register 

def validate_local_register(username: str, email: str, db: DBSession) -> tuple[str, str]:
    """Kiểm tra tên đăng nhập + email (bắt buộc) cho tài khoản thường.

    Trả về (username_norm, email_norm) đã chuẩn hoá. Raise nếu sai định dạng
    hoặc đã bị dùng. Dùng chung cho bước xin OTP và bước xác minh tạo tài khoản.
    """
    uname = username.strip()
    email_norm = email.strip().lower()
    if not is_valid_username(uname):
        raise HTTPException(
            status_code=422,
            detail="Tên đăng nhập phải dài 3-50 ký tự, chỉ gồm chữ/số/dấu chấm/gạch dưới/gạch ngang.",
        )
    if not is_valid_email(email_norm):
        raise HTTPException(status_code=422, detail="Email không hợp lệ.")
    if db.query(User).filter(User.username == uname).first():
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=409, detail="Email đã được sử dụng.")
    return uname, email_norm


def register_local(
    username: str,
    email: str,
    password: str,
    full_name: str | None,
    birth_date: str | None,
    response: Response,
    db: DBSession,
) -> dict:
    """Đăng ký bằng username thường + email (đã xác thực OTP). Tự set cookie."""
    uname, email_norm = validate_local_register(username, email, db)
    validate_password_strength(password)

    user = User(
        username=uname,
        email=email_norm,
        password_hash=hash_password(password),
        full_name=(full_name or "").strip() or None,
        birth_date=(birth_date or "").strip() or None,
        email_verified=True,  
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_user_cookie(response, user.id)
    return {"message": "Đăng ký thành công.", **_user_to_dict(user)}


def reset_user_password(email: str, new_password: str, db: DBSession) -> User:
    """Đặt lại mật khẩu cho tài khoản có email tương ứng (sau khi xác minh OTP)."""
    email_norm = email.strip().lower()
    validate_password_strength(new_password)
    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản với email này.")
    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


# Login / Logout 

def login_user(
    identifier: str,
    password: str,
    response: Response,
    db: DBSession,
) -> dict:
    """Đăng nhập bằng email HUST hoặc username — tự detect theo dấu '@'."""
    ident = identifier.strip()
    if not ident:
        raise HTTPException(status_code=422, detail="Vui lòng nhập tài khoản.")

    if "@" in ident:
        ident_lower = ident.lower()
        user = db.query(User).filter(User.email == ident_lower).first()
    else:
        user = db.query(User).filter(User.username == ident).first()

    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu.")

    _set_user_cookie(response, user.id)
    return {"message": "Đăng nhập thành công.", **_user_to_dict(user)}


def get_or_create_hust_user(email: str, db: DBSession) -> User:
    """Tìm (hoặc tạo) tài khoản ứng với email HUST đã xác thực qua SSO Microsoft.

    Mật khẩu được đặt là chuỗi ngẫu nhiên (người dùng đăng nhập bằng tài khoản
    trường nên không dùng tới); email_verified=True vì đã qua SSO của trường.
    """
    email_norm = email.strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()
    if user:
        return user

    # Gợi ý username từ phần trước @, bỏ trống nếu trùng (CHECK vẫn thỏa vì có email).
    candidate = email_norm.split("@", 1)[0][:50] or None
    if candidate and db.query(User).filter(User.username == candidate).first():
        candidate = None

    user = User(
        username=candidate,
        email=email_norm,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_hust_user(email: str, response: Response, db: DBSession) -> dict:
    """Hoàn tất đăng nhập Microsoft/HUST: upsert user theo email rồi set cookie.

    Việc xác thực mật khẩu với SSO (Playwright) được làm ở router trước khi gọi
    hàm này — tới đây nghĩa là thông tin đăng nhập đã hợp lệ.
    """
    user = get_or_create_hust_user(email, db)
    _set_user_cookie(response, user.id)
    return {"message": "Đăng nhập thành công.", **_user_to_dict(user)}


def logout_user(response: Response) -> dict:
    _clear_user_cookie(response)
    return {"message": "Đã đăng xuất."}


# Dependency xác thực 

def get_current_user(
    user_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: DBSession = Depends(get_db),
) -> User:
    if not user_id:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập.")
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ.")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại.")
    return user


def get_optional_user(
    user_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: DBSession = Depends(get_db),
) -> User | None:
    if not user_id:
        return None
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    return db.query(User).filter(User.id == uid).first()
