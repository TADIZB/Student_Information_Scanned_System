from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text, Uuid

from .database import Base


class User(Base):
    """Bảng users – tài khoản đăng nhập bằng email @hust.edu.vn HOẶC username thường.

    DB ràng buộc CHECK (username IS NOT NULL OR email IS NOT NULL) để đảm bảo
    có ít nhất một định danh.
    """

    __tablename__ = "users"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    full_name = Column(String(200), nullable=True)
    birth_date = Column(String(20), nullable=True)   # yyyy-mm-dd hoặc dd/mm/yyyy
    created_at = Column(DateTime, default=datetime.utcnow)


class Student(Base):
    """Bảng students – dữ liệu sinh viên gốc của trường (nguồn đối chiếu)."""

    __tablename__ = "students"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    student_id = Column(String(20), unique=True, nullable=False, index=True)  # MSSV
    full_name = Column(String(200), nullable=True)   # Họ tên / Name
    birth_date = Column(String(20), nullable=True)   # Ngày sinh / D.O.B
    school = Column(String(200), nullable=True)      # Trường, Viện
    email = Column(String(200), nullable=True)       # Email
    avatar_data = Column(LargeBinary, nullable=True) # Ảnh đại diện (BYTEA)
    avatar_mime = Column(String(20), nullable=True)  # MIME type ảnh đại diện
    created_at = Column(DateTime, default=datetime.utcnow)


class ScanHistory(Base):
    """Bảng scan_history – lưu kết quả thô sau mỗi lần quét."""

    __tablename__ = "scan_history"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_data = Column(LargeBinary, nullable=True)     # Ảnh đã warp lưu thẳng vào DB (BYTEA)
    image_mime = Column(String(20), nullable=True)      # MIME type, thường "image/png"
    raw_text = Column(Text, nullable=True)              # Toàn bộ text OCR nhận được
    qr_data = Column(Text, nullable=True)               # Data từ QR code (nếu có)
    scan_type = Column(String(10), nullable=True)       # "qr" hoặc "ocr"
    match_result = Column(Integer, nullable=True)       # null=N/A, 0=không khớp, 1=khớp
    matched_student_id = Column(                        # FK tới bảng students nếu khớp
        Uuid(),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)


class StudentCard(Base):
    """Bảng student_cards – snapshot thông tin sinh viên tại thời điểm quét."""

    __tablename__ = "student_cards"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    scan_id = Column(Uuid(), ForeignKey("scan_history.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(200), nullable=True)    # Họ tên / Name
    birth_date = Column(String(20), nullable=True)    # Ngày sinh / D.O.B (dd/mm/yyyy)
    school = Column(String(200), nullable=True)       # Trường, Viện
    student_id = Column(String(20), nullable=True)    # Mã số sinh viên / ID No.
    email = Column(String(200), nullable=True)        # Email
    avatar_data = Column(LargeBinary, nullable=True)  # Ảnh đại diện lưu thẳng vào DB (BYTEA)
    avatar_mime = Column(String(20), nullable=True)   # MIME type ảnh đại diện
    created_at = Column(DateTime, default=datetime.utcnow)
