"""Nạp một ảnh từ máy vào students.avatar_data (BYTEA) theo MSSV.

Cách dùng (chạy trong thư mục backend, đã activate .venv):
    python add_avatar.py <MSSV> "<đường_dẫn_ảnh>"
Ví dụ:
    python add_avatar.py 20225814 "D:\\Coding\\anh_sv.jpg"

Lưu ý: sinh viên (MSSV) phải đã tồn tại trong bảng students.
"""
from __future__ import annotations

import mimetypes
import sys

from app.database import SessionLocal
from app.models import Student


def _detect_mime(path: str, data: bytes) -> str:
    """Suy ra MIME: ưu tiên magic bytes, sau đó tới đuôi file."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return mimetypes.guess_type(path)[0] or "image/jpeg"


def main() -> int:
    if len(sys.argv) != 3:
        print('Cách dùng: python add_avatar.py <MSSV> "<đường_dẫn_ảnh>"')
        return 2

    mssv, path = sys.argv[1].strip(), sys.argv[2]

    try:
        with open(path, "rb") as f:        # "rb" = đọc bytes thô
            data = f.read()
    except OSError as exc:
        print(f"Không đọc được file: {exc}")
        return 1

    if not data:
        print("File rỗng.")
        return 1

    mime = _detect_mime(path, data)

    db = SessionLocal()
    try:
        sv = db.query(Student).filter(Student.student_id == mssv).first()
        if not sv:
            print(f"Không tìm thấy sinh viên có MSSV '{mssv}'. Hãy chạy INSERT trước.")
            return 1
        sv.avatar_data = data
        sv.avatar_mime = mime
        db.commit()
        print(f"Đã nạp ảnh {len(data)} bytes ({mime}) cho MSSV {mssv} — {sv.full_name}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
