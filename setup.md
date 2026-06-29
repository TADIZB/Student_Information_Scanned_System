# Hướng dẫn cài đặt TADIZB Scanner

Tài liệu này hướng dẫn cài dự án trên Windows bằng PowerShell. Dự án gồm:

- Backend: Python, FastAPI, PostgreSQL, Gemini API và Playwright.
- Frontend: React, TypeScript và Vite.
- Database: PostgreSQL, quản lý schema thủ công; dự án không dùng Docker hoặc Alembic.

## 1. Yêu cầu hệ thống

Cài các công cụ sau trước khi bắt đầu:

- Git.
- Python 3.10 trở lên.
- Node.js 18 trở lên và npm.
- PostgreSQL 14 trở lên; có thể dùng pgAdmin 4 để tạo database và chạy SQL.
- Tesseract OCR cùng bộ ngôn ngữ `vie`.
- Gemini API key để dùng chức năng OCR CCCD và so khớp khuôn mặt.

Kiểm tra các công cụ đã cài:

```powershell
git --version
python --version
node --version
npm --version
psql --version
tesseract --version
```

Nếu PowerShell không cho phép kích hoạt virtual environment, chạy một lần:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 2. Lấy mã nguồn

Nếu chưa có mã nguồn trên máy:

```powershell
git clone <URL_REPOSITORY>
cd GR2
```

Các lệnh còn lại trong tài liệu giả định terminal đang đứng tại thư mục gốc `GR2`.

## 3. Cài backend

Tạo virtual environment ở thư mục gốc và cài thư viện Python:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\backend\requirements.txt
```

Cài Chromium cho Playwright (cần cho đăng nhập tài khoản HUST):

```powershell
python -m playwright install chromium
```

Kiểm tra Tesseract có bộ dữ liệu tiếng Việt:

```powershell
tesseract --list-langs
```

Danh sách kết quả cần có `eng` và `vie`. Nếu Windows không nhận lệnh `tesseract`, thêm thư mục cài Tesseract (thường là `C:\Program Files\Tesseract-OCR`) vào biến môi trường `PATH`, rồi mở terminal mới.

## 4. Tạo database PostgreSQL

Trong pgAdmin 4, tạo database tên `QR`, mở Query Tool của database đó và chạy:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
```

Sau đó chạy lần lượt các khối `CREATE TABLE` theo thứ tự dưới đây trong [postgres.md](./postgres.md):

1. `users`
2. `students`
3. `scan_history`
4. `student_cards`
5. `email_otps`

Phải giữ đúng thứ tự vì các bảng có khóa ngoại. Backend không tự tạo bảng và cũng không tự chạy migration.

## 5. Cấu hình backend

Tạo file `backend/.env` và điền cấu hình sau:

```dotenv
# PostgreSQL
DATABASE_URL=postgresql+psycopg2://postgres:<MAT_KHAU_POSTGRES>@localhost:5432/QR

# Frontend được phép gọi API
ALLOWED_ORIGINS=https://localhost:3000,http://localhost:3000

# Gemini OCR
GEMINI_API_KEY=<GEMINI_API_KEY>
GEMINI_MODEL=gemini-2.5-flash

# Gửi OTP qua email (ví dụ Gmail SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<EMAIL_GUI_OTP>
SMTP_PASSWORD=<APP_PASSWORD>
SMTP_FROM=<EMAIL_GUI_OTP>

# Chỉ cần khi dùng đăng nhập tài khoản trường.
# URL phải chứa đúng placeholder {encoded_email}.
HUST_SSO_LOGIN_URL_TEMPLATE=<SSO_URL_CO_CHUA_{encoded_email}>
```

Lưu ý:

- Không commit file `.env`; file này đã được khai báo trong `.gitignore`.
- Với Gmail, `SMTP_PASSWORD` phải là App Password, không phải mật khẩu Gmail thông thường.
- Nếu chưa cấu hình SMTP, đăng ký tài khoản và quên mật khẩu qua OTP sẽ không hoạt động.
- Nếu chưa cấu hình `HUST_SSO_LOGIN_URL_TEMPLATE` hoặc Chromium, đăng nhập bằng tài khoản trường sẽ không hoạt động.
- Nếu chưa cấu hình `GEMINI_API_KEY`, chế độ OCR CCCD sẽ trả lỗi cấu hình.

## 6. Cài frontend

```powershell
cd .\frontend
npm install
cd ..
```

Ở môi trường phát triển không cần tạo file `.env` cho frontend: Vite tự proxy các API sang `http://localhost:8000`.

Nếu frontend gọi một backend khác, tạo `frontend/.env.local`:

```dotenv
VITE_API_BASE=https://example.com
```

## 7. Chạy dự án

Mở hai cửa sổ PowerShell.

Terminal 1 — backend:

```powershell
cd <DUONG_DAN_DEN_GR2>
.\.venv\Scripts\Activate.ps1
cd .\backend
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — frontend:

```powershell
cd <DUONG_DAN_DEN_GR2>\frontend
npm run dev
```

Truy cập:

- Frontend: `https://localhost:3000`
- API health check: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

Vite dùng chứng chỉ HTTPS tự ký. Ở lần truy cập đầu, trình duyệt có thể hiện cảnh báo; chọn tiếp tục truy cập localhost để camera hoạt động.

## 8. Kiểm tra cài đặt

Chạy test backend từ thư mục `backend`:

```powershell
cd .\backend
pytest
cd ..
```

Kiểm tra frontend có build thành công:

```powershell
cd .\frontend
npm run build
cd ..
```

Kiểm tra kết nối cơ bản bằng trình duyệt hoặc PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Kết quả mong đợi:

```text
status
------
ok
```

## 9. Lỗi thường gặp

### `password authentication failed for user postgres`

Kiểm tra lại user, mật khẩu, port và tên database trong `DATABASE_URL`.

### `relation ... does not exist`

Schema chưa được tạo hoặc backend đang kết nối nhầm database. Chạy đủ SQL trong `postgres.md` trên đúng database `QR`.

### `tesseract is not installed or it's not in your PATH`

Cài Tesseract, thêm thư mục chứa `tesseract.exe` vào `PATH`, sau đó mở lại terminal.

### Playwright báo thiếu executable Chromium

Kích hoạt virtual environment rồi chạy:

```powershell
python -m playwright install chromium
```

### Frontend không gọi được backend hoặc bị lỗi CORS

Đảm bảo backend chạy ở port `8000`, frontend chạy ở port `3000`, và `ALLOWED_ORIGINS` có `https://localhost:3000`.

### Trình duyệt không cho dùng camera

Mở đúng địa chỉ HTTPS `https://localhost:3000`, chấp nhận chứng chỉ localhost và cấp quyền camera cho trang.

