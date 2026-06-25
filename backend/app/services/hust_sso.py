"""Xác thực tài khoản trường (HUST SSO) qua worker Playwright riêng.

app.services.microsoft_login dùng Playwright (sync) mở headless Chromium, điền mật khẩu vào
sso.hust.edu.vn rồi kiểm tra URL trả về. Trên Windows, Playwright sync KHÔNG
chạy được trong threadpool của uvicorn (worker thread tạo SelectorEventLoop,
không spawn được subprocess trình duyệt → NotImplementedError). Vì vậy ở đây ta
chạy nó trong MỘT TIẾN TRÌNH CON (xem hust_login_worker.py), nơi Playwright hoạt
động bình thường, độc lập với event loop của server.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

# Thời gian tối đa cho cả luồng đăng nhập SSO (mở trình duyệt + điền + chờ mạng).
_TIMEOUT_SECONDS = 90
_WORKER = Path(__file__).resolve().parent / "hust_login_worker.py"
logger = logging.getLogger(__name__)


def check_login(email: str, password: str) -> bool:
    """Trả True nếu email + mật khẩu đăng nhập HUST SSO thành công.

    Chạy ở tiến trình con; raise nếu tiến trình con lỗi (để router trả 502 và
    ghi log) — phân biệt với trường hợp đăng nhập sai (trả False → 401).
    """
    logger.info("Starting HUST SSO worker for email=%s", email)
    proc = subprocess.run(
        [sys.executable, str(_WORKER)],
        input=json.dumps({"email": email, "password": password}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_TIMEOUT_SECONDS,
    )

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if err:
        logger.info("HUST SSO worker stderr for email=%s:\n%s", email, err)
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Worker đăng nhập trả output không hợp lệ "
            f"(stdout={out!r}, stderr={(proc.stderr or '').strip()!r})"
        ) from exc

    if data.get("error"):
        raise RuntimeError(f"Worker đăng nhập lỗi: {data['error']}")
    ok = bool(data.get("ok", False))
    logger.info(
        "HUST SSO worker finished for email=%s returncode=%s ok=%s",
        email,
        proc.returncode,
        ok,
    )
    return ok


__all__ = ["check_login"]
