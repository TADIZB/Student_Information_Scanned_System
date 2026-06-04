from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text, Uuid

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
    birth_date = Column(String(20), nullable=True)
    avatar_data = Column(LargeBinary, nullable=True)
    avatar_mime = Column(String(20), nullable=True)
    # Đánh dấu email đã được xác thực qua OTP (tài khoản trường luôn = True sau verify).
    email_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailOtp(Base):
    """Bảng email_otps – mã OTP đang chờ xác thực khi đăng ký tài khoản trường.

    Chỉ lưu BĂM (sha256) của mã, không bao giờ lưu mã thô. Mỗi mã có hạn dùng
    (expires_at), giới hạn số lần thử (attempts) và dùng-một-lần (xoá sau khi đúng).
    """

    __tablename__ = "email_otps"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    email = Column(String(200), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)   # sha256 hex của mã 6 số
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Student(Base):
    """Bảng students – dữ liệu sinh viên gốc của trường (nguồn đối chiếu)."""

    __tablename__ = "students"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    student_id = Column(String(20), unique=True, nullable=False, index=True)  
    full_name = Column(String(200), nullable=True)   
    birth_date = Column(String(20), nullable=True)  
    school = Column(String(200), nullable=True)      
    email = Column(String(200), nullable=True)       
    study_status = Column(Integer, nullable=True)    
    avatar_data = Column(LargeBinary, nullable=True) 
    avatar_mime = Column(String(20), nullable=True)  
    created_at = Column(DateTime, default=datetime.utcnow)


class ScanHistory(Base):
    """Bảng scan_history – lưu kết quả thô sau mỗi lần quét."""

    __tablename__ = "scan_history"

    id = Column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_data = Column(LargeBinary, nullable=True)     
    image_mime = Column(String(20), nullable=True)     
    raw_text = Column(Text, nullable=True)             
    qr_data = Column(Text, nullable=True)              
    scan_type = Column(String(10), nullable=True)      
    match_result = Column(Integer, nullable=True)       
    matched_student_id = Column(                       
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
    full_name = Column(String(200), nullable=True)
    birth_date = Column(String(20), nullable=True)
    school = Column(String(200), nullable=True)
    student_id = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    study_status = Column(Integer, nullable=True)  
    created_at = Column(DateTime, default=datetime.utcnow)
