from __future__ import annotations

import base64
import io
import re
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


# ─── Helpers cho visualization các bước OCR ──────────────────────────────────

def img_to_data_url(image: np.ndarray, max_dim: int = 1000) -> str:
    """Mã hoá ảnh CV (BGR hoặc grayscale) → PNG data URL, có thu nhỏ nếu lớn."""
    if image is None:
        return ""
    img = image
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        return ""
    return f"data:image/png;base64,{base64.b64encode(buf.tobytes()).decode()}"


def draw_canny_preview(image: np.ndarray) -> np.ndarray:
    """Trả về ảnh edge map (Canny) để minh hoạ bước phát hiện biên."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    return cv2.cvtColor(edged, cv2.COLOR_GRAY2BGR)


def draw_quad_on_image(image: np.ndarray, quad: List[List[int]]) -> np.ndarray:
    """Vẽ tứ giác phát hiện được + chấm 4 góc lên bản copy của ảnh."""
    out = image.copy()
    pts = np.array(quad, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(out, [pts], isClosed=True, color=(0, 200, 60), thickness=4)
    labels = ["TL", "TR", "BR", "BL"]
    for i, (x, y) in enumerate(quad):
        cv2.circle(out, (int(x), int(y)), 14, (40, 40, 220), -1)
        cv2.circle(out, (int(x), int(y)), 16, (255, 255, 255), 2)
        cv2.putText(
            out, labels[i % 4], (int(x) + 18, int(y) + 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 220), 2, cv2.LINE_AA,
        )
    return out


def draw_ocr_blocks_on_image(image: np.ndarray, blocks: List[Dict[str, Any]]) -> np.ndarray:
    """Vẽ khung từng dòng OCR + số thứ tự lên bản copy của ảnh."""
    out = image.copy()
    idx = 1
    for blk in blocks:
        for line in blk.get("lines", []):
            x1, y1, x2, y2 = [int(v) for v in line["bbox"]]
            cv2.rectangle(out, (x1, y1), (x2, y2), (38, 38, 220), 2)
            label = str(idx)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 6, y1), (38, 38, 220), -1)
            cv2.putText(
                out, label, (x1 + 3, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA,
            )
            idx += 1
    return out


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


def _aspect_ratio_ok(quad: np.ndarray) -> bool:
    """Kiểm tra tỉ lệ cạnh có hợp lý với thẻ sinh viên không (~1.4 : 1, cho phép 1.0..2.5)."""
    rect = order_points(quad.astype("float32"))
    (tl, tr, br, bl) = rect
    w = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    h = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    if min(w, h) < 1: return False
    ratio = max(w, h) / min(w, h)
    return 1.0 <= ratio <= 2.5


def find_document_contour(image: np.ndarray) -> np.ndarray | None:
    """
    Phát hiện tứ giác tài liệu robust hơn:
    - Thử nhiều cặp ngưỡng Canny (tự động + tay)
    - Lọc theo aspect ratio (tránh nhặt nhầm khung dài)
    - Fallback minAreaRect khi approxPolyDP không ra 4 cạnh
    - min_area nới xuống 2% để chụp xa vẫn bắt được
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    h, w = image.shape[:2]
    min_area = (h * w) * 0.02
    max_area = (h * w) * 0.97

    # Tự động chọn ngưỡng Canny dựa trên median (Otsu's heuristic)
    median = float(np.median(blurred))
    auto_lo = int(max(0, 0.66 * median))
    auto_hi = int(min(255, 1.33 * median))

    threshold_sets = [
        (auto_lo, auto_hi),
        (50, 150),
        (30, 100),
        (75, 200),
    ]

    best_quad: np.ndarray | None = None
    best_area = 0.0

    for lo, hi in threshold_sets:
        edged = cv2.Canny(blurred, lo, hi)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if min_area < cv2.contourArea(c) < max_area]
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

        for contour in contours:
            peri = cv2.arcLength(contour, True)
            for tol in (0.01, 0.015, 0.02, 0.025, 0.03, 0.04):
                approx = cv2.approxPolyDP(contour, tol * peri, True)
                if len(approx) == 4:
                    quad = approx.reshape(4, 2)
                    area = cv2.contourArea(approx)
                    if min_area < area < max_area and _aspect_ratio_ok(quad) and area > best_area:
                        best_quad = quad
                        best_area = area
                        break
            # Fallback minAreaRect cho contour lớn nhất nếu không ra 4 cạnh
            if best_quad is None and cv2.contourArea(contour) > min_area * 2:
                rect = cv2.minAreaRect(contour)
                box = cv2.boxPoints(rect).astype(np.int32)
                if _aspect_ratio_ok(box):
                    area = cv2.contourArea(box)
                    if area > best_area:
                        best_quad = box
                        best_area = area

        if best_quad is not None:
            break  # đã tìm thấy với set ngưỡng đầu tiên tốt

    return best_quad


def _deskew(image: np.ndarray, max_angle: float = 15.0) -> np.ndarray:
    """
    Phát hiện góc nghiêng qua HoughLinesP rồi xoay bù.
    Chỉ xử lý góc nghiêng nhỏ (|angle| < max_angle) để tránh xoay nhầm.
    """
    if image is None or image.size == 0:
        return image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=100,
        minLineLength=min(gray.shape) // 3, maxLineGap=20,
    )
    if lines is None:
        return image
    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Chỉ giữ line gần ngang
        if abs(a) < max_angle:
            angles.append(a)
    if not angles:
        return image
    angle = float(np.median(angles))
    if abs(angle) < 0.3:
        return image
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


