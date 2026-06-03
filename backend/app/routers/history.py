"""Router lịch sử quét + serve ảnh từ scan_history / student_cards."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from ..auth import get_current_user
from ..database import get_db
from ..models import ScanHistory, StudentCard, User

router = APIRouter(tags=["history"])


# Serve ảnh từ scan_history / student_cards

@router.get("/images/scan/{scan_id}")
def get_scan_image(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    record = (
        db.query(ScanHistory)
        .filter(ScanHistory.id == scan_id, ScanHistory.user_id == current_user.id)
        .first()
    )
    if not record or not record.image_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh.")
    return Response(content=record.image_data, media_type=record.image_mime or "image/png")


# Lịch sử quét

@router.get("/scan-history")
def scan_history(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    records = (
        db.query(ScanHistory)
        .filter(ScanHistory.user_id == current_user.id)
        .order_by(ScanHistory.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "scan_type": r.scan_type,
            "match_result": r.match_result,
            "image_url": f"/images/scan/{r.id}" if r.image_data else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@router.get("/scan-history/{scan_id}")
def scan_detail(
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

    # Avatar chỉ lấy từ bảng students (nếu khớp sinh viên có ảnh đại diện)
    avatar_url: str | None = None
    if record.matched_student_id:
        avatar_url = f"/images/avatar/student/{record.matched_student_id}"

    return {
        "id": str(record.id),
        "scan_type": record.scan_type,
        "match_result": record.match_result,
        "raw_text": record.raw_text,
        "qr_data": record.qr_data,
        "image_url": f"/images/scan/{record.id}" if record.image_data else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "student_info": {
            "full_name": card.full_name,
            "birth_date": card.birth_date,
            "school": card.school,
            "student_id": card.student_id,
            "email": card.email,
            "study_status": card.study_status,
            "avatar_url": avatar_url,
        }
        if card
        else None,
    }
