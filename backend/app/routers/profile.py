"""Router profile: xem/sửa thông tin tài khoản + stats + avatar."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..auth import get_current_user
from ..database import get_db
from ..models import ScanHistory, User
from ..schemas import UpdateProfilePayload

router = APIRouter(tags=["profile"])

# Avatar config
MAX_AVATAR_BYTES = 2 * 1024 * 1024   # 2MB
ALLOWED_AVATAR_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "birth_date": user.birth_date,
        "has_avatar": user.avatar_data is not None,
        "avatar_url": f"/me/avatar?v={user.id}" if user.avatar_data else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/me/profile")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict:
    """Trả về thông tin user + stats các loại scan."""
    rows = (
        db.query(ScanHistory.scan_type, func.count(ScanHistory.id))
        .filter(ScanHistory.user_id == current_user.id)
        .group_by(ScanHistory.scan_type)
        .all()
    )
    counts = {t or "unknown": int(n) for t, n in rows}

    total = sum(counts.values())
    matched = (
        db.query(func.count(ScanHistory.id))
        .filter(ScanHistory.user_id == current_user.id, ScanHistory.match_result == 1)
        .scalar()
    ) or 0

    return {
        "user": _user_dict(current_user),
        "stats": {
            "total_scans": total,
            "qr_scans": counts.get("qr", 0),
            "ocr_scans": counts.get("ocr", 0),
            "lookup_scans": counts.get("lookup", 0),
            "matched": int(matched),
        },
    }


@router.patch("/me")
def update_profile(
    payload: UpdateProfilePayload,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict:
    """Cho phép user sửa full_name + birth_date. Email/username không sửa được ở đây."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip() or None
    if payload.birth_date is not None:
        current_user.birth_date = payload.birth_date.strip() or None
    db.commit()
    db.refresh(current_user)
    return _user_dict(current_user)


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict:
    if not file.content_type or file.content_type not in ALLOWED_AVATAR_MIMES:
        raise HTTPException(
            status_code=400,
            detail="Định dạng ảnh không hỗ trợ. Cho phép: JPEG, PNG, WebP, GIF.",
        )
    data = await file.read()
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Ảnh quá lớn (tối đa 2 MB).")
    current_user.avatar_data = data
    current_user.avatar_mime = file.content_type
    db.commit()
    return {"message": "Đã cập nhật ảnh đại diện.", "avatar_url": f"/me/avatar?v={current_user.id}"}


@router.delete("/me/avatar")
def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict:
    current_user.avatar_data = None
    current_user.avatar_mime = None
    db.commit()
    return {"message": "Đã xoá ảnh đại diện."}


@router.get("/me/avatar")
def get_avatar(
    current_user: User = Depends(get_current_user),
):
    if not current_user.avatar_data:
        raise HTTPException(status_code=404, detail="Chưa có ảnh đại diện.")
    return Response(
        content=current_user.avatar_data,
        media_type=current_user.avatar_mime or "image/jpeg",
    )
