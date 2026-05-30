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
