"""
load_to_sql.py
---------------
Loads data/raw/vehicle_service_data.csv into a SQLite database
(data/processed/vehicle_reliability.db) using sql/schema.sql.

Run:
    python scripts/load_to_sql.py
"""

import sqlite3
import pandas as pd
from pathlib import Path

CSV_PATH = Path("data/raw/vehicle_service_data.csv")
DB_PATH = Path("data/processed/vehicle_reliability.db")
SCHEMA_PATH = Path("sql/schema.sql")

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Apply schema
with open(SCHEMA_PATH, "r") as f:
    cur.executescript(f.read())

# Load CSV and insert
df = pd.read_csv(CSV_PATH, parse_dates=["service_date"])
df["service_date"] = df["service_date"].dt.strftime("%Y-%m-%d")

df.to_sql("vehicle_service_records", conn, if_exists="append", index=False)
conn.commit()

count = cur.execute("SELECT COUNT(*) FROM vehicle_service_records").fetchone()[0]
print(f"Loaded {count} rows into {DB_PATH}")

conn.close()
