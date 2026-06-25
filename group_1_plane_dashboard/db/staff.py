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

# Each row = one staff member assigned to one flight leg.
# FLIGHT_CREW already carries ROUTE_CODE and DEPARTURE, so FLIGHTS is not needed.
STAFF_FLIGHTS_SQL = f"""
SELECT
    fc.EMPNO,
    s.FIRSTNME,
    s.LASTNAME,
    s.DIVISION,
    s.DEPARTMENT,
    fc.ROUTE_CODE,
    fc.DEPARTURE,
    r.ORIGIN,
    r.DESTINATION,
    r.DISTANCE,
    r.FLIGHT_MINUTES
FROM {SCHEMA}.FLIGHT_CREW  fc
JOIN {SCHEMA}.STAFF         s  ON fc.EMPNO      = s.EMPNO
JOIN {SCHEMA}.ROUTES        r  ON fc.ROUTE_CODE = r.ROUTE_CODE
"""

# Aggregate per route per month: total required crew vs. actual crew assigned.
# The inner subquery aggregates at the flight level first (one row per flight) so that
# CREW_MEMBERS is counted once per flight — not once per crew row as it would be in a
# flat LEFT JOIN. The outer query then sums across flights within each route-month.
CREW_GAPS_SQL = f"""
WITH used_crew AS (
    SELECT
        FLIGHT_ID,
        ROUTE_CODE,
        DEPARTURE,                  -- full datetime — this is the key
        COUNT(*) AS used_crew
    FROM ATTGRP1.FLIGHT_CREW
    GROUP BY FLIGHT_ID, ROUTE_CODE, DEPARTURE
)

SELECT
    f.FLIGHT_ID,
    f.ROUTE_CODE,
    r.ORIGIN,
    r.DESTINATION,
    f.DEPARTURE,                    -- keep full datetime here
    DATE(f.DEPARTURE)               AS departure_date,
    a.CREW_MEMBERS                  AS required_crew,
    COALESCE(uc.used_crew, 0)       AS used_crew
--    a.CREW_MEMBERS - COALESCE(uc.used_crew, 0) AS crew_gap

FROM ATTGRP1.FLIGHTS        f
JOIN ATTGRP1.AIRPLANES      a   ON f.AIRPLANE       = a.AIRCRAFT_REGISTRATION
JOIN ATTGRP1.ROUTES         r   ON f.ROUTE_CODE     = r.ROUTE_CODE
LEFT JOIN used_crew         uc  ON uc.FLIGHT_ID     = f.FLIGHT_ID
                                AND uc.ROUTE_CODE   = f.ROUTE_CODE
                                AND uc.DEPARTURE    = f.DEPARTURE  -- exact match on datetime
"""


def fetch_and_save():
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(DB_URL)

    print("Fetching staff flight assignments...")
    with engine.connect() as conn:
        df_staff = _read_sql(STAFF_FLIGHTS_SQL, conn)
    df_staff.write_parquet(DATA_DIR / "staff_flights.parquet")
    print(f"  {len(df_staff):,} assignment rows → data/staff_flights.parquet")

    print("Fetching crew gap data by route and month...")
    with engine.connect() as conn:
        df_gaps = _read_sql(CREW_GAPS_SQL, conn)
    df_gaps.write_parquet(DATA_DIR / "crew_gaps.parquet")
    print(f"  {len(df_gaps):,} route-month rows → data/crew_gaps.parquet")

    print("Done.")


def _read_sql(sql: str, conn) -> pl.DataFrame:
    """Execute SQL and return a Polars DataFrame, normalising column names."""
    try:
        df = pl.read_database(sql, conn)
        return df.rename({c: c.lower().strip() for c in df.columns})
    except Exception:
        raw = pd.read_sql(sql, conn)
        raw.columns = [c.lower().strip() for c in raw.columns]
        return pl.from_pandas(raw)


def test_connection(n: int = 100) -> None:
    """Fetch the first `n` rows of each query, print shape + preview, and exit."""
    print(f"Connecting to {DB_URL} …")
    engine = create_engine(DB_URL)

    queries = {
        "STAFF_FLIGHTS (first {n} rows)": f"SELECT * FROM ({STAFF_FLIGHTS_SQL}) AS t FETCH FIRST {n} ROWS ONLY",
        "CREW_GAPS (first {n} rows)":     f"SELECT * FROM ({CREW_GAPS_SQL}) AS t FETCH FIRST {n} ROWS ONLY",
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
