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

from revenue_analysis import (
    load_revenue_data,
    most_profitable_outgoing_route,
    most_revenue_perceived,
    revenue_class_analysis,
    revenue_per_country,
    revenue_trend_analysis,
    total_revenue_per_range,
)

import db.tickets as db_tickets
import db.staff as db_staff

DB_URL = "db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE"
SCHEMA = "ATTGRP1"
DATA_DIR = Path(__file__).parent / "data"

ALL_OPTION = "All"

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
st.title("IE AIRPLANES ✈️")

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


@st.cache_data(show_spinner="Loading capacity data...", ttl=3600)
def get_capacity_data() -> pl.DataFrame:
    """Load capacity data from parquet file"""
    try:
        capacity_file = DATA_DIR / "capacity.parquet"
        if not capacity_file.exists():
            st.error(f"Capacity file not found at {capacity_file}")
            return pl.DataFrame()
        
        df = pl.read_parquet(capacity_file)
        return df
    except Exception as e:
        st.error(f"Error loading capacity data: {str(e)}")
        st.write("Debug info - trying to read from alternate location...")
        return pl.DataFrame()


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["Revenue & Tax", "Staff Occupation", "Revenue Anlaysis", "Plane Capacity"])


def multiselect_with_all(container, label: str, options: list[str]) -> list[str]:
    """Multiselect dropdown with every option selected by default. Leaving the
    selection empty is treated as selecting every option."""
    selected = container.multiselect(label, options, default=options)
    return selected or options


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Revenue & Tax (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    df = get_ticket_data()

    st.title("Airport & Tax Impact Dashboard")
    st.markdown(
        "How do **airport taxes and geography** affect ticket prices and route "
        "economics? This dashboard analyses tax burden across origin airports."
    )

    filter_container = st.container()
    with filter_container:
        st.subheader("Filters")
        filter_cols = st.columns(3)

        continents = sorted(df["origin_continent"].drop_nulls().unique().to_list())
        selected_continents = multiselect_with_all(filter_cols[0], "Continent", continents)

        countries = sorted(
            df.filter(pl.col("origin_continent").is_in(selected_continents))
            ["origin_country"].drop_nulls().unique().to_list()
        )
        selected_countries = multiselect_with_all(filter_cols[1], "Country", countries)

        max_tax = round(float(df["avg_tax_pct"].drop_nulls().max()), 1)
        tax_range = filter_cols[2].slider(
            "Tax % of ticket price",
            min_value=0.0,
            max_value=max_tax,
            value=(0.0, max_tax),
            step=0.1,
        )

    filtered = filter_data(df, selected_continents, selected_countries, tax_range)

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

# with tab2:
#     staff_flights_raw, crew_gaps_raw = get_staff_data()

#     util_df   = staff_utilisation(staff_flights_raw)
#     route_df  = occupation_by_route(staff_flights_raw)
#     gaps_df   = understaffing_by_route(crew_gaps_raw)
#     trend_df  = temporal_understaffing(crew_gaps_raw)

#     p90 = float(util_df["p90_threshold"].first())
#     p10 = float(util_df["p10_threshold"].first())

#     # ── Sidebar filters (staff tab) ───────────────────────────────────────────
#     st.sidebar.markdown("---")
#     st.sidebar.subheader("Staff filters")

#     all_years = sorted(crew_gaps_raw["year"].unique().to_list())

#     year_range = st.sidebar.select_slider(
#         "Year range", options=all_years, value=(all_years[0], all_years[-1])
#     )

#     divisions = sorted(staff_flights_raw["division"].drop_nulls().unique().to_list())
#     selected_divisions = st.sidebar.multiselect("Division", divisions, default=divisions)

#     # Apply filters
#     filtered_staff = staff_flights_raw.filter(
#         pl.col("division").is_in(selected_divisions)
#         & pl.col("departure").dt.year().is_between(year_range[0], year_range[1])
#     )
#     filtered_gaps = crew_gaps_raw.filter(
#         pl.col("year").is_between(year_range[0], year_range[1])
#     )

#     util_f  = staff_utilisation(filtered_staff)
#     route_f = occupation_by_route(filtered_staff)
#     gaps_f  = understaffing_by_route(filtered_gaps)
#     trend_f = temporal_understaffing(filtered_gaps)

#     # ── Header & KPIs ─────────────────────────────────────────────────────────
#     st.title("Staff Occupation Analysis")
#     st.markdown(
#         "Crew utilisation by route, overworked vs. underused staff, "
#         "and routes where required crew was not met."
#     )

#     k1, k2, k3, k4 = st.columns(4)
#     k1.metric("Total staff", f"{util_f['empno'].n_unique():,}")
#     k2.metric("Avg flights / staff", f"{util_f['total_flights'].mean():.1f}")
#     k3.metric("Avg hours / staff", f"{util_f['total_hours'].mean():.1f} h")
#     k4.metric(
#         "Routes w/ crew gaps",
#         str(len(gaps_f)),
#     )

#     st.divider()

#     # ── Chart 1: Occupation rate by route ─────────────────────────────────────
#     st.subheader("Staff Occupation Rate by Route")
#     st.caption("Average crew-hours per staff member assigned to each route (top 20).")

#     top_routes = route_f.head(20)
#     route_fig = px.bar(
#         top_routes.to_pandas(),
#         x="avg_hours_per_staff",
#         y="route_label",
#         orientation="h",
#         color_discrete_sequence=["#4C78A8"],
#         hover_data={
#             "unique_staff": True,
#             "total_flights": True,
#             "total_crew_hours": ":.0f",
#             "avg_flights_per_staff": ":.1f",
#         },
#         labels={
#             "avg_hours_per_staff": "Avg Hours per Staff",
#             "route_label": "",
#             "avg_flights_per_staff": "Avg Flights / Staff",
#             "unique_staff": "Unique Staff",
#             "total_flights": "Total Flights",
#             "total_crew_hours": "Total Crew Hours",
#         },
#     )
#     route_fig.update_layout(
#         yaxis={"categoryorder": "total ascending"},
#         xaxis={"showgrid": False},
#     )
#     st.plotly_chart(route_fig, width="stretch")

#     st.divider()

#     # ── Chart 2: Utilisation distribution ────────────────────────────────────
#     st.subheader("Staff Utilisation Distribution")
#     st.caption(
#         f"Distribution of total flight hours per employee. "
#         f"P90 threshold = {p90:.0f} h (overused) · P10 = {p10:.0f} h (underused)."
#     )

#     hist_fig = px.histogram(
#         util_f.to_pandas(),
#         x="total_hours",
#         nbins=40,
#         color_discrete_sequence=["#4C78A8"],
#         labels={"total_hours": "Total Flight Hours"},
#     )
#     hist_fig.add_vline(x=p90, line_dash="dash", line_color="red",
#                        annotation_text=f"P90 ({p90:.0f} h)", annotation_position="top right")
#     hist_fig.add_vline(x=p10, line_dash="dash", line_color="orange",
#                        annotation_text=f"P10 ({p10:.0f} h)", annotation_position="top left")
#     st.plotly_chart(hist_fig, width="stretch")

#     col_over, col_under = st.columns(2)

#     with col_over:
#         st.subheader(f"Overworked Staff (≥ P90: {p90:.0f} h)")
#         overused = (
#             util_f.filter(pl.col("is_overused"))
#             .select("firstnme", "lastname", "division", "department",
#                     "total_flights", "total_hours", "unique_routes")
#             .sort("total_hours", descending=True)
#         )
#         st.caption(f"{len(overused)} employees above the 90th percentile.")
#         st.dataframe(
#             overused.rename({
#                 "firstnme": "First", "lastname": "Last",
#                 "division": "Division", "department": "Department",
#                 "total_flights": "Flights", "total_hours": "Hours",
#                 "unique_routes": "Routes",
#             }).to_pandas(),
#             width="stretch",
#         )

#     with col_under:
#         st.subheader(f"Underused Staff (≤ P10: {p10:.0f} h)")
#         underused = (
#             util_f.filter(pl.col("is_underused"))
#             .select("firstnme", "lastname", "division", "department",
#                     "total_flights", "total_hours", "unique_routes")
#             .sort("total_hours")
#         )
#         st.caption(f"{len(underused)} employees below the 10th percentile.")
#         st.dataframe(
#             underused.rename({
#                 "firstnme": "First", "lastname": "Last",
#                 "division": "Division", "department": "Department",
#                 "total_flights": "Flights", "total_hours": "Hours",
#                 "unique_routes": "Routes",
#             }).to_pandas(),
#             width="stretch",
#         )

#     st.divider()

#     # ── Chart 3: Understaffed routes ──────────────────────────────────────────
#     st.subheader("Routes with Crew Shortfalls")
#     st.caption(
#         "Routes where the number of crew assigned was below the aircraft's required crew. "
#         "Gap rate = total missing crew slots / total required crew slots."
#     )

#     if len(gaps_f) == 0:
#         st.info("No crew gaps found for the selected filters.")
#     else:
#         top_gaps = gaps_f.head(20)
#         gap_fig = px.bar(
#             top_gaps.to_pandas(),
#             x="total_crew_gap",
#             y="route_label",
#             orientation="h",
#             color="gap_rate_pct",
#             color_continuous_scale="Reds",
#             hover_data={
#                 "total_flights": True,
#                 "total_required_crew": True,
#                 "total_actual_crew": True,
#                 "months_understaffed": True,
#                 "gap_rate_pct": ":.1f",
#             },
#             labels={
#                 "total_crew_gap": "Total Missing Crew Slots",
#                 "route_label": "",
#                 "gap_rate_pct": "Gap Rate (%)",
#                 "total_flights": "Total Flights",
#                 "total_required_crew": "Required Crew",
#                 "total_actual_crew": "Actual Crew",
#                 "months_understaffed": "Months Understaffed",
#             },
#         )
#         gap_fig.update_layout(yaxis={"categoryorder": "total ascending"})
#         st.plotly_chart(gap_fig, width="stretch")

#     st.divider()

#     # ── Chart 4: Monthly understaffing trend ──────────────────────────────────
#     st.subheader("Monthly Crew Gap Trend")
#     st.caption("Total missing crew slots across all routes per month — reveals seasonal peaks.")

#     if len(trend_f) == 0:
#         st.info("No trend data available for the selected filters.")
#     else:
#         trend_fig = px.line(
#             trend_f.to_pandas(),
#             x="period",
#             y="total_crew_gap",
#             markers=True,
#             labels={
#                 "period": "Month",
#                 "total_crew_gap": "Total Missing Crew Slots",
#             },
#         )
#         trend_fig.update_layout(xaxis_tickangle=-45)
#         st.plotly_chart(trend_fig, width="stretch")

#     st.divider()

#     # ── Full utilisation table ────────────────────────────────────────────────
#     st.subheader("Full Staff Utilisation Table")
#     full_table = (
#         util_f
#         .select("firstnme", "lastname", "division", "department",
#                 "total_flights", "total_hours", "unique_routes",
#                 "is_overused", "is_underused")
#         .rename({
#             "firstnme": "First", "lastname": "Last",
#             "division": "Division", "department": "Department",
#             "total_flights": "Flights", "total_hours": "Hours",
#             "unique_routes": "Routes",
#             "is_overused": "Overused (P90+)", "is_underused": "Underused (P10-)",
#         })
#         .to_pandas()
#     )
#     st.dataframe(full_table, width="stretch")
#     st.download_button(
#         "Download staff utilisation CSV",
#         data=full_table.to_csv(index=False),
#         file_name="staff_utilisation.csv",
#         mime="text/csv",
#     )

#     st.caption(
#         "Data source: ATTGRP1.FLIGHT_CREW joined with ATTGRP1.STAFF and ATTGRP1.ROUTES. "
#         "Crew gaps derived from ATTGRP1.FLIGHTS × ATTGRP1.AIRPLANES.CREW_MEMBERS."
#     )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Revenue Analysis (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    def format_revenue(value: float | int | None) -> str:
        if value is None:
            return "0"
        return f"{float(value):,.0f}"


    def select_options(df: pl.DataFrame, column: str) -> list[str]:
        if df.is_empty():
            return [ALL_OPTION]

        values = (
            df.select(pl.col(column).drop_nulls().unique().sort())
            .to_series()
            .to_list()
        )
        return [ALL_OPTION, *[str(value) for value in values]]


    def apply_dimension_filters(
        df: pl.DataFrame,
        continent: str = ALL_OPTION,
        country: str = ALL_OPTION,
        city: str = ALL_OPTION,
    ) -> pl.DataFrame:
        filtered = df

        if continent != ALL_OPTION:
            filtered = filtered.filter(pl.col("continent") == continent)
        if country != ALL_OPTION:
            filtered = filtered.filter(pl.col("country") == country)
        if city != ALL_OPTION:
            filtered = filtered.filter(pl.col("city") == city)

        return filtered


    def date_bounds(df: pl.DataFrame):
        bounds = df.select(
            pl.col("year_month").min().alias("start_date"),
            pl.col("year_month").max().alias("end_date"),
        ).row(0, named=True)

        return bounds["start_date"], bounds["end_date"]


    def first_row(df: pl.DataFrame) -> dict:
        if df.is_empty():
            return {}

        return df.row(0, named=True)


    def build_revenue_tab() -> None:
        df = get_revenue_data()

        st.title("Revenue")
        st.markdown("""How is the revenue behaving over time? Where are the main hubs for departing flights? What type of tickets are our passengers buyin?
                    This dashboards analyses characterization of the revenue""")

        filter_container = st.container()
        with filter_container:
            st.subheader("Filters")
            filter_cols = st.columns(5)

            continent = filter_cols[0].selectbox(
                    "Continent",
                    select_options(df, "continent"),
            )

            country_base = apply_dimension_filters(df, continent=continent)
            country = filter_cols[1].selectbox(
                    "Country",
                    select_options(country_base, "country"),
                )

            city_base = apply_dimension_filters(
                    df,
                    continent=continent,
                    country=country,
                )
            city = filter_cols[2].selectbox(
                    "City",
                    select_options(city_base, "city"),
                )

            location_filtered = apply_dimension_filters(
                    df,
                    continent=continent,
                    country=country,
                    city=city,
                )

            if location_filtered.is_empty():
                    st.warning("No revenue data matches the selected filters.")
                    return

            min_date, max_date = date_bounds(location_filtered)
            start_date = filter_cols[3].date_input(
                    "Start date",
                    value=min_date,
                    min_value=min_date,
                    max_value=max_date,
                )
            end_date = filter_cols[4].date_input(
                    "End date",
                    value=max_date,
                    min_value=min_date,
                    max_value=max_date,
                )

            if start_date > end_date:
                st.warning("Start date must be before or equal to end date.")
                return

        start = start_date.isoformat()
        end = end_date.isoformat()

        total_revenue = total_revenue_per_range(location_filtered, start, end)
        top_route = first_row(
                most_profitable_outgoing_route(location_filtered, start, end)
            )
        top_city = first_row(most_revenue_perceived(location_filtered, start, end))

        metric_cols = st.columns(3)
        metric_cols[0].metric( f"Total revenue", format_revenue(total_revenue))

        route = top_route.get("route", "No route")
        route_revenue = format_revenue(top_route.get("total_revenue"))
        if top_route.get("destination_city"):
            origin = f"{top_route['city']}"
            destination = f"{top_route['destination_city']}"

        metric_cols[1].metric("Most profitable outgoing route", f"{origin} to {destination}", route_revenue)
        city_label = "No city"
        if top_city:
            city_label = f"{top_city.get('city')}, {top_city.get('country').title()}"
        metric_cols[2].metric(
                "Most revenue perceived",
                city_label,
                format_revenue(top_city.get("total_revenue")),
            )
        st.caption(f"From {start} and {end}")
        trend_df = revenue_trend_analysis(location_filtered, start, end)
        if trend_df.is_empty():
            st.info("No revenue trend data is available for this selection.")
        else:
            trend_fig = px.line(
            trend_df.to_pandas(),
            x="year_month",
            y="total_revenue",
            markers=True,
            labels={
                    "year_month": "Month",
                    "total_revenue": "Revenue",
                    },
                )
            trend_fig.update_layout(
                    title= "Revenue Trend <br>",
                    hovermode="x unified",
                    margin=dict(l=0, r=0, t=50, b=0),
                )
            st.plotly_chart(trend_fig, use_container_width=True)
            st.caption("sub")

        chart_cols = st.columns([1, 1.4])

        class_df = revenue_class_analysis(location_filtered, start, end)
        with chart_cols[0]:
            if class_df.is_empty():
                    st.info("No class revenue data is available for this selection.")
            else:
                class_fig = px.pie(
                    class_df.to_pandas(),
                    names="class",
                    values="total_revenue",
                    hole=0.58,
                    labels={
                            "class": "Class",
                            "total_revenue": "Revenue",
                    },
                )
                class_fig.update_traces(
                    textposition="inside",
                    texttemplate="%{label}<br>%{percent:.1%}",
                    hovertemplate="<b>%{label}</b><br>Revenue: %{value:,.0f}<br>Share: %{percent}<extra></extra>",
                    )
                class_fig.update_layout(
                        title="Revenue by Class",
                        margin=dict(l=0, r=0, t=48, b=0),
                        showlegend=True,
                    )
                st.plotly_chart(class_fig, use_container_width=True)
                class_max = class_df.filter(pl.col('total_revenue') == pl.col('total_revenue').max()).select('class')[0 , 0]
                classes_dict = {"E": "Economy","B": "Business", "P": "Premium"}
                st.caption(f"Class attracting the highest revenue: {classes_dict[class_max]}")

        country_df = revenue_per_country(location_filtered, start, end)
        with chart_cols[1]:
                if country_df.is_empty():
                    st.info("No country revenue data is available for this selection.")
                else:
                    map_fig = px.choropleth(
                        country_df.to_pandas(),
                        locations="country",
                        locationmode="country names",
                        color="total_revenue",
                        hover_name="country",
                        color_continuous_scale="YlOrRd",
                        labels={"total_revenue": "Revenue"},
                        projection="natural earth",
                    )
                    map_fig.update_layout(
                        title="Revenue by Country",
                        margin=dict(l=0, r=0, t=48, b=0),
                    )
                    st.plotly_chart(map_fig, use_container_width=True)
                    country_max = country_df.filter(pl.col('total_revenue') == pl.col('total_revenue').max()).select('country')[0 , 0]
                    st.caption(f"Country attracting the highest revenue: {country_max.title()}")

    st.caption(
        "Data source: ATTGRP1.TICKETS aggregated via SQL JOIN with ROUTES, "
        "enriched with ATTGRP1.AIRPORTS geographic data."
    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Plane Capacity Analysis (NEW)
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    df_capacity = get_capacity_data()
    
    if df_capacity.is_empty():
        st.warning("No capacity data available. Please ensure capacity.parquet is in the data directory.")
    else:
        st.title("Plane Capacity Analysis")
        st.markdown(
            "Track aircraft **seat occupancy and utilization** across routes, flights, and time. "
            "Monitor capacity percentage to optimize scheduling and revenue management."
        )
        
        # Calculate occupancy percentage and add temporal columns for analysis
        try:
            df_capacity = df_capacity.with_columns([
                (pl.col("tickets_sold") / pl.col("total_capacity")).alias("capacity_pct"),
                pl.col("route_code").alias("route_id"),
            ])
            
            # Add temporal columns - handle datetime directly
            df_capacity = df_capacity.with_columns([
                pl.col("departure").dt.week().alias("week"),
                pl.col("departure").dt.month().alias("month"),
                pl.col("departure").dt.weekday().alias("day_of_week"),
                pl.col("departure").dt.strftime("%Y-%m").alias("year_month"),
            ])
        except Exception as e:
            st.error(f"Error processing capacity data: {str(e)}")
            st.write(f"Columns available: {df_capacity.columns}")
            st.write(f"Data types: {df_capacity.schema}")
            st.stop()
        
        # Key metrics
        metric_cols = st.columns(4)
        avg_capacity = df_capacity["capacity_pct"].mean()
        max_capacity = df_capacity["capacity_pct"].max()
        flights_count = df_capacity.select("flight_id").n_unique()
        routes_count = df_capacity.select("route_id").n_unique()
        
        metric_cols[0].metric("Avg Occupancy Rate", f"{avg_capacity:.1%}")
        metric_cols[1].metric("Peak Occupancy", f"{max_capacity:.1%}")
        metric_cols[2].metric("Flights Tracked", int(flights_count))
        metric_cols[3].metric("Routes Covered", int(routes_count))
        
        st.divider()
        
        # ─────────────────────────────────────────────────────────────
        # VISUALIZATION 1: Temporal Analysis (Week, Month, Day of Week)
        # ─────────────────────────────────────────────────────────────
        st.subheader("📅 Capacity Over Time")
        
        temporal_tab1, temporal_tab2, temporal_tab3 = st.tabs(
            ["By Week", "By Month", "By Day of Week"]
        )
        
        # By Week
        with temporal_tab1:
            weekly_data = (
                df_capacity.group_by("week")
                .agg([
                    pl.col("capacity_pct").mean().alias("avg_capacity"),
                    pl.col("flight_id").n_unique().alias("flights"),
                ])
                .sort("week")
                .to_pandas()
            )
            
            weekly_fig = px.line(
                weekly_data,
                x="week",
                y="avg_capacity",
                markers=True,
                title="Average Capacity by Week",
                labels={"week": "Week Number", "avg_capacity": "Avg Occupancy %"},
                hover_data={"flights": True},
            )
            weekly_fig.update_yaxes(tickformat=".0%")
            weekly_fig.update_layout(hovermode="x unified", margin=dict(l=0, r=0, t=50, b=0))
            st.plotly_chart(weekly_fig, use_container_width=True)
        
        # By Month
        with temporal_tab2:
            monthly_data = (
                df_capacity.group_by("year_month")
                .agg([
                    pl.col("capacity_pct").mean().alias("avg_capacity"),
                    pl.col("flight_id").n_unique().alias("flights"),
                ])
                .sort("year_month")
                .to_pandas()
            )
            
            monthly_fig = px.bar(
                monthly_data,
                x="year_month",
                y="avg_capacity",
                title="Average Capacity by Month",
                labels={"year_month": "Month", "avg_capacity": "Avg Occupancy %"},
                hover_data={"flights": True},
                color="avg_capacity",
                color_continuous_scale="RdYlGn",
            )
            monthly_fig.update_yaxes(tickformat=".0%")
            monthly_fig.update_layout(margin=dict(l=0, r=0, t=50, b=0))
            st.plotly_chart(monthly_fig, use_container_width=True)
        
        # By Day of Week
        with temporal_tab3:
            day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 
                        4: "Friday", 5: "Saturday", 6: "Sunday"}
            
            dow_data = (
                df_capacity.group_by("day_of_week")
                .agg([
                    pl.col("capacity_pct").mean().alias("avg_capacity"),
                    pl.col("flight_id").n_unique().alias("flights"),
                ])
                .sort("day_of_week")
                .with_columns(
                    pl.col("day_of_week").map_elements(lambda x: day_names.get(x, str(x))).alias("day_name")
                )
                .to_pandas()
            )
            
            dow_fig = px.bar(
                dow_data,
                x="day_name",
                y="avg_capacity",
                title="Average Capacity by Day of Week",
                labels={"day_name": "Day", "avg_capacity": "Avg Occupancy %"},
                hover_data={"flights": True},
                color="avg_capacity",
                color_continuous_scale="Blues",
            )
            dow_fig.update_yaxes(tickformat=".0%")
            dow_fig.update_layout(margin=dict(l=0, r=0, t=50, b=0))
            st.plotly_chart(dow_fig, use_container_width=True)
        
        st.divider()
        
        # ─────────────────────────────────────────────────────────────
        # VISUALIZATION 2: Capacity by Flight ID
        # ─────────────────────────────────────────────────────────────
        st.subheader("✈️ Capacity by Flight")
        
        flight_data = (
            df_capacity.group_by("flight_id")
            .agg([
                pl.col("capacity_pct").mean().alias("avg_capacity"),
                pl.col("capacity_pct").max().alias("max_capacity"),
                pl.col("capacity_pct").min().alias("min_capacity"),
                pl.col("route_id").first().alias("route_id"),
                pl.col("departure").count().alias("observations"),
            ])
            .sort("avg_capacity", descending=True)
            .to_pandas()
        )
        
        # Create two columns: scatter and table
        flight_col1, flight_col2 = st.columns([2, 1])
        
        with flight_col1:
            flight_fig = px.scatter(
                flight_data,
                x="flight_id",
                y="avg_capacity",
                size="observations",
                color="avg_capacity",
                hover_data={"route_id": True, "max_capacity": ":.1%", "min_capacity": ":.1%"},
                color_continuous_scale="Viridis",
                title="Average Capacity by Flight ID",
                labels={"flight_id": "Flight ID", "avg_capacity": "Avg Occupancy %"},
            )
            flight_fig.update_yaxes(tickformat=".0%")
            flight_fig.update_layout(margin=dict(l=0, r=0, t=50, b=0), height=500)
            st.plotly_chart(flight_fig, use_container_width=True)
        
        with flight_col2:
            st.caption("Top 10 Flights by Capacity")
            top_flights = flight_data.nlargest(10, "avg_capacity")[["flight_id", "avg_capacity", "route_id"]]
            top_flights["avg_capacity"] = top_flights["avg_capacity"].apply(lambda x: f"{x:.1%}")
            st.dataframe(top_flights, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # ─────────────────────────────────────────────────────────────
        # VISUALIZATION 3: Capacity by Route ID
        # ─────────────────────────────────────────────────────────────
        st.subheader("🛫 Capacity by Route")
        
        route_data = (
            df_capacity.group_by("route_id")
            .agg([
                pl.col("capacity_pct").mean().alias("avg_capacity"),
                pl.col("capacity_pct").max().alias("max_capacity"),
                pl.col("flight_id").n_unique().alias("num_flights"),
                pl.col("departure").count().alias("observations"),
            ])
            .sort("avg_capacity", descending=True)
            .to_pandas()
        )
        
        # Horizontal bar chart
        route_fig = px.bar(
            route_data.head(20),
            y="route_id",
            x="avg_capacity",
            orientation="h",
            color="avg_capacity",
            color_continuous_scale="RdYlGn",
            hover_data={"num_flights": True, "max_capacity": ":.1%"},
            title="Top 20 Routes by Average Capacity",
            labels={"route_id": "Route ID", "avg_capacity": "Avg Occupancy %"},
        )
        route_fig.update_xaxes(tickformat=".0%")
        route_fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=0, r=0, t=50, b=0))
        st.plotly_chart(route_fig, use_container_width=True)
        
        st.divider()
        
        # Capacity summary statistics
        st.subheader("Summary Statistics")
        summary_cols = st.columns(3)
        
        with summary_cols[0]:
            st.metric(
                "Flights with >90% Occupancy",
                len(flight_data[flight_data["avg_capacity"] > 0.9])
            )
        
        with summary_cols[1]:
            st.metric(
                "Flights with <50% Occupancy",
                len(flight_data[flight_data["avg_capacity"] < 0.5])
            )
        
        with summary_cols[2]:
            st.metric(
                "Routes Analyzed",
                len(route_data)
            )