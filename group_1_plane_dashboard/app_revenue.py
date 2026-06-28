from datetime import date

import plotly.express as px
import polars as pl
import streamlit as st

from revenue_analysis import (
    load_revenue_data,
    most_profitable_outgoing_route,
    most_revenue_perceived,
    revenue_class_analysis,
    revenue_per_country,
    revenue_trend_analysis,
    total_revenue_per_range,
)


ALL_OPTION = "All"


st.set_page_config(page_title="Plane Revenue Dashboard", layout="wide")


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

    revenue_tab, = st.tabs(["Revenue"])

    with revenue_tab:
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


build_revenue_tab()
