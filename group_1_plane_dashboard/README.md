# Group 1 — IE Airplanes Performance Dashboard

A Streamlit dashboard that analyses the behaviour and performance of the IE Airplanes fleet, built on top of a DB2 data warehouse containing routes, airplanes, flights, staff/crew and ticket-sales data.

## Group Members
- Andrea Alarcon
- Juan José Rincón Briceño
- Ricardo Liévano Pedroza
- Dalton Pearce Kern

## Live Dashboard
🔗 **Deployed app:** _<!-- TODO: add the deployed Streamlit dashboard URL here -->_

---

## 1. Project Objective

The goal of this project is to **analyse the behaviour and performance of the IE Airplanes fleet** by combining information across the airline's core operational entities:

- **Routes** — origin/destination airports, distance, flight duration.
- **Airplanes** — aircraft model, seating configuration, crew requirements, maintenance history.
- **Flights** — scheduled departures/arrivals, fares per cabin class, frequency.
- **Staff/Crew** — crew assignments per flight, utilisation across employees.
- **Tickets** — fares paid, taxes charged, revenue generated per route/class/passenger.

From this data the dashboard answers three business questions:

1. **Tax & pricing** — How do airport taxes and geography affect ticket prices and route economics?
2. **Crew operations** — How is staff utilised across routes, and where do crew shortfalls (understaffed flights) occur?
3. **Revenue** — How does revenue behave over time, which routes/hubs/classes drive it, and where are passengers flying from and to?

---

## 2. Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Language | **Python 3.12+** | Core language for ETL, analysis and the app |
| Database | **IBM DB2** | Source of truth — holds the raw operational tables (`AIRPLANES`, `AIRPORTS`, `FLIGHTS`, `ROUTES`, `TICKETS`, `STAFF`, `FLIGHT_CREW`) |
| DB connectivity | **SQLAlchemy** + **ibm_db** / **ibm_db_sa** | Python ↔ DB2 connection and SQL execution via the `db2+ibm_db://` dialect |
| Data processing & analysis | **Polars** | All post-extraction analysis: joins, aggregations, filtering and insight extraction from the local Parquet tables (chosen over pandas for speed on the larger tables, e.g. the 248M-row `TICKETS` table) |
| Interchange format | **Apache Parquet** (via `pyarrow`) | Local, columnar cache of pre-aggregated query results so the app does not hit DB2 on every run |
| Dashboard / UI | **Streamlit** | Renders the interactive web dashboard (filters, KPIs, tables, tabs) |
| Visualisation | **Plotly Express** | Charts: choropleth/scatter maps, bar charts, histograms, line trends, pie charts |
| Glue | **pandas** | Used only as an intermediate format when reading SQL results before converting to Polars (`pl.from_pandas`) |
| Packaging / environment | **uv** + **pyproject.toml** | Dependency management and virtual environment creation |

---

## 3. How the Dashboard Was Built

The project follows a **"aggregate in the database, analyse locally"** pattern, because the underlying `TICKETS` table alone has ~248 million rows — far too large to pull row-by-row into Python.

**Step 1 — Aggregate on DB2.**
Each ETL script (`db.py`, `db/tickets.py`, `db/staff.py`) opens a SQLAlchemy connection to DB2 and runs a `GROUP BY` / `JOIN` query **on the server side**, so only the already-summarised rows travel over the network. For example, ticket data is aggregated by origin airport (taxes, average ticket value, revenue, ticket count) instead of transferring all 248M individual ticket rows.

**Step 2 — Cache as Parquet.**
The aggregated result sets are loaded into a Polars/pandas DataFrame, normalised (lower-cased column names) and written to the local `data/` folder as Parquet files:

| File | Built from | Contents |
|---|---|---|
| `data/tickets_agg.parquet` | `TICKETS` ⋈ `ROUTES`, grouped by origin | Avg airport/local tax, avg ticket value, total revenue, ticket count per origin airport |
| `data/airports.parquet` | `AIRPORTS` | IATA code, airport name, city, country, continent, lat/lon, airport tax |
| `data/revenue.parquet` | `TICKETS` ⋈ `ROUTES` ⋈ `AIRPORTS` (origin + destination), grouped by year/month/route/class | Revenue by route, cabin class, origin/destination geography, and month |
| `data/staff_flights.parquet` | `FLIGHT_CREW` ⋈ `STAFF` ⋈ `ROUTES` | One row per crew member assigned to a flight leg (route, distance, flight minutes) |
| `data/crew_gaps.parquet` | `FLIGHTS` ⋈ `AIRPLANES` ⋈ `FLIGHT_CREW`, grouped by route/month | Required vs. actual crew per flight, aggregated into monthly crew shortfalls per route |

