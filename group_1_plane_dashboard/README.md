# Group 1 — Airport & Tax Impact Dashboard

## Group Members
- Andrea Alarcon
- Juan José Rincón Briceño
- Ricardo Liévano Pedroza
- Dalton Pearce Kern

## Database Schema
`ATTGRP1` on DB2 host `52.211.123.34:25010`, database `ATTPLANE`.

## Business Question
**How do airport taxes and geography affect ticket prices and route economics?**

## Setup

```bash
pip install -r requirements.txt
```

## How to Run

The `data/` folder contains pre-built Parquet files — no database connection needed.

**Launch the dashboard:**
```bash
streamlit run app.py
```

## Dashboard Sections

| Section | Description |
|---|---|
| KPI row | Total tickets, average tax per ticket, average tax %, airports in view |
| World map | Average tax % by origin airport, bubble-sized by ticket volume |
| Top 15 airports by total tax collected | Airports where high rate × high volume creates the greatest tax burden |
| Tax burden vs ticket price scatter | Whether high-tax airports also charge higher base fares |
| Top 15 countries by tax rate | Which markets consistently have the highest tax burden |
| Summary table + CSV export | Full airport-level metrics |

## Key Findings

1. Tax rates vary significantly by geography — some airports carry a burden above 30% of the ticket price while others stay below 10%.
2. The highest financial impact is concentrated in a few busy airports — volume amplifies the effect even when the rate is not the highest.
3. High ticket prices do not always correlate with high tax rates — some routes have high taxes on low base fares, signalling price sensitivity risk.
4. Specific country markets drive the overall tax burden and should be prioritised for fare strategy review.

## Limitations & Assumptions

- Analysis uses the **origin airport** of each ticket's route leg as the tax reference point.
- Some airports have null values in `AIRPORT_TAX` (e.g., BLQ) — these are excluded from airport-level aggregations but retained in continent/country totals where ticket-level tax data is available.
- Taxes in the `TICKETS` table (`AIRPORT_TAX`, `LOCAL_TAX`) reflect the tax charged per ticket and may differ from the reference rate in the `AIRPORTS` table.