def warp_perspective(image: np.ndarray) -> WarpResult:
    contour = find_document_contour(image)
    if contour is None:
        h, w = image.shape[:2]
        quad = [[0, 0], [w, 0], [w, h], [0, h]]
        # Không có quad → vẫn cố gắng deskew để OCR đỡ gãy dòng
        return WarpResult(image=_deskew(image), quad=quad, used_warp=False)
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
    warped = _deskew(warped)
    quad = rect.astype(int).tolist()
    return WarpResult(image=warped, quad=quad, used_warp=True)


# ─── Preprocessing theo mode ─────────────────────────────────────────────────

def preprocess_for_qr(image: np.ndarray) -> List[np.ndarray]:
    """
    Trả về danh sách các biến thể ảnh để tăng tỷ lệ nhận diện QR.
    pyzbar tự xử lý xoay nên chỉ cần tập trung vào tương phản + scale.
    """
    variants: List[np.ndarray] = [image]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    variants.append(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR))

    # Otsu binary (rõ ràng hơn adaptive với QR đơn sắc)
    _, otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR))

    # Adaptive — fallback cho ánh sáng không đều
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))

    # Upscale 2x cho QR nhỏ (chụp xa)
    h, w = image.shape[:2]
    if max(h, w) < 1500:
        up = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        variants.append(up)

    # Sharpen cho QR nhòe do rung tay
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    variants.append(cv2.filter2D(image, -1, kernel))

    return variants


def preprocess_variants_for_ocr(image: np.ndarray) -> Tuple[List[Tuple[str, np.ndarray]], float]:
    """
    Trả về (variants, scale).
    - variants: list các biến thể preprocess (đã upscale)
    - scale: tỉ lệ upscale so với input. Bbox OCR cần chia cho scale để về không gian gốc.

    Triết lý: KHÔNG nhị phân hóa mạnh / morphology (phá dấu tiếng Việt).
    Ưu tiên grayscale tăng tương phản + làm nét, để Tesseract tự thresh cục bộ.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    # Upscale lên ~1800px để ký tự đủ lớn (~300 DPI cho thẻ kích thước thực).
    # Chữ quá nhỏ là nguyên nhân số 1 khiến Tesseract đọc ra rác.
    h, w = gray.shape
    scale = 1.0
    target = 1800
    if max(h, w) < target:
        scale = target / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # CLAHE nhẹ (clip 2.0) — tăng tương phản cục bộ mà không thổi phồng nhiễu
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Unsharp mask — làm nét nét chữ + dấu nhỏ, giúp Tesseract bắt dấu tiếng Việt
    blur = cv2.GaussianBlur(enhanced, (0, 0), 3)
    sharp = cv2.addWeighted(enhanced, 1.6, blur, -0.6, 0)

    variants: List[Tuple[str, np.ndarray]] = [
        # 1. Grayscale + CLAHE — giữ nguyên dấu, để Tesseract tự thresh (thường tốt nhất)
        ("clahe", enhanced),
        # 2. Grayscale đã làm nét — tốt cho chữ nhỏ / hơi nhòe
        ("sharp", sharp),
        # 3. Otsu binary — tốt khi nền đồng đều
        ("otsu", cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        # 4. Adaptive với block lớn — giữ dấu tốt hơn block nhỏ, fallback ánh sáng lệch
        ("adaptive", cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 12,
        )),
    ]
    return variants, scale


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """Backward-compat: trả về biến thể adaptive (dùng cho overlay/preview)."""
    variants, _ = preprocess_variants_for_ocr(image)
    for name, img in variants:
        if name == "adaptive":
            return img
    return variants[0][1]


# ─── CCCD Pipeline 7 bước (chuẩn nghiệp vụ) ─────────────────────────────────
#
# Mỗi step trả về (image, status_str, description) để router log lên FE:
#   step1_acquire       → ảnh BGR đã chuẩn hoá DPI
#   step2_roi           → ảnh đã crop về vùng thẻ + 4 góc (warp)
#   step3_denoise       → ảnh xám đã giảm nhiễu (median blur preserve edges)
#   step4_flatfield     → ảnh xám đã hiệu chỉnh độ đồng nhất ánh sáng
#   step5_threshold     → ảnh nhị phân (adaptive thresholding)
#   step6_morphology    → ảnh nhị phân đã tinh chỉnh hình thái
#   step7_skew_correct  → ảnh cuối đã deskew nhẹ (nếu còn nghiêng)

def _step3_denoise(image_bgr: np.ndarray) -> np.ndarray:
    """Grayscale + Median blur (giữ biên ký tự, triệt tiêu chấm nhiễu nhỏ)."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    # Median 3×3 giữ đường biên tốt hơn Gaussian cho text
    return cv2.medianBlur(gray, 3)


