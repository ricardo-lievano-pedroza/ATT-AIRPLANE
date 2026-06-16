import streamlit as st
import polars as pl
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path

from analysis import load_data, filter_data, agg_by_continent

DB_URL = "db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE"
SCHEMA = "ATTGRP1"
DATA_DIR = Path(__file__).parent / "data"

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

st.set_page_config(
    page_title="Airport & Tax Impact Dashboard",
    layout="wide",
)


def _fetch_from_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        df = pd.read_sql(TICKETS_AGG_SQL, conn)
    df.columns = [c.lower().strip() for c in df.columns]
    pl.from_pandas(df).write_parquet(DATA_DIR / "tickets_agg.parquet")

    airports_sql = f"SELECT * FROM {SCHEMA}.AIRPORTS"
    with engine.connect() as conn:
        ap = pd.read_sql(airports_sql, conn)
    ap.columns = [c.lower().strip() for c in ap.columns]
    pl.from_pandas(ap).write_parquet(DATA_DIR / "airports.parquet")


@st.cache_data
def get_data() -> pl.DataFrame:
    needed = [
        DATA_DIR / "tickets_agg.parquet",
        DATA_DIR / "airports.parquet",
    ]
    if not all(p.exists() for p in needed):
        with st.spinner("Loading data from database (first run only)..."):
            _fetch_from_db()
    return load_data()


df = get_data()

# ── Sidebar filters ──────────────────────────────────────────────────────────
st.sidebar.title("Filters")

continents = sorted(
    df["origin_continent"].drop_nulls().unique().to_list()
)
selected_continents = st.sidebar.multiselect(
    "Continent", continents, default=continents
)

countries = sorted(
    df.filter(pl.col("origin_continent").is_in(selected_continents))
    ["origin_country"].drop_nulls().unique().to_list()
)
selected_countries = st.sidebar.multiselect(
    "Country", countries, default=countries
)

max_tax = round(float(df["avg_tax_pct"].drop_nulls().max()), 1)
tax_range = st.sidebar.slider(
    "Tax % of ticket price",
    min_value=0.0,
    max_value=max_tax,
    value=(0.0, max_tax),
    step=0.1,
)

filtered = filter_data(
    df, selected_continents, selected_countries, tax_range
)

# ── Page header ──────────────────────────────────────────────────────────────
st.title("Airport & Tax Impact Dashboard")
st.markdown(
    "How do **airport taxes and geography** affect ticket prices and route "
    "economics? This dashboard analyses tax burden across origin airports."
)

# ── KPI row ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total tickets", f"{int(filtered['ticket_count'].sum()):,}")
k2.metric(
    "Avg tax per ticket",
    f"${filtered['avg_total_tax'].mean():.2f}",
)
k3.metric(
    "Avg tax % of price",
    f"{filtered['avg_tax_pct'].mean():.1f}%",
)
k4.metric("Airports in view", str(len(filtered)))

st.divider()

# ── Chart 1: World map ───────────────────────────────────────────────────────
st.subheader("Geographic Tax Distribution")
st.caption(
    "Bubble size = tickets sold · Colour = average tax % of ticket price"
)

map_fig = px.scatter_geo(
    filtered.drop_nulls(subset=["lat", "lon"]).to_pandas(),
    lat="lat",
    lon="lon",
    color="avg_tax_pct",
    size="ticket_count",
    hover_name="origin_airport",
    hover_data={
        "origin_city": True,
        "origin_country": True,
        "avg_tax_pct": ":.1f",
        "avg_total_tax": ":.2f",
        "lat": False,
        "lon": False,
    },
    color_continuous_scale="Reds",
    labels={"avg_tax_pct": "Avg Tax %"},
    projection="natural earth",
)
map_fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
st.plotly_chart(map_fig, width="stretch")

st.divider()

