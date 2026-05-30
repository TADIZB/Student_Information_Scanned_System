"""Router xử lý quét thẻ (QR / OCR) — endpoint chính của ứng dụng."""
from __future__ import annotations

import base64
import io
import re
from typing import Any, Dict, List
from urllib.parse import unquote
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session as DBSession

from ..auth import get_optional_user
from ..database import get_db
from ..middleware.rate_limit import rate_limit_process_scan
from ..models import ScanHistory, Student, StudentCard, User
from ..pipeline import (
    detect_qr,
    draw_canny_preview,
    draw_ocr_blocks_on_image,
    draw_quad_on_image,
    extract_student_info,
    find_document_contour,
    img_to_data_url,
    load_image,
    ocr_ensemble,
    pil_to_cv,
    preprocess_for_ocr,
    resize_image,
    warp_perspective,
)
from ..services.student_matching import _match_student, _student_to_dict

router = APIRouter(tags=["scan"])


# ─── Helpers nội bộ ──────────────────────────────────────────────────────────

def _warped_to_png_bytes(warped_image: np.ndarray) -> bytes:
    arr = np.clip(warped_image, 0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr[:, :, ::-1]).save(buf, format="PNG")
    return buf.getvalue()


def _to_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


def _parse_qr_mssv(qr_data: str) -> dict:
    """Trích MSSV/họ tên từ chuỗi QR.

    Hỗ trợ:
    - URL HUST: https://ctsv.hust.edu.vn/#/card/{MSSV}/{HO_TEN}/{token}
    - Dạng key-value: 'MSSV:12345|HoTen:...'
    - Chuỗi thuần: '12345678' (chỉ MSSV)
    """
    mapping = {"MSSV": "student_id", "HoTen": "full_name", "Truong": "school", "Email": "email"}
    fields: dict = {v: None for v in mapping.values()}

    # 1. URL HUST ctsv (hash route): /card/<MSSV>/<HO_TEN>/<token>
    url_match = re.search(
        r'ctsv\.hust\.edu\.vn/#/card/(?P<mssv>[A-Za-z0-9]+)/(?P<name>[^/?#]+)',
        qr_data,
        re.IGNORECASE,
    )
    if url_match:
        fields["student_id"] = url_match.group("mssv")
        raw_name = unquote(url_match.group("name")).replace("_", " ").strip()
        if raw_name:
            # Chuẩn hoá: "LE DUY HOANG" → "Le Duy Hoang"
            fields["full_name"] = raw_name.title() if raw_name.isupper() else raw_name
        fields["school"] = "Đại học Bách khoa Hà Nội"
        return fields

    # 2. Key-value 'MSSV:...|HoTen:...'
    if "|" in qr_data or ":" in qr_data:
        for part in qr_data.split("|"):
            key, _, value = part.partition(":")
            if key.strip() in mapping:
                fields[mapping[key.strip()]] = value.strip() or None
        if fields["student_id"]:
            return fields

    # 3. Chuỗi thuần = MSSV
    m = re.search(r'\b([A-Z]{0,3}\d{6,12})\b', qr_data, re.IGNORECASE)
    if m:
        fields["student_id"] = m.group(1)
    return fields


# ─── Endpoint chính ──────────────────────────────────────────────────────────

@router.post("/process-scan", dependencies=[Depends(rate_limit_process_scan)])
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
                    "raw_text": None,
                    "extracted_info": None,
                }

            parsed = _parse_qr_mssv(qr_data)
            mssv = parsed.get("student_id")
            student = db.query(Student).filter(Student.student_id == mssv).first() if mssv else None

            # MSSV chưa có trong bảng students nhưng QR có đủ MSSV → tự thêm mới
            auto_created = False
            if not student and mssv and parsed.get("full_name"):
                student = Student(
                    student_id=mssv,
                    full_name=parsed.get("full_name"),
                    school=parsed.get("school"),
                    email=parsed.get("email"),
                )
                db.add(student)
                db.flush()  # cấp UUID để StudentCard dưới đây tham chiếu được
                auto_created = True

            if student:
                student_info = _student_to_dict(student)
            else:
                student_info = {
                    "full_name": parsed.get("full_name"),
                    "birth_date": None,
                    "school": parsed.get("school"),
                    "student_id": mssv,
                    "email": parsed.get("email"),
                    "avatar_url": avatar_data_url,
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
            elif auto_created:
                # Không đăng nhập nhưng đã tạo Student mới → commit riêng
                db.commit()

            return {
                "scan_id": scan_id,
                "scan_type": "qr",
                "match_result": 1 if student else 0,
                "qr_data": qr_data,
                "student_info": student_info,
                "warped_image_url": _to_data_url(warped_bytes),
                "steps": [],
                "blocks": [],
                "raw_text": None,
                "extracted_info": None,
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

        # Bước 6: OCR ensemble — chạy Tesseract trên nhiều variant × PSM
        try:
            blocks = ocr_ensemble(warped.image)
            raw_text = "\n".join(
                line["text"] for block in blocks for line in block.get("lines", [])
            ).strip()
            num_lines = sum(len(b.get("lines", [])) for b in blocks)
            avg_conf = (
                sum(line["conf"] for b in blocks for line in b.get("lines", [])) / num_lines
                if num_lines else 0.0
            )
            ocr_overlay = draw_ocr_blocks_on_image(preprocessed, blocks)
            steps.append({
                "name": "6. Nhận dạng văn bản (Tesseract OCR ensemble)",
                "status": "success" if raw_text else "warning",
                "description": (
                    f"Chạy OCR trên 4 biến thể ảnh × 3 chế độ PSM, gộp dòng theo IoU. "
                    f"Tổng {num_lines} dòng (độ tin cậy trung bình {avg_conf:.1f}%). "
                    f"Các khung đỏ là vùng chữ giữ lại."
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
        ocr_info = extract_student_info(
            raw_text,
            blocks=blocks,
            image_height=warped.image.shape[0],
        )
        mssv_cands = ocr_info.get("student_id_candidates") or []
        # Loại key nội bộ trước khi trả về frontend
        ocr_info_public = {k: v for k, v in ocr_info.items() if k != "student_id_candidates"}

        student, match_note = _match_student(db, mssv_cands, ocr_info.get("full_name"))

        extracted_summary = " · ".join(
            f"{k}: {v}" for k, v in [
                ("MSSV", ocr_info_public.get("student_id")),
                ("Họ tên", ocr_info_public.get("full_name")),
                ("Ngày sinh", ocr_info_public.get("birth_date")),
                ("Email", ocr_info_public.get("email")),
            ] if v
        ) or "Không bóc được trường nào."

        if student:
            match_result = 1
            student_info = _student_to_dict(student)
            steps.append({
                "name": "7. Bóc tách & đối chiếu dữ liệu sinh viên",
                "status": "success",
                "description": f"Bóc được: {extracted_summary}. → {match_note}.",
                "image_url": None,
            })
        else:
            match_result = 0
            student_info = {**ocr_info_public, "avatar_url": avatar_data_url}
            cand_note = f" Đã thử các MSSV: {', '.join(mssv_cands[:5])}." if mssv_cands else ""
            steps.append({
                "name": "7. Bóc tách & đối chiếu dữ liệu sinh viên",
                "status": "fail",
                "description": f"Bóc được: {extracted_summary}.{cand_note} → Không khớp sinh viên nào.",
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
            "raw_text": raw_text,
            "extracted_info": ocr_info_public,
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {exc}") from exc