def _step4_flat_field(gray: np.ndarray) -> np.ndarray:
    """Hiệu chỉnh độ đồng nhất ánh sáng (xử lý glare/hotspot).

    Phương pháp Background Subtraction qua large-kernel Gaussian:
      1. Ước tính ma trận ánh sáng nền = blur cực mạnh (sigma lớn).
      2. Chia gray / bg, scale về [0..255] → triệt tiêu vùng cháy sáng.
    """
    # Kernel rất lớn để chỉ giữ low-frequency illumination
    h, w = gray.shape
    k = max(31, (min(h, w) // 8) | 1)   # odd, ~12.5% chiều ngắn nhất
    bg = cv2.GaussianBlur(gray, (k, k), 0)
    # Tránh chia 0
    bg = np.where(bg < 1, 1, bg)
    normalized = cv2.divide(gray, bg, scale=128).astype(np.uint8)
    # Stretch contrast nhẹ để chữ rõ
    normalized = cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)
    return normalized


def _step5_adaptive_threshold(gray_uniform: np.ndarray) -> np.ndarray:
    """Adaptive thresholding cục bộ → ảnh nhị phân (đen-trắng tuyệt đối).

    Dùng Gaussian-weighted local mean, block size lớn (25) để bắt nét chữ
    có dấu tiếng Việt, C=10 để giảm nhiễu nền sau flat-field.
    """
    binary = cv2.adaptiveThreshold(
        gray_uniform, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=25,
        C=10,
    )
    return binary


def _step6_morphology(binary: np.ndarray) -> np.ndarray:
    """Tinh chỉnh hình thái: nối nét đứt + tách ký tự dính + làm mượt biên.

    Trình tự:
      - Opening 2×2 với fine erosion: xoá vệt mực thừa siêu nhỏ.
      - Closing 2×2: nối lại các nét chữ bị đứt sau threshold.
    Lưu ý: text thường có giá trị 0 (đen), nền 255 → ta đảo về MORPH trên text.
    """
    # Đảo: text = trắng (255) để morphology hoạt động đúng nghĩa
    inv = cv2.bitwise_not(binary)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    # Opening: erosion → dilation (loại noise nhỏ, tách ký tự dính)
    cleaned = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel, iterations=1)
    # Closing: dilation → erosion (nối nét đứt, làm mượt)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Đảo trở lại: text = đen, nền = trắng (Tesseract thích hơn)
    return cv2.bitwise_not(cleaned)


