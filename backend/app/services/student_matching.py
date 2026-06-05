"""Các hàm hỗ trợ đối chiếu sinh viên (so MSSV/fuzzy tên) — tách khỏi router để tái sử dụng."""
from __future__ import annotations

import unicodedata

from sqlalchemy.orm import Session as DBSession

from ..models import Student


def _strip_diacritics(s: str) -> str:
    """Bỏ dấu để so sánh fuzzy (Nguyễn → Nguyen, Đức → Duc)."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    return cleaned.replace("đ", "d").replace("Đ", "D")


def derive_contact_email(full_name: str | None, student_id: str | None) -> str | None:
    """Suy ra email liên lạc @sis.hust.edu.vn theo quy ước HUST.

    Quy ước: ``<Tên>.<viết tắt họ+đệm><MSSV bỏ tiền tố '20'>@sis.hust.edu.vn``
    Ví dụ: "Trương Anh Đức" + 20225814 → ``Duc.TA225814@sis.hust.edu.vn``.

    LƯU Ý: MSSV HUST có thể 8 HOẶC 9 chữ số → KHÔNG cắt cứng "6 số cuối"
    (sẽ sai với mã 9 số). Thay vào đó bỏ tiền tố thế kỷ "20" — chung cho mọi
    MSSV HUST — nên cả 20225814 (→225814) lẫn mã 9 số (vd 202412345→2412345)
    đều ra đúng phần số.
    """
    if not full_name or not student_id:
        return None

    # Phần số: chỉ giữ chữ số, bỏ tiền tố "20" (không phụ thuộc độ dài 8/9).
    digits = "".join(ch for ch in student_id if ch.isdigit())
    if len(digits) < 8:
        return None
    num = digits[2:] if digits.startswith("20") else digits

    # Phần tên: tách từ (đã bỏ dấu). Cần ít nhất họ + tên.
    parts = [p for p in _strip_diacritics(full_name).split() if p]
    if len(parts) < 2:
        return None
    ten = parts[-1].capitalize()                          # tên gọi: "Duc"
    initials = "".join(p[0] for p in parts[:-1]).upper()  # họ + đệm: "TA"

    return f"{ten}.{initials}{num}@sis.hust.edu.vn"


def _match_student(
    db: DBSession,
    mssv_candidates: list[str],
    extracted_name: str | None,
) -> tuple[Student | None, str]:
    """
    Tra cứu sinh viên theo nhiều chiến lược:
    1. MSSV exact (thử từng candidate đã sửa OCR confusion)
    2. Fuzzy tên có dấu (token_set_ratio >= 82)
    3. Fuzzy tên BỎ DẤU (token_set_ratio >= 88) — bắt ca OCR mất dấu

    Returns: (student, strategy_note)
    """
    # Strategy 1: MSSV exact
    for mssv in mssv_candidates:
        st = db.query(Student).filter(Student.student_id == mssv).first()
        if st:
            return st, f"khớp MSSV '{mssv}'"

    # Strategy 2 + 3: Fuzzy name match (case-insensitive)
    if extracted_name and extracted_name.strip():
        try:
            from rapidfuzz import fuzz
            students = db.query(Student).filter(Student.full_name.isnot(None)).all()
            name_lc = extracted_name.lower().strip()
            name_stripped_lc = _strip_diacritics(extracted_name).lower().strip()

            best_st: Student | None = None
            best_score = 0
            best_strategy = ""

            for s in students:
                if not s.full_name:
                    continue
                db_lc = s.full_name.lower().strip()
                db_stripped_lc = _strip_diacritics(s.full_name).lower().strip()
                # 2a. So với dấu (lowercase)
                sc_dia = fuzz.token_set_ratio(name_lc, db_lc)
                # 2b. So không dấu (cao hơn vì OCR hay mất dấu)
                sc_strip = fuzz.token_set_ratio(name_stripped_lc, db_stripped_lc)

                # Ưu tiên: có dấu cao → tin cậy hơn không dấu cao
                if sc_dia >= 82 and sc_dia > best_score:
                    best_score = sc_dia
                    best_st = s
                    best_strategy = f"fuzzy có dấu ({sc_dia}%)"
                elif sc_strip >= 88 and sc_strip > best_score and sc_dia < 82:
                    best_score = sc_strip
                    best_st = s
                    best_strategy = f"fuzzy không dấu ({sc_strip}%)"

            if best_st:
                return best_st, f"{best_strategy}: '{extracted_name}' → '{best_st.full_name}'"
        except ImportError:
            pass

    return None, ""


def _normalize_birth_for_compare(b: str | None) -> str | None:
    """Chuẩn hoá ngày sinh về dd/mm/yyyy để so sánh (DB có thể lưu yyyy-mm-dd hoặc dd/mm/yyyy)."""
    if not b:
        return None
    s = b.strip()
    import re
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    return s


def _match_student_by_cccd(
    db: DBSession,
    full_name: str | None,
    birth_date: str | None,
) -> tuple[Student | None, str]:
    """Tra cứu sinh viên từ thông tin CCCD bằng full_name + birth_date.

    Chiến lược (ưu tiên giảm dần):
    1. Khớp họ tên (fuzzy ≥ 86%) VÀ ngày sinh trùng (chuẩn hoá format) → match cao.
    2. Khớp họ tên không dấu (fuzzy ≥ 90%) VÀ ngày sinh trùng.
    3. Chỉ khớp tên fuzzy ≥ 90% (không có ngày sinh) → match yếu.
    """
    if not (full_name and full_name.strip()):
        return None, ""

    try:
        from rapidfuzz import fuzz
    except ImportError:
        return None, ""

    name_lc = full_name.lower().strip()
    name_stripped_lc = _strip_diacritics(full_name).lower().strip()
    target_birth = _normalize_birth_for_compare(birth_date)

    students = db.query(Student).filter(Student.full_name.isnot(None)).all()
    best: tuple[Student, int, str] | None = None  # (student, score, note)

    for s in students:
        if not s.full_name:
            continue
        db_lc = s.full_name.lower().strip()
        db_stripped_lc = _strip_diacritics(s.full_name).lower().strip()
        s_birth = _normalize_birth_for_compare(s.birth_date)

        sc_dia = fuzz.token_set_ratio(name_lc, db_lc)
        sc_strip = fuzz.token_set_ratio(name_stripped_lc, db_stripped_lc)

        birth_match = bool(target_birth and s_birth and target_birth == s_birth)

        # Strategy 1: tên có dấu cao + birth khớp
        if sc_dia >= 86 and birth_match:
            score = sc_dia + 10  # bonus cho birth khớp
            note = f"khớp tên có dấu ({sc_dia}%) + ngày sinh"
            if best is None or score > best[1]:
                best = (s, score, note)
                continue

        # Strategy 2: tên không dấu cao + birth khớp
        if sc_strip >= 90 and birth_match:
            score = sc_strip + 5
            note = f"khớp tên không dấu ({sc_strip}%) + ngày sinh"
            if best is None or score > best[1]:
                best = (s, score, note)
                continue

        # Strategy 2.5: CCCD CÓ ngày sinh nhưng SV trong DB CHƯA có ngày sinh
        # (vd: sinh viên được tạo khi quét QR — URL HUST không kèm ngày sinh).
        # Không thể xác nhận bằng ngày sinh nên đòi tên khớp RẤT cao, điểm thấp
        # hơn các nhánh có xác nhận ngày sinh. Chỉ chạy khi s_birth rỗng nên KHÔNG
        # khớp nhầm trường hợp hai ngày sinh khác nhau.
        if target_birth and not s_birth:
            if sc_dia >= 90:
                if best is None or sc_dia > best[1]:
                    best = (s, sc_dia, f"khớp tên có dấu ({sc_dia}%), SV chưa có ngày sinh để xác nhận")
                continue
            if sc_strip >= 92:
                if best is None or sc_strip > best[1]:
                    best = (s, sc_strip, f"khớp tên không dấu ({sc_strip}%), SV chưa có ngày sinh để xác nhận")
                continue

        # Strategy 3: chỉ tên (yếu hơn nếu không có birth để xác nhận)
        if not target_birth:
            if sc_dia >= 90:
                if best is None or sc_dia > best[1]:
                    best = (s, sc_dia, f"khớp tên có dấu ({sc_dia}%)")
            elif sc_strip >= 92:
                if best is None or sc_strip > best[1]:
                    best = (s, sc_strip, f"khớp tên không dấu ({sc_strip}%)")

    if best:
        return best[0], best[2]
    return None, ""


def _student_to_dict(s: Student, scan_id: str | None = None) -> dict:
    # Email liên lạc: ưu tiên giá trị đã lưu, nếu trống thì suy ra từ tên + MSSV.
    email = s.email or derive_contact_email(s.full_name, s.student_id)
    return {
        "full_name": s.full_name,
        "birth_date": s.birth_date,
        "school": s.school,
        "student_id": s.student_id,
        "email": email,
        "study_status": s.study_status,
        "avatar_url": f"/images/avatar/student/{s.id}" if s.avatar_data else None,
    }
