"""Load an image file into students.avatar_data by student ID.

Usage, from the backend directory:
    python -m app.scripts.add_avatar <MSSV> "<image_path>"
"""
from __future__ import annotations

import mimetypes
import sys
from pathlib import Path
from typing import List, Optional

from app.database import SessionLocal
from app.models import Student


def detect_mime(path: Path, data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return mimetypes.guess_type(str(path))[0] or "image/jpeg"


def add_student_avatar(student_id: str, image_path: Path) -> None:
    data = image_path.read_bytes()
    if not data:
        raise ValueError("Image file is empty.")

    mime = detect_mime(image_path, data)

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_id == student_id).first()
        if not student:
            raise LookupError(f"Student with MSSV '{student_id}' was not found.")

        student.avatar_data = data
        student.avatar_mime = mime
        db.commit()
        print(f"Loaded {len(data)} bytes ({mime}) for MSSV {student_id} - {student.full_name}.")
    finally:
        db.close()


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print('Usage: python -m app.scripts.add_avatar <MSSV> "<image_path>"')
        return 2

    student_id = args[0].strip()
    image_path = Path(args[1])

    try:
        add_student_avatar(student_id, image_path)
        return 0
    except (OSError, ValueError, LookupError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
