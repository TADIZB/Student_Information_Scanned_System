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
