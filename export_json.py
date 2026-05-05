# รันสคริปต์นี้ทุกครั้งที่มีการอัปเดต Excel
# จะสร้าง accident_data.json ขึ้นมา
# จากนั้นนำ accident_data.json ไปวางใน Joomla web root
import json
import os
import openpyxl

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "doc", "Accident report python.xlsx")
SHEET_NAME = "Accident 2569"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "accident_data.json")

THAI_MONTHS = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
    5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
    9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
}

wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
ws = wb[SHEET_NAME]

records = []
for row in ws.iter_rows(min_row=2, values_only=True):
    date_val, dept, accident_type, injured, not_injured, description = (
        row[1], row[3], row[6], row[7], row[8], row[5]
    )
    if date_val is None or not hasattr(date_val, "month"):
        continue
    records.append({
        "date": date_val.strftime("%d/%m/%Y"),
        "month": date_val.month,
        "dept": dept or "-",
        "type": accident_type or "-",
        "injured": bool(injured and str(injured).strip() in ("ü", "✓", "x", "X", "1", "true")),
        "not_injured": bool(not_injured and str(not_injured).strip() in ("ü", "✓", "x", "X", "1", "true")),
        "description": description or "",
    })

# Summary
injured_count = sum(1 for r in records if r["injured"])
not_injured_count = sum(1 for r in records if r["not_injured"])

# Monthly
monthly = {}
for r in records:
    m = r["month"]
    if m not in monthly:
        monthly[m] = {"injured": 0, "not_injured": 0}
    if r["injured"]:
        monthly[m]["injured"] += 1
    else:
        monthly[m]["not_injured"] += 1

# Department
dept_map = {}
for r in records:
    d = r["dept"]
    dept_map[d] = dept_map.get(d, 0) + 1

# Type
type_injured = {}
type_not_injured = {}
for r in records:
    t = r["type"]
    if r["injured"]:
        type_injured[t] = type_injured.get(t, 0) + 1
    else:
        type_not_injured[t] = type_not_injured.get(t, 0) + 1

data = {
    "summary": {
        "injured": injured_count,
        "not_injured": not_injured_count,
        "total": len(records),
    },
    "monthly": {
        "labels": [THAI_MONTHS[m] for m in sorted(monthly)],
        "injured": [monthly[m]["injured"] for m in sorted(monthly)],
        "not_injured": [monthly[m]["not_injured"] for m in sorted(monthly)],
    },
    "department": {
        "labels": list(dept_map.keys()),
        "values": list(dept_map.values()),
    },
    "type_injured": {
        "labels": list(type_injured.keys()),
        "values": list(type_injured.values()),
    },
    "type_not_injured": {
        "labels": list(type_not_injured.keys()),
        "values": list(type_not_injured.values()),
    },
    "incidents": records,
}

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✓ สร้างไฟล์สำเร็จ: {OUTPUT_PATH}")
print(f"  รวมทั้งหมด {len(records)} รายการ")
print(f"  มีผู้บาดเจ็บ: {injured_count}, ไม่มี: {not_injured_count}")
print()
print("ขั้นตอนต่อไป: นำ accident_data.json วางใน Joomla web root")
