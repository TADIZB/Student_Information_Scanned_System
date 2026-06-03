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
    extract_cccd_info,
    find_document_contour,
    load_image,
    ocr_cccd,
    pil_to_cv,
    preprocess_cccd_pipeline,
    resize_image,
    warp_perspective,
)
from ..services.gemini_ocr import extract_cccd_with_gemini
from ..services.student_matching import _match_student_by_cccd, _student_to_dict

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
        r'ctsv\.hust\.edu\.vn/#/card/(?P<mssv>[A-Za-z0-9]+)/(?P<name>[^/?#]+)'
        r'(?:/(?P<token>[^/?#\s]+))?',
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
        # Token để gọi API HUST lấy thêm ngày sinh / trường / trạng thái.
        # Trang HUST giải mã URL rồi bỏ hết dấu '_' khỏi token (base64), ta làm y hệt.
        token = url_match.group("token")
        if token:
            fields["token"] = unquote(token).replace("_", "")
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
    engine: str = Form("tesseract"),
    current_user: User | None = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    scan_mode='qr' : Phát hiện QR → tra MSSV trong bảng students → trả dữ liệu từ DB.
    scan_mode='ocr': Chụp thủ công → OCR CCCD → đối chiếu bảng students → trả 0/1 + steps.
                     engine='tesseract' (mặc định) hoặc 'gemini' (Gemini Vision).
    """
    if scan_mode not in ("qr", "ocr"):
        raise HTTPException(status_code=400, detail="scan_mode phải là 'qr' hoặc 'ocr'.")
    if engine not in ("tesseract", "gemini"):
        raise HTTPException(status_code=400, detail="engine phải là 'tesseract' hoặc 'gemini'.")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là hình ảnh.")

    try:
        raw_data = await file.read()

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

            # Lưu MỌI sinh viên quét được vào bảng students dùng chung (toàn hệ thống).
            # - Chưa có MSSV → tạo mới, kể cả khi QR chỉ có MSSV mà chưa có tên.
            # - Đã có nhưng thiếu trường → bổ sung từ QR (KHÔNG ghi đè dữ liệu đã có).
            student_changed = False
            if mssv:
                if not student:
                    student = Student(
                        student_id=mssv,
                        full_name=parsed.get("full_name"),
                        school=parsed.get("school"),
                        email=parsed.get("email"),
                    )
                    db.add(student)
                    db.flush()  # cấp UUID để StudentCard dưới đây tham chiếu được
                    student_changed = True
                else:
                    for field in ("full_name", "school", "email"):
                        if not getattr(student, field) and parsed.get(field):
                            setattr(student, field, parsed.get(field))
                            student_changed = True

            if student:
                student_info = _student_to_dict(student)
            else:
                student_info = {
                    "full_name": parsed.get("full_name"),
                    "birth_date": None,
                    "school": parsed.get("school"),
                    "student_id": mssv,
                    "email": parsed.get("email"),
                    "study_status": None,
                    "avatar_url": None,
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
                    full_name=student_info["full_name"],
                    birth_date=student_info["birth_date"],
                    school=student_info["school"],
                    student_id=student_info["student_id"],
                    email=student_info["email"],
                    study_status=student_info.get("study_status"),
                ))
                db.commit()
                scan_id = str(scan_record.id)
            elif student_changed:
                # Không đăng nhập nhưng đã tạo/bổ sung Student → commit riêng
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
        #  CHẾ ĐỘ OCR bằng GEMINI (engine='gemini') — gửi ảnh, nhận JSON
        # ════════════════════════════════════════════════════════════════════
        if engine == "gemini":
            # Chuẩn hoá + nén ảnh trước khi gửi (giảm payload, ổn định mime)
            image = resize_image(load_image(raw_data))
            jpg_buf = io.BytesIO()
            image.convert("RGB").save(jpg_buf, format="JPEG", quality=90)
            gemini_bytes = jpg_buf.getvalue()
            png_buf = io.BytesIO()
            image.convert("RGB").save(png_buf, format="PNG")
            warped_bytes = png_buf.getvalue()

            g_steps: List[Dict[str, Any]] = [{
                "name": "1. Thu thập & chuẩn hoá hình ảnh",
                "status": "success",
                "description": f"Đọc ảnh, sửa hướng EXIF, nén JPEG ({image.size[0]}×{image.size[1]}px).",
                "image_url": None,
            }]

            raw_text, cccd = extract_cccd_with_gemini(gemini_bytes, "image/jpeg")
            g_steps.append({
                "name": "2. Gửi ảnh lên Gemini & nhận JSON",
                "status": "success" if any(cccd.get(k) for k in ("ho_va_ten", "so_cccd")) else "warning",
                "description": (
                    "Gemini Vision đã bóc tách các trường CCCD."
                    if any(cccd.get(k) for k in ("ho_va_ten", "so_cccd"))
                    else "Gemini không bóc được trường nào rõ ràng."
                ),
                "image_url": None,
            })

            student, match_note = _match_student_by_cccd(
                db, full_name=cccd.get("ho_va_ten"), birth_date=cccd.get("ngay_sinh"),
            )
            extracted_summary = " · ".join(
                f"{k}: {v}" for k, v in [
                    ("Số CCCD", cccd.get("so_cccd")),
                    ("Họ tên", cccd.get("ho_va_ten")),
                    ("Ngày sinh", cccd.get("ngay_sinh")),
                    ("Địa chỉ", cccd.get("dia_chi")),
                ] if v
            ) or "Không bóc được trường nào."

            if student:
                match_result = 1
                student_info = {
                    **cccd,
                    "student_id": student.student_id,
                    "school": student.school,
                    "email": student.email,
                    "avatar_url": (
                        f"/images/avatar/student/{student.id}" if student.avatar_data else None
                    ),
                }
                g_steps.append({
                    "name": "3. Đối chiếu sinh viên",
                    "status": "success",
                    "description": f"Bóc được: {extracted_summary}. → {match_note}.",
                    "image_url": None,
                })
            else:
                match_result = 0
                student_info = {**cccd, "student_id": None, "school": None, "email": None,
                                "avatar_url": None}
                g_steps.append({
                    "name": "3. Đối chiếu sinh viên",
                    "status": "fail" if any(cccd.get(k) for k in ("ho_va_ten", "so_cccd")) else "warning",
                    "description": f"Bóc được: {extracted_summary}. → Không khớp sinh viên nào.",
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
                    full_name=cccd.get("ho_va_ten"),
                    birth_date=cccd.get("ngay_sinh"),
                    school=student.school if student else None,
                    student_id=student.student_id if student else None,
                    email=student.email if student else None,
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
                "steps": g_steps,
                "blocks": [],
                "raw_text": raw_text,
                "extracted_info": cccd,
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
                "name": "1. Thu thập & chuẩn hoá hình ảnh",
                "status": "success",
                "description": (
                    f"Đọc ảnh, sửa hướng EXIF và chuẩn hoá độ phân giải "
                    f"({image.size[0]}×{image.size[1]}px)."
                ),
                "image_url": None,
            })
        except Exception:
            steps.append({"name": "1. Thu thập & chuẩn hoá hình ảnh", "status": "fail",
                          "description": "Không đọc được file ảnh.", "image_url": None})
            raise HTTPException(status_code=422, detail="Không đọc được file ảnh.")

        # Pipeline 7 bước CCCD ════════════════════════════════════════════════
        try:
            cleaned, intermediates = preprocess_cccd_pipeline(cv_image)
        except Exception as exc:
            steps.append({"name": "Pipeline tiền xử lý", "status": "fail",
                          "description": str(exc), "image_url": None})
            raise HTTPException(status_code=422, detail=f"Lỗi tiền xử lý: {exc}")

        # Lưu ảnh ROI đã warp (step2_roi) để hiển thị + lưu DB
        warped_bgr = intermediates["step2_roi"]
        warped_bytes = _warped_to_png_bytes(warped_bgr)

        # Bước 2: Bounding Box — khoanh khối nội dung, cắt bỏ nền thừa
        acq = intermediates.get("step1_acquire")
        bbox_img = intermediates.get("step1b_bbox")
        bbox_cropped = (
            acq is not None and bbox_img is not None and bbox_img.shape[:2] != acq.shape[:2]
        )
        steps.append({
            "name": "2. Khoanh vùng nội dung (Bounding Box)",
            "status": "success" if bbox_cropped else "warning",
            "description": (
                f"Phát hiện khối giấy tờ theo mật độ biên (Canny + dilate) rồi cắt bỏ "
                f"nền thừa → còn {bbox_img.shape[1]}×{bbox_img.shape[0]}px, giúp các bước sau chính xác hơn."
                if bbox_cropped
                else "Không thấy nền thừa rõ rệt — giữ nguyên toàn ảnh để không cắt nhầm."
            ),
            "image_url": None,
        })

        # Bước 3: ROI detection (trên ảnh đã khoanh Bounding Box)
        quad = find_document_contour(bbox_img if bbox_img is not None else cv_image)
        steps.append({
            "name": "3. Phát hiện ROI & tạo mặt nạ",
            "status": "success" if quad is not None else "warning",
            "description": (
                "Đã phát hiện 4 góc thẻ và crop về vùng quan tâm."
                if quad is not None
                else "Không tìm được 4 góc đủ rõ — sẽ xử lý nguyên ảnh đầu vào."
            ),
            "image_url": None,
        })

        # Bước 4: Noise reduction
        steps.append({
            "name": "4. Giảm nhiễu & lọc hình ảnh",
            "status": "success",
            "description": "Grayscale + Median Blur (giữ biên ký tự, triệt tiêu hạt nhiễu nhỏ).",
            "image_url": None,
        })

        # Bước 5: Flat-fielding
        steps.append({
            "name": "5. Hiệu chỉnh độ đồng nhất ánh sáng (Flat-fielding)",
            "status": "success",
            "description": "Ước tính ma trận ánh sáng nền (Gaussian blur lớn) rồi chia ảnh / nền → triệt tiêu vùng cháy sáng (glare/hotspot).",
            "image_url": None,
        })

        # Bước 6: Adaptive thresholding
        steps.append({
            "name": "6. Phân ngưỡng thích ứng cục bộ",
            "status": "success",
            "description": "Adaptive Gaussian Threshold (blockSize=25, C=10) → ảnh nhị phân đen-trắng tuyệt đối.",
            "image_url": None,
        })

        # Bước 7: Morphology refinement
        steps.append({
            "name": "7. Tinh chỉnh hình thái & làm sạch",
            "status": "success",
            "description": "Opening (2×2) → loại vệt mực thừa, tách ký tự dính. Closing (2×2) → nối nét đứt, làm mượt biên.",
            "image_url": None,
        })

        # Bước 8: Skew correction
        steps.append({
            "name": "8. Hiệu chỉnh độ lệch & biến đổi phối cảnh",
            "status": "success",
            "description": "Hough transform tính góc nghiêng dòng chữ + Perspective transform đưa phôi thẻ về phẳng đứng.",
            "image_url": None,
        })

        # ── OCR trên ảnh ROI đã warp (ensemble nhiều biến thể × PSM) ─────────
        # KHÔNG OCR trên ảnh nhị phân `cleaned` (morphology phá dấu tiếng Việt).
        try:
            raw_text, blocks = ocr_cccd(warped_bgr)
            num_lines = sum(len(b.get("lines", [])) for b in blocks)
            avg_conf = (
                sum(line["conf"] for b in blocks for line in b.get("lines", [])) / num_lines
                if num_lines else 0.0
            )
            steps.append({
                "name": "→ Nhận dạng văn bản (Tesseract OCR)",
                "status": "success" if raw_text else "warning",
                "description": (
                    f"Đã nhận {num_lines} dòng (độ tin cậy trung bình {avg_conf:.1f}%)."
                    if raw_text else "Không nhận dạng được dòng chữ nào."
                ),
                "image_url": None,
            })
        except Exception:
            steps.append({"name": "→ Nhận dạng văn bản (Tesseract OCR)", "status": "fail",
                          "description": "Lỗi khi chạy OCR.", "image_url": None})
            raise HTTPException(status_code=422, detail="Lỗi khi nhận dạng văn bản.")

        # ── Bóc tách CCCD & đối chiếu sinh viên ──────────────────────────────
        cccd = extract_cccd_info(
            raw_text,
            blocks=blocks,
            image_height=warped_bgr.shape[0],
        )

        student, match_note = _match_student_by_cccd(
            db,
            full_name=cccd.get("ho_va_ten"),
            birth_date=cccd.get("ngay_sinh"),
        )

        extracted_summary = " · ".join(
            f"{k}: {v}" for k, v in [
                ("Số CCCD", cccd.get("so_cccd")),
                ("Họ tên", cccd.get("ho_va_ten")),
                ("Ngày sinh", cccd.get("ngay_sinh")),
                ("Địa chỉ", cccd.get("dia_chi")),
            ] if v
        ) or "Không bóc được trường nào."

        if student:
            match_result = 1
            student_info = {
                **cccd,
                "student_id": student.student_id,
                "school": student.school,
                "email": student.email,
                "avatar_url": (
                    f"/images/avatar/student/{student.id}" if student.avatar_data else None
                ),
            }
            steps.append({
                "name": "→ Bóc tách CCCD & đối chiếu sinh viên",
                "status": "success",
                "description": f"Bóc được: {extracted_summary}. → {match_note}.",
                "image_url": None,
            })
        else:
            match_result = 0
            student_info = {**cccd, "student_id": None, "school": None, "email": None,
                            "avatar_url": None}
            steps.append({
                "name": "→ Bóc tách CCCD & đối chiếu sinh viên",
                "status": "fail" if any(cccd.get(k) for k in ("ho_va_ten", "so_cccd")) else "warning",
                "description": f"Bóc được: {extracted_summary}. → Không khớp sinh viên nào.",
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
            # Lưu vào student_cards: map các trường CCCD vào schema sinh viên
            #   full_name, birth_date: từ CCCD
            #   student_id, school, email: từ student record nếu khớp, ngược lại để trống
            db.add(StudentCard(
                scan_id=scan_record.id,
                user_id=current_user.id,
                full_name=cccd.get("ho_va_ten"),
                birth_date=cccd.get("ngay_sinh"),
                school=student.school if student else None,
                student_id=student.student_id if student else None,
                email=student.email if student else None,
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
            "extracted_info": cccd,
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {exc}") from exc
