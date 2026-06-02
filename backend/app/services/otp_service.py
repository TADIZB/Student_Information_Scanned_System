"""Sinh / xác minh mã OTP cho đăng ký tài khoản trường.

Nguyên tắc bảo mật:
- KHÔNG lưu mã thô — chỉ lưu sha256 của mã.
- Mã có hạn (OTP_TTL_MINUTES) + dùng một lần (xoá sau khi đúng).
- Giới hạn số lần thử sai (MAX_ATTEMPTS) để chống dò mã.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from ..models import EmailOtp

OTP_TTL_MINUTES = 10        # mã hết hạn sau 10 phút
MAX_ATTEMPTS = 5            # tối đa 5 lần nhập sai


def generate_code() -> str:
    """Mã 6 số ngẫu nhiên an toàn (000000–999999)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def create_otp(db: DBSession, email: str) -> str:
    """Tạo (thay thế) OTP cho email. Trả về mã thô để gửi mail (không lưu thô)."""
    # Một email chỉ có một OTP hiệu lực — xoá mã cũ trước.
    db.query(EmailOtp).filter(EmailOtp.email == email).delete()
    code = generate_code()
    otp = EmailOtp(
        email=email,
        code_hash=hash_code(code),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
        attempts=0,
    )
    db.add(otp)
    db.commit()
    return code


def verify_otp(db: DBSession, email: str, code: str) -> None:
    """Kiểm tra mã. Đúng → xoá OTP (dùng một lần). Sai → raise HTTPException."""
    otp = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email)
        .order_by(EmailOtp.created_at.desc())
        .first()
    )
    if not otp:
        raise HTTPException(
            status_code=422,
            detail="Bạn chưa yêu cầu mã xác nhận hoặc mã đã hết hiệu lực. Vui lòng gửi lại mã.",
        )

    if datetime.utcnow() > otp.expires_at:
        db.delete(otp)
        db.commit()
        raise HTTPException(status_code=422, detail="Mã xác nhận đã hết hạn. Vui lòng gửi lại mã.")

    if otp.attempts >= MAX_ATTEMPTS:
        db.delete(otp)
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="Bạn đã nhập sai quá nhiều lần. Vui lòng gửi lại mã mới.",
        )

    if otp.code_hash != hash_code(code):
        otp.attempts += 1
        remaining = MAX_ATTEMPTS - otp.attempts
        db.commit()
        if remaining <= 0:
            raise HTTPException(
                status_code=429,
                detail="Bạn đã nhập sai quá nhiều lần. Vui lòng gửi lại mã mới.",
            )
        raise HTTPException(
            status_code=422,
            detail=f"Mã xác nhận không đúng. Bạn còn {remaining} lần thử.",
        )

    # Đúng → dùng một lần rồi xoá.
    db.delete(otp)
    db.commit()
