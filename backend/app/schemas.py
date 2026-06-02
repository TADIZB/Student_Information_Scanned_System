"""Pydantic schemas dùng chung cho các router."""
from __future__ import annotations

from pydantic import BaseModel


class LoginPayload(BaseModel):
    identifier: str           # email HUST hoặc username thường
    password: str


class RegisterHustPayload(BaseModel):
    """Đăng ký bằng tài khoản trường (email @sis.hust.edu.vn)."""
    email: str
    password: str
    full_name: str | None = None
    birth_date: str | None = None   # ISO yyyy-mm-dd hoặc dd/mm/yyyy


class RequestHustOtpPayload(BaseModel):
    """Bước 1 đăng ký trường: xin mã OTP gửi về email @sis.hust.edu.vn."""
    email: str


class VerifyHustOtpPayload(BaseModel):
    """Bước 2 đăng ký trường: xác minh mã + tạo tài khoản."""
    email: str
    code: str
    password: str
    full_name: str | None = None
    birth_date: str | None = None


class RegisterLocalPayload(BaseModel):
    """Đăng ký bằng username thường (không cần email)."""
    username: str
    password: str
    full_name: str | None = None
    birth_date: str | None = None


class UpdateProfilePayload(BaseModel):
    """Sửa thông tin profile — chỉ những trường được phép."""
    full_name: str | None = None
    birth_date: str | None = None
