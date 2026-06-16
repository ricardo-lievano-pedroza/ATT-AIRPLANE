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

**Step 1 — Pull data from DB2 (run once):**
```bash
python db.py
```
This saves `data/airports.parquet`, `data/routes.parquet`, and `data/tickets.parquet`.

**Step 2 — Launch the dashboard:**
```bash
streamlit run app.py
```

## Dashboard Sections

| Section | Description |
|---|---|
| KPI row | Total tickets, average tax per ticket, average tax %, airports in view |
| World map | Average tax % by origin airport, bubble-sized by ticket volume |
| Top 15 airports bar chart | Airports with highest average tax rate, coloured by continent |
| Tax vs ticket price scatter | Whether high-tax airports also charge higher base fares |
| Tax breakdown by continent | Airport tax vs local tax stacked by continent |
| Summary table + CSV export | Full airport-level metrics |

## Key Findings

1. Tax rates vary widely by geography — some airports exceed 30% tax burden relative to the ticket price.
2. Local tax compounds airport tax in certain markets, raising total cost significantly.
3. High ticket prices do not always accompany high tax rates — some routes have high taxes on low-cost fares.
4. The continent breakdown shows whether tax burden is driven by airport-level or government-level charges.

## Limitations & Assumptions

- Analysis uses the **origin airport** of each ticket's route leg as the tax reference point.
- Some airports have null values in `AIRPORT_TAX` (e.g., BLQ) — these are excluded from airport-level aggregations but retained in continent/country totals where ticket-level tax data is available.
- Taxes in the `TICKETS` table (`AIRPORT_TAX`, `LOCAL_TAX`) reflect the tax charged per ticket and may differ from the reference rate in the `AIRPORTS` table.
