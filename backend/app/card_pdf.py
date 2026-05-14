from __future__ import annotations

import io
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def build_card_pdf(
    full_name: Optional[str],
    birth_date: Optional[str],
    school: Optional[str],
    student_id: Optional[str],
    email: Optional[str],
    avatar_bytes: Optional[bytes] = None,
) -> bytes:
    """
    Tạo PDF mẫu thẻ sinh viên điện tử bằng ReportLab.
    Kích thước chuẩn ISO 7810 ID-1: 85.6 × 54 mm.
    Trả về bytes để stream về client.
    """
    CARD_W = 85.6 * mm
    CARD_H = 54.0 * mm

    MARGIN = 5 * mm
    BLUE_DARK = colors.HexColor("#1a3a6b")
    GOLD = colors.HexColor("#f5a623")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(CARD_W, CARD_H))

    # ── Nền thẻ màu xanh đậm ──────────────────────────────────────────────────
    pdf.setFillColor(BLUE_DARK)
    pdf.rect(0, 0, CARD_W, CARD_H, fill=1, stroke=0)

    # ── Dải tiêu đề màu vàng ─────────────────────────────────────────────────
    HEADER_H = 13 * mm
    pdf.setFillColor(GOLD)
    pdf.rect(0, CARD_H - HEADER_H, CARD_W, HEADER_H, fill=1, stroke=0)

    pdf.setFillColor(BLUE_DARK)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(CARD_W / 2, CARD_H - 8 * mm, "THE SINH VIEN  /  STUDENT CARD")

    # ── Logo placeholder (hình tròn bên trái tiêu đề) ─────────────────────────
    logo_cx = MARGIN + 6 * mm
    logo_cy = CARD_H - HEADER_H - 8 * mm
    pdf.setFillColor(colors.white)
    pdf.circle(logo_cx, logo_cy, 5.5 * mm, fill=1, stroke=0)
    pdf.setFillColor(BLUE_DARK)
    pdf.setFont("Helvetica-Bold", 5)
    pdf.drawCentredString(logo_cx, logo_cy - 1.5 * mm, "LOGO")

    # ── Ô ảnh sinh viên (bên phải) ────────────────────────────────────────────
    PHOTO_W = 18 * mm
    PHOTO_H = 22 * mm
    PHOTO_X = CARD_W - MARGIN - PHOTO_W
    PHOTO_Y = CARD_H - HEADER_H - PHOTO_H - 2 * mm

    pdf.setFillColor(colors.HexColor("#d4dce8"))
    pdf.rect(PHOTO_X, PHOTO_Y, PHOTO_W, PHOTO_H, fill=1, stroke=0)
    if avatar_bytes:
        pdf.drawImage(
            ImageReader(io.BytesIO(avatar_bytes)),
            PHOTO_X, PHOTO_Y, PHOTO_W, PHOTO_H,
            preserveAspectRatio=True, anchor="c", mask="auto",
        )
    else:
        pdf.setFillColor(BLUE_DARK)
        pdf.setFont("Helvetica", 5)
        pdf.drawCentredString(PHOTO_X + PHOTO_W / 2, PHOTO_Y + PHOTO_H / 2, "Photo")

    # ── Hàm vẽ một trường thông tin (label + value cùng dòng) ─────────────────
    def draw_field(label: str, value: Optional[str], y: float) -> None:
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.setFillColor(GOLD)
        pdf.drawString(MARGIN + 13 * mm, y, f"{label}:")
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(colors.white)
        label_w = pdf.stringWidth(f"{label}:", "Helvetica-Bold", 6.5)
        pdf.drawString(MARGIN + 13 * mm + label_w + 2, y, value or "---")

    # ── Thông tin sinh viên ───────────────────────────────────────────────────
    draw_field("Ho Ten/Name",   full_name,  CARD_H - HEADER_H - 7 * mm)
    draw_field("Ngay Sinh/DOB", birth_date, CARD_H - HEADER_H - 13 * mm)
    draw_field("Truong, Vien",  school,     CARD_H - HEADER_H - 19 * mm)
    draw_field("MSSV/ID No.",   student_id, CARD_H - HEADER_H - 25 * mm)
    draw_field("Email",         email,      CARD_H - HEADER_H - 31 * mm)

    # ── Dải chân trang ────────────────────────────────────────────────────────
    FOOTER_H = 5.5 * mm
    pdf.setFillColor(GOLD)
    pdf.rect(0, 0, CARD_W, FOOTER_H, fill=1, stroke=0)
    pdf.setFillColor(BLUE_DARK)
    pdf.setFont("Helvetica", 4.8)
    pdf.drawCentredString(CARD_W / 2, 1.8 * mm, "Khong co gia tri thay the CMND / CCCD")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()