def preprocess_cccd_pipeline(image_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Chạy đầy đủ 7 bước tiền xử lý cho ảnh CCCD.

    Returns:
        final: ảnh nhị phân cuối cùng (đã morph + deskew) sẵn sàng cho Tesseract.
        intermediates: dict các ảnh trung gian từng bước (để log/preview).
    """
    intermediates: Dict[str, np.ndarray] = {}

    # Bước 1: Image Acquisition — ảnh đã được resize_image() trước khi gọi vào đây
    intermediates["step1_acquire"] = image_bgr

    # Bước 2: ROI Detection — phát hiện & warp về dạng phẳng đứng
    warped = warp_perspective(image_bgr)
    intermediates["step2_roi"] = warped.image

    # Bước 3: Noise Reduction (Median blur)
    denoised = _step3_denoise(warped.image)
    intermediates["step3_denoise"] = denoised

    # Bước 4: Uniformity Correction / Flat-Fielding
    uniform = _step4_flat_field(denoised)
    intermediates["step4_flatfield"] = uniform

    # Bước 5: Local Adaptive Thresholding
    binary = _step5_adaptive_threshold(uniform)
    intermediates["step5_threshold"] = binary

    # Bước 6: Morphological Refinement & Cleanup
    refined = _step6_morphology(binary)
    intermediates["step6_morphology"] = refined

    # Bước 7: Skew Correction (deskew nhẹ — warp đã làm phẳng nhưng dòng chữ
    # vẫn có thể nghiêng nhỏ do biến dạng phôi thẻ)
    final = _deskew(refined, max_angle=8.0)
    intermediates["step7_skew_correct"] = final

    return final, intermediates


def ocr_cccd(roi_image: np.ndarray) -> tuple[str, List[Dict[str, Any]]]:
    """OCR cho ảnh CCCD đã warp về ROI.

    Nhận ảnh ROI (BGR hoặc xám) — KHÔNG phải ảnh nhị phân đã morphology.
    Lý do đổi cách làm: nhị phân hóa + morphology 2×2 phá hỏng dấu tiếng Việt
    và thiếu upscale làm chữ quá nhỏ → Tesseract đọc ra rác.

    Dùng ensemble (nhiều biến thể tiền xử lý nhẹ × nhiều PSM), gộp dòng theo
    confidence cao nhất — robust hơn nhiều so với 1 lần PSM 6.
    """
    # PSM 6 (uniform block) + PSM 4 (single column) — hợp với layout 2 cột của CCCD
    blocks = ocr_ensemble(roi_image, psms=(6, 4))
    # blocks đã được sort theo (y, x) trong _dedupe_lines → text đúng thứ tự trên→dưới
    lines = [line for b in blocks for line in b.get("lines", [])]
    raw_text = "\n".join(l["text"] for l in lines).strip()
    return raw_text, blocks


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

def _group_words_into_lines(data: Dict[str, List[str]], min_word_conf: float = 30.0) -> List[Dict[str, Any]]:
    """
    Gộp các word của Tesseract thành dòng.
    - Lọc word có conf < min_word_conf (giảm rác)
    - Confidence dòng = trung bình có trọng số theo độ dài word (thay vì min).
    """
    lines: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        conf = float(data["conf"][i]) if str(data["conf"][i]) != "-1" else 0.0
        if conf < min_word_conf:
            continue
        line_key = (data["block_num"][i], data["line_num"][i])
        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])
        if line_key not in lines:
            lines[line_key] = {
                "text": text,
                "bbox": [left, top, left + width, top + height],
                # weighted conf accumulator: (Σ conf*len, Σ len)
                "_conf_sum": conf * len(text),
                "_len_sum": len(text),
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
            line["_conf_sum"] += conf * len(text)
            line["_len_sum"] += len(text)

    out: List[Dict[str, Any]] = []
    for line in lines.values():
        conf = line["_conf_sum"] / line["_len_sum"] if line["_len_sum"] else 0.0
        out.append({"text": line["text"], "bbox": line["bbox"], "conf": conf})
    return out


def _best_tesseract_lang(prefer_vie_only: bool = True) -> str:
    """
    Lang detection:
    - prefer_vie_only=True: 'vie' thuần (giữ dấu tốt nhất cho thẻ SV Việt)
    - fallback: 'vie+eng' rồi 'eng'

    Lý do: 'vie+eng' khiến Tesseract đôi khi chọn token ASCII vì
    eng dictionary có likelihood cao hơn → mất dấu tiếng Việt.
    """
    try:
        langs = pytesseract.get_languages()
        if "vie" in langs:
            return "vie" if prefer_vie_only else "vie+eng"
    except Exception:
        pass
    return "eng"


def _bbox_iou(a: List[int], b: List[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, inter_x2 - inter_x1), max(0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def _dedupe_lines(lines: List[Dict[str, Any]], iou_thresh: float = 0.4) -> List[Dict[str, Any]]:
    """
    Khi chạy ensemble (nhiều variant × PSM), nhiều dòng cùng vị trí sẽ trùng.
    Giữ dòng có conf cao nhất trong mỗi cụm bbox chồng lấn.
    """
    sorted_lines = sorted(lines, key=lambda l: l["conf"], reverse=True)
    kept: List[Dict[str, Any]] = []
    for line in sorted_lines:
        if any(_bbox_iou(line["bbox"], k["bbox"]) > iou_thresh for k in kept):
            continue
        kept.append(line)
    # Sort cuối cùng theo y rồi x cho hiển thị
    kept.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    return kept


def ocr_preprocessed(preprocessed: np.ndarray) -> List[Dict[str, Any]]:
    """
    Backward-compat: chạy 1 lần OCR trên ảnh đã preprocess.
    Sử dụng PSM 6 + ngưỡng word conf 30%.
    """
    lang = _best_tesseract_lang()
    data = pytesseract.image_to_data(
        preprocessed,
        lang=lang,
        config="--psm 6 --oem 3",
        output_type=pytesseract.Output.DICT,
    )
    lines = _group_words_into_lines(data)
    return [
        {"type": "text", "bbox": l["bbox"], "lines": [l], "confidence": l["conf"]}
        for l in lines if l["conf"] >= 30
    ]


def _rescale_bbox(bbox: List[int], inv_scale: float) -> List[int]:
    return [int(round(v * inv_scale)) for v in bbox]


def ocr_ensemble(image: np.ndarray, psms: Tuple[int, ...] = (6, 4)) -> List[Dict[str, Any]]:
    """
    Chạy Tesseract trên (variant × PSM), gộp dòng theo confidence cao nhất.
    Bbox trả về thuộc không gian `image` đầu vào (đã rescale từ không gian upscaled).

    PSMs mặc định: 6 (uniform block) + 4 (single column). Bỏ PSM 11 (sparse text)
    vì gây nhiều dòng rác làm hỏng dedupe.
    """
    lang = _best_tesseract_lang(prefer_vie_only=True)
    variants, scale = preprocess_variants_for_ocr(image)
    inv_scale = 1.0 / scale if scale else 1.0

    all_lines: List[Dict[str, Any]] = []
    for variant_name, variant_img in variants:
        for psm in psms:
            try:
                data = pytesseract.image_to_data(
                    variant_img,
                    lang=lang,
                    config=f"--psm {psm} --oem 3",
                    output_type=pytesseract.Output.DICT,
                )
                lines = _group_words_into_lines(data)
                # Rescale bbox về không gian input
                for line in lines:
                    line["bbox"] = _rescale_bbox(line["bbox"], inv_scale)
                all_lines.extend(lines)
            except Exception:
                continue

    deduped = _dedupe_lines(all_lines)
    return [
        {"type": "text", "bbox": l["bbox"], "lines": [l], "confidence": l["conf"]}
        for l in deduped
    ]


def layout_and_ocr(image: np.ndarray) -> List[Dict[str, Any]]:
    """Wrapper: dùng ensemble OCR (nhiều variant × PSM) để có kết quả tốt nhất."""
    return ocr_ensemble(image)


# ─── Extract student info từ OCR text ────────────────────────────────────────

# ─── Vietnamese name patterns ────────────────────────────────────────────────

_VN_SURNAMES = {
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
    "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đào", "Đoàn", "Trịnh",
    "Đinh", "Mai", "Cao", "Tô", "Tạ", "Hà", "Lương", "Đậu", "Trương", "Lâm",
    "Châu", "Quách", "Tăng", "Thái", "Khúc", "Kim", "Lưu", "La", "Chu", "Bạch",
}

# Bảng ký tự hoa/thường có dấu tiếng Việt
_VN_UPPER = "A-ZĐÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ"
_VN_LOWER = "a-zđàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"

# Mỗi từ tên: 2-7 ký tự (Vietnamese name word hiếm khi dài hơn — "Thường", "Phương")
# Title case: chữ hoa đầu + 1..6 chữ thường ("Nguyễn", "Trương")
_NAME_WORD_TITLE = rf"[{_VN_UPPER}][{_VN_LOWER}]{{1,6}}"
# ALL CAPS: 2..7 chữ hoa ("TRƯƠNG", "NGUYỄN") — dùng cho CCCD
_NAME_WORD_UPPER = rf"[{_VN_UPPER}]{{2,7}}"

# Tên đầy đủ Title: 2..5 từ
_NAME_PATTERN = re.compile(rf"\b({_NAME_WORD_TITLE}(?:\s+{_NAME_WORD_TITLE}){{1,4}})\b")
# Tên đầy đủ ALL CAPS: 2..5 từ (CCCD format)
_NAME_PATTERN_UPPER = re.compile(rf"\b({_NAME_WORD_UPPER}(?:\s+{_NAME_WORD_UPPER}){{1,4}})\b")


def _strip_diacritics(s: str) -> str:
    """Bỏ dấu để so sánh (Nguyễn → Nguyen, Đức → Duc)."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s or "")
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    return cleaned.replace("đ", "d").replace("Đ", "D")


# Set surname không dấu để bắt OCR mất dấu (TRUONG, NGUYEN, ...)
_VN_SURNAMES_STRIPPED = {_strip_diacritics(s).lower() for s in _VN_SURNAMES}


def _is_vn_surname(word: str) -> bool:
    """Kiểm tra 1 từ có phải họ Việt phổ biến, chấp nhận title/upper/không dấu."""
    if not word:
        return False
    if word in _VN_SURNAMES:
        return True
    if word.title() in _VN_SURNAMES:
        return True
    if _strip_diacritics(word).lower() in _VN_SURNAMES_STRIPPED:
        return True
    return False


def _title_case_vn(name: str) -> str:
    """Title-case 1 tên (TRƯƠNG ANH ĐỨC → Trương Anh Đức)."""
    return " ".join(w.capitalize() for w in name.split())


_NAME_WORD_FULL_TITLE = re.compile(rf"^{_NAME_WORD_TITLE}$")
_NAME_WORD_FULL_UPPER = re.compile(rf"^{_NAME_WORD_UPPER}$")


def _is_name_word(w: str) -> bool:
    return bool(_NAME_WORD_FULL_TITLE.match(w) or _NAME_WORD_FULL_UPPER.match(w))


def _iter_name_candidates(text: str):
    """
    Sinh các candidate 2..5 từ tên liên tiếp từ text.
    Khác `re.finditer` (greedy, không overlap): trả về MỌI sub-window 2..5
    trong các run từ tên liên tiếp → tránh nuốt "Thành phố" cùng với tên thật.
    """
    tokens = re.split(r"\s+", text.strip())
    n = len(tokens)
    i = 0
    while i < n:
        if not _is_name_word(tokens[i]):
            i += 1
            continue
        # Run liên tiếp [i, j) các từ tên hợp lệ
        j = i
        while j < n and _is_name_word(tokens[j]):
            j += 1
        run_len = j - i
        if run_len >= 2:
            # Tạo mọi window 2..5 trong run, mọi offset bắt đầu
            for size in range(2, min(6, run_len + 1)):
                for start in range(i, j - size + 1):
                    yield " ".join(tokens[start:start + size])
        i = j

# OCR confusion: ký tự dễ nhầm giữa chữ và số
_OCR_CONFUSIONS = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1", "|": "1", "l": "1",
    "Z": "2", "S": "5", "B": "8",
    "G": "6", "T": "7", "A": "4",
}

