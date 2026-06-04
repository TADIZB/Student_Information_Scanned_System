"""Lấy ảnh đại diện sinh viên từ endpoint ảnh công khai của HUST.

Khác với `GetUserByQRCode` (cần JWT SSO — xem reference), endpoint ảnh dưới đây
truy cập ẩn danh chỉ bằng MSSV và trả về một CHUỖI JSON là base64 JPEG, hoặc
chuỗi "chua co anh" khi sinh viên chưa có ảnh.

    GET https://ctsv.hust.edu.vn/ctsv-img/getimagebystudentid?mssv=<MSSV>
    → "/9j/4AAQ..."  (JSON-encoded base64 JPEG)
    → "chua co anh"  (không có ảnh)
"""
from __future__ import annotations

import base64
import json
from urllib.parse import quote
from urllib.request import Request, urlopen

_IMG_URL = "https://ctsv.hust.edu.vn/ctsv-img/getimagebystudentid?mssv={mssv}"
_TIMEOUT = 8  # giây — không để treo request quét


def fetch_student_avatar(mssv: str) -> tuple[bytes, str] | None:
    """Tải ảnh đại diện sinh viên theo MSSV.

    Returns (image_bytes, mime) nếu lấy được ảnh hợp lệ, ngược lại None
    (chưa có ảnh, lỗi mạng, hoặc response không hợp lệ — luôn nuốt lỗi để
    không làm hỏng luồng quét).
    """
    if not mssv or not mssv.strip():
        return None

    url = _IMG_URL.format(mssv=quote(mssv.strip()))
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="ignore").strip()
    except Exception:
        return None

    if not raw:
        return None

    # Response là một chuỗi JSON (có dấu nháy bao ngoài) → bóc lấy nội dung.
    try:
        b64 = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        b64 = raw.strip('"')

    if not isinstance(b64, str):
        return None
    b64 = b64.strip()
    if not b64 or b64.lower() == "chua co anh":
        return None

    # Có thể kèm tiền tố data URL — cắt bỏ phần "data:image/...;base64,".
    if b64.startswith("data:"):
        _, _, b64 = b64.partition(",")

    try:
        img = base64.b64decode(b64, validate=False)
    except Exception:
        return None

    if len(img) < 100:
        return None

    # Nhận diện MIME theo magic bytes (mặc định JPEG).
    mime = "image/jpeg"
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif img[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"

    return img, mime
