from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from .auth import get_current_user, get_optional_user, google_login, google_register, login_user
from .card_pdf import build_card_pdf
from .database import get_db
from .models import ScanHistory, Student, StudentCard, User
from .pdf import build_pdf
from .pipeline import (
    detect_qr,
    draw_canny_preview,
    draw_ocr_blocks_on_image,
    draw_quad_on_image,
    extract_student_info,
    find_document_contour,
    img_to_data_url,
    layout_and_ocr,
    load_image,
    ocr_preprocessed,
    pil_to_cv,
    preprocess_for_ocr,
    resize_image,
    warp_perspective,
)

# ─── Thư mục chỉ còn PDF (ảnh quét lưu DB) ───────────────────────────────────

BASE_DIR = Path(__file__).resolve().parents[1]
PDF_DIR = BASE_DIR / "storage" / "pdf"
PDF_DIR.mkdir(parents=True, exist_ok=True)

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="TADIZB Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # cho phép cả điện thoại qua WiFi
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/files/pdf", StaticFiles(directory=PDF_DIR), name="pdf")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _warped_to_png_bytes(warped_image: np.ndarray) -> bytes:
    arr = np.clip(warped_image, 0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr[:, :, ::-1]).save(buf, format="PNG")
    return buf.getvalue()


def _to_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


def _student_to_dict(s: Student, scan_id: str | None = None) -> dict:
    return {
        "full_name": s.full_name,
        "birth_date": s.birth_date,
        "school": s.school,
        "student_id": s.student_id,
        "email": s.email,
        "avatar_url": f"/images/avatar/student/{s.id}" if s.avatar_data else None,
    }


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    identifier: str           # username HOẶC email
    password: str


class RegisterPayload(BaseModel):
    username: str
    password: str
    email: str | None = None
    full_name: str | None = None


class GooglePayload(BaseModel):
    access_token: str         # OAuth access token lấy từ Google Identity Services (FE)


@app.post("/register", status_code=201)
def register(payload: RegisterPayload, db: DBSession = Depends(get_db)):
    from .auth import hash_password
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=422, detail="Mật khẩu phải có ít nhất 6 ký tự.")

    email_norm = payload.email.strip().lower() if payload.email else None
    if email_norm and db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=409, detail="Email đã được sử dụng.")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        email=email_norm,
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    return {"message": "Đăng ký thành công."}


@app.post("/login")
def login(payload: LoginPayload, response: Response, db: DBSession = Depends(get_db)):
    return login_user(payload.identifier, payload.password, response, db)


@app.post("/auth/google/login")
def auth_google_login(payload: GooglePayload, response: Response, db: DBSession = Depends(get_db)):
    """Đăng nhập bằng Google. Báo lỗi nếu tài khoản Google chưa đăng ký."""
    return google_login(payload.access_token, response, db)


@app.post("/auth/google/register")
def auth_google_register(payload: GooglePayload, response: Response, db: DBSession = Depends(get_db)):
    """Đăng ký bằng Google. Nếu đã từng đăng ký thì vẫn đăng nhập, kèm cờ already_existed."""
    return google_register(payload.access_token, response, db)


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_id")
    return {"message": "Đã đăng xuất."}


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
    }


# ─── Tra cứu sinh viên theo MSSV (dùng cho cả QR lẫn nhập tay) ───────────────

@app.get("/students/lookup")
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
            avatar_data=None,
            avatar_mime=None,
            full_name=student.full_name,
            birth_date=student.birth_date,
            school=student.school,
            student_id=student.student_id,
            email=student.email,
        ))
        db.commit()
        scan_id = str(scan_record.id)

    return {**result, "scan_id": scan_id}


# ─── Serve ảnh đại diện từ bảng students ─────────────────────────────────────

@app.get("/images/avatar/student/{student_uuid}")
def get_student_avatar(student_uuid: str, db: DBSession = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_uuid).first()
    if not student or not student.avatar_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh.")
    return Response(content=student.avatar_data, media_type=student.avatar_mime or "image/jpeg")


# ─── Serve ảnh từ scan_history / student_cards ───────────────────────────────

@app.get("/images/scan/{scan_id}")
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