# Header/label phổ biến trên thẻ SV — KHÔNG phải tên dù khớp pattern
_NAME_BLACKLIST = {
    "Trường", "Đại", "Học", "Viện", "Khoa", "Bộ", "Môn", "Sinh", "Viên",
    "Thẻ", "Giáo", "Dục", "Cao", "Đẳng", "Mã", "Số", "Họ", "Tên", "Ngày",
    "Tháng", "Năm", "Sinh", "Lớp", "Khóa", "Quốc", "Gia", "Việt", "Nam",
    "Identity", "Student", "Card", "University", "College", "School",
    "Department", "Faculty", "Date", "Birth", "Name", "Full",
}

# Các từ chỉ địa danh thường gặp — phạt mạnh khi xuất hiện trong candidate tên
_PLACE_NAME_PARTS = {
    "Nội", "Phố", "Tỉnh", "Cộng", "Hòa", "Hoà", "Xã", "Hội", "Chủ", "Nghĩa",
    "Bách", "Thành", "Hóa", "Hoá",
}

# Sửa lỗi OCR phổ biến cho text tiếng Việt
# Pattern: word-level substitution + character-level confusion in alphabetic context
_OCR_TEXT_FIXES = [
    # q ↔ g khi sau N (Nquyễn → Nguyễn)
    (re.compile(r"\bNq([uướờ])"), r"Ng\1"),
    (re.compile(r"\bnq([uướờ])"), r"ng\1"),
    # Vần → Văn (a/ă thường nhầm)
    (re.compile(r"\bV[àầ]n\b"), "Văn"),
    # Đực → Đức (chỉ áp dụng nếu đứng riêng, không phải động từ)
    (re.compile(r"\bĐực\b"), "Đức"),
    # 0 trong từ chữ → o/O
    (re.compile(r"([" + _VN_UPPER + r"])0(?=[" + _VN_LOWER + r"])"), r"\1o"),
    # 1 ở giữa chữ → l/i
    (re.compile(r"([" + _VN_LOWER + r"])1(?=[" + _VN_LOWER + r"])"), r"\1i"),
]


