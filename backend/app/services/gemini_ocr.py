from __future__ import annotations

import json
import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Các khoá trùng khít với extract_cccd_info() — KHÔNG đổi tên.
_CCCD_KEYS = (
    "ho_va_ten", "so_cccd", "ngay_sinh", "dia_chi",
    "sex", "nationality", "hometown", "residence", "expiry",
)

_PROMPT = """Bạn là hệ thống trích xuất dữ liệu từ ảnh giấy tờ tuỳ thân Việt Nam
(Căn cước công dân / CCCD / CMND). Đọc ảnh và trả về DUY NHẤT một object JSON
với đúng các khoá sau (không thêm khoá khác; trường nào không có thì để null):

- ho_va_ten: họ và tên đầy đủ, GIỮ NGUYÊN dấu tiếng Việt
- so_cccd: số CCCD/CMND (chỉ chữ số)
- ngay_sinh: ngày sinh, định dạng dd/mm/yyyy
- dia_chi: nơi thường trú / địa chỉ đầy đủ
- sex: giới tính (Nam/Nữ)
- nationality: quốc tịch
- hometown: quê quán
- residence: nơi thường trú
- expiry: ngày hết hạn (dd/mm/yyyy nếu có)
- raw_text: toàn bộ văn bản đọc được trên ảnh (giữ ký tự xuống dòng)

Chỉ in ra JSON, không giải thích, không bọc trong markdown."""


_FACE_PROMPT = """Bạn nhận được HAI ảnh:
- Ảnh 1: giấy tờ tuỳ thân (CCCD/CMND) có in ảnh chân dung của chủ thẻ.
- Ảnh 2: ảnh đại diện của một sinh viên trong hồ sơ trường.

Hãy xác định khuôn mặt người trong ảnh chân dung ở Ảnh 1 và so sánh với khuôn
mặt ở Ảnh 2 để kết luận có phải CÙNG MỘT NGƯỜI hay không.

Trả về DUY NHẤT một object JSON với đúng các khoá sau:
- ket_qua: một trong "khop" | "khong_khop" | "khong_chac"
- do_tin_cay: số nguyên 0-100 (độ tin cậy của kết luận)
- nhan_xet: giải thích ngắn gọn bằng tiếng Việt (điểm giống/khác, chất lượng ảnh)

Chỉ in ra JSON, không giải thích thêm, không bọc trong markdown."""

_FACE_VERDICTS = ("khop", "khong_khop", "khong_chac")


def _client():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=500,
            detail="Hệ thống chưa cấu hình GEMINI_API_KEY. Vui lòng liên hệ quản trị.",
        )
    try:
        from google import genai
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Server thiếu thư viện google-genai (pip install google-genai).",
        ) from exc
    return genai.Client(api_key=key)


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # Phòng khi model lỡ bọc trong ```json ... ```
        cleaned = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(cleaned)


def extract_cccd_with_gemini(image_bytes: bytes, mime: str = "image/jpeg") -> tuple[str, dict]:
    """Gửi ảnh lên Gemini → (raw_text, cccd_dict) cùng shape extract_cccd_info()."""
    from google.genai import types

    client = _client()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime or "image/jpeg"),
                _PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — gói mọi lỗi Gemini thành 502 cho FE
        logger.error("Gọi Gemini thất bại: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Không gọi được Gemini. Kiểm tra API key/hạn mức rồi thử lại.",
        ) from exc

    try:
        data = _parse_json(resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini trả JSON không hợp lệ: %r", (resp.text or "")[:300])
        raise HTTPException(status_code=502, detail="Gemini trả dữ liệu không hợp lệ.") from exc

    cccd = {k: (data.get(k) or None) for k in _CCCD_KEYS}
    raw_text = data.get("raw_text") or json.dumps(
        {k: v for k, v in cccd.items() if v}, ensure_ascii=False, indent=2
    )
    return raw_text, cccd


def compare_faces(
    card_bytes: bytes,
    card_mime: str,
    avatar_bytes: bytes,
    avatar_mime: str,
) -> dict:
    """So khớp khuôn mặt trên giấy tờ (card) với ảnh đại diện sinh viên (avatar).

    Trả về dict {ket_qua, do_tin_cay, nhan_xet}. KHÔNG raise: đây là bước phụ,
    lỗi Gemini chỉ làm trường này thành 'loi' chứ không hỏng cả lần quét.
    """
    from google.genai import types

    try:
        client = _client()
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        resp = client.models.generate_content(
            model=model,
            contents=[
                "Ảnh 1 (giấy tờ tuỳ thân):",
                types.Part.from_bytes(data=card_bytes, mime_type=card_mime or "image/jpeg"),
                "Ảnh 2 (ảnh đại diện sinh viên):",
                types.Part.from_bytes(data=avatar_bytes, mime_type=avatar_mime or "image/jpeg"),
                _FACE_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        data = _parse_json(resp.text)
    except Exception as exc:  # noqa: BLE001 — bước phụ, nuốt lỗi
        logger.error("So khớp khuôn mặt Gemini thất bại: %s", exc)
        return {"ket_qua": "loi", "do_tin_cay": 0,
                "nhan_xet": "Không thực hiện được so khớp khuôn mặt."}

    verdict = data.get("ket_qua")
    if verdict not in _FACE_VERDICTS:
        verdict = "khong_chac"
    try:
        conf = int(float(data.get("do_tin_cay") or 0))
    except (ValueError, TypeError):
        conf = 0
    conf = max(0, min(100, conf))
    return {"ket_qua": verdict, "do_tin_cay": conf, "nhan_xet": data.get("nhan_xet") or ""}
