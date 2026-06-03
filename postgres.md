# PostgreSQL — TADIZB Scanner

Tài liệu schema database của dự án. **Cập nhật: 2026-06-03**.

## Tổng quan

- **Database:** `QR`
- **Kết nối:** `postgresql://postgres:<password>@localhost:5432/QR` (đặt trong `backend/.env` qua biến `DATABASE_URL`).
- **Quản lý schema:** THỦ CÔNG qua **pgAdmin4**. Dự án **KHÔNG dùng Alembic, KHÔNG dùng Docker**.
- **Quy ước:** KHÔNG có migration tự động chạy lúc khởi động (`database.py` chỉ tạo engine).
- **Lưu trữ ảnh:** mọi ảnh (scan + avatar) lưu thẳng dạng `BYTEA` trong DB, không dùng filesystem.
- **Extension cần có:** `pgcrypto` (cho `gen_random_uuid()`).

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
```

## Sơ đồ quan hệ

```
users (1) ──< (N) scan_history >── (N..1) students
  │                   │
  │                   └──< (1..1) student_cards
  └──< (N) student_cards
  └──< (N) email_otps (liên kết logic qua email, không FK)

students (1) ──< (N) scan_history.matched_student_id
```

- `scan_history.user_id` → `users.id` **ON DELETE CASCADE**
- `scan_history.matched_student_id` → `students.id` **ON DELETE SET NULL**
- `student_cards.user_id` → `users.id` **ON DELETE CASCADE**
- `student_cards.scan_id` → `scan_history.id` **ON DELETE SET NULL**

---

## Bảng

### 1. `users` — tài khoản đăng nhập

Đăng ký 2 cách: **username thường** HOẶC **email** (có OTP xác thực). Auth bằng cookie `user_id` (HttpOnly, 7 ngày) — không JWT, không session table.

```sql
CREATE TABLE users (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(100) UNIQUE,                 -- nullable
    password_hash  VARCHAR(255) NOT NULL,               -- bcrypt
    email          VARCHAR(200) UNIQUE,                 -- nullable, validate app-side
    full_name      VARCHAR(200),
    birth_date     VARCHAR(20),                         -- ISO 'yyyy-mm-dd' (string)
    avatar_data    BYTEA,                               -- ảnh đại diện ≤ 2MB
    avatar_mime    VARCHAR(20),                         -- image/jpeg | png | webp | gif
    email_verified BOOLEAN      NOT NULL DEFAULT false, -- true sau khi xác thực OTP
    created_at     TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT users_identity_chk CHECK (username IS NOT NULL OR email IS NOT NULL)
);
```

- `CHECK users_identity_chk`: bắt buộc có ít nhất `username` hoặc `email`.
- `email` UNIQUE → quan hệ username ↔ email là 1:1, dùng cho khôi phục mật khẩu.

### 2. `students` — kho sinh viên gốc (POOL DÙNG CHUNG toàn hệ thống)

Nguồn đối chiếu cho cả QR lẫn OCR. **Không lọc theo user** — bất kỳ tài khoản nào cũng tra cứu được. Khi quét QR, mọi MSSV đọc được đều được tạo/bổ sung vào đây (kể cả khi chưa đăng nhập).

```sql
CREATE TABLE students (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id   VARCHAR(20)  NOT NULL UNIQUE,  -- MSSV
    full_name    VARCHAR(200),
    birth_date   VARCHAR(20),
    school       VARCHAR(200),                  -- Trường / Viện
    email        VARCHAR(200),
    avatar_data  BYTEA,
    avatar_mime  VARCHAR(20),
    study_status INTEGER,                       -- HUST: 1=Đang học, 0=Nghỉ học, NULL=chưa rõ
    created_at   TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX idx_students_student_id ON students(student_id);
```

### 3. `scan_history` — lịch sử mỗi lần quét (chỉ lưu khi ĐÃ đăng nhập)

```sql
CREATE TABLE scan_history (
    id                 UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_data         BYTEA,                  -- ảnh đã warp (PNG)
    image_mime         VARCHAR(20),            -- thường 'image/png'
    raw_text           TEXT,                   -- text OCR thô (OCR mode)
    qr_data            TEXT,                   -- chuỗi raw từ QR (QR mode)
    scan_type          VARCHAR(10),            -- 'qr' | 'ocr' | 'lookup'
    match_result       SMALLINT,               -- NULL=N/A · 0=không khớp · 1=khớp
    matched_student_id UUID REFERENCES students(id) ON DELETE SET NULL,
    created_at         TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_scan_history_user ON scan_history(user_id);
CREATE INDEX idx_scan_history_time ON scan_history(created_at DESC);
```

### 4. `student_cards` — snapshot thông tin tại thời điểm quét (chỉ lưu khi ĐÃ đăng nhập)

```sql
CREATE TABLE student_cards (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id      UUID         REFERENCES scan_history(id) ON DELETE SET NULL,
    user_id      UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    full_name    VARCHAR(200),
    birth_date   VARCHAR(20),
    school       VARCHAR(200),
    student_id   VARCHAR(20),
    email        VARCHAR(200),
    avatar_data  BYTEA,                         -- (còn trong DB, hiện không dùng)
    avatar_mime  VARCHAR(20),
    study_status INTEGER,
    created_at   TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX idx_student_cards_user   ON student_cards(user_id);
CREATE INDEX idx_student_cards_scan   ON student_cards(scan_id);
CREATE INDEX idx_student_cards_stu_id ON student_cards(student_id);
```

> ⚠️ `avatar_data`/`avatar_mime` còn tồn tại trong DB nhưng **không có** trong model `StudentCard` (`models.py`). KHÔNG truyền 2 cột này vào constructor `StudentCard(...)` — sẽ gây `TypeError` → HTTP 500.

### 5. `email_otps` — mã OTP chờ xác thực khi đăng ký / quên mật khẩu

```sql
CREATE TABLE email_otps (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email      VARCHAR(200) NOT NULL,
    code_hash  VARCHAR(255) NOT NULL,           -- CHỈ lưu sha256, không lưu mã thô
    expires_at TIMESTAMP    NOT NULL,           -- hạn ~10 phút
    attempts   SMALLINT     NOT NULL DEFAULT 0, -- chặn dò mã, tối đa 5
    created_at TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX idx_email_otps_email ON email_otps(email);
```


## Khởi tạo từ đầu (fresh setup)

Chạy theo thứ tự trong pgAdmin4 trên database `QR`:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- Sau đó chạy lần lượt CREATE TABLE: users → students → scan_history → student_cards → email_otps
-- (xem phần "Bảng" ở trên; thứ tự quan trọng vì FK).
```

```sql
ALTER TABLE students      ADD COLUMN IF NOT EXISTS study_status INTEGER;
ALTER TABLE student_cards ADD COLUMN IF NOT EXISTS study_status INTEGER;
```

---


## Lưu ý vận hành

- Backend chạy bằng venv `D:\Coding\GR2\.venv` (Python 3.10) + `uvicorn app.main:app --reload --port 8000`.
- `scan_history` & `student_cards` **chỉ ghi khi user đăng nhập** (có cookie `user_id`). Quét khi chưa đăng nhập vẫn tạo/bổ sung `students` nhưng không lưu lịch sử.
- `match_result`: `1` = khớp sinh viên trong `students`, `0` = không khớp, `NULL` = không áp dụng.
- `birth_date` lưu dạng string, không phải kiểu `DATE` — để giữ nguyên định dạng hiển thị trên thẻ/CCCD.
