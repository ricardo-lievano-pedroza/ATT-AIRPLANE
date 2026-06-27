"""
Run this script once to pull aggregated data from DB2 and save local Parquet files.
Usage: python db.py

The heavy GROUP BY runs on the database — only summary rows are transferred.
"""

import pandas as pd
import polars as pl
from pathlib import Path
from sqlalchemy import create_engine

DB_URL = "db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE"
SCHEMA = "ATTGRP1"
DATA_DIR = Path(__file__).parent / "data"

# Aggregate 248M ticket rows on the DB side — only one row per origin airport comes back
TICKETS_AGG_SQL = f"""
SELECT
    r.ORIGIN,
    AVG(t.AIRPORT_TAX)  AS avg_airport_tax,
    AVG(t.LOCAL_TAX)    AS avg_local_tax,
    AVG(t.TOTAL_AMOUNT) AS avg_ticket_value,
    SUM(t.TOTAL_AMOUNT) AS total_revenue,
    COUNT(*)            AS ticket_count
FROM {SCHEMA}.TICKETS t
JOIN {SCHEMA}.ROUTES r ON t.ROUTE_CODE = r.ROUTE_CODE
GROUP BY r.ORIGIN
"""

AIRPORTS_SQL = f"SELECT * FROM {SCHEMA}.AIRPORTS"


REVENUE_AGG_SQL = """
    WITH
    revenue_agg AS (
        SELECT
            CAST(t.DEPARTURE AS TIMESTAMP) AS DEPARTURE,
            t.ROUTE_CODE,
            t.CLASS,
            sum(t.TOTAL_AMOUNT) AS REVENUE
        FROM TICKETS t
        GROUP BY t.DEPARTURE,t.ROUTE_CODE,t.CLASS
    ),
    routes_add AS (
        SELECT
            t.DEPARTURE,
            t.ROUTE_CODE,
            r.ORIGIN ,
            r.DESTINATION,
            t.CLASS,
            t.REVENUE
        FROM revenue_agg t
        JOIN ROUTES r ON t.ROUTE_CODE = r.ROUTE_CODE
    ),
    geo_add AS (
        SELECT
            YEAR(r.DEPARTURE) AS year,
            date_trunc('MONTH', r.DEPARTURE ) AS MONTH,
            a.CONTINENT,
            a.COUNTRY,
            a.CITY,
            r.ROUTE_CODE,
            r.ORIGIN,
            r.DESTINATION,
            r.CLASS,
            r.REVENUE
        FROM routes_add r 
        JOIN AIRPORTS a 
        ON A.IATA_CODE = r.ORIGIN
    )
    SELECT * FROM geo_add
    """


def fetch_and_save():
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(DB_URL)

    print("Aggregating tickets by origin airport (this runs on DB2)...")
    with engine.connect() as conn:
        tickets_agg = pd.read_sql(TICKETS_AGG_SQL, conn)
    tickets_agg.columns = [c.lower().strip() for c in tickets_agg.columns]
    pl.from_pandas(tickets_agg).write_parquet(DATA_DIR / "tickets_agg.parquet")
    print(f"  {len(tickets_agg)} origin airports → data/tickets_agg.parquet")

    print("Loading airports table...")
    with engine.connect() as conn:
        airports = pd.read_sql(AIRPORTS_SQL, conn)
    airports.columns = [c.lower().strip() for c in airports.columns]
    pl.from_pandas(airports).write_parquet(DATA_DIR / "airports.parquet")
    print(f"  {len(airports)} airports → data/airports.parquet")

    print("Loading revenue table...")
    with engine.connect() as conn:
        revenue = pd.read_sql(REVENUE_AGG_SQL, conn)
    revenue.columns = [c.lower().strip() for c in revenue.columns]
    pl.from_pandas(revenue).write_parquet(DATA_DIR / "revenue.parquet")
    print(f"  {len(revenue)} records of revenue by year-month and route → data/revenue.parquet")

    print("Done.")


if __name__ == "__main__":
    fetch_and_save()