# ── Chart 2 + Chart 3 side by side ──────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Top 15 Airports by Tax Rate")
    top15 = filtered.head(15).to_pandas()
    bar_fig = px.bar(
        top15,
        x="avg_tax_pct",
        y="origin_airport",
        orientation="h",
        color="origin_continent",
        hover_data={
            "origin_country": True,
            "avg_airport_tax": ":.2f",
            "avg_local_tax": ":.2f",
        },
        labels={
            "avg_tax_pct": "Avg Tax % of Ticket",
            "origin_airport": "",
            "origin_continent": "Continent",
        },
    )
    bar_fig.update_layout(
        yaxis={"categoryorder": "total ascending"},
        legend_title_text="Continent",
    )
    st.plotly_chart(bar_fig, width="stretch")

with col_right:
    st.subheader("Tax Burden vs Ticket Price")
    st.caption("Does a higher tax rate mean a higher ticket price?")
    scatter_fig = px.scatter(
        filtered.drop_nulls(subset=["lat", "lon"]).to_pandas(),
        x="avg_ticket_value",
        y="avg_tax_pct",
        size="ticket_count",
        color="origin_continent",
        hover_name="origin_airport",
        labels={
            "avg_ticket_value": "Avg Ticket Price ($)",
            "avg_tax_pct": "Avg Tax % of Ticket",
            "ticket_count": "Tickets Sold",
            "origin_continent": "Continent",
        },
    )
    st.plotly_chart(scatter_fig, width="stretch")

st.divider()

# ── Chart 4: Tax breakdown by continent ─────────────────────────────────────
st.subheader("Tax Breakdown by Continent")
st.caption(
    "How much of the tax burden comes from airport tax vs. local tax?"
)

continent_df = agg_by_continent(filtered)
stacked_fig = px.bar(
    continent_df.to_pandas(),
    x="origin_continent",
    y=["avg_airport_tax", "avg_local_tax"],
    barmode="stack",
    labels={
        "origin_continent": "Continent",
        "value": "Avg Tax ($)",
        "variable": "Tax Type",
    },
    color_discrete_map={
        "avg_airport_tax": "#e07b54",
        "avg_local_tax": "#c0392b",
    },
)
stacked_fig.for_each_trace(
    lambda t: t.update(
        name={
            "avg_airport_tax": "Airport Tax",
            "avg_local_tax": "Local Tax",
        }[t.name]
    )
)
stacked_fig.update_layout(legend_title_text="Tax Type")
st.plotly_chart(stacked_fig, width="stretch")

st.divider()

# ── Summary table ────────────────────────────────────────────────────────────
st.subheader("Airport Tax Summary Table")

display_cols = {
    "origin": "IATA",
    "origin_airport": "Airport",
    "origin_city": "City",
    "origin_country": "Country",
    "origin_continent": "Continent",
    "ticket_count": "Tickets",
    "avg_airport_tax": "Avg Airport Tax ($)",
    "avg_local_tax": "Avg Local Tax ($)",
    "avg_total_tax": "Avg Total Tax ($)",
    "avg_tax_pct": "Tax % of Ticket",
    "avg_ticket_value": "Avg Ticket Value ($)",
}

table_df = (
    filtered
    .select(list(display_cols.keys()))
    .rename(display_cols)
    .to_pandas()
)
st.dataframe(table_df, width="stretch")
st.download_button(
    "Download as CSV",
    data=table_df.to_csv(index=False),
    file_name="airport_tax_summary.csv",
    mime="text/csv",
)

# ── Findings ─────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Key Findings")
st.markdown(
    """
- **Airport tax rates vary significantly by geography.** Some regions show
  tax burdens above 30% of the ticket price, while others stay below 10%.
- **Local tax compounds the burden.** In high-tax markets, local tax adds
  a substantial amount on top of the airport tax.
- **High ticket prices do not always correlate with high tax rates.** Some
  routes carry high taxes relative to a low base fare, signalling price
  sensitivity risk.
- **Tax structure differs by continent.** The stacked bar shows whether the
  burden is driven by airport-level charges or country-level local taxes.
"""
)

st.caption(
    "Data source: ATTGRP1.TICKETS aggregated via SQL JOIN with ROUTES, "
    "enriched with ATTGRP1.AIRPORTS geographic data."
)
