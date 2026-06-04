"""Test parser QR — đảm bảo bóc MSSV/họ tên đúng từ cả 3 dạng input."""
from __future__ import annotations

import sys
from pathlib import Path

# Cho phép import `app.*` khi chạy pytest từ thư mục backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.scan import _parse_qr_mssv  


def test_parse_qr_url_hust():
    """Dạng URL chính thức của HUST: ctsv.hust.edu.vn/#/card/<MSSV>/<HO_TEN>/<token>."""
    qr = "https://ctsv.hust.edu.vn/#/card/20210001/NGUYEN_VAN_A/abcdef"
    result = _parse_qr_mssv(qr)
    assert result["student_id"] == "20210001"
    assert result["full_name"] == "Nguyen Van A"  
    assert result["school"] == "Đại học Bách khoa Hà Nội"


def test_parse_qr_key_value():
    """Dạng key-value 'MSSV:...|HoTen:...|Truong:...'"""
    qr = "MSSV:20210002|HoTen:Tran Thi B|Truong:DHBK|Email:b@hust.edu.vn"
    result = _parse_qr_mssv(qr)
    assert result["student_id"] == "20210002"
    assert result["full_name"] == "Tran Thi B"
    assert result["school"] == "DHBK"
    assert result["email"] == "b@hust.edu.vn"


def test_parse_qr_plain_string():
    """Chuỗi thuần chỉ chứa MSSV (8 chữ số)."""
    qr = "20210003"
    result = _parse_qr_mssv(qr)
    assert result["student_id"] == "20210003"
    assert result["full_name"] is None
