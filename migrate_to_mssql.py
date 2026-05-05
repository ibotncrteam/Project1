"""
migrate_to_mssql.py
-------------------
อ่านข้อมูลจาก SQLite (instance/accidents.db) แล้ว migrate ไปยัง Microsoft SQL Server

ใช้งาน:
    pip install pyodbc
    python migrate_to_mssql.py

แก้ค่า CONNECTION STRING ในตัวแปร MSSQL_CONN ด้านล่างก่อนรัน
"""

import sqlite3
import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# ตั้งค่า connection string ของ MSSQL (อ่านจาก .env)
# ---------------------------------------------------------------------------
MSSQL_CONN = (
    f"DRIVER={{{os.getenv('MSSQL_DRIVER', 'ODBC Driver 17 for SQL Server')}}};"
    f"SERVER={os.getenv('MSSQL_SERVER')};"
    f"DATABASE={os.getenv('MSSQL_DATABASE')};"
    f"UID={os.getenv('MSSQL_UID')};"
    f"PWD={os.getenv('MSSQL_PWD')};"
)

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "instance", "accidents.db")


# ---------------------------------------------------------------------------
# DDL: สร้าง table ใน MSSQL
# ---------------------------------------------------------------------------
DDL_INCIDENTS = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'incidents')
CREATE TABLE incidents (
    id                INT           IDENTITY(1,1) PRIMARY KEY,
    date              NVARCHAR(20)  NOT NULL,
    time              NVARCHAR(10),
    department        NVARCHAR(200) NOT NULL,
    division          NVARCHAR(200),
    person_name       NVARCHAR(200) NOT NULL,
    position          NVARCHAR(200),
    has_injured       INT           NOT NULL DEFAULT 1,
    accident_type     NVARCHAR(200) NOT NULL,
    location          NVARCHAR(500),
    body_part         NVARCHAR(200),
    description       NVARCHAR(MAX) NOT NULL,
    corrective_action NVARCHAR(MAX),
    score1            INT           NOT NULL DEFAULT 1,
    score2            INT           NOT NULL DEFAULT 1,
    score3            INT           NOT NULL DEFAULT 1,
    score4            INT           NOT NULL DEFAULT 1,
    score5            INT           NOT NULL DEFAULT 1,
    score_total       INT           NOT NULL DEFAULT 5,
    is_major          INT           NOT NULL DEFAULT 0,
    classification    NVARCHAR(50)  NOT NULL DEFAULT 'Non-accident',
    created_by        NVARCHAR(200),
    created_at        NVARCHAR(50)
);
"""


def migrate():
    print("=== SQLite → MSSQL Migration ===\n")

    # เชื่อมต่อ SQLite
    print(f"[1/4] เปิด SQLite: {SQLITE_PATH}")
    sqlite_con = sqlite3.connect(SQLITE_PATH)
    sqlite_con.row_factory = sqlite3.Row

    # เชื่อมต่อ MSSQL
    print("[2/4] เชื่อมต่อ MSSQL...")
    mssql_con = pyodbc.connect(MSSQL_CONN, autocommit=False)
    mssql_cur = mssql_con.cursor()

    # สร้าง tables
    print("[3/4] สร้าง tables (ถ้ายังไม่มี)...")
    mssql_cur.execute(DDL_INCIDENTS)
    mssql_con.commit()

    # migrate incidents
    incidents = sqlite_con.execute("SELECT * FROM incidents").fetchall()
    print(f"      พบ {len(incidents)} records ใน incidents")
    for row in incidents:
        mssql_cur.execute(
            """
            INSERT INTO incidents
                (date, time, department, division, person_name, position,
                 has_injured, accident_type, location, body_part, description,
                 corrective_action, score1, score2, score3, score4, score5,
                 score_total, is_major, classification, created_by, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["date"], row["time"], row["department"], row["division"],
                row["person_name"], row["position"], row["has_injured"],
                row["accident_type"], row["location"], row["body_part"],
                row["description"], row["corrective_action"],
                row["score1"], row["score2"], row["score3"],
                row["score4"], row["score5"], row["score_total"],
                row["is_major"], row["classification"],
                row["created_by"], row["created_at"],
            ),
        )

   

    mssql_con.commit()
    print("\n[4/4] Done! Migration สำเร็จ")

    sqlite_con.close()
    mssql_cur.close()
    mssql_con.close()


if __name__ == "__main__":
    migrate()
