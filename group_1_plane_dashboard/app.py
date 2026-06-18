import streamlit as st
import polars as pl
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path

from analysis.ticket_revenue import load_data, filter_data
from analysis.staff import (
    load_staff_flights,
    load_crew_gaps,
    staff_utilisation,
    occupation_by_route,
    understaffing_by_route,
    temporal_understaffing,
)
import db.tickets as db_tickets
import db.staff as db_staff

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
    page_title="ATT Group 1 Dashboard",
    layout="wide",
)


# ── Data loaders with DB fallback ─────────────────────────────────────────────

def _fetch_tickets_from_db() -> None:
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
def get_ticket_data() -> pl.DataFrame:
    needed = [DATA_DIR / "tickets_agg.parquet", DATA_DIR / "airports.parquet"]
    if not all(p.exists() for p in needed):
        with st.spinner("Loading ticket data from database (first run only)..."):
            _fetch_tickets_from_db()
    return load_data()


@st.cache_data
def get_staff_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    needed = [DATA_DIR / "staff_flights.parquet", DATA_DIR / "crew_gaps.parquet"]
    if not all(p.exists() for p in needed):
        with st.spinner("Loading staff data from database (first run only)..."):
            db_staff.fetch_and_save()
    return load_staff_flights(), load_crew_gaps()


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["Revenue & Tax", "Staff Occupation"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Revenue & Tax (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    df = get_ticket_data()

    st.sidebar.title("Filters")

    continents = sorted(df["origin_continent"].drop_nulls().unique().to_list())
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

    filtered = filter_data(df, selected_continents, selected_countries, tax_range)

    st.title("Airport & Tax Impact Dashboard")
    st.markdown(
        "How do **airport taxes and geography** affect ticket prices and route "
        "economics? This dashboard analyses tax burden across origin airports."
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total tickets", f"{int(filtered['ticket_count'].sum()):,}")
    k2.metric("Avg tax per ticket", f"${filtered['avg_total_tax'].mean():.2f}")
    k3.metric("Avg tax % of price", f"{filtered['avg_tax_pct'].mean():.1f}%")
    k4.metric("Airports in view", str(len(filtered)))

    st.divider()

    st.subheader("Geographic Tax Distribution")
    st.caption("Bubble size = tickets sold · Colour = average tax % of ticket price")
    map_fig = px.scatter_geo(
        filtered.drop_nulls(subset=["lat", "lon"]).to_pandas(),
        lat="lat", lon="lon",
        color="avg_tax_pct",
        size="ticket_count",
        hover_name="origin_airport",
        hover_data={
            "origin_city": True, "origin_country": True,
            "avg_tax_pct": ":.1f", "avg_total_tax": ":.2f",
            "lat": False, "lon": False,
        },
        color_continuous_scale="Reds",
        labels={"avg_tax_pct": "Avg Tax %"},
        projection="natural earth",
    )
    map_fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(map_fig, width="stretch")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Top 15 Airports by Total Tax Collected")
        st.caption("High rate + high volume = biggest financial impact on passengers.")
        top15 = (
            filtered.lazy()
            .with_columns(
                (pl.col("avg_total_tax") * pl.col("ticket_count")).alias("total_tax_collected"),
            )
            .sort("total_tax_collected", descending=True)
            .head(15)
            .collect()
            .to_pandas()
        )
        bar_fig = px.bar(
            top15, x="total_tax_collected", y="origin_airport", orientation="h",
            color="origin_continent",
            hover_data={"origin_country": True, "avg_tax_pct": ":.1f", "ticket_count": True},
            labels={
                "total_tax_collected": "Total Tax Collected ($)",
                "origin_airport": "", "origin_continent": "Continent",
                "avg_tax_pct": "Avg Tax %", "ticket_count": "Tickets",
            },
        )
        bar_fig.update_layout(yaxis={"categoryorder": "total ascending"}, legend_title_text="Continent")
        st.plotly_chart(bar_fig, width="stretch")

    with col_right:
        st.subheader("Tax Burden vs Ticket Price")
        st.caption("Does a higher tax rate mean a higher ticket price?")
        scatter_fig = px.scatter(
            filtered.drop_nulls(subset=["lat", "lon"]).to_pandas(),
            x="avg_ticket_value", y="avg_tax_pct",
            size="ticket_count", color="origin_continent",
            hover_name="origin_airport",
            labels={
                "avg_ticket_value": "Avg Ticket Price ($)",
                "avg_tax_pct": "Avg Tax % of Ticket",
                "ticket_count": "Tickets Sold", "origin_continent": "Continent",
            },
        )
        st.plotly_chart(scatter_fig, width="stretch")

    st.divider()

    st.subheader("Top 15 Countries by Tax Rate")
    st.caption(
        "Which markets have the highest tax burden? "
        "These are the routes most exposed to price sensitivity."
    )
    top_countries = (
        filtered.lazy()
        .group_by("origin_country", "origin_continent")
        .agg(
            pl.col("avg_tax_pct").mean().alias("avg_tax_pct"),
            pl.col("ticket_count").sum().alias("ticket_count"),
            pl.col("avg_ticket_value").mean().alias("avg_ticket_value"),
        )
        .sort("avg_tax_pct", descending=True)
        .head(15)
        .collect()
    )
    country_fig = px.bar(
        top_countries.to_pandas(),
        x="avg_tax_pct", y="origin_country", orientation="h",
        color="origin_continent",
        hover_data={"ticket_count": True, "avg_ticket_value": ":.2f"},
        labels={
            "avg_tax_pct": "Avg Tax % of Ticket", "origin_country": "",
            "origin_continent": "Continent", "ticket_count": "Tickets",
            "avg_ticket_value": "Avg Ticket ($)",
        },
    )
    country_fig.update_layout(yaxis={"categoryorder": "total ascending"}, legend_title_text="Continent")
    st.plotly_chart(country_fig, width="stretch")

    st.divider()

    st.subheader("Airport Tax Summary Table")
    display_cols = {
        "origin": "IATA", "origin_airport": "Airport", "origin_city": "City",
        "origin_country": "Country", "origin_continent": "Continent",
        "ticket_count": "Tickets", "avg_airport_tax": "Avg Airport Tax ($)",
        "avg_local_tax": "Avg Local Tax ($)", "avg_total_tax": "Avg Total Tax ($)",
        "avg_tax_pct": "Tax % of Ticket", "avg_ticket_value": "Avg Ticket Value ($)",
    }
    table_df = filtered.select(list(display_cols.keys())).rename(display_cols).to_pandas()
    st.dataframe(table_df, width="stretch")
    st.download_button(
        "Download as CSV", data=table_df.to_csv(index=False),
        file_name="airport_tax_summary.csv", mime="text/csv",
    )

    st.divider()
    st.subheader("Key Findings")
    st.markdown(
        """
- **Tax rates vary significantly by geography.** The map shows that some
  airports carry a tax burden above 30% of the ticket price while others
  stay below 10%, making geography a key factor in route pricing.
- **The highest financial impact is concentrated in a few busy airports.**
  The total tax collected chart shows that high-volume airports dominate
  the tax burden even when their rate is not the highest — volume amplifies
  the effect.
- **High ticket prices do not always correlate with high tax rates.** The
  scatter plot reveals airports where taxes are high relative to a low base
  fare, signalling routes with the greatest price sensitivity risk.
- **Specific country markets drive the tax burden.** The top countries chart
  identifies which markets should be prioritised for fare strategy review
  given their consistently high tax rates across airports.
"""
    )
    st.caption(
        "Data source: ATTGRP1.TICKETS aggregated via SQL JOIN with ROUTES, "
        "enriched with ATTGRP1.AIRPORTS geographic data."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Staff Occupation
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    staff_flights_raw, crew_gaps_raw = get_staff_data()

    util_df   = staff_utilisation(staff_flights_raw)
    route_df  = occupation_by_route(staff_flights_raw)
    gaps_df   = understaffing_by_route(crew_gaps_raw)
    trend_df  = temporal_understaffing(crew_gaps_raw)

    p90 = float(util_df["p90_threshold"].first())
    p10 = float(util_df["p10_threshold"].first())

    # ── Sidebar filters (staff tab) ───────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.subheader("Staff filters")

    all_years = sorted(crew_gaps_raw["year"].unique().to_list())
    year_range = st.sidebar.select_slider(
        "Year range", options=all_years, value=(all_years[0], all_years[-1])
    )

    divisions = sorted(staff_flights_raw["division"].drop_nulls().unique().to_list())
    selected_divisions = st.sidebar.multiselect("Division", divisions, default=divisions)

    # Apply filters
    filtered_staff = staff_flights_raw.filter(
        pl.col("division").is_in(selected_divisions)
        & pl.col("departure").dt.year().is_between(year_range[0], year_range[1])
    )
    filtered_gaps = crew_gaps_raw.filter(
        pl.col("year").is_between(year_range[0], year_range[1])
    )

    util_f  = staff_utilisation(filtered_staff)
    route_f = occupation_by_route(filtered_staff)
    gaps_f  = understaffing_by_route(filtered_gaps)
    trend_f = temporal_understaffing(filtered_gaps)

    # ── Header & KPIs ─────────────────────────────────────────────────────────
    st.title("Staff Occupation Analysis")
    st.markdown(
        "Crew utilisation by route, overworked vs. underused staff, "
        "and routes where required crew was not met."
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total staff", f"{util_f['empno'].n_unique():,}")
    k2.metric("Avg flights / staff", f"{util_f['total_flights'].mean():.1f}")
    k3.metric("Avg hours / staff", f"{util_f['total_hours'].mean():.1f} h")
    k4.metric(
        "Routes w/ crew gaps",
        str(len(gaps_f)),
    )

    st.divider()

    # ── Chart 1: Occupation rate by route ─────────────────────────────────────
    st.subheader("Staff Occupation Rate by Route")
    st.caption("Average crew-hours per staff member assigned to each route (top 20).")

    top_routes = route_f.head(20)
    route_fig = px.bar(
        top_routes.to_pandas(),
        x="avg_hours_per_staff",
        y="route_label",
        orientation="h",
        color_discrete_sequence=["#4C78A8"],
        hover_data={
            "unique_staff": True,
            "total_flights": True,
            "total_crew_hours": ":.0f",
            "avg_flights_per_staff": ":.1f",
        },
        labels={
            "avg_hours_per_staff": "Avg Hours per Staff",
            "route_label": "",
            "avg_flights_per_staff": "Avg Flights / Staff",
            "unique_staff": "Unique Staff",
            "total_flights": "Total Flights",
            "total_crew_hours": "Total Crew Hours",
        },
    )
    route_fig.update_layout(
        yaxis={"categoryorder": "total ascending"},
        xaxis={"showgrid": False},
    )
    st.plotly_chart(route_fig, width="stretch")

    st.divider()

    # ── Chart 2: Utilisation distribution ────────────────────────────────────
    st.subheader("Staff Utilisation Distribution")
    st.caption(
        f"Distribution of total flight hours per employee. "
        f"P90 threshold = {p90:.0f} h (overused) · P10 = {p10:.0f} h (underused)."
    )

    hist_fig = px.histogram(
        util_f.to_pandas(),
        x="total_hours",
        nbins=40,
        color_discrete_sequence=["#4C78A8"],
        labels={"total_hours": "Total Flight Hours"},
    )
    hist_fig.add_vline(x=p90, line_dash="dash", line_color="red",
                       annotation_text=f"P90 ({p90:.0f} h)", annotation_position="top right")
    hist_fig.add_vline(x=p10, line_dash="dash", line_color="orange",
                       annotation_text=f"P10 ({p10:.0f} h)", annotation_position="top left")
    st.plotly_chart(hist_fig, width="stretch")

    col_over, col_under = st.columns(2)

    with col_over:
        st.subheader(f"Overworked Staff (≥ P90: {p90:.0f} h)")
        overused = (
            util_f.filter(pl.col("is_overused"))
            .select("firstnme", "lastname", "division", "department",
                    "total_flights", "total_hours", "unique_routes")
            .sort("total_hours", descending=True)
        )
        st.caption(f"{len(overused)} employees above the 90th percentile.")
        st.dataframe(
            overused.rename({
                "firstnme": "First", "lastname": "Last",
                "division": "Division", "department": "Department",
                "total_flights": "Flights", "total_hours": "Hours",
                "unique_routes": "Routes",
            }).to_pandas(),
            width="stretch",
        )

    with col_under:
        st.subheader(f"Underused Staff (≤ P10: {p10:.0f} h)")
        underused = (
            util_f.filter(pl.col("is_underused"))
            .select("firstnme", "lastname", "division", "department",
                    "total_flights", "total_hours", "unique_routes")
            .sort("total_hours")
        )
        st.caption(f"{len(underused)} employees below the 10th percentile.")
        st.dataframe(
            underused.rename({
                "firstnme": "First", "lastname": "Last",
                "division": "Division", "department": "Department",
                "total_flights": "Flights", "total_hours": "Hours",
                "unique_routes": "Routes",
            }).to_pandas(),
            width="stretch",
        )

    st.divider()

    # ── Chart 3: Understaffed routes ──────────────────────────────────────────
    st.subheader("Routes with Crew Shortfalls")
    st.caption(
        "Routes where the number of crew assigned was below the aircraft's required crew. "
        "Gap rate = total missing crew slots / total required crew slots."
    )

    if len(gaps_f) == 0:
        st.info("No crew gaps found for the selected filters.")
    else:
        top_gaps = gaps_f.head(20)
        gap_fig = px.bar(
            top_gaps.to_pandas(),
            x="total_crew_gap",
            y="route_label",
            orientation="h",
            color="gap_rate_pct",
            color_continuous_scale="Reds",
            hover_data={
                "total_flights": True,
                "total_required_crew": True,
                "total_actual_crew": True,
                "months_understaffed": True,
                "gap_rate_pct": ":.1f",
            },
            labels={
                "total_crew_gap": "Total Missing Crew Slots",
                "route_label": "",
                "gap_rate_pct": "Gap Rate (%)",
                "total_flights": "Total Flights",
                "total_required_crew": "Required Crew",
                "total_actual_crew": "Actual Crew",
                "months_understaffed": "Months Understaffed",
            },
        )
        gap_fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(gap_fig, width="stretch")

    st.divider()

    # ── Chart 4: Monthly understaffing trend ──────────────────────────────────
    st.subheader("Monthly Crew Gap Trend")
    st.caption("Total missing crew slots across all routes per month — reveals seasonal peaks.")

    if len(trend_f) == 0:
        st.info("No trend data available for the selected filters.")
    else:
        trend_fig = px.line(
            trend_f.to_pandas(),
            x="period",
            y="total_crew_gap",
            markers=True,
            labels={
                "period": "Month",
                "total_crew_gap": "Total Missing Crew Slots",
            },
        )
        trend_fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(trend_fig, width="stretch")

    st.divider()

    # ── Full utilisation table ────────────────────────────────────────────────
    st.subheader("Full Staff Utilisation Table")
    full_table = (
        util_f
        .select("firstnme", "lastname", "division", "department",
                "total_flights", "total_hours", "unique_routes",
                "is_overused", "is_underused")
        .rename({
            "firstnme": "First", "lastname": "Last",
            "division": "Division", "department": "Department",
            "total_flights": "Flights", "total_hours": "Hours",
            "unique_routes": "Routes",
            "is_overused": "Overused (P90+)", "is_underused": "Underused (P10-)",
        })
        .to_pandas()
    )
    st.dataframe(full_table, width="stretch")
    st.download_button(
        "Download staff utilisation CSV",
        data=full_table.to_csv(index=False),
        file_name="staff_utilisation.csv",
        mime="text/csv",
    )

    st.caption(
        "Data source: ATTGRP1.FLIGHT_CREW joined with ATTGRP1.STAFF and ATTGRP1.ROUTES. "
        "Crew gaps derived from ATTGRP1.FLIGHTS × ATTGRP1.AIRPLANES.CREW_MEMBERS."
    )
