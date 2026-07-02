import streamlit as st
import polars as pl
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path

from analysis.ticket_revenue import load_data, filter_data
from analysis.staff import (
    load_staff_counts,
    load_staff_employee_dim,
    load_staff_monthly_agg,
    load_staff_usage,
    staff_global_kpis,
    aircraft_staff_requirements,
    route_staff_needs,
    department_stats,
    flying_hours_over_time,
    staff_utilisation
)

from analysis.revenue_analysis import (
    compute_revenue_dashboard_metrics,
    filter_by_date_range,
    load_revenue_data,
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


@st.cache_resource
def get_ticket_data() -> pl.DataFrame:
    needed = [DATA_DIR / "tickets_agg.parquet", DATA_DIR / "airports.parquet"]
    if not all(p.exists() for p in needed):
        with st.spinner("Loading ticket data from database (first run only)..."):
            _fetch_tickets_from_db()
    return load_data()


@st.cache_resource
def get_staff_data() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    needed = [
        DATA_DIR / "q1_staff_counts.parquet",
        DATA_DIR / "staff_employee_dim.parquet",
        DATA_DIR / "staff_monthly_agg.parquet",
        DATA_DIR / "q3_staff_usage.parquet"
    ]
    if not all(p.exists() for p in needed):
        st.error("Missing staff data Parquet files. Please run the extraction script manually (e.g. `python -m db.staff`) before using the dashboard.")
        st.stop()
    return load_staff_counts(), load_staff_employee_dim(), load_staff_monthly_agg(), load_staff_usage()


@st.cache_resource
def get_revenue_data() -> pl.DataFrame:
    return load_revenue_data()


@st.cache_resource(show_spinner="Loading capacity data...", ttl=3600)
def get_capacity_data() -> pl.DataFrame:
    try:
        capacity_file = DATA_DIR / "capacity.parquet"
        if not capacity_file.exists():
            st.error(f"Capacity file not found at {capacity_file}")
            return pl.DataFrame()
        return pl.read_parquet(capacity_file)
    except Exception as e:
        st.error(f"Error loading capacity data: {str(e)}")
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
    st.plotly_chart(map_fig, use_container_width=True)

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
        st.plotly_chart(bar_fig, use_container_width=True)

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
        st.plotly_chart(scatter_fig, use_container_width=True)

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
    st.plotly_chart(country_fig, use_container_width=True)

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
    st.dataframe(table_df, use_container_width=True)

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
    counts_raw, employee_dim, monthly_agg, usage_raw = get_staff_data()
    if counts_raw.is_empty() or monthly_agg.is_empty():
        st.warning("Missing staff data Parquet files. Please run the extraction script manually (e.g. `python -m group_1_plane_dashboard.db.staff`) before using the dashboard.")
    else:

        # ── Header & Filters ───────────────────────────────────────────────
        st.title("Staff Occupation & Requirements")
        st.markdown(
            "Comprehensive analysis of staff deployment, aircraft requirements, "
            "route gaps, and employee utilisation."
        )

        with st.container():
            st.subheader("Staff filters")

            all_years = sorted(monthly_agg["year"].drop_nulls().unique().to_list())
            year_range = st.select_slider(
                "Year range", options=all_years, value=(all_years[0], all_years[-1])
            )

        # Apply filters
        filtered_assign = monthly_agg.filter(
            pl.col("year").is_between(year_range[0], year_range[1])
        )

        filtered_usage = usage_raw.filter(
            pl.col("departure").dt.year().is_between(year_range[0], year_range[1])
        )

        # Compute metrics
        kpis = staff_global_kpis(counts_raw, filtered_assign)
        aircraft_reqs = aircraft_staff_requirements(filtered_usage)
        route_needs = route_staff_needs(filtered_usage)
        dept_stats = department_stats(counts_raw, employee_dim, filtered_assign)
        temporal_hours = flying_hours_over_time(filtered_assign)
        util_df = staff_utilisation(filtered_assign, employee_dim)

        # ── KPIs ─────────────────────────────────────────────────────────
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Staff", f"{kpis['total_staff']:,}")
        k2.metric("Avg Distance / Staff", f"{kpis['avg_km_per_staff']:,.1f} km")
        k3.metric("Avg Hours / Staff", f"{kpis['avg_hours_per_staff']:,.1f} h")

        st.divider()

        # ── Chart: Aircraft Requirements ──────────────────────────────────────────
        st.subheader("Aircraft Staffing Requirements")
        st.caption("Which aircraft models require the most vs. least staff, and how well are they supplied?")

        air_fig = px.bar(
            aircraft_reqs.to_pandas(),
            x="airplane_model",
            y=["avg_required_crew", "avg_used_crew"],
            barmode="group",
            labels={
                "airplane_model": "Aircraft Model",
                "value": "Number of Crew",
                "variable": "Crew Type"
            }
        )
        st.plotly_chart(air_fig, use_container_width=True)

        st.divider()



        # ── Chart: Department Stats ───────────────────────────────────────────────
        st.subheader("Department Analysis")
        st.caption("Which departments have the most staff, and which require the most flight hours?")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            d1_fig = px.bar(
                dept_stats.head(10).to_pandas(),
                x="staff_count", y="department", orientation="h",
                labels={"staff_count": "Total Staff", "department": ""}
            )
            d1_fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(d1_fig, use_container_width=True)

        with col_d2:
            d2_fig = px.bar(
                dept_stats.with_columns(pl.col("total_hours_required").fill_null(0)).sort("total_hours_required", descending=True).head(10).to_pandas(),
                x="total_hours_required", y="department", orientation="h",
                color_discrete_sequence=["#2ca02c"],
                labels={"total_hours_required": "Total Hours", "department": ""}
            )
            d2_fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(d2_fig, use_container_width=True)

        st.divider()

        # ── Chart: Temporal Flying Hours ──────────────────────────────────────────
        st.subheader("Flying Hours Over Time")
        st.caption("Average flying hours per staff member per month.")

        time_fig = px.line(
            temporal_hours.to_pandas(),
            x="period", y="avg_hours_per_staff",
            markers=True,
            labels={"period": "Month", "avg_hours_per_staff": "Avg Hours / Staff"}
        )
        time_fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(time_fig, use_container_width=True)

        st.divider()

        # ── Chart: Vacation / Overworked ──────────────────────────────────────────
        st.subheader("Staff Welfare: Vacations vs More Hours Needed")

        if len(util_df) > 0:
            p90 = float(util_df["p90_threshold"].first())
            p10 = float(util_df["p10_threshold"].first())
            st.caption(f"Based on total hours. P90 threshold (Overworked) = {p90:.0f}h. P10 threshold (Underused) = {p10:.0f}h.")

            col_overw, col_underw = st.columns(2)
            with col_overw:
                st.markdown("**Overworked (Needs Vacation)**")
                overworked = util_df.filter(pl.col("is_overused")).select(
                    ["firstnme", "lastname", "department", "total_hours"]
                )
                st.dataframe(overworked, use_container_width=True)

            with col_underw:
                st.markdown("**Underused (Needs More Hours)**")
                underworked = util_df.filter(pl.col("is_underused")).select(
                    ["firstnme", "lastname", "department", "total_hours"]
                )
                st.dataframe(underworked, use_container_width=True)

        else:
            st.info("No staff utilization data for selected filters.")

        st.divider()
        st.subheader("Key Findings")
        st.markdown(
            """
- **Staff distribution is heavily skewed across departments.** The department analysis charts show that while certain departments contain the vast majority of personnel, others carry a disproportionately high burden of total required flight hours.
- **Aircraft models dictate crewing requirements.** The aircraft staffing requirements chart reveals distinct differences in the required versus average used crew sizes across different airplane models, highlighting potential areas of over- or under-staffing for specific fleets.
- **Workloads fluctuate over time.** The temporal flying hours line chart indicates that the average hours logged per staff member vary by month, suggesting periods of peak operational intensity and seasonality.
- **Staff utilisation is unequal across the workforce.** The staff welfare analysis uses statistical thresholds (P10 and P90) to identify specific employees who are either overworked and require vacation or underused and available for additional assignments.

*Data source: Staff records aggregated via SQL JOINs with aircraft and flight usage data, enriched with department and assignment metrics.*
            """
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Revenue Analysis
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

        date_filtered = filter_by_date_range(location_filtered, start, end)
        metrics = compute_revenue_dashboard_metrics(date_filtered)
        total_revenue = metrics["total_revenue"]
        top_route = metrics["top_route"]
        top_city = metrics["top_city"]
        trend_df = metrics["trend_df"]
        class_df = metrics["class_df"]
        country_df = metrics["country_df"]

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
