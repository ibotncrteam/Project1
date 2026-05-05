"""
import_excel.py
--------------
นำเข้าข้อมูลจาก Excel → SQLite DB

ใช้งาน:
    python import_excel.py [--clear]

    --clear  ลบข้อมูลเดิมทั้งหมดใน DB ก่อน import
             (ถ้าไม่ระบุ จะ skip แถวที่ซ้ำวันที่+ชื่อ)
"""

import os
import sqlite3
import sys
import argparse
from datetime import datetime
import openpyxl

# ---------------------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "doc", "Accident report python.xlsx")
SHEET_NAME = "Accident 2569"
DB_PATH    = os.path.join(BASE_DIR, "instance", "accidents.db")

# คอลัมน์ใน Excel (0-based index, row[0] = column A)
# A=0 (hidden/no), B=1=date, C=2=name, D=3=dept, E=4=division
# F=5=description, G=6=accident_type, H=7=injured, I=8=not_injured
# J=9=score1, K=10=score2, L=11=score3, M=12=score4, N=13=score5
COL_DATE         = 1   # B — ว/ด/ป
COL_NAME         = 2   # C — ชื่อ - สกุล
COL_DEPT         = 3   # D — แผนก
COL_DIVISION     = 4   # E — ฝ่าย
COL_DESCRIPTION  = 5   # F — ลักษณะการเกิดเหตุ
COL_ACC_TYPE     = 6   # G — ประเภทอุบัติเหตุ
COL_INJURED      = 7   # H — มีผู้ได้รับบาดเจ็บ
COL_NOT_INJURED  = 8   # I — ไม่มีผู้ได้รับบาดเจ็บ
COL_SCORE1       = 9   # J — 1. เครื่องจักร/อุปกรณ์
COL_SCORE2       = 10  # K — 2. การประเมิน
COL_SCORE3       = 11  # L — 3. ความบาดเจ็บ
COL_SCORE4       = 12  # M — 4. ส่วนของร่างกาย
COL_SCORE5       = 13  # N — 5. ลักษณะการเกิดซ้ำ
# ---------------------------------------------------------------------------

CHECKMARKS = {"ü", "✓", "x", "X", "1", "true", "yes", "✔", "/"}


def is_checked(val) -> bool:
    return bool(val and str(val).strip().lower() in CHECKMARKS)


def classify(score_total: int, is_major: bool) -> str:
    if is_major:
        return "Major"
    if score_total >= 18:
        return "Minor"
    return "Non-accident"


def import_excel(clear: bool = False):
    if not os.path.exists(EXCEL_PATH):
        print(f"[ERROR] ไม่พบไฟล์ Excel: {EXCEL_PATH}")
        sys.exit(1)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # ต้อง init DB ก่อน (สร้าง table ถ้ายังไม่มี)
    from app import init_db
    init_db()

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    if clear:
        db.execute("DELETE FROM incidents")
        db.commit()
        print("[INFO] ลบข้อมูลเดิมทั้งหมดแล้ว")

    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb[SHEET_NAME]

    inserted = skipped = errors = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        # ดึงค่าแต่ละ cell
        try:
            date_val  = row[COL_DATE]
            name      = str(row[COL_NAME] or "").strip() or "ไม่ระบุ"
            dept      = str(row[COL_DEPT] or "").strip() or "-"
            division  = str(row[COL_DIVISION] or "").strip() or ""
            desc      = str(row[COL_DESCRIPTION] or "").strip()
            acc_type  = str(row[COL_ACC_TYPE] or "").strip() or "-"
            injured     = is_checked(row[COL_INJURED])
            not_injured = is_checked(row[COL_NOT_INJURED])

            def _score(col):
                v = row[col] if col < len(row) else None
                try:
                    return max(1, min(9, int(v or 1)))
                except (ValueError, TypeError):
                    return 1

            s1 = _score(COL_SCORE1)
            s2 = _score(COL_SCORE2)
            s3 = _score(COL_SCORE3)
            s4 = _score(COL_SCORE4)
            s5 = _score(COL_SCORE5)
        except (IndexError, TypeError):
            errors += 1
            continue

        # ข้ามแถวว่าง
        if date_val is None or not hasattr(date_val, "month"):
            continue

        date_str = date_val.strftime("%Y-%m-%d")
        total    = s1 + s2 + s3 + s4 + s5
        is_major = 0
        cls      = classify(total, bool(is_major))

        # Skip duplicate (same date + dept + person placeholder)
        if not clear:
            dup = db.execute(
                "SELECT id FROM incidents WHERE date=? AND department=? AND person_name=?",
                (date_str, dept, name)
            ).fetchone()
            if dup:
                skipped += 1
                continue

        has_injured_val = 1 if injured else (0 if not_injured else 1)

        db.execute(
            """INSERT INTO incidents
               (date, time, department, division, person_name, position,
                has_injured, accident_type, body_part, description, corrective_action,
                score1, score2, score3, score4, score5, score_total,
                is_major, classification, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                date_str,
                None,       # time
                dept,
                division,
                name,
                None,       # position
                has_injured_val,
                acc_type,
                None,       # body_part
                desc or "-",
                None,       # corrective_action
                s1, s2, s3, s4, s5, total,
                is_major, cls,
                "excel_import",
                now_str,
            )
        )
        inserted += 1

    db.commit()
    db.close()

    print(f"\n[DONE] นำเข้าเสร็จสิ้น")
    print(f"  ✓ เพิ่มใหม่  : {inserted} รายการ")
    print(f"  - ข้าม (ซ้ำ) : {skipped} รายการ")
    if errors:
        print(f"  ! error      : {errors} รายการ")
    print(f"\n  หมายเหตุ: score และ person_name เป็นค่าเริ่มต้น")
    print(f"  กรุณาเข้า /admin เพื่อแก้ไขรายละเอียดให้ครบถ้วน")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Excel → SQLite")
    parser.add_argument("--clear", action="store_true",
                        help="ลบข้อมูลใน DB ก่อน import ใหม่ทั้งหมด")
    args = parser.parse_args()
    import_excel(clear=args.clear)
