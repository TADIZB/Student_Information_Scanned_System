"""Pydantic schemas dùng chung cho các router."""
from __future__ import annotations

from pydantic import BaseModel


class LoginPayload(BaseModel):
    identifier: str         
    password: str


class MicrosoftLoginPayload(BaseModel):
    """Đăng nhập bằng tài khoản trường (Microsoft/HUST SSO) — xác thực qua sso.hust.edu.vn."""
    email: str               
    password: str


class RequestLocalOtpPayload(BaseModel):
    """Bước 1 đăng ký thường: kiểm tra username + email rồi gửi OTP về email."""
    username: str
    email: str


class RegisterLocalPayload(BaseModel):
    """Bước 2 đăng ký thường: xác minh OTP + tạo tài khoản (email bắt buộc)."""
    username: str
    email: str
    code: str
    password: str
    full_name: str | None = None
    birth_date: str | None = None


class ForgotPasswordPayload(BaseModel):
    """Bước 1 quên mật khẩu: nhập tên đăng nhập → gửi OTP về email đã đăng ký."""
    username: str


class ResetPasswordPayload(BaseModel):
    """Bước 2 quên mật khẩu: xác minh OTP + đặt lại mật khẩu mới."""
    username: str
    code: str
    password: str


class UpdateProfilePayload(BaseModel):
    """Sửa thông tin profile — chỉ những trường được phép."""
    full_name: str | None = None
    birth_date: str | None = None
