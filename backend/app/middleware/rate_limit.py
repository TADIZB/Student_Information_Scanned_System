"""Rate-limit đơn giản theo IP, dùng in-memory dict.

LƯU Ý: bộ đếm chỉ tồn tại trong RAM của 1 process — nếu chạy nhiều worker / nhiều pod,
cần đẩy lên Redis. Đủ dùng cho dev và 1 instance backend.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request


# Cấu hình mặc định cho /process-scan: 20 request / phút / IP.
_WINDOW_SECONDS = 60
_MAX_REQUESTS = 20

# Map: ip -> deque[timestamp]
_buckets: dict[str, deque[float]] = {}
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """Lấy IP client (có hỗ trợ X-Forwarded-For khi đặt sau proxy)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_process_scan(request: Request) -> None:
    """FastAPI dependency: chặn nếu IP vượt quá _MAX_REQUESTS trong _WINDOW_SECONDS."""
    ip = _client_ip(request)
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        bucket = _buckets.setdefault(ip, deque())
        # Dọn các timestamp đã ra khỏi cửa sổ
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= _MAX_REQUESTS:
            retry_after = max(1, int(bucket[0] + _WINDOW_SECONDS - now))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Bạn đang quét quá nhanh ({_MAX_REQUESTS} request/{_WINDOW_SECONDS}s). "
                    f"Vui lòng thử lại sau {retry_after}s."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)


# ─── Rate-limit gửi OTP đăng ký (chống spam mail) ─────────────────────────────
# Giới hạn riêng theo email và theo IP.
_OTP_EMAIL_MAX, _OTP_EMAIL_WINDOW = 3, 600     # 3 mã / 10 phút / email
_OTP_IP_MAX, _OTP_IP_WINDOW = 10, 3600         # 10 mã / giờ / IP

_otp_email_buckets: dict[str, deque[float]] = {}
_otp_ip_buckets: dict[str, deque[float]] = {}


def _peek_retry(buckets: dict[str, deque[float]], key: str, max_req: int, window: int, now: float) -> int:
    """Dọn timestamp cũ; trả về số giây phải chờ nếu đã đầy, ngược lại 0."""
    bucket = buckets.setdefault(key, deque())
    cutoff = now - window
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= max_req:
        return max(1, int(bucket[0] + window - now))
    return 0


def enforce_otp_rate_limit(email: str, ip: str) -> None:
    """Chặn nếu email hoặc IP yêu cầu mã quá nhiều. Tính cả hai trước khi ghi nhận."""
    now = time.monotonic()
    with _lock:
        retry = _peek_retry(_otp_email_buckets, email, _OTP_EMAIL_MAX, _OTP_EMAIL_WINDOW, now)
        if retry:
            raise HTTPException(
                status_code=429,
                detail=f"Bạn đã yêu cầu mã quá nhiều lần. Vui lòng thử lại sau {retry}s.",
                headers={"Retry-After": str(retry)},
            )
        retry = _peek_retry(_otp_ip_buckets, ip, _OTP_IP_MAX, _OTP_IP_WINDOW, now)
        if retry:
            raise HTTPException(
                status_code=429,
                detail=f"Quá nhiều yêu cầu gửi mã từ thiết bị này. Vui lòng thử lại sau {retry}s.",
                headers={"Retry-After": str(retry)},
            )
        _otp_email_buckets[email].append(now)
        _otp_ip_buckets[ip].append(now)
