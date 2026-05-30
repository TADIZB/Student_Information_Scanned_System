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


def _student_to_dict(s: Student, scan_id: str | None = None) -> dict:
    return {
        "full_name": s.full_name,
        "birth_date": s.birth_date,
        "school": s.school,
        "student_id": s.student_id,
        "email": s.email,
        "avatar_url": f"/images/avatar/student/{s.id}" if s.avatar_data else None,
    }
