"""Router xuất thẻ sinh viên PDF."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from ..auth import get_current_user
from ..card_pdf import build_card_pdf
from ..database import get_db
from ..models import ScanHistory, Student, StudentCard, User

router = APIRouter(tags=["export"])


@router.get("/export-card/{scan_id}")
def export_card(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    record = (
        db.query(ScanHistory)
        .filter(ScanHistory.id == scan_id, ScanHistory.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi.")

    card = db.query(StudentCard).filter(StudentCard.scan_id == scan_id).first()

    # Ưu tiên avatar từ bảng students nếu đã khớp
    avatar_bytes: bytes | None = None
    if record.matched_student_id:
        student = db.query(Student).filter(Student.id == record.matched_student_id).first()
        if student:
            avatar_bytes = student.avatar_data
    if not avatar_bytes and card:
        avatar_bytes = card.avatar_data

    try:
        pdf_bytes = build_card_pdf(
            full_name=card.full_name if card else None,
            birth_date=card.birth_date if card else None,
            school=card.school if card else None,
            student_id=card.student_id if card else None,
            email=card.email if card else None,
            avatar_bytes=avatar_bytes,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo PDF: {exc}") from exc

    filename = f"the_sv_{scan_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