def fix_ocr_text(text: str) -> str:
    """Sửa các lỗi OCR phổ biến trên text tiếng Việt."""
    fixed = text
    for pattern, repl in _OCR_TEXT_FIXES:
        fixed = pattern.sub(repl, fixed)
    return fixed


# Các từ tiếng Anh/Việt phổ biến trên thẻ KHÔNG phải MSSV
_MSSV_WORD_BLACKLIST = {
    "REPUBLIC", "VIETNAM", "SOCIALIST", "IDENTITY", "STUDENT", "UNIVERSITY",
    "COLLEGE", "DEPARTMENT", "FACULTY", "PERSONAL", "PASSPORT",
    "DIPLOMA", "CERTIFICATE", "REGISTER", "REGISTRATION",
}


def _mssv_candidates(text: str, min_digits: int = 5) -> List[str]:
    """
    Sinh danh sách MSSV ứng viên từ text, có sửa các lỗi OCR phổ biến.
    - Yêu cầu ≥ min_digits chữ số (loại "REPUBLIC", "IDENTITY"...)
    - Bỏ qua các từ tiếng Anh phổ biến.
    """
    cands: List[str] = []
    seen: set = set()

    def _accept(cand: str) -> bool:
        if not (7 <= len(cand) <= 10):
            return False
        if cand in seen:
            return False
        if cand.upper() in _MSSV_WORD_BLACKLIST:
            return False
        # Bỏ token nguyên gốc là từ tiếng Anh (chỉ có chữ cái thuần)
        if cand.isalpha():
            return False
        digit_count = sum(c.isdigit() for c in cand)
        if digit_count < min_digits:
            return False
        return True

    # Tìm cụm 7-10 ký tự gồm chữ in hoa + số + ký tự dễ nhầm
    for m in re.finditer(r"[A-Z0-9OQDILZSBGT|l]{7,10}", text):
        raw = m.group(0)
        # Bản map toàn bộ → số (cho MSSV thuần số)
        fixed = "".join(_OCR_CONFUSIONS.get(c, c) for c in raw)
        for cand in (fixed, raw):
            cand_clean = cand.strip()
            if _accept(cand_clean):
                seen.add(cand_clean)
                cands.append(cand_clean)
    # Cũng thử thuần số gốc (đã đúng)
    for m in re.finditer(r"\b\d{7,10}\b", text):
        if _accept(m.group(0)):
            seen.add(m.group(0))
            cands.append(m.group(0))
    return cands


def _score_name_candidate(name: str, y_norm: float, line_conf: float) -> float:
    """Cho điểm 1 candidate tên để chọn cái tốt nhất."""
    words = name.split()
    if not words:
        return 0.0

    # Loại nếu BẤT KỲ từ nào trong blacklist (header label)
    # Check cả title case để bắt ALL CAPS header (TRƯỜNG → Trường ∈ blacklist)
    if any(w in _NAME_BLACKLIST or w.title() in _NAME_BLACKLIST for w in words):
        return -100.0

    score = line_conf / 10.0
    # Có họ Việt phổ biến → +15 (chấp nhận title/upper/không dấu)
    if _is_vn_surname(words[0]):
        score += 15.0
    # Bonus theo số từ (3-4 từ là tên Việt điển hình)
    if 3 <= len(words) <= 4:
        score += 8.0
    elif len(words) == 2:
        score += 3.0
    # Vị trí: bonus liên tục (0.0 đỉnh → +6, 1.0 đáy → 0)
    score += max(0, 6.0 * (1.0 - y_norm))
    # Phạt nếu chứa số
    if any(c.isdigit() for c in name):
        score -= 10.0
    # Phạt nếu candidate có >1 từ là surname (tên Việt thật chỉ có 1 surname ở đầu)
    surname_count = sum(1 for w in words if _is_vn_surname(w))
    if surname_count > 1:
        score -= 15.0
    # Phạt nếu chứa từ là place name part (Hà NỘI, Thanh HÓA, etc.)
    if any(w.title() in _PLACE_NAME_PARTS for w in words):
        score -= 10.0
    return score


