"""Gửi email qua SMTP bằng stdlib (smtplib + email.mime).

Cấu hình lấy từ biến môi trường (.env):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
Ví dụ Gmail: smtp.gmail.com:587, user = email, pass = App Password 16 ký tự.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import HTTPException

from .otp_service import OTP_TTL_MINUTES

logger = logging.getLogger(__name__)


def _smtp_config() -> dict:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    if not (host and user and password):
        raise HTTPException(
            status_code=500,
            detail="Hệ thống chưa cấu hình SMTP để gửi email. Vui lòng liên hệ quản trị.",
        )
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587") or "587"),
        "user": user,
        "password": password,
        "sender": os.getenv("SMTP_FROM", "").strip() or user,
    }


def send_otp_email(to_email: str, code: str) -> None:
    """Gửi mã 6 số tới địa chỉ email (đồng bộ — chạy trong threadpool của FastAPI)."""
    cfg = _smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Mã xác nhận đăng ký TADIZB Scanner"
    msg["From"] = cfg["sender"]
    msg["To"] = to_email

    text = (
        f"Mã xác nhận đăng ký TADIZB Scanner của bạn là: {code}\n"
        f"Mã có hiệu lực trong {OTP_TTL_MINUTES} phút. "
        f"Nếu bạn không yêu cầu, vui lòng bỏ qua email này."
    )
    html = f"""\
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:480px;margin:auto">
  <h2 style="color:#0f142c">TADIZB Scanner</h2>
  <p>Mã xác nhận đăng ký tài khoản trường của bạn là:</p>
  <p style="font-size:32px;font-weight:700;letter-spacing:8px;color:#2563eb">{code}</p>
  <p style="color:#555">Mã có hiệu lực trong <b>{OTP_TTL_MINUTES} phút</b>.
  Nếu bạn không yêu cầu, vui lòng bỏ qua email này.</p>
</div>"""

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.starttls(context=context)
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["sender"], [to_email], msg.as_string())
    except Exception as exc:  # noqa: BLE001 — gói mọi lỗi SMTP thành 502 cho FE
        logger.error("Gửi OTP tới %s thất bại: %s", to_email, exc)
        raise HTTPException(
            status_code=502,
            detail="Không gửi được email xác nhận. Vui lòng thử lại sau ít phút.",
        ) from exc