Once these Parquet files exist, the app **never needs to query DB2 again** — `app.py` checks if the files are present and only falls back to a live DB2 fetch on first run (or if a file is missing), showing a `st.spinner` while it rebuilds the cache.

**Step 3 — Analyse with Polars.**
The `analysis/` package (`ticket_revenue.py`, `staff.py`) and the top-level `revenue_analysis.py` module load the Parquet files into **Polars LazyFrames** and perform all further insight extraction in-memory:
- joining tickets with airport geography to compute tax % of ticket price,
- per-employee utilisation stats and P90/P10 over/under-staffing flags,
- per-route crew-gap rates,
- date-range filtering, revenue trend/seasonality, revenue by cabin class, and revenue by country.

**Step 4 — Render with Streamlit.**
`app.py` wires the loaders and analysis functions to Streamlit widgets (`selectbox`, `multiselect`, `slider`, `date_input`) and Plotly Express charts, organised into tabs.

---

## 4. Environment Setup (uv + pyproject.toml)

This project lives inside the monorepo `ATT-AIRPLANE`, and the **`pyproject.toml` and `uv.lock` are at the repository root** (one level above `group_1_plane_dashboard/`) — there is a single shared environment for the whole repo.

### Prerequisites
- [uv](https://docs.astral.sh/uv/) installed (`pip install uv`, or follow the [official install guide](https://docs.astral.sh/uv/getting-started/installation/)).
- Python 3.12 or newer (uv will download/manage this for you if it's not already installed).

### Steps

1. **Clone the repository and move to the project root** (the folder that contains `pyproject.toml`, not `group_1_plane_dashboard/`):

   ```bash
   cd ATT-AIRPLANE
   ```

2. **Sync the environment.** This reads `pyproject.toml` + `uv.lock` and creates a `.venv/` with every dependency pinned to the locked versions (Streamlit, Polars, pandas, SQLAlchemy, ibm_db, ibm_db_sa, plotly, pyarrow, numpy, scikit-learn, python-dotenv):

   ```bash
   uv sync
   ```

   To also install the development extras (Jupyter/notebook, used for exploratory analysis in `notebooks/`):

   ```bash
   uv sync --extra dev
   ```

3. **Activate the virtual environment** (optional — `uv run` activates it automatically per-command):

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

> **Note on `ibm_db`:** this package ships a precompiled IBM DB2 CLI driver. On Windows you may need the [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) installed for the native extension to load. If `uv sync` succeeds but `import ibm_db` fails at runtime, install the redistributable and retry.

---

## 5. Connecting to the DB2 Instance

The DB2 connection details are defined directly in `db.py` (and mirrored in `db/tickets.py`, `db/staff.py`, and `app.py`):

```python
DB_URL = "db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE"
SCHEMA = "ATTGRP1"
```

This breaks down as:

| Part | Value | Meaning |
|---|---|---|
| Dialect/driver | `db2+ibm_db` | Tells SQLAlchemy to use the `ibm_db_sa` dialect with the `ibm_db` driver |
| User | `********` | DB2 login |
| Password | `**********` | DB2 login |
| Host | `52.211.123.34` | DB2 server address |
| Port | `25010` | DB2 instance port |
| Database | `ATTPLANE` | Target database |
| Schema | `ATTGRP1` | Schema containing all project tables (`AIRPLANES`, `AIRPORTS`, `FLIGHTS`, `ROUTES`, `TICKETS`, `STAFF`, `FLIGHT_CREW`) |

A connection is opened with SQLAlchemy's `create_engine`:

```python
from sqlalchemy import create_engine
engine = create_engine(DB_URL)
with engine.connect() as conn:
    df = pd.read_sql(SOME_SQL, conn)
```

### Running the ETL scripts directly

You generally **do not need to connect to DB2 yourself** — the `data/` folder already ships with pre-built Parquet files, and `app.py` only reaches out to DB2 the first time a required file is missing. If you need to rebuild the cache manually (e.g. the source tables changed), run, from `group_1_plane_dashboard/`:

```bash
uv run python db.py            # rebuilds tickets_agg.parquet, airports.parquet, revenue.parquet
uv run python -m db.tickets    # rebuilds tickets_agg.parquet, airports.parquet
uv run python -m db.staff      # rebuilds staff_flights.parquet, crew_gaps.parquet
uv run python -m db.staff --test   # sanity-check the connection: fetches 100 rows of each query and prints them, without writing files
```

> The credentials above point to a shared training/demo DB2 instance for this course assignment. If the instance is rotated or you are pointed at a different DB2 host, update `DB_URL` in `db.py`, `db/tickets.py`, `db/staff.py` and `app.py`.

---

## 6. Running the Dashboard

From the `group_1_plane_dashboard/` folder, with the environment synced:

```bash
uv run streamlit run app.py
```

Streamlit will print a local URL (typically `http://localhost:8501`) — open it in your browser.

---

## 7. What the Dashboard Shows

`app.py` renders three tabs:

### Tab 1 — Revenue & Tax
*How do airport taxes and geography affect ticket prices and route economics?*
- KPI row: total tickets, average tax per ticket, average tax % of price, airports in view.
- World map: average tax % by origin airport, bubble-sized by ticket volume.
- Top 15 airports by total tax collected (rate × volume).
- Scatter plot: tax burden vs. average ticket price.
- Top 15 countries by average tax rate.
- Full airport-level summary table with CSV export.
- Filters: continent, country, tax % range.

### Tab 2 — Staff Occupation
*How is crew utilised across routes, and where are crews understaffed?*
This tab's analysis logic is implemented in `analysis/staff.py` (utilisation per employee with P90/P10 over/under-use flags, occupation per route, crew-gap rate per route, and monthly crew-gap trend) but is **currently commented out in `app.py`** pending further work — the data (`staff_flights.parquet`, `crew_gaps.parquet`) and analysis functions are ready to be re-enabled.

### Tab 3 — Revenue Analysis
*How is revenue behaving over time, where are the main hubs, and what cabin class do passengers buy?*
- KPI row: total revenue, most profitable outgoing route, location with the most revenue, all for the selected date range.
- Revenue trend line over time (seasonality).
- Pie chart: revenue share by cabin class (Economy / Premium / Business).
- Choropleth map: revenue by destination country.
- Filters: continent, country, city, start/end date.

---

## 8. Project Structure

```
group_1_plane_dashboard/
├── app.py                   # Main Streamlit app (all 3 tabs)
├── app_revenue.py           # Standalone earlier version of the Revenue tab
├── analysis.py               # Legacy ticket/tax analysis helpers
├── revenue_analysis.py       # Revenue analysis functions (Polars) used by app.py tab 3
├── db.py                     # ETL: tickets_agg, airports, revenue → data/*.parquet
├── analysis/
│   ├── ticket_revenue.py     # Tax/revenue loading + filtering (tab 1)
│   └── staff.py              # Staff utilisation, occupation, crew-gap analysis (tab 2)
├── db/
│   ├── tickets.py            # ETL: tickets_agg, airports → data/*.parquet
│   └── staff.py              # ETL: staff_flights, crew_gaps → data/*.parquet
└── data/                      # Cached Parquet files (pre-aggregated DB2 query results)
```

---

## 9. Key Findings

- Tax rates vary significantly by geography — some airports carry a burden above 30% of the ticket price while others stay below 10%.
- The highest financial tax impact is concentrated in a few high-volume airports — volume amplifies the effect even when the rate is not the highest.
- High ticket prices do not always correlate with high tax rates — some routes show high taxes on low base fares, signalling price-sensitivity risk.
- Revenue shows clear seasonality, increasing in Q2 and Q4.
- Economy class drives the majority of revenue (over 70% of tickets sold).
- Departures are highly concentrated in a small number of hubs, mainly in the United States and France.
