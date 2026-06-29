"""Test hash/verify password + validate email HUST + common password check."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Cho phép import `app.*` khi chạy pytest từ thư mục backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth as auth_module  # noqa: E402


def test_hash_and_verify_password():
    plain = "matkhau-cuc-manh-2026"
    hashed = auth_module.hash_password(plain)
    assert auth_module.verify_password(plain, hashed) is True
    assert auth_module.verify_password("wrong-password", hashed) is False


def test_verify_handles_bad_hash():
    """verify_password không crash khi hash bị hỏng — trả False."""
    assert auth_module.verify_password("x", "not-a-bcrypt-hash") is False
    assert auth_module.verify_password("x", "") is False


def test_is_common_password():
    assert auth_module.is_common_password("123456") is True
    assert auth_module.is_common_password("Password") is True 
    assert auth_module.is_common_password("matkhau-cuc-manh-2026") is False


def test_validate_password_strength_too_short():
    with pytest.raises(HTTPException) as exc:
        auth_module.validate_password_strength("abc12")
    assert exc.value.status_code == 422


def test_validate_password_strength_common():
    with pytest.raises(HTTPException) as exc:
        auth_module.validate_password_strength("password")
    assert exc.value.status_code == 422


def test_validate_password_strength_ok():
    auth_module.validate_password_strength("matkhau-cuc-manh-2026")


def test_is_hust_email():
    assert auth_module.is_hust_email("abc@sis.hust.edu.vn") is True
    assert auth_module.is_hust_email("abc.def@SIS.HUST.EDU.VN") is True
    assert auth_module.is_hust_email("abc@hust.edu.vn") is True
    assert auth_module.is_hust_email("abc@HUST.EDU.VN") is True
    assert auth_module.is_hust_email("abc@gmail.com") is False
    assert auth_module.is_hust_email("abc@xsis.hust.edu.vn") is False
    assert auth_module.is_hust_email("@sis.hust.edu.vn") is False
