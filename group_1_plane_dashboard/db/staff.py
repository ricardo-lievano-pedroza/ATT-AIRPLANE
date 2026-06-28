"""
Run this script once to pull staff/crew data from DB2 and save local Parquet files.
Usage:
  python -m db.staff           # full fetch, writes Parquet files
  python -m db.staff --test    # fetch first 100 rows of each query, print & exit

Aggregation happens on the DB side — only summary rows are transferred.
"""

import sys
import pandas as pd
import polars as pl
from pathlib import Path
from sqlalchemy import create_engine

DB_URL = "db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE"
SCHEMA = "ATTGRP1"
DATA_DIR = Path(__file__).parent.parent / "data"

# Query 1: Number of staff by department
Q1_STAFF_COUNTS_SQL = f"""
SELECT 
	DEPARTMENT,
	COUNT(DISTINCT EMPNO) AS STAFF_COUNT
FROM {SCHEMA}.STAFF
GROUP BY 
	DEPARTMENT
"""

# Query 2: Staff assignments for distance and time
Q2_STAFF_ASSIGNMENTS_SQL = f"""
SELECT 
	s.FIRSTNME,
	s.LASTNAME,
	fc.EMPNO,
	fc.FLIGHT_ID,
	fc.ROUTE_CODE,
	fc.DEPARTURE,
	s.DEPARTMENT,
	sum(r.distance) as distance,
	sum(r.flight_minutes) as flight_minutes  
FROM {SCHEMA}.FLIGHT_CREW AS fc
LEFT JOIN {SCHEMA}.ROUTES AS r ON fc.ROUTE_CODE = r.ROUTE_CODE
LEFT JOIN {SCHEMA}.STAFF AS s ON fc.EMPNO = s.EMPNO
GROUP BY 
	s.FIRSTNME,
	s.LASTNAME,
	s.DEPARTMENT,
	fc.EMPNO,
	fc.FLIGHT_ID,
	fc.ROUTE_CODE,
	fc.DEPARTURE
"""

# Query 3: Staff usage vs Required by Aircraft and Route
Q3_STAFF_USAGE_SQL = f"""
WITH fc as (
SELECT 	
	fc.FLIGHT_ID,
	fc.ROUTE_CODE,
	fc.DEPARTURE,
	COUNT(DISTINCT fc.EMPNO) as USED_CREW
FROM {SCHEMA}.FLIGHT_CREW AS fc
GROUP BY 
	FLIGHT_ID,
	ROUTE_CODE,
	DEPARTURE
)

SELECT 
	f.FLIGHT_ID,
	f.ROUTE_CODE,
	r.ORIGIN,
	r.DESTINATION,
	f.DEPARTURE,
	f.AIRPLANE,
	a.CREW_MEMBERS AS REQUIRED_CREW,
	a.MODEL AS AIRPLANE_MODEL,
	a.AIRCRAFT_REGISTRATION AS AIRPLANE_REG,
	fc.USED_CREW
FROM {SCHEMA}.FLIGHTS AS f 
LEFT JOIN {SCHEMA}.AIRPLANES AS a ON f.AIRPLANE = a.AIRCRAFT_REGISTRATION
LEFT JOIN fc ON 
	fc.FLIGHT_ID = f.FLIGHT_ID AND
	fc.ROUTE_CODE = f.ROUTE_CODE AND
	fc.DEPARTURE = f.DEPARTURE
LEFT JOIN {SCHEMA}.ROUTES AS r ON f.ROUTE_CODE = r.ROUTE_CODE
"""

def fetch_and_save():
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(DB_URL)

    print("Fetching Q1: Staff counts...")
    with engine.connect() as conn:
        df_q1 = _read_sql(Q1_STAFF_COUNTS_SQL, conn)
    df_q1.write_parquet(DATA_DIR / "q1_staff_counts.parquet")
    print(f"  {len(df_q1):,} rows → data/q1_staff_counts.parquet")

    print("Fetching Q2: Staff assignments...")
    with engine.connect() as conn:
        df_q2 = _read_sql(Q2_STAFF_ASSIGNMENTS_SQL, conn)
    df_q2.write_parquet(DATA_DIR / "q2_staff_assignments.parquet")
    print(f"  {len(df_q2):,} rows → data/q2_staff_assignments.parquet")

    print("Fetching Q3: Staff usage...")
    with engine.connect() as conn:
        df_q3 = _read_sql(Q3_STAFF_USAGE_SQL, conn)
    df_q3.write_parquet(DATA_DIR / "q3_staff_usage.parquet")
    print(f"  {len(df_q3):,} rows → data/q3_staff_usage.parquet")

    print("Done.")

def _read_sql(sql: str, conn) -> pl.DataFrame:
    """Execute SQL and return a Polars DataFrame, normalising column names."""
    try:
        df = pl.read_database(sql, conn)
        df.columns = [c.lower().strip() for c in df.columns]
        return df
    except Exception as exc:
        print(f"Error executing query:\n{sql}\n\n{exc}")
        # Return an empty DataFrame or re-raise
        raw = pd.read_sql(sql, conn)
        raw.columns = [c.lower().strip() for c in raw.columns]
        return pl.from_pandas(raw)

def test_connection(n: int = 100) -> None:
    """Fetch the first `n` rows of each query, print shape + preview, and exit."""
    print(f"Connecting to {DB_URL} …")
    engine = create_engine(DB_URL)

    queries = {
        "Q1_STAFF_COUNTS (first {n} rows)": f"SELECT * FROM ({Q1_STAFF_COUNTS_SQL}) AS t FETCH FIRST {n} ROWS ONLY",
        "Q2_STAFF_ASSIGNMENTS (first {n} rows)": f"SELECT * FROM ({Q2_STAFF_ASSIGNMENTS_SQL}) AS t FETCH FIRST {n} ROWS ONLY",
        "Q3_STAFF_USAGE (first {n} rows)": f"SELECT * FROM ({Q3_STAFF_USAGE_SQL}) AS t FETCH FIRST {n} ROWS ONLY",
    }

    with engine.connect() as conn:
        for label_tpl, sql in queries.items():
            label = label_tpl.format(n=n)
            print(f"\n── {label} ──")
            try:
                df = _read_sql(sql, conn)
                print(f"  shape : {df.shape}")
                print(f"  cols  : {df.columns}")
                print(df.head(5))
            except Exception as exc:
                print(f"  ERROR : {exc}")

    print("\nConnection test complete.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_connection()
    else:
        fetch_and_save()
