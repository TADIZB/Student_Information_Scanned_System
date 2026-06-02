"""Router xử lý đăng ký / đăng nhập / đăng xuất."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DBSession

from ..auth import (
    HUST_EMAIL_DOMAIN,
    get_current_user,
    is_hust_email,
    login_user,
    logout_user,
    register_hust,
    register_local,
)
from ..database import get_db
from ..middleware.rate_limit import _client_ip, enforce_otp_rate_limit
from ..models import User
from ..schemas import (
    LoginPayload,
    RegisterLocalPayload,
    RequestHustOtpPayload,
    VerifyHustOtpPayload,
)
from ..services.email_sender import send_otp_email
from ..services.otp_service import OTP_TTL_MINUTES, create_otp, verify_otp

router = APIRouter(tags=["auth"])


@router.post("/register/hust/request-otp")
def request_hust_otp(
    payload: RequestHustOtpPayload, request: Request, db: DBSession = Depends(get_db)
):
    """Bước 1: kiểm tra email trường, chống trùng tài khoản, gửi mã OTP về hộp thư."""
    email = payload.email.strip().lower()
    if not is_hust_email(email):
        raise HTTPException(
            status_code=422,
            detail=f"Email phải có đuôi {HUST_EMAIL_DOMAIN} (email trường Bách Khoa).",
        )
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email đã được sử dụng.")

    enforce_otp_rate_limit(email, _client_ip(request))

    code = create_otp(db, email)
    send_otp_email(email, code)
    return {
        "message": "Đã gửi mã xác nhận tới email của bạn.",
        "expires_in": OTP_TTL_MINUTES * 60,
    }


@router.post("/register/hust/verify-otp", status_code=201)
def verify_hust_otp(
    payload: VerifyHustOtpPayload, response: Response, db: DBSession = Depends(get_db)
):
    """Bước 2: xác minh mã rồi tạo tài khoản + set cookie đăng nhập."""
    email = payload.email.strip().lower()
    if not is_hust_email(email):
        raise HTTPException(
            status_code=422,
            detail=f"Email phải có đuôi {HUST_EMAIL_DOMAIN} (email trường Bách Khoa).",
        )
    verify_otp(db, email, payload.code)
    return register_hust(
        email, payload.password, payload.full_name, payload.birth_date, response, db
    )


@router.post("/register/local", status_code=201)
def register_local_route(
    payload: RegisterLocalPayload, response: Response, db: DBSession = Depends(get_db)
):
    return register_local(
        payload.username, payload.password, payload.full_name, payload.birth_date, response, db
    )


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
