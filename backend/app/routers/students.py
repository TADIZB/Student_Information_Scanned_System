"""Router tra cứu sinh viên + serve ảnh đại diện từ bảng students."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session as DBSession

from ..auth import get_optional_user
from ..database import get_db
from ..models import ScanHistory, Student, StudentCard, User
from ..services.student_matching import _student_to_dict

router = APIRouter(tags=["students"])


@router.get("/students/lookup")
def lookup_student(
    student_id: str = Query(..., description="Mã số sinh viên cần tra cứu"),
    current_user: User | None = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
):
    """Tra cứu thông tin sinh viên từ bảng students theo MSSV. Lưu lịch sử nếu đã đăng nhập."""
    student = db.query(Student).filter(Student.student_id == student_id.strip()).first()
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên với MSSV này.")

    result = _student_to_dict(student)
    scan_id: str | None = None

    if current_user:
        scan_record = ScanHistory(
            user_id=current_user.id,
            image_data=None,
            image_mime=None,
            qr_data=None,
            raw_text=None,
            scan_type="lookup",
            match_result=1,
            matched_student_id=student.id,
        )
        db.add(scan_record)
        db.flush()
        db.add(StudentCard(
            scan_id=scan_record.id,
            user_id=current_user.id,
            full_name=student.full_name,
            birth_date=student.birth_date,
            school=student.school,
            student_id=student.student_id,
            email=student.email,
            study_status=student.study_status,
        ))
        db.commit()
        scan_id = str(scan_record.id)

    return {**result, "scan_id": scan_id}


# ─── Serve ảnh đại diện từ bảng students ─────────────────────────────────────

@router.get("/images/avatar/student/{student_uuid}")
def get_student_avatar(student_uuid: str, db: DBSession = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_uuid).first()
    if not student or not student.avatar_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh.")
    return Response(content=student.avatar_data, media_type=student.avatar_mime or "image/jpeg")
