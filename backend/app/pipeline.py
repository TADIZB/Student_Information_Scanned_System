from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps


@dataclass
class WarpResult:
    image: np.ndarray
    quad: List[List[int]]
    used_warp: bool


# ─── Tiện ích ảnh ────────────────────────────────────────────────────────────

def load_image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    return ImageOps.exif_transpose(image)


def resize_image(image: Image.Image, max_dim: int = 2000) -> Image.Image:
    width, height = image.size
    scale = min(1.0, max_dim / max(width, height))
    if scale >= 1.0:
        return image
    new_size = (int(width * scale), int(height * scale))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def pil_to_cv(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def cv_to_pil(image: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


# ─── Warp perspective ────────────────────────────────────────────────────────

def order_points(points: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def find_document_contour(image: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = image.shape[:2]
    min_area = (h * w) * 0.05
    max_area = (h * w) * 0.95
    contours = [c for c in contours if min_area < cv2.contourArea(c) < max_area]
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        for tolerance in [0.01, 0.015, 0.02, 0.025, 0.03]:
            approx = cv2.approxPolyDP(contour, tolerance * peri, True)
            if len(approx) == 4:
                area = cv2.contourArea(approx)
                if min_area < area < max_area:
                    return approx.reshape(4, 2)
    return None


def warp_perspective(image: np.ndarray) -> WarpResult:
    contour = find_document_contour(image)
    if contour is None:
        h, w = image.shape[:2]
        quad = [[0, 0], [w, 0], [w, h], [0, h]]
        return WarpResult(image=image, quad=quad, used_warp=False)
    rect = order_points(contour.astype("float32"))
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))
    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, matrix, (max_width, max_height))
    quad = rect.astype(int).tolist()
    return WarpResult(image=warped, quad=quad, used_warp=True)


# ─── Preprocessing theo mode ─────────────────────────────────────────────────

def preprocess_for_qr(image: np.ndarray) -> List[np.ndarray]:
    """
    Trả về danh sách các biến thể ảnh để tăng tỷ lệ nhận diện QR.
    pyzbar sẽ thử lần lượt đến khi tìm được QR.
    """
    variants: List[np.ndarray] = [image]  # Thử ảnh gốc trước

    # Tăng độ tương phản bằng CLAHE trên kênh grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    variants.append(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR))

    # Adaptive threshold (nhị phân hóa cục bộ)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))

    # Xoay 90°, 180°, 270° — QR lệch góc vẫn nhận được
    for angle in (90, 180, 270):
        center = (image.shape[1] // 2, image.shape[0] // 2)
        rot_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, rot_matrix, (image.shape[1], image.shape[0]))
        variants.append(rotated)

    return variants


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Xử lý ảnh để tối ưu cho Tesseract OCR:
    grayscale → CLAHE → adaptive threshold → denoise.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Phóng to nếu ảnh quá nhỏ (Tesseract cần ít nhất ~150 DPI)
    h, w = gray.shape
    if max(h, w) < 800:
        scale = 800 / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # CLAHE tăng độ tương phản đều
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Adaptive threshold: chuyển về ảnh đen trắng, giảm noise nền
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8
    )

    # Denoise nhẹ để bỏ chấm nhiễu nhỏ
    denoised = cv2.medianBlur(binary, 3)

    return denoised


# ─── QR Detection ────────────────────────────────────────────────────────────

def detect_qr(image: np.ndarray) -> str | None:
    """
    Quét QR trên nhiều biến thể ảnh (gốc, tăng tương phản, xoay).
    Trả về chuỗi dữ liệu đầu tiên tìm được, None nếu không có.
    """
    try:
        from pyzbar.pyzbar import decode

        for variant in preprocess_for_qr(image):
            decoded_objects = decode(variant)
            for obj in decoded_objects:
                data = obj.data.decode("utf-8").strip()
                if data:
                    return data
    except Exception:
        pass
    return None


# ─── OCR ─────────────────────────────────────────────────────────────────────

def _group_words_into_lines(data: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    lines: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        line_key = (data["block_num"][i], data["line_num"][i])
        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])
        conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0
        if line_key not in lines:
            lines[line_key] = {
                "text": text,
                "bbox": [left, top, left + width, top + height],
                "conf": conf,
            }
        else:
            line = lines[line_key]
            line["text"] = f"{line['text']} {text}".strip()
            x1, y1, x2, y2 = line["bbox"]
            line["bbox"] = [
                min(x1, left),
                min(y1, top),
                max(x2, left + width),
                max(y2, top + height),
            ]
            line["conf"] = min(line["conf"], conf)
    return list(lines.values())


def _best_tesseract_lang() -> str:
    """Ưu tiên tiếng Việt nếu được cài, fallback sang eng."""
    try:
        langs = pytesseract.get_languages()
        if "vie" in langs:
            return "vie+eng"
    except Exception:
        pass
    return "eng"


def layout_and_ocr(image: np.ndarray) -> List[Dict[str, Any]]:
    """
    Chạy Tesseract trên ảnh đã được tối ưu hóa cho OCR.
    Trả về các block chữ với bbox để vẽ overlay.
    """
    preprocessed = preprocess_for_ocr(image)
    lang = _best_tesseract_lang()

    # PSM 6: giả định một block văn bản đồng nhất (phù hợp với thẻ)
    config = f"--psm 6 --oem 3"
    data = pytesseract.image_to_data(
        preprocessed,
        lang=lang,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    lines = _group_words_into_lines(data)
    blocks: List[Dict[str, Any]] = []
    for line in lines:
        if line["conf"] < 5:  # Chỉ bỏ kết quả hoàn toàn vô nghĩa
            continue
        blocks.append(
            {
                "type": "text",
                "bbox": line["bbox"],
                "lines": [line],
                "confidence": line["conf"],
            }
        )
    return blocks


# ─── Extract student info từ OCR text ────────────────────────────────────────

def extract_student_info(raw_text: str) -> dict:
    """
    Bóc tách thông tin sinh viên từ raw OCR text bằng regex.
    Hỗ trợ cả chữ hoa/thường và dấu tiếng Việt.
    """
    import re

    # Mã sinh viên: 7-10 chữ số, có thể có tiền tố 1-3 chữ cái (vd: SV12345678)
    student_id_match = re.search(r'\b([A-Z]{0,3}\d{7,10})\b', raw_text, re.IGNORECASE)

    # Họ tên: tìm sau nhãn "Họ và tên", "Họ tên", "Name"
    name_match = re.search(
        r'(?:H[oọ]\s+(?:v[aà]\s+)?t[eê]n|Full\s*Name)[:\s]+([^\n\d]{3,60})',
        raw_text,
        re.IGNORECASE,
    )

    # Ngày sinh: dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy
    birth_match = re.search(r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b', raw_text)

    # Trường, Viện: sau "Trường", "Viện", "School"
    school_match = re.search(
        r'(?:Tr[ưu][oờ]ng|Vi[eê]n|School)[:\s]+([^\n]{3,150})',
        raw_text,
        re.IGNORECASE,
    )

    # Email
    email_match = re.search(r'\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b', raw_text)

    return {
        "full_name": name_match.group(1).strip() if name_match else None,
        "birth_date": birth_match.group(1) if birth_match else None,
        "school": school_match.group(1).strip() if school_match else None,
        "student_id": student_id_match.group(1).strip() if student_id_match else None,
        "email": email_match.group(0) if email_match else None,
    }