@app.get("/images/avatar/{scan_id}")
def get_scan_avatar(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    card = (
        db.query(StudentCard)
        .filter(StudentCard.scan_id == scan_id, StudentCard.user_id == current_user.id)
        .first()
    )
    if not card or not card.avatar_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh đại diện.")
    return Response(content=card.avatar_data, media_type=card.avatar_mime or "image/jpeg")


# ─── Quét thẻ chính ───────────────────────────────────────────────────────────

@app.post("/process-scan")
async def process_scan(
    file: UploadFile = File(...),
    scan_mode: str = Form("qr"),
    avatar: UploadFile | None = File(None),
    current_user: User | None = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    scan_mode='qr' : Phát hiện QR → tra MSSV trong bảng students → trả dữ liệu từ DB.
    scan_mode='ocr': Chụp thủ công → OCR → đối chiếu bảng students → trả 0/1 + steps.
    """
    if scan_mode not in ("qr", "ocr"):
        raise HTTPException(status_code=400, detail="scan_mode phải là 'qr' hoặc 'ocr'.")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là hình ảnh.")

    try:
        raw_data = await file.read()

        avatar_bytes: bytes | None = None
        avatar_mime: str | None = None
        avatar_data_url: str | None = None
        if avatar and avatar.content_type and avatar.content_type.startswith("image/"):
            avatar_bytes = await avatar.read()
            avatar_mime = avatar.content_type
            avatar_data_url = _to_data_url(avatar_bytes, avatar_mime)

        # ════════════════════════════════════════════════════════════════════
        #  CHẾ ĐỘ QR
        # ════════════════════════════════════════════════════════════════════
        if scan_mode == "qr":
            image = resize_image(load_image(raw_data))
            warped = warp_perspective(pil_to_cv(image))
            warped_bytes = _warped_to_png_bytes(warped.image)

            qr_data = detect_qr(warped.image)
            if not qr_data:
                # Không có QR trong frame — trả về im lặng để auto-scan tiếp tục
                return {
                    "scan_id": "",
                    "scan_type": "qr",
                    "match_result": None,
                    "qr_data": None,
                    "student_info": None,
                    "warped_image_url": None,
                    "steps": [],
                    "blocks": [],
                }

            parsed = _parse_qr_mssv(qr_data)
            mssv = parsed.get("student_id")
            student = db.query(Student).filter(Student.student_id == mssv).first() if mssv else None

            student_info = _student_to_dict(student) if student else {
                "full_name": None, "birth_date": None, "school": None,
                "student_id": mssv, "email": None, "avatar_url": avatar_data_url,
            }

            scan_id = uuid4().hex
            if current_user:
                scan_record = ScanHistory(
                    user_id=current_user.id,
                    image_data=warped_bytes,
                    image_mime="image/png",
                    qr_data=qr_data,
                    raw_text=None,
                    scan_type="qr",
                    match_result=1 if student else 0,
                    matched_student_id=student.id if student else None,
                )
                db.add(scan_record)
                db.flush()
                db.add(StudentCard(
                    scan_id=scan_record.id,
                    user_id=current_user.id,
                    avatar_data=avatar_bytes,
                    avatar_mime=avatar_mime,
                    full_name=student_info["full_name"],
                    birth_date=student_info["birth_date"],
                    school=student_info["school"],
                    student_id=student_info["student_id"],
                    email=student_info["email"],
                ))
                db.commit()
                scan_id = str(scan_record.id)

            return {
                "scan_id": scan_id,
                "scan_type": "qr",
                "match_result": 1 if student else 0,
                "qr_data": qr_data,
                "student_info": student_info,
                "warped_image_url": _to_data_url(warped_bytes),
                "steps": [],
                "blocks": [],
            }

        # ════════════════════════════════════════════════════════════════════
        #  CHẾ ĐỘ OCR – xử lý từng bước, trả steps + match_result
        # ════════════════════════════════════════════════════════════════════
        steps: List[Dict[str, Any]] = []

        # Bước 1: Tải & tiền xử lý
        try:
            image = resize_image(load_image(raw_data))
            cv_image = pil_to_cv(image)
            steps.append({
                "name": "1. Tải & chuẩn hoá ảnh đầu vào",
                "status": "success",
                "description": (
                    f"Đọc ảnh, sửa hướng EXIF và thu nhỏ về tối đa 2000px "
                    f"(kích thước hiện tại: {image.size[0]}×{image.size[1]}px)."
                ),
                "image_url": img_to_data_url(cv_image),
            })
        except Exception:
            steps.append({"name": "1. Tải & chuẩn hoá ảnh đầu vào", "status": "fail", "description": "Không đọc được file ảnh.", "image_url": None})
            raise HTTPException(status_code=422, detail="Không đọc được file ảnh.")

        # Bước 2: Edge detection (Canny) — minh hoạ
        try:
            edge_preview = draw_canny_preview(cv_image)
            steps.append({
                "name": "2. Phát hiện cạnh (Canny + GaussianBlur)",
                "status": "success",
                "description": "Khử nhiễu Gaussian rồi dò cạnh bằng Canny (50, 150) để tìm các đường biên có thể là tài liệu.",
                "image_url": img_to_data_url(edge_preview),
            })
        except Exception:
            pass

        # Bước 3: Phát hiện biên tài liệu — vẽ tứ giác lên ảnh gốc
        quad = find_document_contour(cv_image)
        if quad is not None:
            quad_overlay = draw_quad_on_image(cv_image, quad.tolist())
            steps.append({
                "name": "3. Khoanh vùng tài liệu (tứ giác 4 góc)",
                "status": "success",
                "description": "Lọc contour kín gần hình tứ giác, chọn vùng có diện tích lớn nhất. 4 chấm đỏ là 4 góc phát hiện được (TL/TR/BR/BL).",
                "image_url": img_to_data_url(quad_overlay),
            })
        else:
            steps.append({
                "name": "3. Khoanh vùng tài liệu (tứ giác 4 góc)",
                "status": "warning",
                "description": "Không tìm được tứ giác đủ rõ — sẽ dùng nguyên ảnh đầu vào, bỏ qua bước warp.",
                "image_url": img_to_data_url(cv_image),
            })

        # Bước 4: Warp perspective — ảnh đã được cắt + nắn thẳng
        warped = warp_perspective(cv_image)
        warped_bytes = _warped_to_png_bytes(warped.image)
        steps.append({
            "name": "4. Cắt & nắn phối cảnh (Warp Perspective)",
            "status": "success" if warped.used_warp else "warning",
            "description": (
                f"Áp dụng phép biến đổi phối cảnh đưa tài liệu về hình chữ nhật thẳng "
                f"({warped.image.shape[1]}×{warped.image.shape[0]}px)."
                if warped.used_warp
                else "Bỏ qua warp do không có 4 góc rõ — giữ nguyên ảnh."
            ),
            "image_url": img_to_data_url(warped.image),
        })

        # Bước 5: Tiền xử lý ảnh cho OCR (grayscale + CLAHE + threshold + denoise)
        try:
            preprocessed = preprocess_for_ocr(warped.image)
            steps.append({
                "name": "5. Tăng cường ảnh cho OCR",
                "status": "success",
                "description": "Chuỗi: Grayscale → CLAHE (tăng tương phản cục bộ) → Adaptive Threshold → Median Blur. Đây chính là ảnh mà Tesseract sẽ đọc.",
                "image_url": img_to_data_url(preprocessed),
            })
        except Exception:
            steps.append({"name": "5. Tăng cường ảnh cho OCR", "status": "fail", "description": "Lỗi khi tiền xử lý ảnh.", "image_url": None})
            raise HTTPException(status_code=422, detail="Lỗi tiền xử lý ảnh.")

        # Bước 6: OCR — vẽ bounding box của từng dòng lên ảnh tiền xử lý
        try:
            blocks = ocr_preprocessed(preprocessed)
            raw_text = " ".join(
                line["text"] for block in blocks for line in block.get("lines", [])
            ).strip()
            num_lines = sum(len(b.get("lines", [])) for b in blocks)
            avg_conf = (
                sum(line["conf"] for b in blocks for line in b.get("lines", [])) / num_lines
                if num_lines else 0.0
            )
            ocr_overlay = draw_ocr_blocks_on_image(preprocessed, blocks)
            steps.append({
                "name": "6. Nhận dạng văn bản (Tesseract OCR)",
                "status": "success" if raw_text else "warning",
                "description": (
                    f"Tesseract phát hiện {num_lines} dòng văn bản (độ tin cậy trung bình {avg_conf:.1f}%). "
                    f"Các khung đỏ là vùng chữ tìm được."
                    if raw_text else "Không nhận dạng được dòng chữ nào."
                ),
                "image_url": img_to_data_url(ocr_overlay),
            })
        except HTTPException:
            raise
        except Exception:
            steps.append({"name": "6. Nhận dạng văn bản (Tesseract OCR)", "status": "fail", "description": "Lỗi khi chạy OCR.", "image_url": None})
            raise HTTPException(status_code=422, detail="Lỗi khi nhận dạng văn bản.")

        # Bước 7: Bóc tách & đối chiếu dữ liệu sinh viên
        ocr_info = extract_student_info(raw_text)
        mssv = ocr_info.get("student_id")
        student = db.query(Student).filter(Student.student_id == mssv).first() if mssv else None

        extracted_summary = " · ".join(
            f"{k}: {v}" for k, v in [
                ("MSSV", ocr_info.get("student_id")),
                ("Họ tên", ocr_info.get("full_name")),
                ("Ngày sinh", ocr_info.get("birth_date")),
                ("Email", ocr_info.get("email")),
            ] if v
        ) or "Không bóc được trường nào."

        if student:
            match_result = 1
            student_info = _student_to_dict(student)
            steps.append({
                "name": "7. Bóc tách & đối chiếu dữ liệu sinh viên",
                "status": "success",
                "description": f"Bóc được: {extracted_summary}. → Khớp MSSV {mssv} trong CSDL.",
                "image_url": None,
            })
        else:
            match_result = 0
            student_info = {**ocr_info, "avatar_url": avatar_data_url}
            steps.append({
                "name": "7. Bóc tách & đối chiếu dữ liệu sinh viên",
                "status": "fail",
                "description": f"Bóc được: {extracted_summary}. → Không khớp với sinh viên nào trong CSDL.",
                "image_url": None,
            })

        scan_id = uuid4().hex
        if current_user:
            scan_record = ScanHistory(
                user_id=current_user.id,
                image_data=warped_bytes,
                image_mime="image/png",
                raw_text=raw_text,
                qr_data=None,
                scan_type="ocr",
                match_result=match_result,
                matched_student_id=student.id if student else None,
            )
            db.add(scan_record)
            db.flush()
            db.add(StudentCard(
                scan_id=scan_record.id,
                user_id=current_user.id,
                avatar_data=avatar_bytes,
                avatar_mime=avatar_mime,
                full_name=student_info.get("full_name"),
                birth_date=student_info.get("birth_date"),
                school=student_info.get("school"),
                student_id=student_info.get("student_id"),
                email=student_info.get("email"),
            ))
            db.commit()
            scan_id = str(scan_record.id)

        return {
            "scan_id": scan_id,
            "scan_type": "ocr",
            "match_result": match_result,
            "qr_data": None,
            "student_info": student_info,
            "warped_image_url": _to_data_url(warped_bytes),
            "steps": steps,
            "blocks": blocks,
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {exc}") from exc


def _parse_qr_mssv(qr_data: str) -> dict:
    """Trích MSSV từ chuỗi QR. Hỗ trợ dạng 'MSSV:12345' hoặc '12345678' thuần."""
    import re
    mapping = {"MSSV": "student_id", "HoTen": "full_name", "Truong": "school", "Email": "email"}
    fields: dict = {v: None for v in mapping.values()}
    if "|" in qr_data or ":" in qr_data:
        for part in qr_data.split("|"):
            key, _, value = part.partition(":")
            if key.strip() in mapping:
                fields[mapping[key.strip()]] = value.strip() or None
    else:
        # Chuỗi thuần = MSSV
        m = re.search(r'\b([A-Z]{0,3}\d{6,12})\b', qr_data, re.IGNORECASE)
        if m:
            fields["student_id"] = m.group(1)
    return fields


# ─── Lịch sử quét ────────────────────────────────────────────────────────────

@app.get("/scan-history")
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


@app.get("/scan-history/{scan_id}")
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

    # Nếu có matched_student_id thì lấy avatar từ bảng students
    avatar_url: str | None = None
    if record.matched_student_id:
        avatar_url = f"/images/avatar/student/{record.matched_student_id}"
    elif card and card.avatar_data:
        avatar_url = f"/images/avatar/{record.id}"

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
            "avatar_url": avatar_url,
        }
        if card
        else None,
    }


# ─── Export thẻ PDF ───────────────────────────────────────────────────────────

@app.get("/export-card/{scan_id}")
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


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ─── Legacy OCR endpoints ─────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là hình ảnh.")
    data = await file.read()
    image = resize_image(load_image(data))
    warped = warp_perspective(pil_to_cv(image))
    blocks = layout_and_ocr(warped.image)
    warped_id = uuid4().hex
    return {
        "warped_image_id": warped_id,
        "warped_preview_url": _to_data_url(_warped_to_png_bytes(warped.image)),
        "blocks": blocks,
    }


@app.post("/export")
async def export(payload: Dict[str, Any]) -> JSONResponse:
    blocks = payload.get("blocks", [])
    warped_b64 = payload.get("warped_image_b64")
    if not warped_b64:
        raise HTTPException(status_code=400, detail="warped_image_b64 là bắt buộc.")
    try:
        warped_bytes = base64.b64decode(warped_b64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="warped_image_b64 không hợp lệ.")
    pdf_bytes = build_pdf(warped_bytes, blocks)
    pdf_id = uuid4().hex
    (PDF_DIR / f"{pdf_id}.pdf").write_bytes(pdf_bytes)
    return JSONResponse({"export_pdf_url": f"/files/pdf/{pdf_id}.pdf", "export_pdf_id": pdf_id})
