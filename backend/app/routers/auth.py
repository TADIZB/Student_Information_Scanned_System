"""Router xử lý đăng ký / đăng nhập / đăng xuất."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DBSession

from ..auth import (
    get_current_user,
    login_user,
    logout_user,
    register_local,
    reset_user_password,
    validate_local_register,
)
from ..database import get_db
from ..middleware.rate_limit import _client_ip, enforce_otp_rate_limit
from ..models import User
from ..schemas import (
    ForgotPasswordPayload,
    LoginPayload,
    RegisterLocalPayload,
    RequestLocalOtpPayload,
    ResetPasswordPayload,
)
from ..services.email_sender import send_otp_email
from ..services.otp_service import OTP_TTL_MINUTES, create_otp, verify_otp

router = APIRouter(tags=["auth"])


@router.post("/register/local/request-otp")
def request_local_otp(
    payload: RequestLocalOtpPayload, request: Request, db: DBSession = Depends(get_db)
):
    """Bước 1 đăng ký thường: validate username + email (bắt buộc) rồi gửi OTP về email."""
    email = payload.email.strip().lower()
    # Kiểm tra username/email hợp lệ & chưa bị dùng trước khi tốn 1 lần gửi mail.
    validate_local_register(payload.username, email, db)

    enforce_otp_rate_limit(email, _client_ip(request))

    code = create_otp(db, email)
    send_otp_email(email, code, purpose="register")
    return {
        "message": "Đã gửi mã xác nhận tới email của bạn.",
        "expires_in": OTP_TTL_MINUTES * 60,
    }


@router.post("/register/local/verify-otp", status_code=201)
def verify_local_otp(
    payload: RegisterLocalPayload, response: Response, db: DBSession = Depends(get_db)
):
    """Bước 2 đăng ký thường: xác minh mã rồi tạo tài khoản + set cookie."""
    email = payload.email.strip().lower()
    # Validate lại (username/email có thể đã bị người khác chiếm trong lúc chờ).
    validate_local_register(payload.username, email, db)
    verify_otp(db, email, payload.code)
    return register_local(
        payload.username,
        payload.email,
        payload.password,
        payload.full_name,
        payload.birth_date,
        response,
        db,
    )


def _find_user_for_reset(username: str, db: DBSession) -> User:
    """Tìm tài khoản theo tên đăng nhập để khôi phục mật khẩu (phải có email đăng ký)."""
    uname = username.strip()
    if not uname:
        raise HTTPException(status_code=422, detail="Vui lòng nhập tên đăng nhập.")
    user = db.query(User).filter(User.username == uname).first()
    if not user:
        raise HTTPException(status_code=404, detail="Tài khoản không tồn tại.")
    if not user.email:
        raise HTTPException(
            status_code=422,
            detail="Tài khoản này chưa có email đăng ký nên không thể khôi phục mật khẩu.",
        )
    return user


@router.post("/password/forgot/request-otp")
def request_password_reset_otp(
    payload: ForgotPasswordPayload, request: Request, db: DBSession = Depends(get_db)
):
    """Quên mật khẩu - Bước 1: nhập tên đăng nhập → gửi OTP về email đã đăng ký của tài khoản."""
    user = _find_user_for_reset(payload.username, db)

    enforce_otp_rate_limit(user.email, _client_ip(request))

    code = create_otp(db, user.email)
    send_otp_email(user.email, code, purpose="reset")
    return {
        "message": "Đã gửi mã xác nhận đến email đăng ký.",
        "expires_in": OTP_TTL_MINUTES * 60,
    }


@router.post("/password/reset")
def reset_password(payload: ResetPasswordPayload, db: DBSession = Depends(get_db)):
    """Quên mật khẩu - Bước 2: xác minh OTP (theo email của tài khoản) rồi đặt lại mật khẩu."""
    user = _find_user_for_reset(payload.username, db)
    verify_otp(db, user.email, payload.code)
    reset_user_password(user.email, payload.password, db)
    return {"message": "Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại."}


@router.post("/login")
def login(payload: LoginPayload, response: Response, db: DBSession = Depends(get_db)):
    return login_user(payload.identifier, payload.password, response, db)


@router.post("/logout")
def logout(response: Response):
    return logout_user(response)


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "birth_date": current_user.birth_date,
    }
