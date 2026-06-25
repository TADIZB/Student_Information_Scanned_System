"""Chạy check_login (Playwright sync) trong MỘT TIẾN TRÌNH RIÊNG.

Vì sao cần tiến trình riêng: trên Windows, Playwright sync phải spawn subprocess
trình duyệt qua asyncio — việc này chỉ chạy được trên ProactorEventLoop. Khi gọi
check_login từ threadpool của uvicorn (đặc biệt ở chế độ --reload), worker thread
lại tạo SelectorEventLoop → create_subprocess_exec ném NotImplementedError → 502.

Chạy ở tiến trình con (main thread, ProactorEventLoop mặc định của Windows) thì
Playwright hoạt động bình thường, độc lập hoàn toàn với event loop của server.

Giao tiếp:
  - stdin : JSON {"email": "...", "password": "..."}
  - stdout: JSON {"ok": true/false} hoặc {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure the backend root is importable when this file is executed as a script.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
        from app.services.microsoft_login import check_login

        ok = bool(check_login(payload["email"], payload["password"]))
        sys.stdout.write(json.dumps({"ok": ok}))
        return 0
    except Exception as exc:  # noqa: BLE001 — báo lỗi về tiến trình cha qua stdout
        sys.stdout.write(json.dumps({"ok": False, "error": repr(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
