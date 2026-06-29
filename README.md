# TADIZB Scanner

Ứng dụng web quét **thẻ sinh viên (QR)** và **Căn cước công dân (OCR)** cho ĐHBK Hà Nội. Khi đọc được dữ liệu, hệ thống đối chiếu với danh sách sinh viên trong DB và lưu lại lịch sử quét.

---

## Tính năng

- **QR thẻ sinh viên** — quét tự động qua camera, phát hiện QR ngay tại trình duyệt (jsQR) rồi mới gọi server để parse MSSV + đối chiếu DB.
- **OCR Căn cước công dân** — chụp ảnh CCCD VN, server warp + OCR (Tesseract ensemble) + bóc các trường (số CCCD, họ tên, ngày sinh, giới tính, quốc tịch, quê quán, nơi thường trú, ngày hết hạn) + fuzzy match sinh viên theo họ tên + ngày sinh.
- **Tài khoản** — đăng nhập trường bằng email `@sis.hust.edu.vn` hoặc `@hust.edu.vn`, hoặc dùng tài khoản username thường. Cookie session đơn giản, không JWT.
- **Hồ sơ cá nhân** — sửa thông tin, đổi avatar, xem thống kê quét (tổng/QR/OCR/lookup/matched).
- **Lịch sử quét** — xem lại từng phiên cùng ảnh đã warp.
- **PWA** — cài đặt được như app.

---

## Kiến trúc

```
┌─────────────────────────────┐
│  Frontend (React + Vite)    │  HTTPS dev :3000
│  • react-router-dom         │
│  • react-day-picker         │
│  • jsQR (client-side QR)    │
│  • react-webcam             │
└─────────────┬───────────────┘
              │  Axios + Cookie (withCredentials)
┌─────────────▼───────────────┐
│  Backend (FastAPI)          │  :8000
│  • 5 router: auth / profile │
│    / students / scan /      │
│    history                  │
│  • Tesseract OCR ensemble   │
│  • OpenCV warp + Canny      │
│  • pyzbar QR fallback       │
│  • rapidfuzz matching       │
└─────────────┬───────────────┘
              │  SQLAlchemy
┌─────────────▼───────────────┐
│  PostgreSQL (pgAdmin4)      │
│  users / students /         │
│  scan_history /             │
│  student_cards              │
└─────────────────────────────┘
```

DB quản lý thủ công qua pgAdmin4 — không Alembic, không Docker.

---

## Cài đặt

### Yêu cầu
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (chạy local + tạo DB qua pgAdmin4)
- Tesseract OCR binary với `vie` traineddata (Windows: `choco install tesseract`)

### Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Tạo backend/.env (xem .env.example)
# DATABASE_URL=postgresql://postgres:<password>@localhost:5432/<db>
# ALLOWED_ORIGINS=http://localhost:3000

uvicorn app.main:app --reload --port 8000
```

### Frontend
```powershell
cd frontend
npm install
npm run dev       # https://localhost:3000 (cert tự ký — accept ở browser)
```

### Schema DB
Schema khởi tạo bằng SQL chạy tay trong pgAdmin4 (xem CLAUDE.md hoặc liên hệ tác giả để có file SQL khởi tạo).

---

## Endpoints chính

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/register/hust` | Đăng ký email trường |
| `POST` | `/register/local` | Đăng ký username thường |
| `POST` | `/login` | Đăng nhập (identifier + password) |
| `POST` | `/logout` | Đăng xuất |
| `GET`  | `/me` | Thông tin user |
| `GET`  | `/me/profile` | Profile + stats |
| `PATCH`| `/me` | Sửa full_name + birth_date |
| `POST` | `/me/avatar` | Upload avatar |
| `POST` | `/process-scan` | QR / OCR pipeline chính |
| `GET`  | `/students/lookup` | Tra cứu sinh viên theo MSSV |
| `GET`  | `/scan-history` | Danh sách lịch sử |
| `GET`  | `/scan-history/{id}` | Chi tiết 1 lần quét |
| `GET`  | `/images/scan/{id}` | Ảnh đã warp |
| `GET`  | `/images/avatar/student/{id}` | Avatar sinh viên |

---

## Tác giả
**Trương Anh Đức** — đồ án tốt nghiệp ĐHBK Hà Nội.
