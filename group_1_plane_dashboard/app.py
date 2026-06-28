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


<<<<<<< HEAD
MONTH_LABELS   = {7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
WEEKDAY_LABELS = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


@st.cache_data
def get_capacity_data() -> pl.DataFrame | None:
    path = DATA_DIR / "capacity.parquet"
    if not path.exists():
        return None
    return (
        pl.read_parquet(path)
        .with_columns(
            pl.when(pl.col("total_capacity") > 0)
              .then(pl.col("tickets_sold").cast(pl.Float64) / pl.col("total_capacity"))
              .otherwise(None)
              .alias("occupancy_rate"),
            (pl.col("total_capacity") - pl.col("tickets_sold")).alias("available_seats"),
            pl.col("departure").dt.month().alias("month"),
            pl.col("departure").dt.week().alias("week"),
            pl.col("departure").dt.weekday().alias("day_of_week"),
        )
    )
=======
@st.cache_data(show_spinner="Loading revenue data...")
def get_revenue_data() -> pl.DataFrame:
    df = pl.DataFrame()
    try:
        df = load_revenue_data()
    except Exception:
        pass
    return df
>>>>>>> origin/main


# ── Tabs ──────────────────────────────────────────────────────────────────────

<<<<<<< HEAD
tab1, tab2, tab3 = st.tabs(["Revenue & Tax", "Staff Occupation", "Flight Occupation"])
=======
tab1, tab2, tab3 = st.tabs(["Revenue & Tax", "Staff Occupation", "Revenue Anlaysis"])


def multiselect_with_all(container, label: str, options: list[str]) -> list[str]:
    """Multiselect dropdown with every option selected by default. Leaving the
    selection empty is treated as selecting every option."""
    selected = container.multiselect(label, options, default=options)
    return selected or options
>>>>>>> origin/main


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

    build_revenue_tab()
    st.subheader("Key Findings")
    st.markdown(
        """
- **Revenue seasonality.** The revenue trend shows that during the second and 
    fourth quarter revenue increaseas, showing evidennce of higer demand during 
    that time.
- **Economy class is the higest revenue driver**
  Most tickets that are sold are for Economy passengers reaching over the 70%
  of tickets sold.
- **Airplanes departures are higgly concentrated.** The
  map reveals how most of the planes come from two specific hubs, United States and France.
"""
    )
    st.caption(
<<<<<<< HEAD
        "Data source: ATTGRP1.FLIGHT_CREW joined with ATTGRP1.STAFF and ATTGRP1.ROUTES. "
        "Crew gaps derived from ATTGRP1.FLIGHTS × ATTGRP1.AIRPLANES.CREW_MEMBERS."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Flight Occupation
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    cap_df = get_capacity_data()

    if cap_df is None:
        st.error(
            "data/capacity.parquet not found. "
            "Run the SQL cell in s04_group_project.ipynb to generate it, "
            "then copy the file into the data/ folder."
        )
    else:
        # ── Sidebar filters ───────────────────────────────────────────────────
        st.sidebar.markdown("---")
        st.sidebar.subheader("Flight Occupation filters")
        st.sidebar.caption("Leave a filter empty to include all values.")

        all_months = sorted(cap_df["month"].unique().to_list())
        sel_months = st.sidebar.multiselect(
            "Departure month",
            options=all_months,
            default=[],
            format_func=lambda m: MONTH_LABELS.get(m, str(m)),
        )

        all_weekdays = sorted(cap_df["day_of_week"].unique().to_list())
        sel_weekdays = st.sidebar.multiselect(
            "Departure day of week",
            options=all_weekdays,
            default=[],
            format_func=lambda d: WEEKDAY_LABELS.get(d, str(d)),
        )

        all_weeks = sorted(cap_df["week"].unique().to_list())
        sel_weeks = st.sidebar.multiselect(
            "Departure week (ISO #)",
            options=all_weeks,
            default=[],
        )

        all_routes = sorted(cap_df["route_code"].drop_nulls().unique().to_list())
        sel_routes = st.sidebar.multiselect(
            "Route code",
            options=all_routes,
            default=[],
        )

        all_airplanes = sorted(cap_df["airplane_id"].drop_nulls().unique().to_list())
        sel_airplanes = st.sidebar.multiselect(
            "Airplane ID",
            options=all_airplanes,
            default=[],
        )

        all_flights = sorted(cap_df["flight_id"].drop_nulls().unique().to_list())
        sel_flights = st.sidebar.multiselect(
            "Flight ID",
            options=all_flights,
            default=[],
        )

        # Apply filters — empty selection means no filter on that dimension
        filtered_cap = cap_df
        if sel_months:
            filtered_cap = filtered_cap.filter(pl.col("month").is_in(sel_months))
        if sel_weekdays:
            filtered_cap = filtered_cap.filter(pl.col("day_of_week").is_in(sel_weekdays))
        if sel_weeks:
            filtered_cap = filtered_cap.filter(pl.col("week").is_in(sel_weeks))
        if sel_routes:
            filtered_cap = filtered_cap.filter(pl.col("route_code").is_in(sel_routes))
        if sel_airplanes:
            filtered_cap = filtered_cap.filter(pl.col("airplane_id").is_in(sel_airplanes))
        if sel_flights:
            filtered_cap = filtered_cap.filter(pl.col("flight_id").is_in(sel_flights))

        # ── Header & KPIs ─────────────────────────────────────────────────────
        st.title("Flight Occupation Analysis  (Jul – Dec 2025)")
        st.markdown(
            "Seat occupancy rates across routes, aircraft, and time — "
            "how many available seats were filled on each departure."
        )

        total_cap_val  = filtered_cap["total_capacity"].sum()
        total_sold_val = filtered_cap["tickets_sold"].sum()
        overall_occ    = total_sold_val / total_cap_val if total_cap_val > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Flight Departures",   f"{filtered_cap.height:,}")
        k2.metric("Total Seat Capacity", f"{total_cap_val:,}")
        k3.metric("Tickets Sold",        f"{total_sold_val:,}")
        k4.metric("Overall Occupancy",   f"{overall_occ:.1%}")

        st.divider()

        # ── Aggregation helper ────────────────────────────────────────────────
        def agg_occ(df: pl.DataFrame, dim: str) -> pl.DataFrame:
            return (
                df.group_by(dim)
                .agg(
                    pl.len().alias("flights"),
                    pl.col("total_capacity").sum().alias("total_capacity"),
                    pl.col("tickets_sold").sum().alias("tickets_sold"),
                )
                .with_columns(
                    (pl.col("tickets_sold") / pl.col("total_capacity")).alias("occupancy_rate"),
                    (pl.col("total_capacity") - pl.col("tickets_sold")).alias("available_seats"),
                )
                .sort(dim)
            )

        # ── Row 1: Month and Day of Week ──────────────────────────────────────
        col_month, col_dow = st.columns(2)

        with col_month:
            st.subheader("Occupancy by Month")
            month_agg = agg_occ(filtered_cap, "month").with_columns(
                pl.col("month")
                  .map_elements(lambda m: MONTH_LABELS.get(m, str(m)), return_dtype=pl.String)
                  .alias("label")
            )
            fig_m = px.bar(
                month_agg.to_pandas(), x="label", y="occupancy_rate",
                custom_data=["flights", "tickets_sold", "total_capacity", "available_seats"],
                labels={"label": "Month", "occupancy_rate": "Occupancy Rate"},
                color="occupancy_rate", color_continuous_scale="RdYlGn", range_color=[0, 1],
            )
            fig_m.update_traces(
                texttemplate="%{y:.1%}", textposition="outside",
                hovertemplate=(
                    "<b>%{x}</b><br>Occupancy: %{y:.1%}<br>"
                    "Tickets sold: %{customdata[1]:,}<br>Capacity: %{customdata[2]:,}<br>"
                    "Available: %{customdata[3]:,}<br>Flights: %{customdata[0]:,}<extra></extra>"
                ),
            )
            fig_m.update_yaxes(tickformat=".0%", range=[0, 1.15])
            fig_m.update_coloraxes(showscale=False)
            st.plotly_chart(fig_m, use_container_width=True)

        with col_dow:
            st.subheader("Occupancy by Day of Week")
            dow_agg = agg_occ(filtered_cap, "day_of_week").with_columns(
                pl.col("day_of_week")
                  .map_elements(lambda d: WEEKDAY_LABELS.get(d, str(d)), return_dtype=pl.String)
                  .alias("label")
            )
            fig_d = px.bar(
                dow_agg.to_pandas(), x="label", y="occupancy_rate",
                custom_data=["flights", "tickets_sold", "total_capacity", "available_seats"],
                labels={"label": "Day of Week", "occupancy_rate": "Occupancy Rate"},
                color="occupancy_rate", color_continuous_scale="RdYlGn", range_color=[0, 1],
            )
            fig_d.update_traces(
                texttemplate="%{y:.1%}", textposition="outside",
                hovertemplate=(
                    "<b>%{x}</b><br>Occupancy: %{y:.1%}<br>"
                    "Tickets sold: %{customdata[1]:,}<br>Capacity: %{customdata[2]:,}<br>"
                    "Available: %{customdata[3]:,}<br>Flights: %{customdata[0]:,}<extra></extra>"
                ),
            )
            fig_d.update_yaxes(tickformat=".0%", range=[0, 1.15])
            fig_d.update_coloraxes(showscale=False)
            st.plotly_chart(fig_d, use_container_width=True)

        st.divider()

        # ── Row 2: Weekly trend ───────────────────────────────────────────────
        st.subheader("Weekly Occupancy Trend")
        st.caption("Occupancy rate per ISO week — reveals seasonal patterns across the 6-month window.")
        week_agg = agg_occ(filtered_cap, "week")
        fig_w = px.line(
            week_agg.to_pandas(), x="week", y="occupancy_rate", markers=True,
            custom_data=["flights", "tickets_sold", "total_capacity"],
            labels={"week": "ISO Week", "occupancy_rate": "Occupancy Rate"},
        )
        fig_w.update_traces(
            hovertemplate=(
                "<b>Week %{x}</b><br>Occupancy: %{y:.1%}<br>"
                "Tickets sold: %{customdata[1]:,}<br>Capacity: %{customdata[2]:,}<br>"
                "Flights: %{customdata[0]:,}<extra></extra>"
            ),
        )
        fig_w.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig_w, use_container_width=True)

        st.divider()

        # ── Row 3: Route and Airplane ─────────────────────────────────────────
        col_route, col_plane = st.columns(2)

        with col_route:
            st.subheader("Top 20 Routes by Occupancy")
            route_agg = (
                agg_occ(filtered_cap, "route_code")
                .sort("occupancy_rate", descending=True)
                .head(20)
            )
            fig_r = px.bar(
                route_agg.to_pandas(), x="occupancy_rate", y="route_code", orientation="h",
                custom_data=["flights", "tickets_sold", "total_capacity", "available_seats"],
                labels={"route_code": "", "occupancy_rate": "Occupancy Rate"},
                color="occupancy_rate", color_continuous_scale="RdYlGn", range_color=[0, 1],
            )
            fig_r.update_traces(
                texttemplate="%{x:.1%}", textposition="outside",
                hovertemplate=(
                    "<b>%{y}</b><br>Occupancy: %{x:.1%}<br>"
                    "Tickets sold: %{customdata[1]:,}<br>Capacity: %{customdata[2]:,}<br>"
                    "Available: %{customdata[3]:,}<br>Flights: %{customdata[0]:,}<extra></extra>"
                ),
            )
            fig_r.update_xaxes(tickformat=".0%", range=[0, 1.15])
            fig_r.update_coloraxes(showscale=False)
            fig_r.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_r, use_container_width=True)

        with col_plane:
            st.subheader("Top 20 Airplanes by Occupancy")
            plane_agg = (
                agg_occ(filtered_cap, "airplane_id")
                .sort("occupancy_rate", descending=True)
                .head(20)
            )
            fig_p = px.bar(
                plane_agg.to_pandas(), x="occupancy_rate", y="airplane_id", orientation="h",
                custom_data=["flights", "tickets_sold", "total_capacity", "available_seats"],
                labels={"airplane_id": "", "occupancy_rate": "Occupancy Rate"},
                color="occupancy_rate", color_continuous_scale="RdYlGn", range_color=[0, 1],
            )
            fig_p.update_traces(
                texttemplate="%{x:.1%}", textposition="outside",
                hovertemplate=(
                    "<b>%{y}</b><br>Occupancy: %{x:.1%}<br>"
                    "Tickets sold: %{customdata[1]:,}<br>Capacity: %{customdata[2]:,}<br>"
                    "Available: %{customdata[3]:,}<br>Flights: %{customdata[0]:,}<extra></extra>"
                ),
            )
            fig_p.update_xaxes(tickformat=".0%", range=[0, 1.15])
            fig_p.update_coloraxes(showscale=False)
            fig_p.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_p, use_container_width=True)

        st.divider()

        # ── Flight-level detail ───────────────────────────────────────────────
        st.subheader("Flight Departure Detail")
        st.caption(f"{filtered_cap.height:,} departures matching current filters.")
        detail = (
            filtered_cap
            .with_columns(
                (pl.col("occupancy_rate") * 100).round(1).alias("occupancy_%")
            )
            .select([
                "flight_id", "departure", "route_code", "airplane_id",
                "total_capacity", "tickets_sold", "available_seats", "occupancy_%",
            ])
            .sort("occupancy_%", descending=True)
            .to_pandas()
        )
        st.dataframe(detail, use_container_width=True)
        st.download_button(
            "Download flight detail CSV",
            data=detail.to_csv(index=False),
            file_name="flight_occupation_detail.csv",
            mime="text/csv",
        )

        st.caption(
            "Data source: ATTGRP1.FLIGHTS × ATTGRP1.AIRPLANES × ATTGRP1.TICKETS "
            "(Jul–Dec 2025). Occupancy = tickets sold / total seat capacity."
        )
=======
        "Data source: ATTGRP1.TICKETS aggregated via SQL JOIN with ROUTES, "
        "enriched with ATTGRP1.AIRPORTS geographic data."
    )
>>>>>>> origin/main