def extract_student_info(
    raw_text: str,
    blocks: List[Dict[str, Any]] | None = None,
    image_height: int | None = None,
) -> dict:
    """
    Bóc tách thông tin sinh viên từ OCR.
    - Nếu có `blocks` (với bbox) và `image_height` → dùng spatial heuristics
      để chọn tên (ưu tiên nửa trên, ưu tiên dòng có họ Việt).
    - Tên không bắt buộc có nhãn "Họ tên".
    - MSSV thử thêm các candidate đã sửa lỗi OCR confusion.
    - Áp dụng fix_ocr_text để sửa lỗi OCR phổ biến trước khi extract.
    """
    # Sửa lỗi OCR trước khi extract
    text = fix_ocr_text(raw_text)

    # ── MSSV ────────────────────────────────────────────────────────────
    mssv_cands = _mssv_candidates(text)
    # Ưu tiên candidate là số thuần (8 chữ số là phổ biến nhất ở VN)
    mssv_cands.sort(key=lambda c: (not c.isdigit(), abs(len(c) - 8)))
    student_id = mssv_cands[0] if mssv_cands else None

    # ── Tên ─────────────────────────────────────────────────────────────
    full_name: str | None = None

    # 1. Ưu tiên có nhãn — chấp nhận cả title lẫn ALL CAPS
    # Tách 2 bước: tìm vị trí label (case-insensitive) → match name (case-sensitive)
    label_match = re.search(
        r"(?:H[oọ]\s+(?:v[aà]\s+)?t[eê]n|Full\s*Name)[:\s]+",
        text,
        re.IGNORECASE,
    )
    if label_match:
        after_label = text[label_match.end():].lstrip()
        name_match = re.match(
            rf"({_NAME_WORD_TITLE}(?:[ \t]+{_NAME_WORD_TITLE}){{1,4}}|"
            rf"{_NAME_WORD_UPPER}(?:[ \t]+{_NAME_WORD_UPPER}){{1,4}})",
            after_label,
        )
        if name_match:
            cand = name_match.group(1).strip()
            if not any(w in _NAME_BLACKLIST or w.title() in _NAME_BLACKLIST for w in cand.split()):
                full_name = cand

    # 2. Spatial scan qua từng line — chọn candidate điểm cao nhất
    if not full_name and blocks and image_height:
        best_score = -1.0
        for blk in blocks:
            for line in blk.get("lines", []):
                line_text = fix_ocr_text(line.get("text", ""))
                line_conf = line.get("conf", 0.0)
                bbox = line.get("bbox", [0, 0, 0, 0])
                y_center = (bbox[1] + bbox[3]) / 2.0
                y_norm = y_center / max(image_height, 1)
                for cand in _iter_name_candidates(line_text):
                    sc = _score_name_candidate(cand, y_norm, line_conf)
                    if sc > best_score:
                        best_score = sc
                        full_name = cand

    # 3. Fallback: scoring-based qua sliding window (chọn candidate điểm cao nhất)
    if not full_name:
        best_score = -1.0
        for cand in _iter_name_candidates(text):
            sc = _score_name_candidate(cand, y_norm=0.3, line_conf=80.0)
            if sc > best_score:
                best_score = sc
                full_name = cand

    # Chuẩn hoá: title-case nếu ALL CAPS, để hiển thị đẹp và so DB nhất quán
    if full_name and full_name.isupper():
        full_name = _title_case_vn(full_name)

    # ── Ngày sinh ───────────────────────────────────────────────────────
    birth_match = re.search(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})\b", text)

    # ── Trường, Viện ────────────────────────────────────────────────────
    school_match = re.search(
        r"(?:Tr[ưu][oờ]ng|Vi[eê]n|School)[:\s]+([^\n]{3,150})",
        text,
        re.IGNORECASE,
    )

    # ── Email ───────────────────────────────────────────────────────────
    email_match = re.search(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b", text)

    return {
        "full_name": full_name,
        "birth_date": birth_match.group(1) if birth_match else None,
        "school": school_match.group(1).strip() if school_match else None,
        "student_id": student_id,
        "student_id_candidates": mssv_cands,
        "email": email_match.group(0) if email_match else None,
    }


# ─── CCCD VN extraction ─────────────────────────────────────────────────────

# Số CCCD: 12 chữ số (CCCD mới gắn chip) hoặc 9 chữ số (CMND cũ)
_CCCD_NUMBER_RE = re.compile(r"\b(\d{12}|\d{9})\b")

# Ngày dd/mm/yyyy hoặc dd-mm-yyyy, dd.mm.yyyy
_DATE_RE = re.compile(r"\b(\d{1,2}[/\-.\s]\d{1,2}[/\-.\s]\d{4})\b")


def _normalize_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.match(r"(\d{1,2})[/\-.\s](\d{1,2})[/\-.\s](\d{4})", s.strip())
    if not m:
        return s.strip()
    d, mo, y = m.groups()
    return f"{int(d):02d}/{int(mo):02d}/{y}"


def _line_after_label(text: str, label_pattern: str, *, multiline: bool = False) -> str | None:
    """Trả về phần text NGAY SAU label trên 1 hoặc nhiều dòng.

    label_pattern: chuỗi regex bắt label (vd: r"Họ và tên|Full\s*name").
    multiline: nếu True, lấy luôn dòng kế tiếp nếu giá trị tràn xuống.
    """
    flags = re.IGNORECASE
    rx = re.compile(rf"(?:{label_pattern})\s*[:\-]?\s*(.+)", flags)
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        m = rx.search(ln)
        if not m:
            continue
        value = m.group(1).strip()
        if multiline and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            # Dòng kế tiếp được nối vào nếu nó KHÔNG bắt đầu bằng 1 label CCCD khác
            if nxt and not re.search(
                r"(Họ|Full|Ngày|Date|Giới|Sex|Quốc|Nationality|"
                r"Quê|Place|Nơi|Residence|Có giá|Expiry|Số|No\.?)",
                nxt,
                re.IGNORECASE,
            ):
                value = f"{value} {nxt}".strip()
        return value or None
    return None


def extract_cccd_info(
    raw_text: str,
    blocks: List[Dict[str, Any]] | None = None,
    image_height: int | None = None,
) -> dict:
    """Bóc các trường trên Căn cước công dân VN.

    Hiểu cả nhãn tiếng Việt lẫn tiếng Anh trên CCCD mới:
      - Số / No.
      - Họ và tên / Full name
      - Ngày, tháng, năm sinh / Date of birth
      - Giới tính / Sex
      - Quốc tịch / Nationality
      - Quê quán / Place of origin
      - Nơi thường trú / Place of residence
      - Có giá trị đến / Date of expiry
    """
    text = fix_ocr_text(raw_text)

    # ─── Số CCCD: ưu tiên 12 chữ số (CCCD gắn chip) trước 9 chữ số (CMND cũ) ──
    cccd_number = None
    cands = _CCCD_NUMBER_RE.findall(text)
    if cands:
        twelve = [c for c in cands if len(c) == 12]
        nine = [c for c in cands if len(c) == 9]
        cccd_number = (twelve or nine)[0]

    # ─── Họ và tên: uàu tin label, fallback spatial scan ──
    full_name = None
    raw_name = _line_after_label(text, r"Họ\s+và\s+tên|Họ\s+tên|Full\s*name")
    if raw_name:
        # CCCD tên thường ALL CAPS → chỉ lấy cụm 2..5 từ ALL CAPS đầu
        m = re.search(rf"({_NAME_WORD_UPPER}(?:\s+{_NAME_WORD_UPPER}){{1,4}})", raw_name)
        if m:
            full_name = _title_case_vn(m.group(1))
        else:
            # Trường hợp title-case
            m2 = re.search(rf"({_NAME_WORD_TITLE}(?:\s+{_NAME_WORD_TITLE}){{1,4}})", raw_name)
            if m2:
                full_name = m2.group(1)

    if not full_name and blocks and image_height:
        # Fallback: scoring spatial như student card
        best_score = -1.0
        for blk in blocks:
            for line in blk.get("lines", []):
                line_text = fix_ocr_text(line.get("text", ""))
                line_conf = line.get("conf", 0.0)
                bbox = line.get("bbox", [0, 0, 0, 0])
                y_center = (bbox[1] + bbox[3]) / 2.0
                y_norm = y_center / max(image_height, 1)
                for cand in _iter_name_candidates(line_text):
                    sc = _score_name_candidate(cand, y_norm, line_conf)
                    if sc > best_score:
                        best_score = sc
                        full_name = cand
        if full_name and full_name.isupper():
            full_name = _title_case_vn(full_name)

    # ─── Ngày sinh ──
    birth_raw = _line_after_label(
        text, r"Ngày[,\s]*tháng[,\s]*năm\s+sinh|Ngày\s+sinh|Date\s+of\s+birth|DOB"
    )
    birth_date = None
    if birth_raw:
        m = _DATE_RE.search(birth_raw)
        if m:
            birth_date = _normalize_date(m.group(1))
    if not birth_date:
        # fallback: lấy date đầu tiên trong text (CCCD thường có 2 date: sinh + hết hạn)
        all_dates = _DATE_RE.findall(text)
        if all_dates:
            birth_date = _normalize_date(all_dates[0])

    # ─── Giới tính ──
    sex_raw = _line_after_label(text, r"Giới\s+tính|Sex")
    sex = None
    if sex_raw:
        if re.search(r"\bNam\b|\bMale\b|\bM\b", sex_raw, re.IGNORECASE):
            sex = "Nam"
        elif re.search(r"\bNữ\b|\bFemale\b|\bF\b", sex_raw, re.IGNORECASE):
            sex = "Nữ"

    # ─── Quốc tịch ──
    nationality_raw = _line_after_label(text, r"Quốc\s+tịch|Nationality")
    nationality = None
    if nationality_raw:
        # Bỏ các ký tự rác, lấy đến dấu xuống dòng/label kế
        m = re.match(r"([A-Za-zÀ-ỹ\s]+)", nationality_raw)
        if m:
            nationality = m.group(1).strip()
        # Mặc định: nếu có từ "Việt Nam" trong text
        if not nationality and re.search(r"Việt\s+Nam|Vietnam", text, re.IGNORECASE):
            nationality = "Việt Nam"

    # ─── Quê quán ──
    hometown = _line_after_label(
        text, r"Quê\s+quán|Place\s+of\s+origin|Nguyên\s+quán", multiline=True
    )

    # ─── Nơi thường trú ──
    residence = _line_after_label(
        text, r"Nơi\s+thường\s+trú|Place\s+of\s+residence|Thường\s+trú",
        multiline=True,
    )

    # ─── Có giá trị đến ──
    expiry_raw = _line_after_label(
        text, r"Có\s+giá\s+trị\s+đến|Date\s+of\s+expiry|Expiry"
    )
    expiry = None
    if expiry_raw:
        m = _DATE_RE.search(expiry_raw)
        if m:
            expiry = _normalize_date(m.group(1))
    if not expiry:
        # fallback: date cuối cùng trong text nếu khác birth_date
        all_dates = _DATE_RE.findall(text)
        norm_all = [_normalize_date(d) for d in all_dates]
        if birth_date and birth_date in norm_all:
            others = [d for d in norm_all if d != birth_date]
            if others:
                expiry = others[-1]

    # Họ tên: giữ ALL CAPS theo đặc tả output JSON
    ho_va_ten = full_name.upper() if full_name else None

    # Địa chỉ: ưu tiên Nơi thường trú, fallback Quê quán
    dia_chi = residence or hometown

    return {
        # ─ Schema chính theo đặc tả nghiệp vụ (4 trường tiếng Việt) ─
        "ho_va_ten": ho_va_ten,
        "so_cccd": cccd_number,
        "ngay_sinh": birth_date,
        "dia_chi": dia_chi,
        # ─ Các trường phụ (giữ để matching + lịch sử) ─
        "sex": sex,
        "nationality": nationality,
        "hometown": hometown,
        "residence": residence,
        "expiry": expiry,
    }
