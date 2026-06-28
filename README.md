# Group 1 — IE Airplanes Performance Dashboard

A Streamlit dashboard that analyses the behaviour and performance of the IE Airplanes fleet, built on top of a DB2 data warehouse containing routes, airplanes, flights, staff/crew, and ticket-sales data.

## Group Members

- Andrea Alarcon
- Juan José Rincón Briceño
- Ricardo Liévano Pedroza
- Dalton Pearce Kern

---

## 1. Project Objective

The goal of this project is to **analyse the behaviour and performance of the IE Airplanes fleet** by combining information across the airline's core operational entities:

- **Routes** — origin/destination airports, distance, flight duration.
- **Airplanes** — aircraft model, seating configuration, crew requirements.
- **Flights** — scheduled departures/arrivals, frequency by route.
- **Staff/Crew** — crew assignments per flight, utilisation across employees.
- **Tickets** — fares paid, taxes charged, revenue generated per route/class/passenger.

From this data the dashboard answers three business questions:

1. **Tax & pricing** — How do airport taxes and geography affect ticket prices and route economics?
2. **Crew operations** — How is staff utilised across routes, and where do crew shortfalls occur?
3. **Revenue** — How does revenue behave over time, which routes/hubs/classes drive it, and where are passengers flying from and to?

---

## 2. Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Language | **Python 3.12+** | Core language for ETL, analysis, and the app |
| Database | **IBM DB2** | Source of truth — holds the raw operational tables (`AIRPLANES`, `AIRPORTS`, `FLIGHTS`, `ROUTES`, `TICKETS`, `STAFF`, `FLIGHT_CREW`) |
| DB connectivity | **SQLAlchemy** + **ibm_db** / **ibm_db_sa** | Python ↔ DB2 connection and SQL execution via the `db2+ibm_db://` dialect |
| Data processing | **Polars** | All post-extraction analysis: joins, aggregations, filtering, and insight extraction from local Parquet files (chosen for speed on the 248M-row `TICKETS` table) |
| Interchange format | **Apache Parquet** (via `pyarrow`) | Local, columnar cache of pre-aggregated query results so the app does not hit DB2 on every run |
| Dashboard / UI | **Streamlit** | Renders the interactive web dashboard (filters, KPIs, charts, tabs) |
| Visualisation | **Plotly Express** | Choropleth/scatter maps, bar charts, histograms, line trends, pie charts |
| Glue | **pandas** | Intermediate format when reading SQL results before converting to Polars |

---

## 3. Architecture — "Aggregate on DB2, Analyse Locally"

Because the underlying `TICKETS` table has ~248 million rows, the project avoids pulling raw data into Python. Instead it follows a three-step pattern:

**Step 1 — Aggregate on DB2.**
Each ETL script (`db.py`, `db/tickets.py`, `db/staff.py`) opens a SQLAlchemy connection to DB2 and runs a `GROUP BY` / `JOIN` query **on the server side**, so only the already-summarised rows travel over the network. For example, ticket data is aggregated by origin airport (taxes, average ticket value, total revenue, ticket count) instead of transferring all 248M individual rows.

**Step 2 — Cache as Parquet.**
The aggregated results are normalised (lower-cased column names) and written to the local `data/` folder as Parquet files:

| File | Source tables | Contents |
|---|---|---|
| `data/tickets_agg.parquet` | `TICKETS` ⋈ `ROUTES`, grouped by origin | Avg airport/local tax, avg ticket value, total revenue, ticket count per origin airport |
| `data/airports.parquet` | `AIRPORTS` | IATA code, airport name, city, country, continent, lat/lon |
| `data/revenue.parquet` | `TICKETS` ⋈ `ROUTES` ⋈ `AIRPORTS` (origin + destination), grouped by year/month/route/class | Revenue by route, cabin class, origin/destination geography, and month |
| `data/staff_flights.parquet` | `FLIGHT_CREW` ⋈ `STAFF` ⋈ `ROUTES` | One row per crew member assigned to a flight leg (route, distance, flight minutes) |
| `data/crew_gaps.parquet` | `FLIGHTS` ⋈ `AIRPLANES` ⋈ `FLIGHT_CREW`, grouped by route/month | Required vs. actual crew per flight, aggregated into monthly crew shortfalls per route |

Once these files exist, **`app.py` never queries DB2 again** — it checks for the files on startup and only falls back to a live fetch if one is missing.

**Step 3 — Analyse with Polars.**
The `analysis/` package and `revenue_analysis.py` load the Parquet files into Polars LazyFrames and perform all insight extraction in-memory:
- Join tickets with airport geography to compute tax % of ticket price.
- Per-employee utilisation stats and P90/P10 over/under-staffing flags.
- Per-route crew-gap rates and monthly trend.
- Date-range filtering, revenue trend/seasonality, revenue by cabin class, revenue by country.

**Step 4 — Render with Streamlit.**
`app.py` wires loaders and analysis functions to Streamlit widgets (`selectbox`, `multiselect`, `slider`, `date_input`) and Plotly Express charts, organised into three tabs.

---

## 4. Project Structure

