from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .database import Base


class User(Base):
    """Bảng users – tài khoản đăng nhập (hỗ trợ local + OAuth)."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=True)        # nullable: user Google có thể không có
    password_hash = Column(String(255), nullable=True)                # nullable: user OAuth không có mật khẩu
    email = Column(String(200), unique=True, nullable=True)
    full_name = Column(String(200), nullable=True)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserIdentity(Base):
    """Bảng user_identities – liên kết provider OAuth với user."""

    __tablename__ = "user_identities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(20), nullable=False)        # 'google' | 'local' | ...
    provider_uid = Column(String(255), nullable=False)   # Google "sub"
    email = Column(String(200), nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    """Bảng sessions – lưu session_id và thời hạn."""

    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class Student(Base):
    """Bảng students – dữ liệu sinh viên gốc của trường (nguồn đối chiếu)."""

    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_data = Column(LargeBinary, nullable=True)     # Ảnh đã warp lưu thẳng vào DB (BYTEA)
    image_mime = Column(String(20), nullable=True)      # MIME type, thường "image/png"
    raw_text = Column(Text, nullable=True)              # Toàn bộ text OCR nhận được
    qr_data = Column(Text, nullable=True)               # Data từ QR code (nếu có)
    scan_type = Column(String(10), nullable=True)       # "qr" hoặc "ocr"
    match_result = Column(Integer, nullable=True)       # null=N/A, 0=không khớp, 1=khớp
    matched_student_id = Column(                        # FK tới bảng students nếu khớp
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)


class StudentCard(Base):
    """Bảng student_cards – snapshot thông tin sinh viên tại thời điểm quét."""

    __tablename__ = "student_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id = Column(UUID(as_uuid=True), ForeignKey("scan_history.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(200), nullable=True)    # Họ tên / Name
    birth_date = Column(String(20), nullable=True)    # Ngày sinh / D.O.B (dd/mm/yyyy)
    school = Column(String(200), nullable=True)       # Trường, Viện
    student_id = Column(String(20), nullable=True)    # Mã số sinh viên / ID No.
    email = Column(String(200), nullable=True)        # Email
    avatar_data = Column(LargeBinary, nullable=True)  # Ảnh đại diện lưu thẳng vào DB (BYTEA)
    avatar_mime = Column(String(20), nullable=True)   # MIME type ảnh đại diện
    created_at = Column(DateTime, default=datetime.utcnow)
