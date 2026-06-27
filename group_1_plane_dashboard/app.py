import streamlit as st
import polars as pl
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path

from analysis.ticket_revenue import load_data, filter_data
from analysis.staff import (
    load_staff_counts,
    load_staff_assignments,
    load_staff_usage,
    staff_global_kpis,
    aircraft_staff_requirements,
    route_staff_needs,
    department_stats,
    flying_hours_over_time,
    staff_utilisation
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
def get_staff_data() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    needed = [
        DATA_DIR / "q1_staff_counts.parquet", 
        DATA_DIR / "q2_staff_assignments.parquet", 
        DATA_DIR / "q3_staff_usage.parquet"
    ]
    if not all(p.exists() for p in needed):
        return pl.DataFrame(), pl.DataFrame(), pl.DataFrame()
    return load_staff_counts(), load_staff_assignments(), load_staff_usage()



# ── Revenue Tab Helpers ──
from datetime import date

import plotly.express as px
import polars as pl
import streamlit as st

from analysis.revenue_analysis import (
    load_revenue_data,
    most_profitable_outgoing_route,
    most_revenue_perceived,
    revenue_class_analysis,
    revenue_per_country,
    revenue_trend_analysis,
    total_revenue_per_range,
)


ALL_OPTION = "All"





@st.cache_data(show_spinner="Loading revenue data...")
def get_revenue_data() -> pl.DataFrame:
    df = pl.DataFrame()
    try:
        df = load_revenue_data()
    except Exception:
        pass
    return df


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


def date_bounds(df: pl.DataFrame) -> tuple[date, date]:
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
    metric_cols[0].metric("Total revenue", format_revenue(total_revenue))

    route_label = top_route.get("route", "No route")
    route_revenue = format_revenue(top_route.get("total_revenue"))
    if top_route.get("destination"):
        route_label = f"{route_label} to {top_route['destination']}"
    metric_cols[1].metric("Most profitable outgoing route", route_label, route_revenue)

    city_label = "No city"
    if top_city:
        city_label = f"{top_city.get('city')}, {top_city.get('country')}"
    metric_cols[2].metric(
        "Most revenue perceived",
        city_label,
        format_revenue(top_city.get("total_revenue")),
    )

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
            title="Revenue Trend",
            hovermode="x unified",
            margin=dict(l=0, r=0, t=48, b=0),
        )
        st.plotly_chart(trend_fig, use_container_width=True)

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


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["Revenue & Tax", "Staff Occupation", "Revenue Analysis"])


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
    counts_raw, assign_raw, usage_raw = get_staff_data()
    if counts_raw.is_empty() or assign_raw.is_empty():
        st.warning("Missing staff data Parquet files. Please run the extraction script manually (e.g. `python -m group_1_plane_dashboard.db.staff`) before using the dashboard.")
    else:

        # ── Sidebar filters (staff tab) ───────────────────────────────────────────
        st.sidebar.markdown("---")
        st.sidebar.subheader("Staff filters")

        all_years = sorted(assign_raw["year"].drop_nulls().unique().to_list())
        year_range = st.sidebar.select_slider(
            "Year range", options=all_years, value=(all_years[0], all_years[-1])
        )

        divisions = sorted(assign_raw["division"].drop_nulls().unique().to_list())
        selected_divisions = st.sidebar.multiselect("Division", divisions, default=divisions)

        # Apply filters
        filtered_assign = assign_raw.filter(
            pl.col("division").is_in(selected_divisions)
            & pl.col("year").is_between(year_range[0], year_range[1])
        )

        filtered_usage = usage_raw.filter(
            pl.col("departure").dt.year().is_between(year_range[0], year_range[1])
        )

        # Compute metrics
        kpis = staff_global_kpis(counts_raw, filtered_assign)
        aircraft_reqs = aircraft_staff_requirements(filtered_usage)
        route_needs = route_staff_needs(filtered_usage)
        dept_stats = department_stats(counts_raw, filtered_assign)
        temporal_hours = flying_hours_over_time(filtered_assign)
        util_df = staff_utilisation(filtered_assign)

        # ── Header & KPIs ─────────────────────────────────────────────────────────
        st.title("Staff Occupation & Requirements")
        st.markdown(
            "Comprehensive analysis of staff deployment, aircraft requirements, "
            "route gaps, and employee utilisation."
        )

        k1, k2, k3 = st.columns(3)
        k1.metric("Total Staff", f"{kpis['total_staff']:,}")
        k2.metric("Avg Distance per Staff", f"{kpis['avg_km_per_staff']:,.1f} km")
        k3.metric("Avg Hours per Staff", f"{kpis['avg_hours_per_staff']:,.1f} h")

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
        st.plotly_chart(air_fig, width="stretch")

        st.divider()

        # ── Chart: Routes Understaffed vs Overstaffed ─────────────────────────────
        st.subheader("Route Staffing Needs")
        st.caption(
            "Routes with Crew Gaps (Positive = Missing Crew, Negative = Overstaffed)."
        )

        col_under, col_over = st.columns(2)
        with col_under:
            st.markdown("**Most Understaffed Routes**")
            understaffed = route_needs.filter(pl.col("crew_gap") > 0).head(15)
            if len(understaffed) > 0:
                under_fig = px.bar(
                    understaffed.to_pandas(),
                    x="crew_gap", y="route_label", orientation="h",
                    color="crew_gap", color_continuous_scale="Reds",
                    labels={"crew_gap": "Missing Crew Slots", "route_label": ""}
                )
                under_fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(under_fig, width="stretch")
            else:
                st.info("No understaffed routes.")

        with col_over:
            st.markdown("**Most Overstaffed Routes**")
            overstaffed = route_needs.filter(pl.col("crew_gap") < 0).sort("crew_gap").head(15)
            if len(overstaffed) > 0:
                over_fig = px.bar(
                    overstaffed.to_pandas(),
                    x="crew_gap", y="route_label", orientation="h",
                    color="crew_gap", color_continuous_scale="Blues_r",
                    labels={"crew_gap": "Surplus Crew Slots", "route_label": ""}
                )
                over_fig.update_layout(yaxis={"categoryorder": "total descending"})
                st.plotly_chart(over_fig, width="stretch")
            else:
                st.info("No overstaffed routes.")

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
            st.plotly_chart(d1_fig, width="stretch", key="dept_staff")

        with col_d2:
            d2_fig = px.bar(
                dept_stats.sort("total_hours_required", descending=True).head(10).to_pandas(),
                x="total_hours_required", y="department", orientation="h",
                color_discrete_sequence=["#2ca02c"],
                labels={"total_hours_required": "Total Hours", "department": ""}
            )
            d2_fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(d2_fig, width="stretch", key="dept_hours")

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
        st.plotly_chart(time_fig, width="stretch")

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
                st.dataframe(overworked.to_pandas(), width="stretch")

            with col_underw:
                st.markdown("**Underused (Needs More Hours)**")
                underworked = util_df.filter(pl.col("is_underused")).select(
                    ["firstnme", "lastname", "department", "total_hours"]
                )
                st.dataframe(underworked.to_pandas(), width="stretch")
        else:
            st.info("No staff utilization data for selected filters.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Revenue Analysis
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    build_revenue_tab()