```
group_1_plane_dashboard/
├── app.py                    # Main Streamlit app — all three dashboard tabs
├── app_revenue.py            # Standalone earlier version of the Revenue tab only
├── revenue_analysis.py       # Revenue analysis functions used by app.py Tab 3
├── db.py                     # ETL: builds tickets_agg, airports, revenue Parquet files
├── analysis/
│   ├── ticket_revenue.py     # load_data() and filter_data() — Tax/Revenue tab (Tab 1)
│   └── staff.py              # Staff utilisation, route occupation, crew-gap analysis (Tab 2)
├── db/
│   ├── tickets.py            # ETL: rebuilds tickets_agg.parquet and airports.parquet
│   └── staff.py              # ETL: rebuilds staff_flights.parquet and crew_gaps.parquet
└── data/                     # Cached Parquet files (pre-aggregated DB2 query results)
    ├── tickets_agg.parquet
    ├── airports.parquet
    ├── revenue.parquet
    ├── staff_flights.parquet
    ├── crew_gaps.parquet
    └── routes.parquet
```

---

## 5. What the Dashboard Shows

`app.py` renders three tabs:

### Tab 1 — Revenue & Tax
*How do airport taxes and geography affect ticket prices and route economics?*

- **KPI row:** total tickets, average tax per ticket, average tax % of price, airports in view.
- **World map:** average tax % by origin airport, bubble-sized by ticket volume.
- **Top 15 airports** by total tax collected (rate × volume).
- **Scatter plot:** tax burden vs. average ticket price, coloured by continent.
- **Top 15 countries** by average tax rate.
- **Summary table** with CSV export.
- **Filters:** continent, country, tax % range slider.

### Tab 2 — Staff Occupation
*How is crew utilised across routes, and where are crews understaffed?*

The analysis logic is fully implemented in `analysis/staff.py`:
- `staff_utilisation()` — per-employee total flights, hours, unique routes; P90 overuse / P10 underuse flags.
- `occupation_by_route()` — unique staff, total assignments, crew-hours, and averages per route.
- `understaffing_by_route()` — total missing crew slots and gap rate per route (across all months).
- `temporal_understaffing()` — monthly crew-gap trend across all routes.

> **Note:** this tab is currently commented out in `app.py` and does not render. The data files and analysis functions are ready; re-enabling requires uncommenting the `with tab2:` block.

### Tab 3 — Revenue Analysis
*How is revenue behaving over time, where are the main hubs, and what cabin class do passengers buy?*

- **KPI row:** total revenue, most profitable outgoing route, city with the most revenue — all scoped to the selected date range.
- **Revenue trend line** over time (monthly, with seasonality).
- **Donut chart:** revenue share by cabin class (Economy / Premium / Business).
- **Choropleth map:** total revenue by origin country.
- **Filters:** continent, country, city, start/end date.

---

## 6. Environment Setup

This project lives inside the `ATT-AIRPLANE` monorepo. The `pyproject.toml` and `uv.lock` are at the **repository root** (one level above `group_1_plane_dashboard/`).

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — `pip install uv` or see the [official install guide](https://docs.astral.sh/uv/getting-started/installation/).
- Python 3.12 or newer (uv manages this automatically).

### Steps

1. **Move to the repository root** (the folder containing `pyproject.toml`):

   ```bash
   cd ATT-AIRPLANE
   ```

2. **Sync the environment:**

   ```bash
   uv sync
   ```

   To include development extras (Jupyter notebooks):

   ```bash
   uv sync --extra dev
   ```

3. **Activate the virtual environment** (optional — `uv run` activates it per-command):

   ```bash
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1

   # macOS / Linux
   source .venv/bin/activate
   ```

4. **Verify the install:**

   ```bash
   uv run python -c "import streamlit, polars, ibm_db; print('OK')"
   ```

> **Note on `ibm_db`:** this package ships a precompiled IBM DB2 CLI driver. On Windows you may need the [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) installed for the native extension to load.

---

## 7. Running the Dashboard

From the `group_1_plane_dashboard/` folder:

```bash
uv run streamlit run app.py
```

Streamlit will print a local URL (typically `http://localhost:8501`) — open it in your browser.

---

## 8. Connecting to DB2 / Rebuilding the Cache

The DB2 connection is configured in `db.py` (and mirrored in `db/tickets.py`, `db/staff.py`, and `app.py`):

```python
DB_URL = "db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE"
SCHEMA = "ATTGRP1"
```

The `data/` folder ships with pre-built Parquet files, so **you normally do not need to connect to DB2**. If the source tables change and you need to rebuild the cache, run from `group_1_plane_dashboard/`:

```bash
# Rebuilds tickets_agg.parquet, airports.parquet, and revenue.parquet
uv run python db.py

# Rebuilds tickets_agg.parquet and airports.parquet only
uv run python -m db.tickets

# Rebuilds staff_flights.parquet and crew_gaps.parquet
uv run python -m db.staff

# Sanity-check: fetches 100 rows of each staff query and prints them, no files written
uv run python -m db.staff --test
```

---

## 9. Key Findings

- **Tax rates vary significantly by geography** — some airports carry a tax burden above 30% of the ticket price while others stay below 10%, making geography a key factor in route pricing.
- **The highest tax impact is concentrated in a few high-volume airports** — volume amplifies the effect even when the individual rate is not the highest.
- **High ticket prices do not always correlate with high tax rates** — some routes show high taxes on low base fares, signalling price-sensitivity risk.
- **Revenue shows clear seasonality**, increasing in Q2 and Q4.
- **Economy class is the highest revenue driver**, accounting for over 70% of tickets sold.
- **Departures are highly concentrated** in a small number of hubs, primarily in the United States and France.